"""First-run FFmpeg download; no admin rights or shell required."""
import hashlib
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile
import threading
import urllib.request
import zipfile

URL = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'
MAX_DOWNLOAD = 512 * 1024 * 1024


class SetupCancelled(Exception):
    pass


def cache_bin():
    base = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
    return base / 'HandyToolsApp' / 'bin'


def check_cancel(cancel):
    if cancel.is_set():
        raise SetupCancelled()


def install(progress=lambda message, percent: None, cancel=None, destination=None,
            opener=urllib.request.urlopen, validator=None):
    cancel = cancel or threading.Event()
    if platform.system() != 'Windows' or platform.machine().lower() not in {'amd64', 'x86_64'}:
        raise RuntimeError('Automatic FFmpeg setup requires 64-bit Windows on an Intel/AMD computer.')
    destination = Path(destination) if destination else cache_bin()
    destination.parent.mkdir(parents=True, exist_ok=True)
    check_cancel(cancel)
    progress('Checking download…', None)
    def request(url):
        return opener(urllib.request.Request(url, headers={'User-Agent': 'HandyToolsApp/0.1'}), timeout=30)
    with request(URL + '.sha256') as response:
        text = response.read(4096).decode('ascii').strip()
    match = re.match(r'^([0-9a-fA-F]{64})(?:\s|$)', text)
    if not match:
        raise RuntimeError('The download server returned an invalid checksum. Please retry.')
    expected = match.group(1).lower()
    with tempfile.TemporaryDirectory(prefix='.setup-', dir=destination.parent) as temporary:
        staging = Path(temporary)
        archive = staging / 'ffmpeg.zip'
        digest = hashlib.sha256()
        with request(URL) as response, archive.open('wb') as output:
            total = int(response.headers.get('Content-Length', 0))
            if total > MAX_DOWNLOAD:
                raise RuntimeError('FFmpeg download is unexpectedly large.')
            received = 0
            while True:
                check_cancel(cancel)
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                received += len(chunk)
                if received > MAX_DOWNLOAD:
                    raise RuntimeError('FFmpeg download is unexpectedly large.')
                output.write(chunk)
                digest.update(chunk)
                progress(f'Downloading FFmpeg — {received / 1048576:.1f} MB',
                         min(90, received * 90 / total) if total else None)
            if total and received != total:
                raise RuntimeError('The FFmpeg download was interrupted. Please retry.')
        check_cancel(cancel)
        if digest.hexdigest() != expected:
            raise RuntimeError('FFmpeg download verification failed. Please retry.')
        progress('Verifying and installing…', 93)
        # Only copy expected filenames, never extract arbitrary ZIP paths.
        with zipfile.ZipFile(archive) as bundle:
            for name in ('ffmpeg.exe', 'ffprobe.exe'):
                matches = [i for i in bundle.infolist()
                           if i.filename.replace('\\', '/').endswith('/bin/' + name)]
                if len(matches) != 1 or not 0 < matches[0].file_size <= MAX_DOWNLOAD:
                    raise RuntimeError('The FFmpeg archive is missing required files.')
                check_cancel(cancel)
                with bundle.open(matches[0]) as src, (staging / name).open('wb') as dst:
                    shutil.copyfileobj(src, dst)
                if validator:
                    validator(staging / name)
                else:
                    result = subprocess.run([str(staging / name), '-version'], capture_output=True,
                                            timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
                    if result.returncode:
                        raise RuntimeError(f'{name} could not run on this computer.')
            # Keep the distribution's license alongside the downloaded binaries.
            for item in bundle.infolist():
                if item.filename.rsplit('/', 1)[-1].upper() == 'LICENSE':
                    (staging / 'LICENSE').write_bytes(bundle.read(item))
                    break
        check_cancel(cancel)
        destination.mkdir(parents=True, exist_ok=True)
        for name in ('ffmpeg.exe', 'ffprobe.exe', 'LICENSE'):
            if (staging / name).exists():
                os.replace(staging / name, destination / name)
        progress('FFmpeg is ready.', 100)
    return destination
