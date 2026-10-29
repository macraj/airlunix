# Draft — request for Airlunix runtime redistribution permission

**Status: prepared, not sent.**

Intended initial recipient: Orange Pi / Shenzhen Xunlong, supplier of the pinned
`sun60iw2_packages` package. Please route to the responsible Allwinner and/or
Vivante/VeriSilicon licensing rightsholder if your organization cannot grant the
requested rights. VeriSilicon technical routing contact, as documented in its
official Acuitylite repository: `ML_Support@verisilicon.com`.

**Subject: Written redistribution terms for exact A733 VIPLite runtime and sample assets in public Airlunix images**

We are preparing Airlunix, an independent RAM-resident Linux distribution for
the Orange Pi 4 Pro / Allwinner A733. We wish to retain NPU support and need the
applicable written redistribution terms for the exact files below, supplied in
`https://gitee.com/orangepi-xunlong/sun60iw2_packages.git`, commit
`28961f4804cf8c2826b4e560c76bd5239658e90b`.

| File | SHA-256 |
| --- | --- |
| `npu/usr/lib/libVIPhal.so` | `648444a26a1aeaec0182c0ba348b7a453134b8ccdf8282a211ce4c0f5e5e51a0` |
| `npu/usr/lib/libNBGlinker.so` | `de93bb4a7d86af67bc4ca597d12228b9b21b062601b18f33ca30393a2af4a842` |
| `npu/opt/vpm_run/vpm_run` | `dbcea3266070d51a4e0b3aac19540814d065f3727a6045ee96e25f9464371407` |
| `npu/opt/vpm_run/network_binary.nb` | `fc0d50bdc863e4dfc74eef6dad9d34655c560e759a2f426979a01c505fa9b95f` |
| `npu/opt/vpm_run/input_0.dat` | `d38c22c2007db314572c9ddfeb513a9f3d11ec99e8deec0f65bc91481502f1b9` |

The installed runtime/sample reports VIPLite `2.0.3.2-AW-2024-08-30`. The source
built kernel driver has separate Dual MIT/GPL notices and is not presumed to
share the userspace binary terms. The common header's MIT/GPL choice and TIM-VX's
MIT licence are also not presumed to cover these binaries.

Please provide the applicable licence/EULA and confirm, file by file:

1. Whether we may reproduce and redistribute these unmodified target binaries
   inside complete, publicly downloadable Airlunix raw/compressed images and
   update packages, free of charge, through GitHub Releases, our download service,
   public mirrors and downstream redistributors retaining required notices.
2. Whether permission is worldwide, applies to archival/versioned releases,
   and permits recipients to install and use them on Orange Pi 4 Pro / A733.
   Identify hardware restrictions, commercial-use restrictions, fees, acceptance
   requirements or limits on further redistribution.
3. What copyright notices, attribution, licence texts, source offers, source
   materials, EULA presentation or other conditions must accompany distribution.
   Identify the rightsholder and your authority to grant or relay these rights.
4. Whether the runtime libraries and sample executable have different terms
   from the development/conversion SDK and its headers. We are not requesting
   blanket permission to redistribute an entire development SDK.
5. Separately, identify the author, original weights/checkpoint, model licence,
   conversion provenance and redistribution rights for `network_binary.nb`
   (graph identifier `ShuffleNetV2_uint8_NCHW`), plus rights for `input_0.dat`.
   If these sample assets cannot be cleared, please identify a supported sample
   with explicit redistribution terms or an authorized way to generate one.
6. If these exact versions cannot be authorized, please identify a supported
   A733 target runtime package with explicit public redistribution permission,
   its download source, version, hashes and compatibility requirements.

We have not located an applicable standalone licence/EULA in the original
package. We therefore describe redistribution rights as unverified, rather than
assuming permission or claiming a prohibition. Please supply the authoritative
terms or an explicit written grant covering the requested distribution channels.
