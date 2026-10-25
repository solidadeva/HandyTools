"""Build and validate the self-contained Windows x64 executable."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

from version import VERSION

ROOT = Path(__file__).resolve().parent


def main():
    if sys.platform != 'win32' or struct.calcsize('P') != 8:
        raise RuntimeError('Build on Windows with 64-bit Python.')
    output = ROOT / 'dist' / 'portable'
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
        '--onefile', '--windowed', '--noupx', '--collect-all', 'pillow_heif',
        '--add-data', 'downloader;downloader',
        '--add-data', 'assets/icons/genyconnect.png;assets/icons',
        '--icon', 'assets/handy.ico', '--name', 'HandyToolsApp',
        '--distpath', str(output), 'launch.pyw'], cwd=ROOT, check=True)
    executable = output / 'HandyToolsApp.exe'
    # Reproduce the reported scenario: ONLY the EXE, moved away from build files.
    with tempfile.TemporaryDirectory(prefix='Handy build ') as temp:
        isolated = Path(temp) / 'Standalone folder with spaces'
        isolated.mkdir()
        copied = isolated / executable.name
        shutil.copy2(executable, copied)
        report = isolated / 'startup.json'
        try:
            subprocess.run([str(copied), '--smoke-test', str(report)], cwd=isolated,
                           check=True, timeout=120)
        except (subprocess.SubprocessError, OSError):
            error_report = report.with_suffix('.error.txt')
            if error_report.exists():
                print(error_report.read_text(encoding='utf-8'), flush=True)
            raise
        data = json.loads(report.read_text(encoding='utf-8'))
        if data != {'version': VERSION, 'frozen': True, 'ok': True}:
            raise RuntimeError('The standalone startup test did not complete correctly.')
    release = ROOT / 'release'
    release.mkdir(exist_ok=True)
    target = release / f'HandyToolsApp-Windows-x64-v{VERSION}.exe'
    shutil.copy2(executable, target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.exe.sha256').write_text(f'{digest}  {target.name}\n', encoding='ascii')
    print(f'Ready: {executable}')
    print('Standalone startup passed. You can move this EXE by itself; no _internal folder is needed.')


if __name__ == '__main__':
    main()
