"""The bundled keymap, compiled once for lookup by phase and chord."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from types import MappingProxyType
from typing import Iterable

from yuragi.chord.keys import WIN, Chord
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


@cache
def default_keymap() -> Keymap:
    path = Path(__file__).resolve().parents[1] / "data" / "keymaps" / "ms-ime.json"
    return Keymap(json.loads(path.read_text(encoding="utf-8"))["bindings"])
