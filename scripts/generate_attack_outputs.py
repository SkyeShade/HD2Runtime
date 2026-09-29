"""Generate the attack-output catalog from research/attack-outputs-F5FEE03DCFDB.json.

There is no common native attack-output abstraction: a weapon entity owns one output-family component
(ProjectileWeapon, BeamWeapon, ArcWeapon, SprayWeapon, MeleeWeapon), each referencing its own settings family through
its own enum. The catalog is therefore family-aware:

- domains/attack_outputs.lua (runtime): every catalogued output by semantic ID. Projectile outputs carry the source
  identity the projectile-reference write re-proves live (owner entity, its ProjectileWeapon record identity, the
  ProjectileSettings row); beam, arc, spray and melee outputs carry only their family and the reason no projectile
  host can reference them. Also the projectile hosts eligible for cross-class outputs.
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


def outputs():
    research = json.loads(RESEARCH.read_text(encoding='utf-8'))
    runtime_outputs, aliases, public, hosts = {}, {}, [], {}
    for entry in sorted(research['weapons'], key=lambda e: (e['kind'], e['weapon'])):
        semantic = f"output/v1/{entry['family']}/{slug(entry['weapon'])}"
        owner = {'kind': entry['kind'], 'name': entry['weapon']}
        selectable = (entry['family'] == 'projectile' and entry.get('output') is not None
            and entry.get('compatibilityClass') is not None)
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
                if entry['family'] != 'projectile' else
                'The projectile row this weapon fires is not resolved in the retained snapshot.')
        runtime_outputs[semantic] = row
        for alias in (entry['weapon'], entry['weapon'] + '/primary'):
            if alias in aliases:
                raise ValueError('duplicate attack output alias ' + alias)
            aliases[alias] = semantic
        if entry['projectileHost']:
            hosts[entry['weapon']] = {'kind': entry['kind'], 'class': entry.get('compatibilityClass')}
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
            'liveProof': None})
    runtime = migration_overlay.apply('attack_outputs', {'outputs': runtime_outputs, 'aliases': aliases,
        'hosts': hosts, 'crossClassReason': UNVERIFIED_REFERENCE})
    cases = research['liberatorCases']
    document = {'contract': CONTRACT, 'schemaVersion': 1,
        'hd2RuntimeVersion': (ROOT / 'VERSION').read_text().strip(), 'build': 'F5FEE03DCFDB',
        'model': dict(research['model'], proofLevels={
            'identity': 'the owner weapon, its output-family component and settings row are re-proven live',
            'assets': 'the owner package is loaded through the 0.27 asset loader before the reference is written',
            'structural': 'projectile-family outputs only: one ProjectileType reference; cross-family is blocked',
            'gameplay': 'live-proven only by a user-run test (sdk/LiveEvidenceCatalog.json); none yet'}),
        'hostModel': {'projectileHosts': sorted(hosts),
            'rule': ('A cross-class projectile output needs a magazine-fed projectile host whose every round is '
                'ProjectileWeapon +0: a WeaponMagazine with an empty magazine pattern, and no WeaponRounds, '
                'WeaponCharge or WeaponHeat component that selects projectiles by ammo type, charge or heat level. '
                'The host keeps its magazine, ammo consumption, reload, RPM and handling; only +0 changes.'),
            'retained': research['hostRetains']},
        'liberatorCases': cases,
        'summary': {'outputs': len(public), 'byFamily': research['summary']['byFamily'],
            'selectable': sum(1 for o in public if o['selectableAsProjectileReference']),
            'projectileHosts': len(hosts)},
        'outputs': public,
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
