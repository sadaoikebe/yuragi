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
    ALT_VKS, MODIFIER_VKS, SHIFT, SPACE, VK_BACK, VK_RETURN, Chord, alnum_character,
    classify, literal_character, modifier_bits,
)
from yuragi.lattice.alternation import SIDES, Plan, face_of, restrict
from yuragi.lattice.expand import is_literal_face, literal_text
from yuragi.lattice.mozc_dict import MozcLex, left_id_after, load_lex
from yuragi.lattice.table import load_table
from yuragi.text import katakana, to_full_width, to_half_width
from .bunsetsu import (BOS_ID, PAGE_SIZE, Bunsetsu, Candidate, CandidateOrder, CandidateStream,
                       Segment, arranged_candidates, candidate_note, candidates, dictionary_candidates,
                       normal_bunsetsu, without_heads, word_piece)
from .commands import CONVERTED, KANA, Command
from .keymap import Keymap, default_keymap
from .learning import LearningStore, LearningView
from .zenz import CONTEXT_CHARS, KanaRun, ZenzConverter, conversion_picks, prompt
from .numbers import is_digit, number_spellings
from .personal import PersonalLexicon
from .symbols import symbol_spellings
from .symbol_readings import load_symbols
from .predict import (DEFAULT_MODE as DEFAULT_PREDICTION, HISTORY_MIN_KANA, MAX_TAILS,
                      PREVIEW_DELAY_MS, PREVIEW_TAIL_TOKENS, PreviewBudget, ReadingIndex,
                      predict)

PREDICTION = "predict"  # Segment.context of the predictions' segment


@dataclass(frozen=True, slots=True)
class Literal:
    text: str
    alnum: bool = False
    frozen: bool = False  # a spelling left before subsequent input by NonConvert

    def __post_init__(self) -> None:
        if not self.text or (len(self.text) != 1 and not self.frozen):
            raise ValueError("invalid literal input unit")


_HALF_KATAKANA: dict[str, str] = {}
for _code in range(0xFF66, 0xFF9E):
    _half = chr(_code)
    _HALF_KATAKANA.setdefault(unicodedata.normalize("NFKC", _half), _half)
    for _mark in ("\uff9e", "\uff9f"):
        _full = unicodedata.normalize("NFKC", _half + _mark)
        if len(_full) == 1:
            _HALF_KATAKANA.setdefault(_full, _half + _mark)


KANA_SCRIPTS = ("hiragana", "katakana", "half_katakana")


def half_katakana(hiragana: str) -> str:
    """F8: ひらがな → ﾊﾝｶｸｶﾀｶﾅ (a kana with no half-width form stays full-width)."""
    return "".join(_HALF_KATAKANA.get(c, c) for c in katakana(hiragana))


def kana_script(reading: str, script: str) -> str:
    if script == "katakana":
        return katakana(reading)
    if script == "half_katakana":
        return half_katakana(reading)
    return reading


def alnum_spelling(keys: str, current: str | None, *, full: bool) -> str:
    """F9/F10: the typed keys; again on the same width cycles the letter case."""
    forms = [keys.lower(), keys.upper(), keys[:1].upper() + keys[1:].lower()]
    if full:
        forms = [to_full_width(f) for f in forms]
    if current in forms:
        return forms[(forms.index(current) + 1) % len(forms)]
    return forms[0]


def half_width_ascii(text: str) -> bool:
    """Half-width ASCII without the space: what Shift+letter and 英数の続き type."""
    return bool(text) and all("!" <= c <= "~" for c in text)



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
            prev = previous_bunsetsu(segments, index, self.prev, lex)
            heads = candidate_heads(segment, lex, self.learning, prev, repeat)
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


def previous_bunsetsu(segments: list[Segment], index: int, prev: Bunsetsu | None, lex: MozcLex):
    return normal_bunsetsu(segments[index - 1].selected, lex) if index > 0 else prev


def candidate_base(segment: Segment) -> Candidate:
    source = segment.source
    return source if source is not None and source.reading == segment.selected.reading else segment.selected


def candidate_heads(segment: Segment, lex: MozcLex, learning: LearningView | None,
                    prev: Bunsetsu | None, repeat: bool) -> tuple[Candidate | None, Candidate | None]:
    evidence = segment.zenz
    confirmed = evidence.candidate if evidence is not None and evidence.complete else None
    learned = (learning.preferred(candidate_base(segment), lex, prev, repeat=repeat, evidence=evidence)
               if learning is not None else None)
    if learned is not None and confirmed is not None and learned.surface == confirmed.surface:
        confirmed = None
    return learned, confirmed


def candidate_context(segment: Segment, pins: dict, left: int, right: int,
                      learning: LearningView | None, personal_revision: int | None,
                      prev: Bunsetsu | None, repeat: bool) -> tuple:
    return (segment.start, segment.end, left, right, pins,
            learning.revision if learning is not None else None, personal_revision,
            candidate_base(segment) if learning is not None else segment.selected.reading,
            prev, repeat, segment.zenz)


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


@dataclass(frozen=True)
class Suggestion:
    index: int  # the suffix begins at this segment
    rows: list[Candidate]
    personal_revision: int | None
    learning_revision: int | None


@dataclass
class ImeSession:
    fsm: ChordFsm = field(default_factory=ChordFsm)
    direct: bool = False
    tokens: list[Token | Literal] = field(default_factory=list)
    composition: str = ""
    converted: bool = False
    resizing: bool = False
    editing: bool = False  # the focused clause is open for input within a conversion
    _cursor: int | None = None  # token boundary; None is the end of the active input
    _reading_edit: bool = False  # show the reading after moving within unconverted input
    _resize_origin: tuple[list[Segment], bool] | None = None
    candidates: list[str] = field(default_factory=list)
    cand_index: int = 0
    segments: list[Segment] = field(default_factory=list)
    focus: int = -1
    candidate_page: int = 0
    candidate_kinds: list[str] = field(default_factory=list)
    candidate_notes: list[str] = field(default_factory=list)
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
    prediction: str = DEFAULT_PREDICTION
    predict_index: ReadingIndex = field(default_factory=ReadingIndex)  # shared
    predicting: bool = False  # the focused candidates are predictions
    suggest_at: int | None = None
    suggestion: Suggestion | None = None
    _suggest_dirty: bool = False
    _word_starts: set[int] = field(default_factory=set)  # 1-best word boundaries
    # Thumb directions constrained before a partial commit or a press split.
    # Keyed by the remaining tokens' press number, cleared on reset.
    _carry: dict[int, frozenset[str]] = field(default_factory=dict)
    keymap: Keymap = field(default_factory=default_keymap)
    _fsm_down: set[int] = field(default_factory=set)
    key_eat: bool | None = field(default=None, init=False)  # None while a down awaits dispatch
    key_global: str | None = field(default=None, init=False)
    commit_caret_back: int = field(default=0, init=False)  # distance from the latest commit's end
    input_mode: str = "hiragana"
    _input_script: str | None = None  # current unconverted run styled with NonConvert
    _alnum_held: bool = False  # Shift+CapsLock: 英数の続き until the input ends
    max_tokens: int | None = None

    @property
    def phase(self) -> str:
        if self.direct:
            return "direct"
        if not self.tokens:
            return "empty"
        if self.predicting:
            return "predicting"
        if not self.converted:
            return "composing"
        if self.resizing:
            return "resizing"
        if self.editing:
            return "editing"
        return "selecting" if self.candidates else "converting"

    def load(self) -> None:
        if not self._table:
            self._table = load_table()
        if self._lex is None:
            self._lex = load_lex()
        if self._symbols is None:
            self._symbols = load_symbols()

    def reset(self) -> None:
        """Discard composition and input state after focus loss/termination."""
        self._modifiers.clear()
        self._cancel()

    def _cancel(self) -> None:
        self._reset_input()
        self._clear_context()

    def _reset_input(self) -> None:
        self._clear_input()
        self.fsm.reset()
        self.fsm.pressed_at.clear()
        self._fsm_down.clear()
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
        if self.phase != "empty" or self._await is not None or self.fsm.state != "S1":
            return False
        chord = Chord(vk, modifier_bits(mods, self._modifiers))
        command = self.keymap.lookup("empty", chord)
        return chord.typing or (command is not None and command.id == "insert_alt_space")

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

    def set_direct(self, direct: bool, *, commit: bool = False) -> str | None:
        """Change input mode, discarding unfinished input on a transition."""
        if direct != self.direct:
            if direct and commit:
                return self._then(self._finish_pending(), self._commit_direct)
            self.reset()
            self.direct = direct
        return None

    def _commit_direct(self) -> str:
        text = self._commit()
        self.direct = True
        return text

    def set_mode(self, mode: str) -> str | None:
        if mode not in (*KANA_SCRIPTS, "full_alnum"):
            return None
        if self.direct:
            self.set_direct(False)
        self._end_alnum()  # Ctrl+CapsLock keeps the input; later keys type kana (MS-IME)
        if mode != "hiragana":
            return self._then(self._finish_pending(), lambda: self._commit_mode(mode))
        self.input_mode = mode
        if not self.converted and self.tokens:
            self._refresh()
        return None

    def _commit_mode(self, mode: str) -> str:
        text = self._commit()
        self.input_mode = mode
        return text

    def _cycle_kana_mode(self) -> None:
        index = KANA_SCRIPTS.index(self.input_mode) if self.input_mode in KANA_SCRIPTS else -1
        self.input_mode = KANA_SCRIPTS[(index + 1) % len(KANA_SCRIPTS)]

    def _toggle_alnum_width(self) -> None:
        if self.input_mode == "full_alnum":
            self.set_direct(True)
        else:
            self.input_mode = "full_alnum"

    def on_key(
        self, down: bool, vk: int, now_ms: int, mods: list[str] | None = None,
    ) -> str | None:
        """Return this event's committed text; record its consumption in key_eat.

        With no modifier snapshot, the raw host's modifier down/up events
        provide the state.
        """
        self.key_eat = None if down else False
        self.key_global = None
        if self.direct:
            self.key_eat = False
            return None
        if vk in MODIFIER_VKS:
            if down:
                self._modifiers.add(vk)
            else:
                self._modifiers.discard(vk)
            self.key_eat = False
            if down and vk in ALT_VKS:
                return self._then(self._finish_pending(), self._commit)
            return None
        if not down:
            if vk not in self._fsm_down:
                return None
            self._fsm_down.remove(vk)
            kind, key = classify(vk)
            return self._then(self.flush_timeout(now_ms),
                              lambda: self._ingest(self.fsm.on_up(kind, key, now_ms)))

        chord = Chord(vk, modifier_bits(mods, self._modifiers))
        if chord.typing:
            return self._then(self.flush_timeout(now_ms),
                              lambda: self._type_key(chord, now_ms))
        return self._then(self._finish_pending(), lambda: self._dispatch_chord(chord))

    def pending_key_eat(self, vk: int, mods: list[str] | None) -> bool:
        """Reserve a queued down if it can be consumed after the LM resolves."""
        if self.direct or vk in MODIFIER_VKS:
            return False
        chord = Chord(vk, modifier_bits(mods, self._modifiers))
        if chord.typing:
            return True
        commands = (self.keymap.command_for(phase, chord) for phase in KANA)
        return any(command.key == "eat" and command.where == "engine" for command in commands)

    def _dispatch_chord(self, chord: Chord) -> str | None:
        command = self.keymap.command_for(self.phase, chord)
        self.key_eat = command.key == "eat" and command.where == "engine"
        if command.where == "tip":
            self.key_global = command.id
        self._forget_fsm_down(chord.vk)
        if command.key == "pass" and self.phase == "empty":
            self._pass_empty_key(chord)
        return self._run_command(command)

    def _type_key(self, chord: Chord, now_ms: int) -> str | None:
        # Plain Space is looked up only on ThumbTap. A Space that forms
        # a NICOLA chord must keep its original timing in every phase.
        if chord.character and (self.phase in CONVERTED or self.predicting):
            if self.keymap.lookup(self.phase, chord) is not None:
                return self._then(self._finish_pending(), lambda: self._dispatch_chord(chord))

        self.key_eat = True
        kind, key = classify(chord.vk)
        if self._alnum_held and self.converted and not self.editing and chord.vk != SPACE.vk:
            # MS-IME commits the conversion and drops the character: the IME is off.
            self._forget_fsm_down(chord.vk)
            return self._then(self._finish_pending(), self._commit)
        alnum = self._alnum_continues()
        if self.input_mode == "full_alnum" and not self._alnum_held and chord == SPACE:
            return self._then(self._finish_pending(), lambda: self._space_in_alnum(Literal("　")))
        if alnum and chord == SPACE:
            pending = self._finish_pending()
            self._forget_fsm_down(chord.vk)
            if self._alnum_held:
                return self._then(pending, lambda: self._space_in_alnum(Literal(" ", alnum=True)))
            return self._then(pending, lambda: self._ingest([ThumbTap()]))
        literal = literal_character(chord.vk, bool(chord.mods & SHIFT))
        if self.input_mode == "full_alnum" and not self._alnum_held and kind == "M":
            literal = to_full_width(alnum_character(chord.vk, bool(chord.mods & SHIFT)))
        elif alnum and kind == "M":
            literal = alnum_character(chord.vk, bool(chord.mods & SHIFT))
        if literal is not None:
            pending = self._finish_pending()
            self._forget_fsm_down(chord.vk)
            continues = alnum or (kind == "M" and literal.isascii() and literal.isalpha())
            return self._then(pending, lambda: self._ingest([Literal(literal, alnum=continues)]))

        assert key is not None
        insert = ""
        if chord.character and self.converted and not self.editing:
            # Preserve a pending Space chord while starting the next input.
            insert = self._commit(reset_input=False)
        self._fsm_down.add(chord.vk)
        return insert + (self._ingest(self.fsm.on_down(kind, key, now_ms)) or "") or None

    def _space_in_alnum(self, literal: Literal) -> str | None:
        command = self.keymap.lookup(self.phase, SPACE)
        if command == default_keymap().lookup(self.phase, SPACE):
            return self._ingest([literal])
        return self._run_command(command)

    def _forget_fsm_down(self, vk: int) -> None:
        if vk in self._fsm_down:
            self._fsm_down.remove(vk)
            _, key = classify(vk)
            self.fsm.pressed_at.pop(key, None)

    def _run_command(self, command: Command | None) -> str | None:
        if command is None or command.run is None:
            return None
        if command.keeps_resizing:
            return command.run(self)
        self.resizing = False
        try:
            return command.run(self)
        finally:
            self._resize_origin = None

    def _alnum_continues(self) -> bool:
        """英数の続き: Shift+CapsLock held it, or the input ends in a half-width ASCII literal.

        Only Shift+letter and the continuation itself type one (every other
        key types kana or a full-width literal), so the tail is the state.
        A conversion in progress (or awaited) is not part of it: a key there
        commits the conversion and starts a new input.
        """
        if (self.converted and not self.editing) or self._await is not None or not self.tokens:
            return False
        end = self.segments[self.focus].end if self.editing else len(self.tokens)
        tail = self.tokens[end - 1]
        return self._alnum_held or (isinstance(tail, Literal) and tail.alnum)

    def _hold_alnum(self) -> None:
        """Shift+CapsLock with input (MS-IME's 英数 mode): the input and any
        conversion stay; later keys type half-width alphanumerics."""
        self._alnum_held = True

    def _end_alnum(self) -> None:
        """A mode change ends 英数の続き, held or not; the input stays."""
        self._alnum_held = False
        if self.tokens:
            end = self.segments[self.focus].end if self.editing else len(self.tokens)
            tail = self.tokens[end - 1]
            if isinstance(tail, Literal) and tail.alnum:
                self.tokens[end - 1] = replace(tail, alnum=False)

    def _end_alnum_hold(self) -> None:
        """The input ended while held: MS-IME is left off, so the reply to an
        eaten key asks the TIP to turn off. A passed key or an op only clears it."""
        if self._alnum_held:
            self._alnum_held = False
            if self.key_eat:
                self.key_global = "ime_off"

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
        self._input_script = None
        self._cursor = None
        self._reading_edit = False
        if picks is not None or self._display_key != request.key:
            self._refresh(picks=picks, request=request)
        self._clear_cands()  # the first conversion keeps the candidate window closed (MS-IME)

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

    def _cancel_conversion(self, *, show_reading: bool = False) -> None:
        self.converted = False
        self.editing = False
        self._cursor = None
        self._reading_edit = show_reading
        self._clear_cands()
        self._refresh()
        self._clear_suggestion()

    def _segment_revert(self) -> None:
        if self.focus >= 0:
            self._cursor = None
            self._show_edited_segment(self.focus, self.segments[self.focus].selected.reading)

    def _clear_suggestion(self) -> None:
        self.suggest_at = self.suggestion = None
        self._suggest_dirty = False

    def schedule_suggestion(self, now_ms: int) -> None:
        """Start the idle delay when new input is ready, after any chord decision."""
        if self.prediction != "auto":
            return
        if (self.phase != "composing" or self._await is not None or self._alnum_held
                or self._input_script is not None or self.input_mode == "full_alnum"
                or self._cursor is not None
                or len(self.tokens) < HISTORY_MIN_KANA):
            self._clear_suggestion()
        elif self.fsm.state != "S1":
            self._suggest_dirty |= self.suggest_at is not None or self.suggestion is not None
            self.suggest_at = self.suggestion = None
        elif self._suggest_dirty:
            self._suggest_dirty = False
            self.suggest_at = now_ms + PREVIEW_DELAY_MS

    def suggest(self, now_ms: int, *, busy: bool = False) -> None:
        """One bounded peek at stable input. The ranges and preedit stay untouched."""
        if self.suggest_at is None or now_ms < self.suggest_at:
            return
        self.suggest_at = None
        if busy or self._lex is None:
            return
        try:
            budget = PreviewBudget()
            lattice = self._lattice()
            end = len(lattice)
            learning = self._learning_view
            if self._learning is not None and learning is not None:
                if self._learning.revision != learning.revision:
                    learning = None
            added_readings = self.personal.added_readings if self.personal is not None else ()
            # Use only already decoded clause boundaries. Opening the explicit
            # list can afford to decode a head split in the middle of a clause.
            tail_begin = max(0, end - PREVIEW_TAIL_TOKENS)
            for pos in range(end - 1, tail_begin - 1, -1):
                if lattice[pos]["kind"] == "literal":
                    tail_begin = pos + 1
                    break
            starts = [(i, s.start) for i, s in enumerate(self.segments)
                      if tail_begin <= s.start <= end - HISTORY_MIN_KANA]
            for index, start in starts[-MAX_TAILS:]:
                if budget.exhausted():
                    return
                tail = restrict(lattice, start, end, press_pins(lattice, start, end, self.segments[:index]))
                rows = predict(tail, self._lex, self.predict_index, learning,
                               added_readings=added_readings, budget=budget)
                if rows:
                    self.suggestion = Suggestion(index, rows,
                                                 self.personal.revision if self.personal else None,
                                                 learning.revision if learning else None)
                    return
        except Exception as exc:
            print(f"Prediction failed ({type(exc).__name__})", file=sys.stderr, flush=True)

    def _predict_key(self) -> None:
        """Open the predictions for the trailing reading, if there are any."""
        if self.prediction == "off" or not self.tokens or self.converted or self._lex is None:
            return
        self._sync_personal()
        learning = self._learning.snapshot() if self._learning is not None else None
        personal_revision = self.personal.revision if self.personal is not None else None
        if (self.suggestion is not None and self.suggestion.personal_revision == personal_revision
                and self.suggestion.learning_revision == (learning.revision if learning else None)):
            index = self.suggestion.index
            self._start_prediction(self.segments[index].start, self.segments[-1].end,
                                   self.segments[:index], self.suggestion.rows)
            return
        added_readings = self.personal.added_readings if self.personal is not None else ()
        lattice = self._lattice()
        run = len(lattice)  # the trailing kana run: no literal inside a prediction
        while run > 0 and lattice[run - 1]["kind"] != "literal":
            run -= 1
        starts = sorted(b for b in self._word_starts if run <= b < len(lattice))
        for start in starts[-MAX_TAILS:]:  # longest tail first
            index = next(i for i, s in enumerate(self.segments) if s.end > start)
            head = self.segments[:index]
            head_request = None
            try:
                if self.segments[index].start != start:
                    # Inside a clause (いい|天気): decode the typed head alone.
                    head_request = self._conversion_input(self._parts(lattice[:start]))
                    head_picks = head_request.decode(self._lex)
                    head = display_segments(head_request.parts, head_picks)
                    for segment in head:
                        segment.mark_shown()
                # A press crossing into the tail keeps the head's direction.
                tail = restrict(lattice, start, len(lattice),
                                press_pins(lattice, start, len(lattice), head))
                found = predict(tail, self._lex, self.predict_index, learning,
                                added_readings=added_readings)
            except Exception as exc:
                print(f"Prediction failed ({type(exc).__name__})", file=sys.stderr, flush=True)
                return
            if not found:
                continue
            if head_request is not None:
                self._display_key = head_request.key
                self._learning_view = head_request.learning
                self._word_starts = {start for run in head_picks or () for start in run.word_starts}
            self._start_prediction(start, len(lattice), head, found)
            return

    def _start_prediction(self, start: int, end: int, head: list[Segment],
                          rows: list[Candidate]) -> None:
        self._clear_suggestion()
        self._input_script = None
        stream = CandidateStream(iter(rows))
        stream.ensure(0)
        self.segments = head + [Segment(start, end, rows[0], fixed=True,
                                        choices=stream, context=PREDICTION)]
        self.segments[-1].mark_shown()
        self.converted = True
        self.predicting = True
        self.focus = len(head)
        self.composition = "".join(s.selected.surface for s in self.segments)
        self._open_cands()

    def _script_units(self, segment: Segment, script: str) -> list[str]:
        tokens = self.tokens[segment.start:segment.end]
        if script in KANA_SCRIPTS and not segment.literal:
            return [kana_script(c, script) for c in segment.selected.reading]
        if script in KANA_SCRIPTS:
            return [token.text for token in tokens]
        units = []
        for token in tokens:
            if isinstance(token, Literal) and token.frozen:
                units.append(token.text)
                continue
            text = to_half_width(token.text) if isinstance(token, Literal) else token.key
            if script == "full_alnum":
                text = "　" if text == " " else to_full_width(text)
            units.append(text)
        return units

    def _cycle_jis_script(self, *, alnum: bool) -> None:
        if self.predicting:
            self._cancel_conversion()
        if not self.segments:
            return
        if not self.converted:
            current = self._input_script or self.input_mode
            if alnum:
                script = "half_alnum" if current == "full_alnum" else "full_alnum"
            else:
                index = KANA_SCRIPTS.index(current) if current in KANA_SCRIPTS else -1
                script = KANA_SCRIPTS[(index + 1) % len(KANA_SCRIPTS)]
            self._set_input_script(script, move_to_end=False)
            return

        if self.focus < 0:
            return
        segment = self.segments[self.focus]
        if segment.literal and not alnum:
            return
        if alnum:
            full = "".join(self._script_units(segment, "full_alnum"))
            script = "half_alnum" if segment.selected.surface == full else "full_alnum"
        else:
            selected = segment.selected
            forms = [kana_script(selected.reading, style) for style in KANA_SCRIPTS]
            script = (KANA_SCRIPTS[(forms.index(selected.surface) + 1) % len(forms)]
                      if selected.kind == "kana" and selected.surface in forms else "hiragana")
        surface = "".join(self._script_units(segment, script))
        self._clear_cands()
        self.editing = False
        self._cursor = None
        segment.fixed, segment.raw = True, False
        segment.index = -1
        selected = segment.selected
        # A literal keeps its kind: a symbol or a run of digits has its own rows.
        kind = selected.kind if segment.literal else "alnum" if alnum else "kana"
        self._set_selection(self.focus, Candidate(surface, selected.reading, selected.score,
                                                  selected.lid, selected.rid, kind))

    def _set_input_script(self, script: str, *, move_to_end: bool = True) -> None:
        self._input_script = script
        if move_to_end:
            self._cursor = None
        self._clear_cands()
        self._clear_suggestion()
        self._show_input_reading()
        self._update_composition()

    def _freeze_input_script(self) -> None:
        """Keep the spelling of the last input run when another run starts."""
        if self._input_script is None:
            return
        for segment in self.segments:
            units = self._script_units(segment, self._input_script)
            self.tokens[segment.start:segment.end] = [Literal(text, frozen=True) for text in units]
        self._input_script = None

    def _to_script(self, script: str) -> None:
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
        show = not self.converted
        if show:
            self._show_conversion(self._conversion_input(self._parts()), converter=self.lm)
        else:
            self._clear_cands()
        if self.focus < 0:
            return
        segment = self.segments[self.focus]
        if segment.literal:
            return
        self.editing = False
        self._cursor = None
        self._prepare_cands(self.focus)
        stream = segment.choices
        assert stream is not None
        rows: list[int] = []
        i = 0
        while len(rows) < 2 and stream.ensure(i):
            if stream.cache[i].kind == "kana":
                rows.append(i)
            i += 1
        if not rows:
            return
        if script in ("hiragana", "katakana"):
            hiragana = script == "hiragana"
            default = rows[0] if hiragana or len(rows) == 1 else rows[1]
            self._select(self._next_kana_row(segment, hiragana=hiragana, default=default),
                         show=show)
            return
        hira = (segment.selected if segment.selected.kind == "kana"
                else stream.cache[rows[0]])
        if script == "half_katakana":
            surface, kind = half_katakana(hira.reading), "kana"
        else:
            keys = [t.get("key", "") for t in self._lattice()[segment.start:segment.end]]
            surface = alnum_spelling("".join(keys), segment.selected.surface
                                     if segment.selected.kind == "alnum" else None,
                                     full=script == "full_alnum")
            kind = "alnum"
        chosen = Candidate(surface, hira.reading, hira.score, hira.lid, hira.rid, kind)
        self._set_selection(self.focus, chosen)
        segment.fixed = True
        segment.raw = False
        segment.index = stream.find(chosen)  # -1: shown with no highlighted row
        if show:
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

    def forget_candidate(self) -> None:
        """Suppress the highlighted pair, then choose the newly ranked first row."""
        if (self._learning is None or not self.converted or self.focus < 0
                or not self.candidates or self.cand_index < 0):
            return
        segment = self.segments[self.focus]
        c = segment.selected
        if c.kind in ("literal", "number", "date") or not c.reading:
            return
        pairs = [(c.reading, c.surface)]
        if c.kind == "dictionary":
            pairs.extend((p.reading, p.surface) for p in c.words if word_piece(p, self._lex))
        if not self._learning.suppress_pairs(pairs):
            return
        if segment.context == PREDICTION:
            # The forgotten word leaves the list; back to the input if none remain.
            self._cancel_conversion()
            self._predict_key()
            return
        self._learning_view = self._learning.snapshot()
        segment.fixed = False
        self._prepare_cands(self.focus, reselect=True)
        segment.mark_shown()
        self._open_cands()

    def _delete_before(self) -> str | None:
        if self.converted and not self.editing and self.segments:
            self._delete_converted_char()
            return None
        return self._delete_at_cursor(before=True)

    def _edit_bounds(self) -> tuple[int, int]:
        if self.editing:
            segment = self.segments[self.focus]
            return segment.start, segment.end
        return 0, len(self.tokens)

    @property
    def caret(self) -> int | None:
        """Code-point offset in the composition, when it has an editable caret."""
        if self.editing:
            start, end = self._edit_bounds()
            prefix = sum(len(segment.selected.surface) for segment in self.segments[:self.focus])
            return prefix + (end if self._cursor is None else self._cursor) - start
        if not self.converted and self._reading_edit:
            end = len(self.tokens) if self._cursor is None else self._cursor
            length = 0
            for segment in self.segments:
                count = min(end, segment.end) - segment.start
                if count <= 0:
                    break
                script = self._input_script or self.input_mode
                length += sum(len(c) for c in self._script_units(segment, script)[:count])
            return length
        return None

    def _move_cursor(self, delta: int, *, pass_at_edge: bool = False) -> str | None:
        start, end = self._edit_bounds()
        cursor = end if self._cursor is None else self._cursor
        target = cursor + delta
        if start <= target <= end:
            self._set_cursor(target, end)
        elif self.editing:
            if 0 <= self.focus + delta < len(self.segments):
                self._move_segment(delta)
            elif pass_at_edge:
                return self._commit_and_pass_key()
        return None

    def _cursor_edge(self, *, end: bool) -> None:
        start, stop = self._edit_bounds()
        self._set_cursor(stop if end else start, stop)

    def _set_cursor(self, position: int, end: int) -> None:
        if self.predicting:  # cursor aliases inherited by the focused prediction list
            return
        self._cursor = None if position == end else position
        if not self.editing and not self._reading_edit and self._cursor is not None:
            self._reading_edit = True
            self._show_input_reading()
            self._update_composition()

    def _delete_at_cursor(self, *, before: bool, pass_at_edge: bool = False) -> str | None:
        start, end = self._edit_bounds()
        cursor = end if self._cursor is None else self._cursor
        index = cursor - 1 if before else cursor
        if not start <= index < end:
            if pass_at_edge and self.editing and self.focus == (0 if before else len(self.segments) - 1):
                return self._commit_and_pass_key()
            return None
        self._cursor = index if index < end - 1 else None
        if self.editing:
            clause = self.focus
            tokens = self.tokens[start:index] + self.tokens[index + 1:end]
            self._replace_edited_tokens(clause, tokens)
            if before and not tokens and clause == len(self.segments):
                self._open_tail_for_editing()
        else:
            del self.tokens[index]
            if self.tokens:
                self._refresh()
            else:
                self._clear_input()
        return None

    def _commit_and_pass_key(self) -> str:
        self.key_eat = False
        return self._commit()

    def _commit_at_cursor(self, *, only_inside: bool = False) -> str | None:
        if self._cursor is None or (caret := self.caret) is None:
            return None if only_inside else self._commit()
        suffix = len(self.composition) - caret
        text = self._commit()
        self.commit_caret_back = suffix
        return text

    def _delete_converted_char(self) -> None:
        # Delete the end of the whole conversion, regardless of the focused candidate.
        self._cursor = None
        index = len(self.segments) - 1
        segment = self.segments[index]
        selected = segment.selected
        text = selected.surface[:-1]
        if selected.surface == selected.reading:
            tokens = self.tokens[segment.start:segment.end - 1]
        else:
            # There is no character-to-keystroke map for a converted spelling.
            # Keep the visible remainder as typed text, without stale readings.
            tokens = [Literal(char) for char in text]
        self._replace_edited_tokens(index, tokens, text)
        if not text:
            self._open_tail_for_editing()

    def _open_tail_for_editing(self) -> None:
        # The tail disappeared. Open the preceding clause at its displayed
        # spelling so another deletion can continue from there.
        if not self.segments:
            return
        segment = self.segments[-1]
        text = segment.selected.surface
        if text == segment.selected.reading:
            self._show_edited_segment(len(self.segments) - 1, text)
        else:
            self._replace_edited_tokens(len(self.segments) - 1, [Literal(c) for c in text], text)

    def _replace_edited_tokens(self, index: int, tokens: list[Token | Literal],
                               text: str | None = None) -> None:
        segment = self.segments[index]
        delta = len(tokens) - (segment.end - segment.start)
        self.tokens[segment.start:segment.end] = tokens
        segment.end += delta
        for following in self.segments[index + 1:]:
            following.start += delta
            following.end += delta
        self._display_key = None
        self._word_starts.clear()
        if not tokens:
            del self.segments[index]
            if not self.segments:
                self._clear_input()
                return
            self.editing = False
            self._cursor = None
            self.focus = min(index, len(self.segments) - 1)
            self._clear_cands()
            self._update_composition()
            return
        segment.literal = any(isinstance(token, Literal) for token in tokens)
        if text is None:
            segments = self._decode_edited_segment(index, self._lattice())
            text = "".join(s.selected.reading for s in segments)
        self._show_edited_segment(index, text)

    def _show_edited_segment(self, index: int, reading: str) -> None:
        self._make_raw(index, reading)
        self.focus = index
        self.converted = self.editing = len(self.segments) > 1
        self._display_key = None
        self._clear_cands()
        self._update_composition()

    def _decode_edited_segment(self, index: int, lattice: list[dict]) -> list[Segment]:
        segment = self.segments[index]
        pins, left, _ = candidate_inputs(lattice, self.segments, index, self._left_id, self._lex)
        parts = self._parts(restrict(lattice, segment.start, segment.end, pins))
        prev = previous_bunsetsu(self.segments, index, self._left_bunsetsu, self._lex)
        picks = conversion_picks(parts, self._lex, self._learning_view, "", None,
                                 left_id=left, prev=prev)
        return display_segments(parts, picks)

    def _convert_edited_segment(self) -> None:
        index = self.focus
        segment = self.segments[index]
        lattice = self._lattice()
        if segment.literal:
            parts = self._decode_edited_segment(index, lattice)
            for part in parts:
                part.start += segment.start
                part.end += segment.start
                part.mark_shown()
            self.segments[index:index + 1] = parts
        else:
            self._convert_raw(index, lattice)
            self._apply_segment_learning(index)
        self.editing = False
        self._cursor = None
        self._update_composition()

    def _pass_empty_key(self, chord: Chord) -> None:
        if chord.mods in (0, SHIFT):
            if chord.vk == VK_RETURN:
                return  # keep the context available to the next input
            if chord.vk == VK_BACK:
                tail = self._committed_context[:-1]
                self._clear_context()
                self._lm_context = self._committed_context = tail
                return
        self._clear_context()

    def _move_segment(self, delta: int) -> None:
        # Every segment is a stop: a symbol or a run of digits has its own rows.
        if self.focus >= 0:
            focus = max(0, min(self.focus + delta, len(self.segments) - 1))
            if focus != self.focus:
                self.editing = False
                self._cursor = None
                self.focus = focus
            self._clear_cands()

    def _accept_candidate(self) -> None:
        self.segments[self.focus].fixed = True
        self._move_segment(1)

    def _select_row(self, row: int, *, close: bool = False) -> None:
        if self.focus >= 0 and row < len(self.candidates):
            self._select(self.candidate_page * PAGE_SIZE + row, show=not close)
            if close:
                self._clear_cands()

    def _open_cands(self) -> None:
        self._clear_cands()
        if self.focus < 0:
            return
        segment = self.segments[self.focus]
        if segment.raw and segment.literal:
            self._convert_edited_segment()  # as _cycle: its parts have their own rows
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
        prev = previous_bunsetsu(self.segments, index, self._left_bunsetsu, self._lex)
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
            heads = candidate_heads(segment, self._lex, learning, prev, repeat)
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

    def _resize(self, delta: int, *, convert: bool = False) -> None:
        """Override one automatic boundary, keeping all other intervals intact."""
        if self.focus < 0:
            return
        segment = self.segments[self.focus]
        if segment.literal or self.predicting:
            return  # a digit run keeps its interval; predictions span the input
        self._clear_cands()
        following = self.focus + 1
        neighbor = self.segments[following] if following < len(self.segments) else None
        if delta > 0 and (neighbor is None or neighbor.literal):
            return
        if delta < 0 and segment.end - segment.start == 1:
            return
        if not self.resizing and not convert:
            self._resize_origin = ([replace(s) for s in self.segments], self.editing)
        self.editing = False
        reading = segment.selected.reading
        if delta > 0:
            assert neighbor is not None
            neighbor_reading = neighbor.selected.reading
            segment.end += 1
            neighbor.start += 1
            reading += neighbor_reading[0]
            if neighbor.start == neighbor.end:
                del self.segments[following]
            else:
                self._make_raw(following, neighbor_reading[1:])
        else:
            segment.end -= 1
            self.segments.insert(following, Segment(segment.end, segment.end + 1, segment.selected))
            self._make_raw(following, reading[-1])
            reading = reading[:-1]
        self._make_raw(self.focus, reading)
        if convert:
            self._end_resize()
        else:
            self._update_composition()
            self.resizing = True

    def _cancel_resize(self) -> None:
        if self._resize_origin is not None:
            self.segments, self.editing = self._resize_origin
            self._update_composition()

    def _make_raw(self, index: int, reading: str) -> None:
        segment = self.segments[index]
        segment.selected = Candidate(reading, reading, 0, BOS_ID, BOS_ID, "raw")
        segment.raw = True
        segment.fixed = False
        segment.choices = segment.context = None
        segment.index = 0
        segment.zenz = segment.order = segment.source = segment.shown = None

    def _convert_raw(self, index: int, lattice: list[dict]) -> None:
        segment = self.segments[index]
        pins, left, right = candidate_inputs(lattice, self.segments, index, self._left_id, self._lex)
        segment.selected = next(candidates(
            restrict(lattice, segment.start, segment.end, pins), self._lex, left, right,
            learning=self._learning_view))
        segment.source = segment.selected
        segment.raw = False

    def _apply_segment_learning(self, index: int) -> None:
        segment = self.segments[index]
        repeat = self._repeat and not self._partial and len(self.segments) == 1
        prev = previous_bunsetsu(self.segments, index, self._left_bunsetsu, self._lex)
        learned, _ = candidate_heads(segment, self._lex, self._learning_view, prev, repeat)
        if learned is not None:
            segment.selected = learned

    def _end_resize(self) -> None:
        # The base conversion uses the right POS. Learning uses the left
        # selection, which can itself be a learned spelling.
        raw = [i for i, segment in enumerate(self.segments) if segment.raw and not segment.literal]
        lattice = self._lattice()
        for i in reversed(raw):
            self._convert_raw(i, lattice)
        for i in raw:
            self._apply_segment_learning(i)
        self._update_composition()

    def _clear_cands(self) -> None:
        self.candidates = []
        self.candidate_kinds = []
        self.candidate_notes = []
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
        self.candidate_notes = [candidate_note(c) for c in page]
        self.cand_index = segment.index - start

    def _select(self, index: int, *, show: bool = True) -> None:
        if self.focus < 0:
            return
        segment = self.segments[self.focus]
        stream = segment.choices
        if stream is not None and stream.ensure(index):
            segment.index = index
            self._set_selection(self.focus, stream.cache[index])
            segment.fixed = True
            segment.raw = False
            if show:
                self._show_page()

    def _select_last(self) -> None:
        if self.focus >= 0:
            stream = self.segments[self.focus].choices
            if stream is not None:
                self._select(stream.last())

    def _cycle(self, delta: int, *, wrap_start: bool = True) -> None:
        if self.focus < 0:
            return
        if self.segments[self.focus].raw:
            self._convert_edited_segment()
        segment = self.segments[self.focus]
        if not self.candidates or segment.choices is None:
            self._prepare_cands(self.focus)
        stream = segment.choices
        if stream is None:
            return
        index = segment.index + delta
        if index < 0:
            if not wrap_start:
                return
            index = stream.last()
        elif not stream.ensure(index):
            index = 0
        self._select(index)

    def _page(self, delta: int, *, wrap_start: bool = False) -> None:
        if self.focus < 0:
            return
        stream = self.segments[self.focus].choices
        if stream is None:
            return
        page = self.candidate_page + delta
        if page < 0:
            if not wrap_start:
                return
            page = stream.last() // PAGE_SIZE
        start = page * PAGE_SIZE
        if stream.ensure(start):
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
                insert += self._run_command(self.keymap.lookup(self.phase, SPACE)) or ""
                continue
            mapped = to_lattice_token(tok, self._table)
            if mapped is None:
                continue  # An empty face (] alone, Q right, ...): nothing is typed.
            if self.converted and not self.editing:
                insert += self._commit(reset_input=False)
            if self.max_tokens is not None and len(self.tokens) >= self.max_tokens:
                continue  # Keep both sides of the caret when the input is full.
            if isinstance(tok, AmbShift) and tok.press is not None:
                if mapped["kind"] == "literal":
                    self._press_alias[tok.press] = self._next_alias
                    self._next_alias -= 1
                elif tok.press in self._press_alias:
                    tok = AmbShift(tok.key, self._press_alias[tok.press], tok.turn)
            if mapped["kind"] == "literal" and not isinstance(tok, Literal):
                tok = Literal(mapped["text"])
            self._insert_token(tok)
        return insert or None

    def _insert_token(self, token: Token | Literal) -> None:
        self._freeze_input_script()
        start, end = self._edit_bounds()
        index = end if self._cursor is None else self._cursor
        if isinstance(token, (AmbShift, Literal)):
            self._split_press_at(index)
        self._cursor = index + 1 if index < end else None
        if self.editing:
            tokens = [*self.tokens[start:index], token, *self.tokens[index:end]]
            self._replace_edited_tokens(self.focus, tokens)
        else:
            self.tokens.insert(index, token)
            self._clear_cands()
            self._refresh()

    def _split_press_at(self, index: int) -> None:
        # An inserted literal or a new Space press ends an old press. Give the
        # right half a new id while keeping its original thumb-turn parity.
        if index == 0 or index == len(self.tokens):
            return
        left = next((t for t in reversed(self.tokens[:index]) if not isinstance(t, Plain)), None)
        if not isinstance(left, AmbShift) or left.press is None:
            return
        right = index
        while right < len(self.tokens) and isinstance(self.tokens[right], Plain):
            right += 1
        if right == len(self.tokens):
            return
        first = self.tokens[right]
        if not isinstance(first, AmbShift) or first.press != left.press:
            return
        alias = self._next_alias
        self._next_alias -= 1
        plan = Plan(self._lattice())
        directions = frozenset(direction for _, direction in plan.branches[right]
                               if direction is not None)
        if len(directions) == 1:
            self._carry[left.press] = self._carry[alias] = directions
        for pos in range(right, len(self.tokens)):
            token = self.tokens[pos]
            if isinstance(token, AmbShift) and token.press == left.press:
                self.tokens[pos] = replace(token, press=alias)

    def _insert_space(self, text: str) -> str:
        self._note_commit(text)
        return text

    def _add_space(self, text: str) -> str | None:
        """Ctrl+Space / Ctrl+Shift+Space: a space of a fixed width.

        With no input it goes to the document. Otherwise it is typed into the
        input or the clause being edited. After a conversion, _ingest commits
        first and the space starts the next input (MS-IME).
        """
        if not self.tokens:
            return self._insert_space(text)
        return self._ingest([Literal(text)])

    def _convert(self) -> None:
        if self.predicting:
            self._cancel_conversion()
        request = self.conversion_request() if self.lm_deferred else None
        if request is not None:
            self._await = request
            return
        self._show_conversion(self._conversion_input(self._parts()), converter=self.lm)

    def _lattice(self) -> list[dict]:
        out = []
        for t in self.tokens:
            d = to_lattice_token(t, self._table)
            assert d is not None  # _ingest drops empty faces before inserting tokens.
            carried = self._carry.get(d.get("press")) if self._carry else None
            if carried is not None:
                # The committed head chose this press's direction (部分確定).
                d = {**d, "faces": {face: kana for face, kana in d["faces"].items()
                                    if face_of(face, d["turn"]) in carried}}
            out.append(d)
        return out

    def _parts(self, lattice: list[dict] | None = None) -> list[str | list[dict]]:
        """Literal texts and kana runs; a literal ends the press (ChordFsm.reset,
        or a new press number after a symbol chord), so no press crosses one."""
        if lattice is None:
            lattice = self._lattice()
        parts: list[str | list[dict]] = []
        run: list[dict] = []
        for token in lattice:
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
        self._clear_suggestion()
        self._suggest_dirty = self.prediction == "auto" and not self.converted
        self.predicting = False
        if request is None:
            request = self._conversion_input(self._parts())
        self._display_key = request.key
        self._learning_view = request.learning
        if picks is None and self._lex is not None:
            picks = request.decode(self._lex)
        self.segments = display_segments(request.parts, picks)
        if not self.converted:
            self._show_input_reading()
        for segment in self.segments:
            segment.mark_shown()
        self._word_starts = {start for run in picks or () for start in run.word_starts}
        self.focus = _first_stop(self.segments)
        self.composition = "".join(s.selected.surface for s in self.segments)

    def _show_input_reading(self) -> None:
        script = self._input_script or self.input_mode
        if not self._reading_edit and self._input_script is None and script not in KANA_SCRIPTS[1:]:
            return
        for index, segment in enumerate(self.segments):
            if self._reading_edit and not segment.literal:
                self._make_raw(index, segment.selected.reading)
            if self._input_script is not None or not segment.literal:
                surface = "".join(self._script_units(segment, script))
                segment.selected = replace(segment.selected, surface=surface)
                if self._input_script is not None:
                    segment.mark_shown()
        self._display_key = None  # conversion must compute the regular candidates

    def _sync_personal(self) -> None:
        if self.personal is not None and self._lex is not None:
            self.personal.sync(self._lex)

    def _confirm(self, segments: list[Segment], *, standalone: bool) -> None:
        if self._learning is not None and self._lex is not None:
            # Only the user's own choices: a commit of what the engine showed
            # changes nothing later (CONVERSION「学習」).
            self._learning.confirm(
                [s.selected for s in segments], self._lex,
                prev=self._left_bunsetsu, repeat=self._repeat and standalone,
                chosen=[not s.raw and s.chosen() for s in segments],
                shown=[s.shown for s in segments])

    def _commit(self, *, reset_input: bool = True, suffix: str = "") -> str:
        text = self.composition
        if text:
            standalone = len(self.segments) == 1 and not self._partial
            self._confirm(self.segments, standalone=standalone)
            last = self.segments[-1]
            self._note_commit(text + suffix, None if suffix or last.raw else last,
                              standalone=standalone and not suffix)
        if reset_input:
            self._reset_input()
        else:
            self._clear_input()
        return text + suffix

    def _delete_last_and_commit(self) -> str:
        text = self.composition[:-1]
        if text:
            # The last clause loses a character: what it showed is not a choice.
            self._confirm(self.segments[:-1], standalone=False)
            self._note_commit(text)
        self._reset_input()
        return text

    def _clear_input(self) -> None:
        """The input is gone (committed); the connection's state stays."""
        self._end_alnum_hold()
        self._clear_suggestion()
        self._input_script = None
        self.tokens.clear()
        self.segments.clear()
        self._partial = False
        self._display_key = None
        self._learning_view = None
        self.focus = -1
        self.composition = ""
        self.converted = False
        self.resizing = False
        self.editing = False
        self._cursor = None
        self._reading_edit = False
        self._resize_origin = None
        self.predicting = False
        self._clear_cands()

    def _commit_prefix(self) -> str:
        """部分確定 (Ctrl+↓): commit the first interval only.

        The first clause, or the first literal (a run of digits or of 英数の続き
        is one). The rest keeps its intervals, selections and fixed state.
        """
        if not self.segments:
            return ""
        if len(self.segments) == 1:
            return self._commit(reset_input=False)
        head = self.segments[0]
        end = head.end
        text = head.selected.surface
        if not head.raw:
            self._confirm([head], standalone=False)
        self._note_commit(text, None if head.raw else head)
        self._partial = True
        self._display_key = None
        # The directions the committed reading gives each press (the thumbs
        # of one press alternate); the remaining chords of a press keep it.
        chosen = Plan(self._lattice()).directions(head.start, head.end, head.selected.reading)
        del self.tokens[:end]
        if self._cursor is not None:
            self._cursor = max(0, self._cursor - end)
        remaining = {t.press for t in self.tokens if isinstance(t, AmbShift)}
        for press, dirs in chosen.items():
            if press in remaining and dirs and dirs != SIDES:
                self._carry[press] = dirs
        self.segments = self.segments[1:]
        if self.editing:
            self._cursor = None
        self.editing = False
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
        self._clear_cands()
        return text

    def _commit_one_char(self) -> str:
        """Shift+↓ before conversion: commit the first press (one kana or literal).

        MS-IME commits the first unit it typed (one romaji syllable, one
        letter or digit); a press is that unit here. 英数の続き started by
        Shift+letter ends; under Shift+CapsLock everything is committed.
        """
        if not self.segments:
            return ""
        if self._alnum_held:
            return self._commit(reset_input=False)
        head = self.segments[0]
        # Commit the first input unit, which can display two half-width characters.
        text = self._script_units(head, self._input_script or self.input_mode)[0]
        self._note_commit(text)
        if len(self.tokens) == 1:
            self._clear_input()
            return text
        self._partial = True
        chosen = Plan(self._lattice()).directions(0, 1, head.selected.reading[0])
        del self.tokens[0]
        if self._cursor is not None:
            self._cursor = max(0, self._cursor - 1)
        remaining = {t.press for t in self.tokens if isinstance(t, AmbShift)}
        for press, dirs in chosen.items():
            if press in remaining and dirs and dirs != SIDES:
                self._carry[press] = dirs
        self._end_alnum()
        self._refresh()
        return text

    def _note_commit(self, text: str, last: Segment | None = None, *,
                     standalone: bool = False) -> None:
        """Advance the current input and remember what this connection committed."""
        self.commit_caret_back = 0
        right_id = BOS_ID
        if self._lex is not None and last is not None:
            if last.literal:
                right_id = left_id_after(last.selected.reading, self._lex)
            elif 0 <= last.selected.rid < self._lex.pos_size + len(self._lex.numeral_pos):
                right_id = last.selected.rid
        self._committed_context = _append_context(self._committed_context, text)
        self._lm_context = _append_context(self._lm_context, text)
        self._left_id = right_id
        self._left_bunsetsu = (normal_bunsetsu(last.selected, self._lex)
                               if last is not None and self._lex is not None else None)
        self._repeat = standalone and self._left_bunsetsu is not None
        self._last_commit = CommitContext(text[-CONTEXT_CHARS:], right_id,
                                          self._left_bunsetsu, self._repeat)


def _first_stop(segments: list[Segment]) -> int:
    """Conversion starts on the first kana interval; without kana, on the first segment."""
    return next((i for i, s in enumerate(segments) if not s.literal),
                0 if segments else -1)
