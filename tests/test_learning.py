from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from yuragi.chord.fsm import Plain
from yuragi.ime.bunsetsu import Candidate
from yuragi.ime.learning import LearningStore
from yuragi.ime.server import dispatch
from yuragi.ime.session import ImeSession
from yuragi.lattice.mozc_dict import load_lex


def press_shift(s, vk):
    """Shift+key down and up (the learning operations live on Shift+F6/F7)."""
    reply = dispatch(s, {"op": "down", "vk": vk, "mods": ["shift"]})
    dispatch(s, {"op": "up", "vk": vk, "mods": ["shift"]})
    return reply


class LearningTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lex = load_lex()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "learning.jsonl"
        self.path.touch()
        self.now = 1_800_000_000.0

    def store(self):
        return LearningStore(self.path, clock=lambda: self.now)

    def session(self, *, lex=None):
        return ImeSession(_lex=lex or self.lex, learning_path=None, _learning=self.store())

    def type_reading(self, s, reading):
        # Exercise production refresh/candidate/commit logic without duplicating
        # the chord FSM tests. Every character has an unambiguous physical face.
        s._table = {"keys": {c: {"plain": c} for c in reading}}
        s.tokens = [Plain(c) for c in reading]
        s._refresh()

    def choose(self, s, surface, *, kind="dictionary", reading=None):
        if reading is not None:
            s.focus = next(i for i, seg in enumerate(s.segments)
                           if seg.selected.reading == reading)
        s.converted = True
        s._open_cands()
        stream = s.segments[s.focus].choices
        stream.last()
        index = next(i for i, c in enumerate(stream.cache)
                     if c.surface == surface and c.kind == kind)
        s._select(index)

    def rows(self):
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()]

    def test_missing_disabled_and_corrupt_files_and_write_failure(self):
        self.path.unlink()
        s = self.session()
        self.type_reading(s, "こうせい")
        dispatch(s, {"op": "down", "vk": 13})
        self.assertFalse(self.path.exists())
        self.path.write_text('broken\n{"version": 999}\n{"incomplete":', encoding="utf-8")
        store = self.store()
        self.assertIsNone(store.snapshot())
        c = Candidate("校正", "こうせい", 0, 1, 1, word_cost=5000)
        store.confirm([(c, "")], self.lex)
        self.assertEqual(self.store().bonus("こうせい", "校正", ""), 6000)
        s._learning = store
        self.type_reading(s, "こうせい")
        expected = s.composition
        with patch("yuragi.ime.learning.os.open", side_effect=PermissionError):
            self.assertEqual(dispatch(s, {"op": "down", "vk": 13})["commit"], expected)

    def test_learning_operations_disabled_and_failed_writes_can_retry(self):
        s = self.session()
        self.type_reading(s, "こうせい")
        self.choose(s, "校正")
        dispatch(s, {"op": "down", "vk": 13})
        dispatch(s, {"op": "reset"})
        self.type_reading(s, "こうせい")
        self.choose(s, "校正")
        before, composition = self.path.read_bytes(), s.composition
        with patch("yuragi.ime.learning.os.open", side_effect=PermissionError):
            self.assertFalse(s.forget_candidate())
            self.assertFalse(s.undo_learning())
        self.assertEqual((self.path.read_bytes(), s.composition), (before, composition))
        self.assertTrue(s.undo_learning())  # failed write did not pop the undo group
        self.path.unlink()
        self.assertFalse(s.forget_candidate())
        self.assertFalse(self.path.exists())
        disabled = ImeSession(learning_path=None)
        for vk in (0x75, 0x76):
            self.assertEqual(press_shift(disabled, vk)["commit"], "")

    def test_corrupt_control_records_do_not_hide_valid_confirmations(self):
        store = self.store()
        c = Candidate("校正", "こうせい", 0, 1851, 1851, word_cost=5000)
        store.confirm([(c, "")], self.lex)
        # REDESIGN §6.7 rule 5: a line counts when it is JSON with the needed
        # fields; anything else is skipped and counted, nothing more is checked.
        invalid = [
            {"type": "suppress", "reading": c.reading, "timestamp": self.now},  # no surface
            {"type": "tombstone", "timestamp": self.now},  # no record_ids
            {"type": "future", "timestamp": self.now},
            {"type": "suppress", "reading": c.reading, "surface": c.surface,
             "timestamp": self.now, "unknown_field": 1},
        ]
        with self.path.open("a", encoding="utf-8") as stream:
            for row in invalid:
                stream.write(json.dumps(row) + "\n")
            stream.write("not json\n")
            stream.write('{"type":"suppress",')
        reread = self.store()
        self.assertEqual(reread.bonus(c.reading, c.surface, ""), 6000)
        self.assertEqual((reread.lines, reread.skipped), (7, 6))
        store.suppress(c.reading, c.surface)  # repairs the missing newline on append
        self.assertEqual(self.store().bonus(c.reading, c.surface, ""), 0)


if __name__ == "__main__":
    unittest.main()
