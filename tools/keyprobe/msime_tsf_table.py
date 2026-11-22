"""msime_table.py with the TSF RichEdit (target_tsf.py): what MS-IME does in a TSF app, state x key.

    python -m tools.keyprobe.msime_tsf_table [state ...]

Per run: set the state up in an empty document, press the key, and record
  passed   the key downs that reached the app (the IME did not eat them)
  shown    the text right after the key (composition included)
  kept     the text after Esc x3 (Esc cancels a composition, so this is what was committed)
Writes out/msime_tsf_table.jsonl.
"""
import json
import os
import subprocess
import sys
import time

from . import lib
from .msime import press, tokens
from .msime_table import STATES, keys

MODVK = {"0x10", "0x11", "0x12"}


class TsfTarget:
    def __init__(self, title):
        os.makedirs(lib.WORK, exist_ok=True)
        self.log = os.path.join(lib.WORK, f"{title}.log")
        open(self.log, "w").close()
        self.proc = subprocess.Popen([sys.executable, os.path.join(lib.HERE, "target_tsf.py"), title, self.log])
        self.hwnd, pid = lib.find_window(title)
        lib.bring_front(self.hwnd, pid)
        time.sleep(0.8)

    def rows(self):
        with open(self.log, encoding="utf-8") as f:
            return [json.loads(x) for x in f.read().splitlines() if x.strip()]

    def close(self):
        lib.close(self.hwnd)
        try:
            self.proc.wait(10)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def status(rows):
    for r in reversed(rows):
        if r["ev"] == "status" and "open" in r:
            return r
    return {}


def text(rows):
    for r in reversed(rows):
        if r["ev"] == "text":
            return r["text"]
    return ""


_win = [None]


def target():
    if _win[0] is None:
        _win[0] = TsfTarget("ms-ime-tsf")
        time.sleep(0.3)
    return _win[0]


def drop():
    if _win[0] is not None:
        _win[0].close()
        _win[0] = None


def esc3():
    for _ in range(3):
        lib.chord(lib.VK_ESCAPE, settle=0.08)
    time.sleep(0.2)


def one(state, key):
    t = target()
    try:
        st = status(t.rows())
        if st.get("caps"):
            raise lib.Aborted("caps lock is on")
        if not st.get("open"):
            press("Alt+`")
        if status(t.rows()).get("conv") != "0x9":
            press("Ctrl+CapsLock")
        if (status(t.rows()).get("open"), status(t.rows()).get("conv")) != (True, "0x9"):
            raise lib.Aborted(f"could not get MS-IME into hiragana: {status(t.rows())}")
        if text(t.rows()):
            raise lib.Aborted("document not empty")
        for tok in list(tokens(STATES[state]))[1:]:
            press(tok, settle=0.06 if len(tok) == 1 else 0.3)
        time.sleep(0.4)
        before = t.rows()
        mark = len(before)
        press(key)
        time.sleep(0.4)
        rows = t.rows()
        after = rows[mark:]
        shown = text(rows)
        st = status(rows)
        esc3()
        kept = text(t.rows())
        return {"state": state, "key": key, "before": text(before),
                "passed": [r["vk"] for r in after if r["ev"] == "key" and r["kind"] in ("down", "sysdown")
                           and r["vk"] not in MODVK],
                "shown": shown, "kept": kept, "open": st.get("open"), "conv": st.get("conv")}
    except lib.Aborted as e:
        return {"state": state, "key": key, "error": str(e)}
    finally:
        lib.release_mods()
        try:
            lib.guard()
            esc3()
            rows = t.rows()
            if status(rows).get("caps"):
                press("CapsLock")
            if text(t.rows()):
                if not status(t.rows()).get("open"):
                    press("Alt+`")
                press("Ctrl+A")
                press("Delete")
                time.sleep(0.2)
            rows = t.rows()
            if "Insert" in key or text(rows) or status(rows).get("caps") or (status(rows).get("open"), status(rows).get("conv")) != (True, "0x9"):
                drop()
        except lib.Aborted:
            drop()


def main():
    states = sys.argv[1:] or list(STATES)
    os.makedirs(lib.OUT, exist_ok=True)
    path = os.path.join(lib.OUT, "msime_tsf_table.jsonl")
    try:
        with open(path, "a", encoding="utf-8") as f:
            for st in states:
                for k in keys():
                    r = one(st, k)
                    if "error" in r and "caps" not in r["error"]:
                        drop()
                        r = one(st, k)
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
                    f.flush()
                    print(st, k, r.get("passed"), repr(r.get("shown")), repr(r.get("kept")), r.get("error", ""), flush=True)
                    if "error" in r:
                        return
    finally:
        drop()


if __name__ == "__main__":
    main()
