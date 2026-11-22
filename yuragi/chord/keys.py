"""US ANSI virtual-key → NICOLA-A key id, and the Shift (little finger) layer."""

from __future__ import annotations

from dataclasses import dataclass

# Win32 VK
VK_SPACE = 0x20
VK_BACK = 0x08
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
VK_CONVERT = 0x1C
VK_NONCONVERT = 0x1D
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_OEM_1 = 0xBA  # ;
VK_OEM_PLUS = 0xBB
VK_OEM_COMMA = 0xBC
VK_OEM_MINUS = 0xBD
VK_OEM_PERIOD = 0xBE
VK_OEM_2 = 0xBF  # /
VK_OEM_3 = 0xC0
VK_OEM_4 = 0xDB  # [
VK_OEM_5 = 0xDC  # \
VK_OEM_6 = 0xDD  # ]
VK_OEM_7 = 0xDE  # '

# letter key id as in data/nicola_a.json
VK_TO_M: dict[int, str] = {
    0x51: "q",
    0x57: "w",
    0x45: "e",
    0x52: "r",
    0x54: "t",
    0x59: "y",
    0x55: "u",
    0x49: "i",
    0x4F: "o",
    0x50: "p",
    0x41: "a",
    0x53: "s",
    0x44: "d",
    0x46: "f",
    0x47: "g",
    0x48: "h",
    0x4A: "j",
    0x4B: "k",
    0x4C: "l",
    VK_OEM_1: ";",
    VK_OEM_4: "[",
    0x5A: "z",
    0x58: "x",
    0x43: "c",
    0x56: "v",
    0x42: "b",
    0x4E: "n",
    0x4D: "m",
    VK_OEM_COMMA: ",",
    VK_OEM_PERIOD: ".",
    VK_OEM_2: "/",
    # The digit row and the other symbol keys: plain and
    # thumb faces in data/nicola_a.json, so they take part in the chord FSM.
    **{0x30 + d: str(d) for d in range(10)},
    VK_OEM_3: "`",
    VK_OEM_MINUS: "-",
    VK_OEM_PLUS: "=",
    VK_OEM_6: "]",
    VK_OEM_5: "\\",
    VK_OEM_7: "'",
}

SHIFT, CTRL, ALT, WIN = 1, 2, 4, 8
SHIFT_VKS = {VK_SHIFT, 0xA0, 0xA1}
CTRL_VKS = {VK_CONTROL, 0xA2, 0xA3}
ALT_VKS = {VK_MENU, 0xA4, 0xA5}
WIN_VKS = {VK_LWIN, VK_RWIN}
SHORTCUT_VKS = CTRL_VKS | ALT_VKS | WIN_VKS
MODIFIER_VKS = SHIFT_VKS | SHORTCUT_VKS
_MODIFIERS = (("Ctrl", CTRL, CTRL_VKS), ("Alt", ALT, ALT_VKS),
              ("Shift", SHIFT, SHIFT_VKS), ("Win", WIN, WIN_VKS))
_MOD_BITS = {name.lower(): bit for name, bit, _ in _MODIFIERS}

# Shift is the little-finger layer and never joins a chord:
# Shift+letters are the native upper-case letters; Shift+digits/symbols give
# the upper engraving in full width, with ' giving ”.
ANSI_SHIFTED = {
    VK_OEM_1: ":", VK_OEM_PLUS: "+", VK_OEM_COMMA: "<", VK_OEM_MINUS: "_",
    VK_OEM_PERIOD: ">", VK_OEM_2: "?", VK_OEM_3: "~", VK_OEM_4: "{",
    VK_OEM_5: "|", VK_OEM_6: "}", VK_OEM_7: '"',
    **{0x30 + d: ")!@#$%^&*("[d] for d in range(10)},
}


def _full_width(ch: str) -> str:
    return chr(ord(ch) + 0xFEE0)


SHIFT_FACES: dict[int, str] = {vk: _full_width(ch) for vk, ch in ANSI_SHIFTED.items()}
SHIFT_FACES[VK_OEM_7] = "\u201d"  # ”, not ＂

NUMPAD = dict(zip(range(0x60, 0x6A), "0123456789"))
NUMPAD.update({0x6A: "*", 0x6B: "+", 0x6D: "-", 0x6E: ".", 0x6F: "/"})
_NAMES = {
    **{vk: name.upper() for vk, name in VK_TO_M.items()},
    VK_SPACE: "Space", VK_RETURN: "Enter", VK_BACK: "Backspace", 0x09: "Tab",
    VK_CONVERT: "Convert", VK_NONCONVERT: "NonConvert",
    VK_ESCAPE: "Esc", 0x2E: "Delete", 0x2D: "Insert", 0x24: "Home", 0x23: "End",
    0x21: "PageUp", 0x22: "PageDown", 0x25: "Left", 0x27: "Right", 0x26: "Up",
    0x28: "Down", 0x14: "CapsLock", **{0x6F + n: f"F{n}" for n in range(1, 25)},
    **{0x60 + n: f"Numpad{n}" for n in range(10)},
    0x6A: "NumpadMultiply", 0x6B: "NumpadAdd", 0x6D: "NumpadSubtract",
    0x6E: "NumpadDecimal", 0x6F: "NumpadDivide",
}
_VKS = {name.lower(): vk for vk, name in _NAMES.items()}
KEY_NAMES = tuple(_NAMES.values())


@dataclass(frozen=True, slots=True)
class Chord:
    vk: int
    mods: int = 0

    @classmethod
    def parse(cls, name: str) -> Chord:
        *modifiers, key = name.lower().split("+")
        if key not in _VKS or len(set(modifiers)) != len(modifiers):
            raise ValueError(f"invalid chord: {name}")
        bits = 0
        for modifier in modifiers:
            bit = _MOD_BITS.get(modifier, 0)
            if not bit or bit == WIN:
                raise ValueError(f"invalid chord: {name}")
            bits |= bit
        return cls(_VKS[key], bits)

    def __str__(self) -> str:
        return "+".join([name for name, bit, _ in _MODIFIERS if self.mods & bit]
                        + [_NAMES.get(self.vk, f"VK_{self.vk:02X}")])

    @property
    def code(self) -> int:
        return self.vk | self.mods << 8

    @property
    def alt_only(self) -> bool:
        return self.mods & (CTRL | ALT) == ALT

    @property
    def character(self) -> bool:
        return self.mods in (0, SHIFT) and (self.vk in VK_TO_M or self.vk in NUMPAD)

    @property
    def typing(self) -> bool:
        return self.character or self == SPACE


SPACE = Chord(VK_SPACE)


def modifier_bits(mods: list[str] | None, held: set[int]) -> int:
    if mods is None:
        return sum(bit for _, bit, vks in _MODIFIERS if vks & held)
    return sum({_MOD_BITS[mod] for mod in mods if mod in _MOD_BITS})


def literal_character(vk: int, shift: bool) -> str | None:
    """The character a key gives outside the chord FSM: numpad or Shift."""
    if vk in NUMPAD:
        return NUMPAD[vk]
    if not shift:
        return None
    if ord("A") <= vk <= ord("Z"):
        return chr(vk)
    return SHIFT_FACES.get(vk)


def alnum_character(vk: int, shift: bool) -> str:
    """A letter or symbol's half-width engraving in 英数の続き."""
    if not shift:
        return VK_TO_M[vk]
    return ANSI_SHIFTED.get(vk, chr(vk))


def classify(vk: int) -> tuple[str, str | None]:
    """Return (kind, key_id). kind is M, O, MOD, EDIT, OTHER."""
    if vk == VK_SPACE:
        return "O", "space"
    if vk in VK_TO_M:
        return "M", VK_TO_M[vk]
    if vk in MODIFIER_VKS:
        return "MOD", None
    if vk in (VK_BACK, VK_RETURN, VK_ESCAPE):
        return "EDIT", None
    return "OTHER", None
