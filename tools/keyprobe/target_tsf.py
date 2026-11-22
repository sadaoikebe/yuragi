"""Window with a TSF RichEdit (like Notepad) that records the key messages the IME let through and the text.

    python target_tsf.py <title> <log path>

Each line of the log is JSON: {"t": ms, "ev": ...}.
  key   WM_KEYDOWN/WM_KEYUP/WM_SYSKEYDOWN/WM_SYSKEYUP that reached the RichEdit (the IME did not eat it)
  text  the whole text of the RichEdit (composition included) after each key message and on every change
"""
import ctypes
import ctypes.wintypes as wt
import json
import sys
import time

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32")
kernel32.LoadLibraryW("msftedit.dll")

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.CallWindowProcW.restype = LRESULT
user32.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_void_p]
user32.SetWindowLongPtrW.restype = ctypes.c_void_p
user32.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.SendMessageW.restype = LRESULT
user32.CreateWindowExW.restype = wt.HWND
user32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]
user32.GetWindowTextLengthW.argtypes = [wt.HWND]
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]

imm32 = ctypes.WinDLL("imm32")
imm32.ImmGetContext.restype = wt.HANDLE
imm32.ImmGetContext.argtypes = [wt.HWND]
imm32.ImmReleaseContext.argtypes = [wt.HWND, wt.HANDLE]
imm32.ImmGetCompositionStringW.argtypes = [wt.HANDLE, wt.DWORD, ctypes.c_void_p, wt.DWORD]
imm32.ImmGetCompositionStringW.restype = wt.LONG
imm32.ImmGetOpenStatus.argtypes = [wt.HANDLE]
imm32.ImmGetConversionStatus.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD), ctypes.POINTER(wt.DWORD)]


def imm_state(h):
    himc = imm32.ImmGetContext(h)
    if not himc:
        return {}
    conv, sent = wt.DWORD(), wt.DWORD()
    imm32.ImmGetConversionStatus(himc, ctypes.byref(conv), ctypes.byref(sent))
    r = {"open": bool(imm32.ImmGetOpenStatus(himc)), "conv": hex(conv.value), "caps": user32.GetKeyState(0x14) & 1}
    for name, kind in (("comp", 0x8), ("attr", 0x10)):
        n = imm32.ImmGetCompositionStringW(himc, kind, None, 0)
        if n > 0:
            b = ctypes.create_string_buffer(n)
            imm32.ImmGetCompositionStringW(himc, kind, b, n)
            r[name] = b.raw[:n].decode("utf-16-le", "replace") if name == "comp" else "".join(str(x) for x in b.raw[:n])
    imm32.ImmReleaseContext(h, himc)
    return r


KEY_MSGS = {0x100: "down", 0x101: "up", 0x104: "sysdown", 0x105: "sysup"}
EM_SETEDITSTYLE, SES_USECTF, SES_CTFALLOWEMBED = 0x04CC, 0x00010000, 0x00200000
EM_SETEVENTMASK, ENM_CHANGE, EN_CHANGE = 0x0445, 0x1, 0x0300
EM_EXGETSEL = 0x0434

out = None
edit = [None]
old = [None]
last_text = [None]


def log(**kw):
    kw["t"] = int(time.monotonic() * 1000)
    out.write(json.dumps(kw, ensure_ascii=False) + "\n")


class CHARRANGE(ctypes.Structure):
    _fields_ = [("cpMin", wt.LONG), ("cpMax", wt.LONG)]


def text_now(force=False):
    h = edit[0]
    n = user32.GetWindowTextLengthW(h)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(h, buf, n + 1)
    cr = CHARRANGE()
    user32.SendMessageW(h, EM_EXGETSEL, 0, ctypes.addressof(cr))
    if force or buf.value != last_text[0]:
        last_text[0] = buf.value
        log(ev="text", text=buf.value, sel=[cr.cpMin, cr.cpMax])
    log(ev="status", **imm_state(h))


@WNDPROC
def edit_proc(hwnd, msg, wp, lp):
    if msg in KEY_MSGS:
        log(ev="key", kind=KEY_MSGS[msg], vk=hex(wp), scan=hex((lp >> 16) & 0xFF), prev=(lp >> 30) & 1)
    elif msg == 0x102:
        log(ev="char", code=hex(wp))
    res = user32.CallWindowProcW(old[0], hwnd, msg, wp, lp)
    if msg in KEY_MSGS:
        text_now()
    return res


@WNDPROC
def main_proc(hwnd, msg, wp, lp):
    if msg == 0x0111 and (wp >> 16) == EN_CHANGE:
        text_now()
    elif msg == 0x0005 and edit[0]:  # WM_SIZE
        user32.MoveWindow(edit[0], 0, 0, lp & 0xFFFF, (lp >> 16) & 0xFFFF, True)
    elif msg == 0x0007 and edit[0]:  # WM_SETFOCUS
        user32.SetFocus(edit[0])
        return 0
    elif msg == 0x0002:
        user32.PostQuitMessage(0)
        return 0
    return user32.DefWindowProcW(hwnd, msg, wp, lp)


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
    wc = WNDCLASSW(lpfnWndProc=main_proc, hInstance=hinst, lpszClassName="YuragiTsfTarget",
                   hCursor=user32.LoadCursorW(None, 32512), hbrBackground=6)
    user32.RegisterClassW(ctypes.byref(wc))
    hwnd = user32.CreateWindowExW(0, "YuragiTsfTarget", title, 0x10CF0000, 160, 160, 640, 300,
                                  None, None, hinst, None)
    edit[0] = user32.CreateWindowExW(0, "RICHEDIT50W", "", 0x50200004 | 0x1000, 0, 0, 620, 260,
                                     hwnd, None, hinst, None)  # WS_CHILD|WS_VISIBLE|WS_VSCROLL|ES_MULTILINE|ES_WANTRETURN
    user32.SendMessageW(edit[0], EM_SETEDITSTYLE, SES_USECTF | SES_CTFALLOWEMBED, SES_USECTF | SES_CTFALLOWEMBED)
    user32.SendMessageW(edit[0], EM_SETEVENTMASK, 0, ENM_CHANGE)
    old[0] = user32.SetWindowLongPtrW(edit[0], -4, ctypes.cast(edit_proc, ctypes.c_void_p))
    user32.SetFocus(edit[0])
    log(ev="ready")
    msg = wt.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))


if __name__ == "__main__":
    main()
