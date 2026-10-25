import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import exe_updater as exe
from updater import UpdateCancelled


class ExecutableUpdateTests(unittest.TestCase):
    def setUp(self):
        self.data = b'MZtest executable payload'
        self.package = dict(kind='windows-exe', version='0.5.0',
            name='HandyToolsApp-Windows-x64-v0.5.0.exe', size=len(self.data),
            sha256=hashlib.sha256(self.data).hexdigest(),
            url=exe.PREFIX+'v0.5.0/HandyToolsApp-Windows-x64-v0.5.0.exe')
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)

    def test_latest_asset_selection_digest_and_companion(self):
        asset = dict(name=self.package['name'], size=self.package['size'],
                     browser_download_url=self.package['url'], digest='sha256:'+self.package['sha256'])
        release = dict(tag_name='v0.5.0', assets=[dict(name='unrelated.exe'), asset])
        calls = []
        def fetch(url, limit, cancel):
            calls.append(url)
            return json.dumps(release).encode() if url.endswith('/latest') else (self.package['sha256']+'  '+self.package['name']).encode()
        self.assertEqual(exe.latest_exe_release(fetch=fetch), self.package)
        asset.pop('digest');release['assets'].append(dict(name=asset['name']+'.sha256',browser_download_url=asset['browser_download_url']+'.sha256'))
        self.assertEqual(exe.latest_exe_release(fetch=fetch), self.package)
        self.assertTrue(calls[-1].endswith('.sha256'))
        asset['browser_download_url'] = 'https://evil.example/app.exe'
        with self.assertRaises(ValueError): exe.latest_exe_release(fetch=fetch)
        release['assets'] = []
        with self.assertRaises(RuntimeError): exe.latest_exe_release(fetch=fetch)

    def test_streaming_verified_download_and_staged_tampering(self):
        progress = []
        stage = exe.stage_exe_update(self.package, progress=lambda *x:progress.append(x),
                                    opener=lambda *a,**k:io.BytesIO(self.data))
        import shutil
        self.addCleanup(shutil.rmtree, stage, True)
        self.assertEqual((stage/'package.exe').read_bytes(),self.data)
        self.assertTrue((stage/'install.ps1').is_file())
        self.assertEqual(progress[-1][0],100)
        exe.verify_exe(stage/'package.exe',self.package)
        (stage/'package.exe').write_bytes(b'MZ'+b'X'*(len(self.data)-2))
        with self.assertRaises(ValueError):exe.verify_exe(stage/'package.exe',self.package)

    def test_failed_cancelled_and_oversized_downloads_clean_stage(self):
        root = Path(self.temp.name)
        for data in (b'MZshort', self.data+b'x', b'NO'+self.data[2:]):
            stage = root/'stage';stage.mkdir()
            with patch('exe_updater.tempfile.mkdtemp', return_value=str(stage)):
                with self.assertRaises(ValueError):exe.stage_exe_update(self.package, opener=lambda *a,**k:io.BytesIO(data))
            self.assertFalse(stage.exists())
        cancel=threading.Event();cancel.set();stage=root/'stage';stage.mkdir()
        with patch('exe_updater.tempfile.mkdtemp', return_value=str(stage)):
            with self.assertRaises(UpdateCancelled):exe.stage_exe_update(self.package,cancel,opener=lambda *a,**k:io.BytesIO(self.data))
        self.assertFalse(stage.exists())

    def test_package_origin_version_size_and_checksum_validation(self):
        for changes in (dict(url=self.package['url']+'?redirect=bad'),dict(version='../x'),dict(size=exe.MAX_EXE+1),dict(size=True),dict(sha256='x'*64),dict(kind='source')):
            with self.assertRaises(ValueError):exe.validate_package(dict(self.package,**changes))

    def test_installer_verifies_before_launch_and_resets_frozen_environment(self):
        import shutil
        stage=exe.stage_exe_update(self.package,opener=lambda *a,**k:io.BytesIO(self.data))
        self.addCleanup(shutil.rmtree,stage,True)
        target=Path(self.temp.name)/'Handy tools.exe';target.write_bytes(b'old')
        with patch('exe_updater.sys.platform','win32'), patch('exe_updater.subprocess.CREATE_NO_WINDOW',0,create=True), patch('exe_updater.subprocess.Popen') as popen:
            exe.start_exe_installer(target,stage,123)
            self.assertEqual(popen.call_args.kwargs['env']['PYINSTALLER_RESET_ENVIRONMENT'],'1')
            self.assertIn(str(stage/'install.ps1'),popen.call_args.args[0])
            (stage/'package.exe').write_bytes(b'corrupted')
            popen.reset_mock()
            with self.assertRaises(ValueError):exe.start_exe_installer(target,stage,123)
            popen.assert_not_called()
        self.assertEqual(target.read_bytes(),b'old')
