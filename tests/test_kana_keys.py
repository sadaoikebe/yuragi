"""F7 (katakana) and F10 (the typed keys as alphanumerics) on the input."""
from __future__ import annotations

import unittest

from yuragi.chord.fsm import Plain
from yuragi.chord.keys import VK_CONVERT, VK_ESCAPE, VK_NONCONVERT, VK_SPACE
from yuragi.ime.server import dispatch
from yuragi.ime.session import ImeSession
from yuragi.lattice.table import load_table
from tests.support import Keys, ingest_plain, kana_session, small_lex, type_plain

VK_F6, VK_F7, VK_F10, VK_SEMICOLON = 0x75, 0x76, 0x79, 0xBA
VK_BACK, VK_LEFT, VK_RIGHT, VK_HOME = 0x08, 0x25, 0x27, 0x24
LEX = small_lex("""
きょう 京 2000
きょう 今日 1000
きょう 強 3000
きょう 凶 3000
きょう 経 3000
がっこう 学校 1000
は は 0 283
に に 0 283
いく 行く 1000
い 行 1000
とうき 陶器 1000
くじ 籤 1000""")


def type_keys(s, keys):
    """Real NICOLA keys (unshifted faces), so F9/F10 have key letters to show."""
    s._table = load_table()
    s.tokens = [Plain(k) for k in keys]
    s._refresh()


def tap(s, vk):
    """A full press: down and up."""
    reply = dispatch(s, {"op": "down", "vk": vk})
    dispatch(s, {"op": "up", "vk": vk})
    return reply


class KanaKeyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lex = LEX

    def session(self):
        return ImeSession(_lex=self.lex)

    def test_f7_converts_unconverted_input_to_katakana(self):
        s = self.session()
        type_plain(s, "きょう")
        reply = dispatch(s, {"op": "down", "vk": VK_F7})
        self.assertEqual(reply["composition"], "キョウ")
        self.assertTrue(s.converted)
        selected = s.segments[s.focus].selected
        self.assertEqual((selected.surface, selected.kind), ("キョウ", "kana"))

    def test_f7_again_steps_to_the_next_reading_the_thumb_keys_allow(self):
        # く, あ/じ, ん, ば/み: one thumb key leaves each of the two ambiguous.
        k = Keys(kana_session(self.lex))
        k.plain("i")
        k.chords("s")
        k.tap(VK_SEMICOLON)
        k.chords("h")
        k.idle()
        self.assertEqual([k.tap(VK_F7)["composition"] for _ in range(5)],
                         ["クジンバ", "クジンミ", "クアンバ", "クアンミ", "クジンバ"])
        self.assertEqual([k.tap(VK_F6)["composition"] for _ in range(2)], ["くじんば", "くじんみ"])

    def test_f10_gives_the_typed_keys_and_cycles_case(self):
        s = self.session()
        type_keys(s, "ew")  # た か
        surfaces = [tap(s, VK_F10)["composition"] for _ in range(4)]
        self.assertEqual(surfaces, ["ew", "EW", "Ew", "ew"])
        self.assertEqual(s.segments[s.focus].selected.reading, "たか")

    def test_script_keys_respell_all_of_the_unconverted_input(self):
        # MS-IME's F7 and F10 change the input string (ms-ime.md §1), not its first run:
        # a digit typed between two kana must not leave the second kana as it was.
        for vk, typed in ((VK_F7, "ト１ト"), (VK_F10, "j1j")):
            with self.subTest(key=hex(vk)):
                k = Keys(kana_session(self.lex))
                k.letters("j")
                k.tap(ord("1"))
                k.letters("j")
                self.assertEqual(k.idle()["composition"], "と１と")
                self.assertEqual(k.tap(vk)["composition"], typed)


class JisKeyTest(unittest.TestCase):
    def test_convert_starts_conversion_and_shift_convert_opens_its_candidates(self):
        k = Keys(kana_session(LEX))
        input_text = k.letters("jak")["composition"]
        passed = k.down(VK_CONVERT, ["shift"])
        k.up(VK_CONVERT, ["shift"])
        self.assertEqual((passed["eat"], passed["commit"], passed["composition"]),
                         (False, "", input_text))
        converted = k.tap(VK_CONVERT)
        self.assertEqual((converted["phase"], converted["candidates"]), ("converting", []))
        opened = k.tap(VK_CONVERT, ["shift"])
        self.assertEqual(opened["composition"], converted["composition"])
        self.assertEqual(opened["phase"], "selecting")
        self.assertIn(opened["composition"], opened["candidates"])

    def test_nonconvert_cycles_kana_and_keeps_the_reading_for_space(self):
        k = Keys(kana_session())
        k.letters("jak")
        changed = [k.tap(VK_NONCONVERT) for _ in range(4)]
        self.assertEqual([r["composition"] for r in changed],
                         ["トウキ", "ﾄｳｷ", "とうき", "トウキ"])
        for reply in changed:
            self.assertEqual((reply["phase"], reply["commit"]), ("composing", ""))
        self.assertEqual(k.tap(VK_SPACE)["composition"], "とうき")

    def test_converted_nonconvert_restyles_the_focused_clause_and_a_literal_keeps_its_rows(self):
        k = Keys(kana_session(LEX))
        k.letters("jak")  # とうき
        k.tap(ord("1"))
        k.tap(ord("2"))
        k.tap(VK_SPACE)
        self.assertEqual([k.tap(VK_NONCONVERT)["composition"] for _ in range(4)],
                         ["とうき１２", "トウキ１２", "ﾄｳｷ１２", "とうき１２"])
        k.tap(VK_RIGHT)
        self.assertEqual(k.tap(VK_NONCONVERT, ["shift"])["composition"], "とうき12")
        opened = k.tap(VK_CONVERT, ["shift"])
        self.assertEqual((opened["candidates"], opened["cand_index"]),
                         (["１２", "12", "一二", "十二"], 1))

        # A clause that Backspace left as typed text, revisited: its own rows.
        s = kana_session(LEX)
        type_plain(s, "きょうはがっこうにいく")
        k = Keys(s)
        k.tap(VK_SPACE)
        self.assertEqual(k.tap(VK_BACK)["composition"], "今日は学校に行")
        k.tap(VK_LEFT, ["ctrl"])
        k.tap(VK_LEFT)
        k.tap(VK_RIGHT)
        self.assertEqual(k.tap(VK_CONVERT, ["shift"])["candidates"], ["行"])

    def test_the_spelling_left_before_more_input_is_one_clause(self):
        s = kana_session(LEX)
        k = Keys(s)
        ingest_plain(s, "がい")
        k.tap(VK_NONCONVERT)
        self.assertEqual(k.tap(VK_NONCONVERT)["composition"], "ｶﾞｲ")
        ingest_plain(s, "がっこうにいく")
        converted = k.tap(VK_SPACE)
        self.assertEqual([(g["surface"], g["start"], g["end"]) for g in converted["segments"]],
                         [("ｶﾞｲ", 0, 2), ("学校に", 2, 7), ("行く", 7, 9)])
        self.assertEqual(k.tap(VK_HOME)["focus"], 0)
        # Open for input, the caret is after ｶﾞｲ: two units, three characters.
        edited = k.tap(VK_ESCAPE)
        self.assertEqual((edited["phase"], edited["caret"]), ("editing", 3))

    def test_width_changes_leave_the_input_uncommitted_and_keep_it_when_typing(self):
        k = Keys(kana_session())
        k.letters("jak")
        self.assertEqual(k.tap(VK_NONCONVERT, ["shift"])["composition"], "ｊａｋ")
        self.assertEqual(k.tap(VK_NONCONVERT, ["shift"])["composition"], "jak")
        self.assertEqual(k.letters("l")["composition"], "jakい")
        self.assertEqual(k.tap(VK_NONCONVERT)["composition"], "jakイ")
        self.assertEqual(k.tap(VK_ESCAPE)["composition"], "")
        self.assertEqual(k.committed, "")

    def test_empty_mode_switches_affect_following_text(self):
        k = Keys(kana_session())
        k.tap(VK_NONCONVERT)
        self.assertEqual(k.letters("k")["composition"], "キ")
        k.tap(VK_ESCAPE)
        k.tap(VK_NONCONVERT)
        self.assertEqual(k.letters("k")["composition"], "ｷ")
        k.tap(VK_ESCAPE)
        k.tap(VK_NONCONVERT, ["shift"])
        self.assertEqual(k.letters("a")["composition"], "ａ")
        k.tap(VK_ESCAPE)
        self.assertEqual(k.tap(VK_NONCONVERT, ["shift"])["phase"], "direct")
        self.assertFalse(k.down(ord("A"))["eat"])


if __name__ == "__main__":
    unittest.main()
