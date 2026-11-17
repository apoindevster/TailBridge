#!/usr/bin/env python3
"""Check publishable file boundaries; optionally stage exact Git-visible source.

This is an artifact hygiene check, not a replacement for secret scanning or review.
It never reads ignored working files or prints file contents.
"""
import argparse
from pathlib import Path, PurePosixPath
import shutil
import struct
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_PARTS = {'.git', '.cache', '.venv', '.local', '.ssh', '__pycache__',
                 '.pytest_cache', 'install-backup', 'node_modules'}
PRIVATE_SUFFIXES = {'.pyc', '.pem', '.key', '.p12', '.pfx', '.nmconnection',
                    '.pcap', '.pcapng', '.log', '.dtbo', '.dtb', '.zip', '.gz'}
SCREENSHOTS = {name + '.png' for name in (
    'wifi', 'password', 'symbols', 'joining', 'failed-join', 'open-failed',
    'status', 'status-renamed', 'status-no-name', 'status-long-name', 'status-no-qr',
    'status-error', 'status-offline', 'enrollment')}


def check_path(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError(f'Unsafe publication path: {name}')
    if (PRIVATE_PARTS.intersection(path.parts) or path.suffix.lower() in PRIVATE_SUFFIXES
            or path.name.startswith('tailscaled.state')
            or path.name.startswith('.env') and path.name != '.env.example'
            or path.name in {'rules.json', 'id_rsa', 'id_ed25519', '.coverage',
                             '.bash_history', '.zsh_history', '.netrc'}):
        raise ValueError(f'Private/generated file must not be published: {name}')


def check_png(file):
    # Reject text, EXIF, timestamps and unknown chunks; screenshot pixels are
    # reviewed separately and QR contents checked by tests/ui_smoke.py.
    data = file.read_bytes()
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError(f'Invalid PNG: {file.name}')
    offset = 8
    chunks = []
    while offset < len(data):
        length, chunk = struct.unpack('>I4s', data[offset:offset + 8])
        if offset + 12 + length > len(data):
            raise ValueError(f'Truncated PNG: {file.name}')
        if chunk not in {b'IHDR', b'PLTE', b'tRNS', b'IDAT', b'IEND'}:
            raise ValueError(f'Unexpected screenshot metadata: {file.name}; regenerate with -strip')
        if chunk == b'IHDR' and struct.unpack('>II', data[offset + 8:offset + 16]) != (480, 320):
            raise ValueError(f'Wrong screenshot size: {file.name}')
        chunks.append(chunk)
        offset += length + 12
    if not chunks or chunks[0] != b'IHDR' or chunks[-1] != b'IEND' or b'IDAT' not in chunks:
        raise ValueError(f'Incomplete PNG: {file.name}')


def check_files(root, names, bundle=False):
    names = set(names)
    required = {'README.md', 'LICENSE', 'SECURITY.md', 'CONTRIBUTING.md',
                'packaging/display-source.json', 'scripts/install.sh', 'scripts/fetch_display.py'}
    if bundle:
        required.update({'bin/ts-redir', 'licenses/ts-redir-MIT.txt', 'licenses/Go-LICENSE.txt'})
    else:
        required.update({'.github/workflows/ci.yml', '.gitignore'})
    required.update('artifacts/' + name for name in SCREENSHOTS)
    if required - names:
        raise ValueError('Missing publication files: ' + ', '.join(sorted(required - names)))
    for name in sorted(names):
        check_path(name)
        file = root / name
        if file.is_symlink() or not file.is_file():
            raise ValueError(f'Only regular publication files are allowed: {name}')
        if not bundle and file.parts[len(root.parts)] in {'build', 'dist'}:
            raise ValueError(f'Generated output must not be in source: {name}')
        if file.suffix == '.png':
            if PurePosixPath(name).parent != PurePosixPath('artifacts') or file.name not in SCREENSHOTS:
                raise ValueError(f'Unreviewed screenshot: {name}')
            check_png(file)
        elif not (bundle and name == 'bin/ts-redir'):
            if file.stat().st_size > 1024 * 1024:
                raise ValueError(f'Unexpected large source/document: {name}')
            try:
                content = file.read_text(encoding='utf-8')
            except UnicodeDecodeError as exc:
                raise ValueError(f'Unexpected binary: {name}') from exc
            if '\x00' in content:
                raise ValueError(f'Unexpected binary content: {name}')
    if bundle:
        with (root / 'bin/ts-redir').open('rb') as binary:
            header = binary.read(20)
        if header[:6] != b'\x7fELF\x02\x01' or header[18:20] != b'\xb7\x00':
            raise ValueError('Release binary must be Linux arm64 ELF')
    print(f'Publication file checks passed: {len(names)} files ({"bundle" if bundle else "source"}).')


def check_archive(file):
    with tarfile.open(file, 'r:gz') as archive:
        for member in archive:
            name = PurePosixPath(member.name)
            if name.is_absolute() or '..' in name.parts or name.parts[0] != 'tailbridge-pi':
                raise ValueError('Unsafe release archive path')
            if not (member.isfile() or member.isdir()):
                raise ValueError('Release archive contains a link or special file')
            if member.uid or member.gid or member.uname or member.gname:
                raise ValueError('Release archive leaks builder ownership metadata')
            if len(name.parts) > 1:
                check_path(str(PurePosixPath(*name.parts[1:])))
    print('Archive paths, file types and anonymous ownership passed.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--stage-source', type=Path)
    args = parser.parse_args()
    if args.bundle:
        if args.stage_source:
            parser.error('--stage-source cannot be combined with --bundle')
        root = args.bundle.resolve()
        names = [p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() or p.is_symlink()]
        check_files(root, names, bundle=True)
    else:
        output = subprocess.check_output(['git', 'ls-files', '--cached', '--others',
                                          '--exclude-standard', '-z'], cwd=ROOT)
        names = sorted(set(output.decode().rstrip('\x00').split('\x00')))
        check_files(ROOT, names)
        if args.stage_source:
            destination = args.stage_source.resolve()
            if destination == ROOT or ROOT in destination.parents and '.cache' not in destination.relative_to(ROOT).parts:
                parser.error('Stage source into an empty .cache subdirectory or outside the project')
            destination.mkdir(parents=True, exist_ok=False)
            for name in names:
                target = destination / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)
            print('Staged exact Git-visible source for secret scanning.')
    if args.archive:
        check_archive(args.archive)


if __name__ == '__main__':
    main()
