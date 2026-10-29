#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
"$ROOT/scripts/prepare-sources.sh"
"$ROOT/scripts/prepare-uboot-toolchain.sh"

UBOOT="$ROOT/downloads/u-boot-orangepi"
BUILDER="$ROOT/downloads/orangepi-build"
PACK_SRC="$BUILDER/external/packages/pack-uboot/sun60iw2/bin"
PACK_TOOLS="$BUILDER/external/packages/pack-uboot/tools"
KERNEL_DTC="$ROOT/build/kernel/scripts/dtc/dtc"
OUT="$ROOT/build/uboot"
TOOLCHAIN="$ROOT/downloads/toolchains/gcc-linaro-7.4.1-2019.02-x86_64_arm-linux-gnueabi"
CROSS_COMPILE="$TOOLCHAIN/bin/arm-linux-gnueabi-"
JOBS=${JOBS:-$(nproc)}

for cmd in make gcc python3; do
    command -v "$cmd" >/dev/null || { echo "Missing host tool: $cmd" >&2; exit 1; }
done
[[ -x "$PACK_TOOLS/dragonsecboot" && -x "$PACK_TOOLS/update_uboot" && -x "$PACK_TOOLS/dtc" ]] || {
    echo "Orange Pi A733 boot-package tools are missing." >&2
    exit 1
}
[[ -x "$KERNEL_DTC" ]] || { echo "Build and validate the Linux kernel first; its host DTC is required." >&2; exit 1; }

mkdir -p "$OUT"
mkdir -p "$OUT/board/sunxi"
mkdir -p "$OUT/scripts/dtc"
if [[ -L "$OUT/scripts/dtc/dtc" ]]; then
    current_dtc=$(readlink -f "$OUT/scripts/dtc/dtc")
    if [[ "$current_dtc" == "$(readlink -f "$PACK_TOOLS/dtc")" ]]; then
        rm -f "$OUT/scripts/dtc/dtc"
    elif [[ "$current_dtc" != "$(readlink -f "$KERNEL_DTC")" ]]; then
        echo "Unexpected DTC symlink in U-Boot output: $current_dtc" >&2
        exit 1
    fi
fi
if [[ ! -e "$OUT/scripts/dtc/dtc" ]]; then
    ln -s "$KERNEL_DTC" "$OUT/scripts/dtc/dtc"
fi
if [[ -e "$OUT/configs" ]]; then
    if [[ ! -L "$OUT/configs" || "$(readlink -f "$OUT/configs")" != "$(readlink -f "$UBOOT/configs")" ]]; then
        echo "Unexpected existing U-Boot output configs path: $OUT/configs" >&2
        exit 1
    fi
else
    ln -s "$UBOOT/configs" "$OUT/configs"
fi
HOST_TOOLS="$ROOT/scripts/host-tools"
chmod 0755 "$HOST_TOOLS/xxd"
LOCAL_BC="$ROOT/downloads/host-tools/bc/usr/bin"
[[ -x "$LOCAL_BC/bc" ]] && HOST_TOOLS="$HOST_TOOLS:$LOCAL_BC"
PATH="$HOST_TOOLS:$PATH"
command -v bc >/dev/null || { echo "Missing host tool: bc" >&2; exit 1; }
mkdir -p "$OUT/scripts"
if [[ -e "$OUT/scripts/sunxi_ubootools" ]]; then
    if [[ ! -L "$OUT/scripts/sunxi_ubootools" || \
        "$(readlink -f "$OUT/scripts/sunxi_ubootools")" != "$(readlink -f "$UBOOT/scripts/sunxi_ubootools")" ]]; then
        echo "Unexpected existing sunxi_ubootools in U-Boot output." >&2
        exit 1
    fi
else
    ln -s "$UBOOT/scripts/sunxi_ubootools" "$OUT/scripts/sunxi_ubootools"
fi

# The vendor Makefile copies extra convenience binaries after linking. Keep
# those optional copies inside this project's ignored build tree, never /bin or /.
LICHEE_STAGE="$OUT/staging"
mkdir -p "$LICHEE_STAGE/chip-config/alpine-build/bin" "$LICHEE_STAGE/platform"

make -C "$UBOOT" O="$OUT" ARCH=arm CROSS_COMPILE="$CROSS_COMPILE" \
    sun60iw2p1_t736_defconfig

# Match the board-support script's U-Boot environment, while making the edit
# only in the ignored out-of-tree build directory.
sed -i 's/^CONFIG_LOCALVERSION=""$/CONFIG_LOCALVERSION="-orangepi"/' "$OUT/.config"
sed -i 's/^# CONFIG_LOCALVERSION_AUTO is not set$/# CONFIG_LOCALVERSION_AUTO is not set/' "$OUT/.config"
sed -i 's/^CONFIG_BOOTDELAY=.*/CONFIG_BOOTDELAY=1/' "$OUT/.config"
grep -q '^CONFIG_BOOTDELAY=' "$OUT/.config" || echo 'CONFIG_BOOTDELAY=1' >> "$OUT/.config"
grep -q '^CONFIG_ENV_IS_IN_EXT4=y$' "$OUT/.config" || {
    echo "Pinned U-Boot defconfig does not enable the expected ext4 environment." >&2
    exit 1
}
sed -i '/^CONFIG_ENV_EXT4_INTERFACE=/d; /^CONFIG_ENV_EXT4_DEVICE_AND_PART=/d; /^CONFIG_ENV_EXT4_FILE=/d' "$OUT/.config"
cat >> "$OUT/.config" <<'EOF'
CONFIG_ENV_EXT4_INTERFACE="mmc"
CONFIG_ENV_EXT4_DEVICE_AND_PART="0:auto"
CONFIG_ENV_EXT4_FILE="/boot/boot.env"
EOF
make -C "$UBOOT" O="$OUT" ARCH=arm CROSS_COMPILE="$CROSS_COMPILE" olddefconfig
PATH="$HOST_TOOLS:$PATH" make -C "$UBOOT" O="$OUT" ARCH=arm CROSS_COMPILE="$CROSS_COMPILE" \
    LICHEE_CHIP_CONFIG_DIR="$LICHEE_STAGE/chip-config" \
    LICHEE_BUSSINESS=alpine-build LICHEE_PLAT_OUT="$LICHEE_STAGE/platform" \
    -j"$JOBS" all tools

[[ -s "$OUT/u-boot.bin" ]] || { echo "U-Boot binary was not produced" >&2; exit 1; }
[[ -x "$OUT/tools/mkimage" ]] || { echo "U-Boot mkimage was not produced" >&2; exit 1; }
[[ ! -e "$ROOT/output/uboot" ]] || {
    echo "Refusing to overwrite existing U-Boot artifacts: $ROOT/output/uboot" >&2
    echo "Move the existing artifacts aside after inspecting them, then rerun." >&2
    exit 1
}

# Re-create the board's Allwinner package using the pinned vendor packer assets.
PKG=$(mktemp -d "$OUT/package.XXXXXX")
mkdir -p "$ROOT/output"
OUTPUT_STAGE=$(mktemp -d "$ROOT/output/.uboot.XXXXXX")
cleanup() {
    rm -rf -- "$PKG"
    [[ -z "${OUTPUT_STAGE:-}" ]] || rm -rf -- "$OUTPUT_STAGE"
}
trap cleanup EXIT HUP INT TERM
cp -a "$PACK_SRC/." "$PKG/"
cp "$OUT/u-boot.bin" "$PKG/u-boot.fex"
cp "$PKG/sys_config/sys_config.fex" "$PKG/sys_config.fex"
cp "$PKG/dts/u-boot-current.dts" "$PKG/dts/orangepi4pro-u-boot.dts"

python3 - "$PKG/sys_config.fex" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
data = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
path.write_bytes(data.replace(b"\n", b"\r\n"))
PY

(cd "$PKG" && \
    "$PACK_TOOLS/dtc" -p 2048 -W no-unit_address_vs_reg -@ -O dtb \
        -o orangepi4pro-u-boot.dtb -b 0 dts/u-boot-current.dts && \
    cp orangepi4pro-u-boot.dtb sunxi.fex && \
    "$PACK_TOOLS/update_dtb" sunxi.fex 4096 && \
    "$PACK_TOOLS/script" sys_config.fex && \
    "$PACK_TOOLS/update_uboot" -no_merge u-boot.fex sys_config.bin && \
    "$PACK_TOOLS/dragonsecboot" -pack boot_package.cfg)

[[ -s "$PKG/boot_package.fex" ]] || { echo "Allwinner boot package was not produced" >&2; exit 1; }
install -m 0644 "$PKG/boot0_sdcard_a733.fex" "$OUTPUT_STAGE/boot0_sdcard.fex"
install -m 0644 "$PKG/boot_package.fex" "$OUTPUT_STAGE/boot_package.fex"
install -m 0644 "$PKG/u-boot.fex" "$OUTPUT_STAGE/u-boot.fex"
install -m 0755 "$OUT/tools/mkimage" "$OUTPUT_STAGE/mkimage"
cat > "$OUTPUT_STAGE/build-info.txt" <<EOF
U-Boot source: $(git -C "$UBOOT" rev-parse HEAD)
Build system: $(git -C "$BUILDER" rev-parse HEAD)
Defconfig: sun60iw2p1_t736_defconfig
Cross compiler: $(${CROSS_COMPILE}gcc -dumpfullversion)
SD boot0: boot0_sdcard_a733.fex (vendor-provided binary)
EOF

mv "$OUTPUT_STAGE" "$ROOT/output/uboot"
OUTPUT_STAGE=""
echo "U-Boot artifacts: $ROOT/output/uboot"
