"""Keymap presets and user overrides, compiled for lookup by phase and chord."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import cache
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from yuragi.chord.keys import (
    ALT, DEFAULT_KEYBOARD, KEYBOARDS, MODE_KEYS, MODIFIER_VKS, SPACE, VK_OEM_3, WIN, Chord, Keyboard,
    modifier_bits,
)
from . import config
from .commands import COMMANDS, Command, INPUT, SEND_KEYS

PRESET_PATH = Path(__file__).resolve().parents[1] / "data" / "keymaps" / "ms-ime.json"
DEFAULT_PRESET = "ms-ime"
KEYMAP_NAME = "keymap.json"
CUSTOM = "custom"
DEFAULT_TOGGLE = Chord("`", ALT)  # tip.json's default: Alt+` as pressed, which Windows makes 漢字
KANJI = Chord("漢字")

PARENT = {
    "direct": "global",
    "empty": "global",
    "composing": "global",
    "converting": "global",
    "selecting": "converting",
    "resizing": "converting",
    "predicting": "composing",
    "editing": "converting",
}

type BindingKey = tuple[str, Chord]
type Bindings = dict[BindingKey, str | None]


def chord_allowed(phase: str, chord: Chord) -> bool:
    """The same on every keyboard (KEYBIND §4.2)."""
    return not (
        (chord.key in MODE_KEYS and chord.mods)  # Windows makes these with the modifier
        or (chord.alt_only and phase != "global")
        or (chord.character and phase in ("empty", "composing"))
        or (chord.typing and phase in ("global", "direct"))
    )


def command_allowed(phase: str, chord: Chord, command: Command) -> bool:
    if phase not in command.phases:
        return False
    # A ThumbTap runs after down. Commands that need to return the original
    # stroke or ask the TIP to act require a regular key request.
    return chord != SPACE or (
        command.where == "engine" and command.key == "eat"
        and not (phase in ("converting", "editing") and command.passes_at_edge)
    )


def implemented(command: Command) -> bool:
    return command.run is not None or command.where == "tip"


def merged_bindings(base: Bindings, overrides: Bindings) -> Bindings:
    # A key given a global command leaves the phase rows, except a key sent in place of another:
    # where a phase binds it (Ctrl+H while composing), that row stays first.
    global_keys = {chord for (phase, chord), command_id in overrides.items()
                   if phase == "global" and command_id is not None
                   and implemented(COMMANDS[command_id]) and command_id not in SEND_KEYS}
    rows = {key: command for key, command in base.items()
            if key[0] == "global" or key[1] not in global_keys}
    for key, command in overrides.items():
        if command is None:
            rows.pop(key, None)
        else:
            rows[key] = command
    return rows


class Keymap:
    def __init__(self, bindings: Bindings, unbound_input: str = "commit_and_pass"):
        self._unbound_input = COMMANDS[unbound_input]
        rows: dict[str, dict[Chord, Command]] = {phase: {} for phase in (*PARENT, "global")}
        for (phase, chord), command_id in bindings.items():
            command = COMMANDS[command_id]
            if implemented(command):
                rows[phase][chord] = command

        # Keep global fallbacks separate from bindings scoped to a phase. A phase
        # inherits only the parent's rows whose command works in it (KEYBIND §5.4).
        for phase, parent in PARENT.items():
            if parent != "global":
                inherited = {chord: command for chord, command in rows[parent].items()
                             if phase in command.phases}
                rows[phase] = inherited | rows[phase]
        self._rows = MappingProxyType({phase: MappingProxyType(row) for phase, row in rows.items()})

    def lookup(self, phase: str, chord: Chord) -> Command | None:
        return self._rows[phase].get(chord) or self._rows["global"].get(chord)

    def command_for(self, phase: str, chord: Chord) -> Command:
        command = self.lookup(phase, chord)
        if command is not None:
            return command
        if phase in INPUT and not chord.alt_only and not chord.mods & WIN:
            return self._unbound_input
        return COMMANDS["pass_through"]

    def eat_table(self, keyboard: Keyboard) -> dict:
        """The table the TIP looks keys up in (KEYBIND §7.1), in the keyboard's key codes."""
        def coded(phase: str) -> list[tuple[int, Command]]:
            rows = ((keyboard.code(chord), command) for chord, command in self._rows[phase].items()
                    if not chord.typing)
            return sorted(((code, command) for code, command in rows if code is not None),
                          key=lambda row: row[0])

        phases = {}
        for phase in self._rows:
            if phase in ("global", "direct"):
                continue
            row = {"eat": [], "pass": []}
            for code, command in coded(phase):
                row["pass" if command.key == "pass" else "eat"].append(code)
            if phase in INPUT:
                row["rest"] = "eat"
            phases[phase] = row
        table = {
            "characters": keyboard.character_vks(),  # the keys typing goes to the engine with
            "phases": phases,
            "global": [{"code": code, "command": command.id} for code, command in coded("global")],
        }
        canonical = json.dumps(table, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return {"rev": sha256(canonical).hexdigest()[:12], **table}


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def _read_object(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"), parse_constant=_reject_json_constant)
    except RecursionError as exc:
        raise ValueError("JSON の入れ子が深すぎます") from exc
    if not isinstance(raw, dict):
        raise ValueError("JSON オブジェクトが必要です")
    return raw


def _read_binding(row, *, allow_remove: bool) -> tuple[BindingKey, str | None]:
    if (not isinstance(row, list) or len(row) != 3
            or not isinstance(row[0], str) or not isinstance(row[1], str)
            or not (isinstance(row[2], str) or (allow_remove and row[2] is None))):
        raise ValueError("[局面, キー, 機能] の形式ではありません")
    phase, name, command_id = row
    if phase not in PARENT and phase != "global":
        raise ValueError(f"知らない局面: {phase!r}")
    try:
        chord = Chord.parse(name)
    except ValueError as exc:
        raise ValueError(f"読めないキー: {name!r}") from exc
    if not chord_allowed(phase, chord):
        raise ValueError(f"{name} は {phase} に割り当てられません")
    if command_id is not None:
        command = COMMANDS.get(command_id)
        if command is None:
            raise ValueError(f"知らない機能: {command_id!r}")
        if not command_allowed(phase, chord, command):
            raise ValueError(f"{command.label} は {phase} の {name} に割り当てられません")
    return (phase, chord), command_id


@dataclass(frozen=True)
class Preset:
    label: str
    bindings: Bindings
    unbound_input: str


def _read_preset(name: str) -> Preset:
    if name == DEFAULT_PRESET:
        path = PRESET_PATH
    elif name != CUSTOM and re.fullmatch(r"[a-z0-9][a-z0-9_-]*", name):
        path = PRESET_PATH.with_name(name + ".json")
    else:
        raise ValueError(f"知らないプリセット: {name!r}")
    raw = _read_object(path)
    label, bindings = raw.get("label"), raw.get("bindings")
    if raw.get("name") != name or not isinstance(label, str) or not isinstance(bindings, list):
        raise ValueError(f"プリセット {name} の形式が不正です")
    unbound_input = raw.get("unbound_input", "commit_and_pass")
    if unbound_input not in ("commit_and_pass", "noop"):
        raise ValueError(f"割り当ての無いキーの機能が不正です: {unbound_input!r}")
    rows = dict(_read_binding(row, allow_remove=False) for row in bindings)
    return Preset(label, rows, unbound_input)


@cache
def _default_preset() -> Preset:
    return _read_preset(DEFAULT_PRESET)


@cache
def default_keymap() -> Keymap:
    preset = _default_preset()
    return Keymap(preset.bindings, preset.unbound_input)


def _legacy_overrides(data_dir: Path) -> Bindings:
    """Carry the previous tip.json toggle through to the negotiated table. The versions that
    wrote tip.json knew only the US keyboard, so its key code is read as one."""
    try:
        tip = _read_object(data_dir / "tip.json")
    except (OSError, ValueError):
        return {}
    vk = tip.get("toggle_vk", VK_OEM_3)
    mods = tip.get("toggle_mods", ["alt"])
    if type(vk) is not int or not (0 < vk <= 0xFF) or vk in MODIFIER_VKS:
        return {}
    if not isinstance(mods, list) or any(m not in ("shift", "ctrl", "alt") for m in mods):
        return {}
    chord = KEYBOARDS["ansi101"].chord(vk, modifier_bits(mods, set()))
    if chord == DEFAULT_TOGGLE or chord.typing:
        return {}
    try:
        Chord.parse(str(chord))
    except ValueError:
        return {}
    return {("global", KANJI): None, ("global", chord): "ime_toggle"}


@dataclass
class KeymapSettings:
    presets: dict[str, Preset]
    use: str = DEFAULT_PRESET
    base: str | None = None
    overrides: Bindings = field(default_factory=dict)
    legacy: Bindings = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    error: str | None = None
    custom_name: str = ""

    def bindings(self) -> Bindings:
        if self.use == CUSTOM:
            return merged_bindings(self.presets[self.base].bindings, self.overrides)
        return merged_bindings(self.presets[self.use].bindings, self.legacy)

    def compile(self) -> Keymap:
        if self.use == DEFAULT_PRESET and not self.legacy:
            return default_keymap()
        preset = self.presets[self.base if self.use == CUSTOM else self.use]
        return Keymap(self.bindings(), preset.unbound_input)

    def begin_custom(self) -> None:
        if self.use != CUSTOM:
            self.base, self.use = self.use, CUSTOM
            self.custom_name = ""
            self.overrides = self.legacy.copy()
            self.legacy.clear()

    def save(self, data_dir: Path) -> None:
        raw = {"version": 1, "use": self.use}
        if self.base is not None:
            raw["custom"] = {"base": self.base, "overrides": [
                [phase, str(chord), self.overrides[phase, chord]]
                for phase, chord in sorted(self.overrides, key=lambda key: (key[0], str(key[1])))
            ]}
            if self.custom_name:
                raw["custom"]["name"] = self.custom_name
        config.write_json(data_dir / KEYMAP_NAME, raw)


def load_keymap(data_dir: Path, *, list_presets: bool = False) -> KeymapSettings:
    """Use the same parser for the engine and the editor; only the engine applies it to typing."""
    settings = KeymapSettings({DEFAULT_PRESET: _default_preset()})

    def load_preset(name) -> str:
        if not isinstance(name, str):
            raise ValueError("プリセット名がありません")
        if name not in settings.presets:
            try:
                settings.presets[name] = _read_preset(name)
            except (OSError, ValueError) as exc:
                raise ValueError(f"プリセット {name!r} を使えません ({exc})") from exc
        return name

    try:
        raw = _read_object(data_dir / KEYMAP_NAME)
    except FileNotFoundError:
        settings.legacy = _legacy_overrides(data_dir)
    except (OSError, ValueError) as exc:
        settings.error = f"{KEYMAP_NAME} を読めません ({exc})"
    else:
        try:
            use = raw.get("use", DEFAULT_PRESET)
            if use == CUSTOM or "custom" in raw:
                try:
                    custom = raw.get("custom")
                    if not isinstance(custom, dict) or not isinstance(custom.get("overrides"), list):
                        raise ValueError("ユーザー定義の形式が不正です")
                    settings.base = load_preset(custom.get("base"))
                    name = custom.get("name")
                    if isinstance(name, str):
                        settings.custom_name = name.strip()
                    for index, row in enumerate(custom["overrides"], 1):
                        try:
                            key, command = _read_binding(row, allow_remove=True)
                        except ValueError as exc:
                            settings.notes.append(f"差分 {index} 行目: {exc}")
                            continue
                        if command is not None and not implemented(COMMANDS[command]):
                            continue
                        if key in settings.overrides:
                            settings.notes.append(f"差分 {index} 行目: 同じ局面とキーの前の行を無視しました")
                        settings.overrides[key] = command
                except ValueError as exc:
                    if use == CUSTOM:
                        raise
                    settings.notes.append(str(exc))
            settings.use = CUSTOM if use == CUSTOM else load_preset(use)
        except ValueError as exc:
            settings.error = str(exc)

    if list_presets:
        for path in sorted(PRESET_PATH.parent.glob("*.json")):
            if path.stem not in settings.presets:
                try:
                    load_preset(path.stem)
                except ValueError:
                    continue
    return settings


if __name__ == "__main__":
    # CMake compiles this same preset into the TIP for use before hello.
    import sys

    serialized = json.dumps(default_keymap().eat_table(DEFAULT_KEYBOARD), separators=(",", ":"))
    Path(sys.argv[1]).write_text(
        '#pragma once\n'
        f'inline constexpr char kDefaultKeyTable[] = R"keymap({serialized})keymap";\n',
        encoding="utf-8")
