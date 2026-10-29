# NPU component redistribution review — 2026-10-29

NPU support remains an intended Airlunix capability. No runtime, driver or model
has been removed from the observation device or private build. Public binary
publication remains pending component-specific verification.

Follow-up: [exact upstream comparison](npu-upstream-comparison.md) records
matching headers/sample files, nonmatching runtime builds, and the
[unsent supplier permission request](npu-permission-request.md).

## Sources and permission provenance

The runtime bundle is not a versioned APK/DEB package. Its exact identity is
`sun60iw2_packages`, commit `28961f4804cf8c2826b4e560c76bd5239658e90b`,
from <https://gitee.com/orangepi-xunlong/sun60iw2_packages.git>, directory `npu/`.
The kernel source is `linux-orangepi`, commit
`2ac08e8c7cdc28abbdc5c9a9dd812f887ae9c79f`, from
<https://github.com/orangepi-xunlong/linux-orangepi>.

The earliest located permission assertion is project commit `8ee5f4f`,
`docs/licensing.md`: “The owner confirmed permission for **local use only**;
these binaries are not licensed for redistribution.” This is a secondary project
note. No original grant, EULA, vendor correspondence or verbatim owner permission
establishing that scope was located. It does not substantiate a prohibition.
The current conclusion for unspecified binaries is **redistribution rights
unverified**. A notice on one header is not evidence of terms for every file.

## Component decisions

| Component / exact version or identity | Applicable evidence and terms | Current decision / unresolved question |
| --- | --- | --- |
| `vipcore.ko`, Linux 6.6.98-sun60iw2; source VIPLite 2.0.3.5-AW-2026-03-17 | Pinned kernel `bsp/drivers/npu/aw_nna_vip/vip2`; `os/linux/vip_drv_device_driver.c:1808` declares `MODULE_LICENSE("Dual MIT/GPL")`; individual source notices must be retained | Source-built driver can be distributed under its declared licence, subject to source/notice obligations and the kernel's own requirements. Audit the precise source closure in the release bundle. |
| `usr/lib/libVIPhal.so`, runtime reports VIPLite 2.0.3.2-AW-2024-08-30 | Vendor commit above; no binary-specific licence/EULA or root licence found in the inspected NPU tree | Redistribution rights unverified. Request a target-runtime grant, including A733 hardware scope and notice conditions. |
| `usr/lib/libNBGlinker.so`, same bundle, no independent package version verified | No applicable binary grant located | Redistribution rights unverified; ask whether covered by the target-runtime grant. |
| `opt/vpm_run/vpm_run`, same bundle | No applicable executable licence or corresponding source located | Redistribution rights unverified; obtain sample-tool redistribution terms separately. |
| `usr/include/vip_lite.h` | Lines 2–8: Vivante copyright 2017–2024, proprietary/confidential; prohibits disclosure, reproduction, copying, transmission or use without express written permission | Restrictive terms documented for this header. Do not redistribute it without permission; do not extrapolate its notice to the shared libraries. |
| `usr/include/vip_lite_common.h` | Lines 3–51 contain a dual MIT/GPL notice, including distribution permission under MIT subject to retaining its notice, or GPL-2.0-or-later | Keep the full applicable notice. This file is not governed solely by the adjacent header's restrictive wording. |
| `opt/vpm_run/network_binary.nb`, `input_0.dat` | Compiled model and sample data; no origin/model/data licence established | Redistribution rights unverified; identify model authors, source weights, conversion and dataset rights. |
| `opt/yolov5/model/yolov5.nb`, images/result and sample executable | Separate sample set, not proof of the weights' upstream licence or permission to redistribute this conversion | Redistribution rights unverified. Do not assign a current upstream YOLO licence without tracing these exact assets. |
| OpenCV `.so.407`, `libjpeg.so.8`, `libpng16.so.16` in vendor tree | Distinct third-party components; filenames alone do not establish the exact source revision, build options or included notices | Determine whether each is actually included; use traceable Alpine packages where compatible. Do not classify these as Vivante proprietary software. |
| Separate NPU firmware | No separate firmware payload identified in the inspected 20-file NPU tree or inspected driver directory | Not proof that no firmware exists anywhere in the platform. Identify any firmware requests and release payload before closing this row. |
| ACUITY development/conversion SDK | Not downloaded, pinned or installed as part of this runtime review; no applicable full SDK EULA captured | SDK licensing is a separate question from target runtime redistribution. No finding of prohibition. |
| `opt/pvrsrvkm.ko` | Unrelated GPU module built for Linux 5.15, not the source-built A733 NPU driver | Not included in the working NPU runtime. No proposed change. |
| `boot0_sdcard_a733.fex`, `monitor.fex`, `scp.fex` | Separate boot assets from pinned Orange Pi build inputs; a GPL U-Boot licence does not automatically cover these blobs | Redistribution rights unverified, independently of NPU. Public image publication also depends on resolving these assets. |

## Recorded runtime file hashes

| Vendor-relative file | SHA-256 |
| --- | --- |
| `npu/usr/lib/libVIPhal.so` | `648444a26a1aeaec0182c0ba348b7a453134b8ccdf8282a211ce4c0f5e5e51a0` |
| `npu/usr/lib/libNBGlinker.so` | `de93bb4a7d86af67bc4ca597d12228b9b21b062601b18f33ca30393a2af4a842` |
| `npu/opt/vpm_run/vpm_run` | `dbcea3266070d51a4e0b3aac19540814d065f3727a6045ee96e25f9464371407` |
| `npu/opt/vpm_run/network_binary.nb` | `fc0d50bdc863e4dfc74eef6dad9d34655c560e759a2f426979a01c505fa9b95f` |
| `npu/opt/vpm_run/input_0.dat` | `d38c22c2007db314572c9ddfeb513a9f3d11ec99e8deec0f65bc91481502f1b9` |

## Vendor-authorized route and alternatives

The [official Radxa A733/T527 SDK guide](https://docs.radxa.com/en/cubie/a7s/app-dev/npu-dev/cubie-acuity-sdk)
identifies the Vivante SDK and vendor distribution route. A downloadable SDK or
model zoo is evidence of availability, not by itself redistribution permission.
The [VeriSilicon acuitylite repository](https://github.com/VeriSilicon/acuitylite)
provides a support contact and an MIT licence for that repository; that does not
establish terms for every separately delivered SDK binary.
[TIM-VX](https://github.com/VeriSilicon/TIM-VX) is a possible open integration
layer, but its platform SDK dependency remains. A compatible, fully cleared
A733 runtime replacement has not been demonstrated.

Recommended next step: obtain written, file-specific target-runtime terms from
Orange Pi/Allwinner or VeriSilicon, identifying the commit and hashes above.
Ask separately about redistribution with a public A733 Linux image, hardware
restrictions, notices, model assets, headers and development SDK use. No vendor
message has been sent; contacting third parties requires owner authorization.

Keep NPU in the intended feature scope and preserve private working builds.
Prepare source and release materials while holding uncleared binary publication.
Do not describe this hold as a proven redistribution prohibition or remove NPU
as a shortcut to releasing the image.
