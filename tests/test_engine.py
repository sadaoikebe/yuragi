"""REDESIGN §6 / §10 stage 1: the engine process, run as the broker runs it.

Each test starts ``python -m yuragi.engine`` with pipes and the broker's
environment, and talks the line protocol. The real dictionary is used (as for
the other session tests); the LM is used when torch and the model are
present, otherwise the engine reports the "lm" warning and converts without it.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from yuragi.lattice import mozc_dict

ROOT = Path(__file__).resolve().parents[1]
START_TIMEOUT = 300  # a cache rebuild on a slow machine
VK_KA = 0x57  # NICOLA-A plain face か


def broker_environment(extra=None) -> dict:
    """As the broker builds it (§5.3): the user's environment, plus four, minus two."""
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
    env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8", PYTHONNOUSERSITE="1",
               HF_HUB_OFFLINE="1")
    env.update(extra or {})
    return env


class EngineProcess:
    def __init__(self, data_dir: Path, *args, command=None, env=None, cwd=ROOT):
        command = command or [sys.executable, "-m", "yuragi.engine"]
        self.proc = subprocess.Popen(
            [*command, "--data-dir", str(data_dir), *map(str, args)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=cwd, env=broker_environment(env))
        self.lines: queue.Queue = queue.Queue()
        self.stderr: list[str] = []
        self.seq = 0
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._read_err, daemon=True).start()

    def _read(self):
        for raw in self.proc.stdout:
            self.lines.put(json.loads(raw))  # every stdout line must be protocol JSON
        self.lines.put(None)

    def _read_err(self):
        for raw in self.proc.stderr:
            self.stderr.append(raw.decode("utf-8", "replace"))

    def next(self, timeout=30):
        return self.lines.get(timeout=timeout)

    def wait_ready(self) -> tuple[dict, list[dict]]:
        """The ready line, and what came before it."""
        before = []
        while True:
            line = self.next(START_TIMEOUT)
            if line is None:
                raise AssertionError("engine exited before ready:\n" + self.log())
            if line.get("ready"):
                return line, before
            before.append(line)

    def send(self, msg: dict) -> None:
        self.proc.stdin.write((json.dumps(msg) + "\n").encode("utf-8"))
        self.proc.stdin.flush()

    def request(self, sid: int, msg: dict) -> dict:
        self.seq += 1
        self.send({"sid": sid, "seq": self.seq, **msg})
        while True:
            reply = self.next()
            if reply is None:
                raise AssertionError("engine exited:\n" + self.log())
            if "seq" in reply:
                assert (reply["sid"], reply["seq"]) == (sid, self.seq), reply
                return reply

    def tap(self, sid: int, vk: int, t: int) -> dict:
        self.request(sid, {"op": "down", "vk": vk, "t": t})
        return self.request(sid, {"op": "up", "vk": vk, "t": t + 20})

    def close(self, timeout=60) -> int:
        self.proc.stdin.close()
        code = self.proc.wait(timeout)
        return code

    def log(self) -> str:
        time.sleep(0.2)
        return "".join(self.stderr)

    def kill(self):
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait()
        for stream in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            try:
                stream.close()
            except OSError:
                pass  # stdin of a process that already exited


class EngineCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.data = self.tmp / "data"
        self.data.mkdir()

    def start(self, *args, **kwargs) -> EngineProcess:
        engine = EngineProcess(self.data, *args, **kwargs)
        self.addCleanup(engine.kill)
        return engine

    def write_config(self, values: dict) -> None:
        (self.data / "config.json").write_text(json.dumps(values), encoding="utf-8")


class CacheTest(EngineCase):
    def test_zero_byte_cache_is_rebuilt(self):
        cache = self.tmp / "cache"
        cache.mkdir()
        (cache / mozc_dict.CACHE.name).write_bytes(b"")
        engine = self.start("--cache-dir", cache)
        engine.wait_ready()
        self.assertGreater((cache / mozc_dict.CACHE.name).stat().st_size, 1_000_000)
        self.assertEqual(list(cache.glob("*.tmp")), [])
        self.assertIn("dictionary cache unreadable", engine.log())
        engine.send({"op": "open", "sid": 1})
        self.assertEqual(engine.tap(1, VK_KA, 0)["composition"], "か")
        self.assertEqual(engine.close(), 0)


if __name__ == "__main__":
    unittest.main()
