"""Real Windows replacement/restart and rollback check; run after EXE build."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from exe_updater import start_exe_installer, PREFIX
from updater import digest
from version import VERSION


def prepare(folder, data):
    folder.mkdir()
    name=f'HandyToolsApp-Windows-x64-v{VERSION}.exe'
    package=dict(kind='windows-exe',version=VERSION,name=name,url=PREFIX+'v'+VERSION+'/'+name,
                 size=len(data),sha256=hashlib.sha256(data).hexdigest())
    (folder/'package.exe').write_bytes(data)
    (folder/'package.json').write_text(json.dumps(package),encoding='utf-8')
    shutil.copy2(Path(__file__).resolve().parents[1]/'downloader/ExeUpdate.ps1',folder/'install.ps1')
    return folder


def main():
    source=Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix='Handy EXE update ') as temporary:
        root=Path(temporary)/'آزمایش with spaces [app]';root.mkdir()
        target=root/'Handy Tools.exe';shutil.copy2(source,target)
        data=source.read_bytes();original=digest(target)
        stage=prepare(root/'valid stage',data)
        old_report=root/'old startup.json'
        parent=subprocess.Popen([str(target),'--smoke-test',str(old_report)],
            env=dict(os.environ,HANDY_SMOKE_DELAY_MS='8000'),cwd=root)
        report=root/'updated startup.json'
        # Emulate a frozen parent's stale extraction environment. Restart must reset it.
        with patch.dict(os.environ, {'_PYI_ARCHIVE_FILE':str(target),
                         '_PYI_APPLICATION_HOME_DIR':str(root/'removed extraction'),
                         '_PYI_PARENT_PROCESS_LEVEL':'1'}):
            helper=start_exe_installer(target,stage,parent.pid,restart_smoke_report=report)
        helper_status=helper.wait(timeout=180)
        parent.wait(timeout=120)
        if helper_status != 0:
            raise AssertionError((stage/'result.json').read_text(encoding='utf-8-sig') if (stage/'result.json').exists() else 'No installer result')
        assert old_report.is_file() and report.is_file()
        assert json.loads(report.read_text())==dict(version=VERSION,frozen=True,ok=True)
        assert json.loads((stage/'result.json').read_text(encoding='utf-8-sig'))['ok']
        assert digest(target)==original and not list(root.glob('.handy-previous-*'))
        print('PASS: real moved EXE exits, is atomically replaced, and restarts with Unicode/spaced paths.')
        # Correct checksum + deliberately invalid PE must trigger real replacement rollback.
        stage=prepare(root/'rollback stage',b'MZ'+b'invalid executable'*100)
        parent=subprocess.Popen([sys.executable,'-c','pass'])
        helper=start_exe_installer(target,stage,parent.pid,restart_smoke_report=root/'invalid startup.json')
        assert helper.wait(timeout=180)!=0
        parent.wait(timeout=10)
        result=json.loads((stage/'result.json').read_text(encoding='utf-8-sig'))
        assert not result['ok'] and 'restored' in result['message'],result
        assert digest(target)==original
        assert not list(root.glob('.handy-previous-*'))
        assert not Path(str(target)+'.handy-update.lock').exists()
        subprocess.run([str(target),'--smoke-test',str(root/'restored startup.json')],check=True,timeout=120)
        print('PASS: failed replacement startup rolls back, preserves old EXE, and the restored app runs.')


if __name__=='__main__': main()
