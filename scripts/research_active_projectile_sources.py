"""Active projectile source of every projectile weapon. Read-only research.

Live controls (schemas/live_evidence.json, session attack-output-host-path-2026-09-29):

- positive: SMG-32 Reprimand, ProjectileWeapon +0 -> LAS-58 Talon projectile: the Reprimand fired Talon bolts.
- negative: AR-23 Liberator, the same guarded write of ProjectileWeapon +0 -> Talon: the write landed and the
  Liberator kept firing its own bullet.

Question: which projectile reference does a shot consume, and why does the same member work on one weapon and not
the other? A weapon is spawned from its entity components plus the entity deltas of its customization. Each
WeaponCustomizationComponentData default (slot, option) names a WeaponCustomizableItem; its AddPath keys a
ComponentEntityDeltaStorage entry that patches component members (component index, member offset, bytes). Ammunition
items (slot 6) patch ProjectileWeaponComponentData +0 (ProjType) itself. On a weapon whose default customization
carries such an item, the delta overwrites the base member when the weapon is built: the base member is dormant and
the ammunition delta is the active source. That is the Liberator (RIFLE 5,5x50mm. FULL METAL JACKET patches +0 to
its bullet). The Reprimand has no ammunition slot and no delta on +0, so its base member is what it fires.

Every ProjectileType-typed member reachable from a weapon is enumerated from the pinned type library, and every
customization delta that patches one is decoded, for defaults and for the runtime unlock lists (options the weapon
can equip). Each projectile weapon is classified:

  ACTIVE_DIRECT        no default or equippable customization patches any projectile member and no other selector
                       (magazine pattern, rounds, charge, heat, spawned entity, weapon function) exists: the base
                       ProjectileWeapon +0 is the fired projectile (the Reprimand's structure, live-proven).
  INDIRECT             exactly one default ammunition item patches +0 and nothing else selects a projectile: its
                       delta data is the active source; the base member is dormant.
  DORMANT_OR_METADATA  the base member is overridden, but the overriding source is not uniquely identified.
  AMBIGUOUS            the active projectile depends on runtime state not proven offline (an equippable option that
                       patches a projectile member, or a weapon function that switches projectile).
  BLOCKED              another native selector owns the projectile (magazine pattern, rounds ammo types, charge or
                       heat levels, or a spawned entity), or the weapon has no projectile family.

No native reader of the firing path was traced: the classification rests on the decoded data path plus the two
live controls, and it is published with that proof basis.

Output: research/active-projectile-sources-F5FEE03DCFDB.json.
"""
from __future__ import annotations

import collections
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_attack_outputs as attack_outputs  # noqa: E402
from research_magazine_attachments import DATALIB, DELTAS_SHA, customization_items, entity_deltas, sha  # noqa: E402

OUTPUT = ROOT / 'research/active-projectile-sources-F5FEE03DCFDB.json'
SENTRY_OUTPUT = ROOT / 'research/sentry-projectile-hosts-F5FEE03DCFDB.json'
UNLOCK_LISTS = ROOT / 'research/attachment-unlock-lists-F5FEE03DCFDB.json'
DEFENSIVE = ROOT / 'research/defensive-stratagem-runtime-F5FEE03DCFDB.json'
OPTIONS = ROOT / 'sdk/AttachmentOptionCapabilities.json'
AMMUNITION_SLOT = 6
COMPONENT_INDEX = {'WeaponMagazineComponentData': 5, 'WeaponRoundsComponentData': 117,
    'WeaponCustomizationComponentData': 271, 'ProjectileWeaponComponentData': 321}
# ProjectileType members per component (offsets proven against the pinned type library below).
PROJECTILE_MEMBERS = {'ProjectileWeaponComponentData': {0: 'ProjType', 576: 'WeaponFunctionProjectileType'},
    'WeaponRoundsComponentData': {64: 'PrimaryProjectileType', 68: 'AlternateProjectileType'},
    'WeaponMagazineComponentData': {**{4 + 4 * i: f'Projectiles[{i}]' for i in range(32)}, 132: 'FirstProjectile'},
    'WeaponChargeComponentData': {}, 'WeaponHeatComponentData': {}}
PROJECTILE_ENTITY = 40  # ProjectileWeaponComponent ProjectileEntity (u64): spawn an entity instead of a projectile
FIRE_RATE = (4, 16)     # ProjectileWeaponComponent RoundsPerMinute vec3 (+8 is the published weapon.fire_rate)
LIVE_CONTROLS = {'SMG-32 Reprimand': {'result': 'LIVE_PASS', 'write': 'ProjectileWeapon +0 -> LAS-58 Talon',
        'observation': 'The Reprimand fired Talon bolts with correct visuals and function.'},
    'AR-23 Liberator': {'result': 'LIVE_FAIL', 'write': 'ProjectileWeapon +0 -> LAS-58 Talon',
        'observation': 'The write landed; the Liberator kept firing its own bullet.'}}


def prove_layout(native):
    """Component delta indices and every ProjectileType member offset, from the pinned library."""
    for name, index in COMPONENT_INDEX.items():
        found = native.probe.find_component(native.entities, name)
        if struct.unpack_from('<I', native.entities, found[4] - 4)[0] != index:
            raise ValueError(name + ' component index changed')
    projectile_hash = native.probe.dl_hash('ProjectileType')

    def flatten(type_ref, base=0):
        """(offset, array length) of every ProjectileType leaf, through nested structs and inline arrays."""
        for m in native.typelib_module.layout(native.typelib, type_ref, structured=True)['members']:
            if m['type_hash'] == projectile_hash:
                yield base + m['offset64'], m['array_or_bits']
            elif m.get('storage') == 'STRUCT':
                count = m['array_or_bits'] if m['atom'] == 'INLINE_ARRAY' else 1
                for k in range(count):
                    yield from flatten(m['type_hash'], base + m['offset64'] + k * (m['size64'] // count))

    members = {}
    for name in PROJECTILE_MEMBERS:
        found = sorted(flatten(name.removesuffix('Data')))
        members[name] = {'offsets': [offset for offset, _ in found],
            'arrays': {str(offset): count for offset, count in found if count}}
    expected = {'ProjectileWeaponComponentData': [0, 576], 'WeaponRoundsComponentData': [64, 68],
        'WeaponMagazineComponentData': [4, 132]}
    for name, offsets in expected.items():
        if members[name]['offsets'] != offsets:
            raise ValueError(f'{name} ProjectileType members changed: {members[name]}')
    if members['WeaponMagazineComponentData']['arrays'].get('4') != 32:
        raise ValueError('WeaponMagazineComponent pattern is no longer ProjectileType[32]')
    for name in ('WeaponChargeComponentData', 'WeaponHeatComponentData'):
        PROJECTILE_MEMBERS[name] = {offset: 'ProjType' for offset in members[name]['offsets']}
    layout = {m['offset64']: m for m in native.typelib_module.layout(native.typelib, 'ProjectileWeaponComponent',
        structured=True)['members']}
    if layout[PROJECTILE_ENTITY]['size64'] != 8 or layout[4]['size64'] != 12:
        raise ValueError('ProjectileWeaponComponent ProjectileEntity / RoundsPerMinute layout changed')
    return members


def projectile_patches(delta, names):
    """Delta entries that patch a ProjectileType member (or the spawned entity / fire rate)."""
    out = []
    for entry in (delta or {}).get('entries', []):
        component = names.get(entry['component'])
        members = PROJECTILE_MEMBERS.get(component, {})
        for at in range(0, entry['size'], 4):
            member = members.get(entry['offset'] + at)
            if member:
                out.append({'component': component, 'offset': entry['offset'] + at, 'member': member,
                    'value': struct.unpack_from('<I', entry['bytes'], at)[0], 'dataOffset': entry['dataOffset'] + at,
                    'entrySize': entry['size'], 'ownRow': entry['size'] == 4})
        if component == 'ProjectileWeaponComponentData' and entry['offset'] < PROJECTILE_ENTITY + 8 \
                and entry['offset'] + entry['size'] > PROJECTILE_ENTITY:
            out.append({'component': component, 'offset': PROJECTILE_ENTITY, 'member': 'ProjectileEntity',
                'value': None, 'dataOffset': entry['dataOffset'], 'entrySize': entry['size'], 'ownRow': False})
    return out


def other_patches(delta, names):
    return sorted({f"{names.get(e['component'], e['component'])}+{e['offset']}/{e['size']}"
        for e in (delta or {}).get('entries', [])})


def attack_sources(by_name):
    """The member behind every catalogued player attack.<role>.projectile field, classified like the weapons.

    A ProjectileWeapon +0 backing takes its weapon's status. A WeaponRounds +64 / +68 backing (rounds-fed weapons) is
    the fired projectile only when nothing else carries one: no customization patches that rounds member (default or
    equippable), ProjectileWeapon +0 is empty and unpatched, and no other selector exists. When +0 also carries a
    projectile, which member a shot consumes is not proven offline."""
    composition = json.loads((ROOT / 'schemas/player_weapon_composition_catalog.json').read_text())['weapons']
    rows = []
    for name, graph in sorted(composition.items()):
        for attack in graph['attacks']:
            backing = attack.get('targetBacking')
            if not backing:
                continue
            entry = by_name.get(name) or {}
            row = {'weapon': name, 'role': attack['role'],
                'backing': backing['component'].removesuffix('ComponentData') + ' +' + str(backing['offset']),
                'baseValue': attack['projectileType'], 'compatibilityClass': attack['compatibilityClass'],
                'previouslyWritable': attack['writableReferenceSwap']}
            if not entry:
                status, reason, mechanism = 'AMBIGUOUS', ('The weapon identity does not resolve uniquely, so its '
                    'customization and active source are not classified.'), None
            elif backing['component'] == 'ProjectileWeaponComponentData':
                status, reason = entry['status'], entry['reason']
                mechanism = {'ACTIVE_DIRECT': 'component', 'INDIRECT': 'ammunition'}.get(status)
            else:
                member = 'PrimaryProjectileType' if backing['offset'] == 64 else 'AlternateProjectileType'
                defaults = entry.get('defaultCustomization', [])
                patched = [(d['item'], p['value']) for d in defaults for p in d['projectilePatches']
                    if p['member'] == member]
                base_patched = [d['item'] for d in defaults for p in d['projectilePatches'] if p['member'] == 'ProjType']
                equippable = [o['item'] for o in entry.get('equippableProjectileOptions', [])
                    if any(p['member'] == member for p in o['projectilePatches'])]
                others = [s for s in entry.get('selectors', []) if not s.startswith('WeaponRounds')]
                mechanism = None
                if others:
                    status, reason = 'BLOCKED', 'Another native selector owns the fired projectile: ' + '; '.join(others) + '.'
                elif len(patched) > 1 or equippable:
                    status, reason = 'AMBIGUOUS', ('Customization options patch WeaponRounds ' + member + ' ('
                        + ', '.join(sorted({i for i, _ in patched} | set(equippable))) + '); the fired projectile '
                        'depends on the equipped option.')
                elif patched:
                    status, reason = 'INDIRECT', ('The default ammunition item ' + patched[0][0] + ' patches WeaponRounds '
                        + member + ' when the weapon is built, so the base member is dormant. The rounds ammunition '
                        'source is not offered for writes.')
                elif entry.get('base', {}).get('projType') or base_patched:
                    status, reason = 'AMBIGUOUS', ('Both WeaponRounds ' + member + ' and ProjectileWeapon +0 carry a '
                        'projectile' + (' (+0 patched by ' + base_patched[0] + ')' if base_patched else '') + '; which '
                        'member a shot consumes is not proven offline.')
                    # Whichever member is consumed, a shot fires the same row when every candidate names it.
                    values = {attack['projectileType'], entry['base']['projType']} | {p['value'] for d in defaults
                        for p in d['projectilePatches'] if p['member'] == 'ProjType'}
                    row['candidatesAgree'] = len(values - {0}) == 1
                else:
                    status, reason, mechanism = 'ACTIVE_DIRECT', ('WeaponRounds ' + member + ' is the only projectile '
                        'the weapon carries (ProjectileWeapon +0 is empty) and no customization patches it.'), 'component'
            row.update(status=status, reason=reason, mechanism=mechanism)
            rows.append(row)
    return rows


def build():
    native = attack_outputs.entity_research.Native()
    members = prove_layout(native)
    names = {index: name for name, index in COMPONENT_INDEX.items()}
    deltas_file = (DATALIB / 'generated_entity_deltas.dl_bin').read_bytes()
    if sha(deltas_file) != DELTAS_SHA:
        raise ValueError('pinned entity delta table changed')
    items = customization_items((DATALIB / 'generated_weapon_customization_settings.dl_bin').read_bytes())
    deltas, _ = entity_deltas(deltas_file)
    by_id = {item['optionId']: item for item in items}
    by_add = {item['addPath']: item for item in items}
    unlock = {entry['weapon']: entry for entry in json.loads(UNLOCK_LISTS.read_text())['weapons'] if entry['weapon']}
    ui_categories = {w['weapon']: sorted(c['category'] for c in w.get('categories', []))
        for w in json.loads(OPTIONS.read_text())['weapons']}

    # Every customization item that patches a projectile member, whoever equips it.
    patching = {}
    for item in items:
        patches = projectile_patches(deltas.get(item['addPath']), names)
        if patches:
            patching[item['addPath']] = patches

    weapons, default_users = [], collections.defaultdict(list)
    listed_users = collections.defaultdict(list)
    def classify(name, kind, resource):
        """One host's fired-projectile classification (its entity components, customization defaults and unlock
        list), or None when it has no ProjectileWeapon component."""
        components = {c['name']: c for c in native.report(resource)['components'] if c['resolved'] and c['name']}
        if 'ProjectileWeaponComponentData' not in components:
            return None
        pw = native.record('ProjectileWeaponComponentData', components['ProjectileWeaponComponentData']['record_index'])
        entry = {'weapon': name, 'kind': kind, 'resource': resource,
            'components': sorted(c.removesuffix('ComponentData') for c in components
                if c.startswith('Weapon') or c == 'ProjectileWeaponComponentData'),
            'base': {'projType': struct.unpack_from('<I', pw, 0)[0],
                'weaponFunctionProjectileType': struct.unpack_from('<I', pw, 576)[0],
                'projectileEntity': struct.unpack_from('<Q', pw, PROJECTILE_ENTITY)[0] != 0,
                'fireRate': round(struct.unpack_from('<f', pw, 8)[0], 3)}}
        selectors = []
        if 'WeaponMagazineComponentData' in components:
            magazine = native.record('WeaponMagazineComponentData',
                components['WeaponMagazineComponentData']['record_index'])
            pattern = [v for v in struct.unpack_from('<32I', magazine, 4) if v]
            first = struct.unpack_from('<I', magazine, 132)[0]
            entry['magazinePattern'] = {'entries': len(pattern), 'firstProjectile': first}
            if pattern or first:
                selectors.append('magazine pattern (WeaponMagazine Projectiles[32] / FirstProjectile)')
        if 'WeaponRoundsComponentData' in components:
            rounds = native.record('WeaponRoundsComponentData', components['WeaponRoundsComponentData']['record_index'])
            entry['rounds'] = list(struct.unpack_from('<II', rounds, 64))
            selectors.append('WeaponRounds ammo types (primary / alternate magazine projectile)')
        for component in ('WeaponChargeComponentData', 'WeaponHeatComponentData'):
            if component in components:
                levels = native.record(component, components[component]['record_index'])
                values = [struct.unpack_from('<I', levels, offset)[0] for offset in PROJECTILE_MEMBERS[component]]
                entry[component.removesuffix('ComponentData')[6:].lower() + 'LevelProjectiles'] = values
                if any(values):
                    selectors.append(component.removesuffix('ComponentData') + ' (level-selected projectile)')
        if entry['base']['projectileEntity']:
            selectors.append('ProjectileEntity (spawns an entity instead of a projectile)')

        defaults = []
        if 'WeaponCustomizationComponentData' in components:
            body = native.record('WeaponCustomizationComponentData',
                components['WeaponCustomizationComponentData']['record_index'])
            for at in range(0, 80, 8):
                slot, option = struct.unpack_from('<II', body, at)
                if option in by_id:
                    item = by_id[option]
                    defaults.append({'slot': slot, 'item': item['debugName'], 'optionId': f'0x{option:08X}', 'pairOffset': at,
                        'addPath': f"0x{item['addPath']:016X}",
                        'projectilePatches': patching.get(item['addPath'], []),
                        'fireRatePatched': any(e['component'] == 321 and e['offset'] < FIRE_RATE[1]
                            and e['offset'] + e['size'] > FIRE_RATE[0]
                            for e in (deltas.get(item['addPath']) or {}).get('entries', []))})
                    default_users[item['addPath']].append(name)
        entry['defaultCustomization'] = defaults
        listed = unlock.get(name)
        equippable = []
        for option in (listed or {}).get('options', []):
            path = int(option['addPath'], 16)
            if path in patching and not any(int(d['addPath'], 16) == path for d in defaults):
                equippable.append({'item': by_add[path]['debugName'], 'slots': by_add[path]['slots'],
                    'addPath': option['addPath'], 'projectilePatches': patching[path]})
            listed_users[path].append(name)
        entry['unlockList'] = listed is not None
        entry['equippableProjectileOptions'] = equippable
        entry['armoryCategories'] = ui_categories.get(name)

        overriding = [(d, p) for d in defaults for p in d['projectilePatches']]
        base_overrides = [(d, p) for d, p in overriding if p['member'] == 'ProjType']
        other_overrides = [(d, p) for d, p in overriding if p['member'] != 'ProjType']
        entry['fireRateOverriddenByDefault'] = [d['item'] for d in defaults if d['fireRatePatched']]
        if kind == 'player_weapon' and name in LIVE_CONTROLS:
            entry['liveControl'] = LIVE_CONTROLS[name]
        if selectors:
            status, reason, source = 'BLOCKED', 'Another native selector owns the fired projectile: ' + '; '.join(
                selectors) + '.', None
        elif other_overrides:
            status, reason, source = 'AMBIGUOUS', ('A default customization patches ' + ', '.join(sorted({
                p['member'] for _, p in other_overrides})) + '.'), None
        elif len(base_overrides) > 1:
            status, reason, source = 'DORMANT_OR_METADATA', ('Several default customization items patch '
                'ProjectileWeapon +0; the applied order is not proven.'), None
        elif base_overrides:
            item, patch = base_overrides[0]
            source = {'kind': 'ammunition_delta', 'item': item['item'], 'slot': item['slot'], 'addPath': item['addPath'],
                'defaultPairOffset': item['pairOffset'],
                'optionId': item['optionId'], 'value': patch['value'], 'dataOffset': patch['dataOffset'],
                'ownRow': patch['ownRow'], 'baseAgrees': patch['value'] == entry['base']['projType']}
            status = 'INDIRECT' if patch['ownRow'] else 'DORMANT_OR_METADATA'
            reason = (f"The default ammunition item {item['item']} (customization slot {item['slot']}) patches "
                'ProjectileWeapon +0 when the weapon is built, so the base member is dormant; the ammunition delta '
                'is the active source.')
            if equippable:
                reason += (' The unlock list also carries ' + str(len(equippable)) + ' other options that patch a '
                    'projectile member (alternate ammunition), each with its own projectile.')
        elif equippable:
            status, reason, source = 'AMBIGUOUS', ('No default overrides +0, but the unlock list carries an option '
                'that patches a projectile member: the fired projectile depends on the equipped option.'), None
        elif entry['base']['weaponFunctionProjectileType']:
            status, reason, source = 'AMBIGUOUS', ('A weapon function (programmable ammo) switches to '
                'WeaponFunctionProjectileType; the base member is only the default function\'s projectile.'), None
        else:
            status, reason, source = 'ACTIVE_DIRECT', ('No customization delta patches a projectile member and no '
                'other selector exists: every shot is ProjectileWeapon +0.'), {'kind': 'component',
                'value': entry['base']['projType']}
        # Output-composition hosts keep the structure of the live controls: magazine-fed, no rounds, charge or heat
        # fire control. The mechanism is where the fired projectile is written.
        entry['magazineFed'] = ('WeaponMagazineComponentData' in components and not any(c in components for c in
            ('WeaponRoundsComponentData', 'WeaponChargeComponentData', 'WeaponHeatComponentData')))
        entry['outputHost'] = ({'ACTIVE_DIRECT': 'component', 'INDIRECT': 'ammunition'}.get(status)
            if entry['magazineFed'] else None)
        entry['selectors'] = selectors
        entry.update(status=status, reason=reason, activeSource=source,
            baseMember='ACTIVE' if status == 'ACTIVE_DIRECT' else 'DORMANT' if status in (
                'INDIRECT', 'DORMANT_OR_METADATA') else 'NOT_SOLE_SOURCE' if status == 'BLOCKED' else 'UNPROVEN')
        return entry

    for name, kind, resource in attack_outputs.weapons():
        entry = classify(name, kind, resource)
        if entry:
            weapons.append(entry)
    # Sentry and emplacement hosts (0.30.2): stratagem deployed entities that carry their own ProjectileWeapon
    # record, classified by the same rules (research/defensive-stratagem-runtime-F5FEE03DCFDB.json).
    sentry_hosts = []
    for item in json.loads(DEFENSIVE.read_text(encoding='utf-8'))['stratagems']:
        entity = item.get('deployedEntity') or {}
        if 'ProjectileWeaponComponentData' in (entity.get('componentNames') or []):
            entry = classify(item['name'], 'stratagem', entity['resource'])
            if entry:
                entry['family'] = item['family']
                # What a projectile-reference field on this host needs (the mounted-weapon host model): the
                # ProjectileWeapon record's identity and the host's own projectile row and class.
                own = {c['name']: c for c in native.report(entity['resource'])['components']
                    if c['resolved'] and c['name']}['ProjectileWeaponComponentData']
                ownership = native.ownership(own)
                entry['componentIdentity'] = {'recordIndex': own['record_index'], 'indexRow': own['index_row'],
                    'ownerCount': ownership['ownerCount'], 'uniqueOwner': ownership['uniqueOwner']}
                sentry_hosts.append(entry)
    rows = attack_outputs.resolve_settings(sorted({e['base']['projType'] for e in sentry_hosts}), [], [])['projectiles']
    for entry in sentry_hosts:
        row = rows.get(str(entry['base']['projType']))
        entry['output'] = row
        entry['compatibilityClass'] = attack_outputs.projectile_class(row) if row else None

    ammunition_types = sorted({e['activeSource']['value'] for e in weapons
        if e['activeSource'] and e['activeSource']['kind'] == 'ammunition_delta'})
    settings = attack_outputs.resolve_settings(ammunition_types, [], [])['projectiles']
    for entry in weapons:
        source = entry['activeSource']
        if source and source['kind'] == 'ammunition_delta':
            row = settings.get(str(source['value']))
            source['settings'] = row and row['settings']
            source['compatibilityClass'] = row and attack_outputs.projectile_class(row)
            path = int(source['addPath'], 16)
            source['defaultOf'] = sorted(default_users[path])
            source['unlockListedBy'] = sorted(listed_users[path])
            source['otherPatches'] = other_patches(deltas.get(path), names)
            source['hashmapSlot'] = deltas[path]['hashmapSlot']
            source['settingsIndex'] = deltas[path]['settingsIndex']

    old_hosts = {e['weapon'] for e in json.loads((ROOT / 'research/attack-outputs-F5FEE03DCFDB.json').read_text())[
        'weapons'] if e.get('projectileHost')}
    by_name = {e['weapon']: e for e in weapons}
    attacks = attack_sources(by_name)
    counts = collections.Counter(e['status'] for e in weapons)
    audit = collections.Counter(e['status'] for e in weapons if e['weapon'] in old_hosts)
    ammunition = [{'item': by_add[path]['debugName'], 'addPath': f'0x{path:016X}', 'slots': by_add[path]['slots'],
        'projectilePatches': [{k: p[k] for k in ('component', 'offset', 'member', 'value', 'ownRow')} for p in patches],
        'defaultOf': sorted(default_users.get(path, [])), 'unlockListedBy': sorted(listed_users.get(path, []))}
        for path, patches in sorted(patching.items(), key=lambda kv: by_add[kv[0]]['debugName'])]
    return {'schemaVersion': 1, 'writes': 0, 'fixtureFallback': 'disabled', 'build': 'F5FEE03DCFDB',
        'proofBasis': ('Decoded data path (entity components, customization defaults, entity deltas, runtime unlock '
            'lists) checked against two live controls: the Reprimand (no customization patch on +0) fired a swapped '
            'projectile; the Liberator (default ammunition delta patches +0) did not. No native reader of the firing '
            'path was traced.'),
        'projectileMembers': members,
        'referencesReachable': {
            'ProjectileWeapon +0 ProjType': 'the fired projectile unless a customization delta patches it',
            'ProjectileWeapon +576 WeaponFunctionProjectileType': 'used when a programmable-ammo weapon function is active',
            'ProjectileWeapon +40 ProjectileEntity': 'when set, firing spawns an entity instead of a projectile',
            'WeaponMagazine +4 Projectiles[32] / +132 FirstProjectile': 'magazine pattern; overrides per round when set',
            'WeaponRounds +64 / +68': 'primary / alternate magazine projectile of rounds-fed weapons',
            'WeaponCharge / WeaponHeat ProjType': 'charge- or heat-level projectile',
            'customization entity deltas': 'ammunition items patch them at weapon build: slot 6 patches '
                'ProjectileWeapon +0 or WeaponRounds +64, slot 7 (alternate magazine) WeaponRounds +68; the delta, '
                'not the base member, is then the fired projectile. No other customization slot patches a '
                'projectile member.'},
        'controls': {name: {k: by_name[name].get(k) for k in ('status', 'base', 'defaultCustomization',
            'activeSource', 'baseMember', 'liveControl', 'equippableProjectileOptions', 'armoryCategories')}
            for name in ('SMG-32 Reprimand', 'AR-23 Liberator')},
        'summary': {'projectileWeapons': len(weapons), 'byStatus': dict(sorted(counts.items())),
            'previousHosts': len(old_hosts), 'previousHostsByStatus': dict(sorted(audit.items())),
            'baseDisagreesWithActive': sorted(e['weapon'] for e in weapons if e['activeSource']
                and e['activeSource'].get('baseAgrees') is False),
            'fireRateOverriddenByDefault': sorted(e['weapon'] for e in weapons if e['fireRateOverriddenByDefault']),
            'outputHosts': dict(sorted(collections.Counter(e['outputHost'] for e in weapons if e['outputHost']).items())),
            'ammunitionItemsPatchingProjectile': len(ammunition),
            'attackFields': len(attacks),
            'attackFieldsByStatus': dict(sorted(collections.Counter(a['status'] for a in attacks).items())),
            'previouslyWritableAttackFieldsByStatus': dict(sorted(collections.Counter(
                a['status'] for a in attacks if a['previouslyWritable']).items()))},
        'attackFields': attacks, 'ammunitionItems': ammunition, 'weapons': weapons}, {
        'schemaVersion': 1, 'writes': 0, 'fixtureFallback': 'disabled', 'build': 'F5FEE03DCFDB',
        'proofBasis': ('The same decoded data path and rules as research/active-projectile-sources-F5FEE03DCFDB.json, '
            'applied to every stratagem deployed entity that carries its own ProjectileWeapon record (sentries and '
            'emplacements): ACTIVE_DIRECT means every shot is that record\'s ProjectileWeapon +0. No type-level sentry '
            'swap has been live-tested; the custom-stratagem sentry (a private copy of +0 on one sentry, Gatling '
            'chassis, pattern off) fired its swapped round live.'),
        'summary': {'hosts': len(sentry_hosts),
            'byStatus': dict(sorted(collections.Counter(e['status'] for e in sentry_hosts).items()))},
        'hosts': sentry_hosts}


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sentry-hosts', action='store_true',
        help='write only research/sentry-projectile-hosts-F5FEE03DCFDB.json (the weapon report is left as it is)')
    args = parser.parse_args(argv)
    report, sentries = build()
    SENTRY_OUTPUT.write_text(json.dumps(sentries, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(sentries['summary'], indent=1))
    if not args.sentry_hosts:
        OUTPUT.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
        print(json.dumps(report['summary'], indent=1))


if __name__ == '__main__':
    main()
