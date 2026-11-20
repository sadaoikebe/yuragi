"""Left-context reading selection through the model and the Space key."""
from contextlib import contextmanager, redirect_stderr
import io
import math
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tests.real_dictionary import real_lex
from tests.test_document_context import Keys, SPACE
from tests.test_lm_async import Clock, ManualWorker, TERMINAL, Typist
from yuragi.ime.lm_async import ConnectionPipeline, LmWorker
from yuragi.ime.server import dispatch
from yuragi.ime.session import ImeSession
from yuragi.ime.zenz import ZenzConverter, ZenzModel, spell
from yuragi.lattice.decode import DecodeResult
from yuragi.lattice.mozc_dict import BOS_ID
from yuragi.lattice.table import load_table, reverse_table
from yuragi.lattice.token_viterbi import decode_tokens

START, CONTEXT, END = "\uee00", "\uee02", "\uee01"
VOCAB_SIZE = 32
MESSAGE = "メッセージを送るとすぐに"
CHILDHOOD = "子どものころの"


class PromptLogits:
    """Small causal model that gives a boost to specified next tokens."""

    def __init__(self):
        self.vocab = {START: 1, CONTEXT: 2, END: 3}
        self.bonus = {}
        self.batches = []
        self.inference = False

    def encode(self, text, *, add_special_tokens):
        assert not add_special_tokens
        return [self.vocab.setdefault(ch, len(self.vocab) + 1) for ch in text]

    @contextmanager
    def inference_mode(self):
        self.inference = True
        try:
            yield
        finally:
            self.inference = False

    def __call__(self, *, input_ids, use_cache):
        assert self.inference and not use_cache
        self.batches.append(input_ids)
        inverses = {index: ch for ch, index in self.vocab.items()}
        rows = []
        for ids in input_ids:
            row = []
            prefix = ""
            for index in ids:
                prefix += inverses.get(index, "")
                scores = [0.0] * VOCAB_SIZE
                target, bonus = self.bonus.get(prefix, (0, 0))
                scores[target] = bonus
                row.append(scores)
            rows.append(row)
        return SimpleNamespace(logits=SimpleNamespace(float=lambda: rows))

    def log_softmax(self, logits, dim):
        assert self.inference and dim == -1
        rows = []
        for row in logits:
            scores = []
            for step in row:
                normalizer = math.log(sum(math.exp(x) for x in step))
                scores.append([x - normalizer for x in step])
            rows.append(scores)

        class LogProbs:
            def __getitem__(self, index):
                row, steps, targets = index
                return SimpleNamespace(sum=lambda: sum(rows[row][step][target]
                                                       for step, target in zip(steps, targets)))

        return LogProbs()


class PromptLikelihoodTest(unittest.TestCase):
    def setUp(self):
        self.backend = PromptLogits()
        self.model = ZenzModel.__new__(ZenzModel)
        self.model.torch = self.backend
        self.model.tok = SimpleNamespace(encode=Mock(wraps=self.backend.encode))
        self.model.model = self.backend
        self.model._ids = lambda rows: rows
        self.model._readings = {}
        self.model.eos = 0

    def test_sum_includes_context_and_end_but_excludes_padding(self):
        short = START + "カ" + CONTEXT + "本文" + END
        long = START + "カナ" + CONTEXT + "本文" + END
        for text in (short, long):
            self.backend.encode(text, add_special_tokens=False)
        vocab = self.backend.vocab
        self.backend.bonus.update({
            short[:-2]: (vocab["文"], 2),
            long[:-1]: (vocab[END], 3),
            short: (self.model.eos, 9),
        })

        uniform = math.log(VOCAB_SIZE)
        expected = [
            (len(short) - 2) * uniform + math.log1p((VOCAB_SIZE - 1) * math.exp(-2)),
            (len(long) - 2) * uniform + math.log1p((VOCAB_SIZE - 1) * math.exp(-3)),
        ]
        nll = self.model.reading_nll
        result = nll("本文", ["か", "かな", "か"])
        self.assertAlmostEqual(result[0], expected[0])
        self.assertAlmostEqual(result[1], expected[1])
        self.assertEqual(result[2], result[0])
        self.assertEqual(nll("本文", ["かな", "か"]), result[1::-1])
        self.assertEqual(nll("本文", []), [])
        self.assertEqual(len(self.backend.batches), 1)

        self.model._readings.clear()
        self.backend.bonus[short] = (self.model.eos, -9)
        self.assertEqual(nll("本文", ["か"]), result[:1])
        self.assertEqual(nll("本文", ["かな"]), result[1:2])
        self.model._readings.clear()
        self.assertEqual(nll("本文", ["か", "かな"]), result[:2])

        self.model._readings.clear()
        self.backend.bonus.pop(long[:-1])
        self.assertGreater(nll("本文", ["かな"])[0], result[1])

    def test_cache_tracks_the_effective_prompt(self):
        nll = self.model.reading_nll
        tail = "𠮷" * 38 + " 甲"
        a = nll("文頭\n" + tail, ["か", "かな"])
        self.backend.bonus[START + "カ" + CONTEXT + "𠮷" * 38 + "　乙"] = (
            self.backend.vocab[END], 4)
        b = nll(tail[:-1] + "乙", ["か", "かな"])
        self.assertLess(b[0], a[0])
        self.assertEqual(nll("別の文頭" + tail.replace(" ", "　"), ["か", "かな"]), a)
        self.assertNotEqual(nll(" ", ["か"]), nll("", ["か"]))
        self.assertEqual(nll("　", ["か"]), nll(" ", ["か"]))
        self.assertEqual(nll("\n\n", ["か"]), nll("", ["か"]))
        self.assertEqual(nll(tail[:-1] + "乙", ["かな", "か"]), b[::-1])
        self.assertEqual(len(self.backend.batches), 4)


class ContextReadingTest(unittest.TestCase):
    def setUp(self):
        self.sess = ImeSession(_table=load_table(), _lex=real_lex())
        self.reviewer = Mock()
        self.reviewer.candidate_nll.side_effect = lambda context, rows: [0.0] * len(rows)
        self.reviewer.reading_nll.side_effect = lambda context, readings: [
            (0.0 if r == "きどく" else 10.0) if context == MESSAGE else 0.0
            for r in readings
        ]
        self.reviewer.review.return_value = None
        self.sess.lm = ZenzConverter(self.reviewer)

    @staticmethod
    def events(context, **first):
        events = Typist().kana("きどく").space().events
        events[0].update(left_context=context, **first)
        return events

    def replay(self, context):
        dispatch(self.sess, {"op": "reset"})
        events = self.events(context)
        for event in events[:-2]:
            reply = dispatch(self.sess, event)
        self.assertEqual(reply["composition"], "記憶")
        self.reviewer.reading_nll.assert_not_called()
        for event in events[-2:]:
            reply = dispatch(self.sess, event)
        return reply

    def assert_reading(self, reply, reading, surface):
        self.assertEqual("".join(seg["reading"] for seg in reply["segments"]), reading)
        self.assertEqual(reply["composition"], surface)

    def test_space_compares_unique_readings_using_document_context(self):
        for context, reading, surface in (
            ("", "きおく", "記憶"),
            (MESSAGE, "きどく", "既読"),
            (CHILDHOOD, "きおく", "記憶"),
        ):
            with self.subTest(context=context):
                self.reviewer.reset_mock()
                self.assert_reading(self.replay(context), reading, surface)
                self.reviewer.reading_nll.assert_called_once_with(context, ["きおく", "きどく"])
                self.reviewer.review.assert_called_once_with(context, reading, surface, b"")

    def test_surface_review_cannot_reopen_the_reading(self):
        self.reviewer.review.return_value = spell("記憶"), True
        self.assert_reading(self.replay(MESSAGE), "きどく", "既読")
        self.assertTrue(all(segment.zenz is None for segment in self.sess.segments))

    def test_single_reading_skips_scoring(self):
        k = Keys(lambda msg: dispatch(self.sess, msg))
        k.tap("K", left_context="文頭")  # き
        reply = k.tap(SPACE)
        self.assertEqual("".join(seg["reading"] for seg in reply["segments"]), "き")
        self.reviewer.reading_nll.assert_not_called()
        self.reviewer.review.assert_called_once()

    def test_unavailable_document_context_uses_the_commit_only(self):
        self.assert_reading(self.replay(MESSAGE), "きどく", "既読")
        k = Keys(lambda msg: dispatch(self.sess, msg))
        k.t = self.events(MESSAGE)[-1]["t"]
        seq = k.commit()
        self.reviewer.reset_mock()
        for event in self.events(None, after_commit_seq=seq):
            reply = dispatch(self.sess, {**event, "t": event["t"] + k.t + 100})
        self.assert_reading(reply, "きおく", "記憶")
        self.reviewer.reading_nll.assert_called_once_with("既読", ["きおく", "きどく"])

    def test_prefetch_can_only_be_used_for_the_same_context(self):
        self.sess.lm = None
        worker = ManualWorker(self.sess._lex, self.reviewer, eager_prefetch=True)
        pipe = ConnectionPipeline(self.sess, worker, clock=worker.clock)
        *down, up = self.events(MESSAGE)
        for event in down:
            pipe.handle(event)
        prefetch = pipe.spec
        self.assertIsNotNone(prefetch)
        self.assert_reading(pipe.handle(up), "きどく", "既読")
        self.assertEqual(worker.jobs, [prefetch])
        self.reviewer.reading_nll.assert_called_once_with(MESSAGE, ["きおく", "きどく"])

        other = ImeSession(_table=self.sess._table, _lex=self.sess._lex)
        pipe = ConnectionPipeline(other, worker, clock=worker.clock, prefetch="off")
        self.reviewer.reset_mock()
        *down, up = self.events(CHILDHOOD)
        for event in down:
            pipe.handle(event)
        pipe.spec = prefetch  # exercise the key check with an otherwise identical request
        self.assert_reading(pipe.handle(up), "きおく", "記憶")
        self.assertEqual(len(worker.jobs), 2)
        self.assertEqual(worker.jobs[-1].request.parts, prefetch.request.parts)
        self.reviewer.reading_nll.assert_called_once_with(CHILDHOOD, ["きおく", "きどく"])

    def test_only_finished_on_time_conversion_changes_the_display(self):
        self.sess.lm = None
        for outcome in ("on_time", "deadline", "error", "reset"):
            with self.subTest(outcome=outcome), redirect_stderr(io.StringIO()) as log:
                entered, release = threading.Event(), threading.Event()

                def review(*args):
                    entered.set()
                    if not release.wait(5) or outcome == "error":
                        raise RuntimeError("review failed")
                    return None

                self.reviewer.reset_mock()
                self.reviewer.review.side_effect = review
                clock = Clock()
                worker = LmWorker(lambda: ZenzConverter(self.reviewer), self.sess._lex, clock=clock)
                try:
                    self.assertTrue(worker.wait_until_loaded())
                    pipe = ConnectionPipeline(self.sess, worker, prefetch="off", clock=clock,
                                              timing=True)
                    pipe.handle({"op": "reset"})
                    for event in self.events(MESSAGE):
                        reply = pipe.handle(event)
                    self.assertTrue(reply["pending"])
                    self.assertEqual(reply["composition"], "記憶")
                    job = pipe.job
                    self.assertTrue(entered.wait(5))
                    self.reviewer.review.assert_called_once_with(MESSAGE, "きどく", "既読", b"")
                    if outcome == "reset":
                        self.assertEqual(pipe.handle({"op": "reset"})["composition"], "")
                    clock.now = job.deadline + (0.001 if outcome == "deadline" else -0.001)
                    if outcome == "deadline":
                        self.assert_reading(pipe.handle(TERMINAL), "きおく", "記憶")
                    release.set()
                    self.assertTrue(job.done.wait(5))
                    reply = pipe.handle(TERMINAL)
                    self.assertFalse(reply["pending"])
                    if outcome == "reset":
                        self.assertEqual(reply["composition"], "")
                        self.assertTrue(job.cancelled)
                    elif outcome == "on_time":
                        self.assert_reading(reply, "きどく", "既読")
                    else:
                        self.assert_reading(reply, "きおく", "記憶")
                        self.assertIn(f"outcome={outcome}", log.getvalue())
                finally:
                    release.set()
                    worker.stop()
                    worker.thread.join(5)

    def test_first_path_per_reading_and_first_minimum(self):
        best = DecodeResult("あ", "亜", 0, [])
        same = DecodeResult("あ", "阿", -100, [])
        second = DecodeResult("い", "胃", 500, [])
        cheaper = DecodeResult("い", "意", 0, [])
        third = DecodeResult("う", "鵜", 1000, [])
        args = ("文脈", best, [], self.sess._lex, BOS_ID)
        self.reviewer.reading_nll.side_effect = None
        ranked = [same, second, cheaper, third]
        with patch("yuragi.ime.zenz.nbest_tokens", return_value=(ranked, {})):
            self.reviewer.reading_nll.return_value = [2, 1, 0]
            self.assertIs(self.sess.lm.reading(*args), best)
            self.reviewer.reading_nll.return_value = [3, 1, 0]
            self.assertIs(self.sess.lm.reading(*args), second)
        self.reviewer.reading_nll.assert_called_with("文脈", ["あ", "い", "う"])

    def test_readings_reach_the_model_past_homophones(self):
        """The 4 cheapest paths of うつだ are all うつり (移り・映り・写り・移)."""
        reverse = reverse_table(self.sess._table)
        tokens = [reverse[kana] for kana in "うつだ"]
        best, _ = decode_tokens(tokens, self.sess._lex)
        self.reviewer.reading_nll.side_effect = lambda context, readings: [
            0 if reading == "うつだ" else 100 for reading in readings]
        picked = self.sess.lm.reading("", best, tokens, self.sess._lex, BOS_ID)
        self.assertEqual(picked.reading, "うつだ")
