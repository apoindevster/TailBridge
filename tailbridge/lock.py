"""Local touchscreen authentication. PINs and session tokens never enter logs."""
import argparse
from contextlib import contextmanager
import fcntl
import getpass
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import time
import warnings

from .common import LockedError, UserError, atomic_json

PIN_FILE = Path('/var/lib/tailbridge-lock/pin.json')
ITERATIONS = 600_000
MAX_DELAY = 60


def valid_pin(pin):
    return isinstance(pin, str) and re.fullmatch(r'[0-9]{6,12}', pin) is not None


def derive(pin, salt):
    return hashlib.pbkdf2_hmac('sha256', pin.encode('ascii'), bytes.fromhex(salt), ITERATIONS).hex()


class PinStore:
    def __init__(self, path=PIN_FILE, owner=0):
        self.path, self.owner = Path(path), owner

    def directory(self, create=False):
        if create:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.path.parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != self.owner or info.st_mode & 0o077:
            raise ValueError('Unsafe PIN directory')

    def read(self):
        try:
            self.directory()
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return None
        with os.fdopen(fd, 'r') as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != self.owner or info.st_mode & 0o077 or info.st_size > 4096:
                raise ValueError('Unsafe PIN file')
            record = json.loads(source.read(4097))
        if (not isinstance(record, dict) or set(record) != {'version', 'salt', 'hash', 'failures', 'retry_until'}
                or type(record['version']) is not int or record['version'] != 1
                or not isinstance(record['salt'], str) or not re.fullmatch('[0-9a-f]{32}', record['salt'])
                or not isinstance(record['hash'], str) or not re.fullmatch('[0-9a-f]{64}', record['hash'])
                or type(record['failures']) is not int or not 0 <= record['failures'] <= 32
                or type(record['retry_until']) not in (int, float)
                or not math.isfinite(record['retry_until']) or not 0 <= record['retry_until'] <= 10**12):
            raise ValueError('Invalid PIN record')
        return record

    def write(self, record):
        self.directory(create=True)
        # Never follow a link or silently replace an unsafe existing file.
        self.read()
        atomic_json(self.path, record)

    @contextmanager
    def transaction(self):
        # Serialize administrator resets with complete verification attempts so
        # an in-flight unlock cannot overwrite newly configured credentials.
        self.directory(create=True)
        fd = os.open(self.path.parent / '.guard', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != self.owner or info.st_mode & 0o077:
                raise ValueError('Unsafe PIN transaction file')
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def configure(self, pin):
        if not valid_pin(pin):
            raise ValueError('Use 6–12 digits for the PIN.')
        with self.transaction():
            salt = secrets.token_hex(16)
            self.write({'version': 1, 'salt': salt, 'hash': derive(pin, salt),
                        'failures': 0, 'retry_until': 0})


class PinGate:
    """Single kiosk session, revoked by lock, process restart or credential change."""
    def __init__(self, store=None, wall=time.time, monotonic=time.monotonic):
        self.store = store or PinStore()
        self.wall, self.monotonic = wall, monotonic
        self.record, self.session, self.deadline = None, '', 0

    def refresh(self):
        try:
            record = self.store.read()
        except (OSError, ValueError):
            self.session, self.record = '', None
            raise UserError('PIN setup unavailable. Check installation through SSH.') from None
        if record != self.record:
            self.session = ''
            self.record = record
            # Bound a reboot's wait even when the Pi's wall clock moved back.
            remaining = min(MAX_DELAY, max(0, record['retry_until'] - self.wall())) if record else 0
            self.deadline = self.monotonic() + remaining

    def state(self):
        self.refresh()
        return {'configured': self.record is not None,
                'retry_after': max(0, math.ceil(self.deadline - self.monotonic()))}

    def lock(self):
        self.session = ''
        return self.state()

    def save(self, record, delay):
        self.session = ''
        self.deadline = self.monotonic() + delay
        try:
            self.store.write(record)
        except (OSError, ValueError):
            raise UserError('PIN verification unavailable. Check installation through SSH.') from None
        self.record = record

    def unlock(self, pin):
        try:
            with self.store.transaction():
                return self._unlock(pin)
        except (OSError, ValueError):
            self.session = ''
            raise UserError('PIN verification unavailable. Check installation through SSH.') from None

    def _unlock(self, pin):
        state = self.state()
        if not state['configured'] or state['retry_after']:
            return {**state, 'unlocked': False}
        failures = min(32, self.record['failures'] + 1)
        delay = min(MAX_DELAY, 2 ** min(failures - 1, 6))
        # Persist the attempt BEFORE checking the PIN. A crash, malformed request
        # or restarted UI cannot erase guesses. No wait blocks the socket server.
        self.save({**self.record, 'failures': failures, 'retry_until': self.wall() + delay}, delay)
        if not valid_pin(pin) or not hmac.compare_digest(derive(pin, self.record['salt']), self.record['hash']):
            return {**self.state(), 'unlocked': False}
        self.save({**self.record, 'failures': 0, 'retry_until': 0}, 0)
        self.session = secrets.token_urlsafe(32)
        return {'unlocked': True, 'session': self.session}

    def authorize(self, session):
        self.refresh()
        if not self.session or not isinstance(session, str) or not session.isascii() or not hmac.compare_digest(self.session, session):
            raise LockedError('Screen locked. Enter your PIN.')


def configure_interactively(store, reset=False):
    if store.read() is not None and not reset:
        print('Existing touchscreen PIN preserved.')
        return
    # getpass must never fall back to echoing or consuming a redirected secret.
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise UserError('PIN setup requires a private interactive terminal (use ssh -t).')
    while True:
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            pin = getpass.getpass('New touchscreen PIN (6–12 digits): ')
        if not valid_pin(pin):
            print('Use 6–12 digits.', file=sys.stderr)
            continue
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            confirmation = getpass.getpass('Confirm touchscreen PIN: ')
        if not valid_pin(confirmation) or not hmac.compare_digest(pin, confirmation):
            pin = confirmation = ''
            print('PINs did not match. Try again.', file=sys.stderr)
            continue
        store.configure(pin)
        pin = confirmation = ''
        print('Touchscreen PIN saved. Restart the broker and display, or reboot, to activate.')
        return


def main():
    parser = argparse.ArgumentParser(description='Private touchscreen PIN setup; no PIN command-line option.')
    parser.add_argument('--reset', action='store_true', help='replace an existing PIN after authenticated sudo')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run PIN setup with authenticated sudo.')
    try:
        configure_interactively(PinStore(), args.reset)
    except (EOFError, KeyboardInterrupt):
        raise SystemExit('PIN setup cancelled.') from None
    except (OSError, ValueError, UserError, getpass.GetPassWarning):
        raise SystemExit('PIN setup failed. Use a private interactive terminal and check the protected PIN state.') from None


if __name__ == '__main__':
    main()
