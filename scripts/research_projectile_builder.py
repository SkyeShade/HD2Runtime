"""What a projectile builder can compose in this build, from the pinned datalibrary. Read-only.

A ProjectileSettings row (272 bytes, one per ProjectileType, indexed by type) is the whole projectile: flight
(velocity, mass, drag, gravity), visuals and audio (resource hashes), and three references that decide what it does:

* +60  DamageInfoType: the direct-hit damage row (damage, armor penetration, forces, up to four statuses);
* +144 ExplosionType:  the impact explosion (released when the projectile hits);
* +156 ExplosionType:  the expiry explosion (released when the projectile expires, for example a stuck spear);
* an explosion row in turn names its own DamageInfo (+4), a submunition projectile (+84), an arc (+120) and a
  lingering status volume (+100 template, +104 seconds).

The research answers, per composition class:

1. REFERENCE_COMPOSITION: re-point those references. Writing a row's reference member changes every consumer of
   that row; referencing another row's damage or explosion changes nothing of that row.
2. DERIVED_MUTATION: an independent row. The table has fixed rows; a row that no typed data member references is a
   spare row. A spare row that is byte-identical to an owned row except its references is a native spare twin: the
   same flight, visuals and audio (so the owner's package covers its assets), with an identity no other consumer
   uses. Copying a whole different base into a spare row is not offered (asset residency and code references are
   unproven).
3. CUSTOM_ROW: not possible. The game reads the settings table by type with no bound (game.dll, pinned in
   domains/event_natives.lua), the table has exactly one row per type, and the type is the network identity.

Every ProjectileType-typed member in the type library is scanned: entity components (through nested structs and
inline arrays), entity deltas that patch one, and explosion submunitions.

Output: research/projectile-builder-F5FEE03DCFDB.json.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import research_entity_authoring as entity_research  # noqa: E402
import research_magazine_attachments as attachments  # noqa: E402
from reference_format import dl_hash, groups  # noqa: E402

OUTPUT = ROOT / 'research/projectile-builder-F5FEE03DCFDB.json'
ATTACK_RESEARCH = ROOT / 'research/attack-outputs-F5FEE03DCFDB.json'
ACTIVE_RESEARCH = ROOT / 'research/active-projectile-sources-F5FEE03DCFDB.json'
DONOR_RESEARCH = ROOT / 'research/stun-field-donors-F5FEE03DCFDB.json'
STATUS_RESEARCH = ROOT / 'research/status-effects-F5FEE03DCFDB.json'
PROJECTILE_STRIDE, EXPLOSION_STRIDE, DAMAGE_STRIDE = 272, 152, 76
PROJECTILE_SETTINGS_TYPE, EXPLOSION_SETTINGS_TYPE = '0xBD4042C2', '0x2AEA2592'
REFERENCES = {'directDamage': 60, 'impactExplosion': 144, 'expiryExplosion': 156}
# Members a spare row may legitimately differ in from its twin: the type key, the mode label (+12) and icon
# (+16..+23, both authored presentation), and the three references.
TWIN_EXCLUDED = [(0, 4), (12, 24), (60, 64), (144, 148), (156, 160)]
UNKNOWN_ROW_MEMBERS = {148: 'f32 (name length 19) after the impact explosion: its meaning (a delay or a chance) is not '
    'proven', 152: 'f32 (name length 15) after it: not proven', 228: 'ProjectileStatusEffect enum: not proven'}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def u32(raw, at):
    return struct.unpack_from('<I', raw, at)[0]


def f32(raw, at):
    return round(struct.unpack_from('<f', raw, at)[0], 4)


def settings_rows(name, tname, stride):
    raw = (entity_research.FILEDIVER / 'datalibrary' / name).read_bytes()
    result = {}
    for group in groups(raw):
        if group['type'] != dl_hash(tname):
            continue
        offset, count = struct.unpack_from('<QQ', raw, group['root'])
        for index in range(count):
            row = raw[group['root'] + offset + index * stride:group['root'] + offset + (index + 1) * stride]
            result[u32(row, 0)] = {'row': index, 'bytes': row}
    return result


def masked(raw):
    out = bytearray(raw)
    for low, high in TWIN_EXCLUDED:
        out[low:high] = bytes(high - low)
    return bytes(out)


def leaves(native, type_hash, wanted, base=0, depth=0):
    name = native.names.get(type_hash)
    try:
        desc = native.typelib_module.layout(native.typelib, name or type_hash, structured=True)
    except Exception:  # noqa: BLE001  a type without a layout has no members to scan
        return []
    out = []
    for member in desc['members']:
        count = member.get('array_or_bits') or 1
        inline = member['atom'] == 'INLINE_ARRAY'
        type_name = native.names.get(member['type_hash']) if member['type_hash'] else None
        if member['storage'] == 'STRUCT' and type_name and depth < 5:
            stride = member['size64'] // max(count, 1) if inline else member['size64']
            for rep in range(count if inline else 1):
                out += leaves(native, member['type_hash'], wanted, base + member['offset64'] + rep * stride, depth + 1)
        elif member['type_hash'] == wanted:
            width = member['size64'] // max(count, 1) if inline else member['size64']
            out += [base + member['offset64'] + rep * width for rep in range(count if inline else 1)]
    return out


def reference_graph(native, explosions):
    """ProjectileType -> every data consumer: component members, entity deltas and explosion submunitions."""
    wanted = dl_hash('ProjectileType')
    names = sorted({line for line in (entity_research.FILEDIVER / 'hashes/dl_type_names.txt').read_text(
        encoding='utf-8').splitlines() if line.endswith('ComponentData')})
    refs, members, type_index = {}, {}, {}
    for name in names:
        try:
            body, _, offset, size, count = native.table(name)
            desc = native.typelib_module.layout(native.typelib, name, structured=True)
        except Exception:  # noqa: BLE001  not a component table in this build
            continue
        offsets = leaves(native, desc['members'][1]['type_hash'], wanted)
        if not offsets:
            continue
        members[name] = offsets
        _, _, _, _, table_offset = native.probe.find_component(native.entities, name)
        type_index[u32(native.entities, table_offset - 4)] = name
        owners = native.owners(name)
        for record in range(count):
            raw = body[offset + record * size:offset + (record + 1) * size]
            for at in offsets:
                value = u32(raw, at)
                if not value:
                    continue
                for owner in owners.get(record, []) or [None]:
                    refs.setdefault(value, []).append({'kind': 'component', 'component': name, 'offset': at,
                        'owner': (native.path(owner) or '0x%016X' % owner) if owner else None})
    deltas, _ = attachments.entity_deltas((entity_research.FILEDIVER / 'datalibrary/generated_entity_deltas.dl_bin')
        .read_bytes())
    for resource, item in deltas.items():
        for entry in item['entries']:
            name = type_index.get(entry['component'])
            for at in members.get(name, []):
                if entry['offset'] <= at and at + 4 <= entry['offset'] + entry['size']:
                    value = u32(entry['bytes'], at - entry['offset'])
                    if value:
                        refs.setdefault(value, []).append({'kind': 'entity_delta', 'component': name, 'offset': at,
                            'item': native.path(resource) or '0x%016X' % resource})
    for explosion, item in explosions.items():
        value = u32(item['bytes'], 84)
        if value:
            refs.setdefault(value, []).append({'kind': 'explosion_submunition', 'explosion': explosion})
    return refs, {name: offsets for name, offsets in sorted(members.items())}


def main():
    native = entity_research.Native()
    projectiles = settings_rows('generated_projectile_settings.dl_bin', 'ProjectileSettings', PROJECTILE_STRIDE)
    explosions = settings_rows('generated_explosion_settings.dl_bin', 'ExplosionSettings', EXPLOSION_STRIDE)
    damages = settings_rows('generated_damage_settings.dl_bin', 'DamageSettings', DAMAGE_STRIDE)
    statuses = json.loads(STATUS_RESEARCH.read_text(encoding='utf-8'))
    status_name = {row['nativeType']: row['semanticId'] for row in statuses['statuses']}
    donors_research = json.loads(DONOR_RESEARCH.read_text(encoding='utf-8'))
    templates = donors_research['templates']
    attack = json.loads(ATTACK_RESEARCH.read_text(encoding='utf-8'))
    active = json.loads(ACTIVE_RESEARCH.read_text(encoding='utf-8'))

    # The retained-snapshot identities of the outputs must be this file's array positions.
    for entry in attack['weapons']:
        settings = (entry.get('output') or {}).get('settings')
        if (entry['family'] == 'projectile' and settings
                and projectiles[settings['recordType']]['row'] != settings['row']):
            raise ValueError('projectile settings row positions differ from the snapshot identities')

    refs, members = reference_graph(native, explosions)
    spare = sorted(t for t in projectiles if t not in refs)

    def damage_view(kind):
        item = damages.get(kind)
        if not item:
            return {'type': kind, 'resolved': False}
        raw = item['bytes']
        return {'type': kind, 'standard': struct.unpack_from('<i', raw, 4)[0],
            'durable': struct.unpack_from('<i', raw, 8)[0],
            'ap': list(struct.unpack_from('<4I', raw, 12)),
            'statuses': [{'status': status_name.get(u32(raw, 44 + 8 * i), u32(raw, 44 + 8 * i)),
                'strength': f32(raw, 48 + 8 * i)} for i in range(4) if u32(raw, 44 + 8 * i)]}

    def explosion_view(kind):
        if not kind:
            return None
        raw = explosions[kind]['bytes']
        volume = u32(raw, 100)
        return {'type': kind, 'row': explosions[kind]['row'], 'damage': damage_view(u32(raw, 4)),
            'radii': [f32(raw, 16), f32(raw, 20), f32(raw, 24)],
            'volume': templates.get(str(volume), volume) if volume else None,
            'volumeSeconds': f32(raw, 104) if volume else None,
            'submunition': u32(raw, 84) or None, 'arc': u32(raw, 120) or None}

    def slots(kind):
        raw = projectiles[kind]['bytes']
        return {'directDamage': damage_view(u32(raw, 60)), 'impactExplosion': explosion_view(u32(raw, 144)),
            'expiryExplosion': explosion_view(u32(raw, 156)),
            'unknownMembers': {str(o): {'value': f32(raw, o) if o != 228 else u32(raw, o), 'note': note}
                for o, note in UNKNOWN_ROW_MEMBERS.items()}}

    def identity(kind):
        return {'group': 0, 'row': projectiles[kind]['row'], 'recordType': kind, 'settingsType': PROJECTILE_SETTINGS_TYPE}

    def consumers(kind):
        return [dict(item, owner=(item.get('owner') or '').rsplit('/', 1)[-1] or item.get('owner')) for item in
            refs.get(kind, [])]

    # Owned rows fired as a catalogued output (their owner is established to fire them).
    outputs = {}
    for entry in attack['weapons']:
        output = entry.get('output') or {}
        if entry['family'] != 'projectile' or not output.get('settings'):
            continue
        kind = output['type']
        outputs.setdefault(kind, []).append({'weapon': entry['weapon'], 'kind': entry['kind']})
    for donor in donors_research['donors']:
        outputs.setdefault(donor['projectileType'], []).append({'weapon': donor['name'], 'kind': donor['ownerKind']})

    index = {}
    for kind, row in projectiles.items():
        if kind in refs:
            index.setdefault(masked(row['bytes']), []).append(kind)
    twins = []
    for kind in spare:
        matches = [t for t in index.get(masked(projectiles[kind]['bytes']), []) if t in outputs]
        if len(matches) != 1:
            continue
        twin = matches[0]
        differing = {name: {'spare': u32(projectiles[kind]['bytes'], at), 'twin': u32(projectiles[twin]['bytes'], at)}
            for name, at in REFERENCES.items() if u32(projectiles[kind]['bytes'], at) != u32(projectiles[twin]['bytes'], at)}
        owners = outputs[twin]
        twins.append({'spare': kind, 'twin': twin, 'twinOutputs': owners, 'identity': identity(kind),
            'twinIdentity': identity(twin), 'differingReferences': differing,
            'maskedSha256': sha(masked(projectiles[kind]['bytes'])), 'slots': slots(kind),
            'excludedFromTwinCheck': [{'from': low, 'to': high} for low, high in TWIN_EXCLUDED]})

    # Speargun: the gas field is the spear's expiry explosion; the spare twin is the same spear with another expiry.
    spear = next(t for t in twins if t['twin'] == 125)
    ems = next(d for d in donors_research['donors'] if d['name'] == 'A/M-23 EMS Mortar Sentry')
    ems_row = projectiles[ems['projectileType']]['bytes']
    ems_field = explosion_view(u32(ems_row, 156 if ems['field']['role'] == 'expiry' else 144))
    speargun = {'weapon': 'S-11 Speargun', 'projectile': {'type': 125, 'identity': identity(125), 'slots': slots(125),
            'consumers': consumers(125)},
        'spareTwin': {'type': spear['spare'], 'identity': spear['identity'], 'slots': spear['slots'],
            'differingReferences': spear['differingReferences'], 'consumers': consumers(spear['spare'])},
        'emsField': {'donor': ems['name'], 'role': ems['field']['role'], 'explosion': ems_field},
        'findings': [
            'The gas cloud is the spear\'s EXPIRY explosion (+156 -> 97: Gas volume 10 s, radius 5, 3 damage with Gas '
            'and Gas Confusion); its impact explosion (+144) is empty. The spear\'s own direct-hit damage (65) also '
            'applies Gas and Gas Confusion.',
            'Row 300 is byte-identical to the spear (flight, visuals, audio, damage row 65) except its expiry explosion '
            '(342: 400 damage, radius 2.5 / 7 / 8, no field). No typed data member references it.',
            'Mode B can keep the spear exactly: the function projectile is row 300, and its own expiry explosion is '
            'pointed at the EMS Mortar shell\'s StaticField explosion. Row 300 has no other consumer, so both writes '
            'are exclusive; mode A keeps row 125 unchanged.']}

    hmg = next(e for e in attack['weapons'] if e['weapon'] == 'MG-206 Heavy Machine Gun')
    hmg_type = hmg['output']['type']
    hmg_damage = u32(projectiles[hmg_type]['bytes'], 60)
    damage_users = sorted(t for t, row in projectiles.items() if u32(row['bytes'], 60) == hmg_damage)
    fire_bullets = []
    for kind, owners in sorted(outputs.items()):
        view = damage_view(u32(projectiles[kind]['bytes'], 60))
        names = [s['status'] for s in view.get('statuses', [])]
        if any(isinstance(n, str) and n in ('fire', 'burning_heavy', 'acid_splash') for n in names) \
                and not u32(projectiles[kind]['bytes'], 144) and not u32(projectiles[kind]['bytes'], 156):
            fire_bullets.append({'type': kind, 'outputs': owners, 'statuses': view['statuses'],
                'velocity': f32(projectiles[kind]['bytes'], 32)})
    hmg_case = {'weapon': 'MG-206 Heavy Machine Gun', 'projectile': {'type': hmg_type, 'identity': identity(hmg_type),
            'consumers': consumers(hmg_type), 'slots': slots(hmg_type)},
        'directDamageRowUsers': damage_users, 'spareTwin': None,
        'fireOnHitDonors': fire_bullets,
        'findings': [
            'The HMG bullet row and its direct-hit damage row are shared: the row by %d consumers, the damage row by %d '
            'projectile rows. A status on the HMG\'s own damage row reaches every one of them (allow_shared).'
            % (len(consumers(hmg_type)), len(damage_users)),
            'No spare row is a twin of the HMG bullet, so an alternate HMG mode with exactly the HMG ballistics and a '
            'different status would need a derived row, which this build does not offer.',
            'An alternate mode with a native fire-on-hit bullet works through ProgrammableAmmo (the HMG\'s left input '
            'is free): the mode fires that bullet (its own flight and damage) and the HMG keeps its magazine, rate '
            'selector and handling.']}

    active_by_weapon = {entry['weapon']: entry for entry in active['weapons']}
    support_hosts = []
    for entry in active['weapons']:
        if entry['kind'] != 'support_weapon':
            continue
        source = entry.get('activeSource') or {}
        support_hosts.append({'weapon': entry['weapon'], 'status': entry['status'],
            'magazineFed': entry.get('magazineFed'), 'mechanism': source.get('kind'),
            'componentHost': entry['status'] == 'ACTIVE_DIRECT' and bool(entry.get('magazineFed')),
            'reason': entry.get('reason')})

    projectile_outputs = []
    for kind, owners in sorted(outputs.items()):
        projectile_outputs.append({'type': kind, 'outputs': owners, 'identity': identity(kind), 'slots': slots(kind),
            'consumerCount': len(refs.get(kind, [])),
            'consumerOwners': sorted({c['owner'].rsplit('/', 1)[-1] for c in refs.get(kind, []) if c.get('owner')})})

    result = {'schemaVersion': 1,
        'source': {'mode': 'offline', 'writes': 0, 'protectionChanges': 0, 'entitiesSha256': build_profile.ENTITY_SHA256,
            'typelibSha256': build_profile.TYPELIB_SHA256},
        'model': {'row': 'ProjectileSettings, 272 bytes, one per ProjectileType (the type is +0 and the row key)',
            'references': {name: {'offset': at, 'type': 'DamageInfoType' if at == 60 else 'ExplosionType'}
                for name, at in REFERENCES.items()},
            'explosion': {'damage': 4, 'submunition': 84, 'arc': 120, 'volumeTemplate': 100, 'volumeSeconds': 104},
            'typedProjectileMembers': members,
            'rows': len(projectiles), 'referencedRows': len([t for t in projectiles if t in refs]),
            'spareRows': spare},
        'classes': {
            'REFERENCE_COMPOSITION': {'supported': True, 'reason': 'Re-point a row\'s direct damage, impact or expiry '
                'explosion. The written row changes for every consumer (allow_shared when more than one entity fires '
                'it); the donor rows are only referenced, never changed.'},
            'DERIVED_MUTATION': {'supported': 'spare_twins_only', 'spareTwins': [t['spare'] for t in twins],
                'reason': 'A spare twin is an independent native row with its twin\'s exact flight, visuals and audio, '
                    'so it can be composed without touching any consumer. Copying a different base into a spare row '
                    'is not offered: whether the game resolves a row\'s visual resources when it fires (rather than '
                    'once at load), and whether code references spare types directly, are not proven; other players '
                    'without the mod would see the spare row\'s vanilla contents.'},
            'CUSTOM_ROW': {'supported': False, 'reason': 'The settings table has exactly one row per ProjectileType and '
                'the game reads it by type with no bound (projectile settings by type, pinned in '
                'domains/event_natives.lua); the type is also what the network replicates. There is no allocation.'}},
        'spareTwins': twins, 'projectileOutputs': projectile_outputs,
        'speargun': speargun, 'hmg': hmg_case,
        'liberatorTalon': {'finding': 'Unchanged: the AR-23 Liberator fires its default ammunition delta, so a donor '
            'goes through ammunition.projectile (live-proven for EAT-700 and GL-52); the Talon is a catalogued output.'},
        'supportHosts': support_hosts}
    OUTPUT.write_text(json.dumps(result, indent=1) + '\n', newline='\n')
    print(json.dumps({'rows': len(projectiles), 'spare': len(spare), 'twins': [(t['spare'], t['twin']) for t in twins],
        'emsField': ems_field['type'] if ems_field else None, 'hmgConsumers': len(consumers(hmg_type)),
        'supportComponentHosts': [h['weapon'] for h in support_hosts if h['componentHost']]}))


if __name__ == '__main__':
    main()
