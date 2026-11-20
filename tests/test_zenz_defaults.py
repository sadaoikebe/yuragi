"""The product's zenz settings (2026-11-19, from the Windows measurement
of zenz medium): threads 4, k 4, one review, the same on CPU and GPU; the
engine waits for the LM and its deadline only detects a fault. No torch: the
model and torch are stand-ins.
"""
from __future__ import annotations

from argparse import Namespace
import io
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

from yuragi.engine import Engine
from yuragi.ime.session import ConversionRequest
from yuragi.ime import server, session, zenz
from yuragi.ime.lm_async import DEADLINE_MS


class DefaultsTest(unittest.TestCase):
    def test_build_converter_uses_the_defaults(self):
        made = {}

        class FakeModel:
            def __init__(self, model, *, threads, device):
                made.update(model=model, threads=threads, device=device)

            def review(self, *args):
                return None

        args = server.argument_parser().parse_args([])
        with (mock.patch.object(zenz, "ZenzModel", FakeModel),
              mock.patch.object(zenz, "cuda_devices", return_value=())):
            converter = server.build_converter(args)
        self.assertEqual(made, dict(model=zenz.DEFAULT_MODEL, threads=4, device="cpu"))
        self.assertEqual((converter.k, converter.steps, converter.alpha), (4, 1, 1.0))
        args = server.argument_parser().parse_args(
            ["--lm-threads", "2", "--lm-k", "8", "--lm-steps", "2", "--lm-device", "cpu"])
        with (mock.patch.object(zenz, "ZenzModel", FakeModel),
              mock.patch.object(zenz, "cuda_devices", return_value=())):
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

        with (mock.patch.object(zenz, "ZenzModel", FakeModel),
              mock.patch.object(zenz, "cuda_devices", return_value=())):
            server.build_converter(Namespace(lm_model=None, lm_threads=None, lm_alpha=None,
                                             lm_k=None, lm_steps=None))
        self.assertEqual(made, dict(threads=4, device="cpu"))

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


class DeviceStartupTest(unittest.TestCase):
    def setUp(self):
        self.devices = 2
        self.placement_failures = set()
        self.warmup_failures = set()
        self.placed = []
        self.warmed = []
        self.model_loads = []
        self.set_threads = mock.Mock()
        torch = SimpleNamespace(
            cuda=SimpleNamespace(device_count=lambda: self.devices),
            set_num_threads=self.set_threads,
            tensor=lambda rows, *, device: (rows, device),
        )

        def place(device):
            self.placed.append(device)
            if device in self.placement_failures:
                raise RuntimeError("model placement failed")
            return SimpleNamespace(eval=lambda: None)

        def load_model(name, **options):
            self.model_loads.append(options)
            return SimpleNamespace(to=place)

        tokenizer = SimpleNamespace(
            eos_token_id=1, byte_decoder={"a": 97}, get_vocab=lambda: {"a": 0},
        )
        transformers = SimpleNamespace(
            AutoModelForCausalLM=SimpleNamespace(from_pretrained=load_model),
            GPT2Tokenizer=SimpleNamespace(from_pretrained=lambda *a, **kw: tokenizer),
        )
        self.enterContext(mock.patch.dict(sys.modules, {"torch": torch, "transformers": transformers}))
        self.enterContext(mock.patch.object(zenz.ZenzModel, "review", autospec=True,
                                            side_effect=self.warm_up))
        self.enterContext(mock.patch("sys.stderr", new_callable=io.StringIO))

    def warm_up(self, model, *_):
        self.warmed.append(model.device)
        if model.device in self.warmup_failures:
            raise RuntimeError("model inference failed")

    def build(self, *argv):
        return server.build_converter(server.argument_parser().parse_args(argv))

    def test_uses_the_first_gpu_that_warms_up(self):
        model = self.build().model
        self.assertEqual(self.placed, ["cuda:0"])
        self.assertEqual(self.warmed, ["cuda:0"])
        self.assertEqual(model._ids([[0]]), ([[0]], "cuda:0"))
        self.set_threads.assert_called_once_with(4)
        self.assertTrue(self.model_loads[0]["local_files_only"])

    def test_uses_cpu_without_cuda_devices(self):
        self.devices = 0
        self.assertEqual(self.build().model.device, "cpu")
        self.assertEqual(self.warmed, ["cpu"])

    def test_reloads_on_cpu_after_cuda_placement_fails(self):
        self.devices = 1
        self.placement_failures.add("cuda:0")
        model = self.build().model
        self.assertEqual(self.placed, ["cuda:0", "cpu"])
        self.assertEqual(len(self.model_loads), 2)
        self.assertEqual(self.warmed, ["cpu"])
        self.assertEqual(model._ids([[0]]), ([[0]], "cpu"))

    def test_engine_tries_later_gpu_if_warmup_conversion_fails(self):
        conversions = []

        def convert(parts, lex, learning, context, converter, **kwargs):
            device = converter.model.device
            conversions.append(device)
            if device == "cuda:0":
                raise RuntimeError("warm-up conversion failed")

        engine = Engine(None, Namespace())
        engine.loaded = SimpleNamespace(_lex=object())
        request = ConversionRequest([], "", 0, None, ())
        args = server.argument_parser().parse_args([])
        with mock.patch.object(session, "conversion_picks", side_effect=convert):
            converter = engine.load_lm(server, args, request)
        self.assertEqual(converter.model.device, "cuda:1")
        self.assertEqual(self.warmed, ["cuda:0", "cuda:1"])
        self.assertEqual(conversions, ["cuda:0", "cuda:1"])

    def test_explicit_device_failure_is_reported(self):
        self.warmup_failures.add("cuda")
        with self.assertRaisesRegex(RuntimeError, "model inference failed"):
            self.build("--lm-device", "cuda")
        self.assertEqual(self.placed, ["cuda"])
        self.assertEqual(self.warmed, ["cuda"])


if __name__ == "__main__":
    unittest.main()
