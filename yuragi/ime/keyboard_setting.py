"""Which keyboard Windows is set to for Japanese input (docs/JIS.md §2).

The setting is one for the whole PC (the Japanese layout's layer driver, kbd101 or kbd106)
and changes only with a restart, so the engine reads it once and every TIP agrees with it.
A keyboard kbd106 cannot tell from the standard one (the FMV-KB232) is the user's choice
(config.json "keyboard").
"""
from __future__ import annotations

import sys

from typing import Mapping

from yuragi.chord.fsm import thumb_sides
from yuragi.chord.keys import DEFAULT_KEYBOARD, KEYBOARDS, VK_OEM_3, Keyboard

_JAPANESE = 0x0411
_SCAN_RIGHT_OF_P = 0x1A  # [ on 101 (VK_OEM_4), @ on 106 (VK_OEM_3)
_MAPVK_VSC_TO_VK = 1


def keyboard_for(vk_right_of_p: int | None, choice: str = "auto") -> Keyboard:
    """The keyboard whose key right of P has this VK; 101 when unknown.
    On kbd106, a choice other than "auto" names the keyboard; on kbd101 it does not apply."""
    if vk_right_of_p != VK_OEM_3:
        return DEFAULT_KEYBOARD
    return KEYBOARDS["jis106" if choice == "auto" else choice]


def space_sides(keyboard: Keyboard, choice: str = "auto") -> Mapping[str, str]:
    """The thumb keys' sides (config.json "space_thumb"). On 101 Space is the only thumb key,
    so it stays either thumb's whatever the choice: one side would leave the other no chord."""
    if choice == "auto" or keyboard is DEFAULT_KEYBOARD:
        return thumb_sides()
    return thumb_sides(choice)


def japanese_vk_right_of_p() -> int | None:
    """The VK the Japanese layout gives the key right of P, or None without one.
    Reads the layouts already loaded: it loads none, so the user's list does not change."""
    if sys.platform != "win32":
        return None
    import ctypes

    user32 = ctypes.WinDLL("user32")
    user32.GetKeyboardLayoutList.argtypes = [ctypes.c_int, ctypes.c_void_p]
    user32.MapVirtualKeyExW.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p]
    user32.MapVirtualKeyExW.restype = ctypes.c_uint
    count = user32.GetKeyboardLayoutList(0, None)
    layouts = (ctypes.c_void_p * max(count, 1))()
    count = user32.GetKeyboardLayoutList(count, layouts)
    for hkl in layouts[:count]:
        if (hkl or 0) & 0xFFFF == _JAPANESE:
            return user32.MapVirtualKeyExW(_SCAN_RIGHT_OF_P, _MAPVK_VSC_TO_VK, hkl) or None
    return None


def system_keyboard(choice: str = "auto") -> Keyboard:
    return keyboard_for(japanese_vk_right_of_p(), choice)
