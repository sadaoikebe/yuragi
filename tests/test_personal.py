"""Personal word list persistence and its effect on conversion."""
from __future__ import annotations

from array import array
from pathlib import Path
import tempfile
import unittest

from tests.test_document_context import ENTER, Keys, SPACE
from yuragi.ime.personal import DEFAULT_COST, PersonalLexicon, add_word, read_words, remove_word
from yuragi.ime.server import dispatch
from yuragi.ime.session import ImeSession
from yuragi.lattice.mozc_dict import DEFAULT_NOUN_ID, MozcLex


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

    def test_personal_word_appears_in_conversion_until_removed(self):
        size = DEFAULT_NOUN_ID + 1
        lex = MozcLex({}, set(), array("h", [0]) * (size * size), size)
        session = ImeSession(_lex=lex,
                             personal=PersonalLexicon(self.path), prediction="off")
        session.load()
        keys = Keys(lambda msg: dispatch(session, msg))

        add_word(self.path, "かか", "花歌")
        keys.tap("W")
        keys.tap("W")
        self.assertEqual(keys.tap(SPACE)["composition"], "花歌")
        self.assertEqual(keys.tap(ENTER)["commit"], "花歌")

        remove_word(self.path, "かか", "花歌")
        keys.tap("W")
        keys.tap("W")
        self.assertEqual(keys.tap(SPACE)["composition"], "かか")

if __name__ == "__main__":
    unittest.main()
