"""Runtime-owned custom MODELS (docs/custom-models.md): a mod's own unit, derived at build time from a vanilla weapon's
unit in the installed game, shipped BESIDE the vanilla resources (never replacing one).

A model project file models/<id>.json names its base weapon and a palette:

    {"base": "M-1000 Maxigun", "palette": "debug"}
    {"base": "M-1000 Maxigun", "palette": {"all": "#FF2A2A", "rows": {"2": "#20E0FF"}}}

The build derives three resources under the mod's own names, from the base's reviewed facts
(sdk/ModelBaseCapabilities.json, research/weapon-variants-F5FEE03DCFDB.json):
* <mod>/models/<id>: the base unit's exact bytes (main and GPU parts), its body material slot naming the material below;
  its bones, state machine, physics and every other material stay the vanilla ones it names;
* <mod>/models/<id>/m_weapon: the base body material's exact bytes, its material LUT reference naming the LUT below;
* <mod>/models/<id>/lut: the base material LUT (23 x 8 R16G16B16A16_FLOAT, 5 mips) with the palette's colours in its
  base colour column (column 0; each row is one material zone), every other value the base's, the mips rebuilt.
They go into a patch of the base's own package archive, so they load exactly when the base weapon's package loads,
beside every vanilla resource they reference. The installed unit, material and LUT must be byte-identical to the
reviewed ones (SHA-256): another game build or a modded base is refused, never guessed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import struct

ID = re.compile(r'^[a-z0-9_]{1,64}$')
COLOUR = re.compile(r'^#[0-9A-Fa-f]{6}$')
UNIT_TYPE, MATERIAL_TYPE, TEXTURE_TYPE = 0xE0A48D0BE9A7453F, 0xEAC0B497876ADEDF, 0xCD4238C6A0C69E32
# The debug palette: one unmistakable colour per material zone (row), so a live look also tells which zone is which.
DEBUG = ['#FF2020', '#20FF40', '#2060FF', '#FFE020', '#FF20E0', '#20F0FF', '#FFFFFF', '#FF8010']
RECORD = 'hd2runtime_models'


def valid_model_id(value: str) -> bool:
    return isinstance(value, str) and ID.fullmatch(value) is not None


def model_name(resource: str, model_id: str) -> str:
    return resource + '/models/' + model_id


def names(resource: str, model_id: str) -> dict:
    base = model_name(resource, model_id)
    return {'unit': base, 'material': base + '/m_weapon', 'lut': base + '/lut'}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def colour(text: str) -> tuple[float, float, float]:
    if not isinstance(text, str) or not COLOUR.fullmatch(text):
        raise ValueError('a palette colour is "#RRGGBB": ' + repr(text))
    return tuple(int(text[k:k + 2], 16) / 255.0 for k in (1, 3, 5))


def palette_rows(palette, rows: int) -> list:
    """The colour (r, g, b) of each LUT row, or None to keep the base's."""
    if palette == 'debug':
        return [colour(DEBUG[k % len(DEBUG)]) for k in range(rows)]
    if not isinstance(palette, dict) or not palette or set(palette) - {'all', 'rows'}:
        raise ValueError('palette must be "debug" or {"all": "#RRGGBB", "rows": {"<row>": "#RRGGBB"}}')
    out = [colour(palette['all']) if 'all' in palette else None] * rows
    for key, value in (palette.get('rows') or {}).items():
        if not (isinstance(key, str) and key.isdigit() and 0 <= int(key) < rows):
            raise ValueError('palette rows are "0".."%d": %r' % (rows - 1, key))
        out[int(key)] = colour(value)
    return out


def read_spec(path: Path) -> dict:
    spec = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(spec, dict) or set(spec) - {'base', 'palette', 'description'}:
        raise ValueError(path.name + ': a model is {"base": <weapon>, "palette": ...}')
    if not isinstance(spec.get('base'), str):
        raise ValueError(path.name + ': "base" names the weapon whose unit the model derives from')
    if 'palette' not in spec:
        raise ValueError(path.name + ': "palette" is required ("debug" or colours)')
    return spec


def project_models(project: Path) -> dict:
    """{model id: spec} of the project's models/<id>.json; {} without models."""
    folder = Path(project) / 'models'
    if not folder.exists():
        return {}
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError('models must be a folder inside the project')
    out = {}
    for path in sorted(folder.iterdir()):
        if path.is_symlink() or not path.is_file() or path.suffix != '.json':
            raise ValueError('models/ holds model files only (models/<id>.json): ' + path.name)
        if not valid_model_id(path.stem):
            raise ValueError('a model id is 1 to 64 lowercase letters, digits or underscores: ' + path.stem)
        out[path.stem] = read_spec(path)
    return out


# ---------------------------------------------------------------------------------------------------- the LUT
def half(value: float) -> bytes:
    return struct.pack('<e', value)


def lut_mips(top: list[list[tuple]], width: int, height: int, mips: int) -> bytes:
    """The mip chain of an RGBA16F image (rows of (r, g, b, a) floats): each lower mip the mean of its 2 x 2 block."""
    levels = [top]
    w, h = width, height
    for _ in range(1, mips):
        nw, nh = max(1, w // 2), max(1, h // 2)
        prev = levels[-1]
        nxt = []
        for y in range(nh):
            row = []
            for x in range(nw):
                block = [prev[min(2 * y + dy, h - 1)][min(2 * x + dx, w - 1)] for dy in (0, 1) for dx in (0, 1)]
                row.append(tuple(sum(p[c] for p in block) / 4.0 for c in range(4)))
            nxt.append(row)
        levels.append(nxt)
        w, h = nw, nh
    out = bytearray()
    for level in levels:
        for row in level:
            for px in row:
                out += b''.join(half(v) for v in px)
    return bytes(out)


def recolour_lut(gpu: bytes, fmt: dict, rows: list) -> bytes:
    width, height, mips = fmt['width'], fmt['height'], fmt['mips']
    if fmt['dxgi'] != 10 or len(rows) != height:
        raise ValueError('the material LUT is not the reviewed R16G16B16A16_FLOAT image')
    top = []
    for y in range(height):
        row = []
        for x in range(width):
            px = list(struct.unpack_from('<4e', gpu, (y * width + x) * 8))
            if x == 0 and rows[y] is not None:
                px[0], px[1], px[2] = rows[y]
            row.append(tuple(px))
        top.append(row)
    out = lut_mips(top, width, height, mips)
    if len(out) != len(gpu):
        raise ValueError('the rebuilt LUT mip chain differs in size from the base (%d, %d)' % (len(out), len(gpu)))
    return out


# ---------------------------------------------------------------------------------------------------- derive
def base_keys(base: dict) -> list:
    """The (type hash, name hash) of the base unit, body material and material LUT."""
    return [(UNIT_TYPE, int(base['unit']['resource'], 16)), (MATERIAL_TYPE, int(base['body']['material'], 16)),
        (TEXTURE_TYPE, int(base['lut']['texture'], 16))]


def derive(resource: str, model_id: str, spec: dict, base: dict, parts: dict) -> tuple[dict, dict]:
    """The model's three resources {(type, name hash): (main, gpu)} and its build record entry. base: the reviewed
    facts of spec['base'] (ModelBaseCapabilities.json); parts: {(type hash, name hash): (main, gpu)} of base_keys(base)
    from the installed game. Every base part must be byte-identical to the reviewed one."""
    try:
        from hd2_archive import resource_hash
    except ImportError:
        from tools.hd2_archive import resource_hash
    (_u, unit_id), (_m, mat_id), (_t, lut_id) = base_keys(base)
    unit_main, unit_gpu = parts[(UNIT_TYPE, unit_id)]
    mat_main, _ = parts[(MATERIAL_TYPE, mat_id)]
    lut_main, lut_gpu = parts[(TEXTURE_TYPE, lut_id)]
    checks = ((unit_main, base['unit']['mainSha256'], 'unit'), (unit_gpu, base['unit']['gpuSha256'], 'unit GPU part'),
        (mat_main, base['body']['mainSha256'], 'body material'), (lut_main, base['lut']['mainSha256'], 'material LUT'),
        (lut_gpu, base['lut']['gpuSha256'], 'material LUT GPU part'))
    for data, want, what in checks:
        if sha(data) != want:
            raise ValueError('%s: the installed %s\'s %s is not the reviewed one (game build %s): another game build or a '
                'modded base; the model is not built' % (model_id, spec['base'], what, base['build']))
    n = names(resource, model_id)
    h = {k: resource_hash(v) for k, v in n.items()}
    slot = base['slots'][base['body']['slotIndex']]
    at = int(slot['at'], 16)
    if struct.unpack_from('<Q', unit_main, at)[0] != mat_id:
        raise ValueError(model_id + ': the body material slot is not where the review found it')
    unit = bytearray(unit_main)
    struct.pack_into('<Q', unit, at, h['material'])
    lut_at = int(base['body']['lutAt'], 16)
    if struct.unpack_from('<Q', mat_main, lut_at)[0] != lut_id:
        raise ValueError(model_id + ': the body material\'s LUT reference is not where the review found it')
    material = bytearray(mat_main)
    struct.pack_into('<Q', material, lut_at, h['lut'])
    rows = palette_rows(spec['palette'], base['lut']['format']['height'])
    lut = recolour_lut(lut_gpu, base['lut']['format'], rows)
    resources = {(UNIT_TYPE, h['unit']): (bytes(unit), unit_gpu), (MATERIAL_TYPE, h['material']): (bytes(material), b''),
        (TEXTURE_TYPE, h['lut']): (lut_main, lut)}
    record = {'base': spec['base'], 'archive': base['archive'], 'build': base['build'],
        'baseUnit': base['unit']['resource'], 'baseUnitSha256': base['unit']['mainSha256'],
        'unit': n['unit'], 'material': n['material'], 'lut': n['lut'],
        'palette': spec['palette'] if spec['palette'] == 'debug' else 'custom',
        'rows': ['#%02X%02X%02X' % tuple(round(c * 255) for c in r) if r else None for r in rows],
        'sha256': {'unit': sha(bytes(unit)), 'material': sha(bytes(material)), 'lut': sha(lut)}}
    return resources, record


def record_lua(records: dict) -> str:
    """The Lua resource <mod resource>/hd2runtime_models: each model's base, names, palette and digests (the Runtime
    checks it before it names the model's unit anywhere; runtime/model_resources.lua)."""
    lines = ['-- Generated by the HD2Runtime SDK build (docs/custom-models.md): the models this mod derived.',
        'return {format=1,models={']
    for model_id, r in sorted(records.items()):
        rows = ','.join(json.dumps(x) if x else 'false' for x in r['rows'])
        lines.append('[%s]={base=%s,archive=%s,build=%s,baseUnit=%s,baseUnitSha256=%s,unit=%s,material=%s,lut=%s,'
            'palette=%s,rows={%s},sha256={unit=%s,material=%s,lut=%s}},' % (json.dumps(model_id), json.dumps(r['base']),
            json.dumps(r['archive']), json.dumps(r['build']), json.dumps(r['baseUnit']), json.dumps(r['baseUnitSha256']),
            json.dumps(r['unit']), json.dumps(r['material']), json.dumps(r['lut']), json.dumps(r['palette']), rows,
            json.dumps(r['sha256']['unit']), json.dumps(r['sha256']['material']), json.dumps(r['sha256']['lut'])))
    lines.append('}}')
    return '\n'.join(lines) + '\n'


def game_parts(keys, folder=None) -> dict:
    """{(type hash, name hash): (main, gpu)} of the wanted resources from the installed game's data (read-only)."""
    try:
        import hd2_game_data
    except ImportError:
        from tools import hd2_game_data
    data = hd2_game_data.Data(folder) if folder else hd2_game_data.Data()
    found = data.find({(name, kind) for kind, name in keys})
    out = {}
    for kind, name in keys:
        hit = found.get((name, kind))
        if not hit:
            raise ValueError('the installed game has no resource 0x%016X of type 0x%016X' % (name, kind))
        archive, main, _stream, gpu = hit
        out[(kind, name)] = (data.read(archive, main), data.read(archive, gpu, '.gpu_resources'))
    return out
