#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
if [[ ${OPI_BUILD_UIDMAP:-} != yes ]]; then
    exec scripts/with-build-userns.sh bash "$0"
fi
sha256sum -c configs/airlunix-apks.sha256
sha256sum -c configs/airlunix-rootfs-input.sha256
sha256sum -c configs/airlunix-board-artifacts.sha256
mapfile -t APK_INPUTS < <(awk '{print $2}' configs/airlunix-apks.sha256)
mapfile -t DIST < <(python3 - <<'PY'
import json
c = json.load(open('configs/distribution.json'))
for key in ('id', 'version', 'profile', 'image_bytes', 'source_date_epoch'):
    print(str(c[key]).lower().replace(' ', '-') if key == 'profile' else c[key])
PY
)
IMAGE_BYTES=${DIST[3]}
mkdir -p build output/images
(( IMAGE_BYTES <= 1000000000 && IMAGE_BYTES % 512 == 0 && IMAGE_BYTES > 268435456 ))
PART_BYTES=$((IMAGE_BYTES - 33554432))
STAGE=$(mktemp -d "$ROOT/build/airlunix-build.XXXXXX")
echo "Build workspace: $STAGE"
mkdir -p "$STAGE/rootfs"
tar -xpf build/airlunix/rootfs-input.tar -C "$STAGE/rootfs"
downloads/host-tools/apk-static/sbin/apk.static --root "$STAGE/rootfs" \
    --arch aarch64 --no-network --no-scripts add "${APK_INPUTS[@]}"
downloads/host-tools/apk-static/sbin/apk.static --root "$STAGE/rootfs" info -v \
    > "$STAGE/rootfs/etc/airlunix-packages.lock"
python3 scripts/configure-rootfs.py "$STAGE/rootfs"
# Boot files are consumed by U-Boot, not part of the runtime RAM archive.
if [[ -d "$STAGE/rootfs/boot" ]]; then mv "$STAGE/rootfs/boot" "$STAGE/runtime-old-boot"; fi
mkdir -p "$STAGE/rootfs/boot"
mkdir -p "$STAGE/media/boot/dtb/allwinner/overlay"
cp output/kernel/boot/dtb/allwinner/sun60i-a733-orangepi-4-pro.dtb "$STAGE/media/boot/dtb/allwinner/"
cp build/kernel/arch/arm64/boot/dts/allwinner/overlay/sun60i-a733-uart7.dtbo "$STAGE/media/boot/dtb/allwinner/overlay/"
export SOURCE_DATE_EPOCH=${DIST[4]}
find "$STAGE/rootfs" -exec touch -h -d "@$SOURCE_DATE_EPOCH" {} +
(cd "$STAGE/rootfs" && find . -print0 | LC_ALL=C sort -z |
    cpio --null -o --format=newc --reproducible --quiet | gzip -n -9) > "$STAGE/runtime.cpio.gz"
MKIMAGE="$ROOT/output/uboot/mkimage"
"$MKIMAGE" -A arm -O linux -T ramdisk -C gzip -a 0x4fe00000 -e 0x4fe00000 \
    -n 'Airlunix RAM runtime' -d "$STAGE/runtime.cpio.gz" "$STAGE/media/boot/uInitrd"
"$MKIMAGE" -A arm -O linux -T kernel -C none -a 0x40080000 -e 0x40080000 \
    -n 'Airlunix A733' -d output/kernel/boot/Image "$STAGE/media/boot/uImage"
cp downloads/boot-sun60iw2.cmd "$STAGE/media/boot/boot.cmd"
sed -i -e 's/console=ttyS0,115200/console=ttyS7,115200/' \
    -e 's/swiotlb=65536/swiotlb=16384/' \
    -e 's/root=${rootdev} rootwait rootfstype=${rootfstype}/rdinit=\/init airlunix.ram=1/' \
    "$STAGE/media/boot/boot.cmd"
# Explicit addresses avoid the vendor 32-bit U-Boot's alternate defaults.
sed -i '1i setenv kernel_addr_r 0x40080000\nsetenv fdt_addr_r 0x4fa00000\nsetenv ramdisk_addr_r 0x4fe00000\nsetenv bootm_size 0x30000000' "$STAGE/media/boot/boot.cmd"
printf '%s\n' 'console=serial' 'verbosity=4' 'earlycon=off' 'overlays=uart7' \
    'overlay_prefix=sun60i-a733' 'fdtfile=allwinner/sun60i-a733-orangepi-4-pro.dtb' \
    > "$STAGE/media/boot/orangepiEnv.txt"
"$MKIMAGE" -A arm -T script -C none -n 'Airlunix RAM boot' \
    -d "$STAGE/media/boot/boot.cmd" "$STAGE/media/boot/boot.scr"
touch "$STAGE/media/airlunix-media"
find "$STAGE/media" -exec touch -h -d "@$SOURCE_DATE_EPOCH" {} +
truncate -s "$PART_BYTES" "$STAGE/media.ext4"
export E2FSPROGS_FAKE_TIME=$SOURCE_DATE_EPOCH
mke2fs -q -F -t ext4 -m 0 -L airlunix-state -U 71d094ae-0ef4-4d21-8553-85a4baae0300 \
    -E hash_seed=71d094ae-0ef4-4d21-8553-85a4baae0300,lazy_itable_init=0,lazy_journal_init=0 \
    -O '^64bit,^metadata_csum,^orphan_file' -d "$STAGE/media" "$STAGE/media.ext4"
e2fsck -fn "$STAGE/media.ext4"
IMAGE="$ROOT/output/images/${DIST[0]}-${DIST[1]}-${DIST[2]}-a733.img"
[[ ! -e "$IMAGE" ]] || { echo "Refusing overwrite: $IMAGE" >&2; exit 1; }
truncate -s "$IMAGE_BYTES" "$IMAGE"
printf 'label: dos\nlabel-id: 0xa7eb0300\nunit: sectors\n\nstart=65536,size=%s,type=83,bootable\n' "$((PART_BYTES / 512))" | sfdisk "$IMAGE" >/dev/null
dd if=output/uboot/boot0_sdcard.fex of="$IMAGE" bs=8192 seek=1 conv=notrunc status=none
dd if=output/uboot/boot_package.fex of="$IMAGE" bs=8192 seek=2050 conv=notrunc status=none
dd if="$STAGE/media.ext4" of="$IMAGE" bs=4M seek=8 conv=notrunc status=none
[[ $(stat -c %s "$IMAGE") -le 1000000000 ]]
(cd output/images && sha256sum "$(basename "$IMAGE")" > "$(basename "$IMAGE").sha256")
cp "$STAGE/runtime.cpio.gz" "output/images/${DIST[0]}-${DIST[1]}-runtime.cpio.gz"
echo "Image: $IMAGE; runtime root: $STAGE/rootfs"
