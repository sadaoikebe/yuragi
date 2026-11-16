"""One settings file for the conversion engine.

~/.yuragi-ime/config.json holds any of the server's options under their
command-line names (lm_deadline_ms for --lm-deadline-ms). A value in the file
replaces the built-in default. No file, or a file that cannot be used as a
whole (broken JSON, an unknown key, a wrong value), means the built-in
defaults; the engine logs why and goes on.

The engine reads the file when it starts: a changed setting takes effect at
the next engine start. The management window (admin_ui) shows and edits it.
The TIP keeps its own ~/.yuragi-ime/tip.json (read by the C++ side).
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

DEFAULT_RUNTIME_DIR = Path.home() / ".yuragi-ime"  # the user's data: config.json, logs, ...
CONFIG_NAME = "config.json"

LEARNING_MODES = ("on", "off")  # config.json "learning" (REDESIGN §6.7)

# Options that only make sense per invocation, never from a file.
NOT_IN_FILE = {"runtime_dir", "config", "help"}


def file_settings(parser: argparse.ArgumentParser) -> dict[str, argparse.Action]:
    # The first action of a dest owns its default (--lm-rescore before --no-lm-rescore).
    actions: dict[str, argparse.Action] = {}
    for a in parser._actions:
        if a.dest not in NOT_IN_FILE:
            actions.setdefault(a.dest, a)
    return actions


def read_config(path: Path, parser: argparse.ArgumentParser) -> dict:
    """The file's values, converted like the command line would; {} if absent.

    Anything wrong in it leaves every setting at its default (REDESIGN §6.2):
    a file the user edited by hand never stops the IME.
    """
    try:
        raw = _read_raw(path)
        return {key: parse_value(parser, key, value) for key, value in raw.items()}
    except (OSError, ValueError) as exc:  # UnicodeDecodeError is a ValueError
        print(f"{path}: not used, built-in defaults instead ({exc})", file=sys.stderr)
        return {}


def load(parser: argparse.ArgumentParser, runtime_dir: Path | None = None,
         config_path: Path | None = None) -> argparse.Namespace:
    """The settings: config.json over the parser's defaults."""
    path = config_path if config_path is not None else (
        (runtime_dir or DEFAULT_RUNTIME_DIR) / CONFIG_NAME)
    parser.set_defaults(**read_config(path, parser))
    settings = parser.parse_args([])
    settings.runtime_dir = runtime_dir
    settings.config = path
    return settings


def is_switch(action: argparse.Action) -> bool:
    """An on/off option (store_true): its file value is true or false."""
    return action.nargs == 0 and isinstance(action.const, bool)


def parse_value(parser: argparse.ArgumentParser, key: str, value):
    """A value as the file holds it, converted and checked like the command line."""
    action = file_settings(parser).get(key)
    if action is None:
        raise ValueError(f"unknown setting {key!r}")
    if is_switch(action):
        if not isinstance(value, bool):
            raise ValueError(f"{key} is true or false, not {value!r}")
    elif value is not None and action.type is not None:
        try:
            value = action.type(value)
        except (TypeError, ValueError):
            raise ValueError(f"{key}: {value!r} is not a valid value") from None
    if action.choices is not None and value not in action.choices:
        raise ValueError(f"{key} is one of {list(action.choices)}, not {value!r}")
    return value


def parse_setting(parser: argparse.ArgumentParser, key: str, text: str):
    """Text typed for a setting (the management window), converted and checked."""
    action = file_settings(parser).get(key)
    if action is None:
        raise ValueError(f"unknown setting {key!r}")
    text = text.strip()
    if is_switch(action):
        lowered = text.lower()
        if lowered in ("true", "on", "yes", "1"):
            return True
        if lowered in ("false", "off", "no", "0"):
            return False
        raise ValueError(f"{key} is on or off (true/false), not {text!r}")
    return parse_value(parser, key, text)


def _read_raw(path: Path) -> dict:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))  # a BOM is fine
    except FileNotFoundError:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path} does not hold a JSON object")
    return raw


def _read_known(path: Path, parser: argparse.ArgumentParser) -> dict:
    """The file's settings the engine knows, as written (writing drops the rest)."""
    known = file_settings(parser)
    return {key: value for key, value in _read_raw(path).items() if key in known}


def _write_raw(path: Path, raw: dict) -> None:
    """Replace the file atomically."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def set_setting(path: Path, parser: argparse.ArgumentParser, key: str, text: str):
    """Write one setting into the file; returns the value as stored. A broken
    file raises ValueError (it is not overwritten)."""
    value = parse_setting(parser, key, text)
    raw = _read_known(path, parser)
    raw[key] = str(value) if isinstance(value, Path) else value
    _write_raw(path, raw)
    return value


def unset_setting(path: Path, parser: argparse.ArgumentParser, key: str) -> bool:
    """Drop a setting from the file (back to the built-in default)."""
    raw = _read_known(path, parser)
    if key not in raw:
        return False
    del raw[key]
    _write_raw(path, raw)
    return True


def learning_mode(settings: argparse.Namespace) -> str:
    """on or off: the learning setting (REDESIGN §6.7); unset is on."""
    return settings.learning or "on"
