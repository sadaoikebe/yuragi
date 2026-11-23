"""Bunsetsu boundaries, candidate navigation and partial commits."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import ANY, Mock

from yuragi.ime.keymap import load_keymap
from yuragi.ime.learning import LearningStore
from yuragi.ime.server import dispatch
from yuragi.ime.session import ImeSession
from yuragi.ime.zenz import ZenzConverter
from yuragi.lattice.mozc_dict import Entry, MozcLex
from yuragi.lattice.table import load_table
from tests.real_dictionary import real_lex
from tests.support import Keys, type_plain

VK_SPACE, VK_RETURN, VK_LEFT, VK_UP, VK_DOWN = 0x20, 0x0D, 0x25, 0x26, 0x28
VK_RIGHT, VK_ESC, VK_F7, VK_END, VK_HOME = 0x27, 0x1B, 0x76, 0x23, 0x24
VK_CAPITAL = 0x14


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
        s = self.session(learning=learning)
        type_plain(s, reading)
        return Keys(s)

    def rows(self):
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()]

    def surfaces(self, reply):
        return [seg["surface"] for seg in reply["segments"]]

    def macos_keymap(self):
        directory = self.path.parent
        settings = load_keymap(directory, list_presets=True)
        self.assertIn("macos", settings.presets)
        settings.use = "macos"
        settings.save(directory)
        return load_keymap(directory).compile()

    def test_macos_candidate_enter_only_advances_to_the_next_segment(self):
        k = self.typed("わたしはがっこうにいく")
        k.s.keymap = self.macos_keymap()
        converted = k.convert()
        opened = k.press(VK_DOWN)
        self.assertEqual((opened["phase"], opened["composition"]),
                         ("selecting", converted["composition"]))
        first = k.press(ord("2"))
        self.assertEqual((first["phase"], first["commit"], first["segments"][0]["surface"]),
                         ("converting", "", opened["candidates"][1]))
        opened = k.press(VK_DOWN)
        accepted = k.press(VK_RETURN)
        self.assertEqual((accepted["phase"], accepted["commit"], accepted["focus"]),
                         ("converting", "", 1))
        self.assertEqual(k.press(VK_RETURN)["commit"], opened["composition"])

    def test_macos_shrink_reconverts_and_escape_restores_all_readings(self):
        reading = "わたしはがっこうにいく"
        k = self.typed(reading)
        k.s.keymap = self.macos_keymap()
        k.convert()
        shrunk = k.press(ord("I"), ["ctrl"])
        self.assertEqual((shrunk["phase"], self.surfaces(shrunk)),
                         ("converting", ["私", "は", "学校に", "行く"]))
        ignored = k.press(ord("C"), ["ctrl"])
        self.assertEqual((ignored["eat"], ignored["commit"], ignored["composition"]),
                         (True, "", shrunk["composition"]))
        reverted = k.press(VK_ESC)
        self.assertEqual((reverted["phase"], reverted["composition"]), ("composing", reading))

    def test_macos_prediction_space_converts_but_a_number_starts_new_input(self):
        k = Keys(self.session())
        k.s.keymap = self.macos_keymap()
        for key in "JAK":  # とうき
            k.plain(key)
        prediction = k.press(ord("N"), ["ctrl"])
        self.assertEqual(prediction["phase"], "predicting")
        converted = k.convert()
        self.assertEqual((converted["phase"], converted["commit"]), ("converting", ""))
        k.press(VK_ESC)
        prediction = k.press(ord("N"), ["ctrl"])
        self.assertEqual(prediction["phase"], "predicting")
        typed = k.plain("2")
        self.assertEqual((k.committed, typed["phase"], typed["composition"]),
                         (prediction["composition"], "composing", "２"))

    def test_compounds_are_one_interval_and_can_still_be_split(self):
        for reading in ("れんらくする", "ごたんとうしゃ", "じゅうまんえん"):
            with self.subTest(reading=reading):
                reply = self.typed(reading).convert()
                self.assertEqual([seg["reading"] for seg in reply["segments"]], [reading])
        k = self.typed("れんらくする")
        k.convert()
        k.press(VK_LEFT, ["shift"])
        k.press(VK_LEFT, ["shift"])
        k.convert()
        self.assertEqual(k.ctrl_down()["commit"], "連絡")

    def test_shrink_then_expand_reconverts_before_opening_candidates(self):
        k = self.typed("わたしはがっこうにいく")
        k.convert()
        listed = k.convert()["candidates"]
        k.press(VK_UP)  # back to the first row, the window still open
        shrunk = k.press(VK_LEFT, ["shift"])
        self.assertEqual((shrunk["phase"], shrunk["candidates"]), ("resizing", []))
        self.assertEqual(self.surfaces(shrunk), ["わたし", "は", "学校に", "行く"])
        expanded = k.press(VK_DOWN)
        self.assertEqual(expanded["phase"], "resizing")
        self.assertEqual(self.surfaces(expanded), ["わたしは", "学校に", "行く"])

        converted = k.convert()
        self.assertEqual((converted["phase"], converted["candidates"]), ("converting", []))
        self.assertEqual(self.surfaces(converted), ["私は", "学校に", "行く"])
        self.assertEqual([(g["start"], g["end"]) for g in converted["segments"]],
                         [(0, 4), (4, 9), (9, 11)])
        for reply, index in ((k.convert(), 1), (k.press(VK_DOWN), 2)):
            self.assertEqual((reply["phase"], reply["cand_index"]), ("selecting", index))
            self.assertEqual(reply["segments"][0]["surface"], listed[index])

    def test_expand_displays_both_changed_readings_and_preserves_new_boundaries(self):
        k = self.typed("わたしはがっこうにいく")
        k.convert()
        expanded = k.press(VK_RIGHT, ["shift"])
        self.assertEqual(self.surfaces(expanded), ["わたしはが", "っこうに", "行く"])
        converted = k.press(VK_SPACE, ["shift"])
        self.assertEqual((converted["phase"], converted["candidates"]), ("converting", []))
        self.assertEqual([(g["start"], g["end"]) for g in converted["segments"]],
                         [(0, 5), (5, 9), (9, 11)])
        self.assertTrue(all(g["surface"] != g["reading"] for g in converted["segments"][:2]))

    def test_commit_of_raw_segments_keeps_the_reading_out_of_learning(self):
        for partial in (False, True):
            with self.subTest(partial=partial):
                k = self.typed("わたしはがっこうにいく", learning=True)
                k.convert()
                k.press(VK_LEFT, ["shift"])
                if partial:
                    reply = k.ctrl_down()
                    self.assertEqual((reply["phase"], reply["commit"], reply["composition"]),
                                     ("converting", "わたし", "は学校に行く"))
                else:
                    moved = k.press(VK_RIGHT)
                    self.assertEqual((moved["phase"], moved["focus"]), ("converting", 1))
                self.assertEqual(k.press(VK_RETURN)["phase"], "empty")
                self.assertEqual(k.committed, "わたしは学校に行く")
                self.assertEqual(self.rows(), [])

    def test_resize_exits_on_script_conversion_cancel_or_new_input(self):
        for key, phase, text, commit in (
                (VK_F7, "converting", "ワタシは学校に行く", ""),
                (VK_ESC, "converting", "私は学校に行く", ""),
                (ord("W"), "composing", "か", "わたしは学校に行く")):
            with self.subTest(key=key):
                k = self.typed("わたしはがっこうにいく")
                k.convert()
                k.press(VK_LEFT, ["shift"])
                if key == ord("W"):
                    k.s._table["keys"]["w"] = {"plain": "か"}
                    reply = k.plain("w")
                else:
                    reply = k.press(key)
                self.assertEqual((reply["phase"], reply["composition"], k.committed,
                                  reply["candidates"]), (phase, text, commit, []))

    def test_candidate_and_segment_edges_depend_on_the_phase(self):
        k = self.typed("わたしはがっこうにいく")
        original = k.convert()
        k.convert()  # the second Space opens the window
        last = k.press(VK_END)
        self.assertEqual((last["phase"], last["focus"], last["has_next_page"]),
                         ("selecting", 0, False))
        self.assertEqual(last["cand_index"], len(last["candidates"]) - 1)
        self.assertEqual(k.press(VK_HOME)["composition"], original["composition"])

        moved = k.press(VK_RIGHT)
        self.assertEqual((moved["phase"], moved["focus"], moved["candidates"]), ("converting", 1, []))
        self.assertEqual(k.press(VK_END)["focus"], 2)
        k.convert()
        blocked = k.press(VK_RIGHT, ["shift"])
        self.assertEqual((blocked["phase"], blocked["candidates"]), ("converting", []))
        k.press(VK_LEFT, ["shift"])
        resized = k.press(VK_DOWN)
        for key, mods in ((VK_RIGHT, ["shift"]), (VK_HOME, []), (VK_END, []),
                          (0x08, []), (ord("H"), ["ctrl"])):
            unchanged = k.press(key, mods)
            self.assertEqual((unchanged["phase"], unchanged["focus"], unchanged["segments"]),
                             ("resizing", 2, resized["segments"]))
        k.convert()
        self.assertEqual(k.press(VK_HOME)["focus"], 0)

        k.press(VK_LEFT, ["shift"])
        k.press(VK_RIGHT)
        k.press(VK_LEFT)
        selected = k.convert()
        self.assertEqual((selected["phase"], selected["cand_index"], selected["candidates"][0]),
                         ("selecting", 1, "私"))

    def test_fixed_width_spaces_follow_the_phase(self):
        k = self.typed("わたし")
        k.s._table["keys"]["w"] = {"plain": "か"}
        added = k.press(VK_SPACE, ["ctrl"])
        self.assertEqual((added["phase"], added["eat"], added["commit"]), ("composing", True, ""))
        k.plain("w")
        k.press(VK_RETURN)
        head, space, tail = k.committed.partition(" ")
        self.assertEqual((bool(head), space, tail.count(" "), bool(tail)), (True, " ", 0, True))

        empty = k.press(VK_SPACE, ["ctrl", "shift"])
        self.assertEqual((empty["phase"], empty["eat"], empty["commit"]), ("empty", True, "　"))

        k = self.typed("わたし")
        converted = k.convert()["composition"]
        reply = k.press(VK_SPACE, ["ctrl", "shift"])
        self.assertEqual((reply["phase"], reply["commit"], reply["composition"]),
                         ("composing", converted, "　"))

    def test_closing_the_candidate_window_keeps_the_conversion(self):
        for key, mods in ((0x08, []), (VK_ESC, []), (0x2E, []), (ord("G"), ["ctrl"]),
                          (ord("H"), ["ctrl"])):
            with self.subTest(key=key, mods=mods):
                k = self.typed("わたしはがっこうにいく")
                k.convert()
                chosen = k.convert()  # the window opens on the next row
                closed = k.press(key, mods)
                self.assertEqual((closed["phase"], closed["candidates"], closed["composition"],
                                  closed["focus"]),
                                 ("converting", [], chosen["composition"], 0))
                reverted = k.press(VK_ESC)
                self.assertEqual((reverted["phase"], reverted["focus"],
                                  self.surfaces(reverted)[1:]),
                                 ("editing", 0, self.surfaces(chosen)[1:]))

    def test_backspace_deletes_the_display_tail_then_edits_the_previous_clause(self):
        k = self.typed("わたしはがっこうにいく", learning=True)
        k.convert()
        deleted = k.press(0x08)
        self.assertEqual((deleted["phase"], deleted["focus"], self.surfaces(deleted)),
                         ("editing", 2, ["私は", "学校に", "行"]))
        self.assertEqual(deleted["commit"], "")
        again = k.press(ord("H"), ["ctrl"])
        self.assertEqual((again["phase"], again["focus"], self.surfaces(again)),
                         ("editing", 1, ["私は", "学校に"]))
        self.assertEqual(k.press(VK_RETURN)["commit"], "私は学校に")
        self.assertEqual(self.rows(), [])

    def test_deleting_a_one_character_last_clause_opens_the_previous_one(self):
        lex = MozcLex({"き": [Entry("木", "き", 1, 1, 100)], "か": [Entry("蚊", "か", 1, 1, 100)]},
                      {"き", "か"}, [0] * 4, 2)
        k = Keys(ImeSession(_table=load_table(), _lex=lex))
        k.tap("K")
        k.tap("W")
        k.convert()
        k.press(VK_LEFT, ["shift"])
        self.assertEqual(self.surfaces(k.convert()), ["木", "蚊"])
        deleted = k.press(0x08)
        self.assertEqual((deleted["phase"], deleted["composition"]), ("composing", "木"))

    def test_deleting_past_the_edge_of_an_edited_clause_commits_and_passes(self):
        k = self.typed("わたしはがっこうにいく")
        k.convert()
        self.assertEqual(k.press(VK_ESC)["focus"], 0)  # わたしは, the caret at its end
        k.press(VK_LEFT, ["ctrl"])  # to its start
        reply = k.press(0x08)
        self.assertEqual((reply["eat"], reply["phase"], reply["commit"]),
                         (False, "empty", "わたしは学校に行く"))

        k = self.typed("わたしはがっこうにいく")
        k.convert()
        k.press(VK_RIGHT)
        k.press(VK_RIGHT)
        self.assertEqual(k.press(VK_ESC)["focus"], 2)  # いく, the caret at its end
        reply = k.press(0x2E)
        self.assertEqual((reply["eat"], reply["phase"], reply["commit"]),
                         (False, "empty", "私は学校にいく"))

    def test_reverted_middle_clause_accepts_input_without_changing_its_neighbors(self):
        k = self.typed("わたしはがっこうにいく")
        k.s._table["keys"]["w"] = {"plain": "は"}
        k.convert()
        k.press(VK_RIGHT)
        reverted = k.press(VK_ESC)
        self.assertEqual((reverted["phase"], reverted["focus"], self.surfaces(reverted)),
                         ("editing", 1, ["私は", "がっこうに", "行く"]))
        typed = k.plain("w")
        self.assertEqual((typed["commit"], self.surfaces(typed)),
                         ("", ["私は", "がっこうには", "行く"]))
        self.assertEqual(typed["segments"][2]["start"], reverted["segments"][2]["start"] + 1)
        self.assertEqual(self.surfaces(k.press(0x08)), self.surfaces(reverted))
        converted = k.convert()
        self.assertEqual((converted["phase"], converted["focus"],
                          self.surfaces(converted), converted["candidates"]),
                         ("converting", 1, ["私は", "学校に", "行く"], []))

    def test_cursor_edit_resolves_the_pending_key_at_the_old_position(self):
        k = self.typed("がっこう")
        k.s.max_tokens = 5
        k.s._table["keys"].update(w={"plain": "っ"}, a={"plain": "が"})
        moved = k.press(VK_HOME)
        self.assertEqual((moved["composition"], moved["caret"]), ("がっこう", 0))
        k.press(VK_RIGHT)
        k.send("down", ord("W"))  # unresolved thumb chord at position 1
        moved = k.press(VK_LEFT, step=10)
        self.assertEqual((moved["composition"], moved["caret"], moved["commit"]), ("がっっこう", 1, ""))
        k.send("up", ord("W"))
        full = k.plain("w")
        self.assertEqual((full["composition"], full["caret"]), ("がっっこう", 1))
        self.assertEqual(k.press(0x2E)["composition"], "がっこう")
        deleted = k.press(0x08)
        self.assertEqual((deleted["composition"], deleted["caret"]), ("っこう", 0))
        typed = k.plain("a")
        self.assertEqual((typed["composition"], typed["caret"]), ("がっこう", 1))
        converted = k.convert()
        self.assertEqual((converted["phase"], converted["composition"], converted.get("caret")),
                         ("converting", "学校", None))

    def test_inserting_a_thumb_press_inside_an_earlier_press_preserves_its_direction(self):
        lex = MozcLex({"え": [Entry("絵", "え", 1, 1, -10000)]}, {"え"}, [0] * 4, 2)
        k = Keys(ImeSession(_table=load_table(), _lex=lex))
        k.chords("q", "w")  # q has only a left face, so w must be its right face (が)
        moved = k.press(VK_LEFT)
        self.assertEqual((moved["composition"], moved["caret"]), ("ぁが", 1))
        inserted = k.chords("q", "w")
        self.assertEqual((inserted["composition"], inserted["caret"]), ("ぁぁがが", 3))

    def test_word_deletion_passes_the_key_at_the_current_position(self):
        for vk in (0x08, 0x2E):
            with self.subTest(vk=vk):
                k = self.typed("がっこう")
                if vk == 0x2E:
                    end = k.press(vk, ["ctrl"])
                    self.assertEqual((end["eat"], end["phase"], end["commit"]), (False, "composing", ""))
                k.press(VK_LEFT)
                reply = k.press(vk, ["ctrl"])
                self.assertEqual((reply["eat"], reply["commit"], reply["commit_caret"]), (False, "がっこう", 3))

    def test_mixed_input_moves_to_the_next_clause_and_passes_the_outer_arrow(self):
        k = self.typed("わたしはがっこうにいく")
        k.s._table["keys"]["w"] = {"plain": "は"}
        k.convert()
        k.press(VK_RIGHT)
        k.press(VK_ESC)
        k.press(VK_LEFT)
        inserted = k.plain("w")
        self.assertEqual((self.surfaces(inserted), inserted["caret"]),
                         (["私は", "がっこうはに", "行く"], 7))
        deleted = k.press(0x2E)
        self.assertEqual((self.surfaces(deleted), deleted["caret"]),
                         (["私は", "がっこうは", "行く"], 7))
        moved = k.press(VK_RIGHT)
        self.assertEqual((moved["phase"], moved["focus"], moved["eat"], moved["commit"]),
                         ("converting", 2, True, ""))
        tail = k.press(VK_ESC)
        self.assertEqual((tail["phase"], tail["caret"]), ("editing", 9))
        clamped = k.press(VK_RIGHT, ["shift"])
        self.assertEqual((clamped["phase"], clamped["eat"], clamped["commit"]), ("editing", True, ""))
        passed = k.press(VK_RIGHT)
        self.assertEqual((passed["phase"], passed["eat"], passed["commit"]),
                         ("empty", False, "私はがっこうはいく"))

    def test_reconverting_a_trimmed_clause_preserves_the_displayed_kanji(self):
        k = self.typed("わたしはがっこうにいく")
        k.s._table["keys"]["w"] = {"plain": "は"}
        k.convert()
        k.press(0x08)  # 行く → 行
        self.assertEqual(k.plain("w")["composition"], "私は学校に行は")
        converted = k.convert()
        self.assertEqual((converted["phase"], converted["composition"], converted["commit"]),
                         ("converting", "私は学校に行は", ""))
        self.assertEqual(k.press(VK_RETURN)["commit"], "私は学校に行は")

    def test_selected_clause_revert_and_all_revert_are_distinct(self):
        k = self.typed("わたしはがっこうにいく")
        initial = k.convert()
        k.press(VK_RIGHT)
        self.assertEqual(k.convert()["phase"], "selecting")
        reverted = k.press(ord("Z"), ["ctrl"])
        self.assertEqual((reverted["phase"], reverted["focus"], reverted["candidates"],
                          self.surfaces(reverted)),
                         ("editing", 1, [], ["私は", "がっこうに", "行く"]))
        all_reverted = k.press(VK_ESC, ["shift"])
        self.assertEqual((all_reverted["phase"], all_reverted["composition"]),
                         ("composing", initial["composition"]))
        self.assertEqual(k.press(VK_ESC)["phase"], "empty")

    def test_cancel_resize_restores_boundaries_and_selected_spelling(self):
        k = self.typed("わたしはがっこうにいく")
        k.convert()
        k.press(VK_RIGHT)
        selected = k.convert()
        self.assertEqual(selected["phase"], "selecting")
        k.press(VK_LEFT, ["shift"])
        self.assertEqual(k.press(VK_LEFT, ["shift"])["phase"], "resizing")
        restored = k.press(ord("Z"), ["ctrl"])
        self.assertEqual((restored["phase"], restored["focus"], restored["candidates"],
                          restored["segments"]),
                         ("converting", selected["focus"], [], selected["segments"]))

    def test_ctrl_f10_commits_a_pending_character_before_passing_to_the_app(self):
        k = Keys(self.session())
        k.send("down", ord("K"))  # the thumb chord is unresolved
        reply = k.send("down", 0x79, ["ctrl"])
        self.assertEqual((reply["commit"], reply["eat"], reply.get("global")), ("き", False, None))
        k.send("up", ord("K"))
        self.assertEqual(k.press(0x79, ["ctrl"]).get("global"), "open_menu")

    # Shift+CapsLock with input is MS-IME's 英数 mode (ms-ime.md §1.5): the input
    # stays, later keys type half-width, and the IME is off once the input ends.
    def test_shift_capslock_types_alphanumerics_and_the_end_turns_the_ime_off(self):
        k = Keys(self.session())
        k.send("down", ord("K"))  # awaiting the chord decision
        held = k.press(VK_CAPITAL, ["shift"])
        k.send("up", ord("K"))
        self.assertEqual((held["phase"], held["eat"], held["composition"]),
                         ("composing", True, "き"))
        k.plain("a")
        spaced = k.convert()  # a half-width space, not a conversion
        self.assertEqual((spaced["phase"], spaced["composition"]), ("composing", "きa "))
        done = k.press(VK_RETURN)
        self.assertEqual((k.committed, done["eat"], done.get("global")), ("きa ", True, "ime_off"))
        self.assertIsNone(k.press(VK_RETURN).get("global"))

    def test_shift_capslock_ends_when_backspace_empties_the_input(self):
        k = self.typed("きし")
        k.press(VK_CAPITAL, ["shift"])
        self.assertEqual([k.press(0x08).get("global") for _ in range(2)], [None, "ime_off"])
        self.assertEqual(k.committed, "")

    def test_ctrl_capslock_after_shift_capslock_types_kana_again(self):
        k = Keys(self.session())
        k.plain("k")
        k.press(VK_CAPITAL, ["shift"])
        k.plain("a")
        dispatch(k.s, {"op": "set_mode", "mode": "hiragana"})  # the TIP's Ctrl+CapsLock
        k.plain("k")
        k.idle()
        done = k.press(VK_RETURN)
        self.assertEqual((k.committed, done.get("global")), ("きaき", None))

    def test_shift_capslock_keeps_the_conversion_until_a_character(self):
        k = Keys(self.session())
        for letter in "RAGL":  # こうせい
            k.plain(letter)
        k.convert()
        listed = k.convert()
        held = k.press(VK_CAPITAL, ["shift"])
        self.assertEqual((held["phase"], held["composition"]), ("selecting", listed["composition"]))
        self.assertEqual(k.convert()["cand_index"], 2)  # the candidate keys still work
        ended = k.press(ord("W"))  # MS-IME commits and drops the character
        self.assertEqual((ended["phase"], ended["composition"], ended.get("global")),
                         ("empty", "", "ime_off"))
        settled = k.idle()
        self.assertEqual((settled["phase"], settled["composition"]), ("empty", ""))
        self.assertEqual(k.committed, listed["candidates"][2])

        k = self.typed("わたしはがっこうにいく")
        k.convert()
        k.press(VK_LEFT, ["shift"])
        self.assertEqual(k.press(VK_CAPITAL, ["shift"])["phase"], "resizing")
        self.assertEqual(k.convert()["phase"], "converting")

    # Shift+↓ before conversion commits the first press: MS-IME commits the
    # first unit it typed (ms-ime.md §1.5), shown as kana, not the live conversion.
    def test_shift_down_commits_the_input_one_press_at_a_time(self):
        k = Keys(self.session())
        for letter in "kan":
            k.plain(letter)
        replies = [k.press(VK_DOWN, ["shift"]) for _ in range(3)]
        self.assertEqual([(r["commit"], r["phase"]) for r in replies],
                         [("き", "composing"), ("う", "composing"), ("め", "empty")])
        k.s.input_mode = "katakana"
        k.plain("k")
        k.plain("a")
        self.assertEqual(k.press(VK_DOWN, ["shift"])["commit"], "キ")

    def test_shift_down_keeps_the_direction_of_the_rest_of_the_press(self):
        words = {"えでる": [Entry("江出る", "えでる", 1, 1, 0)],
                 "なる": [Entry("成る", "なる", 1, 1, 0)],
                 "でる": [Entry("出る", "でる", 1, 1, 3000)]}
        lex = MozcLex(words, {w[:i] for w in words for i in range(1, len(w) + 1)}, [0] * 4, 2)
        k = Keys(ImeSession(_lex=lex, _table=load_table()))
        k.chords("w", "d")  # え・で (left) or が・な (right)
        k.chords("i")
        k.idle()
        reply = k.press(VK_DOWN, ["shift"])
        self.assertEqual((reply["commit"], reply["composition"]), ("え", "出る"))

    def test_shift_down_ends_alphanumerics(self):
        k = Keys(self.session())
        k.plain("k")
        k.press(ord("A"), ["shift"])
        self.assertEqual(k.press(VK_DOWN, ["shift"])["commit"], "き")
        k.plain("k")  # Shift+letter's 英数の続き ended: kana again
        self.assertEqual(k.s.composition[1:], "き")

        k = Keys(self.session())
        k.plain("k")
        k.press(VK_CAPITAL, ["shift"])
        k.plain("b")
        done = k.press(VK_DOWN, ["shift"])  # under Shift+CapsLock: all of it, then off
        self.assertEqual((done["commit"], done.get("global")), ("きb", "ime_off"))

    def test_commits_clause_by_clause_up_to_the_enter_result(self):
        k = self.typed("わたしはがっこうにいく")
        reply = k.convert()
        self.assertEqual(self.surfaces(reply), ["私は", "学校に", "行く"])
        enter = self.typed("わたしはがっこうにいく")
        enter.convert()
        whole = enter.press(VK_RETURN)["commit"]

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
        reply = k.press(ord("2"))
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
        k.press(0x1B)  # cancel conversion and decode the remaining chords again
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
