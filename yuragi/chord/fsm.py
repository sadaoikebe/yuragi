"""Host-side NICOLA chord state machine (S1–S7). The specification is docs/JIS-FSM.md.

The thumb keys are Space (either thumb) and, on JIS 106, 無変換 (left thumb
only) and 変換 (right thumb only). One thumb stroke presses one of them, or
two within JOIN_MS. A stroke is fresh until it is used: by a chord (the
character with the thumb) or by a lone thumb key (ThumbTap). A used Space
still held is a carrier: a character typed under it may be a chord with the
other thumb, which gives no signal.

| state | fresh stroke | carrier | pending character |
| --- | --- | --- | --- |
| S1 | no | no | none (idle) |
| S2 | no | no | yes |
| S3 | yes | either | none (thumb first) |
| S4 | yes | either | yes, the character came first |
| S5 | yes | either | yes, the thumb came first |
| S6 | no | yes | none |
| S7 | no | yes | yes: a character typed under the carrier |

With Space as the only thumb key (ANSI 101) a stroke is one Space press and
S3–S5 never have a carrier.

S1–S6 decide with the 80 ms window (T) and the 20 ms overlap (V). The
deadline is the stroke's start + T in S3/S4 and character down + T in
S2/S5/S7. If a short overlap leaves one key pending, its original down time
sets the deadline.

S7 decides at its exit, comparing the overlap with the carrier ("cover")
with what would still be left of the character after it, estimated from the
last released character's held length ("last"): a chord if
cover >= last - cover, else a plain character. No last length yet (first
stroke): T stands in. Under a carrier used by a lone Space the character is
plain, and so it is while 無変換 and 変換 are both held (no thumb is free).

The machine does not decide which thumb it was. Every AmbShift carries the
evidence: the thumb keys its stroke pressed (struck), the ones other strokes
held (held, over), and its place in the chain of one Space press (press,
turn), where the thumbs alternate. thumb_side reads the first three.

Plain, AmbShift and ThumbTap are decided once, from key order and timing;
their kind and order never change. ThumbJoin and ThumbOver only add evidence
to an AmbShift already emitted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Literal, Mapping

TIMEOUT_MS = 80
OVERLAP_MS = 20
JOIN_MS = 30  # one thumb stroke presses its second key within this of the first

# The thumb keys only one thumb presses. Space is either thumb's, unless the user
# gives it one (thumb_sides): then it is a thumb key like 無変換 and 変換, with no carrier.
THUMB_SIDE = {"muhenkan": "left", "henkan": "right"}
_OTHER = {"left": "right", "right": "left"}

State = Literal["S1", "S2", "S3", "S4", "S5", "S6", "S7"]


@dataclass(frozen=True, slots=True)
class Plain:
    key: str


@dataclass(frozen=True, slots=True)
class AmbShift:
    """A chord: the key with one thumb stroke.

    The other fields say how it was typed, not what it is, so they do not
    take part in equality. The state machine always sets them; a chord made
    without them (a test, an expected reading) belongs to no press.

    - press, turn: the chain of one Space press and the position in it (1, 2, ...).
      The session renumbers press; origin keeps the machine's (press, turn).
    - struck: the thumb keys of the stroke, in the order pressed. Empty: the
      stroke gave no signal (the other thumb on a Space already down).
    - held: the thumb keys other strokes held when this one began.
    - over: 無変換/変換 pressed alone while this stroke was held.
    """
    key: str
    press: int | None = field(default=None, compare=False)
    turn: int | None = field(default=None, compare=False)
    struck: tuple[str, ...] = field(default=(), compare=False)
    held: frozenset[str] = field(default=frozenset(), compare=False)
    over: tuple[str, ...] = field(default=(), compare=False)
    origin: tuple[int, int] | None = field(default=None, compare=False)


@dataclass(frozen=True, slots=True)
class ThumbTap:
    """A thumb key alone: the function of that key."""
    key: str = "space"


@dataclass(frozen=True, slots=True)
class ThumbJoin:
    """A key the stroke of an emitted AmbShift (origin = (press, turn)) pressed late: add it to struck."""
    press: int
    turn: int
    key: str


@dataclass(frozen=True, slots=True)
class ThumbOver:
    """A key pressed alone while the stroke of an emitted AmbShift was held: add it to over."""
    press: int
    turn: int
    key: str


Token = Plain | AmbShift | ThumbTap | ThumbJoin | ThumbOver


def thumb_sides(space: str | None = None) -> Mapping[str, str]:
    """The thumb keys one thumb presses: THUMB_SIDE, and Space when it is given a side."""
    return THUMB_SIDE if space is None else {**THUMB_SIDE, "space": space}


def thumb_side(struck: Iterable[str], held: Iterable[str] = (), over: Iterable[str] = (),
               sides: Mapping[str, str] = THUMB_SIDE) -> str | None:
    """The thumb the evidence settles, or None (no evidence, or a mis-stroke giving both).

    A stroke that pressed 無変換 is the left thumb's. A stroke made while
    another one held 変換 is the left thumb's too: the right one was busy.
    """
    found = {sides[key] for key in struck if key in sides}
    found |= {_OTHER[sides[key]] for key in (*held, *over) if key in sides}
    return next(iter(found)) if len(found) == 1 else None


def _one_thumb(keys: Iterable[str], sides: Mapping[str, str]) -> bool:
    return len({sides[key] for key in keys if key in sides}) < 2


@dataclass(slots=True)
class _Stroke:
    keys: list[str]
    start: int
    before: frozenset[str]  # thumb keys of other strokes held at start
    linked: bool  # began under a carrier used by a chord: the same chain
    first: str  # the key whose function a lone stroke runs
    over: list[str] = field(default_factory=list)
    use: Literal["fresh", "chord", "tap", "void"] = "fresh"
    ended: bool = False  # one of its keys is up
    token: tuple[int, int] | None = None  # the chord it made, until a reset


@dataclass
class ChordFsm:
    sides: Mapping[str, str] = field(default_factory=thumb_sides)  # thumb key → its thumb
    state: State = "S1"
    held: dict[str, int] = field(default_factory=dict)  # thumb key → down time
    stroke: _Stroke | None = None  # the last thumb stroke begun
    carrier: Literal["chord", "tap"] | None = None  # how the used Space still held was used
    m_key: str | None = None  # the pending character
    m_time: int = 0
    m_held: set[str] = field(default_factory=set)  # thumb keys held at its down
    m_under: Literal["chord", "tap"] | None = None  # the carrier it overlapped
    m_from: int = 0  # that overlap
    m_to: int | None = None
    press: int = 0  # serial number of the current (or last) chain
    turn: int = 0  # AmbShifts emitted in it
    timer_deadline: int | None = None
    last_length: int | None = None  # held length of the last released character
    pressed_at: dict[str, int] = field(default_factory=dict)  # character key → down time

    def reset(self) -> None:
        """Close the judgment at a literal/edit boundary. Keys may still be down."""
        self.state = "S1"
        self.m_key = self.carrier = self.m_under = self.timer_deadline = None
        if self.stroke is not None:
            if self.stroke.use == "fresh":
                self.stroke.use = "void"
            self.stroke.token = None
        self.press += 1
        self.turn = 0

    def clear(self) -> None:
        """reset, and no key is down: their releases will not arrive (focus loss)."""
        self.reset()
        self.held.clear()
        self.stroke = None
        self.pressed_at.clear()

    def forget(self, key: str) -> None:
        """After reset: a key whose release will not be passed here."""
        self.pressed_at.pop(key, None)
        self.held.pop(key, None)

    # -- procedures (JIS-FSM.md §6) --------------------------------------

    def _hold(self, key: str, now: int) -> None:
        self.m_key, self.m_time, self.m_held = key, now, set(self.held)
        self.m_under, self.m_from, self.m_to = self.carrier, now, None

    def _begin(self, key: str, now: int, after: _Stroke | None = None) -> None:
        """A new stroke. after: the fresh stroke it supersedes, which ends without a tap."""
        stroke = _Stroke([], now, frozenset(self.held), self.carrier == "chord", key)
        if after is not None:
            stroke.first, stroke.over = after.first, after.over
        self.stroke = stroke
        self._add(key)

    def _add(self, key: str) -> None:
        stroke = self.stroke
        stroke.keys.append(key)
        if stroke.linked and key != "space":
            stroke.over.append(key)

    def _fits(self, key: str, now: int) -> bool:
        """The key is the fresh stroke's own: pressed soon after its first, by the same thumb."""
        stroke = self.stroke
        return now - stroke.start <= JOIN_MS and _one_thumb((*stroke.keys, key), self.sides)

    def _plain(self) -> list[Token]:
        assert self.m_key is not None
        token = Plain(self.m_key)
        self.m_key = None
        return [token]

    def _shift(self) -> list[Token]:
        """The pending character with the fresh stroke."""
        assert self.m_key is not None
        stroke = self.stroke
        if not stroke.linked:
            self.press += 1
            self.turn = 0
        self.turn += 1
        at = (self.press, self.turn)
        token = AmbShift(self.m_key, *at, tuple(stroke.keys), stroke.before, origin=at)
        stroke.use, stroke.token = "chord", at
        if self._carries(stroke):
            self.carrier = "chord"
        self.m_key = None
        return [token]

    def _unseen(self) -> list[Token]:
        """The pending character with a stroke that gave no signal."""
        assert self.m_key is not None
        self.turn += 1
        at = (self.press, self.turn)
        token = AmbShift(self.m_key, *at, held=frozenset(self.m_held), origin=at)
        self.m_key = None
        return [token]

    def _tap(self) -> list[Token]:
        """The fresh stroke alone."""
        stroke = self.stroke
        out: list[Token] = []
        if self.turn >= 1:
            out += [ThumbOver(self.press, self.turn, key) for key in stroke.over]
        out.append(ThumbTap(stroke.first))
        stroke.use = "tap"
        if self._carries(stroke):
            self.carrier = "tap"
            if self.m_key is not None:
                self.m_under, self.m_from, self.m_to = "tap", self.m_time, None
        self.press += 1
        self.turn = 0
        return out

    def _carries(self, stroke: _Stroke) -> bool:
        """The used stroke leaves a carrier: its Space is still down, and Space is either thumb's."""
        return "space" in stroke.keys and "space" in self.held and "space" not in self.sides

    def _cover(self, now: int) -> int:
        return (now if self.m_to is None else min(now, self.m_to)) - self.m_from

    def _no_free_thumb(self) -> bool:
        return not _one_thumb(self.m_held, self.sides)

    def _follower(self, now: int) -> list[Token]:
        """A character under the carrier, at the carrier's release or the next character: the cover comparison."""
        if self.m_under == "tap" or self._no_free_thumb():
            return self._plain()
        cover = self._cover(now)
        last = self.last_length if self.last_length is not None else TIMEOUT_MS
        return self._unseen() if cover >= last - cover else self._plain()

    def _held_follower(self) -> list[Token]:
        """A character under the carrier, at its own release or the deadline: a chord."""
        if self.m_under == "tap" or self._no_free_thumb():
            return self._plain()
        return self._unseen()

    def _unpaired(self, now: int, by_release: bool) -> list[Token]:
        """The pending character that did not go with the fresh stroke."""
        if self.m_under is None:
            return self._plain()
        if by_release and self.m_to is None:
            return self._held_follower()
        return self._follower(now)

    def _rest(self) -> None:
        """The state once no stroke is fresh."""
        if self.carrier is not None:
            self.state = "S7" if self.m_key is not None else "S6"
        else:
            self.state = "S2" if self.m_key is not None else "S1"
            self.m_under = None

    def _set_timer(self) -> None:
        if self.state in ("S1", "S6"):
            self.timer_deadline = None
        elif self.state in ("S3", "S4"):
            self.timer_deadline = self.stroke.start + TIMEOUT_MS
        else:
            self.timer_deadline = self.m_time + TIMEOUT_MS

    # -- events (JIS-FSM.md §7) ------------------------------------------

    def on_down(self, kind: str, key: str, now: int) -> list[Token]:
        if kind == "M":
            self.pressed_at[key] = now
            out = self._m_down(key, now)
        elif kind == "O" and key not in self.held:
            out = self._o_down(key, now)
        else:
            return []
        self._set_timer()
        return out

    def on_up(self, kind: str, key: str, now: int) -> list[Token]:
        if kind == "M":
            out = self._m_up(now) if key == self.m_key else []
            start = self.pressed_at.pop(key, None)
            if start is not None:
                self.last_length = now - start
        elif kind == "O" and key in self.held:
            out = self._o_up(key, now)
        else:
            return []
        self._set_timer()
        return out

    def on_timeout(self, now: int) -> list[Token]:
        if self.timer_deadline is None or now < self.timer_deadline:
            return []
        st = self.state
        out: list[Token] = []
        if st == "S2":
            out = self._plain()
            self.state = "S1"
        elif st == "S3":
            out = self._tap()
            self._rest()
        elif st in ("S4", "S5"):
            out = self._shift()
            self._rest()
        elif st == "S7":
            out = self._held_follower()
            self.state = "S6"
        self._set_timer()
        return out

    def _m_down(self, key: str, now: int) -> list[Token]:
        st = self.state
        out: list[Token] = []
        if st == "S1":
            self._hold(key, now)
            self.state = "S2"
        elif st == "S2":
            out = self._plain()
            self._hold(key, now)
        elif st == "S3":
            self._hold(key, now)
            self.state = "S5"
        elif st == "S4":
            t1 = self.stroke.start - self.m_time
            t2 = now - self.stroke.start
            if t1 <= t2:  # a tie goes to the first character (NICOLA 5.4.2)
                out = self._shift()
                self._hold(key, now)
                self._rest()
            else:
                out = self._unpaired(now, False)
                self._hold(key, now)
                self.state = "S5"
        elif st == "S5":
            out = self._shift()
            self._hold(key, now)
            self._rest()
        elif st == "S6":
            self._hold(key, now)
            self.state = "S7"
        elif st == "S7":
            out = self._follower(now)
            self._hold(key, now)
        return out

    def _o_down(self, key: str, now: int) -> list[Token]:
        st = self.state
        stroke = self.stroke
        out: list[Token] = []
        if st in ("S3", "S4", "S5") and self._fits(key, now):
            self._add(key)
        elif st == "S3":
            self._begin(key, now, after=stroke)
        elif st == "S5" and self.m_time - stroke.start > now - self.m_time:
            # The character goes with the nearer stroke: the one beginning now.
            self._begin(key, now, after=stroke)
            self.state = "S4"
        elif st in ("S4", "S5"):
            out = self._shift()
            self._begin(key, now)
            self.state = "S3"
        elif (stroke is not None and stroke.use in ("chord", "void") and not stroke.ended
              and self._fits(key, now)):
            # The stroke already used pressed this key late.
            stroke.keys.append(key)
            if stroke.token is not None:
                out = [ThumbJoin(*stroke.token, key)]
            if self.m_key is not None:
                self.m_held.add(key)
            if key == "space" and stroke.use == "chord" and "space" not in self.sides:
                self.carrier = "chord"
                if self.m_key is not None:
                    self.m_under, self.m_from, self.m_to = "chord", now, None
                self.state = "S7" if self.m_key is not None else "S6"
        else:
            self._begin(key, now)
            self.state = "S4" if self.m_key is not None else "S3"
        self.held[key] = now
        return out

    def _m_up(self, now: int) -> list[Token]:
        st = self.state
        out: list[Token] = []
        if st == "S2":
            out = self._plain()
            self.state = "S1"
        elif st == "S4":
            t1 = self.stroke.start - self.m_time
            t2 = now - self.stroke.start
            if t1 > t2 and t2 < OVERLAP_MS:  # a tie is a chord (NICOLA 5.5.2, n = 1)
                out = self._unpaired(now, True)
                self.state = "S3"
            else:
                out = self._shift()
                self._rest()
        elif st == "S5":
            out = self._shift()
            self._rest()
        elif st == "S7":
            out = self._held_follower()
            self.state = "S6"
        return out

    def _o_up(self, key: str, now: int) -> list[Token]:
        del self.held[key]
        st = self.state
        stroke = self.stroke
        out: list[Token] = []
        if stroke is not None and key in stroke.keys and not stroke.ended:
            stroke.ended = True  # a stroke ends when its first key goes up
            if stroke.use == "fresh":
                if st == "S3":
                    out = self._tap()
                elif st == "S4":
                    out = self._shift()
                else:
                    t1 = self.m_time - stroke.start
                    t2 = now - self.m_time
                    out = self._tap() if t1 > t2 and t2 < OVERLAP_MS else self._shift()
                self._rest()
                return out
        if key == "space" and self.carrier is not None:
            if st in ("S4", "S5"):
                if self.m_under is not None:
                    self.m_to = now
            elif st == "S6":
                self.state = "S1"
            elif st == "S7":
                if self.m_under == "tap" or self._cover(now) < OVERLAP_MS:
                    self.m_under = None  # the character stays pending; its deadline stands
                    self.state = "S2"
                else:
                    out = self._follower(now)
                    self.state = "S1"
            self.carrier = None
        return out
