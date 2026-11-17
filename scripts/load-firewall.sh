#!/bin/bash
set -euo pipefail
transaction=$(mktemp)
trap 'rm -f "$transaction"' EXIT
if nft list table inet tailbridge_guard >/dev/null 2>&1; then
    echo 'delete table inet tailbridge_guard' > "$transaction"
fi
cat /opt/tailbridge/packaging/forwarding.nft >> "$transaction"
# Replacement is one nftables transaction: there is no unguarded flush interval.
nft --check --file "$transaction"
nft --file "$transaction"
sysctl -q -w net.ipv4.ip_forward=1
