"""The user's own word list.

Personal words live in their own JSONL file, are overlaid on the shared
lexicon only by the running IME (never by the evaluation loaders), and take
effect without a restart: every conversion checks the file's signature.

The overlay never mutates a reading's entry list in place. Each change builds
a new list and swaps it into lex.by_reading in one assignment, so a decode
running on another thread (the engine's sessions, the LM worker) sees either
the old list or the new one.
"""
from __future__ import annotations

import codecs
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys

from yuragi.lattice.expand import is_literal_face
from yuragi.lattice.mozc_dict import Entry, MozcLex, pos_id
from .config import DEFAULT_RUNTIME_DIR

DEFAULT_PERSONAL_PATH = DEFAULT_RUNTIME_DIR / "personal_lexicon.jsonl"
# The default cost of a registered word (CONVERSION「辞書の重ね方」).
DEFAULT_COST = 2600
# A short list of what a user registers: its name in Mozc's id.def.
POS_NAMES = {
    "名詞": "名詞,一般", "サ変名詞": "名詞,サ変接続", "形容動詞": "名詞,形容動詞語幹",
    "固有名詞": "名詞,固有名詞,一般", "人名": "名詞,固有名詞,人名,一般", "名": "名詞,固有名詞,人名,名",
    "姓": "名詞,固有名詞,人名,姓", "地名": "名詞,固有名詞,地域,一般", "組織": "名詞,固有名詞,組織",
    "副詞": "副詞,一般",
}


@dataclass(frozen=True)
class Word:
    reading: str
    surface: str
    pos: str = "名詞"
    cost: int = DEFAULT_COST

    @property
    def lid(self) -> int:
        return pos_id(POS_NAMES[self.pos])


def validate(reading: str, surface: str, pos: str) -> None:
    if not reading or is_literal_face(reading):
        raise ValueError("読みは、ひらがなと長音記号（ー）で入力してください")
    if not surface or surface != surface.strip():
        raise ValueError("単語を入力してください（前後に空白は入れられません）")
    if pos not in POS_NAMES:
        raise ValueError(f"品詞「{pos}」は使えません。次から選んでください: {'、'.join(POS_NAMES)}")


def read_words(path: Path) -> list[Word]:
    """Valid rows in file order; a later row for the same pair wins."""
    return scan_words(path)[0]


def _lines(path: Path) -> list[bytes]:
    try:
        return Path(path).read_bytes().removeprefix(codecs.BOM_UTF8).splitlines()  # an editor's BOM
    except FileNotFoundError:
        return []


def _word(raw: bytes) -> Word | None:
    """The word on one line, or None for a blank line, a comment, or a line that is not a valid word."""
    try:
        row = json.loads(raw.decode("utf-8"))
        word = Word(row["reading"], row["surface"], row.get("pos", "名詞"),
                    int(row.get("cost", DEFAULT_COST)))
        validate(word.reading, word.surface, word.pos)
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):  # UnicodeError is a ValueError
        return None
    return word


def scan_words(path: Path) -> tuple[list[Word], int]:
    """(valid rows as read_words, number of lines skipped as not a valid word)."""
    words: dict[tuple[str, str], Word] = {}
    skipped = 0
    for raw in _lines(path):
        if not raw.strip() or raw.lstrip().startswith(b"#"):
            continue
        word = _word(raw)
        if word is None:
            skipped += 1  # A hand edit gone wrong must not stop conversion (DESIGN「起動時の読み込み」).
            continue
        words.pop((word.reading, word.surface), None)
        words[(word.reading, word.surface)] = word
    return list(words.values()), skipped


def _replace(path: Path, reading: str, surface: str, word: Word | None) -> bool:
    """Take the pair's rows out and put word, if any, at the end; True when a row was there.

    Every other line stays as it is, comments and lines that are not valid
    words included: they are the user's, who may yet correct them. The file
    is replaced atomically (a reader never sees half a file)."""
    path = Path(path)
    lines = _lines(path)
    kept = [raw for raw in lines
            if (w := _word(raw)) is None or (w.reading, w.surface) != (reading, surface)]
    if word is not None:
        kept.append(json.dumps({"reading": word.reading, "surface": word.surface, "pos": word.pos,
                                "cost": word.cost}, ensure_ascii=False).encode("utf-8"))
    elif len(kept) == len(lines):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(b"".join(raw + b"\n" for raw in kept))
    os.replace(tmp, path)
    return len(kept) - (word is not None) < len(lines)


def add_word(path: Path, reading: str, surface: str, pos: str = "名詞",
             cost: int = DEFAULT_COST) -> Word:
    validate(reading, surface, pos)
    word = Word(reading, surface, pos, cost)
    _replace(path, reading, surface, word)
    return word


def remove_word(path: Path, reading: str, surface: str) -> bool:
    return _replace(path, reading, surface, None)


class PersonalLexicon:
    """Keeps a lexicon's overlay equal to the file; shared by all sessions."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.revision = 0
        self.count = 0
        self.skipped = 0  # lines of the file that are not a valid word (shown to the user)
        self._signature: object = ()  # never equal to a stat signature or None
        self._unreadable = False
        self._original: dict[str, list[Entry] | None] = {}  # reading -> list before overlay
        self.added_readings: tuple[str, ...] = ()  # sorted additions to the base reading index

    def sync(self, lex: MozcLex) -> None:
        # Only the request thread updates the overlay. The LM worker reads it.
        try:
            try:
                st = self.path.stat()
                signature = (st.st_ino, st.st_mtime_ns, st.st_size)
            except FileNotFoundError:
                signature = None
            if signature == self._signature and not self._unreadable:
                return
            words, skipped = scan_words(self.path) if signature is not None else ([], 0)
        except OSError as exc:
            if not self._unreadable:
                print(f"personal lexicon unreadable ({type(exc).__name__}); keeping the current words",
                      file=sys.stderr, flush=True)
            self._unreadable = True
            return
        self._unreadable = False
        by_reading: dict[str, list[Word]] = {}
        for w in words:
            by_reading.setdefault(w.reading, []).append(w)
        for reading in set(self._original) | set(by_reading):
            if reading not in self._original:
                self._original[reading] = lex.by_reading.get(reading)
            base = self._original[reading]
            if reading not in by_reading:
                if base is None:
                    lex.by_reading.pop(reading, None)
                else:
                    lex.by_reading[reading] = base
                del self._original[reading]
                continue
            merged = list(base or ())
            for w in by_reading[reading]:
                # A known spelling keeps its POS and
                # gets the cheaper cost; a new one gets the chosen POS.
                # New Entry objects: the originals stay untouched for removal.
                at = next((i for i, e in enumerate(merged) if e.surface == w.surface), None)
                if at is None:
                    merged.append(Entry(w.surface, reading, w.lid, w.lid, w.cost))
                else:
                    old = merged[at]
                    merged[at] = Entry(w.surface, reading, old.lid, old.rid,
                                       min(old.cost, w.cost))
            lex.by_reading[reading] = sorted(merged, key=lambda e: e.cost)
            # Prefixes only prune the search; extra ones after a removal are harmless.
            lex.prefixes.update(reading[:i] for i in range(1, len(reading) + 1))
        self.count = len(words)
        self.skipped = skipped
        self.added_readings = tuple(sorted(r for r, base in self._original.items() if base is None))
        self._signature = signature
        self.revision += 1
