"""Read-only source/fingerprint verification; does not open the game process."""
from pathlib import Path
import hashlib
import json
import os

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest().upper()


def main():
    manifest=json.loads((ROOT/'docs/provenance.json').read_text())
    changed=[s['path'] for s in manifest['sources'] if digest(ROOT.parent/s['path'])!=s['sha256']]
    if changed:
        raise RuntimeError('Audited sibling inputs changed: '+', '.join(changed))
    game=Path(os.environ.get('HD2_GAME_ROOT',r'C:\Program Files (x86)\Steam\steamapps\common\Helldivers 2'))
    expected=json.loads((ROOT.parent/'Jar-5_buff/src/current_build.json').read_text())['files']
    files={}
    for relative,spec in expected.items():
        actual=digest(game/relative)
        files[relative]={'sha256':actual,'matches':actual==spec['sha256']}
    report={'audited_sources_unchanged':len(manifest['sources']), 'installed_files':files,
            'live_process_read':False,'game_launched':False,'deployed':False}
    (ROOT/'build').mkdir(exist_ok=True)
    (ROOT/'build/audit-verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    if not all(f['matches'] for f in files.values()):
        raise RuntimeError('Installed build differs from audited input')


if __name__=='__main__':
    main()
