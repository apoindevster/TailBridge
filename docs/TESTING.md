# Pi acceptance checklist — PARTIALLY RUN

Remote installation, reboot, framebuffer/touch-driver startup and the retained
Wi-Fi/SSH connection were verified on 2026-11-16. The checkboxes below require the
broader physical and end-to-end checks described; see RESULTS.md for exact evidence.

Record date, Pi revision/RAM, image date, `uname -r`, Tailscale version and screen
revision. Do not paste passwords, Tailscale state, enrollment URLs or auth keys.
Use a disposable test service on an authorized tailnet peer, not sensitive services.

- [ ] Install on clean Raspberry Pi OS Trixie arm64 using Ethernet; save an SD image.
- [ ] Install/update in an interactive SSH terminal: hidden PIN prompts match,
  upgrades retain the PIN and explicit reset replaces it without exposing it.
- [ ] Cold boot without a keyboard: PIN lock appears without a Linux login prompt;
  unlocking opens Home with Lock, Status and Wi-Fi. Check numeric keypad touch
  targets, leading zeroes, deletion, masking and 30-second partial-input clearing.
- [ ] Home routes to Status/Wi-Fi and both return Home. Manual Lock hides details
  and QR codes immediately; no keyboard/back navigation bypasses authentication.
- [ ] Wrong PINs enforce the displayed cooldown across display/broker restarts
  and reboot. Correct PIN succeeds after cooldown. Missing/unreadable PIN state
  fails closed. Recover a forgotten PIN through authenticated SSH; unsafe state
  requires administrator repair. Measure verification latency on the Pi without
  recording the PIN, salt or derived hash.
- [ ] Wi-Fi, Tailscale and redirects continue while locked; ts-redir's existing
  tailnet authentication remains unchanged. No automatic idle lock is expected.
- [ ] Display fills 480×320; all four touch corners and every keyboard row align.
- [ ] Confirm dark neon colors and readable text on the actual SPI display.
- [ ] With a physical keyboard, Alt-F4, Ctrl-Alt-F2, Ctrl-Alt-Backspace,
  Ctrl-Alt-Del (including repeated presses), and Alt-SysRq do not reveal a shell
  or bypass the application. Run during a supervised maintenance window.
- [ ] Authenticated SSH remains available. With SSH, stop/kill the UI during a
  supervised test; the display service recovers without an automatic console login.
- [ ] `sudo python3 /opt/tailbridge/scripts/verify_kiosk.py` passes after cold boot.
- [ ] Scan, rescan, paging, empty scan, hidden SSID, WPA2, WPA3, open-network warning.
- [ ] Wrong password, unavailable AP and DHCP failure restore a previously working
  connection. Interrupt broker during a join and check automatic rollback after 90s.
- [ ] Successful Wi-Fi profile reconnects after reboot. Ethernet SSH remains usable
  while Wi-Fi changes. Test a long SSID and a password with punctuation privately.
- [ ] Tailscale QR enrollment succeeds; status shows the correct numeric URL and
  full MagicDNS URL with port 8800. Name-unavailable and very long-name fallback
  leave the complete numeric URL usable.
- [ ] From a phone already on the tailnet, scan the status QR on the physical
  SunFounder panel and confirm the browser opens ts-redir without enrollment.
  Check the name and IP fallback at practical distances/angles. Confirm the
  code disappears on stopped/unavailable status and updates after an address/name
  change. Screenshot decoding is not a physical phone-camera test.
- [ ] Authorized tailnet client reaches port 8800; LAN-only client cannot reach it,
  including packets addressed to the Pi's Tailscale IP over its LAN interface.
- [ ] Tailnet client blocked by grants/ACLs cannot administer the Pi.
- [ ] With MagicDNS enabled and client DNS accepted, both displayed URLs open
  ts-redir. Other device names, arbitrary Host values and cross-alias Origin
  mutations are rejected. After a rename, allow 30 seconds for name refresh.
- [ ] Create/delete TCP and UDP redirects; verify persistence over service restart
  and full reboot. Check failure with Tailscale stopped and with no route to peer.
- [ ] Check packets for redirected connections do not leak onto Ethernet/Wi-Fi
  when Tailscale is down. Verify unrelated destination ports are not forwarded.
- [ ] Recovery script restores the original boot/display settings and SSH still
  works after reboot. Test once before treating the appliance as unattended.

## Direct and DERP measurements

On the test peer, run an iperf3 server bound to its Tailscale IPv4 address. Install
iperf3 on a separate LAN client and create a TCP redirect on the Pi, for example
LAN port 5201 → peer port 5201. Limit the peer's tailnet access to this test.

From the LAN client run `iperf3 -c PI_LAN_IP -p 5201 -t 30 -P 1`, then repeat with
`-P 2`, `4`, `8`, and `16`. Use at least three runs per level, increasing concurrency
only while latency, failures, CPU, memory and temperature remain acceptable. Record
client throughput, median/p95 service latency from a parallel small-request workload,
failed connections, Pi CPU, RSS, temperature and throttling (`vcgencmd get_throttled`).
Report **Mbit/s**; divide by eight for approximate MB/s. Pick the lowest connection
count that achieves stable useful throughput without degrading responsiveness.

For UDP, create a matching UDP rule too; iperf3 also uses a TCP control connection.
Start with a low bitrate (e.g. `-u -b 1M`) and record loss/jitter before raising it.

Verify the actual path on the Pi with `tailscale ping PEER_TS_IP` and
`tailscale status` during each run; a connection can switch from DERP to direct.
Measure a confirmed direct path first. For DERP, use an isolated test network/router
that blocks direct peer UDP while allowing the Tailscale relay connection, with
Ethernet SSH recovery retained. Recheck the relay path throughout; do not label a
run DERP from its first ping alone. Do not change the appliance firewall merely to
force a result. Restore the test network restrictions afterwards.

Finish with repeated Wi-Fi loss/reconnect, service restarts and power-cycle tests.
Only mark a 24-hour soak complete after actually running one and recording its start,
finish, workload, path changes, errors and resource trends. No throughput, direct,
DERP, physical touch or soak result has yet been established for this implementation.

## Host checks

`python3 -m unittest discover -s tests -v` runs protocol, validation, simulated
NetworkManager recovery, and file-only installer tests. The complete bundle test
installs the current runtime and all policies into a temporary root, reinstalls
without replacing the original recovery baseline, restores original configuration,
and checks that a synthetic credential file is untouched. It runs on the host and
inside an extracted bundle without requiring root or contacting NetworkManager.
`scripts/build.sh` runs Go
race tests against an in-memory firewall and HTTP request recorder, including
exact local MagicDNS identity, malformed names, cache expiry/concurrency/failure,
and Host/Origin boundaries, then compiles
arm64 and runs the Python suite against a freshly assembled package before
publishing it. After building, `scripts/kernel_smoke.sh` opts into real nftables operations
inside disposable network namespaces and checks the forwarding guard with the host
nft binary. It requires Linux user/network namespaces and never targets host networking.
`tests/ui_smoke.py` exercises native Tk with synthetic network data and
captures only its own window. With `--decode-qr`, it additionally uses Pillow and
[zxing-cpp](https://github.com/zxing-cpp/zxing-cpp/tree/master/wrappers/python)
to decode the real captured pixels: normal/name-change codes must contain the
exact name URL, missing/dense names must contain the IP URL, and status errors,
unenrolled and missing-library views must contain no QR. It also verifies that
unchanged status preserves the existing canvas, recovery restores it, and the
separate enrollment QR remains correct. These optional decoder dependencies are
development-only. These checks cannot establish actual hardware or
kernel packet-path behavior.
