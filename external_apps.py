"""On-demand installation of the official, independent GenyConnect application."""
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import subprocess
import tempfile
import threading
import urllib.request

REPO='genyleap/GenyConnect'
PREFIX='https://github.com/'+REPO+'/releases/download/'
MAX_PACKAGE=512*1024*1024


class InstallCancelled(Exception):
    pass


def cancelled(cancel):
    if cancel is not None and cancel.is_set():
        raise InstallCancelled()


def app_storage():
    if platform.system()=='Windows':
        base=Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))
    elif platform.system()=='Darwin':
        base=Path.home()/'Library/Application Support'
    else:
        base=Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))
    return base/'HandyToolsApp/apps/GenyConnect'


def host_target(system=None,machine=None,environ=None):
    system=system or platform.system();environ=os.environ if environ is None else environ
    if machine is None and system=='Windows' and os.name=='nt':
        info=ctypes.create_string_buffer(64)
        native=ctypes.WinDLL('kernel32',use_last_error=True)
        native.GetNativeSystemInfo.argtypes=[ctypes.c_void_p]
        native.GetNativeSystemInfo.restype=None
        native.GetNativeSystemInfo(info)
        machine={9:'amd64',12:'arm64',0:'x86'}.get(ctypes.c_ushort.from_buffer(info).value)
    machine=machine or (environ.get('PROCESSOR_ARCHITEW6432') or environ.get('PROCESSOR_ARCHITECTURE') if system=='Windows' else None) or platform.machine()
    arch={'amd64':'x86_64','x64':'x86_64','x86_64':'x86_64','arm64':'arm64','aarch64':'arm64'}.get(machine.lower())
    if not arch:
        raise RuntimeError('برای معماری '+machine+' بستهٔ پشتیبانی‌شده‌ای موجود نیست.')
    os_name={'Windows':'windows','Darwin':'macos','Linux':'linux'}.get(system)
    if not os_name:
        raise RuntimeError('سیستم‌عامل '+system+' در این نصب‌کننده پشتیبانی نمی‌شود.')
    return os_name,arch


def select_package(release,system=None,machine=None,environ=None):
    os_name,arch=host_target(system,machine,environ)
    suffix={'windows':'exe','macos':'dmg','linux':'AppImage'}[os_name]
    pattern=r'GenyConnect-\d+(?:\.\d+)+-'+os_name+'-'+arch+r'\.'+suffix
    choices=[a for a in release.get('assets',[]) if re.fullmatch(pattern,a.get('name',''))]
    if len(choices)!=1:
        raise RuntimeError('بستهٔ رسمی مناسب '+os_name+' / '+arch+' در این انتشار موجود نیست.')
    asset=choices[0]
    if not asset.get('browser_download_url','').startswith(PREFIX) or not 0<asset.get('size',0)<=MAX_PACKAGE:
        raise RuntimeError('اطلاعات بستهٔ رسمی معتبر نیست.')
    return asset


def get_release(opener=urllib.request.urlopen):
    req=urllib.request.Request('https://api.github.com/repos/'+REPO+'/releases/latest',headers={'User-Agent':'HandyToolsApp','Accept':'application/vnd.github+json'})
    with opener(req,timeout=30) as response:
        data=response.read(2*1024*1024+1)
    if len(data)>2*1024*1024:raise RuntimeError('Release response is too large')
    release=json.loads(data)
    if release.get('draft') or release.get('prerelease'):
        raise RuntimeError('انتشار پایدار در دسترس نیست.')
    return release


def expected_digest(release,asset,opener=urllib.request.urlopen):
    value=asset.get('digest','') or ''
    if re.fullmatch(r'sha256:[0-9a-fA-F]{64}',value):return value[7:].lower()
    checksum=next((x for x in release.get('assets',[]) if x.get('name')==asset['name']+'.sha256'),None)
    if checksum and checksum.get('browser_download_url','').startswith(PREFIX):
        req=urllib.request.Request(checksum['browser_download_url'],headers={'User-Agent':'HandyToolsApp'})
        with opener(req,timeout=30) as r:value=r.read(4096).decode('ascii').strip()
        match=re.match(r'^([0-9a-fA-F]{64})(?:\s|$)',value)
        if match:return match[1].lower()
    raise RuntimeError('هش معتبر برای بررسی بستهٔ رسمی در دسترس نیست؛ نصب انجام نشد.')


def file_digest(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as f:
        for data in iter(lambda:f.read(256*1024),b''):digest.update(data)
    return digest.hexdigest()


def download_package(release,asset,folder,cancel=None,progress=lambda value,text:None,opener=urllib.request.urlopen):
    # Recheck identity even when called without select_package().
    name=asset['name']
    if Path(name).name!=name or '/' in name or '\\' in name or not asset['browser_download_url'].startswith(PREFIX):
        raise ValueError('Unsafe package path or origin')
    if not 0<asset['size']<=MAX_PACKAGE:raise ValueError('Invalid package size')
    expected=expected_digest(release,asset,opener);folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    output=folder/name;cancelled(cancel)
    if output.is_file() and output.stat().st_size==asset['size'] and file_digest(output)==expected:
        progress(100,'بستهٔ دریافت‌شده بررسی شد');return output
    fd,path=tempfile.mkstemp(prefix='.geny-download-',dir=folder);os.close(fd);temporary=Path(path)
    try:
        digest=hashlib.sha256();received=0
        req=urllib.request.Request(asset['browser_download_url'],headers={'User-Agent':'HandyToolsApp'})
        with opener(req,timeout=30) as response,temporary.open('wb') as stream:
            while True:
                cancelled(cancel);block=response.read(256*1024)
                if not block:break
                received+=len(block)
                if received>asset['size']:raise RuntimeError('اندازهٔ فایل با انتشار رسمی مطابقت ندارد.')
                stream.write(block);digest.update(block)
                progress(min(99,received*100/asset['size']),f'دریافت GenyConnect • {received/1048576:.1f} / {asset["size"]/1048576:.1f} MB')
        cancelled(cancel)
        if received!=asset['size'] or digest.hexdigest()!=expected:
            raise RuntimeError('بررسی فایل ناموفق بود؛ نصاب اجرا نشد. دوباره تلاش کنید.')
        os.replace(temporary,output);progress(100,'بستهٔ رسمی دریافت و بررسی شد');return output
    finally:temporary.unlink(missing_ok=True)


def detect_installed(system=None,storage=None):
    system=system or platform.system();storage=Path(storage) if storage else app_storage()
    candidates=[]
    marker=storage/'installed.json'
    try:
        saved=Path(json.loads(marker.read_text(encoding='utf-8'))['path'])
        if saved.is_absolute():candidates.append(saved)
    except (OSError,ValueError,KeyError,TypeError):pass
    if system=='Windows':
        for key in ('ProgramW6432','ProgramFiles','ProgramFiles(x86)'):
            if os.environ.get(key):
                candidates.extend([Path(os.environ[key])/'GenyConnect/GenyConnect.exe',Path(os.environ[key])/'GenyConnect/bin/GenyConnect.exe'])
        if os.name=='nt':
            import winreg
            for hive in (winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE):
                for flag in (winreg.KEY_WOW64_64KEY,winreg.KEY_WOW64_32KEY):
                    try:
                        with winreg.OpenKey(hive,r'Software\Microsoft\Windows\CurrentVersion\Uninstall',0,winreg.KEY_READ|flag) as root:
                            for i in range(winreg.QueryInfoKey(root)[0]):
                                try:
                                    with winreg.OpenKey(root,winreg.EnumKey(root,i)) as entry:
                                        if 'genyconnect' not in str(winreg.QueryValueEx(entry,'DisplayName')[0]).lower():continue
                                        for value in ('InstallLocation','InstallDir'):
                                            try:
                                                folder=Path(winreg.QueryValueEx(entry,value)[0]);candidates.extend([folder/'GenyConnect.exe',folder/'bin/GenyConnect.exe'])
                                            except OSError:pass
                                except OSError:pass
                    except OSError:pass
    elif system=='Darwin':
        candidates.extend([Path.home()/'Applications/GenyConnect.app',Path('/Applications/GenyConnect.app')])
    else:
        candidates.append(storage/'GenyConnect.AppImage')
        found=shutil.which('GenyConnect') or shutil.which('genyconnect')
        if found:candidates.append(Path(found))
    for path in candidates:
        if (system=='Darwin' and path.suffix=='.app' and (path/'Contents/MacOS').is_dir()) or (system!='Darwin' and path.is_file() and (system=='Windows' or os.access(path,os.X_OK))):
            return path
    return None


def windows_installer(package):
    """Start the upstream NSIS installer through normal Windows elevation."""
    if os.name!='nt':raise RuntimeError('Windows installer requires Windows')
    class SHELLEXECUTEINFO(ctypes.Structure):
        _fields_=[('cbSize',wintypes.DWORD),('fMask',wintypes.ULONG),('hwnd',wintypes.HWND),
            ('lpVerb',wintypes.LPCWSTR),('lpFile',wintypes.LPCWSTR),('lpParameters',wintypes.LPCWSTR),
            ('lpDirectory',wintypes.LPCWSTR),('nShow',ctypes.c_int),('hInstApp',wintypes.HINSTANCE),
            ('lpIDList',ctypes.c_void_p),('lpClass',wintypes.LPCWSTR),('hkeyClass',wintypes.HKEY),
            ('dwHotKey',wintypes.DWORD),('hIcon',wintypes.HANDLE),('hProcess',wintypes.HANDLE)]
    shell=ctypes.WinDLL('shell32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    shell.ShellExecuteExW.argtypes=[ctypes.POINTER(SHELLEXECUTEINFO)];shell.ShellExecuteExW.restype=wintypes.BOOL
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    info=SHELLEXECUTEINFO();info.cbSize=ctypes.sizeof(info);info.fMask=0x40
    info.lpVerb='runas';info.lpFile=str(Path(package).resolve());info.lpParameters='/S';info.nShow=1
    if not shell.ShellExecuteExW(ctypes.byref(info)):
        if ctypes.get_last_error()==1223:raise RuntimeError('نصب با لغو تأیید دسترسی ویندوز متوقف شد؛ فایل برای تلاش بعدی نگه داشته شد.')
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        while True:
            state=kernel.WaitForSingleObject(info.hProcess,200)
            if state==0:break
            if state!=258:raise RuntimeError('Cannot wait for the Windows installer')
        code=wintypes.DWORD()
        if not kernel.GetExitCodeProcess(info.hProcess,ctypes.byref(code)) or code.value not in (0,3010):
            raise RuntimeError('نصاب GenyConnect موفق نبود؛ کد '+str(code.value))
    finally:kernel.CloseHandle(info.hProcess)


def install_package(package,release,system=None,storage=None,runner=subprocess.run,win_install=windows_installer):
    system=system or platform.system();storage=Path(storage) if storage else app_storage();storage.mkdir(parents=True,exist_ok=True)
    package=Path(package)
    if system=='Windows':
        win_install(package);result=detect_installed(system,storage)
        if not result:raise RuntimeError('نصاب بسته شد، اما برنامهٔ نصب‌شده پیدا نشد. نصب را دوباره بررسی کنید.')
    elif system=='Linux':
        result=storage/'GenyConnect.AppImage';temp=storage/'GenyConnect.AppImage.new'
        try:
            shutil.copy2(package,temp);temp.chmod(0o755);os.replace(temp,result)
        finally:temp.unlink(missing_ok=True)
    elif system=='Darwin':
        with tempfile.TemporaryDirectory(prefix='handy-geny-mount-') as mount:
            mounted=False
            try:
                response=runner(['hdiutil','attach',str(package),'-readonly','-nobrowse','-mountpoint',mount,'-plist'],check=True,capture_output=True)
                mounted=True
                # Parse the plist too, so an invalid mount response cannot be mistaken for success.
                plistlib.loads(response.stdout)
                apps=list(Path(mount).glob('GenyConnect.app'))
                if len(apps)!=1:raise RuntimeError('GenyConnect.app was not found in the disk image')
                result=Path.home()/'Applications/GenyConnect.app';result.parent.mkdir(parents=True,exist_ok=True)
                if result.exists():raise RuntimeError('GenyConnect از قبل نصب است؛ آن را از دراور باز کنید.')
                with tempfile.TemporaryDirectory(prefix='.handy-geny-',dir=result.parent) as temporary:
                    staged=Path(temporary)/'GenyConnect.app'
                    shutil.copytree(apps[0],staged,symlinks=True)
                    os.rename(staged,result)
            finally:
                if mounted:runner(['hdiutil','detach',mount],check=False,capture_output=True)
    else:raise RuntimeError('Unsupported OS')
    marker=storage/'installed.json';temp=storage/'installed.json.new'
    temp.write_text(json.dumps(dict(path=str(result.resolve()),version=release['tag_name'])),encoding='utf-8');os.replace(temp,marker)
    return result


def launch_installed(path,system=None):
    path=Path(path);system=system or platform.system()
    args=['open',str(path)] if system=='Darwin' else [str(path)]
    return subprocess.Popen(args,cwd=str(path.parent),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
        **({'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {'start_new_session':True}))
