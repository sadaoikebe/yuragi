"""英数の続き: Shift+letter starts half-width alphanumerics that last until
the input is committed, cancelled or erased."""
from __future__ import annotations

import unittest

from tests.support import Keys, kana_session

VK_SPACE, VK_RETURN, VK_BACK, VK_ESCAPE = 0x20, 0x0D, 0x08, 0x1B
VK_LEFT, VK_RIGHT = 0x25, 0x27
VK_F6, VK_F7, VK_F8, VK_F9, VK_F10 = 0x75, 0x76, 0x77, 0x78, 0x79
VK_COMMA, VK_PERIOD, VK_SLASH, VK_RBRACKET = 0xBC, 0xBE, 0xBF, 0xDD


class AlnumContinuationTest(unittest.TestCase):
    def keys(self):
        return Keys(kana_session())

    def test_the_run_takes_each_key_as_half_width(self):
        # Letters, Shift+letters, plain symbols and digits, Shift+digit (the
        # upper engraving) and a key with no plain face (]) all go on the run.
        k = self.keys()
        k.shift("A")
        k.shift("B")
        k.letters("c")
        for vk, mods in ((VK_COMMA, []), (VK_PERIOD, []), (VK_SLASH, []), (ord("1"), []),
                         (ord("1"), ["shift"]), (VK_RBRACKET, [])):
            k.tap(vk, mods)
        self.assertEqual(k.letters("d")["composition"], "ABc,./1!]d")
        self.assertEqual(k.tap(VK_RETURN)["commit"], "ABc,./1!]d")
        self.assertEqual(k.s.composition, "")

    def test_the_run_is_one_clause(self):
        # き, then Windows10: two clauses; ←/→ step over the run as a whole and
        # its candidates are the run as typed.
        k = self.keys()
        k.letters("k")  # き
        k.idle()
        k.shift("W")
        k.letters("indows")
        k.tap(ord("1"))
        k.tap(ord("0"))
        reply = k.tap(VK_SPACE)
        self.assertEqual([g["surface"] for g in reply["segments"]], ["き", "Windows10"])
        self.assertEqual(reply["focus"], 0)
        reply = k.tap(VK_RIGHT)
        self.assertEqual((reply["focus"], reply["candidates"]), (1, []))
        self.assertEqual(k.tap(VK_SPACE)["candidates"], ["Windows10"])
        self.assertEqual(k.tap(VK_RIGHT)["focus"], 1)
        self.assertEqual(k.tap(VK_LEFT)["focus"], 0)
        self.assertEqual(k.tap(VK_RETURN)["commit"], "きWindows10")

    def test_overlapping_space_converts_the_run(self):
        k = self.keys()
        k.shift("T")
        k.letters("es")
        k.down(ord("T"), [])
        reply = k.down(VK_SPACE, [])  # before t is released
        k.up(ord("T"), [])
        k.up(VK_SPACE, [])
        self.assertTrue(reply["converted"])
        self.assertEqual(reply["composition"], "Test")
        self.assertEqual(k.tap(VK_RETURN)["commit"], "Test")

    def test_script_keys_leave_a_run_with_no_kana_as_typed(self):
        k = self.keys()
        k.shift("A")
        k.letters("bc")
        for vk in (VK_F6, VK_F7, VK_F8, VK_F9, VK_F10):
            reply = k.tap(vk)
            self.assertEqual((reply["phase"], reply["composition"]), ("composing", "Abc"))
        self.assertEqual(k.letters("d")["composition"], "Abcd")
        self.assertEqual(k.committed, "")

    def test_ways_back_to_kana(self):
        k = self.keys()
        k.shift("A")
        self.assertEqual(k.letters("a")["composition"], "Aa")  # the を key
        k.tap(VK_BACK)
        k.tap(VK_BACK)
        self.assertEqual(k.s.composition, "")
        k.letters("a")
        k.idle()
        self.assertEqual(k.s.composition, "う")
        k.tap(VK_RETURN)
        k.shift("A")
        k.tap(VK_RETURN)
        self.assertEqual(k.committed, "うA")
        k.letters("a")
        k.idle()
        self.assertEqual(k.s.composition, "う")


if __name__ == "__main__":
    unittest.main()
