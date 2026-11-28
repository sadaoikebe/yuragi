"""The dictionary's files on disk: the cache the engine starts from, and the
manifest the installer checks a downloaded dictionary against."""
from __future__ import annotations

from contextlib import redirect_stderr
import io
from pathlib import Path
import pickle
import tempfile
import unittest
from unittest.mock import patch

from yuragi.lattice import dict_manifest, mozc_dict
from tests.support import small_lex


class Files(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name)


class CacheTest(Files):
    def test_a_written_cache_reads_back_the_same(self):
        lex = small_lex("き 木 300\nき 気 400\nきしゃ 記者 1000")
        cache = self.dir / "new" / "lex.pkl"  # the folder is made on the first run
        mozc_dict.write_cache(cache, lex)
        self.assertEqual([p.name for p in cache.parent.iterdir()], ["lex.pkl"])  # no temporary file left
        back = mozc_dict.read_cache(cache)
        self.assertEqual((back.by_reading, back.prefixes, back.connect, back.pos_size),
                         (lex.by_reading, lex.prefixes, lex.connect, lex.pos_size))

    def test_a_cache_that_cannot_be_used_is_built_again(self):
        """Written halfway, emptied by a full disk, or left by another version."""
        cache = self.dir / "lex.pkl"
        self.assertIsNone(mozc_dict.read_cache(cache))  # none yet: nothing to say
        mozc_dict.write_cache(cache, small_lex("き 木 300"))
        whole = cache.read_bytes()
        for label, data in (("empty", b""), ("cut", whole[:len(whole) // 2]), ("not a cache", b"hello"),
                            ("another shape", pickle.dumps((1, 2, 3)))):
            with self.subTest(label), redirect_stderr(io.StringIO()) as log:
                cache.write_bytes(data)
                self.assertIsNone(mozc_dict.read_cache(cache))
                self.assertIn("rebuilding", log.getvalue())


class ManifestTest(Files):
    def test_verify_names_what_differs_from_the_manifest(self):
        for name in dict_manifest.REQUIRED:
            (self.dir / name).write_text(name, encoding="utf-8")
        with patch.object(mozc_dict, "DICT_DIR", self.dir):
            manifest = dict_manifest.build("test", "0000")
            self.assertEqual(dict_manifest.verify(manifest), [])
            (self.dir / "suffix.txt").unlink()  # a download that stopped
            (self.dir / "dictionary03.txt").write_text("dictionary03.tx", encoding="utf-8")  # cut short
            (self.dir / "dictionary10.txt").write_text("x", encoding="utf-8")
            self.assertEqual(dict_manifest.verify(manifest),
                             ["changed dictionary03.txt", "missing suffix.txt",
                              "unrecorded dictionary10.txt (the loader would read it)"])


if __name__ == "__main__":
    unittest.main()
