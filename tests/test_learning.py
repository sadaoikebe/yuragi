"""Learning: confirmed choices, contextual ranking and suppression."""

from __future__ import annotations

from contextlib import redirect_stderr
import io
from pathlib import Path
import tempfile
import unittest

from yuragi.chord.fsm import Plain
from yuragi.ime.learning import LearningStore
from yuragi.ime.server import dispatch
from yuragi.ime.session import ImeSession
from yuragi.ime import learning_admin
from tests.support import small_lex, type_plain

VK_RETURN, VK_SPACE, VK_UP, VK_DOWN, VK_DELETE, VK_F7 = 0x0D, 0x20, 0x26, 0x28, 0x2E, 0x76


class LearningTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lex = small_lex("""
こうせい 構成 1000
こうせい 公正 2000
こうせい 厚生 3000
こうせい 恒星 4000
きかん 帰還 1000
きかん 旗艦 2000
きのう 昨日 1000
きょう 今日 1000
は は 0 283
も も 0 283
いい 良い 1000
てんき 天気 1000
いち 市 3000
いち 1 0 2044
ようか 養家 3000
ようか 8日 0 2046
きしゃ 記者 1000
きしゃ 汽車 2000""")

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
        type_plain(s, reading)
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

    def test_left_bunsetsu_takes_priority_over_recency(self):
        s = self.session()
        self.choose(s, "きのうはきかん", "きかん", "旗艦")
        self.assertEqual(self.choose(s, "きょうもきかん", "きかん", "帰還"), "旗艦")
        segment = self.shown(s, "きのうはきかん", "きかん")
        self.assertEqual(segment.selected.surface, "旗艦")
        self.assertEqual(segment.choices.cache[0].surface, "旗艦")
        self.assertIn(b'"prev"', self.path.read_bytes())

    def test_penalized_numeral_can_be_chosen_and_learned(self):
        for reading, first, surface in (("いち", "市", "1"), ("ようか", "養家", "8日")):
            with self.subTest(reading=reading):
                s = self.session()
                self.assertEqual(self.choose(s, reading, reading, surface), first)
                row = LearningStore(self.path).snapshot().head(reading)
                self.assertEqual(row.surface, surface)
                self.assertLess(max(row.lid, row.rid), self.lex.pos_size)
                reopened = self.session()
                self.assertEqual(self.convert(reopened, reading).selected.surface, surface)

    def test_committing_what_was_shown_writes_nothing(self):
        # Every way to commit the shown result. One path that misses it would
        # learn the engine's own pick again (CONVERSION「学習」).
        # きょうは shows an earlier choice, a learned row without words.
        text = "きょうはいいてんきですね"
        earlier = self.session()
        self.convert(earlier, "きょうは")
        dispatch(earlier, {"op": "down", "vk": VK_F7})
        dispatch(earlier, {"op": "down", "vk": VK_RETURN})
        learned = self.path.read_bytes()
        s = self.session()

        def show(convert):
            type_plain(s, text)
            if convert:
                for op in ("down", "up"):  # a lone thumb key converts on its release
                    dispatch(s, {"op": op, "vk": VK_SPACE})
                self.assertTrue(s.converted)
                self.assertTrue(s.composition.startswith("キョウハ"))
            return s.composition

        for name, convert, keys in (
                ("enter before converting", False, []),
                ("enter after converting", True, []),
                ("partial commit", True, [(VK_DOWN, ["ctrl"])]),
                ("down and back up", True, [(VK_DOWN, None), (VK_UP, None)])):
            with self.subTest(name):
                shown = show(convert)
                committed = "".join(
                    dispatch(s, {"op": "down", "vk": vk, **({"mods": mods} if mods else {})})
                    ["commit"] for vk, mods in keys + [(VK_RETURN, None)])
                self.assertEqual(committed, shown)
        with self.subTest("the next key commits"):
            shown = show(True)
            self.assertEqual(s._ingest([Plain(text[0])]), shown)
            s.reset()
        self.assertEqual(self.path.read_bytes(), learned)

    def test_ctrl_delete_forgets_the_choice(self):
        s = self.session()
        chosen = self.choose_second(s, "こうせい")
        segment = self.convert(s, "こうせい")
        self.assertEqual(segment.selected.surface, chosen)
        dispatch(s, {"op": "down", "vk": VK_DELETE, "mods": ["ctrl"]})
        self.assertNotEqual(segment.selected.surface, chosen)
        self.assertFalse(LearningStore(self.path).has_pair("こうせい", chosen))
        # Nothing learned is left to forget: no line, and the selection stays.
        s._select(2)
        shown, size = segment.selected.surface, self.path.stat().st_size
        dispatch(s, {"op": "down", "vk": VK_DELETE, "mods": ["ctrl"]})
        self.assertEqual((segment.selected.surface, self.path.stat().st_size), (shown, size))

    def test_forgetting_in_the_window_reaches_a_running_session(self):
        s = self.session()
        chosen = self.choose_second(s, "こうせい")
        self.assertTrue(learning_admin.forget(self.path, "こうせい", chosen))
        self.assertNotEqual(self.convert(s, "こうせい").selected.surface, chosen)

    def test_a_commit_right_after_forgetting_keeps_it_forgotten(self):
        s = self.session()
        chosen = self.choose_second(s, "こうせい")
        self.convert(s, "きしゃ")
        s._select(1)
        # The window forgets while this conversion is open; Enter then appends.
        self.assertTrue(learning_admin.forget(self.path, "こうせい", chosen))
        dispatch(s, {"op": "down", "vk": VK_RETURN})
        self.assertFalse(s._learning.has_pair("こうせい", chosen))
        self.assertNotEqual(self.convert(s, "こうせい").selected.surface, chosen)

    def test_an_unreadable_history_is_not_used_until_it_can_be_read(self):
        s = self.session()
        chosen = self.choose_second(s, "こうせい")
        aside = self.path.with_name("aside")
        self.path.rename(aside)
        self.path.mkdir()  # it exists, but cannot be read as a file
        with redirect_stderr(io.StringIO()) as log:
            for _ in range(2):  # one line for the whole time, not one per conversion
                self.assertNotEqual(self.convert(s, "こうせい").selected.surface, chosen)
        self.assertEqual(log.getvalue().count("learning history unreadable"), 1)
        self.path.rmdir()
        aside.rename(self.path)
        self.assertEqual(self.convert(s, "こうせい").selected.surface, chosen)

    def test_rows_of_the_wrong_shape_are_skipped_and_the_rest_is_used(self):
        good = ('{"reading":"こうせい","surface":"公正","timestamp":1,"cost":2000,'
                '"lid":1851,"rid":1851,"choice":true}')
        bad = [good.replace('"こうせい"', '5'), good.replace('"こうせい"', '["a"]'),
               good.replace('"公正"', 'null'), good.replace('"公正"', '""'),
               good.replace('"cost":2000', '"cost":"2000"'), good.replace('"lid":1851', '"lid":null'),
               good.replace('"timestamp":1', '"timestamp":"x"'), '[1]',
               '{"type":"suppress","reading":"きかん","surface":7,"timestamp":1}']
        # A BOM, as an editor or Windows PowerShell writes it, does not hide the first row.
        self.path.write_text("\ufeff" + "\n".join([good, *bad]) + "\n", encoding="utf-8")
        s = self.session()
        self.assertEqual(s._learning.skipped, len(bad))
        self.assertEqual(self.convert(s, "こうせい").selected.surface, "公正")
        self.assertEqual(learning_admin.pairs(s._learning)[0].surface, "公正")

    def test_a_word_row_with_an_id_the_dictionary_lacks_is_not_used(self):
        self.path.write_text('{"reading":"きしゃ","surface":"汽車","timestamp":1,"cost":2000,'
                             '"lid":99999,"rid":99999,"choice":true,"word":true}\n', encoding="utf-8")
        s = self.session()
        self.assertEqual(self.convert(s, "きしゃは").selected.surface, "記者は")


if __name__ == "__main__":
    unittest.main()
