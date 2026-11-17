#!/bin/bash
# Run on the Pi from the built arm64 bundle. Never run a remote script as root.
set -euo pipefail
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if [[ ${EUID} -ne 0 ]]; then echo 'Run with sudo.' >&2; exit 1; fi
if [[ $# -lt 2 || $# -gt 3 || $1 != --country || ! $2 =~ ^[A-Z]{2}$ || ( $# -eq 3 && $3 != --reset-pin ) ]]; then
    echo 'Usage: sudo ./scripts/install.sh --country YOUR_TWO_LETTER_COUNTRY [--reset-pin]' >&2; exit 1
fi
country=$2
if [[ $(uname -m) != aarch64 ]] || ! grep -aq 'Raspberry Pi 4' /proc/device-tree/model; then
    echo 'This installer targets Raspberry Pi 4 with a 64-bit OS.' >&2; exit 1
fi
source /etc/os-release
if [[ ${VERSION_CODENAME:-} != trixie ]]; then echo 'Raspberry Pi OS Trixie is required.' >&2; exit 1; fi
if [[ ! -x "$project/bin/ts-redir" || ! -f "$project/packaging/display-source.json" ]]; then
    echo 'Use the built arm64 bundle; see README.md.' >&2; exit 1
fi
if [[ ! -f /boot/firmware/config.txt ]]; then echo 'Pi firmware config not found.' >&2; exit 1; fi
if [[ -f /var/lib/tailbridge/install-backup/restored ]]; then
    echo 'Previous install was recovered. Archive /var/lib/tailbridge/install-backup before reinstalling.' >&2; exit 1
fi
# Shared with the post-boot audit. Reject autologin/custom console commands and
# an unsafe existing UI account before installing packages or changing files.
python3 "$project/scripts/verify_kiosk.py" --preflight
pin_options=()
if [[ ${3:-} == --reset-pin ]]; then pin_options+=(--reset); fi
PYTHONPATH="$project" python3 -m tailbridge.lock "${pin_options[@]}"
install -d -m 0700 /var/lib/tailbridge/install-backup
if [[ ! -f /var/lib/tailbridge/install-backup/services.json ]]; then
    python3 - <<'PY'
import json, pathlib, subprocess
read = lambda *args: subprocess.run(args, capture_output=True, text=True).stdout.strip()
pathlib.Path('/var/lib/tailbridge/install-backup/services.json').write_text(json.dumps({
    'default': read('systemctl', 'get-default'),
    'forwarding': pathlib.Path('/proc/sys/net/ipv4/ip_forward').read_text().strip(),
}))
PY
fi
# Dependencies come from signed distribution repositories.
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3 python3-tk python3-dbus python3-qrcode network-manager \
    xserver-xorg-core xserver-xorg-video-fbdev xserver-xorg-input-evdev \
    xinit xauth x11-xserver-utils fonts-dejavu-core nftables curl ca-certificates \
    openssl util-linux raspberrypi-sys-mods raspi-config
# The vendor blob is fetched locally, never redistributed in public artifacts.
# Verify it before changing boot/display configuration, including on reinstallation.
python3 "$project/scripts/fetch_display.py"
if ! command -v tailscale >/dev/null; then
    install -d -m 0755 /usr/share/keyrings
    curl --fail --silent --show-error --location https://pkgs.tailscale.com/stable/debian/trixie.noarmor.gpg \
        -o /usr/share/keyrings/tailscale-archive-keyring.gpg
    curl --fail --silent --show-error --location https://pkgs.tailscale.com/stable/debian/trixie.tailscale-keyring.list \
        -o /etc/apt/sources.list.d/tailscale.list
    chmod 0644 /usr/share/keyrings/tailscale-archive-keyring.gpg /etc/apt/sources.list.d/tailscale.list
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y tailscale
fi
if ! id tailbridge >/dev/null 2>&1; then
    useradd --system --user-group --home-dir /var/lib/tailbridge-ui --create-home --shell /usr/sbin/nologin tailbridge
fi
# One file-installation path copies the current payload and installs every boot
# and kiosk policy. The same path is exercised under a temporary root in tests.
python3 "$project/scripts/configure_system.py"
install -m 0755 /opt/tailbridge/scripts/doctor.sh /usr/local/bin/tailbridge-doctor
# The user supplies the regulatory country; no inferred region is programmed.
raspi-config nonint do_wifi_country "$country"
systemctl daemon-reload
systemctl daemon-reexec
sysctl -q -p /etc/sysctl.d/99-tailbridge-kiosk.conf
systemctl enable --now NetworkManager tailscaled
systemctl set-default multi-user.target
systemctl mask getty@tty1.service
systemctl enable tailbridge-network tailbridge-display tailbridge-firewall tailbridge-redir
printf '%s\n' 'Installed. No reboot was forced.' \
    'Run sudo reboot when ready. Enter your touchscreen PIN to open Home.' \
    'After reboot: sudo python3 /opt/tailbridge/scripts/verify_kiosk.py' \
    'Recovery: sudo /opt/tailbridge/scripts/recover.sh'
