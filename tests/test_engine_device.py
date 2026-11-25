"""When the engine restarts to choose its LM device again (CONVERSION「装置とモデル」).

A laptop's GPU stays awake while a CUDA context is held, so on battery the
engine leaves it; back on AC it tries it again. It restarts only when nobody is
typing: a restart drops what is being converted.
"""
from __future__ import annotations

from argparse import Namespace
import io
from types import SimpleNamespace
import unittest
from unittest import mock

from yuragi import engine as engine_module
from yuragi.engine import Engine
from yuragi.ime import power, server
from yuragi.ime.zenz import CALIBRATION_LIMIT_MS


def worker(device=None, failures=0, state="ready"):
    template = None if device is None else SimpleNamespace(model=SimpleNamespace(device=device))
    return SimpleNamespace(template=template, failures=failures, state=state)


class DeviceChangeTest(unittest.TestCase):
    def make(self, *, device, battery_at_load=False, gpu_model="medium", failures=0,
             state="ready"):
        engine = Engine(None, Namespace(data_dir=None))
        engine.worker = worker(device, failures, state)
        engine.lm_on_battery = battery_at_load
        engine.settings = SimpleNamespace(lm_model=gpu_model)
        return engine

    def change(self, engine, *, battery):
        with mock.patch.object(power, "on_battery", return_value=battery):
            return engine.device_change()

    def test_leaves_the_gpu_on_battery(self):
        self.assertIsNotNone(self.change(self.make(device="cuda:0"), battery=True))
        self.assertIsNone(self.change(self.make(device="cuda:0"), battery=False))

    def test_tries_the_gpu_again_on_ac_only_if_it_was_skipped_for_the_battery(self):
        on_battery = self.make(device="cpu", battery_at_load=True)
        self.assertIsNotNone(self.change(on_battery, battery=False))
        self.assertIsNone(self.change(on_battery, battery=True))
        # Chosen on AC: the GPU was tried then (too slow, failed or absent).
        self.assertIsNone(self.change(self.make(device="cpu"), battery=False))
        # A CPU-only installation has no GPU model.
        cpu_only = self.make(device="cpu", battery_at_load=True, gpu_model=None)
        self.assertIsNone(self.change(cpu_only, battery=False))

    def test_lm_off_on_battery_tries_again_on_ac(self):
        # small too slow on battery: no LM; on AC the GPU may do.
        disabled = self.make(device=None, battery_at_load=True, state="disabled")
        self.assertIsNotNone(self.change(disabled, battery=False))


class LmRetryTest(unittest.TestCase):
    """An LM too slow at a busy moment (sign-in) is calibrated once more; a far slower PC
    is not loaded again and again."""

    def retry(self, engine, fastest_ms):
        with mock.patch("sys.stderr", io.StringIO()):
            return engine.lm_retry_after(server.LmTooSlow("too slow", fastest_ms))

    def test_once_more_only_near_the_limit(self):
        engine = Engine(None, Namespace(data_dir=None))
        self.assertIsNone(self.retry(engine, 3 * CALIBRATION_LIMIT_MS))
        self.assertIsNotNone(self.retry(engine, 351))  # the sign-in of 2026-11-20
        self.assertIsNone(self.retry(engine, 351))
        self.assertIsNone(engine.lm_retry_after(RuntimeError("no kernel image")))


class IdleTest(unittest.TestCase):
    def make(self, **sess):
        engine = Engine(None, Namespace(data_dir=None))
        state = dict(tokens=[], converted=False, _await=None)
        state.update(sess)
        engine.connections = {1: SimpleNamespace(sess=SimpleNamespace(**state))}
        engine.last_request -= engine_module.IDLE_BEFORE_RESTART_S + 1
        return engine

    def test_not_idle_with_input_under_way(self):
        self.assertFalse(self.make(tokens=[object()]).idle())
        self.assertFalse(self.make(converted=True).idle())
        self.assertFalse(self.make(_await=object()).idle())

    def test_idle_only_a_while_after_the_last_key(self):
        engine = self.make()
        engine.last_request = engine_module.time.monotonic()
        self.assertFalse(engine.idle())
        engine.last_request -= engine_module.IDLE_BEFORE_RESTART_S + 1
        self.assertTrue(engine.idle())


if __name__ == "__main__":
    unittest.main()
