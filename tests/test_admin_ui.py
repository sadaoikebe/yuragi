"""The management window's logic, without tkinter or a display."""
from __future__ import annotations

from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from yuragi.ime import admin_ui, broker_client, config, personal
from yuragi.ime.admin_ui import SETTINGS, AdminModel
from yuragi.chord.keys import Chord
from yuragi.ime.bunsetsu import Candidate
from yuragi.ime.learning import LearningStore
from yuragi.ime.personal import read_words
from yuragi.lattice.mozc_dict import Entry, MozcLex
from tests import support  # noqa: F401 (Mozc の品詞名)

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
        self.personal = self.dir / "personal_lexicon.jsonl"
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
        store.confirm([Candidate("ヌエ", "ぬえ", 0, 1, 1, "kana")], small_lex())
        store.confirm([Candidate("肩", "かた", 0, 1851, 1851, word_cost=3000)],
                      small_lex())


class SettingsTest(Base):
    def test_saving_one_setting_keeps_what_another_version_wrote(self):
        self.config.write_text('{"learning": "off", "a_later_setting": "x"}', encoding="utf-8")
        self.assertTrue(self.model.set_setting("lm_rescore", "使わない").ok)
        self.assertTrue(self.model.reset_setting("learning").ok)
        self.assertEqual(json.loads(self.config.read_text(encoding="utf-8")),
                         {"a_later_setting": "x", "lm_rescore": False})

    def test_a_broken_config_file_is_not_used_and_not_overwritten(self):
        self.config.write_text('{"learning":', encoding="utf-8")
        with redirect_stderr(io.StringIO()):
            self.assertEqual(config.load(self.config), config.DEFAULTS)
        self.assertFalse(self.model.set_setting("lm_rescore", "使わない").ok)
        self.assertFalse(self.model.reset_setting("learning").ok)
        self.assertEqual(self.config.read_text(encoding="utf-8"), '{"learning":')



class ModelTest(Base):
    def test_what_cannot_be_done_is_an_error(self):
        m = self.model
        self.assertFalse(m.set_setting("prediction", "ときどき").ok)
        self.assertFalse(m.add_word("おやゆび", "親指", "名詞", "多め").ok)
        self.assertFalse(self.personal.exists())
        self.assertFalse(m.restart_engine().ok)  # no broker
        self.assertTrue(m.reset_setting("learning").ok)  # already the default: not an error,
        self.assertFalse(self.config.exists())              # and nothing to write
        with mock.patch.object(broker_client, "reload_keymap",
                               return_value={"keymap_reload": "failed", "reason": "壊れた行"}):
            self.assertFalse(m.save_keys(m.key_settings()).ok)


class SocketClientTest(unittest.TestCase):
    """The macOS line (broker_client._SocketConnection) against a small server."""

    def serve(self, answers):
        import socket
        import threading
        directory = tempfile.TemporaryDirectory(dir="/tmp")  # a socket path is short
        self.addCleanup(directory.cleanup)
        address = str(Path(directory.name) / "s")
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(server.close)
        server.bind(address)
        server.listen(1)
        got = []

        def run():
            connection, _ = server.accept()
            with connection, connection.makefile("rwb") as lines:
                for line in lines:
                    request = json.loads(line)
                    got.append(request)
                    for answer in answers.get(request["op"], []):
                        lines.write((json.dumps(answer) + "\n").encode())
                    lines.flush()

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        return address, got

    @unittest.skipIf(sys.platform == "win32", "Unix domain socket")
    def test_reload_skips_events_and_returns_the_reply(self):
        address, got = self.serve({
            "hello": [{"proto": 1, "state": "ready", "warnings": []}],
            "reload_keymap": [{"event": "keymap", "keymap": {}}, {"seq": 1, "keymap_reload": "applied"}]})
        with mock.patch.object(sys, "platform", "darwin"):
            self.assertEqual(broker_client.reload_keymap(address), {"seq": 1, "keymap_reload": "applied"})
            self.assertIsNone(broker_client.status(address + "-none"))
        self.assertEqual([request["op"] for request in got], ["hello", "reload_keymap"])


@unittest.skipUnless(sys.platform == "win32", "uses Windows named objects")
class ActivationTest(unittest.TestCase):
    def test_open_during_startup_signals_existing_instance(self):
        import _winapi

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            with admin_ui._windows_activation(path) as event:
                self.assertIsNotNone(event)
                self.assertEqual(_winapi.WaitForSingleObject(event, 0), _winapi.WAIT_TIMEOUT)
                # The owner has no Tk window yet. A second entry point must only signal it.
                command = ("from yuragi.ime import admin_ui\n"
                           "admin_ui._run_window = lambda *args: 1\n"
                           "raise SystemExit(admin_ui.main())")
                subprocess.run([sys.executable, "-c", command, "--runtime-dir", directory],
                               check=True, timeout=10)
                self.assertEqual(_winapi.WaitForSingleObject(event, 0), _winapi.WAIT_OBJECT_0)
            with admin_ui._windows_activation(path) as event:
                self.assertIsNotNone(event)


class FakeVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class WidgetLayerTest(Base):
    """AdminWindow against a stand-in tkinter: the window builds, and the word,
    learning and setting handlers reach their files. Of the key tab
    (keymap_ui.py), only KeyTab.__init__ runs; the status tab is not checked."""

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
        w.l_pos.set("人名")
        w._promote()
        self.assertEqual([(x.surface, x.pos) for x in read_words(self.personal)], [("ヌエ", "人名")])
        w._forget()
        self.assertEqual([p.surface for p in self.model.learned()], ["肩"])
        w.settings_tree.selection.return_value = (str(list(SETTINGS).index("prediction")),)
        w._pick_setting()
        self.assertEqual(w.s_help.get(), SETTINGS["prediction"].help)  # whole, not cut by the column
        w.s_value.set("使わない")
        w._save_setting()
        self.assertEqual(json.loads(self.config.read_text(encoding="utf-8"))["prediction"], "off")
        self.assertIn("再起動", w.message.get())
        w._reset_setting()
        self.assertNotIn("prediction", json.loads(self.config.read_text(encoding="utf-8")))
        w._tab_changed()
        self.assertEqual(w.message.get(), "")  # a message stays with its tab
        # A handler that raises (the file cannot be written) says so in the window.
        with mock.patch.object(personal, "add_word", side_effect=PermissionError("読み取り専用")):
            w.w_reading.set("おやゆび")
            w.w_surface.set("親指")
            try:
                w._add_word()
            except PermissionError as exc:
                w.root.report_callback_exception(PermissionError, exc, None)
        self.assertIn("読み取り専用", w.message.get())
        w._refresh_status()


if __name__ == "__main__":
    unittest.main()
