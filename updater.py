"""Per-file source updates from the project's public GitHub releases.

No archive is extracted into the installation. Every managed path is validated,
bytes are checked before application, and user files/caches are outside scope.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from urllib.parse import quote

REPOSITORY = 'solidadeva/HandyTools'
API = 'https://api.github.com/repos/' + REPOSITORY
MANIFEST_NAME = 'handy-update.json'
INSTALLED = '.handy-installed.json'
MAX_FILE = 32 * 1024 * 1024
MAX_TOTAL = 128 * 1024 * 1024
ROOT_NAMES = {'requirements.txt', 'requirements-build.txt', 'Start.vbs', 'Install.bat',
              'Update.bat', 'Build-Windows.bat', 'README.md', 'README-fa.md',
              'THIRD-PARTY.md', 'VALIDATION.txt'}


class UpdateCancelled(Exception):
    pass


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r'v?\d+\.\d+(?:\.\d+)?', value):
        raise ValueError('Invalid release version')
    parts = tuple(int(x) for x in value.lstrip('v').split('.'))
    return parts + (0,) * (3-len(parts))


def managed_path(name):
    if not isinstance(name, str) or not name or '\\' in name or ':' in name:
        raise ValueError('Invalid update path')
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or any(x.startswith('.') for x in p.parts) or p.as_posix() != name:
        raise ValueError('Unsafe update path: ' + name)
    if len(p.parts) == 1 and (p.suffix in {'.py', '.pyw'} or name in ROOT_NAMES):
        return name
    if len(p.parts) == 2 and p.parts[0] == 'downloader' and p.suffix == '.ps1':
        return name
    if name in {'assets/handy.ico', 'assets/handy.png'}:
        return name
    if len(p.parts) == 3 and p.parts[:2] == ('assets', 'icons') and p.suffix in {'.svg', '.png'}:
        return name
    raise ValueError('Path is outside the managed app files: ' + name)


def target_path(root, name):
    managed_path(name)
    root = Path(root).resolve()
    current = root
    for part in PurePosixPath(name).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('Updates cannot follow symbolic links: ' + name)
    if not current.resolve().is_relative_to(root):
        raise ValueError('Update escapes installation')
    return current


def validate_manifest(data):
    if not isinstance(data, dict) or data.get('schema') != 1 or data.get('repository') != REPOSITORY:
        raise ValueError('Invalid update manifest')
    version_tuple(data.get('version'))
    if not re.fullmatch(r'[0-9a-f]{40}', data.get('commit', '')):
        raise ValueError('Invalid release commit')
    files = data.get('files')
    if not isinstance(files, dict) or not files or len(files)>500:
        raise ValueError('Invalid update file list')
    size = 0
    casefolded = set()
    for name, info in files.items():
        managed_path(name)
        if name.casefold() in casefolded:
            raise ValueError('Duplicate Windows update path')
        casefolded.add(name.casefold())
        if not isinstance(info, dict) or not re.fullmatch(r'[0-9a-f]{64}',info.get('sha256', '')):
            raise ValueError('Invalid file checksum')
        count = info.get('size')
        if type(count) is not int or not 0 <= count <= MAX_FILE:
            raise ValueError('Invalid update size')
        size += count
    if size>MAX_TOTAL:
        raise ValueError('Update is too large')
    for required in ('version.py','app.py','launcher.py','launch.pyw','updater.py','update_apply.py','update_ui.py','requirements.txt'):
        if required not in files:
            raise ValueError('Release is missing '+required)
    return data


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(256*1024),b''):
            h.update(block)
    return h.hexdigest()


def check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise UpdateCancelled()


def fetch_bytes(url, limit, cancel=None, progress=lambda n:None, opener=urllib.request.urlopen):
    request = urllib.request.Request(url, headers={'User-Agent':'HandyToolsApp-Updater',
                                                  'Accept':'application/vnd.github+json' if url.startswith(API) else '*/*'})
    chunks=[];count=0
    with opener(request, timeout=30) as response:
        while True:
            check_cancel(cancel)
            block=response.read(min(256*1024,limit-count+1))
            if not block:
                break
            count+=len(block)
            if count>limit:
                raise ValueError('Server response exceeds its expected size')
            chunks.append(block);progress(count)
    return b''.join(chunks)


def latest_release(cancel=None, fetch=fetch_bytes):
    try:
        release=json.loads(fetch(API+'/releases/latest',2*1024*1024,cancel))
    except urllib.error.HTTPError as exc:
        if exc.code==404:
            raise RuntimeError('هنوز نسخهٔ آپدیت روی گیت‌هاب منتشر نشده است.') from exc
        raise
    asset=next((a for a in release.get('assets',[]) if a.get('name')==MANIFEST_NAME),None)
    prefix='https://github.com/'+REPOSITORY+'/releases/download/'
    if not asset or not asset.get('browser_download_url','').startswith(prefix):
        raise RuntimeError('فایل آپدیت این انتشار در دسترس نیست.')
    manifest=validate_manifest(json.loads(fetch(asset['browser_download_url'],2*1024*1024,cancel)))
    if version_tuple(release['tag_name'])!=version_tuple(manifest['version']):
        raise ValueError('Release version does not match the update manifest')
    return manifest


def plan_update(root, manifest):
    validate_manifest(manifest)
    changed=[]
    for name,info in manifest['files'].items():
        path=target_path(root,name)
        if not path.is_file() or path.stat().st_size!=info['size'] or digest(path)!=info['sha256']:
            changed.append(name)
    deleted=[]
    marker=Path(root)/INSTALLED
    if marker.is_file():
        previous=validate_manifest(json.loads(marker.read_text(encoding='utf-8')))
        deleted=[name for name in previous['files'] if name not in manifest['files']]
        for name in deleted:
            target_path(root,name)
    return dict(changed=changed,deleted=deleted,
                bytes=sum(manifest['files'][n]['size'] for n in changed))


def stage_update(root,manifest,plan,cancel=None,progress=lambda percent,text:None,fetch=fetch_bytes):
    validate_manifest(manifest)
    # Recompute the authoritative plan; never accept paths supplied by a caller.
    plan=plan_update(root,manifest)
    stage=Path(tempfile.mkdtemp(prefix='handy-update-'))
    done=0;total=plan['bytes']
    try:
        for name in plan['changed']:
            check_cancel(cancel)
            info=manifest['files'][name]
            url='https://raw.githubusercontent.com/'+REPOSITORY+'/'+manifest['commit']+'/'+quote(name,safe='/')
            def on_progress(n):
                progress(min(99,(done+n)*100/max(1,total)),'دریافت '+name)
            data=fetch(url,info['size'],cancel,on_progress)
            if len(data)!=info['size'] or hashlib.sha256(data).hexdigest()!=info['sha256']:
                raise ValueError('Downloaded file did not pass verification: '+name)
            path=target_path(stage/'files',name);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
            done+=len(data)
        check_cancel(cancel)
        (stage/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
        (stage/'plan.json').write_text(json.dumps(plan),encoding='utf-8')
        # Run a private copy of the current installer, so it can replace itself safely.
        runner=stage/'runner';runner.mkdir()
        for name in ('updater.py','update_apply.py'):
            shutil.copy2(Path(__file__).parent/name,runner/name)
        progress(100,'آپدیت دریافت و بررسی شد')
        return stage
    except BaseException:
        shutil.rmtree(stage,ignore_errors=True)
        raise


def start_installer(root,stage,pid):
    if getattr(sys,'frozen',False):
        raise RuntimeError('این آپدیتر مخصوص نسخهٔ Python است؛ برای EXE بستهٔ مستقل لازم است.')
    args=[sys.executable,str(Path(stage)/'runner/update_apply.py'),'--root',str(Path(root).resolve()),
          '--stage',str(Path(stage).resolve()),'--pid',str(pid)]
    hidden={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {'start_new_session':True}
    return subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**hidden)
