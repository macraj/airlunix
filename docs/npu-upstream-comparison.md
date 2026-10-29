# Exact NPU upstream comparison

Checked 2026-10-29. The candidate keeps working private NPU support. Nothing was
removed from the board. No third-party message or public upload was performed.

## Provenance and file identity

The candidate's immediate supplier is Orange Pi's
`sun60iw2_packages@28961f4804cf8c2826b4e560c76bd5239658e90b`, not an inferred
TIM-VX installation. The comparison SDK is
[ZIFENG278/ai-sdk](https://github.com/ZIFENG278/ai-sdk/tree/fc90006d0f6569da2f6726c2d8395877686f5aca),
revision `fc90006d0f6569da2f6726c2d8395877686f5aca`. Its `v2.0` directory name
does not establish an independently verified semantic version for each library.

| File | Candidate / Orange Pi SHA-256 | Comparison SDK SHA-256 | Finding |
| --- | --- | --- | --- |
| `libVIPhal.so` | `648444a26a1aeaec0182c0ba348b7a453134b8ccdf8282a211ce4c0f5e5e51a0` | `3ed5357b26bd6c4fb68fbdc0b21d637227dda711d1fe67b9e28accdc48bb11f2` | 39,248 vs 39,416 bytes; not identical |
| `libNBGlinker.so` | `de93bb4a7d86af67bc4ca597d12228b9b21b062601b18f33ca30393a2af4a842` | `82f049b0ed0065dd4d443e37eeb1edfcbef24457c9c24e36170d64d5b748ca66` | 174,560 vs 174,728 bytes; not identical |
| `vip_lite_common.h` | `d807216e8376de4729de074ecb1b91cd5ccab279ef18543acd3adb61b1a1518e` | Same | Exact match; dual MIT/GPL applies to this file |
| `vip_lite.h` | `33fee8f985210cb34f14b7e2b0614096e6972718f87d8107497521d561d9df41` | Same | Exact match; separate restrictive header notice |
| `network_binary.nb` | `fc0d50bdc863e4dfc74eef6dad9d34655c560e759a2f426979a01c505fa9b95f` | Same, `examples/vpm_run/operator/v3/network_binary.nb` | Exact sample-model match; licence still unresolved |
| `input_0.dat` | `d38c22c2007db314572c9ddfeb513a9f3d11ec99e8deec0f65bc91481502f1b9` | Same, `examples/vpm_run/operator/input_0.dat` | Exact sample-data match; licence still unresolved |

Comparison runtime paths are
`viplite-tina/lib/aarch64-none-linux-gnu/v2.0/{libVIPhal.so,libNBGlinker.so}`.
The inspected debug variants also did not match. Git blob IDs were compared
against the complete, non-truncated SDK tree; SHA-256 was verified on downloaded
matching model/data files. Neither actual runtime binary nor `vpm_run` matched
any blob in that tree. Shared headers or similar library names do not prove the
binary builds are equivalent.

The installed sample executable reports runtime VIPLite
`2.0.3.2-AW-2024-08-30`. This identifies the working vendor combination; no
independent embedded version string was found in either exact shared library.
The driver source separately reports `2.0.3.5-AW-2026-03-17`.

## Applicable grants and inspected package materials

The original Orange Pi package tree contains a usage `readme.txt`, but no
LICENSE, LICENCE, EULA, copyright or notice filename was found anywhere in its
pinned Git tree. The inspected SDK tree likewise contains no such standalone
licence filenames. Relevant example/model readmes and adjacent headers were
inspected. The usage readme explains building/running samples; it grants no
identified runtime-binary redistribution rights. No applicable grant was found
for the exact Orange Pi libraries or executable. This is a bounded evidence
finding, not proof that no separate vendor agreement exists.

The [matching common header](https://github.com/ZIFENG278/ai-sdk/blob/fc90006d0f6569da2f6726c2d8395877686f5aca/viplite-tina/lib/aarch64-none-linux-gnu/v2.0/inc/vip_lite_common.h)
expressly permits choosing MIT or GPL-2.0-or-later for that file. The
[TIM-VX licence](https://github.com/VeriSilicon/TIM-VX/blob/main/LICENSE)
contains MIT permission for its covered software. TIM-VX is not the provenance
of these candidate `.so` files. Neither grant has been established as covering
the adjacent Orange Pi runtime binaries. The restrictive `vip_lite.h` notice
also must not be extended to those binaries.

## Sample model assessment

The bundled `network_binary.nb` contains the graph identifier
`ShuffleNetV2_uint8_NCHW`. That is descriptive evidence, not verified authorship,
weight origin or a licence. The exact SDK sample-path match strengthens package
provenance but does not identify the source checkpoint, conversion record,
calibration/input-data rights or an applicable grant for the compiled model.
The SDK model readmes describe example conversion workflows without resolving
those specific rights. Do not assign a generic ShuffleNet or YOLO licence based
on the architecture name. The candidate's vpm sample is distinct from the
separate YOLO sample tree, which is not included in this candidate.

## Next action

Use [the prepared permission request](npu-permission-request.md) with Orange Pi /
Xunlong as immediate supplier, requesting the applicable grant and the chain of
authority from Allwinner and Vivante/VeriSilicon where needed. VeriSilicon's
[official Acuitylite support instructions](https://github.com/VeriSilicon/acuitylite#support)
list `ML_Support@verisilicon.com` as a technical contact; it is a routing contact,
not proof that the mailbox itself can grant all requested rights. Model/data
permission must be addressed separately. No message has been sent.
