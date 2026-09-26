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
    for folder in ['api', 'core', 'runtime', 'schemas', 'domains', 'examples', 'validation']:
        for path in sorted((ROOT/folder).glob('*.lua')):
            name = 'hd2runtime/' + path.relative_to(ROOT).with_suffix('').as_posix()
            output.append('package.preload['+lua(name)+']=function(...)\n'+path.read_text()+'\nend\n')
    return ''.join(output)


def fixture():
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
    return 'local spans='+lua(spans)+'\nlocal cooldown_offset='+str(target_offset)+'\n'+(ROOT/'tests/memory.lua').read_text()


def run(body):
    return execute((modules()+fixture()+'\n'+body).encode())
