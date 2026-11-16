"""Resident LM pipeline: the IME never hangs on a slow, broken or stalled LM.
Fake scorers, no torch.

The deadline (400 ms) falls back to the dictionary-only conversion, an overflowing
queue stops the wait, reset / input-mode switch / disconnect drop what is pending,
and the worker survives model exceptions and stalls.
"""
from __future__ import annotations

from dataclasses import replace
import threading
import time
import unittest

from yuragi.chord.keys import VK_TO_M
from yuragi.ime.lm_async import ConnectionPipeline, Job, LmStats, LmWorker
from yuragi.ime.lm_rescore import LmRescorer, conversion_picks
from yuragi.ime.server import dispatch
from yuragi.ime.session import ImeSession
from yuragi.lattice.mozc_dict import Entry, MozcLex
from yuragi.lattice.table import load_table, reverse_table
from tests.real_dictionary import real_lex

# Up of an unclassified key: a no-op for every session state. Sent last to both
# sides so the subject has one request in which to resolve what is still pending.
TERMINAL = {"op": "up", "vk": 0x7B}
VK_SPACE, VK_RETURN = 0x20, 0x0D


class PickyScorer:
    """Deterministic, context-dependent NLL that often overrides the 1-best."""

    def __init__(self):
        self.calls: list[tuple[str, list[str]]] = []

    def nll(self, context, candidates):
        self.calls.append((context, list(candidates)))
        return [sum(ord(ch) % 7 for ch in c) * 0.7 + (len(context) % 3) * len(c)
                for c in candidates]


class ManualWorker:
    """LmWorker's interface; the test decides when each wanted job completes."""

    def __init__(self, lex, scorer, delay=lambda index: 0, eager_prefetch=False):
        self.lex = lex
        self.template = LmRescorer(scorer)
        self.delay = delay  # conversion index -> completes before the Nth later request
        self.eager_prefetch = eager_prefetch
        self.stats = LmStats()
        self.ready = True
        self.jobs: list[Job] = []
        self.countdown: dict[int, int] = {}
        self.conversions = 0
        self.draining = False  # complete_all(): later conversions complete at once too

    def available(self):
        return self.ready

    def submit(self, job):
        self.jobs.append(job)
        if job.wanted:
            self._schedule(job)
        elif job.kind == "prime" or self.eager_prefetch:
            self.complete(job)

    def promote(self, job, deadline):
        job.wanted, job.deadline = True, deadline
        if not job.done.is_set():
            self._schedule(job)

    def cancel_owner(self, owner):
        for job in self.jobs:
            if job.owner is owner and not job.done.is_set():
                job.cancelled = True

    def _schedule(self, job):
        n = self.delay(self.conversions)
        self.conversions += 1
        if n == 0 or self.draining:
            self.complete(job)
        else:
            self.countdown[id(job)] = n

    def complete(self, job):
        if job.done.is_set():
            return
        if job.kind == "convert" and not job.cancelled:
            r = job.request
            job.picks = conversion_picks(r.parts, self.lex, r.learning, r.left_surface,
                                         r.lm_context, replace(self.template, last={}),
                                         cancelled=lambda: job.cancelled)
        job.done.set()

    def tick(self):
        """Called before each request."""
        for job in self.jobs:
            if id(job) in self.countdown:
                self.countdown[id(job)] -= 1
                if self.countdown[id(job)] == 0:
                    del self.countdown[id(job)]
                    self.complete(job)

    def complete_all(self):
        self.draining = True
        for job in self.jobs:
            if job.wanted:
                self.complete(job)
        self.countdown.clear()


def final_state(reply: dict) -> dict:
    return {k: v for k, v in reply.items() if k not in ("pending", "timer", "commit")}


def run_reference(new_session, events, scorer):
    sess = new_session()
    sess.lm = LmRescorer(scorer) if scorer is not None else None
    commits = ""
    for event in events + [TERMINAL]:
        reply = dispatch(sess, dict(event))
        commits += reply["commit"]
    return commits, final_state(reply)


class Typist:
    """Timed key events for kana text on NICOLA-A (US VKs)."""

    def __init__(self):
        self.reverse = reverse_table(load_table())
        self.vk = {key: vk for vk, key in VK_TO_M.items()}
        self.t = 0
        self.events: list[dict] = []

    def at(self, gap):
        self.t += gap
        return self.t

    def key(self, op, vk, gap=0, **extra):
        self.events.append({"op": op, "vk": vk, "t": self.at(gap), **extra})
        return self

    def tap(self, vk, gap=150, hold=30):
        return self.key("down", vk, gap).key("up", vk, hold)

    def kana(self, text, gap=150):
        for ch in text:
            token = self.reverse[ch]
            vk = self.vk[token["key"]]
            if token["kind"] == "plain":
                self.tap(vk, gap)
            else:  # chord with the thumb: thumb 10 ms after, letter released first
                self.key("down", vk, gap).key("down", VK_SPACE, 10)
                self.key("up", vk, 30).key("up", VK_SPACE, 5)
        return self

    def space(self, gap=150, hold=40):
        return self.tap(VK_SPACE, gap, hold)

    def timeout(self, gap):
        self.events.append({"op": "timeout", "t": self.at(gap)})
        return self


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class DeadlineAndAbandonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lex = real_lex()

    def session(self):
        return ImeSession(_table=load_table(), _lex=self.lex, learning_path=None)

    def pipeline(self, **kwargs):
        sess = self.session()
        worker = ManualWorker(self.lex, PickyScorer(), delay=lambda i: 10 ** 6)
        clock = Clock()
        return ConnectionPipeline(sess, worker, grace_ms=0, clock=clock, **kwargs), worker, clock

    def test_deadline_falls_back_to_viterbi(self):
        typist = Typist().kana("きしゃ").space()
        head = list(typist.events)
        tail = Typist()
        tail.t = typist.t
        tail.kana("かいせい", gap=20).tap(VK_RETURN)
        pipe, worker, clock = self.pipeline()
        commits = ""
        for event in head:
            commits += pipe.handle(dict(event))["commit"]
        self.assertTrue(pipe.sess._await is not None)
        job = pipe.job
        for event in tail.events[:3]:  # still pending: keys queue up
            reply = pipe.handle(dict(event))
            self.assertTrue(reply["pending"])
            self.assertEqual(reply["timer"], min(reply["timer"], event["t"] + 10))
        clock.now += 0.4
        for event in tail.events[3:] + [TERMINAL]:
            reply = pipe.handle(dict(event))
            commits += reply["commit"]
        self.assertTrue(job.cancelled)
        self.assertEqual(pipe.stats.conversions["timeout"], 1)
        worker.complete_all()  # a late result changes nothing
        self.assertFalse(pipe.handle({"op": "timeout", "t": 0})["pending"])
        expected = run_reference(self.session, head + tail.events, None)
        self.assertEqual((commits, final_state(reply)), expected)
        self.assertNotEqual(expected, run_reference(self.session, head + tail.events,
                                                    PickyScorer()))

    def test_queue_overflow_falls_back(self):
        events = Typist().kana("きしゃ").space().kana("こうせいする", gap=20).tap(VK_RETURN).events
        pipe, worker, clock = self.pipeline(max_queue=3)
        commits = ""
        for event in events + [TERMINAL]:
            reply = pipe.handle(dict(event))
            commits += reply["commit"]
        self.assertEqual(pipe.stats.conversions["timeout"], 1)
        self.assertEqual((commits, final_state(reply)),
                         run_reference(self.session, events, None))

    def test_reset_toggle_and_disconnect_abandon(self):
        for op in ({"op": "reset"}, {"op": "toggle_direct"}, "close"):
            with self.subTest(op=op):
                pipe, worker, clock = self.pipeline()
                for event in Typist().kana("きしゃ").space().kana("こう", gap=20).events:
                    pipe.handle(dict(event))
                job = pipe.job
                self.assertTrue(pipe.queue)
                if op == "close":
                    pipe.close()
                    self.assertTrue(job.cancelled)
                    continue
                reply = pipe.handle(op)
                self.assertTrue(job.cancelled)
                self.assertFalse(pipe.queue)
                self.assertFalse(reply["pending"])
                self.assertEqual((reply["composition"], reply["commit"], reply["n_tokens"]),
                                 ("", "", 0))
                worker.complete_all()  # completing afterwards does nothing
                reply = pipe.handle({"op": "timeout", "t": 10 ** 6})
                self.assertEqual((reply["composition"], reply["commit"], reply["pending"]),
                                 ("", "", False))
                self.assertIsNone(pipe.sess._await)


def small_lex():
    lex = MozcLex({"う": [Entry("宇", "う", 1, 1, 100), Entry("卯", "う", 1, 1, 200)]},
                  {"う"}, [0] * 4, 2)
    return lex


class Recording:
    """Scorer stand-in for LmWorker tests; prime is optional."""

    def __init__(self, preferred="卯", gate: threading.Event | None = None,
                 fail: bool = False, sleep: float = 0):
        self.preferred = preferred
        self.gate = gate
        self.fail = fail
        self.sleep = sleep
        self.calls: list[str] = []

    def nll(self, context, candidates):
        self.calls.append("nll:" + context)
        if self.sleep:
            time.sleep(self.sleep)
        if self.fail and context:
            raise RuntimeError("model failure")
        return [0.0 if c == self.preferred else 10.0 for c in candidates]

    def prime(self, context):
        self.calls.append("prime:" + context)
        if self.gate is not None:
            self.gate.wait(5)


def ready_worker(scorer, **kwargs):
    worker = LmWorker(lambda: LmRescorer(scorer), small_lex(), **kwargs)
    deadline = time.monotonic() + 5
    while worker.state == "loading" and time.monotonic() < deadline:
        time.sleep(0.005)
    scorer.calls.clear()
    return worker


def u_request(context="上"):
    sess = ImeSession(_table=load_table(), _lex=small_lex(), learning_path=None)
    sess.on_key(True, 0x41, 0)
    sess.on_key(False, 0x41, 30)
    sess._lm_context = context
    return sess.conversion_request()


class LmWorkerTest(unittest.TestCase):
    def test_three_errors_disable(self):
        scorer = Recording(fail=True)
        worker = ready_worker(scorer)
        owner = object()
        for i in range(3):
            self.assertTrue(worker.available())
            job = Job("convert", owner, u_request(f"文{i}"), wanted=True)
            worker.submit(job)
            self.assertTrue(job.done.wait(2))
            self.assertTrue(job.error)
        self.assertEqual(worker.state, "disabled")
        self.assertFalse(worker.available())

    def test_stalled_job_makes_worker_unavailable(self):
        gate = threading.Event()
        scorer = Recording(gate=gate)
        worker = ready_worker(scorer, stall_ms=50)
        job = Job("prime", object(), None, context="x")
        worker.submit(job)
        time.sleep(0.1)
        self.assertFalse(worker.available())
        gate.set()
        self.assertTrue(job.done.wait(2))
        self.assertTrue(worker.available())


if __name__ == "__main__":
    unittest.main()
