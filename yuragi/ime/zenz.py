"""Conversion with zenz-v2.5, the way Zenzai uses it (Space only).

The engine uses it unless the setting lm_rescore turns it off. Nothing here
imports torch/transformers until a model is constructed, so a session without
it has no new dependency.

Per kana run (Zenzai: AzooKeyKanaKanjiConverter, all_zenzai and
ZenzCandidateEvaluator):
1. The draft is the dictionary 1-best (decode_tokens).
2. zenz reads its prompt and the draft in one forward. Where the model's
   greedy next token first differs from the draft's, the draft is wrong from
   there: the constraint becomes the draft's bytes so far plus the model's
   token (or exactly the bytes so far, if the model's token is </s>). If no
   token differs, the draft passes.
3. The dictionary 1-best under that prefix constraint (decode_prefix) is the
   next draft, reviewed again. At most `steps` reviews; after the last one
   the latest draft stands. A constraint no dictionary path satisfies keeps
   the current draft.
So zenz writes the surface and the dictionary keeps it to words of the
reading; the pick is a dictionary path like the 1-best, and the bunsetsu,
candidate lists and learning work on it unchanged.

Prompt (zenz-v2; Zenzai's ZenzPromptBuilder .v2, Docs/zenzai.md):
  U+EE00 <reading in katakana> [U+EE02 <left context, last 40 chars>] U+EE01
then the output. Spaces become U+3000 and newlines are dropped; prompt and
draft are tokenized separately; no <s> (tokenizer_config.json: add_bos_token
false). The reading is the draft's: the thumb sides are not known, and a
constraint may change the reading only where the dictionary agrees.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Protocol

from yuragi.lattice.decode import DecodeResult
from yuragi.lattice.mozc_dict import BOS_ID, MozcLex, left_id_after
from yuragi.lattice.token_viterbi import decode_prefix, decode_tokens, nbest_tokens

from .bunsetsu import segments_from

DEFAULT_MODEL = "Miwa-Keita/zenz-v2.5-medium"
DEFAULT_ALPHA = 1.0
# Measured on Windows (zenz medium, 200 own items; 2026-11-19): k 8 or 16
# picks no better than 4, a second review adds one right answer, and 4 threads
# is the fastest CPU setting. The same defaults on a GPU: it changes the speed,
# not the picks.
DEFAULT_K = 4
DEFAULT_STEPS = 1
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

    def reading_nll(self, readings: list[str]) -> list[float]: ...


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
        self._readings: dict[str, float] = {}

    def _ids(self, rows: list[list[int]]):
        return self.torch.tensor(rows, device=self.device)

    def _prompt_state(self, text: str):
        """KV cache and greedy next token after the prompt (kept for the next review)."""
        if self._prompt is None or self._prompt[0] != text:
            ids = self.tok.encode(text, add_special_tokens=False)
            out = self.model(input_ids=self._ids([ids]), use_cache=True)
            self._prompt = text, out.past_key_values, int(out.logits[0, -1].argmax())
        return self._prompt[1], self._prompt[2]

    def reading_nll(self, readings: list[str]) -> list[float]:
        """NLL (nats) of each reading as zenz's input: the prompt without context.

        zenz models its input too: a reading that is not Japanese (a wrong
        thumb side, あとなおちゃ) costs several nats more than the right one."""
        todo = [r for r in dict.fromkeys(readings) if r not in self._readings]
        if todo:
            seqs = [self.tok.encode(prompt("", r), add_special_tokens=False) for r in todo]
            width = max(map(len, seqs))
            # Right padding: the causal mask keeps it out of every row's score.
            ids = [s + [self.eos] * (width - len(s)) for s in seqs]
            with self.torch.inference_mode():
                lp = self.torch.log_softmax(
                    self.model(input_ids=self._ids(ids)).logits.float(), -1)
            for row, (r, s) in enumerate(zip(todo, seqs)):
                self._readings[r] = -float(lp[row, list(range(len(s) - 1)), s[1:]].sum())
        result = [self._readings[r] for r in readings]
        while len(self._readings) > 4096:
            del self._readings[next(iter(self._readings))]
        return result

    def review(self, context: str, reading: str, draft: str,
               accepted: bytes) -> tuple[bytes, bool] | None:
        """Zenzai's candidate evaluation: None if the draft passes, else
        (prefix constraint, exact). Differences inside the accepted constraint
        (the draft may tokenize it differently from the model) do not count."""
        ids = self.tok.encode(normalize(draft), add_special_tokens=False)
        with self.torch.inference_mode():
            past, first = self._prompt_state(prompt(context, reading))
            size = past.get_seq_length()
            logits = self.model(input_ids=self._ids([ids[:-1]]), past_key_values=past,
                                use_cache=True).logits[0] if len(ids) > 1 else None
            past.crop(size)
        guesses = [first] + (logits.argmax(-1).tolist() if logits is not None else [])
        done = b""
        for token, guess in zip(ids, guesses):
            if guess != token and len(done) >= len(accepted):
                return (done, True) if guess == self.eos else (done + self.bytes[guess], False)
            done += self.bytes[token]
        return None


@dataclass
class ZenzConverter:
    """Pick, per kana run, a reading and then the dictionary path zenz writes."""
    model: Reviewer
    alpha: float = DEFAULT_ALPHA
    k: int = DEFAULT_K
    steps: int = DEFAULT_STEPS
    last: dict = field(default_factory=dict)  # stats of the most recent conversion

    def reading(self, best: DecodeResult, tokens: list[dict], lex: MozcLex,
                left_id: int) -> DecodeResult:
        """The cheapest path of the reading with the lowest
        (cost - 1-best cost) + alpha * 500 * zenz's NLL of the reading,
        among the 1-best and the readings of the k-best surfaces."""
        nb, _ = nbest_tokens(tokens, lex, k=self.k, left_id=left_id)
        paths: dict[str, DecodeResult] = {}
        for d in [best] + nb:
            paths.setdefault(d.reading, d)
        if len(paths) < 2:
            return best
        nlls = self.model.reading_nll(list(paths))
        # min() keeps the earliest on ties, i.e. the 1-best's reading.
        return min(zip(paths.values(), nlls),
                   key=lambda dn: (dn[0].score - best.score)
                   + self.alpha * COST_PER_NAT * dn[1])[0]

    def rescore(self, context: str, best: DecodeResult, tokens: list[dict], lex: MozcLex,
                left_id: int = BOS_ID, learning=None) -> DecodeResult:
        t0 = time.perf_counter()
        draft = self.reading(best, tokens, lex, left_id)
        t1 = time.perf_counter()
        # zenz writes for this reading; its constraints must not move it.
        fixed = [{"kind": "plain", "kana": kana} for kana in draft.reading]
        accepted, reviews = b"", 0
        while reviews < self.steps:
            reviews += 1
            fix = self.model.review(context, draft.reading, draft.surface, accepted)
            if fix is None:
                break
            accepted, exact = fix
            found = decode_prefix(fixed, lex, accepted, exact=exact, spell=spell,
                                  learning=learning, left_id=left_id)
            if found is None:
                break
            draft = found
        t2 = time.perf_counter()
        for key, value in (("reading_ms", (t1 - t0) * 1000), ("zenz_ms", (t2 - t1) * 1000),
                           ("runs", 1), ("reviews", reviews),
                           ("changed", draft.surface != best.surface)):
            self.last[key] = self.last.get(key, 0) + value
        return draft

    def warm_up(self) -> None:
        self.model.review("", "あ", "あ", b"")


def conversion_picks(parts, lex: MozcLex, learning, lm_context: str,
                     converter: ZenzConverter, cancelled=lambda: False, *,
                     left_id: int = BOS_ID) -> list[DecodeResult] | None:
    """The LM part of ImeSession._refresh(rescore=True): one pick per kana run.

    The left context follows _refresh's loop exactly, so the synchronous and
    the worker paths pick the same results. None if cancelled.
    """
    picks: list[DecodeResult] = []
    text = ""
    for part in parts:
        if isinstance(part, str):  # literal
            text += part
            left_id = left_id_after(part, lex)
            continue
        if cancelled():
            return None
        dec, _ = decode_tokens(part, lex, learning=learning, left_id=left_id)
        dec = converter.rescore(lm_context + text, dec, part, lex, left_id, learning)
        picks.append(dec)
        segs = segments_from(dec.pieces, 0, lex, learning=learning)
        text += "".join(s.selected.surface for s in segs)
    return picks
