"""F7 (katakana) and F10 (the typed keys as alphanumerics) on the input."""
from __future__ import annotations

import unittest

from yuragi.chord.fsm import Plain
from yuragi.ime.server import dispatch
from yuragi.ime.session import ImeSession
from yuragi.lattice.mozc_dict import load_lex
from yuragi.lattice.table import load_table

VK_F7, VK_F10 = 0x76, 0x79


def type_reading(s, reading):
    # Unambiguous faces, no FSM.
    s._table = {"keys": {c: {"plain": c} for c in reading}}
    s.tokens = [Plain(c) for c in reading]
    s._refresh()


def type_keys(s, keys):
    """Real NICOLA keys (unshifted faces), so F9/F10 have key letters to show."""
    s._table = load_table()
    s.tokens = [Plain(k) for k in keys]
    s._refresh()


def tap(s, vk):
    """A full press: a held key's repeat does not act again."""
    reply = dispatch(s, {"op": "down", "vk": vk})
    dispatch(s, {"op": "up", "vk": vk})
    return reply


class KanaKeyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lex = load_lex()

    def session(self):
        return ImeSession(_lex=self.lex, learning_path=None)

    def test_f7_converts_unconverted_input_to_katakana(self):
        s = self.session()
        type_reading(s, "きょう")
        reply = dispatch(s, {"op": "down", "vk": VK_F7})
        self.assertEqual(reply["composition"], "キョウ")
        self.assertTrue(s.converted)
        selected = s.segments[s.focus].selected
        self.assertEqual((selected.surface, selected.kind), ("キョウ", "kana"))

    def test_f10_gives_the_typed_keys_and_cycles_case(self):
        s = self.session()
        type_keys(s, "ew")  # た か
        self.assertEqual("".join(t["kana"] for t in s._lattice()), "たか")
        surfaces = [tap(s, VK_F10)["composition"] for _ in range(4)]
        self.assertEqual(surfaces, ["ew", "EW", "Ew", "ew"])
        self.assertEqual(s.segments[s.focus].selected.reading, "たか")


if __name__ == "__main__":
    unittest.main()
