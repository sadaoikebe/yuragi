"""Input-mode switching through the same dispatch() the engine uses: IME on/off
passes keys through, and switching mid-chord leaves nothing behind."""
from __future__ import annotations

import unittest

from yuragi.ime import server
from yuragi.ime.session import ImeSession
from yuragi.lattice.mozc_dict import Entry, MozcLex
from yuragi.lattice.table import load_table


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.session = ImeSession(_table=load_table(), _lex=MozcLex({}, set(), [0] * 4, 2))

    def send(self, op, **kwargs):
        return server.dispatch(self.session, {"op": op, **kwargs})

    def test_direct_dispatch_and_reset(self):
        send = self.send
        send("down", vk=65, t=0, mods=["shift"])
        self.assertEqual(self.session.composition, "A")
        reply = send("set_direct", direct=False)
        self.assertEqual(reply["composition"], "A")
        reply = send("set_direct", direct=True)
        self.assertEqual((reply["direct"], reply["composition"], reply["commit"]),
                         (True, "", ""))
        for op in ("down", "up"):
            reply = send(op, vk=65, t=20)
            self.assertTrue(reply["pass_through"])
            self.assertEqual(reply["phase"], "direct")
            if op == "down":
                self.assertIs(reply["eat"], False)
            self.assertEqual((reply["composition"], reply["commit"], reply["timer"]),
                             ("", "", None))
        self.assertTrue(send("reset")["direct"])
        self.assertEqual(send("timeout", t=100)["composition"], "")
        self.assertFalse(send("set_direct", direct=False)["direct"])
        self.assertFalse(send("down", vk=65, t=200)["pass_through"])
        send("up", vk=65, t=230)
        self.assertEqual(send("down", vk=13, t=300)["commit"], "う")

    def test_shift_space_is_immediate_and_uses_the_resolved_phase(self):
        self.session._lex = MozcLex({"き": [Entry("木", "き", 1, 1, 100),
                                          Entry("気", "き", 1, 1, 200)]},
                                   {"き"}, [0] * 4, 2)
        reply = self.send("down", vk=0x20, t=0, mods=["shift"])
        self.assertEqual((reply["phase"], reply["eat"], reply["commit"], reply["timer"]),
                         ("empty", True, " ", None))
        self.send("up", vk=0x20, t=10)
        self.send("down", vk=ord("K"), t=20)  # still in the NICOLA window
        converted = self.send("down", vk=0x20, t=30, mods=["shift"])
        self.assertEqual((converted["phase"], converted["eat"], converted["commit"]),
                         ("converting", True, ""))
        self.send("down", vk=0x20, t=32)  # opens the window
        self.send("up", vk=0x20, t=34)
        self.send("down", vk=ord("3"), t=40)
        previous = self.send("down", vk=0x20, t=50, mods=["shift"])
        self.assertEqual(previous["cand_index"], 1)

    def test_pass_through_and_commit_then_pass(self):
        numeral = self.send("down", vk=0x61, t=10)  # Numpad1
        self.assertEqual((numeral["eat"], numeral["composition"]), (True, "1"))
        self.send("down", vk=ord("K"), t=100)
        self.assertEqual(self.send("up", vk=ord("K"), t=130)["composition"], "1き")
        through = self.send("down", vk=0x75, t=160, mods=["shift"])
        self.assertEqual((through["eat"], through["phase"], through["commit"]),
                         (False, "composing", ""))
        committed = self.send("down", vk=ord("C"), t=190, mods=["ctrl"])
        self.assertEqual((committed["eat"], committed["phase"], committed["commit"]),
                         (False, "empty", "1き"))

    def test_mode_shortcuts_preserve_or_commit_pending_composition(self):
        self.send("down", vk=ord("K"), t=10)
        self.assertEqual(self.send("set_mode", mode="katakana")["commit"], "き")
        self.send("down", vk=ord("K"), t=100)
        self.assertEqual(self.send("up", vk=ord("K"), t=130)["composition"], "キ")
        hiragana = self.send("set_mode", mode="hiragana")
        self.assertEqual((hiragana["commit"], hiragana["composition"]), ("", "き"))
        direct = self.send("set_direct", direct=True, commit=True)
        self.assertEqual((direct["phase"], direct["commit"]), ("direct", "き"))

    def test_alt_down_flushes_pending_input_and_remains_held(self):
        self.send("down", vk=ord("K"), t=10)
        reply = self.send("down", vk=0x12, t=20)
        self.assertEqual((reply["eat"], reply["phase"], reply["commit"]), (False, "empty", "き"))
        reply = self.send("down", vk=ord("K"), t=30)
        self.assertEqual((reply["eat"], reply["timer"]), (False, None))

if __name__ == "__main__":
    unittest.main()
