"""Learning (CONVERSION §7): a committed choice comes first next time, Shift+F6
forgets it, and another process's change to the file is read again."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from yuragi.chord.fsm import Plain
from yuragi.ime.learning import LearningStore
from yuragi.ime.server import dispatch
from yuragi.ime.session import ImeSession
from yuragi.ime import learning_admin
from tests.real_dictionary import real_lex

VK_RETURN, VK_SPACE, VK_F6 = 0x0D, 0x20, 0x75


class LearningTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lex = real_lex()

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "learning.jsonl"
        self.path.touch()

    def session(self):
        return ImeSession(_lex=self.lex, _learning=LearningStore(self.path))

    @staticmethod
    def convert(s, reading):
        """Type the reading (unambiguous faces, no FSM) and convert it."""
        s._table = {"keys": {c: {"plain": c} for c in reading}}
        s.tokens = [Plain(c) for c in reading]
        s._refresh()
        s.converted = True
        s._open_cands()
        return s.segments[s.focus]

    def choose_second(self, s, reading):
        """Convert, pick a dictionary row that is not first, commit; its surface."""
        segment = self.convert(s, reading)
        stream = segment.choices
        stream.ensure(5)
        index = next(i for i, c in enumerate(stream.cache)
                     if i > 0 and c.kind == "dictionary")
        s._select(index)
        surface = segment.selected.surface
        dispatch(s, {"op": "down", "vk": VK_RETURN})
        return surface

    def test_a_committed_choice_comes_first_next_time(self):
        s = self.session()
        chosen = self.choose_second(s, "こうせい")
        self.assertEqual(self.convert(self.session(), "こうせい").selected.surface, chosen)

    def test_shift_f6_forgets_the_choice(self):
        s = self.session()
        chosen = self.choose_second(s, "こうせい")
        segment = self.convert(s, "こうせい")
        self.assertEqual(segment.selected.surface, chosen)
        dispatch(s, {"op": "down", "vk": VK_F6, "mods": ["shift"]})
        self.assertNotEqual(segment.selected.surface, chosen)
        self.assertFalse(LearningStore(self.path).has_pair("こうせい", chosen))

    def test_forgetting_in_the_window_reaches_a_running_session(self):
        s = self.session()
        chosen = self.choose_second(s, "こうせい")
        self.assertTrue(learning_admin.forget(self.path, "こうせい", chosen))
        self.assertNotEqual(self.convert(s, "こうせい").selected.surface, chosen)


if __name__ == "__main__":
    unittest.main()
