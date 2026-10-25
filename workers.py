"""UI-independent adapters around the two existing project engines."""
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from urllib.parse import urlsplit

from PySide6.QtCore import QThread, Signal
from engine import Conversion, Cancelled, tool, hidden
from ffmpeg_setup import cache_bin, install, SetupCancelled

SETUP_LOCK = threading.Lock()


def resource_path(name):
    return Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / name


def validate_url(value):
    try:
        parsed = urlsplit(value.strip())
        return parsed.scheme.lower() in {'http', 'https'} and bool(parsed.hostname)
    except ValueError:
        return False


def parse_report(line):
    if line.startswith('DL|'):
        fields = line.split('|')
        match = re.search(r'([\d.]+)%', fields[1])
        detail = ' • '.join(x.strip() for x in fields[2:])
        return ('progress', (float(match[1]) if match else None, 'دانلود • ' + detail))
    if line.startswith('CV|'):
        try:
            return ('progress', (float(line[3:]), 'تبدیل به MP4 / H.264'))
        except ValueError:
            return ('log', line)
    if line.startswith('FILE|'):
        return ('file', line[5:])
    messages = {'CONVERT|START': 'در حال تبدیل به MP4 / H.264…',
                'CONVERT|VERIFY': 'بررسی کدک خروجی…'}
    return ('status', messages[line]) if line in messages else ('log', line)


class Task(QThread):
    progress = Signal(object, str)
    log = Signal(str)
    succeeded = Signal(str)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, kind, options, parent=None):
        super().__init__(parent)
        self.kind, self.options = kind, options
        self.stop_event = threading.Event()
        self.conversion = None
        self.process = None
        self.lock = threading.Lock()

    def cancel(self):
        self.stop_event.set()
        if self.conversion:
            self.conversion.cancel()
        # Child process trees are stopped on the worker, never on the UI thread.

    def check(self):
        if self.stop_event.is_set():
            raise Cancelled()

    def ensure_tools(self):
        while not SETUP_LOCK.acquire(timeout=.1):
            self.check()
        try:
            self.check()
            try:
                tool('ffmpeg')
                tool('ffprobe')
            except RuntimeError:
                install(lambda message, percent: self.progress.emit(percent, message), self.stop_event)
        finally:
            SETUP_LOCK.release()

    def run(self):
        try:
            self.check()
            if self.kind != 'update':
                self.ensure_tools()
            self.check()
            if self.kind == 'convert':
                self.conversion = Conversion()
                self.check()
                result = self.conversion.run(
                    self.options['source'], self.options['folder'], self.options['format'],
                    lambda p: self.progress.emit(p, 'در حال تبدیل فایل…'))
            elif self.kind == 'setup':
                result = None
            else:
                result = self.download()
            self.check()
            self.succeeded.emit(str(result or ''))
        except (Cancelled, SetupCancelled):
            self.cancelled.emit()
        except Exception as exc:
            if self.stop_event.is_set():
                self.cancelled.emit()
            else:
                self.failed.emit(str(exc))

    def download(self):
        if os.name != 'nt':
            return self.download_posix()
        powershell = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        if not powershell.is_file():
            raise RuntimeError('Windows PowerShell was not found.')
        # Reuse one shared FFmpeg cache for both tools. Copy legacy binaries once.
        common = cache_bin()
        common.mkdir(parents=True, exist_ok=True)
        if self.kind != 'update':
            with SETUP_LOCK:
                for name in ('ffmpeg', 'ffprobe'):
                    target = common / (name + '.exe')
                    if not target.exists():
                        stage = common / (name + '.copying')
                        shutil.copy2(tool(name), stage)
                        os.replace(stage, target)
        with tempfile.TemporaryDirectory(prefix='handy-job-') as temp:
            folder = Path(temp)
            log = folder / 'progress.log'
            job = dict(self.options, log=str(log), bin=str(common),
                       mode='update' if self.kind == 'update' else 'download')
            jobfile = folder / 'job.json'
            jobfile.write_text(json.dumps(job, ensure_ascii=False), encoding='utf-8-sig')
            args = [str(powershell), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                    '-File', str(resource_path('downloader/Engine.ps1')), '-JobFile', str(jobfile)]
            self.check()
            error_path = folder / 'powershell-error.txt'
            with error_path.open('wb') as errors:
                self.process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=errors, **hidden())
            position, output, tail = 0, '', []

            def drain():
                nonlocal position, output
                if not log.exists():
                    return
                # Read only complete UTF-8 lines, allowing the writer to append mid-poll.
                with log.open('rb') as stream:
                    stream.seek(position)
                    data = stream.read()
                end = data.rfind(b'\n') + 1
                position += end
                for line in data[:end].decode('utf-8', errors='replace').splitlines():
                    tail.append(line)
                    del tail[:-30]
                    kind, value = parse_report(line)
                    if kind == 'file':
                        output = value
                    elif kind == 'progress':
                        self.progress.emit(*value)
                    elif kind == 'status':
                        self.progress.emit(None, value)
                    else:
                        self.log.emit(value)

            try:
                while self.process.poll() is None:
                    if self.stop_event.wait(.15):
                        taskkill = powershell.parents[2] / 'taskkill.exe'
                        subprocess.run([str(taskkill), '/PID', str(self.process.pid), '/T', '/F'],
                                       capture_output=True, timeout=15, **hidden())
                        raise Cancelled()
                    drain()
                drain()
                self.process.wait(timeout=5)
                if self.process.returncode:
                    raise RuntimeError('\n'.join(tail[-12:]) or error_path.read_text(encoding='utf-8', errors='replace')[-4000:])
                if self.kind != 'update' and (not output or not Path(output).is_file()):
                    raise RuntimeError('فایل خروجی پیدا نشد.\n' + '\n'.join(tail[-10:]))
                return output
            finally:
                if self.process.poll() is None:
                    self.process.kill()
                self.process.wait(timeout=10)
                if self.process.stderr:
                    self.process.stderr.close()
                self.process = None

    def download_posix(self):
        if self.kind == 'update':
            raise RuntimeError('موتور دانلود مک همراه نسخهٔ جدید برنامه به‌روز می‌شود.')
        with tempfile.TemporaryDirectory(prefix='handy-download-') as temporary:
            folder=Path(temporary)
            jobfile=folder/'job.json'
            jobfile.write_text(json.dumps(self.options,ensure_ascii=False),encoding='utf-8')
            log=folder/'progress.log'
            args=[sys.executable]
            if not getattr(sys,'frozen',False): args.append(str(resource_path('launch.pyw')))
            args += ['--download-job',str(jobfile)]
            environment=dict(os.environ,PYTHONIOENCODING='utf-8',PYINSTALLER_RESET_ENVIRONMENT='1')
            position=0;output='';tail=[]
            def drain():
                nonlocal position,output
                with log.open('rb') as stream:
                    stream.seek(position);data=stream.read()
                end=data.rfind(b'\n')+1;position+=end
                for line in data[:end].decode('utf-8',errors='replace').splitlines():
                    tail.append(line);del tail[:-30]
                    kind,value=parse_report(line)
                    if kind=='file':output=value
                    elif kind=='progress':self.progress.emit(*value)
                    elif kind=='status':self.progress.emit(None,value)
                    else:self.log.emit(value)
            self.check()
            with log.open('wb') as stream:
                self.process=subprocess.Popen(args,stdout=stream,stderr=stream,env=environment,start_new_session=True)
            try:
                while self.process.poll() is None:
                    if self.stop_event.wait(.15):
                        try: os.killpg(self.process.pid,signal.SIGTERM)
                        except ProcessLookupError: pass
                        try:self.process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            try:os.killpg(self.process.pid,signal.SIGKILL)
                            except ProcessLookupError:pass
                        raise Cancelled()
                    drain()
                drain()
                if self.process.returncode:
                    raise RuntimeError('\n'.join(tail[-15:]))
                if not output or not Path(output).is_file():
                    raise RuntimeError('فایل خروجی پیدا نشد.\n'+'\n'.join(tail[-10:]))
                return output
            finally:
                if self.process.poll() is None:
                    try:os.killpg(self.process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                self.process.wait(timeout=10);self.process=None
