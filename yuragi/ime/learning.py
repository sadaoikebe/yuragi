"""Local confirmation history (REDESIGN §6.7). Never imported by the evaluation loaders.

The file is a JSONL log of confirmations and pair suppressions (Shift+F6,
"forget"). Its meaning is the latest confirmation of every (reading, surface,
left) triple that is not older than the last suppression of its pair: a
dictionary holding the latest row per triple.

This process appends its own rows and updates the index directly. A file that
changed otherwise (the management window forgot a pair or cleared the
history) is read again from the start at the next conversion: one stat per
conversion tells. Compaction runs once at engine start (compact_if_needed).

Learning is on or off (config.json "learning"), decided by the caller. A store
whose file does not exist reads and writes nothing (deleting the file while the
IME runs does not bring it back); the engine creates the file at start when
learning is on. A file that cannot be read or written leaves learning off for
now, with a line on stderr.

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
from .bunsetsu import Candidate, content

DEFAULT_LEARNING_PATH = Path.home() / ".yuragi-ime" / "learning.jsonl"
PAIR_BONUS = 2400
CONTEXT_BONUS = 3600  # additional to PAIR_BONUS
HALF_LIFE_SECONDS = 30 * 24 * 60 * 60
USER_WORD_COST = 6000
COMPACT_MIN_LINES = 5000  # REDESIGN §11
LEARN_EXPIRE_DAYS = 365  # REDESIGN §11; words the user taught (user_word) never expire


@dataclass(frozen=True)
class Confirmation:
    reading: str
    surface: str
    left: str
    timestamp: float
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
    """What a conversion reads: the history at one moment, with that moment's clock.

    A conversion uses one view, including its lazy candidates, so another
    session's commit cannot change a candidate list while it is shown.
    """

    max_bonus = PAIR_BONUS + CONTEXT_BONUS

    def __init__(self, index: tuple, now: float, revision: int):
        # _index(): pairs, entries and prefixes, shared by the views of one revision
        self._pairs, self._entries, self._prefixes = index
        self.now = now
        self.revision = revision

    def bonus(self, reading: str, surface: str, left: str) -> int:
        rows = self._pairs.get((reading, surface), ())
        pair = contextual = 0.0
        for row in rows:
            age = max(0, self.now - row.timestamp)
            weight = 2 ** (-age / HALF_LIFE_SECONDS)
            pair = weight
            if row.left == left:
                contextual = max(contextual, weight)
        return round(PAIR_BONUS * pair + CONTEXT_BONUS * contextual)

    def has_prefix(self, reading: str) -> bool:
        return reading in self._prefixes

    def learned(self):
        """The latest confirmation of every learned pair (prediction's history),
        readings in order of their first appearance."""
        for rows in self._entries.values():
            yield from rows

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

    @staticmethod
    def next_context(previous: str, word, *, boundary: bool = False) -> str:
        e = word.entry
        if boundary or word.start == 0 or word.literal or word.learned or content(e.lid):
            return e.surface
        return previous + e.surface


def _index(pairs: dict[tuple[str, str], dict[str, Confirmation]]) -> tuple:
    """(reading, surface) -> rows (latest per left context, the latest last),
    pairs in order of their first appearance; reading -> the latest row of each
    of its pairs; every prefix of a learned reading."""
    rows = {pair: tuple(by_left.values()) for pair, by_left in pairs.items()}
    entries: dict[str, list[Confirmation]] = {}
    for (reading, _), pair_rows in rows.items():
        entries.setdefault(reading, []).append(pair_rows[-1])
    prefixes = {r[:i] for r in entries for i in range(1, len(r) + 1)}
    return rows, entries, prefixes


class LearningStore:
    """The history of one file; snapshot() gives conversions a frozen view."""

    def __init__(self, path: Path, *, clock=time.time, recording: bool = True):
        self.path = Path(path)
        self.clock = clock
        self.recording = recording  # False: learning off (nothing is recorded)
        self.now = clock()
        self.revision = 0
        self.active = False  # the file exists and was read
        self.lines = 0  # lines of the file, valid or not
        self.skipped = 0  # lines that were not JSON with the needed fields
        self._seen = None  # the file's (st_dev, st_ino, st_size, st_mtime_ns) when last read
        self._needs_newline = False
        self._pairs: dict[tuple[str, str], dict[str, Confirmation]] = {}
        self._index: tuple | None = None  # _index(self._pairs), built when a view needs it
        self.sync()

    @staticmethod
    def _stamp(st) -> tuple:
        return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)

    def _changed(self) -> None:
        self.revision += 1
        self._index = None

    def _apply(self, event) -> None:
        pair = (event.reading, event.surface)
        if isinstance(event, Suppression):
            self._pairs.pop(pair, None)
            return
        rows = self._pairs.setdefault(pair, {})
        rows.pop(event.left, None)  # the latest row of each left context comes last
        rows[event.left] = event

    # -- reading the file ----------------------------------------------------
    def sync(self) -> None:
        """Read the file again if it changed since this process last saw it."""
        self.now = self.clock()
        try:
            stamp = self._stamp(os.stat(self.path))
        except FileNotFoundError:
            stamp = None
        except OSError:
            stamp = self._seen  # cannot look now; keep what we have
        if stamp == self._seen:
            return
        self._pairs = {}
        self.active = False
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
        self.active = True
        self._needs_newline = bool(data) and not data.endswith(b"\n")
        for raw in data.split(b"\n"):
            if not raw.strip():
                continue
            self.lines += 1
            line = parse_line(raw)
            if line is None:
                self.skipped += 1
                continue
            self._apply(line)

    def records(self) -> list[Confirmation]:
        """The surviving confirmations, oldest first (what compaction keeps)."""
        return sorted((row for rows in self._pairs.values() for row in rows.values()),
                      key=lambda row: row.timestamp)

    def pair_rows(self):
        """((reading, surface), rows) for every learned pair."""
        return ((pair, tuple(rows.values())) for pair, rows in self._pairs.items())

    def has_pair(self, reading: str, surface: str) -> bool:
        return (reading, surface) in self._pairs

    # -- what conversions read -------------------------------------------------
    def snapshot(self) -> LearningView | None:
        self.sync()
        if not self.active or not self._pairs:
            return None
        if self._index is None:
            self._index = _index(self._pairs)
        return LearningView(self._index, self.now, self.revision)

    # -- writing -------------------------------------------------------------
    def confirm(self, selections: list[tuple[Candidate, str]], lex: MozcLex) -> None:
        self.sync()
        if not self.active or not self.recording:
            return
        rows = []
        for c, left in selections:
            if c.kind in ("literal", "number", "date", "alnum") or not c.reading:
                continue
            cost, lid, rid = c.word_cost, c.lid, c.rid
            user_word = any(r.user_word for r in self._pairs.get((c.reading, c.surface), {}).values())
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
                rows.append(Confirmation(c.reading, c.surface, left, self.now,
                                         cost, lid, rid, user_word))
        self._append(rows)

    def suppress(self, reading: str, surface: str) -> bool:
        self.sync()
        return self._append([Suppression(reading, surface, self.now)])

    def _append(self, rows) -> bool:
        """Write rows and index them; False when there is nothing to write, no
        file, or the write failed."""
        if not self.active or not rows:
            return False
        payload = (("\n" if self._needs_newline else "") + "".join(
            json.dumps(asdict(r), ensure_ascii=False) + "\n" for r in rows)).encode("utf-8")
        try:
            # No O_CREAT: deleting the file while this process lives disables it.
            fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | getattr(os, "O_BINARY", 0))
            try:
                view = memoryview(payload)
                while view:
                    view = view[os.write(fd, view):]
                stamp = self._stamp(os.fstat(fd))
            finally:
                os.close(fd)
        except OSError as exc:
            print(f"learning history not written ({type(exc).__name__})",
                  file=sys.stderr, flush=True)
            return False
        self._needs_newline = False
        self._seen = stamp
        self.lines += len(rows)
        for row in rows:
            self._apply(row)
        self._changed()
        return True

    # -- compaction (engine start) -------------------------------------------
    def compact_if_needed(self, *, min_lines: int = COMPACT_MIN_LINES,
                          expire_days: float = LEARN_EXPIRE_DAYS) -> tuple[int, int] | None:
        """Rewrite the file with only the live records, once, at start.

        Runs when the file has more than twice the live records and more than
        min_lines lines. Records whose last confirmation is older than
        expire_days are dropped too, except words the user taught (user_word).
        The old file becomes <name>.bak. Returns (lines before, lines after),
        or None when nothing was done.
        """
        self.sync()
        if not self.active:
            return None
        live = self.records()
        if not (self.lines > 2 * len(live) and self.lines > min_lines):
            return None
        oldest = self.clock() - expire_days * 24 * 60 * 60
        kept = [r for r in live if r.user_word or r.timestamp >= oldest]
        write_history(self.path, kept, backup=True)
        before = self.lines
        self.sync()  # a new file: read from the start
        return before, len(kept)


def write_history(path: Path, rows: list, *, backup: bool = False) -> None:
    """Replace the history file with rows; a crash leaves the old or the new file whole.

    The new file is written beside it and flushed to disk before it takes the
    name. backup=True first gives the old file a second name, <name>.bak.
    """
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as stream:
        stream.write("".join(json.dumps(asdict(r), ensure_ascii=False) + "\n"
                             for r in rows).encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())
    if backup:
        bak = path.with_name(path.name + ".bak")
        bak.unlink(missing_ok=True)
        os.link(path, bak)
    os.replace(tmp, path)
