"""The DIRECT DAMAGE OVERRIDES of a fired round (the user's choice of 2026-10-07 for the custom Gas and EMS EATs:
"500/500" instead of the EAT-17 rocket's 2000/2000, per rocket, never the shared rows). Read-only, offline. Writes
research/direct-damage-F5FEE03DCFDB.json; scripts/generate_direct_damage.py turns it into domains/direct_damage.lua.

A projectile's direct hit is a DamageInfo row named by id: ProjectileInfo +0x3C. SpawnProjectile copies that id into
the spawned projectile's own hit record +0x0C, and the DamageInfo row's first armour penetration (u16 +0xC) into the
record +0x18 (research/projectile-rows-F5FEE03DCFDB.json `copied`; the pins below). The row's +0x3C is never read again
through a spawned projectile's stored type (docs/custom-projectile-rows.md, the five late lookups), and a Runtime-owned
row whose +0x3C named another damage hit harder live (F5, OBSERVED). So one exact rocket can hit with another reviewed
DamageInfo row: ONE guarded 4-byte write of its own record +0x0C while it flies (runtime/projectile_impact.lua, in the
same transaction as its impact explosion), its +0x18 (the penetration it spawned with) untouched. Neither DamageInfo row
nor the ProjectileInfo row is ever written: they are only named.

Proven here, on build F5FEE03DCFDB, in every retained snapshot:

1. The round's row (EAT-17 rocket 132) names the reviewed `from` DamageInfo (+0x3C), and both DamageInfo rows (the
   round's own and every override's) are byte-identical across snapshots and decode to the reviewed values.
2. The spawn-copy instructions (+0x3C -> record +0x0C; the penetration -> record +0x18) are identical in every snapshot.

The reviewed override: DamageInfo 238 (500 / 500, AP 6/5/4/0, no status; the direct hit of projectile 272, a rocket
of no catalogued weapon): the 500 / 500 row whose penetration is closest to the EAT-17's own (6/6/6/3). Its first
penetration (6) equals the EAT-17's, so the record's +0x18 copy is the same either way.
"""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_event_state as base  # noqa: E402
from research_stratagem_calldown import SNAPSHOTS  # noqa: E402

OUTPUT = ROOT / 'research/direct-damage-F5FEE03DCFDB.json'
ROWS = ROOT / 'research/projectile-rows-F5FEE03DCFDB.json'
TABLES = {'projectile': 0x37C7670, 'damage': 0x37C60C0}
STRIDES = {'projectile': 272, 'damage': 76}
PROJECTILE_DAMAGE = 0x3C
# The spawned projectile's own hit record: the DamageInfo id and the penetration SpawnProjectile copied.
HIT = {'directDamage': 0x0C, 'armorPenetration': 0x18}
COPY_ROLES = ('row +0x3C DamageInfoType read at spawn', 'stored in the projectile record +0x0C',
    'its DamageInfo row looked up at spawn', 'armour penetration copied from the DamageInfo row',
    'into the projectile record +0x18')

# {round projectile: {name, from DamageInfo, overrides: {label: DamageInfo id}}}
REVIEWED = {
    132: {'weapon': 'EAT-17 Expendable Anti-Tank', 'from': 227, 'overrides': {500: 238}},
}


def decode(raw: bytes) -> dict:
    v = struct.unpack_from('<19I', raw, 0)
    statuses = [{'status': v[k], 'value': v[k + 1]} for k in range(11, 19, 2) if v[k]]
    return {'standard': v[1], 'durable': v[2], 'armorPenetration': list(v[3:7]), 'statuses': statuses}


def row(mem, kind: str, ident: int) -> bytes:
    p = mem.ptr(mem.game + TABLES[kind] + 8 * ident)
    raw = mem.read(p, STRIDES[kind]) if p else None
    if raw is None or struct.unpack_from('<I', raw, 0)[0] != ident:
        raise ValueError('%s: %s %d is not its row' % (mem.name, kind, ident))
    return raw


def copy_pins() -> list[dict]:
    copied = json.loads(ROWS.read_text(encoding='utf-8'))
    found = {}

    def walk(o):
        if isinstance(o, dict):
            if o.get('role') in COPY_ROLES and 'rva' in o and 'bytes' in o:
                found[o['role']] = {'rva': o['rva'], 'bytes': o['bytes'], 'label': o['role']}
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(copied)
    missing = [r for r in COPY_ROLES if r not in found]
    if missing:
        raise ValueError('the projectile-rows research lacks the spawn-copy pins: %r' % missing)
    return [found[r] for r in COPY_ROLES]


def build() -> dict:
    pins = copy_pins()
    rounds = {}
    for projectile, spec in REVIEWED.items():
        ids = [spec['from']] + list(spec['overrides'].values())
        seen: dict[int, bytes] = {}
        for name in SNAPSHOTS:
            mem = base.Mem(name)
            try:
                p = row(mem, 'projectile', projectile)
                if struct.unpack_from('<I', p, PROJECTILE_DAMAGE)[0] != spec['from']:
                    raise ValueError('%s: projectile %d does not name DamageInfo %d' % (name, projectile, spec['from']))
                for ident in ids:
                    raw = row(mem, 'damage', ident)
                    if seen.setdefault(ident, raw) != raw:
                        raise ValueError('DamageInfo %d differs between snapshots' % ident)
            finally:
                mem.close()
        own = decode(seen[spec['from']])
        overrides = {}
        for label, ident in spec['overrides'].items():
            d = decode(seen[ident])
            if d['statuses']:
                raise ValueError('DamageInfo %d has statuses: not a plain override' % ident)
            if (d['standard'], d['durable']) != (label, label):
                raise ValueError('DamageInfo %d is not %d / %d' % (ident, label, label))
            overrides[str(label)] = {'damage': ident, 'reviewed': seen[ident].hex(), **d}
        rounds[str(projectile)] = {'weapon': spec['weapon'], 'from': spec['from'], 'fromReviewed': seen[spec['from']].hex(),
            'own': own, 'overrides': overrides}
    bad = {name: base.verify_pins_live(name, pins, []) for name in SNAPSHOTS}
    if any(bad.values()):
        raise ValueError('a spawn-copy pin differs in a snapshot: %r' % bad)
    return {'build': 'F5FEE03DCFDB', 'snapshots': list(SNAPSHOTS),
        'tables': {'damage': '0x%X' % TABLES['damage'], 'damageStride': STRIDES['damage']},
        'hit': HIT, 'pins': pins, 'rounds': rounds}


if __name__ == '__main__':
    out = build()
    OUTPUT.write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8', newline='\n')
    for k, r in out['rounds'].items():
        print(k, r['weapon'], 'own', r['own'], 'overrides', {l: (o['damage'], o['armorPenetration']) for l, o in
            r['overrides'].items()})
