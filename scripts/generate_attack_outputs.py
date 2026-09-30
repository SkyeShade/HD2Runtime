"""Generate the attack-output catalog from research/attack-outputs-F5FEE03DCFDB.json.

There is no common native attack-output abstraction: a weapon entity owns one output-family component
(ProjectileWeapon, BeamWeapon, ArcWeapon, SprayWeapon, MeleeWeapon), each referencing its own settings family through
its own enum. The catalog is therefore family-aware:

- domains/attack_outputs.lua (runtime): every catalogued output by semantic ID. Projectile outputs carry the source
  identity the projectile-reference write re-proves live (owner entity, its ProjectileWeapon record identity, the
  ProjectileSettings row); beam, arc, spray and melee outputs carry only their family and the reason no projectile
  host can reference them. Also, from research/active-projectile-sources-F5FEE03DCFDB.json: the active projectile
  source of every player attack (`sources`), the ammunition-delta source of weapons whose default ammunition
  customization owns the fired projectile (`ammunition`), and the hosts eligible for cross-class outputs, each with
  the mechanism that writes its fired projectile (`hosts`).
- sdk/AttackOutputCapabilities.json (public): every output with family, kind, owner, package dependency, structural
  compatibility with host families, required coordinated references, acknowledgements and live proof. No native
  identifiers or addresses.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from migration import overlay as migration_overlay  # noqa: E402  build-migration hook
import live_evidence  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research/attack-outputs-F5FEE03DCFDB.json'
ACTIVE = ROOT / 'research/active-projectile-sources-F5FEE03DCFDB.json'
DONORS = ROOT / 'research/stun-field-donors-F5FEE03DCFDB.json'
PRESENTATION = ROOT / 'research/weapon-presentation-F5FEE03DCFDB.json'
MODE_UNVERIFIED = ('The label and icon are the fired projectile\'s own ProjectileInfo members, which every native '
    'weapon-function mode reads as; the menu reader is not traced and an edited mode label or icon has not been '
    'gameplay-tested. Only native strings and native weapon-function icons are offered.')
ASSETS = ROOT / 'sdk/AssetDependencyCapabilities.json'
LUA_OUTPUT = ROOT / 'domains/attack_outputs.lua'
JSON_OUTPUT = ROOT / 'sdk/AttackOutputCapabilities.json'
CONTRACT = 'hd2runtime.attack_outputs.v1'
FAMILY_EMITTER = {'beam': 'BeamWeaponComponent', 'arc': 'ArcWeaponComponent', 'spray': 'SprayWeaponComponent',
    'melee': 'MeleeWeaponComponent'}
CROSS_FAMILY = ('A projectile host references only ProjectileType. {family} outputs are fired by their own '
    '{emitter} (which also owns their cadence{extra}); no projectile or explosion member can reference them, and '
    'adding the component to another weapon entity changes its composition, which Runtime does not do.')
EXTRA = {'beam': ', beam fire mode and heat buildup', 'arc': ', RPM and infinite ammo', 'spray': '', 'melee': ''}
UNVERIFIED_REFERENCE = ('A projectile from a different structural class (for example a ballistic host firing a '
    'rocket or an arc grenade) is structurally a single ProjectileType reference, but no live test has confirmed the '
    'gameplay of that composition yet.')
AMMUNITION_EFFECT = ('The ammunition delta is the projectile the weapon is built with (the base ProjectileWeapon member '
    'is overwritten by it), but no live test has yet confirmed that an edited ammunition delta reaches the weapon: '
    'the delta is applied when the weapon is built, and whether an edit is re-applied to the next build or cached is '
    'not gameplay-tested.')
AMMUNITION_SHARED = ('An ammunition definition applies to every weapon that equips it. sharedWithWeapons lists the '
    'other weapons observed to default to it or to carry it in their runtime unlock list; the list is runtime state '
    'and does not prove that no other weapon equips it.')
SOURCE_CODE = {'INDIRECT': 'DORMANT_PROJECTILE_REFERENCE', 'DORMANT_OR_METADATA': 'DORMANT_PROJECTILE_REFERENCE',
    'AMBIGUOUS': 'UNPROVEN_PROJECTILE_SOURCE', 'BLOCKED': 'PROJECTILE_SOURCE_BLOCKED'}


def source_reason(row):
    """The read-only reason of a non-direct attack projectile field, with its error code and the redirect."""
    reason = SOURCE_CODE[row['status']] + ': ' + row['reason']
    if row.get('mechanism') == 'ammunition':
        reason += ' Write weapon:ammunition():projectile() (hd2.fields.ammunition.projectile) instead.'
    return reason


def ammunition_proven(weapon):
    """Live evidence for one weapon's ammunition source: only the weapons whose own delta row a test exercised."""
    family = live_evidence.family('weapon_ammunition_projectile_reference')
    if family['status'] != 'live_proven' or weapon not in family.get('provenWeapons', []):
        return None
    return live_evidence.proven('weapon_ammunition_projectile_reference')


def proven_compositions():
    """host -> {output semantic id: mechanism} for cross-class compositions a user test proved in play."""
    family = live_evidence.family('attack_output_cross_class')
    result = {}
    if family['status'] != 'live_proven':
        return result
    for item in family.get('provenCompositions', []):
        output = 'output/v1/projectile/' + slug(item['output'])
        result.setdefault(item['host'], {})[output] = item['mechanism']
    return result


def active_sources():
    """(research, sources, ammunition, by_weapon) from the active projectile source research."""
    active = json.loads(ACTIVE.read_text(encoding='utf-8'))
    by_weapon = {e['weapon']: e for e in active['weapons']}
    sources = {}
    for row in active['attackFields']:
        sources.setdefault(row['weapon'], {})[row['role']] = {'status': row['status'], 'mechanism': row['mechanism'],
            'member': row['backing'], 'reason': row['reason'], 'previouslyWritable': row['previouslyWritable'],
            'compatibilityClass': row['compatibilityClass'], 'candidatesAgree': row.get('candidatesAgree', False)}
    ammunition = {}
    for entry in active['weapons']:
        source = entry['activeSource']
        if entry['kind'] != 'player_weapon' or entry['status'] != 'INDIRECT' or source['kind'] != 'ammunition_delta':
            continue
        if not (source['ownRow'] and source['settings'] and source['compatibilityClass']):
            raise ValueError(entry['weapon'] + ': ammunition source is not a resolvable own 4-byte delta row')
        sources.setdefault(entry['weapon'], {}).setdefault('primary', {'status': 'INDIRECT', 'mechanism': 'ammunition',
            'member': 'ProjectileWeapon +0', 'reason': entry['reason'], 'previouslyWritable': False,
            'compatibilityClass': source['compatibilityClass']})
        shared = sorted((set(source['defaultOf']) | set(source['unlockListedBy'])) - {entry['weapon']})
        ammunition[entry['weapon']] = {'id': 'ammunition/v1/' + slug(entry['weapon']) + '/' + slug(source['item']),
            'weapon': entry['weapon'], 'item': source['item'], 'semanticFieldId': 'ammunition.projectile',
            'type': 'projectile_reference', 'referenceKind': 'projectile', 'referenceRole': 'primary',
            'compatibilityClass': source['compatibilityClass'],
            'currentDefault': {'weapon': entry['weapon'], 'projectileType': source['value']},
            'referenceSettings': source['settings'], 'editable': True,
            'acknowledgement': None if ammunition_proven(entry['weapon']) else 'allow_unverified_effect',
            'acknowledgementReason': None if ammunition_proven(entry['weapon']) else AMMUNITION_EFFECT,
            'liveEvidence': ammunition_proven(entry['weapon']),
            'affectsMultipleWeapons': True, 'sharedWithWeapons': shared, 'sharedReason': AMMUNITION_SHARED,
            'writeScope': 'ammunition_definition', 'appliesWhen': 'weapon_build',
            # Entity delta coordinates, re-proven live (domains/attachment_writes.prove) before every write.
            'resource': source['addPath'], 'hashmapSlot': source['hashmapSlot'], 'settingsIndex': source['settingsIndex'],
            'component': 321, 'componentOffset': 0, 'dataOffset': source['dataOffset'],
            'backing': {'kind': 'entity_delta', 'component': 'ProjectileWeaponComponentData', 'offset': 0, 'width': 4,
                'storage': 'u32'},
            # The weapon's own default customization must still name this ammunition item (checked live).
            'defaultCustomization': {'offset': source['defaultPairOffset'], 'slot': source['slot'],
                'optionId': int(source['optionId'], 16)}}
    return active, sources, ammunition, by_weapon


def output_live_proof(weapon):
    """Donor-side live evidence: a host fired this weapon's projectile and it worked (sdk/LiveEvidenceCatalog.json)."""
    runs = [test for session in live_evidence.load()['sessions'] for test in session['tests']
        if test.get('donor') == weapon and (test.get('evidence') or {}).get('gameplayOutputChanged')]
    if not runs:
        return None
    return {'donorOutput': 'live_proven', 'tests': sorted({run['mod'] for run in runs}),
        'provenOnHosts': sorted({run['host'] for run in runs if run['evidence']['hostReadsReference']})}


def host_live_proof(weapon):
    """Host-side live evidence: tests whose host was this weapon, with the host-path result."""
    runs = [test for session in live_evidence.load()['sessions'] for test in session['tests']
        if test.get('host') == weapon and test.get('evidence')]
    return [{'test': run['mod'] + (' (' + run['choice'] + ')' if run.get('choice') else ''), 'result': run['result'],
        'family': run['family'], 'hostReadsReference': run['evidence']['hostReadsReference'],
        'superseded': bool(run.get('supersededBy'))} for run in runs] or None


def owner_source(entry):
    """Whether an output's owner is established to fire the projectile row the output names."""
    if entry is None:
        return 'unclassified', None
    status = entry['status']
    if status == 'ACTIVE_DIRECT':
        return 'fires_reference', None
    if status == 'INDIRECT':
        if entry['activeSource'].get('baseAgrees'):
            return 'fires_reference', None
        return 'not_established', ('The owner fires its default ammunition projectile; its ProjectileWeapon member '
            'names a different row.')
    if status == 'AMBIGUOUS':
        return 'default_projectile', None
    selectors = entry.get('selectors') or []
    if selectors and all(s.startswith('WeaponRounds') for s in selectors) and entry.get('rounds') \
            and entry['rounds'][0] == entry['base']['projType']:
        return 'fires_reference', None
    return 'not_established', ('The owner fires through another selector, so this row is not established as its '
        'attack output: ' + '; '.join(selectors) + '.')


def slug(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')


def lua(value) -> str:
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if value is None:
        return 'nil'
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, dict):
        return '{' + ','.join(('[' + lua(key) + ']=' if not re.fullmatch(r'[A-Za-z_]\w*', str(key))
            else str(key) + '=') + lua(item) for key, item in value.items()) + '}'
    return '{' + ','.join(lua(item) for item in value) + '}'


def kind_of(entry):
    family = entry['family']
    if family == 'projectile':
        return {'conventional_plain': 'ballistic', 'explosive_impact': 'explosive',
            'explosive_impact_and_expiry': 'explosive', 'explosive_shrapnel': 'explosive_submunition',
            'explosive_arc': 'arc_on_impact'}.get(entry.get('compatibilityClass'), 'projectile')
    if family == 'beam':
        return 'pulsed_multi_beam' if entry.get('beamFireMode') == 6 else 'continuous_beam'
    return family


def public_presentation(row):
    fields = row['presentationFields']
    label, icon = fields['presentation.mode_label'], fields['presentation.mode_icon']
    return {'label': label['currentDefault'], 'icon': icon['currentDefault'], 'writable': True,
        'shared': label['shared'], 'acknowledgements': ['allow_unverified_effect'] + (['allow_shared']
            if label['shared'] else [])}


GENERIC_FALLBACK = (json.loads(PRESENTATION.read_text(encoding='utf-8'))['modes']['genericFallbackIcon'],
    json.loads(PRESENTATION.read_text(encoding='utf-8'))['modes']['iconVisuals'])


def mode_catalog():
    """(labels, icons, projectiles) from research/weapon-presentation-F5FEE03DCFDB.json `modes`."""
    modes = json.loads(PRESENTATION.read_text(encoding='utf-8'))['modes']
    labels = {'none': {'nativeId': int(modes['placeholderLabel'], 16), 'offered': True, 'label': None}}
    for item in modes['labels']:
        labels[item['semanticId']] = {'nativeId': int(item['nativeId'], 16), 'offered': item['offered'],
            'label': item['label']}
    for native in modes['unnamedLabels']:
        labels['unnamed_' + native.lower()] = {'nativeId': int(native, 16), 'offered': False, 'label': None}
    icons = {item['semanticId']: {'resource': item['resource'], 'offered': item['offered']}
        for item in modes['icons'] if item['semanticId']}
    # Icon for a label: the exact native icon a projectile with that label shows, else the generic fallback.
    for key, item in labels.items():
        choice = modes['labelIcons'].get(key) or {'icon': modes['genericFallbackIcon'], 'source': 'generic_fallback'}
        item['icon'], item['iconSource'] = choice['icon'], choice['source']
    icons['auto'] = {'auto': True, 'offered': True, 'generic': modes['genericFallbackIcon']}
    return labels, icons, modes['projectiles']


def presentation_fields(row, consumers, labels, icons, projectiles):
    """The weapon-function mode label and HUD icon of a selectable projectile output (its ProjectileInfo +12, +16)."""
    projectile = projectiles.get(str(row['currentDefault']))
    settings = row['referenceSettings']
    if not projectile or projectile['settings'] != settings:
        raise ValueError(row['id'] + ': projectile presentation row does not match the output settings')
    shared = sorted(consumers)
    common = {'editable': True, 'acknowledgement': 'allow_unverified_effect', 'acknowledgementReason': MODE_UNVERIFIED,
        'shared': len(shared) > 1, 'sharedConsumers': shared, 'operationGroup': 'mode_presentation',
        'appliesWhen': 'menu_build'}
    backing = {'kind': 'settings', 'settings': 'projectile', 'recordType': settings['recordType'],
        'group': settings['group'], 'row': settings['row'], 'settingsType': settings['settingsType']}
    label = projectile['label'] or 'none'
    if label not in labels:
        raise ValueError(row['id'] + ': unknown mode label ' + label)
    return {'presentation.mode_label': dict(common, semanticFieldId='presentation.mode_label', type='mode_label',
            currentDefault=label, backing=dict(backing, offset=12, width=4, storage='u32')),
        'presentation.mode_icon': dict(common, semanticFieldId='presentation.mode_icon', type='mode_icon',
            currentDefault=projectile['icon'], backing=dict(backing, offset=16, width=8, storage='u64'))}


def outputs():
    research = json.loads(RESEARCH.read_text(encoding='utf-8'))
    mode_labels, mode_icons, mode_projectiles = mode_catalog()
    active, sources, ammunition, by_weapon = active_sources()
    runtime_outputs, aliases, public = {}, {}, []
    for entry in sorted(research['weapons'], key=lambda e: (e['kind'], e['weapon'])):
        semantic = f"output/v1/{entry['family']}/{slug(entry['weapon'])}"
        owner = {'kind': entry['kind'], 'name': entry['weapon']}
        fires, owner_reason = owner_source(by_weapon.get(entry['weapon'])) if entry['family'] == 'projectile' else (
            None, None)
        selectable = (entry['family'] == 'projectile' and entry.get('output') is not None
            and entry.get('compatibilityClass') is not None and fires != 'not_established')
        row = {'id': semantic, 'family': entry['family'], 'owner': owner}
        if selectable:
            settings = entry['output']['settings']
            row.update(resource=entry['resource'], entityRow=entry['entityRow'],
                backing={'kind': 'component', 'component': entry['component'], 'offset': 0, 'storage': 'u32',
                    'width': 4, **entry['componentIdentity']},
                currentDefault=entry['reference']['value'], editable=True,
                referenceSettings={'group': settings['group'], 'row': settings['row'],
                    'recordType': settings['recordType'], 'settingsType': settings['settingsType']},
                compatibilityClass=entry['compatibilityClass'],
                dependencyKey=entry['kind'] + '/' + entry['weapon'])
        else:
            row['reason'] = (CROSS_FAMILY.format(family=entry['family'].capitalize(),
                emitter=FAMILY_EMITTER.get(entry['family'], entry['component']), extra=EXTRA.get(entry['family'], ''))
                if entry['family'] != 'projectile' else owner_reason if fires == 'not_established' else
                'The projectile row this weapon fires is not resolved in the retained snapshot.')
        if selectable:
            row['presentationFields'] = presentation_fields(row, entry.get('outputConsumers') or [], mode_labels,
                mode_icons, mode_projectiles)
        runtime_outputs[semantic] = row
        for alias in (entry['weapon'], entry['weapon'] + '/primary'):
            if alias in aliases:
                raise ValueError('duplicate attack output alias ' + alias)
            aliases[alias] = semantic
        output = entry.get('output') or {}
        public.append({'semanticId': semantic, 'family': entry['family'], 'kind': kind_of(entry), 'owner': owner,
            'emitter': entry['component'].removesuffix('ComponentData'),
            'compatibilityClass': entry.get('compatibilityClass'),
            'selectableAsProjectileReference': selectable,
            'compatibleHostFamilies': ['projectile'] if selectable else [],
            'requiredCoordinatedReferences': [] if selectable else None,
            'blockedReason': row.get('reason'),
            'chain': ({'impactExplosion': bool(output.get('impact')), 'expiryExplosion': bool(output.get('expiry')),
                'submunition': bool((output.get('impact') or {}).get('shrapnel')),
                'arcOnImpact': bool((output.get('impact') or {}).get('arc'))} if entry['family'] == 'projectile'
                else None),
            'ownerFireResource': [c.removesuffix('ComponentData') for c in entry['fireResource']],
            'package': {'name': entry.get('package'), 'known': entry.get('package') is not None,
                'autoLoad': bool(entry.get('packageAutoLoad'))},
            'acknowledgements': ({'sameClass': [], 'crossClass': ['allow_unverified_reference',
                'allow_unverified_effect']} if selectable else None),
            'ownerFiresThisProjectile': fires,
            'presentation': public_presentation(row) if selectable else None,
            'liveProof': output_live_proof(entry['weapon'])})
    # Stratagem-owned projectile donors (research/stun-field-donors-F5FEE03DCFDB.json): a projectile a stratagem entity
    # fires through its own ProjectileWeapon +0 (the EMS Mortar turret's shell). They are catalogued for exactly the
    # fields in referenceScope (a ProgrammableAmmo function projectile), with the entity's own loadout package.
    assets = {o['key']: o['packageDependency'] for o in json.loads(ASSETS.read_text(encoding='utf-8'))['objects']}
    for donor in json.loads(DONORS.read_text(encoding='utf-8'))['donors']:
        semantic = 'output/v1/projectile/' + slug(donor['name'])
        owner = {'kind': donor['ownerKind'], 'name': donor['name']}
        key = 'stratagem_weapon/' + donor['name']
        package = assets.get(key) or {}
        if not package.get('autoLoadSupported'):
            raise ValueError(donor['name'] + ': a stratagem donor needs a loadable package (' + key + ')')
        settings = donor['settings']
        field = donor['field']
        effect = {'volume': field['volume'], 'seconds': field['volumeSeconds'], 'radius': field['radii'][1],
            'status': field['damage']['status'], 'explosion': field['role']}
        runtime_outputs[semantic] = {'id': semantic, 'family': 'projectile', 'owner': owner,
            'resource': donor['resource'], 'entityRow': donor['entityRow'],
            'backing': {'kind': 'component', 'component': donor['component'], 'offset': 0, 'storage': 'u32',
                'width': 4, **donor['componentIdentity']},
            'currentDefault': donor['projectileType'], 'editable': True,
            'referenceSettings': {'group': settings['group'], 'row': settings['row'],
                'recordType': settings['recordType'], 'settingsType': settings['settingsType']},
            'compatibilityClass': donor['compatibilityClass'], 'dependencyKey': key,
            'referenceScope': list(donor['referenceScope']), 'fieldEffect': effect}
        runtime_outputs[semantic]['presentationFields'] = presentation_fields(runtime_outputs[semantic],
            [entity for entity in donor.get('consumers') or [donor['name']]], mode_labels, mode_icons, mode_projectiles)
        for alias in (donor['name'], donor['name'] + '/primary'):
            if alias in aliases:
                raise ValueError('duplicate attack output alias ' + alias)
            aliases[alias] = semantic
        public.append({'semanticId': semantic, 'family': 'projectile', 'kind': 'status_field', 'owner': owner,
            'emitter': 'ProjectileWeapon', 'compatibilityClass': donor['compatibilityClass'],
            'selectableAsProjectileReference': True, 'compatibleHostFamilies': ['projectile'],
            'referenceScope': list(donor['referenceScope']),
            'requiredCoordinatedReferences': [], 'blockedReason': None,
            'chain': {'impactExplosion': True, 'expiryExplosion': True, 'submunition': False, 'arcOnImpact': False},
            'fieldEffect': effect,
            'ownerFireResource': [],
            'package': {'name': package.get('package'), 'known': True, 'autoLoad': True},
            'acknowledgements': {'sameClass': [], 'crossClass': ['allow_unverified_reference',
                'allow_unverified_effect']},
            'ownerFiresThisProjectile': 'fires_reference',
            'presentation': public_presentation(runtime_outputs[semantic]),
            'liveProof': output_live_proof(donor['name'])})
    # Hosts: a player attack whose fired projectile Runtime can write. `component`: the attack's own ProjectileWeapon
    # +0 is its active source; `ammunition`: the default ammunition delta is. Both keep the live controls' structure
    # (magazine-fed; no rounds, charge or heat). Support weapons have no guarded projectile reference target.
    hosts = {}
    for name, roles in sorted(sources.items()):
        primary = roles.get('primary')
        entry = by_weapon.get(name)
        if not primary or not entry or entry['kind'] != 'player_weapon' or not entry['magazineFed']:
            continue
        if primary['mechanism'] == 'component' and primary['status'] == 'ACTIVE_DIRECT' \
                and primary['previouslyWritable'] and primary['member'] == 'ProjectileWeapon +0':
            hosts[name] = {'kind': 'player_weapon', 'class': primary['compatibilityClass'], 'mechanism': 'component'}
        elif primary['mechanism'] == 'ammunition' and name in ammunition:
            hosts[name] = {'kind': 'player_weapon', 'class': ammunition[name]['compatibilityClass'],
                'mechanism': 'ammunition'}
    compositions = proven_compositions()
    for host, pairs in compositions.items():
        for output, mechanism in pairs.items():
            if output not in runtime_outputs or (hosts.get(host) or {}).get('mechanism') != mechanism:
                raise ValueError(f'proven composition {host} / {output} is not a catalogued host and output')
    runtime_labels = {key: {'nativeId': item['nativeId'], 'offered': item['offered'], 'icon': item['icon'],
        'iconSource': item['iconSource']} for key, item in mode_labels.items()}
    runtime_icons = {key: (dict(item) if item.get('auto') else {'resource': item['resource'], 'offered': item['offered']})
        for key, item in mode_icons.items()}
    runtime = migration_overlay.apply('attack_outputs', {'outputs': runtime_outputs, 'aliases': aliases,
        'modeLabels': runtime_labels, 'modeIcons': runtime_icons,
        'hosts': hosts, 'sources': sources, 'ammunition': ammunition, 'provenCompositions': compositions,
        'crossClassReason': UNVERIFIED_REFERENCE})
    cases = research['liberatorCases']
    public_sources = []
    for name, roles in sorted(sources.items()):
        for role, row in sorted(roles.items()):
            item = {'weapon': name, 'attack': role, 'status': row['status'], 'mechanism': row['mechanism'],
                'member': row['member'], 'reason': row['reason'],
                'directWritable': row['status'] == 'ACTIVE_DIRECT' and row['previouslyWritable'],
                'previouslyWritable': row['previouslyWritable']}
            if row['mechanism'] == 'ammunition':
                item['write'] = 'weapon:ammunition():projectile() (hd2.fields.ammunition.projectile)'
            elif item['directWritable']:
                item['write'] = 'weapon:attack(role):projectile() (hd2.fields.attack.projectile)'
            else:
                item['write'] = None
            public_sources.append(item)
    public_ammunition = [{'weapon': name, 'semanticId': a['id'], 'item': a['item'],
        'compatibilityClass': a['compatibilityClass'], 'sharedWithWeapons': a['sharedWithWeapons'],
        'sharedReason': a['sharedReason'], 'appliesWhen': 'weapon build (the ammunition delta is applied when the '
            'weapon is built)',
        'acknowledgements': ['allow_shared'] + ([] if ammunition_proven(name) else ['allow_unverified_effect']),
        'crossClassAcknowledgements': ['allow_unverified_reference', 'allow_unverified_effect'],
        'effectReason': a['acknowledgementReason'],
        'liveProof': 'live_proven' if ammunition_proven(name) else 'pending'}
        for name, a in sorted(ammunition.items())]
    classified = active['summary']
    document = {'contract': CONTRACT, 'schemaVersion': 2,
        'hd2RuntimeVersion': (ROOT / 'VERSION').read_text().strip(), 'build': 'F5FEE03DCFDB',
        'model': dict(research['model'], proofLevels={
            'identity': 'the owner weapon, its output-family component and settings row are re-proven live',
            'assets': 'the owner package is loaded through the 0.27 asset loader before the reference is written',
            'structural': 'projectile-family outputs only: one ProjectileType reference; cross-family is blocked',
            'activeSource': ('the written member is the projectile the host fires: its active projectile source '
                '(projectileSources), established from the decoded data path and the live controls'),
            'gameplay': 'live-proven only by a user-run test (sdk/LiveEvidenceCatalog.json)'}),
        'activeSourceModel': {
            'guarantee': ('When Runtime reports a projectile reference as writable for a host, changing it changes the '
                'projectile that host fires, as far as the decoded data path and the live controls establish. Attacks '
                'whose fired projectile comes from elsewhere are read-only with the reason.'),
            'statuses': {'ACTIVE_DIRECT': 'the attack member itself is the fired projectile; writable directly',
                'INDIRECT': ('the default ammunition customization patches the member when the weapon is built; the '
                    'member is dormant and the ammunition delta is the active source'),
                'DORMANT_OR_METADATA': 'the member is overridden and the overriding source is not uniquely identified',
                'AMBIGUOUS': 'the active projectile depends on state not proven offline',
                'BLOCKED': 'another native selector owns the fired projectile'},
            'proofBasis': active['proofBasis'],
            'referencesReachable': active['referencesReachable'],
            'liveControls': {'positive': 'SMG-32 Reprimand -> LAS-58 Talon (pass)',
                'negative': 'AR-23 Liberator -> LAS-58 Talon (fail: field written, no gameplay effect)'},
            'counts': {'projectileWeapons': classified['projectileWeapons'], 'byStatus': classified['byStatus'],
                'previousHosts': classified['previousHosts'],
                'previousHostsByStatus': classified['previousHostsByStatus'],
                'attackFields': classified['attackFields'], 'attackFieldsByStatus': classified['attackFieldsByStatus'],
                'previouslyWritableAttackFieldsByStatus': classified['previouslyWritableAttackFieldsByStatus']}},
        'projectileSources': public_sources,
        'ammunitionSources': public_ammunition,
        'provenCompositions': [{'host': host, 'output': output, 'mechanism': mechanism,
            'acknowledgementsRequired': []} for host, pairs in sorted(compositions.items())
            for output, mechanism in sorted(pairs.items())],
        'hostModel': {'componentHosts': sorted(n for n, h in hosts.items() if h['mechanism'] == 'component'),
            'ammunitionHosts': sorted(n for n, h in hosts.items() if h['mechanism'] == 'ammunition'),
            'rule': ('A projectile output needs a player attack whose fired projectile Runtime can write. component: '
                'the attack\'s own ProjectileWeapon +0 is its active source (ACTIVE_DIRECT). ammunition: the default '
                'ammunition delta is (INDIRECT), written through weapon:ammunition(). Both keep the live controls\' '
                'structure: magazine-fed, empty magazine pattern, no WeaponRounds, WeaponCharge or WeaponHeat. A '
                'projectile pointer existing is not enough. Support weapons have no guarded projectile reference '
                'target.'),
            'hostLiveProof': {name: host_live_proof(name) for name in sorted(hosts) if host_live_proof(name)},
            'retained': research['hostRetains']},
        'liberatorCases': cases,
        'summary': {'outputs': len(public), 'byFamily': {family: sum(1 for o in public if o['family'] == family)
                for family in research['summary']['byFamily']},
            'stratagemDonors': sorted(o['owner']['name'] for o in public if o['owner']['kind'] == 'stratagem'),
            'selectable': sum(1 for o in public if o['selectableAsProjectileReference']),
            'projectileHosts': len(hosts),
            'componentHosts': sum(1 for h in hosts.values() if h['mechanism'] == 'component'),
            'ammunitionHosts': sum(1 for h in hosts.values() if h['mechanism'] == 'ammunition'),
            'directWritableAttackFields': sum(1 for s in public_sources if s['directWritable'])},
        'outputs': public,
        'modePresentation': {'fields': {'label': 'hd2.fields.presentation.mode_label',
                'icon': 'hd2.fields.presentation.mode_icon'},
            'target': 'hd2.attack_output(name): the output whose projectile a weapon-function mode fires',
            'model': ('A weapon-function mode (ProgrammableAmmo, magazine or guidance selection) shows the fired '
                'projectile\'s own short label and HUD icon. They are members of its ProjectileSettings row, a shared '
                'definition: every weapon firing that projectile shows the same label and icon.'),
            'fallback': 'A projectile no native menu shows has no label (none) and the default (skull) icon.',
            'labels': [{'value': key, 'label': item['label'], 'native': key != 'none', 'icon': item['icon'],
                'iconSource': item['iconSource']} for key, item in mode_labels.items() if item['offered']],
            'icons': [{'value': key, 'source': 'auto' if item.get('auto') else 'native',
                'genericFallback': key == GENERIC_FALLBACK[0], 'description': GENERIC_FALLBACK[1].get(key)}
                for key, item in mode_icons.items() if item['offered']],
            'autoIcon': ('mode_icon = "auto" writes the label exact native icon (iconSource exact_native) or, when '
                'no native icon exists for it, the generic fallback; it uses the mode_label written in the same '
                'operation, else the current one. An explicit native icon always overrides it.'),
            'genericFallbackIcon': GENERIC_FALLBACK[0],
            'defaultIcon': ('default: the skull every unlabelled projectile holds; it is another texture set and '
                'shows as no usable weapon-function icon (the GAS live test, 2026-09-30).'),
            'acknowledgement': 'allow_unverified_effect (plus allow_shared when other weapons fire the projectile)',
            'customText': 'not supported: labels are native localization strings only',
            'customIcons': 'not supported in this release: icons are the native weapon-function icons only'},
        'safety': {'runtimeAddresses': False, 'nativeIdentifiers': False, 'writesDuringGeneration': 0}}
    text = json.dumps(document, indent=1)
    if re.search(r'0x[0-9A-Fa-f]{8}', text):
        raise ValueError('native identifier leaked into the public attack-output catalog')
    return {LUA_OUTPUT: '-- Generated by scripts/generate_attack_outputs.py; do not edit.\nreturn ' + lua(runtime) + '\n',
        JSON_OUTPUT: text + '\n'}


def generate(check=False):
    stale = []
    for path, body in outputs().items():
        if not path.exists() or path.read_text(encoding='utf-8') != body:
            stale.append(path)
            if not check:
                path.write_text(body, encoding='utf-8', newline='\n')
    if check and stale:
        raise RuntimeError('Stale attack outputs: ' + ', '.join(map(str, stale)))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    print(', '.join(str(path.relative_to(ROOT)) for path in generate(parser.parse_args().check)) or 'up to date')
