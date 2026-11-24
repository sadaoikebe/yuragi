"""Win32 chords and the keyboards (docs/JIS.md §2)."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from yuragi.text import to_full_width

# Win32 VK
VK_SPACE = 0x20
VK_BACK = 0x08
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
VK_IME_ON = 0x16
VK_IME_OFF = 0x1A
VK_CONVERT = 0x1C
VK_NONCONVERT = 0x1D
VK_KANJI = 0x19
VK_DBE_ALPHANUMERIC = 0xF0  # 英数
VK_DBE_KATAKANA = 0xF1
VK_DBE_HIRAGANA = 0xF2
VK_DBE_SBCSCHAR = 0xF3  # 半角/全角
VK_DBE_DBCSCHAR = 0xF4  # 半角/全角 too: the key alternates its two codes
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_OEM_1 = 0xBA
VK_OEM_PLUS = 0xBB
VK_OEM_COMMA = 0xBC
VK_OEM_MINUS = 0xBD
VK_OEM_PERIOD = 0xBE
VK_OEM_2 = 0xBF
VK_OEM_3 = 0xC0
VK_OEM_4 = 0xDB
VK_OEM_5 = 0xDC
VK_OEM_6 = 0xDD
VK_OEM_7 = 0xDE
VK_OEM_102 = 0xE2

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

# The numeric keypad types the same on every keyboard.
NUMPAD = {**dict(zip(range(0x60, 0x6A), "0123456789")), 0x6A: "*", 0x6B: "+", 0x6D: "-", 0x6E: ".", 0x6F: "/"}

# The keys other than character keys, by the names in MS-IME's key table (docs/KEYBIND.md §4.1).
KEY_NAMES = {
    VK_SPACE: "Space", VK_RETURN: "Enter", VK_BACK: "Backspace", 0x09: "Tab",
    VK_IME_ON: "ImeOn", VK_IME_OFF: "ImeOff",
    VK_CONVERT: "変換", VK_NONCONVERT: "無変換", VK_KANJI: "漢字", VK_DBE_SBCSCHAR: "半角/全角",
    VK_DBE_ALPHANUMERIC: "英数", VK_DBE_HIRAGANA: "ひらがな", VK_DBE_KATAKANA: "カタカナ",
    VK_ESCAPE: "Esc", 0x2E: "Delete", 0x2D: "Insert", 0x24: "Home", 0x23: "End",
    0x21: "PageUp", 0x22: "PageDown", 0x25: "Left", 0x27: "Right", 0x26: "Up",
    0x28: "Down", 0x14: "CapsLock", **{0x6F + n: f"F{n}" for n in range(1, 25)},
    **{0x60 + n: f"Numpad{n}" for n in range(10)},
    0x6A: "NumpadMultiply", 0x6B: "NumpadAdd", 0x6D: "NumpadSubtract",
    0x6E: "NumpadDecimal", 0x6F: "NumpadDivide",
}

# The thumb keys of the chord FSM, the same on every keyboard. Which thumb presses each is
# fsm.THUMB_SIDE.
THUMBS = {VK_SPACE: "space", VK_NONCONVERT: "muhenkan", VK_CONVERT: "henkan"}
THUMB_VK = {key: vk for vk, key in THUMBS.items()}

# Windows makes these from a key and a modifier (Alt+` is 漢字, Shift+CapsLock is 英数,
# Shift+カタカナひらがなローマ字 is カタカナ): one row each, with no modifier.
MODE_KEYS = frozenset({"漢字", "英数", "ひらがな", "カタカナ"})
# The two a keyboard makes with Alt: TSF hands them to the IME as PreservedKeys only.
ALT_MADE_KEYS = frozenset({"漢字", "カタカナ"})

# Faces decided by the character, not the keyboard (docs/JIS.md §2).
_KANA_SHIFT = {'"': "”", "'": "’"}  # the quotes as MS-IME types them
_FULL = {"¥": "￥"}


def _full(text: str) -> str:
    return _FULL.get(text) or to_full_width(text)


@dataclass(frozen=True, slots=True)
class Chord:
    key: str  # the key's name (docs/KEYBIND.md §4.1)
    mods: int = 0

    @classmethod
    def parse(cls, name: str) -> Chord:
        *modifiers, key = name.split("+")
        key = _NAMES.get(key.lower())
        if key is None or len(set(m.lower() for m in modifiers)) != len(modifiers):
            raise ValueError(f"invalid chord: {name}")
        bits = 0
        for modifier in modifiers:
            bit = _MOD_BITS.get(modifier.lower(), 0)
            if not bit or bit == WIN:
                raise ValueError(f"invalid chord: {name}")
            bits |= bit
        return cls(key, bits)

    def __str__(self) -> str:
        return "+".join([name for name, bit, _ in _MODIFIERS if self.mods & bit] + [self.key])

    @property
    def character(self) -> bool:
        """A character key of any keyboard, with no modifier or Shift."""
        return self.mods in (0, SHIFT) and self.key in CHARACTER_KEYS

    @property
    def thumb(self) -> bool:
        """A thumb key with no modifier. With one it is a command key (Shift+Space)."""
        return self.mods == 0 and self.key in _THUMB_NAMES

    @property
    def typing(self) -> bool:
        return self.character or self.thumb

    @property
    def alt_only(self) -> bool:
        """Pressed with Alt and not Ctrl: TSF gives it to the IME only as a PreservedKey."""
        return self.mods & (CTRL | ALT) == ALT or self.key in ALT_MADE_KEYS


SPACE = Chord("Space")
_THUMB_NAMES = frozenset(KEY_NAMES[vk] for vk in THUMBS)


def thumb_chord(key: str) -> Chord:
    """The chord a lone thumb key is looked up by (ThumbTap.key)."""
    return Chord(KEY_NAMES[THUMB_VK[key]])


@dataclass(frozen=True, slots=True)
class Key:
    """A character key: one row of a keyboard file."""
    vk: int
    id: str  # what it types without Shift: the chord FSM's and the kana table's key
    shift: str  # what it types with Shift ("" nothing)
    alnum: str  # what it types in alnum (half width)
    kana: bool  # in the kana table: it joins the chord FSM

    @property
    def name(self) -> str:
        return self.id.upper()


class Keyboard:
    """What each key types on one keyboard (data/keyboards/*.json)."""

    def __init__(self, path: Path):
        raw = json.loads(path.read_text(encoding="utf-8"))
        self.name: str = raw["name"]
        self.kana = (path.parent / raw["kana"]).resolve()
        faces = json.loads(self.kana.read_text(encoding="utf-8"))["keys"]
        keys = [Key(int(vk, 16), key, shift, alnum[0] if alnum else key, key in faces)
                for vk, key, shift, *alnum in raw["keys"]]
        self._by_vk = {key.vk: key for key in keys}
        self._by_id = {key.id: key for key in keys}
        self._vks = {key.name: key.vk for key in keys} | {name: vk for vk, name in KEY_NAMES.items()}

    def __repr__(self) -> str:
        return f"Keyboard({self.name!r})"

    def chord(self, vk: int, mods: int) -> Chord:
        """The chord a key event is looked up by: Windows made the modifier part of a mode key."""
        if vk == VK_DBE_DBCSCHAR:
            vk = VK_DBE_SBCSCHAR
        key = self._by_vk.get(vk)
        name = key.name if key else KEY_NAMES.get(vk, f"VK_{vk:02X}")
        if name in MODE_KEYS:
            mods &= WIN
        return Chord(name, mods)

    def code(self, chord: Chord) -> int | None:
        """The chord as the TIP sees it, or None for a key this keyboard lacks."""
        vk = self._vks.get(chord.key)
        return None if vk is None else vk | chord.mods << 8

    def character_names(self) -> list[str]:
        return [key.name for key in self._by_vk.values()]

    def names(self) -> list[str]:
        return self.character_names() + list(KEY_NAMES.values())

    def character_vks(self) -> list[int]:
        return sorted(self._by_vk.keys() | NUMPAD.keys())

    def key_vk(self, key: str) -> int | None:
        found = self._by_id.get(key)
        return None if found is None else found.vk

    def classify(self, vk: int) -> tuple[str, str | None]:
        """Return (kind, key) for the chord FSM."""
        if vk in THUMBS:
            return "O", THUMBS[vk]
        key = self._by_vk.get(vk)
        if key is not None and key.kana:
            return "M", key.id
        if vk in MODIFIER_VKS:
            return "MOD", None
        return "OTHER", None

    def alnum_key(self, vk: int) -> bool:
        """A letter, digit or symbol key: it has alnum faces."""
        return vk in self._by_vk

    def literal_character(self, vk: int, shift: bool) -> str | None:
        """What a key types in kana outside the chord FSM: numpad, Shift or a key with no kana.
        "" is a no-op (eaten, nothing typed); None sends the key to the chord FSM."""
        if vk in NUMPAD:
            return NUMPAD[vk]
        key = self._by_vk.get(vk)
        if key is None:
            return None
        if not shift:
            return None if key.kana else ""
        if key.shift.isascii() and key.shift.isalpha():
            return key.shift
        return _KANA_SHIFT.get(key.shift) or to_full_width(key.shift)

    def alnum_character(self, vk: int, shift: bool, full: bool = False) -> str:
        """What a key types in alnum ("" is a no-op, as JIS Shift+0)."""
        key = self._by_vk[vk]
        if shift:
            return to_full_width(key.shift) if full else key.shift
        return _full(key.id) if full else key.alnum

    def width_faces(self, vk: int | None) -> tuple[str, str] | None:
        """A key whose alnum is not its engraving (JIS ¥ types \\): its half- and full-width faces."""
        found = self._by_vk.get(vk)
        if found is None or found.alnum == found.id:
            return None
        return found.alnum, _full(found.id)

    def key_alnum(self, key: str) -> tuple[str, str]:
        """F9/F10: a chord key's unshifted half- and full-width alnum faces."""
        found = self._by_id.get(key)
        if found is None:  # a key id from a test table: its own text
            return key, to_full_width(key)
        return found.alnum, _full(found.id)


KEYBOARDS = {keyboard.name: keyboard for keyboard in map(
    Keyboard, sorted((Path(__file__).resolve().parents[2] / "data" / "keyboards").glob("*.json")))}
# The keyboard of a request that names none (docs/JIS.md §2).
DEFAULT_KEYBOARD = KEYBOARDS["ansi101"]
# Every keyboard's character keys are character keys here: the rules do not depend on the keyboard.
CHARACTER_KEYS = frozenset(
    {name for keyboard in KEYBOARDS.values() for name in keyboard.character_names()}
    | {KEY_NAMES[vk] for vk in NUMPAD})
_NAMES = {name.lower(): name for name in (*CHARACTER_KEYS, *KEY_NAMES.values())}


def modifier_bits(mods: list[str] | None, held: set[int]) -> int:
    if mods is None:
        return sum(bit for _, bit, vks in _MODIFIERS if vks & held)
    return sum({_MOD_BITS[mod] for mod in mods if mod in _MOD_BITS})
