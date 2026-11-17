# TailBridge for Raspberry Pi

## Product purpose
Turn the user's Raspberry Pi 4 (2 GB) and SunFounder 3.5-inch IPS SPI touch
display into a Wi-Fi-configurable entry point to selected tailnet services.

## Confirmed scope
- Raspberry Pi OS Trixie, 64-bit, confirmed by the user.
- Boot directly to Wi-Fi configuration without a Linux login manager.
- Landscape 480 × 320 touch interface with an on-screen keyboard.
- Use apoindevster/ts-redir for browser-managed redirections from the Pi's IP.
- Open management by the Pi's Tailscale IP or full tailnet name on port 8800;
  show both on the touchscreen status page.
- Include a status-page QR that opens the management URL directly on a phone
  already connected to the tailnet, without a separate enrollment step.
- User will perform physical screen/touch testing; actual remote boot and driver
  checks are recorded separately in RESULTS.md.
- Default dark retro 1980s/1990s cyberpunk theme with neon magenta, cyan and orange.
- The touchscreen hosts only TailBridge; system administration requires an
  authenticated login. SSH recovery is preserved.
- Previous ESP implementation was intentionally removed. This is a new project.

## Implementation choices
Python/Tk on a dedicated Xorg framebuffer session; NetworkManager over D-Bus;
official Tailscale service; pinned ts-redir bound only to tailscale0. The user
explicitly chose Tailscale access policy as the browser authentication layer;
there is no LAN-facing web gateway and no separate web password.
These are implementation decisions, not additional user-confirmed requirements.
Keep the established appliance flow: network list, password entry, connection
feedback and status. This is an operating interface, not a desktop workspace.

## Security and recovery
Keep credentials out of logs and process arguments. Restrict privileged local
commands, enforce tailnet-only management and same-origin mutations, keep recovery
over SSH, and preserve system files before installation. No irreversible fuses.
Linux storage protection is a separate design from the retired ESP key store.
