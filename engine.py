"""FFmpeg conversion engine. No shell, no UI dependencies."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
from ffmpeg_setup import cache_bin

FORMATS = ('MP4', 'MKV', 'MOV', 'WEBM', 'MP3', 'WAV', 'FLAC', 'PNG', 'JPG', 'WEBP')
IMAGES = {'PNG', 'JPG', 'WEBP'}
AUDIO = {'MP3', 'WAV', 'FLAC'}


def tool(name):
    root = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
    suffix = '.exe' if os.name == 'nt' else ''
    legacy = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
    for folder in (root / 'bin', root, cache_bin(), legacy / 'MinimalConvert' / 'ffmpeg' / 'bin',
                   legacy / 'SimpleDownloader' / 'bin'):
        candidate = folder / (name + suffix)
        if candidate.is_file():
            return str(candidate)
    found = shutil.which(name)
    if not found:
        raise RuntimeError(f'{name} was not found. Put ffmpeg.exe and ffprobe.exe in the bin folder.')
    return found


def hidden():
    return {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}


def inspect(source):
    result = subprocess.run([tool('ffprobe'), '-v', 'error', '-show_format', '-show_streams',
                             '-of', 'json', str(source)], capture_output=True,
                            encoding='utf-8', errors='replace', timeout=30, **hidden())
    if result.returncode:
        raise RuntimeError('Cannot read this file. It may be damaged or unsupported.\n' + result.stderr[-2000:])
    return json.loads(result.stdout)


def command(source, target, fmt, ffmpeg=None):
    fmt = fmt.upper()
    if fmt not in FORMATS:
        raise ValueError('Unsupported output format')
    args = [ffmpeg or tool('ffmpeg'), '-hide_banner', '-nostdin', '-y', '-loglevel', 'error',
            '-i', str(source), '-progress', 'pipe:1', '-nostats']
    if fmt in AUDIO:
        args += ['-map', '0:a:0', '-vn', '-sn', '-dn']
        args += {'MP3': ['-c:a', 'libmp3lame', '-b:a', '192k'],
                 'WAV': ['-c:a', 'pcm_s16le'], 'FLAC': ['-c:a', 'flac']}[fmt]
    else:
        args += ['-map', '0:v:0', '-sn', '-dn']
        if fmt in IMAGES:
            args += ['-frames:v', '1', '-an']
            args += {'PNG': ['-c:v', 'png'], 'JPG': ['-c:v', 'mjpeg', '-q:v', '2'],
                     'WEBP': ['-c:v', 'libwebp', '-quality', '90']}[fmt]
        else:
            args += ['-map', '0:a:0?']
            # Make odd pixel dimensions legal for YUV420 codecs, without upscaling.
            args += ['-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2', '-pix_fmt', 'yuv420p']
            if fmt == 'WEBM':
                args += ['-c:v', 'libvpx-vp9', '-crf', '32', '-b:v', '0', '-row-mt', '1',
                         '-c:a', 'libopus', '-b:a', '128k']
            else:
                args += ['-c:v', 'libx264', '-preset', 'fast', '-crf', '20',
                         '-c:a', 'aac', '-b:a', '192k']
                if fmt in {'MP4', 'MOV'}:
                    args += ['-movflags', '+faststart']
    return args + [str(target)]


class Cancelled(Exception):
    pass


class Conversion:
    def __init__(self):
        self.cancelled = threading.Event()
        self.lock = threading.Lock()
        self.process = None

    def cancel(self):
        with self.lock:
            self.cancelled.set()
            if self.process and self.process.poll() is None:
                self.process.terminate()

    def run(self, source, folder, fmt, progress=lambda value: None):
        source = Path(source).resolve()
        if source.suffix.lower() in {'.heic', '.heif', '.hif'}:
            if self.cancelled.is_set():
                raise Cancelled()
            try:
                from pillow_heif import open_heif
            except ImportError as exc:
                raise RuntimeError('HEIC support is missing. Run Install.bat once, then restart the app.') from exc
            # HEIC can contain a grid of HEVC tiles, thumbnails and auxiliary
            # images. Decode the primary image through libheif, never 0:v:0.
            with tempfile.TemporaryDirectory(prefix='minimalconvert-heic-') as temp:
                decoded = Path(temp) / 'primary.png'
                try:
                    heif = open_heif(source, convert_hdr_to_8bit=True)
                    image = heif.to_pillow()
                    image.load()
                    if self.cancelled.is_set():
                        raise Cancelled()
                    # libheif already applies container rotation/crop transforms.
                    # Pass pixels only so FFmpeg cannot rotate them a second time.
                    image.info.clear()
                    image.save(decoded, format='PNG')
                    image.close()
                except Cancelled:
                    raise
                except Exception as exc:
                    raise RuntimeError('Cannot decode the complete HEIC image.\n' + str(exc)) from exc
                return self._run(decoded, folder, fmt, progress, output_stem=source.stem)
        return self._run(source, folder, fmt, progress)

    def _run(self, source, folder, fmt, progress, output_stem=None):
        source, folder = Path(source).resolve(), Path(folder).resolve()
        fmt = fmt.upper()
        if fmt not in FORMATS:
            raise ValueError('Unsupported output format')
        data = inspect(source)
        required = 'audio' if fmt in AUDIO else 'video'
        streams = [s for s in data.get('streams', []) if s.get('codec_type') == required]
        if not streams:
            raise RuntimeError(f'This file has no {required} stream for {fmt} output.')
        try:
            duration = float(data.get('format', {}).get('duration', streams[0].get('duration', 0)))
        except (ValueError, TypeError):
            duration = 0
        if self.cancelled.is_set():
            raise Cancelled()
        output = None
        temporary = None
        committed = False
        try:
            # Reserve our own new filename exclusively; existing files are never overwritten.
            for number in range(10000):
                tag = '' if number == 0 else f' ({number})'
                candidate = folder / f'{output_stem or source.stem}_converted{tag}.{fmt.lower()}'
                try:
                    fd = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                    os.close(fd)
                    output = candidate
                    break
                except FileExistsError:
                    continue
            if output is None:
                raise RuntimeError('Too many outputs with this name.')
            fd, path = tempfile.mkstemp(prefix='.minimalconvert-', suffix='.' + fmt.lower(), dir=folder)
            os.close(fd)
            temporary = Path(path)
            args = command(source, temporary, fmt)
            with tempfile.TemporaryFile() as errors:
                with self.lock:
                    if self.cancelled.is_set():
                        raise Cancelled()
                    self.process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=errors,
                                                    encoding='utf-8', errors='replace', **hidden())
                try:
                    for line in self.process.stdout:
                        if line.startswith('out_time_us=') and duration > 0 and fmt not in IMAGES:
                            try:
                                progress(min(99, max(0, float(line.strip().split('=', 1)[1]) / 10000 / duration)))
                            except ValueError:
                                pass
                    code = self.process.wait()
                    if self.cancelled.is_set():
                        raise Cancelled()
                    if code or not temporary.stat().st_size:
                        errors.seek(0, 2)
                        size = errors.tell()
                        errors.seek(max(0, size - 4000))
                        detail = errors.read().decode('utf-8', errors='replace')
                        raise RuntimeError('Conversion failed.\n' + detail)
                    with self.lock:
                        if self.cancelled.is_set():
                            raise Cancelled()
                        os.replace(temporary, output)
                        committed = True
                    progress(100)
                    return output
                finally:
                    if self.process.poll() is None:
                        self.process.kill()
                    self.process.wait()
                    self.process.stdout.close()
                    with self.lock:
                        self.process = None
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
            if output and not committed:
                output.unlink(missing_ok=True)
