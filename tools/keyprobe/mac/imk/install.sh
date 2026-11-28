#!/bin/sh
# Builds the probe, puts it in ~/Library/Input Methods and enables its two modes.
# Moves to ABC first: stopping the probe while it is selected leaves running apps unable to reach it.
set -eu
cd "$(dirname "$0")"
ID=io.github.yuragi.inputmethod.YuragiProbe
DEST="$HOME/Library/Input Methods/YuragiProbe.app"
./build.sh
out/ctl select com.apple.keylayout.ABC 2>/dev/null || true
pkill -f "Input Methods/YuragiProbe.app/Contents" || true
rm -rf "$DEST" "$HOME/Library/Logs/yuragi-probe/imk.jsonl"
mkdir -p "$HOME/Library/Input Methods" "$HOME/Library/Logs/yuragi-probe"
cp -R out/YuragiProbe.app "$DEST"
# an ad-hoc build is a new app to the OS: the old Input Monitoring record no longer applies and would hide the next prompt
tccutil reset ListenEvent "$ID" >/dev/null 2>&1 || true
out/ctl register "$DEST" 2>/dev/null
out/ctl enable "$ID" 2>/dev/null          # the input method first, then its modes
out/ctl enable "$ID.Japanese" 2>/dev/null
out/ctl enable "$ID.Roman" 2>/dev/null
out/ctl list 2>/dev/null
