#!/usr/bin/env bash
set -euo pipefail

if [[ "${OPI_BUILD_UIDMAP:-}" == yes ]] || [[ $(id -u) == 0 ]]; then
    exec "$@"
fi

user=$(id -un)
uid=$(id -u)
gid=$(id -g)
uid_range=$(awk -F: -v name="$user" '$1 == name { print $2 ":" $3; exit }' /etc/subuid 2>/dev/null || true)
gid_range=$(awk -F: -v name="$user" '$1 == name { print $2 ":" $3; exit }' /etc/subgid 2>/dev/null || true)
[[ -n "$uid_range" && -n "$gid_range" ]] || {
    echo "Rootless image building needs subordinate UID/GID ranges for $user in /etc/subuid and /etc/subgid." >&2
    exit 1
}
IFS=: read -r subuid subuid_count <<< "$uid_range"
IFS=: read -r subgid subgid_count <<< "$gid_range"
(( subuid_count >= 65535 && subgid_count >= 65535 )) || {
    echo "The subordinate UID/GID ranges should each cover at least 65535 IDs." >&2
    exit 1
}

exec unshare --user --setgroups=allow \
    --map-users="0:$uid:1" --map-users="1:$subuid:$subuid_count" \
    --map-groups="0:$gid:1" --map-groups="1:$subgid:$subgid_count" \
    -- env OPI_BUILD_UIDMAP=yes "$@"
