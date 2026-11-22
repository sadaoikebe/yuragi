"""Win32 window that records what an IME does through IMM (for watching MS-IME, which has no source).

    python target_imm.py <title> <log path>

Each line of the log is JSON: {"t": ms, "ev": ...}.
  key     WM_KEYDOWN/WM_KEYUP/WM_SYSKEYDOWN/WM_SYSKEYUP that reached the window (vk 0xE5 = VK_PROCESSKEY: the IME took it)
  char    WM_CHAR / WM_IME_CHAR (text the app received)
  comp    WM_IME_COMPOSITION: comp (string), attr (per char: 0 input, 1 target converted, 2 converted, 3 target not converted),
          clause (offsets), cursor, result (committed string)
  start / end      WM_IME_STARTCOMPOSITION / WM_IME_ENDCOMPOSITION
  notify  WM_IME_NOTIFY (IMN_*), with the candidate list when it is about candidates
  status  open status and conversion mode after every key message
"""
import ctypes
import ctypes.wintypes as wt
import json
import sys
import time

user32 = ctypes.WinDLL("user32", use_last_error=True)
imm32 = ctypes.WinDLL("imm32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32")
gdi32 = ctypes.WinDLL("gdi32")

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.CreateWindowExW.restype = wt.HWND
user32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]
imm32.ImmGetContext.restype = wt.HANDLE
imm32.ImmGetContext.argtypes = [wt.HWND]
imm32.ImmReleaseContext.argtypes = [wt.HWND, wt.HANDLE]
imm32.ImmGetCompositionStringW.argtypes = [wt.HANDLE, wt.DWORD, ctypes.c_void_p, wt.DWORD]
imm32.ImmGetCompositionStringW.restype = wt.LONG
imm32.ImmGetCandidateListW.argtypes = [wt.HANDLE, wt.DWORD, ctypes.c_void_p, wt.DWORD]
imm32.ImmGetCandidateListW.restype = wt.DWORD
imm32.ImmGetOpenStatus.argtypes = [wt.HANDLE]
imm32.ImmGetConversionStatus.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD), ctypes.POINTER(wt.DWORD)]
imm32.ImmSetCompositionWindow.argtypes = [wt.HANDLE, ctypes.c_void_p]

GCS_COMPSTR, GCS_COMPATTR, GCS_COMPCLAUSE, GCS_CURSORPOS, GCS_RESULTSTR = 0x8, 0x10, 0x20, 0x80, 0x800
KEY_MSGS = {0x100: "down", 0x101: "up", 0x104: "sysdown", 0x105: "sysup"}
IMN = {1: "closestatus", 2: "openstatus", 3: "changecand", 4: "closecand", 5: "opencand", 6: "setconv",
       7: "setsentence", 8: "setopen", 9: "setcandpos", 10: "setcompfont", 11: "setcomppos", 12: "setstatuspos",
       13: "guideline", 14: "private"}

out = None


def log(**kw):
    kw["t"] = int(time.monotonic() * 1000)
    out.write(json.dumps(kw, ensure_ascii=False) + "\n")


def comp_bytes(himc, kind):
    n = imm32.ImmGetCompositionStringW(himc, kind, None, 0)
    if n <= 0:
        return b""
    buf = ctypes.create_string_buffer(n)
    imm32.ImmGetCompositionStringW(himc, kind, buf, n)
    return buf.raw[:n]


def candidates(himc):
    n = imm32.ImmGetCandidateListW(himc, 0, None, 0)
    if not n:
        return None
    buf = ctypes.create_string_buffer(n)
    imm32.ImmGetCandidateListW(himc, 0, buf, n)
    dw = lambda i: int.from_bytes(buf.raw[i * 4:i * 4 + 4], "little")
    count, sel, page_start, page_size = dw(3), dw(4), dw(5), dw(6)
    items = []
    for i in range(min(count, 30)):
        off = dw(8 + i)
        s = buf.raw[off:]
        end = 0
        while end + 1 < len(s) and s[end:end + 2] != b"\0\0":
            end += 2
        items.append(s[:end].decode("utf-16-le", "replace"))
    return {"count": count, "sel": sel, "page_start": page_start, "page_size": page_size, "items": items}


def status(hwnd):
    himc = imm32.ImmGetContext(hwnd)
    if not himc:
        return {"himc": 0}
    conv, sent = wt.DWORD(), wt.DWORD()
    imm32.ImmGetConversionStatus(himc, ctypes.byref(conv), ctypes.byref(sent))
    r = {"open": bool(imm32.ImmGetOpenStatus(himc)), "conv": hex(conv.value), "caps": user32.GetKeyState(0x14) & 1}
    imm32.ImmReleaseContext(hwnd, himc)
    return r


@WNDPROC
def proc(hwnd, msg, wp, lp):
    if msg in KEY_MSGS:
        log(ev="key", kind=KEY_MSGS[msg], vk=hex(wp), scan=hex((lp >> 16) & 0xFF), ext=(lp >> 24) & 1,
            prev=(lp >> 30) & 1, rep=lp & 0xFFFF)
    elif msg in (0x102, 0x286):  # WM_CHAR, WM_IME_CHAR
        log(ev="char", ime=msg == 0x286, ch=chr(wp) if wp < 0x110000 else hex(wp), code=hex(wp))
        if msg == 0x286:
            return 0
    elif msg == 0x10D:
        log(ev="start")
    elif msg == 0x10E:
        log(ev="end")
    elif msg == 0x10F:  # WM_IME_COMPOSITION
        himc = imm32.ImmGetContext(hwnd)
        r = {"ev": "comp", "flags": hex(lp)}
        if lp & GCS_COMPSTR:
            r["comp"] = comp_bytes(himc, GCS_COMPSTR).decode("utf-16-le", "replace")
            r["attr"] = "".join(str(b) for b in comp_bytes(himc, GCS_COMPATTR))
            cl = comp_bytes(himc, GCS_COMPCLAUSE)
            r["clause"] = [int.from_bytes(cl[i:i + 4], "little") for i in range(0, len(cl), 4)]
            r["cursor"] = imm32.ImmGetCompositionStringW(himc, GCS_CURSORPOS, None, 0)
        if lp & GCS_RESULTSTR:
            r["result"] = comp_bytes(himc, GCS_RESULTSTR).decode("utf-16-le", "replace")
        imm32.ImmReleaseContext(hwnd, himc)
        log(**r)
    elif msg == 0x282:  # WM_IME_NOTIFY
        r = {"ev": "notify", "what": IMN.get(wp, hex(wp))}
        if wp in (3, 5):
            himc = imm32.ImmGetContext(hwnd)
            r["cand"] = candidates(himc)
            imm32.ImmReleaseContext(hwnd, himc)
        if wp in (6, 8):
            r.update(status(hwnd))
        log(**r)
    elif msg == 0x0002:
        user32.PostQuitMessage(0)
        return 0
    res = user32.DefWindowProcW(hwnd, msg, wp, lp)
    if msg in KEY_MSGS:
        log(ev="status", **status(hwnd))
    return res


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wt.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR)]


def main():
    global out
    title, path = sys.argv[1], sys.argv[2]
    out = open(path, "a", encoding="utf-8", buffering=1)
    hinst = kernel32.GetModuleHandleW(None)
    wc = WNDCLASSW(lpfnWndProc=proc, hInstance=hinst, lpszClassName="YuragiImmTarget",
                   hbrBackground=gdi32.GetStockObject(0), hCursor=user32.LoadCursorW(None, 32512))
    user32.RegisterClassW(ctypes.byref(wc))
    hwnd = user32.CreateWindowExW(0, "YuragiImmTarget", title, 0x10CF0000, 160, 160, 640, 300,
                                  None, None, hinst, None)
    user32.SetFocus(hwnd)
    log(ev="ready", **status(hwnd))
    msg = wt.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))


if __name__ == "__main__":
    main()
