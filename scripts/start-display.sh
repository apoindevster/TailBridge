#!/bin/bash
set -euo pipefail
runtime=/run/tailbridge-display
framebuffer=${FRAMEBUFFER:-}
if [[ -z "$framebuffer" ]]; then
    for attempt in {1..30}; do
        for name in /sys/class/graphics/fb*/name; do
            [[ -f "$name" ]] || continue
            if [[ "$(cat "$name")" =~ (ili9486|st7796|mhs35) ]]; then
                framebuffer="/dev/$(basename "$(dirname "$name")")"
                break
            fi
        done
        [[ -n "$framebuffer" ]] && break
        sleep 1
    done
fi
if [[ ! "$framebuffer" =~ ^/dev/fb[0-9]+$ ]] || [[ ! -c "$framebuffer" ]]; then
    echo 'SunFounder framebuffer not found; run tailbridge-doctor through SSH.' >&2
    exit 1
fi
# Isolate from vendor desktop configs, which may select HDMI or fbturbo instead.
mkdir -p "$runtime/xorg.conf.d"
sed "s|@FRAMEBUFFER@|$framebuffer|g" /opt/tailbridge/packaging/xorg.conf.in > "$runtime/xorg.conf"
export DISPLAY=:0 XAUTHORITY="$runtime/Xauthority"
touch "$XAUTHORITY"
chmod 0640 "$XAUTHORITY"
chown root:tailbridge "$XAUTHORITY"
cookie=$(openssl rand -hex 16)
printf 'add :0 MIT-MAGIC-COOKIE-1 %s\n' "$cookie" | xauth -f "$XAUTHORITY" source -
unset cookie
# xauth can replace the file with mode 0600 while updating it.
chown root:tailbridge "$XAUTHORITY"
chmod 0640 "$XAUTHORITY"
export HOME=/var/lib/tailbridge-ui
exec /usr/bin/xinit /usr/bin/setpriv --reuid=tailbridge --regid=tailbridge --clear-groups \
    --no-new-privs --bounding-set=-all --inh-caps=-all --ambient-caps=-all \
    /usr/bin/python3 -m tailbridge.ui -- /usr/lib/xorg/Xorg :0 vt1 \
    -config "$runtime/xorg.conf" -configdir "$runtime/xorg.conf.d" \
    -auth "$XAUTHORITY" -nolisten tcp -nocursor -noreset -keeptty
