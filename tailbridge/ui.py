"""480x320 touch appliance. --demo never contacts NetworkManager or Tailscale."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import queue
import time
import tkinter as tk
from tkinter import font

from .common import LockedError, UserError, management_urls, request, validate_wifi
from .lock import valid_pin

# A static neon console: no animation or screen texture competing with small text.
BG, PANEL, INK, MUTED = "#0D1021", "#191E36", "#EDF4FF", "#ADBBD5"
ACCENT, CYAN, ORANGE = "#FF64C8", "#54E7F4", "#FFAB57"
LINE, SELECTED, ERROR = "#647496", "#2A3553", ORANGE


class Demo:
    def __init__(self):
        self.connected = False
        self.session = ''

    def __call__(self, command, **data):
        if command in ('lock', 'lock_status'):
            if command == 'lock':
                self.session = ''
            return {'configured': True, 'retry_after': 0}
        if command == 'unlock':
            # Synthetic preview only. Production has no default PIN.
            if data.get('pin') == '123456':
                self.session = 'synthetic-preview-session-only'
                return {'unlocked': True, 'session': self.session}
            return {'unlocked': False, 'configured': True, 'retry_after': 2}
        if not self.session or data.get('session') != self.session:
            raise LockedError('Screen locked. Enter your PIN.')
        if command == "scan":
            return [{"ssid": name, "ssid_hex": name.encode().hex(), "security": security, "strength": strength}
                    for name, security, strength in [("Workshop Wi-Fi", "wpa-psk", 92), ("Guest network", "open", 68),
                                                     ("A long network name for testing", "sae", 51), ("Fourth network", "wpa-psk", 31)]]
        if command == "connect":
            validate_wifi(data["ssid_hex"], data["security"], data["password"])
            self.connected = True
            return {"connected": True}
        if command == "status":
            return {"connected": self.connected, "ssid": "Workshop Wi-Fi" if self.connected else "",
                    "ipv4": ["192.0.2.40"] if self.connected else [], "enabled": True,
                    "hardware_enabled": True, "tailnet": {"state": "Running" if self.connected else "NeedsLogin",
                    "dns_name": "ts-redir.example-tailnet.ts.net" if self.connected else "",
                    "ipv4": ["100.100.20.40"] if self.connected else [], "auth_url": ""}}
        if command == "login":
            return {"started": True}
        raise UserError("Unknown demo action.")


class App:
    def __init__(self, root, client=request, demo=False, fullscreen=True):
        self.root, self.client, self.demo = root, client, demo
        root.title("TailBridge preview" if demo else "TailBridge")
        root.geometry("480x320")
        root.resizable(False, False)
        root.configure(bg=BG)
        if fullscreen:
            root.overrideredirect(True)
            root.attributes("-fullscreen", True)
            root.configure(cursor="none")
        root.tk.call("tk", "scaling", 1.0)
        self.body = font.Font(family="DejaVu Sans", size=-18)
        self.small = font.Font(family="DejaVu Sans", size=-14)
        self.heading = font.Font(family="DejaVu Sans Mono", size=-24, weight="bold")
        self.keyfont = font.Font(family="DejaVu Sans", size=-19)
        self.work = ThreadPoolExecutor(max_workers=1)
        self.completed = queue.Queue()
        self.busy, self.closed = False, False
        self.networks, self.status, self.page = [], {}, "locked"
        self.session, self.pin_configured = '', False
        self.pending_lock, self.next_lock_retry = True, 0
        self.scan_pending = False
        self.retry_deadline, self.lock_error = 0, False
        self.offset, self.generation = 0, 0
        self.selected, self.value, self.keyboard_mode = None, "", "abc"
        self.revealed, self.last_touch, self.reveal_until = False, time.monotonic(), 0
        self.notice = ""
        self.root.bind("<Key>", self.physical_key)
        self.root.bind_all("<ButtonPress>", self.touch, add="+")
        self.root.protocol("WM_DELETE_WINDOW", self.window_close)
        self.root.bind("<Alt-F4>", self.window_close)
        self.render()
        self.send_lock()
        self.render()
        root.after(50, self.pump)
        root.after(4000, self.poll)

    def touch(self, event=None):
        self.last_touch = time.monotonic()

    def close(self):
        self.closed = True
        self.value = ""
        self.session = ''
        self.work.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()

    def window_close(self, event=None):
        # Only synthetic previews can be dismissed from the screen. Production
        # shutdown belongs to authenticated system administration through SSH.
        if self.demo:
            self.close()
        return "break"

    def short(self, text, width, selected_font=None):
        selected_font = selected_font or self.body
        text = str(text)
        if selected_font.measure(text) <= width:
            return text
        while text and selected_font.measure(text + "…") > width:
            text = text[:-1]
        return text + "…"

    def label(self, text, x, y, w, h, size=None, color=INK, anchor="w"):
        item = tk.Label(self.root, text=text, bg=BG, fg=CYAN if size is self.heading else color, font=size or self.body,
                        anchor=anchor, justify="left", wraplength=w - 6)
        item.place(x=x, y=y, width=w, height=h)
        return item

    def button(self, text, action, x, y, w, h=42, primary=False, disabled=False, size=None):
        item = tk.Button(self.root, text=text, command=action, font=size or self.body,
                         bg=ACCENT if primary and not disabled else PANEL, fg=BG if primary else INK,
                         activebackground=CYAN if primary else SELECTED, activeforeground=BG if primary else CYAN,
                         disabledforeground=MUTED, relief="flat", bd=0, highlightthickness=1,
                         highlightbackground=ACCENT if primary and not disabled else LINE,
                         highlightcolor=CYAN, takefocus=not disabled)
        item.place(x=x, y=y, width=w, height=h)
        if disabled:
            item.configure(state="disabled")
        return item

    def navigate(self, page):
        if not self.session:
            return
        if self.busy and self.page == "joining":
            return
        self.value = ""
        self.revealed = False
        self.notice = ""
        self.page, self.generation = page, self.generation + 1
        self.render()
        if page == "status" and not self.busy:
            self.call("status", self.updated)
        elif page == 'networks':
            self.scan_pending = True
            if not self.busy:
                self.rescan()

    def lock_screen(self):
        # Hide private data immediately, even if a prior status call is finishing.
        # Its callback is invalidated; the broker lock runs before any new unlock.
        self.session, self.value, self.notice = '', '', ''
        self.networks, self.status, self.selected = [], {}, None
        self.revealed, self.pin_configured = False, False
        self.page, self.generation = 'locked', self.generation + 1
        self.pending_lock, self.next_lock_retry = True, 0
        self.scan_pending = False
        self.render()
        self.send_lock()

    def send_lock(self):
        if not self.busy and self.pending_lock and time.monotonic() >= self.next_lock_retry:
            self.next_lock_retry = time.monotonic() + 5
            self.call('lock', self.locked)

    def locked(self, result):
        self.pending_lock, self.notice, self.lock_error = False, '', False
        self.lock_state(result)
        self.render()

    def lock_state(self, result):
        configured = result.get('configured') is True
        changed = self.pin_configured != configured
        self.pin_configured = configured
        self.retry_deadline = time.monotonic() + min(60, max(0, int(result.get('retry_after', 0))))
        if self.lock_error:
            self.notice, self.lock_error = '', False
        if changed:
            self.render()
        self.update_lock()

    def unlock_pin(self):
        if self.busy or self.pending_lock or not self.pin_configured or time.monotonic() < self.retry_deadline:
            return
        if not valid_pin(self.value):
            self.notice = 'Enter 6–12 digits.'
            self.update_lock()
            return
        pin, self.value = self.value, ''
        self.notice = 'Checking PIN…'
        self.call('unlock', self.unlocked, pin=pin)
        self.render()

    def unlocked(self, result):
        if result.get('unlocked') is True and isinstance(result.get('session'), str) and result['session']:
            self.session = result['session']
            self.last_touch = time.monotonic()
            self.navigate('home')
        else:
            self.notice = 'Incorrect PIN.'
            self.lock_state(result)
            self.render()

    def update_lock(self):
        if self.page != 'locked' or not hasattr(self, 'lock_notice'):
            return
        remaining = max(0, int(self.retry_deadline - time.monotonic() + 0.999))
        if self.pending_lock:
            message = self.notice or 'Securing screen…'
        elif not self.pin_configured:
            message = self.notice or 'PIN setup required.\nRun installer through SSH.'
        elif remaining:
            message = ('Incorrect PIN.\n' if self.notice == 'Incorrect PIN.' else '') + 'Try again in %ds.' % remaining
        else:
            message = self.notice
        if self.lock_notice.cget('text') != message:
            self.lock_notice.configure(text=message)
        state = 'normal' if self.pin_configured and not self.pending_lock and not self.busy else 'disabled'
        for key in self.pin_keys:
            if key.cget('state') != state:
                key.configure(state=state)
        unlock_state = state if valid_pin(self.value) and not remaining else 'disabled'
        if self.unlock_button.cget('state') != unlock_state:
            self.unlock_button.configure(state=unlock_state,
                                         bg=ACCENT if unlock_state == 'normal' else PANEL,
                                         highlightbackground=ACCENT if unlock_state == 'normal' else LINE)

    def call(self, command, done, **kwargs):
        if self.busy:
            return
        self.busy = True
        generation = self.generation
        if command in ('status', 'scan', 'login', 'connect'):
            kwargs['session'] = self.session

        def operation():
            locked = False
            try:
                result, error = self.client(command, **kwargs), None
            except LockedError:
                result, error, locked = None, 'Screen locked. Enter your PIN.', True
            except UserError as exc:
                result, error = None, str(exc)
            except Exception:
                result, error = None, "Service unavailable. Check installation through SSH."
            finally:
                kwargs.clear()
            self.completed.put((generation, done, result, error, command, locked))

        self.work.submit(operation)

    def pump(self):
        if self.closed:
            return
        try:
            generation, done, result, error, command, locked = self.completed.get_nowait()
            self.busy = False
            if generation == self.generation:
                if locked:
                    self.lock_screen()
                elif error:
                    self.notice = error
                    if self.page == 'locked':
                        self.notice = 'Lock unavailable.\nCheck setup through SSH.'
                        self.pin_configured, self.lock_error = False, True
                    if command == "status":
                        self.status["tailnet"] = {"state": "Unavailable"}
                    if self.page == "joining":
                        self.page = "open" if self.selected["security"] == "open" else "password"
                    self.render()
                else:
                    done(result)
        except queue.Empty:
            pass
        now = time.monotonic()
        if self.revealed and now >= self.reveal_until:
            self.revealed = False
            self.update_field()
        if self.page in ("password", "hidden") and now - self.last_touch > 120:
            self.navigate("networks")
        if self.page == 'locked':
            if self.value and now - self.last_touch > 30:
                self.value = ''
                self.update_field()
            self.send_lock()
            self.update_lock()
        elif self.page == 'networks' and self.scan_pending and not self.busy:
            self.rescan()
        self.root.after(50, self.pump)

    def poll(self):
        if self.closed:
            return
        if not self.busy and self.page == 'locked' and not self.pending_lock:
            self.call('lock_status', self.lock_state)
        elif not self.busy and self.page in ("home", "networks", "status", "tailnet"):
            self.call("status", self.updated)
        self.root.after(5000, self.poll)

    def updated(self, result):
        changed = self.status != result or (self.page == "status" and bool(self.notice))
        if self.page == "status":
            self.notice = ""
        self.status = result
        # Keep the QR stable while a phone scans it; no redraw for an idle poll.
        if self.page == "tailnet" or (self.page == "status" and changed):
            self.render()

    def scanned(self, result):
        self.networks, self.offset = result, 0
        self.notice = "" if result else "No networks found. Rescan or add a hidden network."
        self.render()

    def rescan(self):
        if not self.busy:
            self.scan_pending = False
            self.notice = "Scanning for networks…"
            self.call("scan", self.scanned)
            self.render()

    def select(self, item):
        if self.busy or not self.session:
            return
        self.selected, self.value, self.keyboard_mode = dict(item), "", "abc"
        self.notice, self.revealed = "", False
        self.generation += 1
        self.page = "open" if item["security"] == "open" else "password"
        if item["security"] == "unsupported":
            self.page = "unsupported"
        self.render()

    def hidden_security(self, security):
        self.selected = {"security": security, "hidden": True}
        self.navigate("hidden")

    def join(self):
        if self.busy or not self.session:
            return
        if self.page == "hidden":
            raw = self.value.encode("utf-8")
            if not 1 <= len(raw) <= 32:
                self.notice = "Use a network name of 1–32 bytes."
                self.render()
                return
            self.selected.update(ssid=self.value, ssid_hex=raw.hex())
            self.navigate("open" if self.selected["security"] == "open" else "password")
            return
        try:
            validate_wifi(self.selected["ssid_hex"], self.selected["security"], self.value)
        except UserError as exc:
            self.notice = str(exc)
            self.render()
            return
        password, self.value, self.revealed = self.value, "", False
        self.page, self.notice = "joining", ""
        self.generation += 1
        self.render()
        self.call("connect", self.joined, ssid_hex=self.selected["ssid_hex"],
                  security=self.selected["security"], password=password, hidden=self.selected.get("hidden", False))

    def joined(self, result):
        self.navigate("status")

    def key(self, char):
        if self.page == 'locked':
            if self.busy or not self.pin_configured or self.pending_lock:
                return
            if char == 'BACK':
                self.value = self.value[:-1]
            elif char == 'CLEAR':
                self.value = ''
            elif char in '0123456789' and len(char) == 1 and len(self.value) < 12:
                self.value += char
            if self.notice == 'Incorrect PIN.':
                self.notice = ''
            self.update_field()
            self.update_lock()
            return
        if char == "BACK":
            self.value = self.value[:-1]
        elif char == "CLEAR":
            self.value = ""
        elif len((self.value + char).encode()) <= (32 if self.page == "hidden" else 64):
            self.value += char
        self.update_field()

    def physical_key(self, event):
        if self.page == 'locked':
            self.touch()
            if event.keysym == 'BackSpace':
                self.key('BACK')
            elif event.keysym in ('Return', 'KP_Enter'):
                self.unlock_pin()
            elif event.keysym == 'Escape':
                self.key('CLEAR')
            elif event.char:
                self.key(event.char)
            return 'break'
        if self.page not in ("password", "hidden"):
            return
        self.touch()
        if event.keysym == "BackSpace":
            self.key("BACK")
        elif event.keysym == "Return":
            self.join()
        elif event.keysym == "Escape":
            self.navigate("networks")
        elif event.char and event.char.isprintable():
            self.key(event.char)
        return "break"

    def toggle_reveal(self):
        self.revealed = not self.revealed
        self.reveal_until = time.monotonic() + 15
        self.update_field()

    def update_field(self):
        if self.page == 'locked' and hasattr(self, 'field'):
            self.field.configure(text='•' * len(self.value) or 'PIN', fg=INK if self.value else MUTED)
            return
        if self.page not in ("password", "hidden") or not hasattr(self, "field"):
            return
        shown = self.value if self.page == "hidden" or self.revealed else "•" * len(self.value)
        while self.body.measure(shown) > 346:
            shown = shown[1:]
        self.field.configure(text=shown or ("Network name" if self.page == "hidden" else "Wi-Fi password"),
                             fg=INK if shown else MUTED)
        if hasattr(self, "show_button") and self.page == "password":
            self.show_button.configure(text="Hide" if self.revealed else "Show")

    def keyboard(self):
        modes = {"abc": ["qwertyuiop", "asdfghjkl", "zxcvbnm"],
                 "ABC": ["QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"],
                 "123": ["1234567890", "@#$%&*-+", "_!?/.,:"],
                 "sym": ["[]{}()<>\\|", "'\"`~^=;", "$&%#@!?"]}
        for row, chars in enumerate(modes[self.keyboard_mode]):
            start = (480 - len(chars) * 46) // 2
            for column, char in enumerate(chars):
                self.button(char, lambda c=char: self.key(c), start + column * 46, 96 + row * 43, 43, 42, size=self.keyfont)
        mode_label = "123" if self.keyboard_mode in ("abc", "ABC") else ("#+=" if self.keyboard_mode == "123" else "abc")
        next_mode = "123" if self.keyboard_mode in ("abc", "ABC") else ("sym" if self.keyboard_mode == "123" else "abc")
        self.button(mode_label, lambda: self.change_keys(next_mode), 10, 225, 72)
        self.button("Shift", lambda: self.change_keys("ABC" if self.keyboard_mode == "abc" else "abc"), 86, 225, 76)
        self.button("Space", lambda: self.key(" "), 166, 225, 158)
        self.button("Delete", lambda: self.key("BACK"), 328, 225, 142)

    def change_keys(self, mode):
        self.keyboard_mode = mode
        self.render()

    def render(self):
        for widget in self.root.winfo_children():
            widget.destroy()
        # The three-color edge gives the compact console its identity without
        # consuming touch space or adding redraw work to the SPI display.
        for x, width, color in ((0, 240, CYAN), (240, 160, ACCENT), (400, 80, ORANGE)):
            tk.Frame(self.root, bg=color).place(x=x, y=318, width=width, height=2)
        page = self.page
        if page == 'locked':
            self.label('Screen locked', 16, 10, 448, 36, self.heading)
            self.label('Enter your PIN', 16, 54, 204, 26, self.small, MUTED)
            self.field = self.label('', 16, 90, 204, 42)
            self.field.configure(bg=PANEL, padx=6, highlightthickness=1, highlightbackground=CYAN)
            self.lock_notice = self.label('', 16, 140, 204, 70, self.small, ORANGE)
            self.label('Forgot PIN? Use SSH.', 16, 214, 204, 26, self.small, MUTED)
            self.pin_keys = []
            for n, digit in enumerate('123456789'):
                self.pin_keys.append(self.button(digit, lambda d=digit: self.key(d),
                                                248 + (n % 3) * 74, 72 + (n // 3) * 58, 68, 52, size=self.keyfont))
            for n, (label, key) in enumerate((('Delete', 'BACK'), ('0', '0'), ('Clear', 'CLEAR'))):
                self.pin_keys.append(self.button(label, lambda k=key: self.key(k),
                                                248 + n * 74, 246, 68, 52, size=self.small if n != 1 else self.keyfont))
            self.unlock_button = self.button('Unlock', self.unlock_pin, 16, 254, 204, 48, primary=True, disabled=True)
            self.update_field()
            self.update_lock()
        elif page == 'home':
            self.label('TailBridge', 16, 12, 448, 36, self.heading)
            self.label('Choose an action.', 16, 52, 448, 26, self.small, MUTED)
            self.button('Lock', self.lock_screen, 16, 96, 448, 54, primary=True)
            self.button('Status', lambda: self.navigate('status'), 16, 164, 448, 54)
            self.button('Wi-Fi', lambda: self.navigate('networks'), 16, 232, 448, 54)
        elif page == "networks":
            self.label("Choose Wi-Fi", 16, 8, 310, 34, self.heading)
            self.button("Home", lambda: self.navigate("home"), 360, 6, 104)
            subtitle = "Demo · sample networks" if self.demo else "Select a network to connect your Pi."
            self.label(subtitle, 16, 46, 448, 22, self.small, MUTED)
            for index, item in enumerate(self.networks[self.offset:self.offset + 3]):
                label = self.short(item["ssid"], 310) + "  ·  " + str(item["strength"]) + "%"
                self.button(label, lambda n=item: self.select(n), 16, 74 + index * 50, 448, 48, disabled=self.busy)
            if not self.networks:
                self.label("Scanning…" if self.busy else "No networks found", 16, 100, 448, 65, color=MUTED, anchor="center")
            self.label(self.short(self.notice, 320, self.small), 16, 226, 320, 28, self.small, ERROR if "Scanning" not in self.notice else MUTED)
            self.button("<", lambda: self.move_page(-3), 348, 224, 54, disabled=self.offset == 0)
            self.button(">", lambda: self.move_page(3), 410, 224, 54, disabled=self.offset + 3 >= len(self.networks))
            self.button("Hidden network", lambda: self.navigate("security"), 16, 270, 250, disabled=self.busy)
            self.button("Rescan", self.rescan, 278, 270, 186, primary=True, disabled=self.busy)
        elif page in ("password", "hidden"):
            title = "Hidden network" if page == "hidden" else self.short(self.selected["ssid"], 448)
            self.label(title, 16, 0, 448, 28)
            self.label(self.short(self.notice or ("Enter network name" if page == "hidden" else "Enter Wi-Fi password"), 448, self.small),
                       16, 28, 448, 21, self.small, ERROR if self.notice else MUTED)
            self.field = self.label("", 16, 52, 354, 38)
            self.field.configure(bg=PANEL, bd=0, padx=6, highlightthickness=1, highlightbackground=CYAN)
            if page == "password":
                self.show_button = self.button("Show", self.toggle_reveal, 378, 50, 86, size=self.small)
            else:
                self.button("Clear", lambda: self.key("CLEAR"), 378, 50, 86, size=self.small)
            self.keyboard()
            self.button("Cancel", lambda: self.navigate("networks"), 16, 272, 180)
            self.button("Next" if page == "hidden" else "Connect", self.join, 208, 272, 256, primary=True)
            self.update_field()
        elif page in ("open", "unsupported", "security"):
            self.label("Network security", 16, 10, 448, 36, self.heading)
            if page == "security":
                for n, (label, key) in enumerate((("WPA2 / WPA3 Personal", "wpa-psk"), ("WPA3 only", "sae"), ("Open network", "open"))):
                    self.button(label, lambda k=key: self.hidden_security(k), 16, 65 + n * 56, 448, 48)
                self.button("Back", lambda: self.navigate("networks"), 16, 270, 448)
            else:
                self.label(self.short(self.selected["ssid"], 448), 16, 62, 448, 34)
                message = ("No Wi-Fi encryption on this network.\nConnect only if you trust it." if page == "open" else
                           "Enterprise and legacy Wi-Fi need\nconfiguration through SSH.")
                self.label(message, 16, 110, 448, 80, color=MUTED)
                if self.notice:
                    self.label(self.short(self.notice, 448, self.small), 16, 208, 448, 36, self.small, ERROR)
                self.button("Back", lambda: self.navigate("networks"), 16, 270, 180)
                if page == "open":
                    self.button("Connect", self.join, 208, 270, 256, primary=True)
        elif page == "joining":
            self.label("Connecting…", 16, 30, 448, 42, self.heading)
            self.label(self.short(self.selected["ssid"], 448), 16, 95, 448, 38)
            self.label("Joining Wi-Fi and getting an IP address.\nThis may take about a minute.\nIf it fails, the last connection is restored.",
                       16, 145, 448, 120, self.small, color=MUTED)
        elif page == "status":
            self.label("TailBridge", 16, 8, 310, 34, self.heading)
            self.button("Home", lambda: self.navigate("home"), 360, 6, 104)
            tailnet = self.status.get("tailnet", {})
            ip_url, name_url = management_urls(tailnet)
            ready = bool(ip_url)
            width = 280 if ready else 448
            self.label(self.short(self.status.get("ssid") or "Wi-Fi not connected", width - 6), 16, 54, width, 30)
            wifi_ip = "Pi Wi-Fi IP: " + (", ".join(self.status.get("ipv4", [])) or "Waiting for connection")
            self.label(self.short(wifi_ip, width - 6, self.small), 16, 86, width, 26, self.small, MUTED)
            self.label("Tailscale: " + tailnet.get("state", "Checking…"), 16, 122, width, 28)
            self.label(ip_url or "Connect Tailscale to manage redirections.",
                       16, 153, width, 30, self.small, CYAN if ready else MUTED)
            if ready:
                qr_url = self.draw_qr(name_url or ip_url, x=308, y=54, budget=156,
                                      fallback=ip_url, missing="QR unavailable.\nOpen a URL\non your phone.")
                caption = ("Scan for ts-redir · " + ("name" if qr_url == name_url else "IP")) if qr_url else "Open a URL on your phone."
                self.label(caption, 16, 183, 280, 26, self.small, MUTED)
                shown = self.short(name_url, 442, self.small)
                self.label(shown or "Tailnet name unavailable; use IP above.",
                           16, 212, 448, 26, self.small, CYAN if name_url else MUTED)
                hint = "Name shortened; scan the QR or use the IP." if shown != name_url else "Use a phone connected to your tailnet."
            else:
                hint = "Wi-Fi setup also works without internet."
            self.label(self.short(self.notice, 442, self.small) if ready and self.notice else hint,
                       16, 240 if ready else 216, 448, 26, self.small, ERROR if ready and self.notice else MUTED)
            if self.notice and not ready:
                self.label(self.short(self.notice, 448, self.small), 16, 242, 448, 24, self.small, ERROR)
            self.button("Tailscale setup", lambda: self.navigate("tailnet"), 16, 270, 448, primary=not ready)
        elif page == "tailnet":
            self.label("Connect Tailscale", 16, 8, 448, 36, self.heading)
            tailnet = self.status.get("tailnet", {})
            url = tailnet.get("auth_url", "")
            if url:
                self.draw_qr(url)
                self.label("Scan with your phone\nand approve this Pi.\n\nKeep this screen private.", 228, 65, 238, 165, self.small)
            else:
                self.label("Authorize this Pi in your tailnet.\nA sign-in QR code will appear here.", 16, 72, 448, 90, color=MUTED)
                self.label(self.short(self.notice or tailnet.get("state", "Checking…"), 448, self.small), 16, 184, 448, 48, self.small)
            self.button("Back", lambda: self.navigate("status"), 16, 270, 180)
            self.button("Start sign-in", self.login, 208, 270, 256, primary=True, disabled=self.busy or tailnet.get("state") == "Running")

    def move_page(self, amount):
        self.offset = max(0, min(self.offset + amount, max(0, len(self.networks) - 1)))
        self.render()

    def login(self):
        def started(result):
            self.notice = "Waiting for a sign-in link…"
            self.render()
        self.call("login", started)

    def draw_qr(self, url, x=16, y=58, budget=192, fallback="", missing=None):
        try:
            import qrcode
            def matrix_for(value):
                qr = qrcode.QRCode(border=4)
                qr.add_data(value)
                qr.make(fit=True)
                return qr.get_matrix()
            matrix = matrix_for(url)
            if fallback and budget // len(matrix) < 3:
                url = fallback
                matrix = matrix_for(url)
            scale = max(1, budget // len(matrix))
            size = scale * len(matrix)
            offset = (budget - size) // 2
            canvas = tk.Canvas(self.root, bg="white", highlightthickness=0)
            canvas.place(x=x, y=y, width=budget, height=budget)
            for row, values in enumerate(matrix):
                for col, dark in enumerate(values):
                    if dark:
                        canvas.create_rectangle(offset + col * scale, offset + row * scale,
                                                offset + (col + 1) * scale, offset + (row + 1) * scale,
                                                fill="black", outline="")
            return url
        except ImportError:
            self.label(missing or "QR library missing.\nUse sudo tailscale up\nthrough SSH.",
                       x, y, budget, budget, self.small, ERROR)
            return ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--windowed", action="store_true")
    args = parser.parse_args()
    root = tk.Tk()
    App(root, Demo() if args.demo else request, args.demo, not args.windowed)
    root.mainloop()


if __name__ == "__main__":
    main()
