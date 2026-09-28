"""Read one live allocation from the retained snapshot through the production locator.

Research helper: `region_bytes('projectile')` returns the exact bytes of the uniquely
located settings (or `entity` / `entity_deltas`) allocation, found by
runtime/discover.lua exactly as a guarded write would find it. Nothing is written.
"""
from __future__ import annotations

from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'sdk'))
from tools.lua_runner import execute

SNAPSHOT = Path(r'C:\Users\Skye\AppData\Local\HD2Runtime\local_research\snapshots\F5FEE03DCFDB-20260926T222226Z.hd2snap')


def _lua(value: str) -> str:
    return '"' + ''.join(c if 32 <= ord(c) < 127 and c not in '"\\' else '\\%03d' % ord(c)
        for c in value) + '"'


def _sources():
    result = {}
    for folder in ('api', 'core', 'runtime', 'schemas', 'domains'):
        for path in sorted((ROOT / folder).glob('*.lua')):
            result['hd2runtime/' + path.relative_to(ROOT).with_suffix('').as_posix()] = path.read_bytes()
    return result


def region_bytes(key: str, snapshot: Path = SNAPSHOT) -> tuple[int, bytes]:
    """Return (allocation base, bytes) of the live allocation for a profile key."""
    preload = '\n'.join('package.preload[' + _lua(name) + ']=function(...) return assert(loadstring('
        + _lua(body.decode('latin-1')) + ',' + _lua(name) + '))(...) end' for name, body in _sources().items())
    program = preload + r'''
local profile=require('hd2runtime/schemas/current')
local source=require('hd2runtime/runtime/snapshot_memory_reader').open(''' + _lua(str(Path(snapshot).resolve())) + r''',{
 expected_exe_sha=profile.exe_sha,expected_dll_sha=profile.dll_sha})
local Reader=require('hd2runtime/runtime/reader')
local discover=require('hd2runtime/runtime/discover')
local KEY=''' + _lua(key) + r'''
local worker=coroutine.create(function()
 local reader=Reader.new(source)
 local roots=discover.locate(source,reader,profile,{[KEY]=true})
 local item=roots[KEY];local owner=item.owner or item
 local size=KEY=='entity'and profile.entity_size or KEY=='entity_deltas'and profile.entity_deltas.size
  or profile.settings[KEY].size
 -- Located through the production path; bulk bytes come straight from the snapshot
 -- source because the guarded reader's byte budget is sized for write operations.
 local parts={}
 for at=0,size-1,1048576 do
  parts[#parts+1]=assert(source.read(owner.base+at,math.min(1048576,size-at)))
 end
 local bytes=table.concat(parts)
 source.close()
 local base=owner.base
 return string.char(base%256,math.floor(base/256)%256,math.floor(base/65536)%256,
  math.floor(base/16777216)%256,math.floor(base/4294967296)%256,math.floor(base/1099511627776)%256,0,0)..bytes
end)
local ok,result
repeat ok,result=coroutine.resume(worker)until not ok or coroutine.status(worker)=='dead'
assert(ok,result);return result
'''
    raw = execute(program.encode('latin-1'))
    return struct.unpack_from('<Q', raw, 0)[0], raw[8:]


def compare_pinned(live: bytes, base: int, pinned: bytes) -> dict:
    """Byte comparison allowing only 8-byte pointer relocations (pinned offset -> live base + offset)."""
    if len(live) != len(pinned):
        return {'identical': False, 'reason': 'size differs', 'live': len(live), 'pinned': len(pinned)}
    relocated, other = 0, []
    at = 0
    while at < len(live):
        if live[at] == pinned[at]:
            at += 1
            continue
        # DL pointers may be unaligned and relative to their instance root (base + k).
        match = None
        for word in range(max(0, at - 7), at + 1):
            if word + 8 > len(live):
                break
            a, p = struct.unpack_from('<Q', live, word)[0], struct.unpack_from('<Q', pinned, word)[0]
            delta = a - p - base
            if 0 <= delta <= 64 and p < len(pinned):
                match = word
                break
        if match is None:
            other.append(at)
            at += 1
        else:
            relocated += 1
            at = match + 8
    return {'identical': not other, 'relocatedPointers': relocated, 'otherDifferences': len(other),
        'firstDifferences': other[:8]}
