"""DESIGN「インストール・更新・アンインストール」: what can be checked of the installer scripts without Windows.

- The elevated part gets exactly the arguments setup/uninstall meant, however
  odd the paths (spaces, quotes, Japanese; its own path too): the
  -EncodedCommand round trip.
- The workflow steps that run in Windows PowerShell 5.1 are ASCII (it reads
  them as ANSI: one Japanese character can end a string and break the step).

PowerShell runs the rest: the one YURAGI_PWSH names, else pwsh (GitHub's Ubuntu
runners have it), else Windows PowerShell 5.1 (powershell, what users run).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PWSH = os.environ.get("YURAGI_PWSH") or shutil.which("pwsh") or shutil.which("powershell")


def pwsh(script: str) -> str:
    result = subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-Command", script],
                            capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    return result.stdout


def ps_quote(text: str) -> str:
    """A PowerShell single-quoted string (it reads U+2018, U+2019, U+201A and U+201B as ' too)."""
    return "'" + "".join(c * 2 if c in "'\u2018\u2019\u201a\u201b" else c for c in text) + "'"


def function_text(path: Path, name: str) -> str:
    """One function's definition, taken from the script by PowerShell's own parser."""
    out = pwsh(
        f"$ast = [System.Management.Automation.Language.Parser]::ParseFile('{path}', [ref]$null, [ref]$null);"
        f"$ast.FindAll({{ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst]"
        f" -and $n.Name -eq '{name}' }}, $true)[0].Extent.Text")
    if not out.strip():
        raise AssertionError(f"{name} not found in {path}")
    return out


@unittest.skipIf(PWSH is None, "neither pwsh nor powershell is installed (set YURAGI_PWSH)")
class PowerShellTest(unittest.TestCase):
    def test_dev_registration_requires_lm_with_an_empty_model_cache(self):
        write_config = function_text(ROOT / "src/tip/dev-register.ps1", "Write-DevEngineConfig")
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            engine_json = data / "engine.json"
            quoted = ["'" + str(path).replace("'", "''") + "'"
                      for path in (engine_json, sys.executable, ROOT)]
            pwsh(f"{write_config}\nWrite-DevEngineConfig {' '.join(quoted)}")
            engine = json.loads(engine_json.read_text(encoding="utf-8"))
            (data / "config.json").write_text('{"lm_rescore": false}', encoding="utf-8")
            cache = str(data / "empty-hf-cache")
            env = dict(os.environ, HF_HOME=cache, HF_HUB_CACHE=cache, HUGGINGFACE_HUB_CACHE=cache,
                       TRANSFORMERS_CACHE=cache, HF_HUB_OFFLINE="1", PYTHONDONTWRITEBYTECODE="1")
            result = subprocess.run(
                [engine["python"], *engine["args"], "--data-dir", str(data)],
                cwd=engine["app"], input=b"", capture_output=True, env=env, timeout=120,
            )
            self.assertEqual(result.returncode, 1, result.stderr.decode("utf-8", errors="replace"))
            self.assertEqual(result.stdout, b"")
            self.assertIn(b"fatal lm-unavailable", result.stderr.splitlines())

    def test_elevated_arguments_survive_encoding(self):
        odd = {
            "Tag": "v0.2.0",
            # PowerShell reads U+2019 (and U+2018, U+201A, U+201B) as a single quote too.
            "DllSource": r"C:\Users\O’Brien; Write-Output INJECTED #\テスト user\versions\v0.2.0\download\yuragi_tip.dll",
            "BrokerSource": r"C:\Users\O'Brien\AppData\Local\yuragi-ime\versions\v0.2.0\download\yuragi-broker.exe",
            "ResultFile": "",
        }
        with tempfile.TemporaryDirectory() as tmp:
            result = Path(tmp) / "result dir" / "r.json"
            result.parent.mkdir()
            odd["ResultFile"] = str(result)
            fake = Path(tmp) / "O'Brien ’s の script" / "elevated.ps1"
            fake.parent.mkdir()
            fake.write_text("param([string]$Action, [string]$ResultFile, [string]$Tag, "
                            "[string]$DllSource, [string]$BrokerSource)\n"
                            "[IO.File]::WriteAllText($ResultFile, ($PSBoundParameters | ConvertTo-Json))",
                            encoding="utf-8-sig")
            def run(encoded):
                return subprocess.run([PWSH, "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
                                      capture_output=True, text=True, timeout=120)

            args = ["-Action", "install"]
            for key, value in odd.items():
                args += [f"-{key}", value]
            listed = ", ".join(ps_quote(a) for a in args)
            for script in ("setup.ps1", "uninstall.ps1"):
                with self.subTest(script=script):
                    func = function_text(ROOT / "packaging" / script, "New-ElevatedCommand")
                    # setup.ps1 runs only the content whose SHA-256 it took (the script is in a
                    # folder the user can write); uninstall.ps1 runs the copy in Program Files.
                    sha = ps_quote(hashlib.sha256(fake.read_bytes()).hexdigest().upper()) if script == "setup.ps1" else ""
                    encoded = pwsh(f"{func}\nNew-ElevatedCommand {ps_quote(str(fake))} {sha} @({listed})").strip()
                    done = run(encoded)
                    self.assertEqual(done.returncode, 0, done.stderr)
                    got = json.loads(result.read_text(encoding="utf-8-sig"))
                    self.assertEqual(got, {"Action": "install", **odd})
                    result.unlink()
                    if script == "setup.ps1":
                        # Changed between the check at stage 2 and the UAC prompt: it does not run.
                        fake.write_text(fake.read_text(encoding="utf-8-sig") + "\n# changed", encoding="utf-8-sig")
                        self.assertEqual(run(encoded).returncode, 3)
                        self.assertFalse(result.exists())


def powershell_steps(path: Path):
    """(name, script lines) of each workflow step with shell: powershell."""
    steps, step, block = [], None, None
    for line in path.read_text(encoding="utf-8").splitlines():
        indent = len(line) - len(line.lstrip())
        if block is not None:
            if not line.strip() or indent > block:
                step["run"].append(line)
                continue
            block = None
        key = line.strip()
        if key.startswith("- "):
            step = {"name": key[2:], "shell": None, "run": []}
            steps.append(step)
            key = key[2:]
        if step is None:
            continue
        if key.startswith("shell:"):
            step["shell"] = key.split(":", 1)[1].strip()
        elif key.startswith("run:"):
            block = indent if key.endswith("|") else None
            step["run"].append(key[4:])
    return [(s["name"], s["run"]) for s in steps if s["shell"] == "powershell"]


class WorkflowTest(unittest.TestCase):
    def test_windows_powershell_steps_are_ascii(self):
        checked = 0
        for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
            for name, script in powershell_steps(path):
                checked += 1
                self.assertEqual([l for l in script if not l.isascii()], [], f"{path.name}: {name}")
        self.assertGreater(checked, 0)


if __name__ == "__main__":
    unittest.main()
