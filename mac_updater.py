"""Check/download verified macOS installers; Finder performs the app replacement."""
import hashlib
import json
from pathlib import Path
import platform
import shutil
import tempfile
import urllib.request

from updater import API, fetch_bytes, check_cancel, version_tuple
from exe_updater import PREFIX


def latest_mac_release(cancel=None, fetch=fetch_bytes, machine=None):
    arch={'arm64':'arm64','aarch64':'arm64','x86_64':'x86_64','amd64':'x86_64'}.get((machine or platform.machine()).lower())
    if not arch: raise RuntimeError('Unsupported Mac architecture')
    release=json.loads(fetch(API+'/releases/latest',2*1024*1024,cancel))
    version_tuple(release.get('tag_name'))
    version=release['tag_name'].lstrip('v')
    name=f'HandyToolsApp-macOS-{arch}-v{version}.dmg'
    asset=next((a for a in release.get('assets',[]) if a.get('name')==name),None)
    if not asset: raise RuntimeError('بستهٔ مک این انتشار هنوز آماده نیست؛ کمی بعد دوباره بررسی کنید.')
    sha=asset.get('digest','') or ''
    if not sha.startswith('sha256:'):
        checksum_url=PREFIX+'v'+version+'/'+name+'.sha256'
        companion=next((a for a in release['assets'] if a.get('name')==name+'.sha256' and a.get('browser_download_url')==checksum_url),None)
        if not companion:raise ValueError('Mac installer checksum is unavailable')
        parts=fetch(checksum_url,4096,cancel).decode('ascii').strip().split()
        if len(parts)!=2 or parts[1]!=name:raise ValueError('Invalid Mac checksum file')
        sha='sha256:'+parts[0]
    package=dict(kind='mac-dmg',version=version,name=name,url=asset.get('browser_download_url'),size=asset.get('size'),sha256=sha[7:])
    validate_package(package)
    return package


def validate_package(package):
    import re
    version_tuple(package.get('version'))
    name=package.get('name','')
    if not re.fullmatch(r'HandyToolsApp-macOS-(arm64|x86_64)-v'+re.escape(package['version'])+r'\.dmg',name):raise ValueError('Invalid Mac package name')
    if package.get('url')!=PREFIX+'v'+package['version']+'/'+name:raise ValueError('Untrusted Mac package URL')
    if type(package.get('size')) is not int or not 0<package['size']<=1024*1024*1024:raise ValueError('Invalid Mac package size')
    if not re.fullmatch('[0-9a-f]{64}',package.get('sha256','')):raise ValueError('Invalid Mac package checksum')


def stage_mac_update(package,cancel=None,progress=lambda p,t:None,opener=urllib.request.urlopen):
    validate_package(package)
    stage=Path(tempfile.mkdtemp(prefix='handy-mac-update-'))
    try:
        output=stage/package['name'];count=0;sha=hashlib.sha256()
        request=urllib.request.Request(package['url'],headers={'User-Agent':'HandyToolsApp-Updater'})
        with opener(request,timeout=30) as response,output.open('wb') as stream:
            while True:
                check_cancel(cancel)
                block=response.read(min(256*1024,package['size']-count+1))
                if not block:break
                count+=len(block)
                if count>package['size']:raise ValueError('Mac package exceeds expected size')
                sha.update(block);stream.write(block)
                progress(min(99,count*100/package['size']),'دریافت نسخهٔ مک…')
        check_cancel(cancel)
        if count!=package['size'] or sha.hexdigest()!=package['sha256']:raise ValueError('Mac package did not pass SHA-256 verification')
        (stage/'package.json').write_text(json.dumps(package),encoding='utf-8')
        progress(100,'بستهٔ مک دریافت و بررسی شد')
        return stage
    except BaseException:
        shutil.rmtree(stage,ignore_errors=True);raise


def staged_installer(stage):
    from updater import digest
    stage=Path(stage);package=json.loads((stage/'package.json').read_text(encoding='utf-8'))
    validate_package(package);path=stage/package['name']
    if path.is_symlink() or path.stat().st_size!=package['size'] or digest(path)!=package['sha256']:raise ValueError('Mac package verification failed')
    return path
