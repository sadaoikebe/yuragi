"""Loading the bundled overlay independently of the base Mozc dictionary."""

from array import array
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from yuragi.lattice.mozc_dict import DictionaryFormatError, MozcLex, apply_user_lex


class UserLexiconTest(unittest.TestCase):
    def test_a_broken_row_stops_loading(self):
        # The overlay is a program file: a broken row stops like a broken
        # dictionary line instead of being skipped or ending in a traceback.
        rows = ['{broken JSON}', '{"reading":"いろ","surface":"色"}',
                '{"reading":"いろ","surface":"色","cost":"x"}']
        with TemporaryDirectory() as directory:
            path = Path(directory) / "user_lexicon.jsonl"
            for row in rows:
                with self.subTest(row=row):
                    path.write_text('{"reading":"あ","surface":"亜","cost":10}\n' + row + "\n",
                                    encoding="utf-8")
                    lex = MozcLex({}, set(), array("h", [0]), 1)
                    with self.assertRaisesRegex(DictionaryFormatError, r"user_lexicon\.jsonl:2:"):
                        apply_user_lex(lex, path)
