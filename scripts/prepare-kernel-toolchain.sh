#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
NAME=gcc-arm-11.2-2022.02-x86_64-aarch64-none-linux-gnu
ARCHIVE="$ROOT/downloads/toolchains/$NAME.tar.xz"
TOOLCHAIN="$ROOT/downloads/toolchains/$NAME"
URL="https://developer.arm.com/-/media/Files/downloads/gnu/11.2-2022.02/binrel/$NAME.tar.xz"
SHA256=52dbac3eb71dbe0916f60a8c5ab9b7dc9b66b3ce513047baa09fae56234e53f3

mkdir -p "$(dirname "$ARCHIVE")"
if [[ ! -f "$ARCHIVE" ]]; then
    curl -fL --retry 3 "$URL" -o "$ARCHIVE"
fi
printf '%s  %s\n' "$SHA256" "$ARCHIVE" | sha256sum --check --status || {
    echo "Arm toolchain archive checksum mismatch: $ARCHIVE" >&2
    exit 1
}

if [[ ! -x "$TOOLCHAIN/bin/aarch64-none-linux-gnu-gcc" ]]; then
    tar -xJf "$ARCHIVE" -C "$(dirname "$ARCHIVE")"
fi

"$TOOLCHAIN/bin/aarch64-none-linux-gnu-gcc" --version | head -n 1
