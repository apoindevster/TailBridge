import io
import json
import os
from pathlib import Path
import socket
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tailbridge.broker import allowed_peer, dispatch
from tailbridge.common import UserError, atomic_json, display_ssid, management_urls, normalize_tailnet_name, read_message, validate_wifi
from tailbridge.network import NetworkManager, security_type
from scripts.configure_system import Installer, boot_config, configure_kiosk, install_payload


class ProtocolTests(unittest.TestCase):
    def test_management_urls_are_only_plain_local_addresses(self):
        status = {'state': 'Running', 'ipv4': ['100.100.20.40'],
                  'dns_name': 'TS-REDIR.example-tailnet.ts.net.',
                  'auth_url': 'https://login.tailscale.com/a/DO-NOT-ENCODE'}
        ip_url = 'http://100.100.20.40:8800'
        self.assertEqual(management_urls(status), (ip_url, 'http://ts-redir.example-tailnet.ts.net:8800'))
        for name in (None, '', 'bad.ts.net:8800/?token=secret', 'https://login.tailscale.com/a/private'):
            self.assertEqual(management_urls({**status, 'dns_name': name}), (ip_url, ''))

    def test_management_urls_require_running_tailnet_ipv4(self):
        for state, ips in (('NeedsLogin', ['100.100.20.40']), ('Stopped', ['100.100.20.40']),
                           ('Unavailable', ['100.100.20.40']), ('Running', []), ('Running', None),
                           ('Running', ['192.168.1.10']), ('Running', ['100.100.20.40:8800']),
                           ('Running', ['fd7a:115c:a1e0::1'])):
            self.assertEqual(management_urls({'state': state, 'ipv4': ips,
                             'dns_name': 'ts-redir.example.ts.net'}), ('', ''))

    def test_unenrolled_tailscale_null_fields(self):
        backend = NetworkManager.__new__(NetworkManager)
        backend.login_process = None
        payload = {"BackendState": "NeedsLogin", "TailscaleIPs": None, "AuthURL": None}
        with patch('tailbridge.network.subprocess.run', return_value=SimpleNamespace(stdout=json.dumps(payload), returncode=0)):
            result = backend.tailnet_status()
        self.assertEqual(result, {"state": "NeedsLogin", "ipv4": [], "dns_name": "", "auth_url": "", "login_running": False})

    def test_tailnet_name_uses_local_identity(self):
        backend = NetworkManager.__new__(NetworkManager)
        backend.login_process = None
        payload = {"BackendState": "Running", "TailscaleIPs": ["100.100.20.40"],
                   "Self": {"DNSName": "TS-REDIR.example-tailnet.ts.net.", "TailscaleIPs": ["100.100.20.40"]}}
        for state, own, expected in (
                ("Running", payload["Self"], "ts-redir.example-tailnet.ts.net"),
                ("Stopped", payload["Self"], ""),
                ("Running", {"DNSName": "other.example.ts.net", "TailscaleIPs": ["100.100.20.41"]}, ""),
                ("Running", None, "")):
            payload.update(BackendState=state, Self=own)
            with patch('tailbridge.network.subprocess.run', return_value=SimpleNamespace(stdout=json.dumps(payload), returncode=0)):
                self.assertEqual(backend.tailnet_status()['dns_name'], expected)
        with patch('tailbridge.network.subprocess.run', return_value=SimpleNamespace(stdout='private diagnostic', returncode=1)):
            self.assertEqual(backend.tailnet_status()['state'], 'Unavailable')

    def test_tailnet_name_rejects_malformed_names(self):
        for name in (None, '', 'evil\n.example.ts.net', 'http://a.example.ts.net',
                     'a.example.ts.net:8800', '-a.example.ts.net', 'a..ts.net',
                     'a.example.ts.net.evil.test', 'a.example.ts.net..',
                     'a' * 64 + '.example.ts.net'):
            self.assertEqual(normalize_tailnet_name(name), '')

    def test_bounded_and_structured_input(self):
        for body in (b'x' * 16385 + b'\n', b'{"command":"status"}', b'[]\n', b'bad\n'):
            with self.assertRaises(UserError):
                read_message(io.BytesIO(body))

    def test_only_supported_commands(self):
        for value in ({"command": []}, {"command": "reboot"}, {"command": "status", "shell": "ignored"},
                      {"command": "connect", "hidden": "yes"}):
            with self.assertRaises(UserError):
                dispatch(None, value)

    def test_peer_identity_comes_from_kernel(self):
        first, second = socket.socketpair()
        with first, second:
            self.assertTrue(allowed_peer(first, os.getuid()))
            if os.getuid() != 0:
                self.assertFalse(allowed_peer(first, os.getuid() + 1))

    def test_ssid_is_not_a_command_or_delimiter(self):
        for name in ('a:b\\c', '$(echo secret)', '雪', '"quoted"'):
            validate_wifi(name.encode().hex(), 'wpa-psk', 'not-a-real-password')
        self.assertNotIn('\x1b', display_ssid(b'evil\x1b[31m'))
        self.assertNotIn('\n', display_ssid(b'evil\n'))

    def test_no_security_downgrade(self):
        self.assertEqual(security_type(1, 0, 0), 'unsupported')
        self.assertEqual(security_type(1, 0x100, 0), 'unsupported')
        self.assertEqual(security_type(1, 0, 0x200), 'unsupported')
        self.assertEqual(security_type(1, 0, 0x400), 'sae')
        self.assertEqual(security_type(1, 0, 0x500), 'wpa-psk')
        with self.assertRaises(UserError):
            validate_wifi('61', 'open', 'a-password')
        with self.assertRaises(UserError):
            validate_wifi('61', 'wpa-psk', 'short')

    def test_atomic_private_storage(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / 'state.json'
            atomic_json(file, {'test': 1})
            atomic_json(file, {'test': 2})
            self.assertEqual(json.loads(file.read_text()), {'test': 2})
            self.assertEqual(file.stat().st_mode & 0o777, 0o600)


class FakeAPI:
    def __init__(self, owner): self.owner = owner
    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.owner.calls.append((name, args))
            if name == 'CheckpointCreate': return '/checkpoint'
            if name == 'AddAndActivateConnection2': return '/profile', '/active', {}
            if name == 'CheckpointRollback' and self.owner.rollback_fails:
                raise self.owner.dbus.DBusException('private data must not escape')
            if name == 'CheckpointRollback': return {'/wifi-only': 0}
        return call


class FakeNM(NetworkManager):
    def __init__(self, success=False, rollback_fails=False):
        import dbus
        self.dbus, self.interface, self.calls = dbus, 'wlan0', []
        self.success, self.rollback_fails = success, rollback_fails
    def api(self, path, interface): return FakeAPI(self)
    def device(self): return '/wifi-only'
    def props(self, path, interface):
        if interface.endswith('Connection.Active'): return {'State': 4}
        if interface.endswith('IP4Config'): return {'AddressData': [{'address': '192.0.2.40'}]}
        return {'State': 100 if self.success else 120, 'ActiveConnection': '/active', 'Ip4Config': '/ipv4'}
    def _remove_previous_owned_profiles(self, *args): pass


class ConnectionTests(unittest.TestCase):
    def test_open_network_failure_does_not_ask_for_password(self):
        with self.assertRaisesRegex(UserError, 'Check signal and retry'):
            FakeNM().connect('74657374', 'open', '')

    def test_failed_explicit_rollback_keeps_automatic_recovery_armed(self):
        backend = FakeNM(rollback_fails=True)
        with self.assertRaises(UserError): backend.connect('74657374', 'wpa-psk', 'test-password')
        self.assertNotIn('CheckpointDestroy', [name for name, _ in backend.calls])

    def test_success_saves_only_after_address(self):
        backend = FakeNM(success=True)
        result = backend.connect('74657374', 'wpa-psk', 'test-password')
        self.assertTrue(result['connected'])
        names = [name for name, _ in backend.calls]
        self.assertIn('Save', names)
        self.assertNotIn('CheckpointRollback', names)
        settings = next(args for name, args in backend.calls if name == 'AddAndActivateConnection2')
        self.assertEqual(settings[3]['persist'], 'memory')

    def test_failed_join_rolls_back_without_saving(self):
        backend = FakeNM()
        with self.assertRaises(UserError): backend.connect('74657374', 'wpa-psk', 'test-password')
        names = [name for name, _ in backend.calls]
        self.assertIn('CheckpointRollback', names)
        self.assertIn('Delete', names)
        self.assertNotIn('Save', names)
        checkpoint = next(args for name, args in backend.calls if name == 'CheckpointCreate')
        self.assertEqual(checkpoint[0], ['/wifi-only'])


class InstallTests(unittest.TestCase):
    def test_reinstall_can_replace_a_running_executable(self):
        with tempfile.TemporaryDirectory() as folder:
            source, root = Path(folder) / 'source', Path(folder) / 'root'
            for name in ('tailbridge', 'scripts', 'packaging', 'bin', 'vendor'):
                (source / name).mkdir(parents=True)
            binary = source / 'bin/ts-redir'
            shutil.copyfile('/usr/bin/sleep', binary)
            (source / 'vendor/mhs35ips.dtbo').write_bytes(b'synthetic overlay')
            install_payload(source, root)
            installed = root / 'opt/tailbridge/bin/ts-redir'
            running = subprocess.Popen([str(installed), '30'])
            try:
                binary.write_bytes(b'replacement executable fixture')
                install_payload(source, root)
                self.assertIsNone(running.poll())
                self.assertEqual(installed.read_bytes(), binary.read_bytes())
                self.assertEqual(installed.stat().st_mode & 0o777, 0o755)
                self.assertFalse(list(installed.parent.glob('.install-*')))
            finally:
                running.terminate()
                running.wait(timeout=3)

    def bundle(self):
        project = Path(__file__).resolve().parents[1]
        default = project if (project / 'bin/ts-redir').exists() else project / 'build/tailbridge-pi'
        bundle = Path(os.environ.get('TAILBRIDGE_BUNDLE', default)).resolve()
        if not (bundle / 'bin/ts-redir').exists():
            self.skipTest('Build the bundle before the complete installer test')
        # Public bundles fetch the vendor overlay only
        # at installation. File-only tests use an explicit synthetic stand-in.
        if not (bundle / 'vendor/mhs35ips.dtbo').exists():
            fixture = tempfile.TemporaryDirectory()
            self.addCleanup(fixture.cleanup)
            copied = Path(fixture.name) / 'bundle'
            shutil.copytree(bundle, copied, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            (copied / 'vendor/mhs35ips.dtbo').write_bytes(b'synthetic overlay for file-only tests')
            bundle = copied
        return bundle

    def test_kiosk_upgrade_is_reversible_and_retains_original_sysrq(self):
        with tempfile.TemporaryDirectory() as folder:
            root, backup = Path(folder) / 'root', Path(folder) / 'backup'
            policy = root / 'etc/sysctl.d/99-tailbridge-kiosk.conf'
            policy.parent.mkdir(parents=True)
            policy.write_text('# Original setting\nkernel.sysrq = 176\n')
            sysrq = root / 'proc/sys/kernel/sysrq'
            sysrq.parent.mkdir(parents=True)
            sysrq.write_text('176\n')
            cad = root / 'etc/systemd/system/ctrl-alt-del.target'
            cad.parent.mkdir(parents=True)
            cad.symlink_to('/usr/lib/systemd/system/reboot.target')
            installer = Installer(root, backup)
            source = Path(__file__).resolve().parents[1]
            configure_kiosk(installer, source)
            self.assertEqual(os.readlink(cad), '/dev/null')
            self.assertIn('kernel.sysrq = 0', policy.read_text())
            self.assertIn('CtrlAltDelBurstAction=none', (root / 'etc/systemd/system.conf.d/99-tailbridge-kiosk.conf').read_text())
            sysrq.write_text('0\n')
            configure_kiosk(Installer(root, backup), source)
            self.assertEqual(json.loads((backup / 'kiosk.json').read_text()), {'sysrq': 176})
            installer.restore()
            self.assertEqual(os.readlink(cad), '/usr/lib/systemd/system/reboot.target')
            self.assertIn('kernel.sysrq = 176', policy.read_text())
            self.assertFalse((root / 'etc/systemd/system.conf.d/99-tailbridge-kiosk.conf').exists())
            self.assertFalse((root / 'etc/systemd/system/getty@tty1.service').exists())

    def test_complete_staged_configuration_round_trip(self):
        bundle = self.bundle()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'root'; backup = Path(folder) / 'backup'
            boot = root / 'boot/firmware/config.txt'
            boot.parent.mkdir(parents=True)
            original = 'arm_64bit=1\ndtoverlay=vc4-kms-v3d\n'
            boot.write_text(original)
            sysrq = root / 'proc/sys/kernel/sysrq'
            sysrq.parent.mkdir(parents=True)
            sysrq.write_text('438\n')
            preserved = root / 'etc/tailbridge/environment'
            preserved.parent.mkdir(parents=True)
            preserved.write_text('WIFI_INTERFACE=wlan0\nFRAMEBUFFER=/dev/fb1\n')
            cad = root / 'etc/systemd/system/ctrl-alt-del.target'
            cad.parent.mkdir(parents=True)
            cad.symlink_to('/usr/lib/systemd/system/reboot.target')
            credentials = root / 'etc/NetworkManager/system-connections/synthetic.nmconnection'
            credentials.parent.mkdir(parents=True)
            credentials.write_text('synthetic-profile-sentinel')
            command = ['python3', str(bundle / 'scripts/configure_system.py'), '--root', str(root), '--backup', str(backup)]
            subprocess.run(command, check=True)
            self.assertEqual(len(list((root / 'etc/systemd/system').glob('tailbridge-*.service'))), 4)
            self.assertTrue((root / 'boot/firmware/overlays/mhs35ips.dtbo').is_file())
            self.assertIn('dtoverlay=mhs35ips', boot.read_text())
            installed = root / 'opt/tailbridge'
            for name in ('tailbridge/ui.py', 'tailbridge/network.py', 'scripts/start-display.sh', 'scripts/verify_kiosk.py', 'bin/ts-redir'):
                self.assertEqual((installed / name).read_bytes(), (bundle / name).read_bytes())
            for name in ('apply-boot-fix.sh', 'update_kiosk.py'):
                self.assertFalse((installed / 'scripts' / name).exists())
            self.assertEqual((installed / 'bin/ts-redir').stat().st_mode & 0o777, 0o755)
            self.assertEqual((installed / 'tailbridge/ui.py').stat().st_mode & 0o777, 0o644)
            self.assertIn('kernel.sysrq = 0', (root / 'etc/sysctl.d/99-tailbridge-kiosk.conf').read_text())
            self.assertIn('CtrlAltDelBurstAction=none', (root / 'etc/systemd/system.conf.d/99-tailbridge-kiosk.conf').read_text())
            self.assertEqual(os.readlink(cad), '/dev/null')
            self.assertEqual(os.readlink(root / 'etc/systemd/system/getty@tty1.service'), '/dev/null')
            # A repeated install must keep the first recovery baseline and the
            # user's environment/profile, even after the live policy is applied.
            first_boot = boot.read_text()
            sysrq.write_text('0\n')
            subprocess.run(command, check=True)
            self.assertEqual(boot.read_text(), first_boot)
            self.assertEqual(json.loads((backup / 'kiosk.json').read_text()), {'sysrq': 438})
            self.assertIn('FRAMEBUFFER=/dev/fb1', preserved.read_text())
            subprocess.run(command + ['--restore'], check=True)
            self.assertEqual(boot.read_text(), original)
            self.assertFalse((root / 'boot/firmware/overlays/mhs35ips.dtbo').exists())
            self.assertFalse((root / 'etc/sysctl.d/99-tailbridge-kiosk.conf').exists())
            self.assertFalse((root / 'etc/systemd/system.conf.d/99-tailbridge-kiosk.conf').exists())
            self.assertFalse((root / 'etc/systemd/system/getty@tty1.service').is_symlink())
            self.assertEqual(os.readlink(cad), '/usr/lib/systemd/system/reboot.target')
            self.assertIn('FRAMEBUFFER=/dev/fb1', preserved.read_text())
            self.assertEqual(credentials.read_text(), 'synthetic-profile-sentinel')

    def test_payload_removes_retired_patch_scripts(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            scripts = root / 'opt/tailbridge/scripts'
            scripts.mkdir(parents=True)
            for name in ('apply-boot-fix.sh', 'update_kiosk.py'):
                (scripts / name).write_text('obsolete patch')
            install_payload(self.bundle(), root)
            for name in ('apply-boot-fix.sh', 'update_kiosk.py'):
                self.assertFalse((scripts / name).exists())
            self.assertTrue((scripts / 'install.sh').is_file())

    def test_payload_rejects_symlinks_before_writing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            installed = root / 'opt/tailbridge'
            installed.mkdir(parents=True)
            outside = root / 'untouched'
            outside.write_text('sentinel')
            (installed / 'unexpected').symlink_to(outside)
            with self.assertRaises(ValueError):
                install_payload(self.bundle(), root)
            self.assertEqual(outside.read_text(), 'sentinel')
            self.assertFalse((installed / 'tailbridge').exists())

    def test_config_preserves_unrelated_settings_and_is_idempotent(self):
        original = '# User setting\narm_64bit=1\ndtoverlay=vc4-kms-v3d\n[pi4]\nfoo=bar\n'
        result = boot_config(original)
        self.assertEqual(boot_config(result), result)
        self.assertIn('foo=bar', result)
        self.assertIn('[all]\ndtparam=spi=on', result)
        self.assertEqual(result.count('dtoverlay=mhs35ips'), 1)

    def test_backup_restores_files_symlinks_and_absence(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'root'; root.mkdir()
            (root / 'existing').write_text('original')
            (root / 'alias').symlink_to('/old/target')
            installer = Installer(root, Path(folder) / 'backup')
            installer.write('existing', 'new')
            installer.write('alias', 'replacement')
            installer.write('created', 'new')
            installer.write('existing', 'upgrade')
            installer.restore()
            self.assertEqual((root / 'existing').read_text(), 'original')
            self.assertEqual(os.readlink(root / 'alias'), '/old/target')
            self.assertFalse((root / 'created').exists())


if __name__ == '__main__': unittest.main()
