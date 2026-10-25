"""Build native macOS app/DMG with all media tools and verify after relocation."""
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess
import sys
import tempfile

from version import VERSION
ROOT=Path(__file__).resolve().parent


def run(args,**kwargs):return subprocess.run(args,check=True,**kwargs)


def main():
    if sys.platform!='darwin':raise RuntimeError('Build this package on macOS.')
    arch=platform.machine().lower()
    if arch not in ('arm64','x86_64'):raise RuntimeError('Unsupported Mac architecture')
    icon=ROOT/'build/handy.icns';icon.parent.mkdir(exist_ok=True)
    from PIL import Image
    Image.open(ROOT/'assets/handy.png').save(icon,format='ICNS')
    args=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed',
        '--name','HandyToolsApp','--icon',str(icon),'--target-architecture',arch,
        '--osx-bundle-identifier','ir.prismacreatives.handytools','--collect-all','pillow_heif',
        '--collect-all','yt_dlp','--collect-all','yt_dlp_ejs',
        '--add-data','downloader:downloader','--add-data','assets/icons/genyconnect.png:assets/icons',
        '--distpath','dist/macos']
    for name in ('ffmpeg','ffprobe','deno'):
        binary=shutil.which(name)
        if not binary:raise RuntimeError('Install build tool via Homebrew: '+name)
        args += ['--add-binary',str(Path(binary).resolve())+':bin']
    args.append('launch.pyw');run(args,cwd=ROOT)
    app=ROOT/'dist/macos/HandyToolsApp.app'
    info=app/'Contents/Info.plist'
    data=plistlib.loads(info.read_bytes());data.update(CFBundleShortVersionString=VERSION,CFBundleVersion=VERSION,LSMinimumSystemVersion='15.0',CFBundleDisplayName='Handy Tools App')
    info.write_bytes(plistlib.dumps(data))
    run(['codesign','--force','--deep','--sign','-',str(app)])
    run(['codesign','--verify','--deep','--strict',str(app)])
    with tempfile.TemporaryDirectory(prefix='Handy Mac ') as temporary:
        moved=Path(temporary)/'HandyToolsApp.app'
        run(['ditto',str(app),str(moved)])
        report=Path(temporary)/'startup.json'
        env=dict(os.environ,PATH='/usr/bin:/bin:/usr/sbin:/sbin')
        run([str(moved/'Contents/MacOS/HandyToolsApp'),'--smoke-test',str(report)],env=env,timeout=180)
        assert json.loads(report.read_text())==dict(version=VERSION,frozen=True,ok=True)
        # Exercise native downloader inside the packaged app against a local HTTP server.
        sys.path.insert(0,str(ROOT/'tests'))
        from macos_download_check import check_download
        check_download(moved,Path(temporary),env)
    release=ROOT/'release';release.mkdir(exist_ok=True)
    dmg=release/f'HandyToolsApp-macOS-{arch}-v{VERSION}.dmg'
    with tempfile.TemporaryDirectory(prefix='handy-dmg-') as temporary:
        contents=Path(temporary)/'contents';contents.mkdir()
        run(['ditto',str(app),str(contents/'HandyToolsApp.app')])
        (contents/'Applications').symlink_to('/Applications')
        shutil.copy2(ROOT/'THIRD-PARTY.md',contents/'THIRD-PARTY.md')
        (contents/'README.txt').write_text('Handy Tools App '+VERSION+'\nmacOS 15 or later / '+arch+'\nDrag HandyToolsApp into Applications.\nAd-hoc signed; not Apple notarized. See the release notes for first-open guidance.\n',encoding='utf-8')
        run(['hdiutil','create','-volname','Handy Tools App','-srcfolder',str(contents),'-ov','-format','UDZO',str(dmg)])
    run(['hdiutil','verify',str(dmg)])
    dmg.with_suffix('.dmg.sha256').write_text(hashlib.sha256(dmg.read_bytes()).hexdigest()+'  '+dmg.name+'\n',encoding='ascii')
    print('PASS native Mac app, bundled FFmpeg/Deno, actual conversion/download, relocated startup and DMG verification:',arch)


if __name__=='__main__':main()
