"""The personal word list file: written, read back, and hand edits survived."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from yuragi.ime.personal import (DEFAULT_COST, PersonalLexicon, add_word,
                                  read_words, remove_word, scan_words)
from yuragi.lattice.mozc_dict import Entry, MozcLex


def lex():
    return MozcLex({"かた": [Entry("肩", "かた", 1851, 1851, 3000),
                            Entry("方", "かた", 1852, 1852, 3500),
                            Entry("方", "かた", 1900, 1900, 4000)]},
                   {"か", "かた"}, [0] * (3000 * 3000), 3000)


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

    def test_hand_edits_tolerated(self):
        self.path.write_text('# comment\n{"reading": "あ", "surface": "亜"}\nnot json\n'
                             '{"reading": "abc", "surface": "x"}\n', encoding="utf-8")
        self.assertEqual([(w.surface, w.cost) for w in read_words(self.path)],
                         [("亜", DEFAULT_COST)])

    def test_skipped_lines_are_counted(self):
        """REDESIGN §6.2: a broken line is skipped and counted (shown to the user)."""
        self.path.write_bytes('{"reading": "あ", "surface": "亜"}\nnot json\n'
                              '{"reading": "い"}\n'.encode("utf-8") + b"\xff\xfe broken\n")
        words, skipped = scan_words(self.path)
        self.assertEqual(([w.surface for w in words], skipped), (["亜"], 3))
        overlay = PersonalLexicon(self.path)
        overlay.sync(lex())
        self.assertEqual((overlay.count, overlay.skipped), (1, 3))


if __name__ == "__main__":
    unittest.main()
