"""The two rules of one spacebar: the chord judgment (fsm.py) and the
alternating thumbs of one press (alternation.py). No dictionary."""
import unittest

from yuragi.chord.fsm import AmbShift, ChordFsm
from yuragi.ime.session import load_table, to_lattice_token
from yuragi.lattice.alternation import Plan


def tokens(events):
    """Run key events through a fresh state machine; ("t", ms) is a timeout."""
    fsm = ChordFsm()
    out = []
    for event in events:
        if event[0] == "t":
            out += fsm.on_timeout(event[1])
            continue
        updown, kind, key, now = event
        out += (fsm.on_down if updown == "down" else fsm.on_up)(kind, key, now)
    return out + fsm.on_timeout(10**6)


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
