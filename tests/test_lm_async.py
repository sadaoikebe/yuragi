"""Resident LM pipeline: the IME never hangs on a slow LM. A fake model, no torch.

A conversion waits for the LM's picks. The deadline (DEADLINE_MS) only detects
a fault: it is logged and falls back to the dictionary-only conversion, the
same as converting without the LM.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr
from dataclasses import replace
import io
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from yuragi.chord.fsm import AmbShift, Plain
from yuragi.chord.keys import VK_TO_M
from yuragi.ime.bunsetsu import Candidate
from yuragi.ime.learning import LearningStore
from yuragi.ime.lm_async import DEADLINE_MS, ConnectionPipeline, Job, LmWorker
from yuragi.ime.zenz import ZenzConverter
from yuragi.ime.server import dispatch
from yuragi.ime.session import ConversionRequest, ImeSession, Literal
from yuragi.lattice.mozc_dict import Entry, MozcLex
from yuragi.lattice.table import load_table, reverse_table
from tests.real_dictionary import real_lex

# Up of an unclassified key: a no-op for every session state. Sent last to both
# sides so the subject has one request in which to resolve what is still pending.
TERMINAL = {"op": "up", "vk": 0x7B}
VK_SPACE, VK_RETURN = 0x20, 0x0D


class PickyModel:
    """Deterministic, context-dependent zenz stand-in that often overrides the 1-best."""

    def reading_nll(self, context, readings):
        return [sum(ord(ch) % 7 for ch in r) * 0.7 for r in readings]

    def candidate_nll(self, context, candidates):
        return [0.0] * len(candidates)

    def review(self, context, reading, draft, accepted, reachable):
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

    def busy(self):
        """A job is queued or running (the worker drops cancelled ones)."""
        return any(not job.done.is_set() and not job.cancelled for job in self.jobs)

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
            job.picks = job.request.decode(
                self.lex, replace(self.template, last={}), cancelled=lambda: job.cancelled)
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


class LearnedContextTest(unittest.TestCase):
    def test_lm_context_matches_the_learned_display(self):
        for deferred in (False, True):
            with self.subTest(deferred=deferred), tempfile.TemporaryDirectory() as directory:
                lex = MozcLex({
                    "か": [Entry("科", "か", 1, 1, 100), Entry("課", "か", 1, 1, 300)],
                    "い": [Entry("胃", "い", 1, 1, 100)],
                    "ち": [Entry("地", "ち", 1, 1, 800)],
                }, {"か", "い", "ち"}, [0] * 4, 2)
                learning = LearningStore(Path(directory) / "learning.jsonl")
                learning.confirm([Candidate("課", "か", 0, 1, 1, word_cost=300)], lex)
                session = ImeSession(_lex=lex, _learning=learning, _lm_context="本文", _table={
                    "keys": {"K": {"plain": "か"}, "I": {"left": "い", "right": "ち"}},
                })
                session.tokens = [Plain("K"), Literal("、"), AmbShift("I")]
                model = Mock()
                model.candidate_nll.side_effect = lambda context, rows: [0.0] * len(rows)
                model.reading_nll.return_value = [5.0, 0.0]
                # The LM cannot write its fix for か, so the learned 課 is shown there.
                model.review.side_effect = lambda ctx, reading, draft, accepted, reachable: (
                    ("存".encode(), True) if reading == "か" else None)
                events = Typist().space().events
                if deferred:
                    worker = ManualWorker(lex, model, delay=lambda _: 1)
                    pipe = ConnectionPipeline(session, worker, prefetch="off", clock=worker.clock)
                    for event in events:
                        reply = pipe.handle(event)
                    self.assertTrue(reply["pending"])
                    # A different session can update the file while inference is pending.
                    writer = LearningStore(learning.path)
                    writer.confirm([Candidate("科", "か", 0, 1, 1, word_cost=100)], lex)
                    worker.complete_all()
                    reply = pipe.handle(TERMINAL)
                else:
                    session.lm = ZenzConverter(model)
                    for event in events:
                        reply = dispatch(session, event)
                self.assertTrue(reply["converted"])
                model.reading_nll.assert_called_once_with("本文課、", ["い", "ち"])
                self.assertEqual((reply["composition"], model.review.call_args_list[-1].args[:2]),
                                 ("課、地", ("本文課、", "ち")))

    def test_ranked_page_keeps_heads_and_reverts_after_left_edit(self):
        surfaces = list("医井意衣胃位威異遺伊移維")
        lex = MozcLex({
            "か": [Entry("科", "か", 1, 1, 100), Entry("課", "か", 1, 1, 200)],
            "い": [Entry(text, "い", 1, 1, 100 + i) for i, text in enumerate(surfaces)]
                 + [Entry("偉", "い", 1, 1, 7000)],
        }, {"か", "い"}, [0] * 4, 2)
        with tempfile.TemporaryDirectory() as directory:
            learning = LearningStore(Path(directory) / "learning.jsonl")
            learning.confirm([Candidate("学", "い", 0, 1, 1, word_cost=200)], lex)
            session = ImeSession(_lex=lex, _learning=learning, _lm_context="本文", _table={
                "keys": {"K": {"plain": "か"}, "I": {"plain": "い"}},
            })
            session.tokens = [Plain("K"), Literal("、"), Plain("I")]
            model = Mock()
            model.review.side_effect = lambda ctx, reading, draft, accepted, reachable: (
                ("偉".encode(), True) if reading == "い" and draft != "偉" else None)
            model.candidate_nll.side_effect = lambda ctx, rows: (
                [2, 2] + list(range(1, 3 - len(rows), -1)) if ctx == "本文科、"
                else [0] * len(rows))
            worker = ManualWorker(lex, model)
            pipe = ConnectionPipeline(session, worker, prefetch="off", clock=worker.clock)
            for event in Typist().space().events:
                pipe.handle(event)
            self.assertEqual([c.surface for c in model.candidate_nll.call_args.args[1]],
                             surfaces[:9])

            # Visit the right clause. The LM's 偉 leads (学 was learned with no left
            # bunsetsu, so it does not override the LM); eight ranked rows follow.
            for vk in (0x27, 0x27):  # Right twice
                pipe.handle({"op": "down", "vk": vk})
            for event in Typist().space().events:
                pipe.handle(event)
            self.assertEqual(session.candidates, ["偉"] + surfaces[2:9][::-1] + surfaces[:1])
            pipe.handle({"op": "down", "vk": 0x22})  # PageDown
            self.assertEqual(session.candidates, surfaces[1:2] + surfaces[9:] + ["学", "い", "イ"])

            # Same POS, different text to the left. The old score and review both
            # expire; with no LM vote left, the learned 学 leads.
            for vk in (0x25, 0x25):
                pipe.handle({"op": "down", "vk": vk})
            for event in Typist().space().events:
                pipe.handle(event)
            for vk in (ord("2"), 0x27, 0x27):
                pipe.handle({"op": "down", "vk": vk})
            self.assertEqual(session.composition, "課、井")
            for event in Typist().space().events:
                pipe.handle(event)
            self.assertEqual(session.candidates, ["学"] + surfaces[:8])
            self.assertEqual(model.candidate_nll.call_count, 1)


class LoadRetryTest(unittest.TestCase):
    """The worker loads the LM again when retry_after says so (engine.lm_retry_after)."""

    def test_loaded_on_the_second_try(self):
        loads = []

        def loader():
            loads.append(None)
            if len(loads) == 1:
                raise RuntimeError("too slow")
            return object()

        worker = LmWorker(loader, None, retry_after=lambda exc: 0.01)
        self.assertTrue(worker.wait_until_loaded())
        self.assertEqual(len(loads), 2)
        worker.stop()
        worker.thread.join(5)

    def test_engine_exit_does_not_wait_out_the_delay(self):
        def loader():
            raise RuntimeError("too slow")

        worker = LmWorker(loader, None, retry_after=lambda exc: 3600)
        worker.stop()
        worker.thread.join(5)  # engine.main joins it on exit
        self.assertFalse(worker.thread.is_alive())


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

    def test_candidate_number_waits_for_conversion(self):
        pipe, worker, _ = self.pipeline(prefetch="off")
        keys = Typist().kana("きしゃ").space().space()  # the second Space opens the window
        for event in keys.events:
            reply = pipe.handle(event)
        self.assertEqual((reply["phase"], reply["pending"]), ("composing", True))
        digit = pipe.handle({"op": "down", "vk": ord("3"), "t": keys.t + 10})
        self.assertEqual((digit["eat"], digit["pending"], digit["commit"]), (True, True, ""))
        worker.complete(pipe.job)
        selected = pipe.handle(TERMINAL)
        self.assertEqual((selected["phase"], selected["cand_index"], selected["commit"]),
                         ("selecting", 2, ""))
        self.assertEqual(selected["composition"], selected["candidates"][2])

        # Releasing a number used as a command must leave the next stroke
        # waiting for its own timeout, even if that timeout is already due.
        next_key = pipe.handle({"op": "down", "vk": ord("K"), "t": keys.t + 20})
        released = pipe.handle({"op": "up", "vk": ord("3"), "t": next_key["timer"] + 1})
        self.assertNotIn("eat", released)
        self.assertEqual((released["composition"], released["timer"]), ("", next_key["timer"]))

    def test_poll_returns_toggle_for_the_key_after_a_deferred_commit(self):
        pipe, worker, _ = self.pipeline(prefetch="off")
        keys = Typist().kana("きしゃ").space()
        for event in keys.events:
            pipe.handle(event)
        requests = ((11, VK_RETURN, []), (12, 0x14, ["shift"]), (13, VK_RETURN, []))
        for seq, vk, mods in requests:
            reply = pipe.handle({"op": "down", "vk": vk, "mods": mods, "seq": seq,
                                 "t": keys.t + seq})
            self.assertTrue(reply["eat_pending"])
            self.assertNotIn("global", reply)

        worker.complete(pipe.job)
        reply = pipe.handle({"op": "timeout", "t": keys.t + 20, "seq": 14})
        self.assertTrue(reply["commit"])
        self.assertNotIn("eat", reply)
        self.assertNotIn("global", reply)
        self.assertEqual(reply["resolved_keys"], [
            {"seq": 11, "eat": True},
            {"seq": 12, "eat": False, "global": "ime_toggle"},
            {"seq": 13, "eat": False},
        ])
        self.assertNotIn("resolved_keys", pipe.handle({"op": "timeout", "t": keys.t + 30}))

    def test_replay_pauses_at_next_conversion_and_resumes_in_order(self):
        pipe, worker, _ = self.pipeline(prefetch="off")
        keys = Typist().kana("きしゃ").key("down", VK_SPACE, 150)
        # Enter arrives before Space resolves, so Enter itself starts the LM job.
        keys.tap(VK_RETURN, gap=10).key("up", VK_SPACE, 10)
        keys.kana("かいせい").space()
        keys.tap(0x28).tap(VK_RETURN).kana("う")
        for event in keys.events:
            reply = pipe.handle(event)
            self.assertEqual(reply["commit"], "")

        first = pipe.job
        self.assertIsNotNone(first)
        worker.complete(first)
        reply = pipe.handle(TERMINAL)
        self.assertTrue(reply["pending"])
        first_commit = reply["commit"]
        self.assertTrue(first_commit)

        second = pipe.job
        self.assertIsNotNone(second)
        self.assertIsNot(second, first)
        self.assertTrue(pipe.queue)
        reply = pipe.handle(TERMINAL)
        self.assertTrue(reply["pending"])
        self.assertEqual(reply["commit"], "")

        worker.complete(second)
        reply = pipe.handle(TERMINAL)
        self.assertFalse(reply["pending"])
        self.assertTrue(reply["commit"])
        self.assertFalse(pipe.queue)
        self.assertEqual((first_commit + reply["commit"], final_state(reply)),
                         run_reference(self.session, keys.events, PickyModel()))
        self.assertEqual(pipe.handle(TERMINAL)["commit"], "")

    def test_disconnect_drops_pending_enter_before_and_after_completion(self):
        for completed in (False, True):
            with self.subTest(completed=completed):
                pipe, worker, clock = self.pipeline()
                for event in Typist().kana("きしゃ").space().events:
                    reply = pipe.handle(event)
                self.assertTrue(reply["pending"])
                old = pipe.job
                self.assertTrue(pipe.handle({"op": "down", "vk": VK_RETURN, "t": 1000})["pending"])
                if completed:
                    worker.complete(old)
                pipe.close()
                self.assertIsNone(pipe.job)
                self.assertFalse(pipe.queue)
                if not completed:
                    self.assertTrue(old.cancelled)
                    worker.complete(old)

                replacement = ConnectionPipeline(self.session(), worker, clock=clock)
                reply = replacement.handle(TERMINAL)
                self.assertEqual((reply["commit"], reply["composition"], reply["pending"]),
                                 ("", "", False))

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

    def test_poll_does_not_expire_an_on_time_result_being_published(self):
        inference_done = threading.Event()
        publishing = threading.Event()
        poll_deciding = threading.Event()
        release_publication = threading.Event()
        deadline = 100.0

        def finish_inference(*args, **kwargs):
            inference_done.set()
            return []

        def completion_clock():
            if not inference_done.is_set():
                return deadline - 0.010
            publishing.set()
            if not release_publication.wait(5):
                raise TimeoutError("test did not release publication")
            return deadline - 0.001

        worker = LmWorker(lambda: ZenzConverter(PickyModel()), self.lex, clock=completion_clock)
        self.addCleanup(worker.thread.join, 5)
        self.addCleanup(worker.stop)
        self.assertTrue(worker.wait_until_loaded())

        pipeline = ConnectionPipeline(self.session(), worker, clock=lambda: deadline + 0.001)
        request = ConversionRequest([], "", 0, None, ())
        job = pipeline.job = Job(pipeline, request, wanted=True, deadline=deadline)
        lock = job.completion_lock

        class ObservedLock:
            def __enter__(self):
                if threading.current_thread() is not worker.thread:
                    poll_deciding.set()
                lock.acquire()

            def __exit__(self, *_):
                lock.release()

        job.completion_lock = ObservedLock()
        cancel_owner = worker.cancel_owner

        def observe_cancel(owner):
            # A poll that bypasses the completion lock reaches cancellation.
            poll_deciding.set()
            cancel_owner(owner)

        with (patch("yuragi.ime.session.conversion_picks", side_effect=finish_inference),
              patch.object(worker, "cancel_owner", side_effect=observe_cancel)):
            with ThreadPoolExecutor(max_workers=1) as polling:
                try:
                    worker.submit(job)
                    self.assertTrue(publishing.wait(5))
                    result = polling.submit(pipeline._outcome, wait=False)
                    self.assertTrue(poll_deciding.wait(5))
                finally:
                    release_publication.set()
                self.assertEqual(result.result(timeout=5), [])
                self.assertFalse(job.cancelled)

    def test_reset_and_direct_switch_drop_pending_enter(self):
        for boundary in ({"op": "reset"}, {"op": "set_direct", "direct": True}):
            for completed in (False, True):
                self.assert_boundary_drops_pending_enter(boundary, completed)

    def assert_boundary_drops_pending_enter(self, boundary, completed):
        with self.subTest(boundary=boundary, completed=completed):
            pipe, worker, _ = self.pipeline()
            for event in Typist().kana("きしゃ").space().events:
                pipe.handle(event)
            old = pipe.job
            self.assertIsNotNone(old)
            self.assertTrue(pipe.handle({"op": "down", "vk": VK_RETURN, "t": 1000})["pending"])
            if completed:
                worker.complete(old)
            reply = pipe.handle(boundary)
            self.assertEqual(reply["commit"], "")
            self.assertFalse(reply["pending"])
            self.assertIsNone(pipe.spec)
            if not completed:
                self.assertTrue(old.cancelled)
                worker.complete(old)
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
