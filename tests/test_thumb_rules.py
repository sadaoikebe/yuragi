"""The two rules of one spacebar: the chord judgment (fsm.py) and the
alternating thumbs of one press (alternation.py). No dictionary."""
import re
import unittest

from yuragi.chord.fsm import AmbShift, ChordFsm, Plain, ThumbTap
from yuragi.ime.session import load_table, to_lattice_token
from yuragi.lattice.alternation import Plan


def tokens(events):
    """Run key events through a fresh state machine. As the session does, a
    deadline reached by the time of an event fires before that event."""
    fsm = ChordFsm()
    out = []
    for updown, kind, key, now in events:
        out += fsm.on_timeout(now)
        out += (fsm.on_down if updown == "down" else fsm.on_up)(kind, key, now)
    return out + fsm.on_timeout(10**6)


def keys(spec):
    """Spec "w+0 O+50 w-69" → events: + is down, - is up, O is Space."""
    events = []
    for item in spec.split():
        updown = "down" if "+" in item else "up"
        key, now = re.split(r"[+-]", item)
        events.append((updown, "O", "space", int(now)) if key == "O"
                      else (updown, "M", key, int(now)))
    return events


def chord(key, now, up):
    return [("down", "M", key, now), ("up", "M", key, up)]


class ChordJudgmentTest(unittest.TestCase):
    def test_character_first_then_thumb(self):
        out = tokens([("down", "M", "w", 0), ("down", "O", "space", 40),
                      ("up", "M", "w", 90), ("up", "O", "space", 100)])
        self.assertEqual(out, [AmbShift("w")])
        self.assertEqual((out[0].press, out[0].turn), (1, 1))

    def test_characters_typed_while_the_thumb_stays_down(self):
        out = tokens([("down", "O", "space", 0), *chord("w", 10, 60), *chord("e", 100, 150),
                      *chord("w", 200, 250), ("up", "O", "space", 300)])
        self.assertEqual(out, [AmbShift("w"), AmbShift("e"), AmbShift("w")])
        self.assertEqual([(t.press, t.turn) for t in out], [(1, 1), (1, 2), (1, 3)])

    def test_each_exit_at_its_boundary(self):
        """The exits of fsm.py's table, each on both sides of its boundary:
        the 80 ms window, the 20 ms overlap, and S7's cover against last."""
        P, A, T = Plain, AmbShift, ThumbTap
        cases = [
            # S2: the next character makes the pending one plain.
            ("w+0 e+30 w-40 e-70", [P("w"), P("e")]),
            # S2's window: the thumb at 79 ms makes a chord, at 80 ms it is too late.
            ("w+0 O+79 O-100 w-120", [A("w")]),
            ("w+0 O+80 O-100 w-120", [P("w"), T()]),
            # S3's window; after a lone Space the character held in the press is plain.
            ("O+0 w+79 w-130 O-150", [A("w")]),
            ("O+0 w+80 w-130 O-150", [T(), P("w")]),
            # S4, character up: an overlap under 20 ms is a plain character.
            ("w+0 O+50 w-69 O-150", [P("w"), T()]),
            ("w+0 O+50 w-70 O-150", [A("w")]),
            # S4, Space up first: a chord.
            ("w+0 O+30 O-60 w-90", [A("w")]),
            # S4, next character: a chord if Space came nearer the next character.
            ("w+0 O+30 e+61 e-100 O-120", [A("w"), A("e")]),
            ("w+0 O+30 e+60 e-100 O-120", [P("w"), A("e")]),
            # S4/S5 deadline: a chord.
            ("w+0 O+30 O-500 w-510", [A("w")]),
            ("O+0 w+10 O-500 w-510", [A("w")]),
            # S5, Space up: an overlap under 20 ms is a lone Space, the character pending.
            ("O+0 w+50 O-69 w-100", [T(), P("w")]),
            ("O+0 w+50 O-70 w-100", [A("w")]),
            # S5, next character: a chord.
            ("O+0 w+10 e+30 w-50 e-60 O-100", [A("w"), A("e")]),
            # S7 (last 50 ms), Space up: a chord if cover >= last - cover.
            ("O+0 w+10 w-60 e+100 O-125 e-140", [A("w"), A("e")]),
            ("O+0 w+10 w-60 e+100 O-124 e-140", [A("w"), P("e")]),
            # S7 (last 30 ms), Space up under 20 ms leaves the character pending.
            ("O+0 w+10 w-40 e+100 O-120 e-150", [A("w"), A("e")]),
            ("O+0 w+10 w-40 e+100 O-119 e-150", [A("w"), P("e")]),
            # S7 (last 50 ms), next character: the comparison with the cover so far.
            ("O+0 w+10 w-60 e+100 r+125 e-130 r-160 O-200", [A("w"), A("e"), A("r")]),
            ("O+0 w+10 w-60 e+100 r+124 e-130 r-160 O-200", [A("w"), P("e"), A("r")]),
            # S7 (last 290 ms), deadline at 80 ms: a chord, though the cover is short.
            ("O+0 w+10 w-300 e+400 O-480 e-500", [A("w"), A("e")]),
            ("O+0 w+10 w-300 e+400 O-479 e-500", [A("w"), P("e")]),
        ]
        for spec, expected in cases:
            with self.subTest(spec):
                self.assertEqual(tokens(keys(spec)), expected)

    def test_each_press_counts_its_own_turns(self):
        out = tokens(keys("O+0 w+10 w-60 O-100 O+200 e+210 e-260 O-300"))
        self.assertEqual([(t.press, t.turn) for t in out], [(1, 1), (2, 1)])


class AlternationTest(unittest.TestCase):
    """w is か; with the left thumb え, with the right が."""

    @classmethod
    def setUpClass(cls):
        cls.table = load_table()

    def readings(self, chords):
        lattice = [to_lattice_token(AmbShift(key, press, turn), self.table)
                   for key, press, turn in chords]
        return sorted(reading for end, reading, _ in
                      Plan(lattice).walk(lattice, 0, lambda _: True) if end == len(lattice))

    def test_the_chords_of_one_press_alternate(self):
        self.assertEqual(self.readings([("w", 1, 1), ("w", 1, 2)]), ["えが", "がえ"])
        self.assertEqual(self.readings([("w", 1, 1), ("w", 1, 2), ("w", 1, 3)]),
                         ["えがえ", "がえが"])

    def test_separate_presses_choose_freely(self):
        self.assertEqual(self.readings([("w", 1, 1), ("w", 2, 1)]),
                         ["ええ", "えが", "がえ", "がが"])


if __name__ == "__main__":
    unittest.main()
