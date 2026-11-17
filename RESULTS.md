# Results

## GitHub CI idle-time regression — 2026-11-17

The first hosted build passed publication/workflow checks but failed the native
UI smoke test's hidden Wi-Fi input timeout assertion. The test assigned zero to
the last-touch timestamp, assuming the monotonic clock had already passed 120
seconds. A simulated clock starting at 10 seconds reproduced the exact failing
assertion on the host; the failed runner's clock origin was not recorded.

The smoke test now sets expiry timestamps relative to the current UI clock. It
uses a fresh clock origin by default and checks that newly entered Wi-Fi/PIN
input remains present before simulating expiry. Only the UI clock is replaced;
test deadlines and worker waits retain real time. Application timeouts, PIN
throttling, recovery and networking behavior are unchanged.

Both the 10-second and 1,000,000-second origins passed all 20 synthetic native
captures, including decoding each QR payload, on the host and under Xvfb in a
clean Ubuntu 24.04 container. The complete workflow rehearsal also passed all
53 Python tests, Go race tests, Linux arm64 packaging, workflow lint, publication
boundaries, archive checksum verification and source/history/release secret
scans. These are host tests; no Pi installation, physical test or traffic
benchmark was performed for this fix.

GitHub Actions [run 44140891293](https://github.com/apoindevster/TailBridge/actions/runs/44140891293)
then passed both jobs for fix commit `9bd51f5` on `fix/ci-idle-clock`, including
the previously failing UI step and the complete build/release audit. GitHub
confirmed both uploaded artifacts: `tailbridge-pi-arm64` and
`synthetic-ui-captures`. This verifies the correction on a hosted runner; merging
the branch into `main` remains separate.

## PIN/Home package uploaded for installation — 2026-11-17

Rebuilt the current package with the distribution Python and the previously
tested Go toolchain. Go race tests, all **53 host Python tests**, arm64 packaging,
publication boundaries and release secret scanning passed. Uploaded the archive
and checksum to a new private staging directory on the authorized Pi, verified
the checksum there and extracted it without replacing the installed application.

The target reports arm64 and Trixie. Its read-only installation preflight passed
console authentication, the dedicated UI account and active SSH recovery. All
**53 Python tests also passed on the Pi in 25.452 seconds**, using temporary
synthetic fixtures, including PIN storage and broker transport tests. No real PIN,
Wi-Fi credentials or Tailscale state was read or changed. No installer, service
restart or reboot was run; the user received an interactive SSH install command.

Uploaded archive SHA-256:
`deb09df2448e0d5d244160278df2eb3e6b19c275db5a9986d819b549394c4810`.
This receipt records the completed transfer after archive generation. Actual
activation, post-boot root audit, physical touch and PIN verification usability
remain pending; these synthetic device tests do not establish those results.

## Build-host D-Bus dependency diagnostics — 2026-11-17

The reported four missing-`dbus` errors match the four connection tests, which
need the Python D-Bus binding even during a cross-build. The host's distribution
Python can import it; an isolated venv reproduced the missing dependency. The
user's shell interpreter has not been directly observed.

The build now checks Python version, Tk and D-Bus imports before downloading or
compiling, gives distribution-package/venv instructions on failure, and supports
`TAILBRIDGE_PYTHON` to select an interpreter explicitly for all Python build
steps. README and contributor instructions now place build-host dependencies
before the build command. Network tests remain mandatory.

Verified that an isolated venv fails at preflight with actionable instructions
and no traceback. Rebuilding with the distribution Python passed Go race tests,
all **53 Python tests** and arm64 packaging. Shell syntax and whitespace checks
also pass. This build-host correction adds no Pi hardware evidence.

## Installer PIN lock and Home screen — 2026-11-17

Added the requested Home screen with exactly Lock, Status and Wi-Fi, plus a
numeric PIN lock using the existing neon palette, typography and control styles.
Startup/display restart begins locked; successful authentication opens Home.
Status and Wi-Fi return to Home. Lock clears private visible state and discards
late replies before accepting another unlock. Saved networking, redirects and
tailnet-only web management continue while the touchscreen is locked.

The unified installer privately prompts twice for a 6–12 digit PIN when missing,
preserves it on reinstall and accepts `--reset-pin` for an administrator reset.
There is no production default or command-line/environment PIN input. The broker
checks a random session on every network/status/enrollment operation, stores only
a salted PBKDF2-HMAC-SHA256 result in root-private state and persists rate-limited
attempts before verification. Reset/verification serialization prevents an
in-flight attempt from replacing a newly configured PIN. Authenticated SSH
recovery, app-only startup and existing tailnet controls remain in place.

Executed validation:

- **53 Python tests passed**, including PIN validation, hidden-terminal setup,
  salted private storage, all protected broker commands, session revocation,
  persisted cooldowns, malformed state, write failures, reset races and a real
  Unix-socket client/server authentication and revocation check. The transport
  test substitutes only privileged socket ownership and uses synthetic state.
- **20 native 480×320 captures passed**, including the six new Home/PIN states,
  masked input, wrong-PIN cooldown, setup/service errors, late-reply suppression
  and input clearing. All management/enrollment QR payloads decoded correctly.
  Visual finish review returned **ship**; documentation records the same theme
  and updated navigation without changing the design tokens.
- Go race tests, the Linux arm64 build, Python compilation, shell syntax,
  systemd unit verification, workflow lint and publication boundary checks passed.
  Gitleaks found no secrets in the **89-file source snapshot** or final release
  contents. Screenshots use synthetic data and stripped metadata; protected PIN
  state is excluded from source and release artifacts.

This feature has **not been installed on the Pi**. No real PIN was requested,
read or configured. Physical keypad accuracy, Pi PIN-verification latency,
real-device restart/cooldown and administrator recovery checks remain pending.
No physical phone scan, direct/DERP benchmark or 24-hour test is claimed. See
the updated acceptance checklist in [docs/TESTING.md](docs/TESTING.md).

## Initial commit privacy review — 2026-11-17

Rechecked all 80 publishable files before the initial local commit. Gitleaks
8.30.1 found no secrets; supplemental checks found no personal home paths,
private account/device identifiers, private keys or MAC addresses. Reviewed IPs
and URLs belong to synthetic fixtures, documentation examples or public upstream
services. Email-like source strings are systemd service names. Public upstream
copyright and repository attribution are intentionally retained.

All 14 images match the previously reviewed synthetic captures, including their
decoded QR contents; metadata checks pass. Caches, virtual environments, generated
builds, device state and the vendor overlay remain excluded. Publication checks,
workflow linting and all 35 Python tests pass. The repository's commit email is
set locally to the maintainer's GitHub no-reply address to avoid exposing a
personal email through commit metadata. Global Git settings are unchanged.

This review does not add hardware evidence. No remote or push is part of this
step; the first GitHub-hosted run and remaining Pi acceptance checks are pending.

## GitHub publication preparation — 2026-11-17

Added the user-selected MIT license for original TailBridge code, a four-screen
README gallery, contribution/security reporting guidance, publication notes,
issue/PR templates and GitHub Actions CI. All 14 native images contain synthetic
data only, have stripped metadata and are now included in source and the release
bundle. The joining capture now holds its synthetic worker until the screenshot
finishes, avoiding an intermittent capture of the following error screen.

The file review removed two personal staging paths from this log. No real device
identifiers or credentials were found in the reviewed publication inputs. Public
upstream copyright/provenance remains intact. Caches, virtual environments, logs,
keys, device state and generated builds are excluded from Git. The local source
directory was initialized on `main`; no commit, remote repository or push was
created. There was no existing project history to audit. See
[publication scope and first-push steps](docs/PUBLISHING.md).

The pinned SunFounder tree did not establish an overlay redistribution license,
so public source and archives exclude the binary. `scripts/install.sh` remains
the single installation entry point and now fetches the pinned overlay over HTTPS
for local installation, verifies SHA-256 and rejects incorrect cached files before
changing boot/display configuration. Recovery, credentials and existing kiosk and
tailnet security controls are preserved. Installer filesystem tests use explicit
synthetic overlay bytes. Downloading the blob does not establish distribution rights.

Executed validation:

- **35 Python tests passed** against the fresh host bundle, including five new
  download tests for checksum, size, HTTPS, cached-file and symlink handling.
- **14 native 480×320 captures passed** layout, masking, recovery and exact QR
  decoding checks. All images were visually reviewed. The README's relative
  image/document links resolve and PNGs contain no ancillary metadata.
- **Gitleaks 8.30.1 found no secrets** in the Git-visible source snapshot or rebuilt
  release contents, with redacted output and no custom allowlist. Supplemental
  checks found no personal home paths, actual test-device identifiers or private
  key material. Systemd instance names are not personal email addresses; upstream
  license authors and public repository names are intentional attribution.
- **actionlint 1.7.12 passed.** Python compilation and all shell syntax checks
  passed. The Linux arm64 executable is static and uses `-trimpath`; publication
  checks verify expected files, exclude the vendor blob and confirm anonymous tar
  ownership, safe archive members and stripped PNG metadata.
- **Clean Ubuntu 24.04 rehearsal passed** as an unprivileged user with Python 3.12
  and the current stable **Go 1.27.4**. Executed the CI shell commands with fresh
  dependencies: actionlint including ShellCheck, source scan, history scan of a
  disposable synthetic commit, Xvfb native captures/QR decoding, Go race tests,
  all 35 Python tests, arm64 build, checksum verification, archive extraction and
  secret/file checks on the extracted package. No source cache was required.
- **Live pinned vendor download passed** SHA-256 verification (2,600 bytes) in a
  temporary local directory; it was removed afterwards and not packaged.

The CI workflow runs on pushes, pull requests and manual dispatch. It uses
read-only repository permissions, nonpersistent checkout credentials, full-SHA
action pins, no deployment secrets and verified audit-tool downloads. It uploads
the install archive/checksum/integration patch and synthetic captures only after
checks pass. GitHub-hosted execution and artifact upload remain unverified until
the first push; the Ubuntu rehearsal does not claim otherwise.

No Pi services, network settings or credentials were changed during publication
preparation. The new install-time download path has not been installed on the Pi.
Physical screen/touch/camera, clean-image install/recovery, direct/DERP throughput,
concurrency and 24-hour acceptance remain pending. Earlier actual Pi evidence
below is unchanged and does not certify this publication package's deployment.

## Status QR for ts-redir — 2026-11-17

The status page now includes a management QR beside the connection details. It
encodes the exact full-name URL with port 8800 when available. Missing names or
names too dense for modules of at least three pixels use the Tailscale IPv4 URL.
Both text URLs remain available; a caption identifies the QR's name/IP choice.
Black modules, integer scaling and a four-module quiet border are preserved.
The QR contains no credentials or enrollment URL. It relies on the scanning
phone's existing tailnet connection and access policy.

Unchanged status polls preserve the QR canvas instead of redrawing during a scan.
Address/name changes replace it, and stopped/unavailable status removes it. A
failed status request clears the old QR; successful recovery restores it and
clears the error. Missing QR support leaves the typed URLs available. The existing
enrollment flow remains on its separate screen.

Executed checks:

- **30 Python tests passed** against the fresh package on the host and again in
  the extracted package on the actual Pi, with no skips. The URL tests explicitly
  exclude enrollment URLs and invalid/non-tailnet addresses; installation,
  reinstallation, recovery and existing security controls also pass.
- Native Tk smoke produced **14 synthetic 480×320 captures** and checked bounds,
  control size, credentials, status recovery and unchanged-QR stability. The
  rendered pixels were decoded with zxing-cpp 3.1.1 and Pillow 13.0.0, using qrcode
  8.2 for generation. Exact normal/renamed name URLs, missing/long-name IP fallback
  URLs and the separate fake enrollment URL decoded successfully. No QR was found
  in unavailable, unenrolled or missing-library captures. Captures were visually
  inspected, including the preserved enrollment screen. These are software tests,
  not phone-camera or physical display tests.
- The arm64 package rebuilt successfully; Go race tests passed (cached). Python
  compilation and shell syntax passed. All four service units validated on the
  Pi, and installation preflight passed. The QR decoder dependencies were added
  only to the host development environment, not the appliance.
- The earlier MagicDNS update is now installed on the Pi: installed UI and binary
  hashes match that release. Both IP and full-name HTTP requests return **200**.
  Seven real HTTP checks also confirmed **403** for unrelated Hosts and invalid
  mutation Origins, including cross-alias requests. No valid rule mutation was
  sent. Existing Tailscale, display and ts-redir services remain active.

The QR package is staged at
a private staging directory on the test Pi and its archive checksum is
verified. It uses the unified installer and includes the earlier fixes. Activation
still requires the user's sudo authentication; the QR UI is not yet installed.
Physical phone scanning and the full post-boot root kiosk audit remain pending.
No clean-image install, touch/escape test, throughput/direct/DERP measurement or
24-hour soak was performed in this step.

## MagicDNS management and status — 2026-11-17

Implemented entirely in TailBridge's integration over pinned ts-redir. Management
accepts the existing Tailscale IPv4 URL and this device's exact full MagicDNS name
on port 8800. The name is read from the local daemon's Self identity, checked
against the bound IP, and cached for 30 seconds with a three-second lookup limit.
Other hosts and cross-origin mutations, including between the two accepted aliases,
remain rejected. The socket/interface binding and firewall are unchanged.

The status page now shows both URLs in the existing dark neon theme, with explicit
IP fallback for unavailable or overlong names. The new status captures include
the normal, missing-name, long-name and unenrolled/error states. An initial capture
caught clipped unenrolled guidance; the corrected capture fits. All examples use
synthetic data. No physical screen or touch check is claimed.

The main installer also now replaces payload files by rename rather than
truncating the destination. This fixes reinstallation over a running executable
(`ETXTBSY`); the previous process keeps its old executable until reboot. A host
and Pi test actually runs a temporary executable while replacing it. This is
per-file replacement, not a transaction or automatic release rollback.

Executed checks:

- **28 Python tests passed** against the fresh build and again inside the staged
  package on the Pi, without skips. Installer recovery, original backup retention,
  credential/profile preservation, live executable replacement, local DNS identity
  validation and existing security checks are included.
- Go race tests passed, including Host/Origin rejection, same-alias mutation,
  local identity validation, malformed names and concurrent cache refresh/failure.
  The release binary is a static ARM aarch64 ELF.
- Native Tk smoke passed **11 synthetic captures**, bounds, minimum control size,
  credential masking/timeouts and app-only close behavior. The four changed status
  states were visually inspected; physical panel readability remains pending.
- Python compilation and shell syntax passed. All four service units validated
  on the Pi. Host unit validation cannot resolve the Pi-only `/opt/tailbridge`
  executables; it was not treated as a successful host check.
- The Pi is reachable again. Existing Tailscale, ts-redir and display services
  are active. The staged broker reads the expected current Self DNSName and
  Tailscale IPv4 from the actual local daemon. Installation preflight passes.
- Before activation, real tailnet HTTP requests returned **200 by IP and 403 by
  full name**. The client already resolves the correct MagicDNS name. This is the
  observed old-version defect, not a passing test of the new web service.

The SHA-256-verified package is staged under
a private staging directory on the Pi. At this initial
staging, activation required the user's sudo authentication through the unified
installer and reboot; no privileged files were changed by the staging step.
The subsequent status-QR session above confirmed this release was installed and
verified its live URL and Host/Origin behavior. The full root kiosk audit remains
pending. No clean-image installation,
physical escape/touch test, direct/DERP benchmark or 24-hour soak was performed.

## Unified installer — 2026-11-17

`scripts/install.sh` is now the sole installation entry point. The complete code
payload, first-boot fixes, neon UI, kiosk policy and tailnet-only ts-redir setup
are included in a fresh install. The login/SSH/account preflight previously used
by the kiosk patch now runs before the main installer makes system changes.
The separate boot-fix and kiosk-update scripts, and the kiosk-only configuration
mode, were removed. Reinstallation removes installed retired entry points while
retaining the original recovery baseline and user configuration. It requires a
planned reboot; automatic live-update rollback is not offered by this path.

Builds now assemble into an empty staging directory, test that new bundle, and
replace the generated release only after those checks succeed. The archive has
no retired patch scripts or Python bytecode caches and includes the current design
record. Screen behavior has not changed; idle blanking remains unimplemented.

Executed checks:

- **25 Python tests passed**, both during the build against the new staged bundle
  and from an independently extracted archive, with no skips. The complete
  temporary-root test installs the current runtime and policies, repeats the
  installation, restores the original configuration and Ctrl-Alt-Del alias,
  retains the original SysRq baseline, and preserves a synthetic network profile
  and customized environment file. Additional checks reject payload symlinks,
  unsafe UI accounts, autologin commands and missing SSH recovery.
- Go race tests passed (cached); the rebuilt executable is a static ARM aarch64 ELF.
- Python compilation, shell syntax and all four systemd unit validations passed.
- Archive inspection confirmed that only the unified installation workflow ships.

No live reinstall or clean-image boot was performed. SSH to the known Pi LAN
address returned **No route to host** during this session. Earlier actual-device
evidence below remains historical evidence, not validation of this fresh-install
workflow. No host networking, credentials or Pi settings were changed.

## Neon theme and kiosk update — 2026-11-16 historical patch deployment

The user requested a default dark 1980s/1990s cyberpunk palette and an app-only
screen with authenticated system access. Implemented near-black indigo surfaces,
cyan headings/readouts, magenta actions, orange errors and a static three-color
edge. All eight synthetic native captures were regenerated at 480×320. Text
contrast meets 4.5:1 for the tested pairs; control edges/focus meet 3:1. Keyboard
geometry, password masking and black-on-white QR rendering are retained.

Production rejects window-close requests. The update drops all UI capabilities
and supplementary groups, sets no_new_privs, disables keyboard SysRq and both
Ctrl-Alt-Del paths, and preserves the existing Xorg VT/termination restrictions.
The previous display release is backed up before activation and restored if the
runtime audit fails. Full recovery retains the original system configuration,
keyboard policy and SysRq value. Console autologin/custom login commands cause the
update to stop before changing the running installation.

Read-only checks on the live Pi during this update confirmed normal authenticated
getty commands, the nologin UI account, and the existing masked tty1. Tailscale now
reports Running with an assigned IPv4 address; ts-redir is active and its socket
is bound to that address on tailscale0:8800. No Wi-Fi credentials, Tailscale
enrollment link or private key was read. Activation initially required the user's
sudo authentication. During the subsequent temperature/screen-sleep request,
the installed runtime audit passed: app-only startup, login-gated consoles,
keyboard policy, capability-free/no_new_privs UI and authenticated SSH recovery.
The installed UI hash matches the staged source, with zero display restarts.

Host checks: 19 Python tests pass, including reversible kiosk configuration,
autologin rejection, color contrast and open-network failure guidance. The native
smoke passes all eight captures, layout bounds, 42px minimum controls, credential
timeouts and production window-close rejection. The arm64 build and Go race tests
pass. Physical display, touch and keyboard escape tests remain unperformed.

On the Pi, the staged source passed 18 Python tests; the full bundle-directory
round-trip test was skipped because its host build-directory layout is absent on
the Pi (that test passed on the host). Python compilation also passed on the Pi.
The final visual reviewer scored the open-network wording and design-record
corrections resolved, with a ship disposition limited to those fixes. Both design
records now match the implementation. All four systemd units validate on the host.

## Temperature and screen power inspection

The user reported warmth and asked about screen-off/tap-to-wake. A live CPU sensor
snapshot was **46.251°C**, with `vcgencmd get_throttled` reporting `0x0`. This is a
single observation, not a thermal/load test or a screen-on/off power comparison.
Linux exposes no devices under `/sys/class/backlight`; the installed SPI display
device tree has no backlight/LED GPIO. SunFounder's published pinout likewise lists
no backlight-control pin. Software blanking can hide pixels but must not be
described as switching off the LED backlight or proven to reduce heat. No hardware
wiring or power changes were attempted.

## Device installation session

The user authorized direct SSH installation. Read-only preflight confirmed a
Raspberry Pi 4 Model B Rev 1.4 running Trixie arm64, active NetworkManager,
approximately 24 GB free root storage, existing US regulatory configuration and
no current throttling flags. SSH currently uses wlan0; Ethernet is disconnected.
No hardware benchmark or serial-port process was found running.

The package was transferred, its SHA-256 verified, and extracted. The user
authenticated sudo in their own terminal and ran the prepared installer/reboot
command. No sudo password or SSH private key was read or shared with the agent.

After reboot, SSH returned on the original Wi-Fi connection. Remote evidence:

- Kernel `6.18.50+rpt-rpi-v8`; `fb_ili9486` framebuffer reports **480×320**.
- Xorg uses the SPI framebuffer and detects **ADS7846 Touchscreen** on event0.
- `tailbridge-display`, `tailbridge-network`, `tailbridge-firewall`, and
  `tailscaled` are active. Tk runs as the unprivileged `tailbridge` user.
- Tailscale reports `NeedsLogin`, with no assigned Tailscale address. ts-redir
  waits/retries without opening a management listener on another interface.
- The broker runtime directory is root:tailbridge 0750; the SSH user cannot read
  its socket or the private X authority file. No TCP X listener was observed.
- Read-only memory snapshot before installation: 1,844 MiB RAM, 1,682 MiB available,
  no throttling flags. This is an idle snapshot, not a load or capacity benchmark.
- After installation, idle RSS snapshots were 39,616 KiB for tailscaled, 59,868 KiB
  for Xorg, and 26,344 KiB for the Tk UI. Shared pages make these unsuitable for
  simply summing into a total; no traffic or concurrent-connection load was applied.

Real boot exposed `TailscaleIPs: null` before enrollment. The original status
adapter treated it as iterable and failed. The corrected adapter was tested on
the actual Pi and reports Wi-Fi connected / `NeedsLogin`; a regression test was
added. Xorg's input class was also narrowed to event devices to avoid attempting
evdev on the duplicate legacy mouse node. The user executed the prepared sudo
repair, which also exercises broker status/scanning under the touchscreen UID.
Installed file hashes match the tested sources. After the restart, both display
and broker remain active with zero restart counts and no new operation warnings.

Xorg logs a missing logind session because this dedicated root X server does not
use a desktop login session. It also reports the intentionally empty supplemental
config directory. These did not prevent framebuffer, calibrated event-device,
or application startup; visual appearance and actual touch remain user checks.

## Software milestone: ready for Pi acceptance testing

Implemented for Raspberry Pi 4, Raspberry Pi OS Trixie arm64, SunFounder
MHS35IPS 480×320. This replaces the removed NM-CYD-C5 implementation; no ESP
benchmark, physical result or recovery test is carried forward.

The screen opens Wi-Fi setup through systemd/Xorg without a desktop login manager.
ts-redir uses the official Tailscale daemon and listens on the Tailscale IPv4 address
and device, TCP 8800. Tailscale grants/ACLs provide management authentication.
Redirects use the Pi's LAN IP, Linux nftables, and private persisted rule state.

## Executed in this workspace

| Check | Result / scope |
| --- | --- |
| `python3 -m unittest discover -s tests -v` | **13 passed**. Bounded broker protocol, kernel-reported local UID, hostile SSIDs, security validation, mocked NM save/rollback, retained automatic checkpoint recovery, private atomic storage, boot configuration idempotence, file/symlink/absence recovery, complete file-only staged installation and restoration, and null Tailscale status before enrollment. |
| `go test -race ./...` on integrated pinned source | **Passed**. Seven web/persistence test functions; kernel test skipped in this ordinary run. HTTP Host/Origin/body/type controls, CSP matches rendered JavaScript, text-node rendering, durable restart/delete behavior, invalid saved rules rejected before firewall changes, destination/ingress/port restrictions, storage failure reporting. |
| `scripts/kernel_smoke.sh` | **Passed**. Real Linux nftables create/list/persist/delete in a new unprivileged user/network namespace, including a normal peer label. Forwarding guard accepted by `nft --check` in a separate empty namespace. The test refuses the host network namespace. This is host-kernel evidence, not Pi or Tailscale packet forwarding evidence. |
| Linux arm64 build | **Passed**. `CGO_ENABLED=0 GOOS=linux GOARCH=arm64`; ELF inspection confirms static ARM aarch64 executable, approximately 9.7 MiB. |
| Native UI smoke | **Passed** with synthetic data only. Eight actual 480×320 Tk window captures; Wi-Fi selection/paging, password masking/reveal expiry, both failed-join paths, hidden SSID, status, QR render and idle clearing. All widgets fit the viewport; all buttons at least 42 px high. |
| UI finish review | Reviewer found progress-text clipping and small controls; both fixes scored **resolved**, disposition **ship** for the reviewed native UI scope. Physical touch remains unverified. |
| Syntax and services | Python compileall and each shell file's `bash -n` passed. All four services passed `systemd-analyze verify` with executable paths relocated to the staged bundle. No services were installed or started on the host. |
| Vendor assets | Pinned display overlay and embedded Pico CSS SHA-256 checks passed. Full provenance and notices are in docs/THIRD-PARTY.md and bundle licenses/. |

Host environment: Debian 12, x86-64 with an existing X display. Python dependencies
for QR preview were installed only in the workspace virtual environment. The native
captures contain invented network names, documentation IPs and a deliberately fake
enrollment URL. No host Wi-Fi, real credentials, Tailscale login or serial port was
used. No host firewall/network settings were changed; real nft operations were
confined to disposable network namespaces.

## Not performed

- Visual screen inspection and physical touch calibration.
- New NetworkManager joins/rollback or saving a new Wi-Fi credential on the target,
  Tailscale QR enrollment, ACL enforcement or LAN rejection on the actual Pi.
- End-to-end TCP/UDP forwarding through real Tailscale direct or DERP paths.
- Throughput, CPU/RAM load, concurrent connection sweet spot, thermal or latency measurements.
- Physical recovery, repeated power interruption, or a 24-hour soak.

These remain unchecked in docs/TESTING.md. The host checks establish a runnable,
tested software package, not certified display compatibility or measured speed.
No irreversible eFuse/OTP/bootloader provisioning is included or performed.

## Artifacts and pins

- `build/tailbridge-pi-arm64.tar.gz` and adjacent `.sha256`: installable bundle.
- `build/ts-redir-integration.patch`: full integration diff, including new source/tests.
- `artifacts/*.png`: native UI evidence, regenerated by `tests/ui_smoke.py`.
- ts-redir: `935fda9def785f49dc1e5435388c6c344b8e68a1`.
- SunFounder LCD-show: `056fa9deda0167d05063c7abcccfc151cdc1f834`.

Recovery preserves original changed files, saved Wi-Fi profiles and Tailscale
identity. Credentials have root-restricted storage; SD-card encryption and
cryptographic memory erasure are not claimed. See docs/SECURITY.md for the precise
scope and the reserved management/recovery ports.
