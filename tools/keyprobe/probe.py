"""The probe TIP (tip/keyprobe_tip.cpp): probe.json / probe.log, the Tk target, clipboard, menu state.

The probe TIP reads %USERPROFILE%\\.yuragi-ime\\probe.json and logs every key callback to probe.log
(see README.md). The general parts (SendInput, the foreground guard, windows) are in lib.py.
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import re
import subprocess
import sys
import time

from .lib import *  # noqa: F401,F403

HOME = os.path.join(os.environ["USERPROFILE"], ".yuragi-ime")
PROBE_JSON = os.path.join(HOME, "probe.json")
PROBE_LOG = os.path.join(HOME, "probe.log")
EXE_PY = os.path.basename(sys.executable)  # the Tk target runs under the same python.exe
ANY = 16  # probe.json: TF_MOD_IGNORE_ALL_MODIFIER (preserve only)


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("flags", wt.DWORD), ("hwndActive", wt.HWND), ("hwndFocus", wt.HWND),
                ("hwndCapture", wt.HWND), ("hwndMenuOwner", wt.HWND), ("hwndMoveSize", wt.HWND),
                ("hwndCaret", wt.HWND), ("rcCaret", wt.RECT)]


def menu_state(hwnd):
    """Win32 menu mode of the window's thread (WinUI apps such as the new Notepad do not report it)."""
    info = GUITHREADINFO(cbSize=ctypes.sizeof(GUITHREADINFO))
    if not user32.GetGUIThreadInfo(user32.GetWindowThreadProcessId(hwnd, None), ctypes.byref(info)):
        return "?"
    return "+".join(n for bit, n in ((0x4, "INMENU"), (0x8, "SYSMENU"), (0x10, "POPUP")) if info.flags & bit) or "none"


# -- clipboard -----------------------------------------------------------------------------------

kernel32.GlobalAlloc.restype = wt.HGLOBAL
kernel32.GlobalAlloc.argtypes = [wt.UINT, ctypes.c_size_t]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [wt.HGLOBAL]
kernel32.GlobalUnlock.argtypes = [wt.HGLOBAL]
user32.GetClipboardData.restype = wt.HANDLE
user32.SetClipboardData.argtypes = [wt.UINT, wt.HANDLE]
user32.SetClipboardData.restype = wt.HANDLE


def _open_clipboard():
    for _ in range(50):
        if user32.OpenClipboard(None):
            return
        time.sleep(0.05)
    raise OSError("clipboard busy")


def clip_get():
    _open_clipboard()
    try:
        h = user32.GetClipboardData(13)  # CF_UNICODETEXT
        if not h:
            return None
        p = kernel32.GlobalLock(h)
        try:
            return ctypes.wstring_at(p)
        finally:
            kernel32.GlobalUnlock(h)
    finally:
        user32.CloseClipboard()


def clip_set(text):
    data = (text + "\0").encode("utf-16-le")
    _open_clipboard()
    try:
        user32.EmptyClipboard()
        h = kernel32.GlobalAlloc(0x2, len(data))
        ctypes.memmove(kernel32.GlobalLock(h), data, len(data))
        kernel32.GlobalUnlock(h)
        user32.SetClipboardData(13, h)
    finally:
        user32.CloseClipboard()


# -- probe.json and probe.log ----------------------------------------------------------------------

_seq = [int(time.time()) % 1000000]


def probe(eat=(), test_only=(), preserve=(), exe=None):
    """Write probe.json; with exe, wait until the TIP in that process has applied it."""
    _seq[0] += 1
    cfg = {"on": True, "seq": _seq[0], "eat": [list(c) for c in eat],
           "test_only": [list(c) for c in test_only], "preserve": [list(c) for c in preserve]}
    os.makedirs(HOME, exist_ok=True)
    with open(PROBE_JSON + ".tmp", "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    os.replace(PROBE_JSON + ".tmp", PROBE_JSON)
    if exe:
        wait_log(lambda r: r.get("exe", "").lower() == exe.lower() and r["what"] == "config"
                 and r.get("seq") == str(_seq[0]), f"probe config in {exe}")


def probe_off():
    if os.path.exists(PROBE_JSON):
        os.remove(PROBE_JSON)


def log_size():
    return os.path.getsize(PROBE_LOG) if os.path.exists(PROBE_LOG) else 0


_LINE = re.compile(r"^(\d+) (.*)$")


def log_since(offset):
    """probe.log lines after offset as dicts: tick, pid, tid, exe, what (the callback), and its key=value fields."""
    if not os.path.exists(PROBE_LOG):
        return []
    with open(PROBE_LOG, "rb") as f:
        f.seek(offset)
        data = f.read().decode("utf-8", "replace")
    rows = []
    for line in data.splitlines():
        m = _LINE.match(line)
        if not m:
            continue
        r = {"tick": int(m.group(1)), "what": None}
        for w in m.group(2).split(" "):
            if "=" in w:
                k, v = w.split("=", 1)
                r[k] = v
            elif r["what"] is None:
                r["what"] = w
        rows.append(r)
    return rows


def wait_log(pred, label, timeout=6.0):
    end = time.time() + timeout
    while time.time() < end:
        if any(pred(r) for r in log_since(0)[-500:]):
            return
        time.sleep(0.1)
    raise Aborted(f"timed out waiting for {label}: is「キーの確認（keyprobe）」the input method there? "
                  f"(README.md「準備」)")


KEY_CALLS = ("TestKeyDown", "KeyDown", "TestKeyUp", "KeyUp", "PreservedKey")


def key_rows(offset, exe, scan=None):
    return [r for r in log_since(offset) if r.get("exe", "").lower() == exe.lower() and r["what"] in KEY_CALLS
            and (scan is None or r["what"] == "PreservedKey" or r.get("scan") == f"0x{scan:02X}")]


def describe(rows, preserved=()):
    """Compact text of key callbacks: TestKeyDown:0xC0, KeyDown:0x19* (eaten), Preserved(0x19+16)."""
    out = []
    for r in rows:
        if r["what"] == "PreservedKey":
            i = int(r["index"])
            out.append(f"Preserved({hex(preserved[i][0])}+{preserved[i][1]})" if 0 <= i < len(preserved) else "Preserved(?)")
        else:
            out.append(f"{r['what']}:{r['vk']}{'*' if r['ret'] == '1' else ''}")
    return " ".join(out) or "(nothing)"


# -- the Tk target ---------------------------------------------------------------------------------

class TkTarget:
    """A Tk window that logs every key event it receives (target_tk.py)."""

    def __init__(self, title, menu=False):
        os.makedirs(WORK, exist_ok=True)
        self.log = os.path.join(WORK, f"{title}.log")
        open(self.log, "w").close()
        args = [sys.executable, os.path.join(HERE, "target_tk.py"), title, self.log] + (["--menu"] if menu else [])
        self.proc = subprocess.Popen(args)
        self.hwnd, pid = find_window(title)
        bring_front(self.hwnd, pid)
        time.sleep(0.8)

    def size(self):
        return os.path.getsize(self.log)

    def rows(self, offset):
        with open(self.log, encoding="utf-8") as f:
            f.seek(offset)
            return [json.loads(x) for x in f.read().splitlines() if x.strip()]

    def text(self, offset):
        return " ".join(f"{r['ev']}:{r.get('keysym', '')}" for r in self.rows(offset)
                        if r["ev"] == "menu" or r.get("keycode") not in (16, 17, 18)) or "(nothing)"

    def close(self):
        close(self.hwnd)
        try:
            self.proc.wait(10)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def key_state(exe):
    """Key state in the target thread, read from the probe's log line for an F12 press."""
    off = log_size()
    chord(VK_F12, settle=0.25)
    for r in key_rows(off, exe):
        if r.get("vk") == "0x7B" and "ks_kanji" in r:
            return {k: int(r[k], 16) for k in ("ks_oem3", "ks_kanji", "ks_capital", "ks_kana") if k in r}
    return {}


def restore_state(exe):
    """Undo what the checks may leave behind: a stuck VK_KANJI, caps lock, kana lock."""
    st = key_state(exe)
    if st.get("ks_kanji", 0) & 0x8000:
        guard()
        send(VK_KANJI, True)  # the up the layout never sent (Alt released before `)
    if st.get("ks_capital", 0) & 1:
        chord(0, scan=SC["caps"])  # CapsLock alone toggles it (Shift+CapsLock is 英数 on kbd101)
    if st.get("ks_kana", 0) & 1:
        chord(0, CTRL | SHIFT, scan=SC["caps"])
    return key_state(exe)
