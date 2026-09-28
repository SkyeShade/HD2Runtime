"""Resolve each StratagemInfo row to the game's own stratagem icon template. Read-only research.

Structural chain (no display names are used):
  1. StratagemInfo row: member 0 is `type` (ENUM_UINT32, enum StratagemType) in the pinned type
     library; Runtime already reads it as record_kind and requires it to be unique per row.
  2. StratagemType value -> native member name: the game's own enum name table in game.dll
     (a contiguous array of string pointers from "None" to "Count"). The table is accepted only if it
     is the unique such run whose length equals the enum's value count and whose every entry
     length equals the pinned type library's hidden alias length for that value.
  3. Native member name -> icon key: the game UI's StratagemTypeDataTemplate DataTriggers in
     content/ui/shared/resources/generated_icons/stratagem_icons (Value="<name>" ->
     ContentTemplate {DynamicResource <key>}).
  4. Icon key -> DataTemplate in the same library; templates without vector paths are reported empty.

Inputs: the retained snapshot (game.dll image and StratagemInfo rows through the production parser),
the pinned type library, and the icon library extracted read-only from the installed game data.
Output: research/stratagem-icons-F5FEE03DCFDB.json. No artwork is written.
"""
from __future__ import annotations

import bisect
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_entity_authoring as entity_research
from research_booster_authoring import TypeLibrary
import snapshot_regions

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'research/stratagem-icons-F5FEE03DCFDB.json'
PROFILE = ROOT / 'schemas/current.lua'
LIBRARY = 'content/ui/shared/resources/generated_icons/stratagem_icons'
# Raw Stingray xaml resource (16-byte header + text) of the reviewed game build.
LIBRARY_SHA256 = 'DEDA7000592065F14D79D41C5D153EC1041FFF7A58D6A607DEF232ADD7702EAE'
EXTRACT = entity_research.SIBLINGS / 'ShieldRelayImprovements/local_research/dependencies/hd2-resource-extract.exe'
GAME_DIR = Path(r'C:\Program Files (x86)\Steam\steamapps\common\Helldivers 2')
ENUM = 'StratagemType'
INFO_TYPE = 'StratagemInfo'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def module_image(snapshot: Path, name: str) -> tuple[int, bytes, str, str]:
    """(base, image, exe sha, dll sha) of a loaded module in an HD2SNAP snapshot (core/snapshot_format.lua)."""
    with open(snapshot, 'rb') as handle:
        preamble = handle.read(16)
        if preamble[:8] != b'HD2SNAP\0' or struct.unpack_from('<I', preamble, 8)[0] != 1:
            raise ValueError('unsupported snapshot format')
        handle.seek(0)
        header = handle.read(struct.unpack_from('<I', preamble, 12)[0])
        _, regions, modules, _, _, _ = struct.unpack_from('<6I', header, 16)
        at = 16 + 24 + 32
        exe_sha, dll_sha = header[at:at + 64].decode(), header[at + 64:at + 128].decode()
        at += 128

        def text():
            nonlocal at
            size = struct.unpack_from('<I', header, at)[0]
            at += 4 + size
            return header[at - size:at]
        for _ in range(3):
            text()
        at += 64
        found = None
        for _ in range(modules):
            module = text().decode().lower()
            base, size = struct.unpack_from('<QQ', header, at)
            at += 80
            if module == name:
                found = (base, size)
        rows = []
        for _ in range(regions):
            row = struct.unpack_from('<QQQIIIIQQII', header, at)
            at += 64
            rows.append((row[0], row[2], row[6], row[8]))
        base, size = found
        image = bytearray(size)
        starts = [r[0] for r in rows]
        address = base
        while address < base + size:
            index = bisect.bisect_right(starts, address) - 1
            region = rows[index] if index >= 0 and address < rows[index][0] + rows[index][1] else None
            if region is None:
                later = bisect.bisect_right(starts, address)
                address = starts[later] if later < len(starts) else base + size
                continue
            end = min(region[0] + region[1], base + size)
            if region[2] == 1:
                handle.seek(region[3] + address - region[0])
                image[address - base:end - base] = handle.read(end - address)
            address = end
        return base, bytes(image), exe_sha, dll_sha


def name_table(base: int, image: bytes, lengths: dict[int, int]) -> tuple[int, list[str]]:
    """The unique StratagemType name table: pointer run None..Count whose lengths match the type library."""
    def cstr(pointer):
        offset = pointer - base
        if not 0 <= offset < len(image):
            return None
        end = image.find(b'\0', offset, offset + 128)
        raw = image[offset:end]
        return raw.decode('ascii') if end > offset and all(32 < c < 127 for c in raw) else None
    count = len(lengths)
    if sorted(lengths) != list(range(count)):
        raise ValueError('StratagemType values are not contiguous')
    none = {base + m.start() for m in re.finditer(rb'None\0', image)}
    matches = []
    for offset in range(0, len(image) - 8 * count + 1, 8):
        if struct.unpack_from('<Q', image, offset)[0] not in none:
            continue
        names = [cstr(struct.unpack_from('<Q', image, offset + 8 * i)[0]) for i in range(count)]
        if None in names or names[-1] != 'Count':
            continue
        if all(len(ENUM + '_' + names[v]) == lengths[v] for v in range(count)):
            matches.append((offset, names))
    if len(matches) != 1:
        raise ValueError('expected one StratagemType name table, found %d' % len(matches))
    return matches[0]


def icon_library() -> tuple[bytes, str]:
    with tempfile.TemporaryDirectory() as folder:
        out = Path(folder) / 'stratagem_icons.bin'
        subprocess.run([str(EXTRACT), '-game-dir', str(GAME_DIR), '-name', LIBRARY, '-type', 'xaml', '-out', str(out)],
            check=True, capture_output=True)
        raw = out.read_bytes()
    if sha(raw) != LIBRARY_SHA256:
        raise ValueError('stratagem icon library differs from the reviewed build: ' + sha(raw))
    size = struct.unpack_from('<I', raw, 0)[0]
    return raw, raw[16:16 + size].decode('utf-8')


def bindings(xaml: str) -> tuple[dict[str, str], set[str], set[str]]:
    """(native name -> icon key, templates with vector paths, all template keys)."""
    start = xaml.index('x:Key="StratagemTypeDataTemplate"')
    block = xaml[start:xaml.index('</DataTemplate>', start)]
    pairs = re.findall(r'<DataTrigger Binding="\{Binding\}" Value="([A-Za-z0-9_]+)">\s*'
        r'<Setter TargetName="StratagemIconsContentControl" Property="ContentTemplate" '
        r'Value="\{DynamicResource ([A-Za-z0-9]+)\}"/>', block)
    names = [a for a, _ in pairs]
    if len(set(names)) != len(names):
        raise ValueError('duplicate StratagemType icon binding')
    keys = set(re.findall(r'<DataTemplate x:Key="([A-Za-z0-9]+)">', xaml)) - {'StratagemTypeDataTemplate'}
    vector = {k for k in keys if re.search(r'<DataTemplate x:Key="' + k + r'">\s*<Viewbox>\s*<Canvas[^>]*>\s*<Path ', xaml)}
    return dict(pairs), vector, keys


def main():
    profile = PROFILE.read_text()
    native = entity_research.Native()
    library = TypeLibrary(native.typelib, native.probe)
    lengths = library.lengths(ENUM)
    layout = native.typelib_module.layout(native.typelib, INFO_TYPE, structured=True)
    member = layout['members'][0]
    if not (member['offset64'] == 0 and member['storage'] == 'ENUM_UINT32' and member['type_hash'] == native.probe.dl_hash(ENUM)):
        raise ValueError('StratagemInfo member 0 is not the StratagemType enum')

    base, image, exe_sha, dll_sha = module_image(snapshot_regions.SNAPSHOT, 'game.dll')
    for key, value in (('exe_sha', exe_sha), ('dll_sha', dll_sha)):
        if '["%s"]="%s"' % (key, value) not in profile:
            raise ValueError('snapshot does not match the pinned profile ' + key)
    table_offset, names = name_table(base, image, lengths)

    raw = snapshot_regions.run_lua(r'''
local Reader=require('hd2runtime/runtime/reader')
local out={}
for _,r in ipairs(require('hd2runtime/core/stratagem').capture_all(source,Reader.new(source),profile)) do
 out[#out+1]=r.id..','..r.record_kind end
return table.concat(out,'\n')''').decode()
    rows = {int(i): int(k) for i, k in (line.split(',') for line in raw.splitlines())}
    if len(set(rows.values())) != len(rows) or any(k >= len(names) for k in rows.values()):
        raise ValueError('StratagemInfo types are not unique or out of range')

    resource, xaml = icon_library()
    bound, vector, keys = bindings(xaml)
    unknown = sorted(set(bound) - set(names))
    if unknown:
        raise ValueError('icon bindings name non-StratagemType members: ' + ', '.join(unknown))
    missing = sorted(set(bound.values()) - keys)
    if missing:
        raise ValueError('icon bindings reference missing templates: ' + ', '.join(missing))

    types = []
    for value, name in enumerate(names):
        icon = bound.get(name)
        types.append({'value': value, 'name': name, 'iconKey': icon,
            'template': None if icon is None else 'vector' if icon in vector else 'empty'})
    result = {
        'schemaVersion': 1,
        'snapshot': snapshot_regions.SNAPSHOT.name,
        'exeSha256': exe_sha, 'gameDllSha256': dll_sha,
        'typelibSha256': entity_research.TYPELIB_SHA256,
        'enum': ENUM, 'enumValues': len(names),
        'nameTable': {'module': 'game.dll', 'rva': table_offset, 'lengthsMatchTypeLibrary': True},
        'infoMember': {'type': INFO_TYPE, 'member': 0, 'storage': member['storage']},
        'iconLibrary': {'resource': LIBRARY, 'sha256': LIBRARY_SHA256, 'textSha256': sha(xaml.encode()),
            'templates': len(keys), 'vectorTemplates': len(vector), 'emptyTemplates': sorted(keys - vector),
            'typeBindings': len(bound)},
        'types': types,
        'rows': [{'id': i, 'type': k} for i, k in sorted(rows.items())],
    }
    OUTPUT.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('enumValues', 'nameTable', 'iconLibrary')}, indent=2))


if __name__ == '__main__':
    main()
