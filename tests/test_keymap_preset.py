"""Reading the key settings: a damaged bundled preset stops the engine through
its startup error path; keymap.json rows and tip.json are checked row by row;
the compiled map gives the TIP its eat table."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from yuragi.chord.keys import CTRL, KEYBOARDS, SHIFT, VK_DBE_ALPHANUMERIC, VK_DBE_DBCSCHAR, Chord
from yuragi.ime import keymap

ANSI, JIS = KEYBOARDS["ansi101"], KEYBOARDS["jis106"]
ROOT = Path(__file__).resolve().parents[1]
CHILD = """
from pathlib import Path
import sys

from yuragi.engine import main
from yuragi.ime import keymap

directory = Path(sys.argv[1])
keymap.PRESET_PATH = directory / "ms-ime.json"
raise SystemExit(main(["--data-dir", str(directory)]))
"""


class BundledPresetTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = directory.name
        self.preset = Path(directory.name) / "ms-ime.json"

    def test_missing_preset_reports_fatal_before_ready(self):
        child = subprocess.run([sys.executable, "-c", CHILD, self.directory], cwd=ROOT,
                               input="", capture_output=True, encoding="utf-8", timeout=30)
        self.assertEqual(child.returncode, 1, child.stderr)
        self.assertIn("fatal program-files-unreadable", child.stderr.splitlines())
        self.assertEqual(child.stdout, "")

    def test_damaged_preset_is_rejected(self):
        """The engine reports these through the same path as a missing file."""
        deep = 100_000  # deeper than the limit of the C stack, too
        header = b'{"name":"ms-ime","label":"MS-IME"'
        cases = {
            "invalid UTF-8": b'\xff',
            "invalid JSON": b'{',
            "non-JSON number": header + b',"version":NaN,"bindings":[]}',
            "deep nesting": b'[' * deep + b'0' + b']' * deep,
            "not an object": b'[]',
            "missing bindings": header + b'}',
            "malformed row": header + b',"bindings":[["composing",13,"commit"]]}',
            "unknown command": header + b',"bindings":[["composing","Enter","unknown"]]}',
            "bad chord": header + b',"bindings":[["composing","NoSuchKey","commit"]]}',
            "forbidden assignment": header + b',"bindings":[["composing","Enter","commit"],'
                                             b'["composing","A","commit"]]}',
        }
        with patch.object(keymap, "PRESET_PATH", self.preset):
            for label, data in cases.items():
                with self.subTest(label=label):
                    self.preset.write_bytes(data)
                    with self.assertRaises(ValueError):
                        keymap._read_preset(keymap.DEFAULT_PRESET)


class KeymapFileTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name)

    def test_custom_name_survives_switching_presets(self):
        path = self.dir / "keymap.json"
        raw = {"use": "custom", "custom": {"base": "macos", "overrides": [
            ["global", "Ctrl+M", "send_enter"],
        ]}}
        path.write_text(json.dumps(raw), encoding="utf-8")
        settings = keymap.load_keymap(self.dir)
        self.assertEqual(settings.custom_name, "")
        original = settings.compile().eat_table(ANSI)

        settings.custom_name = "親指シフト用"
        settings.use = keymap.DEFAULT_PRESET
        settings.save(self.dir)
        settings = keymap.load_keymap(self.dir)
        self.assertEqual(settings.custom_name, "親指シフト用")
        settings.use = keymap.CUSTOM
        self.assertEqual(settings.compile().eat_table(ANSI), original)

        settings.use = keymap.DEFAULT_PRESET
        settings.begin_custom()
        self.assertEqual(settings.custom_name, "")
        settings.save(self.dir)
        self.assertNotIn("name", json.loads(path.read_text(encoding="utf-8"))["custom"])

    def test_rows_that_cannot_work_are_skipped_with_a_note(self):
        rows = [["composing", "Alt+F5", "commit"],                 # Alt chords are global only
                ["global", "A", "ime_toggle"],                     # a typing key, everywhere
                ["direct", "Shift+A", "reconvert"],
                ["empty", "F5", "commit"],                         # nothing to commit
                ["editing", "Space", "delete_before_or_pass"],     # Space cannot be passed on
                ["typing", "F5", None],                            # no such phase
                ["global", "Alt+F5", "ime_toggle"],
                ["editing", "Space", "commit"]]
        (self.dir / "keymap.json").write_text(json.dumps(
            {"use": "custom", "custom": {"base": "ms-ime", "overrides": rows}}), encoding="utf-8")
        settings = keymap.load_keymap(self.dir)
        self.assertIsNone(settings.error)
        self.assertEqual([note.split(":")[0] for note in settings.notes],
                         [f"差分 {index} 行目" for index in range(1, 7)])
        self.assertEqual(set(settings.overrides), {("global", Chord.parse("Alt+F5")),
                                                   ("editing", Chord.parse("Space"))})

    def test_ime_keys_take_ime_commands_in_place_of_their_function_with_no_input(self):
        """MS-IME's key assignment (KEYBIND §4.2): with input, 変換 still converts."""
        rows = [["global", "無変換", "ime_off"], ["global", "変換", "ime_on"],
                ["global", "Space", "ime_off"],            # Space types: no global row
                ["global", "変換", "convert"],             # only what the TIP runs
                ["direct", "変換", "ime_on"]]
        (self.dir / "keymap.json").write_text(json.dumps(
            {"use": "custom", "custom": {"base": "ms-ime", "overrides": rows}}), encoding="utf-8")
        settings = keymap.load_keymap(self.dir)
        self.assertEqual([note.split(":")[0] for note in settings.notes],
                         [f"差分 {index} 行目" for index in (3, 4, 5)])
        compiled = settings.compile()
        henkan, muhenkan = Chord.parse("変換"), Chord.parse("無変換")
        self.assertEqual([compiled.command_for(phase, henkan).id
                          for phase in ("empty", "composing", "converting")],
                         ["ime_on", "convert", "next_candidate"])
        self.assertEqual([compiled.command_for(phase, muhenkan).id for phase in ("empty", "composing")],
                         ["ime_off", "cycle_kana_script"])
        table = compiled.eat_table(JIS)
        self.assertIn({"code": 0x1C, "command": "ime_on"}, table["global"])
        self.assertIn({"code": 0x1D, "command": "ime_off"}, table["global"])

    def test_a_composing_row_does_not_run_in_the_prediction_list(self):
        # predicting inherits composing's rows; a composing-only command there
        # would edit the input while the prediction list is focused.
        rows = [["composing", "Ctrl+J", "delete_before"]]
        (self.dir / "keymap.json").write_text(json.dumps(
            {"use": "custom", "custom": {"base": "ms-ime", "overrides": rows}}), encoding="utf-8")
        compiled = keymap.load_keymap(self.dir).compile()
        self.assertEqual(compiled.command_for("composing", Chord.parse("Ctrl+J")).id, "delete_before")
        self.assertEqual(compiled.command_for("predicting", Chord.parse("Ctrl+J")).id,
                         "commit_and_pass")

    def test_unreadable_keymap_json_is_an_error(self):
        (self.dir / "keymap.json").write_text('{"use": "custom",', encoding="utf-8")
        self.assertIsNotNone(keymap.load_keymap(self.dir).error)


class OneTableTest(unittest.TestCase):
    """One key table for every keyboard: rows name the keys Windows delivers (KEYBIND §4.1)."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name)

    def test_a_row_is_the_key_engraved_so_on_each_keyboard(self):
        ctrl_semicolon = Chord.parse("Ctrl+;")
        self.assertEqual(ANSI.code(ctrl_semicolon), 0xBA | CTRL << 8)
        self.assertEqual(JIS.code(ctrl_semicolon), 0xBB | CTRL << 8)
        self.assertEqual(JIS.chord(0xBA, CTRL), Chord(":", CTRL))

    def test_macos_on_jis_switches_with_a_lone_thumb_key_only_when_there_is_no_input(self):
        # As Mac's 英数 and かな keys; with input, a lone thumb key converts as Space does.
        (self.dir / "keymap.json").write_text(json.dumps({"use": "macos"}), encoding="utf-8")
        compiled = keymap.load_keymap(self.dir).compile()
        phases = ("empty", "composing", "converting")
        for name, alone in (("無変換", "ime_off"), ("変換", "mode_hiragana"), ("Space", "insert_space")):
            self.assertEqual([compiled.command_for(phase, Chord.parse(name)).id for phase in phases],
                             [alone, "convert", "next_candidate"], name)
        for name in ("英数", "半角/全角"):
            self.assertEqual(compiled.command_for("empty", Chord.parse(name)).id, "ime_toggle", name)

    def test_mode_keys_are_looked_up_without_the_modifier_that_made_them(self):
        self.assertEqual(ANSI.chord(VK_DBE_ALPHANUMERIC, SHIFT), Chord("英数"))  # Shift+CapsLock
        self.assertEqual(ANSI.chord(VK_DBE_DBCSCHAR, CTRL), Chord("半角/全角", CTRL))  # Ctrl+`
        self.assertFalse(keymap.chord_allowed("global", Chord.parse("Shift+英数")))

    def test_the_rules_do_not_depend_on_the_keyboard(self):
        allowed = {name: keymap.chord_allowed(phase, Chord.parse(name))
                   for phase, name in (("global", "変換"), ("composing", "漢字"),
                                       ("composing", "'"), ("converting", "Ctrl+@"))}
        self.assertEqual(allowed, {"変換": True, "漢字": False, "'": False, "Ctrl+@": True})

    def test_a_key_the_keyboard_lacks_keeps_its_row(self):
        rows = [["converting", "Ctrl+'", "commit"], ["converting", "Ctrl+@", "commit"]]
        path = self.dir / "keymap.json"
        path.write_text(json.dumps({"use": "custom", "custom": {"base": "ms-ime", "overrides": rows}}),
                        encoding="utf-8")
        settings = keymap.load_keymap(self.dir)
        self.assertEqual(settings.notes, [])
        settings.save(self.dir)
        saved = json.loads(path.read_text(encoding="utf-8"))["custom"]["overrides"]
        self.assertEqual(sorted(saved), sorted(rows))
        compiled = settings.compile()
        for keyboard, present, absent in ((ANSI, 0xDE, 0xC0), (JIS, 0xC0, 0xDE)):
            eaten = compiled.eat_table(keyboard)["phases"]["converting"]["eat"]
            self.assertIn(present | CTRL << 8, eaten, keyboard.name)
            self.assertNotIn(absent | CTRL << 8, eaten, keyboard.name)
            self.assertEqual(compiled.command_for("converting", keyboard.chord(present, CTRL)).id, "commit")


class EatTableTest(unittest.TestCase):
    def test_typing_keys_stay_off_the_table_and_pass_keys_are_passed(self):
        one, shift_f6, enter = (Chord.parse(k) for k in ("1", "Shift+F6", "Enter"))
        phases = keymap.Keymap({("selecting", one): "select_candidate_1",
                                ("composing", shift_f6): "pass_through",
                                ("composing", enter): "commit"}).eat_table(ANSI)["phases"]
        self.assertNotIn(ANSI.code(one), phases["selecting"]["eat"])  # the engine sees typing keys anyway
        self.assertEqual((phases["composing"]["eat"], phases["composing"]["pass"]),
                         ([ANSI.code(enter)], [ANSI.code(shift_f6)]))
        self.assertEqual({phase for phase, row in phases.items() if row.get("rest") == "eat"},
                         set(phases) - {"empty"})

    def test_thumb_keys_stay_off_the_table(self):
        table = keymap.default_keymap().eat_table(ANSI)["phases"]
        codes = {code for row in table.values() for code in row["eat"] + row["pass"]}
        self.assertTrue({0x1C, 0x1D}.isdisjoint(codes))
        self.assertIn(0x1D | SHIFT << 8, codes)  # Shift+無変換 is a command key