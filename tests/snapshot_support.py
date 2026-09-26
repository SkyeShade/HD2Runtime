from __future__ import annotations

from pathlib import Path
import json
import struct

from support import ROOT

MAGIC=b'HD2SNAP\0'
VERSION=1
RESERVE=16*1024*1024
CAPTURED=1


def _text(value: str) -> bytes:
    raw=value.encode()
    return struct.pack('<I',len(raw))+raw


def snapshot_bytes(path: Path, regions, *, exe_sha=None, dll_sha=None, version=VERSION,
                   region_order=None, total_override=None):
    profile_text=(ROOT/'schemas/current.lua').read_text()
    import re
    exe_sha=exe_sha or re.search(r'\["exe_sha"\]="([0-9A-F]+)"',profile_text).group(1)
    dll_sha=dll_sha or re.search(r'\["dll_sha"\]="([0-9A-F]+)"',profile_text).group(1)
    ordered=list(regions if region_order is None else region_order)
    payload=bytearray();rows=[]
    for item in ordered:
        data=item.get('data',b'')
        status=item.get('status',CAPTURED if len(data)==item['size'] else 0)
        offset=RESERVE+len(payload) if data else 0
        payload.extend(data)
        rows.append(struct.pack('<QQQIIIIQQII',item['base'],item.get('allocation_base',item['base']),
            item['size'],item.get('state',0x1000),item.get('type',0x20000),item.get('protect',2),
            status,len(data),offset,item.get('error_code',0),0))
    total_virtual=sum(r['size'] for r in ordered)
    total_captured=len(payload) if total_override is None else total_override
    modules=[('helldivers2.exe',0x10000000,0x1000,exe_sha),('game.dll',0x10001000,0x1000,dll_sha)]
    fixed=struct.pack('<8sIIIIIIIIQQQQ',MAGIC,version,0,RESERVE,len(rows),2,0x8664,4096,0,
        0x10002000,total_virtual,total_captured,1700000000)
    body=fixed+exe_sha.encode()+dll_sha.encode()+_text('0.7.1')+_text('')+_text('2026-01-01T00:00:00Z')
    body+=struct.pack('<8Q',0,0,0,0,0,0,0,0)
    for name,base,size,sha in modules:
        body+=_text(name)+struct.pack('<QQ',base,size)+sha.encode()
    body+=b''.join(rows)
    body=body[:12]+struct.pack('<I',len(body))+body[16:]
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('wb') as file:
        file.write(body);file.seek(RESERVE);file.write(payload)
    return path


def materialized_mapper_regions(folder: Path):
    fixture=json.loads((ROOT/'tests/fixtures/reference.json').read_text())
    import re
    profile=(ROOT/'schemas/current.lua').read_text()
    entity_size=int(re.search(r'\["entity_region_size"\]=(\d+)',profile).group(1))
    entity=bytearray(entity_size)
    for span in fixture['entity']:
        raw=bytes.fromhex(span['hex']);entity[span['offset']:span['offset']+len(raw)]=raw
    projectile=bytes.fromhex(fixture['buffers']['projectile']).ljust(0x18000,b'\0')
    damage=bytes.fromhex(fixture['buffers']['damage']).ljust(0xD000,b'\0')
    regions=[
        {'base':0x100000,'allocation_base':0x100000,'size':entity_size,'data':bytes(entity)},
        {'base':0x4000000,'allocation_base':0x4000000,'size':0x18000,'data':projectile},
        {'base':0x5000000,'allocation_base':0x5000000,'size':0xD000,'data':damage},
        {'base':0x10000000,'allocation_base':0x10000000,'size':0x1000,'type':0x1000000,'data':b'MZ'+b'\0'*4094},
        {'base':0x10001000,'allocation_base':0x10001000,'size':0x1000,'type':0x1000000,'data':b'MZ'+b'\0'*4094},
    ]
    snapshot_bytes(folder/'parity.hd2snap',regions)
    for index,r in enumerate(regions):
        (folder/f'region{index}.bin').write_bytes(r['data'])
    return regions,folder/'parity.hd2snap'
