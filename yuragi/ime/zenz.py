"""Conversion with zenz-v2.5, the way Zenzai uses it (Space only).

The engine uses it unless the setting lm_rescore turns it off. Nothing here
imports torch/transformers until a model is constructed, so a session without
it has no new dependency.

Per kana run (Zenzai: AzooKeyKanaKanjiConverter, all_zenzai and
ZenzCandidateEvaluator):
1. Choose a reading from the dictionary paths using their costs and the
   likelihood of the full prompt with left context. Its representative path
   becomes the draft.
2. zenz reads its prompt and the draft in one forward. Where the model's
   greedy next token first differs from the draft's, the draft is wrong from
   there: the constraint becomes the draft's bytes so far plus the model's
   token (or exactly the bytes so far, if the model's token is </s>). If no
   token differs, the draft passes.
3. The dictionary 1-best under that prefix constraint (decode_prefix) is the
   next draft, reviewed again, until a draft passes. Each constraint is
   longer than the last or the same one made exact, so this ends within the
   draft's byte length. The first review of every kana run always happens;
   further ones stop once the conversion's review budget (shared by its kana
   runs) has passed, or when the job is cancelled, and the latest draft
   stands. `steps` can cap the reviews per run. A constraint no dictionary
   path satisfies keeps the current draft.
Consecutive reviews reuse the KV cache of the prompt and of the token prefix
the new draft shares with the previous one.
So zenz writes the surface and the dictionary keeps it to words of the
reading; the pick is a dictionary path like the 1-best, and the bunsetsu,
candidate lists and learning work on it unchanged.

Prompt (zenz-v2; Zenzai's ZenzPromptBuilder .v2, Docs/zenzai.md):
  U+EE00 <reading in katakana> [U+EE02 <left context, last 40 chars>] U+EE01
then the output. Spaces become U+3000 and newlines are dropped; prompt and
draft are tokenized separately; no <s> (tokenizer_config.json: add_bos_token
false). Reading selection scores the prompt through the output start marker.
Surface review keeps the selected reading fixed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import time
from typing import Protocol

from yuragi.lattice.decode import DecodeResult
from yuragi.lattice.mozc_dict import BOS_ID, MozcLex, left_id_after
from yuragi.lattice.token_viterbi import decode_prefix, decode_tokens, nbest_tokens

from .bunsetsu import (Bunsetsu, Segment, ZenzEvidence, learned_row,
                       normal_bunsetsu, segments_from)

DEFAULT_MODEL = "Miwa-Keita/zenz-v2.5-medium"
DEFAULT_ALPHA = 1.0
# Measured on Windows (zenz medium, 200 own items; Sadao 2026-11-19): k 8 or 16
# picks no better than 4, and 4 threads is the fastest CPU setting. The same
# defaults on a GPU: it changes the speed, not the picks.
DEFAULT_K = 4
DEFAULT_STEPS = None  # reviews per kana run: until the draft passes
# Reviews after a run's first stop this long after the conversion started:
# lm_async.DEADLINE_MS (600) less one more review and the remaining runs'
# first reviews. A GPU (median 30 ms per conversion) does not reach it.
REVIEW_BUDGET_MS = 400
DEFAULT_THREADS = 4  # torch CPU threads
COST_PER_NAT = 500  # Mozc cost scale: cost ~ -500 ln p
CONTEXT_CHARS = 200  # left context kept per connection (characters)
PROMPT_CONTEXT_CHARS = 40  # what the prompt takes of it (Zenzai's default)


def normalize(text: str) -> str:
    return text.replace(" ", "　").replace("\n", "")


def spell(surface: str) -> bytes:
    """A surface as the bytes zenz writes."""
    return normalize(surface).encode()


def prompt(context: str, reading: str) -> str:
    reading = "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in reading)
    context = normalize(context)[-PROMPT_CONTEXT_CHARS:]
    return normalize("" + reading + ("" + context if context else "") + "")


class Reviewer(Protocol):
    def review(self, context: str, reading: str, draft: str,
               accepted: bytes) -> tuple[bytes, bool] | None: ...

    def reading_nll(self, context: str, readings: list[str]) -> list[float]: ...


def cuda_devices() -> tuple[str, ...]:
    """Enumerate the CUDA devices visible to this process in PyTorch's order."""
    import torch

    try:
        return tuple(f"cuda:{index}" for index in range(torch.cuda.device_count()))
    except (RuntimeError, OSError):
        return ()


class ZenzModel:
    def __init__(self, model: str = DEFAULT_MODEL, *, threads: int | None = DEFAULT_THREADS,
                 device: str = "cpu") -> None:
        import torch
        from transformers import AutoModelForCausalLM, GPT2Tokenizer

        if threads:
            torch.set_num_threads(threads)
        self.torch = torch
        # float32 on either device: the GPU changes the speed, not the picks.
        self.device = device
        # local_files_only: the IME never goes to the network (DESIGN「エンジン」);
        # the model is fetched at install (packaging/fetch_model.py).
        self.tok = GPT2Tokenizer.from_pretrained(model, local_files_only=True)
        self.model = AutoModelForCausalLM.from_pretrained(
            model, attn_implementation="eager", local_files_only=True).to(self.device).eval()
        # config.json's eos (2) is <s> in vocab.json; </s> is the tokenizer's.
        self.eos = self.tok.eos_token_id
        self.bytes = {i: bytes(self.tok.byte_decoder[c] for c in token)
                      for token, i in self.tok.get_vocab().items()}
        self._prompt: tuple[str, object, int] | None = None  # text, KV cache, next token
        # The last reviewed draft's token ids and greedy guesses under the
        # current prompt; the KV cache then holds the prompt and ids[:-1].
        self._draft: tuple[list[int], list[int]] | None = None
        self._readings: dict[bytes, float] = {}

    def _ids(self, rows: list[list[int]]):
        return self.torch.tensor(rows, device=self.device)

    def _prompt_state(self, text: str):
        """KV cache and greedy next token after the prompt (kept for the next review)."""
        if self._prompt is None or self._prompt[0] != text:
            ids = self.tok.encode(text, add_special_tokens=False)
            out = self.model(input_ids=self._ids([ids]), use_cache=True)
            self._prompt = text, out.past_key_values, int(out.logits[0, -1].argmax())
            self._draft = None
        return self._prompt[1], self._prompt[2]

    def reading_nll(self, context: str, readings: list[str]) -> list[float]:
        """Sum next-token NLLs (nats) through the end of each full prompt."""
        keys, todo = [], {}
        for reading in readings:
            text = prompt(context, reading)
            key = sha256(text.encode("utf-8")).digest()
            keys.append(key)
            if key not in self._readings:
                todo[key] = text
        if todo:
            seqs = [self.tok.encode(text, add_special_tokens=False) for text in todo.values()]
            width = max(map(len, seqs))
            # With causal attention, padding to the right cannot affect the prompt.
            ids = [seq + [self.eos] * (width - len(seq)) for seq in seqs]
            with self.torch.inference_mode():
                lp = self.torch.log_softmax(
                    self.model(input_ids=self._ids(ids), use_cache=False).logits.float(), -1)
                for row, (key, seq) in enumerate(zip(todo, seqs)):
                    self._readings[key] = -float(lp[row, list(range(len(seq) - 1)), seq[1:]].sum())
        result = [self._readings[key] for key in keys]
        while len(self._readings) > 4096:
            del self._readings[next(iter(self._readings))]
        return result

    def review(self, context: str, reading: str, draft: str,
               accepted: bytes) -> tuple[bytes, bool] | None:
        """Zenzai's candidate evaluation: None if the draft passes, else
        (prefix constraint, exact). Differences inside the accepted constraint
        (the draft may tokenize it differently from the model) do not count."""
        ids = self.tok.encode(normalize(draft), add_special_tokens=False)
        text = prompt(context, reading)
        with self.torch.inference_mode():
            guesses = self._guesses(text, ids)
        done = b""
        for token, guess in zip(ids, guesses):
            if guess != token and len(done) >= len(accepted):
                return (done, True) if guess == self.eos else (done + self.bytes[guess], False)
            done += self.bytes[token]
        return None

    def _guesses(self, text: str, ids: list[int]) -> list[int]:
        """The greedy next token at each position of ids after the prompt text.

        The guess at position i depends on ids[:i] only, so the guesses and KV
        of the prefix shared with the previous draft are kept."""
        past, first = self._prompt_state(text)
        keep, guesses, size = 0, [first], past.get_seq_length()
        if self._draft is not None:
            old, old_guesses = self._draft
            size -= max(len(old) - 1, 0)  # the cache holds the prompt and old[:-1]
            lcp = 0
            for a, b in zip(old, ids):
                if a != b:
                    break
                lcp += 1
            keep = max(0, min(lcp, len(old) - 1, len(ids) - 1))
            guesses = old_guesses[:keep + 1]
        past.crop(size + keep)
        self._draft = None  # until the cache matches again
        if keep < len(ids) - 1:
            logits = self.model(input_ids=self._ids([ids[keep:-1]]), past_key_values=past,
                                use_cache=True).logits[0]
            guesses = guesses + logits.argmax(-1).tolist()
        self._draft = ids, guesses
        return guesses


@dataclass
class ZenzConverter:
    """Pick, per kana run, a reading and then the dictionary path zenz writes."""
    model: Reviewer
    alpha: float = DEFAULT_ALPHA
    k: int = DEFAULT_K
    steps: int | None = DEFAULT_STEPS  # cap on reviews per kana run
    review_budget_ms: float = REVIEW_BUDGET_MS
    last: dict = field(default_factory=dict)  # stats of the most recent conversion

    def reading(self, context: str, best: DecodeResult, tokens: list[dict], lex: MozcLex,
                left_id: int) -> DecodeResult:
        """Compare the first path per reading, starting with the dictionary 1-best."""
        nb, _ = nbest_tokens(tokens, lex, k=self.k, left_id=left_id)
        paths: dict[str, DecodeResult] = {}
        for d in [best] + nb:
            paths.setdefault(d.reading, d)
        if len(paths) < 2:
            return best
        nlls = self.model.reading_nll(context, list(paths))
        # min() keeps the earliest among the paths tied for lowest score.
        return min(zip(paths.values(), nlls),
                   key=lambda dn: (dn[0].score - best.score)
                   + self.alpha * COST_PER_NAT * dn[1])[0]

    def rescore(self, context: str, best: DecodeResult, tokens: list[dict], lex: MozcLex,
                left_id: int = BOS_ID, learning=None, *, until: float | None = None,
                cancelled=lambda: False) -> tuple[DecodeResult, int]:
        """Review until the draft passes. Reviews after the first stop at
        `until` (perf_counter seconds; default: the budget from now) or on
        cancellation."""
        t0 = time.perf_counter()
        if until is None:
            until = t0 + self.review_budget_ms / 1000
        draft = self.reading(context, best, tokens, lex, left_id)
        t1 = time.perf_counter()
        # zenz writes for this reading; its constraints must not move it.
        fixed = [{"kind": "plain", "kana": kana} for kana in draft.reading]
        accepted, reviews, supported, cut = b"", 0, 0, 0
        while self.steps is None or reviews < self.steps:
            if reviews and (time.perf_counter() > until or cancelled()):
                cut = 1
                break
            reviews += 1
            fix = self.model.review(context, draft.reading, draft.surface, accepted)
            if fix is None:
                supported = len(spell(draft.surface))
                break
            accepted, exact = fix
            found = decode_prefix(fixed, lex, accepted, exact=exact, spell=spell,
                                  learning=learning, left_id=left_id)
            if found is None:
                break
            draft = found
            supported = len(accepted)
        t2 = time.perf_counter()
        for key, value in (("reading_ms", (t1 - t0) * 1000), ("zenz_ms", (t2 - t1) * 1000),
                           ("runs", 1), ("reviews", reviews), ("cut", cut),
                           ("changed", draft.surface != best.surface)):
            self.last[key] = self.last.get(key, 0) + value
        return draft, supported

    def warm_up(self) -> None:
        self.model.review("", "あ", "あ", b"")


@dataclass
class KanaRun:
    segments: list[Segment]
    word_starts: set[int]


def conversion_picks(parts, lex: MozcLex, learning, lm_context: str,
                     converter: ZenzConverter | None, cancelled=lambda: False, *,
                     left_id: int = BOS_ID, prev: Bunsetsu | None = None,
                     repeat: bool = False) -> list[KanaRun] | None:
    """Decode and choose the displayed segments once, including for the LM prompt.

    Each run has absolute token offsets. None means the worker was cancelled.
    """
    picks: list[KanaRun] = []
    text = ""
    if converter is not None:
        until = time.perf_counter() + converter.review_budget_ms / 1000
    offset = 0
    for part in parts:
        if isinstance(part, str):
            text += part
            left_id = left_id_after(part, lex)
            prev = None
            offset += 1
            continue
        if cancelled():
            return None
        dec, _ = decode_tokens(part, lex, learning=learning, left_id=left_id)
        supported = 0
        if converter is not None:
            dec, supported = converter.rescore(lm_context + text, dec, part, lex,
                                               left_id, learning, until=until,
                                               cancelled=cancelled)
            if cancelled():
                return None
        segments = segments_from(dec.pieces, offset, lex)
        if learning is not None:
            reviewed = text
            displayed = text
            end = 0
            standalone = repeat and len(parts) == len(segments) == 1
            for segment in segments:
                original = segment.selected
                if supported:
                    end += len(spell(original.surface))
                    if end <= supported and displayed == reviewed:
                        segment.zenz = ZenzEvidence(reviewed, original.reading, original.surface)
                row = learning.head(original.reading, prev, repeat=standalone,
                                    zenz=segment.zenz.surface if segment.zenz else None)
                if row is not None:
                    segment.selected = learned_row(row)
                prev = normal_bunsetsu(segment.selected)
                reviewed += original.surface
                displayed += segment.selected.surface
            text = displayed
        else:
            text += "".join(s.selected.surface for s in segments)
        picks.append(KanaRun(segments, {offset + p.start for p in dec.pieces if not p.literal}))
        offset += len(part)
    return picks
