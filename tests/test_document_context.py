"""Document context through the stdio and resident request paths."""
from __future__ import annotations

from array import array
from contextlib import redirect_stderr
import io
import unittest
from unittest.mock import patch

from tests.test_engine_sessions import EngineCase
from tests.test_lm_async import ManualWorker
from yuragi.ime.lm_async import ConnectionPipeline, LmWorker
from yuragi.ime.server import dispatch, process_request
from yuragi.ime.session import ImeSession
from yuragi.ime.zenz import ZenzConverter
from yuragi.lattice.mozc_dict import BOS_ID, NUMBER_ID, Entry, MozcLex
from yuragi.lattice.table import load_table

ENTER, SPACE, BACK, ESC, DOWN = 0x0D, 0x20, 0x08, 0x1B, 0x28
HEAD, ALTERNATE = 2, 3


def context_session():
    size = NUMBER_ID + 1
    matrix = array("h", [0]) * (size * size)
    for rid in (HEAD, NUMBER_ID):
        matrix[rid * size + 1] = 300
    words = {
        "と": [Entry("語尾", "と", 1, HEAD, 10), Entry("別語尾", "と", 1, ALTERNATE, 50)],
        "か": [Entry("河", "か", 1, 1, 10), Entry("川", "か", 2, 1, 20)],
    }
    return ImeSession(_table=load_table(), _lex=MozcLex(words, set(words), matrix, size))


class Reviewer:
    def __init__(self):
        self.calls = []

    def reading_nll(self, context, readings):
        return [0.0 for _ in readings]

    def candidate_nll(self, context, candidates):
        return [0.0] * len(candidates)

    def review(self, context, reading, draft, accepted, reachable):
        self.calls.append((context, reading, draft))
        return None


class Keys:
    def __init__(self, handle):
        self.handle = handle
        self.t = 0
        self.seq = 0

    def send(self, op, key=None, **extra):
        self.t += 30
        self.seq += 1
        msg = {"op": op, "t": self.t, "seq": self.seq, **extra}
        if key is not None:
            msg["vk"] = ord(key) if isinstance(key, str) else key
        return self.handle(msg)

    def tap(self, key, **extra):
        down = self.send("down", key, **extra)
        up = self.send("up", key)
        return {**up, "commit": down["commit"] + up["commit"]}

    def commit(self):
        self.send("down", ENTER)
        return self.seq


class ContextCase(unittest.TestCase):
    def setUp(self):
        # Treat the test dictionary's one-word entries as separate clauses.
        content = patch("yuragi.ime.bunsetsu.content", return_value=True)
        content.start()
        self.addCleanup(content.stop)
        self.sess = context_session()
        self.reviewer = Reviewer()
        self.sess.lm = ZenzConverter(self.reviewer)
        self.keys = Keys(lambda msg: dispatch(self.sess, msg))


class DocumentContextTest(ContextCase):
    def test_first_down_holds_context_until_up_or_timeout(self):
        for trigger in ("up", "timeout"):
            with self.subTest(trigger=trigger):
                k = self.keys
                k.send("reset")
                down = k.send("down", "W", left_context="原稿の誤字を", after_commit_seq=None)
                self.assertEqual((down["composition"], down["fsm"]), ("", "S2"))
                if trigger == "timeout":
                    k.t = down["timer"]
                    k.send("timeout", left_context="別の本文")
                k.send("up", "W", left_context="別の本文")
                reply = k.tap(SPACE, left_context="未確定表示")
                self.assertEqual(reply["composition"], "河")
                self.assertEqual(self.reviewer.calls[-1], ("原稿の誤字を", "か", "河"))

    def test_thumb_first_chord_keeps_the_context_of_space_down(self):
        k = self.keys
        self.assertEqual(k.send("down", SPACE, left_context="親指から")["fsm"], "S3")
        k.send("down", "W", left_context="後続のキー")
        k.send("up", "W")
        k.send("up", SPACE)
        k.tap(SPACE)
        self.assertEqual(self.reviewer.calls[-1][0], "親指から")

    def test_loss_of_read_does_not_reuse_external_text(self):
        k = self.keys
        k.tap("J", left_context="既存の文章", after_commit_seq=None)
        seq = k.commit()
        k.tap("W", left_context=None, after_commit_seq=seq)
        k.tap(SPACE)
        self.assertEqual(self.reviewer.calls[-1], ("語尾", "か", "川"))
        k.commit()
        k.tap("W", left_context=None, after_commit_seq=None)
        k.tap(SPACE)
        self.assertEqual(self.reviewer.calls[-1], ("", "か", "河"))

    def test_observed_text_is_bounded_and_kept_out_of_logs(self):
        text = "先頭" + "𠮷" * 199 + "尾"
        k = Keys(lambda msg: process_request(self.sess, msg, log_text=True, lm_timing=True))
        logs = io.StringIO()
        with redirect_stderr(logs):
            reply = k.tap("W", left_context=text)
            k.tap(SPACE)
        self.assertEqual(reply["seq"], 2)
        self.assertEqual(self.reviewer.calls[-1], (text[-200:], "か", "河"))
        self.assertNotIn("𠮷", logs.getvalue())

    def test_sequence_and_observed_suffix_determine_continuity(self):
        for text, after, expected_text, winner in (
            ("外部語尾", "latest", "外部語尾", "川"),
            ("尾", "latest", "尾", "川"),
            ("", "latest", "", "河"),
            ("外部", "latest", "外部", "河"),
            ("語尾", None, "語尾", "河"),
            ("語尾", "missing", "語尾", "河"),
            ("語尾", "stale", "語尾", "河"),
            (123, True, "語尾語尾", "河"),
            (123, 3.0, "語尾語尾", "河"),
            ("\ud800", "latest", "語尾語尾", "川"),
        ):
            with self.subTest(text=text, after=after):
                k = self.keys
                k.send("reset")
                k.tap("J")
                old_seq = k.commit()
                k.tap("J")
                seq = k.commit()
                numbers = {"latest": seq, "stale": old_seq}
                extra = {} if after == "missing" else {"after_commit_seq": numbers.get(after, after)}
                self.assertEqual(k.tap("W", left_context=text, **extra)["composition"], winner)
                reply = k.tap(SPACE)
                self.assertEqual(reply["candidates"][0], winner)
                self.assertEqual(self.reviewer.calls[-1], (expected_text, "か", winner))

    def test_auto_commit_uses_selected_right_id_and_appends_once(self):
        k = self.keys
        k.tap("J", left_context="文章の")
        k.tap(SPACE)
        k.tap(DOWN)  # 別語尾 has an RID whose next word is 河.
        r = k.tap("W", left_context="無視する")
        self.assertEqual((r["commit"], r["composition"]), ("別語尾", "河"))
        k.tap(SPACE)
        self.assertEqual(self.reviewer.calls[-1], ("文章の別語尾", "か", "河"))

    def test_partial_commit_sets_the_remainder_context_and_can_reopen_candidates(self):
        k = self.keys
        k.tap("J", left_context="本文の")
        k.tap("W")
        k.tap(SPACE)
        r = k.send("down", DOWN, mods=["ctrl"])
        self.assertEqual((r["commit"], r["composition"], r["candidates"][0]), ("語尾", "川", "川"))
        k.tap(ESC)
        k.tap(SPACE)
        self.assertEqual(self.reviewer.calls[-1], ("本文の語尾", "か", "川"))
        k.commit()
        k.tap("W", left_context=None)
        k.tap(SPACE)
        self.assertEqual(self.reviewer.calls[-1], ("語尾川", "か", "河"))

    def test_numbers_carry_pos_and_punctuation_and_space_set_bos(self):
        k = self.keys
        for key, expected_commit, winner in (("1", "１", "川"), ("Q", "。", "河"),
                                               (SPACE, "　", "河")):
            with self.subTest(key=key):
                k.send("reset")
                reply = k.tap(key, left_context="ある文章")
                if key != SPACE:
                    reply = k.send("down", ENTER)
                self.assertEqual(reply["commit"], expected_commit)
                self.assertEqual(k.tap("W", after_commit_seq=reply["seq"])["composition"], winner)
                self.assertEqual(k.tap(SPACE)["candidates"][0], winner)

    def test_a_literal_inside_input_overrides_its_starting_pos(self):
        k = self.keys
        k.tap("J")
        seq = k.commit()
        k.tap("Q", after_commit_seq=seq)
        self.assertEqual(k.tap("W")["composition"], "。河")
        k.tap(SPACE)
        self.assertEqual(self.reviewer.calls[-1], ("語尾。", "か", "河"))

    def test_empty_enter_preserves_commit_but_backspace_and_reset_invalidate_it(self):
        for op, key, expected in (("down", ENTER, "川"), ("down", BACK, "河"),
                                   ("reset", None, "河"), ("down", 0x25, "河")):
            with self.subTest(op=op, key=key):
                k = self.keys
                k.send("reset")
                k.tap("J")
                seq = k.commit()
                self.assertEqual(k.send(op, key)["commit"], "")
                self.assertEqual(k.tap("W", left_context="語尾", after_commit_seq=seq)["composition"],
                                 expected)


class PipelineContextTest(ContextCase):
    def setUp(self):
        super().setUp()
        self.sess.lm = None
        self.worker = ManualWorker(self.sess._lex, self.reviewer, delay=lambda _: 100)
        self.pipeline = ConnectionPipeline(self.sess, self.worker, clock=self.worker.clock)
        self.keys = Keys(self.pipeline.handle)

    def test_queued_commit_binds_last_span_to_the_reply_that_contains_it(self):
        k, worker = self.keys, self.worker
        k.tap("J", left_context="最初の本文")
        self.assertTrue(k.tap(SPACE)["pending"])
        self.assertEqual(k.send("down", ENTER)["commit"], "")
        k.tap("1", left_context=None)
        k.send("down", ENTER)
        worker.complete(worker.jobs[-1])
        r = k.send("timeout")
        self.assertEqual(r["commit"], "語尾１")
        self.assertEqual(self.reviewer.calls, [("最初の本文", "と", "語尾")])
        r = k.tap("W", left_context="外１", after_commit_seq=k.seq)
        self.assertEqual((r["commit"], r["composition"]), ("", "川"))

    def test_queued_start_with_unavailable_context_uses_the_commit_before_it(self):
        k, worker = self.keys, self.worker
        k.tap("J", left_context="外部の本文")
        self.assertTrue(k.tap(SPACE)["pending"])
        k.send("down", ENTER)
        k.tap("W", left_context=None)
        worker.complete(self.pipeline.job)
        r = k.send("timeout")
        self.assertEqual((r["commit"], r["composition"]), ("語尾", "河"))
        self.assertTrue(k.tap(SPACE)["pending"])
        worker.complete(self.pipeline.job)
        self.assertEqual(k.send("timeout")["commit"], "")
        self.assertEqual(self.reviewer.calls[-1], ("語尾", "か", "河"))

    def test_prefetch_with_a_different_left_pos_cannot_be_promoted(self):
        k = self.keys
        k.tap("J")
        k.commit()
        k.tap("W", left_context="語尾")
        k.send("down", SPACE)
        prefetch = self.pipeline.spec
        # Retain the old prefetch while preparing identical input with a
        # verified position, to isolate the POS component of the cache key.
        self.sess._cancel()
        k.tap("J")
        seq = k.commit()
        k.tap("W", left_context="語尾", after_commit_seq=seq)
        k.send("down", SPACE)
        self.pipeline.spec = prefetch
        k.send("up", SPACE)
        job = self.pipeline.job
        self.assertIsNot(job, prefetch)
        self.assertEqual((prefetch.request.lm_context, job.request.lm_context), ("語尾", "語尾"))
        self.assertEqual(prefetch.request.parts, job.request.parts)
        self.assertEqual((prefetch.request.left_id, job.request.left_id), (BOS_ID, HEAD))

    def test_deadline_keeps_the_display_and_candidate_order(self):
        k = self.keys
        k.tap("J")
        seq = k.commit()
        self.assertEqual(k.tap("W", left_context="外語尾", after_commit_seq=seq)["composition"],
                         "川")
        self.assertTrue(k.tap(SPACE)["pending"])
        self.worker.clock.now += 1
        with redirect_stderr(io.StringIO()):
            r = k.send("timeout")
        self.assertEqual((r["pending"], r["composition"], r["candidates"][0]),
                         (False, "川", "川"))

    def test_reset_drops_queued_context_and_delayed_commit(self):
        k = self.keys
        k.tap("J", left_context="古い欄")
        k.tap(SPACE)
        job = self.pipeline.job
        k.send("down", ENTER)
        k.tap("W", left_context="古い欄の後続")
        self.assertEqual(k.send("reset")["commit"], "")
        self.worker.complete(job)
        self.assertTrue(job.cancelled)
        self.assertEqual(k.tap("W", left_context="新しい欄")["composition"], "河")
        k.tap(SPACE)
        self.worker.complete(self.pipeline.job)
        self.assertEqual(k.send("timeout")["commit"], "")
        self.assertEqual(self.reviewer.calls, [("新しい欄", "か", "河")])

    def test_worker_uses_the_request_snapshot(self):
        worker = LmWorker(lambda: ZenzConverter(self.reviewer), self.sess._lex)
        self.addCleanup(worker.thread.join, 5)
        self.addCleanup(worker.stop)
        self.assertTrue(worker.wait_until_loaded())
        pipe = ConnectionPipeline(self.sess, worker, grace_ms=500, prefetch="off")
        k = Keys(pipe.handle)
        k.tap("J")
        seq = k.commit()
        k.tap("W", left_context="外語尾", after_commit_seq=seq)
        r = k.tap(SPACE)
        self.assertEqual((r["pending"], r["composition"], r["candidates"][0]),
                         (False, "川", "川"))
        self.assertEqual(self.reviewer.calls, [("外語尾", "か", "川")])


class ConnectionContextTest(EngineCase):
    def test_same_reply_number_is_local_to_each_sid(self):
        with patch("yuragi.ime.bunsetsu.content", return_value=True):
            engine = self.engine(loaded=context_session())
            self.open(engine, 1)
            self.open(engine, 2)
            first = Keys(lambda msg: engine.request({"sid": 1, **msg}))
            second = Keys(lambda msg: engine.request({"sid": 2, **msg}))
            for k in (first, second):
                k.tap("J")
                k.tap(SPACE)
            first.tap(0x7B)
            self.assertEqual(second.tap(DOWN)["composition"], "別語尾")
            seq = first.commit()
            self.assertEqual(seq, second.commit())
            self.assertEqual(first.tap("W", left_context="尾", after_commit_seq=seq)["composition"],
                             "川")
            self.assertEqual(second.tap("W", left_context="尾", after_commit_seq=seq)["composition"],
                             "河")
