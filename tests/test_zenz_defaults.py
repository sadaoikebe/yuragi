"""The product's zenz settings (2026-11-19, from the Windows measurement
of zenz medium): threads 4, k 4, one review, the same on CPU and GPU; the
engine waits for the LM and its deadline only detects a fault. No torch: the
model and torch are stand-ins.
"""
from __future__ import annotations

from argparse import Namespace
import unittest
from unittest import mock

from yuragi.engine import Engine
from yuragi.ime import server, zenz
from yuragi.ime.lm_async import DEADLINE_MS


class DefaultsTest(unittest.TestCase):
    def test_constants(self):
        self.assertEqual((zenz.DEFAULT_THREADS, zenz.DEFAULT_K, zenz.DEFAULT_STEPS), (4, 4, 1))
        self.assertEqual(zenz.DEFAULT_ALPHA, 1.0)  # not part of this change
        converter = zenz.ZenzConverter(model=None)
        self.assertEqual((converter.k, converter.steps, converter.alpha), (4, 1, 1.0))

    def test_build_converter_uses_the_defaults(self):
        made = {}

        class FakeModel:
            def __init__(self, model, *, threads, device):
                made.update(model=model, threads=threads, device=device)

            def review(self, *args):
                return None

        args = server.argument_parser().parse_args([])
        with mock.patch.object(zenz, "ZenzModel", FakeModel):
            converter = server.build_converter(args)
        self.assertEqual(made, dict(model=zenz.DEFAULT_MODEL, threads=4, device=None))
        self.assertEqual((converter.k, converter.steps, converter.alpha), (4, 1, 1.0))
        args = server.argument_parser().parse_args(
            ["--lm-threads", "2", "--lm-k", "8", "--lm-steps", "2", "--lm-device", "cpu"])
        with mock.patch.object(zenz, "ZenzModel", FakeModel):
            converter = server.build_converter(args)
        self.assertEqual((made["threads"], made["device"]), (2, "cpu"))
        self.assertEqual((converter.k, converter.steps), (8, 2))

    def test_build_converter_without_device_attribute(self):
        """Callers that build their own Namespace (tools/eval) still get the auto device."""
        made = {}

        class FakeModel:
            def __init__(self, model, *, threads, device):
                made.update(threads=threads, device=device)

            def review(self, *args):
                return None

        with mock.patch.object(zenz, "ZenzModel", FakeModel):
            server.build_converter(Namespace(lm_model=None, lm_threads=None, lm_alpha=None,
                                             lm_k=None, lm_steps=None))
        self.assertEqual(made, dict(threads=4, device=None))

    def test_engine_pipeline_deadline(self):
        settings = server.argument_parser().parse_args([])
        settings.require_lm = False
        self.assertIsNone(settings.lm_deadline_ms)
        engine = Engine(None, Namespace())
        engine.worker = object()
        engine.settings = settings
        self.assertEqual(engine.new_pipeline(sess=None).deadline_ms, DEADLINE_MS)
        settings.lm_deadline_ms = 250.0  # an evaluation override still works
        self.assertEqual(engine.new_pipeline(sess=None).deadline_ms, 250.0)


class FakeCuda:
    def __init__(self, available, works=True):
        self.available, self.works = available, works

    def is_available(self):
        return self.available


class FakeTensor:
    def __init__(self, value):
        self.value = value

    def __add__(self, other):
        return FakeTensor(self.value + other.value)

    def sum(self):
        return self

    def item(self):
        return self.value


class FakeTorch:
    def __init__(self, available, works=True):
        self.cuda = FakeCuda(available)
        self.works = works

    def ones(self, n, device):
        if not self.works:
            raise RuntimeError("CUDA error: no kernel image is available for execution on the device")
        return FakeTensor(float(n))


class DeviceTest(unittest.TestCase):
    def test_gpu_when_torch_can_use_it(self):
        self.assertEqual(zenz.pick_device(FakeTorch(True)), "cuda")

    def test_cpu_without_a_gpu(self):
        self.assertEqual(zenz.pick_device(FakeTorch(False)), "cpu")

    def test_cpu_when_the_gpu_cannot_run_torch(self):
        self.assertEqual(zenz.pick_device(FakeTorch(True, works=False)), "cpu")


class ModelPlacementTest(unittest.TestCase):
    """ZenzModel puts the model and every input on the device pick_device chose."""

    def load(self, torch_module, **kwargs):
        import sys
        import types
        calls = {}

        class Model:
            def to(self, device):
                calls["to"] = device
                return self

            def eval(self):
                return self

        class Auto:
            @staticmethod
            def from_pretrained(name, **kw):
                calls["model"] = (name, kw)
                return Model()

        class Tok:
            eos_token_id = 1
            byte_decoder = {"a": 97}

            @staticmethod
            def from_pretrained(name, **kw):
                return Tok()

            def get_vocab(self):
                return {"a": 0}

        transformers = types.SimpleNamespace(AutoModelForCausalLM=Auto, GPT2Tokenizer=Tok)
        with mock.patch.dict(sys.modules, {"torch": torch_module, "transformers": transformers}):
            model = zenz.ZenzModel("m", **kwargs)
        return model, calls

    def torch(self, available, works=True):
        fake = FakeTorch(available, works)
        fake.threads = []
        fake.set_num_threads = fake.threads.append
        fake.tensors = []
        fake.tensor = lambda rows, device: fake.tensors.append(device) or (rows, device)
        return fake

    def test_gpu(self):
        torch = self.torch(True)
        model, calls = self.load(torch)
        self.assertEqual((model.device, calls["to"], torch.threads), ("cuda", "cuda", [4]))
        self.assertEqual(model._ids([[0]]), ([[0]], "cuda"))
        self.assertTrue(calls["model"][1]["local_files_only"])

    def test_cpu(self):
        torch = self.torch(False)
        model, calls = self.load(torch)
        self.assertEqual((model.device, calls["to"], torch.threads), ("cpu", "cpu", [4]))
        self.assertEqual(model._ids([[0]]), ([[0]], "cpu"))

    def test_device_override(self):
        model, calls = self.load(self.torch(True), device="cpu", threads=2)
        self.assertEqual((model.device, calls["to"]), ("cpu", "cpu"))


if __name__ == "__main__":
    unittest.main()
