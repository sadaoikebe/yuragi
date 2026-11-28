"""The conversion engine (DESIGN「エンジン」): one JSON object per line on stdin/stdout.

The installed broker starts the bundled Python with the ``-c`` bootstrap in
``engine.json`` (DESIGN §1). With development Python, run
``python -m yuragi.engine``. The broker writes stderr to logs/engine.log.

Broker → engine:
  {"op":"open","sid":3}                    a TIP connection's session
  {"op":"close","sid":3}
  {"sid":3,"seq":17,"op":"down","vk":74,"t":123456,"mods":[]}
      op as for yuragi.ime.server: down/up/timeout/reset/set_direct/set_mode/suggest
      resolve asks for a conversion the engine said was ready (lm_done); it is no key
      reload_keymap reloads the key settings for all sessions
Engine → broker:
  {"ready":true,"proto":1,"warnings":[...],"keymap":{...}}
  {"sid":3,"seq":17, ...the reply of yuragi.ime.server...}   one per request, in order
      "error":true   the request raised; the session was started afresh (DESIGN「要求 1 件ごとの防壁」)
  {"event":"warning","warning":"lm"}       a warning found after ready
  {"event":"warning","warning":"keymap","active":false}  clears that warning
  {"event":"keymap","keymap":{...}}         an updated key table
  {"event":"lm_done","sid":3}               the conversion that waited for the LM is ready

Warnings can be lm (LM unavailable) or keymap (key settings could not load).
open/close have no reply. stdin closure initiates shutdown.

A startup failure ends the process with exit code 1 and the reason on stderr,
``fatal <reason>`` (DESIGN「止まるときの理由」): the broker keeps it in its log.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import threading
import time
import traceback

from yuragi.ime.config import DEFAULT_RUNTIME_DIR

PROTO = 1
MAX_TOKENS = 200  # DESIGN「定数」: the input length a conversion handles
# DESIGN「見張り」: exiting with this code after ready asks the broker to start the
# engine again without counting it as a failure (broker_core.h ENGINE_RESTART_CODE).
RESTART_CODE = 75
# CONVERSION「装置とモデル」: when the LM device should change (the power source),
# the engine restarts once nobody has typed for this long.
IDLE_BEFORE_RESTART_S = 60
POWER_POLL_S = 15
# At exit, an LM worker that does not stop (stuck in the LM) is not waited for longer.
WORKER_EXIT_S = 5
# CONVERSION「装置とモデル」: an LM found too slow is calibrated once more, this long
# after, if it was within LM_RETRY_FACTOR times the limit (a busy moment at sign-in,
# 2026-11-20: 351 ms there, 186 ms on the same PC when it was quiet). A PC far
# slower is not tried again.
LM_RETRY_DELAY_S = 300
LM_RETRY_FACTOR = 2
LM_RETRIES = 1
# The TIP is told this long after a job's deadline at the latest: past it by any clock.
LM_DONE_SLACK_S = 0.005
# Warm-up input (DESIGN「暖機」): かいはつしてきた on the NICOLA-A plain layer, then Space.
WARM_KEYS = (0x57, 0x4C, 0x48, 0x4F, 0x53, 0x44, 0x4B, 0x45)


def log(message: str) -> None:
    """One line on stderr (the broker keeps it in engine.log). Never input text."""
    stamp = datetime.now().isoformat(timespec="milliseconds")
    print(f"{stamp} engine: {message}", file=sys.stderr, flush=True)


def fatal(reason: str):
    log(f"stopping: {reason}")
    print(f"fatal {reason}", file=sys.stderr, flush=True)
    raise SystemExit(1)


def where(exc: BaseException) -> str:
    """The exception's type and its frames, innermost last; no message (it may hold text)."""
    frames = traceback.extract_tb(exc.__traceback__)
    path = " <- ".join(f"{Path(f.filename).name}:{f.lineno} {f.name}" for f in reversed(frames))
    return f"{type(exc).__name__} at {path}"


def encode_line(message: dict) -> bytes:
    """One message as a line. Half a surrogate pair (a hand-edited word, a cut
    emoji) becomes "?": text that cannot be sent must not end the engine."""
    return (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8", "replace")


class Channel:
    """The engine's half of the pipe: the real stdin and stdout, reserved for messages.

    Python's sys.stdout (and file descriptor 1) point at stderr instead, so a
    library that prints cannot corrupt the protocol. The standard input becomes
    NUL: on Windows, while this process waits on a synchronous read of the
    pipe, loading a DLL that looks at the standard input (numpy's OpenBLAS,
    when torch is imported on the LM worker) stalls until the next message
    arrives, which, with nobody typing, can be indefinitely.
    """

    def __init__(self):
        self.input = os.fdopen(os.dup(0), "rb")
        null = os.open(os.devnull, os.O_RDONLY)
        os.dup2(null, 0)  # also the process's standard input handle (Windows)
        os.close(null)
        sys.stdin = open(os.devnull, encoding="utf-8")
        self._out = os.fdopen(os.dup(1), "wb", buffering=0)
        os.dup2(2, 1)
        sys.stdout = sys.stderr
        self._lock = threading.Lock()
        self._ready = False
        self._warnings: list[str] = []

    def send(self, message: dict) -> None:
        data = encode_line(message)
        with self._lock:
            self._out.write(data)

    def warning(self, code: str) -> None:
        """A problem the user is told about once (DESIGN「通知」); kept until ready."""
        with self._lock:
            if code in self._warnings:
                return
            self._warnings.append(code)
            if not self._ready:
                return
        log(f"warning {code}")
        self.send({"event": "warning", "warning": code})

    def clear_warning(self, code: str) -> None:
        with self._lock:
            if code not in self._warnings:
                return
            self._warnings.remove(code)
        self.send({"event": "warning", "warning": code, "active": False})

    def ready(self, keymap: dict) -> None:
        with self._lock:
            self._ready = True
            warnings = list(self._warnings)
        for code in warnings:
            log(f"warning {code}")
        self.send({"ready": True, "proto": PROTO, "warnings": warnings, "keymap": keymap})


def argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m yuragi.engine",
                                     description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_RUNTIME_DIR,
                        help="the user's data: config.json, learning.jsonl, "
                             "personal_lexicon.jsonl (default ~/.yuragi-ime)")
    parser.add_argument("--dict-dir", type=Path, default=None,
                        help="the Mozc dictionary files (default third_party/mozc_oss_dict)")
    parser.add_argument("--cache-dir", type=Path, default=None,
                        help="where the dictionary cache is kept (default data/cache)")
    parser.add_argument("--lm-model", default=None,
                        help="the installed LM model directory for a GPU (engine.json); "
                             "also for the CPU without --lm-cpu-model")
    parser.add_argument("--lm-cpu-model", action="append", default=None,
                        help="an installed LM model directory for the CPU, in the order "
                             "they are tried (repeat; engine.json)")
    parser.add_argument("--lm-timing", action="store_true",
                        help="log LM job and resolution timestamps")
    parser.add_argument("--require-lm", action="store_true",
                        help="enable the LM and finish its warm-up before reporting ready")
    return parser


class Connection:
    """One TIP connection's session (and its LM pipeline)."""

    def __init__(self, engine: "Engine"):
        self.engine = engine
        self.sess = engine.new_session()
        self.pipeline = engine.new_pipeline(self.sess)
        self.watched = None  # the LM job a thread will tell the TIP about (Engine.watch_conversion)

    def handle(self, msg: dict) -> dict:
        from yuragi.ime.server import process_request
        if self.pipeline is not None:
            return self.pipeline.handle(msg)
        return process_request(self.sess, msg)

    def recover(self) -> dict:
        """DESIGN「要求 1 件ごとの防壁」: drop the session that raised; continue from a clean one."""
        from yuragi.ime.server import snapshot
        direct = self.sess.direct
        mode = self.sess.input_mode
        self.close()
        self.sess = self.engine.new_session()
        self.sess.direct = direct
        self.sess.input_mode = mode
        self.pipeline = self.engine.new_pipeline(self.sess)
        reply = snapshot(self.sess, None)
        reply.update(commit="", pending=False)
        return reply

    def close(self) -> None:
        if self.pipeline is not None:
            self.pipeline.close()


class Engine:
    def __init__(self, channel: Channel, args: argparse.Namespace):
        self.channel = channel
        self.data_dir = args.data_dir
        self.keymap = None
        self.connections: dict[object, Connection] = {}
        self.loaded = None
        self.worker = None
        self.settings = None
        # One request at a time with its reply written, a "lm_done" sent, or the restart: the TIP
        # is told only after the reply that left the conversion waiting.
        self.lock = threading.Lock()
        self.last_request = time.monotonic()
        self.lm_on_battery = False  # the power source when the LM device was chosen
        self.lm_retries = 0

    # -- startup -----------------------------------------------------------------
    def load(self, args: argparse.Namespace) -> None:
        try:
            from yuragi.lattice import mozc_dict
            if args.dict_dir is not None:
                mozc_dict.DICT_DIR = args.dict_dir
            if args.cache_dir is not None:
                mozc_dict.CACHE_DIR = args.cache_dir
            # Imported after the directories are set: some modules read them at import.
            from yuragi.ime import config, server
            from yuragi.ime.keymap import load_keymap
            import yuragi.ime.lm_async  # noqa: F401  (its worker starts after the warm-up)
            self.keymap = self.read_keymap(load_keymap(self.data_dir))
        except (ImportError, SyntaxError, OSError, ValueError) as exc:
            log(where(exc))
            fatal("program-files-unreadable")

        missing = [name for name in [*mozc_dict.LOADER_FILES, "id.def"] if not (mozc_dict.DICT_DIR / name).exists()]
        if missing:
            log(f"dictionary: missing {', '.join(missing)}")
            fatal("dictionary-missing")

        settings = self.read_settings(args, config, server)
        self.settings = settings
        from yuragi.ime.keyboard_setting import system_keyboard
        keyboard = system_keyboard(settings.keyboard)
        log(f"keyboard: {keyboard.name}")

        with server.freeze_after_dictionary_load():
            try:
                lex = mozc_dict.load_lex()
            except (OSError, ValueError) as exc:  # not UTF-8, a bad line, cannot be opened
                log(where(exc))
                fatal("dictionary-unreadable")
            loaded = server.load_session(settings, lex=lex, keyboard=keyboard)
        store = loaded._learning
        if store is not None:
            log(f"learning on: {store.lines} lines, "
                f"{len(store.records())} live, {store.skipped} skipped")
            try:
                compacted = store.compact_if_needed()
            except OSError as exc:
                log(f"learning history not compacted: {where(exc)}")
            else:
                if compacted is not None:
                    log("learning history compacted: %d -> %d lines" % compacted)
        if loaded.personal is not None and loaded.personal.skipped:
            log(f"personal lexicon: {loaded.personal.skipped} line(s) skipped")
        self.loaded = loaded
        if not settings.lm_rescore:
            log("LM off (setting)")

    def read_settings(self, args, config, server) -> argparse.Namespace:
        """config.json in the data directory (DESIGN「起動時の読み込み」); everything else as the
        stdio host's defaults."""
        settings = server.argument_parser().parse_args([])
        settings.learning_file = args.data_dir / "learning.jsonl"
        settings.personal_file = args.data_dir / "personal_lexicon.jsonl"
        settings.lm_model = args.lm_model
        settings.lm_cpu_model = args.lm_cpu_model
        settings.lm_timing = args.lm_timing
        for key, value in config.load(args.data_dir / config.CONFIG_NAME).items():
            setattr(settings, key, value)
        settings.require_lm = args.require_lm
        if settings.require_lm:
            settings.lm_rescore = True
        return settings

    def load_lm(self, server, settings, warm):
        """Load and run a sample conversion on the LM worker (DESIGN「暖機」)."""
        from yuragi.ime.power import on_battery
        start = time.perf_counter()
        self.lm_on_battery = on_battery()

        def warm_conversion(converter):
            loaded = time.perf_counter()
            warm.decode(self.loaded._lex, converter)
            log(f"LM loaded on {converter.model.device} in {loaded - start:.1f} s; "
                f"warm-up conversion {1000 * (time.perf_counter() - loaded):.0f} ms")

        def calibration(converter):
            from yuragi.ime.zenz import calibrate
            from yuragi.lattice.table import reverse_table
            return calibrate(converter, self.loaded._lex, reverse_table(self.loaded._table))

        return server.build_converter(settings, warm_conversion=warm_conversion,
                                      calibration=calibration, log=log)

    def lm_retry_after(self, exc: Exception) -> float | None:
        """Seconds until the LM is loaded and calibrated again, or None (given up)."""
        from yuragi.ime.server import LmTooSlow
        from yuragi.ime.zenz import CALIBRATION_LIMIT_MS
        if (not isinstance(exc, LmTooSlow) or exc.fastest_ms is None
                or exc.fastest_ms > LM_RETRY_FACTOR * CALIBRATION_LIMIT_MS
                or self.lm_retries >= LM_RETRIES):
            return None
        self.lm_retries += 1
        log(f"LM too slow for now ({exc.fastest_ms:.0f} ms); "
            f"calibrating again in {LM_RETRY_DELAY_S} s")
        return LM_RETRY_DELAY_S

    def lm_disabled(self) -> None:
        log("LM not used (it could not be loaded, or it kept failing)")
        self.channel.warning("lm")

    def warm_up(self) -> None:
        """DESIGN「暖機」: one conversion before ready, so the user's first key is not the slow one.

        Then the LM worker starts and converts the same input before it is used."""
        from yuragi.ime import server
        from yuragi.ime.keymap import default_keymap
        from yuragi.ime.lm_async import LmWorker
        from yuragi.ime.server import process_request
        start = time.perf_counter()
        sess = self.new_session()
        sess.keymap = default_keymap()  # the scripted conversion always uses Space
        t = 0
        for vk in WARM_KEYS:
            process_request(sess, {"op": "down", "vk": vk, "t": t})
            process_request(sess, {"op": "up", "vk": vk, "t": t + 20})
            t += 300
        warm = sess.conversion_request()
        process_request(sess, {"op": "down", "vk": 0x20, "t": t})
        reply = process_request(sess, {"op": "up", "vk": 0x20, "t": t + 20})
        process_request(sess, {"op": "reset"})
        log(f"warm-up conversion {1000 * (time.perf_counter() - start):.0f} ms "
            f"(converted: {reply['converted']})")
        if self.settings.lm_rescore:
            settings = self.settings
            self.worker = LmWorker(loader=lambda: self.load_lm(server, settings, warm),
                                   lex=self.loaded._lex, on_disabled=self.lm_disabled,
                                   retry_after=self.lm_retry_after, timing=settings.lm_timing)

    # -- sessions ----------------------------------------------------------------
    def new_session(self):
        from yuragi.chord.fsm import ChordFsm
        from yuragi.ime.session import ImeSession
        loaded = self.loaded
        return ImeSession(
            fsm=ChordFsm(sides=loaded.fsm.sides),
            _table=loaded._table, _lex=loaded._lex, _symbols=loaded._symbols,
            _learning=loaded._learning, personal=loaded.personal,
            prediction=loaded.prediction, predict_index=loaded.predict_index, keymap=self.keymap,
            keyboard=loaded.keyboard, max_tokens=MAX_TOKENS)

    def new_pipeline(self, sess):
        if self.worker is None:
            return None
        from yuragi.ime.lm_async import ConnectionPipeline, REQUIRED_LM_DEADLINE_MS
        s = self.settings
        deadline = REQUIRED_LM_DEADLINE_MS if s.require_lm else None
        return ConnectionPipeline(sess, self.worker, deadline_ms=deadline,
                                  require_lm=s.require_lm, timing=s.lm_timing)

    def read_keymap(self, settings):
        for note in settings.notes:
            log(f"keymap: {note}")
        if settings.error:
            log(f"keymap: {settings.error}")
            self.channel.warning("keymap")
        return settings.compile()

    def eat_table(self) -> dict:
        """The TIPs' table, in the keyboard's key codes (docs/JIS.md §2)."""
        return self.keymap.eat_table(self.loaded.keyboard)

    def reload_keymap(self) -> dict:
        from yuragi.ime.keymap import load_keymap
        settings = load_keymap(self.data_dir)
        keymap = self.read_keymap(settings)
        if settings.error:
            return {"keymap_reload": "failed", "reason": settings.error}
        self.keymap = keymap
        for connection in self.connections.values():
            connection.sess.keymap = keymap
        self.channel.send({"event": "keymap", "keymap": self.eat_table()})
        self.channel.clear_warning("keymap")
        return {"keymap_reload": "applied"}

    # -- serving -----------------------------------------------------------------
    def serve(self, stream) -> None:
        for raw in stream:
            if not raw.strip():
                continue
            try:
                msg = json.loads(raw)
                if not isinstance(msg, dict):
                    raise ValueError("not an object")
            except ValueError as exc:  # UnicodeDecodeError is a ValueError
                log(f"unreadable message from the broker ({type(exc).__name__}); ignored")
                continue
            op = msg.get("op")
            if op in ("open", "close"):
                with self.lock:  # watch_device reads the connections under it
                    if op == "open":
                        self.connections[msg.get("sid")] = Connection(self)
                    else:
                        connection = self.connections.pop(msg.get("sid"), None)
                        if connection is not None:
                            connection.close()
            else:
                with self.lock:
                    self.last_request = time.monotonic()
                    self.channel.send(self.request(msg))

    # -- choosing the LM device again (CONVERSION「装置とモデル」) ---------------------
    def device_change(self) -> str | None:
        """Why the LM should be loaded again on another device, or None."""
        from yuragi.ime.power import on_battery
        worker = self.worker
        if worker is None or worker.state == "loading":
            return None
        template = worker.template
        on_gpu = template is not None and str(template.model.device).startswith("cuda")
        battery = on_battery()
        if on_gpu and battery:
            return "on battery: leaving the GPU"
        if (not on_gpu and self.lm_on_battery and not battery
                and self.settings.lm_model is not None):
            return "on AC power: trying the GPU"
        return None

    def idle(self) -> bool:
        """Nobody has typed for a while and no input is under way (caller holds the lock)."""
        if time.monotonic() - self.last_request < IDLE_BEFORE_RESTART_S:
            return False
        for connection in self.connections.values():
            sess = connection.sess
            if sess.tokens or sess.converted or sess._await is not None:
                return False
        return True

    def watch_device(self) -> None:
        """Runs on its own thread: restarts the engine for another LM device, when idle."""
        while True:
            time.sleep(POWER_POLL_S)
            reason = self.device_change()
            if reason is None:
                continue
            with self.lock:
                if not self.idle():
                    continue
                log(f"restarting: {reason}")
                sys.stderr.flush()
                os._exit(RESTART_CODE)

    def request(self, msg: dict) -> dict:
        """One request; whatever goes wrong inside stays inside this one (DESIGN「要求 1 件ごとの防壁」)."""
        sid, seq = msg.get("sid"), msg.get("seq")
        connection = self.connections.get(sid)
        if msg.get("op") == "reload_keymap":
            try:
                reply = self.reload_keymap()
            except (OSError, ValueError) as exc:
                log(f"keymap: {where(exc)}")
                self.channel.warning("keymap")
                reply = {"keymap_reload": "failed", "reason": "キー設定を読み直せませんでした"}
        elif connection is None:
            log(f"request for a session that is not open (op {msg.get('op')!r})")
            reply = {"error": True}
        else:
            try:
                reply = connection.handle(msg)
            except Exception as exc:
                log(f"request failed: {where(exc)}; session started afresh")
                reply = connection.recover()
                reply["error"] = True
                if msg.get("op") == "down":
                    reply["eat"] = not reply["direct"]
            self.watch_conversion(sid, connection)
        reply["sid"] = sid
        reply["seq"] = seq
        return reply

    # -- LM results (DESIGN「LM の結果」) -------------------------------------------
    def watch_conversion(self, sid, connection: Connection) -> None:
        """A conversion waiting for the LM: a thread tells the TIP when the LM is done or the
        deadline has come, and the TIP asks for the result once ("resolve"). It does not poll."""
        pipeline = connection.pipeline
        job = pipeline.job if pipeline is not None and pipeline.sess._await is not None else None
        if job is None or job is connection.watched:
            return
        connection.watched = job
        threading.Thread(target=self.tell_lm_done, args=(sid, connection, pipeline, job),
                         name="lm-done", daemon=True).start()

    def tell_lm_done(self, sid, connection: Connection, pipeline, job) -> None:
        while not job.done.wait(max(0.0, job.deadline - pipeline.clock()) + LM_DONE_SLACK_S):
            if pipeline.clock() >= job.deadline:
                break  # the deadline: the result is the dictionary's
        with self.lock:
            if (self.connections.get(sid) is connection and connection.pipeline is pipeline
                    and pipeline.job is job and pipeline.sess._await is not None):
                self.channel.send({"event": "lm_done", "sid": sid})


def main(argv=None) -> int:
    channel = Channel()
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace", line_buffering=True)
    started = time.perf_counter()
    args = argument_parser().parse_args(argv)
    log(f"start pid {os.getpid()} python {sys.version.split()[0]} proto {PROTO}")
    engine = Engine(channel, args)
    engine.load(args)
    engine.warm_up()
    if args.require_lm and not engine.worker.wait_until_loaded():
        engine.worker.thread.join()
        fatal("lm-unavailable")
    channel.ready(engine.eat_table())
    log(f"ready in {time.perf_counter() - started:.2f} s")
    if engine.worker is not None and not args.require_lm:
        threading.Thread(target=engine.watch_device, name="lm-device", daemon=True).start()
    engine.serve(channel.input)
    log("stdin closed; exiting")
    if engine.worker is not None:
        engine.worker.stop()
        engine.worker.thread.join(WORKER_EXIT_S)
        if engine.worker.thread.is_alive():
            log("the LM worker did not stop; exiting without it")
            sys.stderr.flush()
            os._exit(0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
