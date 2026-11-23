"""The rows of clauses that are not dictionary words: a number typed with the
digit keys, a relative date, a typed symbol (numbers.py, dates.py, symbols.py)."""
from __future__ import annotations

from datetime import datetime
import unittest

from yuragi.ime.session import ImeSession
from yuragi.lattice.mozc_dict import Entry, MozcLex
from yuragi.lattice.table import load_table
from tests.support import Keys, kana_session, type_plain

VK_SPACE, VK_NEXT = 0x20, 0x22
NOW = datetime(2026, 11, 12, 9, 30)  # a Thursday


def rows_of(keys):
    """Convert, open the candidate window: its first page."""
    keys.convert()
    return keys.tap(VK_SPACE)["candidates"]


class CandidateRowsTest(unittest.TestCase):
    def test_digits_make_one_number_clause(self):
        keys = Keys(kana_session())
        for digit in "1234":
            keys.tap(digit)  # the digit keys type full-width digits
        self.assertEqual(len(keys.s.segments), 1)
        self.assertEqual(rows_of(keys),
                         ["１２３４", "1234", "一二三四", "千二百三十四", "1,234", "１，２３４"])

    def test_numpad_digits_make_one_number_clause(self):
        keys = Keys(kana_session())
        for vk in (0x61, 0x62):  # Numpad 1, 2: half-width digits
            keys.tap(vk)
        self.assertEqual(len(keys.s.segments), 1)
        self.assertEqual(keys.s.segments[0].selected.kind, "number")
        self.assertIn("十二", rows_of(keys))

    def test_relative_dates_follow_the_clock(self):
        lex = MozcLex({"あした": [Entry("明日", "あした", 1, 1, 100)],
                       "ことし": [Entry("今年", "ことし", 1, 1, 100)]},
                      {"あ", "あし", "あした", "こ", "こと", "ことし"}, [0] * 4, 2)
        keys = Keys(ImeSession(_table=load_table(), _lex=lex, clock=lambda: NOW))
        type_plain(keys.s, "あした")
        self.assertEqual(rows_of(keys), [
            "明日", "あした", "アシタ", "2026/11/13", "2026-11-13", "2026年11月13日",
            "11月13日", "11/13", "令和8年11月13日"])
        self.assertEqual(keys.tap(VK_NEXT)["candidates"], ["金曜日"])

        keys = Keys(ImeSession(_table=load_table(), _lex=lex, clock=lambda: NOW))
        type_plain(keys.s, "ことし")
        self.assertEqual(rows_of(keys), ["今年", "ことし", "コトシ", "2026年", "令和8年"])

    def test_a_typed_symbol_comes_first_then_its_half_width_form(self):
        cases = [(("1", ["shift"]), ["！", "!"]),
                 ((0x6B, []), ["+"])]  # Numpad + types the half-width form: no other row
        for (key, mods), rows in cases:
            with self.subTest(key=key, mods=mods):
                keys = Keys(kana_session())
                self.assertEqual(keys.tap(key, mods)["composition"], rows[0])
                self.assertEqual(rows_of(keys), rows)


if __name__ == "__main__":
    unittest.main()
