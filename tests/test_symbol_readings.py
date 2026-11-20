"""Symbols from their readings: where the symbols come
in a clause's candidates."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from yuragi.chord.fsm import Plain
from yuragi.ime.bunsetsu import SYMBOL_HEAD, SYMBOL_OFFSET
from yuragi.ime.learning import LearningStore
from yuragi.ime.server import dispatch
from yuragi.ime.session import ImeSession
from yuragi.ime.symbol_readings import load_symbols
from tests.real_dictionary import real_lex

VK_RETURN, VK_F6 = 0x0D, 0x75


class SymbolConversionTest(unittest.TestCase):
    """With the real dictionary."""

    @classmethod
    def setUpClass(cls):
        cls.lex = real_lex()
        cls.symbols = load_symbols()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "learning.jsonl"
        self.path.touch()

    def session(self, reading, *, learning=False):
        s = ImeSession(_lex=self.lex, _symbols=self.symbols,
                       _learning=LearningStore(self.path) if learning else None)
        s._table = {"keys": {c: {"plain": c} for c in reading}}
        s.tokens = [Plain(c) for c in reading]
        s._refresh()
        return s

    def rows(self, s, count=40):
        s.converted = True
        s._open_cands()
        stream = s.segments[s.focus].choices
        stream.ensure(count)
        return stream.cache[:count]

    def assert_symbols_fourth(self, reading, first, symbol):
        s = self.session(reading)
        self.assertEqual(s.composition, first)  # the 1-best is the dictionary's
        rows = self.rows(s)
        self.assertEqual(rows[0].surface, first)
        self.assertTrue(all(c.kind == "dictionary" for c in rows[:SYMBOL_OFFSET]))
        self.assertEqual(rows[SYMBOL_OFFSET].kind, "symbol")
        self.assertIn(symbol, [c.surface for c in rows if c.kind == "symbol"])
        symbols = [c.surface for c in rows if c.kind == "symbol"]
        self.assertEqual(len(symbols), len(set(symbols)))
        self.assertFalse(set(symbols) & {c.surface for c in rows if c.kind == "dictionary"})
        return rows

    def test_yajirushi(self):
        self.assert_symbols_fourth("やじるし", "矢印", "→")

    def test_kigou(self):
        rows = self.assert_symbols_fourth("きごう", "記号", "゛")
        self.assertEqual(rows[SYMBOL_OFFSET + SYMBOL_HEAD].kind, "dictionary")

    def test_a_chosen_symbol_comes_first_next_time(self):
        s = self.session("かっこ", learning=True)
        rows = self.rows(s, 200)  # 「」 is beyond the first SYMBOL_HEAD: near the end
        s._select(next(i for i, c in enumerate(rows) if c.surface == "「」"))
        self.assertEqual(dispatch(s, {"op": "down", "vk": VK_RETURN})["commit"], "「」")
        before = rows
        rows = self.rows(self.session("かっこ", learning=True), 200)
        self.assertEqual(rows[0].surface, "「」")
        self.assertEqual(rows[0].kind, "symbol")
        self.assertEqual(rows[1:], [c for c in before if c.surface != "「」"])

    def test_shift_f6_forgets_a_chosen_symbol(self):
        s = self.session("かっこ", learning=True)
        rows = self.rows(s, 200)
        s._select(next(i for i, c in enumerate(rows) if c.surface == "「」"))
        dispatch(s, {"op": "down", "vk": VK_RETURN})
        s = self.session("かっこ", learning=True)
        rows = self.rows(s)
        s._select(0)
        self.assertEqual(s.segments[s.focus].selected.surface, "「」")
        dispatch(s, {"op": "down", "vk": VK_F6, "mods": ["shift"]})
        self.assertEqual(s.segments[s.focus].selected, rows[1])  # the newly ranked first
        self.assertFalse(LearningStore(self.path).has_pair("かっこ", "「」"))
        rows = self.rows(self.session("かっこ", learning=True), 200)
        self.assertEqual(rows[SYMBOL_OFFSET].surface, self.symbols["かっこ"][0])
        self.assertEqual(sum(c.surface == "「」" for c in rows), 1)  # still offered


if __name__ == "__main__":
    unittest.main()
