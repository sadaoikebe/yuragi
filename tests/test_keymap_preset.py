"""A damaged bundled preset stops the engine through its startup error path."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from yuragi.ime import keymap

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
