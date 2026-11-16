"""Key repeat (CONVERSION §5.1): a held FSM key gives its last token again;
keys outside the FSM act again on every repeated down."""
from __future__ import annotations

import unittest

from yuragi.chord.fsm import AmbShift
from yuragi.ime.server import dispatch
from yuragi.ime.session import ImeSession
from yuragi.lattice.mozc_dict import MozcLex
from yuragi.lattice.table import load_table

VK_SPACE, VK_K = 0x20, ord("K")


class KeyRepeatTest(unittest.TestCase):
    def setUp(self):
        # No dictionary rows: kana stays kana.
        lex = MozcLex({}, set(), [0] * 4, 2)
        self.s = ImeSession(_table=load_table(), _lex=lex)
        self.t = 1000
        self.committed = ""

    def send(self, op, vk=None, mods=None, *, step=30):
        self.t += step
        msg = {"op": op, "t": self.t}
        if vk is not None:
            msg["vk"] = vk
        if mods is not None:
            msg["mods"] = mods
        reply = dispatch(self.s, msg)
        self.committed += reply["commit"]
        return reply

    def hold(self, vk, repeats, mods=None):
        """The first down, the 80 ms window, then repeated downs (no up)."""
        self.send("down", vk, mods)
        self.send("timeout", step=200)
        for _ in range(repeats):
            reply = self.send("down", vk, mods)
        return reply

    def test_a_held_character_repeats(self):
        self.assertEqual(self.hold(VK_K, 3)["composition"], "きききき")

    def test_a_held_chord_repeats_the_same_face(self):
        self.send("down", VK_SPACE)
        reply = self.hold(VK_K, 3)
        self.assertEqual(len(reply["composition"]), 4)
        self.assertEqual(len(set(reply["composition"])), 1)  # のののの or ぎぎぎぎ, never mixed
        chords = {(t.press, t.turn) for t in self.s.tokens if isinstance(t, AmbShift)}
        self.assertEqual(len(chords), 1)
        self.assertEqual(len(self.s.tokens), 4)

    def test_a_lone_space_repeats(self):
        self.hold(VK_SPACE, 3)
        self.assertEqual(self.committed, "\u3000" * 4)  # full width: the kana mode's space
        self.assertEqual(self.s.tokens, [])

    def test_a_lone_space_with_input_converts_then_cycles(self):
        self.send("down", VK_K)
        self.send("up", VK_K)
        self.send("timeout", step=200)
        self.send("down", VK_SPACE)
        self.assertTrue(self.send("timeout", step=200)["converted"])
        first = self.s.segments[self.s.focus].index
        self.send("down", VK_SPACE)
        self.assertEqual(self.s.segments[self.s.focus].index, first + 1)


if __name__ == "__main__":
    unittest.main()
