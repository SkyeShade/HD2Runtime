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
import beam_fields  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / 'research/attack-outputs-F5FEE03DCFDB.json'
ACTIVE = ROOT / 'research/active-projectile-sources-F5FEE03DCFDB.json'
SENTRY_HOSTS = ROOT / 'research/sentry-projectile-hosts-F5FEE03DCFDB.json'
DONORS = ROOT / 'research/stun-field-donors-F5FEE03DCFDB.json'
MORE_DONORS = ROOT / 'research/projectile-donors-F5FEE03DCFDB.json'
PRESENTATION = ROOT / 'research/weapon-presentation-F5FEE03DCFDB.json'
MODE_UNVERIFIED = ('The label and icon are the fired projectile\'s own ProjectileInfo members, which every native '
    'weapon-function mode reads as; the menu reader is not traced and an edited mode label or icon has not been '
    'gameplay-tested. Only native strings and native weapon-function icons are offered.')
ASSETS = ROOT / 'sdk/AssetDependencyCapabilities.json'
LUA_OUTPUT = ROOT / 'domains/attack_outputs.lua'
# Published names whose output a later correction removed: name -> why (api/target.lua refuses them with it).
_DEFENDER_150 = ('Projectile 150 is the round of the SEAF SMG, not of the SMG-37 Defender: 0.30.2 resolved the Defender '
    'to its own weapon root (research/weapon-roots-F5FEE03DCFDB.json), so this donor no longer exists. Pick another '
    'projectile (hd2.attack_output names) or an attack of the Defender itself.')
RETIRED = {'SMG-37 Defender (projectile 150)': _DEFENDER_150,
    'output/v1/projectile/smg-37-defender-projectile-150': _DEFENDER_150}
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


# Families whose provenCompositions list cross-class (host, output) pairs a user test proved in play.
COMPOSITION_FAMILIES = ('attack_output_cross_class', 'vehicle_projectile_reference')


def proven_compositions():
    """host -> {output semantic id: mechanism} for cross-class compositions a user test proved in play."""
    result = {}
    for name in COMPOSITION_FAMILIES:
        family = live_evidence.family(name)
        if family['status'] != 'live_proven':
            continue
        for item in family.get('provenCompositions', []):
            output = 'output/v1/projectile/' + slug(item['output'])
            result.setdefault(item['host'], {})[output] = item['mechanism']
    return result


def proven_host_pairs():
    """Every (host, output, mechanism) a live test proved, across families: cross-class compositions, same-class
    support host swaps and programmable-ammo function projectiles, for the catalog's provenCompositions view."""
    pairs = [(host, output, mechanism) for host, items in proven_compositions().items()
        for output, mechanism in items.items()]
    for family, mechanism, field in (('support_projectile_reference', 'component', 'attack.primary.projectile'),
            ('vehicle_projectile_reference', 'component', 'attack.primary.projectile'),
            ('weapon_programmable_ammo_added', 'programmable_ammo', 'function_ammo.projectile')):
        for item in live_evidence.family(family).get('provenTargets') or []:
            if item['field'] == field and live_evidence.proven(family):
                pairs += [(item['target'], value, mechanism) for value in item['values']]
    return sorted(set(pairs))


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


def public_slots(row):
    """The composable references of a selectable projectile row, for a projectile builder."""
    result = {}
    for field_id, key, offset, kind in SLOTS:
        field = row['slotFields'][field_id]
        result[key] = {'field': 'hd2.fields.' + field_id, 'current': field['currentDefault'] != 0,
            'allowNone': field['allowNone'], 'shared': field['shared'],
            'sharedConsumerCount': len(field['sharedConsumers']), 'consumerReferences': field['consumerReferences'],
            'namedSharedConsumers': [c for c in field['sharedConsumers'] if not c.startswith('0x')],
            'acknowledgements': ['allow_unverified_effect'] + (['allow_shared'] if field['shared'] else []),
            'liveProvenValues': field.get('liveProvenValues') or [],
            'valueHandle': 'hd2.attack_output(donor):' + {'directDamage': 'direct_damage',
                'impactExplosion': 'impact_explosion', 'expiryExplosion': 'expiry_explosion'}[key] + '()'}
    return result


def public_presentation(row):
    fields = row['presentationFields']
    label, icon = fields['presentation.mode_label'], fields['presentation.mode_icon']
    return {'label': label['currentDefault'], 'icon': icon['currentDefault'], 'writable': True,
        'shared': label['shared'], 'acknowledgements': ['allow_unverified_effect'] + (['allow_shared']
            if label['shared'] else []),
        # Values a live test showed in the menu: they need no allow_unverified_effect (allow_shared still applies).
        'liveProven': {'labels': label.get('liveProvenValues') or [], 'icons': icon.get('liveProvenValues') or []}}


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


BUILDER = ROOT / 'research/projectile-builder-F5FEE03DCFDB.json'
SLOT_UNVERIFIED = ('Re-points one reference of the projectile row (its direct-hit damage, impact or expiry explosion) '
    'to another catalogued output\'s. Every weapon firing this row changes; the donor row is only referenced. Not yet '
    'shown in game.')
SLOTS = (('projectile.direct_damage', 'directDamage', 60, 'damage_slot'),
    ('projectile.impact_explosion', 'impactExplosion', 144, 'explosion_slot'),
    ('projectile.expiry_explosion', 'expiryExplosion', 156, 'explosion_slot'))


def builder_research():
    return json.loads(BUILDER.read_text(encoding='utf-8'))


def slot_summary(slot):
    if slot is None:
        return None
    if 'radii' in slot:
        return {'type': slot['type'], 'volume': slot['volume'], 'volumeSeconds': slot['volumeSeconds'],
            'radius': slot['radii'][1], 'damage': slot['damage'].get('standard'),
            'statuses': [s['status'] for s in slot['damage'].get('statuses', [])],
            'submunition': slot['submunition'] is not None, 'arc': slot['arc'] is not None}
    return {'type': slot['type'], 'damage': slot.get('standard'), 'durable': slot.get('durable'),
        'armorPenetration': (slot.get('ap') or [None])[0], 'statuses': [s['status'] for s in slot.get('statuses', [])]}


def slot_fields(row, consumers, slots, references=None):
    """The three references of a selectable projectile row (research/projectile-builder): direct-hit damage, impact
    and expiry explosion. Shared when more than one entity fires the row (the typed reference graph: components,
    entity deltas and explosion submunitions; references counts every typed member naming the row)."""
    settings = row['referenceSettings']
    shared = sorted(consumers)
    backing = {'kind': 'settings', 'settings': 'projectile', 'recordType': settings['recordType'],
        'group': settings['group'], 'row': settings['row'], 'settingsType': settings['settingsType']}
    fields = {}
    for field_id, key, offset, kind in SLOTS:
        slot = slots[key]
        fields[field_id] = {'semanticFieldId': field_id, 'type': kind, 'editable': True,
            'acknowledgement': 'allow_unverified_effect', 'acknowledgementReason': SLOT_UNVERIFIED,
            'shared': len(shared) > 1, 'sharedConsumers': shared, 'consumerReferences': references or len(shared),
            'operationGroup': 'projectile_slots',
            'appliesWhen': 'use', 'currentDefault': slot['type'] if slot else 0, 'allowNone': kind == 'explosion_slot',
            'backing': dict(backing, offset=offset, width=4, storage='u32')}
    return promote(row, fields)


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
    return promote(row, {'presentation.mode_label': dict(common, semanticFieldId='presentation.mode_label',
            type='mode_label', currentDefault=label, backing=dict(backing, offset=12, width=4, storage='u32')),
        'presentation.mode_icon': dict(common, semanticFieldId='presentation.mode_icon', type='mode_icon',
            currentDefault=projectile['icon'], backing=dict(backing, offset=16, width=8, storage='u64'))})


def promote(row, fields):
    """Exact live promotions (schemas/live_evidence.json provenTargets keyed by the output's owner name): the proven
    values (slot donors "<output id>#<slot>" or none; labels; resolved icons) need no allow_unverified_effect."""
    targets = live_evidence.proven_targets()
    for field_id, field in fields.items():
        evidence = targets.get((row['owner']['name'], field_id))
        if evidence and evidence.get('values'):
            field['liveEvidence'] = evidence
            field['liveProvenValues'] = list(evidence['values'])
    return fields


# Beam outputs and beam swaps (0.30.4; research/beam-outputs-F5FEE03DCFDB.json, scripts/beam_fields.py). A beam output is
# the BeamSettings row a named Helldiver-side owner fires (its active beam source); it is a donor for beam hosts only
# (hd2.fields.attack.beam), never for projectile hosts. Enemy beams are catalogued read-only: their effects ship in
# faction content no catalogued package names.
BEAM_DONOR_KINDS = {'player_weapon': 'player_weapon', 'support_weapon': 'support_weapon', 'sentry': 'stratagem'}
BEAM_HOST_KINDS = {'player_weapon': 'player_weapon', 'support_weapon': 'support_weapon',
    'vehicle_weapon': 'vehicle_weapon', 'sentry': 'vehicle_weapon'}
# Enemy beams by BeamType: a stable public name, checked against the research owners below.
ENEMY_BEAMS = {12: ('Illuminate tripod beam', 'tripod'), 23: ('Illuminate tripod second beam', 'tripod'),
    22: ('Illuminate war machine cannon beam', 'war_machine'), 14: ('Illuminate turret beam', 'turret_01'),
    29: ('Illuminate objective turret beam', 'turret_tactical_obj')}
ENEMY_BEAM_REASON = ('An enemy beam: no catalogued package ships its effect (Illuminate faction content), so Runtime '
    'cannot load its assets before a swap, and its owner is not a Helldiver weapon. Listed read-only.')
BEAM_OTHER_REASON = ('Not a donor: which beam the {name} fires is not proven. {reason} The two candidates are its '
    "record's BeamType {base} and the {fires} beam (BeamType {value}); for the latter use hd2.attack_output('{fires}').")
BEAM_ATTACHMENT_EFFECT = ("The muzzle definition's delta row is the beam the weapon is built with (its BeamWeapon +0 is "
    'overwritten by it, research/beam-outputs-F5FEE03DCFDB.json), but no live test has confirmed an edited beam delta '
    'yet: the delta is applied when the weapon is built (re-equip or a new call-in after the write).')
BEAM_ATTACHMENT_SHARED = ('A muzzle definition applies to every weapon that equips it: sharedWithWeapons lists the other '
    'catalogued weapons that default to it. The AX/LAS-5 Rover drone gun also defaults to Laser. Standard Prism; whether '
    'a drone weapon applies it is not proven (its beam source is AMBIGUOUS), so a write may change the Rover\'s beam too. '
    'allow_shared is required.')


def beam_outputs(runtime_outputs, aliases, public, assets):
    """Beam outputs (donors and read-only listings), beam hosts and beam attachment sources."""
    data = beam_fields.research()
    owners = [(record, item) for record in data['records'] for item in record['owners']]
    host_name = {}
    for record, item in owners:
        if item['kind'] in BEAM_HOST_KINDS:
            host_name[item['resource']] = item['name'] + (' / weapon' if item['kind'] == 'sentry' else '')
    donors, by_type = {}, {}
    for record, item in owners:
        if item['kind'] not in BEAM_DONOR_KINDS or not item['componentIdentity']['uniqueOwner']:
            continue
        source = item['activeSource'] or {}
        if item['status'] not in ('ACTIVE_DIRECT', 'INDIRECT') or source.get('value') != record['beamType']:
            continue
        package = next((p for p in item['packages'] if p['listsBeamResources'] and not p['key'].startswith(
            ('pickup/', 'mounted_weapon/'))), None)
        dependency = assets.get(package['key']) if package else None
        if not dependency or not dependency.get('autoLoadSupported'):
            raise ValueError(item['name'] + ': a beam donor needs a loadable package that lists its beam resources')
        row = beam_fields.row(record['beamType'])
        semantic = 'output/v1/beam/' + slug(item['name'])
        identity = item['componentIdentity']
        runtime_outputs[semantic] = {'id': semantic, 'family': 'beam',
            'owner': {'kind': BEAM_DONOR_KINDS[item['kind']], 'name': item['name']},
            'resource': item['resource'], 'entityRow': item['entityRow'],
            'backing': {'kind': 'component', 'component': beam_fields.BEAM, 'offset': 0, 'storage': 'u32', 'width': 4,
                'recordIndex': identity['recordIndex'], 'indexRow': identity['indexRow'],
                'ownerCount': identity['ownerCount'], 'uniqueOwner': identity['uniqueOwner']},
            'currentDefault': record['beamType'], 'editable': True, 'selectableAs': 'beam',
            'referenceSettings': row['settings'], 'beamClass': beam_fields.CLASSES.get(record['fireMode']),
            'dependencyKey': package['key'], 'hostWeapon': host_name.get(item['resource']),
            'familyReason': CROSS_FAMILY.format(family='Beam', emitter=FAMILY_EMITTER['beam'], extra=EXTRA['beam'])}
        for alias in (item['name'], item['name'] + '/primary'):
            if alias in aliases:
                raise ValueError('duplicate attack output alias ' + alias)
            aliases[alias] = semantic
        donors[semantic] = (record, item, row, package)
        by_type[record['beamType']] = semantic
    for semantic, (record, item, row, package) in sorted(donors.items()):
        public.append({'semanticId': semantic, 'family': 'beam',
            'kind': 'pulsed_multi_beam' if record['fireMode'] == 6 else 'continuous_beam',
            'beamClass': beam_fields.CLASSES.get(record['fireMode']),
            'owner': {'kind': BEAM_DONOR_KINDS[item['kind']], 'name': item['name']}, 'emitter': 'BeamWeapon',
            'beamType': record['beamType'], 'compatibilityClass': None,
            'selectableAsProjectileReference': False, 'selectableAsBeamReference': True,
            'compatibleHostFamilies': ['beam'], 'requiredCoordinatedReferences': [],
            'blockedReason': CROSS_FAMILY.format(family='Beam', emitter=FAMILY_EMITTER['beam'], extra=EXTRA['beam']),
            'row': {'length': row['length'], 'radius': round(row['radius'], 4), 'explosion': bool(row['explosion']),
                'pulseRow': bool(row['pulseRowFlag'])},
            'ownerFireResource': item['fireResource'], 'ownerFiresThisBeam': item['status'],
            'package': {'name': package['name'].rsplit('/', 1)[-1], 'known': True, 'autoLoad': True,
                'listsBeamResources': True},
            'acknowledgements': {'donor': ['allow_unverified_reference', 'allow_unverified_effect'],
                'restoreOwn': []},
            'liveProof': None})
    # Owners that are not donors but fire a beam a Runtime catalogue names: the Rover drone gun (another weapon's beam)
    # and the enemy beams (read-only with the reason).
    for record, item in owners:
        source = item['activeSource'] or {}
        if item['kind'] == 'vehicle_weapon' and item['status'] == 'AMBIGUOUS' and source.get('item'):
            fires = by_type.get(source['value'])
            if not fires:
                raise ValueError(item['name'] + ' names a candidate beam no donor output names')
            semantic = 'output/v1/beam/' + slug(item['name'])
            fires_name = runtime_outputs[fires]['owner']['name']
            reason = BEAM_OTHER_REASON.format(name=item['name'], fires=fires_name, reason=item['reason'],
                base=record['beamType'], value=source['value'])
            runtime_outputs[semantic] = {'id': semantic, 'family': 'beam',
                'owner': {'kind': 'vehicle_weapon', 'name': item['name']}, 'editable': False, 'reason': reason,
                'familyReason': reason}
            for alias in (item['name'], item['name'] + '/primary'):
                if alias in aliases:
                    raise ValueError('duplicate attack output alias ' + alias)
                aliases[alias] = semantic
            public.append({'semanticId': semantic, 'family': 'beam', 'kind': 'continuous_beam',
                'beamClass': beam_fields.CLASSES.get(record['fireMode']),
                'owner': {'kind': 'vehicle_weapon', 'name': item['name']}, 'emitter': 'BeamWeapon',
                'beamType': record['beamType'], 'candidateBeamTypes': [record['beamType'], source['value']],
                'compatibilityClass': None, 'selectableAsProjectileReference': False,
                'selectableAsBeamReference': False, 'candidateOutput': fires, 'compatibleHostFamilies': [],
                'requiredCoordinatedReferences': None, 'blockedReason': reason,
                'ownerFireResource': item['fireResource'], 'ownerFiresThisBeam': item['status'],
                'package': {'name': None, 'known': False, 'autoLoad': False}, 'acknowledgements': None,
                'liveProof': None})
    for beam_type, (name, needle) in sorted(ENEMY_BEAMS.items()):
        fired = [item for record, item in owners if record['beamType'] == beam_type]
        if not fired or not any(needle in (item['name'] or '') and item['kind'] in ('enemy', 'enemy_structure')
                for item in fired):
            raise ValueError(f'enemy beam {beam_type} no longer matches the research owners')
        semantic = 'output/v1/beam/' + slug(name)
        label = name + ' (beam ' + str(beam_type) + ')'
        runtime_outputs[semantic] = {'id': semantic, 'family': 'beam', 'owner': {'kind': 'enemy', 'name': name},
            'editable': False, 'reason': ENEMY_BEAM_REASON, 'familyReason': ENEMY_BEAM_REASON}
        for alias in (name, label):
            if alias in aliases:
                raise ValueError('duplicate attack output alias ' + alias)
            aliases[alias] = semantic
        row = beam_fields.row(beam_type)
        public.append({'semanticId': semantic, 'family': 'beam', 'kind': 'continuous_beam', 'beamClass': 'continuous',
            'owner': {'kind': 'enemy', 'name': name}, 'names': [name, label], 'emitter': 'BeamWeapon',
            'beamType': beam_type, 'compatibilityClass': None, 'selectableAsProjectileReference': False,
            'selectableAsBeamReference': False, 'compatibleHostFamilies': [], 'requiredCoordinatedReferences': None,
            'blockedReason': ENEMY_BEAM_REASON, 'row': {'length': row['length'], 'radius': round(row['radius'], 4),
                'explosion': bool(row['explosion']), 'pulseRow': bool(row['pulseRowFlag'])},
            'firedBy': sorted(item['name'] for item in fired if item['name']), 'ownerFireResource': [],
            'package': {'name': None, 'known': False, 'autoLoad': False}, 'acknowledgements': None, 'liveProof': None})
    # Hosts: every catalogued beam weapon, by the member its beam swap writes.
    hosts, attachments, beam_aliases, public_hosts = {}, {}, {}, []
    sharers = {}
    for record, item in owners:
        source = item['activeSource'] or {}
        # Every catalogued beam weapon that defaults to a muzzle patching BeamWeapon +0, proven source or not.
        if item['kind'] in BEAM_HOST_KINDS and source.get('addPath'):
            sharers.setdefault(source['addPath'], []).append(host_name[item['resource']])
    for record, item in owners:
        if item['kind'] not in BEAM_HOST_KINDS:
            continue
        kind, name = BEAM_HOST_KINDS[item['kind']], host_name[item['resource']]
        key = kind + ':' + name
        source = item['activeSource'] or {}
        fired_type = beam_fields.active_type(record, item)
        mechanism = {'ACTIVE_DIRECT': 'component', 'INDIRECT': 'attachment'}.get(item['status'])
        if mechanism and not item['componentIdentity']['uniqueOwner']:
            mechanism = None
        hosts[key] = {'kind': kind, 'weapon': name, 'status': item['status'], 'mechanism': mechanism,
            'member': 'BeamWeapon +0' if mechanism != 'attachment' else source['item'] + ' delta (BeamWeapon +0)',
            'reason': item['reason'], 'beamType': fired_type, 'beamClass': beam_fields.CLASSES.get(record['fireMode']),
            'fires': by_type.get(fired_type), 'stratagem': item['name'] if item['kind'] == 'sentry' else None}
        beam_aliases[key] = by_type.get(fired_type)
        if mechanism == 'attachment':
            others = sorted(set(sharers[source['addPath']]) - {name})
            attachments[key] = {'id': 'beam-attachment/v1/' + slug(name) + '/' + slug(source['item']), 'weapon': name,
                'kind': kind, 'item': source['item'], 'semanticFieldId': beam_fields.FIELD, 'type': 'beam_reference',
                'displayName': 'Attack beam reference', 'referenceKind': 'beam',
                'currentDefault': {'weapon': name, 'beamType': fired_type},
                'referenceSettings': beam_fields.row(fired_type)['settings'],
                'beamClass': beam_fields.CLASSES.get(record['fireMode']), 'editable': True,
                'acknowledgement': 'allow_unverified_effect', 'acknowledgementReason': BEAM_ATTACHMENT_EFFECT,
                'affectsMultipleWeapons': True, 'sharedWithWeapons': others, 'sharedReason': BEAM_ATTACHMENT_SHARED,
                'writeScope': 'attachment_definition', 'appliesWhen': 'weapon_build',
                'resource': source['addPath'], 'hashmapSlot': source['hashmapSlot'],
                'settingsIndex': source['settingsIndex'], 'component': beam_fields.BEAM_INDEX, 'componentOffset': 0,
                'dataOffset': source['dataOffset'],
                'backing': {'kind': 'entity_delta', 'component': beam_fields.BEAM, 'offset': 0, 'width': 4,
                    'storage': 'u32'},
                'defaultCustomization': {'offset': source['defaultPairOffset'], 'slot': source['slot'],
                    'optionId': int(source['optionId'], 16)}}
        public_hosts.append({'weapon': name, 'kind': kind, 'stratagem': hosts[key]['stratagem'],
            'status': item['status'], 'mechanism': mechanism, 'member': hosts[key]['member'], 'reason': item['reason'],
            'writable': mechanism is not None, 'beamClass': hosts[key]['beamClass'], 'fires': hosts[key]['fires'],
            'sharedWithWeapons': attachments[key]['sharedWithWeapons'] if key in attachments else [],
            'acknowledgements': (['allow_shared'] if key in attachments else []) + ['allow_unverified_reference',
                'allow_unverified_effect'],
            'write': ('beam_source()' + (' (the muzzle definition: hd2.fields.attack.beam)' if mechanism == 'attachment'
                else ' (hd2.fields.attack.beam on the weapon itself)')) if mechanism else None})
    public_hosts.sort(key=lambda h: (h['kind'], h['weapon']))
    model = {'rule': ('A beam swap re-points the BeamType (BeamWeapon +0) a weapon that already owns a BeamWeapon '
            'component fires; no component is ever added, so a projectile weapon cannot fire a beam (docs/attack-'
            "outputs.md \"Lasers everywhere\"). The written member is the active beam source: the weapon's own record "
            "(component) or, where a default customization item patches BeamWeapon +0 at weapon build, that item's "
            'delta row (attachment, shared by every weapon that equips it).'),
        'api': {'source': ("weapon:beam_source() (player, support and mounted weapons; "
                "hd2.stratagem(name):attack('primary'):beam_source() for a sentry)"),
            'field': 'hd2.fields.attack.beam', 'expect': "weapon:beam() (the host's own beam; also the restore value)",
            'value': "hd2.attack_output(donor) or another beam weapon's weapon:beam()"},
        'acknowledgements': beam_fields.REFERENCE_REASON,
        'assets': ("The donor owner's own loadout package (it lists the beam row's resources: research/beam-outputs "
            'packages[].listsBeamResources) is loaded before the write; a donor without one is not catalogued.'),
        'hostKeeps': 'its fire mode, rate, pulse, heat or charge, magazine, handling and sounds',
        'donorBrings': 'its BeamSettings row: length, radius, damage row, hit effects and the beam visuals',
        'research': 'research/beam-outputs-F5FEE03DCFDB.json',
        'counts': {'records': data['summary']['records'], 'owners': data['summary']['owners'],
            'donors': len(donors), 'hosts': len(public_hosts),
            'writableHosts': sum(1 for h in public_hosts if h['writable'])}}
    return {'hosts': hosts, 'attachments': attachments, 'aliases': beam_aliases, 'public': public_hosts,
        'model': model}


def outputs():
    research = json.loads(RESEARCH.read_text(encoding='utf-8'))
    mode_labels, mode_icons, mode_projectiles = mode_catalog()
    active, sources, ammunition, by_weapon = active_sources()
    runtime_outputs, aliases, public = {}, {}, []
    builder = builder_research()
    builder_slots = {item['type']: item['slots'] for item in builder['projectileOutputs']}
    # Who fires each row, from the typed reference graph (a superset of the package owners research/attack-outputs saw).
    builder_owners = {item['type']: item['consumerOwners'] for item in builder['projectileOutputs']}
    builder_references = {item['type']: item['consumerCount'] for item in builder['projectileOutputs']}
    for entry in sorted(research['weapons'], key=lambda e: (e['kind'], e['weapon'])):
        if entry['family'] == 'beam':
            # Beam outputs come from research/beam-outputs-F5FEE03DCFDB.json (beam_outputs above): every beam row a
            # weapon fires, by its active source.
            continue
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
                dependencyKey=entry.get('assetKey') or entry['kind'] + '/' + entry['weapon'])
        else:
            row['reason'] = (CROSS_FAMILY.format(family=entry['family'].capitalize(),
                emitter=FAMILY_EMITTER.get(entry['family'], entry['component']), extra=EXTRA.get(entry['family'], ''))
                if entry['family'] != 'projectile' else owner_reason if fires == 'not_established' else
                'The projectile row this weapon fires is not resolved in the retained snapshot.')
        if selectable:
            owners = builder_owners.get(row['currentDefault'], entry.get('outputConsumers') or [])
            row['presentationFields'] = presentation_fields(row, owners, mode_labels, mode_icons, mode_projectiles)
            row['slotFields'] = slot_fields(row, owners, builder_slots[row['currentDefault']],
                builder_references.get(row['currentDefault']))
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
            'slots': public_slots(row) if selectable else None,
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
        runtime_outputs[semantic]['slotFields'] = slot_fields(runtime_outputs[semantic],
            builder_owners.get(donor['projectileType']) or donor.get('consumers') or [donor['name']],
            builder_slots[donor['projectileType']], builder_references.get(donor['projectileType']))
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
            'slots': public_slots(runtime_outputs[semantic]),
            'liveProof': output_live_proof(donor['name'])})
    # More projectile donors (research/projectile-donors-F5FEE03DCFDB.json): named projectile types held by one fixed
    # member of one uniquely owned, profiled component record (a stratagem's Eagle payload, orbital shell or entity
    # weapon; a weapon's second projectile; a vehicle gun). Selectable as a projectile reference only (no row fields
    # of their own here); not yet live-tested, so every use needs allow_unverified_reference and
    # allow_unverified_effect, whatever the class.
    for donor in json.loads(MORE_DONORS.read_text(encoding='utf-8'))['donors']:
        semantic = 'output/v1/projectile/' + slug(donor['name'])
        owner = {'kind': donor['ownerKind'], 'name': donor['owner']}
        settings = donor['settings']
        entry = {'id': semantic, 'family': 'projectile', 'owner': owner,
            'resource': donor['resource'], 'entityRow': donor['entityRow'],
            'backing': {'kind': 'component', 'component': donor['component'], 'offset': donor['member'],
                'storage': 'u32', 'width': 4, **donor['componentIdentity']},
            'currentDefault': donor['projectileType'], 'editable': True, 'unverifiedDonor': True,
            'referenceSettings': {'group': settings['group'], 'row': settings['row'],
                'recordType': settings['recordType'], 'settingsType': settings['settingsType']},
            'compatibilityClass': donor['compatibilityClass'], 'role': donor['role']}
        if donor['ownerKind'] == 'stratagem':
            key = 'projectile_donor/' + donor['name']
            package = assets.get(key) or {}
            if not package.get('autoLoadSupported'):
                raise ValueError(donor['name'] + ': a stratagem donor needs a loadable package (' + key + ')')
            entry['dependencyKey'] = key
        else:
            package = {'package': None}
        runtime_outputs[semantic] = entry
        for alias in donor['aliases']:
            if alias in aliases:
                raise ValueError('duplicate attack output alias ' + alias)
            aliases[alias] = semantic
        impact, expiry = donor.get('impact'), donor.get('expiry')
        public.append({'semanticId': semantic, 'family': 'projectile', 'kind': 'projectile_donor', 'owner': owner,
            'role': donor['role'], 'names': list(donor['aliases']), 'projectileType': donor['projectileType'],
            'emitter': donor['component'].replace('ComponentData', ''), 'member': donor['member'],
            'compatibilityClass': donor['compatibilityClass'],
            'selectableAsProjectileReference': True, 'compatibleHostFamilies': ['projectile'],
            'requiredCoordinatedReferences': [], 'blockedReason': None,
            'chain': {'impactExplosion': bool(impact), 'expiryExplosion': bool(expiry),
                'submunition': bool(impact and impact.get('shrapnel')), 'arcOnImpact': bool(impact and impact.get('arc'))},
            'flight': {'velocity': round(donor['velocity'], 3), 'mass': round(donor['mass'], 3),
                'unitDriven': bool(donor['properties'].get('unit'))},
            'ownerFireResource': [],
            'package': {'name': package.get('package'), 'known': True, 'autoLoad': True,
                'via': 'owner weapon' if donor['ownerKind'] != 'stratagem' else 'owner entity loadout package'},
            'acknowledgements': {'sameClass': ['allow_unverified_reference', 'allow_unverified_effect'],
                'crossClass': ['allow_unverified_reference', 'allow_unverified_effect']},
            'ownerFiresThisProjectile': 'fires_reference',
            'liveProof': None})
    # Native spare twins (research/projectile-builder): a row no typed data member references that is byte-identical
    # to a catalogued output's row except its references. The same flight, visuals and audio as its twin (whose
    # package covers its assets), with an identity no other consumer uses: composing it changes nothing else.
    for twin in builder['spareTwins']:
        owner_output = twin['twinOutputs'][0]
        twin_id = aliases[owner_output['weapon']]
        twin_row = runtime_outputs[twin_id]
        name = owner_output['weapon'] + ' (spare twin)'
        semantic = 'output/v1/projectile/' + slug(name)
        identity = twin['identity']
        row = {'id': semantic, 'family': 'projectile', 'owner': {'kind': 'spare_row', 'name': name},
            'spare': {'twinOf': twin_id, 'twinSettings': twin['twinIdentity'],
                'excluded': [[item['from'], item['to']] for item in twin['excludedFromTwinCheck']],
                # Unreferenced is proven on this build only (the typed reference graph); build migration does not
                # re-derive it, so every other build refuses the row (SPARE_TWIN_UNVERIFIED_BUILD).
                'researchedBuild': builder['source']['exeSha256']},
            'currentDefault': twin['spare'], 'editable': True,
            'referenceSettings': identity, 'compatibilityClass': twin_row['compatibilityClass'],
            'dependencyKey': twin_row.get('dependencyKey'), 'dependencyOwner': twin_row['owner'],
            'referenceScope': ['function_ammo.projectile']}
        twin_projectile = mode_projectiles.get(str(twin['twin']))
        mode_projectiles[str(twin['spare'])] = dict(twin_projectile, settings=identity)
        row['presentationFields'] = presentation_fields(row, [], mode_labels, mode_icons, mode_projectiles)
        row['slotFields'] = slot_fields(row, [], twin['slots'])
        runtime_outputs[semantic] = row
        for alias in (name, name + '/primary'):
            if alias in aliases:
                raise ValueError('duplicate attack output alias ' + alias)
            aliases[alias] = semantic
        twin_public = next(item for item in public if item['semanticId'] == twin_id)
        public.append({'semanticId': semantic, 'family': 'projectile', 'kind': 'spare_twin',
            'owner': {'kind': 'spare_row', 'name': name}, 'emitter': 'ProjectileSettings',
            'compatibilityClass': row['compatibilityClass'], 'selectableAsProjectileReference': True,
            'compatibleHostFamilies': ['projectile'], 'referenceScope': list(row['referenceScope']),
            'requiredCoordinatedReferences': [], 'blockedReason': None,
            'spareTwin': {'twinOf': twin_id, 'twinName': owner_output['weapon'], 'independent': True,
                'consumers': 0, 'borrowedVanillaRow': True, 'interim': True, 'buildScoped': True,
                'differingReferences': sorted(twin['differingReferences']),
                'reason': ('No typed data member references this row; it is byte-identical to its twin except its '
                    'references, so it flies, looks and sounds like the twin and its twin\'s package covers it. '
                    'Composing it (slots, presentation) changes no other weapon. It borrows a vanilla ProjectileType '
                    'slot: an interim until Runtime owns ids of its own, and re-proven before every write.')},
            'chain': {'impactExplosion': bool(twin['slots']['impactExplosion']),
                'expiryExplosion': bool(twin['slots']['expiryExplosion']), 'submunition': False, 'arcOnImpact': False},
            'ownerFireResource': [], 'package': twin_public['package'],
            'acknowledgements': {'sameClass': [],
                'crossClass': ['allow_unverified_reference', 'allow_unverified_effect']},
            'ownerFiresThisProjectile': 'spare_row', 'presentation': public_presentation(row),
            'slots': public_slots(row), 'liveProof': None})
    beams = beam_outputs(runtime_outputs, aliases, public, assets)
    # Hosts: a player attack whose fired projectile Runtime can write. `component`: the attack's own ProjectileWeapon
    # +0 is its active source; `ammunition`: the default ammunition delta is. Both keep the live controls' structure
    # (magazine-fed; no rounds, charge or heat). Support weapons have no guarded projectile reference target.
    hosts = {}
    # Support weapons: the same rule. ACTIVE_DIRECT (their own ProjectileWeapon +0 is fired) and magazine-fed.
    classes = {entry['weapon']: entry.get('compatibilityClass') for entry in research['weapons']}
    support_sources = {}
    # Mounted weapons join the same rule and pool (kind vehicle_weapon; sharedEntity: another mount carries the same
    # weapon entity, so a write there changes both mounts).
    host_items = ([(item, 'support_weapon') for item in builder['supportHosts']]
        + [(item, 'vehicle_weapon') for item in builder.get('mountedHosts', [])])
    # Sentry and emplacement hosts (0.30.2; research/sentry-projectile-hosts-F5FEE03DCFDB.json): their deployed entity's
    # own ProjectileWeapon +0, keyed '<stratagem> / weapon' like a mount. The same rule: ACTIVE_DIRECT and magazine-fed.
    for item in json.loads(SENTRY_HOSTS.read_text(encoding='utf-8'))['hosts']:
        key = item['weapon'] + ' / weapon'
        classes[key] = item.get('compatibilityClass')
        host_items.append(({'weapon': key, 'status': item['status'],
            'mechanism': 'component' if item['status'] == 'ACTIVE_DIRECT' else None, 'reason': item['reason'],
            'componentHost': item['status'] == 'ACTIVE_DIRECT' and item['magazineFed']}, 'vehicle_weapon'))
    for item, kind in host_items:
        host = bool(item['componentHost'] and classes.get(item['weapon']))
        if host:
            hosts[item['weapon']] = {'kind': kind, 'class': classes[item['weapon']], 'mechanism': 'component'}
            if item.get('sharedEntity'):
                hosts[item['weapon']]['sharedEntity'] = item['sharedEntity']
        reason = item['reason']
        if not host and item['status'] == 'ACTIVE_DIRECT':
            reason = ('Every shot is ProjectileWeapon +0, but the weapon is not magazine-fed: the host rule the live '
                'controls established covers magazine-fed weapons only (no rounds feed, charge or heat), so its '
                'projectile reference stays read-only.')
        support_sources[item['weapon']] = {'status': item['status'], 'mechanism': item['mechanism'],
            'member': 'ProjectileWeapon +0' if item['mechanism'] == 'component' else None, 'reason': reason,
            'writable': host, 'compatibilityClass': classes.get(item['weapon']), 'kind': kind,
            'sharedEntity': item.get('sharedEntity') or []}
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
    for name in RETIRED:
        if name in aliases or name in runtime_outputs:
            raise ValueError(f'retired attack output {name} is catalogued again')
    runtime = migration_overlay.apply('attack_outputs', {'outputs': runtime_outputs, 'aliases': aliases,
        'retired': RETIRED, 'modeLabels': runtime_labels, 'modeIcons': runtime_icons,
        'hosts': hosts, 'sources': sources, 'supportSources': support_sources, 'ammunition': ammunition,
        'beamHosts': beams['hosts'], 'beamAttachments': beams['attachments'], 'beamAliases': beams['aliases'],
        'beamDonorReason': beam_fields.REFERENCE_REASON,
        'provenCompositions': compositions, 'crossClassReason': UNVERIFIED_REFERENCE})
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
    for name, row in sorted(support_sources.items()):
        public_sources.append({'weapon': name, 'kind': row['kind'], 'attack': 'primary', 'status': row['status'],
            'mechanism': row['mechanism'], 'member': row['member'], 'reason': row['reason'],
            'directWritable': row['writable'], 'previouslyWritable': False, 'sharedEntity': row['sharedEntity'],
            'write': (('hd2.support_weapon(name):attack(role):projectile_source()' if row['kind'] == 'support_weapon'
                else 'hd2.vehicle(vehicle):weapon(mount):attack(role):projectile_source()')
                + ' (hd2.fields.attack.projectile)' if row['writable'] else None)})
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
        'beamSources': beams['public'],
        'beamModel': beams['model'],
        'ammunitionSources': public_ammunition,
        'provenCompositions': [{'host': host, 'output': output, 'mechanism': mechanism,
            'acknowledgementsRequired': []} for host, output, mechanism in proven_host_pairs()],
        'hostModel': {'componentHosts': sorted(n for n, h in hosts.items() if h['mechanism'] == 'component'),
            'ammunitionHosts': sorted(n for n, h in hosts.items() if h['mechanism'] == 'ammunition'),
            'rule': ('A projectile output needs a player attack whose fired projectile Runtime can write. component: '
                'the attack\'s own ProjectileWeapon +0 is its active source (ACTIVE_DIRECT). ammunition: the default '
                'ammunition delta is (INDIRECT), written through weapon:ammunition(). Both keep the live controls\' '
                'structure: magazine-fed, empty magazine pattern, no WeaponRounds, WeaponCharge or WeaponHeat. A '
                'projectile pointer existing is not enough. Support weapons follow the same rule (component hosts: '
                'hd2.support_weapon(name):attack(role) with hd2.fields.attack.projectile); the donor pool is one '
                'catalog (hd2.attack_output(name)) whatever loadout slot the donor comes from.'),
            'hostLiveProof': {name: host_live_proof(name) for name in sorted(hosts) if host_live_proof(name)},
            'retained': research['hostRetains']},
        'liberatorCases': cases,
        # The projectile builder (weapon:programmable_ammo(), research/projectile-builder): what kind of composition the
        # game supports, the slot model and the guards, for tools that build modes (no native identifiers).
        'projectileBuilder': {
            'api': {'builder': 'weapon:programmable_ammo()', 'operations': 'builder:operations(spec)',
                'presentation': 'builder:presentation(spec)', 'bases': 'builder:bases()',
                'slotHandles': 'hd2.attack_output(name):direct_damage() / :impact_explosion() / :expiry_explosion()',
                'acknowledgements': 'passed on from the spec exactly as given; the builder never adds one'},
            'classes': {name: {'supported': item['supported'], 'interim': item.get('interim', False),
                'reason': item['reason']} for name, item in builder['classes'].items()},
            'rows': {'total': builder['model']['rows'], 'referenced': builder['model']['referencedRows'],
                'unreferenced': len(builder['model']['spareRows'])},
            'spareTwins': [{'output': 'output/v1/projectile/' + slug(t['twinOutputs'][0]['weapon'] + ' (spare twin)'),
                'twinOf': aliases[t['twinOutputs'][0]['weapon']], 'borrowedVanillaRow': True, 'interim': True,
                'differingReferences': sorted(t['differingReferences'])} for t in builder['spareTwins']],
            'slots': [{'field': 'hd2.fields.' + field_id, 'key': key, 'kind': kind,
                'none': 'removes it' if kind == 'explosion_slot' else 'refused (a projectile always has a direct hit)',
                'meaning': {'directDamage': 'the damage, penetration and statuses of a direct hit',
                    'impactExplosion': 'the explosion released when the projectile hits',
                    'expiryExplosion': 'the explosion released when the projectile expires (a stuck spear, a timed shell)'
                    }[key]} for field_id, key, offset, kind in SLOTS],
            'guards': {
                'donorProof': 'the donor row is only read; its reference is re-proven live (CONFLICT if it moved)',
                'slotTypes': 'a damage slot takes only a direct_damage() handle, an explosion slot an explosion handle',
                'spareTwin': 'before every write the spare twin is re-proven byte-identical to its twin outside its '
                    'references and presentation (SPARE_TWIN_CHANGED); it is offered only on the build its row was '
                    'proven unreferenced on (SPARE_TWIN_UNVERIFIED_BUILD elsewhere)',
                'package': 'the donor package is a declared asset dependency; no catalogued package is refused '
                    '(ASSET_UNAVAILABLE)',
                'recursion': 'an explosion chain (explosion, its submunition projectile, that projectile\'s explosions, '
                    'read live) that reaches the written row is refused (RECURSIVE_COMPOSITION)',
                'sharing': 'a slot or presentation write changes every entity that fires the row; more than one needs '
                    'allow_shared (slots[].sharedConsumerCount, consumerReferences)',
                'effect': 'every slot write needs allow_unverified_effect: no composed slot is gameplay-tested yet'},
            'unprovenMembers': ['two f32 values after the impact explosion (a delay or a chance is not proven)',
                'a ProjectileStatusEffect enum (what it does is not proven)'],
            'examples': ['SpeargunProjectileBuilderTest', 'HMGSpecialAmmoTest', 'UnifiedProjectileSwapTest']},
        'summary': {'outputs': len(public), 'byFamily': {family: sum(1 for o in public if o['family'] == family)
                for family in research['summary']['byFamily']},
            'stratagemDonors': sorted({o['owner']['name'] for o in public if o['owner']['kind'] == 'stratagem'
                and o['family'] == 'projectile'}),
            'selectable': sum(1 for o in public if o['selectableAsProjectileReference']),
            'beamDonors': sum(1 for o in public if o.get('selectableAsBeamReference')),
            'beamHosts': sum(1 for h in beams['public'] if h['writable']),
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
            'fallback': ('A projectile no native menu shows has no label (none) and the default icon, a placeholder '
                'the weapon-function menu shows as an empty spot.'),
            'labels': [{'value': key, 'label': item['label'], 'native': key != 'none', 'icon': item['icon'],
                'iconSource': item['iconSource']} for key, item in mode_labels.items() if item['offered']],
            'icons': [{'value': key, 'source': 'auto' if item.get('auto') else 'native',
                'genericFallback': key == GENERIC_FALLBACK[0], 'description': GENERIC_FALLBACK[1].get(key)}
                for key, item in mode_icons.items() if item['offered']],
            'autoIcon': ('mode_icon = "auto" writes the label exact native icon (iconSource exact_native) or, when '
                'no native icon exists for it, the generic fallback; it uses the mode_label written in the same '
                'operation, else the current one. An explicit native icon always overrides it.'),
            'genericFallbackIcon': GENERIC_FALLBACK[0],
            'defaultIcon': ('default: the placeholder every unlabelled projectile holds (a skull resource from another '
                'texture set). The weapon-function menu shows it as an empty spot (live tests, 2026-09-30), so it is '
                'only for restoring vanilla; "auto" never writes it.'),
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
