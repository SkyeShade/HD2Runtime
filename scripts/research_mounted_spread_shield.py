"""Mounted-weapon spread and the EXO-55 Breakthrough shield arm. Read-only research.

Question (user report, 0.30.4): "Breacher flak gun spread and the shield stats (if the shield stats are even possible)".

1. Spread. Player, support and sentry weapons expose WeaponData +84 / +88 (weapon.horizontal_spread /
   weapon.vertical_spread). Do vehicle-mounted weapons read the same members when they fire?
   - WeaponData's post-create callback (0x54026D -> 0x752370) builds every WeaponData instance from its type record
     once, at creation: the spread pair (type +84/+88) lands at instance +0x58 (x the instance's own multipliers).
     The callback belongs to the component, not to a kind of wielder.
   - The projectile shot (0x615940) resolves the firing weapon entity's WeaponData instance through the WeaponData
     component map (game+0x3326CE0, records +0x58, 0x3F0 each) and passes instance +0x58 to 0x759740 on every shot,
     which turns the shot by up to half of each width (milliradians). No branch tests what wields the weapon.
   - The fire routine (0x6128B0) calls the shot once per pellet for plain projectiles: it reads the projectile row
     (0x11EC7C0, the ProjectileSettings table) and loops pellet_count (+28) times (0x614445..0x6144F7), so a pellet
     weapon (the Breakthrough's 40-pellet flak round) spreads every pellet by the WeaponData widths.
   - 0x615940 is called only from 0x6128B0, and no function that touches the ProjectileWeapon component spawns a
     projectile row itself (0x13A9830): every ProjectileWeapon shot - player, sentry or mounted - reaches the read.
   - Exact published values: the wiki's spread of every published mounted weapon equals its WeaponData +84/+88.
   Mounts that fire a spray, beam or arc keep their WeaponData spread unexposed (the sentry rule: their attack path's
   read is not shown).
2. The Breakthrough's left mount (slot 0, 'left_gun') holds combat_walker_shield: a wieldable unit with its own
   HealthComponent, WeaponData, MeleeShield and AbilityWeapon (the shield bash), no ProjectileWeapon/Spray/Beam/Arc
   and no ShieldComponent - a physical shield arm, not an energy shield. Its HealthComponent (one owner) is exactly the wiki's two anatomy rows: zone 0 "ShieldArm" (actors
   damageable_base, damageable_arm and one unnamed; armor 3, health -1 = the main pool of 800, durable 80 %,
   counts toward main) and zone 1 "Shield" (actor damageable_shield; armor 4, its own 5000 health, durable 80 %, does
   not count toward main). The zone lookup (game.dll 0x922060, research/ballistic-shield) picks the zone that lists
   the hit actor; the default zone (+280) is only the fallback for an unlisted actor.

Nothing here writes memory. Requires the research-only packages capstone and numpy.
Output: research/mounted-spread-shield-F5FEE03DCFDB.json. `--check` compares with the committed output.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402
import research_entity_authoring as entity_research  # noqa: E402
from scan import xref  # noqa: E402

OUTPUT = ROOT / 'research/mounted-spread-shield-F5FEE03DCFDB.json'
VEHICLE_WEAPONS = ROOT / 'research/vehicle-weapons-F5FEE03DCFDB.json'
WIKI = ROOT.parent / 'HD2WikiImporter/output/wiki_vehicle_stratagems.json'
WD, PW, HC = 'WeaponDataComponentData', 'ProjectileWeaponComponentData', 'HealthComponentData'
ATTACKS = {'ProjectileWeaponComponentData': 'projectile', 'SprayWeaponComponentData': 'spray',
    'BeamWeaponComponentData': 'beam', 'ArcWeaponComponentData': 'arc'}
SHOT, FIRE, SPREAD_TURN, SPAWN_ROW, PW_MANAGER = 0x615940, 0x6128B0, 0x759740, 0x13A9830, 0x33266D8
SHIELD_PATH = 'content/fac_helldivers/vehicles/combat_walker_shield/combat_walker_shield'
SHIELD_VEHICLE, SHIELD_SLOT = 'EXO-55 Breakthrough Exosuit', 0
# Hit actors of the shield's zones that the thin-hash dictionary does not name; named by hashing these candidates.
ACTOR_NAMES = ('damageable_base', 'damageable_arm', 'damageable_shield')
ZONES, ZONE_BASE, ZONE_STRIDE, DEFAULT_ZONE, ZONE_ACTORS = 38, 520, 552, 64, 456
# DamageableZoneInfo members (offset in the zone, storage): research/ballistic-shield ZONE_MEMBERS.
ZONE_MEMBERS = {'nameHash': (96, 'u32'), 'durableResistance': (204, 'f32'), 'armor': (216, 'u32'),
    'health': (232, 'i32'), 'affectsMainHealth': (248, 'f32'), 'affectedByExplosions': (323, 'u8'),
    'explosiveDamagePercentage': (324, 'f32')}

PINS = {
    'instanceBuild': [
        (0x54026D, 'jmp 0x752370', 'WeaponData\'s post-create callback builds the instance (every WeaponData owner)'),
        (0x75263D, 'movsd xmm0, qword ptr [r15 + 0x54]', 'type +84/+88 (the spread pair) ...'),
        (0x752643, 'movsd qword ptr [rbp + 0x58], xmm0', '... into instance +0x58 (then x the instance multipliers)'),
    ],
    'shotReadsInstance': [
        (0x615976, 'mov rbx, qword ptr [rip + 0x2d11363]', 'the WeaponData component (game+0x3326CE0)'),
        (0x6159AE, 'mov r13, qword ptr [rax + rcx*8]', 'the firing weapon'),
        (0x6159C7, 'mov eax, dword ptr [r13 + 8]', 'its entity id, looked up in the WeaponData map (+0x30..+0x40)'),
        (0x615A30, 'imul rdi, rcx, 0x3f0', 'instance index x 0x3F0 ...'),
        (0x615A3A, 'add rdi, qword ptr [rbx + 0x58]', '... + the instance records: this weapon\'s own WeaponData instance'),
        (0x615BAB, 'lea r9, [rdi + 0x58]', 'every shot: the instance spread pair ...'),
        (0x615BBA, 'call 0x759740', '... turns the shot by up to half of each width (milliradians)'),
    ],
    'pellets': [
        (0x6143CD, 'cmp qword ptr [rax + 0x28], 0', 'ProjectileWeapon +40 (ProjectileEntity) set: one shot ...'),
        (0x61443B, 'call 0x615940', '... (the entity path, research/wasp-rocket)'),
        (0x614445, 'mov ecx, dword ptr [rbp - 0x68]', 'plain projectiles: the shot\'s projectile type ...'),
        (0x61444B, 'call 0x11ec7c0', '... its ProjectileSettings row ...'),
        (0x614450, 'cmp dword ptr [rax + 0x1c], 0', '... pellet_count (+28) ...'),
        (0x6144E3, 'call 0x615940', '... one shot per pellet, each turned by the spread'),
        (0x6144F3, 'cmp r14d, dword ptr [rax + 0x1c]', 'loop until pellet_count'),
        (0x11EC7CE, 'lea rcx, [rip + 0x25dae9b]', 'the ProjectileSettings row table (0x37C7670)'),
        (0x11EC7D5, 'mov rax, qword ptr [rcx + rax*8]', 'row of the type'),
    ],
}
RIP_TARGETS = {0x615976: 0x3326CE0, 0x11EC7CE: 0x37C7670}


def hexid(value: int) -> str:
    return f'0x{value:016X}'


def f32(raw, at):
    return round(struct.unpack_from('<f', raw, at)[0], 6)


def structural(img) -> dict:
    """Who reaches the spread read: callers of the shot and the fire routine, and the absence of any other
    ProjectileWeapon-side projectile spawn."""
    shot_callers = sorted({img.root(site) for site in img.calls_to(SHOT)})
    fire_callers = sorted({img.root(site) for site in img.calls_to(FIRE)})
    turn_callers = sorted({img.root(site) for site in img.calls_to(SPREAD_TURN)})
    spawners = {img.root(site) for site in img.calls_to(SPAWN_ROW)}
    pw_functions = {img.root(ins.address) for ins in img.references(PW_MANAGER)}
    bypass = sorted(f for f in pw_functions if f in spawners)
    if shot_callers != [FIRE] or bypass:
        raise ValueError('the projectile shot is reached another way: %r %r' % (shot_callers, bypass))
    if SHOT not in turn_callers:
        raise ValueError('the shot no longer applies the spread')
    return {'shotCallers': ['0x%X' % f for f in shot_callers], 'fireRoutineCallers': ['0x%X' % f for f in fire_callers],
        'spreadTurnCallers': ['0x%X' % f for f in turn_callers],
        'projectileWeaponFunctions': len(pw_functions), 'projectileWeaponFunctionsSpawningRowsDirectly': [],
        'note': ('0x615940 (the shot) is called only by the fire routine 0x6128B0; none of the %d functions that touch '
            'the ProjectileWeapon component (game+0x33266D8) spawns a projectile row (0x13A9830) itself. The two other '
            'callers of 0x759740 are other fire paths (not ProjectileWeapon shots) and are not used here.'
            % len(pw_functions))}


def published_spreads() -> dict:
    """Vehicle name -> [(wiki weapon name, [h, v])] from the scraped wiki vehicle pages."""
    if not WIKI.is_file():
        return {}
    items = json.loads(WIKI.read_text(encoding='utf-8'))
    items = items['stratagems'] if isinstance(items, dict) else items
    out = {}
    for item in items:
        for node in (item.get('graph') or {}).get('nodes', []):
            common = ((node.get('weapon') or {}).get('common') or {})
            spread = common.get('spread')
            if spread:
                values = [float(v) for v in re.findall(r'\[(-?[\d.]+)\]', spread)]
                out.setdefault(item['name'], []).append({'name': common.get('name') or node.get('name'),
                    'spread': values})
    return out


def zone_values(raw, base) -> dict:
    out = {}
    for key, (offset, storage) in ZONE_MEMBERS.items():
        at = base + offset
        out[key] = (struct.unpack_from('<I', raw, at)[0] if storage == 'u32' else
            struct.unpack_from('<i', raw, at)[0] if storage == 'i32' else raw[at] if storage == 'u8' else f32(raw, at))
        out.setdefault('recordOffsets', {})[key] = at
    return out


def shield(native, wiki) -> dict:
    resource = native.probe.resource_hash(SHIELD_PATH)
    key = hexid(resource)
    report = native.report(key)
    components = sorted(c['name'] for c in report['components'] if c['name'] and c['resolved'])
    if not {HC, WD, 'MeleeShieldComponentData', 'WieldableComponentData'} <= set(components) or any(
            c in components for c in ('ShieldComponentData', 'ShieldControllerComponentData', *ATTACKS)):
        raise ValueError('combat_walker_shield component set changed: %r' % components)
    health = native.component(key, HC)
    raw = native.record(HC, health['record_index'])
    owners = native.owners(HC).get(health['record_index'], [])
    if owners != [resource]:
        raise ValueError('the shield HealthComponent record is shared')
    names = {native.probe.resource_hash(name) >> 32: name for name in ACTOR_NAMES}
    zones = []
    for index in range(ZONES):
        base = ZONE_BASE + index * ZONE_STRIDE
        if not struct.unpack_from('<I', raw, base + 96)[0]:
            continue
        zone = dict(zone_values(raw, base), index=index, zoneOffset=base)
        actors = [v for v in struct.unpack_from('<24I', raw, base + ZONE_ACTORS) if v]
        zone['actors'] = [native.thin_name(v) or names.get(v) or '0x%08X' % v for v in actors]
        zone['nameHash'] = '0x%08X' % zone['nameHash']
        zones.append(zone)
    default = zone_values(raw, DEFAULT_ZONE)
    default.pop('nameHash')
    arm, plate = zones if len(zones) == 2 else (None, None)
    if not (arm and plate and arm['health'] == -1 and arm['affectsMainHealth'] == 1.0 and plate['health'] > 0
            and plate['affectsMainHealth'] == 0.0 and plate['actors'] == ['damageable_shield']
            and 'damageable_arm' in arm['actors']):
        raise ValueError('the shield zone anatomy changed')
    main = struct.unpack_from('<i', raw, 0)[0]
    anatomy = {}
    for node in wiki:
        anatomy[node['name']] = node
    checks = {
        'ShieldArm health = main health': [main, (anatomy.get('ShieldArm') or {}).get('health')],
        'ShieldArm armor = zone 0 armor': [arm['armor'], (anatomy.get('ShieldArm') or {}).get('armor')],
        'ShieldArm durable 80 % = zone 0 durable resistance': [arm['durableResistance'],
            (anatomy.get('ShieldArm') or {}).get('durable')],
        'Shield health = zone 1 health': [plate['health'], (anatomy.get('Shield') or {}).get('health')],
        'Shield armor = zone 1 armor': [plate['armor'], (anatomy.get('Shield') or {}).get('armor')],
        'Shield durable 80 % = zone 1 durable resistance': [plate['durableResistance'],
            (anatomy.get('Shield') or {}).get('durable')],
        'Shield overflow "No" = zone 1 does not count toward main': [plate['affectsMainHealth'],
            0.0 if (anatomy.get('Shield') or {}).get('overflowCap') == 'No' else None],
    }
    exact = {label: {'native': pair[0], 'published': pair[1],
        'exact': pair[1] is not None and abs(pair[0] - pair[1]) < 1e-6} for label, pair in checks.items()}
    return {'vehicle': SHIELD_VEHICLE, 'slot': SHIELD_SLOT, 'mount': 'left_gun', 'resource': key, 'path': SHIELD_PATH,
        'components': components, 'shieldComponent': False,
        'health': {'recordIndex': health['record_index'], 'indexRow': health['index_row'], 'ownerCount': 1,
            'mainHealth': main, 'defaultZone': default, 'zones': zones},
        'publishedChecks': exact,
        'reading': ('A physical shield arm with two damage zones: hits on the arm or its base resolve to zone 0 '
            '(armor 3; damage goes to the main pool, 800), hits on the plate to zone 1 (armor 4, its own 5000 '
            'health, not counted toward the arm). The default zone (+280) is only the fallback for an actor no zone '
            'lists. No ShieldComponent: no capacity, recharge delay or recharge rate exists for this shield.'),
        'lifecycle': ('The health instance copies the armor values when the entity spawns (research/ballistic-shield '
            '0x12A2334/0x12A2368): an edit reaches shield arms of Exosuits called in after it.')}


def wiki_anatomy() -> list:
    if not WIKI.is_file():
        return []
    items = json.loads(WIKI.read_text(encoding='utf-8'))
    items = items['stratagems'] if isinstance(items, dict) else items
    item = next(i for i in items if i.get('name') == SHIELD_VEHICLE)
    out = []
    for node in item['graph']['nodes']:
        if node.get('id') in ('component.shieldarm', 'component.shield'):
            entity = node['entity']
            out.append({'name': node['name'], 'health': entity['mainHealth']['value'],
                'armor': entity['mainArmor']['value'], 'durable': entity['durability']['value'],
                'overflowCap': entity['overflowCap']})
    return out


def build() -> dict:
    native = entity_research.Native()
    img = xref.CodeImage.from_snapshot()
    if img.sha256.upper() != build_profile.ACTIVE['gameDllSha256'].upper():
        raise ValueError('snapshot game.dll is not the profile build')
    code = {}
    for group, rows in PINS.items():
        code[group] = []
        for rva, asm, role in rows:
            entry = img.pin(rva, role, asm)
            if rva in RIP_TARGETS and entry.get('ripTarget') != RIP_TARGETS[rva]:
                raise ValueError('rip target at %x changed' % rva)
            entry = {k: ('0x%X' % v if k in ('rva', 'ripTarget', 'branchTarget') else v) for k, v in entry.items()}
            code[group].append(entry)
    research = json.loads(VEHICLE_WEAPONS.read_text())
    published = published_spreads()
    wd_owners = native.owners(WD)
    mounts = []
    for vehicle in research['vehicles']:
        native_values = []
        for slot in vehicle['slots']:
            own = slot['ownership']
            if WD not in own:
                continue
            identity = own[WD]
            raw = native.record(WD, identity['recordIndex'])
            resource = int(slot['path'], 16)
            if resource not in wd_owners.get(identity['recordIndex'], []):
                raise ValueError('%s slot %d: WeaponData identity diverged' % (vehicle['name'], slot['slot']))
            attack = next((family for component, family in ATTACKS.items() if component in own), None)
            spread = [f32(raw, 84), f32(raw, 88)]
            native_values.append(spread)
            label = slot.get('name') or slot.get('attachNodeName') or 'slot_%d' % slot['slot']
            mounts.append({'weapon': vehicle['name'] + ' / ' + label, 'vehicle': vehicle['name'], 'slot': slot['slot'],
                'resource': slot['path'], 'attack': attack, 'isWeapon': slot['isWeapon'],
                'weaponData': {k: identity[k] for k in ('recordIndex', 'indexRow', 'ownerCount')},
                'spread': spread, 'readOnShot': attack == 'projectile',
                'reason': None if attack == 'projectile' else
                    'No attack component: nothing fires through this record.' if attack is None else
                    'A %s attack: the projectile shot\'s read (0x615BAB) is not on its path; its WeaponData spread '
                    'stays unexposed (the sentry rule).' % attack})
        for entry in published.get(vehicle['name'], []):
            entry['matchesNative'] = entry['spread'] in native_values
    mismatched = [(v, e) for v, items in published.items() for e in items if not e['matchesNative']]
    if mismatched:
        raise ValueError('published mounted spread without a native match: %r' % mismatched)
    return {'schemaVersion': 1, 'build': build_profile.BUILD_ID, 'gameDllSha256': img.sha256.upper(),
        'entitiesSha256': entity_research.ENTITY_SHA256,
        'question': 'Do vehicle-mounted weapons read WeaponData spread like player weapons; what is the EXO-55 '
            'Breakthrough left mount and which of its stats are editable?',
        'code': code, 'structural': structural(img),
        'spread': {'members': {'horizontal': 84, 'vertical': 88}, 'unit': 'milliradians, full width',
            'lifecycle': 'copied into the weapon instance when the mounted weapon entity is created (with its '
                'vehicle): an edit reaches vehicles called in after it; one already in the world keeps its copy',
            'mounts': mounts, 'published': published,
            'publishedExact': sum(1 for items in published.values() for e in items if e['matchesNative'])},
        'shield': shield(native, wiki_anatomy()),
        'notCovered': [
            'Recoil (WeaponData +0/+4/+28/+32): each shot kicks the wielder slot\'s aim (0x784CE2); which aim a '
            'mounted weapon\'s wielder is (the Exosuit, a seat or the vehicle) is not traced, so mounted recoil stays '
            'unexposed.',
            'Sway (+104) and ergonomics (+356): no read on the mounted fire path is shown.',
            'The shield arm\'s zone 0 armor (3) and the default-zone armor (+280): the mount target carries one zone '
            '(the plate); the arm zone needs a zone sub-target and the default zone is only a fallback.']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    result = build()
    text = json.dumps(result, indent=1) + '\n'
    if args.check:
        if OUTPUT.read_text(encoding='utf-8') != text:
            raise SystemExit('stale: ' + str(OUTPUT))
        print('up to date')
        return
    OUTPUT.write_text(text, encoding='utf-8', newline='\n')
    print(json.dumps({'publishedExact': result['spread']['publishedExact'],
        'shieldChecks': result['shield']['publishedChecks'], 'structural': result['structural']}, indent=1))


if __name__ == '__main__':
    main()
