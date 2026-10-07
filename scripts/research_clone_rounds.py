"""The ROUND OVERRIDES of the carrier weapon clone: a reviewed round a donor's clone may fire instead of the donor's own
(build/test-artifacts/airburst-research/airburst.md option (b); research/docs/carrier-weapon-clone-F5FEE03DCFDB.md).
Read-only, offline. scripts/research_carrier_weapon_clone.py puts the result in research/carrier-weapon-clone-
F5FEE03DCFDB.json `roundOverrides`; scripts/generate_weapon_clone.py validates it and emits domains/weapon_clone.lua
`rounds`.

The one reviewed round: an EAT-17 clone (on the EAT-700 or EAT-411 carrier type) firing the RL-77 Airburst Rocket
Launcher's "Cluster" round 312 natively. The clone's ProjectileWeapon +0 ProjType (the member the full clone already
writes, 132) becomes 312 on the carrier's own type record, so every machine spawns every copy of every shot as 312.
The airburst belongs to the round, not to the weapon:

* projectile row 312: +0x94 = 2.0 turns on a per-frame overlap (proximity) query once the rocket has flown +0xA0 = 1 m
  (its filter: +0xF8 through the stored type); a contact is processed as a hit at the rocket; it requests explosion
  +0x90 = 325; the rocket also bursts when its lifetime +0x34 = 1.5 s runs out (+0x9C = 325, fuse delay +0x98);
* explosion 325 releases its shrapnel: +0x50 = 25 projectiles of +0x54 = type 78 (the bomblet), each exploding as
  explosion 7 on impact or expiry.

Proven here, on build F5FEE03DCFDB:

1. The rows (projectile 312, its damage row, explosion 325, its damage row, the submunition projectile 78, explosion
   7, its damage row; templates and statuses when named: none) are identical in every retained snapshot except the
   explosions' relocated +0x28 word (masked, as research_custom_payloads `reviewed_chain`), and decode to the
   reviewed semantics (SEMANTICS).
2. The code path that consumes those members (SpawnProjectile, the per-frame proximity query, its consumer, the impact
   arming and the fuse): instruction pins (PINS), identical in every retained snapshot.
3. The weapon side: the RL-77's ProjectileWeapon +0 is the round; it differs from the GR-8's only in +0, +0x104, +0x114
   and +0x240 (no fuse, range or lock member); the clone hosts and the RL-77 have the networked fire flag (PW +0x94) and
   the hosts have no ammunition selector (WeaponData +0xB8 = 0): the clone fires the round only.
4. The packages: every resource the chain's rows name ships in the RL-77's own loadout package (its LoadoutPackage +8,
   packages/generated/loadout/airburst_rocket_launcher: the unit 312 needs ships ONLY there) or in the mission package
   0x7ED1F941859987B4 (explosion 325's effect and bomblet 78's unit ship ONLY there); the mission package is resident in
   every in-mission snapshot, absent aboard the ship and unloading at the mission-end transition, and never in the
   RefcountedPackageSystem map (loaded with the level): core/assets `state` reads the engine's package list (the list
   research_package_residency reads), not that map, so it finds the package resident.
"""
from __future__ import annotations

import hashlib
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import hd2_game_data  # noqa: E402
import research_event_state as base  # noqa: E402
import research_package_residency as residency  # noqa: E402
from research_stratagem_calldown import SNAPSHOTS  # noqa: E402
import snapshot_image  # noqa: E402

DONOR = 'EAT-17 Expendable Anti-Tank'
MISSION = [s for s in SNAPSHOTS if 'mission-host' in s]
SHIP = [s for s in SNAPSHOTS if 'mission' not in s]

# The tables (research_custom_payloads: PROJECTILES, EXPLOSIONS, DAMAGES, TEMPLATES, STATUSES, STRIDES).
TABLES = {'projectile': 0x37C7670, 'explosion': 0x37CC920, 'damage': 0x37C60C0, 'template': 0x37C5E90,
    'status': 0x37C5C50}
STRIDES = {'projectile': 272, 'explosion': 152, 'damage': 76, 'template': 40, 'status': 152}
# The words a snapshot may differ in: an explosion row's relocated +0x28 pointer; a status row's +8 (research_custom_
# payloads). Any other differing word refuses the review.
RELOCATED = {'explosion': [40, 44], 'status': [8, 12]}
P = {'speed': 0x20, 'mass': 0x24, 'drag': 0x28, 'gravity': 0x2C, 'lifetime': 0x34, 'lifetimeVariance': 0x38,
    'damage': 0x3C, 'impact': 0x90, 'proximity': 0x94, 'fuseDelay': 0x98, 'expiry': 0x9C, 'arming': 0xA0,
    'overlapFilter': 0xF8}
P_RESOURCES = (0x48, 0x50, 0x60, 0x68, 0x70, 0x78, 0x80)   # ProjectileInfo resources (spawn / trail effects, unit)
X = {'damage': 0x4, 'radii': (0x10, 0x14, 0x18), 'effect': 0x38, 'shrapnelCount': 0x50, 'shrapnelProjectile': 0x54,
    'template': 0x64, 'arc': 0x78}
DAMAGE = {'standard': 0x4, 'durable': 0x8, 'armorPenetration': 0xC, 'statuses': range(0x2C, 0x4C, 8)}
TYPE_NAMES = ('unit', 'particles', 'material', 'texture', 'state_machine', 'bones', 'physics', 'animation',
    'wwise_bank', 'wwise_dep')
LOADOUT_PACKAGE = ('LoadoutPackageComponentData', 8)        # a weapon's own loadout package (u64)

# The reviewed rounds: {donor: {round name: what it is}}.
ROUNDS = {DONOR: {
    'RL-77 Airburst Rocket Launcher': {
        'weapon': 'RL-77',                                   # research_carrier_weapon_clone FOCUS key
        'type': 312,
        'assetKey': 'support_weapon/RL-77 Airburst Rocket Launcher',
        'unitPackage': 'packages/generated/loadout/airburst_rocket_launcher',
        'missionPackage': 0x7ED1F941859987B4,
        'compareWith': 'GR-8',                               # the same ballistics and unit family
        'weaponDifferences': [0x0, 0x104, 0x114, 0x240],     # ProjType, fire sound, haptics, programmable round
    }}}

# What the chain must decode to (a changed value refuses the review).
SEMANTICS = {
    'RL-77 Airburst Rocket Launcher': {
        'round': {'type': 312, 'speed': 250.0, 'mass': 3300.0, 'drag': 0.3, 'lifetime': 1.5, 'proximity': 2.0,
            'arming': 1.0, 'fuseDelay': 0.2, 'impact': 325, 'expiry': 325, 'overlapFilter': '0xAB96E9D8',
            'damage': {'row': 380, 'standard': 350, 'durable': 350, 'armorPenetration': [3, 3, 3, 0]}},
        'explosion': {'id': 325, 'radii': [3.0, 5.0, 7.0], 'template': 0, 'arc': 0,
            'damage': {'row': 277, 'standard': 150, 'durable': 150, 'armorPenetration': [3, 3, 3, 0]},
            'shrapnel': {'count': 25, 'projectile': 78}},
        'submunition': {'type': 78, 'speed': 25.0, 'gravity': 4.0, 'lifetime': 0.8, 'lifetimeVariance': 0.7,
            'impact': 7, 'expiry': 7, 'proximity': 0.0,
            'damage': {'row': 277, 'standard': 150, 'durable': 150, 'armorPenetration': [3, 3, 3, 0]}},
        'submunitionExplosion': {'id': 7, 'radii': [4.0, 6.0, 8.0], 'template': 0, 'arc': 0,
            'damage': {'row': 335, 'standard': 500, 'durable': 500, 'armorPenetration': [3, 0, 0, 0]},
            'shrapnel': {'count': 0, 'projectile': 0}},
    }}
SUMMARY = {'RL-77 Airburst Rocket Launcher': 'round 312 (RL-77 Airburst Rocket Launcher: direct 350, AP 3, 250 m/s; '
    'proximity 2 m after 1 m of flight, else a burst after 1.5 s; explosion 325 (150, AP 3; 3 / 5 / 7 m) + 25 x '
    'bomblet 78 -> explosion 7 (500, AP 3; 4 / 6 / 8 m))'}

# The code that consumes the round's members (game.dll, system-relative offsets in the projectile system): (rva, exact
# instruction, role). Re-proved by runtime/weapon_clone.lua before a round write.
PINS = [
    # SpawnProjectile 0x13A9830: the fuse members copied into the slot.
    (0x13AA103, 'movss xmm2, dword ptr [rcx + 0x34]', 'spawn: row +0x34 lifetime (into flight +0x3074)'),
    (0x13AA486, 'mov ecx, dword ptr [rax + 0x94]', 'spawn: row +0x94 proximity ...'),
    (0x13AA48C, 'mov dword ptr [r15], ecx', '... -> source record +0x00'),
    (0x13AA493, 'mov ecx, dword ptr [rax + 0xa0]', 'spawn: row +0xA0 arming distance ...'),
    (0x13AA49D, 'mov dword ptr [rsi + rax*4 + 0x3b044], ecx', '... -> source record +0x04'),
    (0x13AA646, 'mov ecx, dword ptr [rax + 0x90]', 'spawn: row +0x90 impact explosion -> hit +0x7C'),
    (0x13AA653, 'mov ecx, dword ptr [rax + 0x9c]', 'spawn: row +0x9C expiry explosion -> hit +0x80'),
    (0x13AA700, 'mov ecx, dword ptr [rax + 0x98]', 'spawn: row +0x98 fuse delay ...'),
    (0x13AA706, 'mov dword ptr [rdi + 0x8c], ecx', '... -> hit +0x8C'),
    # The per-frame update after each step's raycast: the proximity query.
    (0x13ABE3A, 'movss xmm1, dword ptr [rbx + r14*4 + 0x3b040]', 'update: source +0x00 (proximity) ...'),
    (0x13ABE4E, 'jne 0x13abf98', '... non-zero: the overlap query'),
    (0x13ABFB7, 'comiss xmm0, dword ptr [rbx + r14*4 + 0x3b044]', 'only once the flight distance reaches source +0x04'),
    (0x13AC064, 'movss xmm1, dword ptr [rbx + r14*4 + 0x3b040]', 'the query shape sized by the proximity'),
    (0x13AC0B8, 'or dword ptr [rax + rbx + 0xe7050], 1', 'the query entry marked (flag bit 0)'),
    (0x13AC0D8, 'mov ecx, dword ptr [r15 + 0xf8]', 'its filter: row +0xF8 through the stored type'),
    (0x13AC1A6, 'mov dword ptr [rcx + rbx + 0xe704c], eax', 'the query handle -> entry +0xC'),
    # The consumer: a marked entry's results become hits at the projectile's own position.
    (0x13AC50C, 'test byte ptr [rbx + r15 + 0xe7050], 1', 'consumer: a proximity contact is a hit at the rocket'),
    (0x13AC68F, 'cmp ebx, dword ptr [r15 + r8*4 + 0x3b04c]', 'hits on the projectile\'s own source are skipped'),
    # The impact arming.
    (0x13AED2A, 'movss xmm0, dword ptr [r15 + rbx*4 + 0x3b044]', 'impact: source +0x04 against the distance flown'),
    (0x13AEDC6, 'mov dword ptr [r14 + 0x80], eax', 'not armed: the impact explosion becomes the expiry one ...'),
    (0x13AEDE5, 'movss dword ptr [r14 + 0x8c], xmm0', '... with a fuse'),
    # The lifetime's end: the pending expiry explosion, now or after the fuse delay.
    (0x13AB6F4, 'mov edx, dword ptr [rbx + rcx + 0x4d0c0]', 'lifetime over: the pending expiry explosion hit +0x80'),
    (0x13AB72F, 'call 0x13b06c0', '... no delay: explode now'),
    (0x13AB751, 'movss dword ptr [rbx + r13 + 0x3074], xmm0', '... else the lifetime becomes the delay (the fuse)'),
    (0x13B0BB9, 'movss dword ptr [rax + rcx + 0x3074], xmm1', 'the fuse routine 0x13B0B90 does the same'),
]


def hexid(value: int) -> str:
    return '0x%016X' % value


def f32(raw: bytes, offset: int) -> float:
    return round(struct.unpack_from('<f', raw, offset)[0], 6)


def u32(raw: bytes, offset: int) -> int:
    return struct.unpack_from('<I', raw, offset)[0]


# ------------------------------------------------------------------------------------------------- rows
def chain(mem, projectile: int) -> list[tuple[str, int, bytes]]:
    """The round's rows in discovery order: the projectile, its damage row, its explosions (each: its damage row, its
    volume template and every status named, then its shrapnel projectile, recursively). Each row is its own id."""
    out, seen = [], set()

    def row(kind, ident):
        p = mem.ptr(mem.game + TABLES[kind] + 8 * ident)
        raw = mem.read(p, STRIDES[kind]) if p else None
        if raw is None or (kind in ('projectile', 'explosion', 'damage') and u32(raw, 0) != ident):
            raise ValueError('%s: %s %d is not its row' % (mem.name, kind, ident))
        return raw

    def add(kind, ident):
        if (kind, ident) in seen:
            return None
        seen.add((kind, ident))
        raw = row(kind, ident)
        out.append((kind, ident, raw))
        return raw

    def damage(ident):
        raw = add('damage', ident)
        if raw is not None:
            for o in DAMAGE['statuses']:
                if u32(raw, o):
                    add('status', u32(raw, o))

    def explosion(ident):
        raw = add('explosion', ident)
        if raw is None:
            return
        damage(u32(raw, X['damage']))
        template = u32(raw, X['template'])
        if template:
            t = add('template', template)
            for o in range(4, 0x24, 8):
                if t is not None and u32(t, o):
                    add('status', u32(t, o))
        if u32(raw, X['shrapnelCount']) and u32(raw, X['shrapnelProjectile']):
            round_(u32(raw, X['shrapnelProjectile']))

    def round_(ident):
        raw = add('projectile', ident)
        if raw is None:
            return
        damage(u32(raw, P['damage']))
        for member in ('impact', 'expiry'):
            if u32(raw, P[member]):
                explosion(u32(raw, P[member]))

    round_(projectile)
    return out


def reviewed_rows(projectile: int) -> tuple[list[dict], dict]:
    """The chain in every retained snapshot: the reviewed rows (the first snapshot's bytes, the words that differ
    between snapshots masked: only the known relocated words may) and each row's masked SHA-256 prefix (the same in
    every snapshot by construction)."""
    per = {}
    for name in SNAPSHOTS:
        mem = base.Mem(name)
        try:
            per[name] = chain(mem, projectile)
        finally:
            mem.close()
    first = per[SNAPSHOTS[0]]
    shape = [(k, i) for k, i, _ in first]
    rows, digests = [], {}
    for name, rows_ in per.items():
        if [(k, i) for k, i, _ in rows_] != shape:
            raise ValueError('%s: the chain of round %d differs: %r' % (name, projectile, rows_))
    for n, (kind, ident, raw) in enumerate(first):
        variants = [per[name][n][2] for name in SNAPSHOTS]
        masked = [o for o in range(0, len(raw), 4) if len({v[o:o + 4] for v in variants}) != 1]
        if any(o not in RELOCATED.get(kind, []) for o in masked):
            raise ValueError('%s %d differs between snapshots outside its relocated words: %r' % (kind, ident, masked))
        if kind in RELOCATED and masked != RELOCATED[kind]:
            raise ValueError('%s %d: its relocated word did not move between snapshots: %r' % (kind, ident, masked))
        rows.append({'kind': kind, 'id': ident, 'table': '0x%X' % TABLES[kind], 'stride': STRIDES[kind],
            'reviewed': raw.hex(), 'masked': masked})
        m = bytearray(raw)
        for o in masked:
            m[o:o + 4] = b'\0' * 4
        digests['%s %d' % (kind, ident)] = hashlib.sha256(bytes(m)).hexdigest().upper()[:16]
    return rows, digests


def damage_of(raw: bytes, ident: int) -> dict:
    return {'row': ident, 'standard': u32(raw, DAMAGE['standard']), 'durable': u32(raw, DAMAGE['durable']),
        'armorPenetration': list(struct.unpack_from('<4I', raw, DAMAGE['armorPenetration']))}


def semantics_of(rows: list[dict], projectile: int) -> dict:
    by = {(r['kind'], r['id']): bytes.fromhex(r['reviewed']) for r in rows}

    def projectile_of(ident, keys):
        raw = by[('projectile', ident)]
        out = {'type': ident}
        for key in keys:
            if key == 'overlapFilter':
                out[key] = '0x%08X' % u32(raw, P[key])
            elif key in ('impact', 'expiry'):
                out[key] = u32(raw, P[key])
            else:
                out[key] = f32(raw, P[key])
        d = u32(raw, P['damage'])
        out['damage'] = damage_of(by[('damage', d)], d)
        return out

    def explosion_of(ident):
        raw = by[('explosion', ident)]
        d = u32(raw, X['damage'])
        return {'id': ident, 'radii': [f32(raw, o) for o in X['radii']], 'template': u32(raw, X['template']),
            'arc': u32(raw, X['arc']), 'damage': damage_of(by[('damage', d)], d),
            'shrapnel': {'count': u32(raw, X['shrapnelCount']), 'projectile': u32(raw, X['shrapnelProjectile'])}}
    top = projectile_of(projectile, ('speed', 'mass', 'drag', 'lifetime', 'proximity', 'arming', 'fuseDelay', 'impact',
        'expiry', 'overlapFilter'))
    x = explosion_of(top['impact'])
    out = {'round': top, 'explosion': x}
    if x['shrapnel']['count']:
        sub = projectile_of(x['shrapnel']['projectile'], ('speed', 'gravity', 'lifetime', 'lifetimeVariance', 'impact',
            'expiry', 'proximity'))
        out['submunition'] = sub
        out['submunitionExplosion'] = explosion_of(sub['impact'])
    return out


# ------------------------------------------------------------------------------------------------- resources
def resources_of(rows: list[dict]) -> list[dict]:
    """Every resource member the chain's rows name: projectile spawn / trail effects and unit, explosion effects."""
    out = []
    for r in rows:
        raw = bytes.fromhex(r['reviewed'])
        offsets = P_RESOURCES if r['kind'] == 'projectile' else (X['effect'],) if r['kind'] == 'explosion' else ()
        for o in offsets:
            value = struct.unpack_from('<Q', raw, o)[0]
            if value:
                out.append({'row': '%s %d' % (r['kind'], r['id']), 'member': '+0x%X' % o, 'resource': hexid(value)})
    return out


def package_names() -> dict:
    """Package names a known path hashes to: the generated residency catalogue's and the reviewed rounds' own."""
    text = (ROOT / 'domains/package_residency.lua').read_text(encoding='utf-8')
    names = set(re.findall(r'packages/[A-Za-z0-9_/\-\.]+', text))
    names.update(spec['unitPackage'] for rounds in ROUNDS.values() for spec in rounds.values())
    return {hd2_game_data.murmur64(n.encode()): n for n in sorted(names)}


def ship_scan(resources: list[dict]) -> dict:
    """{resource: [(type name, package id)]}: every package of the installed game data that ships it."""
    wanted = {int(r['resource'], 16) for r in resources}
    types = {hd2_game_data.murmur64(n.encode()): n for n in TYPE_NAMES}
    found = {w: set() for w in wanted}
    for archive, rname, rtype, _main, _stream, _gpu in hd2_game_data.Data().tables():
        if rname in found:
            found[rname].add((types.get(rtype, '0x%016X' % rtype), int(archive, 16)))
    return found


def packages_report(spec: dict, resources: list[dict]) -> dict:
    names = package_names()
    unit = hd2_game_data.murmur64(spec['unitPackage'].encode())
    mission = spec['missionPackage']
    shipped = ship_scan(resources)
    rows = []
    for r in resources:
        hits = shipped[int(r['resource'], 16)]
        kinds = sorted({k for k, _ in hits})
        packages = sorted({p for _, p in hits})
        rows.append(dict(r, types=kinds, packages=len(packages), inUnitPackage=unit in packages,
            inMissionPackage=mission in packages, onlyIn=[names.get(p, hexid(p)) for p in packages]
            if len(packages) <= 2 else None))
    uncovered = [r for r in rows if not (r['inUnitPackage'] or r['inMissionPackage'])]
    if uncovered:
        raise ValueError('a resource of the round ships in neither of its packages: %r' % uncovered)
    snap = snapshot_image.Snapshot(build_profile.SNAPSHOT)
    try:
        pins = residency.loader_pins(snap)
    finally:
        snap.close()
    resident = {}
    for name in SNAPSHOTS:
        s = snapshot_image.Snapshot(build_profile.snapshot_directory() / name)
        try:
            found, refs, _capacity = residency.residency(s, pins)
        finally:
            s.close()
        resident[name] = {label: {'resident': found.get(pid), 'refcounted': pid in refs}
            for label, pid in (('unit', unit), ('mission', mission))}
    if not all(resident[n]['mission']['resident'] is True for n in MISSION):
        raise ValueError('the mission package is not resident in every mission snapshot: %r' % resident)
    if any(resident[n]['mission']['resident'] for n in SHIP):
        raise ValueError('the mission package is resident aboard the ship: %r' % resident)
    if any(resident[n]['mission']['refcounted'] for n in SNAPSHOTS):
        raise ValueError('the mission package is refcounted: %r' % resident)
    bundles = residency.bundle_database()['packages']
    return {
        'unit': {'id': hexid(unit), 'name': spec['unitPackage'], 'inBundleDatabase': unit in bundles,
            'role': 'the round\'s own resources (its unit ships only here): loaded through the asset loader by the '
                'definition (asset key ' + spec['assetKey'] + ')'},
        'mission': {'id': hexid(mission), 'name': names.get(mission), 'inBundleDatabase': mission in bundles,
            'role': 'explosion 325\'s effect and bomblet 78\'s unit ship only here: loaded with the mission level '
                '(not refcounted), never requested by the Runtime; checked resident before the write'},
        'resources': rows,
        'residency': resident,
        'residencyRule': 'core/assets state(): the engine resource manager\'s package list, every part loaded (the '
            'list research_package_residency reads); the RefcountedPackageSystem map is not consulted, so a package '
            'loaded with the level is found as resident',
    }


# ------------------------------------------------------------------------------------------------- weapon side
def weapon_side(t, labels: dict, spec: dict, hosts: list[str]) -> dict:
    pw, wd = t.component('ProjectileWeaponComponentData'), t.component('WeaponDataComponentData')
    lp = t.component(LOADOUT_PACKAGE[0])

    def record(component, key):
        return component.raw(component.record_of(labels[key]))
    weapon = record(pw, spec['weapon'])
    other = record(pw, spec['compareWith'])
    differs = [o for o in range(0, len(weapon), 4) if weapon[o:o + 4] != other[o:o + 4]]
    if u32(weapon, 0) != spec['type'] or differs != spec['weaponDifferences']:
        raise ValueError('the %s ProjectileWeapon is not the reviewed round carrier: +0 %d, differs from the %s at %r'
            % (spec['weapon'], u32(weapon, 0), spec['compareWith'], [hex(o) for o in differs]))
    package = struct.unpack_from('<Q', record(lp, spec['weapon']), LOADOUT_PACKAGE[1])[0]
    if package != hd2_game_data.murmur64(spec['unitPackage'].encode()):
        raise ValueError('the %s\'s own loadout package is %s, not %s' % (spec['weapon'], hexid(package),
            spec['unitPackage']))
    host_keys = {'EAT-700 Expendable Napalm': 'EAT-700', 'EAT-411 Leveller': 'EAT-411'}
    facts = {'networkedFire': {}, 'selector': {}}
    for key in [spec['weapon']] + [host_keys[h] for h in hosts] + ['EAT-17']:
        facts['networkedFire'][key] = record(pw, key)[0x94]
        facts['selector'][key] = u32(record(wd, key), 0xB8)
    if any(v != 1 for v in facts['networkedFire'].values()):
        raise ValueError('a weapon lacks the networked fire flag: %r' % facts)
    if any(facts['selector'][host_keys[h]] for h in hosts) or facts['selector']['EAT-17']:
        raise ValueError('a clone host has an ammunition selector: %r' % facts)
    return {'weapon': hexid(labels[spec['weapon']]), 'projType': u32(weapon, 0),
        'differsFrom' + spec['compareWith'].replace('-', ''): ['+0x%X' % o for o in differs],
        'loadoutPackage': hexid(package), 'networkedFire': facts['networkedFire'], 'selector': facts['selector'],
        'meaning': 'the airburst is the round\'s own (rows and code above): the weapon has no fuse, range or lock '
            'member; PW +0x94 = 1 on the hosts as on the RL-77 (SpawnProjectile assigns the networked projectile id '
            'as for the RL-77); the hosts have no selector (WeaponData +0xB8 = 0), so only this round is fired'}


# ------------------------------------------------------------------------------------------------- main
def prove_pins(image) -> list[dict]:
    out = []
    for rva, asm, role in PINS:
        pin = image.pin(rva, role, asm)
        if pin.get('ripTarget') is not None:
            raise ValueError('pin %x is rip-relative: not a stable round pin' % rva)
        out.append(pin)
    return out


def round_overrides(t, image, labels: dict, hosts: list[str]) -> dict:
    """research/carrier-weapon-clone `roundOverrides`: {donor: {round name: the reviewed round}}."""
    pins = prove_pins(image)
    relocation = {name: base.verify_pins_live(name, pins, []) for name in SNAPSHOTS}
    if any(relocation.values()):
        raise ValueError('a round pin differs in a snapshot: %r' % relocation)
    out = {}
    for donor, rounds in ROUNDS.items():
        out[donor] = {}
        for name, spec in rounds.items():
            rows, digests = reviewed_rows(spec['type'])
            semantics = semantics_of(rows, spec['type'])
            if semantics != SEMANTICS[name]:
                raise ValueError('%s: the chain no longer decodes to the reviewed semantics: %r' % (name, semantics))
            resources = resources_of(rows)
            out[donor][name] = {
                'name': name, 'type': spec['type'], 'assetKey': spec['assetKey'],
                'hosts': hosts,
                'rows': rows, 'rowDigests': digests,
                'semantics': semantics, 'summary': SUMMARY[name],
                'weaponSide': weapon_side(t, labels, spec, hosts),
                'packages': packages_report(spec, resources),
                'pins': [{'rva': p['rva'], 'hex': p['bytes'], 'asm': p['asm'], 'label': p['role']} for p in pins],
                'pinnedBytesMismatchPerSnapshot': relocation,
                'write': {'component': 'ProjectileWeaponComponentData', 'offset': 0, 'width': 4,
                    'value': struct.pack('<I', spec['type']).hex(),
                    'levels': 'every level: at full it replaces the donor\'s ProjType value; at presentation and model '
                        'it is one more write from the carrier\'s native ProjType'},
                'refused': ['modify.impact_explosion with the round (row 312 has an expiry explosion: '
                    'projectile_impact refuses EXPIRY_EXPLOSION)', 'modify.projectile with the round',
                    'a raw type number or an unreviewed round'],
                'unproven': ['live: the burst, the bomblets and their sound from an EAT clone (offline only)',
                    'what the overlap filter 0xAB96E9D8 matches (vanilla RL-77 behaviour)',
                    'the explosion and trail audio events\' package (no Wwise event id match)',
                    'the mission package in mission types other than the retained one (checked at apply time)',
                    'join in progress (as for the clone)'],
            }
    return out
