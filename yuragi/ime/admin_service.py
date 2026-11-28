"""The management window's work for a window that is not Python (macOS: src/mac/settings).

  python -m yuragi.ime.admin_service [--runtime-dir DIR] [--dict-dir DIR]

One JSON object per line on stdin ({"op": ..., ...}), one reply per line on stdout.
The work is AdminModel's (admin_ui), on the same files; the key editor's rules are
keymap's, as in keymap_ui. Everything shown comes from here in Japanese: the window
only lays it out.

A change replies {"ok", "message"}; the window then asks for what it shows again.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from yuragi.chord.keys import Chord, modifier_bits
from . import broker_client, keymap, personal
from .admin_ui import RESTART_NOTE, SETTINGS, AdminModel, Outcome
from .commands import COMMANDS
from .keyboard_setting import system_keyboard
from .keymap_ui import PHASES, KeyTab

# The settings of keyboards the input program does not tell apart yet (docs/MACOS.md §8).
UNUSED = {"keyboard", "space_thumb"} if sys.platform == "darwin" else set()
FOLLOW_PRESET = "プリセットに従う"
REMOVE = "割り当てを外す"


class KeyEditor:
    """The key settings being edited: nothing is written until save."""

    def __init__(self, model: AdminModel):
        self.model = model
        self.settings: keymap.KeymapSettings | None = None
        self.added: set[Chord] = set()
        self.chords: dict[str, Chord] = {}
        self.presets: list[str | None] = []
        self.dirty = False
        self.keyboard = system_keyboard()

    def _open(self) -> keymap.KeymapSettings:
        if self.settings is None:
            self.settings = self.model.key_settings()
            # A file that was read with notes is worth saving again as it was understood.
            self.dirty = bool(self.settings.error or self.settings.notes)
        return self.settings

    def view(self) -> dict:
        settings = self._open()
        self.presets = list(settings.presets)
        labels = [preset.label for preset in settings.presets.values()]
        if settings.legacy:
            self.presets.append(None)
            labels.append(settings.presets[keymap.DEFAULT_PRESET].label + "（従来の切り替えキー）")
        if settings.base is not None:
            self.presets.append(keymap.CUSTOM)
            label = settings.custom_name or "ユーザー定義"
            labels.append(label + "（ユーザー定義）" if label in labels else label)
        rows = settings.bindings()
        keys = sorted(self.added | {key for _, key in rows}, key=lambda k: str(k).casefold())
        self.chords = {str(key): key for key in keys}
        return {
            "presets": labels,
            "selected": self.presets.index(None if settings.legacy else settings.use),
            "custom": settings.use == keymap.CUSTOM,
            "name": settings.custom_name,
            "notes": ([settings.error] if settings.error else []) + settings.notes,
            "phases": list(PHASES.values()),
            "rows": [{"key": name, "cells": [KeyTab._cell(rows, phase, key) for phase in PHASES]}
                     for name, key in self.chords.items()],
            "dirty": self.dirty,
        }

    def select_preset(self, index: int) -> Outcome:
        settings = self._open()
        use = self.presets[index]
        if use is not None and (use != settings.use or settings.legacy):
            settings.use = use
            settings.legacy.clear()
            self.dirty = True
        return Outcome(True, "")

    def rename(self, name: str) -> Outcome:
        settings = self._open()
        if settings.use != keymap.CUSTOM:
            return Outcome(False, "名前を変えられるのは、ユーザー定義のキー設定です")
        if name.strip() != settings.custom_name:
            settings.custom_name = name.strip()
            self.dirty = True
        return Outcome(True, "")

    def _choices(self, phase: str, chord: Chord) -> dict[str, str]:
        return {cmd.label: cmd.id for cmd in COMMANDS.values()
                if keymap.command_allowed(phase, chord, cmd) and keymap.implemented(cmd)}

    def detail(self, key: str) -> dict:
        """What one key does in each phase, and what it can be given there."""
        settings, chord = self._open(), self.chords[key]
        active = settings.overrides if settings.use == keymap.CUSTOM else settings.legacy
        rows = settings.bindings()
        phases = []
        for phase, label in PHASES.items():
            allowed = keymap.chord_allowed(phase, chord)
            picked = FOLLOW_PRESET
            if (phase, chord) in active:
                command = active[phase, chord]
                picked = REMOVE if command is None else COMMANDS[command].label
            phases.append({"id": phase, "label": label, "allowed": allowed, "picked": picked,
                           "now": KeyTab._cell(rows, phase, chord),
                           "choices": [FOLLOW_PRESET, REMOVE, *self._choices(phase, chord)]
                           if allowed else []})
        return {"key": key, "phases": phases}

    def assign(self, key: str, phase: str, choice: str) -> Outcome:
        settings, chord = self._open(), self.chords[key]
        if phase not in PHASES or not keymap.chord_allowed(phase, chord):
            return Outcome(False, f"{key} は「{PHASES.get(phase, phase)}」に割り当てられません")
        choices = self._choices(phase, chord)
        if choice not in (FOLLOW_PRESET, REMOVE, *choices):
            return Outcome(False, f"{key} に「{choice}」は割り当てられません")
        settings.begin_custom()
        if choice == FOLLOW_PRESET:
            settings.overrides.pop((phase, chord), None)
        else:
            settings.overrides[phase, chord] = choices.get(choice)
        self.dirty = True
        return Outcome(True, "")

    def press(self, vk: int, mods: list[str]) -> dict:
        """A key pressed in the window: its row, added when the table has none."""
        self._open()
        if "win" in mods:
            return {"ok": False, "message": "Command を使うキーは割り当てられません"}
        chord = self.keyboard.chord(vk, modifier_bits(mods, set()))
        try:
            Chord.parse(str(chord))
        except ValueError:
            return {"ok": False, "message": "このキーは割り当てに使えません"}
        if not any(keymap.chord_allowed(phase, chord) for phase in PHASES):
            return {"ok": False, "message": f"{chord} は割り当てに使えません"}
        if str(chord) not in self.chords:
            self.added.add(chord)
        return {"ok": True, "message": "", "key": str(chord)}

    def save(self) -> Outcome:
        settings = self._open()
        outcome = self.model.save_keys(settings)
        if outcome.ok:
            settings.error = None
            settings.notes.clear()
            self.dirty = False
        return outcome

    def revert(self) -> Outcome:
        """Drop the unsaved changes: the next view reads the file again."""
        self.settings = None
        self.added.clear()
        return Outcome(True, "")


class Service:
    def __init__(self, model: AdminModel):
        self.model = model
        self.keys = KeyEditor(model)

    def state(self) -> dict:
        m = self.model
        store = m.learning_store()
        learned = []
        for pair in m.learned(store=store):
            reading, surface, when, word = m.learned_row(pair)
            learned.append({"reading": reading, "surface": surface, "when": when, "word": bool(word)})
        return {
            "words": [{"reading": w.reading, "surface": w.surface, "pos": w.pos, "cost": w.cost}
                      for w in m.words()],
            "learned": learned,
            "counts": m.learning_counts(store),
            "settings": [{"name": row.name, "label": row.label, "help": row.help,
                          "value": row.edit, "choices": row.choices}
                         for row in m.setting_rows() if row.name not in UNUSED],
            "pos": list(personal.POS_NAMES),
            "default_cost": personal.DEFAULT_COST,
        }

    def status(self) -> dict:
        broker = broker_client.status()
        return {"engine": broker["state"] if broker else "",
                "rows": [list(row) for row in self.model.status_rows()]}

    def set_setting(self, name: str, value: str) -> Outcome:
        """Write the setting and start the engine again: it reads the file when it starts."""
        if name not in SETTINGS:
            return Outcome(False, f"知らない設定です: {name}")
        outcome = self.model.set_setting(name, value)
        if not outcome.ok:
            return outcome
        message = outcome.message.removesuffix(RESTART_NOTE)
        if self.model.restart_engine().ok:
            return Outcome(True, message)
        return Outcome(True, message + "変換エンジンが次に起動したときに反映されます。")

    def handle(self, msg: dict):
        m, keys, op = self.model, self.keys, msg.get("op")
        if op == "state":
            return self.state()
        if op == "status":
            return self.status()
        if op == "add_word":
            return m.add_word(msg["reading"], msg["surface"], msg["pos"], msg.get("cost", ""))
        if op == "remove_word":
            return m.remove_word(msg["reading"], msg["surface"])
        if op == "forget":
            return m.forget(msg["reading"], msg["surface"])
        if op == "promote":
            return m.promote(msg["reading"], msg["surface"], msg["pos"])
        if op == "set_setting":
            return self.set_setting(msg["name"], msg["value"])
        if op == "restart":
            return m.restart_engine()
        if op == "keys":
            return keys.view()
        if op == "key_preset":
            return keys.select_preset(msg["index"])
        if op == "key_rename":
            return keys.rename(msg["name"])
        if op == "key_detail":
            return keys.detail(msg["key"])
        if op == "key_assign":
            return keys.assign(msg["key"], msg["phase"], msg["choice"])
        if op == "key_press":
            return keys.press(msg["vk"], msg["mods"])
        if op == "key_save":
            return keys.save()
        if op == "key_revert":
            return keys.revert()
        return Outcome(False, f"知らない操作です: {op}")

    def reply(self, line: str) -> dict:
        """One request's answer. Whatever goes wrong is said in the window, as AdminWindow does."""
        try:
            answer = self.handle(json.loads(line))
        except Exception as exc:  # a file that cannot be written, a request without its field
            answer = Outcome(False, f"できませんでした（{exc}）")
        if isinstance(answer, Outcome):
            return {"ok": answer.ok, "message": answer.message}
        return answer


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runtime-dir", type=Path, default=None)
    parser.add_argument("--dict-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    if args.dict_dir is not None:
        from yuragi.lattice import mozc_dict
        mozc_dict.DICT_DIR = args.dict_dir
    service = Service(AdminModel(args.runtime_dir))
    # Bytes: the replies are UTF-8 whatever the locale says.
    for line in sys.stdin.buffer:
        text = line.decode("utf-8", "replace").strip()
        if text:
            sys.stdout.buffer.write(json.dumps(service.reply(text), ensure_ascii=False).encode("utf-8") + b"\n")
            sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
