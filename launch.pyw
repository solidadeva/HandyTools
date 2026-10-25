"""Windowed entry point; report startup problems without a console."""
import sys
import traceback

try:
    from pathlib import Path
    if (Path(__file__).parent / '.handy-update.lock').exists():
        raise RuntimeError('An update is being installed. Please wait and open the app again. If installation was interrupted, inspect the update log before removing .handy-update.lock.')
    from app import main
    smoke_report = sys.argv[2] if len(sys.argv) == 3 and sys.argv[1] == '--smoke-test' else None
    result = main(smoke_report=smoke_report)
except Exception:
    detail = traceback.format_exc()
    if '--smoke-test' in sys.argv:
        # CI must fail instead of waiting behind a modal window.
        if len(sys.argv) == 3:
            Path(sys.argv[2]).with_suffix('.error.txt').write_text(detail, encoding='utf-8')
    elif sys.platform == 'win32':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None,
            'Handy Tools App could not start.\nRun Install.bat first.\n\n' + detail,
            'Handy Tools App', 16)
    else:
        print(detail, file=sys.stderr)
    result = 1
sys.exit(result)
