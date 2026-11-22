"""Typing and conversion with keys held down."""
from __future__ import annotations

import unittest

from yuragi.ime.server import dispatch
from yuragi.ime.session import ImeSession
from yuragi.lattice.mozc_dict import MozcLex
from yuragi.lattice.table import load_table

VK_SPACE, VK_K, VK_ENTER = 0x20, ord("K"), 0x0D


class KeyRepeatTest(unittest.TestCase):
    def setUp(self):
        # No dictionary rows: kana stays kana.
        lex = MozcLex({}, set(), [0] * 4, 2)
        self.s = ImeSession(_table=load_table(), _lex=lex)
        self.t = 1000

    def send(self, op, vk=None, *, step=30):
        self.t += step
        msg = {"op": op, "t": self.t}
        if vk is not None:
            msg["vk"] = vk
        return dispatch(self.s, msg)

    def test_a_held_character_repeats(self):
        self.send("down", VK_K)
        self.send("down", VK_K, step=400)
        for _ in range(2):
            self.send("down", VK_K)
        self.send("up", VK_K)
        self.assertEqual(self.send("down", VK_ENTER)["commit"], "きききき")

    def test_a_lone_space_repeats(self):
        self.send("down", VK_SPACE)
        first = self.send("down", VK_SPACE, step=400)["commit"]
        second = self.send("down", VK_SPACE)["commit"]
        third = self.send("up", VK_SPACE)["commit"]
        self.assertEqual(first + second + third, "\u3000" * 3)

    def test_held_space_converts_after_a_chord(self):
        self.send("down", VK_K)
        self.send("down", VK_K, step=400)
        self.send("down", VK_SPACE)
        self.send("up", VK_K)
        self.send("down", VK_SPACE, step=400)
        converted = self.send("down", VK_SPACE)
        self.assertTrue(converted["converted"])
        # Held on, it opens the window on the next candidate (USAGE「押しっぱなし」).
        following = self.send("down", VK_SPACE)
        self.assertEqual((following["cand_index"], following["composition"]),
                         (1, following["candidates"][1]))


if __name__ == "__main__":
    unittest.main()
