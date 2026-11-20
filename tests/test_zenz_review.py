"""zenz review: the shared review budget, and reuse of the previous draft's KV."""
from __future__ import annotations

import unittest

from tests.real_dictionary import real_lex
from yuragi.ime.session import ImeSession, Literal
from yuragi.ime.zenz import DEFAULT_MODEL, ZenzConverter, ZenzModel, prompt, spell
from yuragi.lattice.table import load_table
from yuragi.chord.fsm import Plain


class Disagrees:
    """For each reading, wants an option other than the first draft; passes
    once the draft writes it."""

    def __init__(self, options):
        self.options = options
        self.wanted = {}
        self.calls = []

    def reading_nll(self, context, readings):
        return [0.0 for _ in readings]

    def review(self, context, reading, draft, accepted):
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
        s._table = {"keys": {c: {"plain": c} for c in text}}
        s._ingest([Literal(c) if c == "、" else Plain(c) for c in text])
        self.assertIsNotNone(s.conversion_request().decode(s._lex, s.lm))
        self.assertEqual(model.calls, ["げんこうの", "こうせい"])
        self.assertEqual(s.lm.last["cut"], 2)


def load_model():
    try:
        return ZenzModel(DEFAULT_MODEL, device="cpu")
    except Exception:  # no torch/transformers, or the model is not downloaded
        return None


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
        self.assertNotEqual(cases["no shared prefix"][0], a[0])
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
