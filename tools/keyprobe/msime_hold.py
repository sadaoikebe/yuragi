"""MS-IME with held keys and the four release orders (the auto-repeat of a real keyboard is a run of downs
of the last pressed key; SendInput reproduces that run, it never adds repeats itself).

    python -m tools.keyprobe.msime_hold
"""
import os
import time

from . import lib
from .msime import hiragana, press, status, summarize, tokens

G, CAPS, ALT, CTRL, SHIFT = lib.SC["grave"], lib.SC["caps"], lib.SC["alt"], lib.SC["ctrl"], lib.SC["shift"]


def d(sc):
    return ("d", sc)


def u(sc):
    return ("u", sc)


def rep(sc, n):
    return [("d", sc)] * n


SEQS = {
    "Alt+` 順A": [d(ALT), d(G), u(G), u(ALT)],
    "Alt+` 順B": [d(ALT), d(G), u(ALT), u(G)],
    "Alt+` 順C": [d(G), d(ALT), u(G), u(ALT)],
    "Alt+` 順D": [d(G), d(ALT), u(ALT), u(G)],
    "Alt+` 押し続け": [d(ALT), d(G)] + rep(G, 15) + [u(G), u(ALT)],
    "Alt+` 押し続け、Alt を先に離す": [d(ALT), d(G)] + rep(G, 5) + [u(ALT)] + rep(G, 10) + [u(G)],
    "Ctrl+Caps 押し続け": [d(CTRL), d(CAPS)] + rep(CAPS, 15) + [u(CAPS), u(CTRL)],
    "Alt+Caps 押し続け": [d(ALT), d(CAPS)] + rep(CAPS, 15) + [u(CAPS), u(ALT)],
    "Shift+Caps 押し続け": [d(SHIFT), d(CAPS)] + rep(CAPS, 15) + [u(CAPS), u(SHIFT)],
    "Ctrl+` 押し続け": [d(CTRL), d(G)] + rep(G, 15) + [u(G), u(CTRL)],
}
# state before the sequence: IME on with nothing typed, and IME on while typing
SETUPS = {"入力なし": "", "入力中": "kanji", "変換済み": "kanji {Space}", "オフ": None}


def run(name, seq, setup):
    t = lib.Target("target_imm.py", "ms-ime-hold")
    out = [f"== {name} / {setup_name(setup)}"]
    try:
        time.sleep(0.3)
        if setup is not None:
            hiragana(t)
            for tok in tokens(setup):
                press(tok, settle=0.06 if len(tok) == 1 else 0.3)
        time.sleep(0.4)
        mark = len(t.rows())
        lib.guard()
        for kind, sc in seq:
            lib.send(0, kind == "u", sc)
            time.sleep(0.03)
        time.sleep(0.6)
        rows = t.rows()[mark:]
        out.append(summarize(rows) or "  (nothing)")
        st = [r for r in t.rows() if r["ev"] == "status"]
        if st:
            out.append(f"  end: open={st[-1]['open']} conv={st[-1]['conv']} caps={st[-1].get('caps')}")
    except lib.Aborted as e:
        out.append(f"ABORTED: {e}")
    finally:
        lib.release_mods()
        try:
            lib.guard()
            lib.send(lib.VK_KANJI, True)  # a stuck VK_KANJI from order B (windows.md §3.3)
            lib.send(lib.VK_OEM_3, True)  # a stuck VK_OEM_3 from order C
            for _ in range(3):
                lib.chord(lib.VK_ESCAPE, settle=0.05)
            if status(t.rows()).get("caps"):
                press("CapsLock")
        except lib.Aborted:
            pass
        t.close()
    return "\n".join(out)


def setup_name(s):
    return [k for k, v in SETUPS.items() if v == s][0]


def main():
    os.makedirs(lib.OUT, exist_ok=True)
    texts = []
    for name, seq in SEQS.items():
        for setup in SETUPS.values():
            texts.append(run(name, seq, setup))
            print(texts[-1], flush=True)
    with open(os.path.join(lib.OUT, "msime_hold.txt"), "w", encoding="utf-8") as f:
        f.write("\n\n".join(texts) + "\n")


if __name__ == "__main__":
    main()
