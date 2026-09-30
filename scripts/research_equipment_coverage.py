"""Coverage pass for backpacks, Guard Dog drones, the LAS-17/LAS-98 lasers and the Maxigun. Read-only.

Every field this pass names is proven from retained evidence, never from magnitude alone:

* owner and layout: the pinned type library (member offset, storage, hidden-name length, enclosing struct type) and
  the pinned decoded entity table (the record, its owners and its values);
* meaning: an exact published value on one or more independent entities (wiki pages pinned by revision, read from
  the importer cache), a differential across every owner of the same record type, and the hidden-name length;
* identity chains: stratagem -> hellpod rack -> backpack (research/entity-authoring-runtime), then the backpack's own
  typed link to the entity it spawns (DepositComponent +24 -> Guard Dog drone, ShieldControllerComponent +0 -> the
  SH-51 energy barrier) and the drone's MountComponent slot -> its weapon;
* shared ownership: owner counts of every record, and every settings row that references a status tick DamageInfo.

Members without that proof are published as unknown with what is known (offset, type, name length, values) and
stay read-only. Third-party mods (Maxigun Reimagined, SH32 ShieldBoost) are leads only: every claim is re-located
and classified here. Muzzle-flash, particle, material and audio members are ignored by design.

Output: research/equipment-coverage-F5FEE03DCFDB.json.
"""
from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import research_entity_authoring as entity_research  # noqa: E402
from reference_format import dl_hash, groups  # noqa: E402

OUTPUT = ROOT / 'research/equipment-coverage-F5FEE03DCFDB.json'
ENTITY_RESEARCH = ROOT / 'research/entity-authoring-runtime-F5FEE03DCFDB.json'
STATUS_RESEARCH = ROOT / 'research/status-effects-F5FEE03DCFDB.json'
SUPPORT_RESEARCH = ROOT / 'research/support-weapon-runtime-F5FEE03DCFDB.json'
WIKI_CACHE = ROOT.parent / 'HD2WikiImporter/cache'
MAXIGUN_REIMAGINED = Path.home() / 'Downloads/Maxigun-Reimagined-v1.0/Addon/9ba626afa44a3aa3.patch_0'

DRONE_BACKPACKS = ('AX/AR-23 Guard Dog', 'AX/LAS-5 Rover', 'AX/FLAM-75 Hot Dog', 'AX/ARC-3 K-9', 'AX/TX-13 Dog Breath')
WEAPON_COMPONENTS = ('WeaponDataComponentData', 'ProjectileWeaponComponentData', 'BeamWeaponComponentData',
    'SprayWeaponComponentData', 'ArcWeaponComponentData', 'WeaponHeatComponentData', 'WeaponMagazineComponentData',
    'WeaponReloadComponentData', 'HealthComponentData', 'TurretComponentData')
FAMILY = {'ProjectileWeaponComponentData': 'projectile', 'BeamWeaponComponentData': 'beam',
    'SprayWeaponComponentData': 'spray', 'ArcWeaponComponentData': 'arc'}
DRONE_GENERIC = ('SensorEyeComponentData', 'NavigationComponentData', 'TargetingComponentData',
    'WeaponWielderComponentData', 'MultiTargetComponentData', 'DetectorComponentData', 'BehaviorComponentData',
    'AbilityComponentData', 'BoidsComponentData', 'RotationComponentData', 'MotionComponentData',
    'FactionComponentData', 'UnitComponentData', 'AttachableComponentData', 'TagComponentData')

# Wiki facts this pass correlates, pinned by page revision and the exact published text. The cache is the
# importer's saved API response; a changed revision or a missing phrase stops the research.
WIKI = {
    'SH-32 Shield Generator Pack': (136374, {
        'capacity': ('Shield Capacity: 150 Health', 150.0), 'rechargeDelay': ('Shield Recharge Delay: 60 Seconds', 60.0),
        'brokenRechargeDelay': ('Shield Broken Recharge Delay: 12 Second', 12.0),
        'rechargeRate': ('Shield Regen Rate: 150 Health/Second', 150.0),
        'mainHealth': ('Main Health\n200', 200), 'mainArmor': ('Main Armor\nUnarmored', 0)}),
    'SH-51 Directional Shield': (136373, {
        'capacity': ('Shield Capacity\n1000', 1000.0), 'rechargeRate': ('Shield Regen\n300 shield/s', 300.0),
        'rechargeDelay': ('Shield Regen Delay\n3 s', 3.0), 'brokenRechargeDelay': ('Shield Broken Delay\n6 s', 6.0),
        'radius': ('Shield Radius\n0 m', 0.0), 'mainHealth': ('Main Health\n400', 400), 'mainArmor': ('Main Armor\nHeavy', 4)}),
    'FX-12 Shield Generator Relay': (None, {
        'capacity': ('Shield Capacity\n4000', 4000.0), 'rechargeRate': ('Shield Regen\n400 shield/s', 400.0),
        'rechargeDelay': ('Shield Regen Delay\n0.00999999978 s', 0.00999999978),
        'brokenRechargeDelay': ('Shield Broken Delay\n45 s', 45.0), 'radius': ('Shield Radius\n15 m', 15.0)}),
    'LIFT-182 Warp Pack': (136830, {
        'teleportDistance': ('Teleport Distance\n10 m', 10.0), 'upwardBias': ('Upward Bias\n1.4 m', 1.4),
        'downwardBias': ('Downward Bias\n4 m', 4.0), 'maxSurvivableUnitSize': ('Max Survivable Unit Size\nMedium', 'Medium'),
        'safeHeatThreshold': ('Safe Heat Threshold\n15 %', 15.0),
        'unsafeHeatThreshold': ('Unsafe Heat Threshold\n45 %', 45.0), 'heatGain': ('Heat Gain\n33 %/use', 33.0),
        'heatCooldown': ('Heat Cooldown\n6 %/s', 6.0),
        'injury.head': ('Head / 10 DMG', 10.0), 'injury.l_hand': ('Left Arm / 35 DMG', 35.0),
        'injury.r_hand': ('Right Arm / 35 DMG', 35.0), 'injury.l_knee': ('Left Leg / 45 DMG', 45.0),
        'injury.r_knee': ('Right Leg / 45 DMG', 45.0), 'injury.chest': ('Chest / Inflicts Fire', 'fire')}),
    'LIFT-860 Hover Pack': (None, {
        'hoverSeconds': ("maintaining the user's height for six seconds before deactivating", 6.0),
        'recharge': ('The Hover Pack will take at most 12 seconds to recharge', 12.0)}),
    'LAS-17 Double-Edge Sickle': (None, {
        'capacity': ('Overheats at\n200 °C', 200.0), 'heatPerShot': ('Heat Per Shot\n1.14999998 °C', 1.14999998),
        'coolPerSecond': ('Cool Per Sec\n12 - 8 - 6', (12.0, 8.0, 6.0)),
        'level1': ('26-50% heat: Laser pulses are  Medium armor penetrating and deal 55 damage. Deals 10 heat damage per second to the user.', None),
        'level2': ('51-90% heat: Laser pulses are  Medium armor penetrating and deal 70 damage. Deals 20 heat damage a second to the user.', None),
        'level3': ('91%+ heat: Laser pulses are  Heavy armor penetrating and deal 70 damage. Sets the user on fire and deals 50 heat damage a second', None),
        'noLock': ('the heatsink does not need to be replaced upon reaching maximum heat', None)}),
    'LAS-98 Laser Cannon': (None, {
        'capacity': ('Overheats at\n100 °C', 100.0), 'heatPerSecond': ('Heat Per Second\n8 °C', 8.0),
        'coolPerSecond': ('Cool Per Sec\n7.5 - 5 - 3.8', (7.5, 5.0, 3.8)), 'warmup': ('Warmup\n0.5 sec', 0.5),
        'beamFireRate': ('Beam Fire Rate\n60 rpm', 60), 'beamRange': ('Beam Range\n1000 m', 1000.0)}),
    'LAS-13 Trident': (None, {'beamFireRate': ('Beam Fire Rate\n300 rpm', 300)}),
    '40-K Meltagun': (None, {'beamFireRate': ('Beam Fire Rate\n50 rpm', 50)}),
    'LAS-5 Scythe': (None, {'beamFireRate': ('Beam Fire Rate\n60 rpm', 60), 'warmup': ('Warmup\n0.2 sec', 0.2),
        'heatPerSecond': ('Heat Per Second\n12.5 °C', 12.5),
        'coolPerSecond': ('Cool Per Sec\n12.8 - 8.5 - 6.4', (12.8, 8.5, 6.4))}),
    'LAS-7 Dagger': (None, {'beamFireRate': ('Beam Fire Rate\n60 rpm', 60)}),
    'A/LAS-98 Laser Sentry': (None, {'beamFireRate': ('Beam Fire Rate\n60 rpm', 60)}),
    'AX/LAS-5 Rover': (None, {'beamFireRate': ('Beam Fire Rate\n60 rpm', 60), 'warmup': ('Warmup\n0.2 sec', 0.2)}),
    'M-1000 Maxigun': (None, {'velocity': ('Initial Velocity\n920 m/s', 920.0), 'mass': ('Mass\n11 g', 11.0)}),
}
WIKI_FILES = {'SH-32 Shield Generator Pack': 'SH-32_Shield_Generator_Pack', 'SH-51 Directional Shield': 'SH-51_Directional_Shield',
    'FX-12 Shield Generator Relay': 'FX-12_Shield_Generator_Relay', 'LIFT-182 Warp Pack': 'LIFT-182_Warp_Pack',
    'LIFT-860 Hover Pack': 'LIFT-860_Hover_Pack', 'LAS-17 Double-Edge Sickle': 'LAS-17_Double-Edge_Sickle',
    'LAS-98 Laser Cannon': 'LAS-98_Laser_Cannon', 'LAS-13 Trident': 'LAS-13_Trident', '40-K Meltagun': '40-K_Meltagun',
    'LAS-5 Scythe': 'LAS-5_Scythe', 'LAS-7 Dagger': 'LAS-7_Dagger', 'A/LAS-98 Laser Sentry': 'A_LAS-98_Laser_Sentry',
    'AX/LAS-5 Rover': 'AX_LAS-5_Rover', 'M-1000 Maxigun': 'M-1000_Maxigun'}
BEAM_ENTITIES = {'LAS-98 Laser Cannon': 'content/fac_helldivers/equipment/support_weapons/laser_cannon/laser_cannon',
    'LAS-13 Trident': 'content/fac_helldivers/equipment/primary_weapons/laser_shotgun/laser_shotgun',
    '40-K Meltagun': 'content/fac_helldivers/equipment/support_weapons/energy_weapon_shark/energy_weapon_shark',
    'LAS-5 Scythe': 'content/fac_helldivers/equipment/primary_weapons/laser_rifle/laser_rifle',
    'LAS-7 Dagger': 'content/fac_helldivers/equipment/sidearm_weapons/laser_pistol/laser_pistol',
    'A/LAS-98 Laser Sentry': 'content/fac_helldivers/hellpod/laser_cannon_turret/laser_cannon_turret',
    'AX/LAS-5 Rover': 'content/fac_helldivers/equipment/backpacks/drone_weapons/drone_laser_rifle/drone_laser_rifle_mount'}
HEAT_ENTITIES = {'LAS-98 Laser Cannon': BEAM_ENTITIES['LAS-98 Laser Cannon'], 'LAS-5 Scythe': BEAM_ENTITIES['LAS-5 Scythe'],
    'LAS-16 Sickle': 'content/fac_helldivers/equipment/primary_weapons/laser_rifle_long/laser_rifle_long',
    'LAS-17 Double-Edge Sickle': 'content/fac_helldivers/equipment/primary_weapons/laser_rifle_long_hotshot/'
        'laser_rifle_long_hotshot',
    'LAS-13 Trident': BEAM_ENTITIES['LAS-13 Trident'], 'A/LAS-98 Laser Sentry': BEAM_ENTITIES['A/LAS-98 Laser Sentry'],
    'AX/LAS-5 Rover': BEAM_ENTITIES['AX/LAS-5 Rover']}
MAXIGUN = 'content/fac_helldivers/equipment/support_weapons/minigun/minigun'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def hexid(value: int) -> str:
    return f'0x{value:016X}'


def f32(raw, at):
    return round(struct.unpack_from('<f', raw, at)[0], 6)


def u32(raw, at):
    return struct.unpack_from('<I', raw, at)[0]


def i32(raw, at):
    return struct.unpack_from('<i', raw, at)[0]


def u64(raw, at):
    return struct.unpack_from('<Q', raw, at)[0]


def wiki_text(name):
    stem = WIKI_FILES[name]
    path = next(p for p in WIKI_CACHE.iterdir() if p.name.startswith(stem + '-'))
    body = json.loads(path.read_text(encoding='utf-8'))['parse']
    text = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', body['text'], flags=re.S)
    text = re.sub(r'</(tr|p|li|h\d|div|table)>', '\n', text)
    text = re.sub(r'</t[dh]>', ' | ', text)
    text = html.unescape(re.sub(r'<[^>]+>', '', text))
    lines = [re.sub(r'[ \t]+', ' ', line).strip(' |') for line in text.splitlines()]
    return body['revid'], '\n'.join(line for line in lines if line), path.name


def wiki_facts():
    result = {}
    for name, (revision, facts) in WIKI.items():
        revid, text, file_name = wiki_text(name)
        if revision is not None and revid != revision:
            raise ValueError(f'{name}: wiki revision changed ({revid})')
        flat = re.sub(r'\s+', ' ', text)
        values = {}
        for key, (phrase, value) in facts.items():
            if re.sub(r'\s+', ' ', phrase) not in flat:
                raise ValueError(f'{name}: published fact absent: {phrase!r}')
            values[key] = {'value': list(value) if isinstance(value, tuple) else value, 'text': phrase}
        result[name] = {'revision': revid, 'cache': file_name, 'facts': values}
    return result


class Layouts:
    """Leaf members of a component record from the pinned type library (offset, storage, name length, struct)."""

    def __init__(self, native):
        self.native = native

    def members(self, component):
        desc = self.native.typelib_module.layout(self.native.typelib, component, structured=True)
        return self._flat(desc['members'][1]['type_hash'], 0, 0, '')

    def _flat(self, type_hash, base, depth, prefix):
        native = self.native
        name = native.names.get(type_hash)
        desc = native.typelib_module.layout(native.typelib, name or type_hash, structured=True)
        out = []
        for member in desc['members']:
            length = member['name'].split('inferred_length=')[-1]
            length = int(length) if length.isdigit() else None
            type_name = native.names.get(member['type_hash']) if member['type_hash'] else None
            offset = base + member['offset64']
            count = member.get('array_or_bits') or 1
            if member['storage'] == 'STRUCT' and depth < 3 and type_name:
                inline = member['atom'] == 'INLINE_ARRAY'
                stride = member['size64'] // max(count, 1) if inline else member['size64']
                for rep in range(count if inline else 1):
                    out += self._flat(member['type_hash'], offset + rep * stride, depth + 1,
                        prefix + f'{type_name}<{length}>' + (f'[{rep}]' if inline else '') + '.')
            else:
                out.append({'offset': offset, 'size': member['size64'], 'storage': member['storage'],
                    'nameLength': length, 'type': type_name, 'struct': prefix.rstrip('.') or None,
                    'count': count if member['atom'] == 'INLINE_ARRAY' else 1})
        return out


def value_of(raw, member):
    offset, size, storage = member['offset'], member['size'], member['storage']
    if storage == 'FP32' and size == 4:
        return f32(raw, offset)
    if storage in ('UINT8', 'ENUM_UINT8') and size == 1:
        return raw[offset]
    if size == 4:
        return i32(raw, offset) if storage in ('INT32', 'ENUM_INT32') else u32(raw, offset)
    if size == 8:
        return hexid(u64(raw, offset))
    return raw[offset:offset + size].hex()


def ownership(native, resource, component):
    found = native.component(resource, component)
    if not found:
        return None
    return native.ownership(found)


def record_of(native, resource, component):
    found = native.component(resource, component)
    return native.record(component, found['record_index']) if found else None


def resource_of(native, path):
    value = native.probe.resource_hash(path)
    if native.path(value) != path:
        raise ValueError('native path does not resolve: ' + path)
    return hexid(value)


def differential(native, layouts, component, offsets):
    """Every owner's value of the given members, grouped: the fingerprint that separates one consumer."""
    members = {m['offset']: m for m in layouts.members(component)}
    rows = []
    for record, owners in sorted(native.owners(component).items()):
        raw = native.record(component, record)
        rows.append({'record': record, 'owners': sorted(native.path(r) or 'unnamed entity' for r in owners),
            'values': {str(o): value_of(raw, members[o]) for o in offsets}})
    return rows


def shield_section(native, layouts, entity, wiki):
    backpacks = {item['name']: item for item in entity['backpacks']}
    members = {m['offset']: m for m in layouts.members('ShieldComponentData')}
    offsets = (0, 76, 80, 84, 88, 92, 96, 100, 104, 108, 324)
    barrier = resource_of(native, 'content/fac_helldivers/equipment/backpacks/directional_energy_shield/'
        'directional_energy_shield')
    consumers = {'SH-32 Shield Generator Pack': backpacks['SH-32 Shield Generator Pack']['resource'],
        'SH-51 Directional Shield': barrier, 'FX-12 Shield Generator Relay': entity['shieldRelay']['resource']}
    result = []
    for name, resource in consumers.items():
        raw = record_of(native, resource, 'ShieldComponentData')
        result.append({'consumer': name, 'entity': native.path(int(resource, 16)),
            'ownership': ownership(native, resource, 'ShieldComponentData'),
            'values': {str(o): value_of(raw, members[o]) for o in offsets},
            'wiki': {key: fact['value'] for key, fact in wiki[name]['facts'].items()}})
    # Semantic decisions: an exact published value on all three independent consumers, plus the name length.
    semantic = {
        '76': ('shield.durability', 'capacity', 'Shield capacity'),
        '88': ('shield.recharge_delay', 'rechargeDelay', 'Delay before a damaged (unbroken) shield recharges'),
        '92': ('shield.broken_recharge_delay', 'brokenRechargeDelay', 'Delay before a broken shield restarts'),
        '96': ('shield.recharge_rate', 'rechargeRate', 'Shield recharge rate'),
        '0': ('shield.radius', 'radius', 'Shield radius')}
    decisions = {}
    for offset, (field, key, meaning) in semantic.items():
        checks = []
        for item in result:
            if key not in item['wiki']:
                continue
            want = item['wiki'][key]
            have = item['values'][offset]
            checks.append({'consumer': item['consumer'], 'native': have, 'published': want,
                'exact': abs(have - want) <= max(1e-6, abs(want) * 1e-6)})
        exact = [c for c in checks if c['exact']]
        if len(exact) != len(checks):
            raise ValueError(f'shield +{offset}: published value mismatch {checks}')
        decisions[offset] = {'field': field, 'meaning': meaning, 'nameLength': members[int(offset)]['nameLength'],
            'correlations': checks, 'independentConsumers': len(exact)}
    unknown = [{'offset': o, 'storage': members[o]['storage'], 'nameLength': members[o]['nameLength'],
        'type': members[o]['type'], 'values': {item['consumer']: item['values'][str(o)] for item in result},
        'lead': lead} for o, lead in ((80, None), (84, None),
            (100, 'external export label "restart charge" (ShieldRelayImprovements); no published value'),
            (104, None), (108, 'StatusEffectType member; 0 on every backpack shield'), (324, 'ShieldShapeType'))]
    return {'component': 'ShieldComponentData', 'recordSize': 344, 'consumers': result, 'decisions': decisions,
        'unknownMembers': unknown,
        'leads': [{'source': 'SH32 ShieldBoost (third-party addon)', 'claims': {'+88': 'damaged recharge delay, '
            'original 60', '+92': 'broken recharge delay, original 12'}, 'status': 'lead only; the exact '
            'published values above prove the members independently'}]}


def directional_shield(native, entity, wiki):
    item = next(b for b in entity['backpacks'] if b['name'] == 'SH-51 Directional Shield')
    backpack = item['resource']
    controller = native.component(backpack, 'ShieldControllerComponentData')
    raw = native.record('ShieldControllerComponentData', controller['record_index'])
    barrier = hexid(u64(raw, 0))
    barrier_path = native.path(int(barrier, 16))
    report = native.report(barrier)
    names = sorted(c['name'] for c in report['components'] if c['name'])
    health = entity_research.health_evidence(native, barrier)
    body = entity_research.health_evidence(native, backpack)
    zones = [z for z in health['zones'] if z['populated']]
    if len(zones) != 1 or zones[0]['name'] != 'body_front' or zones[0]['actorCount'] != 1:
        raise ValueError('SH-51 barrier damage zones changed')
    zone_raw = native.record('HealthComponentData', health['ownership']['recordIndex'])
    actor = [v for v in struct.unpack_from('<24I', zone_raw, 520 + 456) if v]
    hit_filter = record_of(native, barrier, 'ShieldHitFilterComponentData')
    body_zones = [z for z in body['zones'] if z['populated']]
    facts = wiki['SH-51 Directional Shield']['facts']
    return {'backpack': backpack, 'controller': native.ownership(controller), 'controllerLink': {
            'component': 'ShieldControllerComponentData', 'offset': 0, 'storage': 'u64', 'nameLength': 18},
        'barrier': {'resource': barrier, 'path': barrier_path, 'entityRow': native.entity_row(int(barrier, 16)),
            'components': names,
            'shield': ownership(native, barrier, 'ShieldComponentData'),
            'health': {'ownership': health['ownership'], 'mainHealth': health['mainHealth'],
                'defaultArmor': health['defaultArmor'],
                'zones': [{'index': z['index'], 'name': z['name'], 'armor': z['armor'], 'health': z['health'],
                    'affectsMainHealth': z['affectsMainHealth'], 'actorCount': z['actorCount'],
                    'actors': [native.thin_name(a) for a in actor], 'nameHash': z['nameHash']} for z in zones]},
            'hitFilter': {'ownership': ownership(native, barrier, 'ShieldHitFilterComponentData'),
                'members': [{'offset': 0, 'storage': 'FP32', 'nameLength': 23, 'value': f32(hit_filter, 0)}]}},
        'body': {'ownership': body['ownership'], 'mainHealth': body['mainHealth'], 'defaultArmor': body['defaultArmor'],
            'populatedZones': len(body_zones),
            'wiki': {'mainHealth': facts['mainHealth']['value'], 'mainArmor': facts['mainArmor']['value']},
            'exact': body['mainHealth'] == facts['mainHealth']['value'] and body['defaultArmor'] == facts['mainArmor']['value']},
        'findings': [
            'The backpack body and the energy barrier are separate entities: the body (Health 400, armor 4, no '
            'populated damage zone, so every hit on it resolves to the default zone) is the published "Main '
            'Health 400 / Heavy"; the barrier is spawned through ShieldControllerComponent +0.',
            'The barrier owns the shield energy (ShieldComponent: capacity 1000, delays 3/6 s, 300/s, exact '
            'published values) and its own Health 450 with one damage zone, "body_front", whose only hit actor is '
            'the barrier collision "c_collision": that zone is what projectiles striking the barrier resolve to.',
            'The barrier default-zone armor (1) is the fallback for hits on actors no zone lists; the barrier '
            'lists its only collision actor in body_front, so the fallback is not the shield-facing armor (the '
            'same rule the SH-20 live test demonstrated).',
            'Whether a barrier hit is absorbed by the shield energy before the Health zone is consulted is not '
            'traced; zone armor/health stay behind allow_unverified_effect.']}


def warp_section(native, layouts, entity, wiki):
    item = next(b for b in entity['backpacks'] if b['name'] == 'LIFT-182 Warp Pack')
    resource = item['resource']
    own = ownership(native, resource, 'DisplacementComponentData')
    if not own or not own['uniqueOwner']:
        raise ValueError('Warp Pack DisplacementComponent ownership changed')
    raw = record_of(native, resource, 'DisplacementComponentData')
    members = layouts.members('DisplacementComponentData')
    by_offset = {m['offset']: m for m in members}
    facts = {key: fact['value'] for key, fact in wiki['LIFT-182 Warp Pack']['facts'].items()}
    named = {120: ('warp.distance', 'teleportDistance'), 128: ('warp.upward_bias', 'upwardBias'),
        132: ('warp.downward_bias', 'downwardBias'), 140: ('warp.safe_heat_threshold', 'safeHeatThreshold'),
        144: ('warp.unsafe_heat_threshold', 'unsafeHeatThreshold'), 148: ('warp.heat_per_use', 'heatGain'),
        152: ('warp.heat_cooldown_per_second', 'heatCooldown')}
    decisions = {}
    for offset, (field, key) in named.items():
        have, want = f32(raw, offset), facts[key]
        if abs(have - want) > 1e-5:
            raise ValueError(f'Warp Pack +{offset}: {have} != published {want}')
        decisions[str(offset)] = {'field': field, 'native': have, 'published': want,
            'nameLength': by_offset[offset]['nameLength'], 'exact': True}
    injuries = []
    for index in range(12):
        base = 160 + index * 24
        name_hash, damage, _, bone_hash, status = struct.unpack_from('<IfQIi', raw, base)
        injuries.append({'index': index, 'offset': base, 'limb': native.thin_name(name_hash), 'limbHash': name_hash,
            'damage': round(damage, 6), 'damageOffset': base + 4, 'bone': native.thin_name(bone_hash),
            'statusType': status, 'statusOffset': base + 20, 'unused': name_hash == 0})
    published = {'head': facts['injury.head'], 'l_hand': facts['injury.l_hand'], 'r_hand': facts['injury.r_hand'],
        'l_knee': facts['injury.l_knee'], 'r_knee': facts['injury.r_knee']}
    for entry in injuries:
        if entry['limb'] in published and abs(entry['damage'] - published[entry['limb']]) > 1e-6:
            raise ValueError('Warp Pack injury damage mismatch: ' + entry['limb'])
    chest = next(e for e in injuries if e['limb'] == 'chest')
    if chest['statusType'] != 5 or chest['damage'] != 0:
        raise ValueError('Warp Pack chest injury no longer applies Fire')
    unit = i32(raw, 72)
    known = set(named) | {72} | {e['damageOffset'] for e in injuries} | {e['statusOffset'] for e in injuries}
    unknown = [{'offset': m['offset'], 'storage': m['storage'], 'nameLength': m['nameLength'], 'type': m['type'],
        'struct': m['struct'], 'value': value_of(raw, m)} for m in members
        if m['offset'] not in known and not (m['struct'] or '').startswith(('HeatInjuryInfo', 'HeatEffectSet'))
        and m['storage'] in ('FP32', 'UINT8', 'INT32', 'ENUM_INT32', 'ENUM_UINT32')]
    return {'resource': resource, 'ownership': own, 'recordSize': len(raw), 'decisions': decisions,
        'maxSurvivableUnitSize': {'offset': 72, 'type': 'UnitSize', 'nameLength': by_offset[72]['nameLength'],
            'value': unit, 'published': facts['maxSurvivableUnitSize'],
            'reason': 'Enum value names for UnitSize are not in the pinned name tables; only value 1 is '
                'correlated (Medium).'},
        'injuries': {'struct': 'HeatInjuryInfo', 'nameLength': 17, 'count': 12, 'stride': 24, 'offset': 160,
            'members': {'+0': 'limb name hash (u32, name length 10)', '+4': 'damage (f32, name length 13)',
                '+8': 'u64 (name length 6), identical on every used entry', '+16': 'bone name hash (u32, 18)',
                '+20': 'StatusEffectType (name length 18)'},
            'entries': injuries, 'publishedChestStatus': facts['injury.chest']},
        'explosionType': {'offset': 56, 'type': 'ExplosionType', 'value': u32(raw, 56),
            'reason': 'The arrival explosion is an ExplosionSettings row (wiki "LIFT-182 WARP PACK E"); explosion '
                'rows are shared settings and are not authored through the backpack in this release.'},
        'unknownMembers': unknown}


def hover_section(native, layouts, entity, wiki):
    backpacks = {item['name']: item for item in entity['backpacks']}
    hover, jump = backpacks['LIFT-860 Hover Pack']['resource'], backpacks['LIFT-850 Jump Pack']['resource']
    members = layouts.members('JumppackComponentData')
    owners = native.owners('JumppackComponentData')
    rows = {}
    for record, resources in owners.items():
        raw = native.record('JumppackComponentData', record)
        label = ('hover' if hexid(resources[0]) == hover else 'jump' if hexid(resources[0]) == jump else 'variant')
        rows[label] = {'record': record, 'owners': [native.path(r) or hexid(r) for r in resources],
            'ownerCount': len(resources), 'raw': raw}
    if set(rows) != {'hover', 'jump', 'variant'}:
        raise ValueError('Jumppack record owners changed')
    table = []
    for m in members:
        values = {label: value_of(rows[label]['raw'], m) for label in rows}
        table.append({'offset': m['offset'], 'storage': m['storage'], 'nameLength': m['nameLength'],
            'type': m['type'], 'struct': m['struct'], 'values': values,
            'hoverOnly': values['hover'] != values['jump'] and values['jump'] == values['variant']})
    duration = next(t for t in table if t['offset'] == 156)
    facts = {key: fact['value'] for key, fact in wiki['LIFT-860 Hover Pack']['facts'].items()}
    if duration['values']['hover'] != facts['hoverSeconds'] or duration['values']['jump'] != -1.0:
        raise ValueError('Hover duration correlation changed')
    recharge = {label: f32(native.record('RechargeComponentData', native.component(res, 'RechargeComponentData')
        ['record_index']), 0) for label, res in (('hover', hover), ('jump', jump))}
    return {'records': {label: {k: v for k, v in row.items() if k != 'raw'} for label, row in rows.items()},
        'members': table,
        'decisions': {'156': {'field': 'hover.duration', 'nameLength': duration['nameLength'],
            'native': {'hover': duration['values']['hover'], 'jump': duration['values']['jump']},
            'published': facts['hoverSeconds'],
            'evidence': ['exact published hover time (six seconds)', 'hover-only member: both jump-pack '
                'records hold the -1 sentinel', 'typed f32 in JumppackComponent, unique Hover Pack record']},
            '0': {'field': 'jump.vertical_launch_velocity', 'native': {'hover': rows['hover'] and
                f32(rows['hover']['raw'], 0), 'jump': f32(rows['jump']['raw'], 0)},
                'evidence': ['same typed member gameplay-proven on the LIFT-850 Jump Pack (JumpPackImprovements)',
                    'the wiki: the Hover Pack "launches the user high into the air before slowly leveling out"'],
                'unproven': 'whether the hover launch reads the same member'}},
        'recharge': {'native': recharge, 'published': facts['recharge'],
            'note': 'recharge.time is already authored (schema_proven); the wiki gives an upper bound (at most 12 s '
                'depending on fuel), not an exact value, so no hover-specific promotion.'},
        'jumpComparison': 'Jump Pack members +0..+144 are identical except +44 (0.1 vs 0.3) and the ability ids; '
            'the Hover Pack adds +145/+152..+155 flags, +156 hover duration and the vector/scalar block +160..+276 '
            'that both jump records leave zero or neutral.'}


def drone_section(native, entity, wiki_rows):
    backpacks = {item['name']: item for item in entity['backpacks']}
    generic_owners = {name: native.owners(name) for name in DRONE_GENERIC if native.table(name)}
    result = []
    for name in DRONE_BACKPACKS:
        item = backpacks[name]
        resource = item['resource']
        deposit = native.component(resource, 'DepositComponentData')
        raw = native.record('DepositComponentData', deposit['record_index'])
        drone = hexid(u64(raw, 24))
        drone_path = native.path(int(drone, 16))
        health = entity_research.health_evidence(native, drone)
        mount = native.component(drone, 'MountComponentData')
        mount_raw = native.record('MountComponentData', mount['record_index'])
        slots = []
        for slot in range(5):
            path = u64(mount_raw, slot * 24)
            if path:
                slots.append({'slot': slot, 'resource': hexid(path), 'path': native.path(path),
                    'name': native.thin_name(u32(mount_raw, slot * 24 + 16)),
                    'attachNode': native.thin_name(u32(mount_raw, slot * 24 + 8))})
        if len(slots) != 1:
            raise ValueError(f'{name}: drone does not mount exactly one weapon')
        weapon = slots[0]['resource']
        weapon_own = {c: ownership(native, weapon, c) for c in WEAPON_COMPONENTS}
        weapon_own = {c: v for c, v in weapon_own.items() if v}
        families = sorted(FAMILY[c] for c in weapon_own if c in FAMILY)
        if len(families) != 1 or 'WeaponDataComponentData' not in weapon_own:
            raise ValueError(f'{name}: drone weapon family ambiguous')
        report = native.report(drone)
        drone_components = sorted(c['name'] for c in report['components'] if c['name'])
        generic = {}
        for component in DRONE_GENERIC:
            found = native.component(drone, component)
            if found:
                generic[component] = {'recordIndex': found['record_index'],
                    'ownerCount': len(generic_owners[component].get(found['record_index'], []))}
        zones = [z for z in health['zones'] if z['populated']]
        wiki = wiki_rows.get(name, {})
        result.append({'backpack': name, 'backpackResource': resource,
            'deposit': dict(native.ownership(deposit), values={'0': u32(raw, 0), '4': i32(raw, 4), '8': u32(raw, 8)},
                link={'offset': 24, 'storage': 'u64', 'nameLength': 10}),
            'drone': {'resource': drone, 'path': drone_path, 'entityRow': native.entity_row(int(drone, 16)),
                'components': drone_components,
                'health': {'ownership': health['ownership'], 'mainHealth': health['mainHealth'],
                    'defaultArmor': health['defaultArmor'],
                    'zones': [{'index': z['index'], 'name': z['name'], 'nameHash': z['nameHash'], 'armor': z['armor'],
                        'health': z['health'], 'affectsMainHealth': z['affectsMainHealth'],
                        'actorCount': z['actorCount']} for z in zones]},
                'mount': dict(native.ownership(mount), slots=slots),
                'genericComponents': generic},
            'weapon': {'resource': weapon, 'path': slots[0]['path'], 'entityRow': native.entity_row(int(weapon, 16)),
                'family': families[0], 'ownership': weapon_own},
            'wiki': wiki,
            'correlation': {'mainHealth': health['mainHealth'] == wiki.get('mainHealth'),
                'mainArmor': health['defaultArmor'] == wiki.get('mainArmor'),
                'capacity': u32(raw, 0) == wiki.get('maxRounds'), 'start': i32(raw, 4) == wiki.get('startingRounds'),
                'fromSupply': u32(raw, 8) == wiki.get('magsFromSupply')}})
    variant = resource_of(native, 'content/fac_helldivers/equipment/backpacks/drone_weapons/drone_assault_rifle/'
        'drone_assault_rifle_backpack')
    rack_owners = native.owners('HellpodRackComponentData')
    racks = sorted({hexid(owner) for record in range(native.table('HellpodRackComponentData')[4])
        for slot in range(8) if hexid(u64(native.record('HellpodRackComponentData', record), slot * 64)) == variant
        for owner in rack_owners.get(record, [])})
    research = entity_research.load_module('offensive_research_equipment', ROOT / 'scripts/research_stratagem_authoring.py')
    stratagems = research.snapshot_evidence(entity_research.SNAPSHOT)['stratagems']
    delivered = [row['id'] for row in stratagems if any(p in racks for p in row.get('payloads') or [])]
    return {'chain': ['stratagem', 'hellpod rack', 'backpack entity', 'backpack DepositComponent +24 (u64, name '
            'length 10): the drone entity', 'drone MountComponent slot 0: the drone weapon entity',
            'drone weapon: WeaponData plus one attack component (projectile, beam, spray or arc)'],
        'drones': result,
        'variants': [{'path': native.path(int(variant, 16)),
            'racks': [native.path(int(rack, 16)) for rack in racks], 'stratagemsDeliveringRack': delivered,
            'reason': 'A hellpod rack attaches this assault-rifle drone backpack, but no stratagem in the retained '
                'snapshot delivers that rack and the wiki lists no such backpack; not a catalog item, not exposed.'}],
        'genericNote': ('Sensor, navigation, targeting, behavior, boids, rotation and motion are generic unit '
            'components; every drone record holds the same values and their members have no published '
            'correlation (no wiki value for detection, leash or speed). They stay unknown and read-only.')}


def drone_wiki(entity):
    rows = {}
    other = json.loads((ROOT.parent / 'HD2WikiImporter/output/wiki_non_offensive_stratagems.json').read_text(
        encoding='utf-8'))
    for item in other['stratagems']:
        if item['name'] not in DRONE_BACKPACKS:
            continue
        facts = {}
        for node in item['graph']['nodes']:
            if node['id'] != 'entity.main':
                continue
            for field in node['rawStructuredFields']:
                if field['label'] == 'Main Health':
                    facts['mainHealth'] = field['value']
                elif field['label'] == 'Main Armor':
                    facts['mainArmor'] = {'Very Light': 1}.get(field['raw'])
                elif field['label'] == 'Max Rounds':
                    facts['maxRounds'] = field['value']
                elif field['label'] == 'Starting Rounds':
                    facts['startingRounds'] = field['value']
                elif field['label'] == 'Mags from Supply':
                    facts['magsFromSupply'] = field['value']
        rows[item['name']] = facts
    return rows


def heat_section(native, layouts, wiki, statuses):
    members = layouts.members('WeaponHeatComponentData')
    by_offset = {m['offset']: m for m in members}
    weapons = {}
    for name, path in HEAT_ENTITIES.items():
        resource = resource_of(native, path)
        raw = record_of(native, resource, 'WeaponHeatComponentData')
        weapons[name] = {'resource': resource, 'ownership': ownership(native, resource, 'WeaponHeatComponentData'),
            'values': {str(o): value_of(raw, by_offset[o]) for o in (80, 96, 104, 108, 116, 120, 124, 128, 132, 136,
                140, 144, 148, 152, 156, 172)}}
    all_rows = differential(native, layouts, 'WeaponHeatComponentData', (80,))
    zero = [row['owners'] for row in all_rows if row['values']['80'] == 0]
    status_rows = {row['nativeType']: row for row in statuses['statuses']}
    slots = statuses['damageSlots']
    sickle = HEAT_ENTITIES['LAS-17 Double-Edge Sickle']
    raw = record_of(native, resource_of(native, sickle), 'WeaponHeatComponentData')
    levels = []
    for index in range(3):
        base = index * 24
        status = i32(raw, base + 20)
        row = status_rows[status]
        tick = row['tickDamage']
        secondary = [slot for slot in slots[str(tick['damageType'])] if slot[0]]
        levels.append({'index': index + 1, 'thresholdOffset': base, 'threshold': f32(raw, base),
            'projectileTypeOffset': base + 4, 'projectileType': u32(raw, base + 4),
            'statusOffset': base + 20, 'statusType': status, 'status': row['semanticId'],
            'statusDuration': row['duration'], 'tickDamage': tick,
            'tickDamageStatuses': [{'statusType': s[0], 'status': status_rows[s[0]]['semanticId'], 'strength': s[1]}
                for s in secondary]})
    # Every settings row that could share the self-damage DamageInfo rows (projectiles, explosions, beams, arcs,
    # sprays, melee and statuses reference DamageInfo by type).
    tick_types = {level['tickDamage']['damageType'] for level in levels}
    tick_users = {t: [row['semanticId'] for row in statuses['statuses']
        if (row.get('tickDamage') or {}).get('damageType') == t] for t in tick_types}
    facts = wiki['LAS-17 Double-Edge Sickle']['facts']
    cool = facts['coolPerSecond']['value']
    base = weapons['LAS-17 Double-Edge Sickle']['values']
    return {'component': 'WeaponHeatComponentData', 'recordSize': 592,
        'members': [{'offset': m['offset'], 'storage': m['storage'], 'nameLength': m['nameLength'], 'type': m['type'],
            'struct': m['struct']} for m in members if m['offset'] < 196 or m['offset'] >= 484],
        'weapons': weapons,
        'doubleEdge': {'levels': levels, 'levelStruct': {'type': 'HeatLevelSetting', 'nameLength': 19, 'count': 3,
                'stride': 24, 'members': {'+0': 'f32 (name length 21): heat at which the level applies',
                    '+4': 'ProjectileType (15): the projectile fired at this level',
                    '+8': 'u64 (19)', '+16': 'u32 (17)', '+20': 'StatusEffectType (22): the status applied to the '
                        'wielder while firing at this level'}},
            'tickDamageUsers': tick_users,
            'ignition': {'mechanism': 'data-driven: level 3 applies status hotshot_laser_rifle_3, whose tick DamageInfo '
                    'carries status slot 1 = Fire (strength 10); no hard-coded heat callback',
                'threshold': levels[2]['threshold'], 'sameAsDamageThreshold': True},
            'overheatLock': {'offset': 80, 'storage': 'UINT8', 'nameLength': by_offset[80]['nameLength'],
                'value': raw[80], 'zeroOn': zero,
                'evidence': ['LAS-17 is the only weapon record with 0 (the other 0 is a shoulder camera with '
                    '10000 capacity that never overheats)', 'armory: "all overheating protections conveniently '
                    'removed"', 'wiki: "the heatsink does not need to be replaced upon reaching maximum heat"'],
                'unproven': 'that the game reads this byte as the lock-at-maximum-heat switch'},
            'published': {key: fact['value'] for key, fact in facts.items()},
            'coolMultipliers': {'native': [base['136'], base['132']], 'coolPerSecond': base['128'],
                'publishedTriple': cool,
                'exact': abs(base['128'] * base['136'] - cool[0]) < 1e-6 and abs(base['128'] * base['132'] - cool[2]) < 1e-6}},
        'laserCannon': {'values': weapons['LAS-98 Laser Cannon']['values'],
            'published': {key: fact['value'] for key, fact in wiki['LAS-98 Laser Cannon']['facts'].items()},
            'coolMultipliers': 'WeaponHeat +136 (1.5) and +132 (0.75) times the cool rate give the published '
                'triple 7.5 - 5 - 3.8 (and 12 - 8 - 6 on the LAS-17, 12.8 - 8.5 - 6.4 on the Scythe). Which '
                'condition selects each multiplier is not published (the LAS-17 page ties 1.5x to Extreme Cold but '
                'also calls the LAS-17 unaffected by Intense Heat while it carries the same 0.75); read-only.',
            'warmup': 'The published 0.5 s warmup (0.2 s on the Scythe and Rover) is stored in no common member of '
                'the laser components or their BeamSettings rows; not located.'}}


def beam_section(native, layouts, wiki):
    members = {m['offset']: m for m in layouts.members('BeamWeaponComponentData')}
    rows = []
    for name, path in BEAM_ENTITIES.items():
        resource = resource_of(native, path)
        raw = record_of(native, resource, 'BeamWeaponComponentData')
        published = wiki[name]['facts']['beamFireRate']['value']
        rows.append({'weapon': name, 'resource': resource, 'ownership': ownership(native, resource,
            'BeamWeaponComponentData'), 'fireRate': i32(raw, 104), 'fireMode': u32(raw, 100),
            'published': published, 'exact': i32(raw, 104) == published})
    if not all(row['exact'] for row in rows):
        raise ValueError('beam fire rate correlation failed: ' + json.dumps(rows))
    return {'component': 'BeamWeaponComponentData', 'member': {'offset': 104, 'storage': members[104]['storage'],
            'nameLength': members[104]['nameLength'], 'unit': 'rpm'},
        'fireModeMember': {'offset': 100, 'type': members[100]['type']},
        'correlations': rows,
        'decision': 'beam.fire_rate: exact published "Beam Fire Rate" on seven weapons, including the two '
            'non-60 values (LAS-13 300 rpm, 40-K 50 rpm); typed INT32, one owner per weapon.'}


def scythe_identity(native, wiki):
    """Why the LAS-5 Scythe has no authorable fields: its catalog identity is DUPLICATE. Records which of the two
    candidates the published heat data selects; the identity itself is not changed in this pass."""
    catalog = json.loads((ROOT / 'schemas/player_weapon_authoring_catalog.json').read_text())
    entry = next(w for w in catalog['weapons'] if w['name'] == 'LAS-5 Scythe')
    facts = {key: fact['value'] for key, fact in wiki['LAS-5 Scythe']['facts'].items()}
    rows = []
    for resource in entry['resources']:
        heat = record_of(native, resource, 'WeaponHeatComponentData')
        beam = record_of(native, resource, 'BeamWeaponComponentData')
        cool = f32(heat, 128)
        rows.append({'path': native.path(int(resource, 16)), 'heatCapacity': f32(heat, 96),
            'heatPerSecond': f32(heat, 120), 'coolPerSecond': cool, 'beamType': u32(beam, 0),
            # The page rounds to one decimal (8.5 x 1.5 = 12.75 is published as 12.8).
            'matchesPublishedHeat': abs(f32(heat, 120) - facts['heatPerSecond']) < 1e-6
                and abs(cool * f32(heat, 136) - facts['coolPerSecond'][0]) <= 0.05 + 1e-9
                and abs(cool - facts['coolPerSecond'][1]) < 1e-6
                and abs(cool * f32(heat, 132) - facts['coolPerSecond'][2]) <= 0.05 + 1e-9})
    if [row['matchesPublishedHeat'] for row in rows] != [True, False]:
        raise ValueError('LAS-5 Scythe candidate heat correlation changed: ' + json.dumps(rows))
    return {'catalogResolution': entry['resolution'], 'candidates': rows,
        'finding': ('Both candidates fire the same BeamSettings type, so the shared weapon mapper cannot separate them '
            'and the catalog blocks the Scythe (DUPLICATE). The published heat data (12.5 heat/s, cooling 12.8 - 8.5 - '
            '6.4) matches laser_rifle only; laser_rifle_charge (30 heat/s, cooling 15) is another weapon.'),
        'decision': ('Not changed in this pass: the weapon identity feeds about 45 generated catalogs (attachments, '
            'residency, ownership, composition). A reviewed disambiguation that selects laser_rifle is the follow-up.')}


def maxigun_section(native):
    resource = resource_of(native, MAXIGUN)
    data = native.component(resource, 'WeaponDataComponentData')
    raw = native.record('WeaponDataComponentData', data['record_index'])
    layout = native.typelib_module.layout(native.typelib, 'WeaponDataComponentData', structured=True)
    record_type = native.names.get(layout['members'][1]['type_hash'])
    text = MAXIGUN_REIMAGINED.read_bytes().decode('latin1') if MAXIGUN_REIMAGINED.exists() else ''
    source = {'path': 'Maxigun-Reimagined-v1.0/Addon/9ba626afa44a3aa3.patch_0',
        'sha256': sha(MAXIGUN_REIMAGINED.read_bytes()) if text else None, 'available': bool(text)}
    projectile_rows = []
    raw_settings = (entity_research.FILEDIVER / 'datalibrary/generated_projectile_settings.dl_bin').read_bytes()
    for group in groups(raw_settings):
        if group['type'] != dl_hash('ProjectileSettings'):
            continue
        offset, count = struct.unpack_from('<QQ', raw_settings, group['root'])
        for index in range(count):
            row = raw_settings[group['root'] + offset + index * 272:group['root'] + offset + (index + 1) * 272]
            if abs(f32(row, 32) - 820) < 0.5 and abs(f32(row, 36) - 11) < 0.01:
                projectile_rows.append(u32(row, 0))
    support = json.loads(SUPPORT_RESEARCH.read_text())
    weapon = next(w for w in support['weapons'] if w['catalogIdentity'] == 'M-1000 Maxigun')
    fired = weapon['runtimeAttacks'][0]
    modifiers = [{'offset': o, 'nameLength': n, 'value': f32(raw, o)} for o, n in
        ((60, 21), (64, 19), (68, 27), (72, 25), (76, 27), (80, 25))]
    everyone = {}
    for record in range(native.table('WeaponDataComponentData')[4]):
        body = native.record('WeaponDataComponentData', record)
        key = tuple(f32(body, o) for o in (60, 64))
        everyone[str(key)] = everyone.get(str(key), 0) + 1
    claims = [
        {'claim': 'fire rate selector low/medium/high 1000/2000/3000 (ProjectileWeapon +4/+8/+12)',
         'located': 'ProjectileWeaponComponent record of the Maxigun: +8 is the live rate, +4/+12 the X/Z slots',
         'classification': 'already_mapped (+8: weapon.fire_rate) / dormant (+4/+12)',
         'reason': 'The Maxigun binds no fire-rate selector, so the X/Z slots are never read; Reimagined binds one '
            'through the weapon-function members below. Selectors are not authored on wind-up weapons.'},
        {'claim': 'function_left 0, function_mode 2 (its +176/+180)', 'located': 'WeaponDataComponent +184/+188 '
            '(Reimagined addresses the record from +8)',
         'classification': 'already_mapped, blocked by policy (weapon_function.left/right)',
         'reason': 'Binding a selector on the wind-up Maxigun is unproven; Runtime blocks it with a reason.'},
        {'claim': 'recoil_h 0.5 / recoil_v 5.0 "internal multipliers" (its +52/+56)',
         'located': 'WeaponDataComponent +60/+64: members of the typed struct RecoilModifiers (member name '
            'recoil_modifiers), six f32 with name lengths 21/19/27/25/27/25',
         'classification': 'genuinely_missing',
         'reason': 'Typed recoil multipliers, 1.0 on 363 of 365 weapon records, never changed by an attachment '
            'delta; the first pair is exposed behind allow_unverified_effect with a live test.',
         'values': modifiers, 'distribution': everyone},
        {'claim': 'spread 6/6 (its +76/+80)', 'located': 'WeaponDataComponent +84/+88',
         'classification': 'already_mapped (weapon.horizontal_spread / weapon.vertical_spread)'},
        {'claim': 'sway 1.5 (its +96)', 'located': 'WeaponDataComponent +104', 'classification': 'already_mapped (weapon.sway)'},
        {'claim': 'ergonomics 10 (its +348)', 'located': 'WeaponDataComponent +356',
         'classification': 'already_mapped (weapon.ergonomics)'},
        {'claim': 'crosshair 3 (its +392)', 'located': 'WeaponDataComponent +400 CrosshairWeaponType',
         'classification': 'already_mapped (weapon.third_person_reticle)',
         'reason': 'Runtime authors the reticle through its reviewed on/off policy; the raw type 3 is not reproduced.'},
        {'claim': 'companion record: same edits plus mobile_fire 0 (its +0x173)',
         'located': 'the same Maxigun WeaponData record (Reimagined addresses it from +16): +387',
         'classification': 'already_mapped (weapon.stationary_while_firing)',
         'reason': 'Not a second record: both Reimagined layouts resolve to WeaponData record '
            + str(data['record_index']) + ' (one owner, the Maxigun).'},
        {'claim': 'wind up 0.3 / down 0.2', 'located': 'WeaponWindUpComponent +0/+4',
         'classification': 'already_mapped (windup.wind_up_seconds / windup.wind_down_seconds)'},
        {'claim': 'backpack capacity/start/refill 600', 'located': 'Maxigun backpack DepositComponent +0/+4/+8',
         'classification': 'already_mapped (deposit.capacity / start_amount / refill_amount, range 0..1023)'},
        {'claim': 'damage durable 36, AP 4, stagger 35, push 2, status 37 (stun_small) with buildup 0.2',
         'located': 'DamageInfo ' + str(fired['damageInfo']['recordType']) + ' (one projectile consumer)',
         'classification': 'already_mapped (damage.durable_damage, ap_*, stagger, push_force, status_1_type, '
            'status_1_strength)'},
        {'claim': 'projectile speed 820 -> 900, mass 11 -> 35',
         'located': 'Reimagined scans for a ProjectileSettings row at 820 m/s and 11 g; the Maxigun fires '
            'projectile type ' + str(fired['projectileType']) + ' at 920 m/s and 11 g (wiki M-1000 P, retained '
            'snapshot)', 'rowsAt820': projectile_rows,
         'classification': 'incorrect_target',
         'reason': 'The 820 m/s rows belong to other weapons; Runtime maps the fired row (projectile.velocity, '
            'projectile.mass).'},
        {'claim': 'calibre, penetration slowdown, raycast flag', 'classification': 'no_op',
         'reason': 'Reimagined writes them only when already equal to its targets.'},
        {'claim': 'muzzle effect (ProjectileWeapon +0xE0) and audio events',
         'classification': 'ignored_by_request', 'reason': 'Muzzle-flash, particle, material and audio edits are '
            'excluded from this pass.'}]
    return {'resource': resource, 'weaponData': native.ownership(data), 'recordType': record_type,
        'firedProjectile': {'type': fired['projectileType'], 'velocity': fired['resolvedFields']['projectile_velocity'],
            'mass': fired['resolvedFields']['projectile_mass']},
        'reference': source, 'claims': claims,
        'recoilModifiers': {'struct': 'RecoilModifiers', 'memberNameLength': 16, 'offset': 60, 'members': modifiers,
            'exposed': [{'offset': 60, 'field': 'weapon.recoil_multiplier_horizontal'},
                {'offset': 64, 'field': 'weapon.recoil_multiplier_vertical'}],
            'unexposed': 'the drift and climb pairs (+68..+80): no lead or published value separates them.'}}


def build():
    native = entity_research.Native()
    layouts = Layouts(native)
    entity = json.loads(ENTITY_RESEARCH.read_text())
    statuses = json.loads(STATUS_RESEARCH.read_text())
    wiki = wiki_facts()
    drones = drone_section(native, entity, drone_wiki(entity))
    for item in drones['drones']:
        if not all(item['correlation'].values()):
            raise ValueError(item['backpack'] + ': drone wiki correlation failed ' + json.dumps(item['correlation']))
    return {'schemaVersion': 1,
        'source': {'mode': 'offline', 'writes': 0, 'protectionChanges': 0, 'fixtureFallback': 'disabled',
            'entitiesSha256': build_profile.ENTITY_SHA256, 'typelibSha256': build_profile.TYPELIB_SHA256,
            'wiki': {name: {'revision': item['revision'], 'cache': item['cache']} for name, item in wiki.items()}},
        'shields': shield_section(native, layouts, entity, wiki),
        'directionalShield': directional_shield(native, entity, wiki),
        'warpPack': warp_section(native, layouts, entity, wiki),
        'hoverPack': hover_section(native, layouts, entity, wiki),
        'guardDogs': drones,
        'heat': heat_section(native, layouts, wiki, statuses),
        'beamFireRate': beam_section(native, layouts, wiki),
        'maxigun': maxigun_section(native),
        'scytheIdentity': scythe_identity(native, wiki)}


def main():
    report = build()
    OUTPUT.write_text(json.dumps(report, indent=1, allow_nan=False) + '\n', newline='\n')
    print(json.dumps({'shieldDecisions': sorted(report['shields']['decisions']),
        'warp': sorted(report['warpPack']['decisions']), 'drones': len(report['guardDogs']['drones']),
        'beamRates': [row['fireRate'] for row in report['beamFireRate']['correlations']],
        'las17Levels': [(l['threshold'], l['status']) for l in report['heat']['doubleEdge']['levels']]}))


if __name__ == '__main__':
    main()
