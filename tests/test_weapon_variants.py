"""Weapon VARIANTS and Runtime-owned custom MODELS (scripts/research_weapon_variants.py,
research/weapon-variants-F5FEE03DCFDB.json, domains/weapon_variants.lua, runtime/weapon_clone.lua variant_body,
runtime/model_resources.lua, scripts/hd2_model.py, runtime/custom_stratagems.lua delivery.family 'weapon';
docs/custom-models.md, research/docs/weapon-variants-F5FEE03DCFDB.md):
  * the research: the Maxigun alone in its component class, its four records exclusively owned, every UnitPath consumer
    site reviewed; the generated domain and sdk/ModelBaseCapabilities.json are current;
  * registration: a weapon delivery on a reviewed variant host; its round a catalogued output of the host's own
    compatibility class (never another class, never an unverified donor); its model the mod's own; refusals with reasons;
  * no fallback (the user's rule of 2026-10-06): a native Maxigun pick makes the variant UNAVAILABLE; the selected variant
    blocks the Maxigun in the native picker;
  * the model guard: no build record, another base, another build, another base unit, a name mismatch, a resource not
    loaded: never ready;
  * the SDK derivation on synthetic bytes: exactly the material slot and the LUT reference renamed, the palette in the
    LUT's base colour column, the mips rebuilt, a base part that differs from the reviewed one refused;
  * the variant on every retained snapshot (scripts/validate_weapon_variant_snapshot.py) when present."""
import hashlib
import importlib.util
import json
import struct
import unittest

from support import ROOT, run

import build_profile

RESEARCH = json.loads((ROOT / 'research/weapon-variants-F5FEE03DCFDB.json').read_text(encoding='utf-8'))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HARNESS = r"""
local images=require('hd2runtime/runtime/image_resources');images.reset_for_tests()
local texts=require('hd2runtime/runtime/text_resources');texts.reset_for_tests()
require('hd2runtime/runtime/virtual_stratagems').reset_for_tests()
local custom=require('hd2runtime/runtime/custom_stratagems');custom.reset_for_tests()
local clone=require('hd2runtime/runtime/weapon_clone');clone.reset_for_tests()
local models=require('hd2runtime/runtime/model_resources');models.reset_for_tests()
local catalog=require('hd2runtime/domains/stratagem_authoring')
local log_module=require('hd2runtime/runtime/log')
local lines={}
log_module.emit=function(text)lines[#lines+1]=tostring(text)end
local function said(text)local o={};for _,l in ipairs(lines)do if l:find(text,1,true)then o[#o+1]=l end end
    return table.concat(o,' | ')end
local MAXI='M-1000 Maxigun'
local MAXI_ID=catalog.stratagems[MAXI].root.id
local OWNER='mods/test/laser'
local function out(name)return {resource='attack_output',output=name}end
local function laser(over)
    local s={id='laser_maxigun',name='LAS-1000 LASER MAXIGUN',name_cased='LAS-1000 Laser Maxigun',description='d',
        icon='laser',code={'down','up','up','down','down','left'},carrier={group='weapon'},
        delivery={family='weapon',weapon={resource='support_weapon',weapon=MAXI},
            round=out('output/v1/projectile/las-58-talon'),model='laser_maxigun',model_use='check'}}
    for k,v in pairs(over or{})do if v==false then s[k]=nil else s[k]=v end end
    return s
end
local function refused(spec,text)
    local ok,why=pcall(custom.register,spec,OWNER)
    assert(not ok,'accepted: '..tostring(text))
    assert(tostring(why):find(text,1,true),tostring(why))
end
"""


class WeaponVariantResearchTests(unittest.TestCase):
    def test_the_research(self):
        self.assertEqual((RESEARCH['writes'], RESEARCH['protectionChanges']), (0, 0))
        h = RESEARCH['hosts']['M-1000 Maxigun']
        self.assertEqual(h['componentClass'], ['content/fac_helldivers/equipment/support_weapons/minigun/minigun'])
        self.assertEqual(h['pool'], ['M-1000 Maxigun'])
        self.assertEqual(h['projectile'], 306)
        self.assertEqual(h['model']['unit'], '0x43A58CB89CFA197C')
        self.assertTrue(all(r['ownerCount'] == 1 for r in h['records'].values()))
        self.assertEqual(sorted(h['records']), ['EncyclopediaEntryComponentData', 'ProjectileWeaponComponentData',
            'SpottableComponentData', 'UnitComponentData'])
        u = RESEARCH['unitPathConsumers']
        self.assertEqual((u['callSites'], u['functions'], len(u['typeTableReaders'])), (20, 19, 3))
        self.assertTrue(all(s['kind'] for s in u['sites']))
        # No site keys, compares or serializes UnitPath: copies, other members, engine unit calls, two accessors.
        self.assertEqual(sum(u['byKind'].values()), 20)
        m = RESEARCH['models']['M-1000 Maxigun']
        self.assertEqual(m['archive'], 'b2c627b3ba7e0c0a')
        self.assertEqual([x['slotName'] for x in m['unit']['materials']], ['m_shadow', 'm_weapon', 'm_collision'])
        self.assertEqual(m['body']['slotIndex'], 1)
        self.assertEqual(m['lut']['format'], {'width': 23, 'height': 8, 'mips': 5, 'fourcc': 'DX10', 'dxgi': 10})
        self.assertEqual(m['unit']['ownNameAt'], ['0x20', '0x8'])

    def test_the_generated_domain_is_current(self):
        generator = load('generate_weapon_variants', 'scripts/generate_weapon_variants.py')
        self.assertEqual(generator.generate(check=True), [])

    @unittest.skipUnless(build_profile.SNAPSHOT.is_file(), 'retained snapshot absent')
    def test_every_retained_snapshot(self):
        module = load('validate_weapon_variant_snapshot', 'scripts/validate_weapon_variant_snapshot.py')
        names = [n for n in module.SNAPSHOTS if (build_profile.snapshot_directory() / n).is_file()]
        results = module.validate(tuple(names))
        for name, result in results.items():
            self.assertTrue(result['passed'], name + ': ' + '; '.join(result['problems']))
        self.assertTrue([r for r in results.values() if r['phase'] in ('alive', 'reinforced')],
            'no live mission snapshot validated')


class WeaponDeliveryTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(HARNESS + body + "\nreturn 'ok'"), b'ok')

    def test_registration_and_refusals(self):
        self.lua(r"""
local d=custom.register(laser(),OWNER)
assert(d.kind=='expendable'and d.delivery.variant and d.group=='weapon',tostring(d.group))
assert(table.concat(d.delivery.pool,',')==MAXI and d.delivery.round.type==144 and d.delivery.round.class=='conventional_plain')
assert(models.issued(d.delivery.model)and d.delivery.model_use=='check')
-- the round's package is a definition dependency (loaded with the clone's asset gate)
assert(d.pod_deps and d.pod_deps[1].package==d.delivery.round.package)
assert(said('REGISTERED laser_maxigun'):find('VARIANT of the M-1000 Maxigun on its own type',1,true))
custom.reset_for_tests()
refused(laser({id='x1',delivery={family='weapon',weapon={resource='support_weapon',weapon='AC-8 Autocannon'}}}),
    'delivery.weapon must name a reviewed variant weapon')
refused(laser({id='x2',delivery={family='weapon',weapon={resource='support_weapon',weapon=MAXI},
    round=out('output/v1/projectile/eagle-500kg-bomb-projectile-239')}}),'not live-tested yet')
local A=require('hd2runtime/domains/attack_outputs')
local other
for id,o in pairs(A.outputs)do
    if o.family=='projectile'and o.editable and not o.unverifiedDonor and o.compatibilityClass~='conventional_plain'
        and type(o.currentDefault)=='number'and o.dependencyKey then other=other or id end
end
refused(laser({id='x3',delivery={family='weapon',weapon={resource='support_weapon',weapon=MAXI},round=out(other)}}),
    'the compatibility class must be its own')
refused(laser({id='x4',delivery={family='weapon',weapon={resource='support_weapon',weapon=MAXI},model_use='apply'}}),
    'delivery.model_use needs delivery.model')
refused(laser({id='x5',delivery={family='weapon',weapon={resource='support_weapon',weapon=MAXI},modify={rpm=900}}}),
    'unsupported weapon delivery field: modify')
refused(laser({id='x6',delivery={family='weapon',weapon={resource='support_weapon',weapon=MAXI},model='laser_maxigun',
    model_use='later'}}),"delivery.model_use must be 'apply' or 'check'")
refused(laser({id='x7',carrier={group='expendable'}}),'carrier.group expendable cannot carry a weapon payload')
-- A code EQUAL to a vanilla stratagem's (live r25: DOWN LEFT DOWN UP RIGHT is the MG-43's): refused, naming it.
refused(laser({id='x8',code={'down','left','down','up','right'}}),"is the vanilla MG-43 Machine Gun's own code")
""")

    def test_no_fallback_availability_and_blocking(self):
        self.lua(r"""
local WC=require('hd2runtime/runtime/weapon_carriers')
local d=custom.register(laser(),OWNER)
-- Its pool is the Maxigun alone: free -> the Maxigun; picked natively -> UNAVAILABLE (no donor fallback).
local a=WC.allocate({{id='laser_maxigun',donor=MAXI}},{})
assert(a.assignments.laser_maxigun.weapon==MAXI)
local b=WC.allocate({{id='laser_maxigun',donor=MAXI}},{[MAXI_ID]=true},{who={[MAXI_ID]={'peer A'}}})
assert(a and b.assignments.laser_maxigun==nil and b.refused.laser_maxigun:find('^UNAVAILABLE'),tostring(b.refused.laser_maxigun))
assert(b.refused.laser_maxigun:find('M-1000 Maxigun (picked natively: peer A)',1,true),b.refused.laser_maxigun)
-- Selected, the Maxigun is its last viable carrier: blocked natively (the policy allocator stubbed).
local allocator=require('hd2runtime/runtime/carrier_allocator')
require('hd2runtime/runtime/event_world').players=function()return {}end
allocator.allocate_lobby=function(world,defs,opts)
    local r={ready=true,assignments={},refused={},verdicts={},candidates={},order={},line='CUSTOM CARRIERS: stub'}
    for k,x in ipairs(defs)do r.order[k]=x.id;r.assignments[x.id]={carrier='spare',stable_id=9000+k,type=300+k}end
    return r
end
local I=custom.internals_for_tests()
local al=I.allocate({},{},{d},'test',nil,nil,true)
local blocks=custom.carrier_blocks({},{present={},list={d}},al,{'laser_maxigun'})
assert(blocks[MAXI_ID]and blocks[MAXI_ID].ids[1]=='laser_maxigun','the vanilla Maxigun is blocked while selected')
""")

    def test_the_panel_details(self):
        # What the native-style panel draws over the native details panel (custom.panel_details): the stats in the
        # user's layout of 2026-10-06 (call-in time, uses, cooldown, the call-in code with its directions for the arrows).
        self.lua(r"""
custom.register(laser(),OWNER)
local function default(name,semantic)
    for _,f in ipairs(catalog.stratagems[name].fields)do if f.semanticFieldId==semantic then return f.currentDefault end end
end
local p=custom.panel_details('laser_maxigun')
assert(p.category=='CUSTOM SUPPLY STRATAGEM'and string.upper(tostring(p.name))=='LAS-1000 LASER MAXIGUN',tostring(p.name))
local labels={}
for k,row in ipairs(p.stats)do labels[k]=row[1]end
assert(table.concat(labels,',')=='CALL-IN TIME,USES,COOLDOWN TIME,CALL-IN CODE',table.concat(labels,','))
-- not picked yet: its carrier weapon's own stratagem (the Maxigun) and a hellpod's 4.75 s travel, to the native 0.05
local t=math.floor((default(MAXI,'stratagem.call_in_time')+custom.POD_TRAVEL)*20+0.5)/20
assert(p.stats[1][2]==('%.2f SEC'):format(t),p.stats[1][2])
assert(p.stats[3][2]==('%d SEC'):format(math.floor(default(MAXI,'stratagem.cooldown')+0.5)),p.stats[3][2])
assert(string.upper(p.stats[4][2])=='DOWN UP UP DOWN DOWN LEFT'
    and table.concat(p.stats[4].code,',')=='down,up,up,down,down,left',p.stats[4][2])
assert(custom.POD_TRAVEL==4.75 and custom.POD_KINDS.expendable and not custom.POD_KINDS.orbital)
-- a definition without a carrier yet and no pool: the carrier's own, as the cooldown
custom.register({id='later_orbital',name='LATER ORBITAL',description='d',icon='laser',
    code={'up','left','up','left','up','left','up'},carrier={group='orbital'},delivery='runtime'},OWNER)
local q=custom.panel_details('later_orbital')
assert(q.stats[1][2]=='AS ITS CARRIER'and q.stats[3][2]=='AS ITS CARRIER',q.stats[1][2])
""")

    def test_the_mission_glue(self):
        # One mission: the variant's apply spec (its round; the model only with model_use 'apply' and ready), its own
        # pod's delivery firing the round, its registry line.
        self.lua(r"""
local core_assets=require('hd2runtime/core/assets')
core_assets.gate=function()return {tick=function()return'ready'end}end
local cp=require('hd2runtime/runtime/carrier_presentation')
local applied={}
clone.apply=function(s,cb)applied[#applied+1]=s;cb({status='applied'});return {status='applied'}end
cp.apply=function(s,cb)cb({status='applied'});return {status='applied'}end
local ready=false
models.ready=function()if ready then return true end;return nil,'NOT_RESIDENT','its unit is not loaded'end
local I=custom.internals_for_tests()
local function mission_of(use)
    custom.reset_for_tests();clone.reset_for_tests();require('hd2runtime/runtime/virtual_stratagems').reset_for_tests()
    texts.reset_for_tests();lines={}
    local d=custom.register(laser({delivery={family='weapon',weapon={resource='support_weapon',weapon=MAXI},
        round=out('output/v1/projectile/las-58-talon'),model='laser_maxigun',model_use=use}}),OWNER)
    I.add_clone(d,{weapon={weapon=MAXI,stable_id=MAXI_ID},carrier=MAXI,stable_id=MAXI_ID,condensed=true})
    for _=1,3 do I.clone_step({runtime={}})end
    return d,applied[#applied]
end
-- check: the model is only read (MODEL NOT READY logged), never in the spec; the round always.
local d,s=mission_of('check')
assert(s.variant==true and s.carrier==MAXI and s.model==nil and s.round.type==144 and s.round.label=='LAS-58 Talon',
    tostring(s.variant))
assert(said('MODEL NOT READY (NOT_RESIDENT: its unit is not loaded)'):find('nothing written to its UnitPath (check only)',1,
    true),said('MODEL'))
-- apply, not ready: the vanilla model is kept, the round and name still apply.
d,s=mission_of('apply')
assert(s.model==nil and s.round.type==144)
assert(said('MODEL NOT READY'):find('the vanilla model is kept',1,true))
-- apply, ready: the model is in the spec.
ready=true
d,s=mission_of('apply')
assert(models.issued(s.model),'the model is applied when ready')
assert(said('MODEL READY:'):find("model 'laser_maxigun' of mods/test/laser",1,true),said('MODEL READY'))
-- Its delivery: the Maxigun's own pod (the gun and its backpack), the gun firing the Talon round.
local dl=custom.delivery_of(d)
assert(dl.stratagem==MAXI and dl.items['43A58CB89CFA197C'].projectile==144 and dl.items['056DE1C5E21E723E'].kind=='backpack')
""")

    def test_the_model_guard(self):
        self.lua(r"""
local V=require('hd2runtime/domains/weapon_variants')
local h=models.handle('laser_maxigun',OWNER)
assert(models.unit_hex(h)=='0x'..string.format('%08X%08X',images.hash(OWNER..'/models/laser_maxigun')))
local ok,code=models.ready({},h,MAXI)
assert(not ok and code=='NO_BUILD_RECORD',code)
local names=models.names(OWNER,'laser_maxigun')
local function record(over)
    local e={base=MAXI,archive='b2c627b3ba7e0c0a',build=V.source.build,baseUnit=V.hosts[MAXI].model.unit,
        baseUnitSha256=V.models[MAXI].unit.mainSha256,unit=names.unit,material=names.material,lut=names.lut}
    for k,v in pairs(over or{})do e[k]=v end
    package.loaded[OWNER..'/hd2runtime_models']={format=1,models={laser_maxigun=e}}
    models.reset_for_tests()
end
local loaded={}
images.loaded=function(runtime,kind,name)if loaded[name]then return true end;return false,'not in the game\'s resources'end
for _,case in ipairs({{{base='EAT-17 Expendable Anti-Tank'},'WRONG_BASE'},{{build='000000000000'},'OTHER_BUILD'},
    {{baseUnit='0x0000000000000001'},'BASE_CHANGED'},{{lut=names.lut..'x'},'NAME_MISMATCH'},{{},'NOT_RESIDENT'}})do
    record(case[1])
    local r,c=models.ready({},h,MAXI)
    assert(not r and c==case[2],tostring(c)..' expected '..case[2])
end
loaded[names.unit],loaded[names.material]=true,true
local r,c,why=models.ready({},h,MAXI)
assert(not r and c=='NOT_RESIDENT'and why:find('its lut',1,true),why)
loaded[names.lut]=true
assert(models.ready({},h,MAXI)==true)
assert(not models.ready({},h,'AC-8 Autocannon'))
""")


class ModelDerivationTests(unittest.TestCase):
    def test_derive_on_synthetic_bytes(self):
        import sys
        sys.path.insert(0, str(ROOT / 'scripts'))
        import hd2_model
        from hd2_archive import resource_hash
        mat_id, lut_id, unit_id = 0xB8F8D0F13850E657, 0x59B90501E2825030, 0x43A58CB89CFA197C
        unit = bytearray(0x100)
        struct.pack_into('<Q', unit, 0x80, mat_id)
        material = bytearray(0x140)
        struct.pack_into('<Q', material, 0x114, lut_id)
        width, height, mips = 23, 8, 5
        top = b''.join(struct.pack('<4e', 0.5, 0.5, 0.5, 1.0) for _ in range(width * height))
        lut_gpu = hd2_model.lut_mips([[(0.5, 0.5, 0.5, 1.0)] * width for _ in range(height)], width, height, mips)
        self.assertEqual(len(lut_gpu), 1928)
        self.assertEqual(lut_gpu[:len(top)], top)
        lut_main, unit_gpu = b'\x01' * 340, b'\x02' * 64
        sha = lambda b: hashlib.sha256(bytes(b)).hexdigest()
        base = {'archive': 'b2c627b3ba7e0c0a', 'build': 'F5FEE03DCFDB',
            'unit': {'resource': '0x%016X' % unit_id, 'mainSha256': sha(unit), 'gpuSha256': sha(unit_gpu)},
            'slots': [{'at': '0x78'}, {'at': '0x80'}], 'body': {'slotIndex': 1, 'material': '0x%016X' % mat_id,
                'mainSha256': sha(material), 'lutAt': '0x114'},
            'lut': {'texture': '0x%016X' % lut_id, 'format': {'width': width, 'height': height, 'mips': mips,
                'fourcc': 'DX10', 'dxgi': 10}, 'mainSha256': sha(lut_main), 'gpuSha256': sha(lut_gpu)}}
        keys = hd2_model.base_keys(base)
        parts = {keys[0]: (bytes(unit), unit_gpu), keys[1]: (bytes(material), b''), keys[2]: (lut_main, lut_gpu)}
        res, rec = hd2_model.derive('mods/test/laser', 'laser_maxigun', {'base': 'M-1000 Maxigun', 'palette': 'debug'},
            base, parts)
        names = hd2_model.names('mods/test/laser', 'laser_maxigun')
        u = res[(hd2_model.UNIT_TYPE, resource_hash(names['unit']))]
        m = res[(hd2_model.MATERIAL_TYPE, resource_hash(names['material']))]
        t = res[(hd2_model.TEXTURE_TYPE, resource_hash(names['lut']))]
        # The unit: only its body material slot renamed; its GPU part the base's.
        self.assertEqual(struct.unpack_from('<Q', u[0], 0x80)[0], resource_hash(names['material']))
        self.assertEqual(u[0][:0x80] + u[0][0x88:], bytes(unit[:0x80] + unit[0x88:]))
        self.assertEqual(u[1], unit_gpu)
        # The material: only its LUT reference renamed.
        self.assertEqual(struct.unpack_from('<Q', m[0], 0x114)[0], resource_hash(names['lut']))
        self.assertEqual(m[0][:0x114] + m[0][0x11C:], bytes(material[:0x114] + material[0x11C:]))
        # The LUT: the debug palette in column 0 of each row, everything else the base's; same size.
        self.assertEqual(t[0], lut_main)
        self.assertEqual(len(t[1]), len(lut_gpu))
        r0 = struct.unpack_from('<4e', t[1], 0)
        self.assertEqual((round(r0[0], 2), round(r0[1], 2), r0[3]), (1.0, 0.13, 1.0))
        self.assertEqual(struct.unpack_from('<4e', t[1], 8), (0.5, 0.5, 0.5, 1.0))
        self.assertEqual(rec['rows'], hd2_model.DEBUG)
        self.assertIn('laser_maxigun', hd2_model.record_lua({'laser_maxigun': rec}))
        # A base part that differs from the reviewed one: refused.
        bad = dict(parts)
        bad[keys[1]] = (bytes(material[:-1]) + b'\x07', b'')
        with self.assertRaisesRegex(ValueError, 'is not the reviewed one'):
            hd2_model.derive('mods/test/laser', 'laser_maxigun', {'base': 'M-1000 Maxigun', 'palette': 'debug'},
                base, bad)
        # Palettes.
        rows = hd2_model.palette_rows({'all': '#FF0000', 'rows': {'2': '#00FF00'}}, 8)
        self.assertEqual((rows[0], rows[2]), ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)))
        self.assertEqual(hd2_model.palette_rows({'rows': {'1': '#0000FF'}}, 8)[0], None)
        for bad_palette in ('blue', {'all': 'red'}, {'rows': {'9': '#FFFFFF'}}, {'tint': '#FFFFFF'}):
            with self.assertRaises(ValueError):
                hd2_model.palette_rows(bad_palette, 8)

    def test_the_sdk_capabilities_match_the_research(self):
        sdk = json.loads((ROOT / 'sdk/ModelBaseCapabilities.json').read_text(encoding='utf-8'))
        base = sdk['bases']['M-1000 Maxigun']
        m = RESEARCH['models']['M-1000 Maxigun']
        self.assertEqual((base['unit']['mainSha256'], base['lut']['gpuSha256'], base['body']['lutAt']),
            (m['unit']['mainSha256'], m['lut']['gpuSha256'], m['body']['lutAt']))
        self.assertEqual(base['build'], 'F5FEE03DCFDB')


if __name__ == '__main__':
    unittest.main()
