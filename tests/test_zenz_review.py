"""zenz review: the shared review budget, the model's fixes no path can write,
and reuse of the previous draft's KV."""
from __future__ import annotations

from contextlib import nullcontext
import math
from types import SimpleNamespace
import unittest

from tests.real_dictionary import real_lex
from tests.support import ingest_plain
from yuragi.ime.bunsetsu import Candidate
from yuragi.ime.session import ImeSession
from yuragi.ime.zenz import DEFAULT_MODEL, ZenzConverter, ZenzModel, prompt, spell
from yuragi.lattice.table import load_table


class Disagrees:
    """For each reading, wants an option other than the first draft; passes
    once the draft writes it."""

    def __init__(self, options):
        self.options = options
        self.wanted = {}
        self.calls = []

    def reading_nll(self, context, readings):
        return [0.0 for _ in readings]

    def candidate_nll(self, context, candidates):
        return [0.0] * len(candidates)

    def review(self, context, reading, draft, accepted, reachable):
        self.calls.append(reading)
        wanted = self.wanted.setdefault(
            reading, next(o for o in self.options[reading] if o != draft))
        return None if draft == wanted else (spell(wanted), True)


class ReviewBudgetTest(unittest.TestCase):
    def test_later_runs_get_their_first_review_after_the_budget(self):
        model = Disagrees({"げんこうの": ("原稿の", "現行の"), "こうせい": ("構成", "厚生")})
        s = ImeSession(_lex=real_lex(), _table=load_table(),
                       lm=ZenzConverter(model, review_budget_ms=0))
        text = "げんこうの、こうせい"
        s.start_input(None, None, disconnected=True)
        ingest_plain(s, text, literals="、")
        self.assertIsNotNone(s.conversion_request().decode(s._lex, s.lm))
        self.assertEqual(model.calls, ["げんこうの", "こうせい"])
        self.assertEqual(s.lm.last["cut"], 2)


class ReachTest(unittest.TestCase):
    def test_an_unreachable_token_gives_way_to_the_next(self):
        """Per position, the model's best tokens in order, down to the draft's own."""
        model = ZenzModel.__new__(ZenzModel)
        model.torch = SimpleNamespace(inference_mode=nullcontext)
        model.tok = SimpleNamespace(encode=lambda text, *, add_special_tokens: list(map(ord, text)))
        model.bytes = {ord(c): c.encode() for c in "あいうかきえ"}
        model.eos = 0
        a, i, u, ka, ki, e = map(ord, "あいうかきえ")
        for name, accepted, ranked, reachable, fix in (
            ("the 2nd token", "", [[a], [ka, ki, i], [u]], {("あき", False)}, ("あき", False)),
            ("</s>, then the 2nd", "", [[a], [0, ka], [u]], {("あか", False)}, ("あか", False)),
            ("</s> ends the text exactly", "", [[a], [0, ka], [u]], {("あ", True)}, ("あ", True)),
            ("none before the draft's token: on to the next position", "",
             [[a], [ka, i, ki], [e, u]], {("あき", False), ("あいえ", False)}, ("あいえ", False)),
            ("inside the accepted constraint, differences do not count", "あい",
             [[ka, a], [ki, i], [e, u]], {("か", False), ("あき", False), ("あいえ", False)},
             ("あいえ", False)),
        ):
            with self.subTest(name):
                model._guesses = lambda text, ids: ranked
                self.assertEqual(
                    model.review("", "あいう", "あいう", spell(accepted),
                                 lambda prefix, exact: (prefix.decode(), exact) in reachable),
                    (fix[0].encode(), fix[1]))


def load_model():
    try:
        return ZenzModel(DEFAULT_MODEL, device="cpu")
    except Exception:  # no torch/transformers, or the model is not downloaded
        return None


class CandidateLikelihoodTest(unittest.TestCase):
    def test_scores_only_surface_tokens_and_eos_with_each_candidates_reading(self):
        try:
            import torch
        except ImportError:
            self.skipTest("torch not available")

        short_prompt = prompt("前", "あ")
        long_prompt = prompt("前", "あい")
        ids = {text: tokens for text, tokens in (
            (short_prompt, [1, 2]), (long_prompt, [1, 3, 2]), ("会", [4]), ("会　議", [4, 5]),
        )}
        model = ZenzModel.__new__(ZenzModel)
        model.torch = torch
        model.device = "cpu"
        model.eos = 0
        model.tok = SimpleNamespace(encode=lambda text, *, add_special_tokens: ids[text])

        def forward(*, input_ids, use_cache):
            self.assertFalse(use_cache)
            self.assertEqual(input_ids.tolist(), [[1, 2, 4, 0, 0], [1, 3, 2, 4, 5]])
            logits = torch.zeros((2, 5, 6))
            logits[0, 1, 4] = 1
            logits[0, 2, 0] = 2
            logits[1, 3, 5] = 3
            logits[1, 4, 0] = 4
            return SimpleNamespace(logits=logits)

        model.model = forward
        scores = model.candidate_nll("前", (Candidate("会", "あ", 0, 0, 0),
                                           Candidate("会 議", "あい", 0, 0, 0)))
        nll = [math.log1p(5 * math.exp(-boost)) for boost in (1, 2, 3, 4)]
        self.assertAlmostEqual(scores[0], nll[0] + nll[1], places=6)
        self.assertAlmostEqual(scores[1], math.log(6) + nll[2] + nll[3], places=6)


class DraftCacheTest(unittest.TestCase):
    """Guesses after reviewing another draft equal those of a fresh forward."""

    @classmethod
    def setUpClass(cls):
        cls.model = load_model()
        if cls.model is None:
            raise unittest.SkipTest("zenz model not available")

    def ids(self, text):
        return self.model.tok.encode(text, add_special_tokens=False)

    def guesses(self, text, ids):
        with self.model.torch.inference_mode():
            return self.model._guesses(text, ids)

    def fresh(self, text, ids):
        self.model._prompt = None
        return self.guesses(text, ids)

    def test_shared_prefix_of_any_length(self):
        text = prompt("会議の資料を", "こうせいする")
        a = self.ids("構成する")
        cases = {
            "no shared prefix": self.ids("校正する"),
            "partly shared": a[:1] + self.ids("物"),
            "all of B shared": a[:1],
            "B equals A": a,
            "B extends A": a + self.ids("ので"),
        }
        for name, b in cases.items():
            with self.subTest(name):
                expected = self.fresh(text, b)
                self.fresh(text, a)
                self.assertEqual(self.guesses(text, b), expected)
                # The cache left behind serves the next draft as well.
                self.assertEqual(self.guesses(text, a), self.fresh(text, a))

    def test_a_new_prompt_starts_over(self):
        a = self.ids("構成する")
        self.fresh(prompt("", "こうせいする"), a)
        text = prompt("会議の資料を", "こうせいする")
        self.assertEqual(self.guesses(text, a), self.fresh(text, a))


if __name__ == "__main__":
    unittest.main()
