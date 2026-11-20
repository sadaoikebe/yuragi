"""Local confirmation history (DESIGN「学習履歴のファイル」). Never imported by the evaluation loaders.

The file is a JSONL log of the user's choices and pair suppressions
(Shift+F6, "forget"), read in order. Only a choice is recorded: a commit of
what the engine showed adds nothing, so it changes no later conversion. What
a conversion uses, for each reading: the surface chosen by LearningView.head
from the last choices for the reading and its left bunsetsu. A choice
overrides the LM's pick only after the same left bunsetsu. Nothing is added
to any score. A suppression removes its (reading, surface) pair from every
context.

Rows written before choices were told apart (no "choice") are kept in the
file but not used, except words learned from kana and symbols, which only a
choice produced.

Confirmed bunsetsu are also whole-bunsetsu arcs of the lattice (spans), so a
spelling absent from the dictionary (user_word, from a kana confirmation) can
be converted to, and predictions come from them (predict.py).

A symbol chosen from its reading (kind "symbol", symbol_readings.py) is
recorded too, marked "symbol": the one confirmed last leads that reading's
candidates (LearningView.symbol), and it is nothing else (no head, arc or
prediction).

This process appends its own rows and updates the index directly. A file that
changed otherwise (the management window forgot a pair) is read again from the
start at the next conversion: one stat per conversion tells. Compaction runs
once at engine start (compact_if_needed). A file that cannot be read or
written leaves learning off for now, with a line on stderr.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, fields, replace
import json
import os
from pathlib import Path
import sys
import time

from yuragi.lattice.alternation import Plan
from yuragi.lattice.mozc_dict import DEFAULT_NOUN_ID, Entry, MozcLex
from .bunsetsu import Bunsetsu, Candidate, normal_bunsetsu

DEFAULT_LEARNING_PATH = Path.home() / ".yuragi-ime" / "learning.jsonl"
USER_WORD_COST = 6000
COMPACT_MIN_LINES = 5000  # DESIGN「定数」
_UNREAD = object()


@dataclass(frozen=True)
class Confirmation:
    reading: str
    surface: str
    timestamp: float  # shown in the management window
    cost: int
    lid: int
    rid: int
    user_word: bool = False
    symbol: bool = False  # a symbol from its reading: promotes it in candidates only
    prev: str | None = None
    choice: bool = False  # written by a version that records the user's choices only

    def used(self) -> bool:
        """False for an older row that may be a plain commit of the engine's pick."""
        return self.choice or self.user_word or self.symbol


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
            row = _event(data, Confirmation)
            return row if isinstance(row.prev, str) and row.prev else replace(row, prev=None)
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
        self._last, self._recent, self._entries, self._prefixes, self._symbols, self._contexts, self._pairs = index
        self.revision = revision

    def head(self, reading: str, prev: Bunsetsu | None = None, *, repeat: bool = False,
             zenz: str | None = None) -> Confirmation | None:
        """The learned spelling for this interval, in rule priority order.

        zenz: the surface the LM wrote for this interval, if it did. A choice
        made in another context does not override it; None then keeps it."""
        if reading not in self._last:
            return None
        if prev is not None and repeat and prev.reading == reading:
            row = self._pairs.get((reading, prev.surface))
            if row is not None:
                return row
        surface = self._contexts.get((reading, prev.surface)) if prev is not None else None
        if surface is not None:
            return self._pairs[reading, surface]
        if zenz is not None:
            return self._pairs.get((reading, zenz))
        return self._last[reading]

    def symbol(self, reading: str) -> str | None:
        """The symbol last chosen from this reading, if any."""
        return self._symbols.get(reading)

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


def _index(rows: list[Confirmation], contexts: list[Confirmation]) -> tuple:
    """From the live rows (one per pair, oldest first): reading -> the latest
    row; the rows, the most recent first; reading -> those of its pairs; every
    prefix of a learned reading; reading -> the symbol chosen last. Symbol rows
    are only in the symbol index. Context rows are also oldest first."""
    last: dict[str, Confirmation] = {}
    symbols: dict[str, str] = {}
    recent: list[Confirmation] = []
    for row in reversed(rows):
        if row.symbol:
            symbols.setdefault(row.reading, row.surface)
            continue
        last.setdefault(row.reading, row)
        recent.append(row)
    entries: dict[str, list[Confirmation]] = {}
    for row in recent:
        entries.setdefault(row.reading, []).append(row)
    prefixes = {r[:i] for r in entries for i in range(1, len(r) + 1)}
    winners = {(row.reading, row.prev): row.surface for row in contexts}
    pairs = {(row.reading, row.surface): row for row in recent}
    return last, recent, entries, prefixes, symbols, winners, pairs


class LearningStore:
    """The history of one file; snapshot() gives conversions a frozen view."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.revision = 0
        self.lines = 0  # lines of the file, valid or not
        self.skipped = 0  # lines that were not JSON with the needed fields
        self._seen = None  # the file's (st_dev, st_ino, st_size, st_mtime_ns) when last read
        # (reading, surface) -> the latest such confirmation, the oldest first
        self._rows: dict[tuple[str, str], tuple[int, Confirmation]] = {}
        # Pair -> left surface -> latest confirmation in that context.
        self._contexts: dict[tuple[str, str], dict[str, tuple[int, Confirmation]]] = {}
        # Older rows not used (Confirmation.used), kept through compaction.
        self._unused: dict[tuple[str, str], tuple[int, Confirmation]] = {}
        self._index: tuple | None = None  # built when a view needs it
        self.sync()

    @staticmethod
    def _stamp(st) -> tuple:
        return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)

    def _changed(self) -> None:
        self.revision += 1
        self._index = None

    def _apply(self, event, position: int) -> None:
        key = (event.reading, event.surface)
        if isinstance(event, Confirmation) and not event.used():
            self._unused[key] = (position, event)
            return
        previous = self._rows.pop(key, None)
        if isinstance(event, Confirmation):
            if previous is not None and previous[1].symbol != event.symbol:
                self._contexts.pop(key, None)
            self._rows[key] = (position, event)
            if not event.symbol and event.prev:
                self._contexts.setdefault(key, {})[event.prev] = (position, event)
        else:
            self._unused.pop(key, None)
            self._contexts.pop(key, None)

    def _context_rows(self):
        return sorted(record for rows in self._contexts.values() for record in rows.values())

    @contextmanager
    def _lock(self):
        # Lock a stable sidecar, since compaction replaces the history inode.
        with self.path.with_name(self.path.name + ".lock").open("a+b") as lock:
            if os.name == "nt":
                import msvcrt
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX)
            yield  # closing the file releases the lock

    # -- reading the file ----------------------------------------------------
    def _stat(self):
        try:
            return self._stamp(self.path.stat())
        except FileNotFoundError:
            return None

    def _clear(self, stamp) -> None:
        self._rows.clear()
        self._contexts.clear()
        self._unused.clear()
        self.lines = self.skipped = 0
        self._seen = stamp
        self._changed()

    def _sync_locked(self) -> None:
        stamp = self._stat()
        if stamp == self._seen:
            return
        if stamp is None:
            self._clear(None)
            return
        data = self.path.read_bytes()
        self._clear(stamp)
        for raw in data.split(b"\n"):
            if not raw.strip():
                continue
            self.lines += 1
            event = parse_line(raw)
            if event is None:
                self.skipped += 1
            else:
                self._apply(event, self.lines)

    def sync(self) -> None:
        """Read a changed file with the same lock used by its writers."""
        try:
            stamp = self._stat()
            if stamp == self._seen:
                return
            if stamp is None:
                self._clear(None)
            else:
                with self._lock():
                    self._sync_locked()
        except OSError as exc:
            if self._seen is not _UNREAD:
                self._clear(_UNREAD)
            print(f"learning history unreadable ({type(exc).__name__}); not used for now",
                  file=sys.stderr, flush=True)

    def records(self) -> list[Confirmation]:
        """One surviving confirmation per pair, oldest first."""
        return [row for _, row in self._rows.values()]

    def has_pair(self, reading: str, surface: str) -> bool:
        return (reading, surface) in self._rows

    # -- what conversions read -------------------------------------------------
    def snapshot(self) -> LearningView | None:
        self.sync()
        if not self._rows:
            return None
        if self._index is None:
            self._index = _index(self.records(), [row for _, row in self._context_rows()])
        return LearningView(self._index, self.revision)

    # -- writing -------------------------------------------------------------
    @contextmanager
    def _writing(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock():
            self._sync_locked()
            yield

    def _write_failed(self, exc: OSError) -> None:
        self._seen = _UNREAD
        print(f"learning history not written ({type(exc).__name__})",
              file=sys.stderr, flush=True)

    def confirm(self, selections: list[Candidate], lex: MozcLex, *,
                prev: Bunsetsu | None = None, repeat: bool = False,
                chosen: list[bool] | None = None) -> None:
        """Record the committed selections that the user chose (chosen[i];
        default all). The others still give their right neighbor its left."""
        if chosen is None:
            chosen = [True] * len(selections)
        if not any(wanted and (normal_bunsetsu(c) is not None
                               or (c.kind == "symbol" and c.reading))
                   for c, wanted in zip(selections, chosen)):
            return
        try:
            with self._writing():
                now = time.time()
                rows = []
                for c, wanted in zip(selections, chosen):
                    current = normal_bunsetsu(c)
                    if wanted and current is not None:
                        left = prev.surface if prev is not None and not (
                            repeat and prev.reading == current.reading) else None
                        rows.append(self._confirmation(c, lex, now, left))
                    elif wanted and c.kind == "symbol" and c.reading:
                        rows.append(Confirmation(c.reading, c.surface, now,
                                                 0, lex.base_pos(c.lid), lex.base_pos(c.rid),
                                                 symbol=True, choice=True))
                    prev = current
                self._append(rows)
        except OSError as exc:
            self._write_failed(exc)

    def _confirmation(self, c: Candidate, lex: MozcLex, now: float,
                      prev: str | None) -> Confirmation:
        cost, lid, rid = c.word_cost, c.lid, c.rid
        learned = self._rows.get((c.reading, c.surface))
        user_word = learned is not None and learned[1].user_word
        if c.kind == "kana":
            existing = [e for e in lex.by_reading.get(c.reading, ()) if e.surface == c.surface]
            if existing:
                e = min(existing, key=lambda e: e.cost)
                cost, lid, rid = e.cost, e.lid, e.rid
            else:
                user_word = True
                cost, lid, rid = USER_WORD_COST, DEFAULT_NOUN_ID, DEFAULT_NOUN_ID
        # Numeral connection IDs are local to the loaded lexicon.
        return Confirmation(c.reading, c.surface, now, cost, lex.base_pos(lid),
                            lex.base_pos(rid), user_word, prev=prev, choice=True)

    def suppress(self, reading: str, surface: str) -> bool:
        """Forget a learned pair; False when it is not learned (nothing written)."""
        try:
            with self._writing():
                if not self.has_pair(reading, surface):
                    return False
                self._append([Suppression(reading, surface, time.time())])
        except OSError as exc:
            self._write_failed(exc)
            return False
        return True

    def _append(self, rows) -> None:
        """Write rows and publish the new index, under the writer lock."""
        with self.path.open("a+b") as stream:
            # An edited file or a failed append may have left an unterminated row.
            if stream.tell():
                stream.seek(-1, os.SEEK_END)
                if stream.read(1) != b"\n":
                    stream.write(b"\n")
            stream.write(_encode(rows))
            stream.flush()
            stamp = self._stamp(os.fstat(stream.fileno()))
        self._seen = stamp
        for row in rows:
            self.lines += 1
            self._apply(row, self.lines)
        self._changed()

    # -- compaction (engine start) -------------------------------------------
    def compact_if_needed(self, *, min_lines: int = COMPACT_MIN_LINES) -> tuple[int, int] | None:
        """Compact when more than half the rows can be dropped."""
        if self._stat() is None:
            return None
        with self._lock():
            self._sync_locked()
            live = dict(self._rows.values())
            live.update(self._context_rows())
            live.update(self._unused.values())  # the user's data: never dropped unasked
            if self.lines <= 2 * len(live) or self.lines <= min_lines:
                return None
            before = self.lines
            tmp = self.path.with_name(self.path.name + ".tmp")
            try:
                tmp.write_bytes(_encode(live[i] for i in sorted(live)))
                os.replace(tmp, self.path)
                self._sync_locked()
            except OSError:
                self._seen = _UNREAD
                raise
            return before, len(live)


def _encode(rows) -> bytes:
    lines = []
    for row in rows:
        data = asdict(row)
        if isinstance(row, Confirmation) and row.prev is None:
            del data["prev"]
        lines.append(json.dumps(data, ensure_ascii=False) + "\n")
    return "".join(lines).encode("utf-8")
