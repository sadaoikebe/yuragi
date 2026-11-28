"""The management window's line protocol (yuragi/ime/admin_service.py), on a data folder of its own."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from yuragi.ime import admin_service, broker_client, keymap
from yuragi.ime.admin_ui import AdminModel


class ServiceTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.service = admin_service.Service(AdminModel(self.dir))
        for name in ("status", "retry", "reload_keymap"):  # no input program here
            patch = mock.patch.object(broker_client, name, return_value=None)
            patch.start()
            self.addCleanup(patch.stop)

    def ask(self, op, **fields):
        return self.service.reply(json.dumps({"op": op, **fields}))

    def test_words_are_listed_after_they_are_added(self):
        self.assertTrue(self.ask("add_word", reading="おやゆび", surface="親指", pos="名詞")["ok"])
        state = self.ask("state")
        self.assertEqual([(w["reading"], w["surface"]) for w in state["words"]], [("おやゆび", "親指")])
        self.assertIn("名詞", state["pos"])
        self.assertTrue(self.ask("remove_word", reading="おやゆび", surface="親指")["ok"])
        self.assertEqual(self.ask("state")["words"], [])

    def test_a_request_that_cannot_be_done_says_why(self):
        self.assertFalse(self.ask("add_word", reading="おやゆび")["ok"])  # no surface
        self.assertFalse(self.ask("no_such_op")["ok"])
        self.assertFalse(self.service.reply("{")["ok"])
        self.assertFalse(self.ask("set_setting", name="no_such", value="x")["ok"])

    def test_a_setting_is_written_and_the_engine_restarted(self):
        with mock.patch.object(broker_client, "retry", return_value=True) as retry:
            reply = self.ask("set_setting", name="prediction", value="使わない")
        self.assertTrue(reply["ok"])
        retry.assert_called_once()
        self.assertNotIn("再起動", reply["message"])  # nothing left for the user to do
        self.assertEqual(json.loads((self.dir / "config.json").read_text(encoding="utf-8")),
                         {"prediction": "off"})
        row = next(s for s in self.ask("state")["settings"] if s["name"] == "prediction")
        self.assertEqual(row["value"], "使わない")

    def test_a_setting_without_an_engine_waits_for_its_start(self):
        reply = self.ask("set_setting", name="learning", value="使わない")
        self.assertTrue(reply["ok"])
        self.assertIn("次に起動したとき", reply["message"])

    def test_status_without_an_input_program(self):
        status = self.ask("status")
        self.assertEqual(status["engine"], "")
        self.assertEqual(status["rows"][0][0], "変換エンジン")

    def test_a_pressed_key_gets_a_row_and_a_command(self):
        table = self.ask("keys")
        self.assertFalse(table["dirty"])
        self.assertEqual(len(table["rows"][0]["cells"]), len(table["phases"]))
        pressed = self.ask("key_press", vk=0x51, mods=["ctrl", "shift"])  # Q
        self.assertEqual(pressed["key"], "Ctrl+Shift+Q")
        self.assertIn("Ctrl+Shift+Q", [row["key"] for row in self.ask("keys")["rows"]])

        composing = next(p for p in self.ask("key_detail", key="Ctrl+Shift+Q")["phases"]
                         if p["id"] == "composing")
        self.assertEqual(composing["picked"], admin_service.FOLLOW_PRESET)
        choice = composing["choices"][2]
        self.assertTrue(self.ask("key_assign", key="Ctrl+Shift+Q", phase="composing", choice=choice)["ok"])
        table = self.ask("keys")
        self.assertTrue(table["dirty"] and table["custom"])
        self.assertEqual(next(p for p in self.ask("key_detail", key="Ctrl+Shift+Q")["phases"]
                              if p["id"] == "composing")["picked"], choice)
        self.assertFalse((self.dir / keymap.KEYMAP_NAME).exists())  # nothing written until save

        self.assertTrue(self.ask("key_save")["ok"])
        self.assertFalse(self.ask("keys")["dirty"])
        saved = keymap.load_keymap(self.dir)
        self.assertEqual(saved.use, keymap.CUSTOM)
        self.assertEqual(len(saved.overrides), 1)

    def test_unsaved_key_changes_can_be_dropped(self):
        before = self.ask("keys")
        self.ask("key_press", vk=0x51, mods=["ctrl", "shift"])
        self.ask("key_preset", index=0)
        self.assertTrue(self.ask("key_revert")["ok"])
        self.assertEqual(self.ask("keys"), before)

    def test_keys_that_cannot_be_assigned(self):
        self.assertFalse(self.ask("key_press", vk=0x51, mods=["win"])["ok"])
        self.assertFalse(self.ask("key_press", vk=0xE8, mods=[])["ok"])  # a key with no name
        self.ask("keys")
        self.assertFalse(self.ask("key_assign", key="Space", phase="global",
                                  choice=admin_service.REMOVE)["ok"])
        self.assertFalse(self.ask("key_rename", name="自分用")["ok"])  # a preset has no name to change


if __name__ == "__main__":
    unittest.main()
