"""REDESIGN §8: what can be checked of the installer scripts without Windows.

- The elevated part gets exactly the arguments setup/uninstall meant, however
  odd the paths (spaces, quotes, Japanese; its own path too): the
  -EncodedCommand round trip.

pwsh runs these (GitHub's Ubuntu runners have it; YURAGI_PWSH names another).
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PWSH = os.environ.get("YURAGI_PWSH") or shutil.which("pwsh")


def pwsh(script: str) -> str:
    result = subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-Command", script],
                            capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    return result.stdout


def function_text(path: Path, name: str) -> str:
    """One function's definition, taken from the script by PowerShell's own parser."""
    out = pwsh(
        f"$ast = [System.Management.Automation.Language.Parser]::ParseFile('{path}', [ref]$null, [ref]$null);"
        f"$ast.FindAll({{ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst]"
        f" -and $n.Name -eq '{name}' }}, $true)[0].Extent.Text")
    if not out.strip():
        raise AssertionError(f"{name} not found in {path}")
    return out


@unittest.skipIf(PWSH is None, "pwsh is not installed (set YURAGI_PWSH)")
class PowerShellTest(unittest.TestCase):
    def test_elevated_arguments_survive_encoding(self):
        odd = {
            "Tag": "v0.2.0",
            "DllSource": r"C:\Users\テスト user\AppData\Local\yuragi-ime\versions\v0.2.0\download\yuragi_tip.dll",
            "BrokerSource": r"C:\Users\O'Brien\AppData\Local\yuragi-ime\versions\v0.2.0\download\yuragi-broker.exe",
            "ResultFile": "",
        }
        with tempfile.TemporaryDirectory() as tmp:
            result = Path(tmp) / "result dir" / "r.json"
            result.parent.mkdir()
            odd["ResultFile"] = str(result)
            fake = Path(tmp) / "O'Brien の script" / "elevated.ps1"
            fake.parent.mkdir()
            fake.write_text("param([string]$Action, [string]$ResultFile, [string]$Tag, "
                            "[string]$DllSource, [string]$BrokerSource)\n"
                            "[IO.File]::WriteAllText($ResultFile, ($PSBoundParameters | ConvertTo-Json))",
                            encoding="utf-8-sig")
            for script in ("setup.ps1", "uninstall.ps1"):
                with self.subTest(script=script):
                    func = function_text(ROOT / "packaging" / script, "New-ElevatedCommand")
                    args = ["-Action", "install"]
                    for key, value in odd.items():
                        args += [f"-{key}", value]
                    listed = ", ".join("'" + a.replace("'", "''") + "'" for a in args)
                    path_quoted = str(fake).replace("'", "''")
                    encoded = pwsh(f"{func}\nNew-ElevatedCommand '{path_quoted}' @({listed})").strip()
                    command = base64.b64decode(encoded).decode("utf-16-le")
                    self.assertTrue(command.startswith("& '"))
                    run = subprocess.run([PWSH, "-NoProfile", "-ExecutionPolicy", "Bypass",
                                          "-EncodedCommand", encoded],
                                         capture_output=True, text=True, timeout=120)
                    self.assertEqual(run.returncode, 0, run.stderr)
                    got = json.loads(result.read_text(encoding="utf-8-sig"))
                    self.assertEqual(got, {"Action": "install", **odd})
                    result.unlink()


if __name__ == "__main__":
    unittest.main()
