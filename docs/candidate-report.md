# Final private candidate report — 2026-10-29

**Airlunix 0.3.0, Headless Server — developer preview candidate. Not accepted,
not cleared for publication, not deployed.**

## Artifacts and source identity

| Artifact | Exact bytes | MiB | SHA-256 |
| --- | ---: | ---: | --- |
| `airlunix-0.3.0-headless-server-a733.img` | 805306368 | 768 | `718af92d55d98a7826e11f7cb119f38a6bd7e951f8ce143bf5de41a839108972` |
| `airlunix-0.3.0-headless-server-a733.img.xz` | 65678972 | 62.6363487244 | `502c4567ffb32cfbec494d5632f37c229198d3f4caecb05dc4f8bed3d6c4582f` |

Compression: XZ, `xz -T2 -6 -k`. Integrity/decompression verified against the
complete raw-image hash. The raw file is below the stricter decimal
1,000,000,000-byte limit. Compared with the earlier base using identical XZ
settings, raw image size is unchanged and compressed size increases 570716 bytes.
This delta includes dependencies and package updates, not only Web Console code.

Build-source revision: `d8b88a3b017a9db1795f687ff666f3eaf14ca253`.
Build identifier: `9a51c51c0bf8a03b`. The source files entering the build digest
match that committed revision; console code/assets match their runtime cpio
contents. Recording is retrospective, not a signed at-build attestation.
[Provenance](candidate-provenance.json) records every checked input hash,
source/runtime matches, package count and limitations. A
[77-package CycloneDX inventory](candidate-sbom.cdx.json) is included; it is not
proof of complete licence/source compliance.

The standalone repository is local only; no remote, push, public repository or
release exists. Proposed target remains public `macraj/airlunix`, subject to the
publication gate. Proposed preview tag: `v0.3.0-devpreview`; no tag published.
The private repository's history has not been mirrored.

The build still uses a locked historical rootfs input and prebuilt board
artifacts. Public clean-bootstrap reconstruction and complete independently
verified source-to-binary provenance remain incomplete. Do not upload that
private input snapshot or call this a clean, fully reproducible public build.

## Storage and runtime size

DOS/MBR, 512-byte sectors; 32 MiB reserved boot area. Bootable Linux partition 1
starts at sector 65536, length 1507328 sectors / 771751936 bytes (736 MiB),
ext4 label `airlunix-state`. Filesystem: 188416 blocks of 4096 bytes; 27373 used
(112119808 bytes), 161043 free (659632128 bytes). No automatic expansion.
Media must expose at least 805306368 bytes; the physical minimum-card test is
pending. New-image minimum RAM and boot/runtime RAM consumption are unmeasured.

Complete runtime cpio is 174730240 bytes; gzip runtime is 57290922 bytes.
The largest individual runtime files include the AIC8800 module (14858072),
nf_tables module (11696128), VIN module (7156048), conntrack module (5604440),
libpython (5361888) and vipcore module (4722448). No capability was removed
solely to meet the image-size limit.

## Console implementation and verification

Included: responsive Overview/Storage/Users/System/Logs; shared on-demand bounded
RAM telemetry; explicit selected save with dirty-state and result reporting;
current-password change; normal-user creation/listing; authenticated storage
previews and guarded expand/create workflows. No administrator promotion,
delete/shrink/move or generic shell/file-write interface exists.

HTTPS runs as `airweb`; a root helper handles fixed allowlisted operations with
fresh authentication. Per-device TLS setup is explicit and defaults to an SSH
tunnel to loopback. Backend roles, CSRF/origin checks, secure cookies, session
expiry/logout, throttling, bounded resources and RAM-only audit records are
implemented. New users receive no wheel access; no blanket nopass rule is added.

Twenty-three host-isolated tests passed: fifteen console/backend/storage tests
and eight inherited NTP lifecycle tests. These cover session expiry/logout,
HTTPS authorization/CSRF/origin/cookie flags, fresh-password checks, normal-user
boundaries, input rejection, unsupported privileged APIs, login throttling,
bounded logs, dirty-state restart tracking, save/unmount failure, storage locking,
preview expiry/confirmation/replay, stale/unsafe layouts, actual disposable ext4
create/expand, preserved boot regions and filesystem-only resize resumption.

Browser checks passed at 1440×1100 and 390×844: navigation, dialog Escape,
unavailable storage state, no horizontal mobile overflow and no JavaScript
exceptions. Screenshots show the actual running interface with real privacy-
filtered x86 host telemetry and a test-only authentication backend, not Orange Pi
measurements: [desktop](screenshots/overview-desktop.png),
[mobile](screenshots/overview-mobile.png),
[unavailable storage](screenshots/storage-unavailable.png).

[Measured host resources](console-host-resources.json): 10.011 s idle, 0.0% CPU,
29024256 bytes RSS; 10.392 s with five concurrent clients, 100 requests,
five shared samples, 1.732% of one core, peak sampled RSS 29413376 bytes.
Process-attributed storage write delta was zero in both phases. The privileged
production helper is not included in those fixture resource measurements.
These are short host measurements, not board SD-I/O or 24-hour results.

## This candidate's Python and NPU results

[Final candidate target results](candidate-target-runtime.json), run in its own
disposable AArch64 rootfs under emulation: Python 3.14.10; OpenSSL 3.5.9;
system pip 26.1.2; freshly created pip-enabled venv with bundled pip 26.2.2;
package indexes disabled, no download. Console module imports pass. The 2136
Python-related image files compared against the tested rootfs match byte-for-byte.
Earlier-image emulation results are separate and are not used as this result.

Real Alpine account creation/password verification, normal-account privilege
rejection, selected account-database restoration and `airweb` doas rejection
passed in an earlier disposable staged rootfs containing the identical console
account implementation. This is not a final-image physical reboot restoration
test. Actual save-to-SD and restoration through a cold boot remain pending.

| NPU component included | Individual validation | Redistribution state |
| --- | --- | --- |
| `vipcore.ko` | Presence/hash; `modinfo` confirms Dual MIT/GPL; no hardware execution on this candidate | Declared source licence; corresponding-source closure pending |
| `libVIPhal.so` | Exact Orange Pi hash; AArch64 loader succeeds | Rights unverified; no exact comparison-SDK binary match |
| `libNBGlinker.so` | Exact Orange Pi hash; AArch64 loader succeeds | Rights unverified; no exact comparison-SDK binary match |
| `opi-vpm-run` | Exact vendor executable hash retained | Rights unverified; no new hardware execution result |
| `network_binary.nb` | Exact vendor/SDK sample hash; graph identifier `ShuffleNetV2_uint8_NCHW` | Weight/model grant and source checkpoint unverified |
| `input_0.dat` | Exact vendor/SDK sample hash | Sample-data grant unverified |

Presence and library loading are not inference, driver compatibility or accuracy
proof. [Per-file comparison](npu-upstream-comparison.md) separates the common
header's dual MIT/GPL grant, the restrictive adjacent header and TIM-VX's MIT
licence. None is extended to these exact runtime binaries. NPU remains in scope;
private working support is preserved. The [permission request](npu-permission-request.md)
is prepared and **not sent**.

## Publication blockers and concrete next actions

| Affected component / requirement | Missing evidence or material | Next action |
| --- | --- | --- |
| Exact `libVIPhal.so`, `libNBGlinker.so`, `vpm_run` | Applicable redistribution grant/EULA | Submit prepared hash-specific request to Orange Pi/Xunlong; obtain authorized Allwinner/Vivante/VeriSilicon terms covering images, GitHub Releases and mirrors |
| Compiled sample model and input | Original checkpoint, conversion/data provenance, applicable grant | Obtain separate model/data permission or identify a vendor-authorized, reproducibly generated cleared sample; do not remove support by assumption |
| `boot0_sdcard_a733.fex`, `monitor.fex`, `scp.fex` | Blob-specific terms/source obligations | Request applicable boot-asset redistribution terms from the supplier separately |
| Kernel, U-Boot, modules and GPL userspace packages | Complete corresponding-source bundle, exact configs/patches/build instructions and required notices | Assemble/audit source closure for the exact shipped binaries and package versions; pinned URLs/SBOM alone are insufficient |
| Other Alpine components | Final notice/licence materials, including conditional obligations | Review each installed package's recorded licence and install required materials |
| Historical private rootfs input / prebuilt board outputs | Clean public bootstrap and independent reconstruction | Recreate from traceable locked upstream packages, retain no development state, rebuild and revalidate a new artifact |
| Newly authored Airlunix code | Owner-approved project licence selection | Confirm licence and add its full notice without relicensing upstream components |
| Physical candidate acceptance | Cold/software boots, SSH/provisioning/save restoration, board CPU/RAM/SD I/O and multi-client operation | Test approved spare media or a separately authorized board deployment; do not claim prior binary tests cover it |
| Physical HDMI / final shutdown tracing / IPv6 firewall | Actual corresponding evidence | Complete hardware/display, shutdown-interval and IPv6 tests in an authorized validation window |
| Daily time/drift/stability observation | Complete uninterrupted observation | Overnight testing is stopped at owner's request; do not restart or infer a 24-hour result |
| Public repository and release | Exact-target publication approval after blockers close | Present public `macraj/airlunix` and prerelease contents for the required publication gate; no upload now |

Public-facing source/assets and inspected runtime text use Airlunix, with no
prior application's marketing references or requirement to install it. Upstream
origins and existing legal notices remain. No trademark clearance is claimed.

## Acceptance and board protection

| Requirement | Evidence | Status | Remaining limit |
| --- | --- | --- | --- |
| Raw image limit / compression | Exact file sizes, SHA-256 and decompression hash | Passed | Bootability still needs physical candidate test |
| Generic credential exclusion | Full cpio policy scan | Passed | Not a complete independent security assessment |
| Console source/runtime integration | Committed-source and cpio byte comparison | Passed | Hardware integration pending |
| Backend/browser/disposable filesystem tests | 23 tests and actual screenshots | Passed | Host/emulated scopes described above |
| Offline Python/SSL/pip/venv | This candidate's own target result and byte comparison | Passed | Not a physical board boot |
| New-image RAM residency / no routine SD I/O | Implemented full-initramfs path | Pending | Physical workload, shutdown and restart tests required |
| NPU hardware execution/accuracy | Components retained; library loader checks only | Pending | No new candidate hardware inference claim |
| Public redistribution / corresponding sources | Per-component review and unsent request | Pending | Explicit blockers above |
| 24-hour observation | Earlier short preserved samples only | Pending | Interrupted by owner-confirmed power disconnect; now stopped by instruction |

The board was not rebooted, reflashed or deployed to by this work. Its collector
was absent after the accidental power disconnect. At the owner's stop request,
evidence was exported again and absence of remaining observation collectors
confirmed. Overnight testing will not restart automatically. Earlier evidence
exports remain private on the build host.
