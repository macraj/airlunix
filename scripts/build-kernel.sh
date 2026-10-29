#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
"$ROOT/scripts/prepare-sources.sh"
"$ROOT/scripts/prepare-kernel-toolchain.sh"

KERNEL="$ROOT/downloads/linux-orangepi"
BUILDER="$ROOT/downloads/orangepi-build"
OUT="$ROOT/build/kernel"
MODULES="$ROOT/output/kernel-modules"
TOOLCHAIN="$ROOT/downloads/toolchains/gcc-arm-11.2-2022.02-x86_64-aarch64-none-linux-gnu"
CROSS_COMPILE="$TOOLCHAIN/bin/aarch64-none-linux-gnu-"
CONFIG="$BUILDER/external/config/kernel/linux-sun60iw2-current-a733.config"
DTB=allwinner/sun60i-a733-orangepi-4-pro.dtb
JOBS=${JOBS:-$(nproc)}
LOCALVERSION=-sun60iw2

required=(make gcc perl python3 rsync bison flex openssl pahole)
for cmd in "${required[@]}"; do
    command -v "$cmd" >/dev/null || {
        echo "Missing host build tool: $cmd" >&2
        echo "See docs/building.md for the host dependency list." >&2
        exit 1
    }
done
if ! command -v bc >/dev/null && [[ -x "$ROOT/downloads/host-tools/bc/usr/bin/bc" ]]; then
    export PATH="$ROOT/downloads/host-tools/bc/usr/bin:$PATH"
fi
command -v bc >/dev/null || { echo "Missing host build tool: bc" >&2; exit 1; }

[[ -f "$CONFIG" ]] || { echo "Pinned vendor kernel config not found: $CONFIG" >&2; exit 1; }
mkdir -p "$OUT" "$ROOT/output/kernel/boot/dtb/allwinner" "$MODULES"
cp "$CONFIG" "$OUT/.config"
# This profile is for a headless server, not a general-purpose TV/media image.
# Disable vendor video-engine subtargets (their out-of-tree codec Makefile is
# absent) and broadcast-TV/radio/SDR support, which otherwise pulls in hundreds
# of unrelated DVB frontend and tuner modules from the vendor defconfig. The
# filter option exposes these Kconfig choices; without it hidden defaults force
# them back on even when the .config says "not set".
sed -i -E \
    -e 's/^CONFIG_AW_VIDEO_ENCODER_DECODER=.*/# CONFIG_AW_VIDEO_ENCODER_DECODER is not set/' \
    -e 's/^CONFIG_AW_VIDEO_KERNEL_ENC=.*/# CONFIG_AW_VIDEO_KERNEL_ENC is not set/' \
    -e 's/^CONFIG_AW_VIDEO_KERNEL_DEC=.*/# CONFIG_AW_VIDEO_KERNEL_DEC is not set/' \
    -e 's/^# CONFIG_MEDIA_SUPPORT_FILTER is not set$/CONFIG_MEDIA_SUPPORT_FILTER=y/' \
    -e 's/^CONFIG_MEDIA_SUPPORT_FILTER=.*/CONFIG_MEDIA_SUPPORT_FILTER=y/' \
    -e 's/^CONFIG_MEDIA_ANALOG_TV_SUPPORT=.*/CONFIG_MEDIA_ANALOG_TV_SUPPORT=n/' \
    -e 's/^CONFIG_MEDIA_DIGITAL_TV_SUPPORT=.*/CONFIG_MEDIA_DIGITAL_TV_SUPPORT=n/' \
    -e 's/^CONFIG_MEDIA_RADIO_SUPPORT=.*/CONFIG_MEDIA_RADIO_SUPPORT=n/' \
    -e 's/^CONFIG_MEDIA_SDR_SUPPORT=.*/CONFIG_MEDIA_SDR_SUPPORT=n/' \
    -e 's/^CONFIG_TOUCHSCREEN_GOODIX=.*/CONFIG_TOUCHSCREEN_GOODIX=n/' \
    "$OUT/.config"
python3 "$ROOT/scripts/apply-kernel-netfilter-profile.py" "$OUT/.config"

export KBUILD_BUILD_USER=alpine-builder
export KBUILD_BUILD_HOST=orangepi-4pro
export KBUILD_BUILD_TIMESTAMP="$(git -C "$KERNEL" show -s --format=%cI HEAD)"

make -C "$KERNEL" O="$OUT" ARCH=arm64 CROSS_COMPILE="$CROSS_COMPILE" \
    LOCALVERSION="$LOCALVERSION" olddefconfig

for option in CONFIG_AW_MMC=y CONFIG_MMC=y CONFIG_MSDOS_PARTITION=y \
    CONFIG_EXT4_FS=y CONFIG_MODULES=y CONFIG_BLK_DEV_INITRD=y; do
    if ! grep -qx "$option" "$OUT/.config"; then
        echo "Required boot config missing after olddefconfig: $option" >&2
        exit 1
    fi
done
for option in CONFIG_AW_VIDEO_ENCODER_DECODER CONFIG_AW_VIDEO_KERNEL_ENC CONFIG_AW_VIDEO_KERNEL_DEC; do
    if grep -qx "${option}=y" "$OUT/.config" || grep -qx "${option}=m" "$OUT/.config"; then
        echo "Headless profile unexpectedly enables $option" >&2
        exit 1
    fi
done
if grep -Eq '^CONFIG_TOUCHSCREEN_GOODIX=(y|m)$' "$OUT/.config"; then
    echo "Headless profile unexpectedly enables the Goodix touchscreen driver" >&2
    exit 1
fi
for option in CONFIG_MEDIA_ANALOG_TV_SUPPORT CONFIG_MEDIA_DIGITAL_TV_SUPPORT \
    CONFIG_MEDIA_RADIO_SUPPORT CONFIG_MEDIA_SDR_SUPPORT CONFIG_DVB_CORE CONFIG_MEDIA_TUNER; do
    if grep -Eq "^${option}=(y|m)$" "$OUT/.config"; then
        echo "Headless profile unexpectedly enables broadcast/media tuner option $option" >&2
        exit 1
    fi
done
for option in CONFIG_NETFILTER_XTABLES CONFIG_NETFILTER_XTABLES_COMPAT \
    CONFIG_BRIDGE_NETFILTER CONFIG_NF_NAT CONFIG_NF_TABLES_BRIDGE CONFIG_NF_TABLES_NETDEV \
    CONFIG_NF_FLOW_TABLE CONFIG_IP_SET CONFIG_IP_VS CONFIG_NFT_COMPAT CONFIG_NFT_NAT \
    CONFIG_NFT_MASQ CONFIG_NFT_REDIR CONFIG_NFT_QUEUE CONFIG_NFT_TUNNEL CONFIG_NFT_QUOTA \
    CONFIG_NFT_SOCKET CONFIG_NFT_OSF CONFIG_NFT_TPROXY CONFIG_NFT_SYNPROXY CONFIG_NF_CT_NETLINK; do
    if grep -Eq "^${option}=(y|m)$" "$OUT/.config"; then
        echo "Host-firewall profile unexpectedly enables optional/legacy Netfilter feature $option" >&2
        exit 1
    fi
done
for option in CONFIG_NETFILTER=y CONFIG_NF_TABLES=m CONFIG_NF_TABLES_INET=y \
    CONFIG_NF_CONNTRACK=m CONFIG_NFT_CT=m CONFIG_NFT_LOG=m CONFIG_NFT_LIMIT=m CONFIG_NFT_REJECT=m; do
    if ! grep -qx "$option" "$OUT/.config"; then
        echo "Required nftables host-firewall option missing: $option" >&2
        exit 1
    fi
done

# olddefconfig writes .config; syncconfig materializes auto.conf/autoconf.h.
make -C "$KERNEL" O="$OUT" ARCH=arm64 CROSS_COMPILE="$CROSS_COMPILE" \
    LOCALVERSION="$LOCALVERSION" syncconfig
for generated in "$OUT/include/config/auto.conf" \
    "$OUT/include/generated/autoconf.h" "$OUT/include/generated/rustc_cfg"; do
    [[ -s "$generated" ]] || { echo "Kconfig output missing: $generated" >&2; exit 1; }
done

# The pinned vendor tree's syncconfig restart loop persists on GNU Make 4.4
# even with the grouped-target fix. syncconfig above has materialized the headers,
# so suppress only the redundant automatic sync step during compilation.
make -C "$KERNEL" O="$OUT" ARCH=arm64 CROSS_COMPILE="$CROSS_COMPILE" \
    LOCALVERSION="$LOCALVERSION" may-sync-config= -j"$JOBS" Image modules dtbs

[[ -s "$OUT/arch/arm64/boot/Image" ]] || { echo "Kernel Image was not produced" >&2; exit 1; }
[[ -s "$OUT/arch/arm64/boot/dts/$DTB" ]] || { echo "Board DTB was not produced: $DTB" >&2; exit 1; }

KERNEL_RELEASE=$(make -s -C "$KERNEL" O="$OUT" ARCH=arm64 \
    CROSS_COMPILE="$CROSS_COMPILE" LOCALVERSION="$LOCALVERSION" kernelrelease)
make -C "$KERNEL" O="$OUT" ARCH=arm64 CROSS_COMPILE="$CROSS_COMPILE" \
    LOCALVERSION="$LOCALVERSION" INSTALL_MOD_PATH="$MODULES" modules_install

install -m 0644 "$OUT/arch/arm64/boot/Image" "$ROOT/output/kernel/boot/Image"
install -m 0644 "$OUT/arch/arm64/boot/dts/$DTB" \
    "$ROOT/output/kernel/boot/dtb/allwinner/$(basename "$DTB")"
install -m 0644 "$OUT/.config" "$ROOT/output/kernel/kernel.config"
printf '%s\n' "$KERNEL_RELEASE" > "$ROOT/output/kernel/kernel.release"
cat > "$ROOT/output/kernel/build-info.txt" <<EOF
Kernel source: $(git -C "$KERNEL" rev-parse HEAD)
Build system: $(git -C "$BUILDER" rev-parse HEAD)
Local Kbuild patch SHA256: $(sha256sum "$ROOT/patches/linux-orangepi-kbuild-make43.patch" | cut -d' ' -f1)
Kernel release: $KERNEL_RELEASE
Cross compiler: $(${CROSS_COMPILE}gcc -dumpfullversion)
DTB: $DTB
Profile: headless server (TV/radio/SDR and legacy/NAT Netfilter removed; nftables host firewall retained)
EOF

echo "Kernel build complete: $KERNEL_RELEASE"
echo "Artifacts: $ROOT/output/kernel"
echo "Modules:   $MODULES/lib/modules/$KERNEL_RELEASE"
