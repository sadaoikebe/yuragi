"""Learning (CONVERSION「学習」): the choice committed last comes first next time,
whatever comes before it; Shift+F6 forgets it, and another process's change to
the file is read again."""

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

VK_RETURN, VK_SPACE, VK_LEFT, VK_F6 = 0x0D, 0x20, 0x25, 0x75


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

    def shown(self, s, text, reading):
        """Convert text; the segment with this reading, focused."""
        self.convert(s, text)
        s.focus = next(i for i, g in enumerate(s.segments) if g.selected.reading == reading)
        s._open_cands()
        return s.segments[s.focus]

    def choose(self, s, text, reading, surface):
        """Convert text, pick this surface for the clause with this reading, commit;
        what that clause showed before the pick."""
        segment = self.shown(s, text, reading)
        before = segment.selected.surface
        index = 0
        while segment.choices.ensure(index) and segment.choices.cache[index].surface != surface:
            index += 1
        s._select(index)
        dispatch(s, {"op": "down", "vk": VK_RETURN})
        return before

    def test_the_last_choice_comes_first(self):
        # One session, as on the machine: each commit is the next one's left neighbor.
        s = self.session()
        picks = ("公正", "厚生", "公正", "厚生", "構成", "公正")  # back and forth
        self.choose(s, "こうせい", "こうせい", picks[0])
        for last, surface in zip(picks, picks[1:]):
            self.assertEqual(self.choose(s, "こうせい", "こうせい", surface), last)

    def test_a_choice_far_down_comes_first_after_any_neighbor(self):
        s = self.session()
        self.choose(s, "きのうはきかん", "きかん", "旗艦")
        self.assertEqual(self.choose(s, "きょうもきかん", "きかん", "帰還"), "旗艦")
        self.assertEqual(self.shown(s, "きのうはきかん", "きかん").selected.surface, "帰還")

    def test_a_learned_clause_resizes_to_its_own_rows(self):
        s = self.session()
        self.choose(s, "きょうは", "きょうは", "今日は")
        self.convert(s, "きょうは")
        dispatch(s, {"op": "down", "vk": VK_LEFT, "mods": ["shift"]})
        self.assertEqual([g.selected.reading for g in s.segments], ["きょう", "は"])
        self.assertEqual(s.composition, "今日は")

    def test_penalized_numeral_can_be_chosen_and_learned(self):
        for reading, first, surface in (("いち", "市", "1"), ("ようか", "ようか", "8日")):
            with self.subTest(reading=reading):
                s = self.session()
                self.assertEqual(self.choose(s, reading, reading, surface), first)
                row = LearningStore(self.path).snapshot().head(reading)
                self.assertEqual(row.surface, surface)
                self.assertLess(max(row.lid, row.rid), self.lex.pos_size)
                reopened = self.session()
                self.assertEqual(self.convert(reopened, reading).selected.surface, surface)

    def test_shift_f6_forgets_the_choice(self):
        s = self.session()
        chosen = self.choose_second(s, "こうせい")
        segment = self.convert(s, "こうせい")
        self.assertEqual(segment.selected.surface, chosen)
        dispatch(s, {"op": "down", "vk": VK_F6, "mods": ["shift"]})
        self.assertNotEqual(segment.selected.surface, chosen)
        self.assertFalse(LearningStore(self.path).has_pair("こうせい", chosen))
        # Nothing learned is left to forget: no line, and the selection stays.
        s._select(2)
        shown, size = segment.selected.surface, self.path.stat().st_size
        dispatch(s, {"op": "down", "vk": VK_F6, "mods": ["shift"]})
        self.assertEqual((segment.selected.surface, self.path.stat().st_size), (shown, size))

    def test_forgetting_in_the_window_reaches_a_running_session(self):
        s = self.session()
        chosen = self.choose_second(s, "こうせい")
        self.assertTrue(learning_admin.forget(self.path, "こうせい", chosen))
        self.assertNotEqual(self.convert(s, "こうせい").selected.surface, chosen)


if __name__ == "__main__":
    unittest.main()
