# Raspberry Pi implementation plan

Target: Raspberry Pi 4, 2 GB; Raspberry Pi OS Trixie arm64;
SunFounder MHS35IPS / ST7796U + XPT2046, 480 × 320 landscape.

- [x] Inspect upstream ts-redir and SunFounder display setup; pin source revisions.
- [x] Implement privileged NetworkManager broker and unprivileged touch UI.
- [x] Integrate ts-redir on tailscale0 with request protection and persistence.
- [x] Add boot services, reversible installer, diagnostics and recovery instructions.
- [x] Run host tests, build ts-redir for arm64 and inspect actual UI captures.
- [x] Verify real nftables rule lifecycle and guard syntax in isolated host network namespaces.
- [x] Install on the authorized Pi 4 and verify reboot, Wi-Fi/SSH return, SPI framebuffer and touch-driver startup.
- [x] Apply and verify the first-boot Tailscale null-status correction on the running Pi.
- [x] Implement the requested dark neon theme, contrast checks and app-only display protections.
- [x] Verify existing Pi console login commands require authentication; confirm Tailscale is now running and ts-redir remains bound to tailscale0.
- [x] Activate the staged neon/kiosk update with authenticated sudo, then verify the running processes and policy.
- [x] Consolidate all changes into the main fresh-install path; remove patch scripts and verify a clean bundle, repeat installation and recovery.
- [x] Add exact local MagicDNS access on port 8800 and show the name beside the tailnet IP on Status; retain tailnet binding and per-origin mutations.
- [x] Build and stage the MagicDNS package; pass 28 Python checks on host and Pi, Go race tests, native status captures and Pi installation preflight.
- [x] Activate the MagicDNS bundle on the Pi and verify both URLs and Host/Origin checks on the running service (installed files match the release).
- [x] Add a plain management-URL QR to Status, with name/IP fallback, stable polling and screenshot decoding.
- [x] Build and stage the QR package; pass 30 Python checks on host and Pi, 14 decoded native captures and Pi installation preflight.
- [x] Prepare GitHub publication: MIT license, synthetic README gallery, privacy review, source/release checks and CI; validate workflow commands in clean Ubuntu 24.04.
- [ ] Push to the chosen GitHub repository and confirm its first hosted CI run and artifact uploads.
- [ ] Install the QR bundle and run the post-boot kiosk audit with sudo.
- [ ] User: scan the management QR from the physical display using a tailnet-connected phone.
- [ ] User: test physical keyboard escape prevention and confirm the neon theme on the SPI display.
- [ ] User: visually confirm the screen and touch alignment, test Wi-Fi changes, enrollment and redirection.

Full hardware acceptance and throughput remain pending; remote boot/driver evidence
is recorded in RESULTS.md and is distinct from physical screen/touch confirmation.
No inherited ESP results apply to this implementation.

The 2026-11-16 software milestone is installed on the authorized Pi. See RESULTS.md
for executed checks and docs/TESTING.md for physical acceptance, direct/DERP and
concurrent-connection measurements. Tailnet-only web management follows the user's
explicit direction; no separate LAN authentication gateway is included.

The 2026-11-17 consolidated bundle passes host installation/reinstallation and
configuration-recovery tests. A clean-image install/reboot has not been performed;
the Pi was unreachable over its LAN address during this consolidation.

The Pi is reachable again. The MagicDNS release is installed; both management
URLs return 200 and unrelated Hosts/cross-origin mutations return 403. The QR
addition is the next package; activation requires sudo authentication. Physical
phone scanning and the post-boot root kiosk audit remain pending.

The public package now excludes the SunFounder overlay because its redistribution
license is not established. The unified installer downloads and checksum-verifies
it locally. Its download path and 35 Python checks pass on the host; the publication
changes have not been installed on the Pi. A clean Ubuntu CI rehearsal also passed
with Go 1.27.4, including the arm64 build and 14 decoded synthetic UI captures.
