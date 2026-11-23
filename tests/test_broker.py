"""The built broker with a fake engine and a fake TIP, as processes.

Windows only: YURAGI_BROKER names the built yuragi-broker.exe (without it the tests
skip, except under CI, which builds one), and the TIP
side is the named pipe. The broker's decisions are tested on every OS by
src/broker/tests/broker_core_test.cpp with a fake platform.
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

import runpy

WINDOWS = sys.platform == "win32"

ROOT = Path(__file__).resolve().parents[1]
FAKE_ENGINE = ROOT / "src" / "broker" / "tests" / "fake_engine.py"
birth = runpy.run_path(str(FAKE_ENGINE))["birth"]

# The longest any wait goes on. Every wait ends as soon as what it waits for has
# happened; this is only how long a slow machine (a shared CI runner starts and
# ends processes many times slower than a desktop) is given before a test fails.
WAIT = 60.0


def broker_binary() -> Path:
    return Path(os.environ["YURAGI_BROKER"])


def skip_without_broker():
    """Without a built broker the tests skip; CI builds one, so there it is a failure."""
    if not WINDOWS:
        return unittest.skip("the broker runs on Windows (src/broker/platform_win.cpp)")
    if os.environ.get("YURAGI_BROKER"):
        return lambda case: case
    if os.environ.get("CI"):
        raise AssertionError("set YURAGI_BROKER to the built yuragi-broker.exe")
    return unittest.skip("set YURAGI_BROKER to the built yuragi-broker.exe")


def alive(pid: int, born: int) -> bool:
    """That process (as the fake engine recorded it) has not exited."""
    return birth(pid) == born


def wait_until(predicate, timeout=WAIT, interval=0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    raise AssertionError("timed out waiting")


class Connection:
    """The TIP's end: the named pipe.

    A synchronous pipe handle runs one operation at a time, so the reader only
    reads what PeekNamedPipe says is there (a blocked read would hold up every
    write)."""

    def __init__(self, address: str):
        import _winapi
        import msvcrt
        self.file = open(address, "r+b", buffering=0)
        self.handle = msvcrt.get_osfhandle(self.file.fileno())
        self.peek = _winapi.PeekNamedPipe

    def recv(self) -> bytes:
        while True:
            try:
                available = self.peek(self.handle)[0]
                if available:
                    return self.file.read(available)
            except OSError:
                return b""
            time.sleep(0.005)

    def send(self, data: bytes) -> None:
        self.file.write(data)

    def close(self) -> None:
        self.file.close()


class FakeTip:
    """A TIP: one connection, one line of JSON per message."""

    def __init__(self, address: str):
        self.connection = Connection(address)
        self.lines: queue.Queue = queue.Queue()
        self.seen: list[dict] = []
        self.state = None  # as last told: the hello reply or a state event
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        buffer = b""
        while True:
            chunk = self.connection.recv()
            if not chunk:
                self.lines.put(None)
                return
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                self.lines.put(json.loads(line))

    def send(self, msg: dict) -> None:
        self.connection.send((json.dumps(msg) + "\n").encode("utf-8"))

    def next(self, timeout=WAIT):
        line = self.lines.get(timeout=timeout)
        if line is not None:
            self.seen.append(line)
            if line.get("event") == "state" or "proto" in line:
                self.state = line["state"]
        return line

    def wait_for(self, predicate, timeout=WAIT) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            line = self.next(max(0.01, deadline - time.monotonic()))
            if line is None:
                raise AssertionError("the broker closed the connection")
            if predicate(line):
                return line

    def hello(self) -> dict:
        self.send({"op": "hello", "proto": 1})
        return self.next()

    def wait_state(self, state: str, timeout=WAIT) -> None:
        """Until the broker has said the state is this (now or before)."""
        if self.state != state:
            self.wait_for(lambda m: self.state == state, timeout)

    def key(self, seq: int, vk: int = 74, op: str = "down") -> None:
        self.send({"seq": seq, "op": op, "vk": vk, "t": seq * 100, "mods": []})

    def reply(self, seq: int, timeout=WAIT) -> dict:
        return self.wait_for(lambda m: m.get("seq") == seq, timeout)

    def close(self):
        self.connection.close()


@skip_without_broker()
class BrokerCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.data = self.dir / "data"
        self.state = self.dir / "engine-state"
        self.state.mkdir()
        self.address = rf"\\.\pipe\yuragi-ime-test-{os.getpid()}-{id(self)}"
        self.engine_json = self.dir / "engine.json"
        self.tips: list[FakeTip] = []

    def plan(self, *modes) -> None:
        (self.state / "plan.json").write_text(json.dumps(list(modes)), encoding="utf-8")
        self.write_engine_json([str(FAKE_ENGINE), str(self.state)])

    def write_engine_json(self, args, app=None, python=sys.executable):
        self.engine_json.write_text(json.dumps({
            "python": python, "pythonw": python,
            "app": str(app or self.dir), "args": args, "admin_args": []}), encoding="utf-8")

    def start(self) -> subprocess.Popen:
        argv = [str(broker_binary()), "--data-dir", str(self.data), "--pipe", self.address,
                "--engine-json", str(self.engine_json)]
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(self.stop, proc)
        return proc

    def stop(self, proc):
        for tip in self.tips:
            tip.close()
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        for stream in (proc.stdout, proc.stderr):
            stream.close()
        # The job object ends the engines with the broker; they run in the
        # temporary folder, which cannot be removed until they have.
        wait_until(lambda: not any(alive(*p) for p in self.engines()))

    def tip(self) -> FakeTip:
        def connect():
            try:
                return FakeTip(self.address)
            except OSError:  # the broker is not listening yet
                return None
        tip = wait_until(connect)
        self.tips.append(tip)
        return tip

    def engines(self) -> list[tuple[int, int]]:
        """The engines the fake engine wrote down: (pid, birth)."""
        path = self.state / "starts"
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        return [tuple(map(int, line.split())) for line in lines]

    def starts(self) -> int:
        return len(self.engines())

    def log(self) -> str:
        path = self.data / "logs" / "broker.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""


class ProcessTest(BrokerCase):
    def test_conversion_recovers_after_an_oversized_engine_ready_message(self):
        self.plan("oversized_ready", "normal")
        self.start()
        tip = self.tip()
        tip.hello()
        tip.wait_state("ready")
        self.assertEqual(self.starts(), 2)
        tip.key(1)
        self.assertEqual(tip.reply(1)["composition"], "down:74")

    def test_one_broker_per_user(self):
        self.plan("normal")
        self.start()
        tip = self.tip()
        tip.hello()
        tip.wait_state("ready")  # the first broker's engine has started and is counted
        second = subprocess.run([str(broker_binary()), "--data-dir", str(self.data),
                                 "--pipe", self.address + "-other",
                                 "--engine-json", str(self.engine_json)], timeout=WAIT)
        self.assertEqual(second.returncode, 0)
        self.assertEqual(self.starts(), 1)

    def test_quit_ends_broker_and_engine(self):
        self.plan("normal")
        proc = self.start()
        tip = self.tip()
        tip.hello()
        tip.wait_state("ready")
        tip.send({"op": "quit"})
        self.assertEqual(proc.wait(timeout=WAIT), 0)


class SelfTestTest(BrokerCase):
    def test_real_engine_converts(self):
        """--selftest with the real engine (no LM), as the installer runs it."""
        data = self.dir / "user"
        data.mkdir()
        (data / "config.json").write_text('{"lm_rescore": false}', encoding="utf-8")
        self.write_engine_json(["-m", "yuragi.engine", "--data-dir", str(data)], app=ROOT)
        self.assert_selftest_converts()

    def test_conversion_completes_after_a_timer(self):
        self.plan("pending_conversion")
        self.assert_selftest_converts()

    def assert_selftest_converts(self):
        result = subprocess.run([str(broker_binary()), "--data-dir", str(self.data),
                                 "--selftest", str(self.engine_json)],
                                capture_output=True, text=True, timeout=600)
        self.assertEqual(result.returncode, 0, result.stdout + self.log())
        self.assertIn("selftest passed", result.stdout)
        self.assertIn("selftest: converted", self.log())


if __name__ == "__main__":
    unittest.main()
