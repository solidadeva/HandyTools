import sys, tempfile, subprocess, threading, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import Conversion, Cancelled, FORMATS, inspect
with tempfile.TemporaryDirectory(prefix='convert-test-') as temp:
    folder=Path(temp)/'تست فارسی with spaces'; folder.mkdir()
    source=folder/'ویدیو test.mkv'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=161x121:rate=12:duration=1','-f','lavfi','-i','sine=frequency=440:duration=1','-c:v','ffv1','-c:a','pcm_s16le',str(source)],check=True)
    original=source.read_bytes()
    for fmt in FORMATS:
        progress=[]
        output=Conversion().run(source,folder,fmt,progress.append)
        assert output.stat().st_size > 0 and progress[-1] == 100
        assert inspect(output)['streams']
        print('PASS',fmt)
    assert source.read_bytes()==original
    first=folder/'ویدیو test_converted.mp4'; before=first.read_bytes()
    next_file=Conversion().run(source,folder,'MP4')
    assert next_file!=first and first.read_bytes()==before
    print('PASS no overwrite and source preserved')
    image=folder/'ویدیو test_converted.png'
    assert Conversion().run(image,folder,'JPG').stat().st_size>0
    print('PASS image to image')
    listing=set(folder.iterdir())
    try: Conversion().run(image,folder,'MP3')
    except RuntimeError as e: assert 'no audio' in str(e)
    else: raise AssertionError('expected error')
    assert set(folder.iterdir())==listing
    bad=folder/'bad.mp4'; bad.write_bytes(b'not a video')
    listing=set(folder.iterdir())
    try: Conversion().run(bad,folder,'MP4')
    except RuntimeError: pass
    else: raise AssertionError('expected error')
    assert set(folder.iterdir())==listing
    print('PASS invalid input and missing stream')
    # Force an encoder failure after the destination is reserved.
    import engine
    real_command=engine.command
    engine.command=lambda src,dst,fmt: ['ffmpeg','-v','error','-i',str(src),'-c:v','no_such_encoder',str(dst)]
    try:
        try: Conversion().run(source,folder,'MP4')
        except RuntimeError: pass
        else: raise AssertionError('expected encoder error')
        assert set(folder.iterdir())==listing
    finally: engine.command=real_command
    print('PASS encoder failure cleanup')
    long=folder/'long.mkv'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=960x540:rate=30:duration=12','-c:v','libx264','-preset','ultrafast',str(long)],check=True)
    listing=set(folder.iterdir()); job=Conversion(); outcomes=[]
    def work():
        try: job.run(long,folder,'WEBM')
        except Cancelled: outcomes.append('cancelled')
    thread=threading.Thread(target=work); thread.start()
    deadline=time.monotonic()+10
    while job.process is None and thread.is_alive() and time.monotonic()<deadline: time.sleep(.02)
    assert job.process is not None
    job.cancel(); thread.join(10)
    assert not thread.is_alive() and outcomes==['cancelled']
    assert set(folder.iterdir())==listing
    print('PASS cancel and partial-file cleanup')
print('ALL INTEGRATION CHECKS PASSED')
