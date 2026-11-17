"""Synthetic PIN fixtures only; no production PIN or device state is read."""
import contextlib
import getpass
import io
import multiprocessing
import os
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import warnings

from tailbridge.broker import dispatch, serve
from tailbridge.common import LockedError, UserError, atomic_json, request
from tailbridge.lock import PinGate, PinStore, configure_interactively, valid_pin


def run_test_broker(socket_path, pin_path):
    # Exercise the real Unix transport without requiring root on the CI runner.
    # Only privileged ownership is stubbed; peer credentials and dispatch run.
    with patch('tailbridge.broker.os.chown'):
        serve(SimpleNamespace(status=lambda: {'fixture': 'synthetic status'}),
              socket_path, os.getuid(), os.getgid(), PinGate(PinStore(pin_path, owner=os.getuid())))


class LockTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'private/pin.json'
        self.store = PinStore(self.path, owner=os.getuid())
        self.now = 1000.0
        self.gate = PinGate(self.store, wall=lambda: self.now, monotonic=lambda: self.now)

    def configured(self):
        self.store.configure('735193')

    def token(self):
        return self.gate.unlock('735193')['session']

    def test_pin_is_salted_hashed_and_private(self):
        self.configured()
        first = self.store.read()
        self.assertNotIn('735193', self.path.read_text())
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.path.parent.stat().st_mode & 0o777, 0o700)
        self.store.configure('735193')
        second = self.store.read()
        self.assertNotEqual(first['salt'], second['salt'])
        self.assertNotEqual(first['hash'], second['hash'])

    def test_pin_validation_has_no_default_and_is_ascii_bounded(self):
        for value in (None, '', '12345', '1' * 13, '１２３４５６', 'abcdef', '123 456'):
            self.assertFalse(valid_pin(value))
        self.assertTrue(valid_pin('012345'))
        self.assertTrue(valid_pin('012345678901'))

    def test_missing_pin_fails_closed(self):
        self.assertFalse(self.gate.state()['configured'])
        self.assertFalse(self.gate.unlock('123456')['unlocked'])
        with self.assertRaises(LockedError):
            self.gate.authorize('anything')

    def test_authentication_is_required_for_every_backend_action(self):
        self.configured()
        backend = Mock()
        requests = [{'command': c} for c in ('status', 'scan', 'login')]
        requests.append({'command': 'connect', 'ssid_hex': '61', 'security': 'open'})
        for data in requests:
            with self.assertRaises(LockedError):
                dispatch(backend, data, self.gate)
        self.assertEqual(backend.mock_calls, [])
        token = self.token()
        for data in requests:
            dispatch(backend, {**data, 'session': token}, self.gate)
        self.assertEqual(len(backend.mock_calls), 4)
        self.gate.lock()
        with self.assertRaises(LockedError):
            dispatch(backend, {'command': 'status', 'session': token}, self.gate)

    def test_invalid_sessions_never_authorize(self):
        self.configured()
        token = self.token()
        for invalid in (None, '', token + 'x', [], '雪'):
            with self.assertRaises(LockedError):
                self.gate.authorize(invalid)
        self.gate.authorize(token)

    def test_broker_restart_and_pin_change_revoke_sessions(self):
        self.configured()
        token = self.token()
        restarted = PinGate(self.store)
        with self.assertRaises(LockedError):
            restarted.authorize(token)
        self.store.configure('481927')
        with self.assertRaises(LockedError):
            self.gate.authorize(token)
        self.assertTrue(self.gate.unlock('481927')['unlocked'])

    def test_attempts_persist_and_cooldown_cannot_be_bypassed(self):
        self.configured()
        result = self.gate.unlock('000000')
        self.assertFalse(result['unlocked'])
        self.assertEqual(result['retry_after'], 1)
        self.assertFalse(self.gate.unlock('735193')['unlocked'])
        restarted = PinGate(self.store, wall=lambda: self.now, monotonic=lambda: self.now)
        self.assertEqual(restarted.state()['retry_after'], 1)
        restarted.lock()
        self.assertFalse(restarted.unlock('735193')['unlocked'])
        self.now += 1
        result = restarted.unlock('000000')
        self.assertEqual(result['retry_after'], 2)
        self.now += 2
        self.assertTrue(restarted.unlock('735193')['unlocked'])
        self.assertEqual(self.store.read()['failures'], 0)

    def test_malformed_pin_is_a_rate_limited_attempt(self):
        self.configured()
        self.assertFalse(self.gate.unlock(['735193'])['unlocked'])
        self.assertEqual(self.store.read()['failures'], 1)

    def test_clock_rollback_wait_is_bounded_by_monotonic_time(self):
        self.configured()
        record = self.store.read()
        record.update(failures=32, retry_until=100000)
        self.store.write(record)
        self.assertEqual(self.gate.state()['retry_after'], 60)
        self.now += 60
        self.assertTrue(self.gate.unlock('735193')['unlocked'])

    def test_attempt_is_saved_before_hash_check_and_write_failure_denies_unlock(self):
        self.configured()
        self.gate.state()
        with patch.object(self.store, 'write', side_effect=OSError('private diagnostic')), patch('tailbridge.lock.derive') as derive:
            with self.assertRaisesRegex(UserError, '^PIN verification unavailable'):
                self.gate.unlock('735193')
        derive.assert_not_called()
        self.assertFalse(self.gate.session)

    def test_unsafe_permissions_symlinks_and_corruption_are_rejected(self):
        self.configured()
        token = self.token()
        self.path.chmod(0o644)
        with self.assertRaises(UserError): self.gate.authorize(token)
        self.assertFalse(self.gate.session)
        self.path.chmod(0o600)
        self.path.write_text('{}')
        with self.assertRaises(UserError): self.gate.state()
        self.path.unlink()
        self.path.symlink_to(self.path.parent / 'absent')
        with self.assertRaises((OSError, ValueError)): self.store.configure('735193')
        self.path.unlink()
        self.path.parent.chmod(0o755)
        with self.assertRaises(ValueError): self.store.configure('735193')

    def test_invalid_state_is_rejected_without_disclosing_contents(self):
        self.configured()
        original = self.store.read()
        for changes in ({'failures': -1}, {'failures': True}, {'retry_until': float('nan')},
                        {'version': True}, {'hash': 'private-value'}, {'salt': 'bad'}):
            atomic_json(self.path, {**original, **changes})
            with self.assertRaisesRegex(UserError, '^PIN setup unavailable'):
                self.gate.state()

    def test_reinstall_preserves_pin_without_prompting(self):
        self.configured()
        before = self.path.read_bytes()
        with patch('tailbridge.lock.getpass.getpass') as prompt, contextlib.redirect_stdout(io.StringIO()):
            configure_interactively(self.store)
        prompt.assert_not_called()
        self.assertEqual(self.path.read_bytes(), before)

    def test_reset_requires_tty_and_matching_hidden_prompts(self):
        self.configured()
        with patch('tailbridge.lock.sys.stdin.isatty', return_value=False), self.assertRaises(UserError):
            configure_interactively(self.store, reset=True)
        with patch('tailbridge.lock.sys.stdin.isatty', return_value=True), patch('tailbridge.lock.sys.stderr.isatty', return_value=True), \
             patch('tailbridge.lock.getpass.getpass', side_effect=['481927', '481927']), contextlib.redirect_stdout(io.StringIO()) as output:
            configure_interactively(self.store, reset=True)
        self.assertNotIn('481927', output.getvalue())
        self.assertTrue(self.gate.unlock('481927')['unlocked'])

    def test_getpass_echo_fallback_is_an_error(self):
        def insecure_prompt(*args):
            warnings.warn('Echo unavailable', getpass.GetPassWarning)
            self.fail('getpass fallback must not read a PIN')
        with patch('tailbridge.lock.sys.stdin.isatty', return_value=True), patch('tailbridge.lock.sys.stderr.isatty', return_value=True), \
             patch('tailbridge.lock.getpass.getpass', side_effect=insecure_prompt), self.assertRaises(getpass.GetPassWarning):
            configure_interactively(self.store)
        self.assertIsNone(self.store.read())

    def test_auth_command_fields_cannot_smuggle_backend_operations(self):
        for request in ({'command': 'unlock', 'pin': '735193', 'connect': True},
                        {'command': 'lock', 'session': 'x'}, {'command': 'lock_status', 'pin': 'x'}):
            with self.assertRaises(UserError): dispatch(Mock(), request, self.gate)

    def test_unix_protocol_authenticates_and_revokes_the_client_session(self):
        self.configured()
        socket_path = str(Path(self.temporary.name) / 'broker.sock')
        process = multiprocessing.get_context('fork').Process(target=run_test_broker, args=(socket_path, self.path))
        process.start()
        try:
            deadline = time.monotonic() + 5
            while True:
                try:
                    state = request('lock_status', path=socket_path)
                    break
                except (FileNotFoundError, ConnectionRefusedError):
                    self.assertTrue(process.is_alive())
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(0.01)
            self.assertTrue(state['configured'])
            with self.assertRaises(LockedError):
                request('status', path=socket_path)
            token = request('unlock', path=socket_path, pin='735193')['session']
            self.assertEqual(request('status', path=socket_path, session=token), {'fixture': 'synthetic status'})
            request('lock', path=socket_path)
            with self.assertRaises(LockedError):
                request('status', path=socket_path, session=token)
        finally:
            process.terminate()
            process.join(5)
            self.assertFalse(process.is_alive())

    def test_reset_cannot_be_overwritten_by_an_inflight_unlock(self):
        self.configured()
        hashing, release, reset_started = threading.Event(), threading.Event(), threading.Event()
        from tailbridge.lock import derive as real_derive
        def delayed_derive(pin, salt):
            if pin == '735193':
                hashing.set()
                self.assertTrue(release.wait(5))
            return real_derive(pin, salt)
        errors = []
        def unlock():
            try: self.gate.unlock('735193')
            except Exception as error: errors.append(error)
        def reset():
            reset_started.set()
            try: self.store.configure('481927')
            except Exception as error: errors.append(error)
        with patch('tailbridge.lock.derive', side_effect=delayed_derive):
            worker = threading.Thread(target=unlock)
            worker.start()
            try:
                self.assertTrue(hashing.wait(5))
                admin = threading.Thread(target=reset)
                admin.start()
                self.assertTrue(reset_started.wait(5))
            finally:
                release.set()
                worker.join(5)
            admin.join(5)
        self.assertFalse(errors)
        self.assertFalse(worker.is_alive() or admin.is_alive())
        self.assertTrue(self.gate.unlock('481927')['unlocked'])
