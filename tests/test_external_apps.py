import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import external_apps as ext


def release():
    assets=[]
    for target in ('windows-x86_64.exe','windows-arm64.exe','linux-x86_64.AppImage','linux-arm64.AppImage','macos-x86_64.dmg','macos-arm64.dmg'):
        name='GenyConnect-1.4.950-'+target
        assets.append(dict(name=name,size=7,digest='sha256:'+hashlib.sha256(b'package').hexdigest(),browser_download_url=ext.PREFIX+'v1.4.950/'+name))
    assets.append(dict(name='GenyConnect-selfupdate-windows-x64.exe',size=7,browser_download_url=ext.PREFIX+'v1.4.950/selfupdate.exe'))
    return dict(tag_name='v1.4.950',assets=assets)


class ExternalAppTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name);self.release=release();self.asset=ext.select_package(self.release,'Windows','AMD64',{})

    def test_arch_and_package_selection_ignores_selfupdater(self):
        for system,machine,expected in [('Windows','AMD64','windows-x86_64.exe'),('Windows','ARM64','windows-arm64.exe'),('Darwin','arm64','macos-arm64.dmg'),('Linux','aarch64','linux-arm64.AppImage'),('Linux','x86_64','linux-x86_64.AppImage')]:
            self.assertTrue(ext.select_package(self.release,system,machine,{})['name'].endswith(expected))
        self.assertEqual(ext.host_target('Windows',environ={'PROCESSOR_ARCHITEW6432':'ARM64'}),('windows','arm64'))
        with self.assertRaises(RuntimeError):ext.host_target('Windows','i686',{})
        with self.assertRaises(RuntimeError):ext.select_package(dict(assets=[]),'Windows','AMD64',{})
        changed=release();changed['assets'][0]['browser_download_url']='https://evil.example/app.exe'
        with self.assertRaises(RuntimeError):ext.select_package(changed,'Windows','AMD64',{})

    def test_download_verified_and_cache_reused(self):
        calls=[]
        def opener(req,timeout):calls.append(req.full_url);return io.BytesIO(b'package')
        updates=[]
        path=ext.download_package(self.release,self.asset,self.folder,progress=lambda *x:updates.append(x),opener=opener)
        self.assertEqual(path.read_bytes(),b'package');self.assertEqual(updates[-1][0],100)
        second=ext.download_package(self.release,self.asset,self.folder,opener=lambda *x,**k:(_ for _ in ()).throw(AssertionError('no redownload')))
        self.assertEqual(path,second);self.assertEqual(len(calls),1)
        self.assertFalse(list(self.folder.glob('.geny-download-*')))

    def test_hash_failure_partial_cleanup_and_cancel(self):
        with self.assertRaises(RuntimeError):ext.download_package(self.release,self.asset,self.folder,opener=lambda *a,**k:io.BytesIO(b'badfile'))
        self.assertEqual(list(self.folder.iterdir()),[])
        cancel=threading.Event();cancel.set()
        with self.assertRaises(ext.InstallCancelled):ext.download_package(self.release,self.asset,self.folder,cancel)
        asset=dict(self.asset,name='../escape.exe')
        with self.assertRaises(ValueError):ext.download_package(self.release,asset,self.folder)
        asset=dict(self.asset,digest=None)
        with self.assertRaises(RuntimeError):ext.expected_digest(self.release,asset)

    def test_checksum_companion_supported(self):
        asset=dict(self.asset,digest=None)
        checksum=dict(name=asset['name']+'.sha256',browser_download_url=asset['browser_download_url']+'.sha256')
        source=dict(assets=[asset,checksum])
        text=(hashlib.sha256(b'package').hexdigest()+'  '+asset['name']).encode()
        self.assertEqual(ext.expected_digest(source,asset,lambda *a,**k:io.BytesIO(text)),hashlib.sha256(b'package').hexdigest())

    def test_windows_native_installer_must_complete_before_marking_installed(self):
        package=self.folder/'setup.exe';package.write_bytes(b'verified-package')
        installed=self.folder/'app/GenyConnect.exe';installed.parent.mkdir()
        invocations=[]
        def install(path):invocations.append(path);installed.write_bytes(b'app')
        with patch('external_apps.detect_installed',side_effect=lambda *a:installed if installed.is_file() else None):
            result=ext.install_package(package,self.release,'Windows',self.folder/'state',win_install=install)
        self.assertEqual(result,installed);self.assertEqual(invocations,[package])
        marker=json.loads((self.folder/'state/installed.json').read_text())
        self.assertEqual(marker['path'],str(installed));self.assertEqual(marker['version'],'v1.4.950')
        with patch('external_apps.detect_installed',return_value=None):
            with self.assertRaises(RuntimeError):ext.install_package(package,self.release,'Windows',self.folder/'failed',win_install=lambda p:None)
        self.assertFalse((self.folder/'failed/installed.json').exists())

    def test_linux_install_and_persisted_detection(self):
        package=self.folder/'app.AppImage';package.write_bytes(b'package')
        state=self.folder/'state';result=ext.install_package(package,self.release,'Linux',state)
        self.assertTrue(os.access(result,os.X_OK));self.assertEqual(result.read_bytes(),b'package')
        self.assertEqual(ext.detect_installed('Linux',state),result)
        result.unlink()
        with patch('external_apps.shutil.which',return_value=None):self.assertIsNone(ext.detect_installed('Linux',state))

    def test_failure_does_not_record_installation(self):
        package=self.folder/'setup.exe';package.write_bytes(b'package')
        def cancelled(path):raise RuntimeError('UAC cancelled')
        with self.assertRaisesRegex(RuntimeError,'UAC cancelled'):
            ext.install_package(package,self.release,'Windows',self.folder/'state',win_install=cancelled)
        self.assertFalse((self.folder/'state/installed.json').exists())


if __name__=='__main__':unittest.main()
