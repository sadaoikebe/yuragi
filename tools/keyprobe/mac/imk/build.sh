#!/bin/sh
# Builds out/YuragiProbe.app (ad-hoc signed) and out/ctl.
set -eu
cd "$(dirname "$0")"
APP=out/YuragiProbe.app
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
swiftc -O -swift-version 5 main.swift -o "$APP/Contents/MacOS/YuragiProbe"
swiftc -O -swift-version 5 ctl.swift -o out/ctl
swiftc -O -swift-version 5 icon.swift -o out/icon
out/icon ゆ "$APP/Contents/Resources/hira.tiff"
out/icon Y "$APP/Contents/Resources/roman.tiff"
cp Info.plist "$APP/Contents/Info.plist"
codesign --force --sign - "$APP"
echo "built $APP"
