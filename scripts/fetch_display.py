#!/usr/bin/env python3
"""Obtain the pinned vendor overlay for local installation; do not redistribute it."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import urllib.request


def fetch_display(project, opener=urllib.request.urlopen):
    source = json.loads((project / 'packaging/display-source.json').read_text())
    if not source['url'].startswith('https://'):
        raise ValueError('Display overlay source must use HTTPS')
    directory = project / 'vendor'
    target = directory / 'mhs35ips.dtbo'
    if directory.is_symlink() or target.is_symlink():
        raise ValueError('Refusing a symlink for the display download')
    directory.mkdir(exist_ok=True)
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() != source['sha256']:
            raise ValueError('Existing display overlay does not match the pinned checksum')
        return target
    with opener(source['url'], timeout=30) as response:
        if not response.geturl().startswith('https://'):
            raise ValueError('Display overlay redirected outside HTTPS')
        payload = response.read(1024 * 1024 + 1)
    if len(payload) > 1024 * 1024 or hashlib.sha256(payload).hexdigest() != source['sha256']:
        raise ValueError('Display overlay download failed checksum validation')
    fd, temporary = tempfile.mkstemp(prefix='.overlay-', dir=directory)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return target


if __name__ == '__main__':
    fetch_display(Path(__file__).resolve().parents[1])
    print('Display overlay ready; pinned SHA-256 verified.')
