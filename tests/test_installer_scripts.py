"""DESIGN「インストール・更新・アンインストール」: what can be checked of the installer scripts without Windows.

- The elevated part gets exactly the arguments setup/uninstall meant, however
  odd the paths (spaces, quotes, Japanese; its own path too): the
  -EncodedCommand round trip.
- The workflow steps that run in Windows PowerShell 5.1 are ASCII (it reads
  them as ANSI: one Japanese character can end a string and break the step).

pwsh runs the rest (GitHub's Ubuntu runners have it; YURAGI_PWSH names another).
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
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

    def test_torch_variant_from_nvidia_smi(self):
        """setup.ps1 picks the CUDA build of torch only for a GPU and driver it supports."""
        func = function_text(ROOT / "packaging" / "setup.ps1", "Select-TorchVariant")
        header = "| NVIDIA-SMI 572.16   Driver Version: 572.16   CUDA Version: {} |"
        cases = [
            (header.format("12.8"), ["NVIDIA GeForce RTX 4060 Laptop GPU, 8.9"], "cu128"),
            (header.format("13.0"), ["NVIDIA GeForce RTX 5070, 12.0"], "cu128"),
            (header.format("12.6"), ["NVIDIA GeForce RTX 3060, 8.6"], "cu126"),
            (header.format("12.6"), ["NVIDIA GeForce RTX 5070, 12.0", "NVIDIA RTX A2000, 8.6"], "cu126"),
            (header.format("12.8"), ["NVIDIA GeForce GTX 1060, 6.1"], "cu126"),  # cu128 has no Pascal
            (header.format("12.4"), ["NVIDIA GeForce RTX 3060, 8.6"], "cpu"),  # old driver
            (header.format("12.8"), ["NVIDIA GeForce GTX 750 Ti, 5.0"], "cpu"),
            (header.format("12.8"), ["NVIDIA GeForce RTX 4060, [N/A]"], "cpu"),
            (header.format("12.8"), [], "cpu"),
            ("", ["NVIDIA GeForce RTX 4060, 8.9"], "cpu"),
            (header.format("12.8"), ["Quadro P1000, 6.1", "NVIDIA RTX A2000, 8.6"], "cu128"),
        ]
        for smi_header, gpus, expected in cases:
            with self.subTest(header=smi_header, gpus=gpus):
                listed = ", ".join("'" + g.replace("'", "''") + "'" for g in gpus)
                got = pwsh(f"{func}\nSelect-TorchVariant '{smi_header}' @({listed})").strip()
                self.assertEqual(got, expected)

    @unittest.skipIf(os.name == "nt", "the stand-in nvidia-smi is a shell script")
    def test_torch_variant_runs_nvidia_smi(self):
        """Get-TorchVariant: no nvidia-smi, a failing one, and a working one."""
        func = function_text(ROOT / "packaging" / "setup.ps1", "Get-TorchVariant")
        select = function_text(ROOT / "packaging" / "setup.ps1", "Select-TorchVariant")
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            env = dict(os.environ, SystemRoot=tmp, ProgramFiles=tmp,
                       PATH=f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
            smi = bin_dir / "nvidia-smi.exe"

            def run():
                result = subprocess.run(
                    [PWSH, "-NoProfile", "-NonInteractive", "-Command",
                     f"{select}\n{func}\nGet-TorchVariant"],
                    capture_output=True, text=True, timeout=120, env=env)
                self.assertEqual(result.returncode, 0, result.stderr)
                return result.stdout.strip()

            self.assertEqual(run(), "cpu")  # no NVIDIA driver
            smi.write_text("#!/bin/sh\necho 'no devices were found' >&2\nexit 6\n")
            smi.chmod(0o755)
            self.assertEqual(run(), "cpu")
            smi.write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = \"--query-gpu=name,compute_cap\" ]; then\n"
                "  echo 'NVIDIA GeForce RTX 4060 Laptop GPU, 8.9'\n"
                "else\n"
                "  echo '| NVIDIA-SMI 572.16  Driver Version: 572.16  CUDA Version: 12.8 |'\n"
                "fi\n")
            self.assertEqual(run(), "cu128")


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
