"""The engine only: the LM (zenz) off the key path.

LmWorker owns the converter on one daemon thread. ConnectionPipeline sits between a
connection and its ImeSession: a ThumbTap with LM work leaves the session
awaiting; the request waits at most GRACE_MS for the worker, otherwise replies
``pending`` with the display unchanged. Keys that arrive while pending are
queued in order and replayed once the LM picks (or, after DEADLINE_MS, the
Viterbi 1-best) resolve the conversion, so the result equals the synchronous one.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, replace
import gc
import sys
import threading
import time

from .zenz import conversion_picks
from .server import apply_op, snapshot
from .session import ConversionRequest, ImeSession

GRACE_MS = 30
DEADLINE_MS = 400
REQUIRED_LM_DEADLINE_MS = 10_000
POLL_MS = 10
PREFETCH_DELAY_MS = 30


@dataclass(eq=False)
class Job:
    owner: object  # the connection's pipeline
    request: ConversionRequest
    wanted: bool = False  # a conversion is waiting for this result
    not_before: float = 0.0  # time.monotonic(); delays a prefetch
    deadline: float = 0.0  # when wanted: give up and use the Viterbi 1-best
    cancelled: bool = False
    done: threading.Event = field(default_factory=threading.Event)
    picks: list | None = None
    error: bool = False


class LmWorker:
    """One daemon thread; the only user of the model."""

    def __init__(self, loader, lex, *, clock=time.monotonic, on_disabled=None):
        """on_disabled(): told once when the LM could not be loaded. Called on
        the worker thread."""
        self.loader = loader
        self.on_disabled = on_disabled
        self.lex = lex
        self.clock = clock
        self.state = "loading"
        self.template = None
        self._cond = threading.Condition()
        self._wanted: deque[Job] = deque()  # first come, first served
        self._slots: dict[int, Job] = {}  # id(owner) -> queued prefetch
        self._running: Job | None = None
        self._stopped = False
        self.thread = threading.Thread(target=self._run, name="lm-worker", daemon=True)
        self.thread.start()

    # -- connection side ----------------------------------------------------
    def available(self) -> bool:
        with self._cond:
            return self.state == "ready"

    def wait_until_loaded(self) -> bool:
        with self._cond:
            self._cond.wait_for(lambda: self.state != "loading")
            return self.state == "ready"

    def submit(self, job: Job) -> None:
        with self._cond:
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
        try:
            template = self.loader()
            template.warm_up()  # before "ready"
        except Exception as exc:
            print(f"LM unavailable ({type(exc).__name__})",
                  file=sys.stderr, flush=True)
            with self._cond:
                self.state = "disabled"
                self._cond.notify_all()
            if self.on_disabled is not None:
                self.on_disabled()
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
                if job.cancelled:
                    job.done.set()
                    continue
                self._running = job
                return job

    def _execute(self, job: Job) -> None:
        try:
            request = job.request
            job.picks = conversion_picks(
                request.parts, self.lex, request.learning, request.lm_context,
                replace(self.template, last={}), cancelled=lambda: job.cancelled)
        except Exception as exc:
            # That conversion is the Viterbi 1-best; the next one tries again.
            job.error = True
            print(f"LM job failed ({type(exc).__name__})", file=sys.stderr, flush=True)
        with self._cond:
            self._running = None
            job.done.set()


PENDING = object()


class ConnectionPipeline:
    """Per connection. Called with the server's dispatch lock held."""

    def __init__(self, sess: ImeSession, worker, *,
                 grace_ms: float = GRACE_MS, deadline_ms: float = DEADLINE_MS,
                 poll_ms: int = POLL_MS, prefetch: str = "thumb",  # thumb | off
                 prefetch_delay_ms: float = PREFETCH_DELAY_MS, clock=time.monotonic,
                 require_lm: bool = False):
        self.sess = sess
        self.worker = worker
        self.grace_ms = grace_ms
        self.deadline_ms = deadline_ms
        self.poll_ms = poll_ms
        self.require_lm = require_lm
        self.prefetch = prefetch
        self.prefetch_delay_ms = prefetch_delay_ms
        self.clock = clock
        self.queue: deque[dict] = deque()
        self.last_t = 0
        self.job: Job | None = None  # the awaited conversion's job
        self.spec: Job | None = None  # the last prefetch
        self.spec_key: tuple | None = None

    def handle(self, msg: dict) -> dict:
        op = msg.get("op")
        if "t" in msg:
            self.last_t = int(msg["t"])
        if self.sess._await is not None and op in ("reset", "set_direct"):
            self._abandon()
        if (self.sess._await is not None and op == "timeout"
                and self.queue and self.queue[-1].get("op") == "timeout"):
            self.queue[-1] = msg  # consecutive timeouts: the last one is equivalent
        else:
            self.queue.append(msg)
        commit, grace = "", False
        while True:
            if self.sess._await is not None:
                outcome = self._outcome(wait=grace)
                grace = False
                if outcome is PENDING:
                    break
                commit += self.sess.finish_conversion(outcome)
                self.job = None
                continue
            if not self.queue:
                break
            m = self.queue.popleft()
            self.sess.lm_deferred = self.worker.available()
            commit += apply_op(self.sess, m)
            if self.sess._await is not None:
                self._submit_convert()
                grace = True
        self._prefetch()
        reply = snapshot(self.sess, op)
        reply["commit"] = commit
        reply["pending"] = self.sess._await is not None
        if reply["pending"]:
            poll = self.last_t + self.poll_ms
            reply["timer"] = poll if reply["timer"] is None else min(reply["timer"], poll)
        return reply

    def close(self) -> None:
        """Connection ended: nothing of this connection may run any more."""
        self.worker.cancel_owner(self)

    def _abandon(self) -> None:
        self.worker.cancel_owner(self)
        self.queue.clear()
        self.sess._await = None
        self.sess._continuation = None
        self.job = None

    def _submit_convert(self) -> None:
        request = self.sess._await
        deadline = self.clock() + self.deadline_ms / 1000
        spec = self.spec
        if (spec is not None and not spec.cancelled and not spec.error
                and spec.request.key == request.key):
            self.worker.promote(spec, deadline)
            self.job = spec
        else:
            self.worker.cancel_owner(self)
            self.job = Job(self, request, wanted=True, deadline=deadline)
            self.worker.submit(self.job)

    def _outcome(self, *, wait: bool):
        job = self.job
        if wait:
            job.done.wait(self.grace_ms / 1000)
        if job.done.is_set():
            if job.error:
                if self.require_lm:
                    raise RuntimeError("LM conversion failed")
                return None
            return job.picks
        if self.clock() >= job.deadline:
            job.cancelled = True
            if self.require_lm:
                raise TimeoutError("LM conversion timed out")
            return None
        return PENDING

    def _prefetch(self) -> None:
        sess = self.sess
        if sess._await is not None or not self.worker.available():
            return
        if self.prefetch == "off" or sess.converted or not sess.tokens:
            return
        if sess.fsm.state != "S3":
            return  # S3: only a thumb key is down, awaiting the chord decision
        request = sess.conversion_request()
        if request is None or request.key == self.spec_key:
            return
        self.spec = Job(self, request,
                        not_before=self.clock() + self.prefetch_delay_ms / 1000)
        self.spec_key = request.key
        self.worker.submit(self.spec)
