"""The JIS 106 character layer (docs/JIS-LAYOUT.md §2): faces, no-op keys, Shift and alnum faces."""
from __future__ import annotations

import unittest

from yuragi.chord.keys import (
    KEYBOARDS, VK_OEM_1, VK_OEM_102, VK_OEM_3, VK_OEM_4, VK_OEM_5, VK_OEM_6, VK_OEM_7, VK_OEM_PLUS,
    VK_SPACE, Chord,
)
from yuragi.ime.keymap import Keymap
from yuragi.ime.session import ImeSession
from yuragi.lattice.table import load_table
from tests.support import Keys, small_lex

ANSI, JIS = KEYBOARDS["ansi101"], KEYBOARDS["jis106"]
VK_AT, VK_CARET, VK_YEN, VK_SEMI, VK_COLON, VK_RBRACKET, VK_BACKSLASH = (
    VK_OEM_3, VK_OEM_7, VK_OEM_5, VK_OEM_PLUS, VK_OEM_1, VK_OEM_6, VK_OEM_102)


def jis_keys(keymap: Keymap | None = None) -> Keys:
    return Keys(ImeSession(_table=load_table(JIS.kana), _lex=small_lex("あ あ 1000"),
                           keymap=keymap or Keymap({}), keyboard=JIS))


class JisKeyboardTest(unittest.TestCase):
    def test_48_character_keys(self):
        table = load_table(JIS.kana)
        self.assertEqual(table["layout"], "NICOLA-J")
        names = JIS.character_names()
        self.assertEqual(len(names), 48)
        self.assertEqual(set(table["keys"]), {name.lower() for name in names} - {":", "]", "\\"})
        for name in names:
            self.assertTrue(Chord(name).character, name)

    def test_ansi_faces_are_unchanged(self):
        self.assertEqual(ANSI.classify(VK_OEM_1), ("M", ";"))
        self.assertEqual(ANSI.alnum_character(VK_OEM_5, False, full=True), "＼")
        self.assertIsNone(ANSI.literal_character(VK_OEM_6, False))
        self.assertEqual(ANSI.literal_character(VK_OEM_7, True), "”")

    def test_names_are_the_engravings(self):
        for name in ("@", "^", "¥", ";", ":", "]", "\\", "Shift+0", "Ctrl+[", "Ctrl+'"):
            self.assertEqual(str(Chord.parse(name)), name)
        self.assertEqual(JIS.chord(VK_SEMI, 0), Chord(";"))
        self.assertEqual(JIS.chord(VK_YEN, 0), Chord("¥"))
        self.assertEqual(JIS.chord(VK_BACKSLASH, 0), Chord("\\"))
        self.assertIsNone(JIS.code(Chord("'")))  # a US key: matches no key here
        with self.assertRaises(ValueError):
            Chord.parse("NoSuchKey")

    def test_shift_faces(self):
        expect = {0x31: "！", 0x32: "”", 0x37: "’", 0x30: "", VK_YEN: "｜", VK_BACKSLASH: "＿",
                  VK_AT: "｀", VK_SEMI: "＋", VK_COLON: "＊", VK_RBRACKET: "｝", VK_CARET: "～"}
        for vk, face in expect.items():
            self.assertEqual(JIS.literal_character(vk, True), face, hex(vk))
        self.assertEqual(JIS.literal_character(ord("Q"), True), "Q")

    def test_alnum_faces(self):
        half = {VK_YEN: ("\\", "|"), VK_BACKSLASH: ("\\", "_"), VK_AT: ("@", "`"), VK_COLON: (":", "*"),
                VK_RBRACKET: ("]", "}"), VK_SEMI: (";", "+"), 0x30: ("0", ""), 0x32: ("2", '"')}
        for vk, (plain, shifted) in half.items():
            self.assertEqual((JIS.alnum_character(vk, False), JIS.alnum_character(vk, True)),
                             (plain, shifted), hex(vk))
        self.assertEqual(JIS.alnum_character(VK_YEN, False, full=True), "￥")
        self.assertEqual(JIS.alnum_character(VK_BACKSLASH, False, full=True), "＼")
        self.assertEqual(JIS.alnum_character(VK_YEN, True, full=True), "｜")
        self.assertEqual(JIS.alnum_character(0x30, True, full=True), "")

class JisTypingTest(unittest.TestCase):
    def tap_all(self, k, *vks, mods=None):
        for vk in vks:
            k.tap(vk, mods)

    def text(self, k):
        return k.idle()["composition"]

    def chord(self, k, vk):
        """One Space press with vk inside it."""
        k.send("down", VK_SPACE, step=200)
        k.send("down", vk, step=20)
        k.send("up", vk, step=40)
        k.send("up", VK_SPACE, step=20)

    def test_plain_faces(self):
        k = jis_keys()
        self.tap_all(k, VK_SEMI, VK_AT, VK_OEM_4, VK_YEN, VK_CARET, 0x33)
        self.assertEqual(self.text(k), "ん、゛￥＾３")

    def test_thumb_faces(self):
        k = jis_keys()
        for vk in (VK_SEMI, VK_OEM_4, 0x34, 0x38):
            self.chord(k, vk)
        self.assertEqual(self.text(k), "っ゜「（")

    def test_empty_thumb_faces_and_inert_keys_are_no_ops(self):
        k = jis_keys()
        k.tap(ord("S"))
        for vk in (0x33, 0x30, VK_AT, VK_YEN):
            self.chord(k, vk)
        self.tap_all(k, VK_COLON, VK_RBRACKET, VK_BACKSLASH)
        k.tap(0x30, ["shift"])
        self.assertEqual(self.text(k), "し")
        self.assertEqual(k.committed, "")

    def test_shift_symbols_and_letters(self):
        k = jis_keys()
        for vk in (VK_COLON, VK_BACKSLASH, VK_YEN, 0x32, ord("A")):
            k.tap(vk, ["shift"])
        self.assertEqual(self.text(k), "＊＿｜”A")

    def test_full_width_alnum_keeps_the_yen_key(self):
        k = jis_keys()
        k.s.set_mode("full_alnum")
        self.tap_all(k, VK_YEN, VK_BACKSLASH, VK_COLON, ord("A"))
        self.assertEqual(self.text(k), "￥＼：ａ")

    def test_alnum_continuation_after_a_shifted_letter(self):
        k = jis_keys()
        k.tap(ord("A"), ["shift"])
        self.tap_all(k, VK_YEN, VK_COLON, VK_RBRACKET, VK_AT)
        self.assertEqual(self.text(k), "A\\:]@")

    def test_width_cycle_keeps_the_yen_key(self):
        # The ¥ key types ￥ in kana and \ in 英数; either way the other width is its own face.
        k = jis_keys()
        k.tap(VK_YEN)
        k.tap(VK_BACKSLASH, ["shift"])
        self.assertEqual(self.text(k), "￥＿")
        widths = []
        for _ in range(3):  # full-width first, from kana
            k.s._cycle_jis_script(alnum=True)
            widths.append(k.s.composition)
        self.assertEqual(widths, ["￥＿", "\\_", "￥＿"])

        k = jis_keys()
        k.tap(ord("A"), ["shift"])
        self.tap_all(k, VK_YEN)
        self.assertEqual(self.text(k), "A\\")
        k.s._cycle_jis_script(alnum=True)
        self.assertEqual(k.s.composition, "Ａ￥")

    def test_f10_uses_the_alnum_faces_of_the_keys(self):
        k = jis_keys()
        for vk in (ord("W"), VK_SEMI, ord("E")):
            k.tap(vk)
        self.assertEqual(self.text(k), "かんた")
        k.s._to_script("half_alnum")
        self.assertEqual(k.s.composition, "w;e")
        k.s._to_script("full_alnum")
        self.assertEqual(k.s.composition, "ｗ；ｅ")


if __name__ == "__main__":
    unittest.main()
