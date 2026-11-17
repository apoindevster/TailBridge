# Contributing

Use synthetic data in code, screenshots, issues and test results. Keep real SSIDs,
addresses, tailnet names, enrollment URLs and credentials out of the repository.
Security reports belong in the [private reporting process](SECURITY.md).

## Development on Linux

Install Git, curl, a C compiler, Go, Python 3 with Tk, D-Bus and venv support,
ImageMagick, Xvfb, xauth and DejaVu fonts. On Debian/Ubuntu the non-Go packages are:

```sh
sudo apt-get install build-essential git curl ca-certificates python3-tk \
  python3-dbus python3-venv python3-qrcode imagemagick xvfb xauth fonts-dejavu-core
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements-dev.txt
./scripts/build.sh
xvfb-run -a -s '-screen 0 800x600x24' .venv/bin/python tests/ui_smoke.py --decode-qr
python3 scripts/check_publication.py
```

The build runs the Go race tests and Python suite against a fresh arm64 bundle.
It checks Tk and D-Bus imports before downloading or compiling. Set
`TAILBRIDGE_PYTHON=/usr/bin/python3` when invoking `scripts/build.sh` to use the
distribution interpreter explicitly; an isolated venv cannot import apt's D-Bus
binding. Use `--system-site-packages` when creating a development venv.
Installer tests use a temporary filesystem and a synthetic overlay; they do not
change the host's services, display, Wi-Fi or firewall. The UI smoke test uses
only the application's synthetic window, checks layout and decodes QR pixels.
Run `scripts/build.sh` again if changed screenshots should be included in the bundle.

For the workflow and secret checks on Linux x86-64:

```sh
./scripts/ci_tools.sh
.cache/tools/actionlint
python3 scripts/check_publication.py --stage-source .cache/public-source
.cache/tools/gitleaks dir .cache/public-source --redact --no-banner
.cache/tools/gitleaks dir build/tailbridge-pi --redact --no-banner
# Once commits exist, scan history too:
.cache/tools/gitleaks git . --log-opts=--all --redact --no-banner
```

Do not allowlist a secret to make CI green. Revoke it, remove it and coordinate
history cleanup before publishing. `.gitignore` is not a security boundary and
does not untrack files already committed. Tool versions/checksums live in
`scripts/ci_tools.sh`; update both together after reviewing official releases.

## Changes and review

Keep `scripts/install.sh` the single install/reinstall entry point. Preserve
authenticated recovery, the unprivileged display, restricted broker protocol,
tailnet binding, request checks, safe rule persistence and forwarding guards.
Changes to ts-redir must keep its source pin, preparation assertions and Go tests
in agreement. Do not run remote installation scripts as part of build or CI.

Describe the behavior change and checks actually run in a pull request. Update
PLAN.md and RESULTS.md when a milestone or acceptance status changes. Keep
software checks separate from the [hardware checklist](docs/TESTING.md); do not
mark unperformed camera, touch, direct/DERP, recovery or soak tests complete.

Contributions to original TailBridge code are under the [MIT license](LICENSE).
Preserve upstream notices and avoid adding vendor binaries without established
redistribution terms.
