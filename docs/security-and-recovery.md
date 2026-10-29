# Secure operation and recovery

The preview manages local operating-system accounts; it does not maintain a
second password database. Native account tooling and the installed system crypt
implementation verify/change passwords. No hashes are returned to the browser.
An account must be interactive to sign in; administrative operations additionally
require current wheel membership and a freshly verified password. The `airweb`
account has no interactive shell or unrestricted doas rule.

Sessions use random bearer tokens stored as hashes server-side in RAM, 15-minute
idle expiry and a one-hour absolute lifetime. Cookies are Secure, HttpOnly and
SameSite=Strict. Logout invalidates the server-side session. Mutations require
same-origin HTTPS, JSON, CSRF validation and backend authorization. Login attempts,
request sizes, handler threads, sessions, jobs, previews and audit history are
bounded. Audit records contain action/result metadata rather than request bodies,
passwords or tokens. Only bundled assets are served.

Fresh password authentication is required for user/password, save and partition
actions. The root helper accepts only fixed operations over its restricted Unix
socket, verifies the peer UID and rechecks account privileges. It exposes no
arbitrary command, file path or shell endpoint. It does not grant new users wheel
membership. There is no delete, disable or administrator-demotion endpoint that
could remove the last administrator.

HTTPS provisioning creates unique per-device certificate/key material only after
administrator provisioning. Default access uses SSH forwarding to loopback and
does not open a new nftables port. Verify the displayed certificate fingerprint
over authenticated SSH before entering a password. Browser testing with an
isolated test certificate is not a certificate trust or security certification.

## First login

Use a physical provisioning console on the supported board. Enter a new
administrator name, an Ed25519 public key and a local console/doas password;
type `SAVE` to explicitly persist identity. There are no shipped credentials.
After the provisioning program exits, console access uses authenticated getty.
Physical HDMI display output is still unverified; use the documented board UART
when available. Never assume a graphical setup screen or administrator autologin.

Connect with your private key using `ssh ADMIN@DEVICE_ADDRESS`; the administrator
password is for local login, Web Console authentication and doas, not SSH
password login. Confirm the device's SSH host fingerprint through a trusted
local/provisioning channel. Do not disable host-key checking to bypass a changed
identity after reflashing.

## Image update and recovery procedure

1. Export RAM-only validation/log data before stopping the device. Save only
   intended supported settings, then copy the selected state archive and recovery
   image into private storage. State includes credentials; never upload it.
2. Verify the replacement image and SHA-256 manifest from a trusted source. Keep
   the old bootable card/image intact. Prefer a separate spare SD for testing.
3. Shut down explicitly, then remove the card only after the system has stopped.
   Identify the exact removable target with `lsblk --bytes --output
   NAME,PATH,SIZE,MODEL,MOUNTPOINTS`; check its physical identity and capacity.
   Unmount its mounted partitions. Flashing destroys that target's contents.
4. Write the verified raw `.img` using a trusted image writer, explicitly selecting
   that device. Do not use a guessed `/dev/mmcblk` number or a partition node.
   Flush writes and verify the written bytes against the raw image before boot.
5. Provision the replacement or restore only a trusted compatible selected-state
   archive offline. Keep it private. Do not transplant shared host keys between
   distinct devices; restoring the same device's identity is a deliberate choice.
6. Cold boot, verify SSH identity/access, firewall, Python, runtime mounts and SD
   counters. Reboot once to verify explicit selected-state restoration. If boot
   or access fails, stop and return to the known-good card/image using the reader.

The Web Console replacement-card workflow automates this procedure for an
already running RAM-resident device. It is still a single-card, non-atomic
operation: interruption can leave the replacement unbootable, and success is
reported only after release-hash and full-media readback verification plus an
explicit selected-state save. Package-level `apk upgrade` remains unsupported;
packages are pinned and rebuilt into complete versioned images.
