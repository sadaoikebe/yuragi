"""Whatever is typed, the session stays whole.

Random key sequences go through dispatch as the engine sends them, with each
preset. After every key the clauses still cover the input, the focus, caret
and candidate are inside it, and the reply can be sent. A sequence that breaks
this raises inside the engine, which costs the user the input being typed.
"""
from __future__ import annotations

import json
from pathlib import Path
import random
import tempfile
import unittest

from yuragi.ime.keymap import load_keymap
from yuragi.ime.learning import LearningStore
from yuragi.ime.server import dispatch
from yuragi.ime.session import ImeSession
from yuragi.lattice.expand import is_literal_face
from yuragi.lattice.table import load_table
from tests.support import small_lex

TABLE = load_table()
LETTERS = "ASDFJK"
SPACE = 0x20
# With some input typed: convert it, or move in it and edit.
EDITS = [(SPACE, []), (0x09, []), (0x09, []), (0x09, []), (0x09, []), (0x25, []), (0x24, []), (0x08, []),
         (0x1D, []), (0x28, ["shift"]), (0x76, [])]
# Every key a preset gives a command while converting, with the modifiers used.
COMMANDS = [(SPACE, []), (SPACE, []), (SPACE, ["shift"]), (0x25, ["shift"]), (0x27, ["shift"]), (0x25, ["shift"]),
            (0x27, ["shift"]), (0x25, []), (0x27, []), (0x26, []), (0x28, []), (0x28, ["ctrl"]), (0x28, ["shift"]),
            (0x08, []), (0x2E, []), (0x2E, ["ctrl"]), (0x1B, []), (0x09, []), (0x24, []), (0x23, []), (0x21, []),
            (0x22, []), (0x75, []), (0x76, []), (0x77, []), (0x78, []), (0x79, []), (0x0D, []), (0x31, []),
            (0x32, []), (0x39, []), (0x08, ["ctrl"]), (0x25, ["ctrl"]), (0x27, ["ctrl"]),
            *((ord(c), ["ctrl"]) for c in "NPKLIOUTZ"), (0x1D, []), (0x1C, []), (0x1D, ["shift"]), (0xF0, [])]


def random_lex(rng: random.Random):
    """Words over the readings the letters can type, so conversions find something."""
    faces = {letter: [face for face in TABLE["keys"][letter.lower()].values()
                      if isinstance(face, str) and face and not is_literal_face(face)] for letter in LETTERS}
    kanji = "亜伊宇江尾加木久毛子佐市須瀬曽"
    lines = []
    for i in range(160):
        reading = "".join(rng.choice(faces[rng.choice(LETTERS)])
                          for _ in range(rng.choice((1, 2, 2, 3, 4, 5, 6, 6))))
        pos = rng.choice(("", "", "", "283", "379", "731", "1841", "12", "433"))
        lines.append(f"{reading} {rng.choice(kanji)}{rng.choice(kanji)}{i % 7} "
                     f"{rng.choice((100, 200, 400, 900))} {pos}".strip())
    return small_lex("\n".join(lines))


class SessionInvariantTest(unittest.TestCase):
    def check(self, s: ImeSession, reply: dict, log: tuple) -> None:
        json.dumps(reply)
        if not s.tokens:
            self.assertEqual((s.segments, s.composition, s.focus), ([], "", -1), log)
            self.assertFalse(s.converted or s.editing or s.predicting or s.resizing, log)
            return
        edges = [(g.start, g.end) for g in s.segments]
        self.assertTrue(all(start < end for start, end in edges), (edges, log))
        self.assertEqual([0, *(end for _, end in edges)], [*(start for start, _ in edges), len(s.tokens)],
                         (edges, log))
        self.assertTrue(0 <= s.focus < len(s.segments), log)
        self.assertEqual(s.composition, "".join(g.selected.surface for g in s.segments), log)
        if s.caret is not None:
            self.assertTrue(0 <= s.caret <= len(s.composition), log)
        if s._cursor is not None:
            low, high = s._edit_bounds()
            self.assertTrue(low <= s._cursor <= high, log)
        if s.candidates:
            self.assertTrue(-1 <= s.cand_index < len(s.candidates), log)
        if s.editing or s.resizing:
            self.assertTrue(s.converted, log)

    def run_one(self, seed: int, preset: str, directory: Path) -> None:
        rng = random.Random(seed)
        lex = random_lex(rng)
        (directory / "keymap.json").write_text(json.dumps({"use": preset}), encoding="utf-8")
        history = directory / "learning.jsonl"
        history.unlink(missing_ok=True)
        s = ImeSession(_table=TABLE, _lex=lex, _learning=LearningStore(history),
                       keymap=load_keymap(directory).compile())
        log: list = []
        now = 1000

        def send(op, vk=None, mods=None, at=0):
            msg = {"op": op, "t": now + at}
            if vk is not None:
                msg["vk"] = vk
            if mods is not None:
                msg["mods"] = mods
            log.append((op, vk, mods))
            self.check(s, dispatch(s, msg), (seed, preset, log[-40:]))

        def tap(vk, mods):
            send("down", vk, mods)
            send("up", vk, mods, 30)

        for _ in range(300):
            now += 200
            r = rng.random()
            if s.converted and rng.random() < 0.9:
                r = 0.5 + r / 2  # stay in the conversion: that is where the states are
            if rng.random() < 0.03:
                s.suggest(now + 500)
            elif len(s.tokens) >= rng.choice((3, 5, 8)) and rng.random() < 0.5:
                r = 2
            if r == 2:
                tap(*rng.choice(EDITS))
            elif r < 0.45:
                vk = ord(rng.choice(LETTERS))
                if rng.random() < 0.3:  # a chord: the letter inside a Space press
                    send("down", SPACE)
                    send("down", vk, at=10)
                    send("up", vk, at=50)
                    send("up", SPACE, at=60)
                else:
                    tap(vk, ["shift"] if rng.random() < 0.05 else [])
            elif r < 0.5:
                tap(rng.choice((0x31, 0x32, 0xBC)), None)
            else:
                tap(*rng.choice(COMMANDS))
            if rng.random() < 0.02:
                send("timeout", at=150)

    def test_random_typing_keeps_the_session_whole(self):
        with tempfile.TemporaryDirectory() as directory:
            # Seed 41 with ms-ime is the sequence that found a clause holding kana and a
            # literal left alone after a partial commit; the others are the net around it.
            for preset, seeds in (("ms-ime", range(30, 45)), ("macos", range(3)), ("japanist", range(3))):
                for seed in seeds:
                    self.run_one(seed, preset, Path(directory))


if __name__ == "__main__":
    unittest.main()
