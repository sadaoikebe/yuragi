"""Prediction: continuations of the typed reading (ATOK 推測変換, MS-IME 予測入力).

Two sources, each usable and testable on its own:

  history_predictions()     the learning store's confirmations (LearningStore)
  dictionary_predictions()  the conversion lexicon, by reading prefix

predict() merges them: history first, then the dictionary, one row per
surface. A prediction is strictly longer than what was typed; it is never the
plain conversion of the input (Space already offers that).

What the learning store holds decides how history is used: the latest
confirmation of each learned (reading, surface) pair, the most recently
confirmed first. Suppressed pairs (forget_candidate) are already gone from the store,
so they never come back as predictions either.

The typed input is a token sequence, not one string: an ambiguous thumb chord
reads either face. The readings are enumerated like the learning store's own
whole-bunsetsu spans, pruned by the source's prefix set, so the walk stays
small even when many tokens are ambiguous.

Tab searches from the last MAX_TAILS word boundaries of the live conversion.
An idle preview searches at clause boundaries and within a small budget.
Both show continuations of the input's tail in the candidate window.
"""
from __future__ import annotations

from bisect import bisect_left
from heapq import nsmallest
from itertools import islice
from time import perf_counter
from typing import Callable, Iterable, Iterator, Sequence, TypeVar

from yuragi.lattice.alternation import Plan
from yuragi.lattice.mozc_dict import MozcLex
from .bunsetsu import Candidate, content
from .config import DEFAULTS, SETTINGS

MODES = SETTINGS["prediction"]
DEFAULT_MODE = DEFAULTS["prediction"]
MAX_PREDICTIONS = 9  # one candidate page
HISTORY_MIN_KANA = 2  # a learned word comes back from its first two kana
DICTIONARY_MIN_KANA = 3  # shorter prefixes match too much of the dictionary
MAX_EXTRA_KANA = 8  # a continuation, not a whole sentence
MAX_READINGS = 64  # bound on ambiguous readings walked per source
MAX_TAILS = 3  # how many words back (1-best boundaries) a prediction may start
PREVIEW_DELAY_MS = 180
PREVIEW_TAIL_TOKENS = 16
PREVIEW_HISTORY_ROWS = 256
PREVIEW_STEPS = 768
PREVIEW_SECONDS = 0.003
T = TypeVar("T")


class PreviewBudget:
    """Shared by all preview tails; count even visits that yield no candidate."""

    def __init__(self) -> None:
        self.until = perf_counter() + PREVIEW_SECONDS
        self.steps = PREVIEW_STEPS

    def exhausted(self) -> bool:
        return self.steps == 0 or perf_counter() >= self.until

    def take(self, items: Iterable[T]) -> Iterator[T]:
        for item in items:
            if self.exhausted():
                break
            self.steps -= 1
            yield item


def typed_readings(tokens: list[dict], is_prefix: Callable[[str], bool],
                   minimum: int, budget: PreviewBudget | None = None) -> list[str]:
    """Every reading of all tokens that is a prefix in the source (DFS, pruned)."""
    if not tokens or any(t["kind"] == "literal" for t in tokens):
        return []  # a digit or punctuation inside: not one word being typed
    out: list[str] = []
    # The chords of one press alternate, as in every other traversal (alternation.py).
    paths = Plan(tokens).walk(tokens, 0, is_prefix)
    for end, reading, _ in budget.take(paths) if budget is not None else paths:
        if end == len(tokens) and len(reading) >= minimum:
            out.append(reading)
            if len(out) >= MAX_READINGS:
                break
    return out


def history_predictions(store, tokens: list[dict],
                        budget: PreviewBudget | None = None) -> list[Candidate]:
    """Learned bunsetsu whose reading continues the input, the most recent first.

    store is a LearningStore snapshot (None: no history).
    """
    if store is None:
        return []
    readings = typed_readings(tokens, store.has_prefix, HISTORY_MIN_KANA, budget)
    if not readings:
        return []
    rows = store.learned()
    if budget is not None:
        rows = budget.take(islice(rows, PREVIEW_HISTORY_ROWS))
    return [Candidate(row.surface, row.reading, 0, row.lid, row.rid, "predict", row.cost)
            for row in rows
            if any(len(row.reading) > len(r) and row.reading.startswith(r) for r in readings)]


class ReadingIndex:
    """Sorted base readings, built before applying the personal overlay."""

    def __init__(self) -> None:
        self._keys: list[str] = []
        self._lex: MozcLex | None = None

    def keys(self, lex: MozcLex, *, prepare: bool = True) -> list[str]:
        if lex is not self._lex:
            if not prepare:
                return []
            self._keys = sorted(lex.by_reading)
            self._lex = lex
        return self._keys


def prefix_keys(keys: Sequence[str], typed: str) -> Iterator[str]:
    at = bisect_left(keys, typed)
    while at < len(keys) and keys[at].startswith(typed):
        yield keys[at]
        at += 1


def dictionary_predictions(lex: MozcLex, index: ReadingIndex, tokens: list[dict],
                           limit: int = MAX_PREDICTIONS,
                           *, added_readings: tuple[str, ...] = (),
                           budget: PreviewBudget | None = None) -> list[Candidate]:
    """Content words whose reading continues the input, cheapest first."""
    readings = typed_readings(tokens, lex.prefixes.__contains__, DICTIONARY_MIN_KANA, budget)
    if not readings:
        return []
    keys = index.keys(lex, prepare=budget is None)
    found = []
    for typed in readings:
        for source in (added_readings, keys):
            matches = prefix_keys(source, typed)
            for reading in budget.take(matches) if budget is not None else matches:
                if reading == typed or len(reading) > len(typed) + MAX_EXTRA_KANA:
                    continue
                entries = lex.by_reading.get(reading, ())
                for e in budget.take(entries) if budget is not None else entries:
                    if content(lex.base_pos(e.lid)):
                        found.append((e.cost, reading, e))
    out: list[Candidate] = []
    seen: set[str] = set()
    for cost, reading, e in nsmallest(limit * 4, found, key=lambda item: item[:2]):
        if e.surface not in seen:
            seen.add(e.surface)
            out.append(Candidate(e.surface, reading, 0, e.lid, e.rid, "predict", cost))
    return out[:limit]


def merge(*sources: Iterable[Candidate], limit: int = MAX_PREDICTIONS) -> list[Candidate]:
    """Sources in order of trust, one row per surface."""
    out: list[Candidate] = []
    seen: set[str] = set()
    for source in sources:
        for c in source:
            if c.surface not in seen:
                seen.add(c.surface)
                out.append(c)
                if len(out) == limit:
                    return out
    return out


def predict(tokens: list[dict], lex: MozcLex, index: ReadingIndex, store,
            *, added_readings: tuple[str, ...] = (),
            budget: PreviewBudget | None = None) -> list[Candidate]:
    """History rows first, then dictionary rows, one per surface."""
    return merge(history_predictions(store, tokens, budget),
                 dictionary_predictions(lex, index, tokens, added_readings=added_readings,
                                        budget=budget))
