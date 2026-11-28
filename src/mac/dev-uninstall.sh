#!/bin/sh
# Removes what dev-install.sh put in place. The user's data (~/.yuragi-ime) and the logs stay.
set -u
cd "$(dirname "$0")"
ID=io.github.yuragi.inputmethod.Yuragi
out/ctl select com.apple.keylayout.ABC >/dev/null 2>&1
for m in "$ID.Roman" "$ID.Japanese" "$ID"; do out/ctl disable "$m" >/dev/null 2>&1; done
pkill -f "Input Methods/Yuragi.app/Contents"
rm -rf "$HOME/Library/Input Methods/Yuragi.app" "$HOME/Library/Application Support/yuragi-ime/versions/dev"
echo "removed"
