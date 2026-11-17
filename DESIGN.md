---
name: TailBridge touchscreen
description: A static neon console for native Wi-Fi setup and tailnet status.
colors:
  background: "#0D1021"
  panel: "#191E36"
  ink: "#EDF4FF"
  muted: "#ADBBD5"
  accent: "#FF64C8"
  line: "#647496"
  cyan: "#54E7F4"
  orange: "#FFAB57"
  selected: "#2A3553"
  qr-ink: "#000000"
  qr-paper: "#FFFFFF"
typography:
  headline:
    fontFamily: "DejaVu Sans Mono"
    fontSize: "24px"
    fontWeight: 700
  body:
    fontFamily: "DejaVu Sans"
    fontSize: "18px"
    fontWeight: 400
  label:
    fontFamily: "DejaVu Sans"
    fontSize: "14px"
    fontWeight: 400
  keyboard:
    fontFamily: "DejaVu Sans"
    fontSize: "19px"
    fontWeight: 400
rounded:
  square: "0px"
spacing:
  page-inset: "16px"
  keyboard-inset: "10px"
  field-inset: "6px"
  footer-gap: "12px"
  control-gap: "4px"
  key-gap: "3px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.background}"
    typography: "{typography.body}"
    rounded: "{rounded.square}"
    height: "42px"
  button-secondary:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.square}"
    height: "42px"
  button-primary-active:
    backgroundColor: "{colors.cyan}"
    textColor: "{colors.background}"
    typography: "{typography.body}"
    rounded: "{rounded.square}"
    height: "42px"
  button-secondary-active:
    backgroundColor: "{colors.selected}"
    textColor: "{colors.cyan}"
    typography: "{typography.body}"
    rounded: "{rounded.square}"
    height: "42px"
  button-disabled:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.muted}"
    typography: "{typography.body}"
    rounded: "{rounded.square}"
    height: "42px"
  network-row:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.square}"
    width: "448px"
    height: "48px"
  keyboard-key:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    typography: "{typography.keyboard}"
    rounded: "{rounded.square}"
    width: "43px"
    height: "42px"
  password-readout:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.square}"
    padding: "0px 6px"
    width: "354px"
    height: "38px"
  console-rail:
    width: "480px"
    height: "2px"
---

# Design System: TailBridge touchscreen

## Overview

**Creative North Star: "The neon setup console"**

TailBridge is a dedicated appliance interface for choosing Wi-Fi, entering a
password, checking a connection and enrolling the Pi in Tailscale. The approved
default is a dark retro 1980s/1990s futuristic cyberpunk console: near-black
indigo, raised indigo control faces and precise magenta, cyan and orange accents.
The fixed landscape surface gives each task one screen and keeps its next action
in a predictable place. The character comes from color, monospaced headings and
a thin three-color lower edge; all presentation stays static.

This document records the finished native Tk implementation in `tailbridge/ui.py`.
The target is the user's Raspberry Pi 4 with Raspberry Pi OS Trixie 64-bit and a
SunFounder 480 × 320 display. Large touch controls, clear feedback and credential
privacy govern the visual choices. This design system covers the local
app-only touchscreen; ts-redir's browser interface is outside its scope.

**Key Characteristics:**

- Fixed 480 × 320 composition with explicit on-screen keyboard layouts.
- Dark indigo layers, magenta primary actions, cyan headings and orange errors.
- Square, flat controls with large readable labels and visible outlines.
- Three network rows per page and predictable bottom actions.
- A static two-pixel cyan, magenta and orange console rail.
- Credential disclosure and connection feedback built into the task flow.

Evidence: the source was checked against `artifacts/wifi.png`, `password.png`,
`symbols.png`, `joining.png`, `failed-join.png`, `open-failed.png`, `status.png`,
`status-renamed.png`, `status-no-name.png`, `status-long-name.png`,
`status-no-qr.png`, `status-error.png`, `status-offline.png` and
`enrollment.png`, all under `artifacts/`. These are actual synthetic Tk
renders at 480 × 320. The finish review found no visual clipping; capture checks
enforce widget bounds and button heights of at least 42 px. Color-pair
calculations meet 4.5:1 for documented text states and 3:1 for resting control
outlines. These checks establish the captured layout and palette, not physical
Pi touch accuracy or display readability. Hardware interaction validation remains
pending.

## Colors

The neon palette separates the primary action, screen identity and recovery
message against the dark console. Frontmatter values are normative; the names
below explain their use.

### Primary

- **Neon magenta (`accent`):** enabled primary button faces and their resting
  outlines, plus the middle segment of the lower console rail. Primary text uses
  the near-black background color.

### Secondary

- **Electric cyan (`cyan`):** standard headings, the available tailnet management
  address, keyboard-focus highlights and the persistent credential-readout
  outline. Active primary buttons use cyan with dark text; active secondary
  buttons use cyan text on selected indigo. Cyan begins the rail.

### Tertiary

- **Bright orange (`orange`):** validation and connection-error text and the final
  rail segment. The source's `ERROR` aliases `ORANGE`; wording carries the error
  meaning alongside color.

### Neutral

- **Midnight indigo (`background`):** root window, text-label backgrounds and
  dark primary button text.
- **Raised indigo (`panel`):** secondary buttons, keyboard keys, the readout and
  disabled button faces. It is a lighter flat surface, without a shadow.
- **Ice white (`ink`):** body text, secondary button text and entered values.
- **Blue-gray (`muted`):** instructions, auxiliary status, placeholders and
  disabled button text.
- **Steel indigo (`line`):** one-pixel secondary and disabled button outlines.
- **Selected indigo (`selected`):** the active secondary button face. It is not
  a persistent selected-network marker.
- **QR black / QR white (`qr-ink`, `qr-paper`):** the enrollment matrix and its
  unobstructed quiet border, remaining black on white within the dark screen.

**The Neon Roles Rule.** Keep magenta for enabled primary actions, cyan for
headings and interaction cues, and orange for textual errors; the small console
rail is the shared three-color signature.

Implemented contrast ratios are 17.05:1 for body text on the root, 14.83:1 for
body text on a panel, 9.74:1 for muted text on the root, 8.47:1 for muted or
disabled text on a panel, 7.10:1 for primary text on magenta, 12.68:1 for primary
active text on cyan and 8.15:1 for cyan secondary-active text on selected indigo.
Orange error text reaches 10.07:1 on the root. Resting steel outlines reach
3.50:1 against the panel and 4.02:1 against the root; cyan readout outlines reach
11.02:1 against the panel. QR black on white is 21:1.

## Typography

Standard headings use DejaVu Sans Mono in cyan. Body, controls, compact titles
and the management URL use DejaVu Sans. The mono heading establishes the retro
console character while the proportional body leaves room for network names
and touch labels. Tk scaling is explicitly set to 1.0 and negative source font
sizes mean pixels. Line height and letter spacing are left to Tk.

| Role | Font / size / weight | Use |
| --- | --- | --- |
| Headline | DejaVu Sans Mono, 24 px bold | Choose Wi-Fi, Network security, Connecting…, TailBridge and Connect Tailscale |
| Body | DejaVu Sans, 18 px regular | Network names, normal button labels, status and input contents |
| Compact title | Body role: DejaVu Sans, 18 px regular | Password and hidden-network headers, leaving room for keyboard and feedback |
| Label | DejaVu Sans, 14 px regular | Instructions, notices, management URLs, IP detail and Show / Hide / Clear buttons |
| Keyboard | DejaVu Sans, 19 px regular | Individual character keys; keyboard utility buttons use body type |

Long network names are measured and ellipsized, not resized. Network rows allow
310 px for the name before signal strength; screen headers and other network
labels allow 448 px. The complete encoded network identity remains in state.

## Layout

The native window is fixed at 480 × 320 with resizing disabled. Production mode
is borderless, fullscreen and hides the pointer; the preview can be windowed.
The display hosts only TailBridge. Production ignores window-manager close and
Alt-F4; system administration belongs to an authenticated login through SSH or
the separate system controls. There are no responsive breakpoints or alternate
orientations. Larger desktop or mobile layouts must not be inferred from this
compact implementation.

Most content begins 16 px from the left, ends 16 px from the right and uses
448 px of width. Ordinary buttons are 42 px high. Network and hidden-security
choice rows are 48 px high.

- **Network list:** heading at y=8, subtitle at y=46, then up to three rows at
  y=74, 124 and 174. Pagination occupies y=224; Hidden network and Rescan begin
  at y=270. Home sits at the upper right.
- **Home:** the unlocked landing page has three 448 × 54 px buttons at x=16,
  y=96, 164 and 232: Lock, Status and Wi-Fi. Lock uses the existing primary style.
- **PIN lock:** the masked 204 × 42 px readout at (16, 90) and notices form a
  left column. A numeric keypad uses 68 × 52 px keys at x=248, 322 and 396, on a
  58 px vertical pitch from y=72; Delete, 0 and Clear occupy the last row at
  y=246. Unlock is 204 × 48 px at (16, 254). No PIN reveal control is provided.
- **Password / hidden network:** a 28 px title region at y=0, a 21 px instruction
  or error line at y=28 and a 354 × 38 px readout at (16, 52). Show / Hide or
  Clear is a separate 86 × 42 px control at (378, 50).
- **Keyboard:** three centered character rows start at y=96, 139 and 182.
  Character keys are 43 × 42 px on a 46 px horizontal pitch and a 43 px vertical
  pitch. Utility controls start at y=225; Cancel and Connect / Next start at
  y=272. The final actions are 180 and 256 px wide with a 12 px gap.
- **Other screens:** bottom actions normally start at y=270. The status screen
  separates Wi-Fi identity (y=54), local address (y=86), Tailscale state (y=122),
  numeric management URL (y=153), scanning caption (y=183), and full MagicDNS URL
  (y=212) into a reading sequence. While Running, the first five rows use a 280 px
  left column and the management QR occupies a 156 px square at (308, 54). Both
  URLs use the 14 px small font; the name keeps the full 448 px row width. An
  overlong name is ellipsized with explicit guidance to scan or use the complete
  IP URL. The tailnet hint or an error occupies y=240. When not ready, the QR is
  absent, content uses the full width, guidance begins at y=216, and an optional
  error remains at y=242. Missing QR support leaves both typed URLs available.
- **QR rendering:** black square modules on white, centered with integer-pixel
  scaling and at least four quiet modules on every side. Status prefers the
  name URL; if it would need modules smaller than 3 px, it uses the IP URL.
  Enrollment uses a 192 px square at (16, 58), with instructions beginning at
  x=228. No decorative styling is applied to either code.

The console rail occupies y=318–319 without taking touch space: cyan spans
x=0–239, magenta x=240–399 and orange x=400–479. These three static segments are
240, 160 and 80 px wide. Credential actions end at y=314; other footer actions
end at y=312, leaving clear space before the rail.

## Elevation & Depth

The interface has no shadows, gradients, glow, scanlines, texture or decorative
animation. Raised indigo faces and thin outlines distinguish controls from the
near-black canvas; the selected surface provides a further tonal step only
while a secondary button is active. Changes of page and button state are
immediate. The narrow neon rail carries the console signature without movement
or additional display refresh work.

**The Static Console Rule.** Express the retro theme through the established
palette, typography and fixed rail; preserve immediate state changes and the
untextured canvas.

## Shapes

Controls are rectangular with square corners. Buttons use flat relief, no
beveled border and a one-pixel highlight outline. The readout has no native
beveled border; its one-pixel cyan highlight is always present, with a 6 px
horizontal inset. This highlight does not imply an editable native Entry or a
separate focused-field state. QR modules retain square edges and an unobstructed
four-module white quiet border.

## Components

### Buttons and navigation

Primary actions use magenta with dark text and a matching magenta resting
outline; secondary actions use raised indigo with ice-white text and a steel
outline. Native active primary buttons use cyan with dark text. Active secondary
buttons use selected indigo with cyan text. Keyboard focus changes the one-pixel
highlight to cyan. There is no animated hover treatment or pressed movement.

Disabled primary and secondary actions both use a raised indigo face, muted
text and a steel outline. Enabled buttons are focusable; disabled buttons are
excluded from native keyboard focus. Removing magenta from a disabled primary
action makes its unavailable state visible without compromising label contrast.

Back, Cancel, Home, Lock, Status and Wi-Fi are explicit labeled controls. The
screen does not use a persistent navigation bar. Startup requires the PIN and
opens Home; the network list and status return to Home through their upper-right
button. The lower actions carry the current task forward or back. The touchscreen
has no exit or system-administration action.

Lock clears private visible state immediately. PIN entry is always masked, clears
on submission and after 30 seconds without input, and uses the existing orange
notice treatment for cooldown and recovery errors. Keypad and Unlock availability
reflect broker readiness; authentication is required before leaving the lock
screen. No automatic idle lock or screen blanking is configured.

### Network rows and security choices

Each network is a full-width button containing the shortened SSID and signal
percentage. Three are visible at once, with previous/next controls and disabled
end states. A scan resets the offset. Selecting a personal network opens password
entry; an open network opens a trust warning before Connect. Enterprise and
legacy networks receive a message directing setup through SSH. Hidden networks
first ask for security, then the network name, then a password when required.

### Credential readout and keyboard

The readout is a Tk label backed by application state, not an editable native
Entry widget. Touch input comes from the keyboard; physical typing, Backspace,
Return and Escape are also handled. Long values display their trailing portion
within the measured 346 px text budget.

Passwords are masked by default. Show becomes Hide during disclosure, which
expires after 15 seconds. Navigation clears the value and disclosure state;
120 seconds without touch or physical-key input returns password or hidden-name
entry to the network list and clears the value. Hidden network names are visible.
Submitting a connection clears the password from the visible UI state before
the background request runs.

The keyboard provides lowercase, uppercase, numeric and symbol pages. The mode
key cycles lowercase/uppercase to numeric, then symbols, then lowercase. Shift
switches lowercase to uppercase and otherwise returns to lowercase. Space and
Delete keep their positions; hidden-name entry also has Clear. Do not remove
symbol access to simplify the keyboard.

### Joining, errors and refresh

Joining replaces the form with a clear in-progress page and an explanation that
IP acquisition may take about a minute. It explains the connection recovery
behavior without adding a progress percentage. A failed request returns to the
appropriate password or open-network page with a textual orange error; password
entry is empty on return. Open-network failure guidance refers to signal and
retry, without asking for a password. Validation errors stay on the entry screen.

Network work runs off the Tk thread. Completion is checked every 50 ms. Status
polling begins after 4 seconds, then repeats every 5 seconds while eligible and
idle. Status polls run on Home, the network list, status and enrollment pages;
the locked page polls only authentication metadata. Polls do not redraw the
network list or change its selected page. Typing is not interrupted by status
refresh.

### Status and Tailscale enrollment

Status distinguishes the Pi's Wi-Fi address from its tailnet management address.
When Tailscale is Running with an address, it displays `http://<tailnet-ip>:8800`
and, when available, `http://<full-tailnet-name>:8800`. A QR beside the connection
details opens ts-redir on a phone already connected to the tailnet. Its caption
identifies whether the name or IP is encoded. Missing names and names too long
for a scannable status QR use the complete IP URL; shortened visible names have
explicit guidance to scan or type the IP. Unchanged status leaves the QR canvas
intact; changed addresses replace it, and status errors remove it. This
reflects ts-redir bound to `tailscale0`; it does not introduce a LAN web interface.

Tailscale setup has a Start sign-in action, a waiting state, then an authorization
QR with private-screen guidance. Start sign-in is disabled while busy or already
Running. A missing QR dependency produces an SSH recovery instruction. The
rendered enrollment example documents layout; successful scanning and real
authorization were not established by the screenshots.

## Do's and Don'ts

### Do:

- **Do** preserve the fixed 480 × 320 composition and test every changed state at that size.
- **Do** use cyan 24 px bold DejaVu Sans Mono for standard headings and 18 px DejaVu Sans for credential headers.
- **Do** keep magenta primary actions legible with dark text, and switch disabled actions to panel and muted colors.
- **Do** retain 48 px network rows, 42 px action heights and 43 × 42 px character keys.
- **Do** preserve the two-pixel rail at y=318 and the black-on-white QR with its four-module quiet border.
- **Do** keep errors textual, preserve full network identity and clear password disclosure on navigation.
- **Do** keep the touchscreen app-only and preserve authenticated administration and SSH recovery.
- **Do** validate touch accuracy and readability on the actual SunFounder display before making hardware usability claims.

### Don't:

- **Don't** add decorative animation, glow, scanlines, shadows or desktop-style chrome to this appliance flow.
- **Don't** let status refresh interrupt credential entry or reset network pagination.
- **Don't** expose passwords by default or omit numeric and symbol keyboard pages.
- **Don't** recolor the QR to match the neon palette or cover its quiet border.
- **Don't** treat desktop captures, demo data or browser component previews as physical Pi validation.
- **Don't** apply this touchscreen system as an unsolicited redesign of ts-redir's browser interface.
