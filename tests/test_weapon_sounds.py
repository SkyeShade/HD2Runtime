"""The weapon firing-sound catalogue (docs/weapon-sounds.md; research/docs/weapon-sounds-F5FEE03DCFDB.md;
research/weapon-sounds-F5FEE03DCFDB.json -> scripts/generate_weapon_sounds.py -> domains/weapon_sounds.lua,
sdk/WeaponSoundCatalogue.json; runtime/weapon_sounds.lua; api/sounds.lua) and a Runtime Pelican chin gun taking any
'shot' or 'loop' entry on its OWN weapon copy (runtime/pelican_weapon.lua), on the host and on another machine's mirror:
  * every ProjectileWeapon type of the retained snapshots that names a firing sound, its events read from its record
    and found in a bank, under a semantic name; the raw ids stay in the domain for the Runtime only;
  * a shot writes the copy's +0x104 (and, for MIDI, +0xED and the instance's +0x38); a loop writes the copy's +0xFC,
    +0x100 and +0x104 = 0 and leaves +0xED and the instance's +0x38 at 0; never a shared record;
  * the package gate: a stratagem's call-in package is requested; a resident-only sound only while resident;
  * hd2.sounds lists and describes the catalogue without any raw id."""
import json
import re
import sys
import unittest

from support import ROOT, run, lua as lua_literal
from test_stratagem_calldown_code import WORLD
from test_stratagem_slot_conversion import SLOT
from test_bombardment_payload import PAYLOAD
from test_pelicans import PELICANS
from test_pelican_gatling import GATLING
from test_pelican_weapon import WEAPON
from test_custom_mp_pelican import MIRROR
from test_pelican_ai import AI
from test_pelican_heading import HEADING
from test_pelican_readonly_probes import HARNESS
from test_pelican_gatling_proof import PROOF
from test_pelican_gunship import GUNSHIP
from test_pelican_sound import SOUND

sys.path.insert(0, str(ROOT / 'scripts'))
RESEARCH = ROOT / 'research/weapon-sounds-F5FEE03DCFDB.json'
NAME = re.compile(r'^[a-z0-9_]+(/[a-z0-9_]+){1,2}$')


def catalogue():
    import generate_weapon_sounds
    return generate_weapon_sounds.build()


class ResearchTests(unittest.TestCase):
    def test_the_research_is_read_only_and_the_loop_path_is_pinned(self):
        r = json.loads(RESEARCH.read_text(encoding='utf-8'))
        self.assertEqual((r['writes'], r['protectionChanges']), (0, 0))
        self.assertEqual(len(r['pinnedBytesMismatchPerSnapshot']), 7)
        self.assertFalse(any(r['pinnedBytesMismatchPerSnapshot'].values()))
        pinned = {p['rva'] for rows in r['pins'].values() for p in rows}
        # The loop: the fire decision's edges (+0x10), the start on the rising one (non-MIDI, not fire mode 2 with a
        # per-shot event), the release on the falling one once the cooldown ran out, the stop there; the decision from
        # the firing byte, which follows the trigger; a loop weapon posts no per-shot event outside fire mode 2.
        self.assertTrue({0x617058, 0x617063, 0x61708A, 0x6170DC, 0x6170E1, 0x6170F0, 0x6170FA, 0x617134, 0x61726E,
            0x6172C4, 0x6172DA, 0x6167BF, 0x6167C9, 0x616806, 0x616855, 0x6168AE, 0x616D51, 0x616C01, 0x616E63, 0x615050,
            0x61505E, 0x614BFF} <= pinned)
        # The per-shot event by fire mode, and the r7 sound path re-proven.
        self.assertTrue({0x614B5D, 0x614B88, 0x614BAD, 0x612A13, 0x614C4D, 0x611D67, 0x6168B2} <= pinned)
        # The trigger is copied from the owner's blob on every machine (research/peer-messaging, re-checked).
        self.assertEqual({p['rva'] for p in r['replication']}, {7604117, 7628023, 6387977, 6385251})
        self.assertIn('rising edge of the fire decision', r['loop']['rule'])

    def test_every_catalogued_event_is_read_from_a_record_and_defined_by_a_bank(self):
        r = json.loads(RESEARCH.read_text(encoding='utf-8'))
        self.assertEqual(r['counts']['types'], 271)
        self.assertEqual(r['counts']['sounding'] + r['counts']['notCatalogued'] + r['counts']['silent'], 271)
        for e in r['entries']:
            s = e['sound']
            ids = [s['start'], s['stop']] if s['kind'] == 'loop' else [s['event']]
            for event in ids:
                self.assertNotEqual(event, '00000000', e['resource'])
                self.assertTrue(r['events'][event]['banks'], e['resource'])
            self.assertTrue(e['banks'])
        # The one type whose event no bank defines stays out.
        self.assertEqual(list(r['notCatalogued']), ['C1841A7BAE3D5CD8'])


class CatalogueTests(unittest.TestCase):
    def test_the_generated_files_are_current(self):
        import generate_weapon_sounds
        self.assertEqual(generate_weapon_sounds.generate(check=True), [])

    def test_the_four_pelican_builds(self):
        sounds = catalogue()['sounds']
        chin = sounds['pelican/chin_autocannon']
        self.assertEqual((chin['kind'], chin['event'], chin['midi'], chin['own'], chin['bank']['name']),
            ('shot', '8D4641BA', 0, True, 'content/audio/vehicle_shuttle'))
        self.assertEqual((chin['writes'], chin['instanceWrites'], chin.get('stratagem'), chin['residentOnly']),
            ([], [], None, False))
        gat = sounds['sentry/gatling']
        self.assertEqual((gat['kind'], gat['start'], gat['stop'], gat['midi'], gat['stratagem'], gat['rpm']),
            ('loop', '98F18D8B', '0C5CA529', 0, 'A/G-16 Gatling Sentry', 1600.0))
        self.assertEqual(gat['bank']['name'], 'content/audio/stratagems_sentry_gatling')
        self.assertEqual(gat['requests'], ['0x992D325D88DE5FBF'])
        # A loop: start, stop, and the per-shot event cleared, as the Gatling's own record; no MIDI, no instance write.
        self.assertEqual(gat['writes'], [
            {'name': 'loopStart', 'offset': 0xFC, 'size': 4, 'from': '00000000', 'to': '8b8df198'},
            {'name': 'loopStop', 'offset': 0x100, 'size': 4, 'from': '00000000', 'to': '29a55c0c'},
            {'name': 'event', 'offset': 0x104, 'size': 4, 'from': 'ba41468d', 'to': '00000000'}])
        self.assertEqual(gat['instanceWrites'], [])
        mael = sounds['vehicle/maelstrom/main_gun']
        self.assertEqual((mael['kind'], mael['event'], mael['midi'], mael['stratagem'], mael['bank']['name'],
            mael['resource']), ('shot', 'E5CA1945', 1, 'TD-110 Maelstrom', 'content/audio/vehicle_storm_tank',
            'D58AE6A04EDB10DE'))
        self.assertEqual(mael['requests'], ['0x65EE777B72347CB4'])
        hmg = sounds['vehicle/bastion/hmg']
        self.assertEqual((hmg['kind'], hmg['event'], hmg['midi'], hmg['resource'], hmg['rpm'], hmg['bank']['name']),
            ('shot', '825E6711', 1, '439F9E65C18567DA', 600.0, 'content/audio/wep_heavy_machinegun'))
        # Its bank comes with the smallest call-in package that lists it: the HMG Emplacement's.
        self.assertEqual((hmg['stratagem'], hmg['requests']), ('E/MG-101 HMG Emplacement', ['0x68E80476C1C602F5']))
        self.assertEqual([(l['distance'], l['count']) for l in hmg['range']['layers']], [(650.0, 2), (240.0, 6), (4.0, 1)])
        self.assertEqual([w['name'] for w in hmg['writes']], ['midi', 'event'])
        self.assertEqual(hmg['instanceWrites'], [{'name': 'midi', 'offset': 0x38, 'size': 1, 'from': '00', 'to': '01'}])
        self.assertEqual(sounds['support/mg206']['event'], '825E6711')

    def test_names_coverage_and_aliases(self):
        d = catalogue()
        sounds = d['sounds']
        self.assertEqual(d['aliases'], {'maelstrom_main_gun': 'vehicle/maelstrom/main_gun',
            # 0.30.2: names published before the Defender and GP-31 roots were proven
            'primary/smg37/seaf': 'seaf/3', 'secondary/gp31/alt': 'other/wep_grenadier_rifle/1'})
        for name, s in sounds.items():
            self.assertRegex(name, NAME)
            self.assertEqual(name.split('/')[0], s['family'])
            # A name never carries a raw event id.
            for event in (s.get('event'), s.get('start'), s.get('stop')):
                if event:
                    self.assertNotIn(event.lower(), name)
            self.assertIn(s['kind'], ('shot', 'loop'))
            self.assertTrue(s['packages'] or s['own'])
            self.assertEqual(s['residentOnly'], not s['own'] and 'stratagem' not in s)
        families = {s['family'] for s in sounds.values()}
        self.assertTrue({'pelican', 'vehicle', 'sentry', 'emplacement', 'eagle', 'backpack', 'support', 'primary',
            'secondary', 'automaton', 'illuminate'} <= families)
        # Every catalogued weapon with a firing sound is named: the Pelican, every sounding vehicle mount, the sentries
        # and emplacements, support, primary and secondary weapons.
        for name in ('sentry/machine_gun', 'sentry/autocannon', 'sentry/mortar', 'sentry/rocket', 'sentry/ems_mortar',
                'sentry/gas_mortar', 'emplacement/hmg', 'emplacement/anti_tank', 'eagle/cannon', 'backpack/guard_dog',
                'vehicle/bastion/cannon', 'vehicle/patriot/minigun', 'vehicle/emancipator/autocannons',
                'vehicle/gunner_frv/hmg', 'support/m1000', 'support/mg43', 'support/mg43/seaf', 'primary/ar23',
                'secondary/p2'):
            self.assertIn(name, sounds)
        self.assertEqual(sounds['support/m1000']['kind'], 'loop')
        # Every type with a firing sound is an entry or folded into one with the same events.
        self.assertEqual(d['counts']['entries'] + d['counts']['folded'], d['counts']['sounding'])

    def test_every_stratagem_is_a_complete_catalogued_call_in(self):
        slots = json.loads((ROOT / 'research/stratagem-slot-conversion-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
        incomplete = set(slots['stratagemPackages']['callIn']['incomplete'])
        known = json.loads((ROOT / 'schemas/stratagem_authoring_catalog.json').read_text(encoding='utf-8'))['stratagems']
        for name, s in catalogue()['sounds'].items():
            if 'stratagem' in s:
                self.assertIn(s['stratagem'], known, name)
                self.assertNotIn(s['stratagem'], incomplete, name)
                self.assertEqual(s['stratagemId'], known[s['stratagem']]['root']['id'])
                self.assertEqual(s['packages'][:len(s['requests'])], [{'package': p, 'label': s['packages'][k]['label']}
                    for k, p in enumerate(s['requests'])])

    def test_the_sdk_catalogue_has_no_raw_ids(self):
        text = (ROOT / 'sdk/WeaponSoundCatalogue.json').read_text(encoding='utf-8')
        d = json.loads(text)
        self.assertEqual(len(d['sounds']), catalogue()['counts']['entries'])
        events = set()
        for s in catalogue()['sounds'].values():
            events |= {s.get('event'), s.get('start'), s.get('stop'), s['resource'], s['bank']['resource']}
        for raw in events - {None}:
            self.assertNotIn(raw, text)
            self.assertNotIn(raw.lower(), text)
        self.assertNotRegex(text, r'0x[0-9A-Fa-f]{16}')


API = r"""
local hd2=require('hd2runtime/api/hd2')
"""


class ApiTests(unittest.TestCase):
    def test_list_and_describe_without_raw_ids(self):
        n = catalogue()['counts']['entries']
        self.assertEqual(run(API + r"""
local all=hd2.sounds.list()
assert(#all==""" + str(n) + r""",#all)
for k=2,#all do assert(all[k-1].name<all[k].name)end
local seen={}
for _,s in ipairs(all)do
    for key in pairs(s)do seen[key]=true end
    assert(not s.event and not s.start and not s.stop and not s.bank and not s.packages and not s.resource)
end
for _,key in ipairs({'name','label','kind','family','resident_only','designed_rpm','midi','pelican_default'})do
    assert(seen[key],key)
end
-- Nothing returned holds an event id (8 hex digits): every string checked.
for _,s in ipairs(all)do
    for key,v in pairs(s)do
        if type(v)=='string'and key~='label'then assert(not v:upper():find('^%x%x%x%x%x%x%x%x$'),key)end
    end
end
local g=hd2.sounds.describe('sentry/gatling')
assert(g.kind=='loop'and g.family=='sentry'and g.stratagem=='A/G-16 Gatling Sentry'and g.resident_only==false
    and g.designed_rpm==1600 and g.range_m==160 and g.midi==false and g.pelican_default==false)
local m=hd2.sounds.describe('maelstrom_main_gun')
assert(m.name=='vehicle/maelstrom/main_gun'and m.kind=='shot'and m.midi==true and m.stratagem=='TD-110 Maelstrom')
local chin=hd2.sounds.describe('pelican/chin_autocannon')
assert(chin.pelican_default==true and chin.stratagem==nil and chin.resident_only==false)
assert(hd2.sounds.describe('E5CA1945')==nil and hd2.sounds.describe('no such sound')==nil and hd2.sounds.describe(7)==nil)
-- Filters.
local sentries=hd2.sounds.list('sentry')
assert(#sentries>=7)
for _,s in ipairs(sentries)do assert(s.family=='sentry')end
local loops=hd2.sounds.list({kind='loop',family='sentry'})
assert(#loops==2 and loops[1].name=='sentry/gatling'and loops[2].name=='sentry/machine_gun')
for _,s in ipairs(hd2.sounds.list({resident_only=true}))do assert(s.resident_only and s.stratagem==nil)end
local hmg=hd2.sounds.list({stratagem='E/MG-101 HMG Emplacement'})
local names={};for _,s in ipairs(hmg)do names[s.name]=true end
assert(names['vehicle/bastion/hmg']and names['support/mg206']and names['emplacement/hmg'])
assert(#hd2.sounds.list({text='maelstrom'})==3)
-- An invalid filter is the mod's mistake: an error that names it.
local ok,why=pcall(hd2.sounds.list,{colour='red'})
assert(not ok and tostring(why):find('unsupported filter key: colour',1,true))
ok,why=pcall(hd2.sounds.list,{kind='burst'})
assert(not ok and tostring(why):find("filter.kind must be 'shot' or 'loop'",1,true))
assert(not pcall(hd2.sounds.list,42))
return 'ok'
"""), b'ok')

    def test_a_custom_stratagem_loads_the_entrys_stratagem(self):
        self.assertEqual(run(r"""
local custom=require('hd2runtime/runtime/custom_stratagems');custom.reset_for_tests()
local codes={{'left','down','left','up','left','up'},{'left','down','left','up','right','up'},
    {'left','down','left','down','right','up'},{'left','down','right','down','right','up'},
    {'left','down','right','up','right','up'}}
local k=0
local function pel(id,sound)
    k=k+1
    return custom.register({id=id,name=id,description='d',icon=id,code=codes[k],
        carrier={beacon='offensive',prefer_families={'orbital'}},pelican={hover=60,gun={behave_as='gatling_sentry',
        sound=sound}}},'mods/test/'..id)
end
local function has(d,name)for _,a in ipairs(d.assets)do if a==name then return true end end;return false end
local gat=pel('gat','sentry/gatling')
assert(has(gat,'A/G-16 Gatling Sentry')and gat.pelican.gun.sound=='sentry/gatling')
local hmg=pel('hmg','vehicle/bastion/hmg')
assert(has(hmg,'E/MG-101 HMG Emplacement')and not has(hmg,'TD-220 Bastion MK XVI'))
-- The chin turret's own sound and a resident-only sound load nothing more than the gun itself does.
local own=pel('own','pelican/chin_autocannon')
assert(#own.assets==1 and own.assets[1]=='A/G-16 Gatling Sentry')
local ro=pel('ro','primary/ar23')
assert(#ro.assets==1 and ro.assets[1]=='A/G-16 Gatling Sentry')
local ok=pcall(pel,'bad','vehicle/no_such_gun')
assert(not ok)
return 'ok'
"""), b'ok')


SETUP = r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
scene()
local inst=sound_instances()
local world=world_module.open()
-- The Bastion's HMG type record (index 3), as the game holds it.
local HMG=WSD.sounds['vehicle/bastion/hmg']
local HMGREC=sound_type(3,HMG,275,600)
"""


class HostTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + PELICANS + 'return (function()\n' + GATLING + WEAPON + SOUND
            + SETUP + body + "\nreturn 'ok'\nend)()\n"), b'ok')

    def test_a_loop_on_its_own_copy_only(self):
        self.check(r"""
local chin_before,gat_before=W.read(CHINREC,PWT.stride),W.read(GATREC,PWT.stride)
local inst_before=W.read(inst,PWS.instanceStride)
local writes=#W.runtime.writes
local r,code,reason=in_update(function()return weapon.configure(world,9501,{projectile=148,rpm=600,
    sound='sentry/gatling'},'test')end)
assert(r and r.verified,tostring(code)..' '..tostring(reason))
-- One transaction: projectile, current RPM, the copy's loop start, loop stop and per-shot event (cleared).
assert(r.writes==5 and #W.runtime.writes==writes+5,'writes '..tostring(r.writes))
assert(r.sound.applied and r.verify.sound and r.verify.sound_shared and r.verify.shared and r.spec.sound=='sentry/gatling')
local copy=W.read(PCOPIES,PWS.copyStride)
assert(differ(copy,chin_before)=='0,252,253,254,255,256,257,258,259,260,261,262,263',differ(copy,chin_before))
assert(b.u32(copy,0xFC)==0x98F18D8B and b.u32(copy,0x100)==0x0C5CA529 and b.u32(copy,0x104)==0 and copy:byte(0xED+1)==0)
-- Its instance record: untouched (+0x38 stays 0, the value the game derives for a non-MIDI record).
assert(W.read(inst,PWS.instanceStride)==inst_before and midi_of(inst)==0)
-- The chin turret's and the Gatling Sentry's type records: unchanged, whole.
assert(W.read(CHINREC,PWT.stride)==chin_before and W.read(GATREC,PWT.stride)==gat_before)
local st=weapon.sound_state(world,8102,GD.chinTurretResource)
assert(st.from=='copy'and weapon.sound_matches(st,'sentry/gatling')and st.loop_start=='98F18D8B'
    and st.loop_stop=='0C5CA529'and st.event=='00000000')
assert(n('PELICAN WEAPON APPLIED (test): chin turret 8102: projectile 148, current RPM 600 (requested), sound '
    ..'sentry/gatling true (98F18D8B / 0C5CA529); 5 writes; verified true')==1,table.concat(logged,' | '))
""")

    def test_a_loop_waits_until_no_loop_can_be_playing(self):
        self.check(r"""
-- Its fire decision is set (a loop started on its rising edge would still play): not applied, the rest is.
W.write(inst+SDX.instance.decision,'\1')
local r=in_update(function()return weapon.configure(world,9501,{projectile=148,rpm=600,sound='sentry/gatling'},'test')end)
assert(r and r.verified and not r.sound.applied and r.sound.retry and r.writes==2)
local w0=#W.runtime.writes
assert(select(2,in_update(function()return weapon.apply_sound(world,8102,'sentry/gatling','test')end))=='NOT_QUIET'
    and#W.runtime.writes==w0)
-- Released (the stop posted, the decision cleared): applied in its own transaction.
W.write(inst+SDX.instance.decision,'\0')
local s=in_update(function()return weapon.apply_sound(world,8102,'sentry/gatling','test')end)
assert(s and s.applied and s.verified and s.writes==3)
assert(n('PELICAN WEAPON SOUND APPLIED (test): chin turret 8102: its own copy posts the A/G-16 Gatling Sentry\'s loop '
    ..'98F18D8B / 0C5CA529 (bank content/audio/stratagems_sentry_gatling')==1,table.concat(logged,' | '))
""")

    def test_the_bastion_hmg_shot(self):
        self.check(r"""
local chin_before,hmg_before=W.read(CHINREC,PWT.stride),W.read(HMGREC,PWT.stride)
local r,code,reason=in_update(function()return weapon.configure(world,9501,{projectile=148,rpm=600,
    sound='vehicle/bastion/hmg'},'test')end)
assert(r and r.verified and r.writes==5,tostring(code)..' '..tostring(reason))
local copy=W.read(PCOPIES,PWS.copyStride)
assert(differ(copy,chin_before)=='0,237,260,261,262,263'and copy:byte(0xED+1)==1 and b.u32(copy,0x104)==0x825E6711)
assert(midi_of(inst)==1 and W.read(HMGREC,PWT.stride)==hmg_before and W.read(CHINREC,PWT.stride)==chin_before)
""")

    def test_a_plain_shot_writes_only_its_event(self):
        name = next(n for n, s in sorted(catalogue()['sounds'].items())
            if s['kind'] == 'shot' and s['midi'] == 0 and not s['own'] and s.get('stratagem'))
        self.check(r"""
local NAME=""" + lua_literal(name) + r"""
local chin_before,inst_before=W.read(CHINREC,PWT.stride),W.read(inst,PWS.instanceStride)
local r,code,reason=in_update(function()return weapon.configure(world,9501,{projectile=148,rpm=600,sound=NAME},'test')end)
assert(r and r.sound.applied and r.writes==3,tostring(code)..' '..tostring(reason))
local copy=W.read(PCOPIES,PWS.copyStride)
for o in differ(copy,chin_before):gmatch('%d+')do assert(({['0']=1,['260']=1,['261']=1,['262']=1,['263']=1})[o],o)end
assert(('%08X'):format(b.u32(copy,0x104))==WSD.sounds[NAME].event and copy:byte(0xED+1)==0)
assert(W.read(inst,PWS.instanceStride)==inst_before)
""")

    def test_the_chin_turrets_own_sound_writes_nothing(self):
        self.check(r"""
local r=in_update(function()return weapon.configure(world,9501,{projectile=148,rpm=600,
    sound='pelican/chin_autocannon'},'test')end)
assert(r and r.verified and r.writes==2 and r.sound==nil and r.spec.sound==nil)
local st=weapon.sound_state(world,8102,GD.chinTurretResource)
assert(st.name=='chin'and weapon.sound_matches(st,'pelican/chin_autocannon')and midi_of(inst)==0)
assert(weapon.sound_assets(world,0,'pelican/chin_autocannon')=='ready')
-- An unknown name or a raw id: refused before anything.
assert(select(2,in_update(function()return weapon.configure(world,9501,{rpm=600,sound='98F18D8B'},'test')end))=='INVALID')
""")

    def test_the_package_gate(self):
        self.check(r"""
-- A stratagem's sound: its call-in package(s) that list the bank are what the Runtime requests.
local deps=weapon.sound_dependencies('vehicle/bastion/hmg')
assert(#deps==1 and deps[1].package=='0x68E80476C1C602F5'and deps[1].label=='E/MG-101 HMG Emplacement',
    tostring(deps and deps[1]and deps[1].package))
assert(weapon.sound_dependencies('pelican/chin_autocannon')==nil and weapon.sound_dependencies('primary/ar23')==nil,
    'no dependencies')
-- Its bank not resident anywhere: refused with ASSET_UNAVAILABLE before any call.
for _,p in ipairs(HMG.packages)do GX.absent_packages[p.package]=true end
local r,code,reason=in_update(function()return weapon.configure(world,9501,{projectile=148,rpm=600,
    sound='vehicle/bastion/hmg'},'test')end)
assert(not r and code=='ASSET_UNAVAILABLE'and reason:find('wep_heavy_machinegun',1,true)and#GX.calls==0,tostring(code))
-- A resident-only sound: never requested; ready only while a package listing its bank is resident here.
local AR=WSD.sounds['primary/ar23']
assert(AR.residentOnly and not AR.stratagem,'resident-only')
for _,p in ipairs(AR.packages)do GX.absent_packages[p.package]=true end
local state,why=weapon.sound_assets(world,0,'primary/ar23')
assert(state=='failed'and why:find('^ASSET_UNAVAILABLE')and why:find('resident-only',1,true),tostring(why))
local requests=GX.requests
GX.absent_packages[AR.packages[#AR.packages].package]=nil
assert(weapon.sound_assets(world,0,'primary/ar23')=='ready'and GX.requests==requests,'ready')
local ok,ocode,oreason=in_update(function()return weapon.configure(world,9501,{projectile=148,rpm=600,
    sound='primary/ar23'},'test')end)
assert(ok and ok.sound.applied and b.u32(W.read(PCOPIES+0x104,4),0)==0xAC6B5FFB and AR.midi==1 and midi_of(inst)==1,
    tostring(ocode)..' '..tostring(oreason)..' '..table.concat(logged,' | '))
assert(n('PELICAN WEAPON APPLIED (test): chin turret 8102: projectile 148, current RPM 600 (requested), sound '
    ..'primary/ar23 ')==1,table.concat(logged,' | '))
""")


class MirrorTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + PELICANS + 'return (function()\n' + GATLING + WEAPON + MIRROR
            + SOUND + body + "\nreturn 'ok'\nend)()\n"), b'ok')

    def test_a_client_loops_on_its_own_copy(self):
        self.check(r"""
local world=client_copy()
local inst=sound_instances()
local chin_before,gat_before=W.read(CHINREC,PWT.stride),W.read(GATREC,PWT.stride)
local entry,mag,inst_before=entry_raw(),W.read(MGRECS,MG.stride),W.read(inst,PWS.instanceStride)
local spec={pelican=9501,round='standard',gatling=true,rate_factor=2,spread=100,recoil='zero',sound='sentry/gatling',
    client=true}
local r,code,reason=in_update(function()return weapon.mirror_configure(world,8102,spec,'mirror')end)
assert(r and r.verified and r.sound.applied and r.verify.sound_shared,tostring(code)..' '..tostring(reason))
local copy=W.read(PCOPIES,PWS.copyStride)
assert(b.u32(copy,0xFC)==0x98F18D8B and b.u32(copy,0x100)==0x0C5CA529 and b.u32(copy,0x104)==0 and copy:byte(0xED+1)==0)
-- Never what the network writes (its current RPM entry, rounds, trigger), never a type record, its instance's MIDI
-- flag untouched.
assert(entry_raw()==entry and W.read(MGRECS,MG.stride)==mag and midi_of(inst)==0)
assert(W.read(CHINREC,PWT.stride)==chin_before and W.read(GATREC,PWT.stride)==gat_before)
assert(n('PELICAN WEAPON MIRROR APPLIED (mirror): chin turret 8102 (a network copy here): its own copy names projectile '
    ..'148, rate slot 3200, casing true, spread true, sound sentry/gatling true (98F18D8B / 0C5CA529)')==1,
    table.concat(logged,' | '))
""")

    def test_the_mirror_takes_the_definitions_sound_and_skips_the_chins_own(self):
        self.check(r"""
local world=client_copy()
local inst=sound_instances()
local GUNS={behave_as='gatling_sentry',rate_multiplier=2,round='standard',spread=100,recoil=false,sound='vehicle/bastion/hmg'}
local m=custom_pelican.mirror({turret=8102,pelican=9501,network=701,gun=GUNS,label='m',client=true})
tick();tick()
assert(m.configured and midi_of(inst)==1 and b.u32(W.read(PCOPIES+0x104,4),0)==0x825E6711,table.concat(logged,' | '))
assert(n('assets for pelican-sound-vehicle/bastion/hmg requested')==1,table.concat(logged,' | '))
""")

    def test_the_chins_own_sound_on_a_mirror(self):
        self.check(r"""
local world=client_copy()
local inst=sound_instances()
local GUNS={behave_as='gatling_sentry',rate_multiplier=2,round='standard',spread=100,recoil=false,
    sound='pelican/chin_autocannon'}
local m=custom_pelican.mirror({turret=8102,pelican=9501,network=701,gun=GUNS,label='m',client=true})
tick();tick()
assert(m.configured and m.configured.sound==nil and midi_of(inst)==0,table.concat(logged,' | '))
assert(b.u32(W.read(PCOPIES+0x104,4),0)==0x8D4641BA and n('pelican-sound')==0,table.concat(logged,' | '))
""")


class GunshipTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + PELICANS + "\nlocal PROOF_ADDON=''\nlocal PROOF_RESOURCE="
            + lua_literal('mods/test/gunship') + '\n' + 'return (function()\n' + HARNESS + GATLING + WEAPON + AI
            + HEADING + PROOF + GUNSHIP + SOUND + body + "\nreturn 'ok'\nend)()\n"), b'ok')

    def test_the_gatling_sentry_loop_build(self):
        self.lua(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
tick(4)
scene()
local inst=sound_instances()
controller()
stage(0,2,0)
ai(4)
local gun={};for k,v in pairs(FROZEN)do gun[k]=v end;gun.sound='sentry/gatling'
local events={}
assert(gunship.arm(9501,{gun=gun,label='g'},function(e)events[#events+1]=e end))
tick(16)
local armed
for _,e in ipairs(events)do if e.kind=='armed'then armed=e end end
assert(armed and armed.sound=='sentry/gatling'and armed.verified,table.concat(logged,' | '))
assert(n('assets for pelican-sound-sentry/gatling requested')==1,table.concat(logged,' | '))
local copy=W.read(PCOPIES,PWS.copyStride)
assert(b.u32(copy,0xFC)==0x98F18D8B and b.u32(copy,0x100)==0x0C5CA529 and b.u32(copy,0x104)==0 and midi_of(inst)==0)
""")


class StubTests(unittest.TestCase):
    def test_the_stubs_and_docs_are_current(self):
        import generate_events
        import generate_sdk
        self.assertEqual(generate_events.generate(check=True), [])
        self.assertEqual(generate_sdk.generate(check=True), [])
        stub = (ROOT / 'sdk/stubs/mods/skyeshade/hd2runtime.lua').read_text(encoding='utf-8')
        for text in ('---@class HD2Sounds', 'function HD2Sounds.list(filter) end', 'function HD2Sounds.describe(name) end',
                '---@class HD2WeaponSound', '---@field sounds HD2Sounds'):
            self.assertIn(text, stub)
        self.assertEqual((ROOT / 'sdk/docs/weapon-sounds.md').read_text(encoding='utf-8'),
            (ROOT / 'docs/weapon-sounds.md').read_text(encoding='utf-8'))
        api = (ROOT / 'docs/custom-stratagem-api.md').read_text(encoding='utf-8')
        self.assertIn("sound='sentry/gatling'", api)
        self.assertIn('docs/weapon-sounds.md', api)


if __name__ == '__main__':
    unittest.main()
