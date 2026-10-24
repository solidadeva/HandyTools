import hashlib
import io
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile
import ffmpeg_setup as setup


def archive(missing=False):
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as z:
        z.writestr('ffmpeg-build/bin/ffmpeg.exe', b'MZ-ffmpeg')
        if not missing:
            z.writestr('ffmpeg-build/bin/ffprobe.exe', b'MZ-ffprobe')
        z.writestr('ffmpeg-build/LICENSE', b'GPL license')
        z.writestr('../../unwanted.txt', b'never extract this')
    return data.getvalue()


class Response(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.headers = {'Content-Length': str(len(data))}


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.target = Path(self.temp.name) / 'tools' / 'bin'
        self.platform = patch.object(setup.platform, 'system', return_value='Windows')
        self.platform.start()
        self.addCleanup(self.platform.stop)
        self.arch = patch.object(setup.platform, 'machine', return_value='AMD64')
        self.arch.start()
        self.addCleanup(self.arch.stop)

    def run_install(self, data=None, checksum=None, **kwargs):
        data = archive() if data is None else data
        checksum = hashlib.sha256(data).hexdigest() if checksum is None else checksum
        def opener(request, timeout):
            self.assertEqual(timeout, 30)
            return Response(checksum.encode() if request.full_url.endswith('.sha256') else data)
        return setup.install(destination=self.target, opener=opener, validator=lambda p: None, **kwargs)

    def test_install_and_existing_detection(self):
        updates = []
        self.run_install(progress=lambda *v: updates.append(v))
        self.assertEqual((self.target/'ffmpeg.exe').read_bytes(), b'MZ-ffmpeg')
        self.assertEqual((self.target/'ffprobe.exe').read_bytes(), b'MZ-ffprobe')
        self.assertTrue((self.target/'LICENSE').is_file())
        self.assertEqual(updates[-1][1], 100)
        self.assertEqual(list(self.target.parent.iterdir()), [self.target])
        self.assertFalse((Path(self.temp.name)/'unwanted.txt').exists())
        from workers import Task
        with patch('workers.tool', return_value='present'), patch('workers.install') as download:
            Task('convert', {}).ensure_tools()
            download.assert_not_called()

    def test_checksum_failure_and_retry(self):
        with self.assertRaisesRegex(RuntimeError, 'verification'):
            self.run_install(checksum='0'*64)
        self.assertFalse(self.target.exists())
        self.assertEqual(list(self.target.parent.iterdir()), [])
        self.run_install()
        self.assertTrue((self.target/'ffprobe.exe').exists())

    def test_missing_binary_does_not_publish(self):
        with self.assertRaisesRegex(RuntimeError, 'missing'):
            self.run_install(data=archive(missing=True))
        self.assertFalse(self.target.exists())

    def test_cancel_and_cleanup(self):
        cancel = threading.Event()
        def progress(message, percent):
            if message.startswith('Downloading'):
                cancel.set()
        with self.assertRaises(setup.SetupCancelled):
            self.run_install(progress=progress, cancel=cancel)
        self.assertFalse(self.target.exists())
        self.assertEqual(list(self.target.parent.iterdir()), [])

    def test_network_error_keeps_existing_files(self):
        self.target.mkdir(parents=True)
        (self.target/'ffmpeg.exe').write_bytes(b'old')
        with self.assertRaises(TimeoutError):
            setup.install(destination=self.target, opener=lambda *a, **k: (_ for _ in ()).throw(TimeoutError()))
        self.assertEqual((self.target/'ffmpeg.exe').read_bytes(), b'old')

    def test_incompatible_windows_arch(self):
        with patch.object(setup.platform, 'machine', return_value='ARM64'):
            with self.assertRaisesRegex(RuntimeError, '64-bit Windows'):
                self.run_install()

if __name__ == '__main__':
    unittest.main()
