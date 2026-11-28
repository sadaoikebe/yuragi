#!/bin/sh
# Removes the probe, its log folder and its Input Monitoring record.
set -u
cd "$(dirname "$0")"
ID=io.github.yuragi.inputmethod.YuragiProbe
out/ctl select com.apple.keylayout.ABC 2>/dev/null
for m in "$ID.Roman" "$ID.Japanese" "$ID"; do out/ctl disable "$m" 2>/dev/null; done
pkill -f "Input Methods/YuragiProbe.app/Contents"
rm -rf "$HOME/Library/Input Methods/YuragiProbe.app" "$HOME/Library/Logs/yuragi-probe"
tccutil reset ListenEvent "$ID" >/dev/null 2>&1
echo "removed"
