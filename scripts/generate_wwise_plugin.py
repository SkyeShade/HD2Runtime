"""Generate domains/wwise_plugin.lua from research/wwise-plugin-F5FEE03DCFDB.json
(research/docs/wwise-plugin-bindings-F5FEE03DCFDB.md): what runtime/wwise_playing.lua and runtime/sound_events.lua
prove in the loaded Wwise plugin (bin/plugins/wwise_pluginw64_release.dll) before they call its bindings or read its
playing-id map: the module's image size, the pinned instructions of every binding the Runtime calls (trigger_event, the
source resolver, stop / pause / resume / is_playing / get_playing_elapsed, set_source_parameter, set_switch,
post_trigger, has_event / wwise_world, the name hash) and of the counter-id map, and that map's layout.

Every layout value is checked against the pinned instruction that shows it (a value the pins do not show is refused).
Pins never cover a relocated byte of the installed DLL (checked when the DLL is present).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from reference_format import lua  # noqa: E402

RESEARCH = ROOT / 'research/wwise-plugin-F5FEE03DCFDB.json'
OUTPUT = 'domains/wwise_plugin.lua'
MODULE = 'wwise_pluginw64_release.dll'
GROUPS = ('apiOffsets', 'resolver', 'triggerEvent', 'postEvent', 'playingLookup', 'stopEvent', 'pauseResume',
    'isPlaying', 'elapsed', 'sourceParameter', 'setSwitch', 'postTrigger', 'wwiseModule', 'hash', 'playingIdMap')
# The counter-id map (research "playingIdTranslation"): each value with the pinned instruction text that shows it.
LAYOUT = {
    'managerGlobal': (0x5757E8, 'ripTarget'),
    'map': (0x1CE70, 'lea r8, [rcx + 0x1ce70]'),
    'entries': (0x10, 'mov r10, qword ptr [r8 + 0x10]'),
    'live': (0x20, 'cmp dword ptr [r8 + 0x20], 0'),
    'buckets': (0x24, 'div dword ptr [r8 + 0x24]'),
    'multiplier': (0x5BD1E995, 'imul eax, r9d, 0x5bd1e995'),
    'shift': (24, 'shr ecx, 0x18'),
    'next': (0xC, 'cmp dword ptr [r10 + rax*8 + 0xc], -2'),
    'chainEnd': (0x7FFFFFFF, 'cmp edx, 0x7fffffff'),
}
ENTRY = {'size': 16, 'key': 0, 'state': 4, 'id': 8, 'next': 0xC, 'empty': 0xFFFFFFFE}
DLL = Path(r'C:\Program Files (x86)\Steam\steamapps\common\Helldivers 2\bin\plugins') / MODULE


def relocated(path: Path) -> set[int]:
    """RVAs of every byte a base relocation of the DLL rewrites."""
    raw = path.read_bytes()
    pe = struct.unpack_from('<I', raw, 0x3C)[0]
    nsec = struct.unpack_from('<H', raw, pe + 6)[0]
    opt = struct.unpack_from('<H', raw, pe + 20)[0]
    reloc_rva, reloc_size = struct.unpack_from('<II', raw, pe + 24 + 112 + 5 * 8)
    sections = []
    for i in range(nsec):
        o = pe + 24 + opt + 40 * i
        vsize, va, rsize, rptr = struct.unpack_from('<IIII', raw, o + 8)
        sections.append((va, max(vsize, rsize), rptr))

    def offset(rva):
        for va, size, rptr in sections:
            if va <= rva < va + size:
                return rptr + rva - va
        raise ValueError('rva outside the sections')
    out, o, end = set(), offset(reloc_rva), offset(reloc_rva) + reloc_size
    while o < end:
        page, size = struct.unpack_from('<II', raw, o)
        if size < 8:
            break
        for k in range((size - 8) // 2):
            entry = struct.unpack_from('<H', raw, o + 8 + 2 * k)[0]
            kind, at = entry >> 12, entry & 0xFFF
            if kind == 10:
                out.update(range(page + at, page + at + 8))
            elif kind == 3:
                out.update(range(page + at, page + at + 4))
        o += size
    return out


def build() -> dict:
    research = json.loads(RESEARCH.read_text(encoding='utf-8'))
    plugin = research['plugin']
    sections = plugin['sections']
    text = next(s for s in sections if s['name'] == '.text')
    last = max(sections, key=lambda s: s['rva'])
    image_size = (last['rva'] + max(last['virtualSize'], last['rawSize']) + 0xFFF) & ~0xFFF
    pins, seen = [], set()
    for group in GROUPS:
        for p in research['pins'][group]:
            if not text['rva'] <= p['rva'] < text['rva'] + text['virtualSize']:
                raise ValueError('a pin outside .text: %r' % p)
            key = (p['rva'], p['bytes'])
            if key in seen:
                continue
            seen.add(key)
            pins.append({'rva': p['rva'], 'hex': p['bytes'], 'label': group + ': ' + p['asm']})
    pins.sort(key=lambda p: (p['rva'], p['hex']))
    by_asm = {p['asm'] for p in research['pins']['playingIdMap']}
    targets = {p.get('ripTarget') for p in research['pins']['playingIdMap'] if 'manager' in p['role']}
    layout = {}
    for name, (value, shown) in LAYOUT.items():
        if shown == 'ripTarget':
            if value not in targets:
                raise ValueError('the manager global is not the pinned one')
        elif shown not in by_asm:
            raise ValueError('the pinned instructions do not show ' + name + ' (' + shown + ')')
        layout[name] = value
    if DLL.is_file():
        moved = relocated(DLL)
        hit = [p for p in pins if moved & set(range(p['rva'], p['rva'] + len(p['hex']) // 2))]
        if hit:
            raise ValueError('pins cover relocated bytes: %r' % hit[:3])
    return {'source': {'research': RESEARCH.name, 'sha256': plugin['sha256'], 'wwiseSdk': plugin.get('wwiseSdk')},
        'module': MODULE, 'imageSize': image_size, 'counterMap': {**layout, 'entry': ENTRY,
            'states': {'posted': 0, 'virtual': 1, 'queued': 2, 'sharedJoined': 3, 'sharedStarted': 4}},
        'pins': pins}


def outputs() -> dict[str, str]:
    return {OUTPUT: '-- Generated by scripts/generate_wwise_plugin.py; do not edit.\nreturn ' + lua(build()) + '\n'}


def generate(check=False):
    stale = []
    for name, body in outputs().items():
        path = ROOT / name
        if not path.exists() or path.read_text(encoding='utf-8') != body:
            stale.append(name)
            if not check:
                with open(path, 'w', encoding='utf-8', newline='') as handle:
                    handle.write(body)
    if check and stale:
        raise RuntimeError('Stale Wwise plugin domain: ' + ', '.join(stale))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    print(', '.join(generate(parser.parse_args().check)) or 'up to date')
