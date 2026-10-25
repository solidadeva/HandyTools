import functools
import hashlib
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from engine import inspect
import mac_updater as mac


class MacReleaseTests(unittest.TestCase):
    def test_arch_selection_and_origin(self):
        data=b'test dmg'
        assets=[]
        for arch in ('arm64','x86_64'):
            name=f'HandyToolsApp-macOS-{arch}-v0.5.0.dmg'
            assets.append(dict(name=name,size=len(data),digest='sha256:'+hashlib.sha256(data).hexdigest(),browser_download_url=mac.PREFIX+'v0.5.0/'+name))
        def fetch(*a):return json.dumps(dict(tag_name='v0.5.0',assets=assets)).encode()
        for arch in ('arm64','x86_64'):
            package=mac.latest_mac_release(fetch=fetch,machine=arch)
            self.assertIn(arch,package['name'])
        assets[0]['browser_download_url']='https://evil.example/app.dmg'
        with self.assertRaises(ValueError):mac.latest_mac_release(fetch=fetch,machine='arm64')

    def test_download_checksum_and_cancel_cleanup(self):
        from updater import UpdateCancelled
        data=b'test dmg';name='HandyToolsApp-macOS-arm64-v0.5.0.dmg'
        package=dict(kind='mac-dmg',version='0.5.0',name=name,url=mac.PREFIX+'v0.5.0/'+name,size=len(data),sha256=hashlib.sha256(data).hexdigest())
        stage=mac.stage_mac_update(package,opener=lambda *a,**k:io.BytesIO(data));self.addCleanup(shutil.rmtree,stage,True)
        self.assertEqual(mac.staged_installer(stage).read_bytes(),data)
        (stage/name).write_bytes(b'corrupt!')
        with self.assertRaises(ValueError):mac.staged_installer(stage)
        cancel=threading.Event();cancel.set()
        with self.assertRaises(UpdateCancelled):mac.stage_mac_update(package,cancel,opener=lambda *a,**k:io.BytesIO(data))
        with self.assertRaises(ValueError):mac.stage_mac_update(package,opener=lambda *a,**k:io.BytesIO(data+b'X'))


@unittest.skipIf(__import__('os').name=='nt','Native POSIX adapter')
class NativeDownloadTests(unittest.TestCase):
    def test_real_video_and_mp3_download_through_isolated_worker(self):
        from workers import Task
        class Quiet(SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);fixture=root/'sample.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=160x120:rate=10:duration=1',
                '-f','lavfi','-i','sine=duration=1','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(fixture)],check=True)
            server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(root)))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                for quality in ('best','audio'):
                    folder=root/quality;folder.mkdir()
                    task=Task('download',dict(folder=str(folder),url=f'http://127.0.0.1:{server.server_port}/sample.mp4',quality=quality))
                    output=Path(task.download_posix())
                    self.assertTrue(output.is_file())
                    streams=inspect(output)['streams']
                    if quality=='audio':self.assertEqual(streams[0]['codec_name'],'mp3')
                    else:
                        self.assertEqual(streams[0]['codec_name'],'h264');self.assertEqual(streams[0]['pix_fmt'],'yuv420p')
                        self.assertEqual(streams[1]['codec_name'],'aac')
                        self.assertTrue(any((folder/'.HandyTools-source').iterdir()))
            finally:server.shutdown();server.server_close();thread.join(timeout=5)
