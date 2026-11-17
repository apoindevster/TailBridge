#!/bin/bash
set -euo pipefail
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project"
mkdir -p .cache build
revision=935fda9def785f49dc1e5435388c6c344b8e68a1
source_dir="$project/.cache/ts-redir-build"
if [[ ! -d "$source_dir/.git" ]]; then
    git clone --quiet https://github.com/apoindevster/ts-redir.git "$source_dir"
fi
# This private build cache is disposable; the user's upstream project is never edited.
git -C "$source_dir" fetch --quiet origin "$revision"
git -C "$source_dir" reset --quiet --hard "$revision"
git -C "$source_dir" clean -fdq
curl --fail --silent --show-error --location \
    https://cdn.jsdelivr.net/npm/@picocss/pico@2.0.0-alpha1/css/pico.min.css -o .cache/pico.min.css
echo '4c4befaa02d5ccf8756c406283945591a623d023c6843ae734b1aa8633c83958  .cache/pico.min.css' | sha256sum --check --status
python3 scripts/prepare_ts_redir.py "$source_dir"
(cd "$source_dir" && GOTOOLCHAIN=auto go test -race ./...)
staging=$(mktemp -d "$project/build/.bundle.XXXXXX")
trap 'rm -rf -- "$staging"' EXIT
bundle="$staging/tailbridge-pi"
mkdir -p "$bundle/bin" "$bundle/vendor" "$bundle/licenses"
(cd "$source_dir" && CGO_ENABLED=0 GOOS=linux GOARCH=arm64 GOTOOLCHAIN=auto \
    go build -trimpath -ldflags="-s -w -X main.version=tailbridge-0.1.0 -X main.commit=$revision" \
    -o "$bundle/bin/ts-redir" ./cmd/ts-redir)
for directory in tailbridge scripts packaging docs integrations licenses tests artifacts; do
    mkdir -p "$bundle/$directory"
    cp -a "$project/$directory/." "$bundle/$directory/"
done
cp "$project/vendor/README.md" "$bundle/vendor/"
cp README.md PLAN.md PRODUCT.md DESIGN.md LICENSE SECURITY.md CONTRIBUTING.md pyproject.toml requirements-dev.txt "$bundle/"
mkdir -p "$bundle/.impeccable"
cp .impeccable/design.json "$bundle/.impeccable/"
if [[ -f RESULTS.md ]]; then cp RESULTS.md "$bundle/"; fi
cp "$source_dir/LICENSE" "$bundle/licenses/ts-redir-MIT.txt"
cp docs/THIRD-PARTY.md "$bundle/licenses/NOTICE.md"
(cd "$source_dir" && python3 "$project/scripts/collect_licenses.py" "$bundle/licenses")
chmod +x "$bundle"/scripts/*.sh
# Include the newly added integration files in the reviewable patch.
git -C "$source_dir" add -N internal/web/guard*.go internal/firewall/persistent*.go internal/firewall/kernel_test.go internal/web/templates/pico.min.css
git -C "$source_dir" diff --stat > build/ts-redir-integration-stat.txt
git -C "$source_dir" diff > build/ts-redir-integration.patch
# Validate the actual fresh bundle, never an older directory from a prior build.
TAILBRIDGE_BUNDLE="$bundle" python3 -m unittest discover -s tests -v
find "$bundle" -type d -name __pycache__ -prune -exec rm -rf '{}' +
# Remove local account names/UIDs and timestamps from downloadable archives.
tar --sort=name --owner=0 --group=0 --numeric-owner --mtime="@${SOURCE_DATE_EPOCH:-0}" \
    -cf - -C "$staging" tailbridge-pi | gzip -n > "$staging/tailbridge-pi-arm64.tar.gz"
rm -rf -- "$project/build/tailbridge-pi"
mv "$bundle" "$project/build/tailbridge-pi"
mv "$staging/tailbridge-pi-arm64.tar.gz" "$project/build/tailbridge-pi-arm64.tar.gz"
(cd build && sha256sum tailbridge-pi-arm64.tar.gz > tailbridge-pi-arm64.tar.gz.sha256)
printf '%s\n' 'Built build/tailbridge-pi-arm64.tar.gz (Pi hardware testing remains required).'
