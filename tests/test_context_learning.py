"""Contextual learning through confirmed selections and LM conversion requests."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from tests.real_dictionary import real_lex
from tests.test_document_context import Keys
from tests.test_engine_sessions import EngineCase
from tests.test_lm_async import ManualWorker
from yuragi.chord.fsm import Plain, ThumbTap
from yuragi.ime import learning_admin
from yuragi.ime.bunsetsu import Bunsetsu, Candidate
from yuragi.ime.learning import LearningStore
from yuragi.ime.lm_async import DEADLINE_MS, ConnectionPipeline
from yuragi.ime.server import argument_parser, dispatch, load_session
from yuragi.ime.session import ImeSession, Literal
from yuragi.ime.zenz import ZenzConverter, spell
from yuragi.lattice.mozc_dict import DEFAULT_NOUN_ID
from yuragi.lattice.table import load_table

ENTER, SPACE, ESC = 0x0D, 0x20, 0x1B
LEFT, RIGHT, DOWN, NEXT, DELETE = 0x25, 0x27, 0x28, 0x22, 0x2E


class Review:
    def __init__(self, text, *, exact=True):
        self.fix = (spell(text) if isinstance(text, str) else text, exact)
        self.calls = []

    def reading_nll(self, context, readings):
        return [0.0 for _ in readings]

    def candidate_nll(self, context, candidates):
        return [0.0] * len(candidates)

    def review(self, context, reading, draft, accepted, reachable):
        """Like the model, pass a draft that already writes the fix."""
        self.calls.append((context, reading, draft))
        text, exact = self.fix
        if spell(draft) == text or not exact and spell(draft).startswith(text):
            return None
        return self.fix


def word(reading, surface, *, cost=5200, kind="dictionary"):
    return Candidate(surface, reading, 0, DEFAULT_NOUN_ID, DEFAULT_NOUN_ID, kind, cost)


class ContextLearningTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lex = real_lex()

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "learning.jsonl"

    def rows(self):
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()]

    def session(self, model=None):
        return ImeSession(_lex=self.lex, _table=load_table(),
                          _learning=LearningStore(self.path),
                          lm=ZenzConverter(model) if model else None)

    def learn(self, prev, surface, *, reading="こうせい", cost=5200):
        LearningStore(self.path).confirm(
            [word(reading, surface, cost=cost)], self.lex,
            prev=Bunsetsu("", prev) if prev else None)

    @staticmethod
    def plain(s, reading, *, after=None):
        """Type reading, unambiguous; after: the commit it continues (TIP's seq)."""
        s.start_input(None, after, disconnected=after is None)
        s._table = {"keys": {c: {"plain": c} for c in reading}}
        s._ingest([Literal(c) if c in "１２、" else Plain(c) for c in reading])

    @staticmethod
    def pick(keys, reply, surface):
        if reply["phase"] == "converting":
            reply = keys.tap(SPACE)
        while surface not in reply["candidates"] and reply["has_next_page"]:
            reply = keys.tap(NEXT)
        return keys.tap(ord("1") + reply["candidates"].index(surface))

    @staticmethod
    def choose_other(keys, reading):
        """Convert, focus the clause with this reading, pick its second row; that surface."""
        reply = keys.tap(SPACE)
        while reply["segments"][reply["focus"]]["reading"] != reading:
            reply = keys.tap(RIGHT)
        if reply["phase"] == "converting":
            keys.tap(SPACE)
        reply = keys.tap("2")
        return reply["segments"][reply["focus"]]["surface"]

    def assert_head(self, keys, reply, surface):
        if reply["phase"] == "converting":  # the first conversion keeps the window closed
            return self.assert_hidden_head(keys, reply, surface)
        self.assertEqual(reply["segments"][reply["focus"]]["surface"], surface)
        self.assertEqual(reply["candidates"][0], surface)

    def assert_hidden_head(self, keys, reply, surface):
        self.assertEqual(reply["segments"][reply["focus"]]["surface"], surface)
        self.assertEqual(keys.tap(SPACE)["candidates"][0], surface)
        keys.tap("1")  # restore the shown selection after opening the list

    def test_same_session_standalone_real_keys_and_lm_vote_for_older_choice(self):
        for model in (None, Review("厚生")):
            with self.subTest(lm=model is not None):
                self.path.write_bytes(b"")
                s = self.session(model)
                keys = Keys(lambda msg: dispatch(s, msg))
                start = {"after_commit_seq": None}
                expected = None
                for surface in ("公正", "厚生", "公正", None):
                    keys.tap("R", **start)  # こ
                    for key in "AGL":  # うせい
                        keys.tap(key)
                    result = keys.tap(SPACE)
                    if expected is not None:
                        self.assert_head(keys, result, expected)
                    if surface is None:
                        break
                    self.pick(keys, result, surface)
                    seq = keys.commit()
                    start = {"after_commit_seq": seq}  # TIP verified position, text unavailable
                    expected = surface
                self.assertEqual([r["surface"] for r in self.rows()], ["公正", "厚生", "公正"])
                self.assertTrue(all("prev" not in r for r in self.rows()))

    def test_document_left_then_lm_after_restart(self):
        for reading, left, selected in (("げんこうの", "原稿の", "校正"),
                                        ("かいぎの", "会議の", "構成")):
            s = self.session()
            k = Keys(lambda msg: dispatch(s, msg))
            self.plain(s, reading + "こうせい")
            self.pick(k, k.tap(SPACE), left)
            self.pick(k, k.tap(RIGHT), selected)
            k.commit()

        initial = self.path.read_bytes()
        # The left word 原稿 matches across particles. Another left word or
        # document text alone leaves the LM's pick in place.
        for reading, left, vote, expected in (
                ("げんこうを", "原稿を", "構成", "校正"), ("しりょうの", "資料の", "公正", "公正"),
                (None, None, "校正", "校正"), (None, None, "公正", "公正")):
            with self.subTest(left=left, vote=vote):
                self.path.write_bytes(initial)
                model = Review(vote)
                s = self.session()
                k = Keys(lambda msg: dispatch(s, msg))
                if left:
                    self.plain(s, reading)
                    k.commit()
                    start = {"after_commit_seq": k.seq}
                else:
                    start = {"left_context": "識別用外部本文原稿の", "after_commit_seq": None}
                s.lm = ZenzConverter(model)
                s._table = load_table()
                k.tap("R", **start)
                for key in "AGL":
                    k.tap(key)
                result = k.tap(SPACE)
                self.assert_head(k, result, expected)
                if left:
                    # Cancel conversion but keep the connected position of this input.
                    for _ in range(4):  # closes the window first
                        if k.tap(ESC)["phase"] == "composing":
                            break
                    self.assertEqual(s.phase, "composing")
                    self.assert_head(k, k.tap(SPACE), expected)
                    self.pick(k, k.tap(LEFT), "構成")
                k.commit()
                if left:
                    self.assertEqual(self.rows()[-1].get("prev"), left[:-1])
                else:  # committed as shown: nothing learned
                    self.assertEqual(self.path.read_bytes(), initial)
                self.assertNotIn("識別用外部本文", self.path.read_text(encoding="utf-8"))

    def test_revisit_same_pos_left_edit_and_partial_commit(self):
        self.learn("原稿の", "校正")
        self.learn("現行の", "構成")
        s = self.session(Review("原稿の校正"))
        k = Keys(lambda msg: dispatch(s, msg))
        self.plain(s, "げんこうのこうせい")
        first = k.tap(SPACE)
        self.assertEqual(first["segments"][0]["surface"], "原稿の")
        self.assert_hidden_head(k, k.tap(RIGHT), "校正")
        right = s.segments[1]
        old_stream = right.choices
        left_rid = s.segments[0].selected.rid
        self.pick(k, k.tap(LEFT), "現行の")
        self.assertEqual(s.segments[0].selected.rid, left_rid)
        revisited = k.tap(RIGHT)
        self.assertEqual(revisited["segments"][1]["surface"], "校正")
        revisited = k.tap(SPACE)
        self.assertEqual(revisited["candidates"][0], "構成")
        self.assertIsNot(right.choices, old_stream)
        self.assertIsNone(right.zenz)
        self.pick(k, revisited, "構成")
        partial = k.tap(DOWN, mods=["ctrl"])
        self.assertEqual(partial["commit"], "現行の")
        self.assertEqual(partial["segments"][0]["start"], 0)
        self.assert_hidden_head(k, partial, "構成")

    def test_word_choice_inside_compound_replays_with_another_particle(self):
        def convert(reading, draft):
            s = self.session(Review(draft))
            keys = Keys(lambda msg: dispatch(s, msg))
            self.plain(s, reading)
            return keys, keys.tap(SPACE)

        keys, shown = convert("げんこうこうせいを", "原稿構成を")
        self.pick(keys, shown, "原稿校正を")
        keys.commit()
        self.assertEqual([(p.reading, p.surface) for p in learning_admin.pairs(self.path)],
                         [("こうせい", "校正")])

        keys, other = convert("しりょうこうせいが", "資料構成が")
        self.assert_head(keys, other, "資料構成が")
        keys, replayed = convert("げんこうこうせいが", "原稿構成が")
        self.assert_head(keys, replayed, "原稿校正が")
        self.assert_head(keys, keys.tap(DELETE, mods=["ctrl"]), "原稿構成が")
        keys, reopened = convert("げんこうこうせいが", "原稿構成が")
        self.assert_head(keys, reopened, "原稿構成が")

    def test_partial_remainder_does_not_count_as_standalone_repeat(self):
        self.learn("公正", "厚生")
        self.learn(None, "公正")
        s = self.session(Review("公正厚生", exact=False))
        k = Keys(lambda msg: dispatch(s, msg))
        self.plain(s, "こうせいこうせい")
        k.tap(SPACE)
        partial = k.tap(DOWN, mods=["ctrl"])
        self.assertEqual(partial["commit"], "公正")
        self.assert_hidden_head(k, partial, "厚生")
        chosen = k.tap("2")["segments"][0]["surface"]
        k.commit()
        self.assertEqual((self.rows()[-1]["surface"], self.rows()[-1]["prev"]), (chosen, "公正"))
        self.assertFalse(s._last_commit.standalone)

    def test_boundaries_and_autocommit(self):
        self.learn(None, "原稿の", reading="げんこうの")
        s = self.session()
        k = Keys(lambda msg: dispatch(s, msg))
        cases = ("げんこうの１２こうせい", "げんこうの、こうせい")
        for text in cases:
            self.plain(s, text)
            self.choose_other(k, "こうせい")
            k.commit()
            self.assertEqual(self.rows()[-1]["reading"], "こうせい")
            self.assertNotIn("prev", self.rows()[-1])  # a literal to the left

        self.plain(s, "げんこうの")
        k.tap(SPACE)
        s._table = load_table()
        auto = k.tap("R")  # first key of こうせい also commits the previous input
        for key in "AGL":
            k.tap(key)
        self.choose_other(k, "こうせい")
        k.commit()
        self.assertEqual(self.rows()[-1]["prev"], auto["commit"])
        self.assertEqual(auto["commit"], "原稿の")

        result = k.tap(SPACE, after_commit_seq=k.seq)
        self.assertEqual(result["commit"], "　")
        k.tap("R", after_commit_seq=k.seq)
        for key in "AGL":
            k.tap(key)
        self.choose_other(k, "こうせい")
        k.commit()
        self.assertNotIn("prev", self.rows()[-1])

    def test_resize_uses_reading_of_the_new_interval(self):
        self.learn("げんこう", "野", reading="の", cost=50_000)
        self.learn("原稿", "ノ", reading="の", cost=50_000)
        self.learn(None, "の", reading="の")
        s = self.session(Review("原稿の"))
        self.learn(None, "原稿", reading="げんこう")
        # The learned whole clause makes the starting interval unambiguous.
        self.learn(None, "原稿の", reading="げんこうの")
        k = Keys(lambda msg: dispatch(s, msg))
        self.plain(s, "げんこうの")
        k.tap(SPACE)
        resized = k.tap(LEFT, mods=["shift"])
        self.assertEqual([seg["surface"] for seg in resized["segments"]], ["げんこう", "の"])
        self.assertEqual(k.tap(SPACE)["composition"], "原稿ノ")
        self.assert_hidden_head(k, k.tap(RIGHT), "ノ")
        k.commit()
        self.assertEqual(self.rows()[-1]["prev"], "原稿")

    def test_ctrl_delete_reselects_the_contextual_head_only_at_the_focus(self):
        self.learn("原稿の", "校正")
        self.learn("原稿の", "構成")
        self.learn("会議の", "構成")
        self.learn(None, "原稿の", reading="げんこうの")
        s = self.session()
        k = Keys(lambda msg: dispatch(s, msg))
        self.plain(s, "げんこうのこうせい")
        self.pick(k, k.tap(SPACE), "原稿の")
        left = s.segments[0]
        self.assert_hidden_head(k, k.tap(RIGHT), "構成")
        self.assert_head(k, k.tap(DELETE, mods=["ctrl"]), "校正")
        self.assertIs(s.segments[0], left)
        self.assertTrue(left.fixed)
        self.assertFalse(s._learning.has_pair("こうせい", "構成"))
        self.learn(None, "構成")
        self.assertEqual(s._learning.snapshot().head(
            "こうせい", Bunsetsu("かいぎの", "会議の"), zenz="校正").surface, "校正")

    def test_learning_off_ignores_history_and_does_not_record_a_choice(self):
        parser = argument_parser()

        def open_candidates(learning):
            args = parser.parse_args([
                "--learning", learning, "--learning-file", str(self.path),
                "--personal-file", str(self.path.with_name("personal.jsonl")),
                "--prediction", "off",
            ])
            session = load_session(args, lex=self.lex)
            keys = Keys(lambda msg: dispatch(session, msg))
            for key in "RAGL":  # こうせい
                keys.tap(key)
            keys.tap(SPACE)
            return keys, keys.tap(SPACE)["candidates"]

        enabled, original = open_candidates("on")
        enabled.tap("2")
        self.assertEqual(enabled.tap(ENTER)["commit"], original[1])
        recorded = self.path.read_bytes()
        self.assertTrue(recorded)
        self.assertEqual(open_candidates("on")[1][0], original[1])

        disabled, candidates = open_candidates("off")
        self.assertEqual(candidates[0], original[0])
        disabled.tap("3")
        self.assertEqual(disabled.tap(ENTER)["commit"], original[2])
        self.assertEqual(self.path.read_bytes(), recorded)

    def test_far_learned_row_and_snapshot_until_next_conversion(self):
        self.learn("原稿の", "私製校正", cost=50_000)
        self.learn("会議の", "構成")
        self.learn(None, "原稿の", reading="げんこうの")
        s = self.session()
        k = Keys(lambda msg: dispatch(s, msg))
        self.plain(s, "げんこうのこうせい")
        k.tap(SPACE)
        self.assert_hidden_head(k, k.tap(RIGHT), "私製校正")
        self.learn("原稿の", "厚生")
        k.tap(LEFT)
        self.assert_hidden_head(k, k.tap(RIGHT), "私製校正")
        for _ in range(4):  # closes the window first
            if k.tap(ESC)["phase"] == "composing":
                break
        self.assertEqual(s.phase, "composing")
        k.tap(SPACE)
        self.assert_hidden_head(k, k.tap(RIGHT), "厚生")

    def test_prefix_review_does_not_vote_for_uncovered_or_changed_segments(self):
        self.learn(None, "校正")
        self.learn(None, "構成", cost=50_000)
        initial = self.path.read_bytes()
        # One review per run: the LM's constraint ends where its fix ends.
        for text, exact, left_override, expected in (
                ("原稿の校正", True, False, "校正"),
                ("原稿の", False, False, "構成"),
                # Ends inside こうせい: its draft 厚生 is not confirmed above the learned row.
                (spell("原稿の") + spell("厚")[:1], False, False, ["構成", "厚生"]),
                ("原稿の校正", True, True, "構成"),
                ("存在しない経路", True, False, "構成")):
            with self.subTest(text=text, left_override=left_override):
                self.path.write_bytes(initial)
                # Chosen after 会議の: overrides the LM's 原稿の after that left.
                self.learn("会議の" if left_override else None,
                           "現行の" if left_override else "原稿の",
                           reading="げんこうの", cost=50_000)
                s = self.session()
                k = Keys(lambda msg: dispatch(s, msg))
                start = {}
                if left_override:
                    self.plain(s, "かいぎの")
                    start = {"after_commit_seq": k.commit()}
                s.lm = ZenzConverter(Review(text, exact=exact), steps=1)
                self.plain(s, "げんこうのこうせい", after=start.get("after_commit_seq"))
                first = k.tap(SPACE)
                if left_override:
                    self.assertEqual(first["segments"][0]["surface"], "現行の")
                if isinstance(expected, list):
                    k.tap(RIGHT)
                    self.assertEqual(k.tap(SPACE)["candidates"][:2], expected)
                else:
                    self.assert_hidden_head(k, k.tap(RIGHT), expected)

    def test_lm_failure_uses_the_same_snapshot_without_a_vote(self):
        self.learn(None, "校正")
        self.learn(None, "構成", cost=50_000)
        s = self.session(Review("校正"))
        k = Keys(lambda msg: dispatch(s, msg))
        self.plain(s, "こうせい")
        with patch.object(s.lm.model, "review", side_effect=RuntimeError("外部本文")):
            with redirect_stderr(io.StringIO()) as log:
                self.assert_head(k, k.tap(SPACE), "構成")
        self.assertNotIn("外部本文", log.getvalue())

    def test_partial_commit_keeps_lm_evidence_of_the_rest(self):
        self.learn(None, "現行の", reading="げんこうの", cost=50_000)
        self.learn(None, "校正")
        self.learn(None, "構成", cost=50_000)

        class TwoRuns(Review):
            def review(self, context, reading, draft, accepted, reachable):
                self.fix = spell("存在しない経路" if reading == "げんこうの" else "校正"), True
                return super().review(context, reading, draft, accepted, reachable)

        model = TwoRuns("")
        s = self.session(model)
        k = Keys(lambda msg: dispatch(s, msg))
        self.plain(s, "げんこうの、こうせい")
        reply = k.tap(SPACE)
        self.assertEqual(reply["composition"], "現行の、校正")
        k.tap(DOWN, mods=["ctrl"])
        partial = k.tap(DOWN, mods=["ctrl"])
        self.assert_hidden_head(k, partial, "校正")

    def test_worker_prefetch_snapshot_and_deadline(self):
        for mode in ("hit", "miss", "deadline"):
            with self.subTest(mode=mode):
                self.path.write_bytes(b"")
                self.learn(None, "校正")
                self.learn(None, "構成", cost=50_000)
                model = Review("校正")
                s = self.session()
                self.plain(s, "こうせい")
                delay = (lambda _: 100) if mode == "deadline" else (lambda _: 0)
                worker = ManualWorker(self.lex, model, delay=delay, eager_prefetch=True)
                pipe = ConnectionPipeline(s, worker, clock=worker.clock, grace_ms=0,
                                          prefetch="on")
                k = Keys(pipe.handle)
                k.send("down", SPACE)
                prefetch = pipe.spec
                if mode in ("miss", "deadline"):
                    self.learn(None, "厚生", cost=50_000)
                reply = k.send("up", SPACE)
                if mode == "hit":
                    self.assertEqual(len(worker.jobs), 1)
                else:
                    self.assertNotEqual(prefetch.request.key, worker.jobs[-1].request.key)
                if mode == "deadline":
                    self.assertTrue(reply["pending"])
                    wanted = pipe.job
                    picks = wanted.request.decode(self.lex, worker.template)
                    self.assertEqual(k.send("down", ENTER)["commit"], "")
                    count = len(self.rows())
                    worker.clock.now += DEADLINE_MS / 1000 + .001
                    with redirect_stderr(io.StringIO()):
                        reply = k.send("timeout")
                    self.assertEqual(reply["commit"], "厚生")  # deadline used the new snapshot
                    wanted.picks = picks  # the already-running inference finishes late
                    wanted.completed_at = worker.clock()
                    wanted.done.set()
                    self.assertEqual(k.send("timeout")["composition"], "")
                    self.assertEqual(len(self.rows()), count)
                else:
                    self.assert_head(k, reply, "校正")

    def test_compaction_retains_context_losers_and_pair_representatives(self):
        # Old rows (legacy left text; choices of another pair with a malformed
        # prev, which reads as none; one from before choices were told apart,
        # no "choice"), equal times, the clock moving backwards.
        legacy = dict(reading="こうせい", surface="公正", timestamp=1000, cost=5200,
                      lid=DEFAULT_NOUN_ID, rid=DEFAULT_NOUN_ID, left="原稿の")
        with self.path.open("w", encoding="utf-8") as stream:
            for prev in (None, "", ["原稿の"]):
                row = {**legacy, "reading": "こう", "surface": "公", "prev": prev,
                       "choice": True}
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            stream.write(json.dumps(legacy, ensure_ascii=False) + "\n")
        with patch("yuragi.ime.learning.time.time", return_value=2000):
            self.learn("原稿の", "校正")
            self.learn("資料の", "校正")
        with patch("yuragi.ime.learning.time.time", return_value=1):
            self.learn(None, "校正", cost=5000)
            self.learn("原稿の", "構成")
            self.learn("会議の", "構成")
            for _ in range(8):
                self.learn(None, "構成")
        store = LearningStore(self.path)
        contexts = [Bunsetsu("", s) for s in ("原稿の", "資料の", "会議の")]

        def view():
            snap = store.snapshot()
            paths = [{"kind": "plain", "kana": c} for c in "こうせい"]
            return (learning_admin.pairs(self.path), list(snap.learned()),
                    list(snap.spans(paths, 0, self.lex)),
                    [getattr(snap.head("こうせい", prev, zenz="公正"), "surface", None)
                     for prev in contexts])

        before = view()
        self.assertEqual(before[-1], ["構成", "校正", "構成"])
        self.assertEqual(len(before[0]), len(before[1]))
        self.assertEqual(len(before[1]), len(before[2]))
        self.assertEqual(store.snapshot().head("こうせい", contexts[1]).cost, 5000)
        self.assertEqual(store.compact_if_needed(min_lines=0), (17, 8))
        self.assertEqual(view(), before)
        self.assertIn("公正", self.path.read_text(encoding="utf-8"))  # kept, not used
        self.assertTrue(learning_admin.forget(self.path, "こうせい", "構成"))
        # 会議の has no choice left; the LM's 公正 stands.
        self.assertEqual(view()[-1], ["校正", "校正", None])
        self.learn(None, "構成")
        self.assertEqual(view()[-1], ["校正", "校正", None])
        store.confirm([word("こうせい", "校正", kind="symbol")], self.lex)
        self.learn(None, "校正")
        self.assertEqual(view()[-1], [None, None, None])

    def test_compaction_waits_until_more_than_half_the_rows_can_go(self):
        self.learn(None, "校正")
        for _ in range(3):
            self.learn(None, "構成")
        before = self.path.read_bytes()  # 4 rows, 2 to keep
        self.assertIsNone(LearningStore(self.path).compact_if_needed(min_lines=0))
        self.assertEqual(self.path.read_bytes(), before)

    def test_failed_append_reloads_history_and_can_learn_again(self):
        self.learn("原稿の", "校正")
        store = LearningStore(self.path)
        view = store.snapshot()

        def partial_write(rows):
            with self.path.open("ab") as out:
                out.write(b'{"reading":')
            raise OSError("append failed")

        with patch.object(store, "_append", side_effect=partial_write):
            with redirect_stderr(io.StringIO()):
                store.confirm([word("こうせい", "構成")], self.lex)
        self.assertEqual(store.records(), list(view.learned()))
        self.assertEqual(list(store.snapshot().learned()), list(view.learned()))
        self.assertEqual(store.skipped, 1)
        store.confirm([word("こうせい", "構成")], self.lex)
        self.assertEqual(LearningStore(self.path).snapshot().head("こうせい").surface, "構成")

    def test_compaction_serializes_with_a_second_writer(self):
        for _ in range(5):
            self.learn("原稿の", "校正")
        writer = LearningStore(self.path)
        compactor = LearningStore(self.path)
        replacing = threading.Event()
        resume = threading.Event()
        append_called = threading.Event()
        appended_to_file = threading.Event()
        from os import replace

        def paused_replace(*args):
            replacing.set()
            self.assertTrue(resume.wait(5))
            replace(*args)

        def append():
            append_called.set()
            writer.confirm([word("こうせい", "構成")], self.lex,
                           prev=Bunsetsu("かいぎの", "会議の"))
            appended_to_file.set()

        with patch("yuragi.ime.learning.os.replace", side_effect=paused_replace):
            with ThreadPoolExecutor(max_workers=2) as pool:
                compacted = pool.submit(compactor.compact_if_needed, min_lines=0)
                try:
                    self.assertTrue(replacing.wait(5))
                    appended = pool.submit(append)
                    self.assertTrue(append_called.wait(5))
                    self.assertFalse(appended_to_file.wait(.05))
                finally:
                    resume.set()
                self.assertEqual(compacted.result(timeout=5), (5, 1))
                appended.result(timeout=5)
        self.assertEqual([(r["surface"], r["prev"]) for r in self.rows()],
                         [("校正", "原稿の"), ("構成", "会議の")])


class LearningConnectionTest(EngineCase):
    def test_only_the_connection_that_confirmed_the_left_bunsetsu_uses_it(self):
        store = LearningStore(self.dir / "learning.jsonl")
        lex = real_lex()
        store.confirm([word("げんこうの", "原稿の"), word("こうせい", "校正")], lex)
        store.confirm([word("こうせい", "構成")], lex)
        loaded = ImeSession(_table=load_table(), _lex=lex, _learning=store)
        engine = self.engine(loaded=loaded)
        self.open(engine, 11)
        self.open(engine, 12)
        one = Keys(lambda msg: engine.request({"sid": 11, **msg}))
        two = Keys(lambda msg: engine.request({"sid": 12, **msg}))

        left = engine.connections[11].sess
        ContextLearningTest.plain(left, "げんこうの")
        left._table = loaded._table
        seq = one.commit()
        for keys, winner in ((one, "校正"), (two, "構成")):
            keys.tap("R", after_commit_seq=seq, left_context="原稿の")
            for key in "AGL":
                keys.tap(key)
            self.assertEqual(keys.tap(SPACE)["composition"], winner)
            self.assertEqual(keys.tap(SPACE)["candidates"][0], winner)  # the window opens


if __name__ == "__main__":
    unittest.main()
