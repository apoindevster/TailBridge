import unittest
from types import SimpleNamespace
from unittest.mock import patch
from scripts.verify_kiosk import check_account, check_logins, preflight


class KioskLoginTests(unittest.TestCase):
    def test_fresh_install_allows_missing_ui_account(self):
        with patch('scripts.verify_kiosk.pwd.getpwnam', side_effect=KeyError):
            check_account()

    def test_existing_ui_account_cannot_be_root_or_have_a_shell(self):
        for uid, shell in ((0, '/usr/sbin/nologin'), (999, '/bin/bash')):
            with self.subTest(uid=uid, shell=shell), patch('scripts.verify_kiosk.pwd.getpwnam',
                    return_value=SimpleNamespace(pw_uid=uid, pw_gid=985, pw_shell=shell)), self.assertRaises(RuntimeError):
                check_account()

    def test_existing_ui_account_requires_dedicated_unprivileged_group(self):
        account = SimpleNamespace(pw_uid=999, pw_gid=985, pw_shell='/usr/sbin/nologin')
        with patch('scripts.verify_kiosk.pwd.getpwnam', return_value=account):
            with patch('scripts.verify_kiosk.grp.getgrnam', return_value=SimpleNamespace(gr_gid=985)):
                check_account()
            for gid in (0, 984):
                with patch('scripts.verify_kiosk.grp.getgrnam', return_value=SimpleNamespace(gr_gid=gid)), self.assertRaises(RuntimeError):
                    check_account()

    def test_preflight_rejects_missing_ssh_recovery(self):
        with patch('scripts.verify_kiosk.check_logins'), patch('scripts.verify_kiosk.check_account'), \
                patch('scripts.verify_kiosk.output', return_value='inactive'), self.assertRaises(RuntimeError):
            preflight()

    def audit(self, command):
        def reply(*args):
            if 'list-units' in args:
                return 'serial-getty@ttyS0.service loaded active running Serial Getty'
            return command
        with patch('scripts.verify_kiosk.output', side_effect=reply):
            check_logins()

    def test_distribution_password_login_is_accepted(self):
        self.audit(r'{ path=/sbin/agetty ; argv[]=/sbin/agetty -o -- \u --noreset --noclear - ${TERM} ; }')

    def test_automatic_or_custom_login_is_rejected(self):
        for flags in ('--autologin root', '--autologin=root', '-a root', '--skip-login', '-n',
                      '--login-program=/bin/sh', '-l /bin/sh', '-o -f root', '-an', '--login-options=-f'):
            with self.subTest(flags=flags), self.assertRaises(RuntimeError):
                self.audit(r'{ path=/sbin/agetty ; argv[]=/sbin/agetty -o -- \u --noreset --noclear - ${TERM} ' + flags + ' ; }')
