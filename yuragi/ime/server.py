"""The engine's request protocol, and a stdio host for tests and evaluation.

The product talks to the engine through yuragi.engine (DESIGN「通信」); this
module holds what both share: dispatch() applies one request to a session and
returns the reply. ``python -m yuragi.ime.server`` serves one session over
stdin/stdout for tests and evaluation only (not a product path).

One JSON object per line:
  {"op":"down","vk":74,"t":123}
  {"op":"up","vk":74,"t":150}
  {"op":"timeout","t":200}
  {"op":"down","vk":65,"t":220,"mods":["shift"]}
  {"op":"down","vk":39,"t":250,"mods":["shift"]}  # extend focused bunsetsu
  {"op":"down","vk":37,"t":280,"mods":["shift"]}  # shrink focused bunsetsu
  {"op":"reset"}  # focus loss or application-terminated composition; no commit
  {"op":"set_direct","direct":true}
  {"op":"down","vk":9,"t":300}  # Tab: predictions for the input, if any
Reply: {"composition":"...","commit":"...","phase":"composing","fsm":"S1","pending":false}
eat: whether the down was consumed (present on down replies). While the LM
      is pending, a down that could be consumed is reserved for later dispatch.
predicting: the candidates are predictions (Tab acted; the TIP eats that Tab).
pending: the conversion awaits the LM (engine); poll with timeout at "timer".
"""

from __future__ import annotations

import argparse
import gc
import json
import sys
from pathlib import Path

from yuragi.ime.session import ImeSession
from yuragi.ime.learning import DEFAULT_LEARNING_PATH, LearningStore
from yuragi.ime.personal import DEFAULT_PERSONAL_PATH, PersonalLexicon
from yuragi.ime import power
from yuragi.ime.config import DEFAULTS, SETTINGS
from yuragi.ime.predict import DEFAULT_MODE as DEFAULT_PREDICTION, MODES as PREDICTION_MODES
from yuragi.ime.zenz import CONTEXT_CHARS


def dispatch(sess: ImeSession, msg: dict) -> dict:
    """Shared protocol path for the engine, the stdio host and transcript tests."""
    commit = apply_op(sess, msg)
    reply = snapshot(sess, msg.get("op"), eat=sess.key_eat)
    set_reply_commit(sess, msg, reply, commit)
    if "seq" in msg:
        reply["seq"] = msg["seq"]
    return reply


def set_reply_commit(sess: ImeSession, msg: dict, reply: dict, commit: str) -> None:
    reply["commit"] = commit
    if commit:
        sess.bind_commit(msg.get("seq"))


def apply_op(sess: ImeSession, msg: dict) -> str:
    """Apply one request to the session; return the committed text."""
    op = msg.get("op")
    commit = ""
    t = int(msg.get("t", 0))
    if op in ("down", "up"):
        down, vk, mods = op == "down", int(msg["vk"]), msg.get("mods")
        if down and sess.starts_input(vk, mods):
            text = msg.get("left_context")
            if isinstance(text, str):
                try:
                    text.encode("utf-8")  # json.loads also accepts lone surrogates
                except UnicodeEncodeError:
                    text = None
                else:
                    text = text[-CONTEXT_CHARS:]
            else:
                text = None
            after = msg.get("after_commit_seq")
            sess.start_input(text, after if type(after) is int else None,
                             disconnected=after is None and "after_commit_seq" in msg)
        commit = sess.on_key(down, vk, t, mods=mods) or ""
    elif op == "timeout":
        commit = sess.on_timeout(t) or ""
    elif op == "reset":
        sess.reset()
    elif op == "set_direct":
        sess.set_direct(msg["direct"])
    return commit


def snapshot(sess: ImeSession, op, *, eat: bool | None = None) -> dict:
    """The reply for the session's state; the caller fills in commit."""
    reply = {
        "direct": sess.direct,
        "pass_through": ((sess.direct and op in ("down", "up"))
                         or (op == "down" and eat is False)),
        "phase": sess.phase,
        "composition": sess.composition,
        "commit": "",
        "converted": sess.converted,
        "fsm": sess.fsm.state,
        "n_tokens": len(sess.tokens),
        "timer": sess.fsm.timer_deadline,
        "candidates": sess.candidates,
        "cand_index": sess.cand_index,
        "segments": sess.segment_snapshot(),
        "focus": sess.focus,
        "candidate_page": sess.candidate_page,
        "candidate_kinds": sess.candidate_kinds,
        "has_next_page": sess.has_next_page,
        "predicting": sess.predicting,
        "pending": False,
    }
    if op == "down" and eat is not None:
        reply["eat"] = eat
    return reply


def argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--log-text", action="store_true", help="log composition/commit text to stderr (private input)"
    )
    parser.add_argument("--learning-file", type=Path, default=DEFAULT_LEARNING_PATH,
                        help="local UTF-8 JSONL history (written when learning is on)")
    parser.add_argument("--learning", choices=SETTINGS["learning"], default=DEFAULTS["learning"],
                        help="on (the default): learn from conversions; off: neither "
                             "record nor use the history")
    parser.add_argument("--personal-file", type=Path, default=DEFAULT_PERSONAL_PATH,
                        help="the user's word list (JSONL; edit in the management window)")
    parser.add_argument("--prediction", choices=PREDICTION_MODES, default=DEFAULT_PREDICTION,
                        help="Tab on unconverted input offers continuations from history "
                             "and the dictionary (tab, the default) or does nothing (off)")
    lm = parser.add_argument_group("LM: zenz-v2.5 (on by default in the engine)")
    lm.add_argument("--lm-rescore", action="store_true", default=None,
                    help="convert with zenz on Space (needs torch+transformers)")
    lm.add_argument("--no-lm-rescore", action="store_false", dest="lm_rescore",
                    help="convert without the LM (the engine's default is with it)")
    lm.add_argument("--lm-model", default=None,
                    help="HF model id or local directory (default Miwa-Keita/zenz-v2.5-medium)")
    lm.add_argument("--lm-cpu-model", action="append", default=None,
                    help="model for the CPU, tried in order (repeat; default --lm-model)")
    lm.add_argument("--lm-alpha", type=float, default=None,
                    help="weight of zenz's reading NLL (default 1)")
    lm.add_argument("--lm-k", type=int, default=None,
                    help="k-best surfaces whose readings are compared (default 4)")
    lm.add_argument("--lm-steps", type=int, default=None,
                    help="cap on zenz reviews per kana run (default: until the draft passes)")
    lm.add_argument("--lm-review-ms", type=float, default=None,
                    help="reviews after a kana run's first stop this long after the "
                         "conversion started (default zenz.REVIEW_BUDGET_MS)")
    lm.add_argument("--lm-threads", type=int, default=None, help="torch CPU threads (default 4)")
    lm.add_argument("--lm-device", choices=("cuda", "cpu"), default=None,
                    help="force a device (default: try CUDA devices, then the CPU)")
    lm.add_argument("--lm-timing", action="store_true",
                    help="log the LM's time per conversion to stderr (no text)")
    lm.add_argument("--lm-prefetch", choices=("thumb", "off"), default="thumb",
                    help="engine: start the LM early on thumb press (default), or never")
    lm.add_argument("--lm-deadline-ms", type=float, default=None,
                    help="engine: a conversion still waiting for the LM after this long is "
                         "taken as a fault: logged, and the Viterbi 1-best is used "
                         "(default: from the LM's calibration, lm_async.deadline_ms)")
    lm.add_argument("--lm-grace-ms", type=float, default=None,
                    help="engine: how long the converting request waits for the LM "
                         "(default lm_async.GRACE_MS)")
    lm.add_argument("--lm-prefetch-delay-ms", type=float, default=30,
                    help="engine: thumb press to prefetch start")
    return parser


class LmTooSlow(RuntimeError):
    """Every device/model took longer than the calibration limit: convert without the LM.

    fastest_ms: the best calibration time among them (None if none got that far)."""

    def __init__(self, message: str, fastest_ms: float | None = None):
        super().__init__(message)
        self.fastest_ms = fastest_ms


def lm_candidates(args) -> list[tuple[str, str]]:
    """(device, model) in the order they are tried (CONVERSION「装置とモデル」).

    Each CUDA device with --lm-model (none on battery), then the CPU with each --lm-cpu-model
    (with --lm-model if none is given). --lm-device: that device and --lm-model only."""
    from yuragi.ime.zenz import DEFAULT_MODEL, cuda_devices

    model = args.lm_model or DEFAULT_MODEL
    device = getattr(args, "lm_device", None)
    if device is not None:
        return [(device, model)]
    cpu_models = getattr(args, "lm_cpu_model", None) or [model]
    # On battery the GPU is not even asked: a CUDA context keeps a laptop's GPU awake.
    gpus = [] if power.on_battery() else cuda_devices()
    return [(d, model) for d in gpus] + [("cpu", m) for m in cpu_models]


def build_converter(args, *, warm_conversion=None, calibration=None, log=None):
    """Return the first converter that completes placement and warm-up and, given
    calibration(converter) -> ms, whose time is within the calibration limit.

    The last candidate's failure is raised; LmTooSlow if none was fast enough."""
    from yuragi.ime.zenz import (CALIBRATION_LIMIT_MS, DEFAULT_ALPHA, DEFAULT_K, DEFAULT_STEPS,
                                DEFAULT_THREADS, REVIEW_BUDGET_MS, ZenzConverter, ZenzModel)

    budget = getattr(args, "lm_review_ms", None)
    if log is None:
        def log(message):
            print(message, file=sys.stderr, flush=True)
    # A developer's --require-lm takes the last candidate however slow it is.
    keep_last = getattr(args, "require_lm", False)

    def prepare(device, model):
        converter = ZenzConverter(
            ZenzModel(model,
                      threads=DEFAULT_THREADS if args.lm_threads is None else args.lm_threads,
                      device=device),
            alpha=DEFAULT_ALPHA if args.lm_alpha is None else args.lm_alpha,
            k=DEFAULT_K if args.lm_k is None else args.lm_k,
            steps=DEFAULT_STEPS if args.lm_steps is None else args.lm_steps,
            review_budget_ms=REVIEW_BUDGET_MS if budget is None else budget,
            # A batch of dictionary candidates can exceed the conversion deadline on CPU.
            rank_candidates=device != "cpu")
        converter.warm_up()
        if warm_conversion is not None:
            warm_conversion(converter)
        return converter

    candidates = lm_candidates(args)
    fastest = None
    for index, (device, model) in enumerate(candidates):
        last = index == len(candidates) - 1
        name = Path(model).name or model
        try:
            converter = prepare(device, model)
        except Exception as exc:
            if last:
                raise
            log(f"LM startup failed: {name} on {device} ({type(exc).__name__})")
        else:
            if calibration is None:
                return converter
            ms = converter.calibration_ms = calibration(converter)
            log(f"LM calibration: {name} on {device}: {ms:.0f} ms")
            if ms <= CALIBRATION_LIMIT_MS or (keep_last and last):
                return converter
            log(f"LM too slow: {name} on {device} (limit {CALIBRATION_LIMIT_MS} ms)")
            fastest = ms if fastest is None else min(fastest, ms)
            converter = None
        # Collect cycles from the failed or rejected model before trying a fresh one.
        gc.collect()
    raise LmTooSlow("no device and model within the calibration limit", fastest)


def load_session(args, with_lm: bool = True, *, lex=None) -> ImeSession:
    """Load expensive resources once, for the engine's sessions or the stdio host.

    with_lm=False leaves sess.lm unset (the engine loads it on a worker).
    lex: an already loaded lexicon (the engine loads it itself).
    """
    store = LearningStore(args.learning_file) if args.learning == "on" else None
    sess = ImeSession(_learning=store, _lex=lex, personal=PersonalLexicon(args.personal_file),
                      prediction=getattr(args, "prediction", DEFAULT_PREDICTION))
    sess.load()
    if sess.prediction != "off":
        sess._sync_personal()
        # The sorted reading index, once at start rather than on the first Tab.
        sess.predict_index.keys(sess._lex, sess.personal.revision
                                if sess.personal is not None else None)
    if with_lm and args.lm_rescore:
        # The LM is optional equipment: a machine without torch/transformers
        # (e.g. a fresh install) still gets a working IME, without the LM.
        try:
            sess.lm = build_converter(args)
        except Exception as exc:
            print(f"LM unavailable ({type(exc).__name__}); continuing without it",
                  file=sys.stderr, flush=True)
            sess.lm = None
    return sess


def process_request(sess: ImeSession, msg: dict, *, log_text=False, lm_timing=False) -> dict:
    converter = sess.lm
    if converter is not None:
        converter.last = {}
    reply = dispatch(sess, msg)
    if lm_timing and converter is not None and converter.last:
        print(json.dumps({"lm": {k: round(v, 3) if isinstance(v, float) else v
                                 for k, v in converter.last.items()}}),
              file=sys.stderr, flush=True)
    if log_text:
        print(json.dumps({"composition": reply["composition"], "commit": reply["commit"]},
                         ensure_ascii=False), file=sys.stderr, flush=True)
    return reply


def main() -> None:
    args = argument_parser().parse_args()  # a developer's host: the command line only
    if args.lm_rescore is None:
        args.lm_rescore = False  # the stdio host converts without the LM unless asked
    # Pipes default to cp1252 on Windows; Japanese composition must be UTF-8.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sess = load_session(args)
    # The long-lived dictionary must not be traversed by full GC during typing.
    gc.freeze()
    print(json.dumps({"ok": True, "msg": "ready"}, ensure_ascii=True), flush=True)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        if msg.get("op") == "quit":
            break
        reply = process_request(sess, msg, log_text=args.log_text, lm_timing=args.lm_timing)
        print(
            json.dumps(
                reply,
                ensure_ascii=False,
            ),
            flush=True,
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Exception messages (e.g. invalid int input) may contain request text.
        print(f"server error: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1)
