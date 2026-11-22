"""State x key table for the macOS Japanese input method (probe.swift's table mode).

    python3 table.py <tag> [state ...]
    python3 table.py <tag> --redo      (again, the cases whose window was not frontmost)

For each state and each key: set the state up, press the key, record what the input method did.
One probe process runs all keys of a state. Appends to out/table-<tag>.jsonl (tag = the settings
the run was taken with, e.g. "default", "windows"). Prints a compact line per case.

Per case (see runTable in probe.swift):
  before / after  text (committed), segs ([string, underline]; 2 = thick = focused), sel, source,
                  panels (other windows of the probe: candidate / prediction window), front
  events          what the input method called: mark (setMarkedText), ins:<s> (insertText),
                  cmd:<selector> (doCommand: the key went to the app), src:<id>, unhandled
  kept            the text left after Esc x3 (what was committed)
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
J = "com.apple.inputmethod.Kotoeri.RomajiTyping.Japanese"
ABC = "com.apple.keylayout.ABC"

STATES = {
    "empty": (J, ""),
    "composing": (J, "kanji"),
    "comp_cursor": (J, "kanji {Left}"),
    "pred_focus": (J, "kanji {Tab}"),
    "converted": (J, "kanji {Space}"),
    "cand": (J, "kanji {Space} {Space}"),
    "multi": (J, "kyouhaamedesu {Space}"),
    "multi_second": (J, "kyouhaamedesu {Space} {Right}"),
    "resized": (J, "kyouhaamedesu {Space} {Shift+Left}"),
    "after_commit": (J, "kanji {Space} {Return}"),
    "abc": (ABC, ""),
    # with live conversion on (JIMPrefLiveConversionKey=1)
    "live": (J, "kyouhaamedesu"),
    "live_cursor": (J, "kyouhaamedesu {Left} {Left}"),
    "live_space": (J, "kyouhaamedesu {Space}"),
    "live_cand": (J, "kyouhaamedesu {Space} {Space}"),
}

BASE = ["Space", "Return", "Esc", "Delete", "ForwardDelete", "Tab", "Left", "Right", "Up", "Down",
        "Home", "End", "PageUp", "PageDown", "Eisu", "Kana",
        "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12",
        "a", "1", "5", "0", "-", ",", ".", "/", "[", "'", ";", "`"]
WITH_SHIFT = ["Space", "Return", "Esc", "Delete", "Tab", "Left", "Right", "Up", "Down", "Home", "End",
              "PageUp", "PageDown", "Eisu", "Kana", "a"]
WITH_CTRL = ["Space", "Return", "Esc", "Delete", "Tab", "Left", "Right", "Up", "Down",
             ";", "'", ",", ".", "/", "[", "]", "-", "0"] + list("abcdefghijklmnopqrstuvwxyz")
WITH_CTRL_SHIFT = ["Space", "Left", "Right", "j", "k", "l", ";", "'", "r", "z"]
WITH_OPT = ["Space", "Return", "Delete", "Left", "Right", "Up", "Down", "8", "9", ";",
            "a", "c", "s", "x", "z", "j", "l", "i", "k", "F1", "F2", "F3", "F4", "F5"]
WITH_OPT_SHIFT = ["z", "x", "r", "8", "9"]
WITH_CMD = ["Left", "Right", "Up", "Down", "Delete", "z"]
OTHER = ["Ctrl+Opt+Space", "Ctrl+Shift+Delete"]


def keys():
    out = list(BASE)
    out += [f"Shift+{k}" for k in WITH_SHIFT]
    out += [f"Ctrl+{k}" for k in WITH_CTRL]
    out += [f"Ctrl+Shift+{k}" for k in WITH_CTRL_SHIFT]
    out += [f"Opt+{k}" for k in WITH_OPT]
    out += [f"Opt+Shift+{k}" for k in WITH_OPT_SHIFT]
    out += [f"Cmd+{k}" for k in WITH_CMD]
    out += OTHER
    return out


def token(k):
    return k if len(k) == 1 else "{" + k + "}"


def show(s):
    if not s:
        return "-"
    m = "|".join(("*" if u == 2 else "") + t for t, u in s["segs"])
    return f"{s['text']}[{m}]{'W' if s['panels'] else ''}{'' if s['source'] == 'Japanese' else '@' + s['source']}"


def bad(r):
    return not (r["before"]["front"] and r["after"]["front"])


def main():
    tag, states = sys.argv[1], sys.argv[2:] or list(STATES)
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"table-{tag}.jsonl")
    redo = None
    if states == ["--redo"]:
        last = {}
        for line in open(path, encoding="utf-8"):
            r = json.loads(line)
            last[(r["state"], r["name"])] = r
        redo = {k for k, r in last.items() if bad(r)}
        states = list(dict.fromkeys(st for st, _ in redo))
        print(f"redo {len(redo)} cases", flush=True)
    for st in states:
        src, prep = STATES[st]
        cases = [{"tag": tag, "state": st, "key": token(k), "name": k, "source": src, "prep": prep} for k in keys()
                 if redo is None or (st, k) in redo]
        cpath = os.path.join(OUT, f"cases-{tag}-{st}.json")
        with open(cpath, "w") as f:
            json.dump(cases, f, ensure_ascii=False)
        p = subprocess.Popen([os.path.join(OUT, "probe"), "table", cpath], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True)
        with open(path, "a", encoding="utf-8") as f:
            for line in p.stdout:
                if not line.startswith("{") or '"state"' not in line:
                    continue
                r = json.loads(line)
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                f.flush()
                warn = " !!front" if bad(r) else ""
                print(f"{st:13} {r['name']:18} {show(r['before'])} -> {show(r['after'])} "
                      f"{','.join(r['events'])} kept={r['kept']!r}{warn}", flush=True)
        p.wait()


if __name__ == "__main__":
    main()
