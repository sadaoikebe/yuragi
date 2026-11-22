"""Key sequences in the TSF RichEdit (target_tsf.py), with a screenshot after each named key.

    python -m tools.keyprobe.msime_tsf_seq <tag> "<keys>" ["<keys>" ...]

Keys as in msime.py ({Wait} only records). After each {Key}, prints the key downs that reached the app,
the text (composition included), and the IME status, and saves out/shots/<tag><run>_<step>.png (the window)
and ..z.png (the first line, 4x: the underlines of the target clause and of unconverted text).
The candidate window of the new MS-IME is drawn in the full-screen "Windows Input Experience" window,
so only the screenshot shows whether it is open.
"""
import ctypes
import ctypes.wintypes as wt
import os
import struct
import sys
import time
import zlib

from . import lib
from .msime import press, tokens
from .msime_tsf_table import TsfTarget, status, text

user32 = ctypes.WinDLL("user32")
gdi32 = ctypes.WinDLL("gdi32")
user32.GetDC.restype = wt.HDC
user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateCompatibleBitmap.restype = wt.HBITMAP
gdi32.CreateCompatibleBitmap.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]
gdi32.SelectObject.restype = wt.HGDIOBJ
gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
gdi32.BitBlt.argtypes = [wt.HDC] + [ctypes.c_int] * 4 + [wt.HDC, ctypes.c_int, ctypes.c_int, wt.DWORD]
gdi32.GetDIBits.argtypes = [wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT, ctypes.c_void_p, ctypes.c_void_p, wt.UINT]
gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wt.HDC]

# Screen areas (this process is not DPI aware, so these are the coordinates it sees for the target window).
WINDOW = (160, 160, 760, 520)
FIRST_LINE = (250, 293, 200, 22)


def grab(area, path, zoom=1):
    x, y, w, h = area
    sdc = user32.GetDC(None)
    mdc = gdi32.CreateCompatibleDC(sdc)
    bmp = gdi32.CreateCompatibleBitmap(sdc, w, h)
    old = gdi32.SelectObject(mdc, bmp)
    gdi32.BitBlt(mdc, 0, 0, w, h, sdc, x, y, 0x00CC0020 | 0x40000000)  # SRCCOPY | CAPTUREBLT
    info = ctypes.create_string_buffer(struct.pack("<IiiHHIIiiII", 40, w, -h, 1, 32, 0, 0, 0, 0, 0, 0), 44)
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, info, 0)
    gdi32.SelectObject(mdc, old)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(None, sdc)
    rows = bytearray()
    for r in range(h):
        line = buf.raw[r * w * 4:(r + 1) * w * 4]
        rgb = bytearray(w * 3)
        rgb[0::3], rgb[1::3], rgb[2::3] = line[2::4], line[1::4], line[0::4]
        big = b"".join(bytes(rgb[c * 3:c * 3 + 3]) * zoom for c in range(w))
        rows += (b"\0" + big) * zoom

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w * zoom, h * zoom, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(bytes(rows), 6)) + chunk(b"IEND", b""))


def run(seq, tag, shots):
    t = TsfTarget("msime-tsf-seq")
    out = [f"== {seq}"]
    try:
        if not status(t.rows()).get("open"):
            press("Alt+`")
        if status(t.rows()).get("conv") != "0x9":
            press("Ctrl+CapsLock")
        out.append(f"  start {status(t.rows())}")
        mark, n = len(t.rows()), 0
        for tok in tokens(seq):
            if tok != "Wait":
                press(tok, settle=0.06 if len(tok) == 1 else 0.5)
            if len(tok) == 1:
                continue
            n += 1
            time.sleep(0.3)
            grab(WINDOW, os.path.join(shots, f"{tag}_{n:02d}.png"))
            grab(FIRST_LINE, os.path.join(shots, f"{tag}_{n:02d}z.png"), 4)
            rows = t.rows()
            passed = [r["vk"] for r in rows[mark:] if r["ev"] == "key" and r["kind"] in ("down", "sysdown")
                      and r["vk"] not in ("0x10", "0x11", "0x12")]
            mark = len(rows)
            st = status(rows)
            out.append(f"[{n:02d} {tok}] passed={passed} text={text(rows)!r} open={st.get('open')} "
                       f"conv={st.get('conv')} caps={st.get('caps')}")
    except lib.Aborted as e:
        out.append(f"ABORTED {e}")
    finally:
        lib.release_mods()
        try:
            lib.guard()
            for _ in range(3):
                lib.chord(lib.VK_ESCAPE, settle=0.08)
        except lib.Aborted:
            pass
        t.close()
    return "\n".join(out)


def main():
    shots = os.path.join(lib.OUT, "shots")
    os.makedirs(shots, exist_ok=True)
    for i, seq in enumerate(sys.argv[2:]):
        print(run(seq, f"{sys.argv[1]}{i}", shots), flush=True)


if __name__ == "__main__":
    main()
