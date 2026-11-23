"""The engine's waiting on its input must not stall the LM worker's DLL loads.

On Windows, while a thread waits on a synchronous read of the stdin pipe,
loading numpy's OpenBLAS (torch's import) on another thread stalls until a
message arrives. With nobody typing after sign-in the LM then never loaded.
engine.Channel reserves the pipe and leaves NUL as the standard input.
Windows only, and only where torch is installed (the dev environment).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import queue
import subprocess
import sys
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHILD = """
import sys, threading
from yuragi.engine import Channel
channel = Channel()
def load():
    import torch  # noqa: F401
    print("loaded", file=sys.stderr, flush=True)
threading.Thread(target=load, daemon=True).start()
channel.input.read(1)  # waits on the pipe, as Engine.serve does
"""


@unittest.skipUnless(sys.platform == "win32", "the stall is a Windows pipe behaviour")
@unittest.skipUnless(importlib.util.find_spec("torch"), "needs torch")
class IdleInputTest(unittest.TestCase):
    def test_torch_loads_while_the_input_is_idle(self):
        # Leaving the with block closes the pipes (after the reader has seen their end).
        with subprocess.Popen([sys.executable, "-c", CHILD], cwd=ROOT,
                              stdin=subprocess.PIPE, stderr=subprocess.PIPE) as child:
            lines = queue.Queue()
            reader = threading.Thread(target=lambda: [lines.put(line) for line in child.stderr],
                                      daemon=True)
            reader.start()
            try:
                # stdin stays open and silent the whole time, as when nobody types.
                while True:
                    try:
                        line = lines.get(timeout=60)
                    except queue.Empty:
                        self.fail("torch did not load while the engine waited on its input")
                    if line.strip() == b"loaded":
                        break
            finally:
                child.kill()
                child.wait()
                reader.join(timeout=10)


if __name__ == "__main__":
    unittest.main()
