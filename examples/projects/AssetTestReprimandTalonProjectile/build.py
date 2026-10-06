"""Build this mod using a shared, separately installed developer SDK.

The SDK is the folder holding hd2.py and metadata.json (the extracted HD2Runtime-<version>-sdk.zip). It is found in
this order: the HD2RUNTIME_SDK environment variable; the "sdk" path in hd2runtime.json; then this project's folder
and every folder above it, each one itself or a subfolder named sdk or ending in -sdk. To point the project at an
SDK for good: python <SDK>/hd2.py configure <this project> --sdk <SDK>"""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parent


def is_sdk(path):
    return (path/'hd2.py').is_file() and (path/'metadata.json').is_file()


def find_sdk():
    configured=json.loads((ROOT/'hd2runtime.json').read_text(encoding='utf-8')).get('sdk')
    named=[Path(os.environ['HD2RUNTIME_SDK'])] if os.environ.get('HD2RUNTIME_SDK') else []
    for path in named+([ROOT/configured] if configured else []):
        if is_sdk(path):return path.resolve()
    for folder in (ROOT,*ROOT.parents):
        if is_sdk(folder):return folder
        try:children=sorted(p for p in folder.iterdir() if p.is_dir() and (p.name.lower()=='sdk'
            or p.name.lower().endswith('-sdk')))
        except OSError:continue
        for child in children:
            if is_sdk(child):return child
    return None


def started_by_double_click():
    """True when this has a console window of its own (a double-click), which closes as soon as it exits."""
    if os.name!='nt' or not sys.stdin.isatty():return False
    try:
        import ctypes
        kernel=ctypes.windll.kernel32
        pids=(ctypes.c_uint32*16)()
        count=kernel.GetConsoleProcessList(pids,16)

        def image(pid):
            handle=kernel.OpenProcess(0x1000,False,pid)
            if not handle:return ''
            try:
                name=ctypes.create_unicode_buffer(1024);size=ctypes.c_uint32(1024)
                return Path(name.value).name.lower() if kernel.QueryFullProcessImageNameW(handle,0,name,
                    ctypes.byref(size)) else ''
            finally:kernel.CloseHandle(handle)
        # Started from a shell, the shell shares the console; started by a double-click, only the py launcher can.
        return 0<count<=16 and all(image(pid) in ('py.exe','pyw.exe') for pid in pids[:count] if pid!=os.getpid())
    except Exception:return False


def main():
    sdk=find_sdk()
    if sdk is None:
        print('HD2Runtime SDK not found for '+str(ROOT)+'.\n'
            'Extract HD2Runtime-<version>-sdk.zip, then either:\n'
            '  * put this project inside or beside the SDK folder (a folder named sdk or ending in -sdk), or\n'
            '  * run: python <SDK>\\hd2.py configure "'+str(ROOT)+'" --sdk <SDK>, or\n'
            '  * set the HD2RUNTIME_SDK environment variable to the SDK folder.\n'
            'The SDK folder is the one holding hd2.py and metadata.json.',file=sys.stderr)
        return 1
    print('HD2Runtime SDK: '+str(sdk),flush=True)
    return subprocess.run([sys.executable,'-B',str(sdk/'hd2.py'),'build',str(ROOT)]).returncode


if __name__=='__main__':
    status=main()
    if started_by_double_click():input('\nBuild '+('finished' if status==0 else 'FAILED')+'. Press Enter to close.')
    sys.exit(status)
