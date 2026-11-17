#!/bin/bash
# No host firewall changes: tests cannot run without a fresh network namespace.
set -euo pipefail
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project/.cache/ts-redir-build"
go test -c -o "$project/build/firewall-kernel.test" ./internal/firewall
export TAILBRIDGE_HOST_NETNS
TAILBRIDGE_HOST_NETNS=$(readlink /proc/self/ns/net)
unshare --user --map-root-user --net env TAILBRIDGE_ISOLATED_KERNEL_TEST=1 \
    "$project/build/firewall-kernel.test" -test.run TestIsolatedKernelLifecycle -test.v
unshare --user --map-root-user --net /usr/sbin/nft --check --file "$project/packaging/forwarding.nft"
