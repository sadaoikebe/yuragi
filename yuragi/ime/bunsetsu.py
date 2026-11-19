"""Segment boundaries and exact, lazy candidate search, independent of 1-best pruning."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from heapq import heappop, heappush
from itertools import count
from typing import Iterator

from yuragi.lattice.alternation import Plan, admits, after
from yuragi.lattice.decode import Piece
from yuragi.lattice import mozc_dict
from yuragi.lattice.mozc_dict import BOS_ID, UNK_COST, MozcLex, require_dict_files
from yuragi.lattice.token_viterbi import BOUNDARY_RID, end_cost, spans_from, word_cost

from .dates import date_spellings

# Half a single unknown-character penalty. This bounds implausible dictionary
# analyses, not the number of homonyms, and never limits the kana escape route.
COST_WINDOW = UNK_COST // 2
PAGE_SIZE = 9
# Symbols from the reading (Mozc's symbol rewriter simplified):
# at most SYMBOL_HEAD symbols after SYMBOL_OFFSET ordinary rows; the rest
# last. The learned symbol comes first overall.
SYMBOL_OFFSET = 3
SYMBOL_HEAD = 6


@lru_cache(maxsize=1)
def _pos_names() -> dict[int, str]:
    directory = mozc_dict.DICT_DIR  # read at call time so --dict-dir overrides apply
    require_dict_files(["id.def"], directory)
    return {int(i): name.strip() for line in (directory / "id.def").read_text(
        encoding="utf-8").splitlines() for i, name in [line.split(None, 1)]}


def content(lid: int) -> bool:
    p = _pos_names().get(lid, "").split(",")
    if p[0] in ("名詞", "動詞", "形容詞"):
        return p[1] not in ("接尾", "非自立")
    return p[0] in ("副詞", "連体詞", "接続詞", "感動詞", "接頭詞")


@dataclass(frozen=True)
class Candidate:
    surface: str
    reading: str
    score: int
    lid: int
    rid: int
    kind: str = "dictionary"
    word_cost: int | None = None  # raw internal cost, without neighbor transitions/learning


@dataclass
class Segment:
    start: int
    end: int
    selected: Candidate
    literal: bool = False
    fixed: bool = False
    choices: CandidateStream | None = None
    context: tuple | None = None
    index: int = 0


def segments_from(pieces: list[Piece], offset: int, lex: MozcLex | None = None,
                  *, learning=None) -> list[Segment]:
    # A kana run has no literals: ImeSession._refresh() makes their segments.
    groups: list[list[Piece]] = []
    for piece in pieces:
        lid = piece.lid if lex is None else lex.base_pos(piece.lid)
        if not groups or piece.learned or content(lid):
            groups.append([])
        groups[-1].append(piece)
    segments = [Segment(offset + g[0].start, offset + g[-1].end,
                        Candidate("".join(p.surface for p in g), "".join(p.reading for p in g),
                                  0, g[0].lid, g[-1].rid, "dictionary",
                                  sum(p.cost for p in g) + (sum(
                                      lex.transition(a.rid, b.lid) for a, b in zip(g, g[1:]))
                                      if lex is not None else 0))) for g in groups]
    if learning is not None:
        for segment in segments:
            row = learning.head(segment.selected.reading)
            if row is not None:
                segment.selected = learned_row(row)
    return segments


def _paths(tokens: list[dict], lex: MozcLex, left: int, right: int,
           *, kana: bool, learning=None) -> Iterator[Candidate]:
    """A* on the full word DAG with an exact reverse-DP potential.

    Dictionary mode keeps all paths within the score band, then deduplicates
    surfaces. Kana mode includes unknown arcs and keeps the cheapest prefix for
    each (position, RID, reading): spelling/POS variants cannot multiply work for
    the same reading. Both permit negative word/connection costs.
    The chords of one press alternate: a state is (RID, direction of the press
    open at that position), as in token_viterbi.
    """
    n = len(tokens)
    plan = Plan(tokens)
    arcs = [[w for w in spans_from(tokens, i, lex, learning, plan) if kana or not w.unknown]
            for i in range(n)]
    # Suffix costs for every reachable previous (RID, side); compute iteratively
    # so a long unknown segment cannot exceed Python's recursion limit.
    states: list[set[tuple[int, str | None]]] = [set() for _ in range(n + 1)]
    initial = (BOUNDARY_RID if left == BOS_ID else left, None)
    states[0].add(initial)
    for i in range(n):
        for side in {side for _, side in states[i]}:
            for w in arcs[i]:
                if admits(w.sides, side):
                    states[w.end].add((w.rid, after(w.sides, side)))
    suffix = [{} for _ in range(n + 1)]
    suffix[n] = {state: end_cost(lex, state[0], right) for state in states[n]}
    inf = float("inf")
    for i in range(n - 1, -1, -1):
        for rid, side in states[i]:
            suffix[i][(rid, side)] = min((
                word_cost(lex, rid, w) + suffix[w.end][(w.rid, after(w.sides, side))]
                for w in arcs[i] if admits(w.sides, side)), default=inf)
    best = suffix[0].get(initial, inf)
    if best == inf:
        return
    limit = inf if kana else best + COST_WINDOW
    serial = count()
    # priority, tie break, cost-so-far, position, RID, open-press side, first LID,
    # surface, reading
    heap = [(best, next(serial), 0, 0, initial[0], None, BOS_ID, "", "")]
    seen = set()
    prefixes = {}
    while heap:
        bound, _, cost, pos, rid, side, lid, surface, reading = heappop(heap)
        if bound > limit:
            break
        if kana and cost != prefixes.get((pos, rid, side, reading), cost):
            continue
        if pos == n:
            key = reading if kana else surface
            if key not in seen:
                seen.add(key)
                yield Candidate(surface, reading, int(bound), lid,
                                BOS_ID if rid == BOUNDARY_RID else rid, "dictionary",
                                cost - lex.transition(BOS_ID if initial[0] == BOUNDARY_RID
                                                      else initial[0], lid))
            continue
        for w in arcs[pos]:
            if not admits(w.sides, side):
                continue
            e = w.entry
            out = after(w.sides, side)
            nc = cost + word_cost(lex, rid, w)
            nr = reading + e.reading
            ns = surface + e.surface
            bound = nc + suffix[w.end][(w.rid, out)]
            if bound > limit:
                continue
            if kana:
                key = (w.end, w.rid, out, nr)
                if nc >= prefixes.get(key, inf):
                    continue
                prefixes[key] = nc
            heappush(heap, (bound, next(serial), nc, w.end, w.rid, out,
                            e.lid if pos == 0 else lid, ns, nr))


def candidates(tokens: list[dict], lex: MozcLex, left: int, right: int,
               *, learning=None, now: datetime | None = None) -> Iterator[Candidate]:
    """Dictionary rows, then kana rows, then date rows (with now). learning (a
    LearningView) adds the learned bunsetsu as paths, at their own cost."""
    dictionary = []
    for c in _paths(tokens, lex, left, right, kana=False, learning=learning):
        dictionary.append(c)
        yield c
    # Even a reading absent from every dictionary prefix remains reachable.
    for c in _paths(tokens, lex, left, right, kana=True, learning=learning):
        hira = c.reading
        kata = _katakana(hira)
        yield Candidate(hira, hira, c.score, c.lid, c.rid, "kana")
        yield Candidate(kata, hira, c.score, c.lid, c.rid, "kana")
    # Last, so every existing row keeps its place (and its number key).
    if now is not None:
        yield from _date_rows(dictionary, now)


def with_symbols(rows: Iterator[Candidate],
                 symbols: dict[str, tuple[str, ...]] | None,
                 learning=None) -> Iterator[Candidate]:
    """A clause's rows (candidates()) with the symbols of its reading.

    The first row's reading (the interval's 1-best) looks them up
    (symbol_readings.load_symbols). At most SYMBOL_HEAD of them come after the
    first SYMBOL_OFFSET rows; the rest come last. The symbol last chosen from
    the reading (learning, a LearningView) comes first overall; the others keep
    the file's order. A later row with a symbol's spelling is dropped.
    """
    first = None
    found: tuple[str, ...] = ()
    shown: set[str] = set()
    inserted: set[str] = set()

    def symbol_rows(surfaces) -> Iterator[Candidate]:
        for surface in surfaces:
            if surface not in shown and surface not in inserted:
                inserted.add(surface)
                yield Candidate(surface, first.reading, first.score, first.lid, first.rid,
                                "symbol")

    for n, c in enumerate(rows):
        if first is None:
            first = c
            found = symbols.get(c.reading, ()) if symbols else ()
            chosen = learning.symbol(c.reading) if learning is not None else None
            if chosen in found:
                yield from symbol_rows((chosen,))
        if c.surface in inserted:
            continue
        shown.add(c.surface)
        yield c
        if n + 1 == SYMBOL_OFFSET:
            yield from symbol_rows(found[:SYMBOL_HEAD])
    yield from symbol_rows(found)


def _katakana(hiragana: str) -> str:
    return "".join(chr(ord(ch) + 0x60) if "ぁ" <= ch <= "ゖ" else ch for ch in hiragana)


def learned_row(row) -> Candidate:
    """A learned confirmation (LearningView.head) as a row: a kana spelling of
    its reading is a kana row, as when it was chosen."""
    kind = "kana" if row.surface in (row.reading, _katakana(row.reading)) else "dictionary"
    return Candidate(row.surface, row.reading, 0, row.lid, row.rid, kind, row.cost)


def with_learned(rows: Iterator[Candidate], head: Candidate | None) -> Iterator[Candidate]:
    """head (learned_row) first, then rows without its spelling."""
    if head is None:
        yield from rows
        return
    yield head
    for c in rows:
        if c.surface != head.surface:
            yield c


def _date_rows(dictionary: list[Candidate], now: datetime) -> Iterator[Candidate]:
    """きょう → 2026/11/12 …; a kana tail (きょうは → 今日は) is kept as typed."""
    seen = {c.surface for c in dictionary}
    for c in dictionary:
        for cut in range(len(c.reading), 0, -1):
            tail = c.reading[cut:]
            spellings = date_spellings(c.reading[:cut], now)
            if spellings and c.surface.endswith(tail):
                for text in spellings:
                    if text + tail not in seen:
                        seen.add(text + tail)
                        yield Candidate(text + tail, c.reading, c.score, c.lid, c.rid, "date")
                break


@dataclass
class CandidateStream:
    source: Iterator[Candidate]
    cache: list[Candidate] = field(default_factory=list)
    exhausted: bool = False

    def ensure(self, index: int) -> bool:
        while len(self.cache) <= index and not self.exhausted:
            c = next(self.source, None)
            if c is None:
                self.exhausted = True
            else:
                self.cache.append(c)
        return index < len(self.cache)

    def last(self) -> int:
        while not self.exhausted:
            self.ensure(len(self.cache) + PAGE_SIZE)
        return len(self.cache) - 1

    def find(self, selected: Candidate) -> int:
        i = 0
        while self.ensure(i):
            if self.cache[i].surface == selected.surface and (
                    selected.kind not in ("kana", "literal")
                    or self.cache[i].kind == selected.kind):
                return i
            i += 1
        # A fixed spelling can fall outside the band after a neighbor changes.
        # Keep its display, with no highlighted row, until explicitly selected.
        return -1
