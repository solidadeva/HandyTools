"""Native yt-dlp worker for macOS/Linux, isolated from the GUI process."""
import json
import os
from pathlib import Path
import sys

from engine import Conversion, inspect, tool


def report(text):
    print(text, flush=True)


class Logger:
    def debug(self, message): report(message)
    def info(self, message): report(message)
    def warning(self, message): report('WARNING: '+message)
    def error(self, message): report('ERROR: '+message)


def run_job(filename):
    import yt_dlp
    job = json.loads(Path(filename).read_text(encoding='utf-8'))
    folder = Path(job['folder']).resolve()
    audio = job.get('quality') == 'audio'
    source_folder = folder if audio else folder/'.HandyTools-source'
    source_folder.mkdir(parents=True, exist_ok=True)
    final = []
    def progress(data):
        if data.get('status') == 'downloading':
            total = data.get('total_bytes') or data.get('total_bytes_estimate') or 0
            value = data.get('downloaded_bytes', 0)*100/total if total else 0
            report(f'DL|{value:.1f}%|{data.get("_speed_str", "")}|{data.get("_eta_str", "")}')
    def complete(data):
        if data.get('status') == 'finished' and data.get('postprocessor') == 'MoveFiles':
            final.append(data['info_dict']['filepath'])
    cap = job.get('quality', '')
    cap = '[height<='+cap+']' if cap in ('480','720','1080') else ''
    options = dict(noplaylist=True, windowsfilenames=True, continuedl=True, overwrites=False,
        socket_timeout=30, retries=3, outtmpl=str(source_folder/'%(title).160B [%(id)s].%(ext)s'),
        format='ba/b' if audio else 'bv'+cap+'+ba/b'+cap, merge_output_format='mkv',
        ffmpeg_location=str(Path(tool('ffmpeg')).parent), logger=Logger(),
        progress_hooks=[progress], postprocessor_hooks=[complete])
    try:
        deno = tool('deno')
        options['js_runtimes'] = {'deno': {'path': deno}}
    except RuntimeError:
        pass
    if audio:
        options['postprocessors'] = [dict(key='FFmpegExtractAudio', preferredcodec='mp3', preferredquality='0')]
    with yt_dlp.YoutubeDL(options) as downloader:
        info = downloader.extract_info(job['url'], download=True)
        source = Path(final[-1] if final else info.get('filepath') or downloader.prepare_filename(info))
    if not source.is_file():
        raise RuntimeError('The completed download was not found.')
    if audio:
        streams = inspect(source)['streams']
        if not any(s.get('codec_name') == 'mp3' for s in streams):
            raise RuntimeError('MP3 output verification failed.')
        output = source
    else:
        report('CONVERT|START')
        output = Conversion().run(source, folder, 'MP4', lambda value:report(f'CV|{value:.1f}'))
        report('CONVERT|VERIFY')
        streams = inspect(output)['streams']
        video = next((s for s in streams if s.get('codec_type') == 'video'), {})
        audio_streams = [s for s in streams if s.get('codec_type') == 'audio']
        if video.get('codec_name') != 'h264' or video.get('pix_fmt') != 'yuv420p' or any(s.get('codec_name') != 'aac' for s in audio_streams):
            output.unlink(missing_ok=True)
            raise RuntimeError('Final H.264/AAC verification failed. Original download retained.')
    report('FILE|'+str(output))
    return 0
