"""Shared parts of the key tools: SendInput, the foreground guard, windows.

Everything here only sends keys to the exact window under test.
"""
import ctypes
import ctypes.wintypes as wt
import os
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
WORK = os.path.join(tempfile.gettempdir(), "yuragi-keyprobe")

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

SHIFT, CTRL, ALT = 1, 2, 4  # modifier bits of chord()
VK_SHIFT, VK_CONTROL, VK_MENU, VK_ESCAPE, VK_F12 = 0x10, 0x11, 0x12, 0x1B, 0x7B
VK_CAPITAL, VK_KANJI, VK_OEM_3 = 0x14, 0x19, 0xC0
SC = {"shift": 0x2A, "ctrl": 0x1D, "alt": 0x38, "grave": 0x29, "caps": 0x3A}
MOD_KEYS = ((SHIFT, VK_SHIFT, SC["shift"]), (CTRL, VK_CONTROL, SC["ctrl"]), (ALT, VK_MENU, SC["alt"]))


class Aborted(Exception):
    pass


# -- SendInput -----------------------------------------------------------------------------------

ULONG_PTR = ctypes.c_size_t


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD), ("time", wt.DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]


class _U(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wt.DWORD), ("u", _U)]


EXTENDED, KEYUP, UNICODE, SCANCODE = 0x1, 0x2, 0x4, 0x8
user32.SendInput.argtypes = [wt.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.MapVirtualKeyW.argtypes = [wt.UINT, wt.UINT]
user32.GetForegroundWindow.restype = wt.HWND
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.SetForegroundWindow.argtypes = [wt.HWND]
user32.BringWindowToTop.argtypes = [wt.HWND]
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.IsWindowVisible.argtypes = [wt.HWND]
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.AttachThreadInput.argtypes = [wt.DWORD, wt.DWORD, wt.BOOL]
user32.GetAncestor.argtypes = [wt.HWND, wt.UINT]
user32.GetAncestor.restype = wt.HWND

TARGET = {"pid": None, "hwnd": None}
GA_ROOT = 2  # the top-level window itself; a dialog is its own root, unlike GA_ROOTOWNER


def guard():
    """Keys go out only while the exact window under test (not a dialog of the same app) is in front."""
    fg = user32.GetForegroundWindow()
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(fg, ctypes.byref(pid))
    if TARGET["pid"] is None or pid.value != TARGET["pid"] or not fg or user32.GetAncestor(fg, GA_ROOT) != TARGET["hwnd"]:
        release_mods()
        raise Aborted(f"foreground is {title_of(fg)!r} (pid {pid.value}), not the window under test; stopped")


def send(vk, up, scan=None, ext=False):
    """One key event. With scan, the layout DLL turns the scan code into the VK (as for a real keyboard).
    ext marks an extended key (arrows, Insert, Delete, Home, End, PageUp, PageDown, NumpadDivide)."""
    flags = (KEYUP if up else 0) | (EXTENDED if ext else 0)
    if scan is not None:
        ki = KEYBDINPUT(0, scan, SCANCODE | flags, 0, 0)
    else:
        ki = KEYBDINPUT(vk, user32.MapVirtualKeyW(vk, 0), flags, 0, 0)
    inp = INPUT(type=1, u=_U(ki=ki))
    if user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) != 1:
        raise OSError(ctypes.get_last_error())
    time.sleep(0.03)


def release_mods():
    for vk in (VK_SHIFT, VK_CONTROL, VK_MENU):
        try:
            send(vk, True)
        except OSError:
            pass


def chord(vk, mods=0, scan=None, order="key_first", settle=0.3, ext=False):
    """Press and release a chord.
    order: key_first  = modifiers down, key down, key up, modifiers up   (順 A)
           mods_first = modifiers down, key down, modifiers up, key up   (順 B)
    With scan, every event (modifiers too) goes as a scan code."""
    guard()
    held = [m for m in MOD_KEYS if mods & m[0]]
    for _, mvk, msc in held:
        send(mvk, False, msc if scan is not None else None)
    send(vk, False, scan, ext)
    if order == "key_first":
        send(vk, True, scan, ext)
    for _, mvk, msc in reversed(held):
        send(mvk, True, msc if scan is not None else None)
    if order == "mods_first":
        send(vk, True, scan, ext)
    time.sleep(settle)


def hold(vk, downs, scan=None):
    """downs key-downs without an up in between, then the up (SendInput itself never auto-repeats)."""
    guard()
    for _ in range(downs):
        send(vk, False, scan)
        time.sleep(0.05)
    send(vk, True, scan)
    time.sleep(0.3)


def type_text(text):
    """As Unicode (VK_PACKET): neither the layout nor a kana lock changes it."""
    for ch in text:
        guard()
        for up in (False, True):
            inp = INPUT(type=1, u=_U(ki=KEYBDINPUT(0, ord(ch), UNICODE | (KEYUP if up else 0), 0, 0)))
            user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
            time.sleep(0.03)
    time.sleep(0.2)


# -- windows -------------------------------------------------------------------------------------

def title_of(hwnd):
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def windows():
    found = []
    proc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def cb(h, _):
        if user32.IsWindowVisible(h):
            pid = wt.DWORD()
            user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
            found.append((h, title_of(h), pid.value))
        return True

    user32.EnumWindows(proc(cb), 0)
    return found


def find_window(part, timeout=30.0):
    end = time.time() + timeout
    while time.time() < end:
        for h, t, pid in windows():
            if part.lower() in t.lower():
                return h, pid
        time.sleep(0.3)
    raise Aborted(f"window {part!r} did not appear")


def bring_front(hwnd, pid):
    me = kernel32.GetCurrentThreadId()
    for _ in range(10):
        fg_tid = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
        user32.AttachThreadInput(me, fg_tid, True)
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.AttachThreadInput(me, fg_tid, False)
        time.sleep(0.4)
        root = user32.GetAncestor(hwnd, GA_ROOT) or hwnd
        fg = user32.GetForegroundWindow()
        if fg and user32.GetAncestor(fg, GA_ROOT) == root:
            TARGET["pid"], TARGET["hwnd"] = pid, root
            return
    raise Aborted(f"could not bring {title_of(hwnd)!r} to the front")


def close(hwnd):
    user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
    TARGET["pid"] = TARGET["hwnd"] = None
