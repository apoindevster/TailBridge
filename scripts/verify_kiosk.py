#!/usr/bin/env python3
"""Read-only checks for the running appliance. Never prints network credentials."""
import argparse
import grp
import os
from pathlib import Path
import pwd
import re
import subprocess


def output(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def check_logins():
    # Inspect effective commands, including instance drop-ins, rather than merely
    # trusting the vendor template. Authenticated console/serial recovery stays.
    units = {'getty@tty%d.service' % n for n in range(2, 7)}
    units.add('serial-getty@ttyS0.service')
    listing = output('systemctl', 'list-units', '--all', '--full', '--plain', '--no-legend',
                     'getty@*.service', 'serial-getty@*.service')
    units.update(line.split()[0] for line in listing.splitlines() if line.strip())
    for unit in sorted(units):
        command = output('systemctl', 'show', '--property=ExecStart', '--value', unit)
        if not command:  # Masked tty1 has no executable.
            continue
        # This appliance targets Trixie's reviewed vendor commands. Fail closed
        # on custom/bundled options instead of trying to blacklist every agetty
        # authentication bypass spelling or alternative login program.
        match = re.search(r'argv\[\]=(.*?) ;', command)
        expected = {
            r'/sbin/agetty -o -- \u --noreset --noclear - ${TERM}',
            r'/sbin/agetty -o -- \u --noreset --noclear --keep-baud 115200,57600,38400,9600 - ${TERM}',
        }
        require(match is not None and match[1] in expected, 'Review console authentication for ' + unit)


def check_account():
    try:
        account = pwd.getpwnam('tailbridge')
    except KeyError:
        return  # The installer creates the dedicated account on a fresh image.
    require(account.pw_uid != 0 and account.pw_shell in ('/usr/sbin/nologin', '/sbin/nologin'),
            'Existing tailbridge account must be unprivileged with a nologin shell')
    try:
        group = grp.getgrnam('tailbridge')
    except KeyError as error:
        raise RuntimeError('Existing tailbridge account needs its dedicated group') from error
    require(group.gr_gid != 0 and account.pw_gid == group.gr_gid,
            'Existing tailbridge account must use its unprivileged dedicated group')


def preflight():
    check_logins()
    check_account()
    require(output('systemctl', 'is-active', 'sshd') == 'active', 'Enable authenticated SSH recovery before installation')
    print('PASS: console login policy, UI account and SSH installation preflight.')


def verify():
    require(os.geteuid() == 0, 'Run this audit with sudo.')
    check_logins()
    for unit in ('tailbridge-display', 'tailbridge-network', 'sshd'):
        require(output('systemctl', 'is-active', unit) == 'active', unit + ' is not active')
    require(output('systemctl', 'get-default') == 'multi-user.target', 'Unexpected boot target')
    require(output('systemctl', 'show', '--property=ActiveState', '--value', 'display-manager.service') == 'inactive', 'A desktop login manager is running alongside the kiosk')
    for name in ('getty@tty1.service', 'ctrl-alt-del.target'):
        require(output('systemctl', 'show', '--property=LoadState', '--value', name) == 'masked', name + ' is not masked')
    require(output('systemctl', 'show', '--property=CtrlAltDelBurstAction', '--value') == 'none', 'Repeated Ctrl-Alt-Del is enabled')
    require(Path('/proc/sys/kernel/sysrq').read_text().strip() == '0', 'Keyboard SysRq is enabled')
    account = pwd.getpwnam('tailbridge')
    require(account.pw_uid != 0 and account.pw_shell in ('/usr/sbin/nologin', '/sbin/nologin'), 'UI account permits a login shell')
    uis, servers = [], []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            args = (entry / 'cmdline').read_bytes().split(b'\0')
            if args and args[0] in (b'/usr/bin/python3', b'python3') and b'tailbridge.ui' in args:
                uis.append(entry)
            if args and args[0] == b'/usr/lib/xorg/Xorg':
                servers.append(args)
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
    require(len(uis) == 1, 'Expected exactly one UI process')
    status = dict(line.split(':', 1) for line in (uis[0] / 'status').read_text().splitlines() if ':' in line)
    require(all(int(v) == account.pw_uid for v in status['Uid'].split()), 'UI is not fully unprivileged')
    require(status['NoNewPrivs'].strip() == '1', 'UI can gain new privileges')
    for field in ('CapInh', 'CapPrm', 'CapEff', 'CapBnd', 'CapAmb'):
        require(int(status[field], 16) == 0, 'UI retains capabilities: ' + field)
    require(len(servers) == 1 and b'-nolisten' in servers[0] and b'tcp' in servers[0], 'Unexpected X server listener policy')
    config = Path('/run/tailbridge-display/xorg.conf').read_text()
    require('Option "DontVTSwitch" "true"' in config and 'Option "DontZap" "true"' in config, 'X keyboard escapes are enabled')
    require(output('systemctl', 'show', '--property=Restart', '--value', 'tailbridge-display') == 'always', 'Display recovery is disabled')
    print('PASS: app-only startup, login-gated consoles, keyboard escape policy, unprivileged UI, SSH recovery.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--preflight', action='store_true', help='check prerequisites before installation; no writes')
    args = parser.parse_args()
    preflight() if args.preflight else verify()
