"""IME session: chord FSM + Mozc lattice decode + composition.

Literal characters split the lattice into kana runs and set the next run's left POS.
The FSM's timing and chord decisions are unchanged. The digit row and the
symbol keys are chord keys too: their plain and thumb faces are literals,
and Shift gives the full-width upper engraving.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from itertools import islice
from math import isfinite
import sys
import time
from typing import Callable
import unicodedata

from yuragi.chord.fsm import AmbShift, ChordFsm, Plain, ThumbTap, Token
from yuragi.chord.keys import (
    ANSI_SHIFTED, SHIFT_VKS, SHORTCUT_VKS, VK_BACK, VK_ESCAPE, VK_RETURN, classify, literal_character,
)
from yuragi.lattice.alternation import SIDES, Plan, face_of, restrict
from yuragi.lattice.expand import is_literal_face, literal_text
from yuragi.lattice.mozc_dict import MozcLex, left_id_after, load_lex
from yuragi.lattice.table import load_table
from .bunsetsu import (BOS_ID, PAGE_SIZE, Bunsetsu, Candidate, CandidateOrder, CandidateStream,
                       Segment, arranged_candidates, candidates, dictionary_candidates,
                       learned_row, normal_bunsetsu, without_heads)
from .learning import LearningStore, LearningView
from .zenz import CONTEXT_CHARS, KanaRun, ZenzConverter, conversion_picks, prompt
from .numbers import is_digit, number_spellings
from .personal import PersonalLexicon
from .symbols import symbol_spellings
from .symbol_readings import load_symbols
from .predict import DEFAULT_MODE as DEFAULT_PREDICTION, MAX_TAILS, ReadingIndex, predict

VK_LEFT = 0x25
VK_RIGHT = 0x27
VK_PRIOR = 0x21
VK_NEXT = 0x22
VK_UP = 0x26
VK_DOWN = 0x28
VK_F6 = 0x75
VK_F7 = 0x76
VK_F8 = 0x77
VK_F9 = 0x78
VK_F10 = 0x79
SCRIPT_VKS = (VK_F6, VK_F7, VK_F8, VK_F9, VK_F10)  # the one-shot spellings
VK_TAB = 0x09
CTRL_VKS = {0x11, 0xA2, 0xA3}  # Ctrl, left and right
PREDICTION = "predict"  # Segment.context of the predictions' segment
IDEOGRAPHIC_SPACE = "\u3000"  # Space with no input (全角の空白)


@dataclass(frozen=True, slots=True)
class Literal:
    text: str

    def __post_init__(self) -> None:
        if len(self.text) != 1:
            raise ValueError("a literal token must contain exactly one character")


_HALF_KATAKANA: dict[str, str] = {}
for _code in range(0xFF66, 0xFF9E):
    _half = chr(_code)
    _HALF_KATAKANA.setdefault(unicodedata.normalize("NFKC", _half), _half)
    for _mark in ("\uff9e", "\uff9f"):
        _full = unicodedata.normalize("NFKC", _half + _mark)
        if len(_full) == 1:
            _HALF_KATAKANA.setdefault(_full, _half + _mark)


def half_katakana(hiragana: str) -> str:
    """F8: ひらがな → ﾊﾝｶｸｶﾀｶﾅ (a kana with no half-width form stays full-width)."""
    out = []
    for ch in hiragana:
        kata = chr(ord(ch) + 0x60) if "ぁ" <= ch <= "ゖ" else ch
        out.append(_HALF_KATAKANA.get(kata, kata))
    return "".join(out)


def alnum_spelling(keys: str, current: str | None, *, full: bool) -> str:
    """F9/F10: the typed keys; again on the same width cycles the letter case."""
    forms = [keys.lower(), keys.upper(), keys[:1].upper() + keys[1:].lower()]
    if full:
        forms = [to_full_width(f) for f in forms]
    if current in forms:
        return forms[(forms.index(current) + 1) % len(forms)]
    return forms[0]


def alnum_character(vk: int, key: str, shift: bool) -> str:
    """A character key's engraving in half width (英数の続き): the key id is
    the lower engraving; Shift gives the upper one (A-Z, ANSI_SHIFTED)."""
    if not shift:
        return key
    if ord("A") <= vk <= ord("Z"):
        return chr(vk)
    return ANSI_SHIFTED[vk]


def half_width_ascii(text: str) -> bool:
    """Half-width ASCII without the space: what Shift+letter and 英数の続き type."""
    return bool(text) and all("!" <= c <= "~" for c in text)


def to_full_width(text: str) -> str:
    return "".join(chr(ord(c) + 0xFEE0) if "!" <= c <= "~" else c for c in text)


def to_lattice_token(tok: Token | Literal, table: dict) -> dict | None:
    if isinstance(tok, Literal):
        return {"kind": "literal", "text": tok.text}
    if isinstance(tok, Plain):
        kana = table["keys"].get(tok.key, {}).get("plain")
        if not kana:
            return None
        if is_literal_face(kana):
            return {"kind": "literal", "text": literal_text(kana)}
        return {"kind": "plain", "key": tok.key, "kana": kana}
    if isinstance(tok, AmbShift):
        faces = {}
        for face in ("left", "right"):
            k = table["keys"].get(tok.key, {}).get(face)
            if k:
                faces[face] = k
        if not faces:
            return None
        texts = set(faces.values())
        if len(texts) == 1 and is_literal_face(next(iter(texts))):
            # A symbol key's thumb face is the same for either thumb: the chord is that literal whichever side is read.
            return {"kind": "literal", "text": literal_text(texts.pop())}
        kind = "amb" if len(faces) > 1 else "shift"
        token = {"kind": kind, "key": tok.key, "faces": faces}
        if tok.press is not None:
            # Where the chord was typed: the conversion alternates the thumbs of one press.
            token.update(press=tok.press, turn=tok.turn)
        return token
    return None


@dataclass(frozen=True)
class ConversionRequest:
    """Everything the LM worker needs for one conversion, captured at ThumbTap."""
    parts: list  # ImeSession._parts()
    lm_context: str
    left_id: int
    learning: LearningView | None
    key: tuple
    prev: Bunsetsu | None = None
    repeat: bool = False
    personal_revision: int | None = None

    def decode(self, lex: MozcLex, converter: ZenzConverter | None = None,
               *, cancelled=lambda: False) -> list[KanaRun] | None:
        until = (time.perf_counter() + converter.review_budget_ms / 1000
                 if converter is not None else None)
        picks = conversion_picks(
            self.parts, lex, self.learning, self.lm_context, converter, cancelled=cancelled,
            left_id=self.left_id, prev=self.prev, repeat=self.repeat, until=until)
        if converter is None or not picks:
            return picks
        if converter.rank_candidates and not cancelled() and time.perf_counter() < until:
            self._rank_candidates(lex, converter, picks, until, cancelled)
        return None if cancelled() else picks

    def _rank_candidates(self, lex: MozcLex, converter: ZenzConverter,
                         picks: list[KanaRun], until: float, cancelled) -> None:
        lattice = [token for part in self.parts for token in (
            [{"kind": "literal", "text": part}] if isinstance(part, str) else part)]
        segments = display_segments(self.parts, picks)
        left_text = self.lm_context
        repeat = self.repeat and len(segments) == 1
        for index, segment in enumerate(segments):
            context = left_text
            left_text += segment.selected.surface
            if segment.literal:
                continue
            if cancelled() or time.perf_counter() >= until:
                break
            pins, left, right = candidate_inputs(lattice, segments, index, self.left_id, lex)
            prev = previous_bunsetsu(segments, index, self.prev)
            heads = candidate_heads(segment, self.learning, prev, repeat)
            tokens = restrict(lattice, segment.start, segment.end, pins)
            dictionary = dictionary_candidates(tokens, lex, left, right, learning=self.learning)
            rows = tuple(islice(without_heads(dictionary, heads), PAGE_SIZE))
            if cancelled() or time.perf_counter() >= until:
                break
            if len(rows) < 2:
                continue
            started = time.perf_counter()
            try:
                scores = converter.model.candidate_nll(context, rows)
            except RuntimeError as exc:
                print(f"LM candidate scoring failed ({type(exc).__name__})",
                      file=sys.stderr, flush=True)
                continue
            finished = time.perf_counter()
            for key, value in (("candidate_ms", (finished - started) * 1000),
                               ("candidate_rows", len(rows))):
                converter.last[key] = converter.last.get(key, 0) + value
            if finished >= until or cancelled():
                break
            if not all(map(isfinite, scores)):
                continue
            permutation = tuple(sorted(range(len(rows)), key=scores.__getitem__))
            if permutation != tuple(range(len(rows))):
                scope = candidate_context(segment, pins, left, right, self.learning,
                                          self.personal_revision, prev, repeat)
                segment.order = CandidateOrder(
                    (scope, prompt(context, segment.selected.reading)), rows, permutation)


def display_segments(parts: list, picks: list[KanaRun] | None) -> list[Segment]:
    runs = iter(picks) if picks is not None else None
    segments: list[Segment] = []
    offset = 0
    for part in parts:
        if isinstance(part, str):
            last = segments[-1] if segments else None
            if (half_width_ascii(part) and last is not None and last.literal
                    and half_width_ascii(last.selected.reading)):
                # 英数の続き: the half-width run is one clause, as digits are.
                text = last.selected.reading + part
                last.end += 1
                last.selected = Candidate(text, text, 0, BOS_ID, BOS_ID, "literal")
            elif is_digit(part) and last is not None and last.selected.kind == "number":
                digits = last.selected.reading + part
                last.end += 1
                last.selected = Candidate(digits, digits, 0, BOS_ID, BOS_ID, "number")
            else:
                segments.append(Segment(offset, offset + 1, Candidate(
                    part, part, 0, BOS_ID, BOS_ID, "number" if is_digit(part)
                    else "literal"), literal=True))
            offset += 1
        else:
            if runs is not None:
                segments.extend(next(runs).segments)
            offset += len(part)
    return segments


def candidate_inputs(lattice: list[dict], segments: list[Segment], index: int,
                     left_id: int, lex: MozcLex):
    segment = segments[index]
    before = segments[index - 1] if index > 0 else None
    left = (left_id if before is None
            else left_id_after(before.selected.reading, lex) if before.literal
            else before.selected.rid)
    right = (segments[index + 1].selected.lid
             if index + 1 < len(segments) and not segments[index + 1].literal else BOS_ID)
    # A press crossing the segment's boundary keeps its neighbors' direction.
    pins = press_pins(lattice, segment.start, segment.end,
                      (s for k, s in enumerate(segments) if k != index))
    return pins, left, right


def press_pins(lattice: list[dict], start: int, end: int,
               others) -> dict[int, frozenset[str]]:
    """Directions that the selections of other segments give the presses of
    [start, end): a press that crosses a boundary keeps one direction."""
    plan = Plan(lattice)
    presses = {plan.press[i] for i in range(start, end)} - {None}
    pins: dict[int, frozenset[str]] = {}
    if presses:
        for other in others:
            for press, dirs in plan.directions(other.start, other.end,
                                               other.selected.reading).items():
                if press in presses:
                    pins[press] = pins.get(press, SIDES) & dirs
    return pins


def previous_bunsetsu(segments: list[Segment], index: int, prev: Bunsetsu | None):
    return normal_bunsetsu(segments[index - 1].selected) if index > 0 else prev


def candidate_heads(segment: Segment, learning: LearningView | None,
                    prev: Bunsetsu | None, repeat: bool) -> tuple[Candidate | None, Candidate | None]:
    confirmed = segment.zenz.candidate if segment.zenz is not None else None
    row = (learning.head(segment.selected.reading, prev, repeat=repeat,
                         zenz=confirmed.surface if confirmed is not None else None)
           if learning is not None else None)
    learned = learned_row(row) if row is not None else None
    if learned is not None and confirmed is not None and learned.surface == confirmed.surface:
        confirmed = None
    return learned, confirmed


def candidate_context(segment: Segment, pins: dict, left: int, right: int,
                      learning: LearningView | None, personal_revision: int | None,
                      prev: Bunsetsu | None, repeat: bool) -> tuple:
    return (segment.start, segment.end, left, right, pins,
            learning.revision if learning is not None else None, personal_revision,
            segment.selected.reading, prev, repeat, segment.zenz)


@dataclass
class CommitContext:
    tail: str
    right_id: int
    bunsetsu: Bunsetsu | None
    standalone: bool
    seq: int | None = None  # assigned when the reply carrying the commit is built


def _append_context(context: str, text: str) -> str:
    context += text
    return context[-CONTEXT_CHARS:] if len(context) > 4 * CONTEXT_CHARS else context


@dataclass
class ImeSession:
    fsm: ChordFsm = field(default_factory=ChordFsm)
    direct: bool = False
    tokens: list[Token | Literal] = field(default_factory=list)
    composition: str = ""
    converted: bool = False
    candidates: list[str] = field(default_factory=list)
    cand_index: int = 0
    segments: list[Segment] = field(default_factory=list)
    focus: int = -1
    candidate_page: int = 0
    candidate_kinds: list[str] = field(default_factory=list)
    has_next_page: bool = False
    _learning: LearningStore | None = None
    _learning_view: LearningView | None = None
    _display_key: tuple | None = None
    _left_bunsetsu: Bunsetsu | None = None
    _repeat: bool = False  # the preceding commit was one independent bunsetsu
    _partial: bool = False  # this input is the remainder of a partial commit
    # The LM (zenz), off unless a converter is given (server --lm-rescore).
    lm: ZenzConverter | None = None
    # Resident pipeline only: a ThumbTap leaves the LM pick to a worker.
    lm_deferred: bool = False
    _await: ConversionRequest | None = None  # conversion waiting for the worker
    _continuation: Callable[[], str | None] | None = None  # rest of that key event
    _committed_context: str = ""  # only text committed by this connection
    _lm_context: str = ""  # left text for the current input
    _left_id: int = BOS_ID
    _last_commit: CommitContext | None = None
    _table: dict = field(default_factory=dict)
    _lex: MozcLex | None = None
    _symbols: dict[str, tuple[str, ...]] | None = None  # reading → symbols, shared
    _modifiers: set[int] = field(default_factory=set)
    # A symbol chord inside a press splits it: the chords after it are another
    # press (no press crosses a literal, alternation.py). press → its alias.
    _press_alias: dict[int, int] = field(default_factory=dict)
    _next_alias: int = -1
    clock: Callable[[], datetime] = datetime.now  # date rows; fixed in transcripts
    personal: PersonalLexicon | None = None  # the user's word list, shared
    prediction: str = DEFAULT_PREDICTION  # "off" or "tab" (predict.py)
    predict_index: ReadingIndex = field(default_factory=ReadingIndex)  # shared
    predicting: bool = False  # the focused candidates are predictions
    _word_starts: set[int] = field(default_factory=set)  # 1-best word boundaries
    # 部分確定: the thumb direction a committed head gave
    # the presses whose chords remain. Keyed by the remaining tokens' press
    # number (presses are never renumbered or reused), cleared on reset.
    _carry: dict[int, frozenset[str]] = field(default_factory=dict)

    def load(self) -> None:
        if not self._table:
            self._table = load_table()
        if self._lex is None:
            self._lex = load_lex()
        if self._symbols is None:
            self._symbols = load_symbols()

    def reset(self) -> None:
        """Discard composition and input state after focus loss/termination."""
        self._reset_input()
        self._clear_context()

    def _reset_input(self) -> None:
        self._clear_input()
        self.fsm.reset()
        self.fsm.pressed_at.clear()
        self._modifiers.clear()
        self._press_alias.clear()
        self._carry.clear()
        self._await = None
        self._continuation = None

    def _clear_context(self) -> None:
        self._committed_context = self._lm_context = ""
        self._left_id = BOS_ID
        self._last_commit = None
        self._left_bunsetsu = None
        self._repeat = False

    def starts_input(self, vk: int, mods: list[str] | None) -> bool:
        return (not self.direct and not self.tokens and self._await is None
                and self.fsm.state == "S1" and classify(vk)[0] in ("M", "O")
                and not self._shortcut(mods))

    def start_input(self, text: str | None, after: int | None, *, disconnected: bool) -> None:
        self._partial = False
        last = self._last_commit
        if after is not None:
            if last is not None and after == last.seq:
                if text is None or (text and
                        (text.endswith(last.tail) or last.tail.endswith(text))):
                    self._lm_context = self._committed_context if text is None else text
                    self._left_id = last.right_id
                    self._left_bunsetsu = last.bunsetsu
                    self._repeat = last.standalone
                    return
            disconnected = True
        if disconnected or text == "":
            self._clear_context()
        self._lm_context = self._committed_context if text is None else text
        self._left_id = BOS_ID
        self._left_bunsetsu = None
        self._repeat = False

    def bind_commit(self, seq: int | None) -> None:
        if self._last_commit is not None:
            self._last_commit.seq = seq

    def _shortcut(self, mods: list[str] | None) -> bool:
        return (bool(set(mods) & {"ctrl", "alt", "win"}) if mods is not None
                else bool(self._modifiers & SHORTCUT_VKS))

    def set_direct(self, direct: bool) -> None:
        """Change input mode, discarding unfinished input on a transition."""
        if direct != self.direct:
            self.reset()
            self.direct = direct

    def on_key(
        self, down: bool, vk: int, now_ms: int, mods: list[str] | None = None,
    ) -> str | None:
        """Return the text to insert for this event (never cumulative text).

        mods is an optional snapshot: ["shift", "ctrl", "alt", "win"]. Without
        it, modifier down/up events provide the state (also used by the host).
        """
        if self.direct:
            return None
        kind, key = classify(vk)
        if kind == "MOD":
            if down:
                self._modifiers.add(vk)
            else:
                self._modifiers.discard(vk)
            return None
        shift = "shift" in mods if mods is not None else bool(self._modifiers & SHIFT_VKS)
        shortcut = self._shortcut(mods)
        ctrl_only = (set(mods) == {"ctrl"} if mods is not None
                     else bool(self._modifiers & CTRL_VKS)
                     and not self._modifiers & (SHORTCUT_VKS - CTRL_VKS) and not shift)
        if (down and vk == VK_DOWN and ctrl_only
                and (self.tokens or self.fsm.timer_deadline is not None
                     or self._await is not None)):
            # 部分確定: Ctrl+↓ commits the first clause.
            pending = self._finish_pending()

            def commit_prefix() -> str | None:
                if not self.tokens or self.predicting:
                    if not self.tokens:
                        self._clear_context()  # as the shortcut below
                    return None
                return self._commit_prefix()
            return self._then(pending, commit_prefix)
        if shortcut:
            if down and not self.tokens:
                self._clear_context()  # Ctrl/Alt/Win may move the caret or edit text.
            return None
        if down and (vk in SCRIPT_VKS and not shift or vk == VK_F6 and shift):
            pending = self._finish_pending()
            if shift:
                # Shift+F6 forgets the candidate's learning; the plain keys
                # carry the conventional script conversions below.
                def forget_key() -> None:
                    if self.converted and self.candidates:
                        self.forget_candidate()
                    return None
                return self._then(pending, forget_key)

            def script_key() -> None:
                self._select_script(vk)
                return None
            return self._then(pending, script_key)
        if kind == "EDIT":
            if not down:
                return None
            pending = self._finish_pending()
            return self._then(pending, lambda: self._edit(vk))
        if (down and shift and self.converted and self.focus >= 0
                and vk in (VK_LEFT, VK_RIGHT)):
            pending = self._finish_pending()
            self._resize(1 if vk == VK_RIGHT else -1)
            return pending
        # Candidate shortcuts precede the digit keys' faces; Shift+digits enter symbols.
        if down and not shift and self.converted:
            if vk in (VK_LEFT, VK_RIGHT, VK_UP, VK_DOWN, VK_PRIOR, VK_NEXT) or (
                    self.candidates and ord("1") <= vk <= ord("9")):
                pending = self._finish_pending()
            else:
                pending = None
            picked = self._on_cand_key(vk)
            if picked is not None:
                return (pending or "") + picked
        if (down and vk == VK_TAB and not shift and self.prediction != "off"
                and self._predict_key()):
            return None
        if down and kind in ("M", "O") and self._alnum_continues():
            # 英数の続き: no chord FSM; keys type their engravings, Space converts.
            pending = self._finish_pending()
            if kind == "O":
                return self._then(pending, lambda: self._ingest([ThumbTap()]))
            return self._then(pending, lambda: self._ingest(
                [Literal(alnum_character(vk, key, shift))]))
        literal = literal_character(vk, shift)
        if literal is not None:
            if not down:
                return None
            pending = self._finish_pending()
            return self._then(pending, lambda: self._ingest([Literal(literal)]))
        if kind not in ("M", "O"):
            if down and not self.tokens:
                self._clear_context()  # Arrows/Home/Tab etc.: the caret may have moved.
            return None
        assert key is not None
        due = self.flush_timeout(now_ms)

        def chord_key() -> str | None:
            insert = ""
            if down and kind == "M" and self.converted:
                # Preserve a pending Space chord: only composition is committed here.
                insert += self._commit(reset_input=False)
            raw = (self.fsm.on_down(kind, key, now_ms) if down
                   else self.fsm.on_up(kind, key, now_ms))
            return insert + (self._ingest(raw) or "") or None
        return self._then(due, chord_key)

    def _alnum_continues(self) -> bool:
        """英数の続き: the input ends in a half-width ASCII literal.

        Only Shift+letter and the continuation itself type one (every other
        key types kana or a full-width literal), so the tail is the state.
        A conversion in progress (or awaited) is not part of it: a key there
        commits the conversion and starts a new input.
        """
        return (not self.converted and self._await is None and bool(self.tokens)
                and isinstance(self.tokens[-1], Literal)
                and half_width_ascii(self.tokens[-1].text))

    def _then(self, text: str | None, rest: Callable[[], str | None]) -> str | None:
        """Run the rest of a key event now, or after the awaited conversion resolves."""
        if self._await is not None:
            self._continuation = rest
            return text
        return ((text or "") + (rest() or "")) or None

    def conversion_request(self) -> ConversionRequest | None:
        """The LM work for converting now; None without a kana run."""
        parts = self._parts()
        if not any(isinstance(part, list) for part in parts):
            return None
        return self._conversion_input(parts)

    def _conversion_input(self, parts: list) -> ConversionRequest:
        self._sync_personal()
        learning = self._learning.snapshot() if self._learning is not None else None
        prev = self._left_bunsetsu
        repeat = self._repeat and not self._partial
        personal_revision = self.personal.revision if self.personal is not None else None
        key = (repr(parts), self._lm_context, self._left_id,
               learning.revision if learning is not None else None,
               personal_revision, prev, repeat)
        return ConversionRequest(parts, self._lm_context, self._left_id, learning, key,
                                 prev, repeat, personal_revision)

    def _show_conversion(self, request: ConversionRequest, *, picks: list[KanaRun] | None = None,
                         converter: ZenzConverter | None = None) -> None:
        if converter is not None:
            converter.last = {}
            try:
                picks = request.decode(self._lex, converter)
            except Exception as exc:
                print(f"LM conversion failed ({type(exc).__name__})", file=sys.stderr, flush=True)
        self.converted = True
        if picks is not None or self._display_key != request.key:
            self._refresh(picks=picks, request=request)
        self._open_cands()

    def finish_conversion(self, picks: list[KanaRun] | None) -> str:
        """Resolve the awaited conversion (picks None: the Viterbi 1-best).

        Returns the text committed by the rest of the deferred key event.
        """
        request = self._await
        assert request is not None
        self._await = None
        self._show_conversion(request, picks=picks)
        rest, self._continuation = self._continuation, None
        text = (rest() if rest is not None else None) or ""
        assert self._await is None
        return text

    def on_timeout(self, now_ms: int) -> str | None:
        if self.direct:
            return None
        return self._ingest(self.fsm.on_timeout(now_ms))

    def flush_timeout(self, now_ms: int) -> str | None:
        deadline = self.fsm.timer_deadline
        if deadline is None or now_ms < deadline:
            return None
        return self.on_timeout(now_ms)

    def _finish_pending(self) -> str | None:
        """End a chord at a literal/edit boundary before applying that event.

        Such keys cannot join a NICOLA chord. Resolve the pending chord using
        the existing FSM timeout path so held keys cannot appear out of order.
        """
        deadline = self.fsm.timer_deadline
        insert = self.on_timeout(deadline) if deadline is not None else None
        self.fsm.reset()
        return insert

    def _cancel_conversion(self) -> None:
        self.converted = False
        self._clear_cands()
        self._refresh()

    def _predict_key(self) -> bool:
        """Tab: open predictions, or the next one; False leaves Tab as it was.

        Only unconverted input with no chord or conversion in flight asks;
        with no prediction nothing changes (the TIP eats Tab while composing).
        """
        if self.predicting:
            self._cycle(1)
            return True
        if (not self.tokens or self.converted or self._await is not None
                or self.fsm.timer_deadline is not None or self._lex is None):
            return False
        self._sync_personal()
        learning = self._learning.snapshot() if self._learning is not None else None
        lattice = self._lattice()
        run = len(lattice)  # the trailing kana run: no literal inside a prediction
        while run > 0 and lattice[run - 1]["kind"] != "literal":
            run -= 1
        starts = sorted(b for b in self._word_starts if run <= b < len(lattice))
        for start in starts[-MAX_TAILS:]:  # longest tail first
            index = next(i for i, s in enumerate(self.segments) if s.end > start)
            head = self.segments[:index]
            redecoded = self.segments[index].start != start
            if redecoded:
                # Inside a clause (いい|天気): the typed head before it, decoded alone.
                tokens = self.tokens
                # Lattice offsets skip tokens with no kana; cut the raw list there.
                kept = [i for i, t in enumerate(tokens)
                        if to_lattice_token(t, self._table) is not None]
                self.tokens = tokens[:kept[start]]
                self._refresh()
                head = self.segments
                self.tokens = tokens
            # A press crossing into the tail keeps the head's direction.
            tail = restrict(lattice, start, len(lattice),
                            press_pins(lattice, start, len(lattice), head))
            found = predict(tail, self._lex, self.predict_index, learning,
                            self.personal.revision if self.personal is not None else None)
            if not found:
                if redecoded:
                    self._refresh()  # restore the clauses exactly as shown
                continue
            stream = CandidateStream(iter(found))
            stream.ensure(0)
            self.segments = head + [Segment(start, len(lattice), found[0], fixed=True,
                                            choices=stream, context=PREDICTION)]
            self.converted = True
            self.predicting = True
            self.focus = len(head)
            self.composition = "".join(s.selected.surface for s in self.segments)
            self._open_cands()
            return True
        return False

    def _select_script(self, vk: int) -> None:
        """F6-F10: give the focused clause one fixed spelling (MS-IME's gestures).

        F6 hiragana, F7 katakana: the kana rows that close out every clause's
        candidate stream, one hiragana/katakana pair per reading the typed
        chords allow; selecting one is an ordinary candidate pick, so a later
        commit learns it like any other selection. Pressed again while a row
        of that script is selected, F6/F7 step to the next reading's row,
        wrapping to the first: a single thumb key leaves left/right faces
        ambiguous, and the decoder's reading need not be the one meant
        (クアンバ: あ/じ and ば/み share keys, so F7 goes
        クジンバ → クジンミ → クアンミ → クアンバ).
        F8 half-width katakana of the selected kana reading (else the first).
        F9/F10 the typed keys as full-/half-width alphanumerics (the kana-input
        convention: what the keys would have typed with the IME off); pressed
        again they cycle lower → UPPER → Capitalized. Not learned.
        Input not yet converted converts first, as with the MS-IME gesture.
        """
        if not self.tokens:
            return
        if self.predicting:
            self._cancel_conversion()  # the kana spelling of what was typed
        if not self.converted:
            self._show_conversion(self._conversion_input(self._parts()), converter=self.lm)
        if self.focus < 0:
            return
        segment = self.segments[self.focus]
        if segment.literal or segment.choices is None:
            return
        stream = segment.choices
        rows: list[int] = []
        i = 0
        while len(rows) < 2 and stream.ensure(i):
            if stream.cache[i].kind == "kana":
                rows.append(i)
            i += 1
        if not rows:
            return
        if vk in (VK_F6, VK_F7):
            self._select(self._next_kana_row(segment, hiragana=vk == VK_F6,
                                             default=rows[1] if vk == VK_F7 and len(rows) > 1
                                             else rows[0]))
            return
        hira = (segment.selected if segment.selected.kind == "kana"
                else stream.cache[rows[0]])
        if vk == VK_F8:
            surface, kind = half_katakana(hira.reading), "kana"
        else:
            keys = [t.get("key", "") for t in self._lattice()[segment.start:segment.end]]
            surface = alnum_spelling("".join(keys), segment.selected.surface
                                     if segment.selected.kind == "alnum" else None,
                                     full=vk == VK_F9)
            kind = "alnum"
        chosen = Candidate(surface, hira.reading, hira.score, hira.lid, hira.rid, kind)
        self._set_selection(self.focus, chosen)
        segment.fixed = True
        segment.index = stream.find(chosen)  # -1: shown with no highlighted row
        self._show_page()

    @staticmethod
    def _is_hiragana_row(c: Candidate) -> bool:
        return c.surface == c.reading  # the katakana row of the same reading differs

    def _next_kana_row(self, segment: Segment, *, hiragana: bool, default: int) -> int:
        """The kana row F6/F7 selects: the next one of that script after the
        current selection when one is already selected, else ``default``."""
        stream = segment.choices
        assert stream is not None
        current = segment.selected
        if (current.kind != "kana" or segment.index < 0
                or self._is_hiragana_row(current) != hiragana):
            return default

        def matches(i: int) -> bool:
            c = stream.cache[i]
            return c.kind == "kana" and self._is_hiragana_row(c) == hiragana

        # Kana rows close out the stream, so the search after the current row
        # never generates dictionary rows; wrapping restarts at the first one.
        i = segment.index + 1
        while stream.ensure(i):
            if matches(i):
                return i
            i += 1
        return default

    def forget_candidate(self) -> bool:
        """Suppress the highlighted pair, then choose the newly ranked first row."""
        if (self._learning is None or not self.converted or self.focus < 0
                or not self.candidates or self.cand_index < 0):
            return False
        segment = self.segments[self.focus]
        c = segment.selected
        if c.kind in ("literal", "number", "date") or not c.reading:
            return False
        if not self._learning.suppress(c.reading, c.surface):
            return False
        if segment.context == PREDICTION:
            # The forgotten word leaves the list; back to the input if none remain.
            self._cancel_conversion()
            self._predict_key()
            return True
        self._learning_view = self._learning.snapshot()
        segment.fixed = False
        self._prepare_cands(self.focus, reselect=True)
        self._open_cands()
        return True

    def _edit(self, vk: int) -> str | None:
        if vk == VK_BACK:
            if self.converted:
                self._cancel_conversion()
            elif self.tokens:
                self.tokens.pop()
                self._refresh()
            else:
                self._committed_context = self._committed_context[:-1]
                self._lm_context = self._committed_context
                self._left_id = BOS_ID
                self._last_commit = None
                self._left_bunsetsu = None
                self._repeat = False
            return None
        if vk == VK_ESCAPE:
            if self.converted:
                self._cancel_conversion()
            else:
                self.reset()
            return None
        if vk == VK_RETURN:
            return self._commit()
        return None

    def _on_cand_key(self, vk: int) -> str | None:
        if vk in (VK_LEFT, VK_RIGHT):
            # Every segment is a stop: a symbol or a run of digits has its own rows.
            if self.focus >= 0:
                at = self.focus + (1 if vk == VK_RIGHT else -1)
                self.focus = max(0, min(at, len(self.segments) - 1))
                self._open_cands()
            return ""
        if vk in (VK_DOWN, VK_UP):
            self._cycle(1 if vk == VK_DOWN else -1)
            return ""
        if vk in (VK_NEXT, VK_PRIOR):
            self._page(1 if vk == VK_NEXT else -1)
            return ""
        if self.candidates and ord("1") <= vk <= ord("9"):
            row = vk - ord("1")
            if self.focus >= 0 and row < len(self.candidates):
                self._select(self.candidate_page * PAGE_SIZE + row)
            return ""
        return None

    def _open_cands(self) -> None:
        self._clear_cands()
        if self.focus < 0:
            return
        self._prepare_cands(self.focus)
        self._show_page()

    def _prepare_cands(self, index: int, *, reselect: bool = False) -> None:
        segment = self.segments[index]
        if segment.context == PREDICTION:
            return  # a fixed list, built by _predict_key
        if segment.literal and segment.selected.kind == "literal":
            if segment.choices is None:
                typed = segment.selected.reading
                segment.choices = CandidateStream(iter([
                    Candidate(text, typed, 0, BOS_ID, BOS_ID, "literal")
                    for text in symbol_spellings(typed)]))
                segment.index = segment.choices.find(segment.selected)
            return
        if segment.selected.kind == "number":
            if segment.choices is None:
                digits = segment.selected.reading
                segment.choices = CandidateStream(iter([
                    Candidate(text, digits, 0, BOS_ID, BOS_ID, "number")
                    for text in number_spellings(digits)]))
                segment.index = segment.choices.find(segment.selected)
            return
        lattice = self._lattice()
        pins, left, right = candidate_inputs(lattice, self.segments, index, self._left_id, self._lex)
        learning = self._learning_view
        prev = previous_bunsetsu(self.segments, index, self._left_bunsetsu)
        repeat = self._repeat and not self._partial and len(self.segments) == 1
        personal_revision = self.personal.revision if self.personal is not None else None
        scope = candidate_context(segment, pins, left, right, learning, personal_revision,
                                  prev, repeat)
        order = segment.order
        if order is not None:
            left_text = self._lm_context + "".join(s.selected.surface for s in self.segments[:index])
            if order.context != (scope, prompt(left_text, segment.selected.reading)):
                order = None
        context = (scope, order is not None)
        if segment.choices is None or segment.context != context:
            rows = candidates(
                restrict(lattice, segment.start, segment.end, pins), self._lex, left, right,
                learning=learning, now=self.clock())
            heads = candidate_heads(segment, learning, prev, repeat)
            segment.choices = CandidateStream(arranged_candidates(
                rows, heads, order, self._symbols, learning))
            segment.context = context
            if not reselect:
                segment.index = segment.choices.find(segment.selected)
        if reselect:
            segment.choices.ensure(0)
            self._set_selection(index, segment.choices.cache[0])
            segment.index = 0

    def _set_selection(self, index: int, selected: Candidate) -> None:
        self.segments[index].selected = selected
        self._update_composition()

    def _update_composition(self) -> None:
        text = ""
        for segment in self.segments:
            evidence = segment.zenz
            if evidence is not None and (evidence.candidate.reading != segment.selected.reading
                                         or evidence.left != text):
                segment.zenz = None
            text += segment.selected.surface
        self.composition = text

    def _resize(self, delta: int) -> None:
        """Override one automatic boundary, keeping all other intervals intact."""
        segment = self.segments[self.focus]
        if segment.literal or self.predicting:
            return  # a digit run keeps its interval; predictions span the input
        following = self.focus + 1
        if delta > 0:
            if following == len(self.segments) or self.segments[following].literal:
                return
            neighbor = self.segments[following]
            segment.end += 1
            neighbor.start += 1
            if neighbor.start == neighbor.end:
                del self.segments[following]
                changed = [self.focus]
            else:
                changed = [self.focus, following]
        else:
            if segment.end - segment.start == 1:
                return
            segment.end -= 1
            if following == len(self.segments) or self.segments[following].literal:
                self.segments.insert(following, Segment(
                    segment.end, segment.end + 1, segment.selected))
            else:
                self.segments[following].start -= 1
            changed = [self.focus, following]
        # Determine the new readings with the right interval's POS available
        # to the left. Apply learning only after both readings are known.
        lattice = self._lattice()
        for index in reversed(changed):
            resized = self.segments[index]
            resized.choices = None
            resized.fixed = False
            resized.zenz = None
            resized.order = None
            pins, left, right = candidate_inputs(
                lattice, self.segments, index, self._left_id, self._lex)
            resized.selected = next(candidates(
                restrict(lattice, resized.start, resized.end, pins), self._lex, left, right,
                learning=self._learning_view))
        repeat = self._repeat and not self._partial and len(self.segments) == 1
        for index in changed:
            resized = self.segments[index]
            prev = previous_bunsetsu(self.segments, index, self._left_bunsetsu)
            learned, _ = candidate_heads(resized, self._learning_view, prev, repeat)
            if learned is not None:
                resized.selected = learned
        self._update_composition()
        self._open_cands()

    def _clear_cands(self) -> None:
        self.candidates = []
        self.candidate_kinds = []
        self.candidate_page = 0
        self.has_next_page = False
        self.cand_index = 0

    def _show_page(self) -> None:
        segment = self.segments[self.focus]
        stream = segment.choices
        assert stream is not None
        self.candidate_page = max(0, segment.index) // PAGE_SIZE
        start = self.candidate_page * PAGE_SIZE
        self.has_next_page = stream.ensure(start + PAGE_SIZE)
        page = stream.cache[start:start + PAGE_SIZE]
        self.candidates = [c.surface for c in page]
        self.candidate_kinds = [c.kind for c in page]
        self.cand_index = segment.index - start

    def _select(self, index: int) -> None:
        segment = self.segments[self.focus]
        stream = segment.choices
        if stream is not None and stream.ensure(index):
            segment.index = index
            self._set_selection(self.focus, stream.cache[index])
            segment.fixed = True
            self._show_page()

    def _cycle(self, delta: int) -> None:
        if self.focus < 0:
            return
        segment = self.segments[self.focus]
        stream = segment.choices
        if stream is None:
            return
        index = segment.index + delta
        if index < 0:
            index = stream.last()
        elif not stream.ensure(index):
            index = 0
        self._select(index)

    def _page(self, delta: int) -> None:
        if self.focus < 0:
            return
        segment = self.segments[self.focus]
        page = self.candidate_page + delta
        if page < 0:
            return
        start = page * PAGE_SIZE
        if segment.choices is not None and segment.choices.ensure(start):
            self._select(start)

    def segment_snapshot(self) -> list[dict]:
        offset = 0
        out = []
        for segment in self.segments:
            text = segment.selected.surface
            out.append({"start": segment.start, "end": segment.end, "surface": text,
                        "reading": segment.selected.reading, "literal": segment.literal,
                        "fixed": segment.fixed, "display_start": offset,
                        "display_end": offset + len(text)})
            offset += len(text)
        return out

    def _ingest(self, raw: list[Token | Literal]) -> str | None:
        insert = ""
        for tok in raw:
            if isinstance(tok, ThumbTap):
                if self.tokens:
                    if self.converted:
                        self._cycle(1)
                    else:
                        request = self.conversion_request() if self.lm_deferred else None
                        if request is not None:
                            assert tok is raw[-1]  # the FSM emits at most one token per call
                            self._await = request
                            continue
                        request = self._conversion_input(self._parts())
                        self._show_conversion(request, converter=self.lm)
                else:
                    # No input: a space, full width as the kana mode's default.
                    insert += IDEOGRAPHIC_SPACE
                    self._note_commit(IDEOGRAPHIC_SPACE)
                continue
            mapped = to_lattice_token(tok, self._table)
            if mapped is None:
                continue  # An empty face (] alone, Q right, ...): nothing is typed.
            if isinstance(tok, AmbShift) and tok.press is not None:
                if mapped["kind"] == "literal":
                    self._press_alias[tok.press] = self._next_alias
                    self._next_alias -= 1
                elif tok.press in self._press_alias:
                    tok = AmbShift(tok.key, self._press_alias[tok.press], tok.turn)
            if self.converted:
                insert += self._commit(reset_input=False)
            self.tokens.append(Literal(mapped["text"]) if mapped["kind"] == "literal" else tok)
            self.converted = False
            self._clear_cands()
            self._refresh()
        return insert or None

    def _lattice(self) -> list[dict]:
        out = []
        for t in self.tokens:
            d = to_lattice_token(t, self._table)
            if d is None:
                continue
            carried = self._carry.get(d.get("press")) if self._carry else None
            if carried is not None:
                # The committed head chose this press's direction (部分確定).
                d = {**d, "faces": {face: kana for face, kana in d["faces"].items()
                                    if face_of(face, d["turn"]) in carried}}
            out.append(d)
        return out

    def _parts(self) -> list[str | list[dict]]:
        """Literal texts and kana runs; a literal ends the press (ChordFsm.reset,
        or a new press number after a symbol chord), so no press crosses one."""
        parts: list[str | list[dict]] = []
        run: list[dict] = []
        for token in self._lattice():
            if token["kind"] == "literal":
                if run:
                    parts.append(run)
                    run = []
                parts.append(token["text"])
            else:
                run.append(token)
        if run:
            parts.append(run)
        return parts

    def _refresh(self, *, picks: list[KanaRun] | None = None,
                 request: ConversionRequest | None = None) -> None:
        """Rebuild the composition from one conversion and its learning view."""
        self.predicting = False
        if request is None:
            request = self._conversion_input(self._parts())
        self._display_key = request.key
        self._learning_view = request.learning
        if picks is None and self._lex is not None:
            picks = request.decode(self._lex)
        self.segments = display_segments(request.parts, picks)
        self._word_starts = {start for run in picks or () for start in run.word_starts}
        self.focus = _first_stop(self.segments)
        self.composition = "".join(s.selected.surface for s in self.segments)

    def _sync_personal(self) -> None:
        if self.personal is not None and self._lex is not None:
            self.personal.sync(self._lex)

    def _confirm(self, segments: list[Segment], *, standalone: bool) -> None:
        if self._learning is not None and self._lex is not None:
            self._learning.confirm(
                [s.selected for s in segments], self._lex,
                prev=self._left_bunsetsu, repeat=self._repeat and standalone)

    def _commit(self, *, reset_input: bool = True) -> str:
        text = self.composition
        if text:
            standalone = len(self.segments) == 1 and not self._partial
            self._confirm(self.segments, standalone=standalone)
            self._note_commit(text, self.segments[-1], standalone=standalone)
        if reset_input:
            self._reset_input()
        else:
            self._clear_input()
        return text

    def _clear_input(self) -> None:
        """The input is gone (committed); the connection's state stays."""
        self.tokens.clear()
        self.segments.clear()
        self._partial = False
        self._display_key = None
        self._learning_view = None
        self.focus = -1
        self.composition = ""
        self.converted = False
        self.predicting = False
        self._clear_cands()

    def _commit_prefix(self) -> str:
        """部分確定 (Ctrl+↓): commit the first interval only.

        The first clause, or the first literal (a run of digits or of 英数の続き
        is one). The rest keeps its intervals, selections and fixed state; when
        converted, its candidates reopen.
        """
        if not self.segments:
            return ""
        if len(self.segments) == 1:
            return self._commit(reset_input=False)
        head = self.segments[0]
        end = head.end
        text = head.selected.surface
        self._confirm([head], standalone=False)
        self._note_commit(text, head)
        self._partial = True
        self._display_key = None
        # The directions the committed reading gives each press (the thumbs
        # of one press alternate); the remaining chords of a press keep it.
        chosen = Plan(self._lattice()).directions(head.start, head.end, head.selected.reading)
        # Lattice offsets skip tokens with no kana; cut the raw list there (as
        # _predict_key does).
        kept = [i for i, t in enumerate(self.tokens)
                if to_lattice_token(t, self._table) is not None]
        del self.tokens[:kept[end]]
        remaining = {t.press for t in self.tokens if isinstance(t, AmbShift)}
        for press, dirs in chosen.items():
            if press in remaining and dirs and dirs != SIDES:
                self._carry[press] = dirs
        self.segments = self.segments[1:]
        for segment in self.segments:
            segment.start -= end
            segment.end -= end
            evidence = segment.zenz
            if evidence is not None:
                segment.zenz = (replace(evidence, left=evidence.left[len(text):])
                                if evidence.left.startswith(text) else None)
        self._word_starts = {b - end for b in self._word_starts if b >= end}
        self.composition = "".join(s.selected.surface for s in self.segments)
        self.focus = _first_stop(self.segments)
        if self.converted:
            self._open_cands()
        return text

    def _note_commit(self, text: str, last: Segment | None = None, *,
                     standalone: bool = False) -> None:
        """Advance the current input and remember what this connection committed."""
        right_id = BOS_ID
        if self._lex is not None and last is not None:
            if last.literal:
                right_id = left_id_after(last.selected.reading, self._lex)
            elif 0 <= last.selected.rid < self._lex.pos_size + len(self._lex.numeral_pos):
                right_id = last.selected.rid
        self._committed_context = _append_context(self._committed_context, text)
        self._lm_context = _append_context(self._lm_context, text)
        self._left_id = right_id
        self._left_bunsetsu = normal_bunsetsu(last.selected) if last is not None else None
        self._repeat = standalone and self._left_bunsetsu is not None
        self._last_commit = CommitContext(text[-CONTEXT_CHARS:], right_id,
                                          self._left_bunsetsu, self._repeat)


def _first_stop(segments: list[Segment]) -> int:
    """Conversion starts on the first kana interval; without kana, on the first segment."""
    return next((i for i, s in enumerate(segments) if not s.literal),
                0 if segments else -1)
