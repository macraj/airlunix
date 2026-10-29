# Airlunix 0.3.0 — developer preview preparation

The rebrand retains 0.3.0 because the prepared distribution line is still its
initial preview. The Airlunix artifact is new: it needs its own build identifier,
hashes and validation. Earlier binary-specific tests do not automatically certify
this image. No public repository or release has been created.

Implemented in source: full initramfs runtime, explicit selected persistence,
secure provisioning, one-shot Chrony lifecycle and the local HTTPS Web Console.
NPU support remains intended; public binary redistribution is pending verification.

| Acceptance area | State | Limitation |
| --- | --- | --- |
| Console unit tests and disposable ext4 operations | Host tests available | Not a physical board test |
| Console authentication / HTTPS browser testing | In progress | Production artifact not yet accepted |
| Rebuilt image size, checksums, provenance | Pending | Previous image hash must not be reused |
| Board no-write observation | Existing collector preserved | Does not cover this new console artifact |
| New console image cold boot / resource measurements | Pending | No deployment during current observation |
| Physical HDMI | Pending | No physical display result claimed |
| Final shutdown-interval tracing | Pending | Earlier network-side evidence is incomplete |
| IPv6 firewall | Pending | IPv4 results do not establish IPv6 coverage |
| 24-hour clock/drift/stability | Pending | Do not infer success before observation ends |
| Public binary redistribution / corresponding sources | Pending | Component-specific review required |

Application-specific readiness is outside the base release acceptance. No
application will be installed solely to manufacture a readiness result.
