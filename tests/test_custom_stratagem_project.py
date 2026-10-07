"""The builder-facing custom stratagem schema and project format (docs/custom-stratagem-builder.md):
  * sdk/CustomStratagemSchema.json and sdk/schemas/custom_stratagems.project.schema.json are generated from the
    Runtime's own limits and catalogues (scripts/generate_custom_stratagem_schema.py) and name no raw offset;
  * the fixtures (sdk/fixtures/custom_stratagems: the data examples) are valid under both, compile deterministically,
    and register in the Runtime exactly as the hand-written examples do (HMG Sentry, Eagle Stun Rocket Pods) or as
    their data-family equivalents (Gas EAT, Gas Barrage: the examples use callbacks);
  * the SDK validator refuses exactly what the Runtime refuses at registration, at every limit;
  * hd2.py build compiles a project's custom_stratagems.json into src/addon.lua (never over a hand-written one), ships
    the JSON and its editable PNGs beside the manifest, and writes build/build-report.json."""
import copy
import hashlib
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from support import ROOT, run, lua as lua_literal
from test_stratagem_calldown_code import WORLD

sys.path.insert(0, str(ROOT / 'sdk'))
sys.path.insert(0, str(ROOT / 'scripts'))
from tools import custom_stratagem_project as P  # noqa: E402

FIXTURES = ROOT / 'sdk/fixtures/custom_stratagems'
EXAMPLES = {'HmgSentryExample': 'hmg_sentry', 'EagleStunRocketPodsExample': 'eagle_stun_rocket_pods',
    'GasEatExample': 'eat17_gas', 'GasBarrageExample': 'orbital_gas_barrage',
    # The 2026-10-06 examples: each IS its project file (the fixture is a copy of proof/<name>/custom_stratagems.json).
    'EAT23Example': 'eat23_ems', 'EAT17GExample': 'eat17g', 'EAT17CExample': 'eat_cluster',
    'PelicanCannonExample': 'pelican_cannon_support', 'PelicanCasExplosive': 'pelican_close_air_support',
    'PelicanGasExample': 'pelican_gas_support', 'PelicanEmsExample': 'pelican_ems_support',
    'OrbitalEmsBarrageExample': 'orbital_ems_barrage', 'ShredderSiloExample': 'shredder_silo'}


def fixture(name):
    return json.loads((FIXTURES / (name + '.json')).read_text(encoding='utf-8'))


def wrapped(name, body):
    from test_event_scripting import SDK
    spec = json.loads((ROOT / 'proof' / name / 'hd2runtime.json').read_text(encoding='utf-8'))
    return spec['resource'], SDK.wrap_addon(spec['resource'], spec['requires']['hd2runtime']['min_version'], body)


def json_schema_errors(value, schema, where='$'):
    """The subset of JSON Schema 2020-12 the project schema uses (no jsonschema package is required)."""
    errors = []
    if 'const' in schema and value != schema['const']:
        errors.append(where + ': not ' + repr(schema['const']))
    if 'enum' in schema and value not in schema['enum']:
        errors.append(where + ': not one of ' + repr(schema['enum']))
    kind = schema.get('type')
    types = {'object': dict, 'array': list, 'string': str, 'integer': int, 'number': (int, float), 'boolean': bool}
    if kind and (not isinstance(value, types[kind]) or (isinstance(value, bool) and kind != 'boolean')
            or (kind == 'integer' and isinstance(value, float))):
        return errors + [where + ': not ' + kind]
    if 'oneOf' in schema:
        matches = [s for s in schema['oneOf'] if not json_schema_errors(value, s, where)]
        if len(matches) != 1:
            errors.append(where + ': matches %d of oneOf' % len(matches))
    if isinstance(value, dict):
        for key in schema.get('required', []):
            if key not in value:
                errors.append(where + ': missing ' + key)
        props = schema.get('properties', {})
        for key, v in value.items():
            if key in props:
                errors += json_schema_errors(v, props[key], where + '.' + key)
            elif schema.get('additionalProperties') is False:
                errors.append(where + ': unexpected ' + key)
    if isinstance(value, list):
        if len(value) < schema.get('minItems', 0) or len(value) > schema.get('maxItems', 10 ** 9):
            errors.append(where + ': item count')
        for i, v in enumerate(value):
            errors += json_schema_errors(v, schema.get('items', {}), '%s[%d]' % (where, i))
    if isinstance(value, str):
        if len(value) < schema.get('minLength', 0) or len(value) > schema.get('maxLength', 10 ** 9):
            errors.append(where + ': length')
        if 'pattern' in schema and not re.search(schema['pattern'], value):
            errors.append(where + ': pattern')
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if 'minimum' in schema and value < schema['minimum'] or 'maximum' in schema and value > schema['maximum']:
            errors.append(where + ': range')
        if 'exclusiveMinimum' in schema and value <= schema['exclusiveMinimum']:
            errors.append(where + ': range')
    return errors


class SchemaTests(unittest.TestCase):
    def test_the_schemas_are_current_and_name_no_raw_offset(self):
        import generate_custom_stratagem_schema
        self.assertEqual(generate_custom_stratagem_schema.generate(check=True), [])
        schema = P.load_schema()
        self.assertEqual(schema['hd2RuntimeVersion'], (ROOT / 'VERSION').read_text(encoding='utf-8').strip())
        self.assertEqual(schema['format'], P.FORMAT)
        text = json.dumps(schema)
        for raw in ('offset', '+0x', '"0x'):
            self.assertNotIn(raw, text)
        self.assertEqual([f['family'] for f in schema['families']], ['script', 'support', 'expendable', 'sentry', 'eagle',
            'orbital', 'pelican', 'silo'])
        self.assertEqual([f['family'] for f in schema['families'] if f['builder']], ['support', 'expendable', 'sentry',
            'eagle', 'orbital', 'pelican', 'silo'])
        # The catalogues a builder's dropdowns read: every one present and non-empty, donors named.
        for key in ('supportDonors', 'projectileDonors', 'sentryDonors', 'eagleDonors', 'orbitals', 'explosionDonors',
                'carrierFamilies', 'beacons', 'directions', 'stratagems', 'pelicanSounds', 'pelicanExplosionDonors',
                'nativeCodes', 'siloDonors', 'blastExplosions'):
            self.assertTrue(schema['catalogs'][key], key)
        names = {d['name'] for d in schema['catalogs']['supportDonors'] if d['deliverable']}
        self.assertIn('EAT-17 Expendable Anti-Tank', names)
        self.assertIn('B-1 Supply Pack', names)            # backpacks are deliverable support donors too
        self.assertEqual({d['name'] for d in schema['catalogs']['explosionDonors']},
            {'Orbital EMS Strike', 'Orbital Gas Strike'})
        eagles = {d['name']: d for d in schema['catalogs']['eagleDonors']}
        self.assertTrue(eagles['Eagle 110mm Rocket Pods']['impactExplosionReplaceable'])
        self.assertFalse(eagles['Eagle Cluster Bomb']['impactExplosionReplaceable'])
        self.assertIn('A/MG-43 Machine Gun Sentry', {d['name'] for d in schema['catalogs']['sentryDonors']})
        self.assertIn('MG-206 Heavy Machine Gun', {d['name'] for d in schema['catalogs']['projectileDonors']})

    def test_the_limits_are_the_runtimes_own(self):
        out = run(r'''
local C=require('hd2runtime/runtime/custom_stratagems')
local L=C.LIMITS
return table.concat({L.definitions,L.id.max,L.text,L.description,L.code[1],L.code[2],L.cooldown[2],L.rounds[2],
    L.eagle.uses[2],L.eagle.rearm_seconds[2],L.orbital.salvos[2],L.orbital.shells_per_salvo[2],L.orbital.shell_interval[2],
    L.orbital.salvo_interval[2],L.orbital.scatter[2],L.orbital.total},',')
''').decode()
        s = P.load_schema()
        F = {f['family']: f['fields'] for f in s['families'] if 'fields' in f}
        expected = [s['limits']['definitions'], s['metadata']['id']['maxLength'], s['metadata']['name']['maxLength'],
            s['metadata']['description']['maxLength'], s['metadata']['code']['min'], s['metadata']['code']['max'],
            s['metadata']['cooldown']['max'], F['support']['items']['item']['modify']['fields']['rounds']['max'],
            F['eagle']['uses']['max'], F['eagle']['rearm_seconds']['max'], F['orbital']['salvos']['max'],
            F['orbital']['shells_per_salvo']['max'], F['orbital']['shell_interval']['max'],
            F['orbital']['salvo_interval']['max'], F['orbital']['scatter']['max'], s['limits']['orbitalShells']]
        self.assertEqual(out, ','.join(str(v) for v in expected))


class FixtureTests(unittest.TestCase):
    def test_every_fixture_is_valid_and_compiles_deterministically(self):
        schema = P.load_schema()
        project_schema = json.loads((ROOT / 'sdk/schemas/custom_stratagems.project.schema.json').read_text(
            encoding='utf-8'))
        self.assertEqual(sorted(p.stem for p in FIXTURES.glob('*.json')), sorted(EXAMPLES))
        for name, sid in EXAMPLES.items():
            project = fixture(name)
            self.assertEqual(P.validate(project, schema), [], name)
            self.assertEqual(json_schema_errors(project, project_schema), [], name)
            text = P.compile_lua(project)
            self.assertEqual(text, P.compile_lua(copy.deepcopy(project)))
            self.assertTrue(text.startswith(P.GENERATED_HEADER))
            self.assertEqual(text.count('hd2.custom_stratagem.register('), 1)
            self.assertIn("icon=hd2.resources.image('%s')," % sid, text)
            # Its icon is the example's own editable PNG.
            self.assertTrue((ROOT / 'proof' / name / project['stratagems'][0]['icon']['source']).is_file())
            for forbidden in ("require('hd2runtime", 'ffi', 'on_activate', 'on_delivered', 'function'):
                self.assertNotIn(forbidden, text)
        # The JSON Schema refuses what the structure forbids.
        bad = fixture('HmgSentryExample')
        bad['stratagems'][0]['payload']['weapon']['impact_explosion'] = 'Orbital EMS Strike'
        bad['stratagems'][0]['code'] = ['up'] * 9
        bad['stratagems'][0]['icon'] = {'image': 'hmg_sentry', 'source': 'icons/hmg.png'}
        errors = json_schema_errors(bad, project_schema)
        self.assertTrue(any('code' in e for e in errors) and any('payload' in e for e in errors)
            and any('icon.source' in e for e in errors), errors)

    def test_compiled_fixtures_register_as_the_examples_do(self):
        loads = []
        for name in EXAMPLES:
            example = (ROOT / 'proof' / name / 'src/addon.lua').read_text(encoding='utf-8')
            resource, a = wrapped(name, example)
            _, b = wrapped(name, P.compile_lua(fixture(name)))
            loads.append('{id=%s,resource=%s,example=%s,compiled=%s}' % (lua_literal(EXAMPLES[name]),
                lua_literal(resource), lua_literal(a), lua_literal(b)))
        self.assertEqual(run(WORLD + 'local LOADS={' + ','.join(loads) + '}\n' + r'''
local custom=require('hd2runtime/runtime/custom_stratagems')
-- A definition as data: every field but callbacks, sorted.
local function dump(v,seen)
    seen=seen or{}
    local t=type(v)
    if t=='function'then return'fn'end
    if t~='table'then return tostring(v)end
    if seen[v]then return'<cycle>'end
    seen[v]=true
    local keys={}
    for k,x in pairs(v)do if type(x)~='function'then keys[#keys+1]=k end end
    table.sort(keys,function(p,q)return tostring(p)<tostring(q)end)
    local out={}
    for _,k in ipairs(keys)do out[#out+1]=tostring(k)..'='..dump(v[k],seen)end
    seen[v]=nil
    return '{'..table.concat(out,',')..'}'
end
local function load(text,resource)
    custom.reset_for_tests()
    require('hd2runtime/runtime/virtual_stratagems').reset_for_tests()
    rawset(_G,'HD2RuntimeMod:'..resource,nil)     -- the wrapper runs a mod once per session
    assert(loadstring(text,'@'..resource))()
    return custom.get
end
local defs={}
for _,l in ipairs(LOADS)do
    local example=load(l.example,l.resource)(l.id)
    local e=dump(example)
    local compiled=load(l.compiled,l.resource)(l.id)
    defs[l.id]={example=example,compiled=compiled,e=e,c=dump(compiled)}
end
-- The data examples: exactly the same definition (GasEatExample 0.1.7 and GasBarrageExample 0.1.7 declare their payload
-- as data: the definition every compatible Runtime derives the mirrored payload from).
for _,id in ipairs({'hmg_sentry','eagle_stun_rocket_pods','eat17_gas','orbital_gas_barrage'})do
    assert(defs[id].e==defs[id].c,id..'\n'..defs[id].e..'\n'..defs[id].c)
end
local eat=defs.eat17_gas
assert(eat.example.kind=='support'and eat.compiled.kind=='support'
    and eat.compiled.delivery.stratagem==eat.example.delivery.stratagem and eat.compiled.delivery.count==2
    and eat.compiled.delivery.impact=='Orbital Gas Strike'and eat.example.delivery.impact=='Orbital Gas Strike')
local gas=defs.orbital_gas_barrage
assert(gas.example.kind=='orbital'and gas.compiled.orbital.native==true
    and gas.compiled.orbital.pattern=='Orbital 120mm HE Barrage'and gas.compiled.orbital.impact=='Orbital Gas Strike'
    and table.concat(gas.compiled.orbital.shells,',')=='194,137'and gas.compiled.delivery.stratagem=='Orbital 120mm HE Barrage')
return 'ok'
'''), b'ok')


# One value at a time, at and past every limit: (label, mutation, valid?). The Runtime's registration decides too.
def _set(path, value):
    def apply(project):
        node = project['stratagems'][0]
        keys = path.split('.')
        for k in keys[:-1]:
            node = node[int(k)] if k.isdigit() else node[k]
        if value is None:
            node.pop(keys[-1], None)
        else:
            node[keys[-1]] = value
    return apply


def _runtime(mutate):
    """The Gas Barrage fixture (native) as the Runtime bombardment form (shell + pattern), then `mutate`."""
    def apply(project):
        node = project['stratagems'][0]
        node['payload'] = {'family': 'orbital', 'shell': 'Orbital Gas Strike', 'pattern': 'Orbital 120mm HE Barrage'}
        mutate(project)
    return apply


CASES = [
    ('HmgSentryExample', 'cooldown 600', _set('cooldown', 600), True),
    ('ShredderSiloExample', 'max_per_player 1', _set('max_per_player', 1), True),
    ('ShredderSiloExample', 'max_per_player 4', _set('max_per_player', 4), True),
    ('ShredderSiloExample', 'max_per_player 5', _set('max_per_player', 5), False),
    ('ShredderSiloExample', 'max_per_player 0', _set('max_per_player', 0), False),
    ('ShredderSiloExample', 'max_per_player 1.5', _set('max_per_player', 1.5), False),
    ('HmgSentryExample', 'cooldown 600.5', _set('cooldown', 600.5), False),
    ('HmgSentryExample', 'cooldown 0', _set('cooldown', 0), False),
    ('HmgSentryExample', 'rpm 3000', _set('payload.weapon.rpm', 3000), True),
    ('HmgSentryExample', 'rpm 3001', _set('payload.weapon.rpm', 3001), False),
    ('HmgSentryExample', 'rpm 30', _set('payload.weapon.rpm', 30), True),
    ('HmgSentryExample', 'rpm 29', _set('payload.weapon.rpm', 29), False),
    ('HmgSentryExample', 'spread 100', _set('payload.weapon.spread', 100), True),
    ('HmgSentryExample', 'spread 0', _set('payload.weapon.spread', 0), False),
    ('HmgSentryExample', 'ammo 2047', _set('payload.weapon.ammo', 2047), True),
    ('HmgSentryExample', 'ammo 2048', _set('payload.weapon.ammo', 2048), False),
    ('HmgSentryExample', 'recoil zero', _set('payload.weapon.recoil', 'zero'), True),
    ('HmgSentryExample', 'projectile no round', _set('payload.weapon.projectile', 'B-1 Supply Pack'), False),
    ('HmgSentryExample', 'sentry impact', _set('payload.weapon.impact_explosion', 'Orbital EMS Strike'), False),
    ('HmgSentryExample', 'sentry not a sentry', _set('payload.donor', 'MG-43 Machine Gun'), False),
    ('HmgSentryExample', 'sentry any family', _set('carrier', {'beacon': 'support'}), False),
    ('HmgSentryExample', 'code 8', _set('code', ['up', 'down'] * 4), True),
    ('HmgSentryExample', 'code 9', _set('code', ['up'] * 9), False),
    ('HmgSentryExample', 'id 48', _set('id', 'h' * 48), True),
    ('HmgSentryExample', 'id 49', _set('id', 'h' * 49), False),
    ('HmgSentryExample', 'id upper', _set('id', 'Hmg'), False),
    ('HmgSentryExample', 'name 64', _set('name', 'N' * 64), True),
    ('HmgSentryExample', 'name 65', _set('name', 'N' * 65), False),
    ('HmgSentryExample', 'description 400', _set('description', 'd' * 400), True),
    ('HmgSentryExample', 'description 401', _set('description', 'd' * 401), False),
    ('HmgSentryExample', 'asset unknown', _set('assets', ['No Such Stratagem']), False),
    ('EagleStunRocketPodsExample', 'uses 20', _set('payload.uses', 20), True),
    ('EagleStunRocketPodsExample', 'uses 21', _set('payload.uses', 21), False),
    ('EagleStunRocketPodsExample', 'uses 0', _set('payload.uses', 0), False),
    ('EagleStunRocketPodsExample', 'rearm 600', _set('payload.rearm_seconds', 600), True),
    ('EagleStunRocketPodsExample', 'rearm 601', _set('payload.rearm_seconds', 601), False),
    ('EagleStunRocketPodsExample', 'eagle cooldown', _set('cooldown', 30), False),
    ('EagleStunRocketPodsExample', 'cluster impact', _set('payload.donor', 'Eagle Cluster Bomb'), False),
    ('EagleStunRocketPodsExample', '500kg plain', lambda p: (_set('payload.donor', 'Eagle 500kg Bomb')(p),
        _set('payload.payload', None)(p)), True),
    ('EagleStunRocketPodsExample', 'eagle blue', _set('carrier.beacon', 'support'), False),
    ('EagleStunRocketPodsExample', 'impact unknown', _set('payload.payload.impact_explosion', 'Big Boom'), False),
    ('GasEatExample', 'count 2', _set('payload.items.0.count', 2), True),
    ('GasEatExample', 'count 1', _set('payload.items.0.count', 1), False),
    ('GasEatExample', 'rounds 64', _set('payload.items.0.modify.rounds', 64), True),
    ('GasEatExample', 'rounds 65', _set('payload.items.0.modify.rounds', 65), False),
    ('GasEatExample', 'backpack modify', lambda p: _set('payload.items', [{'donor': 'B-1 Supply Pack',
        'modify': {'rpm': 600}}])(p), False),
    ('GasEatExample', 'backpack plain', _set('payload.items', [{'donor': 'B-1 Supply Pack'}]), True),
    ('GasEatExample', 'support red', _set('carrier.beacon', 'offensive'), False),
    ('GasEatExample', 'not support', _set('payload.items', [{'donor': 'Orbital Gas Strike'}]), False),
    ('GasBarrageExample', 'native', lambda p: None, True),
    ('GasBarrageExample', 'native without impact', _set('payload.impact_explosion', None), False),
    ('GasBarrageExample', 'native with salvos', _set('payload.salvos', 3), False),
    ('GasBarrageExample', 'native with a shell', _set('payload.shell', 'Orbital Gas Strike'), False),
    ('GasBarrageExample', 'native not a bombardment', _set('payload.pattern', 'Eagle Airstrike'), False),
    ('GasBarrageExample', 'native false', _set('payload.native', False), False),
    ('GasBarrageExample', 'native EMS', _set('payload.impact_explosion', 'Orbital EMS Strike'), True),
    ('GasBarrageExample', 'runtime salvos 16x4', _runtime(lambda p: (_set('payload.salvos', 16)(p),
        _set('payload.shells_per_salvo', 4)(p))), True),
    ('GasBarrageExample', 'runtime salvos 16x5', _runtime(lambda p: (_set('payload.salvos', 16)(p),
        _set('payload.shells_per_salvo', 5)(p))), False),
    ('GasBarrageExample', 'runtime salvos 17', _runtime(_set('payload.salvos', 17)), False),
    ('GasBarrageExample', 'runtime salvos 2.5', _runtime(_set('payload.salvos', 2.5)), False),
    ('GasBarrageExample', 'runtime scatter 100', _runtime(_set('payload.scatter', 100)), True),
    ('GasBarrageExample', 'runtime scatter 100.5', _runtime(_set('payload.scatter', 100.5)), False),
    ('GasBarrageExample', 'runtime shell interval 10', _runtime(_set('payload.shell_interval', 10)), True),
    ('GasBarrageExample', 'runtime shell interval 11', _runtime(_set('payload.shell_interval', 11)), False),
    ('GasBarrageExample', 'runtime salvo interval 30', _runtime(_set('payload.salvo_interval', 30)), True),
    ('GasBarrageExample', 'runtime salvo interval 31', _runtime(_set('payload.salvo_interval', 31)), False),
    ('GasBarrageExample', 'runtime impact EMS', _runtime(_set('payload.impact_explosion', 'Orbital EMS Strike')), True),
    ('GasBarrageExample', 'runtime shell not orbital', _runtime(_set('payload.shell', 'Eagle Airstrike')), False),
    ('GasBarrageExample', 'runtime any beacon', _runtime(_set('carrier.beacon', 'any')), True),
]


class ValidatorTests(unittest.TestCase):
    def test_a_weapon_variant_project_registers_as_the_laser_maxigun_does(self):
        # r44: the weapon variant family (delivery.family = 'weapon') in a project: what LaserMaxigunExample registers
        # by hand (its model_use there is a Mod Options choice; here the fixed value 'check').
        schema = P.load_schema()
        project = {'format': P.FORMAT, 'stratagems': [{
            'id': 'laser_maxigun', 'name': 'LAS-1000 LASER MAXIGUN', 'name_cased': 'LAS-1000 Laser Maxigun',
            'description': 'A Maxigun refitted to fire the LAS-58 Talon\'s laser bolts.',
            'icon': {'image': 'laser_maxigun', 'source': 'images/laser_maxigun.png'},
            'code': ['down', 'up', 'up', 'down', 'down', 'left'], 'carrier': {'group': 'weapon'},
            'payload': {'family': 'weapon', 'weapon': 'M-1000 Maxigun', 'round': 'output/v1/projectile/las-58-talon',
                'model': 'laser_maxigun', 'model_use': 'check'}}]}
        self.assertEqual(P.validate(project, schema), [])
        project_schema = json.loads((ROOT / 'sdk/schemas/custom_stratagems.project.schema.json').read_text(
            encoding='utf-8'))
        self.assertEqual(json_schema_errors(project, project_schema), [])
        text = P.compile_lua(project)
        self.assertIn("delivery={family='weapon',weapon='M-1000 Maxigun',"
            "round=hd2.attack_output('output/v1/projectile/las-58-talon'),model='laser_maxigun',model_use='check'}", text)
        # What the validator refuses: another class's round, an unknown host, model_use without a model.
        bad = copy.deepcopy(project)
        bad['stratagems'][0]['payload'].update(weapon='MG-43 Machine Gun', round='output/v1/projectile/nope')
        del bad['stratagems'][0]['payload']['model']
        problems = P.validate(bad, schema)
        self.assertTrue(any('.weapon: must be a reviewed variant weapon' in x for x in problems)
            and any('.model_use: needs model' in x for x in problems), problems)
        bad = copy.deepcopy(project)
        bad['stratagems'][0]['payload']['round'] = 'output/v1/projectile/nope'
        self.assertTrue(any('.round: must be a round of the M-1000 Maxigun' in x for x in P.validate(bad, schema)))
        bad = copy.deepcopy(project)
        bad['stratagems'][0]['carrier'] = {'group': 'expendable'}
        self.assertTrue(any('carrier.group' in x for x in P.validate(bad, schema)))
        # The compiled project registers the same variant as the hand-written example.
        example = (ROOT / 'proof/LaserMaxigunExample/src/addon.lua').read_text(encoding='utf-8')
        resource, a = wrapped('LaserMaxigunExample', example)
        _, b = wrapped('LaserMaxigunExample', text)
        self.assertEqual(run(WORLD + 'local A=' + lua_literal(a) + '\nlocal B=' + lua_literal(b) + '\nlocal R='
            + lua_literal(resource) + r"""
local custom=require('hd2runtime/runtime/custom_stratagems')
local function load(text)
    custom.reset_for_tests()
    require('hd2runtime/runtime/virtual_stratagems').reset_for_tests()
    require('hd2runtime/runtime/text_resources').reset_for_tests()
    rawset(_G,'HD2RuntimeMod:'..R,nil)
    assert(loadstring(text,'@'..R))()
    return custom.get('laser_maxigun')
end
local e,c=load(A),load(B)
for _,d in ipairs({e,c})do
    assert(d.kind=='expendable'and d.delivery.variant==true and d.delivery.stratagem=='M-1000 Maxigun')
    assert(d.delivery.round and d.delivery.round.output=='output/v1/projectile/las-58-talon')
    assert(d.delivery.model~=nil and d.selection=='carrier')
end
assert(c.delivery.model_use=='check')
return 'ok'
"""), b'ok')

    def test_the_schema_describes_the_r44_additions(self):
        schema = P.load_schema()
        self.assertEqual(schema['schemaVersion'], 1)
        self.assertEqual(schema['variantFamily']['family'], 'weapon')
        self.assertEqual(schema['catalogs']['variantDonors'][0]['name'], 'M-1000 Maxigun')
        # Every payload family a project may use has its live-test record (a builder's badges).
        families = {f['family'] for f in schema['families']} | {schema['podFamily']['family'],
            schema['variantFamily']['family']}
        self.assertEqual(families, set(schema['familyEvidence']))
        for f in schema['familyEvidence'].values():
            self.assertIn(f['status'], ('live', 'partial', 'offline'))
        # The slot holds the carrier itself: no project field (the Runtime's own default and fallback).
        self.assertIsNone(schema['selection']['field'])
        self.assertNotIn('selection', json.dumps(schema['metadata']))

    def test_the_validator_refuses_exactly_what_the_runtime_refuses(self):
        schema = P.load_schema()
        verdicts, chunks = [], []
        for name, label, mutate, valid in CASES:
            project = fixture(name)
            mutate(project)
            problems = P.validate(project, schema)
            self.assertEqual(problems == [], valid, '%s %s: %s' % (name, label, problems))
            verdicts.append(valid)
            resource, text = wrapped(name, P.compile_lua(project))
            chunks.append('{label=%s,resource=%s,text=%s}' % (lua_literal(name + ' ' + label), lua_literal(resource),
                lua_literal(text)))
        out = run(WORLD + 'local CASES={' + ','.join(chunks) + '}\n' + r'''
local custom=require('hd2runtime/runtime/custom_stratagems')
local out={}
for _,c in ipairs(CASES)do
    custom.reset_for_tests()
    require('hd2runtime/runtime/virtual_stratagems').reset_for_tests()
    require('hd2runtime/runtime/text_resources').reset_for_tests()
    rawset(_G,'HD2RuntimeMod:'..c.resource,nil)
    local ok,why=pcall(function()assert(loadstring(c.text,'@'..c.resource))()end)
    out[#out+1]=(ok and'1'or'0')..(ok and''or(' '..c.label..': '..tostring(why)))
end
return table.concat(out,'\n')
''').decode().split('\n')
        self.assertEqual(len(out), len(CASES))
        for (name, label, _, valid), line in zip(CASES, out):
            self.assertEqual(line[0] == '1', valid, '%s %s: the Runtime %s (%s)' % (name, label,
                'accepted' if line[0] == '1' else 'refused', line))


class BuildTests(unittest.TestCase):
    def test_build_compiles_the_project_and_reports_it(self):
        from test_event_scripting import SDK
        source = ROOT / 'proof/HmgSentryExample'
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / 'HmgSentryJson'
            shutil.copytree(source, project, ignore=shutil.ignore_patterns('build', 'src'))
            (project / 'hd2runtime.json').write_text(json.dumps(dict(json.loads((source / 'hd2runtime.json')
                .read_text(encoding='utf-8')), sdk=str(ROOT / 'sdk'))), encoding='utf-8')
            (project / P.PROJECT_FILE).write_bytes((FIXTURES / 'HmgSentryExample.json').read_bytes())
            # A missing icon PNG is refused before anything is written.
            png = (project / 'images/hmg_sentry.png').read_bytes()
            (project / 'images/hmg_sentry.png').unlink()
            with self.assertRaisesRegex(ValueError, 'images/hmg_sentry.png is missing'):
                SDK.build_project(project)
            self.assertFalse((project / 'src').exists())
            (project / 'images/hmg_sentry.png').write_bytes(png)
            path = SDK.build_project(project)
            addon = (project / 'src/addon.lua').read_text(encoding='utf-8')
            self.assertEqual(addon, P.compile_lua(fixture('HmgSentryExample'),
                hashlib.sha256((FIXTURES / 'HmgSentryExample.json').read_bytes()).hexdigest()))
            import zipfile
            with zipfile.ZipFile(path) as z:
                names = set(z.namelist())
                report = json.loads(z.read('build-report.json'))
                self.assertEqual(z.read(P.PROJECT_FILE), (FIXTURES / 'HmgSentryExample.json').read_bytes())
            self.assertIn('images/hmg_sentry.png', names)
            self.assertEqual(report['custom_stratagems']['ids'], ['hmg_sentry'])
            self.assertEqual(report['custom_stratagems']['images'], ['hmg_sentry'])
            beside = json.loads((project / 'build/build-report.json').read_text(encoding='utf-8'))
            self.assertEqual(beside['artifact'], path.name)
            self.assertEqual(beside['artifact_sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(beside['image_sources']['hmg_sentry']['file'], 'images/hmg_sentry.png')
            # Rebuilding the same project writes nothing new and gives the same artifact.
            again = SDK.build_project(project)
            self.assertEqual(again.read_bytes(), path.read_bytes())
            # A hand-written addon is never overwritten.
            (project / 'src/addon.lua').write_text("local hd2=require('mods/skyeshade/hd2runtime')\n", encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'hand-written'):
                SDK.build_project(project)
            # The CLI's validate names every problem.
            bad = fixture('HmgSentryExample')
            bad['stratagems'][0]['payload']['weapon']['rpm'] = 5000
            (project / P.PROJECT_FILE).write_text(json.dumps(bad), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, r'payload\.weapon\.rpm: must be at most 3000'):
                SDK.custom_stratagem_command('validate', project)
            self.assertIn('is valid', SDK.custom_stratagem_command('validate', FIXTURES / 'GasEatExample.json'))


if __name__ == '__main__':
    unittest.main()
