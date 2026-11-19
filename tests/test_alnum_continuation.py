"""英数の続き: Shift+letter starts half-width alphanumerics that last until
the input is committed, cancelled or erased."""
from __future__ import annotations

import unittest

from yuragi.ime.server import dispatch
from yuragi.ime.session import ImeSession
from yuragi.lattice.mozc_dict import MozcLex
from yuragi.lattice.table import load_table

VK_SPACE, VK_RETURN, VK_BACK, VK_ESCAPE = 0x20, 0x0D, 0x08, 0x1B
VK_LEFT, VK_RIGHT = 0x25, 0x27
VK_COMMA, VK_PERIOD, VK_SLASH, VK_RBRACKET = 0xBC, 0xBE, 0xBF, 0xDD


class Keys:
    """A session driven through dispatch() with a running clock."""

    def __init__(self):
        # No dictionary rows: kana stays kana (the run is what is checked).
        lex = MozcLex({}, set(), [0] * 4, 2)
        self.s = ImeSession(_table=load_table(), _lex=lex)
        self.t = 1000
        self.committed = ""

    def send(self, op, vk, mods=None, *, step=30):
        self.t += step
        msg = {"op": op, "vk": vk, "t": self.t}
        if mods is not None:
            msg["mods"] = mods
        reply = dispatch(self.s, msg)
        self.committed += reply["commit"]
        return reply

    def down(self, vk, mods=None):
        return self.send("down", vk, mods)

    def up(self, vk, mods=None):
        return self.send("up", vk, mods)

    def tap(self, vk, mods=None):
        """Down and up; the reply after the release, with both events' commits."""
        commit = self.down(vk, mods)["commit"]
        reply = self.up(vk, mods)
        return {**reply, "commit": commit + reply["commit"]}

    def shift(self, letter):
        return self.tap(ord(letter), ["shift"])

    def letters(self, text):
        for ch in text:
            reply = self.tap(ord(ch.upper()), [])
        return reply

    def idle(self):
        """Let a pending chord's timer run out."""
        self.t += 200
        reply = dispatch(self.s, {"op": "timeout", "t": self.t})
        self.committed += reply["commit"]
        return reply


class AlnumContinuationTest(unittest.TestCase):
    def keys(self):
        return Keys()

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
        self.assertEqual((reply["focus"], reply["candidates"]), (1, ["Windows10"]))
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
        self.assertEqual(k.s.composition, "Test")
        self.assertEqual(k.tap(VK_RETURN)["commit"], "Test")

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
