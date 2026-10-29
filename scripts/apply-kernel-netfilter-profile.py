#!/usr/bin/env python3
"""Trim vendor Netfilter defaults to a stateful nftables host firewall."""

from __future__ import annotations

import re
import sys
from pathlib import Path


KEEP = {
    "CONFIG_NETFILTER": "y",
    "CONFIG_NETFILTER_ADVANCED": "y",
    "CONFIG_NETFILTER_NETLINK": "m",
    "CONFIG_NF_TABLES": "m",
    "CONFIG_NF_TABLES_INET": "y",
    "CONFIG_NF_CONNTRACK": "m",
    "CONFIG_NFT_CT": "m",
    "CONFIG_NFT_LOG": "m",
    "CONFIG_NFT_LIMIT": "m",
    "CONFIG_NFT_REJECT": "m",
    "CONFIG_NFT_REJECT_INET": "m",
    "CONFIG_NF_LOG_SYSLOG": "y",
    "CONFIG_NF_LOG_IPV4": "y",
    "CONFIG_NF_LOG_IPV6": "y",
}

FAMILIES = (
    "CONFIG_NETFILTER_",
    "CONFIG_NF_",
    "CONFIG_NFT_",
    "CONFIG_IP_SET",
    "CONFIG_IP_VS",
    "CONFIG_IP_NF_",
    "CONFIG_IP6_NF_",
    "CONFIG_BRIDGE_NETFILTER",
)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(f"Usage: {Path(sys.argv[0]).name} path/to/.config")
    path = Path(sys.argv[1])
    content = path.read_text()
    lines = content.splitlines()
    seen: set[str] = set()
    updated: list[str] = []

    for line in lines:
        match = re.match(r"(?:# )?(CONFIG_[A-Z0-9_]+)(?:=.*| is not set)$", line)
        if not match:
            updated.append(line)
            continue
        symbol = match.group(1)
        if symbol in KEEP:
            updated.append(f"{symbol}={KEEP[symbol]}")
            seen.add(symbol)
        elif symbol.startswith(FAMILIES):
            updated.append(f"# {symbol} is not set")
        else:
            updated.append(line)

    for symbol, value in KEEP.items():
        if symbol not in seen:
            updated.append(f"{symbol}={value}")

    path.write_text("\n".join(updated) + "\n")


if __name__ == "__main__":
    main()
