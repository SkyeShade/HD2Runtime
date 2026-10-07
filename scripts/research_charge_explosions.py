"""Charge-level shots and overcharge explosions of the PLAS-45 Epoch and the RS-422 Railgun (research only).

Read-only. Nothing here writes game memory, runs in game, or edits the public API. Inputs: the pinned datalibrary
(scan.tables, scan.settings), the game.dll image of a retained snapshot (scan.xref), the retained mission snapshots
(live settings rows), research/railgun-charge-F5FEE03DCFDB.json (the WeaponChargeComponent records), the support
authoring catalog (component identities), research/weapon-fire-modes-F5FEE03DCFDB.json (reachable fire modes) and the
wiki import data/wiki_support_weapons.json (independent published values).

Proven on build F5FEE03DCFDB (pins, rows, census and comparisons in the JSON):

1. Which projectile a charged shot fires. The fire helper (0x73D8C0) picks the projectile type by the charge at
   release c: the state-0 type (WeaponCharge +4) when t0 <= c < t1, the state-2 type (+52) when c >= t2 (and t2 > t1),
   else the state-1 type (+28). It passes the type to the weapon fire (0x741A00 -> 0x741DF0 -> 0x6128B0); a non-zero
   type replaces the weapon's own projectile (a zero type falls back to 0x7456D0, the weapon's own one); the chosen
   type indexes the projectile settings table (game+0x37C7670) for SpawnProjectile (0x616612). The Epoch record names
   165 / 193 / 193, so a release between 1.0 s and 2.5 s fires row 165 (the wiki "PLAS-45 P") and every later release
   fires row 193 (the wiki "P3"). The Railgun names 0 / 0 / 0: every shot is its own projectile 186.
2. Which explosions they release. Row 165 names explosion 227 at impact (+144) and expiry (+156) (the wiki
   "PLAS-45 P IE"); row 193 names 407 at both (the wiki "P3 IE"). SpawnProjectile copies those types into the
   projectile when it is fired (research/projectile-rows: COPIED_AT_SPAWN).
3. The overcharge explosion. The overcharge failure (0x73DC60) requests WeaponCharge +200 at the weapon (0x13C0A80):
   the Epoch's 321 (the wiki "PLAS-45 EPOCH Overcharge E"), the Railgun's 326 ("RS-422 RAILGUN Overcharge E"). It
   spawns where the weapon is, in the wielder's hands, so it damages the wielder. The Epoch reaches it after 3.25 s in
   the overcharged state (the hold limit +204/+208; it never fires automatically, +185 = 0); the Railgun in Unsafe mode
   at 3 s, right after its shot (+185 = 1).
4. Read timing. The explosion queue drain resolves the row by type from the live explosion table (0x13C0DC0) and
   reads its radii (+16/+20/+24) and DamageInfo type (+4, looked up in the live damage table at 0x13C2B2B) when it
   processes the explosion: an explosion row or its damage row edit applies to the next explosion, also one released
   by a projectile already in flight. A projectile row's own members are copied into the projectile when it is fired:
   such an edit applies to shots fired afterwards.
5. Shared ownership (typed census of every component, entity delta and settings row): rows 165 and 193 and their
   damage rows 58 / 59, and explosions 227 / 407 and damage 60, have only the Epoch as consumer. Explosion 407 and the
   overcharge explosion 321 name the SAME damage row 61. Explosion 321 is also the 40-K Meltagun's +200 (unreachable:
   it is never in fire mode 6). Explosion 326 is also the PLAS-39 Accelerator Rifle's +200 (unreachable: always fire
   mode 2); its damage row 352 is also explosion 269's, the overcharge explosion of seven other WeaponCharge records.
   No component, delta or settings row references 165, 193, 227, 407 or 321 otherwise. Code-literal explosion types
   (like the Hellbombs') are not visible to a data census.

  py scripts/research_charge_explosions.py          # write research/charge-explosions-F5FEE03DCFDB.json + docs md
  py scripts/research_charge_explosions.py --check  # fail if the committed outputs are stale

Requires capstone, the pinned datalibrary and the retained snapshots.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
from scan import tables  # noqa: E402
from scan.settings import SettingsView  # noqa: E402
from reference_format import dl_hash  # noqa: E402

OUTPUT = ROOT / 'research/charge-explosions-F5FEE03DCFDB.json'
MARKDOWN = ROOT / 'research/docs/charge-explosions-F5FEE03DCFDB.md'
CHARGE = ROOT / 'research/railgun-charge-F5FEE03DCFDB.json'
FIRE_MODES = ROOT / 'research/weapon-fire-modes-F5FEE03DCFDB.json'
CATALOG = ROOT / 'schemas/support_weapon_authoring_catalog.json'
WIKI = ROOT / 'data/wiki_support_weapons.json'
SNAPSHOTS = ['F5FEE03DCFDB-20260929T172647Z-mission-host.hd2snap',
    'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap',
    'F5FEE03DCFDB-20260929T173206Z-mission-host-after-reinforce.hd2snap',
    'F5FEE03DCFDB-20260926T222226Z.hd2snap']
# Live settings tables (pointer per native type): research/projectile-rows, docs/events.md, research/custom-payloads.
LIVE_TABLES = {'projectile': (0x37C7670, 272), 'explosion': (0x37CC920, 152), 'damage': (0x37C60C0, 76)}
# The explosion row holds a relocated 64-bit pointer at +40 (research/custom-payloads masks the same words).
RELOCATED = {'explosion': (40, 44)}
UNSAFE_MODE = 6
PROJECTILE, EXPLOSION, DAMAGE = 'ProjectileType', 'ExplosionType', 'DamageInfoType'
# The charge-level selectors (WeaponChargeComponent ChargeStateSetting[3], 24 bytes each) and the overcharge explosion.
LEVELS = (('partial', 0, 4, 't0 <= c < t1'), ('full', 1, 28, 't1 <= c < t2'), ('overcharged', 2, 52, 'c >= t2'))
OVERCHARGE_EXPLOSION = 200
IMPACT, EXPIRY, DIRECT = 144, 156, 60

# Native code pins (rva, text the decoded instruction must contain, role, group). A changed game.dll fails loudly.
PINS = [
    (0x73DB24, 'movss xmm1, dword ptr [rdi]', 'fire helper: t0 (charge_time[0], +0) ...', 'selection'),
    (0x73DB28, 'movss xmm0, dword ptr [rdi + 0x18]', '... t1 (+24) ...', 'selection'),
    (0x73DB30, 'mov r8d, dword ptr [rdi + 0x1c]', '... the state-1 projectile (+28) is the default ...', 'selection'),
    (0x73DB3D, 'movss xmm2, dword ptr [r14 + rbp*8 + 8]', '... c, the charge at release (state +0x08) ...', 'selection'),
    (0x73DB44, 'comiss xmm2, xmm1', '... c >= t0 ...', 'selection'),
    (0x73DB49, 'comiss xmm0, xmm2', '... and t1 > c ...', 'selection'),
    (0x73DB4E, 'mov r8d, dword ptr [rdi + 4]', '... select the state-0 projectile (+4)', 'selection'),
    (0x73DB5B, 'movss xmm1, dword ptr [rdi + 0x30]', 'otherwise t2 (+48) ...', 'selection'),
    (0x73DB60, 'comiss xmm1, xmm0', '... when t2 > t1 ...', 'selection'),
    (0x73DB6C, 'comiss xmm0, xmm1', '... and c >= t2 ...', 'selection'),
    (0x73DB71, 'mov r8d, dword ptr [rdi + 0x34]', '... select the state-2 projectile (+52)', 'selection'),
    (0x73DB84, 'call 0x741a00', 'the shot: weapon fire with the selected projectile type (third argument)', 'chain'),
    (0x741A05, 'mov dword ptr [rsp + 0x18], r8d', 'weapon fire keeps the selected projectile type ...', 'chain'),
    (0x741BF6, 'mov esi, dword ptr [rsp + 0xf0]', '... reloads it ...', 'chain'),
    (0x741CEB, 'mov dword ptr [rsp + 0x28], esi', '... and passes it on (sixth argument) ...', 'chain'),
    (0x741D01, 'call 0x741df0', '... to the projectile weapon fire wrapper ...', 'chain'),
    (0x7420A9, 'mov eax, dword ptr [rsp + 0xd8]', '... which forwards it ...', 'chain'),
    (0x7420BF, 'call 0x6128b0', '... to the projectile fire', 'chain'),
    (0x61405B, 'mov eax, dword ptr [rbp + 0x518]', 'projectile fire: the selected projectile type ...', 'chain'),
    (0x614061, 'test eax, eax', '... replaces the weapon\'s own projectile when non-zero ...', 'chain'),
    (0x61406C, 'call 0x7456d0', '... (zero: the weapon\'s own projectile type)', 'chain'),
    (0x6143F4, 'mov r8d, dword ptr [rbp - 0x68]', 'the chosen type ...', 'chain'),
    (0x61443B, 'call 0x615940', '... goes to the projectile spawn path ...', 'chain'),
    (0x615994, 'mov r12d, r8d', '... (kept in r12d) ...', 'chain'),
    (0x615B2C, 'cmovne r12d, eax', '... replaced only by an active weapon-function projectile (+576) ...', 'chain'),
    (0x616523, 'lea rcx, [rip', '... the projectile settings table ...', 'chain'),
    (0x61652A, 'mov rcx, qword ptr [rcx + rax*8]', '... row of that type ...', 'chain'),
    (0x616612, 'call 0x13a9830', '... spawned (SpawnProjectile)', 'chain'),
    (0x73DF54, 'mov r8d, dword ptr [r14 + 0xc8]', 'overcharge failure: the explosion type (+200) ...', 'failure'),
    (0x73DD9F, 'call 0xfdc310', 'overcharge failure: the weapon entity is removed ...', 'failure'),
    (0x73DFB4, 'call 0x13c0a80', '... and the explosion is requested at the weapon (RequestExplosion)', 'failure'),
    (0x13C0DC0, 'mov r14, qword ptr [rcx + rax*8 + 0x37cc920]', 'explosion drain: the row by type, from the live table',
        'drain'),
    (0x13C0E10, 'mulss xmm2, dword ptr [r14 + 0x10]', 'inner radius (+16) read when the explosion is processed',
        'drain'),
    (0x13C0E0A, 'mulss xmm8, dword ptr [r14 + 0x14]', 'outer radius (+20)', 'drain'),
    (0x13C0E20, 'maxss xmm1, dword ptr [r14 + 0x18]', 'shockwave radius (+24)', 'drain'),
    (0x13C2AF8, 'mov eax, dword ptr [r14 + 4]', 'the DamageInfo type (+4) ...', 'drain'),
    (0x13C2B2B, 'mov rax, qword ptr [r12 + rax*8 + 0x37c60c0]', '... looked up in the live damage table', 'drain'),
]
RIP_TARGETS = {0x616523: 0x37C7670}


def u32(raw, at):
    return struct.unpack_from('<I', raw, at)[0]


def f32(raw, at):
    return round(struct.unpack_from('<f', raw, at)[0], 6)


def exact_f32(raw, at):
    return struct.unpack_from('<f', raw, at)[0]


def check_pins(image, pins):
    out = []
    for rva, needle, role, group in pins:
        entry = image.pin(rva, role)
        if needle not in entry['asm']:
            raise ValueError(f'pin {rva:#x} changed: {entry["asm"]!r} does not contain {needle!r}')
        expected = RIP_TARGETS.get(rva)
        if expected is not None and entry.get('ripTarget') != expected:
            raise ValueError(f'pin {rva:#x} references {entry.get("ripTarget")} not {expected:#x}')
        entry['group'] = group
        out.append(entry)
    return out


def settings_rows(sv):
    """kind -> native type -> {group, row, settingsType, bytes} for every group of every settings file."""
    result = {}
    for kind in sv.kinds():
        for group, table in sv.table(kind).groups.items():
            for row, native_type, raw in table.rows:
                result.setdefault(kind, {}).setdefault(native_type, []).append(
                    {'group': group, 'row': row, 'settingsType': '0x%08X' % table.settings_type, 'bytes': raw})
    return result


def single(rows, kind, native_type):
    found = rows[kind].get(native_type) or []
    if len(found) != 1:
        raise ValueError(f'{kind} type {native_type} has {len(found)} rows')
    return found[0]


def identity(entry, native_type):
    return {'group': entry['group'], 'row': entry['row'], 'recordType': native_type,
        'settingsType': entry['settingsType']}


def damage_values(raw):
    return {'standard_damage': struct.unpack_from('<i', raw, 4)[0], 'durable_damage': struct.unpack_from('<i', raw, 8)[0],
        'ap_direct': u32(raw, 12), 'ap_slight': u32(raw, 16), 'ap_large': u32(raw, 20), 'ap_extreme': u32(raw, 24),
        'demolition': u32(raw, 28), 'stagger': u32(raw, 32), 'push_force': u32(raw, 36),
        'statuses': [u32(raw, 44 + 8 * i) for i in range(4) if u32(raw, 44 + 8 * i)]}


def census(t, sv, wanted):
    """Every typed data reference to the wanted native types: component members (through nested structs and inline
    arrays) with their owners, entity deltas that patch such a member, and settings-row members (not the row key)."""
    hashes = {dl_hash(name): name for name in wanted}
    refs = {(name, value): [] for name, values in wanted.items() for value in values}
    from research_railgun_charge import identities
    names = identities()

    def owner_label(resource):
        known = names.get(resource)
        return {'resource': '0x%016X' % resource, 'name': known['name'] if known else None,
            'kind': known['kind'] if known else None, 'path': t.name(resource)}

    members_by_component = {}
    for component in t.components():
        try:
            members = component.members()
        except (KeyError, ValueError):
            continue
        typed = [m for m in members if m.type_hash in hashes]
        if not typed:
            continue
        members_by_component[component.name] = typed
        owners = component.owner_map()
        for record in range(component.count):
            raw = component.raw(record)
            for member in typed:
                value = tables.decode(member, raw)
                for item in value if isinstance(value, list) else [value]:
                    key = (hashes[member.type_hash], item)
                    if key in refs:
                        refs[key].append({'kind': 'component', 'component': component.name, 'member': member.path,
                            'offset': member.offset, 'record': record,
                            'owners': [owner_label(o) for o in owners.get(record, [])]})
    # Entity deltas (customization items) that patch one of those members.
    from research_magazine_attachments import DATALIB, entity_deltas
    t.entity_rows()
    by_index = {index: type_hash for index, type_hash in t._index_type.items()}
    deltas, _ = entity_deltas((DATALIB / 'generated_entity_deltas.dl_bin').read_bytes())
    delta_entries = 0
    for resource, entry in deltas.items():
        for item in entry['entries']:
            type_hash = by_index.get(item['component'])
            name = t.type_name(type_hash) if type_hash is not None else None
            for member in members_by_component.get(name, []):
                if item['offset'] <= member.offset and member.offset + member.size <= item['offset'] + item['size']:
                    delta_entries += 1
                    value = u32(item['bytes'], member.offset - item['offset'])
                    key = (hashes[member.type_hash], value)
                    if key in refs:
                        refs[key].append({'kind': 'entity_delta', 'component': name, 'member': member.path,
                            'item': t.name(resource) or '0x%016X' % resource})
    # Settings rows: every typed member except the row key.
    for kind in sv.kinds():
        for group, table in sv.table(kind).groups.items():
            typed = [m for m in t.flatten(table.layout.type_hash) if m.type_hash in hashes and m.offset != 0]
            for row, native_type, raw in table.rows:
                for member in typed:
                    key = (hashes[member.type_hash], tables.decode(member, raw))
                    if key in refs:
                        refs[key].append({'kind': 'settings', 'settings': kind, 'group': group, 'row': row,
                            'rowType': native_type, 'member': member.offset})
    scope = {'componentTablesWithTypedMembers': sorted(members_by_component),
        'entityDeltaEntriesOnTypedMembers': delta_entries,
        'settingsKinds': sv.kinds(),
        'limits': ['A type requested by a code literal (for example the Hellbomb explosions 242 and 125, '
            'docs/events.md) is not visible to a data census.']}
    return {f'{name}:{value}': items for (name, value), items in sorted(refs.items())}, scope


def live_rows(rows, wanted_rows):
    import research_event_state as base
    out = []
    for name in SNAPSHOTS:
        path = build_profile.snapshot_directory() / name
        if not path.is_file():
            out.append({'snapshot': name, 'status': 'absent'})
            continue
        mem = base.Mem(name)
        try:
            entry = {'snapshot': name, 'status': 'read', 'rows': {}}
            for kind, native_type in wanted_rows:
                table, stride = LIVE_TABLES[kind]
                pointer = mem.ptr(mem.game + table + 8 * native_type)
                live = pointer and mem.read(pointer, stride)
                reference = single(rows, kind, native_type)['bytes']
                masked = RELOCATED.get(kind, ())
                differing = [at for at in range(0, stride, 4) if live and live[at:at + 4] != reference[at:at + 4]]
                entry['rows'][f'{kind}:{native_type}'] = {'readable': bool(live),
                    'equalsDatalibrary': bool(live) and all(at in masked for at in differing),
                    'differingWords': differing, 'maskedRelocatedWords': list(masked)}
            out.append(entry)
        finally:
            mem.close()
    return out


def wiki_branches():
    data = json.loads(WIKI.read_text(encoding='utf-8'))
    out = {}
    for weapon in data['weapons']:
        if weapon['name'] in ('PLAS-45 Epoch', 'RS-422 Railgun'):
            out[weapon['name']] = {'revision': weapon.get('wikiRevisionId'),
                'attacks': {attack['name']: attack for attack in weapon['attacks']}}
    return out


def value_of(item):
    return item.get('value') if isinstance(item, dict) else item


def compare_projectile(branch, projectile, damage):
    p = branch.get('projectile') or {}
    d = branch.get('damage') or {}
    pen = branch.get('penetration') or {}
    sfx = branch.get('specialEffects') or {}
    extra = branch.get('normalizedExtraFields') or {}
    published = {'projectile_velocity': value_of(p.get('initialVelocityMetersPerSecond')),
        'projectile_mass': value_of(p.get('massGrams')), 'drag': value_of(p.get('dragFactor')),
        'gravity': value_of(p.get('gravityFactor')), 'penetration_slowdown': value_of(p.get('penetrationSlowdown')),
        'lifetime': float(str(extra.get('Projectile.Lifetime', '')).split()[0]) if extra.get('Projectile.Lifetime')
            else None,
        'standard_damage': value_of(d.get('standard')), 'durable_damage': value_of(d.get('durable')),
        'ap_direct': value_of(pen.get('direct')), 'ap_slight': value_of(pen.get('slightAngle')),
        'ap_large': value_of(pen.get('largeAngle')), 'ap_extreme': value_of(pen.get('extremeAngle')),
        'demolition': value_of(sfx.get('demolitionForce')), 'stagger': value_of(sfx.get('staggerForce')),
        'push_force': value_of(sfx.get('pushForce'))}
    native = dict(projectile, **{k: v for k, v in damage.items() if k != 'statuses'})
    return compared(published, native)


def compare_explosion(branch, explosion, damage):
    d = branch.get('damage') or {}
    pen = branch.get('penetration') or {}
    sfx = branch.get('specialEffects') or {}
    aoe = branch.get('areaOfEffect') or {}
    published = {'explosion_inner_radius': value_of(aoe.get('innerRadiusMeters')),
        'explosion_outer_radius': value_of(aoe.get('outerRadiusMeters')),
        'explosion_shockwave_radius': value_of(aoe.get('shockwaveRadiusMeters')),
        'standard_damage': value_of(d.get('standard')), 'durable_damage': value_of(d.get('durable')),
        'ap_direct': value_of(pen.get('direct')), 'ap_slight': value_of(pen.get('slightAngle')),
        'ap_large': value_of(pen.get('largeAngle')), 'demolition': value_of(sfx.get('demolitionForce')),
        'stagger': value_of(sfx.get('staggerForce')), 'push_force': value_of(sfx.get('pushForce'))}
    native = dict(explosion, **{k: v for k, v in damage.items() if k != 'statuses'})
    return compared(published, native)


def compared(published, native):
    fields = {key: {'native': native.get(key), 'published': value,
        'exact': value is not None and native.get(key) is not None and abs(native[key] - value) <= 1e-4}
        for key, value in published.items() if value is not None}
    return {'fields': fields, 'matchedFields': sorted(k for k, v in fields.items() if v['exact']),
        'mismatchedFields': sorted(k for k, v in fields.items() if not v['exact']),
        'allExact': all(v['exact'] for v in fields.values())}


def reachable_modes(mode_row):
    slots = [value for value in mode_row['slots'] if value]
    selector = mode_row['selector']
    bound = 'Firemode' in (selector.get('left'), selector.get('right'))
    return sorted(set(slots) if bound else set(slots[:1]))


def build() -> dict:
    t = tables.pinned()
    sv = SettingsView(t)
    rows = settings_rows(sv)
    charge = json.loads(CHARGE.read_text(encoding='utf-8'))
    modes = {item['weapon']: item for item in json.loads(FIRE_MODES.read_text(encoding='utf-8'))['weapons']}
    catalog = json.loads(CATALOG.read_text(encoding='utf-8'))
    wiki = wiki_branches()
    component = t.component('WeaponChargeComponentData')
    owners = component.owner_map()
    matrix = charge['matrix']

    # The charge records and what each level and the overcharge failure select.
    records = {}
    for item in charge['records']:
        label = item['label']
        times = [matrix[f'0[{i}].0'][label] for i in range(3)]
        mode_row = modes.get(label)
        reachable = reachable_modes(mode_row) if mode_row else None
        records[label] = {'record': item['record'], 'owners': item['owners'],
            'identityKind': (item['identity'][0] or {}).get('kind') if item['identity'] else None,
            'chargeTimes': times,
            'levelProjectiles': {level: matrix[f'0[{state}].4'][label] for level, state, _, _ in LEVELS},
            'overchargeExplosion': matrix['200'][label],
            'explodeWhenOvercharged': matrix['185'][label],
            'overchargeLimit': {'state': matrix['204.0'][label], 'seconds': matrix['204.4'][label]},
            'fireModes': {'slots': mode_row['slots'], 'selector': mode_row['selector'],
                'reachable': reachable} if mode_row else None,
            'overchargeReachable': (UNSAFE_MODE in reachable) if reachable is not None else None}
        if records[label]['record'] != item['record'] or sorted('0x%016X' % o for o in owners.get(item['record'], [])) \
                != sorted(item['owners']):
            raise ValueError(label + ': charge record ownership changed')

    def projectile_view(native_type):
        entry = single(rows, 'projectile', native_type)
        raw = entry['bytes']
        return {'identity': identity(entry, native_type),
            'values': {'projectile_velocity': f32(raw, 32), 'projectile_mass': f32(raw, 36), 'drag': f32(raw, 40),
                'gravity': f32(raw, 44), 'pellet_count': u32(raw, 28), 'lifetime': f32(raw, 52),
                'penetration_slowdown': f32(raw, 64)},
            'exact': {'lifetime': exact_f32(raw, 52), 'penetration_slowdown': exact_f32(raw, 64),
                'drag': exact_f32(raw, 40)},
            'directDamage': u32(raw, DIRECT), 'impactExplosion': u32(raw, IMPACT), 'expiryExplosion': u32(raw, EXPIRY)}

    def damage_view(native_type):
        entry = single(rows, 'damage', native_type)
        return {'identity': identity(entry, native_type), 'values': damage_values(entry['bytes'])}

    def explosion_view(native_type):
        entry = single(rows, 'explosion', native_type)
        raw = entry['bytes']
        return {'identity': identity(entry, native_type),
            'values': {'explosion_inner_radius': f32(raw, 16), 'explosion_outer_radius': f32(raw, 20),
                'explosion_shockwave_radius': f32(raw, 24)},
            'exact': {'explosion_inner_radius': exact_f32(raw, 16)},
            'damage': u32(raw, 4), 'submunition': u32(raw, 84), 'arc': u32(raw, 120), 'volumeTemplate': u32(raw, 100)}

    epoch = records['PLAS-45 Epoch']
    rail = records['RS-422 Railgun']
    levels = epoch['levelProjectiles']
    if (levels['partial'], levels['full'], levels['overcharged']) != (165, 193, 193):
        raise ValueError('PLAS-45 Epoch charge-level projectiles changed')
    if set(rail['levelProjectiles'].values()) != {0}:
        raise ValueError('RS-422 Railgun charge-level projectiles changed')
    if (epoch['overchargeExplosion'], rail['overchargeExplosion']) != (321, 326):
        raise ValueError('overcharge explosions changed')

    projectiles = {native_type: projectile_view(native_type) for native_type in (165, 193, 186)}
    explosion_types = sorted({projectiles[165]['impactExplosion'], projectiles[165]['expiryExplosion'],
        projectiles[193]['impactExplosion'], projectiles[193]['expiryExplosion'], 321, 326, 269})
    explosions = {native_type: explosion_view(native_type) for native_type in explosion_types}
    damage_types = sorted({projectiles[165]['directDamage'], projectiles[193]['directDamage'],
        projectiles[186]['directDamage']} | {item['damage'] for item in explosions.values()})
    damages = {native_type: damage_view(native_type) for native_type in damage_types}
    for native_type in (165, 193):
        view = projectiles[native_type]
        if view['impactExplosion'] != view['expiryExplosion']:
            raise ValueError(f'projectile {native_type}: impact and expiry explosions differ')
        if explosions[view['impactExplosion']]['submunition'] or explosions[view['impactExplosion']]['arc']:
            raise ValueError(f'projectile {native_type}: its explosion releases a submunition or an arc')
    if explosions[407]['damage'] != explosions[321]['damage']:
        raise ValueError('the full-charge impact and overcharge explosions no longer share their damage row')

    wanted = {PROJECTILE: {165, 193}, EXPLOSION: set(explosion_types), DAMAGE: set(damage_types)}
    refs, scope = census(t, sv, wanted)

    # Branch identities: the wiki branch values against the rows the structure names.
    published = {'PLAS-45 Epoch': {}, 'RS-422 Railgun': {}}
    attacks = wiki['PLAS-45 Epoch']['attacks']
    for name, native_type in (('PLAS-45 P', 165), ('P3', 193)):
        view = projectiles[native_type]
        published['PLAS-45 Epoch'][name] = dict(compare_projectile(attacks[name], view['values'],
            damages[view['directDamage']]['values']), row='projectile:%d' % native_type)
    for name, native_type in (('PLAS-45 P IE', projectiles[165]['impactExplosion']),
            ('P3 IE', projectiles[193]['impactExplosion']), ('PLAS-45 EPOCH Overcharge E', 321)):
        view = explosions[native_type]
        published['PLAS-45 Epoch'][name] = dict(compare_explosion(attacks[name], view['values'],
            damages[view['damage']]['values']), row='explosion:%d' % native_type)
    rail_attacks = wiki['RS-422 Railgun']['attacks']
    view = explosions[326]
    published['RS-422 Railgun']['RS-422 RAILGUN Overcharge E'] = dict(compare_explosion(
        rail_attacks['RS-422 RAILGUN Overcharge E'], view['values'], damages[view['damage']]['values']),
        row='explosion:326')
    max_charge = rail_attacks['Railgun Max Charge']
    base_damage = damages[projectiles[186]['directDamage']]['values']
    multiplier = matrix['72.12']['RS-422 Railgun']
    published['RS-422 Railgun']['Railgun Max Charge'] = {'row': None, 'explanation': (
        'Not a row: it is the RS-422 shot (projectile 186, %d / %d) at the overcharge damage multiplier %.1f '
        '(charge.damage_multiplier_overcharge), %d / %d published as %d / %d.' % (base_damage['standard_damage'],
        base_damage['durable_damage'], multiplier, base_damage['standard_damage'] * multiplier,
        base_damage['durable_damage'] * multiplier, value_of(max_charge['damage']['standard']),
        value_of(max_charge['damage']['durable']))),
        'exact': abs(base_damage['standard_damage'] * multiplier - value_of(max_charge['damage']['standard'])) < 1
            and abs(base_damage['durable_damage'] * multiplier - value_of(max_charge['damage']['durable'])) < 1}
    for weapon, branches in published.items():
        for name, item in branches.items():
            if item.get('row') and not item['allExact']:
                raise ValueError(f'{weapon} {name}: published values no longer match {item["row"]}')

    # The support catalog's component identities (the charge record each linkage re-proves).
    candidates = catalog['candidates']
    by_name = {weapon['name']: weapon for weapon in catalog['weapons']}

    def charge_identity(weapon_name):
        owner = candidates[by_name[weapon_name]['attackResource']]['ownership']['WeaponChargeComponentData']
        if owner['recordIndex'] != records[weapon_name]['record'] or not owner['uniqueOwner']:
            raise ValueError(weapon_name + ': charge record identity changed')
        return {'recordIndex': owner['recordIndex'], 'indexRow': owner['indexRow'], 'ownerCount': owner['ownerCount']}

    def consumers_of(name, value):
        return refs.get(f'{name}:{value}', [])

    def weapon_consumers(name, value):
        """Weapons whose own data names the type, with whether that path is reachable in vanilla."""
        out = []
        for item in consumers_of(name, value):
            if item['kind'] != 'component':
                continue
            for owner in item['owners'] or [{'name': None}]:
                label = owner.get('name') or ('unidentified WeaponCharge record %d' % item['record']
                    if item['component'] == 'WeaponChargeComponentData' else None)
                out.append({'kind': 'component', 'component': item['component'], 'member': item['offset'],
                    'record': item['record'], 'weapon': label, 'ownerKind': owner.get('kind')})
        return out

    def explosion_consumers(native_type):
        """Who requests the explosion: charge records (+200, with reachability) and projectile rows (+144/+156)."""
        out = []
        for item in consumers_of(EXPLOSION, native_type):
            if item['kind'] == 'component' and item['component'] == 'WeaponChargeComponentData' \
                    and item['offset'] == OVERCHARGE_EXPLOSION:
                label = next((name for name, record in records.items() if record['record'] == item['record']), None)
                record = records.get(label) or {}
                out.append({'kind': 'overcharge_failure', 'weapon': label, 'record': item['record'],
                    'identityKind': record.get('identityKind'), 'reachable': record.get('overchargeReachable'),
                    'reachableModes': (record.get('fireModes') or {}).get('reachable')})
            elif item['kind'] == 'settings' and item['settings'] == 'projectile':
                out.append({'kind': 'projectile_impact' if item['member'] == IMPACT else 'projectile_expiry',
                    'projectile': item['rowType']})
            else:
                out.append(dict(item))
        return out

    def damage_consumers(native_type):
        out = []
        for item in consumers_of(DAMAGE, native_type):
            if item['kind'] == 'settings':
                out.append({'kind': item['settings'] + '_damage', 'row': item['rowType']})
            else:
                out.append(dict(item))
        return out

    sharing = {
        'projectile:165': weapon_consumers(PROJECTILE, 165) + [{'kind': 'settings', **i} for i in
            consumers_of(PROJECTILE, 165) if i['kind'] != 'component'],
        'projectile:193': weapon_consumers(PROJECTILE, 193) + [{'kind': 'settings', **i} for i in
            consumers_of(PROJECTILE, 193) if i['kind'] != 'component'],
        **{f'explosion:{native_type}': explosion_consumers(native_type) for native_type in explosion_types},
        **{f'damage:{native_type}': damage_consumers(native_type) for native_type in damage_types}}
    # Expectations the generator relies on (fail loudly when a build changes them).
    expected_sharing = {
        'projectile:165': {('ProjectileWeaponComponentData', 0), ('WeaponChargeComponentData', 4)},
        'projectile:193': {('WeaponChargeComponentData', 28), ('WeaponChargeComponentData', 52)}}
    for key, expected in expected_sharing.items():
        found = {(item['component'], item['member']) for item in sharing[key] if item.get('component')}
        if found != expected or any(item.get('weapon') != 'PLAS-45 Epoch' for item in sharing[key]
                if item.get('component')) or any(item['kind'] != 'component' for item in sharing[key]):
            raise ValueError(key + ': consumers changed: ' + repr(sharing[key]))
    for native_type, projectile in ((227, 165), (407, 193)):
        if sorted(item['kind'] for item in sharing[f'explosion:{native_type}']) != \
                ['projectile_expiry', 'projectile_impact'] or \
                {item['projectile'] for item in sharing[f'explosion:{native_type}']} != {projectile}:
            raise ValueError(f'explosion {native_type}: consumers changed')
    for native_type, weapons in ((321, {'PLAS-45 Epoch', '40-K Meltagun'}), (326, {'RS-422 Railgun',
            'PLAS-39 Accelerator Rifle'})):
        found = {item.get('weapon') for item in sharing[f'explosion:{native_type}']}
        if found != weapons or any(item['kind'] != 'overcharge_failure' for item in sharing[f'explosion:{native_type}']):
            raise ValueError(f'explosion {native_type}: consumers changed: {found}')
    if sorted(item['row'] for item in sharing['damage:61']) != [321, 407]:
        raise ValueError('damage 61: consumers changed')

    reachable_epoch = records['PLAS-45 Epoch']['overchargeReachable']
    reachable_rail = records['RS-422 Railgun']['overchargeReachable']
    if not (reachable_epoch and reachable_rail) or records['40-K Meltagun']['overchargeReachable'] \
            or records['PLAS-39 Accelerator Rifle']['overchargeReachable']:
        raise ValueError('overcharge reachability changed')

    from scan import xref
    image = xref.CodeImage.from_snapshot('game.dll')
    pins = check_pins(image, PINS)
    live = live_rows(rows, [('projectile', 165), ('projectile', 193)]
        + [('explosion', native_type) for native_type in explosion_types]
        + [('damage', native_type) for native_type in damage_types])
    if any(not item['equalsDatalibrary'] for snap in live if snap['status'] == 'read' for item in snap['rows'].values()):
        raise ValueError('a live settings row differs from the datalibrary')

    t0, t1, t2 = epoch['chargeTimes']
    readings = {
        'explosionRow': ('Read when the explosion is processed: the queue drain looks the row up by its type in the live '
            'explosion table (0x13C0DC0) and reads the radii (+16/+20/+24, 0x13C0E0A..0x13C0E20) and the DamageInfo '
            'type (+4, 0x13C2AF8) then; nothing is copied into the weapon. A write applies to the next explosion, '
            'also one released by a projectile already in flight (it carries only the explosion type).'),
        'explosionDamageRow': ('Looked up by the explosion row\'s DamageInfo type in the live damage table when the '
            'explosion is processed (0x13C2B2B): a write applies to the next explosion.'),
        'projectileRow': ('Copied into the projectile when it is fired (research/projectile-rows: velocity, mass, '
            'drag, gravity, penetration slowdown, the direct-hit damage type and armour penetration, the impact and '
            'expiry explosion types are COPIED_AT_SPAWN): a write applies to shots fired after it; a projectile in '
            'flight keeps its copy.'),
        'projectileDamageRow': ('Its type and armour penetration are copied into the projectile when it is fired '
            '(research/projectile-rows +60); the damage values are read through that type. A write applies to shots '
            'fired after it.'),
        'chargeSelection': ('The fire helper reads the weapon\'s own WeaponCharge type record live for every shot '
            '(research/railgun-charge lifecycle): which row a release fires is decided at release.')}
    epoch_levels = {
        'partial': {'firedWhen': f'released at or after the minimum charge time ({t0:g} s) and before the full charge '
            f'time ({t1:g} s)', 'projectile': 165},
        'full': {'firedWhen': f'released at or after the full charge time ({t1:g} s) and before the overcharge time '
            f'({t2:.3g} s)', 'projectile': 193},
        'overcharged': {'firedWhen': f'released at or after the overcharge time ({t2:.3g} s), before the hold limit '
            f'destroys the weapon ({records["PLAS-45 Epoch"]["overchargeLimit"]["seconds"]:g} s overcharged)',
            'projectile': 193}}

    def attack(role, kind, level, view, damage, parent=None, phases=None, linkage=None, selectors=None,
            existing=False, branch=None, extra=None):
        item = {'role': role, 'kind': kind, 'chargeLevel': level, 'parentRole': parent, 'existing': existing,
            'catalogBranch': branch, 'linkage': linkage, 'selectorOffsets': selectors, 'phases': phases,
            'damage': damage}
        item.update(view)
        item.update(extra or {})
        return item

    epoch_attacks = [
        attack('primary', 'Projectile', 'partial', {'projectile': projectiles[165]}, damages[projectiles[165]
            ['directDamage']], linkage='charge_projectile', selectors=[4], existing=True, branch='PLAS-45 P'),
        attack('primary_impact', 'Explosion', 'partial', {'explosion': explosions[227]}, damages[explosions[227]
            ['damage']], parent='primary', phases=['impact', 'expiry'], linkage='charge_projectile_explosion',
            selectors=[4], existing=True, branch='PLAS-45 P IE'),
        attack('full_charge', 'Projectile', 'full', {'projectile': projectiles[193]}, damages[projectiles[193]
            ['directDamage']], linkage='charge_projectile', selectors=[28, 52], branch='P3'),
        attack('full_charge_impact', 'Explosion', 'full', {'explosion': explosions[407]}, damages[explosions[407]
            ['damage']], parent='full_charge', phases=['impact', 'expiry'], linkage='charge_projectile_explosion',
            selectors=[28, 52], branch='P3 IE'),
        attack('overcharge_explosion', 'Explosion', 'overcharge', {'explosion': explosions[321]}, damages[explosions[321]
            ['damage']], linkage='charge_overcharge_explosion', branch='PLAS-45 EPOCH Overcharge E',
            extra={'explosionOffset': OVERCHARGE_EXPLOSION}),
    ]
    rail_attacks_out = [
        attack('overcharge_explosion', 'Explosion', 'overcharge', {'explosion': explosions[326]}, damages[explosions[326]
            ['damage']], linkage='charge_overcharge_explosion', branch='RS-422 RAILGUN Overcharge E',
            extra={'explosionOffset': OVERCHARGE_EXPLOSION}),
    ]
    weapons = {
        'PLAS-45 Epoch': {'chargeRecord': dict(records['PLAS-45 Epoch'], identity=charge_identity('PLAS-45 Epoch')),
            'levels': epoch_levels, 'attacks': epoch_attacks,
            'overcharge': {'explosion': 321, 'trigger': ('The hold limit: overcharged (charge state 2, fire mode 6, '
                'always on the Epoch) for %g s, the weapon is destroyed and the explosion spawns at it without a shot '
                '(+185 = 0: reaching the overcharge time fires nothing by itself).'
                % records['PLAS-45 Epoch']['overchargeLimit']['seconds'])},
            'branches': {'PLAS-45 P': 'primary', 'PLAS-45 P IE': 'primary_impact', 'P3': 'full_charge',
                'P3 IE': 'full_charge_impact', 'PLAS-45 EPOCH Overcharge E': 'overcharge_explosion'}},
        'RS-422 Railgun': {'chargeRecord': dict(records['RS-422 Railgun'], identity=charge_identity('RS-422 Railgun')),
            'levels': {'all': {'firedWhen': 'every release (all three charge-level selectors are 0: the weapon\'s own '
                'projectile)', 'projectile': 186}},
            'attacks': rail_attacks_out,
            'overcharge': {'explosion': 326, 'trigger': ('Unsafe mode (fire mode 6): reaching the overcharge time '
                '(%g s) fires the shot, then destroys the weapon and spawns the explosion at it (+185 = 1).'
                % records['RS-422 Railgun']['chargeTimes'][2])},
            'branches': {'RS-422 P': 'primary', 'RS-422 RAILGUN Overcharge E': 'overcharge_explosion'}},
    }
    # Each new or re-described row: who else changes when it is written.
    shared = {
        'projectile:165': 'Only the PLAS-45 Epoch: its ProjectileWeapon +0 and its partial-charge selector (+4).',
        'projectile:193': 'Only the PLAS-45 Epoch: its full and overcharged selectors (+28, +52).',
        'damage:%d' % projectiles[165]['directDamage']: 'Only projectile 165 (the Epoch partial-charge shot).',
        'damage:%d' % projectiles[193]['directDamage']: 'Only projectile 193 (the Epoch full-charge shot).',
        'explosion:227': 'Only projectile 165, at impact and at expiry.',
        'damage:60': 'Only explosion 227.',
        'explosion:407': 'Only projectile 193, at impact and at expiry.',
        'explosion:321': ('The PLAS-45 Epoch overcharge failure and the 40-K Meltagun\'s WeaponCharge +200; the '
            'Meltagun never reaches its failure (always fire mode 1: its charge stops at the full time). Also any '
            'charge weapon whose charge.overcharge_explosion a mod sets to \'PLAS-45 Epoch\'.'),
        'damage:61': ('Explosion 407 (the Epoch full-charge impact and expiry explosion) AND explosion 321 (the '
            'Epoch overcharge explosion, also the Meltagun\'s): one write changes both.'),
        'explosion:326': ('The RS-422 Railgun overcharge failure and the PLAS-39 Accelerator Rifle\'s WeaponCharge '
            '+200; the Accelerator Rifle never reaches its failure (always fire mode 2). Also any charge weapon whose '
            'charge.overcharge_explosion a mod sets to \'RS-422 Railgun\'.'),
        'damage:352': ('Explosion 326 AND explosion 269, the overcharge explosion of seven other WeaponCharge records '
            '(PLAS-101 Purifier, PLAS-15 Loyalist, ARC-3 Arc Thrower, the Watcher weapon, two unidentified owners and '
            'one unowned record). The player weapons and the ARC-3 never reach their failure (no fire mode 6); the '
            'Watcher\'s fire mode is not reviewed.'),
    }
    for key in shared:
        if key not in sharing:
            raise ValueError(key + ': no census entry')
    return {'schemaVersion': 1, 'title': 'Charge-level shots and overcharge explosions (PLAS-45 Epoch, RS-422 Railgun)',
        'build': build_profile.BUILD_ID, 'generatedBy': 'scripts/research_charge_explosions.py',
        'inputs': {'entitiesSha256': build_profile.ENTITY_SHA256, 'typelibSha256': build_profile.TYPELIB_SHA256,
            'gameDll': image.describe(), 'chargeResearch': CHARGE.name, 'wiki': {'file': WIKI.name,
                'epochRevision': wiki['PLAS-45 Epoch']['revision'], 'railgunRevision': wiki['RS-422 Railgun']['revision']}},
        'safety': {'writes': 0, 'protectionChanges': 0, 'fixtureFallback': 'disabled'},
        'model': {
            'selection': ('Fire helper 0x73D8C0, with c the charge at release: state 0 (+4) when t0 <= c < t1; state 2 '
                '(+52) when t2 > t1 and c >= t2; otherwise state 1 (+28). A non-zero type replaces the weapon\'s own '
                'projectile (zero: the weapon\'s own, 0x7456D0) and indexes the projectile settings table for '
                'SpawnProjectile.'),
            'levelsTable': [{'level': level, 'chargeState': state, 'selectorOffset': offset, 'when': when}
                for level, state, offset, when in LEVELS],
            'overcharge': ('The overcharge failure (0x73DC60, authority only) removes the weapon and requests '
                'WeaponCharge +200 at its position plus 0.1 m per axis: the wielder stands at the centre of the '
                'blast and takes its damage. Triggered by +185 (fire mode 6, reaching charge_time[2]) or by the hold '
                'limit (+204 state, +208 seconds).'),
            'authority': ('Writes change this machine\'s copy of the type records; the charge update and the failure '
                'run where the weapon is simulated (its owner). What other machines see is not tested.')},
        'records': records, 'rows': {'projectile': {str(k): v for k, v in projectiles.items()},
            'explosion': {str(k): v for k, v in explosions.items()}, 'damage': {str(k): v for k, v in damages.items()}},
        'liveEquality': live, 'census': refs, 'censusScope': scope, 'sharing': sharing, 'sharingSummary': shared,
        'published': published, 'readTiming': readings, 'weapons': weapons,
        'code': {'pins': pins, 'pinGroups': sorted({pin['group'] for pin in pins})},
        'notPromoted': [
            {'item': 'charge-level selectors (WeaponCharge +4/+28/+52) and the overcharge explosion type (+200)',
                'reason': 'The selectors are attack-output references (docs/attack-outputs.md); +200 is already the '
                    'typed reference field charge.overcharge_explosion. This pass edits the CONTENTS of the rows they '
                    'select, never which row they select.'},
            {'item': 'Railgun Max Charge', 'reason': 'Not a row (see published): the overcharged RS-422 shot is its '
                'own projectile at charge.damage_multiplier_overcharge.'},
            {'item': 'explosion rows: members other than the radii and the DamageInfo fields',
                'reason': 'Rows 407 and 321 differ only in their type, a relocated pointer (+40) and the u32 at +64; '
                    'none of those is proven.'}],
        'liveTests': [
            {'id': 'harmless-overcharge', 'target': 'PLAS-45 Epoch', 'writes': {
                'explosion.overcharge_explosion.damage.standard_damage': 1,
                'explosion.overcharge_explosion.damage.durable_damage': 1,
                'explosion.overcharge_explosion.damage.push_force': 0},
                'expect': ('Hold past 3.25 s overcharged: the Epoch is destroyed and explodes, the wielder survives '
                    '(vanilla 800 damage kills). The damage row is shared: full-charge blasts also do 1 damage, so a '
                    'full-charge shot into a group kills only the target it hits directly.')},
            {'id': 'wide-harmless-overcharge', 'target': 'PLAS-45 Epoch', 'writes': {
                'explosion.overcharge_explosion.inner_radius': 15, 'explosion.overcharge_explosion.outer_radius': 18,
                'explosion.overcharge_explosion.shockwave_radius': 20},
                'expect': ('With harmless-overcharge: enemies up to about 18 m away flinch (stagger 35 kept) when the '
                    'Epoch self-destructs; vanilla 4 m.')},
            {'id': 'big-partial-blast', 'target': 'PLAS-45 Epoch', 'writes': {
                'explosion.primary_impact.inner_radius': 9.2, 'explosion.primary_impact.outer_radius': 12,
                'explosion.primary_impact.shockwave_radius': 16},
                'expect': ('Partial-charge shots (release between 1 s and 2.5 s) blast a 12 m area (vanilla 3 m); '
                    'full-charge shots keep 4 m.')},
            {'id': 'big-full-charge-blast', 'target': 'PLAS-45 Epoch', 'writes': {
                'explosion.full_charge_impact.inner_radius': 9, 'explosion.full_charge_impact.outer_radius': 12,
                'explosion.full_charge_impact.shockwave_radius': 15},
                'expect': ('Without harmless-overcharge: full-charge shots blast a 12 m area (vanilla 4 m); partial '
                    'shots keep 3 m.')},
            {'id': 'slow-full-charge', 'target': 'PLAS-45 Epoch', 'writes': {'projectile.full_charge.velocity': 60},
                'expect': 'Full-charge shots crawl at 60 m/s and drop steeply; partial-charge shots keep 250 m/s.'},
            {'id': 'railgun-gentle-overcharge', 'target': 'RS-422 Railgun', 'writes': {
                'explosion.overcharge_explosion.damage.standard_damage': 1,
                'explosion.overcharge_explosion.damage.durable_damage': 1,
                'explosion.overcharge_explosion.damage.push_force': 0},
                'expect': 'Unsafe mode, hold 3 s: the Railgun fires, is destroyed and explodes; the wielder survives.'}],
        'openQuestions': [
            'Gameplay effect of every row edit on the Epoch (not yet shown in game): charge-level selection, the '
            'overcharge explosion damaging the wielder.',
            'Whether other machines see a host write (writes change this machine\'s type records only).',
            'The Watcher weapon\'s fire modes (explosion 269 shares the Railgun overcharge damage row 352).',
            'The u32 at explosion +64 (differs between 407 and 321) and the relocated pointer at +40.']}


def markdown(doc: dict) -> str:
    lines = [f"# {doc['title']}", '',
        f"Build {doc['build']}. Generated by `{doc['generatedBy']}` (research only; nothing is written to the game). "
        f"Full evidence: `research/{OUTPUT.name}`.", '', '## How a charge shot picks its projectile', '',
        doc['model']['selection'], '', '| level | charge state | selector | when |', '| --- | --- | --- | --- |']
    lines += [f"| {item['level']} | {item['chargeState']} | +{item['selectorOffset']} | {item['when']} |"
        for item in doc['model']['levelsTable']]
    lines += ['', doc['model']['overcharge'], '', doc['model']['authority'], '', '## Weapons', '']
    for name, weapon in doc['weapons'].items():
        record = weapon['chargeRecord']
        lines += [f'### {name}', '', f"- Charge times (s): {record['chargeTimes']}; level projectiles "
            f"{record['levelProjectiles']}; overcharge explosion {record['overchargeExplosion']}; explode at "
            f"overcharge {record['explodeWhenOvercharged']}; hold limit {record['overchargeLimit']}; fire modes "
            f"{record['fireModes']['slots']} (reachable {record['fireModes']['reachable']}).",
            f"- Overcharge: {weapon['overcharge']['trigger']}"]
        for level, item in weapon['levels'].items():
            lines.append(f"- {level}: projectile {item['projectile']}, {item['firedWhen']}.")
        lines += ['', '| role | kind | charge level | row | linkage | catalog branch |', '| --- | --- | --- | --- | --- | --- |']
        for attack in weapon['attacks']:
            row = attack.get('projectile') or attack.get('explosion')
            ident = row['identity']
            lines.append(f"| {attack['role']} | {attack['kind']} | {attack['chargeLevel']} | {ident['recordType']} "
                f"(group {ident['group']} row {ident['row']}) | {attack['linkage']} | {attack['catalogBranch']} |")
        lines.append('')
    lines += ['## Rows', '', '| row | values | references |', '| --- | --- | --- |']
    for kind in ('projectile', 'explosion', 'damage'):
        for key, row in doc['rows'][kind].items():
            refs = {k: row[k] for k in ('directDamage', 'impactExplosion', 'expiryExplosion', 'damage') if k in row}
            lines.append(f"| {kind} {key} | {row['values']} | {refs} |")
    lines += ['', '## Published values (wiki)', '']
    for weapon, branches in doc['published'].items():
        for name, item in branches.items():
            if item.get('row'):
                lines.append(f"- {weapon} \"{name}\" = {item['row']}: all exact {item['allExact']} "
                    f"({len(item['matchedFields'])} fields).")
            else:
                lines.append(f"- {weapon} \"{name}\": {item['explanation']} Exact: {item['exact']}.")
    lines += ['', '## Shared ownership', '', 'Typed census: every component table with a typed member, every entity '
        'delta that patches one, and every settings row member (not the row key). '
        + ' '.join(doc['censusScope']['limits']), '']
    lines += [f'- `{key}`: {text}' for key, text in doc['sharingSummary'].items()]
    lines += ['', '## Read timing', '']
    lines += [f'- {key}: {text}' for key, text in doc['readTiming'].items()]
    lines += ['', '## Live rows', '']
    for snap in doc['liveEquality']:
        if snap['status'] != 'read':
            lines.append(f"- {snap['snapshot']}: {snap['status']}")
            continue
        equal = sum(item['equalsDatalibrary'] for item in snap['rows'].values())
        lines.append(f"- {snap['snapshot']}: {equal}/{len(snap['rows'])} rows equal the datalibrary (explosion rows "
            f"masked at their relocated pointer +40).")
    lines += ['', '## Native code pins', '', '| rva | instruction | role |', '| --- | --- | --- |']
    lines += [f"| 0x{pin['rva']:X} | `{pin['asm']}` | {pin['role']} |" for pin in doc['code']['pins']]
    lines += ['', '## Not promoted', '']
    lines += [f"- {item['item']}: {item['reason']}" for item in doc['notPromoted']]
    lines += ['', '## Live tests (strongly differentiated)', '']
    lines += [f"- **{item['id']}** ({item['target']}): {item['writes']} -> {item['expect']}" for item in doc['liveTests']]
    lines += ['', '## Open questions', '']
    lines += [f'- {item}' for item in doc['openQuestions']]
    return '\n'.join(lines) + '\n'


def default(value):
    if isinstance(value, set):
        return sorted(value)
    raise TypeError(type(value))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    doc = build()
    text = json.dumps(doc, indent=1, allow_nan=False, default=default) + '\n'
    md = markdown(doc)
    if args.check:
        stale = [str(p) for p, body in ((OUTPUT, text), (MARKDOWN, md))
            if not p.is_file() or p.read_text(encoding='utf-8') != body]
        if stale:
            print('stale:', ', '.join(stale))
            return 1
        print('up to date')
        return 0
    OUTPUT.write_text(text, encoding='utf-8', newline='\n')
    MARKDOWN.write_text(md, encoding='utf-8', newline='\n')
    print('wrote', OUTPUT.relative_to(ROOT), 'and', MARKDOWN.relative_to(ROOT))
    return 0


if __name__ == '__main__':
    sys.exit(main())
