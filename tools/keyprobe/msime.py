"""Watch what MS-IME does for a sequence of keys (target_imm.py records it through IMM).

    python -m tools.keyprobe.msime "<keys>" ["<keys>" ...]

Keys are space separated: a word of lower-case letters/digits/punct is typed key by key (romaji),
{Name} or {Ctrl+Shift+Name} is one chord. Each argument runs in a fresh window.
MS-IME must be the input method; it starts in the mode the window gets (turned on with {Alt+`} if off).
"""
import json
import os
import subprocess
import sys
import time

from . import lib

NAMES = {"Space": 0x20, "Enter": 0x0D, "Esc": 0x1B, "Backspace": 0x08, "Tab": 0x09, "Delete": 0x2E,
         "Insert": 0x2D, "Home": 0x24, "End": 0x23, "PageUp": 0x21, "PageDown": 0x22, "Left": 0x25,
         "Up": 0x26, "Right": 0x27, "Down": 0x28, "`": 0xC0, "CapsLock": 0x14, "-": 0xBD, "=": 0xBB,
         "[": 0xDB, "]": 0xDD, "\\": 0xDC, ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF}
NAMES.update({f"F{i}": 0x6F + i for i in range(1, 25)})
NAMES.update({f"Numpad{i}": 0x60 + i for i in range(10)})
NAMES.update({"NumpadMultiply": 0x6A, "NumpadAdd": 0x6B, "NumpadSubtract": 0x6D, "NumpadDecimal": 0x6E,
              "NumpadDivide": 0x6F})
SCAN_KEYS = {0xC0: lib.SC["grave"], 0x14: lib.SC["caps"]}  # the layout must see these as scan codes
MODS = {"Shift": lib.SHIFT, "Ctrl": lib.CTRL, "Alt": lib.ALT}
EXT = {0x2D, 0x2E, 0x24, 0x23, 0x21, 0x22, 0x25, 0x26, 0x27, 0x28, 0x6F}


def key_of(name):
    if name in NAMES:
        return NAMES[name]
    if len(name) == 1 and (name.isalnum()):
        return ord(name.upper())
    raise ValueError(name)


def press(spec, settle=0.25):
    parts = spec.split("+")
    name = parts[-1] if parts[-1] else "+"
    mods = 0
    for p in parts[:-1]:
        mods |= MODS[p]
    vk = key_of(name)
    if vk in SCAN_KEYS:
        lib.chord(0, mods, scan=SCAN_KEYS[vk], settle=settle)
    else:
        lib.chord(vk, mods, settle=settle, ext=vk in EXT)


def tokens(seq):
    for w in seq.split():
        if w.startswith("{") and w.endswith("}"):
            yield w[1:-1]
        else:
            for ch in w:
                yield ch


class ImmTarget:
    def __init__(self, title):
        os.makedirs(lib.WORK, exist_ok=True)
        self.log = os.path.join(lib.WORK, f"{title}.log")
        open(self.log, "w").close()
        self.proc = subprocess.Popen([sys.executable, os.path.join(lib.HERE, "target_imm.py"), title, self.log])
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


def summarize(rows):
    """One line per event that matters: keys the app got, composition changes, candidates, commits."""
    out, last = [], None
    for r in rows:
        ev = r["ev"]
        if ev == "key":
            s = f"  app {r['kind']} {r['vk']}" + (" (IME)" if r["vk"] == "0xe5" else "")
            if r["kind"].endswith("up"):
                continue
        elif ev == "comp":
            if "result" in r:
                out.append(f"  commit {r['result']!r}")
            if "comp" in r:
                s = f"  comp {r['comp']!r} attr={r['attr']} clause={r['clause']} cur={r['cursor']}"
            else:
                continue
        elif ev == "char":
            if r["ime"]:
                continue
            s = f"  char {r['ch']!r}"
        elif ev == "notify":
            if r["what"] in ("opencand", "changecand", "closecand"):
                c = r.get("cand")
                s = f"  cand {r['what']}" + (f" sel={c['sel']} page={c['page_start']}/{c['page_size']} n={c['count']} {c['items'][:9]}" if c else "")
            elif r["what"] in ("setopen", "setconv"):
                s = f"  ime open={r.get('open')} conv={r.get('conv')}"
            else:
                continue
        elif ev in ("start", "end"):
            s = f"  {ev}"
        elif ev == "status":
            continue
        else:
            s = f"  {ev} {r}"
        if s != last:
            out.append(s)
        last = s
    return "\n".join(out)


def run(seq, title="ms-ime-watch"):
    t = ImmTarget(title)
    lines = [f"== {seq}"]
    try:
        r0 = t.rows()
        lines.append(f"  start {[{k: v for k, v in r.items() if k in ('open', 'conv')} for r in r0 if r['ev'] == 'ready']}")
        mark = len(r0)
        for tok in tokens(seq):
            press(tok)
            rows = t.rows()
            lines.append(f"[{tok}]")
            s = summarize(rows[mark:])
            if s:
                lines.append(s)
            mark = len(rows)
        time.sleep(0.3)
        rows = t.rows()
        s = summarize(rows[mark:])
        if s:
            lines.append(s)
    except lib.Aborted as e:
        lines.append(f"ABORTED: {e}")
    finally:
        lib.release_mods()
        # leave nothing pending: Esc twice then close (the IME discards the composition)
        try:
            lib.guard()
            for _ in range(3):
                lib.chord(lib.VK_ESCAPE, settle=0.1)
        except lib.Aborted:
            pass
        t.close()
    return "\n".join(lines)


def main():
    os.makedirs(lib.OUT, exist_ok=True)
    texts = [run(seq) for seq in sys.argv[1:]]
    text = "\n\n".join(texts)
    print(text)
    with open(os.path.join(lib.OUT, "msime.txt"), "a", encoding="utf-8") as f:
        f.write(text + "\n\n")


if __name__ == "__main__":
    main()
