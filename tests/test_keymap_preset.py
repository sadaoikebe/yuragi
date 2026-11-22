"""A damaged bundled preset stops the engine through its startup error path."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

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
    def test_invalid_distribution_reports_fatal_before_ready(self):
        deep = sys.getrecursionlimit() + 100
        cases = {
            "missing": None,
            "invalid UTF-8": b'\xff',
            "invalid JSON": b'{',
            "non-JSON number": b'{"version":NaN,"bindings":[]}',
            "deep nesting": b'[' * deep + b'0' + b']' * deep,
            "missing bindings": b'{}',
            "malformed row": b'{"bindings":[["composing",13,"commit"]]}',
            "unknown command": b'{"bindings":[["composing","Enter","unknown"]]}',
            "bad chord": b'{"bindings":[["composing","NoSuchKey","commit"]]}',
            "forbidden assignment": b'{"bindings":[["composing","Enter","commit"],'
                                    b'["composing","A","commit"]]}',
        }
        with tempfile.TemporaryDirectory() as directory:
            preset = Path(directory) / "ms-ime.json"
            for label, data in cases.items():
                with self.subTest(label=label):
                    if data is None:
                        preset.unlink(missing_ok=True)
                    else:
                        preset.write_bytes(data)
                    child = subprocess.run([sys.executable, "-c", CHILD, directory], cwd=ROOT,
                                           input="", capture_output=True, encoding="utf-8", timeout=30)
                    self.assertEqual(child.returncode, 1, child.stderr)
                    self.assertIn("fatal program-files-unreadable", child.stderr.splitlines())
                    self.assertEqual(child.stdout, "")
