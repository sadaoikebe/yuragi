"""部分確定: Ctrl+↓ commits the first clause and keeps the rest."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import ANY, Mock

from yuragi.chord.fsm import Plain
from yuragi.ime.learning import LearningStore
from yuragi.ime.server import dispatch
from yuragi.ime.session import ImeSession
from yuragi.ime.zenz import ZenzConverter
from yuragi.lattice.mozc_dict import Entry, MozcLex
from yuragi.lattice.table import load_table
from tests.real_dictionary import real_lex

VK_SPACE, VK_RETURN, VK_DOWN = 0x20, 0x0D, 0x28


class Keys:
    """A session driven through dispatch() with a running clock."""

    def __init__(self, session):
        self.s = session
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

    def tap(self, vk, mods=None, *, step=100):
        """Down and up; the reply after the down, with both events' commits."""
        reply = self.send("down", vk, mods, step=step)
        commit = self.send("up", vk, mods)["commit"]
        return {**reply, "commit": reply["commit"] + commit}

    def ctrl_down(self):
        return self.tap(VK_DOWN, ["ctrl"])

    def convert(self):
        self.send("down", VK_SPACE, step=200)
        return self.send("up", VK_SPACE)

    def plain(self, letter):
        self.send("down", ord(letter.upper()), step=200)
        return self.send("up", ord(letter.upper()))

    def chords(self, *letters):
        """One Space press with these keys typed inside it (turn 1, 2, ...)."""
        self.send("down", VK_SPACE, step=200)
        for letter in letters:
            self.send("down", ord(letter.upper()), step=20)
            self.send("up", ord(letter.upper()), step=40)
        return self.send("up", VK_SPACE, step=20)

    def idle(self):
        self.t += 300
        reply = dispatch(self.s, {"op": "timeout", "t": self.t})
        self.committed += reply["commit"]
        return reply


class PartialCommitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lex = real_lex()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "learning.jsonl"
        self.path.touch()

    def session(self, *, learning=False, table=None):
        store = LearningStore(self.path) if learning else None
        return ImeSession(_table=table or load_table(), _lex=self.lex,
                          _learning=store)

    def typed(self, reading, *, learning=False):
        """Keys over input set to these readings (every character a plain face)."""
        s = self.session(learning=learning,
                         table={"keys": {c: {"plain": c} for c in reading}})
        s.tokens = [Plain(c) for c in reading]
        s._refresh()
        return Keys(s)

    def rows(self):
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()]

    def surfaces(self, reply):
        return [seg["surface"] for seg in reply["segments"]]

    def test_commits_clause_by_clause_up_to_the_enter_result(self):
        k = self.typed("わたしはがっこうにいく")
        reply = k.convert()
        self.assertEqual(self.surfaces(reply), ["私は", "学校に", "行く"])
        enter = self.typed("わたしはがっこうにいく")
        enter.convert()
        whole = enter.tap(VK_RETURN)["commit"]

        reply = k.ctrl_down()
        self.assertEqual(reply["commit"], "私は")
        self.assertEqual(reply["composition"], "学校に行く")
        self.assertTrue(reply["converted"])
        self.assertEqual(reply["focus"], 0)
        self.assertEqual(reply["candidates"][0], "学校に")
        self.assertEqual([(g["start"], g["end"]) for g in reply["segments"]], [(0, 5), (5, 7)])
        self.assertEqual(reply["n_tokens"], 7)

        reply = k.ctrl_down()
        self.assertEqual(reply["commit"], "学校に")
        self.assertEqual(reply["composition"], "行く")
        self.assertTrue(reply["converted"])

        reply = k.ctrl_down()
        self.assertEqual(reply["commit"], "行く")
        self.assertEqual(reply["composition"], "")
        self.assertFalse(reply["converted"])
        self.assertEqual((reply["n_tokens"], reply["segments"], reply["candidates"]), (0, [], []))
        self.assertEqual(k.committed, whole)

    def test_unconverted_input_stays_unconverted(self):
        k = self.typed("わたしはがっこう")
        reply = k.ctrl_down()
        self.assertEqual(reply["commit"], "私は")
        self.assertFalse(reply["converted"])
        self.assertEqual(reply["candidates"], [])
        self.assertEqual(reply["composition"], "学校")
        self.assertEqual(reply["n_tokens"], 4)
        # Typing goes on after the rest (decoded again with the committed left).
        k.s._table["keys"]["に"] = {"plain": "に"}
        k.s._ingest([Plain("に")])
        self.assertEqual(k.s.composition, "学校に")
        self.assertEqual(k.committed, "私は")

    def test_learning_records_a_chosen_committed_clause(self):
        k = self.typed("わたしはがっこうにいく", learning=True)
        k.convert()
        k.ctrl_down()  # 私は, as shown: not learned, but the next clause's left
        reply = k.tap(ord("2"))
        chosen = reply["segments"][reply["focus"]]["surface"]
        k.ctrl_down()
        self.assertEqual([(r["reading"], r["surface"], r["prev"]) for r in self.rows()],
                         [("がっこうに", chosen, "私は")])

    def test_the_committed_head_keeps_the_press_direction(self):
        # い, then one press: w (turn 1) d (turn 2): left え・で or right が・な; る.
        k = Keys(self.session())
        k.plain("l")
        k.chords("w", "d")
        k.chords("i")
        k.idle()
        reply = k.convert()
        self.assertEqual(self.surfaces(reply), ["家", "出る"])
        reply = k.ctrl_down()
        self.assertEqual(reply["commit"], "家")
        self.assertEqual(self.surfaces(reply), ["出る"])
        self.assertEqual(reply["segments"][0]["reading"], "でる")

        model = Mock()
        model.candidate_nll.side_effect = lambda context, rows: [0.0] * len(rows)
        model.reading_nll.return_value = [0.0, 10.0]
        model.review.return_value = None
        k.s.lm = ZenzConverter(model)
        k.tap(0x1B)  # cancel conversion and decode the remaining chords again
        reply = k.convert()
        self.assertEqual(reply["segments"][0]["reading"], "でる")
        model.reading_nll.assert_called_once_with("家", ["でる", "でぐ"])
        model.review.assert_called_once_with("家", "でる", "出る", b"", ANY)

    def test_lm_only_compares_readings_that_alternate_within_one_press(self):
        words = {
            reading: [Entry(surface, reading, 1, 1, cost)]
            for reading, surface, cost in (
                ("えが", "絵画", 200), ("がえ", "替え", 300),
                ("ええ", "ええ", 100), ("がが", "画が", 100),
            )
        }
        model = Mock()
        model.candidate_nll.side_effect = lambda context, rows: [0.0] * len(rows)
        model.reading_nll.return_value = [5.0, 0.0]
        model.review.return_value = None
        lex = MozcLex(words, set(words) | {"え", "が"}, [0] * 4, 2)
        k = Keys(ImeSession(_lex=lex, _table=load_table(), lm=ZenzConverter(model)))
        k.chords("w", "w")
        reply = k.convert()
        self.assertEqual((reply["segments"][0]["reading"], reply["composition"]), ("がえ", "替え"))
        model.reading_nll.assert_called_once_with("", ["えが", "がえ"])


if __name__ == "__main__":
    unittest.main()
