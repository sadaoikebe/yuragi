"""The personal word list file: written and read back."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from yuragi.ime.personal import DEFAULT_COST, add_word, read_words, remove_word


class TempFile(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "personal.jsonl"

    def tearDown(self):
        self.dir.cleanup()


class PersonalFileTest(TempFile):
    def test_add_replace_remove(self):
        add_word(self.path, "おやゆび", "親指")
        add_word(self.path, "やまだ", "山田", "姓")
        add_word(self.path, "おやゆび", "親指", "名詞", 1000)  # replaces, not duplicates
        self.assertEqual([(w.reading, w.surface, w.pos, w.cost) for w in read_words(self.path)],
                         [("やまだ", "山田", "姓", DEFAULT_COST),
                          ("おやゆび", "親指", "名詞", 1000)])
        self.assertTrue(remove_word(self.path, "やまだ", "山田"))
        self.assertFalse(remove_word(self.path, "やまだ", "山田"))
        self.assertEqual(len(read_words(self.path)), 1)

if __name__ == "__main__":
    unittest.main()
