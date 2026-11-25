"""JIS 106 thumb keys through the session (docs/JIS.md §5): the evidence chooses the face,
evidence that arrives late changes the input, and a lone 無変換/変換 runs its own function.

w is か; with the left thumb え, with the right が. q has a left face only (ぁ).
"""
import unittest

from yuragi.chord.fsm import AmbShift
from yuragi.chord.keys import (
    KEYBOARDS, SHIFT, SPACE, VK_CONVERT, VK_ESCAPE, VK_NONCONVERT, VK_RETURN, VK_SPACE, Chord,
)
from yuragi.ime.keymap import Keymap
from yuragi.ime.session import ImeSession
from yuragi.lattice.mozc_dict import Entry, MozcLex
from yuragi.lattice.table import load_table

from tests.support import Keys

JIS = KEYBOARDS["jis106"]
MUHENKAN, HENKAN, ENTER = Chord("無変換"), Chord("変換"), Chord("Enter")
BINDINGS = {
    ("empty", SPACE): "insert_space",
    ("empty", MUHENKAN): "cycle_kana_mode",
    ("composing", SPACE): "convert",
    ("composing", HENKAN): "convert",
    ("composing", MUHENKAN): "cycle_kana_script",
    ("composing", ENTER): "commit",
    ("converting", SPACE): "next_candidate",
    ("converting", HENKAN): "next_candidate",
    ("converting", ENTER): "commit",
}
# 絵 is much cheaper than 蛾: left to itself the conversion reads w with a thumb as え.
LEX = MozcLex({"え": [Entry("絵", "え", 1, 1, 100)], "が": [Entry("蛾", "が", 1, 1, 3000)]},
              {"え", "が"}, [0] * 4, 2)


class Typist(Keys):
    def __init__(self):
        super().__init__(ImeSession(_table=load_table(JIS.kana), _lex=LEX, keyboard=JIS,
                                    keymap=Keymap(BINDINGS)))

    def play(self, spec):
        """Spec "w+0 O+12 H+20 w-70": + is down, - is up, at ms from now; O N H are Space, 無変換, 変換."""
        vks = {"O": VK_SPACE, "N": VK_NONCONVERT, "H": VK_CONVERT}
        base, reply = self.t + 1000, None
        for item in spec.split():
            down = "+" in item
            key, at = item.split("+" if down else "-")
            self.t = base + int(at)
            reply = self.send("down" if down else "up", vks.get(key, ord(key.upper())), step=0)
        return reply

    def faces(self):
        """Per chord in the input, the faces left to the conversion."""
        return ["".join(sorted(token["faces"].values())) for token in self.s._lattice()
                if token["kind"] in ("amb", "shift")]

    def reading(self):
        return "".join(segment.selected.reading for segment in self.s.segments)


class ThumbEvidenceTest(unittest.TestCase):
    def test_the_thumb_key_chooses_the_face(self):
        for spec, faces in (("w+0 O+10 w-60 O-70", ["えが"]),
                            ("w+0 N+10 w-60 N-70", ["え"]),
                            ("w+0 H+10 w-60 H-70", ["が"]),
                            ("w+0 O+10 H+18 w-60 O-70 H-75", ["が"]),
                            ("N+0 w+10 w-60 N-70", ["え"])):
            with self.subTest(spec):
                k = Typist()
                k.play(spec)
                self.assertEqual(k.faces(), faces)

    def test_a_face_that_is_empty_types_nothing(self):
        k = Typist()
        self.assertEqual(k.play("q+0 N+10 q-60 N-70")["composition"], "ぁ")
        k = Typist()
        reply = k.play("q+0 H+10 q-60 H-70")
        self.assertEqual((reply["composition"], reply["phase"]), ("", "empty"))

    def test_the_other_thumb_was_busy(self):
        k = Typist()
        k.play("N+0 w+10 w-60 w+100 H+110 N-120 w-170 H-200")
        self.assertEqual(k.faces(), ["え", "が"])
        # 変換 still held from a lone press: the next stroke on Space is the left thumb's.
        k = Typist()
        k.play("H+0 w+200 O+210 w-260 O-270 H-300")
        self.assertEqual(k.faces(), ["え"])

    def test_one_settled_chord_settles_its_press(self):
        """Space stays down for three chords; the second also touches 無変換."""
        k = Typist()
        k.play("O+0 w+10 w+90 N+95 w+170 w-230 N-250 O-300")
        self.assertEqual(k.faces(), ["えが", "え", "が"])
        self.assertEqual(k.reading(), "がえが")

    def test_a_chord_with_no_face_still_settles_its_press(self):
        """q with the right thumb types nothing, and the next chord under the same Space is the left's."""
        k = Typist()
        k.play("O+0 H+5 q+10 q-60 H-65 w+100 w-160 O-200")
        self.assertEqual((k.faces(), k.reading()), (["え"], "え"))
        k = Typist()
        k.play("O+0 N+5 q+10 q-60 N-65 w+100 w-160 O-200")
        self.assertEqual(k.reading(), "ぁが")

    def test_evidence_against_a_carried_direction_wins(self):
        k = Typist()
        k.play("O+0 w+10 w-60 w+100 w-160 O-200")
        k.s._carry[k.s.tokens[0].press] = frozenset(("left",))
        self.assertEqual(k.reading(), "えが")
        first = k.s.tokens[0]
        k.s.tokens[0] = AmbShift("w", first.press, 1, struck=("henkan",))
        self.assertEqual(k.faces(), ["が", "えが"])
        self.assertEqual(k.s._carry, {})


class LateEvidenceTest(unittest.TestCase):
    def test_the_second_key_of_the_stroke_arrives_after_the_chord(self):
        """Space 4 ms after w, w up at 14: the chord is shown. 変換 at 22 is the same stroke's."""
        k = Typist()
        base = k.t + 1000
        for op, vk, at in (("down", ord("W"), 0), ("down", VK_SPACE, 4), ("up", ord("W"), 14)):
            k.t = base + at
            shown = k.send(op, vk, step=0)
        self.assertEqual((shown["composition"], k.faces()), ("絵", ["えが"]))
        k.t = base + 22
        joined = k.send("down", VK_CONVERT, step=0)
        self.assertEqual((joined["composition"], k.faces(), joined["phase"]), ("蛾", ["が"], "composing"))
        k.t = base + 80
        k.send("up", VK_SPACE, step=0)
        self.assertEqual(k.send("up", VK_CONVERT, step=5)["composition"], "蛾")
        self.assertEqual(len(k.s.tokens), 1)

    def test_join_that_leaves_no_face_removes_the_chord(self):
        k = Typist()
        k.play("w+0 w-50")
        base = k.t + 1000
        for op, vk, at in (("down", ord("Q"), 0), ("down", VK_SPACE, 4), ("up", ord("Q"), 14)):
            k.t = base + at
            k.send(op, vk, step=0)
        self.assertEqual(k.reading(), "かぁ")
        k.t = base + 22
        self.assertEqual(k.send("down", VK_CONVERT, step=0)["composition"], "か")
        self.assertEqual(len(k.s.tokens), 1)

    def test_join_for_a_chord_already_committed_is_dropped(self):
        k = Typist()
        base = k.t + 1000
        for op, vk, at in (("down", ord("W"), 0), ("down", VK_SPACE, 4), ("up", ord("W"), 14),
                           ("down", VK_RETURN, 16)):
            k.t = base + at
            reply = k.send(op, vk, step=0)
        self.assertEqual(reply["commit"], "絵")
        k.t = base + 22
        reply = k.send("down", VK_CONVERT, step=0)
        self.assertEqual((reply["composition"], reply["commit"]), ("", ""))

    def test_late_evidence_inside_a_clause_being_edited(self):
        lex = MozcLex({"き": [Entry("木", "き", 1, 1, 100)], "か": [Entry("蚊", "か", 1, 1, 100)]},
                      {"き", "か"}, [0] * 4, 2)
        k = Typist()
        k.s._lex = lex
        k.s.keymap = Keymap({**BINDINGS, ("converting", Chord("Left", SHIFT)): "segment_shrink",
                             ("resizing", HENKAN): "convert_segment",
                             ("converting", Chord("Esc")): "segment_revert"})
        k.play("k+0 k-50 w+100 w-150")
        k.play("H+0 H-50")
        k.press(0x25, ["shift"])  # き | か
        k.play("H+0 H-50")
        self.assertEqual(k.press(VK_ESCAPE)["phase"], "editing")  # き, the caret at its end

        def late(letter):
            base, replies = k.t + 1000, []
            for op, vk, at in (("down", ord(letter), 0), ("down", VK_SPACE, 4), ("up", ord(letter), 14),
                               ("down", VK_CONVERT, 22), ("up", VK_SPACE, 80), ("up", VK_CONVERT, 85)):
                k.t = base + at
                replies.append(k.send(op, vk, step=0))
            return [(r["composition"], r["caret"]) for r in replies[2:4]]

        self.assertEqual(late("W"), [("きえ蚊", 2), ("きが蚊", 2)])
        self.assertEqual(late("Q"), [("きがぁ蚊", 3), ("きが蚊", 2)])
        self.assertEqual((k.s.phase, len(k.s.tokens)), ("editing", 3))

    def test_a_lone_key_over_the_chord_settles_it_before_it_converts(self):
        """The left thumb's Space chord; before it is up, the right thumb presses 変換 alone."""
        k = Typist()
        reply = k.play("O+0 w+10 w-70 H+130 O-150 H-190")
        self.assertEqual((reply["phase"], reply["composition"], k.reading()), ("converting", "絵", "え"))
        # The other way round, 蛾 is read though it costs more.
        k = Typist()
        k.s.keymap = Keymap({**BINDINGS, ("composing", MUHENKAN): "convert"})
        reply = k.play("O+0 w+10 w-70 N+130 O-150 N-190")
        self.assertEqual((reply["phase"], reply["composition"]), ("converting", "蛾"))


class LoneThumbKeyTest(unittest.TestCase):
    def test_each_key_runs_its_own_function(self):
        k = Typist()
        k.play("w+0 w-50")
        self.assertEqual(k.play("N+0 N-50")["composition"], "カ")  # 無変換: the script of the input
        k = Typist()
        k.play("w+0 w-50")
        reply = k.play("H+0 H-50")
        self.assertEqual((reply["phase"], reply.get("global")), ("converting", None))
        self.assertEqual(k.play("H+0 H-50")["phase"], "selecting")
        k = Typist()
        k.play("N+0 N-50")
        self.assertEqual(k.s.input_mode, "katakana")

    def test_the_function_runs_at_the_release_or_at_80_ms(self):
        k = Typist()
        k.play("w+0 w-50")
        self.assertEqual(k.play("H+0")["phase"], "composing")
        k.t += 80
        self.assertEqual(k.send("timeout", step=0)["phase"], "converting")
        self.assertEqual(k.send("up", VK_CONVERT)["phase"], "converting")

    def test_a_key_with_no_command_stays_eaten(self):
        """変換 with no input has no command here: like Space, the lone key does nothing more."""
        k = Typist()
        self.assertTrue(k.send("down", VK_CONVERT)["eat"])
        reply = k.send("up", VK_CONVERT)
        self.assertEqual((reply["phase"], reply.get("global")), ("empty", None))
        k.play("w+0 w-50")
        self.assertEqual(k.s.composition, "か")

    def test_a_tip_command_comes_with_the_reply_that_finds_the_key_alone(self):
        """KEYBIND.md §7.6: at the release, at the deadline, or at the down of a key that ends it."""
        def typist():
            k = Typist()
            k.s.keymap = Keymap({**BINDINGS, ("empty", MUHENKAN): "ime_toggle"})
            return k

        k = typist()
        self.assertNotIn("global", k.send("down", VK_NONCONVERT))
        self.assertEqual(k.send("up", VK_NONCONVERT)["global"], "ime_toggle")

        k = typist()
        k.send("down", VK_NONCONVERT)
        k.t += 80
        self.assertEqual(k.send("timeout", step=0)["global"], "ime_toggle")
        self.assertNotIn("global", k.send("up", VK_NONCONVERT))

        # Enter within the window ends it: the TIP runs the command, then decides Enter again.
        k = typist()
        k.send("down", VK_NONCONVERT)
        reply = k.send("down", VK_RETURN, step=20)
        self.assertEqual((reply["eat"], reply["global"], reply["again"]), (False, "ime_toggle", True))
        again = k.send("down", VK_RETURN, step=0)
        self.assertNotIn("again", again)
        self.assertNotIn("global", again)

        # A key past the deadline the TIP has not reported yet: the same.
        k = typist()
        k.send("down", VK_NONCONVERT)
        reply = k.send("down", ord("W"), step=200)
        self.assertEqual((reply["eat"], reply["global"], reply["again"]), (False, "ime_toggle", True))
        self.assertEqual(k.s.fsm.state, "S1")

        # The same through the global column (MS-IME's key assignment): with no input only.
        k = Typist()
        k.s.keymap = Keymap({**BINDINGS, ("global", HENKAN): "ime_on"})
        self.assertEqual(k.play("H+0 H-50")["global"], "ime_on")
        k.play("w+0 w-50")
        reply = k.play("H+0 H-50")
        self.assertEqual((reply["phase"], reply.get("global")), ("converting", None))

        # A character within the window makes a chord: no command.
        k = typist()
        k.send("down", VK_NONCONVERT)
        reply = k.send("down", ord("W"), step=20)
        self.assertEqual((reply["eat"], reply.get("global"), reply.get("again")), (True, None, None))

    def test_with_a_modifier_it_is_a_command_key(self):
        k = Typist()
        k.s.keymap = Keymap({**BINDINGS, ("composing", Chord("変換", SHIFT)): "commit"})
        self.assertEqual(JIS.chord(VK_CONVERT, SHIFT), Chord.parse("Shift+変換"))
        k.play("w+0 w-50")
        reply = k.send("down", VK_CONVERT, ["shift"])
        self.assertEqual((reply["commit"], k.s.fsm.state, k.s.fsm.held), ("か", "S1", {}))

    def test_while_keys_type_alphanumerics_it_runs_at_its_down(self):
        k = Typist()
        k.shift("A")
        self.assertEqual(k.send("down", VK_CONVERT)["phase"], "converting")
        self.assertEqual((k.s.fsm.state, k.s.fsm.held), ("S1", {}))

    def test_two_thumb_keys_without_a_character(self):
        k = Typist()
        k.play("w+0 w-50")
        reply = k.play("N+0 H+50 N-60 H-90")
        self.assertEqual((reply["phase"], reply["composition"]), ("composing", "カ"))

    def test_focus_loss_forgets_the_held_keys(self):
        k = Typist()
        k.send("down", VK_CONVERT)
        k.send("reset")
        self.assertEqual(k.s.fsm.held, {})
        k.send("up", VK_CONVERT)
        k.play("w+0 O+10 w-60 O-70")
        self.assertEqual(k.faces(), ["えが"])


if __name__ == "__main__":
    unittest.main()
