"""Exercise the bundled downloader without relying on YouTube availability."""
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import threading


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self,*args):pass


def check_download(app,temporary,environment):
    from engine import tool
    from workers import parse_report
    fixture=temporary/'sample.mp4'
    subprocess.run([tool('ffmpeg'),'-v','error','-f','lavfi','-i','testsrc2=size=160x120:rate=10:duration=1',
                    '-f','lavfi','-i','sine=duration=1','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(fixture)],check=True)
    server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(QuietHandler,directory=str(temporary)))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        for quality in ('best','audio'):
            folder=temporary/quality;folder.mkdir()
            job=temporary/(quality+'.json')
            job.write_text(json.dumps(dict(url=f'http://127.0.0.1:{server.server_port}/sample.mp4',quality=quality,folder=str(folder))),encoding='utf-8')
            result=subprocess.run([str(app/'Contents/MacOS/HandyToolsApp'),'--download-job',str(job)],env=environment,capture_output=True,text=True,timeout=120)
            if result.returncode:raise RuntimeError(result.stdout+'\n'+result.stderr)
            outputs=[parse_report(line)[1] for line in result.stdout.splitlines() if line.startswith('FILE|')]
            assert outputs and Path(outputs[-1]).is_file(),result.stdout
            print('PASS bundled native download:',quality)
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
