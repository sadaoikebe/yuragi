"""The management window's logic, without tkinter or a display."""
from __future__ import annotations

from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from yuragi.ime import admin_ui, broker_client
from yuragi.ime.admin_ui import SETTINGS, AdminModel
from yuragi.ime.bunsetsu import Candidate
from yuragi.ime.learning import LearningStore
from yuragi.ime.personal import read_words
from yuragi.lattice.mozc_dict import Entry, MozcLex

POS = 2000


def small_lex():
    return MozcLex({"かた": [Entry("肩", "かた", 1851, 1851, 3000)]},
                   {"か", "かた"}, [0] * (POS * POS), POS)


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.config = self.dir / "config.json"
        self.learning = self.dir / "learning.jsonl"
        self.personal = self.dir / "personal.jsonl"
        self.config.write_text(json.dumps({"learning_file": str(self.learning),
                                           "personal_file": str(self.personal)}),
                               encoding="utf-8")
        # Never the broker of the machine running the tests: no broker by default.
        self.broker = {"status": None, "retry": False}
        for name in ("status", "retry"):
            patcher = mock.patch.object(broker_client, name,
                                        side_effect=lambda *a, n=name: self.broker[n])
            patcher.start()
            self.addCleanup(patcher.stop)
        self.model = AdminModel(runtime_dir=self.dir)

    def learn(self):
        self.learning.touch()
        store = LearningStore(self.learning)
        store.confirm([(Candidate("ヌエ", "ぬえ", 0, 1, 1, "kana"), "")], small_lex())
        store.confirm([(Candidate("肩", "かた", 0, 1851, 1851, word_cost=3000), "")],
                      small_lex())


class AdminModelTest(Base):
    def test_restart_engine_reports_no_broker(self):
        outcome = self.model.restart_engine()
        self.assertFalse(outcome.ok)


class SettingsTest(Base):
    def test_absent_config_file_is_created_on_first_edit(self):
        self.config.unlink()
        model = AdminModel(runtime_dir=self.dir)
        self.assertTrue(model.set_setting("lm_k", "4").ok)
        self.assertEqual(json.loads(self.config.read_text(encoding="utf-8")), {"lm_k": 4})

    def test_broken_config_file_is_reported_not_overwritten(self):
        self.config.write_text("[1, 2]", encoding="utf-8")
        with redirect_stderr(io.StringIO()):  # the engine's "not an object" note
            model = AdminModel(runtime_dir=self.dir)
            for outcome in (model.set_setting("lm_k", "4"), model.reset_setting("lm_k")):
                self.assertEqual((outcome.ok, outcome.message),
                                 (False, f"設定ファイル {self.config} が壊れているため保存できません"))
        self.assertEqual(self.config.read_text(encoding="utf-8"), "[1, 2]")


class FakeVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class WidgetLayerTest(Base):
    """AdminWindow against a stand-in tkinter: every builder and handler runs."""

    def window(self):
        tk = mock.MagicMock(StringVar=FakeVar)
        modules = {"tkinter": tk, "tkinter.ttk": tk.ttk, "tkinter.messagebox": tk.messagebox,
                   "tkinter.font": tk.font}
        patcher = mock.patch.dict(sys.modules, modules)
        patcher.start()
        self.addCleanup(patcher.stop)
        tk.messagebox.askyesno.return_value = True
        tk.font.nametofont.return_value.metrics.return_value = 16
        tk.ttk.Treeview.side_effect = lambda *a, **k: mock.MagicMock()  # one per table
        root = mock.MagicMock()
        root.winfo_fpixels.return_value = 144.0  # a 150 % monitor
        w = admin_ui.AdminWindow(root, self.model)
        self.assertEqual(w.px(100), 150)
        return w

    @staticmethod
    def select(w, tree, values):
        w._fill(tree, [("other", "row"), values])
        tree.selection.return_value = ("1",)

    def test_handlers_reach_the_files(self):
        self.learn()
        w = self.window()
        w.w_reading.set("おやゆび")
        w.w_surface.set("親指")
        w._add_word()
        self.assertEqual([x.surface for x in read_words(self.personal)], ["親指"])
        self.assertEqual(w.w_reading.get(), "")  # cleared after success
        self.select(w, w.words_tree, ("おやゆび", "親指", "名詞", "2600"))
        w._remove_word()
        self.assertEqual(read_words(self.personal), [])
        self.select(w, w.learning_tree, ("ぬえ", "ヌエ", "1", "", "○"))
        w._promote()
        self.assertEqual([x.surface for x in read_words(self.personal)], ["ヌエ"])
        w._forget()
        self.assertEqual([p.surface for p in self.model.learned()], ["肩"])
        w.settings_tree.selection.return_value = (str(list(SETTINGS).index("lm_k")),)
        w._pick_setting()
        self.assertEqual((w.s_label.get(), w.s_value.get()), ("言語モデルで比べる候補の数", "8"))
        self.assertEqual(w.s_help.get(), SETTINGS["lm_k"].help)  # whole, not cut by the column
        w.s_value.set("4")
        w._save_setting()
        self.assertEqual(json.loads(self.config.read_text(encoding="utf-8"))["lm_k"], 4)
        self.assertIn("再起動", w.message.get())
        w._reset_setting()
        self.assertNotIn("lm_k", json.loads(self.config.read_text(encoding="utf-8")))
        w._tab_changed()
        self.assertEqual(w.message.get(), "")  # a message stays with its tab
        w._refresh_status()

class EntryPointTest(unittest.TestCase):
    def test_without_tkinter_it_says_so(self):
        import builtins
        real = builtins.__import__

        def no_tk(name, *args, **kwargs):
            if name == "tkinter":
                raise ImportError(name)
            return real(name, *args, **kwargs)

        builtins.__import__ = no_tk
        err = io.StringIO()
        try:
            with redirect_stderr(err):
                self.assertEqual(admin_ui.main([]), 1)
        finally:
            builtins.__import__ = real
        self.assertIn("tkinter", err.getvalue())

    def test_dict_dir_is_where_the_status_tab_checks(self):
        # Installed, the dictionary is the shared copy, not the repository's
        # third_party folder; every file was reported missing.
        from yuragi.lattice import mozc_dict
        import builtins
        real = builtins.__import__

        def no_tk(name, *args, **kwargs):
            if name == "tkinter":
                raise ImportError(name)
            return real(name, *args, **kwargs)

        self.addCleanup(setattr, mozc_dict, "DICT_DIR", mozc_dict.DICT_DIR)
        builtins.__import__ = no_tk
        try:
            with redirect_stderr(io.StringIO()):
                admin_ui.main(["--dict-dir", "shared-dict"])
        finally:
            builtins.__import__ = real
        self.assertEqual(mozc_dict.DICT_DIR, Path("shared-dict"))


if __name__ == "__main__":
    unittest.main()
