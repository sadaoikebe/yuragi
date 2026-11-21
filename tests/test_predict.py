"""Prediction (推測変換): Tab opens the predictions and Enter commits one."""
from __future__ import annotations

from contextlib import redirect_stderr
from io import StringIO
import unittest
from unittest.mock import patch

from yuragi.chord.fsm import Plain
from yuragi.ime import predict as P
from yuragi.ime.server import dispatch
from yuragi.ime.session import ConversionRequest, ImeSession
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
        return ImeSession(_lex=self.lex, _learning=learning,
                          prediction=prediction, predict_index=self.index)


class TabGestureTest(Fixture):
    def test_tab_predicts_operator_with_internal_pos(self):
        s = self.session()
        type_reading(s, "まいな")
        reply = press(s, VK_TAB)
        self.assertTrue(reply["predicting"])
        self.assertIn("マイナス", reply["candidates"])

    def test_tab_opens_predictions_and_enter_commits(self):
        s = self.session()
        type_reading(s, "とうきょ")
        reply = press(s, VK_TAB)
        self.assertTrue(reply["predicting"])
        self.assertTrue(reply["converted"])
        self.assertIn("東京都", reply["candidates"])
        self.assertEqual(reply["composition"], reply["candidates"][0])
        second = press(s, VK_TAB)  # the next prediction
        self.assertEqual(second["composition"], reply["candidates"][1])
        commit = press(s, VK_RETURN)
        self.assertEqual(commit["commit"], reply["candidates"][1])
        self.assertFalse(commit["predicting"])

    def test_tab_can_start_a_prediction_inside_a_clause(self):
        s = self.session()
        type_reading(s, "そらのてん")
        tokens = s.tokens
        self.assertEqual([(segment.start, segment.end) for segment in s.segments], [(0, 5)])

        reply = press(s, VK_TAB)

        self.assertTrue(reply["predicting"])
        self.assertIs(s.tokens, tokens)
        self.assertEqual([(segment.start, segment.end) for segment in s.segments], [(0, 2), (2, 5)])
        self.assertEqual(s.segments[0].selected.reading, "そら")
        self.assertEqual(press(s, VK_RETURN)["commit"], reply["composition"])

    def test_no_prediction_keeps_the_original_clauses(self):
        s = self.session()
        type_reading(s, "このてん")
        original = s.segments
        with patch("yuragi.ime.session.predict", return_value=[]) as predict:
            reply = press(s, VK_TAB)

        self.assertEqual([len(call.args[0]) for call in predict.call_args_list], [4, 2])
        self.assertFalse(reply["predicting"])
        self.assertIs(s.segments, original)

    def test_failure_to_decode_the_head_keeps_the_input(self):
        s = self.session()
        type_reading(s, "このてん")
        tokens = list(s.tokens)
        original = s.segments
        composition = s.composition
        errors = StringIO()
        with (patch("yuragi.ime.session.predict", return_value=[]),
              patch.object(ConversionRequest, "decode", side_effect=RuntimeError),
              redirect_stderr(errors)):
            reply = press(s, VK_TAB)

        self.assertFalse(reply["predicting"])
        self.assertEqual(reply["composition"], composition)
        self.assertEqual(s.tokens, tokens)
        self.assertIs(s.segments, original)
        self.assertIn("Prediction failed (RuntimeError)", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
