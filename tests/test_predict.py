"""Prediction (推測変換): Tab opens the predictions and Enter commits one."""
from __future__ import annotations

from contextlib import redirect_stderr
from dataclasses import replace
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from yuragi.ime import predict as P
from yuragi.ime.personal import PersonalLexicon, add_word, remove_word
from yuragi.ime.server import dispatch
from yuragi.ime.session import ConversionRequest, ImeSession
from yuragi.lattice.mozc_dict import DEFAULT_NOUN_ID, Entry
from yuragi.lattice.table import load_table
from tests.real_dictionary import real_lex
from tests.support import type_plain

VK_TAB, VK_RETURN = 0x09, 0x0D
VK_SPACE, VK_ESCAPE = 0x20, 0x1B


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

    def session(self, *, learning=None, prediction="tab"):
        return ImeSession(_lex=self.lex, _learning=learning,
                          prediction=prediction, predict_index=self.index)


class TabGestureTest(Fixture):
    def test_tab_predicts_operator_with_internal_pos(self):
        s = self.session()
        type_plain(s, "まいな")
        reply = press(s, VK_TAB)
        self.assertTrue(reply["predicting"])
        self.assertIn("マイナス", reply["candidates"])

    def test_tab_opens_predictions_and_enter_commits(self):
        s = self.session()
        type_plain(s, "とうきょ")
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
        type_plain(s, "そらのてん")
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
        type_plain(s, "このてん")
        original = s.segments
        with patch("yuragi.ime.session.predict", return_value=[]) as predict:
            reply = press(s, VK_TAB)

        self.assertEqual([len(call.args[0]) for call in predict.call_args_list], [4, 2])
        self.assertFalse(reply["predicting"])
        self.assertIs(s.segments, original)

    def test_failure_to_decode_the_head_keeps_the_input(self):
        s = self.session()
        type_plain(s, "このてん")
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


class AutomaticPredictionTest(Fixture):
    def setUp(self):
        self.s = self.session(prediction="auto")
        self.s._table = load_table()
        self.s.predict_index.keys(self.lex)
        # Keep the actual work limit and make the wall-clock guard deterministic.
        self.enterContext(patch("yuragi.ime.predict.perf_counter", return_value=0))

    def tap(self, vk, t):
        dispatch(self.s, {"op": "down", "vk": vk, "t": t})
        return dispatch(self.s, {"op": "up", "vk": vk, "t": t + 20})

    def type_prefix(self, t=0):
        for i, key in enumerate("JAK"):  # とうき
            last = self.tap(ord(key), t + i * 50)
        return last

    def suggest(self, t):
        return dispatch(self.s, {"op": "suggest", "t": t})

    def test_prediction_off_keeps_tab_from_opening_candidates(self):
        self.s.prediction = "off"
        typed = self.type_prefix()
        reply = self.tap(VK_TAB, 200)
        self.assertEqual((reply["phase"], reply["composition"], reply["candidates"]),
                         ("composing", typed["composition"], []))

    def test_preview_keeps_preedit_until_tab_and_enter_commits_the_first_row(self):
        typed = self.type_prefix()
        due = typed["suggest_at"]
        self.assertNotIn("candidates", self.suggest(due - 1))
        preview = self.suggest(due)
        self.assertIn("東京", preview["candidates"])
        self.assertEqual(preview["cand_index"], -1)
        self.assertEqual((self.s.phase, self.s.composition), ("composing", typed["composition"]))
        opened = self.tap(VK_TAB, due + 20)
        self.assertEqual(opened["phase"], "predicting")
        self.assertEqual(opened["candidates"], preview["candidates"])
        committed = dispatch(self.s, {"op": "down", "vk": VK_RETURN, "t": due + 60})
        self.assertEqual((committed["phase"], committed["commit"]),
                         ("empty", preview["candidates"][0]))

    def test_new_input_and_space_invalidate_the_earlier_preview(self):
        old_due = self.type_prefix()["suggest_at"]
        down = dispatch(self.s, {"op": "down", "vk": ord("J"), "t": old_due - 10})
        self.assertIsNotNone(down["timer"])  # the character can still form a chord
        self.assertNotIn("candidates", self.suggest(old_due))
        up = dispatch(self.s, {"op": "up", "vk": ord("J"), "t": old_due + 10})
        self.assertGreater(up["suggest_at"], old_due)
        self.assertNotIn("candidates", self.suggest(old_due))

        dispatch(self.s, {"op": "reset"})
        due = self.type_prefix(old_due + 30)["suggest_at"]
        self.assertIn("candidates", self.suggest(due))
        converted = self.tap(VK_SPACE, due + 30)
        self.assertEqual((converted["phase"], converted["candidates"]), ("converting", []))
        self.assertNotIn("candidates", self.suggest(due + 100))

        dispatch(self.s, {"op": "reset"})
        due = self.type_prefix(due + 120)["suggest_at"]
        self.suggest(due)
        closed = self.tap(VK_ESCAPE, due + 10)
        self.assertEqual((closed["phase"], closed["composition"]), ("empty", ""))

    def test_a_changed_personal_dictionary_is_visible_to_the_next_preview(self):
        entry = Entry("登記", "とうき", DEFAULT_NOUN_ID, DEFAULT_NOUN_ID, 3000)
        self.s._lex = replace(self.lex, by_reading={"とうき": [entry]}, prefixes={"と", "とう", "とうき"})
        self.s.predict_index = P.ReadingIndex()
        self.s.predict_index.keys(self.s._lex)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "personal.jsonl"
            self.s.personal = PersonalLexicon(path)
            add_word(path, "とうきゆらぎ", "登記ゆらぎ")
            due = self.type_prefix()["suggest_at"]
            self.assertEqual(self.suggest(due)["candidates"], ["登記ゆらぎ"])
            remove_word(path, "とうきゆらぎ", "登記ゆらぎ")
            dispatch(self.s, {"op": "reset"})
            due = self.type_prefix(due + 100)["suggest_at"]
            self.assertNotIn("candidates", self.suggest(due))


if __name__ == "__main__":
    unittest.main()
