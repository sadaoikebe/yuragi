"""Resident LM pipeline: the IME never hangs on a slow LM. A fake model, no torch.

A conversion waits for the LM's picks. The deadline (DEADLINE_MS) only detects
a fault: it is logged and falls back to the dictionary-only conversion, the
same as converting without the LM.
"""
from __future__ import annotations

from contextlib import redirect_stderr
from dataclasses import replace
import io
import unittest

from yuragi.chord.keys import VK_TO_M
from yuragi.ime.lm_async import DEADLINE_MS, ConnectionPipeline, Job
from yuragi.ime.zenz import ZenzConverter, conversion_picks
from yuragi.ime.server import dispatch
from yuragi.ime.session import ImeSession
from yuragi.lattice.table import load_table, reverse_table
from tests.real_dictionary import real_lex

# Up of an unclassified key: a no-op for every session state. Sent last to both
# sides so the subject has one request in which to resolve what is still pending.
TERMINAL = {"op": "up", "vk": 0x7B}
VK_SPACE, VK_RETURN = 0x20, 0x0D


class PickyModel:
    """Deterministic, context-dependent zenz stand-in that often overrides the 1-best."""

    def reading_nll(self, readings):
        return [sum(ord(ch) % 7 for ch in r) * 0.7 for r in readings]

    def review(self, context, reading, draft, accepted):
        # Wants the run to start in kana, except under some contexts.
        if len(context) % 3 == 2 or draft.startswith(reading[0]):
            return None
        return reading[0].encode(), False


class ManualWorker:
    """LmWorker's interface; the test decides when each wanted job completes."""

    def __init__(self, lex, model, delay=lambda index: 0, eager_prefetch=False):
        self.lex = lex
        self.template = ZenzConverter(model)
        self.delay = delay  # conversion index -> completes before the Nth later request
        self.eager_prefetch = eager_prefetch
        self.ready = True
        self.jobs: list[Job] = []
        self.countdown: dict[int, int] = {}
        self.conversions = 0
        self.clock = Clock()
        self.draining = False  # complete_all(): later conversions complete at once too

    def available(self):
        return self.ready

    def submit(self, job):
        self.jobs.append(job)
        if job.wanted:
            self._schedule(job)
        elif self.eager_prefetch:
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
        if not job.cancelled:
            r = job.request
            job.picks = conversion_picks(r.parts, self.lex, r.learning, r.lm_context,
                                         replace(self.template, last={}),
                                         cancelled=lambda: job.cancelled)
        job.completed_at = self.clock()
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


def run_reference(new_session, events, model):
    sess = new_session()
    sess.lm = ZenzConverter(model) if model is not None else None
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


class DeadlineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lex = real_lex()

    def session(self):
        return ImeSession(_table=load_table(), _lex=self.lex)

    def pipeline(self, **kwargs):
        sess = self.session()
        worker = ManualWorker(self.lex, PickyModel(), delay=lambda i: 10 ** 6)
        clock = worker.clock
        return ConnectionPipeline(sess, worker, grace_ms=0, clock=clock, **kwargs), worker, clock

    def test_deadline_is_a_fault_detector_above_normal_conversions(self):
        # Windows, zenz medium, CPU, k 4, 1 review: median ~340 ms, 95th percentile 369 ms.
        self.assertGreaterEqual(DEADLINE_MS, 369)
        self.assertLessEqual(abs(DEADLINE_MS / 340 - 1.8), 0.1)

    def test_slow_normal_conversion_waits_for_the_lm(self):
        """A conversion slower than the old 400 ms cut (the measured CPU median is
        ~340 ms, so the slow half came close to it) still shows the LM's picks."""
        typist = Typist().kana("きしゃ").space()
        head = list(typist.events)
        tail = Typist()
        tail.t = typist.t
        tail.kana("かいせい", gap=20).tap(VK_RETURN)
        pipe, worker, clock = self.pipeline()
        commits = ""
        for event in head:
            commits += pipe.handle(dict(event))["commit"]
        job = pipe.job
        for event in tail.events[:3]:
            self.assertTrue(pipe.handle(dict(event))["pending"])
        clock.now += 0.5
        log = io.StringIO()
        with redirect_stderr(log):
            reply = pipe.handle(dict(tail.events[3]))
            self.assertTrue(reply["pending"])  # still waiting, not cut
            commits += reply["commit"]
            worker.complete_all()
            for event in tail.events[4:] + [TERMINAL]:
                reply = pipe.handle(dict(event))
                commits += reply["commit"]
        self.assertFalse(job.cancelled)
        self.assertEqual(log.getvalue(), "")
        self.assertEqual((commits, final_state(reply)),
                         run_reference(self.session, head + tail.events, PickyModel()))

    def test_completed_prefetch_opens_candidates_in_the_space_reply(self):
        pipe, worker, _ = self.pipeline()
        worker.eager_prefetch = True
        for event in Typist().kana("きしゃ").space().events:
            reply = pipe.handle(event)
        self.assertEqual(len(worker.jobs), 1)
        self.assertFalse(reply["pending"])
        self.assertTrue(reply["converted"])
        self.assertTrue(reply["candidates"])

    def test_pending_navigation_enter_and_next_character_replay_in_order(self):
        pipe, worker, _ = self.pipeline()
        keys = Typist().kana("きしゃ").space()
        keys.tap(0x28, gap=5).tap(VK_RETURN, gap=5).kana("う", gap=5)
        for event in keys.events:
            reply = pipe.handle(event)
        self.assertTrue(reply["pending"])
        self.assertEqual(reply["commit"], "")
        worker.complete_all()
        reply = pipe.handle(TERMINAL)
        self.assertEqual((reply["commit"], final_state(reply)),
                         run_reference(self.session, keys.events, PickyModel()))
        self.assertTrue(reply["commit"])
        self.assertEqual(pipe.handle(TERMINAL)["commit"], "")

    def test_result_deadline_uses_completion_time(self):
        for offset in (-0.001, 0, 0.001):
            with self.subTest(offset=offset):
                pipe, worker, clock = self.pipeline(prefetch="off")
                for event in Typist().kana("きしゃ").space().events:
                    reply = pipe.handle(event)
                self.assertTrue(reply["pending"])
                job = pipe.job
                clock.now = job.deadline + offset
                worker.complete(job)
                clock.now = job.deadline + 0.010
                with redirect_stderr(io.StringIO()) as log:
                    reply = pipe.handle(TERMINAL)
                self.assertFalse(reply["pending"])
                self.assertEqual("fault" in log.getvalue(), offset > 0)

    def test_reset_and_direct_switch_drop_pending_enter(self):
        for boundary in ({"op": "reset"}, {"op": "set_direct", "direct": True}):
            with self.subTest(boundary=boundary):
                pipe, worker, _ = self.pipeline()
                for event in Typist().kana("きしゃ").space().events:
                    pipe.handle(event)
                old = pipe.job
                self.assertIsNotNone(old)
                self.assertTrue(pipe.handle({"op": "down", "vk": VK_RETURN, "t": 1000})["pending"])
                worker.complete(old)
                reply = pipe.handle(boundary)
                self.assertEqual(reply["commit"], "")
                self.assertFalse(reply["pending"])
                self.assertIsNone(pipe.spec)
                self.assertEqual(pipe.handle(TERMINAL)["commit"], "")

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
        clock.now += DEADLINE_MS / 1000
        log = io.StringIO()
        with redirect_stderr(log):
            for event in tail.events[3:] + [TERMINAL]:
                reply = pipe.handle(dict(event))
                commits += reply["commit"]
        self.assertTrue(job.cancelled)
        self.assertIn("fault", log.getvalue())  # detected, not silent
        worker.complete_all()  # a late result changes nothing
        self.assertFalse(pipe.handle({"op": "timeout", "t": 0})["pending"])
        expected = run_reference(self.session, head + tail.events, None)
        self.assertEqual((commits, final_state(reply)), expected)
        self.assertNotEqual(expected, run_reference(self.session, head + tail.events,
                                                    PickyModel()))

if __name__ == "__main__":
    unittest.main()
