#!/bin/sh
# Builds and runs the tests of the input program's parts that need no OS service (tests/).
set -eu
cd "$(dirname "$0")"
mkdir -p out
swiftc -swift-version 5 -parse-as-library KeyOrder.swift tests/KeyOrderTests.swift -o out/key-order-test
out/key-order-test
