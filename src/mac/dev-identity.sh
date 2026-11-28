#!/bin/sh
# Makes the code-signing identity "Yuragi Dev" in its own keychain (~/Library/Keychains/yuragi-dev.keychain-db),
# once. build.sh signs with it when it exists: the "Input Monitoring" permission then stays across
# builds, because the OS ties it to the signer (docs/MACOS.md §6.2). An ad-hoc signature loses it
# on every build. Only for this Mac: what is released is signed with a Developer ID.
set -eu
KEYCHAIN="$HOME/Library/Keychains/yuragi-dev.keychain-db"
PASS=yuragi-dev   # guards nothing: the key only signs development builds on this Mac
if security find-certificate -c "Yuragi Dev" "$KEYCHAIN" >/dev/null 2>&1; then echo "exists"; exit 0; fi
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=Yuragi Dev" \
    -addext "keyUsage=critical,digitalSignature" -addext "extendedKeyUsage=critical,codeSigning" \
    -keyout "$TMP/key.pem" -out "$TMP/cert.pem" 2>/dev/null
openssl pkcs12 -export -legacy -inkey "$TMP/key.pem" -in "$TMP/cert.pem" -name "Yuragi Dev" \
    -passout "pass:$PASS" -out "$TMP/id.p12"
[ -f "$KEYCHAIN" ] || security create-keychain -p "$PASS" "$KEYCHAIN"
security set-keychain-settings "$KEYCHAIN"           # no auto-lock
security unlock-keychain -p "$PASS" "$KEYCHAIN"
security import "$TMP/id.p12" -k "$KEYCHAIN" -P "$PASS" -T /usr/bin/codesign >/dev/null
security set-key-partition-list -S apple-tool:,apple: -s -k "$PASS" "$KEYCHAIN" >/dev/null
echo "made"
