import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from scripts.fetch_display import fetch_display


class Response(io.BytesIO):
    def geturl(self):
        return 'https://example.invalid/overlay'


class DisplayDownloadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / 'packaging').mkdir()
        self.payload = b'synthetic display overlay for download tests'
        self.source = {'url': 'https://example.invalid/overlay',
                       'sha256': hashlib.sha256(self.payload).hexdigest()}
        self.save_source()

    def save_source(self):
        (self.root / 'packaging/display-source.json').write_text(json.dumps(self.source))

    def test_verified_download_and_offline_reuse(self):
        opener = Mock(return_value=Response(self.payload))
        target = fetch_display(self.root, opener)
        self.assertEqual(target.read_bytes(), self.payload)
        self.assertEqual(target.stat().st_mode & 0o777, 0o644)
        self.assertEqual(fetch_display(self.root, opener), target)
        opener.assert_called_once_with(self.source['url'], timeout=30)
        self.assertEqual(list(target.parent.iterdir()), [target])

    def test_bad_download_never_installs(self):
        for payload in (b'wrong checksum', b'x' * (1024 * 1024 + 1)):
            with self.subTest(size=len(payload)), self.assertRaises(ValueError):
                fetch_display(self.root, Mock(return_value=Response(payload)))
            self.assertEqual(list((self.root / 'vendor').iterdir()), [])

    def test_bad_existing_file_is_preserved_and_rejected(self):
        (self.root / 'vendor').mkdir()
        target = self.root / 'vendor/mhs35ips.dtbo'
        target.write_bytes(b'unexpected existing file')
        opener = Mock()
        with self.assertRaises(ValueError):
            fetch_display(self.root, opener)
        opener.assert_not_called()
        self.assertEqual(target.read_bytes(), b'unexpected existing file')

    def test_http_source_and_redirect_are_rejected(self):
        self.source['url'] = 'http://example.invalid/overlay'
        self.save_source()
        opener = Mock()
        with self.assertRaises(ValueError):
            fetch_display(self.root, opener)
        opener.assert_not_called()
        self.source['url'] = 'https://example.invalid/overlay'
        self.save_source()
        response = Response(self.payload)
        response.geturl = lambda: 'http://example.invalid/overlay'
        with self.assertRaises(ValueError):
            fetch_display(self.root, Mock(return_value=response))
        self.assertFalse((self.root / 'vendor/mhs35ips.dtbo').exists())

    def test_symlink_directory_and_file_are_rejected(self):
        outside = self.root / 'outside'
        outside.mkdir()
        vendor = self.root / 'vendor'
        vendor.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            fetch_display(self.root, Mock())
        vendor.unlink()
        vendor.mkdir()
        (vendor / 'mhs35ips.dtbo').symlink_to(outside / 'file')
        with self.assertRaises(ValueError):
            fetch_display(self.root, Mock())
        self.assertEqual(list(outside.iterdir()), [])
