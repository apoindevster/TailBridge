"""Native UI interaction/capture test. Uses only synthetic data, no network broker."""
import argparse
import copy
from pathlib import Path
import subprocess
import sys
import threading
import time
import tkinter as tk
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tailbridge.common import UserError
from tailbridge.ui import App, Demo


class Fixture(Demo):
    fail = False
    fail_status = False
    join_gate = None
    status_gate = None
    configured = True
    fail_lock = False
    def __call__(self, command, **data):
        if command in ('lock', 'lock_status') and self.fail_lock:
            raise UserError('Synthetic unavailable service')
        if command in ('lock', 'lock_status') and not self.configured:
            self.session = ''
            return {'configured': False, 'retry_after': 0}
        if command == 'status' and self.status_gate is not None:
            assert self.status_gate.wait(10), 'Synthetic status was not released'
        if command == 'status' and self.fail_status:
            raise UserError('Status unavailable. Try again.')
        if command == 'connect' and self.join_gate is not None:
            assert self.join_gate.wait(10), 'Synthetic join was not released'
        if command == 'connect' and self.fail:
            raise UserError('Could not join. Check signal and retry.' if data['security'] == 'open' else
                            'Could not join. Check password and signal.')
        return super().__call__(command, **data)


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--decode-qr', action='store_true', help='Decode actual captures with Pillow and zxing-cpp (development only)')
parser.add_argument('--clock-start', type=float, default=10,
                    help='Initial UI monotonic time; defaults to a fresh-runner clock')
args = parser.parse_args()
if args.decode_qr:
    from PIL import Image
    import zxingcpp

root = tk.Tk()
root.geometry('+20+20')
fixture = Fixture()
# A fresh clock catches absolute-zero timeout assumptions even on long-lived hosts.
# Patch only the UI's clock; worker waits and the test's own deadlines stay real.
clock_started = time.monotonic()
ui_clock = SimpleNamespace(monotonic=lambda: args.clock_start + time.monotonic() - clock_started)
clock_patch = patch('tailbridge.ui.time', ui_clock)
clock_patch.start()
app = App(root, fixture, demo=True, fullscreen=False)
captures = Path('artifacts')
captures.mkdir(exist_ok=True)


def settle():
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        root.update()
        if not app.busy:
            root.update_idletasks()
            return
        time.sleep(0.01)
    raise AssertionError('UI did not finish synthetic operation')


def capture(name, qr_url=None):
    root.update()
    for item in root.winfo_children():
        x, y, w, h = item.winfo_x(), item.winfo_y(), item.winfo_width(), item.winfo_height()
        assert x >= 0 and y >= 0 and x + w <= 480 and y + h <= 320, (name, str(item), x, y, w, h)
        if isinstance(item, tk.Button):
            assert h >= 42, (name, item.cget('text'), 'short touch target')
    # Only this synthetic application window; never capture the user's desktop.
    subprocess.run(['import', '-window', str(root.winfo_id()), '-strip', str(captures / (name + '.png'))], check=True)
    if args.decode_qr:
        with Image.open(captures / (name + '.png')) as frame:
            decoded = [code.text for code in zxingcpp.read_barcodes(frame)]
        assert decoded == ([qr_url] if qr_url else []), (name, 'wrong or missing QR payload')


try:
    settle()
    assert app.page == 'locked' and not app.session and not app.status and not app.networks
    app.navigate('home')
    assert app.page == 'locked', 'navigation must not bypass the PIN'
    capture('locked')
    for char in '000000': app.key(char)
    app.unlock_pin()
    settle()
    assert app.page == 'locked' and not app.value and not app.session
    capture('lock-wait')
    app.retry_deadline = ui_clock.monotonic() - 1  # Real persistent throttling has separate tests.
    app.touch()
    for char in '123456': app.key(char)
    assert '123456' not in app.field.cget('text')
    capture('lock-pin')
    app.unlock_pin()
    settle()
    assert app.page == 'home'
    assert [w.cget('text') for w in root.winfo_children() if isinstance(w, tk.Button)] == ['Lock', 'Status', 'Wi-Fi']
    capture('home')
    app.navigate('networks')
    settle()
    # The real kiosk refuses a window-manager close request. The same root stays
    # alive, including its callbacks, before returning to synthetic preview mode.
    app.demo = False
    root.tk.call(root.protocol('WM_DELETE_WINDOW'))
    assert root.winfo_exists() and not app.closed
    assert app.window_close() == 'break'
    app.demo = True
    assert len(app.networks) == 4
    capture('wifi')
    app.move_page(3)
    assert app.offset == 3
    app.select(app.networks[0])
    for char in 'SyntheticTest!': app.key(char)
    assert 'SyntheticTest!' not in app.field.cget('text')
    capture('password')
    app.change_keys('sym')
    capture('symbols')
    app.toggle_reveal()
    assert app.field.cget('text') == 'SyntheticTest!'
    app.reveal_until = ui_clock.monotonic() - 1
    app.pump()
    assert not app.revealed
    fixture.fail = True
    fixture.join_gate = threading.Event()
    app.join()
    try:
        assert app.busy
        capture('joining')
    finally:
        fixture.join_gate.set()
    settle()
    fixture.join_gate = None
    assert app.page == 'password' and not app.value and app.notice
    capture('failed-join')
    app.navigate('networks')
    settle()
    app.select(app.networks[1])
    app.join()
    settle()
    assert app.page == 'open' and app.notice
    capture('open-failed')
    fixture.fail = False
    app.join()
    settle()
    assert app.page == 'status'
    name = app.status['tailnet']['dns_name']
    assert any(item.cget('text') == 'http://' + name + ':8800' for item in root.winfo_children() if isinstance(item, tk.Label))
    capture('status', 'http://' + name + ':8800')
    canvas = next(item for item in root.winfo_children() if isinstance(item, tk.Canvas))
    app.updated(copy.deepcopy(app.status))
    assert canvas.winfo_exists(), 'unchanged status should not redraw a QR during scanning'
    renamed = copy.deepcopy(app.status)
    renamed['tailnet'].update(dns_name='renamed.example-tailnet.ts.net', ipv4=['100.100.20.41'])
    app.updated(renamed)
    assert not canvas.winfo_exists(), 'a changed address must replace the previous QR'
    capture('status-renamed', 'http://renamed.example-tailnet.ts.net:8800')
    with patch.dict(sys.modules, {'qrcode': None}):
        app.render()
        assert not any(isinstance(item, tk.Canvas) for item in root.winfo_children())
        capture('status-no-qr')
    app.status['tailnet']['dns_name'] = ''
    app.render()
    capture('status-no-name', 'http://100.100.20.41:8800')
    app.status['tailnet']['dns_name'] = 'a' * 63 + '.' + 'b' * 63 + '.ts.net'
    app.render()
    assert any(item.cget('text') == 'Name shortened; scan the QR or use the IP.' for item in root.winfo_children() if isinstance(item, tk.Label))
    capture('status-long-name', 'http://100.100.20.41:8800')
    fixture.fail_status = True
    app.call('status', app.updated)
    settle()
    assert app.status['tailnet']['state'] == 'Unavailable'
    capture('status-error')
    fixture.fail_status = False
    app.call('status', app.updated)
    settle()
    assert not app.notice and any(isinstance(item, tk.Canvas) for item in root.winfo_children())
    app.status['tailnet'] = {'state': 'NeedsLogin', 'ipv4': [], 'dns_name': '',
                            'auth_url': 'https://login.tailscale.com/a/DO-NOT-SHOW-ON-STATUS'}
    app.notice = 'Service unavailable. Try again.'
    app.render()
    capture('status-offline')
    app.navigate('tailnet')
    app.status['tailnet'] = {'state': 'NeedsLogin', 'auth_url': 'https://login.tailscale.com/a/SYNTHETIC-NOT-A-REAL-LOGIN'}
    app.render()
    capture('enrollment', 'https://login.tailscale.com/a/SYNTHETIC-NOT-A-REAL-LOGIN')
    assert any(isinstance(item, tk.Canvas) for item in root.winfo_children()), 'QR did not render'
    app.hidden_security('sae')
    for char in 'Hidden Wi-Fi': app.key(char)
    app.join()
    assert app.selected['hidden'] and app.page == 'password'
    app.key('x')
    app.pump()
    assert app.page == 'password' and app.value == 'x'
    app.last_touch = ui_clock.monotonic() - 121
    app.pump()
    assert app.page == 'networks' and not app.value
    settle()
    app.navigate('home')
    fixture.status_gate = threading.Event()
    app.call('status', app.updated)
    app.lock_screen()
    assert app.page == 'locked' and not app.value and not app.session and not app.status and not app.networks
    fixture.status_gate.set()
    settle()
    fixture.status_gate = None
    assert not app.pending_lock and not fixture.session and not app.status
    # A partial PIN expires, and Escape only clears the field.
    app.touch()
    for char in '123': app.key(char)
    app.pump()
    assert app.value == '123' and app.page == 'locked'
    app.last_touch = ui_clock.monotonic() - 31
    app.pump()
    assert not app.value and app.page == 'locked'
    app.physical_key(type('Key', (), {'keysym': 'Escape', 'char': ''})())
    assert app.page == 'locked'
    fixture.configured = False
    app.call('lock_status', app.lock_state)
    settle()
    assert app.unlock_button.cget('state') == 'disabled'
    capture('lock-setup')
    fixture.fail_lock = True
    app.call('lock_status', app.lock_state)
    settle()
    capture('lock-error')
    fixture.fail_lock, fixture.configured = False, True
    app.call('lock_status', app.lock_state)
    settle()
    app.touch()
    for char in '123456': app.key(char)
    app.unlock_pin()
    settle()
    # Broker restart revokes the session and forces the UI back to the lock.
    fixture.session = ''
    app.call('status', app.updated)
    settle()
    assert app.page == 'locked' and not app.session and not app.status
    print('PASS: native 480x320 UI flow, 20 captures, PIN/home/lock states and revocation, management QR and fallback, bounds, masking, error recovery, idle clearing' +
          ('; all captured QR payloads decoded correctly' if args.decode_qr else ''))
finally:
    app.close()
    clock_patch.stop()
