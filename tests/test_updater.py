import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from updater import (validate_manifest,managed_path,target_path,plan_update,stage_update,
    latest_release,fetch_bytes,version_tuple,UpdateCancelled,REPOSITORY,INSTALLED)
from update_apply import apply_update


REQUIRED=['version.py','app.py','launcher.py','launch.pyw','updater.py','update_apply.py','update_ui.py','requirements.txt']


def make_manifest(payload,version='0.4.0'):
    return dict(schema=1,repository=REPOSITORY,version=version,commit='a'*40,
                files={name:dict(size=len(data),sha256=hashlib.sha256(data).hexdigest()) for name,data in payload.items()})


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'installed';self.root.mkdir()
        self.payload={name:('new '+name).encode() for name in REQUIRED}
        for name in REQUIRED:
            (self.root/name).write_bytes(b'old')
        self.manifest=make_manifest(self.payload)

    def stage(self,payload=None,manifest=None):
        payload=payload or self.payload;manifest=manifest or self.manifest
        plan=plan_update(self.root,manifest)
        def fetch(url,limit,cancel,progress):
            from urllib.parse import unquote
            name=unquote(url.split('/'+'a'*40+'/',1)[1]);data=payload[name]
            progress(len(data));return data
        stage=stage_update(self.root,manifest,plan,fetch=fetch)
        self.addCleanup(lambda:__import__('shutil').rmtree(stage,ignore_errors=True))
        return stage

    def test_safe_paths_and_manifest_limits(self):
        self.assertEqual(managed_path('assets/icons/settings.svg'),'assets/icons/settings.svg')
        for name in ['../app.py','/app.py','C:/app.py','.venv/a.py','assets/../app.py','downloader/../../app.py',
                     'foo\\app.py','assets//handy.ico','documents/user.txt','bin/ffmpeg.exe']:
            with self.assertRaises(ValueError,msg=name):
                managed_path(name)
        self.assertEqual(version_tuple('v0.3'),(0,3,0))
        for value in ['main','v1','0.3.0-evil',None]:
            with self.assertRaises(ValueError):version_tuple(value)
        for mutate in [lambda m:m.update(repository='someone/else'),lambda m:m.update(commit='main'),
                       lambda m:m['files']['app.py'].update(size=999999999),
                       lambda m:m['files'].pop('launcher.py')]:
            bad=copy.deepcopy(self.manifest);mutate(bad)
            with self.assertRaises(ValueError):validate_manifest(bad)

    def test_downloads_only_changed_files(self):
        for name,data in self.payload.items():(self.root/name).write_bytes(data)
        (self.root/'app.py').write_bytes(b'old-app')
        plan=plan_update(self.root,self.manifest)
        self.assertEqual(plan['changed'],['app.py'])
        calls=[]
        def fetch(url,limit,cancel,progress):
            calls.append(url);return self.payload['app.py']
        stage=stage_update(self.root,self.manifest,plan,fetch=fetch)
        self.addCleanup(lambda:__import__('shutil').rmtree(stage,ignore_errors=True))
        self.assertEqual(len(calls),1);self.assertIn('/'+'a'*40+'/app.py',calls[0])
        self.assertEqual((stage/'files/app.py').read_bytes(),self.payload['app.py'])
        apply_update(self.root,stage,lambda p:None)
        self.assertEqual((self.root/'app.py').read_bytes(),self.payload['app.py'])
        self.assertEqual(plan_update(self.root,self.manifest)['changed'],[])

    def test_apply_and_keep_user_data_and_caches(self):
        (self.root/'.venv').mkdir();(self.root/'.venv/user').write_bytes(b'python-runtime')
        (self.root/'bin').mkdir();(self.root/'bin/ffmpeg.exe').write_bytes(b'ffmpeg')
        (self.root/'my video.mp4').write_bytes(b'user-video')
        stage=self.stage();dependencies=[]
        self.assertEqual(apply_update(self.root,stage,dependencies.append),'0.4.0')
        for name,data in self.payload.items():self.assertEqual((self.root/name).read_bytes(),data)
        self.assertEqual(len(dependencies),1)
        self.assertEqual((self.root/'.venv/user').read_bytes(),b'python-runtime')
        self.assertEqual((self.root/'bin/ffmpeg.exe').read_bytes(),b'ffmpeg')
        self.assertEqual((self.root/'my video.mp4').read_bytes(),b'user-video')
        self.assertTrue((self.root/INSTALLED).exists())
        self.assertFalse((self.root/'.handy-update.lock').exists())

    def test_rollback_dependency_failure(self):
        before={p.name:p.read_bytes() for p in self.root.iterdir()}
        stage=self.stage()
        def fail(path):raise RuntimeError('pip offline')
        with self.assertRaisesRegex(RuntimeError,'pip offline'):apply_update(self.root,stage,fail)
        for name,data in before.items():self.assertEqual((self.root/name).read_bytes(),data)
        self.assertFalse((self.root/INSTALLED).exists())
        self.assertFalse((self.root/'.handy-update.lock').exists())

    def test_rejects_tampered_staging_without_touching_app(self):
        stage=self.stage();(stage/'files/app.py').write_bytes(b'tampered')
        with self.assertRaises(ValueError):apply_update(self.root,stage,lambda p:None)
        self.assertEqual((self.root/'app.py').read_bytes(),b'old')

    def test_owned_file_deletion_and_rollback(self):
        old=copy.deepcopy(self.payload);old['obsolete.py']=b'old';old_manifest=make_manifest(old,'0.3.0')
        (self.root/'obsolete.py').write_bytes(b'old');(self.root/INSTALLED).write_text(json.dumps(old_manifest))
        (self.root/'personal.py').write_bytes(b'user-file')
        stage=self.stage();apply_update(self.root,stage,lambda p:None)
        self.assertFalse((self.root/'obsolete.py').exists());self.assertTrue((self.root/'personal.py').exists())

    def test_network_hash_cancel_and_symbolic_link_failures(self):
        plan=plan_update(self.root,self.manifest)
        with self.assertRaisesRegex(ValueError,'verification'):
            stage_update(self.root,self.manifest,plan,fetch=lambda *a:b'wrong')
        stop=threading.Event();stop.set()
        with self.assertRaises(UpdateCancelled):stage_update(self.root,self.manifest,plan,stop)
        outside=Path(self.temp.name)/'outside';outside.mkdir()
        try:(self.root/'assets').symlink_to(outside,target_is_directory=True)
        except OSError:return
        with self.assertRaises(ValueError):target_path(self.root,'assets/handy.ico')

    def test_release_origin_and_bounded_reads(self):
        url='https://github.com/'+REPOSITORY+'/releases/download/v0.4.0/handy-update.json'
        release=dict(tag_name='v0.4.0',assets=[dict(name='handy-update.json',browser_download_url=url)])
        values=[json.dumps(release).encode(),json.dumps(self.manifest).encode()]
        self.assertEqual(latest_release(fetch=lambda *a:values.pop(0))['version'],'0.4.0')
        release['assets'][0]['browser_download_url']='https://evil.example/handy-update.json'
        with self.assertRaises(RuntimeError):latest_release(fetch=lambda *a:json.dumps(release).encode())
        class Response(io.BytesIO):
            pass
        with self.assertRaises(ValueError):
            fetch_bytes('https://example.com',3,opener=lambda *a,**k:Response(b'too much'))


if __name__=='__main__':
    unittest.main()
