"""Building the zenz converter: device choice and fallback. No torch: the
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
from yuragi.ime import power, server, session, zenz


class DeviceStartupTest(unittest.TestCase):
    def setUp(self):
        self.devices = 2
        self.placement_failures = set()
        self.warmup_failures = set()
        self.placed = []
        self.warmed = []
        self.model_loads = []
        torch = SimpleNamespace(
            cuda=SimpleNamespace(device_count=lambda: self.devices),
            set_num_threads=lambda threads: None,
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
        self.enterContext(mock.patch.object(power, "on_battery", return_value=False))
        self.enterContext(mock.patch.object(zenz, "usable_cpus", return_value=8))
        self.enterContext(mock.patch.object(zenz.ZenzModel, "review", autospec=True,
                                            side_effect=self.warm_up))
        self.enterContext(mock.patch("sys.stderr", new_callable=io.StringIO))

    def warm_up(self, model, *_):
        self.warmed.append(model.device)
        if model.device in self.warmup_failures:
            raise RuntimeError("model inference failed")

    def build(self, *argv):
        return server.build_converter(server.argument_parser().parse_args(argv))

    def test_a_device_that_fails_hands_over_to_the_next(self):
        # Only the fallback loop is real here: the failures are stand-ins.
        with self.subTest("placement fails on the only GPU: reload on the CPU"):
            self.devices = 1
            self.placement_failures = {"cuda:0"}
            converter = self.build()
            self.assertEqual(converter.model.device, "cpu")
            self.assertFalse(converter.rank_candidates)
            self.assertEqual(self.placed, ["cuda:0", "cpu"])
            self.assertEqual(len(self.model_loads), 2)
            self.assertTrue(all(o["local_files_only"] for o in self.model_loads))  # no network
            self.assertEqual(self.warmed, ["cpu"])

        with self.subTest("the engine's warm-up conversion fails on a GPU: the next GPU"):
            self.devices = 2
            self.placement_failures, self.warmed = set(), []
            conversions = []

            def convert(parts, lex, learning, context, converter, **kwargs):
                device = converter.model.device
                conversions.append(device)
                if device == "cuda:0":
                    raise RuntimeError("warm-up conversion failed")

            engine = Engine(None, Namespace(data_dir=None))
            engine.loaded = SimpleNamespace(_lex=object(), _table={"keys": {}})
            request = ConversionRequest([], "", 0, None, ())
            args = server.argument_parser().parse_args([])
            with (mock.patch.object(session, "conversion_picks", side_effect=convert),
                  mock.patch.object(zenz, "calibrate", return_value=50.0)):
                converter = engine.load_lm(server, args, request)
            self.assertEqual(converter.model.device, "cuda:1")
            self.assertEqual(self.warmed, ["cuda:0", "cuda:1"])
            self.assertEqual(conversions, ["cuda:0", "cuda:1"])

        with self.subTest("a device named on the command line is not replaced"):
            self.placed, self.warmed = [], []
            self.warmup_failures = {"cuda"}
            with self.assertRaisesRegex(RuntimeError, "model inference failed"):
                self.build("--lm-device", "cuda")
            self.assertEqual(self.placed, ["cuda"])
            self.assertEqual(self.warmed, ["cuda"])


class CalibrateTest(unittest.TestCase):
    def test_uncached_conversions_of_the_faster_pass(self):
        """A stand-in LM: a reading it has seen since the last forget() is fast;
        the first pass is slower (the device warms up)."""
        readings = zenz.CALIBRATION_READINGS
        clock = [0.0]
        calls = []
        model = SimpleNamespace(seen=set())
        model.forget = model.seen.clear

        def convert(parts, lex, learning, context, converter):
            reading = "".join(parts[0])
            ms = 10 if reading in model.seen else 150 if len(calls) < len(readings) else 100
            model.seen.add(reading)
            calls.append(reading)
            clock[0] += ms / 1000

        converter = SimpleNamespace(model=model, last={})
        reverse = {kana: kana for reading in readings for kana in reading}
        with (mock.patch.object(zenz, "conversion_picks", side_effect=convert),
              mock.patch.object(zenz, "time", SimpleNamespace(perf_counter=lambda: clock[0]))):
            ms = zenz.calibrate(converter, None, reverse)
        self.assertAlmostEqual(ms, 100)


class CalibrationLadderTest(unittest.TestCase):
    """Which device and model the engine keeps, from each one's calibration time
    (CONVERSION「装置とモデル」), with the arguments setup.ps1 writes. Models are stand-ins."""

    GPU_INSTALL = ["--lm-model", "medium", "--lm-cpu-model", "small"]  # GPU build of torch
    CPU_INSTALL = ["--lm-cpu-model", "small"]

    def setUp(self):
        self.loaded = []
        self.times = {}
        self.gpus = ("cuda:0",)

        class FakeModel:
            def __init__(model, name, *, threads, device):
                self.loaded.append((device, name))
                if self.times.get((device, name)) == "fails":
                    raise RuntimeError("no kernel image is available for this GPU")
                model.name, model.device = name, device

            def review(model, *args):
                return None

        self.enterContext(mock.patch.object(zenz, "ZenzModel", FakeModel))
        self.enterContext(mock.patch.object(zenz, "cuda_devices", lambda: self.gpus))
        self.battery = False
        self.enterContext(mock.patch.object(power, "on_battery", lambda: self.battery))
        self.enterContext(mock.patch("sys.stderr", new_callable=io.StringIO))

    def build(self, argv, times, *, require_lm=False):
        self.times = times
        args = server.argument_parser().parse_args(argv)
        args.require_lm = require_lm
        calibration = lambda c: times[(c.model.device, c.model.name)]
        return server.build_converter(args, calibration=calibration, log=lambda m: None)

    def test_gpu_install_uses_medium_on_the_gpu_and_loads_nothing_else(self):
        converter = self.build(self.GPU_INSTALL, {("cuda:0", "medium"): 37})
        self.assertEqual((converter.model.device, converter.model.name), ("cuda:0", "medium"))
        self.assertEqual(self.loaded, [("cuda:0", "medium")])
        self.assertEqual(converter.calibration_ms, 37)  # the fault deadline is set from it

    def test_on_battery_the_gpu_is_not_tried(self):
        self.battery = True
        converter = self.build(self.GPU_INSTALL, {("cpu", "small"): 106})
        self.assertEqual((converter.model.device, converter.model.name), ("cpu", "small"))
        self.assertEqual(self.loaded, [("cpu", "small")])

    def test_too_slow_a_pc_converts_without_the_lm(self):
        self.gpus = ()  # the CPU build of torch
        with self.assertRaises(server.LmTooSlow):
            self.build(self.CPU_INSTALL, {("cpu", "small"): 400})

    def test_require_lm_keeps_the_last_candidate_however_slow(self):
        # dev-register.ps1 on a PC without a GPU: the default model on the CPU.
        self.gpus = ()
        converter = self.build([], {("cpu", zenz.DEFAULT_MODEL): 345}, require_lm=True)
        self.assertEqual(converter.model.device, "cpu")


if __name__ == "__main__":
    unittest.main()
