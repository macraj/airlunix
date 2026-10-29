#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
LOCK="$ROOT/configs/baseline.lock"

while read -r name url ref commit; do
    [[ -z "${name:-}" || "$name" == \#* ]] && continue
    dest="$ROOT/downloads/$name"

    if [[ -e "$dest" ]]; then
        if [[ ! -d "$dest/.git" ]]; then
            echo "Refusing to use non-Git source directory: $dest" >&2
            exit 1
        fi
        if ! actual=$(git -C "$dest" rev-parse HEAD 2>/dev/null); then
            git -C "$dest" fetch --depth 1 origin "$commit"
            git -C "$dest" checkout -q --detach FETCH_HEAD
            actual=$(git -C "$dest" rev-parse HEAD)
        fi
        if [[ "$actual" != "$commit" ]]; then
            echo "$name revision mismatch: expected $commit, found $actual" >&2
            echo "Preserving the existing directory; inspect it before replacing it." >&2
            exit 1
        fi
        local_status=$(git -C "$dest" status --porcelain)
        case "$name" in
            linux-orangepi) patch="$ROOT/patches/linux-orangepi-kbuild-make43.patch" ;;
            u-boot-orangepi) patch="$ROOT/patches/u-boot-orangepi-out-of-tree-dtb.patch" ;;
            *) patch="" ;;
        esac
        if [[ -n "$patch" ]]; then
            if [[ -z "$local_status" ]]; then
                git -C "$dest" apply "$patch"
            elif [[ "$local_status" == ' M Makefile' ]] && \
                git -C "$dest" -c diff.mnemonicPrefix=false \
                    diff --binary --unified=0 --src-prefix=a/ --dst-prefix=b/ HEAD -- Makefile \
                    | cmp -s - "$patch"; then
                : # The one tracked local Kbuild compatibility patch is already applied.
            else
                echo "Unexpected local changes in pinned Linux source: $dest" >&2
                echo "Preserving it; inspect the changes before building." >&2
                exit 1
            fi
        elif [[ -n "$local_status" ]]; then
            echo "Pinned source tree has local changes: $dest" >&2
            echo "Preserving it; review the changes before building." >&2
            exit 1
        fi
    else
        mkdir -p "$ROOT/downloads"
        git init -q "$dest"
        git -C "$dest" remote add origin "$url"
        if ! git -C "$dest" fetch --depth 1 origin "$commit"; then
            echo "Could not fetch pinned commit $commit for $name ($ref)." >&2
            exit 1
        fi
        if [[ "$name" == sun60iw2_packages ]]; then
            # This repository also contains unrelated large desktop packages.
            # Only materialize the A733 NPU user-space subtree needed here.
            git -C "$dest" sparse-checkout init --cone
            git -C "$dest" sparse-checkout set npu
        fi
        git -C "$dest" checkout -q --detach FETCH_HEAD
        actual=$(git -C "$dest" rev-parse HEAD)
        if [[ "$actual" != "$commit" ]]; then
            echo "$name checkout mismatch: expected $commit, found $actual" >&2
            exit 1
        fi
    fi
    printf '%-18s %s (%s)\n' "$name" "$commit" "$ref"
done < "$LOCK"
