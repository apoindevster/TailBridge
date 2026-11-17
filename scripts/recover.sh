#!/bin/bash
set -euo pipefail
if [[ ${EUID} -ne 0 ]]; then echo 'Run with sudo.' >&2; exit 1; fi
backup=/var/lib/tailbridge/install-backup
if [[ ! -f "$backup/files.json" ]]; then echo 'No installation backup found.' >&2; exit 1; fi
systemctl disable --now tailbridge-display tailbridge-redir tailbridge-network tailbridge-firewall || true
python3 /opt/tailbridge/scripts/configure_system.py --restore
# Only tables owned by this appliance are removed. Saved rules/identity are retained.
if nft list table ip ts_redir >/dev/null 2>&1; then nft delete table ip ts_redir; fi
if nft list table inet tailbridge_guard >/dev/null 2>&1; then nft delete table inet tailbridge_guard; fi
python3 - <<'PY'
import json, pathlib, subprocess
saved = json.loads(pathlib.Path('/var/lib/tailbridge/install-backup/services.json').read_text())
if saved['forwarding'] in ('0', '1'):
    subprocess.run(['sysctl', '-q', '-w', 'net.ipv4.ip_forward=' + saved['forwarding']], check=True)
kiosk = pathlib.Path('/var/lib/tailbridge/install-backup/kiosk.json')
if kiosk.exists():
    value = int(json.loads(kiosk.read_text())['sysrq'])
    subprocess.run(['sysctl', '-q', '-w', 'kernel.sysrq=' + str(value)], check=True)
subprocess.run(['systemctl', 'daemon-reload'], check=True)
subprocess.run(['systemctl', 'daemon-reexec'], check=True)
subprocess.run(['systemctl', 'set-default', saved['default']], check=True)
PY
touch "$backup/restored"
printf '%s\n' 'Original display/boot files and boot target restored. Reboot when ready.' \
    'Wi-Fi profiles, Tailscale identity, saved redirect rules and installed packages were retained.'
