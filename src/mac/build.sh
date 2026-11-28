#!/bin/sh
# Builds out/Yuragi.app (with the settings window inside) and out/ctl. Python: $PYTHON, else the repository's .venv.
set -eu
cd "$(dirname "$0")"
ROOT=$(cd ../.. && pwd)
PYTHON=${PYTHON:-$ROOT/.venv/bin/python}
APP=out/Yuragi.app
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
(cd "$ROOT" && "$PYTHON" -m yuragi.ime.keymap src/mac/out/default_keymap.h)
clang++ -std=c++17 -fobjc-arc -O2 -I../tip -Iout -c logic.mm -o out/logic.o
clang++ -std=c++17 -O2 -c ../broker/broker_core.cpp -o out/broker_core.o
swiftc -O -swift-version 5 -import-objc-header logic.h main.swift Candidates.swift Controller.swift Engine.swift Launch.swift Peers.swift Keys.swift KeyOrder.swift KeyTap.swift Log.swift \
    out/logic.o out/broker_core.o -lc++ -o "$APP/Contents/MacOS/Yuragi"
swiftc -O -swift-version 5 ctl.swift -o out/ctl
swiftc -O -swift-version 5 icon.swift -o out/icon
out/icon ゆ "$APP/Contents/Resources/hira.tiff"
out/icon Y "$APP/Contents/Resources/roman.tiff"
cp Info.plist "$APP/Contents/Info.plist"
cp -R strings/en.lproj strings/ja.lproj "$APP/Contents/Resources/"
# The settings window: an application of its own inside the bundle (settings/).
SETTINGS="$APP/Contents/Helpers/Yuragi Settings.app"
mkdir -p "$SETTINGS/Contents/MacOS" "$SETTINGS/Contents/Resources"
swiftc -O -swift-version 5 -parse-as-library settings/*.swift Launch.swift Keys.swift -o "$SETTINGS/Contents/MacOS/YuragiSettings"
cp settings/Info.plist "$SETTINGS/Contents/Info.plist"
rm -rf out/yuragi.iconset
mkdir -p out/yuragi.iconset
sips -s format png "$ROOT/assets/icon/yuragi.ico" --out out/icon-256.png >/dev/null
for size in 16 32 128 256; do
    sips -z $size $size out/icon-256.png --out out/yuragi.iconset/icon_${size}x${size}.png >/dev/null
done
cp out/yuragi.iconset/icon_32x32.png out/yuragi.iconset/icon_16x16@2x.png
cp out/yuragi.iconset/icon_256x256.png out/yuragi.iconset/icon_128x128@2x.png
iconutil -c icns out/yuragi.iconset -o "$SETTINGS/Contents/Resources/yuragi.icns"
# "Yuragi Dev" (dev-identity.sh) keeps the Input Monitoring permission across builds; ad-hoc loses it.
KEYCHAIN="$HOME/Library/Keychains/yuragi-dev.keychain-db"
if security find-certificate -c "Yuragi Dev" "$KEYCHAIN" >/dev/null 2>&1; then
    security unlock-keychain -p yuragi-dev "$KEYCHAIN"
    codesign --force --keychain "$KEYCHAIN" --sign "Yuragi Dev" "$SETTINGS"
    codesign --force --keychain "$KEYCHAIN" --sign "Yuragi Dev" "$APP"
else
    codesign --force --sign - "$SETTINGS"
    codesign --force --sign - "$APP"
fi
echo "built $APP"
