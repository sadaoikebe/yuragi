"""The engine's settings file, ~/.yuragi-ime/config.json.

Five settings, each one of a few values (the first is the default):

  learning     "on" or "off": learn from conversions (DESIGN「学習履歴のファイル」)
  prediction   "auto", "tab" or "off": continuations of unconverted input
  lm_rescore   true or false: rescore the candidates with the language model
  keyboard     "auto" or "kb232": a JIS keyboard Windows cannot tell from kbd106 (docs/JIS.md §2)
  space_thumb  "auto", "right" or "left": the thumb that presses Space on a JIS keyboard
               ("auto": either, decided at conversion)

A key the engine does not know is ignored. No file means the defaults; a file
that cannot be used (broken JSON, a wrong value) means the defaults too, and
the engine logs why. The engine reads the file when it starts; the management
window (admin_ui) edits it. The TIP keeps its own tip.json (read by the C++ side).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile

DEFAULT_RUNTIME_DIR = Path.home() / ".yuragi-ime"  # the user's data: config.json, logs, ...
CONFIG_NAME = "config.json"

SETTINGS = {
    "learning": ("on", "off"),
    "prediction": ("auto", "tab", "off"),
    "lm_rescore": (True, False),
    "keyboard": ("auto", "kb232"),
    "space_thumb": ("auto", "right", "left"),
}
DEFAULTS = {name: values[0] for name, values in SETTINGS.items()}


def stored(path: Path) -> dict:
    """The file's settings, as written; raises ValueError when it cannot be used."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))  # a BOM is fine
    except FileNotFoundError:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path} does not hold a JSON object")
    known = {key: value for key, value in raw.items() if key in SETTINGS}
    for key, value in known.items():
        if value not in SETTINGS[key] or isinstance(value, bool) != isinstance(
                SETTINGS[key][0], bool):
            raise ValueError(f"{key} is one of {list(SETTINGS[key])}, not {value!r}")
    return known


def load(path: Path) -> dict:
    """Every setting: the file's value or the default."""
    try:
        return {**DEFAULTS, **stored(path)}
    except (OSError, ValueError) as exc:  # UnicodeDecodeError is a ValueError
        print(f"{path}: not used, built-in defaults instead ({exc})", file=sys.stderr)
        return dict(DEFAULTS)


def write_json(path: Path, raw: dict) -> None:
    """Replace the file atomically."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as f:
            tmp = Path(f.name)
            json.dump(raw, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def set_setting(path: Path, key: str, value) -> None:
    """Write one setting into the file. A broken file raises ValueError (it is
    not overwritten)."""
    if value not in SETTINGS[key]:
        raise ValueError(f"{key} is one of {list(SETTINGS[key])}, not {value!r}")
    raw = stored(path)
    raw[key] = value
    write_json(path, raw)


def unset_setting(path: Path, key: str) -> bool:
    """Drop a setting from the file (back to the default)."""
    raw = stored(path)
    if key not in raw:
        return False
    del raw[key]
    write_json(path, raw)
    return True
