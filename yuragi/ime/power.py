"""Whether the PC runs on its battery (CONVERSION「装置とモデル」).

A laptop's discrete GPU cannot power down while a process holds a CUDA
context: about 2 W all the time even when idle (RTX 4060 Laptop, 2026-11-20).
On battery the engine leaves the GPU alone and uses the CPU.
"""
from __future__ import annotations

import sys


def on_battery() -> bool:
    """True only when Windows says the AC line is off. False for a desktop (no
    battery), on AC, when unknown, and off Windows."""
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    class SystemPowerStatus(ctypes.Structure):
        _fields_ = [("ACLineStatus", wintypes.BYTE), ("BatteryFlag", wintypes.BYTE),
                    ("BatteryLifePercent", wintypes.BYTE), ("SystemStatusFlag", wintypes.BYTE),
                    ("BatteryLifeTime", wintypes.DWORD), ("BatteryFullLifeTime", wintypes.DWORD)]

    status = SystemPowerStatus()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
        return False
    return status.ACLineStatus == 0  # 0 offline, 1 online, 255 unknown
