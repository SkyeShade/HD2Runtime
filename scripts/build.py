"""Build a deterministic source addon for Bingus API 1. Never deploy or launch HD2."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import zipfile

from hd2_archive import ARCHIVE_NAME, make_archive, resource_hash, lua_resource

ROOT = Path(__file__).resolve().parents[1]


def resources(writable=False):
    found = {}
    for folder in ['api', 'core', 'runtime', 'schemas', 'domains', 'examples']:
        for path in sorted((ROOT/folder).glob('*.lua')):
            if path.name == 'addon.lua':
                continue
            if not writable and path.as_posix().endswith(('api/patch.lua', 'core/guarded_write.lua',
                    'domains/patches.lua', 'runtime/windows_write.lua')):
                continue
            name = 'hd2runtime/' + path.relative_to(ROOT).with_suffix('').as_posix()
            found[name] = path.read_bytes()
    found['mods/skyeshade/hd2runtime'] = (ROOT/'runtime/addon.lua').read_bytes()
    found['mods/skyeshade/hd2runtime_report'] = (ROOT/'examples/addon.lua').read_bytes()
    return found


def build():
    version = (ROOT/'VERSION').read_text().strip()
    sources = resources()
    archive = make_archive({resource_hash(name): lua_resource(body) for name, body in sources.items()})
    title = 'HD2Runtime ' + version + ' Read-only Developer Report'
    description = 'Requires Bingus Shared Loader v15+ / API 1. Read-only; no gameplay writes.'
    manifest = {'Version':1, 'Guid':'409256a5-fad4-4f67-bcce-bd7600eca620', 'Name':title,
        'Description':description, 'Options':[{'Name':'Read-only report', 'Description':description, 'Include':['runtime']}]}
    files = {'manifest.json': (json.dumps(manifest, indent=2)+'\n').encode(),
             'runtime/'+ARCHIVE_NAME: archive,
             'runtime/'+ARCHIVE_NAME+'.stream': b'',
             'runtime/'+ARCHIVE_NAME+'.gpu_resources': b'',
             'README.md': (ROOT/'README.md').read_bytes()}
    (ROOT/'build').mkdir(exist_ok=True)
    path = ROOT/'build'/('HD2Runtime-'+version+'-readonly.zip')
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as package:
        for name, content in sorted(files.items()):
            info=zipfile.ZipInfo(name, date_time=(1980,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o100644<<16
            package.writestr(info,content)
    report = {'artifact':path.name, 'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
              'resources':sorted(sources), 'writes':0, 'deployed':False, 'live_game_tested':False}
    (ROOT/'build/build-report.json').write_text(json.dumps(report,indent=2)+'\n')
    return path


if __name__ == '__main__':
    subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-v'],cwd=ROOT,check=True)
    print(build())
