#!/bin/bash
# Intentionally does not print SSIDs, passwords, auth links, IP lists or key files.
set -u
printf 'Architecture: %s\n' "$(uname -m)"
printf 'Kernel: %s\n' "$(uname -r)"
for unit in NetworkManager tailscaled tailbridge-network tailbridge-display tailbridge-firewall tailbridge-redir; do
    printf '%s: %s\n' "$unit" "$(systemctl is-active "$unit" 2>/dev/null)"
done
for name in /sys/class/graphics/fb*/name; do
    [[ -f "$name" ]] && printf '%s: %s\n' "$name" "$(cat "$name")"
done
if [[ -S /run/tailbridge/network.sock ]]; then echo 'Local Wi-Fi socket: present'; else echo 'Local Wi-Fi socket: missing'; fi
if ip link show tailscale0 >/dev/null 2>&1; then echo 'Tailscale interface: present'; else echo 'Tailscale interface: missing'; fi
if [[ $(id -u) -eq 0 ]]; then
    if nft list table inet tailbridge_guard >/dev/null 2>&1; then echo 'Forwarding guard: loaded'; else echo 'Forwarding guard: missing'; fi
fi
printf '%s\n' 'Display detail: sudo journalctl -u tailbridge-display -b --no-pager' \
    'Treat other system logs as private; they may contain network identifiers.'
