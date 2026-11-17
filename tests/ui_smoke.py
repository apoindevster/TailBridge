"""Native UI interaction/capture test. Uses only synthetic data, no network broker."""
import argparse
import copy
from pathlib import Path
import subprocess
import sys
import threading
import time
import tkinter as tk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tailbridge.common import UserError
from tailbridge.ui import App, Demo


class Fixture(Demo):
    fail = False
    fail_status = False
    join_gate = None
    def __call__(self, command, **data):
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
args = parser.parse_args()
if args.decode_qr:
    from PIL import Image
    import zxingcpp

root = tk.Tk()
root.geometry('+20+20')
fixture = Fixture()
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
    app.reveal_until = 0
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
    app.last_touch = 0
    app.pump()
    assert app.page == 'networks' and not app.value
    print('PASS: native 480x320 UI flow, 14 captures, management QR and fallback, bounds, masking, error recovery, idle clearing' +
          ('; all captured QR payloads decoded correctly' if args.decode_qr else ''))
finally:
    app.close()
