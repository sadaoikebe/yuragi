"""Prediction (推測変換): Tab opens the predictions and Enter commits one."""
from __future__ import annotations

import unittest

from yuragi.chord.fsm import Plain
from yuragi.ime import predict as P
from yuragi.ime.server import dispatch
from yuragi.ime.session import ImeSession
from tests.real_dictionary import real_lex

VK_TAB, VK_RETURN = 0x09, 0x0D


def type_reading(s, reading):
    # Unambiguous faces, no FSM.
    s._table = {"keys": {c: {"plain": c} for c in reading}}
    s.tokens = [Plain(c) for c in reading]
    s._refresh()


def press(s, vk, mods=None):
    msg = {"op": "down", "vk": vk}
    if mods:
        msg["mods"] = mods
    reply = dispatch(s, msg)
    dispatch(s, {**msg, "op": "up"})
    return reply


class Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lex = real_lex()
        cls.index = P.ReadingIndex()

    def session(self, *, learning=None, prediction=P.DEFAULT_MODE):
        return ImeSession(_lex=self.lex, learning_path=None, _learning=learning,
                          prediction=prediction, predict_index=self.index)


class TabGestureTest(Fixture):
    def test_tab_opens_predictions_and_enter_commits(self):
        s = self.session()
        type_reading(s, "とうきょ")
        before = s.composition
        reply = press(s, VK_TAB)
        self.assertTrue(reply["predicting"])
        self.assertTrue(reply["converted"])
        self.assertIn("東京都", reply["candidates"])
        self.assertEqual(reply["composition"], reply["candidates"][0])
        second = press(s, VK_TAB)  # the next prediction
        self.assertEqual(second["composition"], reply["candidates"][1])
        self.assertNotEqual(before, "")
        commit = press(s, VK_RETURN)
        self.assertEqual(commit["commit"], reply["candidates"][1])
        self.assertFalse(commit["predicting"])


if __name__ == "__main__":
    unittest.main()
