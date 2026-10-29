# Airlunix image delivery and exact publication dependencies

The requested deliverable is the bootable image. The source-only GitHub preview
is separate and does not complete image delivery. The existing private candidate
is preserved without rebuilding. NPU support has not been removed or made
dependent on experimental replacement projects.

## Existing candidate and private delivery

Private workspace artifact directory:
`output/private-artifacts/airlunix-0.3.0-devpreview/`.
No external private upload destination is configured in this session.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `airlunix-0.3.0-headless-server-a733.img` | 805306368 | `718af92d55d98a7826e11f7cb119f38a6bd7e951f8ce143bf5de41a839108972` |
| `airlunix-0.3.0-headless-server-a733.img.xz` | 65678972 | `502c4567ffb32cfbec494d5632f37c229198d3f4caecb05dc4f8bed3d6c4582f` |

Both private delivery copies were SHA-256 verified against the original
candidate. They are not copies of the provisioned board's SD card.

## Exact boot chain evidence

All three vendor files below come from `orangepi-build`, revision
`a95129bf30ea11886cc35f08ebb3e69695a26656`,
`external/packages/pack-uboot/sun60iw2/bin/`.

| Actual candidate input | Exact bytes / SHA-256 | Role and inclusion evidence |
| --- | --- | --- |
| `boot0_sdcard_a733.fex`, installed as `boot0_sdcard.fex` | 245760 / `9213f1c56ef932930d43b5751e8937bea0e9ae7460ec16187cc1b0dffdb75345` | Exact bytes match raw image at offset 8192; first-stage SD boot component |
| Source-built, patched `u-boot.fex` | 1196032 / `5e44efcc12b0edb822089ec643b883a98e02dd745340b1f6f62dd620cb8c283e` | TOC1 item `u-boot`, relative payload offset 2048 |
| `monitor.fex` | 78609 / `8af16b86ae8e2eff634a3ebca76a8cdf3c10b3540387573d46c3d785545b2632` | Exact TOC1 item `monitor`, relative offset 1198080; reports `v2.5(debug):7dddb263a-dirty`, BL31 and Allwinner sun60iw2p1 paths |
| `scp.fex` | 105912 / `07e6b97628101963e7944e012948c4bdf721f914bad347acd7dfbde89db42749` | Exact TOC1 item `scp`, relative offset 1276928; contains AR100 firmware identification |

The TOC1 container starts at raw image offset **16793600**, SHA-256
`17869ee6e869b8deb94746ca2482850f4dd85644fc1827e6321d9879edd83ad5`.
Parsing the actual container verified the three entries against their inputs.
The pinned `boot_package.cfg` enables only U-Boot, monitor and SCP; its OP-TEE
entry is commented out. **No OP-TEE payload is included.** Other UFS/SPI/board
boot0 variants in the vendor directory are not this image's boot inputs.

The vendor repository has a root GPL-2.0 text. That is repository-level licence
evidence, not a file-specific prohibition. Coverage, authorship and corresponding
source for these exact prebuilt payloads still require confirmation. The monitor's
TF-A-like version/path strings do not establish that an upstream BSD grant covers
this modified binary. Do not label all three files proprietary or forbidden
without applicable terms.

## Publication blocker table

Categories: **R** explicit restriction; **P** missing/ambiguous permission or
licence scope; **S** corresponding source/notices; **T** technical validation.
Multiple categories may apply independently.

| Component/file | Applicable licence evidence | Unresolved requirement | Concrete next action | Essential for boot? |
| --- | --- | --- | --- | --- |
| `boot0_sdcard_a733.fex` | Vendor repository GPL-2.0 text; no located file-specific notice or grant | **P/S:** confirm coverage and obtain matching first-stage/DRAM source or other applicable binary terms | Ask Xunlong/Allwinner for terms and source for the exact hash above; record whether GPL scope includes this payload | Yes, current SD ROM boot path |
| `monitor.fex` | Repository GPL-2.0 text; BL31 v2.5 modified-build strings; no matched exact vendor source/licence materials | **P/S:** applicable terms/notices and source requirements for `7dddb263a-dirty` | Obtain vendor fork plus dirty changes if required by its terms, or an authoritative binary redistribution grant and required notices | Required by current monitor-based handoff; replacement not validated |
| `scp.fex` | Repository GPL-2.0 text; embedded AR100 identification; no located file-specific terms/source match | **P/S:** firmware licence scope, matching source/notice obligations | Request hash-specific AR100 firmware terms/source; establish platform requirements before any proposal to omit it | Included in current baseline; independence from boot/runtime power management unproven |
| `u-boot.fex`, patched DTB/config and boot scripts | U-Boot `Licenses/README` GPL-2.0 and individual file notices; pinned source revision | **S:** source/build/packer closure, notices and exact transformation evidence | Matching source archive, working patch, build config and full licence directory collected; verify packer/tool inputs and publish corresponding materials beside the image | Yes |
| Kernel `uImage`, DTB, modules including `vipcore.ko` | Kernel COPYING/LICENSES; driver declares Dual MIT/GPL (also verified with modinfo) | **S/T:** full source/input reproduction, required notices and final candidate hardware validation | Pinned full source, working patch, config and licence tree collected; finish input closure and physical tests | Kernel/DTB yes; NPU driver no for headless boot |
| `libVIPhal.so` | Exact Orange Pi hash established; neither binary-specific grant nor matching comparison-SDK binary found | **P:** target-runtime redistribution scope | Submit prepared supplier request covering public images, GitHub Releases and mirrors; obtain written applicable terms | No |
| `libNBGlinker.so` | Same bounded finding; exact file tracked separately | **P:** its own or expressly shared runtime grant | Obtain file-specific coverage, hardware restrictions and notices | No |
| Vendor `vpm_run` installed as `opi-vpm-run` | Exact executable hash retained; usage readme is not a licence | **P/S:** executable terms and any required source | Ask supplier separately for sample-tool terms/source | No |
| `network_binary.nb` | Exact match to SDK `examples/vpm_run/operator/v3/network_binary.nb`; graph identifier ShuffleNetV2_uint8_NCHW | **P:** model/weights grant and checkpoint/conversion provenance | Obtain separate model permission/provenance or propose a cleared vendor-supported sample for owner decision | No |
| `input_0.dat` | Exact SDK sample match, no identified data grant | **P:** sample-data redistribution permission | Request separate data terms or an approved, traceable replacement | No |
| `vip_lite_common.h` | Exact matching header explicitly offers MIT or GPL-2.0-or-later | No runtime-binary grant follows from this file | Preserve the header's own notices wherever shipped; do not extend them to `.so` files | No; not a candidate runtime payload |
| `vip_lite.h` | Explicit Vivante confidential/proprietary notice requiring express written permission | **R:** applies to this header if distributed, not automatically adjacent binaries | Do not add this header to release materials without an applicable grant; it is not needed in this candidate | No; not a candidate runtime payload |
| TIM-VX | MIT licence for its covered software; not provenance of these candidate runtime binaries | No claim it clears the shipped `.so` files | Keep separate; it is not a prerequisite or mandatory replacement | No; not included |
| Alpine installed packages, including Python/pip/venv/SSL, BusyBox, Chrony, nftables, OpenSSH, musl and GCC runtime | 77 package licence/origin/commit records; exact aports recipes | **S:** corresponding sources/notices and conditional obligations, rather than a blanket permission failure | 46 exact recipe directories collected; checksum-verified distfiles and extracted notices collected; verify collection closure and distribute the companion materials with the image | Base components yes; package-specific roles vary |
| Newly authored distribution/console code | Owner licence choice not yet recorded; upstream components keep their licences | **P:** explicit chosen distribution licence for original code | Record owner's licence selection and attach its text; this is separate from vendor permissions | Distribution scripts/console code included; console is not kernel boot-critical |
| Historical private rootfs build snapshot | Hash-locked build input, not a public clean bootstrap | **S/T:** public reconstruction and complete input provenance | Reconstruct from locked upstream inputs; never upload the private snapshot; revalidate any rebuilt future artifact | Not a runtime boot dependency, but a reproducibility gap |
| Existing image as a whole | Static, emulated and host tests completed | **T:** physical boot, access, persistence, board resource/I/O, shutdown/IPv6/HDMI checks | Validate on approved spare card/hardware; preserve the current board; do not claim image acceptance from source tests | Yes for a tested bootable-image claim |

## Completed source-material work

The private `output/release-materials/airlunix-0.3.0/` collection contains:

- Full pinned Linux source archive, SHA-256
  `22c71149baf4bdb6f2b0deb975e603f22f3e362c82fced416a3178f3e08698cb`,
  301618452 bytes; actual working-source patch, build config, COPYING and LICENSES.
- Full pinned U-Boot source archive, SHA-256
  `744329d604cbc9c4e71fbd5e421879f1102957c727848ca9013e8c43d214962c`,
  30128995 bytes; actual working-source patch, build config and Licenses directory.
- Build scripts, configuration and patches for the distribution, without images,
  device credentials or vendor runtime blobs.
- 77 installed package records mapped to **46 exact origin/commit recipe directories**,
  all fetched successfully with accompanying local patches/configuration/notices.
- Checksum-verified upstream distfile collection and extracted notice files;
  **312 recipe input entries verified, zero checksum/collection gaps**. Forty-four
  origin/revision pairs declare external inputs; two alpine-base revisions are
  recipe-only metapackages. The collection contains 176 extracted upstream
  licence/notice files. Collection is not a claim that all legal conditions or
  binary reproduction have been independently verified.

These companion materials can be supplied alongside the unchanged image; adding
external notices/source archives does not require rebuilding it. If a particular
applicable term requires an in-image notice or another binary change, that must
be assessed explicitly before a future rebuild.

## Route to publishing the image

1. Existing candidate is privately delivered and hash-preserved now.
2. Finish the source/notice collection review and attach complete companion
   materials; resolve exact boot-file terms/source requirements.
3. Retain NPU in the full private candidate. If optional userspace/model rights
   remain open, present two choices: wait for the full NPU-inclusive public image,
   or authorize a separate base-only public variant while retaining NPU private
   builds and the source-built driver. **No scope change has been made.** Such a
   variant would be a new artifact requiring new hashes/tests, not this image
   renamed. Experimental open-NPU work is not a delivery prerequisite.
4. Physically validate this exact candidate on separate approved media/hardware.
   A 2 GB card has sufficient capacity, but read-back and physical boot must pass.
5. Publish raw/XZ image, SHA256SUMS, exact provenance, required sources/notices
   and candid acceptance results as image assets of an explicitly labelled
   developer prerelease. Keep source preview and image release status distinct.

## 2 GB SD preparation result

The identified spare SD reports 2002780160 bytes. The existing image was written
without rebuilding. The final write flushed 805306368 bytes in 163.186 seconds;
direct read-back (`iflag=direct`) read the same number in 62.8967 seconds and
returned the exact raw candidate SHA-256 above. This is a successful media-content
verification, not a physical board boot result or a whole-card endurance test.

The first verification was invalidated by the host automatically mounting ext4
read/write; its first differing byte was 33555501, in the ext4 superblock. The
automounter was paused and the card unmounted before the successful rewrite.
This does not establish defective media. An intervening user-requested card-swap
attempt interrupted another write; that incomplete state was overwritten fully.

The owner confirms only one board exists. Therefore physical boot testing cannot
both use a separate board and leave the current board running. Controlled
shutdown/card swap requires an explicit change to that constraint, preservation
of remaining RAM evidence and preparation of development-device SSH access.
No board shutdown or deployment has occurred during this preparation.
