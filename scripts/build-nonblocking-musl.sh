#!/usr/bin/env bash
# Existing musl dependency, same 1.2.6 release; only syslog socket is nonblocking.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
PARENT=$(cd "$ROOT/../../.." && pwd)
SOURCE="$PARENT/output/release-materials/airlunix-0.3.0/alpine-distfiles/musl-1.2.6.tar.gz"
STAGE="$ROOT/build/musl-nonblocking"
echo "d585fd3b613c66151fc3249e8ed44f77020cb5e6c1e635a616d3f9f82460512a  $SOURCE" | sha256sum -c -
mkdir -p "$STAGE"
if [[ ! -d "$STAGE/src" ]]; then
    mkdir "$STAGE/src"
    tar -xzf "$SOURCE" --strip-components=1 -C "$STAGE/src"
    patch -d "$STAGE/src" -p1 < "$ROOT/patches/musl-nonblocking-syslog.patch"
fi
cd "$STAGE"
CC="$PARENT/downloads/toolchains/gcc-arm-11.2-2022.02-x86_64-aarch64-none-linux-gnu/bin/aarch64-none-linux-gnu-gcc" \
    CFLAGS='-Os' ./src/configure --target=aarch64-linux-musl --prefix=/usr --syslibdir=/lib >configure.log
make -j4 AR="$PARENT/downloads/toolchains/gcc-arm-11.2-2022.02-x86_64-aarch64-none-linux-gnu/bin/aarch64-none-linux-gnu-ar" RANLIB="$PARENT/downloads/toolchains/gcc-arm-11.2-2022.02-x86_64-aarch64-none-linux-gnu/bin/aarch64-none-linux-gnu-ranlib" >build.log 2>&1
"$PARENT/downloads/toolchains/gcc-arm-11.2-2022.02-x86_64-aarch64-none-linux-gnu/bin/aarch64-none-linux-gnu-strip" --strip-unneeded lib/libc.so
sha256sum lib/libc.so
