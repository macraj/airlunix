# Install Airlunix on Orange Pi 4 Pro

This release targets only **Orange Pi 4 Pro / Allwinner A733**. It is a developer
prerelease. Verify `SHA256SUMS` before writing an image. Writing an image destroys
the selected card.

For a powered-off installation, decompress the `.img.xz`, identify the exact
removable SD device by model, capacity and hardware identity, unmount its
partitions, write the raw `.img`, flush it and verify the written image SHA-256.
Insert the card in the Orange Pi 4 Pro and boot. Never select the build host's
system disk.

For an already running Airlunix device, open Web Console through its configured
management path and choose **Storage → Prepare a replacement SD**. Save current
configuration first. After the Console confirms the boot card is unmounted,
remove it and insert one replacement microSD. The device selects an official
`macraj/airlunix` GitHub Release for this exact hardware, displays the version,
download size and physical destination, and requires fresh administrator
authentication plus exact target confirmation. It downloads `.img.xz` directly,
decompresses and writes with bounded memory, verifies both release hashes and a
full readback, then saves current users and selected configuration. Keep power
connected throughout. A partial or failed write is not a prepared card.

Routine operation runs from RAM. Package changes made with `apk` disappear on
reboot and are not a supported update mechanism. Reproducible package updates
are built into a new complete Airlunix release. Logs and other ordinary runtime
state remain volatile. The single-card update path is not atomic: loss of power
during writing can leave the replacement card unbootable; retain a known-good
card for recovery.
