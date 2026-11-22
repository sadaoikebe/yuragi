"""For each MS-IME state and each key: set the state up, press the key, record what happened.

    python -m tools.keyprobe.msime_table [state ...]

Writes out/msime_table.jsonl (one line per state x key) and prints a compact table.
Keys that open windows, toggle persistent settings, delete learning or go to the web are left out (UNSAFE).
"""
import json
import os
import sys
import time

from . import lib
from .msime import ImmTarget, press, summarize, tokens

STATES = {
    "empty": "{Alt+`}",
    "composing": "{Alt+`} kanji",
    "comp_cursor": "{Alt+`} kanji {Left}",
    "pred_focus": "{Alt+`} kanji {Down}",
    "converted": "{Alt+`} kanji {Space}",
    "cand": "{Alt+`} kanji {Space} {Space}",
    "multi": "{Alt+`} watashihanamaedesu {Space}",
    "resized": "{Alt+`} watashihanamaedesu {Space} {Shift+Left}",
    "after_commit": "{Alt+`} kanji {Space} {Enter}",
}

BASE = ["Space", "Enter", "Esc", "Backspace", "Delete", "Insert", "Tab", "Left", "Right", "Up", "Down",
        "Home", "End", "PageUp", "PageDown", "F6", "F7", "F8", "F9", "F10", "F1", "F2", "F3", "F4", "F11", "F12",
        "CapsLock", "a", "Shift+A", "1", "5", "9", "0", "Numpad1", "Numpad0", "NumpadAdd", "NumpadDecimal", "NumpadDivide"]
WITH_SHIFT = ["Space", "Enter", "Esc", "Backspace", "Delete", "Tab", "Left", "Right", "Up", "Down", "Home", "End",
              "PageUp", "PageDown", "F6", "F10", "CapsLock"]
WITH_CTRL = ["Space", "Enter", "Esc", "Backspace", "Delete", "Tab", "Left", "Right", "Up", "Down", "Home", "End",
             "PageUp", "PageDown", "F6", "F10", "CapsLock", "`"] + list("ACDEFGHIJKLMNOPQRSTUVWXZ")
WITH_CTRL_SHIFT = ["Space", "Enter", "Left", "Right", "Up", "Down"]
WITH_ALT = ["`", "CapsLock", "Enter", "Left", "Right", "Up", "Down", "Space"]
UNSAFE = {"Ctrl+B", "Ctrl+Y", "Ctrl+F7", "Ctrl+F8", "Ctrl+F9", "Ctrl+F10", "Ctrl+Shift+F10", "F5", "Ctrl+Delete",
          "Alt+Space", "Ctrl+Shift+CapsLock", "Ctrl+Esc"}


def keys():
    out = list(BASE)
    out += [f"Shift+{k}" for k in WITH_SHIFT]
    out += [f"Ctrl+{k}" for k in WITH_CTRL]
    out += [f"Ctrl+Shift+{k}" for k in WITH_CTRL_SHIFT]
    out += [f"Alt+{k}" for k in WITH_ALT]
    return [k for k in out if k not in UNSAFE]


def state_now(t):
    for r in reversed(t.rows()):
        if r["ev"] in ("status", "ready") and "open" in r:
            return r["open"], r["conv"]
    return None, None


def caps_on(t):
    for r in reversed(t.rows()):
        if r["ev"] == "status" and "caps" in r:
            return bool(r["caps"])
    return False


def last_comp(rows):
    comp = None
    for r in rows:
        if r["ev"] == "comp" and "comp" in r:
            comp = (r["comp"], r["attr"], r["clause"], r["cursor"])
        if r["ev"] == "end":
            comp = None
    return comp


_win = [None]


def target():
    if _win[0] is None:
        _win[0] = ImmTarget("ms-ime-table")
        time.sleep(0.3)
    return _win[0]


def drop():
    if _win[0] is not None:
        _win[0].close()
        _win[0] = None


def one(state, key):
    t = target()
    try:
        if not state_now(t)[0]:
            press("Alt+`")
        if state_now(t)[1] != "0x9":
            press("Ctrl+CapsLock")
        if caps_on(t):
            raise lib.Aborted("caps lock is on")
        if state_now(t) != (True, "0x9"):
            raise lib.Aborted(f"could not get MS-IME into hiragana: {state_now(t)}")
        if last_comp(t.rows()) is not None:
            raise lib.Aborted("composition left over")
        for tok in list(tokens(STATES[state]))[1:]:
            press(tok, settle=0.06 if len(tok) == 1 else 0.3)
        time.sleep(0.4)
        before = t.rows()
        mark = len(before)
        press(key)
        time.sleep(0.4)
        rows = t.rows()
        after = rows[mark:]
        return {"state": state, "key": key, "before": last_comp(before), "after": last_comp(rows),
                "status": state_now(t), "events": summarize(after),
                "app_down": [r["vk"] for r in after if r["ev"] == "key" and r["kind"] in ("down", "sysdown")],
                "chars": "".join(r["ch"] for r in after if r["ev"] == "char" and not r["ime"]),
                "commit": [r["result"] for r in after if r["ev"] == "comp" and "result" in r]}
    except lib.Aborted as e:
        return {"state": state, "key": key, "error": str(e)}
    finally:
        lib.release_mods()
        try:
            lib.guard()
            for _ in range(3):
                lib.chord(lib.VK_ESCAPE, settle=0.05)
            time.sleep(0.2)
            if caps_on(t):
                press("CapsLock")
                time.sleep(0.2)
            if caps_on(t):
                raise lib.Aborted("caps lock stays on")
            if state_now(t) != (True, "0x9") or last_comp(t.rows()) is not None:
                drop()
        except lib.Aborted:
            drop()


def main():
    states = sys.argv[1:] or list(STATES)
    os.makedirs(lib.OUT, exist_ok=True)
    path = os.path.join(lib.OUT, "msime_table.jsonl")
    try:
        with open(path, "a", encoding="utf-8") as f:
            for st in states:
                for k in keys():
                    r = one(st, k)
                    if "error" in r and "composition left over" in r["error"] or "hiragana" in r.get("error", ""):
                        drop()
                        r = one(st, k)
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
                    f.flush()
                    print(st, k, r.get("after"), r.get("commit"), r.get("app_down"), r.get("error", ""), flush=True)
                    if "error" in r:
                        return
    finally:
        drop()


if __name__ == "__main__":
    main()
