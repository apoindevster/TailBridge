# Security policy

TailBridge is an experimental appliance integration. Physical acceptance and
direct/DERP performance testing are still pending. The current development line
is the only supported version; use a current Raspberry Pi OS and Tailscale.

## Reporting a vulnerability

Use this repository's **Security → Advisories → Report a vulnerability** when
private reporting is enabled. If it is unavailable, open a public issue asking
the maintainer to enable private reporting, without exploit details or private
data. Do not post credentials, enrollment links, device identifiers, network
profiles, Tailscale state, packet captures or unredacted diagnostic output.

Include affected versions, expected/actual behavior and a minimal reproduction
using synthetic data. There is no guaranteed response time. The maintainer
should coordinate fixes and disclosure through the private advisory.

## Scope and operation

Read [the security architecture](docs/SECURITY.md) for the privilege boundaries,
tailnet-only management, forwarding constraints, credential handling and recovery.
Management access to TCP 8800 grants redirect administration; restrict it with
Tailscale policy. Protect SSH and physical access to the Pi and its SD card.

The installer does not program irreversible eFuses or OTP settings. Reinstalling
retains the original recovery baseline and private device state. Neither passing
CI nor a synthetic screenshot proves physical kiosk isolation or throughput.

Upstream ts-redir is deliberately pinned and patched. Update it through a reviewed
source change and rebuild; replacing only its binary drops TailBridge's controls.
Third-party notices and download boundaries are in [THIRD-PARTY.md](docs/THIRD-PARTY.md).
