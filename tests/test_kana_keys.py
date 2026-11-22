"""F7 (katakana) and F10 (the typed keys as alphanumerics) on the input."""
from __future__ import annotations

import unittest

from yuragi.chord.fsm import Plain
from yuragi.chord.keys import VK_CONVERT, VK_ESCAPE, VK_NONCONVERT, VK_SPACE
from yuragi.ime.server import dispatch
from yuragi.ime.session import ImeSession
from yuragi.lattice.table import load_table
from tests.real_dictionary import real_lex
from tests.test_alnum_continuation import Keys

VK_F7, VK_F10 = 0x76, 0x79


def type_reading(s, reading):
    # Unambiguous faces, no FSM.
    s._table = {"keys": {c: {"plain": c} for c in reading}}
    s.tokens = [Plain(c) for c in reading]
    s._refresh()


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
        cls.lex = real_lex()

    def session(self):
        return ImeSession(_lex=self.lex)

    def test_f7_converts_unconverted_input_to_katakana(self):
        s = self.session()
        type_reading(s, "きょう")
        reply = dispatch(s, {"op": "down", "vk": VK_F7})
        self.assertEqual(reply["composition"], "キョウ")
        self.assertTrue(s.converted)
        selected = s.segments[s.focus].selected
        self.assertEqual((selected.surface, selected.kind), ("キョウ", "kana"))

    def test_f10_gives_the_typed_keys_and_cycles_case(self):
        s = self.session()
        type_keys(s, "ew")  # た か
        surfaces = [tap(s, VK_F10)["composition"] for _ in range(4)]
        self.assertEqual(surfaces, ["ew", "EW", "Ew", "ew"])
        self.assertEqual(s.segments[s.focus].selected.reading, "たか")


class JisKeyTest(unittest.TestCase):
    def test_convert_starts_conversion_and_shift_convert_opens_its_candidates(self):
        k = Keys()
        k.s._lex = real_lex()
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
        k = Keys()
        k.letters("jak")
        changed = [k.tap(VK_NONCONVERT) for _ in range(4)]
        self.assertEqual([r["composition"] for r in changed],
                         ["トウキ", "ﾄｳｷ", "とうき", "トウキ"])
        for reply in changed:
            self.assertEqual((reply["phase"], reply["commit"]), ("composing", ""))
        self.assertEqual(k.tap(VK_SPACE)["composition"], "とうき")

    def test_width_changes_leave_the_input_uncommitted_and_keep_it_when_typing(self):
        k = Keys()
        k.letters("jak")
        self.assertEqual(k.tap(VK_NONCONVERT, ["shift"])["composition"], "ｊａｋ")
        self.assertEqual(k.tap(VK_NONCONVERT, ["shift"])["composition"], "jak")
        self.assertEqual(k.letters("l")["composition"], "jakい")
        self.assertEqual(k.tap(VK_NONCONVERT)["composition"], "jakイ")
        self.assertEqual(k.tap(VK_ESCAPE)["composition"], "")
        self.assertEqual(k.committed, "")

    def test_empty_mode_switches_affect_following_text(self):
        k = Keys()
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
