"""Loading the bundled overlay independently of the base Mozc dictionary."""

from array import array
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from yuragi.lattice.mozc_dict import Entry, MozcLex, apply_user_lex


class UserLexiconTest(unittest.TestCase):
    def test_invalid_json_does_not_stop_loading_the_overlay(self):
        lex = MozcLex({}, set(), array("h", [0]), 1)
        errors = StringIO()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "user_lexicon.jsonl"
            path.write_text(
                '{"reading":"あ","surface":"亜","cost":10,"lid":0}\n'
                '{broken JSON}\n'
                '{"reading":"いろ","surface":"色","cost":20,"lid":0}\n',
                encoding="utf-8",
            )
            with redirect_stderr(errors):
                loaded = apply_user_lex(lex, path)

        self.assertEqual(loaded, 2)
        self.assertEqual(lex.by_reading, {
            "あ": [Entry("亜", "あ", 0, 0, 10)],
            "いろ": [Entry("色", "いろ", 0, 0, 20)],
        })
        self.assertEqual(lex.prefixes, {"あ", "い", "いろ"})
        self.assertIn(f"{path}:2:", errors.getvalue())
