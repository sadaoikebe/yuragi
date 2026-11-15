"""The settings file (S1) and the manage CLI (D1/D2/S2) read and write without failing."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from yuragi.ime import broker_client, config, manage
from yuragi.ime.bunsetsu import Candidate
from yuragi.ime.learning import LearningStore
from yuragi.ime.server import argument_parser
from yuragi.lattice.mozc_dict import Entry, MozcLex

POS = 2000


def small_lex():
    return MozcLex({"かた": [Entry("肩", "かた", 1851, 1851, 3000)]},
                   {"か", "かた"}, [0] * (POS * POS), POS)


class TempDir(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.config = self.dir / "config.json"
        # Never the broker of the machine running the tests.
        for name, answer in (("status", None), ("retry", False)):
            patcher = mock.patch.object(broker_client, name, return_value=answer)
            patcher.start()
            self.addCleanup(patcher.stop)

    def write_config(self, **values):
        self.config.write_text(json.dumps(values, ensure_ascii=False), encoding="utf-8")

    def run_manage(self, *argv) -> tuple[int, str]:
        out = io.StringIO()
        with redirect_stdout(out):
            code = manage.main(["--runtime-dir", str(self.dir), *argv])
        return code, out.getvalue()


class ServerTest(TempDir):
    def test_restart_when_not_running(self):
        code, out = self.run_manage("server", "restart")
        self.assertEqual(code, 0)
        self.assertIn("not running", out)

class ConfigTest(TempDir):
    def test_absent_file_is_the_built_in_defaults(self):
        args = config.parse_args(argument_parser(), ["--runtime-dir", str(self.dir)])
        plain = argument_parser().parse_args([])
        for name in config.file_settings(argument_parser()):
            self.assertEqual(getattr(args, name), getattr(plain, name), name)
        self.assertEqual(args.config, self.config)

    def test_unknown_or_invalid_values_are_skipped(self):
        self.write_config(lm_deadlin_ms=1, lm_prefetch="always", resident=True)
        err = io.StringIO()
        with redirect_stderr(err):
            args = config.parse_args(argument_parser(), ["--runtime-dir", str(self.dir)])
        self.assertEqual(args.lm_prefetch, "thumb")
        self.assertFalse(hasattr(args, "resident"))  # the resident server is gone
        self.assertIn("lm_deadlin_ms", err.getvalue())
        self.assertIn("always", err.getvalue())
        self.assertIn("resident", err.getvalue())

    def test_broken_file_never_stops_and_is_reported(self):
        """REDESIGN §6.2: what can be read is used, the rest is the built-in default."""
        cases = {
            '{"lm_k": 4,, broken': ({}, "not readable as JSON"),
            "[1, 2]": ({}, "does not hold a JSON object"),
            b"\xff\xfe{}": ({}, "not readable as JSON"),
            '{"lm_k": "four", "lm_alpha": 0.5}': ({"lm_alpha": 0.5}, "lm_k='four'"),
            '{"learning": "sometimes"}': ({}, "learning='sometimes'"),
        }
        for text, (expected, problem) in cases.items():
            with self.subTest(text=text):
                if isinstance(text, bytes):
                    self.config.write_bytes(text)
                else:
                    self.config.write_text(text, encoding="utf-8")
                problems = []
                with redirect_stderr(io.StringIO()):
                    values = config.read_config(self.config, argument_parser(), problems)
                    args = config.parse_args(argument_parser(), ["--runtime-dir", str(self.dir)])
                self.assertEqual(values, expected)
                self.assertEqual(len(problems), 1)
                self.assertIn(problem, problems[0])
                self.assertEqual(args.lm_k, expected.get("lm_k"))

class ManageTest(TempDir):
    def setUp(self):
        super().setUp()
        self.learning = self.dir / "learning.jsonl"
        self.personal = self.dir / "personal.jsonl"
        self.write_config(learning_file=str(self.learning), personal_file=str(self.personal))

    def test_words(self):
        self.assertEqual(self.run_manage("word", "add", "おやゆび", "親指")[0], 0)
        self.assertEqual(self.run_manage("word", "add", "かた", "型", "--pos", "固有名詞",
                                         "--cost", "1000")[0], 0)
        code, out = self.run_manage("word", "list")
        self.assertEqual(out.splitlines(), ["おやゆび\t親指\t名詞\t2600", "かた\t型\t固有名詞\t1000"])
        self.assertEqual(self.run_manage("word", "remove", "かた", "型")[0], 0)
        self.assertEqual(self.run_manage("word", "remove", "かた", "型")[0], 1)
        self.assertEqual(self.run_manage("word", "add", "ABC", "x")[0], 2)  # not a reading

    def learn(self):
        self.learning.touch()
        store = LearningStore(self.learning)
        store.confirm([(Candidate("ヌエ", "ぬえ", 0, 1, 1, "kana"), "")], small_lex())
        store.confirm([(Candidate("肩", "かた", 0, 1851, 1851, word_cost=3000), "")],
                      small_lex())

    def test_learning_list_promote_clear(self):
        self.assertEqual(self.run_manage("learning", "compact")[0], 1)  # learning off
        self.learn()
        out = self.run_manage("learning", "list")[1].splitlines()
        self.assertEqual([line.split("\t")[:2] for line in out], [["かた", "肩"], ["ぬえ", "ヌエ"]])
        self.assertTrue(out[1].endswith("\tword"))
        self.assertEqual(self.run_manage("learning", "list", "ぬ")[1].count("\n"), 1)
        self.assertEqual(self.run_manage("learning", "promote", "ぬえ", "鵺")[0], 1)
        self.assertEqual(self.run_manage("learning", "promote", "ぬえ", "ヌエ")[0], 0)
        self.assertEqual(self.run_manage("word", "list")[1], "ぬえ\tヌエ\t名詞\t2600\n")
        self.assertEqual(self.run_manage("learning", "clear", "--with-words")[0], 0)
        self.assertEqual(self.run_manage("learning", "list")[1], "")
        self.assertTrue(self.learning.exists())  # cleared, still on

    def test_config_set_and_unset(self):
        self.assertEqual(self.run_manage("config", "set", "lm_k", "4")[0], 0)
        self.assertEqual(json.loads(self.config.read_text(encoding="utf-8"))["lm_k"], 4)
        self.assertIn("lm_k = 4\t[file]", self.run_manage("config", "show")[1])
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(self.run_manage("config", "set", "lm_k", "four")[0], 2)
        self.assertEqual(self.run_manage("config", "unset", "lm_k")[0], 0)
        self.assertNotIn("lm_k", json.loads(self.config.read_text(encoding="utf-8")))
        self.assertEqual(self.run_manage("config", "unset", "lm_k")[0], 1)

if __name__ == "__main__":
    unittest.main()
