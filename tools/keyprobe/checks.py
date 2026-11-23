"""Key-probe checks: the facts in docs/keybind/windows.md, re-measured on this machine.

    python -m tools.keyprobe.checks list
    python -m tools.keyprobe.checks run <check> [<check> ...]     # or: run all
    python -m tools.keyprobe.checks manual-start <set>            # a window for a person to press keys in
    python -m tools.keyprobe.checks manual-report

Each check prints what arrived. Lines that compare with an expectation start with OK / NG; the expectation
is the windows.md section named on the line. Results also go to tools/keyprobe/out/<check>.txt.
Do not touch the keyboard or mouse while checks run. See README.md before the first run.
"""
import os
import subprocess
import sys
import time

from tools.keyprobe import probe as L
from tools.keyprobe.probe import ALT, ANY, CTRL, SC, SHIFT

LINES = []


def say(line):
    LINES.append(line)
    print(line, flush=True)


def expect(ok, section, text, detail=""):
    say(f"{'OK' if ok else 'NG'} [{section}] {text}" + (f"  ({detail})" if detail else ""))


ORDERS = ("key_first", "mods_first")
EXE = L.EXE_PY


# -- §1.1 / §1.2: Ctrl chords in real apps; TestKeyDown TRUE + KeyDown FALSE ----------------------------

def _shortcut_checks(app, exe, select, copy, text):
    L.probe(exe=exe)
    L.type_text(text)
    for label, cfg, want_copied in (("not eaten", {}, True), ("eaten", {"eat": [copy]}, False),
                                    ("TestKeyDown TRUE, KeyDown FALSE", {"test_only": [copy]}, None)):
        L.probe(exe=exe, **cfg)
        off = L.log_size()
        L.clip_set("SENTINEL")
        L.chord(*select)
        L.chord(*copy, settle=0.6)
        got = L.clip_get() or ""
        rows = L.key_rows(off, exe)
        calls = sorted({r["what"] for r in rows if r.get("vk") == f"0x{copy[0]:02X}"})
        copied = text in got.lower()
        if want_copied is None:
            say(f"-- [§1.1] {app}: {label}: app copied={copied}; callbacks for the key: {calls}")
        else:
            expect(copied == want_copied, "§1.2", f"{app}: Ctrl shortcut {label}", f"copied={copied}, callbacks={calls}")
    L.probe(exe=exe)


def check_apps():
    """Ctrl+A / Ctrl+C eaten or not in Notepad, conhost, Windows Terminal (and which callbacks each app uses)."""
    os.makedirs(L.WORK, exist_ok=True)
    path = os.path.join(L.WORK, "keyprobe.txt")
    open(path, "w").close()
    apps = (
        ("Notepad", "Notepad.exe", lambda: subprocess.Popen(["notepad.exe", path]), "keyprobe.txt",
         (ord("A"), CTRL), (ord("C"), CTRL), "keyprobe", lambda h: (L.chord(ord("S"), CTRL), L.chord(ord("W"), CTRL))),
        ("conhost", "conhost.exe", lambda: subprocess.Popen(["conhost.exe", "cmd.exe", "/k", "title keyprobe-con"],
                                                            creationflags=subprocess.CREATE_NEW_CONSOLE),
         "keyprobe-con", (ord("A"), CTRL), (ord("C"), CTRL), "rem keyprobe", L.close),
        ("Windows Terminal", "WindowsTerminal.exe",
         lambda: subprocess.Popen(["wt.exe", "-w", "new", "--title", "keyprobe-wt", "--suppressApplicationTitle", "cmd.exe", "/k"]),
         "keyprobe-wt", (ord("A"), CTRL | SHIFT), (ord("C"), CTRL | SHIFT), "rem keyprobe", L.close),
    )
    saved = L.clip_get()
    try:
        for app, exe, start, title, select, copy, text, finish in apps:
            L.probe()
            start()
            h, pid = L.find_window(title)
            L.bring_front(h, pid)
            time.sleep(1.5)
            _shortcut_checks(app, exe, select, copy, text)
            finish(h)
            time.sleep(1.0)
    finally:
        if saved is not None:
            L.clip_set(saved)


def check_test_only():
    """§1.1: in an app that calls OnTestKeyDown first (Tk), TRUE there and FALSE in OnKeyDown loses the key."""
    L.probe()
    tk = L.tk_target("keyprobe-test-only")
    try:
        for key in ((ord("A"), CTRL), (0x74, 0), (ord("K"), 0)):
            L.probe(test_only=[key], exe=EXE)
            toff = tk.size()
            L.chord(*key, settle=0.4)
            got = any(r["ev"] == "down" and r["keycode"] == key[0] for r in tk.rows(toff))
            expect(not got, "§1.1", f"vk {key[0]:#x} mods {key[1]}: the app does not get it", f"app got it={got}")
    finally:
        tk.close()


# -- §1.3 / §1.4: Alt chords, PreservedKey -------------------------------------------------------------------

def check_alt():
    """Alt+F in both release orders: not registered, and as a PreservedKey. Menu state and where the next letter goes."""
    L.probe()
    tk = L.tk_target("keyprobe-alt", menu=True)
    try:
        for preserve in ([], [(ord("F"), ALT)]):
            L.probe(preserve=preserve, exe=EXE)
            for order in ORDERS:
                off, toff = L.log_size(), tk.size()
                L.chord(ord("F"), ALT, order=order, settle=0.6)
                rows, app = L.key_rows(off, EXE), L.tk_text(tk, toff)
                menu = L.menu_state(tk.hwnd)
                zoff = tk.size()
                L.chord(ord("Z"), settle=0.3)
                letter = any(r["ev"] == "down" and r.get("keysym", "").lower() == "z" for r in tk.rows(zoff))
                for _ in range(3):
                    L.chord(L.VK_ESCAPE, settle=0.2)
                sink_f = any(r["what"] in ("TestKeyDown", "KeyDown") and r.get("vk") == "0x46" for r in rows)
                if preserve:
                    expect(not sink_f and "menu" not in app and menu == "none" and letter, "§1.3",
                           f"Alt+F {order} as PreservedKey: eaten, no menu, next letter reaches the app",
                           f"callbacks={L.describe(rows, preserve)} app={app} menu={menu}")
                else:
                    expect(not sink_f and "menu" in app, "§1.3", f"Alt+F {order} not registered: never in the key sink, opens the menu",
                           f"callbacks={L.describe(rows)} app={app}")
    finally:
        L.probe()
        tk.close()


def check_preserve():
    """§1.4: 40 PreservedKeys, re-register while active, replace the list."""
    L.probe()
    tk = L.tk_target("keyprobe-preserve")
    try:
        f = [0x70 + i for i in range(12)]
        many = ([(k, CTRL | SHIFT) for k in f] + [(k, CTRL | ALT) for k in f] + [(k, CTRL | SHIFT | ALT) for k in f]
                + [(0x30 + i, CTRL | SHIFT) for i in range(4)])
        for label in ("register 40", "unregister and register again"):
            off = L.log_size()
            L.probe(preserve=many, exe=EXE)
            bad = [r for r in L.log_since(off) if r.get("exe", "").lower() == EXE.lower()
                   and r["what"] in ("PreserveKey", "UnpreserveKey") and int(r["hr"], 16) & 0x80000000]
            expect(not bad, "§1.4", label, f"failures={len(bad)}")
        off, toff = L.log_size(), tk.size()
        L.chord(0x70, CTRL | SHIFT)
        L.chord(0x33, CTRL | SHIFT)
        hits = [r["index"] for r in L.key_rows(off, EXE) if r["what"] == "PreservedKey"]
        expect(hits == ["0", "39"], "§1.4", "first and 40th registered chords arrive at OnPreservedKey", str(hits))
        L.probe(preserve=[(0x71, CTRL | SHIFT)], exe=EXE)
        off, toff = L.log_size(), tk.size()
        L.chord(0x70, CTRL | SHIFT)
        back = any(r["ev"] == "down" and r["keysym"] == "F1" for r in tk.rows(toff))
        expect(back, "§1.4", "a chord removed from the list is an ordinary key again at once")
    finally:
        L.probe()
        tk.close()


def check_repeat():
    """§1.5: lParam bit 30 on downs without an up (SendInput cannot auto-repeat; a person must hold a key for that)."""
    L.probe()
    tk = L.tk_target("keyprobe-repeat")
    try:
        L.probe(exe=EXE)
        off = L.log_size()
        L.hold(ord("Q"), 3)
        prev = [r["prev"] for r in L.key_rows(off, EXE) if r["what"] == "TestKeyDown" and r.get("vk") == "0x51"]
        expect(prev == ["0", "1", "1"], "§1.5", "bit 30 is 0, 1, 1", str(prev))
    finally:
        tk.close()


def check_capture():
    """Tk (the settings window) gets exactly the keys the TIP passes."""
    L.probe()
    tk = L.tk_target("keyprobe-capture")
    try:
        for eat in ([], [(ord("A"), CTRL)]):
            L.probe(eat=eat, exe=EXE)
            toff = tk.size()
            L.chord(ord("A"), CTRL)
            got = any(r["ev"] == "down" and r["keysym"].lower() == "a" for r in tk.rows(toff))
            expect(got == (not eat), "§1.2", f"Tk gets Ctrl+A when the TIP {'eats' if eat else 'passes'} it: {got}")
    finally:
        L.probe()
        tk.close()


# -- §2: kbd101 -------------------------------------------------------------------------------------------

CODES = [("Alt+`", ALT, "grave"), ("Shift+Alt+`", ALT | SHIFT, "grave"), ("Ctrl+Alt+`", CTRL | ALT, "grave"),
         ("Ctrl+`", CTRL, "grave"), ("Ctrl+Shift+`", CTRL | SHIFT, "grave"), ("Alt+CapsLock", ALT, "caps"),
         ("Shift+Alt+CapsLock", SHIFT | ALT, "caps"), ("Ctrl+Alt+CapsLock", CTRL | ALT, "caps"),
         ("Shift+CapsLock", SHIFT, "caps"), ("Ctrl+CapsLock", CTRL, "caps"), ("Ctrl+Shift+CapsLock", CTRL | SHIFT, "caps")]
# Alt chords reach the TIP only as PreservedKeys, so register every VK they may become.
CODES_PRESERVE = [(vk, m) for m in (ALT, ALT | SHIFT, ALT | CTRL)
                  for vk in (0xC0, 0x19, 0x14, 0xF0, 0xF1, 0xF2, 0xF3, 0xF4, 0x15)]


def check_codes():
    """§3.2: what each ` / CapsLock chord delivers on down and up, in both release orders (compare by eye with the table)."""
    L.probe()
    tk = L.tk_target("keyprobe-codes")
    try:
        L.probe(preserve=CODES_PRESERVE, exe=EXE)
        L.restore_state(EXE)
        for name, mods, key in CODES:
            for order in ORDERS:
                off, toff = L.log_size(), tk.size()
                L.chord(0, mods, scan=SC[key], order=order, settle=0.4)
                rows = L.key_rows(off, EXE, scan=SC[key])
                st = L.key_state(EXE)
                say(f"-- [§3.2] {name:20} {order:10}: {L.describe(rows, CODES_PRESERVE)} | app: {L.tk_text(tk, toff)} | "
                    f"VK_KANJI held={bool(st.get('ks_kanji', 0) & 0x8000)}")
                L.restore_state(EXE)
    finally:
        L.probe()
        tk.close()


def check_kanji():
    """§3.6: which PreservedKey form catches Alt+`, in both release orders."""
    forms = {"{VK_KANJI, any}": [(0x19, ANY)], "{VK_KANJI, Alt}": [(0x19, ALT)], "{VK_OEM_3, Alt}": [(0xC0, ALT)]}
    L.probe()
    tk = L.tk_target("keyprobe-kanji")
    try:
        for name, keys in forms.items():
            L.probe(preserve=keys, exe=EXE)
            for order in ORDERS:
                off = L.log_size()
                L.chord(0, ALT, scan=SC["grave"], order=order, settle=0.4)
                rows = L.key_rows(off, EXE, scan=SC["grave"])
                hit = any(r["what"] == "PreservedKey" for r in rows)
                expect(hit == (name == "{VK_KANJI, any}"), "§3.6", f"{name} {order}: PreservedKey hit={hit}", L.describe(rows, keys))
                L.restore_state(EXE)
    finally:
        L.probe()
        tk.close()


def check_toggle():
    """§3.2: after Shift+Ctrl+CapsLock (the only entry with the key-up switch), CapsLock alone is VK_CAPITAL again."""
    L.probe()
    tk = L.tk_target("keyprobe-toggle")
    try:
        L.probe(exe=EXE)
        for order in ORDERS:
            L.chord(0, CTRL | SHIFT, scan=SC["caps"], order=order, settle=0.4)
            off = L.log_size()
            L.chord(0, scan=SC["caps"], settle=0.4)
            vks = [r["vk"] for r in L.key_rows(off, EXE, scan=SC["caps"]) if r["what"] == "TestKeyDown"]
            expect(vks == ["0x14"], "§3.2", f"{order}: CapsLock alone after Shift+Ctrl+CapsLock", str(vks))
            L.restore_state(EXE)
    finally:
        tk.close()


# Modifier pressed AFTER the key (windows.md 順 C・D). A held key never keeps repeating once another key goes down
# (windows.md §2), so there is no "repeat while the modifier is down" case to send.
LATE_PRESERVE = [(vk, m) for m in (ALT, ALT | SHIFT, ALT | CTRL)
                 for vk in (0xC0, 0x14, 0xF0, 0xF1, 0xF2, 0xF3, 0xF4, 0x15)] + [(0x19, ANY)]
LATE = [("`+Alt", ALT, "grave"), ("`+Ctrl", CTRL, "grave"), ("`+Shift", SHIFT, "grave"),
        ("CapsLock+Alt", ALT, "caps"), ("CapsLock+Ctrl", CTRL, "caps"), ("CapsLock+Shift", SHIFT, "caps")]


def _late(scan, mods, order):
    held = [m for m in L.MOD_KEYS if mods & m[0]]
    L.guard()
    L.send(0, False, scan)
    for _, mvk, msc in held:
        L.send(mvk, False, msc)
    if order == "C":
        L.send(0, True, scan)
    for _, mvk, msc in reversed(held):
        L.send(mvk, True, msc)
    if order == "D":
        L.send(0, True, scan)
    time.sleep(0.4)


def check_late(only=None):
    """§3.2: the modifier pressed after the key (orders C, D). Alt cases enter the window menu (§1.3)."""
    L.probe()
    tk = L.tk_target("keyprobe-late")
    try:
        L.probe(preserve=LATE_PRESERVE, exe=EXE)
        L.restore_state(EXE)
        for name, mods, key in LATE:
            if only and name not in only:
                continue
            for order in ("C", "D"):
                off, toff = L.log_size(), tk.size()
                _late(SC[key], mods, order)
                rows = L.key_rows(off, EXE, scan=SC[key])
                menu = L.menu_state(tk.hwnd)
                for _ in range(2):  # an Alt released with no key down in between enters the window menu
                    L.chord(L.VK_ESCAPE, settle=0.2)
                st = L.key_state(EXE)
                say(f"-- [§3.2] {name:15} {order}: {L.describe(rows, LATE_PRESERVE)} | app: {L.tk_text(tk, toff)} | menu={menu} | "
                    f"held: oem3={bool(st.get('ks_oem3', 0) & 0x8000)} kanji={bool(st.get('ks_kanji', 0) & 0x8000)} "
                    f"capital={bool(st.get('ks_capital', 0) & 0x8000)}")
                _unstick_late(st)
                L.restore_state(EXE)
    finally:
        L.probe()
        tk.close()


def _unstick_late(st):
    """A key left down by the layout (VK_OEM_3 / VK_CAPITAL here): send its up so the next case starts clean."""
    for name, vk in (("ks_oem3", L.VK_OEM_3), ("ks_capital", L.VK_CAPITAL)):
        if st.get(name, 0) & 0x8000:
            L.guard()
            L.send(vk, True)


def _hook_rows(offset):
    """Key callbacks and the probe's thread-hook lines (Hook ...) in order."""
    return [r for r in L.log_since(offset) if r.get("exe", "").lower() == EXE.lower()
            and (r["what"] in L.KEY_CALLS or r["what"] == "Hook")]


def _hook_text(rows, keys):
    out = []
    for r in rows:
        if r["what"] == "Hook":
            out.append(f"Hook:{r['vk']}{'^' if r['up'] == '1' else ''}(prev{r['prev']})")
        else:
            out.append(L.describe([r], keys))
    return " ".join(out)


HOLD_KEYS = [(0x19, ANY), (ord("F"), ALT)]


def _alt_sequence(seq):
    """seq of ("alt"|"f"|"grave", up) events, sent as one gesture."""
    L.guard()
    for key, up in seq:
        if key == "alt":
            L.send(L.VK_MENU, up, SC["alt"])
        elif key == "f":
            L.send(ord("F"), up)
        else:
            L.send(0, up, SC["grave"])
        time.sleep(0.05)
    time.sleep(0.4)


def check_hold():
    """§1.4, §1.6: a held PreservedKey fires per repeat; the thread hook (probe) tells repeat from re-press."""
    cases = [("Alt+` held (3 downs)", [("alt", 0), ("grave", 0), ("grave", 0), ("grave", 0), ("grave", 1), ("alt", 1)], 3),
             ("Alt+F held (3 downs)", [("alt", 0), ("f", 0), ("f", 0), ("f", 0), ("f", 1), ("alt", 1)], 3),
             ("Alt+F pressed twice", [("alt", 0), ("f", 0), ("f", 1), ("f", 0), ("f", 1), ("alt", 1)], 2)]
    L.probe()
    tk = L.tk_target("keyprobe-hold", menu=True)
    try:
        L.probe(preserve=HOLD_KEYS, exe=EXE)
        for name, seq, fires in cases:
            off = L.log_size()
            _alt_sequence(seq)
            rows = _hook_rows(off)
            hits = sum(1 for r in rows if r["what"] == "PreservedKey")
            expect(hits == fires, "§1.4", f"{name}: OnPreservedKey {hits} times (one per down)", _hook_text(rows, HOLD_KEYS))
            for _ in range(2):
                L.chord(L.VK_ESCAPE, settle=0.2)
            L.restore_state(EXE)
    finally:
        L.probe()
        tk.close()


def check_late_alt():
    """§3.2: the Alt rows of the late check only."""
    check_late({"`+Alt", "CapsLock+Alt"})


CHECKS = {"apps": check_apps, "test-only": check_test_only, "alt": check_alt, "preserve": check_preserve,
          "repeat": check_repeat, "capture": check_capture, "codes": check_codes, "kanji": check_kanji,
          "toggle": check_toggle, "late": check_late, "late-alt": check_late_alt, "hold": check_hold}

# -- a window for a person ----------------------------------------------------------------------------------

MANUAL_SETS = {"none": [], "codes": CODES_PRESERVE, "late": LATE_PRESERVE, "hold": [(0x19, ANY), (ord("F"), ALT)],
               "corvusskk": [(0xC0, ALT), (0x19, ANY), (0xF3, ANY), (0xF4, ANY)]}


def manual_start(name):
    keys = MANUAL_SETS[name]
    L.probe(preserve=keys)
    os.makedirs(L.OUT, exist_ok=True)
    with open(os.path.join(L.OUT, "manual.state"), "w", encoding="utf-8") as f:
        f.write(f"{L.log_size()} {name}")
    log = os.path.join(L.WORK, "keyprobe-manual.log")
    os.makedirs(L.WORK, exist_ok=True)
    open(log, "w").close()
    subprocess.Popen([sys.executable, os.path.join(L.HERE, "target_tk.py"), "keyprobe-manual", log, "--menu"])
    print("opened the window 'keyprobe-manual'. Click into it, press the keys, then run manual-report.")


def manual_report():
    with open(os.path.join(L.OUT, "manual.state"), encoding="utf-8") as f:
        off, name = f.read().split()
    keys = MANUAL_SETS[name]
    for r in L.log_since(int(off)):
        if r.get("exe", "").lower() != EXE.lower() or r["what"] not in L.KEY_CALLS:
            continue
        if r.get("vk") in ("0x10", "0x11", "0x12"):
            continue
        if r["what"] == "PreservedKey":
            print(L.describe([r], keys))
        else:
            print(f"{r['what']:12} vk={r['vk']} scan={r['scan']} mods={r['mods']} prev={r['prev']} rep={r['rep']} "
                  f"kanji={r.get('ks_kanji')} caps={r.get('ks_capital')} kana={r.get('ks_kana')}")
    print("--- what the app (Tk) received ---")
    with open(os.path.join(L.WORK, "keyprobe-manual.log"), encoding="utf-8") as f:
        import json
        for line in f:
            r = json.loads(line)
            if r.get("keycode") not in (16, 17, 18):
                print(r["ev"], r.get("keysym", ""), r.get("keycode", ""))


def main():
    args = sys.argv[1:] or ["list"]
    if args[0] == "list":
        for name, fn in CHECKS.items():
            print(f"{name:10} {fn.__doc__.strip().splitlines()[0]}")
        return
    if args[0] == "manual-start":
        return manual_start(args[1] if len(args) > 1 else "none")
    if args[0] == "manual-report":
        return manual_report()
    if args[0] != "run":
        sys.exit(__doc__)
    names = list(CHECKS) if args[1:] == ["all"] else args[1:]
    os.makedirs(L.OUT, exist_ok=True)
    try:
        for name in names:
            LINES.clear()
            say(f"== {name}")
            try:
                CHECKS[name]()
            except L.Aborted as e:
                say(f"NG [stopped] {e}")
                if "not the window under test" in str(e):
                    break
            finally:
                with open(os.path.join(L.OUT, f"{name}.txt"), "w", encoding="utf-8") as f:
                    f.write("\n".join(LINES) + "\n")
    finally:
        L.release_mods()
        L.probe_off()


if __name__ == "__main__":
    main()
