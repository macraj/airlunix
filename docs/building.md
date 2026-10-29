# Building and validation

This is a shell/Python image assembly project using pinned Orange Pi vendor
kernel/U-Boot sources and Alpine APK inputs. It is not Buildroot or Yocto.
`configs/baseline.lock`, `configs/alpine.lock` and SHA-256 input manifests record
the selected inputs. Public bootstrap/source-closure preparation remains in
progress; a private rootfs snapshot is not a distributable build dependency.

The assembly entry point is `scripts/build-image.sh`. It uses the subordinate
UID/GID namespace wrapper, verifies input hashes, configures a generic rootfs,
constructs the complete cpio runtime and writes a regular-file image. It never
selects or flashes a physical disk. `scripts/validate-image.py IMAGE` verifies
the MBR, boot CRCs, initramfs contents and exclusion of device credentials.

Run `python3 -m unittest discover -s tests -v` for host-isolated tests. Filesystem
tests require e2fsprogs and use temporary regular files. No host account or block
device is changed. Browser QA uses a separate temporary test fixture and real
host telemetry; fixtures are not installed in the distribution.

Release preparation must record exact source revision and all locked input
hashes, package inventory, source/licence materials, raw/compressed sizes and
checksums. A fresh build is not accepted merely because an older board image
booted. No raw image, source compliance or minimum RAM result is asserted here
before the corresponding validation completes.
