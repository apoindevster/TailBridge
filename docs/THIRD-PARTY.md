# Source provenance

- [ts-redir](https://github.com/apoindevster/ts-redir), revision
  `935fda9def785f49dc1e5435388c6c344b8e68a1`, MIT. Its license is included under
  `licenses/ts-redir-MIT.txt` in the source and bundle. Go dependencies use upstream go.sum.
  Integration sources and tests live in `integrations/ts-redir`; preparation fails
  if the expected upstream source differs.
- [Pico CSS 2.0.0-alpha1](https://github.com/picocss/pico/tree/v2.0.0-alpha1), MIT,
  embedded as in upstream ts-redir, with its license included. CSS SHA-256:
  `4c4befaa02d5ccf8756c406283945591a623d023c6843ae734b1aa8633c83958`.
- [SunFounder LCD-show](https://github.com/sunfounder/LCD-show/tree/056fa9deda0167d05063c7abcccfc151cdc1f834),
  revision `056fa9deda0167d05063c7abcccfc151cdc1f834`, supplies the unmodified
  `usr/mhs35ips-overlay.dtb` and the landscape calibration values. Overlay SHA-256:
  `cf8ea1ad0fb4e8e3246bdd9bccd6ce2806dd4b163dddfaf1cdd3a31b3cbb7cd5`.
  A redistribution license for this overlay has not been established in the pinned
  vendor tree. **Source and public release packages exclude the binary.** The
  unified installer obtains it directly from the vendor over HTTPS for local
  installation and verifies the pinned SHA-256 before changing display settings.
  `scripts/fetch_display.py` can also prepare that file before an offline install;
  signed OS packages still need to be available. A preexisting file with a wrong
  hash is rejected. Downloading it does not grant redistribution rights; review
  the vendor's terms before sharing a modified bundle or image. The general vendor
  installation script is not executed.
  [Hardware/driver documentation](https://docs.sunfounder.com/projects/35-ips-screen/en/latest/).
- Tailscale is installed from its [official signed Debian repository](https://pkgs.tailscale.com/stable/#debian-trixie).
  NetworkManager, Tk, Xorg, evdev, qrcode and nftables are installed from signed OS
  repositories. Their distribution packages retain their own copyright notices.

This project is a Raspberry Pi appliance integration. It is not an official
SunFounder or Tailscale product, and it makes no inherited ESP benchmark claims.

TailBridge's original source is MIT licensed; see the root LICENSE. Build-time
module notices are collected into `licenses/go-modules`, with Go's own license
alongside them. The screenshot tooling in requirements-dev.txt and the audit
tools are development dependencies, not shipped executables on the Pi. Their
upstream licensing remains unchanged.
