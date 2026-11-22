"""The engine's sessions, in process (DESIGN「エンジン」).

One engine serves every TIP connection: the dictionary, the face table, the
learning history and the word list are loaded once and shared; each sid has
its own session (chord FSM, composition, input mode, left context) and, with
the LM, its own pipeline.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import time
import unittest

from yuragi.engine import Engine, argument_parser
from yuragi.chord.keys import Chord
from yuragi.ime import config, server
from yuragi.ime.keymap import load_keymap
from yuragi.ime.lm_async import LmWorker
from yuragi.ime.zenz import ZenzConverter
from yuragi.ime.session import ImeSession
from yuragi.lattice.mozc_dict import Entry, MozcLex
from yuragi.lattice.table import load_table

def loaded_session():
    # A has plain=う. A confirmation of the initially second row must change the best.
    lex = MozcLex({"う": [Entry("宇", "う", 1, 1, 100), Entry("卯", "う", 1, 1, 200)]},
                  {"う"}, [0] * 4, 2)
    session = ImeSession(_table=load_table(), _lex=lex)
    session.load()
    return session


class Channel:
    def __init__(self):
        self.warnings = []
        self.events = []

    def warning(self, code):
        if code not in self.warnings:
            self.warnings.append(code)

    def clear_warning(self, code):
        if code in self.warnings:
            self.warnings.remove(code)

    def send(self, message):
        self.events.append(message)


class EngineCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.seq = 0

    def engine(self, loaded=None, worker=None, argv=()):
        args = argument_parser().parse_args(["--data-dir", str(self.dir), *argv])
        engine = Engine(Channel(), args)
        engine.loaded = loaded or loaded_session()
        engine.keymap = engine.loaded.keymap
        engine.worker = worker
        engine.settings = engine.read_settings(args, config, server)
        return engine

    def open(self, engine, sid):
        engine.serve([json.dumps({"op": "open", "sid": sid}).encode()])

    def request(self, engine, sid, msg):
        self.seq += 1
        reply = engine.request({"sid": sid, "seq": self.seq, **msg})
        self.assertEqual((reply["sid"], reply["seq"]), (sid, self.seq))
        return reply

    def type_a(self, engine, sid, t=0):
        self.request(engine, sid, {"op": "down", "vk": 65, "t": t})
        return self.request(engine, sid, {"op": "up", "vk": 65, "t": t + 30})

    def write_keymap(self, *rows):
        (self.dir / "keymap.json").write_text(json.dumps({
            "version": 1, "use": "custom", "custom": {"base": "ms-ime", "overrides": rows},
        }), encoding="utf-8")


class KeyDispatchTest(EngineCase):
    def test_shift_caps_lock_keeps_pending_input(self):
        engine = self.engine()
        self.open(engine, 1)
        reply = self.request(engine, 1, {"op": "down", "vk": 65, "t": 100})
        self.assertEqual(reply["phase"], "empty")
        self.assertGreater(reply["timer"], 101)

        reply = self.request(engine, 1, {"op": "down", "vk": 0x14, "t": 101, "mods": ["shift"]})
        self.assertIs(reply["eat"], True)
        self.assertEqual((reply["phase"], reply["composition"], reply["commit"]),
                         ("composing", "宇", ""))
        self.assertNotIn("global", reply)

    def test_shift_caps_lock_without_input_requests_toggle(self):
        engine = self.engine()
        self.open(engine, 1)
        reply = self.request(engine, 1, {"op": "down", "vk": 0x14, "mods": ["shift"]})
        self.assertIs(reply["eat"], False)
        self.assertEqual(reply["global"], "ime_toggle")
        self.assertEqual((reply["phase"], reply["commit"]), ("empty", ""))

    def test_tip_toggle_takes_priority_over_composing_binding(self):
        (self.dir / "tip.json").write_text('{"toggle_vk": 32, "toggle_mods": ["ctrl"]}',
                                          encoding="utf-8")
        engine = self.engine()
        engine.keymap = load_keymap(self.dir).compile()
        self.open(engine, 1)
        self.type_a(engine, 1)

        reply = self.request(engine, 1, {"op": "down", "vk": 32, "mods": ["ctrl"], "t": 100})
        self.assertIs(reply["eat"], False)
        self.assertEqual(reply["global"], "ime_toggle")
        self.assertEqual((reply["phase"], reply["composition"], reply["commit"]),
                         ("composing", "宇", ""))
        chord = Chord.parse("Ctrl+Space")
        table = engine.keymap.eat_table()
        self.assertIn({"code": chord.code, "command": "ime_toggle"}, table["global"])
        self.assertNotIn(chord.code, table["phases"]["composing"]["eat"])

    def test_reload_changes_existing_sessions_and_keeps_other_input(self):
        engine = self.engine()
        self.open(engine, 1)
        self.open(engine, 2)
        self.type_a(engine, 1)
        self.type_a(engine, 2)
        self.write_keymap(["composing", "Return", "cancel"],   # unknown chord
                          ["composing", "A", "cancel"],        # protected typing key
                          ["composing", "Ctrl+F3", "unrecognized_command"],
                          ["composing", "Enter", "commit"],
                          ["composing", "enter", "cancel"],      # wins after normalization
                          ["composing", "Space", "pass_through"],  # thumb key cannot be replayed
                          ["composing", "Ctrl+Space", "insert_half_space"])
        reply = self.request(engine, 1, {"op": "reload_keymap"})
        self.assertEqual(reply["keymap_reload"], "applied")
        self.assertEqual(len(load_keymap(self.dir).notes), 5)
        first = self.request(engine, 1, {"op": "down", "vk": 13, "t": 100})
        self.assertEqual((first["phase"], first["eat"], first["commit"]), ("empty", True, ""))
        second = self.request(engine, 2, {"op": "down", "vk": 32, "mods": ["ctrl"], "t": 100})
        self.assertEqual((second["phase"], second["eat"], second["composition"]), ("composing", True, "宇 "))
        self.request(engine, 2, {"op": "down", "vk": 32, "t": 200})
        second = self.request(engine, 2, {"op": "up", "vk": 32, "t": 230})
        self.assertTrue(second["converted"])  # the rejected Space override left conversion intact

    def test_broken_reload_retains_custom_map_and_broken_startup_uses_ms_ime(self):
        engine = self.engine()
        self.open(engine, 1)
        self.write_keymap(["composing", "Enter", "cancel"])
        self.request(engine, 1, {"op": "reload_keymap"})
        (self.dir / "keymap.json").write_text('{"use":"missing-preset"}', encoding="utf-8")
        self.assertEqual(self.request(engine, 1, {"op": "reload_keymap"})["keymap_reload"], "failed")
        self.assertIn("keymap", engine.channel.warnings)
        self.assertEqual(len(engine.channel.events), 1)  # no replacement sent

        self.type_a(engine, 1)
        self.assertEqual(self.request(engine, 1, {"op": "down", "vk": 13, "t": 100})["commit"], "")
        fresh = self.engine()
        fresh.keymap = fresh.read_keymap(load_keymap(self.dir))
        self.assertIn("keymap", fresh.channel.warnings)
        self.open(fresh, 2)
        self.type_a(fresh, 2)
        self.assertEqual(self.request(fresh, 2, {"op": "down", "vk": 13, "t": 100})["commit"], "宇")


class SlowModel:
    """Writes 卯 over the Viterbi 宇; each review sleeps (a slow model)."""

    def __init__(self, sleep=0.1):
        self.sleep = sleep

    def reading_nll(self, context, readings):
        return [0.0 for _ in readings]

    def candidate_nll(self, context, candidates):
        return [0.0] * len(candidates)

    def review(self, context, reading, draft, accepted, reachable):
        time.sleep(self.sleep)
        return None if draft.startswith("卯") else ("卯".encode(), False)


class LmPipelineTest(EngineCase):
    """The LM pipeline (lm_async.py), through the engine's sessions."""

    def wait_state(self, worker, state):
        deadline = time.monotonic() + 5
        while worker.state != state and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(worker.state, state)

    def test_pending_reply_then_poll_then_replay(self):
        loaded = loaded_session()
        worker = LmWorker(lambda: ZenzConverter(SlowModel()), loaded._lex)
        self.addCleanup(worker.thread.join, 5)
        self.addCleanup(worker.stop)
        self.wait_state(worker, "ready")
        engine = self.engine(loaded, worker)
        self.open(engine, 1)
        self.type_a(engine, 1)
        self.request(engine, 1, {"op": "down", "vk": 32, "t": 100})
        reply = self.request(engine, 1, {"op": "up", "vk": 32, "t": 130})
        self.assertEqual((reply["pending"], reply["converted"], reply["composition"],
                          reply["candidates"], reply["timer"]), (True, False, "宇", [], 140))
        t = 130
        while reply["pending"]:
            time.sleep(0.016)
            t += 16
            reply = self.request(engine, 1, {"op": "timeout", "t": t})
        self.assertEqual((reply["converted"], reply["composition"]), (True, "卯"))
        self.assertEqual(self.request(engine, 1, {"op": "down", "vk": 13, "t": 900})["commit"], "卯")
        # A key typed while the next conversion is pending waits behind it.
        self.type_a(engine, 1, 1000)
        self.request(engine, 1, {"op": "down", "vk": 32, "t": 1100})
        self.assertTrue(self.request(engine, 1, {"op": "up", "vk": 32, "t": 1130})["pending"])
        reply = self.type_a(engine, 1, 1140)
        self.assertEqual((reply["pending"], reply["composition"], reply["commit"]), (True, "宇", ""))
        t = 1200
        while reply["pending"]:
            time.sleep(0.016)
            reply = self.request(engine, 1, {"op": "timeout", "t": t})
            t += 16
        self.assertEqual((reply["commit"], reply["composition"], reply["converted"]),
                         ("卯", "宇", False))

    def test_reload_keeps_old_bindings_for_keys_already_waiting_for_lm(self):
        from tests.test_lm_async import ManualWorker, PickyModel

        loaded = loaded_session()
        worker = ManualWorker(loaded._lex, PickyModel(), delay=lambda _index: 100)
        engine = self.engine(loaded, worker, argv=["--lm-grace-ms", "0"])
        self.open(engine, 1)
        engine.connections[1].pipeline.clock = worker.clock
        self.type_a(engine, 1)
        self.request(engine, 1, {"op": "down", "vk": 32, "t": 100})
        self.assertTrue(self.request(engine, 1, {"op": "up", "vk": 32, "t": 130})["pending"])
        before = self.request(engine, 1, {"op": "down", "vk": 13, "t": 150})
        self.assertTrue(before["eat_pending"])

        self.write_keymap(["converting", "Enter", "noop"], ["empty", "Enter", "insert_half_space"])
        self.request(engine, 1, {"op": "reload_keymap"})
        after = self.request(engine, 1, {"op": "down", "vk": 13, "t": 170})
        self.assertTrue(after["eat_pending"])
        worker.complete_all()
        reply = self.request(engine, 1, {"op": "timeout", "t": 200})
        self.assertFalse(reply["pending"])
        self.assertEqual(reply["commit"], "宇 ")
        self.assertEqual(reply["resolved_keys"],
                         [{"seq": key["seq"], "eat": True} for key in (before, after)])

if __name__ == "__main__":
    unittest.main()
