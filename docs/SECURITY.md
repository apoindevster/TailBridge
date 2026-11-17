# Architecture and security

`systemd → Xorg/fbdev → unprivileged Tk UI → protected Unix socket → root broker
→ NetworkManager D-Bus` is the local configuration path. The broker accepts only
status, scan, join and Tailscale enrollment operations, authenticates the peer UID
using SO_PEERCRED, and does not offer a shell or arbitrary command endpoint.
Passwords travel as D-Bus fields, never shell commands or process arguments.

The display service owns tty1 and Xorg runs with the privileges required for the
framebuffer and input devices. Only its Tk child runs as `tailbridge`, a dedicated
account with no login shell. Xorg requires a private authority cookie and does not
listen on TCP. The broker and ts-redir have systemd filesystem protections; ts-redir
is limited to NET_ADMIN and NET_RAW capabilities. Core dumps are disabled for these
services. This is privilege separation, not a tamper-resistant hardware boundary.

The status-page QR encodes only a constructed `http://<device-name-or-ip>:8800`
URL. It is built from the validated local MagicDNS name or a Tailscale IPv4 address
while Running, never from `AuthURL`, a password, cookie or authentication token.
Enrollment QR codes remain confined to Tailscale setup. A status error clears the
management QR rather than continuing to advertise stale status. Scanning does
not authenticate a phone or change access policy; its existing Tailscale connection
and permission to reach the management port are still required.

## App-only display and authenticated administration

The display starts directly in TailBridge, without a desktop, window manager,
launcher or terminal. Its production window ignores close/Alt-F4 requests. The
systemd service restarts the display after a crash; tty1's getty is masked, so
exiting the app cannot fall into an automatically logged-in shell. Xorg disables
VT switching and its keyboard termination shortcut. Keyboard SysRq is disabled;
both the ordinary Ctrl-Alt-Del target and systemd's repeated-key fallback are
disabled. The theme uses no executable external content.

The Tk process has no supplementary groups, an empty Linux capability set and
`no_new_privs`. Its account has a nologin shell. The root X server remains necessary
for this framebuffer setup; it is not a complete sandbox against an Xorg exploit.

SSH and password-authenticated console/serial login remain the administrative
entry points. There is no guest desktop or automatic administrative login. Normal
operation keeps the touchscreen app-only; a graphical login manager is not needed
to launch it. `sudo python3 /opt/tailbridge/scripts/verify_kiosk.py` checks effective
console login commands, process privilege state, system keyboard policy, X config,
service restart policy and SSH availability without printing credentials. The
installer refuses custom console commands that differ from the reviewed Trixie
password-login defaults, requiring administrator review before proceeding.
The same preflight requires active SSH and rejects a privileged or login-enabled
existing `tailbridge` account. A fresh installation creates a dedicated nologin
account. The code payload is root-owned and not writable by the UI account.

`scripts/install.sh` includes all boot fixes, UI changes and security policy on
the first install. There are no separate patch scripts. Reinstallation preserves
the initial recovery baseline; it does not provide live activation or automatic
rollback. The recovery script restores original keyboard-policy files, Ctrl-Alt-Del
alias/mask and prior live SysRq value. Recovery requires authenticated sudo.
No physical tamper resistance is claimed: boot media modification or privileged
administrative changes can bypass a software kiosk. Physical keyboard escape
attempts and crash/reboot acceptance still need testing on the actual device.

Policy references: [Xorg server flags](https://xorg.freedesktop.org/archive/X11R6.8.1/doc/xorg.conf.5.html),
[Linux keyboard SysRq](https://docs.kernel.org/admin-guide/sysrq.html), and
[systemd CtrlAltDelBurstAction](https://www.freedesktop.org/software/systemd/man/259/systemd-system.conf.html).

ts-redir's socket binds to both the Tailscale IPv4 address and `tailscale0` using
SO_BINDTODEVICE. An additional input rule drops TCP 8800 arriving elsewhere.
Tailscale policy is the management authentication layer; no separate password is
added. Browser request protections accept only the bound numeric Host or this Pi's
exact full MagicDNS name, both with the configured port. The name comes from
`/usr/bin/tailscale status --json`: `Self.DNSName` is accepted only while Running
and when `Self.TailscaleIPs` contains the server's bound IP. No wildcard `*.ts.net`,
forwarded Host header, client-supplied name or reverse lookup is trusted. Only
ordinary ASCII DNS labels under `.ts.net` are accepted. The daemon's trailing root
dot is removed; browser URLs use the full name without that dot. A mutex-protected
30-second cache bounds lookups, each limited to three seconds. Expiry replaces
the old name even on failure, leaving IP access available. A rename or logout can
therefore leave the prior name accepted for up to the cache interval; the socket
and Tailscale policy remain the authentication boundary throughout.

Mutations require an Origin matching the actual request's Host, so a page opened
by name cannot mutate the IP origin (or vice versa). The existing same-origin
fetch-metadata check also remains. Other controls include a 32 KiB body limit,
server timeouts, CSP and text-node
rendering for peer/rule data. CSS is embedded locally. These changes are maintained
as an integration over the pinned upstream source, without editing its repository.

IPv4 TCP/UDP forwarding is handled by Linux nftables and the official Tailscale
daemon. The additional `inet tailbridge_guard` table permits only explicit DNAT
traffic entering wlan0/eth0 toward Tailscale IPv4 destinations, and return traffic.
Other forwarding is denied. This is a **dedicated appliance configuration**, not a
general router or a Docker host. No IPv6 redirects, exit node or advertised subnet
routes are configured. Tailscale's own firewall and access policy still apply.
Loss of the Tailscale route cannot send redirected traffic out a normal LAN route.

The separate `ip ts_redir` table holds redirects. Rule changes are serialized and
persisted with atomic replacement, mode 0600, file and directory fsync. Invalid
saved data is rejected before restoration. A storage failure is reported; a kernel
change may already have taken effect, so verify the rule list and storage before
rebooting. The whole system does not claim transactions spanning disk and kernel.
Deleting a redirect does not forcibly clear existing conntrack sessions.

Wi-Fi credentials are saved only after the requested connection has an IPv4
address. NetworkManager stores them in root-restricted system profiles; this is
**not SD-card encryption**. Tailscale identity remains in the daemon's protected
state directory. Root, physical SD access, swap or a compromised privileged daemon
can expose secrets. No claim of cryptographic memory erasure is made. Password
display is masked by default; reveal expires after 15 seconds and abandoned input
is cleared after two minutes. Wi-Fi credentials and enrollment links are not
logged by TailBridge. Avoid sharing raw system logs without reviewing them.

No eFuses, OTP settings, bootloader locks or irreversible provisioning are used.
The installer never executes LCD-show's broad configuration script. Original files
are backed up before changing them; the recovery script keeps credentials and
identity. Hardware recovery and network isolation must still be validated on the Pi.
