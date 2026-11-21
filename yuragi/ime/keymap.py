"""The bundled keymap, compiled once for lookup by phase and chord."""

from __future__ import annotations

import json
from functools import cache
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Iterable

from yuragi.chord.keys import ALT, MODIFIER_VKS, VK_OEM_3, WIN, Chord, modifier_bits
from .commands import COMMANDS, Command, INPUT

PARENT = {
    "direct": "global",
    "empty": "global",
    "composing": "global",
    "converting": "global",
    "selecting": "converting",
    "resizing": "converting",
    "predicting": "composing",
}


class Keymap:
    def __init__(self, bindings: Iterable[tuple[str, str, str]]):
        rows: dict[str, dict[int, Command]] = {phase: {} for phase in (*PARENT, "global")}
        for phase, name, command_id in bindings:
            chord = Chord.parse(name)
            command = COMMANDS[command_id]
            if (phase not in command.phases or (chord.alt_only and phase != "global")
                    or (chord.character and phase in ("global", "direct", "empty", "composing"))
                    or (chord.typing and phase in ("global", "direct"))):
                raise ValueError(f"invalid binding: {phase}, {name}, {command_id}")
            if command.run is not None or command.where == "tip":
                rows[phase][chord.code] = command

        for phase, parent in PARENT.items():
            rows[phase] = rows[parent] | rows[phase]
        self._rows = MappingProxyType({phase: MappingProxyType(row) for phase, row in rows.items()})

    def lookup(self, phase: str, chord: Chord) -> Command | None:
        if not 0 <= chord.vk <= 0xFF:
            return None
        return self._rows[phase].get(chord.code)

    def command_for(self, phase: str, chord: Chord) -> Command:
        command = self.lookup(phase, chord)
        if command is not None:
            return command
        if phase in INPUT and not chord.alt_only and not chord.mods & WIN:
            return COMMANDS["commit_and_pass"]
        return COMMANDS["pass_through"]

    def eat_table(self) -> dict:
        phases = {}
        for phase, commands in self._rows.items():
            if phase in ("global", "direct"):
                continue
            row = {"eat": [], "pass": []}
            for code, command in sorted(commands.items()):
                chord = Chord(code & 0xFF, code >> 8)
                if not chord.typing and command.where == "engine":
                    row["pass" if command.key == "pass" else "eat"].append(code)
            if phase in INPUT:
                row["rest"] = "eat"
            phases[phase] = row
        table = {
            "phases": phases,
            "global": [{"code": code, "command": command.id}
                       for code, command in sorted(self._rows["global"].items())],
        }
        canonical = json.dumps(table, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return {"rev": sha256(canonical).hexdigest()[:12], **table}


@cache
def _default_bindings() -> tuple:
    path = Path(__file__).resolve().parents[1] / "data" / "keymaps" / "ms-ime.json"
    return tuple(map(tuple, json.loads(path.read_text(encoding="utf-8"))["bindings"]))


@cache
def default_keymap() -> Keymap:
    return Keymap(_default_bindings())


def startup_keymap(data_dir: Path) -> Keymap:
    """Carry the previous tip.json toggle through to the negotiated table."""
    try:
        config = json.loads((data_dir / "tip.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return default_keymap()
    if not isinstance(config, dict):
        return default_keymap()
    vk = config.get("toggle_vk", VK_OEM_3)
    mods = config.get("toggle_mods", ["alt"])
    if type(vk) is not int or not (0 < vk <= 0xFF) or vk in MODIFIER_VKS:
        return default_keymap()
    if not isinstance(mods, list) or any(m not in ("shift", "ctrl", "alt") for m in mods):
        return default_keymap()
    chord = Chord(vk, modifier_bits(mods, set()))
    if chord == Chord(VK_OEM_3, ALT) or chord.typing:
        return default_keymap()
    try:
        Chord.parse(str(chord))
    except ValueError:
        return default_keymap()
    rows = (row for row in _default_bindings() if row != ("global", "Alt+`", "ime_toggle"))
    return Keymap((*rows, ("global", str(chord), "ime_toggle")))


if __name__ == "__main__":
    # CMake compiles this same preset into the TIP for use before hello.
    import sys

    serialized = json.dumps(default_keymap().eat_table(), separators=(",", ":"))
    Path(sys.argv[1]).write_text(
        f'#pragma once\ninline constexpr char kDefaultKeyTable[] = R"keymap({serialized})keymap";\n',
        encoding="utf-8")
