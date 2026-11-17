# Native UI evidence

Run `.venv/bin/python tests/ui_smoke.py --decode-qr` (with Tk, qrcode, Pillow,
zxing-cpp and ImageMagick `import`
available) from the repository root. This captures only the synthetic application's
window: wifi, password, symbols, joining, failed-join, open-failed, status,
status-renamed, status-no-name, status-long-name, status-no-qr, status-error,
status-offline and enrollment. All 14 images are
480×320, not photographs of the SunFounder screen. Captures strip metadata before
being saved; publication checks reject unexpected PNG metadata. The source PNGs
are intentionally tracked so GitHub can render the README gallery. Never replace
them with captures from an enrolled device or your desktop.

The decoder checks the exact synthetic URL in each captured management/enrollment
QR and verifies that the other views contain none. This is a pixel-level software
check, not a phone-camera test of the physical screen. The enrollment QR contains
a deliberately fake URL. No real password, SSID,
Tailscale identity or host desktop is recorded. These files are development evidence
and are not assets rendered by the installed application.
