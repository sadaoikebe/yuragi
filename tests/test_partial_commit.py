"""Bunsetsu boundaries, candidate navigation and partial commits."""
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

VK_SPACE, VK_RETURN, VK_LEFT, VK_UP, VK_DOWN = 0x20, 0x0D, 0x25, 0x26, 0x28
VK_RIGHT, VK_ESC, VK_F7, VK_END, VK_HOME = 0x27, 0x1B, 0x76, 0x23, 0x24
VK_CAPITAL = 0x14


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

    def test_compounds_are_one_interval_and_can_still_be_split(self):
        for reading in ("れんらくする", "ごたんとうしゃ", "じゅうまんえん"):
            with self.subTest(reading=reading):
                reply = self.typed(reading).convert()
                self.assertEqual([seg["reading"] for seg in reply["segments"]], [reading])
        k = self.typed("れんらくする")
        k.convert()
        k.tap(VK_LEFT, ["shift"])
        k.tap(VK_LEFT, ["shift"])
        k.convert()
        self.assertEqual(k.ctrl_down()["commit"], "連絡")

    def test_shrink_then_expand_reconverts_before_opening_candidates(self):
        k = self.typed("わたしはがっこうにいく")
        k.convert()
        listed = k.convert()["candidates"]
        k.tap(VK_UP)  # back to the first row, the window still open
        shrunk = k.tap(VK_LEFT, ["shift"])
        self.assertEqual((shrunk["phase"], shrunk["candidates"]), ("resizing", []))
        self.assertEqual(self.surfaces(shrunk), ["わたし", "は", "学校に", "行く"])
        expanded = k.tap(VK_DOWN)
        self.assertEqual(expanded["phase"], "resizing")
        self.assertEqual(self.surfaces(expanded), ["わたしは", "学校に", "行く"])

        converted = k.convert()
        self.assertEqual((converted["phase"], converted["candidates"]), ("converting", []))
        self.assertEqual(self.surfaces(converted), ["私は", "学校に", "行く"])
        self.assertEqual([(g["start"], g["end"]) for g in converted["segments"]],
                         [(0, 4), (4, 9), (9, 11)])
        for reply, index in ((k.convert(), 1), (k.tap(VK_DOWN), 2)):
            self.assertEqual((reply["phase"], reply["cand_index"]), ("selecting", index))
            self.assertEqual(reply["segments"][0]["surface"], listed[index])

    def test_expand_displays_both_changed_readings_and_preserves_new_boundaries(self):
        k = self.typed("わたしはがっこうにいく")
        k.convert()
        expanded = k.tap(VK_RIGHT, ["shift"])
        self.assertEqual(self.surfaces(expanded), ["わたしはが", "っこうに", "行く"])
        converted = k.tap(VK_SPACE, ["shift"])
        self.assertEqual((converted["phase"], converted["candidates"]), ("converting", []))
        self.assertEqual([(g["start"], g["end"]) for g in converted["segments"]],
                         [(0, 5), (5, 9), (9, 11)])
        self.assertTrue(all(g["surface"] != g["reading"] for g in converted["segments"][:2]))

    def test_commit_of_raw_segments_keeps_the_reading_out_of_learning(self):
        for partial in (False, True):
            with self.subTest(partial=partial):
                k = self.typed("わたしはがっこうにいく", learning=True)
                k.convert()
                k.tap(VK_LEFT, ["shift"])
                if partial:
                    reply = k.ctrl_down()
                    self.assertEqual((reply["phase"], reply["commit"], reply["composition"]),
                                     ("converting", "わたし", "は学校に行く"))
                else:
                    moved = k.tap(VK_RIGHT)
                    self.assertEqual((moved["phase"], moved["focus"]), ("converting", 1))
                self.assertEqual(k.tap(VK_RETURN)["phase"], "empty")
                self.assertEqual(k.committed, "わたしは学校に行く")
                self.assertEqual(self.rows(), [])

    def test_resize_exits_on_script_conversion_cancel_or_new_input(self):
        for key, phase, text, commit in (
                (VK_F7, "converting", "ワタシは学校に行く", ""),
                (VK_ESC, "composing", "私は学校に行く", ""),
                (ord("W"), "composing", "か", "わたしは学校に行く")):
            with self.subTest(key=key):
                k = self.typed("わたしはがっこうにいく")
                k.convert()
                k.tap(VK_LEFT, ["shift"])
                if key == ord("W"):
                    k.s._table["keys"]["w"] = {"plain": "か"}
                    reply = k.plain("w")
                else:
                    reply = k.tap(key)
                self.assertEqual((reply["phase"], reply["composition"], k.committed,
                                  reply["candidates"]), (phase, text, commit, []))

    def test_candidate_and_segment_edges_depend_on_the_phase(self):
        k = self.typed("わたしはがっこうにいく")
        original = k.convert()
        k.convert()  # the second Space opens the window
        last = k.tap(VK_END)
        self.assertEqual((last["phase"], last["focus"], last["has_next_page"]),
                         ("selecting", 0, False))
        self.assertEqual(last["cand_index"], len(last["candidates"]) - 1)
        self.assertEqual(k.tap(VK_HOME)["composition"], original["composition"])

        moved = k.tap(VK_RIGHT)
        self.assertEqual((moved["phase"], moved["focus"], moved["candidates"]), ("converting", 1, []))
        self.assertEqual(k.tap(VK_END)["focus"], 2)
        k.convert()
        blocked = k.tap(VK_RIGHT, ["shift"])
        self.assertEqual((blocked["phase"], blocked["candidates"]), ("converting", []))
        k.tap(VK_LEFT, ["shift"])
        resized = k.tap(VK_DOWN)
        for key, mods in ((VK_RIGHT, ["shift"]), (VK_HOME, []), (VK_END, []),
                          (0x08, []), (ord("H"), ["ctrl"])):
            unchanged = k.tap(key, mods)
            self.assertEqual((unchanged["phase"], unchanged["focus"], unchanged["segments"]),
                             ("resizing", 2, resized["segments"]))
        k.convert()
        self.assertEqual(k.tap(VK_HOME)["focus"], 0)

        k.tap(VK_LEFT, ["shift"])
        k.tap(VK_RIGHT)
        k.tap(VK_LEFT)
        selected = k.convert()
        self.assertEqual((selected["phase"], selected["cand_index"], selected["candidates"][0]),
                         ("selecting", 1, "私"))

    def test_fixed_width_spaces_follow_the_phase(self):
        k = self.typed("わたし")
        k.s._table["keys"]["w"] = {"plain": "か"}
        added = k.tap(VK_SPACE, ["ctrl"])
        self.assertEqual((added["phase"], added["eat"], added["commit"]), ("composing", True, ""))
        k.plain("w")
        k.tap(VK_RETURN)
        head, space, tail = k.committed.partition(" ")
        self.assertEqual((bool(head), space, tail.count(" "), bool(tail)), (True, " ", 0, True))

        empty = k.tap(VK_SPACE, ["ctrl", "shift"])
        self.assertEqual((empty["phase"], empty["eat"], empty["commit"]), ("empty", True, "　"))

        k = self.typed("わたし")
        converted = k.convert()["composition"]
        reply = k.tap(VK_SPACE, ["ctrl", "shift"])
        self.assertEqual((reply["phase"], reply["commit"], reply["composition"]),
                         ("composing", converted, "　"))

    def test_closing_the_candidate_window_keeps_the_conversion(self):
        for key, mods in ((0x08, []), (VK_ESC, []), (0x2E, []), (ord("G"), ["ctrl"]),
                          (ord("H"), ["ctrl"])):
            with self.subTest(key=key, mods=mods):
                k = self.typed("わたしはがっこうにいく")
                k.convert()
                chosen = k.convert()  # the window opens on the next row
                closed = k.tap(key, mods)
                self.assertEqual((closed["phase"], closed["candidates"], closed["composition"],
                                  closed["focus"]),
                                 ("converting", [], chosen["composition"], 0))
                self.assertEqual(k.tap(VK_ESC)["phase"], "composing")

    def test_ctrl_f7_opens_the_word_register_only_without_input(self):
        k = self.typed("")
        self.assertEqual(k.tap(0x76, ["ctrl"]).get("global"), "open_word_register")
        k = self.typed("わたし")
        self.assertIsNone(k.tap(0x76, ["ctrl"]).get("global"))

    def test_first_space_converts_and_the_second_opens_the_window(self):
        k = self.typed("わたしはがっこうにいく")
        first = k.convert()
        self.assertEqual((first["phase"], first["candidates"]), ("converting", []))
        second = k.convert()
        self.assertEqual((second["phase"], second["cand_index"]), ("selecting", 1))
        self.assertEqual(second["segments"][0]["surface"], second["candidates"][1])

    # Shift+CapsLock with input is MS-IME's 英数 mode (ms-ime.md §1.5): the input
    # stays, later keys type half-width, and the IME is off once the input ends.
    def test_shift_capslock_types_alphanumerics_and_the_end_turns_the_ime_off(self):
        k = Keys(self.session())
        k.send("down", ord("K"))  # awaiting the chord decision
        held = k.tap(VK_CAPITAL, ["shift"])
        k.send("up", ord("K"))
        self.assertEqual((held["phase"], held["eat"], held["composition"]),
                         ("composing", True, "き"))
        k.plain("a")
        spaced = k.convert()  # a half-width space, not a conversion
        self.assertEqual((spaced["phase"], spaced["composition"]), ("composing", "きa "))
        done = k.tap(VK_RETURN)
        self.assertEqual((k.committed, done["eat"], done.get("global")), ("きa ", True, "ime_off"))
        self.assertIsNone(k.tap(VK_RETURN).get("global"))

    def test_shift_capslock_ends_when_backspace_empties_the_input(self):
        k = self.typed("きし")
        k.tap(VK_CAPITAL, ["shift"])
        self.assertEqual([k.tap(0x08).get("global") for _ in range(2)], [None, "ime_off"])
        self.assertEqual(k.committed, "")

    def test_ctrl_capslock_after_shift_capslock_types_kana_again(self):
        k = Keys(self.session())
        k.plain("k")
        k.tap(VK_CAPITAL, ["shift"])
        k.plain("a")
        dispatch(k.s, {"op": "set_mode", "mode": "hiragana"})  # the TIP's Ctrl+CapsLock
        k.plain("k")
        k.idle()
        done = k.tap(VK_RETURN)
        self.assertEqual((k.committed, done.get("global")), ("きaき", None))

    def test_shift_capslock_keeps_the_conversion_until_a_character(self):
        k = self.typed("わたしはがっこうにいく")
        k.convert()
        listed = k.convert()
        held = k.tap(VK_CAPITAL, ["shift"])
        self.assertEqual((held["phase"], held["composition"]), ("selecting", listed["composition"]))
        self.assertEqual(k.convert()["cand_index"], 2)  # the candidate keys still work
        ended = k.tap(ord("W"))  # MS-IME commits and drops the character
        self.assertEqual((ended["phase"], ended["composition"], ended.get("global")),
                         ("empty", "", "ime_off"))
        self.assertEqual(k.committed, held["composition"].replace(
            listed["segments"][0]["surface"], listed["candidates"][2], 1))

        k = self.typed("わたしはがっこうにいく")
        k.convert()
        k.tap(VK_LEFT, ["shift"])
        self.assertEqual(k.tap(VK_CAPITAL, ["shift"])["phase"], "resizing")
        self.assertEqual(k.convert()["phase"], "converting")

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
        self.assertEqual(reply["candidates"], [])
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

    def test_ctrl_down_keeps_unconverted_input(self):
        k = self.typed("わたしはがっこう")
        composition = k.s.composition
        reply = k.ctrl_down()
        self.assertEqual((reply["eat"], reply["commit"], reply["phase"]), (True, "", "composing"))
        self.assertEqual(reply["composition"], composition)

    def test_learning_records_a_chosen_word_in_a_partially_committed_clause(self):
        k = self.typed("わたしはがっこうにいく", learning=True)
        k.convert()
        k.ctrl_down()  # 私は, as shown: not learned, but the next clause's left
        k.convert()
        reply = k.tap(ord("2"))
        chosen = reply["segments"][reply["focus"]]["surface"]
        k.ctrl_down()
        self.assertEqual([(r["reading"], r["surface"], r["prev"]) for r in self.rows()],
                         [("がっこう", chosen.removesuffix("に"), "私")])

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
