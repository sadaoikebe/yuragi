"""The engine's sessions, in process (DESIGN「エンジン」).

One engine serves every TIP connection: the dictionary, the face table, the
learning history and the word list are loaded once and shared; each sid has
its own session (chord FSM, composition, input mode, left context) and, with
the LM, its own pipeline.
"""
from __future__ import annotations

from argparse import Namespace
import json
from pathlib import Path
import tempfile
import time
import unittest

from yuragi.engine import Engine
from yuragi.ime.lm_async import LmWorker
from yuragi.ime.lm_rescore import LmRescorer
from yuragi.ime.session import ImeSession
from yuragi.lattice.mozc_dict import Entry, MozcLex
from yuragi.lattice.table import load_table

SETTINGS = Namespace(lm_grace_ms=30, lm_deadline_ms=400, lm_prefetch="thumb",
                     lm_prefetch_delay_ms=30)


def loaded_session():
    # A has plain=う. A confirmation of the initially second row must change the best.
    lex = MozcLex({"う": [Entry("宇", "う", 1, 1, 100), Entry("卯", "う", 1, 1, 200)]},
                  {"う"}, [0] * 4, 2)
    session = ImeSession(_table=load_table(), _lex=lex)
    session.load()
    return session


class Channel:
    def __init__(self):
        self.warnings = []

    def warning(self, code):
        self.warnings.append(code)

    def send(self, message):
        raise AssertionError("requests are answered by Engine.request in these tests")


class EngineCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.seq = 0

    def engine(self, loaded=None, worker=None, settings=SETTINGS):
        engine = Engine(Channel(), Namespace())
        engine.loaded = loaded or loaded_session()
        engine.worker = worker
        engine.settings = settings
        return engine

    def open(self, engine, sid):
        engine.serve([json.dumps({"op": "open", "sid": sid}).encode()])

    def request(self, engine, sid, msg):
        self.seq += 1
        reply = engine.request({"sid": sid, "seq": self.seq, **msg})
        self.assertEqual((reply["sid"], reply["seq"]), (sid, self.seq))
        return reply

    def type_a(self, engine, sid, t=0):
        self.request(engine, sid, {"op": "down", "vk": 65, "t": t})
        return self.request(engine, sid, {"op": "up", "vk": 65, "t": t + 30})


class SlowScorer:
    """Prefers 卯 over the Viterbi 宇; each call sleeps (a slow model)."""

    def __init__(self, sleep=0.2):
        self.sleep = sleep

    def nll(self, context, candidates):
        time.sleep(self.sleep)
        return [0.0 if c.startswith("卯") else 10.0 for c in candidates]


class LmPipelineTest(EngineCase):
    """The LM pipeline (lm_async.py), through the engine's sessions."""

    def wait_state(self, worker, state):
        deadline = time.monotonic() + 5
        while worker.state != state and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(worker.state, state)

    def test_pending_reply_then_poll_then_replay(self):
        loaded = loaded_session()
        worker = LmWorker(lambda: LmRescorer(SlowScorer()), loaded._lex)
        self.wait_state(worker, "ready")
        engine = self.engine(loaded, worker)
        self.open(engine, 1)
        self.type_a(engine, 1)
        self.request(engine, 1, {"op": "down", "vk": 32, "t": 100})
        start = time.monotonic()
        reply = self.request(engine, 1, {"op": "up", "vk": 32, "t": 130})
        self.assertLess(time.monotonic() - start, 0.1)  # the engine answers at once
        self.assertEqual((reply["pending"], reply["converted"], reply["composition"],
                          reply["candidates"], reply["timer"]), (True, False, "宇", [], 140))
        t = 130
        while reply["pending"]:
            time.sleep(0.016)
            t += 16
            reply = self.request(engine, 1, {"op": "timeout", "t": t})
        self.assertEqual((reply["converted"], reply["composition"]), (True, "卯"))
        self.assertEqual(self.request(engine, 1, {"op": "down", "vk": 13, "t": 900})["commit"], "卯")
        # A key typed while the next conversion is pending waits behind it.
        self.type_a(engine, 1, 1000)
        self.request(engine, 1, {"op": "down", "vk": 32, "t": 1100})
        self.assertTrue(self.request(engine, 1, {"op": "up", "vk": 32, "t": 1130})["pending"])
        reply = self.type_a(engine, 1, 1140)
        self.assertEqual((reply["pending"], reply["composition"], reply["commit"]), (True, "宇", ""))
        t = 1200
        while reply["pending"]:
            time.sleep(0.016)
            reply = self.request(engine, 1, {"op": "timeout", "t": t})
            t += 16
        self.assertEqual((reply["commit"], reply["composition"], reply["converted"]),
                         ("卯", "宇", False))

if __name__ == "__main__":
    unittest.main()
