"""Local confirmation history (REDESIGN §6.7). Never imported by the evaluation loaders.

The file is a JSONL log of confirmations and pair suppressions (Shift+F6,
"forget"), read in order. What a conversion uses, for each reading: the
surface confirmed last. It comes first (LearningView.head); nothing is added to
any score. A suppression removes its (reading, surface) pair.

Confirmed bunsetsu are also whole-bunsetsu arcs of the lattice (spans), so a
spelling absent from the dictionary (user_word, from a kana confirmation) can
be converted to, and predictions come from them (predict.py).

This process appends its own rows and updates the index directly. A file that
changed otherwise (the management window forgot a pair) is read again from the
start at the next conversion: one stat per conversion tells. Compaction runs
once at engine start (compact_if_needed). A file that cannot be read or
written leaves learning off for now, with a line on stderr.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import json
import os
from pathlib import Path
import sys
import time

from yuragi.lattice.alternation import Plan
from yuragi.lattice.mozc_dict import DEFAULT_NOUN_ID, Entry, MozcLex
from .bunsetsu import Candidate

DEFAULT_LEARNING_PATH = Path.home() / ".yuragi-ime" / "learning.jsonl"
USER_WORD_COST = 6000
COMPACT_MIN_LINES = 5000  # REDESIGN §11


@dataclass(frozen=True)
class Confirmation:
    reading: str
    surface: str
    timestamp: float  # shown in the management window
    cost: int
    lid: int
    rid: int
    user_word: bool = False


@dataclass(frozen=True)
class Suppression:
    reading: str
    surface: str
    timestamp: float
    type: str = "suppress"


def _event(data: dict, cls):
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in data.items() if k in names})


def parse_line(raw: bytes):
    """One history line as an event, or None when it is not JSON with the
    needed fields."""
    try:
        data = json.loads(raw.decode("utf-8"))
        kind = data.get("type", "confirm")
        if kind == "confirm":
            return _event(data, Confirmation)
        if kind == "suppress":
            return _event(data, Suppression)
    except (ValueError, TypeError, KeyError, AttributeError):  # UnicodeError is a ValueError
        pass
    return None


class LearningView:
    """What a conversion reads: the history at one revision.

    A conversion uses one view, including its lazy candidates, so another
    session's commit cannot change a candidate list while it is shown.
    """

    def __init__(self, index: tuple, revision: int):
        # _index(): shared by the views of one revision
        self._last, self._recent, self._entries, self._prefixes = index
        self.revision = revision

    def head(self, reading: str) -> Confirmation | None:
        """The confirmation that comes first for this reading: the latest."""
        return self._last.get(reading)

    def has_prefix(self, reading: str) -> bool:
        return reading in self._prefixes

    def learned(self):
        """The latest confirmation of every learned pair (prediction's history),
        the most recent first."""
        return iter(self._recent)

    def spans(self, tokens: list[dict], start: int, lex: MozcLex, plan: Plan | None = None):
        """Virtual whole-bunsetsu arcs; original entries and costs stay intact.

        The learned readings are separate from MAX_WORD_MORA-limited Mozc traversal,
        so long confirmed unknown words also remain available. The chords of
        one press alternate, as in every other traversal (alternation.py).
        """
        for pos, reading, _ in (plan or Plan(tokens)).walk(tokens, start, self.has_prefix):
            for row in self._entries.get(reading, ()):
                if row.lid < lex.pos_size and row.rid < lex.pos_size:
                    yield pos, Entry(row.surface, reading, row.lid, row.rid, row.cost)


def _index(rows: dict[tuple[str, str], Confirmation]) -> tuple:
    """From the live rows (one per pair, oldest first): reading -> the latest
    row; the rows, the most recent first; reading -> those of its pairs; every
    prefix of a learned reading."""
    recent = list(reversed(rows.values()))
    last: dict[str, Confirmation] = {}
    entries: dict[str, list[Confirmation]] = {}
    for row in recent:
        last.setdefault(row.reading, row)
        entries.setdefault(row.reading, []).append(row)
    prefixes = {r[:i] for r in entries for i in range(1, len(r) + 1)}
    return last, recent, entries, prefixes


class LearningStore:
    """The history of one file; snapshot() gives conversions a frozen view."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.revision = 0
        self.lines = 0  # lines of the file, valid or not
        self.skipped = 0  # lines that were not JSON with the needed fields
        self._seen = None  # the file's (st_dev, st_ino, st_size, st_mtime_ns) when last read
        # (reading, surface) -> the latest such confirmation, the oldest first
        self._rows: dict[tuple[str, str], Confirmation] = {}
        self._index: tuple | None = None  # _index(self._rows), built when a view needs it
        self.sync()

    @staticmethod
    def _stamp(st) -> tuple:
        return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)

    def _changed(self) -> None:
        self.revision += 1
        self._index = None

    def _apply(self, event) -> None:
        key = (event.reading, event.surface)
        self._rows.pop(key, None)
        if isinstance(event, Confirmation):
            self._rows[key] = event

    # -- reading the file ----------------------------------------------------
    def sync(self) -> None:
        """Read the file again if it changed since this process last saw it."""
        try:
            stamp = self._stamp(os.stat(self.path))
        except FileNotFoundError:
            stamp = None
        except OSError:
            stamp = self._seen  # cannot look now; keep what we have
        if stamp == self._seen:
            return
        self._rows = {}
        self.lines = self.skipped = 0
        self._seen = stamp
        self._changed()
        if stamp is None:
            return
        try:
            with open(self.path, "rb") as stream:
                data = stream.read()
                self._seen = self._stamp(os.fstat(stream.fileno()))
        except OSError as exc:
            print(f"learning history unreadable ({type(exc).__name__}); not used for now",
                  file=sys.stderr, flush=True)
            return
        for raw in data.split(b"\n"):
            if not raw.strip():
                continue
            self.lines += 1
            event = parse_line(raw)
            if event is None:
                self.skipped += 1
            else:
                self._apply(event)

    def records(self) -> list[Confirmation]:
        """The surviving confirmations, oldest first (what compaction keeps)."""
        return list(self._rows.values())

    def has_pair(self, reading: str, surface: str) -> bool:
        return (reading, surface) in self._rows

    # -- what conversions read -------------------------------------------------
    def snapshot(self) -> LearningView | None:
        self.sync()
        if not self._rows:
            return None
        if self._index is None:
            self._index = _index(self._rows)
        return LearningView(self._index, self.revision)

    # -- writing -------------------------------------------------------------
    def confirm(self, selections: list[Candidate], lex: MozcLex) -> None:
        self.sync()
        now = time.time()
        rows = []
        for c in selections:
            if c.kind in ("literal", "number", "date", "alnum") or not c.reading:
                continue
            cost, lid, rid = c.word_cost, c.lid, c.rid
            learned = self._rows.get((c.reading, c.surface))
            user_word = learned is not None and learned.user_word
            if c.kind == "kana":
                existing = [e for e in lex.by_reading.get(c.reading, ())
                            if e.surface == c.surface]
                if existing:
                    e = min(existing, key=lambda e: e.cost)
                    cost, lid, rid = e.cost, e.lid, e.rid
                else:
                    user_word = True
                    cost, lid, rid = USER_WORD_COST, DEFAULT_NOUN_ID, DEFAULT_NOUN_ID
            if cost is not None:
                rows.append(Confirmation(c.reading, c.surface, now,
                                         cost, lid, rid, user_word))
        self._append(rows)

    def suppress(self, reading: str, surface: str) -> bool:
        """Forget a learned pair; False when it is not learned (nothing written)."""
        self.sync()
        if (reading, surface) not in self._rows:
            return False
        return self._append([Suppression(reading, surface, time.time())])

    def _append(self, rows) -> bool:
        """Write rows and index them; False when there is nothing to write or
        the write failed."""
        if not rows:
            return False
        payload = "".join(json.dumps(asdict(r), ensure_ascii=False) + "\n"
                          for r in rows).encode("utf-8")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "ab") as stream:
                stream.write(payload)
                stream.flush()
                stamp = self._stamp(os.fstat(stream.fileno()))
        except OSError as exc:
            print(f"learning history not written ({type(exc).__name__})",
                  file=sys.stderr, flush=True)
            return False
        self._seen = stamp
        self.lines += len(rows)
        for row in rows:
            self._apply(row)
        self._changed()
        return True

    # -- compaction (engine start) -------------------------------------------
    def compact_if_needed(self, *, min_lines: int = COMPACT_MIN_LINES) -> tuple[int, int] | None:
        """Rewrite the file with only the live records, once, at start.

        Runs when the file has more than twice the live records and more than
        min_lines lines. Returns (lines before, lines after), or None when
        nothing was done.
        """
        self.sync()
        live = self.records()
        if not (self.lines > 2 * len(live) and self.lines > min_lines):
            return None
        write_history(self.path, live)
        before = self.lines
        self.sync()  # a new file: read from the start
        return before, len(live)


def write_history(path: Path, rows: list) -> None:
    """Replace the history file with rows (written beside it, then renamed)."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes("".join(json.dumps(asdict(r), ensure_ascii=False) + "\n"
                            for r in rows).encode("utf-8"))
    os.replace(tmp, path)
