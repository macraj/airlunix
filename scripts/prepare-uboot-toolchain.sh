#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
NAME=gcc-linaro-7.4.1-2019.02-x86_64_arm-linux-gnueabi
ARCHIVE="$ROOT/downloads/toolchains/$NAME.tar.xz"
TOOLCHAIN="$ROOT/downloads/toolchains/$NAME"
URL="https://mirrors.tuna.tsinghua.edu.cn/armbian-releases/_toolchain/$NAME.tar.xz"
SHA256=42ccb2ed99d65b7090499e6f5ad65c4c94ae6bd022decfea102d50109557c7d2

mkdir -p "$(dirname "$ARCHIVE")"
if [[ ! -f "$ARCHIVE" ]]; then
    curl -fL --retry 3 "$URL" -o "$ARCHIVE"
fi
printf '%s  %s\n' "$SHA256" "$ARCHIVE" | sha256sum --check --status || {
    echo "Linaro U-Boot toolchain archive checksum mismatch: $ARCHIVE" >&2
    exit 1
}

if [[ ! -x "$TOOLCHAIN/bin/arm-linux-gnueabi-gcc" ]]; then
    tar -xJf "$ARCHIVE" -C "$(dirname "$ARCHIVE")"
fi

"$TOOLCHAIN/bin/arm-linux-gnueabi-gcc" --version | head -n 1
