"""The engine only: the LM (zenz) off the key path.

LmWorker owns the converter on one daemon thread. ConnectionPipeline sits between a
connection and its ImeSession: a ThumbTap with LM work leaves the session
awaiting; the request uses the worker's result if it is there, otherwise replies
``pending`` with the display unchanged. Keys that arrive while pending are
queued in order and replayed once the LM picks resolve the conversion, so the
result equals the synchronous one.

A conversion waits for the LM: its picks are the conversion. The deadline
(deadline_ms(): DEADLINE_MS, or more for a slower machine's LM) is not a quality
cut but a fault detector, set above every normal conversion; a
conversion that reaches it (a stuck or broken LM) is logged and takes the
Viterbi 1-best so that typing goes on.

LM_FAULTS conversions in a row that raised or reached the deadline end the
LM's use in this engine (a stuck worker, a GPU that went away): conversions no
longer wait for it. Nothing loads the LM again by itself: loading is heavy, and
an LM that keeps failing must not load the machine again and again.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, replace
import gc
import sys
import threading
import time

from .server import apply_op, set_reply_commit, snapshot, suggestion_reply
from .keymap import Keymap
from .session import ConversionRequest, ImeSession
from .zenz import KanaRun

# The least deadline (a fast LM, e.g. on a GPU: median about 30 ms). Reviews
# after a run's first stop at zenz.REVIEW_BUDGET_MS, which keeps a conversion
# under the deadline.
DEADLINE_MS = 600
# The deadline scales with the machine (zenz.calibrate): typing sentences, a
# conversion took up to about 5.5 times the calibration time (small on a CPU,
# 2026-11-20), so a normal one stays under it on a slow PC too.
DEADLINE_CALIBRATIONS = 10
REQUIRED_LM_DEADLINE_MS = 10_000
LM_FAULTS = 2  # in a row: the LM is not used any more
POLL_MS = 10
PREFETCH_DELAY_MS = 30


@dataclass(eq=False)
class Job:
    owner: object  # the connection's pipeline
    request: ConversionRequest
    wanted: bool = False  # a conversion is waiting for this result
    not_before: float = 0.0  # time.monotonic(); delays a prefetch
    deadline: float = 0.0  # when wanted: a fault; log and use the Viterbi 1-best
    cancelled: bool = False
    submitted_at: float = 0.0
    wanted_at: float | None = None
    started_at: float | None = None
    completed_at: float | None = None
    completion_lock: threading.Lock = field(default_factory=threading.Lock)
    done: threading.Event = field(default_factory=threading.Event)
    picks: list[KanaRun] | None = None
    error: bool = False


class LmWorker:
    """One daemon thread; the only user of the model."""

    def __init__(self, loader, lex, *, clock=time.monotonic, on_disabled=None, retry_after=None,
                 timing=False):
        """The loader returns a warmed converter. If it raises, retry_after(exc) gives the
        seconds to wait before loading again, or None: then on_disabled() is called once.
        It is also called once after LM_FAULTS faults in a row (fault()).
        Conversions go without the LM until it is loaded."""
        self.loader = loader
        self.on_disabled = on_disabled
        self.retry_after = retry_after
        self.lex = lex
        self.timing = timing
        self.clock = clock
        self.state = "loading"
        self.template = None
        self._cond = threading.Condition()
        self._wanted: deque[Job] = deque()  # first come, first served
        self._slots: dict[int, Job] = {}  # id(owner) -> queued prefetch
        self._running: Job | None = None
        self._stopped = False
        self.faults = 0  # in a row: jobs that raised or were not done by the deadline
        self.thread = threading.Thread(target=self._run, name="lm-worker", daemon=True)
        self.thread.start()

    # -- connection side ----------------------------------------------------
    def available(self) -> bool:
        with self._cond:
            return self.state == "ready"

    def busy(self) -> bool:
        with self._cond:
            return bool(self._wanted or self._slots or self._running is not None)

    def wait_until_loaded(self) -> bool:
        with self._cond:
            self._cond.wait_for(lambda: self.state != "loading")
            return self.state == "ready"

    def submit(self, job: Job) -> None:
        with self._cond:
            job.submitted_at = self.clock()
            if job.wanted:
                self._wanted.append(job)
            else:
                slot = id(job.owner)
                old = self._slots.pop(slot, None)
                if old is not None:
                    self._drop(old)
                running = self._running
                if (running is not None and running.owner is job.owner
                        and not running.wanted):
                    running.cancelled = True  # stops at the next kana-run boundary
                self._slots[slot] = job
            self._cond.notify()

    def promote(self, job: Job, deadline: float) -> None:
        """A conversion now waits for this prefetch (queued, running or done)."""
        with self._cond:
            job.wanted = True
            job.deadline = deadline
            slot = id(job.owner)
            if self._slots.get(slot) is job:
                del self._slots[slot]
                job.not_before = min(job.not_before, job.wanted_at)
                self._wanted.appendleft(job)
                self._cond.notify()

    def cancel_owner(self, owner) -> None:
        with self._cond:
            for job in [j for j in self._wanted if j.owner is owner]:
                self._wanted.remove(job)
                self._drop(job)
            for slot in [s for s, j in self._slots.items() if j.owner is owner]:
                self._drop(self._slots.pop(slot))
            if self._running is not None and self._running.owner is owner:
                self._running.cancelled = True

    def _drop(self, job: Job) -> None:
        """A queued job that will never run (caller holds the lock)."""
        job.cancelled = True
        job.done.set()

    def fault(self) -> None:
        """A wanted conversion raised or was not done by its deadline."""
        with self._cond:
            self.faults += 1
            if self.faults < LM_FAULTS or self.state != "ready":
                return
            self.state = "disabled"
            self.stop()
        print(f"LM not used any more ({LM_FAULTS} faults in a row)", file=sys.stderr, flush=True)
        if self.on_disabled is not None:
            self.on_disabled()

    def stop(self) -> None:
        """Engine shutdown: finish nothing new, cut the running job short.

        The worker is a daemon thread doing native (torch) work; if the
        interpreter tears down around it, the process can abort instead of
        exiting. stop() + join() (engine.main) makes exit deterministic:
        queued jobs are dropped and a running conversion stops at its next
        kana-run boundary.
        """
        with self._cond:
            self._stopped = True
            if self._running is not None:
                self._running.cancelled = True
            for job in list(self._wanted):
                self._drop(job)
            self._wanted.clear()
            for job in list(self._slots.values()):
                self._drop(job)
            self._slots.clear()
            self._cond.notify()

    # -- worker thread ------------------------------------------------------
    def _run(self) -> None:
        while True:
            try:
                template = self.loader()
                break
            except Exception as exc:
                delay = self.retry_after(exc) if self.retry_after is not None else None
                if delay is None:
                    print(f"LM unavailable ({type(exc).__name__})",
                          file=sys.stderr, flush=True)
                    with self._cond:
                        self.state = "disabled"
                        self._cond.notify_all()
                    if self.on_disabled is not None:
                        self.on_disabled()
                    return
            # Still "loading" while waiting; stop() ends the wait (engine exit joins this thread).
            with self._cond:
                if self._cond.wait_for(lambda: self._stopped, delay):
                    return
        gc.freeze()  # the model's objects must not be traversed by full GC
        with self._cond:
            self.template = template
            self.state = "ready"
            self._cond.notify_all()
        while True:
            job = self._next()
            if job is None:  # stopped
                return
            self._execute(job)

    def _next(self) -> Job | None:
        with self._cond:
            while True:
                if self._stopped:
                    return None
                if self._wanted:
                    job = self._wanted.popleft()
                else:
                    now = self.clock()
                    ready = [s for s, j in self._slots.items() if j.not_before <= now]
                    if ready:
                        job = self._slots.pop(min(ready, key=lambda s: self._slots[s].not_before))
                    else:
                        waits = [j.not_before - now for j in self._slots.values()]
                        self._cond.wait(min(waits) if waits else None)
                        continue
                now = self.clock()
                if job.cancelled or (job.wanted and now >= job.deadline):
                    job.done.set()
                    continue
                job.started_at = now
                self._running = job
                return job

    def _execute(self, job: Job) -> None:
        converter = replace(self.template, last={})
        try:
            job.picks = job.request.decode(
                self.lex, converter, cancelled=lambda: job.cancelled)
        except Exception as exc:
            # That conversion is the Viterbi 1-best; the next one tries again.
            job.error = True
            print(f"LM job failed ({type(exc).__name__})", file=sys.stderr, flush=True)
            self.fault()  # before the result is published: the next conversion sees it
        with self._cond:
            with job.completion_lock:
                job.completed_at = self.clock()
            self._running = None
            job.done.set()
            if not job.error and not job.cancelled:
                self.faults = 0
        if self.timing:
            print(f"LM worker job={id(job)} submitted={job.submitted_at:.6f} "
                  f"eligible={max(job.submitted_at, job.not_before):.6f} "
                  f"started={job.started_at:.6f} completed={job.completed_at:.6f} "
                  f"cancelled={job.cancelled} error={job.error} wanted={job.wanted} "
                  f"stats={ {k: round(v) for k, v in converter.last.items()} }",
                  file=sys.stderr, flush=True)


def deadline_ms(converter) -> float:
    """The fault deadline for this machine's LM (DEADLINE_MS at least)."""
    calibration = converter.calibration_ms
    if calibration is None:
        return DEADLINE_MS
    return max(DEADLINE_MS, DEADLINE_CALIBRATIONS * calibration)


PENDING = object()


class ConnectionPipeline:
    """Per connection. Called with the server's dispatch lock held."""

    def __init__(self, sess: ImeSession, worker, *,
                 deadline_ms: float | None = DEADLINE_MS,
                 prefetch: str = "thumb",  # thumb | off
                 clock=time.monotonic,
                 require_lm: bool = False, timing: bool = False):
        self.sess = sess
        self.worker = worker
        self.deadline_ms = deadline_ms
        self.require_lm = require_lm
        self.timing = timing
        self.prefetch = prefetch
        self.clock = clock
        self.queue: deque[tuple[dict, Keymap]] = deque()
        self.deferred_down: dict | None = None
        self.await_keymap: Keymap | None = None
        self.last_t = 0
        self.job: Job | None = None  # the awaited conversion's job
        self.spec: Job | None = None  # the last prefetch
        self.spec_key: tuple | None = None

    def handle(self, msg: dict) -> dict:
        op = msg.get("op")
        if op == "suggest":
            return suggestion_reply(self.sess, msg, busy=self.worker.busy())
        if "t" in msg:
            self.last_t = int(msg["t"])
        if op == "reset" or (op == "set_direct" and msg["direct"] != self.sess.direct
                             and msg.get("commit") is not True):
            self._abandon()
        keymap = self.sess.keymap
        # Keep the rules at acceptance while the LM delays execution.
        queued = (msg, keymap)
        if (self.sess._await is not None and op == "timeout"
                and self.queue and self.queue[-1][0].get("op") == "timeout"
                and self.queue[-1][1] is keymap):
            self.queue[-1] = queued  # consecutive timeouts with the same rules
        else:
            self.queue.append(queued)
        try:
            return self._drain(msg)
        finally:
            self.sess.keymap = keymap

    def _drain(self, msg: dict) -> dict:
        current_keymap = self.sess.keymap
        op = msg.get("op")
        commit = ""
        eat = key_global = None
        again = False
        resolved_keys = []

        def key_result(m: dict) -> None:
            nonlocal eat, key_global, again
            if m.get("op") != "down":
                if m is msg:
                    key_global = self.sess.key_global
                return
            result = self.sess.key_eat
            if result is None:
                self.deferred_down = m
            elif m is msg:
                eat = result
                key_global = self.sess.key_global
                again = self.sess.key_again
            elif type(m.get("seq")) is int:
                resolved = {"seq": m["seq"], "eat": result}
                if self.sess.key_global is not None:
                    resolved["global"] = self.sess.key_global
                resolved_keys.append(resolved)

        while True:
            if self.sess._await is not None:
                outcome = self._outcome()
                if outcome is PENDING:
                    break
                assert self.await_keymap is not None
                self.sess.keymap = self.await_keymap
                commit += self.sess.finish_conversion(outcome)
                if self.deferred_down is not None:
                    m, self.deferred_down = self.deferred_down, None
                    key_result(m)
                self.job = None
                self.await_keymap = None
                continue
            if not self.queue:
                break
            m, self.sess.keymap = self.queue.popleft()
            self.sess.lm_deferred = self.worker.available()
            commit += apply_op(self.sess, m)
            key_result(m)
            if self.sess._await is not None:
                self.await_keymap = self.sess.keymap
                self._submit_convert()
        self.sess.keymap = current_keymap
        self._prefetch()
        deferred = op == "down" and eat is None
        if deferred:
            # A pending reply reserves the down. The eventual phase is used
            # when it runs, even if preceding queued keys changed the input.
            eat = self.sess.pending_key_eat(int(msg["vk"]), msg.get("mods"))
        reply = snapshot(self.sess, op, eat=eat, key_global=key_global, again=again)
        if deferred:
            reply["eat_pending"] = True
        if resolved_keys:
            reply["resolved_keys"] = resolved_keys
        set_reply_commit(self.sess, msg, reply, commit)
        reply["pending"] = self.sess._await is not None
        if reply["pending"]:
            poll = self.last_t + POLL_MS
            reply["timer"] = poll if reply["timer"] is None else min(reply["timer"], poll)
        return reply

    def close(self) -> None:
        """Connection ended: nothing of this connection may run any more."""
        self._abandon()

    def _abandon(self) -> None:
        self.worker.cancel_owner(self)
        self.queue.clear()
        self.deferred_down = None
        self.await_keymap = None
        self.sess._await = None
        self.sess._continuation = None
        self.job = self.spec = None
        self.spec_key = None

    def _submit_convert(self) -> None:
        request = self.sess._await
        wanted_at = self.clock()
        limit = self.deadline_ms
        if limit is None:  # from the LM's calibration (the worker is ready here)
            limit = deadline_ms(self.worker.template)
        deadline = wanted_at + limit / 1000
        spec = self.spec
        if (spec is not None and not spec.cancelled and not spec.error
                and spec.request.key == request.key):
            spec.wanted_at = wanted_at
            self.worker.promote(spec, deadline)
            self.job = spec
            self.spec = None
            self.spec_key = None
        else:
            self.worker.cancel_owner(self)
            self.job = Job(self, request, wanted=True, deadline=deadline, wanted_at=wanted_at)
            self.worker.submit(self.job)

    def _outcome(self):
        job = self.job
        # Decide expiry atomically with the worker's publication. The lock
        # covers the timestamp, while the inference runs outside it.
        with job.completion_lock:
            now = self.clock()
            completed = job.completed_at
            on_time = completed is not None and completed <= job.deadline
            if not on_time:
                if now < job.deadline:
                    return PENDING
                job.cancelled = True
        if on_time:
            self._trace_resolution(job, now, "error" if job.error else "lm")
            if job.error:
                if self.require_lm:
                    raise RuntimeError("LM conversion failed")
                return None
            return job.picks
        self.worker.cancel_owner(self)
        self.worker.fault()
        self._trace_resolution(job, now, "deadline")
        if self.require_lm:
            raise TimeoutError("LM conversion timed out")
        print(f"LM conversion not done after {1000 * (job.deadline - job.wanted_at):.0f} ms (fault); "
              "dictionary 1-best used", file=sys.stderr, flush=True)
        return None

    def _trace_resolution(self, job: Job, now: float, outcome: str) -> None:
        if self.timing:
            print(f"LM resolve job={id(job)} submitted={job.submitted_at:.6f} "
                  f"wanted={job.wanted_at:.6f} resolved={now:.6f} "
                  f"started={job.started_at} outcome={outcome}", file=sys.stderr, flush=True)

    def _prefetch(self) -> None:
        sess = self.sess
        if sess._await is not None or not self.worker.available():
            return
        if not sess.lone_thumb_converts() and self.spec is not None:
            # The thumb press became a chord (or the input changed otherwise): the
            # prefetch is for an input that will not be converted. Free the worker
            # for the next one instead of finishing it.
            self.worker.cancel_owner(self)
            self.spec = None
            self.spec_key = None
        if self.prefetch == "off" or sess.converted or not sess.tokens:
            return
        if not sess.lone_thumb_converts():
            return  # only a thumb key that converts is down, awaiting the chord decision
        request = sess.conversion_request()
        if request is None or request.key == self.spec_key:
            return
        self.spec = Job(self, request,
                        not_before=self.clock() + PREFETCH_DELAY_MS / 1000)
        self.spec_key = request.key
        self.worker.submit(self.spec)
