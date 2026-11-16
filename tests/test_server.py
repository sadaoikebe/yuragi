"""Input-mode switching through the same dispatch() the engine uses: IME on/off
passes keys through, and switching mid-chord leaves nothing behind."""
from __future__ import annotations

import unittest

from yuragi.ime import server
from yuragi.ime.session import ImeSession
from yuragi.lattice.mozc_dict import MozcLex
from yuragi.lattice.table import load_table


class ServerTest(unittest.TestCase):
    def test_direct_dispatch_and_reset(self):
        session = ImeSession(_table=load_table(), _lex=MozcLex({}, set(), [0] * 4, 2))
        def send(op, **kwargs):
            return server.dispatch(session, {"op": op, **kwargs})

        send("down", vk=65, t=0, mods=["shift"])
        self.assertEqual(session.composition, "A")
        reply = send("set_direct", direct=False)
        self.assertEqual(reply["composition"], "A")
        reply = send("set_direct", direct=True)
        self.assertEqual((reply["direct"], reply["composition"], reply["commit"]),
                         (True, "", ""))
        for op in ("down", "up"):
            reply = send(op, vk=65, t=20)
            self.assertTrue(reply["pass_through"])
            self.assertEqual((reply["composition"], reply["commit"], reply["timer"]),
                             ("", "", None))
        self.assertTrue(send("reset")["direct"])
        self.assertEqual(send("timeout", t=100)["composition"], "")
        self.assertFalse(send("set_direct", direct=False)["direct"])
        self.assertFalse(send("down", vk=65, t=200)["pass_through"])
        send("up", vk=65, t=230)
        self.assertEqual(send("down", vk=13, t=300)["commit"], "う")

if __name__ == "__main__":
    unittest.main()
