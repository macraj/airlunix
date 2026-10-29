# Volatile diagnostics

The administration helper hosts the logging worker. There is no separate
collector daemon and no new APK dependency. Runtime logs live on the dedicated
8 MiB `/run/airlunix-log` tmpfs; ordinary operation does not save them to SD.
The retained channel payload ceiling is 6 MiB. The incremental diagnostic
working-memory target is 32 MiB, not a limit on total server RAM.

| Channel | Total payload ceiling |
| --- | ---: |
| system, kernel, security | 1 MiB each |
| service, network, ntp, administration | 512 KiB each |
| cron, web, helper, health | 256 KiB each |

Each channel has an active file and one previous generation. Rotation deletes
only that channel's previous generation, then renames; it never copytruncates.
Service files use 240 KiB each, reserving 32 KiB for finite early/fallback output
inside the same 512 KiB ceiling. Records are capped at 2048 encoded bytes.

The worker processes at most two frames per ready source per turn, followed by
a 50 ms pause. Per-producer/channel record and byte buckets, fixed-size maps,
repeat coalescing and separate channel budgets constrain retained data. Under
pressure collection intentionally loses data; applications must not wait for
it. Classic Linux socket filters reject oversized datagrams before they occupy
receive queues. Known loss counters are **lower bounds**: oversized frames
rejected in the kernel and native libc syslog losses are not exactly counted.
Counters cover the current collector instance; older summaries remain in Health.

The existing musl 1.2.6 dependency is source-built with a one-line nonblocking
syslog socket patch. This prevents a full or stalled `/dev/log` receiver from
blocking SSH, elevation or DHCP. Its pinned source archive SHA256 is
`d585fd3b613c66151fc3249e8ed44f77020cb5e6c1e635a616d3f9f82460512a`;
upstream release source is `https://musl.libc.org/releases/musl-1.2.6.tar.gz`
(MIT). Run `scripts/build-nonblocking-musl.sh` before building the image.
This overrides the APK's libc file; the package list alone does not describe
that override. Candidate provenance must include its source/patch/binary hashes.

The helper collects kernel messages, root syslog, bounded DHCP hook output,
boot/service diagnostics, NTP results and security/administrative outcomes.
Cron's routine minute dispatch messages are counted instead of appended;
dispatch errors are retained. Python service output is summarized, with safe
exception classes/frames; fixed tool failures retain a sanitized tail. This is
not a verbatim transcript of every application or arbitrary native stdout.
Chrony/tool capture continuously drains bounded tails; it does not first create
an unlimited file. No passwords, hashes, tokens, cookies, sensitive bodies or
arbitrary elevation command arguments belong in these records.

Use Console → Logs as an administrator. Unlock with a fresh password for a
five-minute helper-verified grant. Filter by channel, severity or exact event;
read bounded pages and use Older records. Rotation can expire cursors. Each
response has at most 200 records/256 KiB, two readers and a read-rate limit.
The UI requests 100 records. Actor, outcome, boot-relative ordering and clock
confidence remain distinct. The availability/health panel exposes worker state,
loss counters, source limits and current file sizes.

Diagnostic export requires another fresh password. It downloads a bounded,
redacted gzip JSON summary: recent metadata, health and limited current state.
Raw messages, actors, private network/device state and older pages are omitted
and listed as omissions. Export uses stricter implementation limits than the
policy maximum: 400000 uncompressed bytes and 45000 compressed bytes. It is not
a complete forensic capture. Do not publish private logs or exports by default.

Root SSH can inspect the fixed JSON-line files. Web users do not receive a
file-path or shell API. Normal users cannot read shared logs through Console.

Files survive Web/helper restarts in RAM; sessions/grants and current counters
reset. Reboot/power loss discards logs, telemetry and runtime state. Save
configuration excludes them. There is no shutdown save, automatic persistent
logging, remote receiver or core-dump collection. Kernel failure can prevent
manual export; pstore/ftrace remain unavailable. Root compromise is outside the
audit's tamper-resistance claim. Optional persistent/remote capture is separate,
disabled-by-default work.

Before NTP, wall time is explicitly unsynchronized. Boot identity, monotonic
sequence and boot seconds establish ordering. NTP observation is not a guarantee
of trusted UTC. Kernel records preserve their original header/time and identify
boot replay. Clock discontinuities are recorded without rewriting old records.
