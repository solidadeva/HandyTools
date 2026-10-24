"""Build a reproducible source release and per-file update index."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from updater import managed_path, validate_manifest, REPOSITORY, INSTALLED
from version import VERSION


def build(root,commit,destination):
    root,destination=Path(root),Path(destination);destination.mkdir(parents=True,exist_ok=True)
    files={}
    for path in sorted(root.rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts or '.git' in path.parts or '.venv' in path.parts:
            continue
        name=path.relative_to(root).as_posix()
        try:
            managed_path(name)
        except ValueError:
            continue
        data=path.read_bytes();files[name]=dict(sha256=hashlib.sha256(data).hexdigest(),size=len(data))
    manifest=validate_manifest(dict(schema=1,repository=REPOSITORY,version=VERSION,commit=commit,files=files))
    text=json.dumps(manifest,ensure_ascii=False,indent=2)+'\n'
    (destination/'handy-update.json').write_text(text,encoding='utf-8')
    archive=destination/f'HandyToolsApp-Windows-v{VERSION}.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        selected=set(files)
        for folder in ('tests','tools'):
            selected.update(p.relative_to(root).as_posix() for p in (root/folder).rglob('*.py') if '__pycache__' not in p.parts)
        for name in sorted(selected):
            z.write(root/name,'HandyToolsApp/'+name)
        z.writestr('HandyToolsApp/'+INSTALLED,text)
    return manifest,archive


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--commit',required=True);parser.add_argument('--output',default='release')
    args=parser.parse_args();manifest,archive=build(ROOT,args.commit,args.output)
    print(f'{archive}: {len(manifest["files"])} managed files')
