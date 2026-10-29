# Airlunix — Headless Server

**Runs in RAM. Persists by choice.**

Airlunix is a compact Linux distribution for servers and embedded experiments
on the **Orange Pi 4 Pro, Allwinner A733, AArch64**. It uses Alpine Linux
userspace, OpenRC, BusyBox, OpenSSH, nftables and an Orange Pi vendor Linux
kernel and boot chain. It does not support every Orange Pi board.

Version **0.3.0 developer preview** is being prepared. It is not a production
stability claim. Binary publication is held pending component redistribution
verification and release approval. No trademark registration or clearance is
claimed.

The requested image release is separate from the source preview. The existing
candidate has been delivered privately and verified on a 2 GB SD card; physical
board boot remains pending. See the [exact image publication dependencies and
completed source-material work](docs/image-publication-blockers.md).

## Runtime architecture

U-Boot loads the kernel and a complete compressed initramfs. The kernel unpacks
the operating system, executables, libraries, Python and modules into RAM.
Early boot mounts the SD partition read-only with journal replay disabled,
restores explicitly selected state, captures a storage snapshot and unmounts it.
This is a complete RAM root, rather than an SD-backed read-only root with an
overlay. Boot needs the SD; normal operation is intended to need no further SD
reads or writes. Explicit save and partition operations access the SD.

Changes to the running system disappear at reboot unless they are supported by
the persistence allowlist and explicitly saved. There is no shutdown save.
`doas airlunix-state save` saves identity, accounts/passwords, administrator
authorized keys and selected configuration/data. Package installations are RAM
changes; build packages into a new image for reproducible updates.

## Secure first access

The generic image has no personal accounts, default password, authorized keys,
SSH host private keys or shared TLS private key. Provision an administrator
locally on the supported serial console or authenticated provisioning console;
choose a password and public key. Each device generates its own SSH identity.
Provisioning saves identity explicitly. Public-key SSH disables root, password
and keyboard-interactive login; administrator elevation requires a password.
Normal users created in the console are not administrators and receive no
automatic SSH authorized key.

After provisioning, use authenticated SSH and run `doas airlunix-web-setup`.
Verify the displayed TLS fingerprint through SSH. Start the helper and console
as directed, then forward `ssh -L 8443:127.0.0.1:8443 ADMIN@DEVICE` and open
`https://127.0.0.1:8443`. HTTPS binds loopback by default. Setup does not open a
firewall port or enable WAN management. Save configuration explicitly to retain
the per-device certificate and settings.

## Web Console

The locally bundled console provides Overview, Storage, Users, System and Logs.
It uses no CDN, analytics, desktop or container stack. Monitoring history is
bounded in RAM and sampled only on demand, shared across browser tabs. The
HTTPS process runs as `airweb`; a separate narrow helper verifies passwords and
performs allowlisted administration. A compromised session alone is insufficient
for sensitive operations: fresh system-password authentication is required.

Configuration changes apply in RAM. “Save current configuration to SD” is an
explicit separate operation. Partition changes are durable immediately, including
when a later filesystem operation fails. They cannot be undone by rebooting.
Only guarded expansion of the supported persistence partition or creation of
a new primary ext4 volume in suitable free space is supported. There is no
shrink, delete, move or format-existing-volume API. See
[storage policy](docs/storage.md).

The Storage page can also prepare a replacement microSD while the system keeps
running from RAM. It accepts only the official `macraj/airlunix` GitHub Release
manifest for Orange Pi 4 Pro/A733, downloads the `.img.xz` directly on the
device, decompresses with bounded memory, verifies the compressed and raw
SHA-256 plus a full media readback, and then saves current selected state. It
requires fresh administrator authentication and exact physical-card confirmation.
No browser upload or arbitrary URL is accepted.

## Included capabilities and limits

- Ethernet DHCP, OpenSSH and nftables with default-deny inbound policy except
  configured SSH, required DHCP and ICMP. IPv6 firewall validation remains pending.
- Python **3.14.10**, standard library, SSL, pip and venv are intended offline
  image requirements. New artifact interpreter tests must pass before release.
  pip does not imply an offline collection of every third-party wheel.
- Existing Chrony in bounded one-shot mode, initial networking attempt, daily
  resync after success and bounded failure backoff. No resident NTP client.
  LAN readiness and trusted time are separate; daily steps are not continuous
  frequency discipline or a proven accuracy guarantee.
- Optional A733 NPU support remains in scope. The source-built driver and target
  runtime are separate components. Public target-runtime redistribution rights
  remain unverified; private working support is preserved.

## Build, validation and recovery

Build and image/source evidence are described in [building](docs/building.md).
Verify published SHA-256 files before flashing. Select the actual removable
target with `lsblk`; flashing overwrites that device. No published download is
available yet. The release image must be at most **1,000,000,000 bytes** raw;
compression and sparse allocation are not substitutes for that limit.

The previous base was tested on a 4 GB board. The new console image's minimum
RAM, cold boot, physical HDMI and board resource measurements are pending.
Disk size and RAM consumption are different measurements. Do not infer minimum
memory or a safe SD removal procedure from the image size.

Keep an offline known-good recovery image and a copy of explicitly selected
state. Updates replace the boot/runtime artifact through a controlled procedure;
do not overwrite live storage from a guessed device path. Acceptance and current
limits are in [release notes](docs/release-notes.md).
