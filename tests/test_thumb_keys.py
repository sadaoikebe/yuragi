"""The chord judgment with three thumb keys (docs/JIS-FSM.md): Space, 無変換, 変換.

Two checks on generated typing, with fixed seeds (YURAGI_FSM_RUNS sets how
many sequences each runs), and the cases the specification spells out.
"""
import os
import random
import re
import unittest
from collections import Counter

from yuragi.chord.fsm import (
    AmbShift, ChordFsm, Plain, ThumbJoin, ThumbOver, ThumbTap, thumb_side,
)

RUNS = int(os.environ.get("YURAGI_FSM_RUNS", "2000"))
THUMBS = {"O": "space", "N": "muhenkan", "H": "henkan"}
SIDE = {"left": "muhenkan", "right": "henkan"}


def event(fsm, updown, key, now):
    kind = "O" if key in THUMBS.values() else "M"
    if updown == "down":
        return fsm.on_down(kind, key, now)
    return fsm.on_up(kind, key, now)


def play(spec):
    """Spec "w+0 O+12 H+20 w-70": + is down, - is up, O N H are Space, 無変換, 変換.
    A deadline reached by the time of an event fires before it, as in the session."""
    fsm, out = ChordFsm(), []
    for item in spec.split():
        key, now = re.split(r"[+-]", item)
        out += fsm.on_timeout(int(now))
        out += event(fsm, "down" if "+" in item else "up", THUMBS.get(key, key), int(now))
    return out + fsm.on_timeout(10**6)


def evidence(token):
    return token.key, token.struck, set(token.held), token.press, token.turn


class SpecExamplesTest(unittest.TestCase):
    """JIS-FSM.md §11."""

    def test_one_thumb_on_space_and_henkan(self):
        out = play("k+0 O+12 H+20 k-70 O-90 H-95")
        self.assertEqual(out, [AmbShift("k")])
        self.assertEqual(evidence(out[0]), ("k", ("space", "henkan"), set(), 1, 1))
        self.assertEqual(thumb_side(out[0].struck, out[0].held), "right")

    def test_second_key_after_the_chord_was_decided(self):
        out = play("k+0 O+4 k-14 H+22 O-80 H-85")
        self.assertEqual(out, [AmbShift("k"), ThumbJoin(1, 1, "henkan")])
        self.assertEqual(out[0].origin, (1, 1))

    def test_three_chords_under_one_space(self):
        out = play("O+0 a+10 b+90 N+95 c+170 c-230 b-240 N-250 O-300 a-310")
        self.assertEqual([evidence(t) for t in out], [
            ("a", ("space",), set(), 1, 1),
            ("b", ("muhenkan",), {"space"}, 1, 2),
            ("c", (), {"space", "muhenkan"}, 1, 3),
        ])
        self.assertEqual([thumb_side(t.struck, t.held) for t in out], [None, "left", "right"])

    def test_muhenkan_and_henkan_only(self):
        out = play("N+0 a+10 a-60 b+100 H+110 N-120 b-170 c+200 c-250 H-260")
        self.assertEqual(out, [AmbShift("a"), AmbShift("b"), Plain("c")])
        self.assertEqual([evidence(t) for t in out[:2]], [
            ("a", ("muhenkan",), set(), 1, 1),
            ("b", ("henkan",), {"muhenkan"}, 2, 1),
        ])

    def test_lone_henkan_over_a_space_chord(self):
        out = play("O+0 a+10 a-70 H+130 O-150 H-190")
        self.assertEqual(out, [AmbShift("a"), ThumbOver(1, 1, "henkan"), ThumbTap("henkan")])


class ThumbKeyRulesTest(unittest.TestCase):
    def test_a_lone_thumb_key_runs_its_own_function(self):
        for key, name in THUMBS.items():
            self.assertEqual(play(f"{key}+0 {key}-50"), [ThumbTap(name)])
            self.assertEqual(play(f"{key}+0 {key}-500"), [ThumbTap(name)])  # at 80 ms

    def test_muhenkan_and_henkan_are_never_one_stroke(self):
        out = play("N+0 H+5 w+10 w-60 N-70 H-75")
        self.assertEqual(evidence(out[0]), ("w", ("henkan",), {"muhenkan"}, 1, 1))

    def test_a_key_after_the_join_window_is_another_stroke(self):
        joined = play("w+0 O+10 H+40 w-90 O-100 H-105")
        self.assertEqual(joined[0].struck, ("space", "henkan"))
        apart = play("w+0 O+10 H+41 w-90 O-100 H-105")
        self.assertEqual(apart[0].struck, ("space",))
        self.assertEqual(apart[1:], [ThumbOver(1, 1, "henkan"), ThumbTap("henkan")])

    def test_two_thumb_keys_without_a_character_run_the_first_once(self):
        self.assertEqual(play("N+0 H+50 N-60 H-90"), [ThumbTap("muhenkan")])

    def test_a_character_goes_with_the_nearer_stroke(self):
        near_first = play("N+0 w+40 H+90 w-100 N-110 H-120")
        self.assertEqual(near_first[0].struck, ("muhenkan",))
        near_second = play("N+0 w+60 H+90 w-140 N-150 H-160")
        self.assertEqual(evidence(near_second[0]), ("w", ("henkan",), {"muhenkan"}, 1, 1))
        self.assertEqual(near_second, [AmbShift("w")])

    def test_no_unseen_stroke_while_both_thumbs_are_busy(self):
        out = play("O+0 a+10 a-60 N+100 b+110 b-150 H+200 c+210 c-260 d+300 d-350 N-400 H-410 O-420")
        self.assertEqual(out, [AmbShift("a"), AmbShift("b"), AmbShift("c"), Plain("d")])

    def test_a_thumb_key_held_down_leaves_nothing_behind(self):
        # The downs a held key keeps sending change nothing: once the keys are up, typing is as before.
        out = play("w+0 O+10 w-60 O+510 O+543 O+576 O-600 e+700 e-760")
        self.assertEqual([(type(t), t.key) for t in out], [(AmbShift, "w"), (Plain, "e")])

    def test_reset_keeps_the_held_keys_and_clear_drops_them(self):
        fsm = ChordFsm()
        fsm.on_down("O", "henkan", 0)
        fsm.reset()
        self.assertEqual((fsm.state, fsm.timer_deadline), ("S1", None))
        fsm.on_down("O", "muhenkan", 100)
        out = fsm.on_down("M", "w", 110) + fsm.on_up("M", "w", 160)
        self.assertEqual(out[0].held, {"henkan"})
        fsm.clear()
        self.assertEqual((fsm.state, fsm.held, fsm.stroke, fsm.pressed_at), ("S1", {}, None, {}))
        self.assertEqual(fsm.on_up("O", "henkan", 300), [])
        fsm.on_down("O", "space", 400)
        out = fsm.on_down("M", "w", 410) + fsm.on_up("M", "w", 460)
        self.assertEqual(out[0].held, set())

    def test_a_late_key_after_reset_joins_silently(self):
        fsm = ChordFsm()
        fsm.on_down("M", "w", 0)
        fsm.on_down("O", "space", 4)
        self.assertEqual(fsm.on_up("M", "w", 14), [AmbShift("w")])
        fsm.reset()
        self.assertEqual(fsm.on_down("O", "henkan", 22), [])
        self.assertEqual(fsm.state, "S1")
        self.assertEqual(fsm.on_up("O", "henkan", 60), [])


class StateTableTest(unittest.TestCase):
    """Arbitrary sequences of the three thumb keys: the state agrees with JIS-FSM.md §5."""

    def check(self, fsm, log):
        stroke, st = fsm.stroke, fsm.state
        fresh = stroke is not None and stroke.use == "fresh"
        self.assertEqual(st in ("S3", "S4", "S5"), fresh, log)
        if not fresh:
            self.assertEqual(st in ("S6", "S7"), fsm.carrier is not None, log)
        self.assertEqual(st in ("S2", "S4", "S5", "S7"), fsm.m_key is not None, log)
        self.assertTrue(fsm.carrier is None or "space" in fsm.held, log)
        self.assertEqual(fsm.timer_deadline is None, st in ("S1", "S6"), log)
        if fresh:
            self.assertTrue(set(stroke.keys) <= set(fsm.held), log)
            self.assertFalse({"muhenkan", "henkan"} <= set(stroke.keys), log)

    def run_one(self, seed):
        rng = random.Random(seed)
        fsm, now, down, log, out = ChordFsm(), 0, set(), [], []
        thumbs = list(THUMBS.values())

        def timers(until):
            while fsm.timer_deadline is not None and fsm.timer_deadline <= until:
                out.extend(fsm.on_timeout(fsm.timer_deadline))
                self.check(fsm, log)

        for _ in range(rng.randint(5, 80)):
            now += rng.choice([1, 2, 5, 10, 19, 20, 29, 30, 31, 40, 60, 79, 80, 81, 150])
            timers(now)
            r = rng.random()
            if r < 0.02:
                fsm.reset()
                log.append((now, "reset"))
            elif r < 0.03:
                fsm.clear()
                down.clear()
                log.append((now, "clear"))
            else:
                key = rng.choice(thumbs * 2 + ["a", "b", "c"])
                updown = "up" if key in down else "down"
                log.append((now, updown, key))
                out += event(fsm, updown, key, now)
                (down.discard if key in down else down.add)(key)
            self.check(fsm, log)
        for key in sorted(down):
            now += 500
            timers(now)
            out += event(fsm, "up", key, now)
            self.check(fsm, log)
        self.assertEqual((fsm.state, fsm.held, fsm.m_key), ("S1", {}, None), log)
        # Chains count 1, 2, ...; evidence added later names a chord already emitted.
        seen = set()
        for token in out:
            if isinstance(token, AmbShift):
                at = (token.press, token.turn)
                self.assertEqual(token.origin, at, log)
                self.assertNotIn(at, seen, log)
                self.assertTrue(token.turn == 1 or (token.press, token.turn - 1) in seen, log)
                seen.add(at)
            elif isinstance(token, (ThumbJoin, ThumbOver)):
                self.assertIn((token.press, token.turn), seen, log)
        typed = sum(1 for e in log if e[1] == "down" and e[2] not in thumbs)
        self.assertLessEqual(sum(isinstance(t, (Plain, AmbShift)) for t in out), typed, log)

    def test_states(self):
        for seed in range(RUNS):
            self.run_one(seed)


class TypingModelTest(unittest.TestCase):
    """Typing that follows the model (JIS-FSM.md §1, A1–A5, a stroke's keys at most 25 ms apart):
    the evidence never names the wrong thumb, the chains alternate, and lone strokes are lone."""

    @staticmethod
    def make(rng, space_only, max_stagger):
        """Items in typing order: a chord, a plain character, or a lone thumb stroke."""
        items, now = [], 1000
        for i in range(rng.randint(3, 14)):
            now += rng.randint(85, 220)
            r = rng.random()
            kind = "chord" if r < 0.7 else "plain" if r < 0.93 else "lone"
            if kind == "lone":  # no character inside the 80 ms window around it
                now += 110
            char = None if kind == "lone" else (f"k{i}", now, now + rng.randint(60, 110))
            stroke = None
            if kind != "plain":
                hand = rng.choice(["left", "right"])
                start = now + rng.randint(-15, 15)
                end = start + rng.randint(50, 150)
                own = SIDE[hand]
                if kind == "lone" or rng.random() >= space_only:
                    keys = rng.choice([[own], ["space", own], [own, "space"]])
                else:
                    keys = ["space"]
                stroke = {"hand": hand, "start": start, "end": end, "keys": keys,
                          "stagger": rng.randint(0, max_stagger), "lag": rng.randint(0, 8)}
            items.append({"kind": kind, "char": char, "stroke": stroke})
            if kind == "lone":
                now += 110
        strokes = [item["stroke"] for item in items if item["stroke"]]
        for n, stroke in enumerate(strokes):
            # A3: the same thumb's strokes do not overlap. A4: a stroke overlaps its neighbours only.
            for back, earlier in enumerate(reversed(strokes[:n])):
                if earlier["hand"] == stroke["hand"] or back >= 1:
                    earlier["end"] = min(earlier["end"], stroke["start"] - 15)
        if any(stroke["end"] - stroke["start"] < 45 for stroke in strokes):
            return None
        for item in items:  # a plain character is not under a thumb
            if item["kind"] == "plain":
                _, down, up = item["char"]
                if any(s["start"] - 40 < up and down < s["end"] + 40 for s in strokes):
                    return None
        return items

    @staticmethod
    def events(items):
        """What the keyboard reports: overlapping presses of Space are one press."""
        events, spaces = [], []
        for item in items:
            if item["char"]:
                key, down, up = item["char"]
                events += [(down, 1, "down", key), (up, 1, "up", key)]
            stroke = item["stroke"]
            for n, key in enumerate(stroke["keys"] if stroke else ()):
                down = stroke["start"] + (stroke["stagger"] if n else 0)
                up = stroke["end"] + (stroke["lag"] if n else 0)
                if down >= up:
                    continue
                if key == "space":
                    spaces.append([down, up])
                else:
                    events += [(down, 0, "down", key), (up, 2, "up", key)]
        merged = []
        for down, up in sorted(spaces):
            if merged and down <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], up)
            else:
                merged.append([down, up])
        for down, up in merged:
            events += [(down, 0, "down", "space"), (up, 2, "up", "space")]
        return sorted(events)

    def judge(self, items, stats):
        fsm, out = ChordFsm(), []
        for now, _, updown, key in self.events(items):
            while fsm.timer_deadline is not None and fsm.timer_deadline <= now:
                out += fsm.on_timeout(fsm.timer_deadline)
            out += event(fsm, updown, key, now)
        out += fsm.on_timeout(10**9)
        self.assertEqual((fsm.state, fsm.held), ("S1", {}))

        truth = {item["char"][0]: item for item in items if item["char"]}
        order = {id(item): n for n, item in enumerate(i for i in items if i["stroke"])}
        chords = {}
        for token in out:
            if isinstance(token, AmbShift):
                chords[token.origin] = [token.key, list(token.struck), token.held, []]
            elif isinstance(token, ThumbJoin):
                chords[(token.press, token.turn)][1].append(token.key)
            elif isinstance(token, ThumbOver):
                chords[(token.press, token.turn)][3].append(token.key)
        errors = []
        sides = {}
        for at, (key, struck, held, over) in chords.items():
            item = truth[key]
            sides[at] = thumb_side(struck, held, over)
            if item["kind"] == "chord" and sides[at] not in (None, item["stroke"]["hand"]):
                errors.append(("side", key, struck, set(held), over, item["stroke"]["hand"]))
        ordered = sorted(chords)
        for a, b in zip(ordered, ordered[1:]):
            first, second = truth[chords[a][0]], truth[chords[b][0]]
            if (a[0] == b[0] and first["kind"] == second["kind"] == "chord"
                    and order[id(second)] - order[id(first)] == 1  # no stroke between them judged otherwise
                    and first["stroke"]["hand"] == second["stroke"]["hand"]):
                errors.append(("alternation", chords[a][0], chords[b][0]))
        stats["lone"] += sum(item["kind"] == "lone" for item in items)
        stats["taps"] += sum(isinstance(token, ThumbTap) for token in out)
        stats["chords"] += len(chords)
        stats["settled"] += sum(side is not None for side in sides.values())
        return errors

    def run_model(self, space_only, max_stagger):
        rng, stats, wrong, done = random.Random(1), Counter(), [], 0
        while done < RUNS:
            items = self.make(rng, space_only, max_stagger)
            if items is None:
                continue
            done += 1
            errors = self.judge(items, stats)
            if errors:
                wrong.append((errors, items))
        return stats, wrong

    def test_evidence_agrees_with_the_thumbs(self):
        for space_only in (1.0, 0.8, 0.5, 0.0):
            with self.subTest(space_only=space_only):
                stats, wrong = self.run_model(space_only, 25)
                self.assertEqual(wrong[:1], [])
                self.assertEqual(stats["taps"], stats["lone"])
                if space_only == 1.0:
                    self.assertEqual(stats["settled"], 0)

    def test_a_wide_stagger_is_outside_the_model(self):
        """JIS-FSM.md §12: beyond JOIN_MS the second key is another stroke, and the side can be wrong."""
        _, wrong = self.run_model(0.5, 60)
        self.assertTrue(wrong)


if __name__ == "__main__":
    unittest.main()
