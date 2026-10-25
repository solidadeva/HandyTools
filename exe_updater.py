"""Verified whole-executable updates for the portable Windows edition."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request

from updater import API, REPOSITORY, fetch_bytes, check_cancel, digest, version_tuple

PREFIX = 'https://github.com/' + REPOSITORY + '/releases/download/'
MAX_EXE = 256 * 1024 * 1024


def validate_package(package):
    if not isinstance(package, dict) or package.get('kind') != 'windows-exe':
        raise ValueError('Invalid executable update')
    version_tuple(package.get('version'))
    name = 'HandyToolsApp-Windows-x64-v' + package['version'] + '.exe'
    if package.get('name') != name or package.get('url') != PREFIX+'v'+package['version']+'/'+name:
        raise ValueError('Untrusted executable release URL')
    if type(package.get('size')) is not int or not 2 <= package['size'] <= MAX_EXE:
        raise ValueError('Invalid executable size')
    if not re.fullmatch('[0-9a-f]{64}', package.get('sha256', '')):
        raise ValueError('Missing executable SHA-256')
    return package


def latest_exe_release(cancel=None, fetch=fetch_bytes):
    release = json.loads(fetch(API+'/releases/latest', 2*1024*1024, cancel))
    tag = release.get('tag_name', '')
    version_tuple(tag)
    version = tag.lstrip('v')
    name = 'HandyToolsApp-Windows-x64-v'+version+'.exe'
    asset = next((a for a in release.get('assets', []) if a.get('name') == name), None)
    if not asset:
        raise RuntimeError('فایل EXE این انتشار هنوز آماده نیست؛ کمی بعد دوباره بررسی کنید.')
    checksum = asset.get('digest', '') or ''
    if not checksum.startswith('sha256:'):
        companion = next((a for a in release.get('assets', []) if a.get('name') == name+'.sha256'), None)
        expected = PREFIX+'v'+version+'/'+name+'.sha256'
        if not companion or companion.get('browser_download_url') != expected:
            raise ValueError('Executable checksum is unavailable')
        parts = fetch(expected, 4096, cancel).decode('ascii').strip().split()
        if len(parts) != 2 or parts[1].lstrip('*') != name:
            raise ValueError('Invalid executable checksum file')
        checksum = 'sha256:'+parts[0]
    return validate_package(dict(kind='windows-exe', version=version, name=name,
        url=asset.get('browser_download_url'), size=asset.get('size'), sha256=checksum[7:]))


def verify_exe(path, package):
    validate_package(package)
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size != package['size'] or digest(path) != package['sha256']:
        raise ValueError('Executable update did not pass SHA-256 verification')
    with path.open('rb') as stream:
        if stream.read(2) != b'MZ':
            raise ValueError('The update is not a Windows executable')


def stage_exe_update(package, cancel=None, progress=lambda p,t: None, opener=urllib.request.urlopen):
    validate_package(package)
    stage = Path(tempfile.mkdtemp(prefix='handy-exe-update-'))
    try:
        path = stage/'package.exe'
        request = urllib.request.Request(package['url'], headers={'User-Agent':'HandyToolsApp-Updater'})
        count = 0
        with opener(request, timeout=30) as response, path.open('wb') as output:
            while True:
                check_cancel(cancel)
                block = response.read(min(256*1024, package['size']-count+1))
                if not block: break
                count += len(block)
                if count > package['size']: raise ValueError('Executable exceeds release size')
                output.write(block)
                progress(min(99, count*100/package['size']), 'دریافت نسخهٔ EXE…')
        check_cancel(cancel)
        verify_exe(path, package)
        (stage/'package.json').write_text(json.dumps(package), encoding='utf-8')
        shutil.copy2(Path(__file__).parent/'downloader/ExeUpdate.ps1', stage/'install.ps1')
        progress(100, 'نسخهٔ EXE دریافت و بررسی شد')
        return stage
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def start_exe_installer(target, stage, parent_pid, restart_smoke_report=None):
    if sys.platform != 'win32':
        raise RuntimeError('Executable replacement is only available on Windows.')
    target, stage = Path(target).absolute(), Path(stage).resolve()
    if target.is_symlink() or not target.is_file() or target.suffix.lower() != '.exe':
        raise ValueError('Invalid installed executable path')
    if type(parent_pid) is not int or parent_pid <= 0:
        raise ValueError('Invalid parent process')
    if Path(str(target)+'.handy-update.lock').exists():
        raise RuntimeError('نصب آپدیت دیگری در حال انجام است؛ کمی بعد دوباره تلاش کنید.')
    package = json.loads((stage/'package.json').read_text(encoding='utf-8'))
    verify_exe(stage/'package.exe', package)
    # Fail while the existing app is still running if its directory is read-only.
    try:
        with tempfile.TemporaryFile(dir=target.parent): pass
    except OSError as exc:
        raise RuntimeError('پوشهٔ برنامه اجازهٔ نوشتن ندارد؛ EXE را به پوشهٔ شخصی خود منتقل و دوباره اجرا کنید.') from exc
    config = dict(target=str(target), parentPid=parent_pid, package=package,
                  smokeReport=str(Path(restart_smoke_report).absolute()) if restart_smoke_report else None)
    (stage/'install.json').write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8-sig')
    powershell = Path(os.environ.get('SystemRoot', r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    return subprocess.Popen([str(powershell), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
        '-File', str(stage/'install.ps1'), '-Config', str(stage/'install.json')],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
        env=dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT='1'))
