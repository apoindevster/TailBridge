#!/bin/bash
# Download only reviewed tool versions; verify bytes before running them.
set -euo pipefail
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
destination="$project/.cache/tools"
mkdir -p "$destination"
temporary=$(mktemp -d)
trap 'rm -rf -- "$temporary"' EXIT
fetch_tool() {
    local name=$1 url=$2 checksum=$3
    curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
        "$url" -o "$temporary/$name.tar.gz"
    printf '%s  %s\n' "$checksum" "$temporary/$name.tar.gz" | sha256sum --check --status
    tar -xzf "$temporary/$name.tar.gz" -C "$temporary" "$name"
    install -m 0755 "$temporary/$name" "$destination/$name"
}
fetch_tool gitleaks \
    https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_x64.tar.gz \
    551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb
fetch_tool actionlint \
    https://github.com/rhysd/actionlint/releases/download/v1.7.12/actionlint_1.7.12_linux_amd64.tar.gz \
    8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8
printf '%s\n' 'Verified Gitleaks 8.30.1 and actionlint 1.7.12 in .cache/tools.'
