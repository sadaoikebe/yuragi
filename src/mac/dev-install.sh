#!/bin/sh
# Builds the input program, puts it in ~/Library/Input Methods as the tag "dev" and enables its modes.
# The engine runs from this working tree with $PYTHON (default: the repository's .venv).
#   DATA_DIR=<folder>  the engine's --data-dir (default: ~/.yuragi-ime, the user's own data)
# Moves to ABC first: stopping the input program while it is selected leaves running apps unable
# to reach it until they are reopened (docs/MACOS.md §6.3).
set -eu
cd "$(dirname "$0")"
ROOT=$(cd ../.. && pwd)
PYTHON=${PYTHON:-$ROOT/.venv/bin/python}
ID=io.github.yuragi.inputmethod.Yuragi
DEST="$HOME/Library/Input Methods/Yuragi.app"
VERSION="$HOME/Library/Application Support/yuragi-ime/versions/dev"
./build.sh
out/ctl select com.apple.keylayout.ABC >/dev/null 2>&1 || true
pkill -f "Input Methods/Yuragi.app/Contents" || true
mkdir -p "$HOME/Library/Input Methods" "$VERSION"
ROOT="$ROOT" PYTHON="$PYTHON" DATA_DIR="${DATA_DIR:-}" "$PYTHON" - "$VERSION/engine.json" <<'PY'
import json, os, sys
root, model = os.environ["ROOT"], os.path.join(os.environ["ROOT"], "data", "cache", "model")
args = ["-m", "yuragi.engine"]
if os.environ["DATA_DIR"]:
    args += ["--data-dir", os.environ["DATA_DIR"]]
for option, name in (("--lm-model", "medium"), ("--lm-cpu-model", "small")):
    if os.path.isdir(os.path.join(model, name)):
        args += [option, os.path.join(model, name)]
with open(sys.argv[1], "w", encoding="utf-8") as f:
    admin = ["-m", "yuragi.ime.admin_service"] + (["--runtime-dir", os.environ["DATA_DIR"]] if os.environ["DATA_DIR"] else [])
    json.dump({"python": os.environ["PYTHON"], "app": root, "args": args, "admin_args": admin},
              f, ensure_ascii=False, indent=1)
PY
rm -rf "$DEST"
cp -R out/Yuragi.app "$DEST"
out/ctl register "$DEST" >/dev/null 2>&1
out/ctl enable "$ID" >/dev/null 2>&1          # the input method first, then its modes
out/ctl enable "$ID.Japanese" >/dev/null 2>&1
out/ctl enable "$ID.Roman" >/dev/null 2>&1
out/ctl list 2>/dev/null | grep "$ID[. ]"
# The enable calls can report success and change nothing (docs/MACOS.md §6.3): then the user adds it.
if ! out/ctl list 2>/dev/null | grep -q "^$ID type=.* enabled=true"; then
    echo "not enabled: add Yuragi in System Settings > Keyboard > Input Sources > Edit > + > Japanese (once)"
    open "x-apple.systempreferences:com.apple.Keyboard-Settings.extension" || true
fi
