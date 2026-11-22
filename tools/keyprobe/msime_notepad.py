"""The same held-key sequences as msime_hold.py, in Notepad (a TSF app), read back from the saved file.

    python -m tools.keyprobe.msime_notepad

Each run: open a file, type "a Enter" (shows whether the IME is on), the sequence, "a Enter", save, close.
"""
import os
import subprocess
import time

from . import lib
from .msime import press

G, CAPS, ALT, SHIFT = lib.SC["grave"], lib.SC["caps"], lib.SC["alt"], lib.SC["shift"]

SEQS = {
    "Alt+` 1 回": [("d", ALT), ("d", G), ("u", G), ("u", ALT)],
    "Alt+` down 16 回": [("d", ALT)] + [("d", G)] * 16 + [("u", G), ("u", ALT)],
    "Alt+` down 17 回": [("d", ALT)] + [("d", G)] * 17 + [("u", G), ("u", ALT)],
    "Alt+` 押し続け、Alt を先に離して down 5 回": [("d", ALT), ("d", G), ("u", ALT)] + [("d", G)] * 5 + [("u", G)],
    "Shift+Caps down 16 回": [("d", SHIFT)] + [("d", CAPS)] * 16 + [("u", CAPS), ("u", SHIFT)],
    "Shift+Caps down 17 回": [("d", SHIFT)] + [("d", CAPS)] * 17 + [("u", CAPS), ("u", SHIFT)],
}


def run(name, seq):
    path = os.path.join(lib.WORK, "msime-notepad.txt")
    os.makedirs(lib.WORK, exist_ok=True)
    open(path, "w").close()
    subprocess.Popen(["notepad.exe", path])
    hwnd, pid = lib.find_window("msime-notepad")
    lib.bring_front(hwnd, pid)
    time.sleep(1.0)
    try:
        for tok in ("a", "Enter"):
            press(tok)
        lib.guard()
        for kind, sc in seq:
            lib.send(0, kind == "u", sc)
            time.sleep(0.03)
        time.sleep(0.4)
        lib.send(lib.VK_KANJI, True)  # a stuck VK_KANJI (windows.md §3.3)
        for tok in ("a", "Enter", "Enter"):
            press(tok)
        press("Ctrl+S")
        time.sleep(0.5)
        press("Ctrl+W")
        time.sleep(0.8)
    finally:
        lib.release_mods()
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        return f"{name}: {f.read()!r}"


def main():
    os.makedirs(lib.OUT, exist_ok=True)
    lines = []
    for name, seq in SEQS.items():
        lines.append(run(name, seq))
        print(lines[-1], flush=True)
    with open(os.path.join(lib.OUT, "msime_notepad.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
