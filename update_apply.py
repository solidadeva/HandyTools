"""Separate process that applies verified staged files after the app exits."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import traceback

from updater import validate_manifest, target_path, digest, INSTALLED


def wait_for_exit(pid,timeout=90):
    if pid<=0:
        return
    if os.name=='nt':
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=[ctypes.c_uint32,ctypes.c_int,ctypes.c_uint32]
        kernel.OpenProcess.restype=ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_uint32]
        kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        handle=kernel.OpenProcess(0x00100000,False,pid)
        if not handle:
            if ctypes.get_last_error()==87: # process has already exited
                return
            raise RuntimeError('Cannot wait for the running app to exit')
        try:
            if kernel.WaitForSingleObject(handle,int(timeout*1000))!=0:
                raise RuntimeError('The app did not exit; no files were changed')
        finally:
            kernel.CloseHandle(handle)
    else:
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            try:
                os.kill(pid,0)
            except ProcessLookupError:
                return
            time.sleep(.1)
        raise RuntimeError('The app did not exit; no files were changed')


def apply_update(root,stage,install_dependencies=None):
    root,stage=Path(root).resolve(),Path(stage).resolve()
    manifest=validate_manifest(json.loads((stage/'manifest.json').read_text(encoding='utf-8')))
    plan=json.loads((stage/'plan.json').read_text(encoding='utf-8'))
    # All files must be verified again after the waiting period.
    for name in plan['changed']:
        if name not in manifest['files']:
            raise ValueError('Unexpected staged file')
        path=target_path(stage/'files',name);info=manifest['files'][name]
        if path.stat().st_size!=info['size'] or digest(path)!=info['sha256']:
            raise ValueError('Staged update failed checksum verification')
        target_path(root,name)
    marker=root/INSTALLED
    if marker.is_symlink():
        raise ValueError('The installed-file record cannot be a symbolic link')
    for name,info in manifest['files'].items():
        if name not in plan['changed']:
            current=target_path(root,name)
            if not current.is_file() or digest(current)!=info['sha256']:
                raise ValueError('App files changed during download. Check for updates again.')
    previous=validate_manifest(json.loads(marker.read_text(encoding='utf-8'))) if marker.is_file() else None
    # Deletion is limited to files owned by an earlier successful release.
    deleted=[] if previous is None else [n for n in previous['files'] if n not in manifest['files']]
    affected=list(dict.fromkeys(plan['changed']+deleted))
    for name in affected:
        target_path(root,name)
    lock=root/'.handy-update.lock'
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
    backups=stage/'backup';backups.mkdir(exist_ok=True)
    existed=[];replaced=[];marker_before=marker.read_bytes() if marker.exists() else None
    try:
        # Back up the entire transaction before modifying anything.
        for name in affected:
            path=target_path(root,name)
            if path.exists():
                if not path.is_file():
                    raise ValueError('A managed file path is now a directory')
                backup=target_path(backups,name);backup.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(path,backup);existed.append(name)
        requirements_changed='requirements.txt' in plan['changed']
        for name in plan['changed']:
            dst=target_path(root,name);dst.parent.mkdir(parents=True,exist_ok=True)
            # Stage on the target filesystem before atomic replacement.
            fd,path=tempfile.mkstemp(prefix='.handy-new-',dir=dst.parent)
            os.close(fd);temp=Path(path)
            try:
                shutil.copy2(target_path(stage/'files',name),temp);os.replace(temp,dst)
                replaced.append(name)
            finally:
                temp.unlink(missing_ok=True)
        for name in deleted:
            target_path(root,name).unlink(missing_ok=True);replaced.append(name)
        if requirements_changed:
            if install_dependencies:
                install_dependencies(root/'requirements.txt')
            else:
                result=subprocess.run([sys.executable,'-m','pip','install','-r',str(root/'requirements.txt')],
                    capture_output=True,timeout=900,
                    **({'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}))
                if result.returncode:
                    raise RuntimeError('Dependency installation failed. Run Install.bat.\n'+result.stderr.decode('utf-8',errors='replace')[-2000:])
        temp_marker=root/(INSTALLED+'.new')
        temp_marker.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        os.replace(temp_marker,marker)
    except BaseException:
        for name in reversed(replaced):
            dst=target_path(root,name)
            if name in existed:
                shutil.copy2(target_path(backups,name),dst)
            else:
                dst.unlink(missing_ok=True)
        if marker_before is not None:
            marker.write_bytes(marker_before)
        else:
            marker.unlink(missing_ok=True)
        raise
    finally:
        lock.unlink(missing_ok=True)
    return manifest['version']


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True)
    parser.add_argument('--stage',required=True);parser.add_argument('--pid',type=int,required=True)
    args=parser.parse_args();root=Path(args.root);stage=Path(args.stage)
    try:
        wait_for_exit(args.pid)
        version=apply_update(root,stage)
        (stage/'result.txt').write_text('Installed '+version,encoding='utf-8')
        subprocess.Popen([sys.executable,str(root/'launch.pyw')],cwd=root,
            **({'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {'start_new_session':True}))
        # Retain the previous files and transaction log for manual recovery.
    except Exception:
        detail=traceback.format_exc();(stage/'error.txt').write_text(detail,encoding='utf-8')
        if os.name=='nt':
            ctypes.windll.user32.MessageBoxW(None,'Update failed. Previous app files were restored.\nIf dependency setup failed, run Install.bat.\n\nLog: '+str(stage/'error.txt')+'\n\n'+detail[-1800:], 'Handy Tools App',16)
        return 1
    return 0


if __name__=='__main__':
    sys.exit(main())
