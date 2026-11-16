"""Looking after the learning history file for the management window:
list, forget, promote, the learning setting (on/off).

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
    contexts: int  # distinct left contexts confirmed
    last: float  # timestamp of the latest confirmation
    user_word: bool  # created from a kana spelling absent from the dictionary


def pairs(path: Path) -> list[LearnedPair]:
    """Surviving (reading, surface) pairs, most recent first."""
    store = LearningStore(path)
    out = []
    for (reading, surface), rows in store.pair_rows():
        out.append(LearnedPair(reading, surface, len(rows), max(r.timestamp for r in rows),
                               any(r.user_word for r in rows)))
    return sorted(out, key=lambda p: -p.last)


def search(path: Path, query: str) -> list[LearnedPair]:
    return [p for p in pairs(path) if query in p.reading or query in p.surface]


def forget(path: Path, reading: str, surface: str) -> bool:
    """The same suppression as Shift+F6 on the candidate; False if nothing was learned."""
    store = LearningStore(path)
    if not store.has_pair(reading, surface):
        return False
    return store.suppress(reading, surface)


def is_learned(path: Path, reading: str, surface: str) -> bool:
    return LearningStore(path).has_pair(reading, surface)


def promote(path: Path, personal_path: Path, reading: str, surface: str,
            pos: str = "名詞") -> personal.Word | None:
    """Register a learned pair as a personal word, so it survives clearing the
    history; None if the pair was never learned (register it as a word instead)."""
    if not is_learned(path, reading, surface):
        return None
    return personal.add_word(personal_path, reading, surface, pos)


def state(settings) -> str:
    """on or off (the learning setting, REDESIGN §6.7)."""
    from .config import learning_mode
    return learning_mode(settings)
