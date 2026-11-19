"""Looking after the learning history file for the management window:
list, forget, promote.

Everything here goes through LearningStore's reading of the file, so what is
listed is exactly what conversion uses; a running engine reads the file again
at its next conversion.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import personal
from .learning import LearningStore


@dataclass(frozen=True)
class LearnedPair:
    reading: str
    surface: str
    last: float  # timestamp of the latest confirmation
    user_word: bool  # created from a kana spelling absent from the dictionary


def pairs(path: Path) -> list[LearnedPair]:
    """Surviving (reading, surface) pairs, most recent first."""
    store = LearningStore(path)
    out = []
    for row in store.records():
        out.append(LearnedPair(row.reading, row.surface, row.timestamp, row.user_word))
    return sorted(out, key=lambda p: -p.last)


def search(path: Path, query: str) -> list[LearnedPair]:
    return [p for p in pairs(path) if query in p.reading or query in p.surface]


def forget(path: Path, reading: str, surface: str) -> bool:
    """The same suppression as Shift+F6 on the candidate; False if nothing was learned."""
    return LearningStore(path).suppress(reading, surface)


def is_learned(path: Path, reading: str, surface: str) -> bool:
    return LearningStore(path).has_pair(reading, surface)


def promote(path: Path, personal_path: Path, reading: str, surface: str,
            pos: str = "名詞") -> personal.Word | None:
    """Register a learned pair as a personal word, so it survives clearing the
    history; None if the pair was never learned (register it as a word instead)."""
    if not is_learned(path, reading, surface):
        return None
    return personal.add_word(personal_path, reading, surface, pos)

