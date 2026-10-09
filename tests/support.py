from pathlib import Path
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from reference_format import lua
from lua_offline import execute


def modules():
    output = []
    for folder in ['api', 'core', 'runtime', 'schemas', 'domains', 'examples', 'validation', 'primary_mapper']:
        for path in sorted((ROOT/folder).glob('*.lua')):
            name = 'hd2runtime/' + path.relative_to(ROOT).with_suffix('').as_posix()
            output.append('package.preload['+lua(name)+']=function(...)\n'+path.read_text()+'\nend\n')
    return ''.join(output)


_FIXTURES = {}


def fixture():
    # The fixture program is a pure function of these two files, and most tests run it: build it once per content.
    key = ((ROOT/'tests/fixtures/reference.json').read_bytes(), (ROOT/'tests/memory.lua').read_bytes())
    if key not in _FIXTURES:
        _FIXTURES[key] = _fixture()
    return _FIXTURES[key]


def _fixture():
    data = json.loads((ROOT/'tests/fixtures/reference.json').read_text())
    base = 0x6000000
    counts = [20,1,1,20,15,15,15,15,15,15,17]
    buffer = bytearray(80280)
    struct.pack_into('<I', buffer, 0, 11)
    pointers = bytearray(150*8)
    at, kind = 4, 0
    target_offset = None
    for group, count in enumerate(counts):
        size = 16 + count*400 + (16 if group == 3 else 0)
        if group == 10:
            size = len(buffer)-at-24
        struct.pack_into('<4s5I',buffer,at,b'LDLD',1,0x30EB6399,size,1,0)
        root = at+24
        struct.pack_into('<QQ',buffer,root,base+root+16,count)
        for row in range(count):
            ro = root+16+row*400
            k = 23 if kind==22 else 22 if kind==23 else kind
            if group==3 and row==1:
                assert k==22
                raw = bytes.fromhex(data['cooldown_record'])
                buffer[ro:ro+400] = raw
                payload_at = root+16+count*400
                struct.pack_into('<QII',buffer,ro+152,base+payload_at,2,0)
                struct.pack_into('<QQ',buffer,payload_at,0xED13DDC480EC6910,0x73F8498BFFDCF415)
                target_offset = ro
            else:
                struct.pack_into('<I',buffer,ro,k)
            struct.pack_into('<Q',pointers,k*8,base+ro)
            kind += 1
        at = root+size
    assert kind==149 and at==len(buffer)
    image = bytearray(4096)
    image[:2] = b'MZ'
    struct.pack_into('<I',image,60,128)
    image[128:132] = b'PE\0\0'
    struct.pack_into('<H',image,152,0x20B)
    struct.pack_into('<I',image,208,0x3800000)
    spans = [{'at': 0x100000+x['offset'], 'bytes': bytes.fromhex(x['hex'])} for x in data['entity']]
    for key, addr in [('projectile',0x4000000),('damage',0x5000000)]:
        spans.append({'at':addr,'bytes':bytes.fromhex(data['buffers'][key])})
    spans += [{'at':base,'bytes':bytes(buffer)}, {'at':0x10000000,'bytes':bytes(image)},
              {'at':0x10000000+0x348E8F8,'bytes':struct.pack('<Q',base)},
              {'at':0x10000000+0x37CB600,'bytes':bytes(pointers)}]
    spans += component_table_spans(0x10000000, 0x100000)
    return'local spans='+lua(spans)+'\nlocal cooldown_offset='+str(target_offset)+'\n'+(ROOT/'tests/memory.lua').read_text()


# The game's entity manager in the fixture (core/component_tables.lua): its global, the reviewed code pins and one
# table pointer per component index, each at the entity region's own table (as in every vanilla snapshot).
FIXTURE_SLOTS = 0x20000000


def component_table_spans(dll, entity):
    import re
    import generate_component_tables
    domain = generate_component_tables.build()
    profile = (ROOT/'schemas/current.lua').read_text(encoding='utf-8')
    slots = bytearray(8*domain['slots'])
    for offset, index in re.findall(r'\["offset"\]=(\d+),\["header"\]="[0-9a-f]+",\["index"\]=(\d+)', profile):
        struct.pack_into('<Q', slots, 8*int(index), entity+int(offset)+domain['tableFromProfileOffset'])
    pins = domain['pins'] + [pin for rows in domain['lookups'].values() for pin in rows]
    return ([{'at': dll+domain['global'], 'bytes': struct.pack('<Q', FIXTURE_SLOTS-domain['slotBase'])},
             {'at': FIXTURE_SLOTS, 'bytes': bytes(slots)}]
            + [{'at': dll+pin['rva'], 'bytes': bytes.fromhex(pin['hex'])} for pin in pins])


_BUNDLE = {}


def module_bytecode():
    """modules() compiled to bytecode: rebuilt when a module file changes (size or mtime), shared on disk between
    worker processes (build/test-cache, keyed by the source's digest and the Lua VM's)."""
    files = [p for folder in ['api', 'core', 'runtime', 'schemas', 'domains', 'examples', 'validation', 'primary_mapper']
        for p in sorted((ROOT/folder).glob('*.lua'))]
    key = tuple((p.name, p.stat().st_mtime_ns, p.stat().st_size) for p in files)
    if _BUNDLE.get('key') != key:
        import hashlib
        import os
        import lua_offline
        source = modules().encode()
        vm = (Path(os.environ.get('HD2_GAME_ROOT', r'C:\Program Files (x86)\Steam\steamapps\common\Helldivers 2'))
            / 'bin/lua51.dll').stat()
        digest = hashlib.sha256(source + repr((vm.st_size, vm.st_mtime_ns)).encode()).hexdigest()[:32]
        cache = ROOT/'build/test-cache'/('modules-' + digest + '.ljbc')
        try:
            bytecode = cache.read_bytes()
        except OSError:
            bytecode = lua_offline.compile_chunk(source)
            try:
                cache.parent.mkdir(parents=True, exist_ok=True)
                partial = cache.with_name(cache.name + '.%d' % os.getpid())
                partial.write_bytes(bytecode)
                os.replace(partial, cache)
                # Keep the newest few bundles only (each is ~18 MB).
                for old in sorted(cache.parent.glob('modules-*.ljbc'), key=lambda p: p.stat().st_mtime)[:-4]:
                    old.unlink(missing_ok=True)
            except OSError:
                pass   # another worker wrote or removed it: this one still has its bytecode
        _BUNDLE.update(key=key, bytecode=bytecode)
    return _BUNDLE['bytecode']


def run(body):
    # The modules only define package.preload entries, so they run as a precompiled chunk before fixture + body (one
    # state, the same chunk name: module line numbers read as before; fixture and body lines count from 1).
    from lua_offline import execute_after
    return execute_after(module_bytecode(), (fixture()+'\n'+body).encode())
