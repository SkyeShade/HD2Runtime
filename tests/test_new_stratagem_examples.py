"""The ten custom stratagem examples of 2026-10-06 (the user's specification: names, descriptions, codes in arrows, item
traits, the Pelicans' uses and cooldowns; the codes the user chose where the requested ones collided):
  * each is a custom_stratagems.json project (the format a builder such as ModBuilder writes): valid, its src/addon.lua
    exactly the compiled project, its fixture (sdk/fixtures/custom_stratagems) the project itself, its icon the game's
    red and green masks;
  * every code is free of every native code (catalogued or not) and of the other nine;
  * all ten register TOGETHER through the public API, each in its payload family, with its traits, uses and cooldown;
    the panel's details show them;
  * every one runs on a client with several players (a client family) and the payloads that need it are mirrored on
    every compatible Runtime (a remote handler); the registry hash covers the sentry's weapon."""
import hashlib
import json
import sys
import unittest

from support import ROOT, run
from test_stratagem_calldown_code import WORLD

sys.path.insert(0, str(ROOT / 'sdk'))
from tools import custom_stratagem_project as P  # noqa: E402
from tools import hd2_image  # noqa: E402

ARROWS = {'↑': 'up', '↓': 'down', '←': 'left', '→': 'right'}
# folder: (stratagem id, name, code, cooldown, uses, traits after CUSTOM STRATAGEM, family)
SPEC = {
    'HmgSentryExample': ('hmg_sentry', 'A/MG-101 Heavy MG Sentry', '↓↑→→→←', 150, None,
        ['SENTRY', 'HEAVY ARMOR PENETRATING'], 'sentry'),
    'EAT23Example': ('eat23_ems', 'EAT-23 Expendable EMS', '↓↓←→→', 70, None,
        ['SUPPORT WEAPON', 'ANTI-TANK', 'STUN', 'EXPENDABLE'], 'expendable'),
    'EAT17GExample': ('eat17g_clone', 'EAT-40 Expendable Gas', '↓↓←↓→', 70, None,
        ['SUPPORT WEAPON', 'ANTI-TANK', 'CAUSTIC', 'EXPENDABLE'], 'expendable'),
    'EAT17CExample': ('eat_cluster', 'EAT-77 Expendable Cluster', '↓↓←↓←', 70, None,
        ['SUPPORT WEAPON', 'MEDIUM ARMOR PENETRATING', 'ANTI-TANK', 'EXPENDABLE'], 'expendable'),
    'PelicanCannonExample': ('pelican_cannon_support', 'Pelican Cannon Support', '←↓←↑←↑', 300, 3,
        ['PELICAN', 'ANTI-TANK', 'EXPLOSIVE'], 'pelican'),
    'PelicanCasExplosive': ('pelican_close_air_support', 'Pelican Gatling Support', '←↓←←↑↑', 300, 4,
        ['PELICAN', 'HEAVY ARMOR PENETRATING'], 'pelican'),
    'PelicanGasExample': ('pelican_gas_support', 'Pelican Gas Support', '←↓←→↓→', 300, 4,
        ['PELICAN', 'CAUSTIC'], 'pelican'),
    'PelicanEmsExample': ('pelican_ems_support', 'Pelican EMS Support', '←↓←→←↓', 300, 4,
        ['PELICAN', 'STUN'], 'pelican'),
    'OrbitalEmsBarrageExample': ('orbital_ems_barrage', 'Orbital EMS Barrage', '→↓↑→←↓', 60, None,
        ['ORBITAL', 'ANTI-TANK', 'STUN'], 'orbital'),
    'GasBarrageExample': ('orbital_gas_barrage', 'Orbital Gas Barrage', '→→↓←↓←', 60, None,
        ['ORBITAL', 'ANTI-TANK', 'CAUSTIC'], 'orbital'),
}


def project(name):
    return json.loads((ROOT / 'proof' / name / 'custom_stratagems.json').read_text(encoding='utf-8'))


def addons():
    from test_event_scripting import SDK
    from support import lua
    out = []
    for name in SPEC:
        spec = json.loads((ROOT / 'proof' / name / 'hd2runtime.json').read_text(encoding='utf-8'))
        body = (ROOT / 'proof' / name / 'src/addon.lua').read_text(encoding='utf-8')
        out.append('{resource=%s,body=%s}' % (lua(spec['resource']), lua(SDK.wrap_addon(spec['resource'],
            spec['requires']['hd2runtime']['min_version'], body))))
    return '{' + ','.join(out) + '}'


class ProjectTests(unittest.TestCase):
    def test_each_example_is_its_compiled_project(self):
        schema = P.load_schema()
        for name, (sid, cased, code, cooldown, uses, traits, family) in SPEC.items():
            folder = ROOT / 'proof' / name
            raw = (folder / 'custom_stratagems.json').read_bytes()
            proj = json.loads(raw)
            self.assertEqual(P.validate(proj, schema), [], name)
            self.assertEqual((folder / 'src/addon.lua').read_text(encoding='utf-8'),
                P.compile_lua(proj, hashlib.sha256(raw).hexdigest()), name + ': rebuild it (hd2.py build)')
            self.assertEqual(json.loads((ROOT / 'sdk/fixtures/custom_stratagems' / (name + '.json')).read_text(
                encoding='utf-8')), proj, name + ': its fixture is the project file')
            s, = proj['stratagems']
            self.assertEqual((s['id'], s['name_cased'], s['code'], s['cooldown'], s.get('uses'), s['payload']['family']),
                (sid, cased, [ARROWS[c] for c in code], cooldown, uses, family), name)
            self.assertEqual([t.upper() for t in s['traits']], traits, name)
            self.assertEqual(s['name'], cased.upper())
            meta = json.loads((folder / 'hd2runtime.json').read_text(encoding='utf-8'))
            self.assertNotIn('optional', meta, name + ': no Mod Options')
            self.assertEqual(meta['requires']['hd2runtime']['min_version'], '0.30.0-dev')
            png = (folder / 'images' / (s['icon']['image'] + '.png')).read_bytes()
            self.assertEqual(hd2_image.prepare_icon(png)[1], 'masks (as given)', name + ': the red and green masks')
            readme = (folder / 'README.md').read_text(encoding='utf-8')
            self.assertIn(code, readme)
            self.assertIn(s['description'], readme)

    def test_every_code_is_free(self):
        schema = P.load_schema()
        natives = schema['catalogs']['nativeCodes']
        codes = {name: [ARROWS[c] for c in spec[2]] for name, spec in SPEC.items()}
        for name, code in codes.items():
            for native in natives:
                self.assertIsNone(P._relation(code, native['code']), '%s and %s' % (name, native.get('name')
                    or native['stableId']))
            for other, c in codes.items():
                if other != name:
                    self.assertIsNone(P._relation(code, c), '%s and %s' % (name, other))
        # The two the user asked for that collide (2026-10-06): refused by the builder, naming the stratagem.
        bad = project('EAT17CExample')
        bad['stratagems'][0]['code'] = ['down', 'down', 'left', 'up', 'left']
        self.assertTrue(any('EAT-700 Expendable Napalm' in p and 'equals' in p for p in P.validate(bad, schema)))
        bad['stratagems'][0]['code'] = ['down', 'down', 'left', 'right', 'left']
        self.assertTrue(any('FX-12 Shield Generator Relay' in p and 'start of' in p for p in P.validate(bad, schema)))


class RegistrationTests(unittest.TestCase):
    def test_all_ten_register_together_with_their_traits_uses_and_families(self):
        body = WORLD + 'local ADDONS=' + addons() + r'''
local custom=require('hd2runtime/runtime/custom_stratagems');custom.reset_for_tests()
require('hd2runtime/runtime/spawned_instances').reset_for_tests()
for _,a in ipairs(ADDONS)do assert(loadstring(a.body,'@'..a.resource))()end
local hd2=require('mods/skyeshade/hd2runtime')
local mp=require('hd2runtime/runtime/multiplayer')
local SPEC=''' + spec_lua() + r'''
local n=0
for id,s in pairs(SPEC)do
    local d=custom.get(id)
    assert(d,'not registered: '..id)
    n=n+1
    assert(d.label==s.cased and d.cooldown==s.cooldown and d.uses==s.uses,id)
    local traits={'CUSTOM STRATAGEM'}
    for _,t in ipairs(s.traits)do traits[#traits+1]=t end
    assert(table.concat(d.traits,'|')==table.concat(traits,'|'),id..': '..table.concat(d.traits,'|'))
    -- With several players: a client runs its own call; a payload that needs it is mirrored on every compatible Runtime.
    assert(mp.client_family(d),id..' is host-only')
    if s.mirrored then assert(custom.remote_handler(d),id..' is not mirrored')end
    -- The panel's details: the code's directions for the arrows, the uses, every trait (up to five rows).
    local p=custom.panel_details(id)
    assert(p.stats[4][1]=='CALL-IN CODE'and table.concat(p.stats[4].code,' ')==table.concat(s.code,' '),id)
    assert(p.stats[2][2]==(s.uses and(s.uses..' PER MISSION')or'UNLIMITED'),id..': '..tostring(p.stats[2][2]))
    assert(p.stats[3][2]==s.cooldown..' SEC',id)
    assert(table.concat(p.traits,'|')==table.concat(traits,'|'),id)
end
assert(n==10)
-- The families' payloads.
local s=custom.get('hmg_sentry')
assert(s.kind=='sentry'and s.sentry.weapon.projectile==275 and s.sentry.weapon.rpm==400)
local cannon=custom.get('pelican_cannon_support')
assert(cannon.kind=='pelican'and cannon.pelican.gun.round=='native'and cannon.pelican.gun.behave_as==nil
    and cannon.pelican.hover==90)
local gatling=custom.get('pelican_close_air_support')
assert(gatling.pelican.gun.behave_as=='gatling_sentry'and gatling.pelican.gun.round=='ap4'and gatling.pelican.gun.aim_height==0.7)
assert(custom.get('pelican_gas_support').pelican.gun.impact_explosion=='Gas grenade cloud')
assert(custom.get('pelican_ems_support').pelican.gun.impact_explosion=='EMS mortar field')
assert(custom.get('eat23_ems').delivery.impact=='Orbital EMS Strike'and custom.get('eat17g_clone').delivery.impact
    =='Orbital Gas Strike')
assert(custom.get('eat_cluster').delivery.round.name=='RL-77 Airburst Rocket Launcher')
local ems=custom.get('orbital_ems_barrage')
assert(ems.orbital.native and ems.orbital.pattern=='Orbital 120mm HE Barrage'and ems.orbital.impact=='Orbital EMS Strike')
-- The registry hash covers the sentry's weapon (every machine mirrors it): another weapon is another hash.
local function hash_with(spread)
    custom.reset_for_tests()
    require('hd2runtime/runtime/virtual_stratagems').reset_for_tests()
    require('hd2runtime/runtime/text_resources').reset_for_tests()
    custom.register({id='h_sentry',name='H',description='d',icon='x',code={'up','up','up','up','up','up','up','up'},
        carrier={beacon='support',prefer_families={'sentry'},allow_families={'sentry'}},
        sentry={donor='A/MG-43 Machine Gun Sentry',weapon={projectile=hd2.support_weapon('MG-206 Heavy Machine Gun'),
            rpm=400,spread=spread,ammo=300}}},'mods/test/h')
    return custom.registry_hash()
end
assert(hash_with(5)~=hash_with(6),'the sentry weapon is part of the registry hash')
assert(hash_with(5)==hash_with(5))
return 'ok'
'''
        self.assertEqual(run(body), b'ok')

    def test_uses_and_traits_are_checked_at_registration(self):
        self.assertEqual(run(WORLD + r'''
local custom=require('hd2runtime/runtime/custom_stratagems');custom.reset_for_tests()
local function spec(over)
    local s={id='t_orbital',name='T',description='d',icon='x',code={'up','up','right','left','down','up','right'},
        carrier={beacon='offensive',prefer_families={'orbital'}},
        orbital={native=true,pattern='Orbital 120mm HE Barrage',impact_explosion='Orbital EMS Strike'}}
    for k,v in pairs(over)do s[k]=v end
    return s
end
local function refused(over,text)
    local ok,why=pcall(custom.register,spec(over),'mods/test/t')
    assert(not ok and tostring(why):find(text,1,true),tostring(why))
end
refused({uses=0},'uses must be a whole number of calls per mission from 1 to 100')
refused({uses=2.5},'uses must be a whole number')
refused({uses=101},'from 1 to 100')
refused({traits={'A','B','C','D','E'}},'traits: at most 4 after CUSTOM STRATAGEM')
refused({traits={''}},'traits[1] must be 1 to 32 printable characters')
refused({traits={string.rep('x',33)}},'traits[1] must be 1 to 32')
refused({traits='Orbital'},'traits must be a list')
local d=custom.register(spec({uses=5,traits={'Orbital','custom stratagem','Stun','Orbital'}}),'mods/test/t')
assert(d.uses==5 and table.concat(d.traits,'|')=='CUSTOM STRATAGEM|ORBITAL|STUN','case-insensitive repeats dropped')
return 'ok'
'''), b'ok')


def spec_lua():
    from support import lua
    parts = []
    for name, (sid, cased, code, cooldown, uses, traits, family) in SPEC.items():
        mirrored = family in ('sentry', 'pelican', 'orbital') or sid in ('eat23_ems', 'eat17g_clone')
        parts.append('[%s]={cased=%s,code={%s},cooldown=%d,uses=%s,traits={%s},mirrored=%s}' % (lua(sid), lua(cased),
            ','.join(lua(ARROWS[c]) for c in code), cooldown, 'nil' if uses is None else uses,
            ','.join(lua(t) for t in traits), 'true' if mirrored else 'false'))
    return '{' + ','.join(parts) + '}'


if __name__ == '__main__':
    unittest.main()
