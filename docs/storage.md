# Storage and persistence

The supported MBR image reserves the first 32 MiB for the vendor boot chain.
Partition 1 starts at sector 65536 (512-byte sectors), is bootable Linux/ext4,
and has label `airlunix-state`. It stores boot artifacts and selected state;
there is no conventional persistent writable root filesystem.

First boot does **not** expand to fill the card. The default remains compact.
The console can preview explicit expansion into immediately adjacent unallocated
space or a new primary ext4 data partition in a suitable unallocated region.
It verifies the exact boot-detected device, expected filesystem identity,
unmounted partitions, absence of holders, MBR boundaries and preview freshness.
Extended/GPT layouts and non-512-byte logical sectors are rejected. Every
execution reauthenticates, confirms the named target and revalidates the layout.

Storage operations and explicit saves share an exclusive lock. No operation
reboots automatically. If the kernel cannot reread the table, the new table is
already durable but no filesystem format/resize is attempted. Inspect through
SSH; arrange an explicit reboot/recovery before continuing. A grown partition
with a smaller existing filesystem can be previewed again to resume filesystem
expansion. Never format that existing persistence partition to recover a failed
resize. Newly created data is not mounted automatically or added to boot state.

Filesystem free capacity is space inside a filesystem. Unallocated capacity is
outside partitions. Controller spare capacity is internal to the card. They are
different; reserving a fixed percentage does not guarantee an endurance gain.
There is no automatic whole-card zeroing, periodic discard or maintenance task.

Partition testing uses disposable regular-file images. Do not use the observation
board's card as test media. If a save/unmount fails, do not remove the card;
inspect `/state` and the device mounts through authenticated SSH and recover
before further storage actions.
