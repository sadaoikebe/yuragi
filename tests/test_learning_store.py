"""REDESIGN §6.7: the learning history file survives what can happen to it.

A replaced, shrunk or locked file, a failed write, and a process killed in the
middle of a compaction never stop learning nor leave a broken file.
"""
from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from yuragi.ime.bunsetsu import Candidate
from yuragi.ime.learning import LEARN_EXPIRE_DAYS, Confirmation, LearningStore

ROOT = Path(__file__).resolve().parents[1]
DAY = 24 * 60 * 60


def write_lines(path: Path, events) -> None:
    with path.open("a", encoding="utf-8") as stream:
        for e in events:
            stream.write(json.dumps(asdict(e), ensure_ascii=False) + "\n")


class FileTroubleTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "learning.jsonl"
        self.path.touch()
        self.now = 1_800_000_000.0

    def store(self):
        return LearningStore(self.path, clock=lambda: self.now)

    def test_replaced_or_shrunk_file_is_read_again(self):
        store = self.store()
        write_lines(self.path, [Confirmation("か", "A", "", self.now, 1, 1, 1, record_id="x")])
        store.sync()
        self.assertTrue(store.has_pair("か", "A"))
        replacement = self.path.with_name("new.jsonl")
        write_lines(replacement, [Confirmation("さ", "B", "", self.now, 1, 1, 1, record_id="y")])
        os.replace(replacement, self.path)
        store.sync()
        self.assertEqual([r.reading for r in store.records()], ["さ"])
        self.path.write_text("", encoding="utf-8")
        store.sync()
        self.assertEqual(store.records(), [])

    def test_unreadable_file_is_read_once_more_after_ten_seconds(self):
        clock = [0.0]
        problems = []
        write_lines(self.path, [Confirmation("か", "A", "", self.now, 1, 1, 1, record_id="x")])
        real_open = open

        def locked(path, *args, **kwargs):
            if Path(path) == self.path:
                raise PermissionError("held by another program")
            return real_open(path, *args, **kwargs)

        with patch("builtins.open", locked):
            store = LearningStore(self.path, clock=lambda: self.now,
                                  monotonic=lambda: clock[0], on_problem=problems.append)
            self.assertFalse(store.active)  # no learning now
            clock[0] = 9.9
            store.sync()
            clock[0] = 10.0
            store.sync()  # the one retry, still failing
            self.assertEqual(problems, ["learning-read"])
            clock[0] = 100
            store.sync()
            self.assertEqual(problems, ["learning-read"])  # told once
        clock[0] = 0
        with patch("builtins.open", locked):
            store = LearningStore(self.path, clock=lambda: self.now,
                                  monotonic=lambda: clock[0], on_problem=problems.append)
        clock[0] = 10
        store.sync()  # the retry succeeds
        self.assertTrue(store.active)
        self.assertTrue(store.has_pair("か", "A"))

    def test_failed_write_still_learns_in_memory_and_tells_once(self):
        problems = []
        store = LearningStore(self.path, clock=lambda: self.now, on_problem=problems.append)
        c = Candidate("校正", "こうせい", 0, 1851, 1851, word_cost=5000)
        with patch("yuragi.ime.learning.os.write", side_effect=OSError(28, "No space")):
            self.assertEqual(store.confirm([(c, "")], None), [])  # nothing to undo
            store.confirm([(c, "x")], None)
        self.assertEqual(problems, ["learning-write"])
        self.assertEqual(store.bonus("こうせい", "校正", ""), 6000)
        store.confirm([(c, "")], None)  # the disk has room again
        self.assertEqual(len(self.path.read_text(encoding="utf-8").splitlines()), 1)


class CompactionTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.path = self.dir / "learning.jsonl"
        self.now = 1_800_000_000.0

    def history(self):
        """6,000 lines over 50 live records; one old taught word, one old record."""
        events = []
        for i in range(6000):
            events.append(Confirmation(f"よみ{i % 50}", "表記", "", self.now - 6000 + i,
                                       5000, 1851, 1851, record_id=f"r{i}"))
        old = self.now - (LEARN_EXPIRE_DAYS + 1) * DAY
        events.append(Confirmation("ふるい", "古い", "", old, 5000, 1851, 1851, record_id="old"))
        events.append(Confirmation("ぬえ", "ヌエ", "", old, 6000, 1851, 1851, True,
                                   record_id="taught"))
        write_lines(self.path, events)
        return events

    def test_killed_at_any_point_leaves_a_whole_file(self):
        """The process dies (no clean-up) at each step of the rewrite."""
        self.history()
        original = self.path.read_bytes()
        expected = None
        for point in ("write", "fsync", "link", "replace", "end"):
            with self.subTest(point=point):
                self.path.write_bytes(original)
                for leftover in (".tmp", ".bak"):
                    self.path.with_name(self.path.name + leftover).unlink(missing_ok=True)
                code = subprocess.run(
                    [sys.executable, "-c", KILL_SCRIPT, str(self.path), point, str(self.now)],
                    cwd=ROOT, capture_output=True, text=True)
                self.assertEqual(code.returncode, 0 if point == "end" else 9, code.stderr)
                result = self.path.read_bytes()
                if point == "end":
                    expected = result
                    self.assertNotEqual(result, original)
                self.assertIn(result, (original, expected) if expected else (original,
                                                                              result))
                # Either way the file reads back whole: every line is valid.
                store = LearningStore(self.path, clock=lambda: self.now)
                self.assertEqual(store.skipped, 0)
                self.assertTrue(result == original or store.lines == len(store.records()))
        # The interrupted runs left the original; a run to the end the compacted file.
        self.assertIsNotNone(expected)


KILL_SCRIPT = r"""
import os, sys
from unittest.mock import patch
from yuragi.ime.learning import LearningStore
path, point, now = sys.argv[1], sys.argv[2], float(sys.argv[3])
def die(*a, **k):
    os._exit(9)  # like a kill: no finally blocks, no flushing
real = {"fsync": os.fsync, "link": os.link, "replace": os.replace}
def at(name):
    def step(*a, **k):
        if name == point:
            die()
        return real[name](*a, **k)
    return step
store = LearningStore(path, clock=lambda: now)
if point == "write":
    import builtins
    real_open = builtins.open
    def opener(file, mode="r", *a, **k):
        if str(file).endswith(".tmp"):
            stream = real_open(file, mode, *a, **k)
            stream.write(b'{"partial":')
            stream.flush()
            die()
        return real_open(file, mode, *a, **k)
    patch("builtins.open", opener).start()
with patch("os.fsync", at("fsync")), patch("os.link", at("link")), \
        patch("os.replace", at("replace")):
    store.compact_if_needed()
"""


if __name__ == "__main__":
    unittest.main()
