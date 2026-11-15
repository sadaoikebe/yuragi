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
        session = ImeSession(_table=load_table(), _lex=MozcLex({}, set(), [0] * 4, 2),
                             learning_path=None)
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
        self.assertFalse(send("toggle_direct")["direct"])
        self.assertFalse(send("down", vk=65, t=200)["pass_through"])
        send("up", vk=65, t=230)
        self.assertEqual(send("down", vk=13, t=300)["commit"], "う")
        with self.assertRaises(ValueError):
            send("set_direct", direct="false")

    def test_direct_transition_discards_pending_chord(self):
        session = ImeSession(_table=load_table(), _lex=MozcLex({}, set(), [0] * 4, 2),
                             learning_path=None)
        send = lambda msg: server.dispatch(session, msg)
        self.assertIsNotNone(send({"op": "down", "vk": 65, "t": 0})["timer"])
        reply = send({"op": "toggle_direct"})
        self.assertEqual((reply["direct"], reply["timer"], reply["commit"]), (True, None, ""))
        send({"op": "toggle_direct"})
        self.assertEqual(send({"op": "up", "vk": 65, "t": 10})["composition"], "")
        self.assertEqual(send({"op": "timeout", "t": 200})["composition"], "")


if __name__ == "__main__":
    unittest.main()
