"""The Pelican chin gun's firing sound (research/docs/pelican-maelstrom-sound-F5FEE03DCFDB.md;
research/pelican-maelstrom-sound-F5FEE03DCFDB.json; runtime/pelican_weapon.lua sound section): a projectile weapon's
firing sound is its RESOLVED ProjectileWeapon record's +0xED (MIDI) and +0x104 (the per-shot Wwise event), read at every
shot, plus its instance record's +0x38 the game derives from +0xED at creation. gun.sound = 'maelstrom_main_gun' writes
only the chin turret's OWN copy (+0xED, +0x104) and its OWN instance record (+0x38), in the copy's guarded transaction on
the host and in mirror_configure on another machine (deferred there until its bank is resident), never the chin turret's
or the Maelstrom main gun's type record; refused with ASSET_UNAVAILABLE while no package listing the Maelstrom's bank is
resident. On the offline Pelican world and turret fixture of tests/test_pelican_gatling.py."""
import json
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

RESEARCH = ROOT / 'research/pelican-maelstrom-sound-F5FEE03DCFDB.json'

SOUND = r"""
local SDX=PE.sound
-- The weapon sound catalogue (domains/weapon_sounds.lua): the Maelstrom main gun, by its alias's target.
local WSD=require('hd2runtime/domains/weapon_sounds')
local MS=WSD.sounds[WSD.aliases.maelstrom_main_gun]
for _,pin in ipairs(SDX.pins)do W.write(W.GAME+pin.rva,b.unhex(pin.hex))end
for _,pin in ipairs(WSD.pins)do W.write(W.GAME+pin.rva,b.unhex(pin.hex))end
-- A record's firing-sound block (the fixture builds the fire effects only): the domain's bytes, block by block.
local function put_sound(at,hex)
    local raw,cursor=b.unhex(hex),0
    for _,blk in ipairs(SDX.record.blocks)do W.write(at+blk[1],raw:sub(cursor+1,cursor+blk[2]));cursor=cursor+blk[2]end
end
local PWT=GD.pwTypes
local CHINREC=PWTAB+PWT.records                       -- the chin turret's type record (index 0)
put_sound(CHINREC,SDX.chin.blockBytes)
-- A catalogue sound's own weapon type record (index k) in the same table, its firing-sound block as observed (the chin
-- turret's own with that sound's fields: what the catalogue's blockBytes hold).
local function sound_type(k,entry,projectile,rpm)
    local key=b.unhex(entry.resource):reverse()
    local at=PWTAB+PWT.records+k*PWT.stride
    local lo,hi=b.u32(key,0),b.u32(key,4)
    local slot=((hi%PWT.slots)*(4294967296%PWT.slots)+lo%PWT.slots)%PWT.slots
    while W.read(PWTAB+slot*16,8)~=string.rep('\0',8)do slot=(slot+1)%PWT.slots end
    W.write(PWTAB+slot*16,key..W.u32(k)..W.u32(0))
    W.write(at,W.u32(projectile)..f32(0)..f32(rpm)..f32(0))
    put_sound(at,entry.blockBytes)
    return at
end
-- The Maelstrom main gun's type record (index 2).
local MAELREC=sound_type(2,MS,251,1200)
-- The Gatling Sentry's type record (index 1, the fixture's own) with its observed loop.
local GATSOUND=WSD.sounds['sentry/gatling']
local GATREC=PWTAB+PWT.records+PWT.stride
put_sound(GATREC,GATSOUND.blockBytes)
-- The weapons' instance records in a page-backed allocation (the game's heap is; the fixture's own is half a page).
local PWS=TW.projectileWeapon
local function sound_instances()
    local inst=W.alloc(0x1000)
    W.write(inst,W.read(PINST,0x800))
    W.write(PCOMP+PWS.instances,W.u64(inst))
    return inst
end
-- The packages that list the Maelstrom's bank: resident unless GX.sound_absent; a package in GX.absent_packages:
-- absent.
local sound_previous=W.runtime.package_state
GX.absent_packages={}
W.runtime.package_state=function(hex)
    if GX.absent_packages[hex]then return'absent'end
    for _,p in ipairs(MS.packages)do if hex==p.package then return GX.sound_absent and'absent'or'resident'end end
    return sound_previous(hex)
end
local function midi_of(inst)return W.read(inst+SDX.instance.midi,1):byte()end
-- The bytes of two records that differ (offsets).
local function differ(a,c)
    local out={}
    for k=1,#a do if a:byte(k)~=c:byte(k)then out[#out+1]=k-1 end end
    return table.concat(out,',')
end
"""


class SoundResearchTests(unittest.TestCase):
    def test_the_audio_path_is_pinned_and_read_only(self):
        r = json.loads(RESEARCH.read_text(encoding='utf-8'))
        self.assertEqual((r['writes'], r['protectionChanges']), (0, 0))
        self.assertFalse(any(r['pinnedBytesMismatchPerSnapshot'].values()))
        self.assertEqual(len(r['pinnedBytesMismatchPerSnapshot']), 7)
        pinned = {p['rva'] for rows in r['pins'].values() for p in rows}
        # The shot resolves its record (copy first) and reads the per-shot event and the MIDI switch from it; the loop
        # start / stop at the trigger transitions; creation derives instance +0x38; the release reads it.
        self.assertTrue({0x612A13, 0x612A1F, 0x614BAD, 0x614C4D, 0x615050, 0x6150B4, 0x614D96, 0x614FC2, 0x616B4C,
            0x6170FA, 0x61678C, 0x616806, 0x611CD9, 0x611D52, 0x611D67, 0x6168B2, 0x6168E0, 0x616BD5} <= pinned)
        # A WeaponData override replaces +0x104 only with a non-zero event; the three weapons' tables are empty.
        self.assertTrue({0x612BEE, 0x612C04, 0x612C50, 0x614BA6, 0x614BA9} <= pinned)
        self.assertEqual(r['engine']['rtpcs'], {'2247628': 'rounds_fired', '2247638': 'CyclingTime'})
        # [O] all three types in all seven snapshots; every live weapon's instance +0x38 is its resolved +0xED.
        self.assertEqual(len(r['observed']['completeIn']), 7)
        for name in r['observed']['completeIn']:
            types = r['observed']['types'][name]
            for kind in ('chinTurret', 'gatlingSentry', 'maelstromMainGun'):
                self.assertEqual(types[kind]['overrideEvents'], [0] * 8, (name, kind))
            self.assertGreater(types['overrideTable']['withOverrideEvents'], 0)
        for name, o in r['observed']['instances'].items():
            self.assertEqual(o['copies'], 0, name)
            self.assertTrue(all(row['recordMidi'] == row['instanceMidi'] for row in o['rows']), name)

    def test_the_maelstrom_sound_differs_from_the_chin_turrets_in_two_fields_only(self):
        r = json.loads(RESEARCH.read_text(encoding='utf-8'))
        s, chin = r['sounds']['maelstrom_main_gun'], r['chin']
        self.assertEqual((s['event'], s['midi'], s['fireMode']), ('E5CA1945', 1, 1))
        self.assertEqual((chin['event'], chin['midi']), ('8D4641BA', 0))
        a, c = bytes.fromhex(chin['blockBytes']), bytes.fromhex(s['blockBytes'])
        offsets, at = [], 0
        for offset, size in r['record']['blocks']:
            offsets += [offset + k for k in range(size)]
        self.assertEqual([offsets[k] for k in range(len(a)) if a[k] != c[k]], [0xED, 0x104, 0x105, 0x106, 0x107])
        self.assertEqual(s['writes'], [{'name': 'midi', 'offset': 0xED, 'size': 1, 'from': '00', 'to': '01'},
            {'name': 'event', 'offset': 0x104, 'size': 4, 'from': 'ba41468d', 'to': '4519cae5'}])
        self.assertEqual(s['instanceWrites'], [{'name': 'midi', 'offset': 0x38, 'size': 1, 'from': '00', 'to': '01'}])
        # The bank: an Event of content/audio/vehicle_storm_tank (five Play actions); listed by the Maelstrom's own
        # call-in package (requested) and its slot-3 weapon package (a strict subset), both catalogued.
        self.assertEqual(s['bank']['name'], 'content/audio/vehicle_storm_tank')
        self.assertEqual([a['type'] for a in s['bank']['event']['actions']], ['0403'] * 5)
        self.assertEqual(s['assetKey'], 'vehicle/TD-110 Maelstrom')
        self.assertEqual({p['package'] for p in s['packages']}, {'0x65EE777B72347CB4', '0x0971E953FCBDD346'})
        self.assertTrue(s['smallerIsSubset'])
        self.assertEqual([b['name'] for b in chin['banks']], ['content/audio/wep_autocannon', 'content/audio/vehicle_shuttle'])

    def test_the_domain_is_generated_from_it(self):
        import sys
        sys.path.insert(0, str(ROOT / 'scripts'))
        import generate_pelican
        self.assertEqual(generate_pelican.generate(check=True), [])
        d = generate_pelican.build()['sound']
        # r8: the allowlist is the weapon sound catalogue's (domains/weapon_sounds.lua); the Pelican domain keeps the
        # layout and the chin turret's own values only.
        self.assertNotIn('sounds', d)
        self.assertEqual(d['record']['blocks'], [[0xED, 1], [0xF0, 0x2C], [0x210, 0xC], [0x22C, 1]])
        self.assertEqual(d['instance']['midi'], 0x38)
        import generate_weapon_sounds
        catalogue = generate_weapon_sounds.build()
        self.assertEqual(catalogue['aliases'], {'maelstrom_main_gun': 'vehicle/maelstrom/main_gun'})
        s = catalogue['sounds']['vehicle/maelstrom/main_gun']
        self.assertEqual((s['event'], s['midi'], s['resource'], s['stratagem']),
            ('E5CA1945', 1, 'D58AE6A04EDB10DE', 'TD-110 Maelstrom'))
        self.assertEqual(s['writes'], json.loads(RESEARCH.read_text(encoding='utf-8'))['sounds']['maelstrom_main_gun']
            ['writes'])
        catalogue = (ROOT / 'domains/package_residency.lua').read_text(encoding='utf-8')
        self.assertIn('["vehicle/TD-110 Maelstrom"]={["label"]="TD-110 Maelstrom",["package"]="0x65EE777B72347CB4"',
            catalogue)

    def test_the_example_is_unchanged(self):
        # The proposed example change is reported, not made: PelicanCasExample asks for no sound.
        source = (ROOT / 'proof/PelicanCasExample/src/addon.lua').read_text(encoding='utf-8')
        self.assertNotIn('sound=', source)


class HostSoundTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + PELICANS + 'return (function()\n' + GATLING + WEAPON + SOUND + body
            + "\nreturn 'ok'\nend)()\n"), b'ok')

    def test_the_sound_on_its_own_copy_only(self):
        self.check(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
scene()
local inst=sound_instances()
local world=world_module.open()
local chin_before,mael_before=W.read(CHINREC,PWT.stride),W.read(MAELREC,PWT.stride)
local inst_before=W.read(inst,PWS.instanceStride)
-- Read-only, before: its type's own (the autocannon's) sound; quiet.
local st=weapon.sound_state(world,8102,GD.chinTurretResource)
assert(st.from=='type'and st.name=='chin'and st.event=='8D4641BA'and st.midi==0 and st.instance.midi==0
    and st.instance.quiet,tostring(st and st.name))
local writes=#W.runtime.writes
local r,code,reason=in_update(function()return weapon.configure(world,9501,{projectile=148,rpm=600,
    sound='maelstrom_main_gun'},'test')end)
assert(r and r.verified,tostring(code)..' '..tostring(reason))
-- One transaction: projectile, current RPM, the copy's +0xED and +0x104, its instance +0x38.
assert(r.writes==5 and #W.runtime.writes==writes+5,'writes '..tostring(r.writes))
assert(r.sound.applied and r.verify.sound and r.verify.sound_shared and r.verify.shared
    and r.spec.sound=='vehicle/maelstrom/main_gun')
-- Its own copy: the chin turret's record but the projectile and the two sound fields.
local copy=W.read(PCOPIES,PWS.copyStride)
assert(differ(copy,chin_before)=='0,237,260,261,262,263',differ(copy,chin_before))
assert(copy:byte(0xED+1)==1 and b.u32(copy,0x104)==0xE5CA1945)
-- Its own instance record: +0x38 only.
assert(differ(W.read(inst,PWS.instanceStride),inst_before)=='56'and midi_of(inst)==1)
-- The chin turret's and the Maelstrom main gun's type records: unchanged, whole.
assert(W.read(CHINREC,PWT.stride)==chin_before and W.read(MAELREC,PWT.stride)==mael_before)
st=weapon.sound_state(world,8102,GD.chinTurretResource)
assert(st.from=='copy'and weapon.sound_matches(st,'vehicle/maelstrom/main_gun')and weapon.sound_matches(st,
    'maelstrom_main_gun')and st.event=='E5CA1945'and st.midi==1 and st.instance.midi==1)
assert(n('PELICAN WEAPON APPLIED (test): chin turret 8102: projectile 148, current RPM 600 (requested), sound '
    ..'vehicle/maelstrom/main_gun true (E5CA1945); 5 writes; verified true')==1,table.concat(logged,' | '))
-- Again on its own copy: already there, nothing written.
local w0=#W.runtime.writes
assert(select(2,in_update(function()return weapon.apply_sound(world,8102,'maelstrom_main_gun','test')end))=='ALREADY_APPLIED'
    and#W.runtime.writes==w0)
""")

    def test_no_sound_leaves_its_own(self):
        self.check(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
scene()
local inst=sound_instances()
local world=world_module.open()
local r=in_update(function()return weapon.configure(world,9501,{projectile=148,rpm=600},'test')end)
assert(r and r.verified and r.writes==2 and r.sound==nil)
local st=weapon.sound_state(world,8102,GD.chinTurretResource)
assert(st.from=='copy'and st.name=='chin'and st.event=='8D4641BA'and midi_of(inst)==0)
""")

    def test_refused_while_its_bank_is_not_resident(self):
        self.check(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
scene()
sound_instances()
local world=world_module.open()
GX.sound_absent=true
local writes=#W.runtime.writes
local r,code,reason=in_update(function()return weapon.configure(world,9501,{projectile=148,rpm=600,
    sound='maelstrom_main_gun'},'test')end)
assert(not r and code=='ASSET_UNAVAILABLE'and reason:find('content/audio/vehicle_storm_tank',1,true),tostring(code))
-- Nothing called, nothing written: no copy was made.
assert(#GX.calls==0 and#W.runtime.writes==writes)
assert(n('PELICAN WEAPON REFUSED (test): Pelican 9501: ASSET_UNAVAILABLE: the TD-110 Maelstrom main gun sound\'s bank')==1,
    table.concat(logged,' | '))
-- An unknown sound: refused before anything.
assert(select(2,in_update(function()return weapon.configure(world,9501,{rpm=600,sound='autocannon'},'test')end))=='INVALID')
-- The sound's code changed: refused (its pins are proven before a sound is written).
GX.sound_absent=false
local pin=SDX.pins[1]
W.write(W.GAME+pin.rva,'\204')
assert(select(2,in_update(function()return weapon.configure(world,9501,{rpm=600,sound='maelstrom_main_gun'},'test')end))
    =='UNSUPPORTED_BUILD'and#GX.calls==0)
""")

    def test_firing_waits_for_quiet_and_the_values_are_frozen(self):
        self.check(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
scene()
local inst=sound_instances()
local world=world_module.open()
-- Another mod (or a custom weapon) changed the Maelstrom gun's type record: never read for the configuration.
W.write(MAELREC+0x104,W.u32(0x12345678))
local mael_before=W.read(MAELREC,PWT.stride)
-- It is firing (its trigger held): the sound is not applied, the rest is.
W.write(inst+SDX.instance.trigger,'\1')
local r,code,reason=in_update(function()return weapon.configure(world,9501,{projectile=148,rpm=600,
    sound='maelstrom_main_gun'},'test')end)
assert(r and r.verified,tostring(code)..' '..tostring(reason))
assert(not r.sound.applied and r.sound.retry and r.writes==2 and r.sound.reason:find('firing',1,true))
assert(n('PELICAN WEAPON SOUND NOT APPLIED (test): chin turret 8102: it is firing')==1,table.concat(logged,' | '))
local w0=#W.runtime.writes
assert(select(2,in_update(function()return weapon.apply_sound(world,8102,'maelstrom_main_gun','test')end))=='NOT_QUIET'
    and#W.runtime.writes==w0)
-- Quiet again: applied on its own copy, the frozen event (not the changed record's), its type records unchanged.
W.write(inst+SDX.instance.trigger,'\0')
local s,scode,sreason=in_update(function()return weapon.apply_sound(world,8102,'maelstrom_main_gun','test')end)
assert(s and s.applied and s.verified and s.writes==3,tostring(scode)..' '..tostring(sreason))
assert(b.u32(W.read(PCOPIES+0x104,4),0)==0xE5CA1945 and midi_of(inst)==1 and W.read(MAELREC,PWT.stride)==mael_before)
assert(n('PELICAN WEAPON SOUND APPLIED (test): chin turret 8102: its own copy posts the TD-110 Maelstrom main gun\'s '
    ..'event E5CA1945 as MIDI notes (bank content/audio/vehicle_storm_tank, resident through')==1,table.concat(logged,' | '))
-- Never on a turret the Runtime did not configure, nor outside its update.
assert(select(2,in_update(function()return weapon.apply_sound(world,8103,'maelstrom_main_gun','test')end))=='NOT_CONFIGURED')
assert(select(2,weapon.apply_sound(world,8102,'maelstrom_main_gun','test'))=='NOT_GAME_THREAD')
""")


class MirrorSoundTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + PELICANS + 'return (function()\n' + GATLING + WEAPON + MIRROR
            + SOUND + body + "\nreturn 'ok'\nend)()\n"), b'ok')

    def test_a_client_applies_the_same_sound_on_its_own_copy(self):
        self.check(r"""
local world=client_copy()
local inst=sound_instances()
local chin_before,mael_before=W.read(CHINREC,PWT.stride),W.read(MAELREC,PWT.stride)
local entry,mag=entry_raw(),W.read(MGRECS,MG.stride)
local spec={pelican=9501,round='standard',gatling=true,rate_factor=2,spread=100,recoil='zero',sound='maelstrom_main_gun',
    client=true}
local r,code,reason=in_update(function()return weapon.mirror_configure(world,8102,spec,'mirror')end)
assert(r and r.verified,tostring(code)..' '..tostring(reason))
assert(r.sound.applied and r.verify.sound and r.verify.sound_shared)
local st=weapon.sound_state(world,8102,GD.chinTurretResource)
assert(st.from=='copy'and weapon.sound_matches(st,'vehicle/maelstrom/main_gun')and st.instance.midi==1)
-- Never what the network writes (its current RPM entry, rounds), never a type record.
assert(entry_raw()==entry and W.read(MGRECS,MG.stride)==mag)
assert(W.read(CHINREC,PWT.stride)==chin_before and W.read(MAELREC,PWT.stride)==mael_before)
assert(n('PELICAN WEAPON MIRROR APPLIED (mirror): chin turret 8102 (a network copy here): its own copy names projectile '
    ..'148, rate slot 3200, casing true, spread true, sound vehicle/maelstrom/main_gun true (E5CA1945)')==1,
    table.concat(logged,' | '))
""")

    def test_deferred_until_its_bank_is_resident_here(self):
        self.check(r"""
local world=client_copy()
local inst=sound_instances()
GX.sound_absent=true
local SGUN={behave_as='gatling_sentry',rate_multiplier=2,round='standard',spread=100,recoil=false,sound='maelstrom_main_gun'}
local m=custom_pelican.mirror({turret=8102,pelican=9501,network=701,gun=SGUN,label='m',client=true})
tick()
-- Configured at once (the round, the rate slot, the casing), the sound deferred; its package requested here.
assert(m.configured and m.configured.sound.deferred and not m.configured.sound.applied,table.concat(logged,' | '))
assert(n('PELICAN WEAPON MIRROR SOUND DEFERRED (m): chin turret 8102: ASSET_UNAVAILABLE')==1
    and n('sound vehicle/maelstrom/main_gun deferred')==1
    and n('assets for pelican-sound-vehicle/maelstrom/main_gun requested')==1,
    table.concat(logged,' | '))
assert(midi_of(inst)==0 and b.u32(W.read(PCOPIES+0x104,4),0)==0x8D4641BA)
tick()
assert(midi_of(inst)==0)
-- Resident now, but its trigger is held (the host fires): it waits.
GX.sound_absent=false
W.write(inst+SDX.instance.trigger,'\1')
tick();tick()
assert(midi_of(inst)==0)
-- Quiet: applied on this machine's own copy (tried every SOUND_RETRY s), once.
W.write(inst+SDX.instance.trigger,'\0')
tick();tick()
assert(midi_of(inst)==1 and b.u32(W.read(PCOPIES+0x104,4),0)==0xE5CA1945,table.concat(logged,' | '))
assert(n('REMOTE CUSTOM PELICAN: m: firing sound vehicle/maelstrom/main_gun on this machine\'s own copy (deferred until '
    ..'its bank was resident and the turret quiet); verified true')==1 and n('PELICAN WEAPON MIRROR SOUND APPLIED (m)')==1,
    table.concat(logged,' | '))
local w0=#W.runtime.writes
tick();tick()
assert(n('PELICAN WEAPON MIRROR SOUND APPLIED')==1 and m.describe():find(', sound maelstrom_main_gun',1,true))
""")

    def test_never_on_the_hosts_own_turret(self):
        self.check(r"""
local world=client_copy()
sound_instances()
assert(in_update(function()return weapon.mirror_configure(world,8102,SPEC,'mirror')end))
-- This machine created the turret after all (its world record's created-here bit): the mirror never writes the sound.
W.write(b.pointer(W.read(BHANDLES+8,8),0)+0x14,W.u32(1))
local w0=#W.runtime.writes
local s,code=in_update(function()return weapon.apply_sound(world,8102,'maelstrom_main_gun','mirror',{mirror=true})end)
assert(not s and code=='CREATED_HERE'and#W.runtime.writes==w0,tostring(code))
""")


class GunshipSoundTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + PELICANS + "\nlocal PROOF_ADDON=''\nlocal PROOF_RESOURCE="
            + lua_literal('mods/test/gunship') + '\n' + 'return (function()\n' + HARNESS + GATLING + WEAPON + AI
            + HEADING + PROOF + GUNSHIP + SOUND + body + "\nreturn 'ok'\nend)()\n"), b'ok')

    def test_the_gun_option(self):
        self.lua(r"""
local g=FROZEN
local with={};for k,v in pairs(g)do with[k]=v end;with.sound='maelstrom_main_gun'
assert(gunship.check_gun(with))
local ok,why=gunship.check_gun({sound='autocannon'})
assert(not ok and why:find('^gun%.sound must be a name of hd2%.sounds%.list%(%)')and why:find("'sentry/gatling'",1,true),
    tostring(why))
-- The chin turret's own sound: accepted, nothing to write (no sound).
local own=assert(gunship.check_gun({sound='pelican/chin_autocannon'}))
assert(own.sound==nil)
-- A raw Wwise id is never a name.
assert(not gunship.check_gun({sound='E5CA1945'}))
""")

    def test_the_gunship_requests_its_bank_and_arms_with_the_sound(self):
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
local gun={};for k,v in pairs(FROZEN)do gun[k]=v end;gun.sound='maelstrom_main_gun'
local events={}
local g=assert(gunship.arm(9501,{gun=gun,credit=true,label='pelican_close_air_support#1 Pelican 9501'},
    function(e)events[#events+1]=e end))
tick(16)
local armed
for _,e in ipairs(events)do if e.kind=='armed'then armed=e end end
assert(armed and armed.sound=='vehicle/maelstrom/main_gun'and armed.verified,table.concat(logged,' | '))
assert(n('assets for pelican-sound-vehicle/maelstrom/main_gun requested')==1,table.concat(logged,' | '))
assert(n('pelican gunship pelican_close_air_support#1 Pelican 9501: ARMED: chin turret 8102: projectile 275 (ap4), 3200 '
    ..'RPM, spread 100 mrad, aim recoil zero, magazine 2047, credit to the caller (the host), sound '
    ..'vehicle/maelstrom/main_gun;')==1,
    table.concat(logged,' | '))
assert(midi_of(inst)==1 and b.u32(W.read(PCOPIES+0x104,4),0)==0xE5CA1945)
""")

    def test_a_bank_still_loading_never_holds_up_the_gun(self):
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
GX.sound_absent=true
gunship.SOUND_WAIT=1
local gun={};for k,v in pairs(FROZEN)do gun[k]=v end;gun.sound='maelstrom_main_gun'
local events={}
local g=assert(gunship.arm(9501,{gun=gun,label='p'},function(e)events[#events+1]=e end))
tick(24)
-- Armed after SOUND_WAIT without the sound (the round, rate, casing and the rest unchanged); the sound follows.
local armed
for _,e in ipairs(events)do if e.kind=='armed'then armed=e end end
assert(armed and armed.verified and armed.sound==nil,table.concat(logged,' | '))
assert(n('pelican gunship p: the firing sound\'s package is still loading: the sound follows once it is resident')==1
    and n('credit native, sound vehicle/maelstrom/main_gun once its bank is resident;')==1,table.concat(logged,' | '))
assert(midi_of(inst)==0)
tick(4)
assert(midi_of(inst)==0 and n('SOUND REFUSED')==0,table.concat(logged,' | '))
-- Resident: applied on its own copy at the next step, once.
GX.sound_absent=false
tick(4)
assert(midi_of(inst)==1 and b.u32(W.read(PCOPIES+0x104,4),0)==0xE5CA1945,table.concat(logged,' | '))
assert(n('pelican gunship p: SOUND: chin turret 8102: vehicle/maelstrom/main_gun, verified true')==1,
    table.concat(logged,' | '))
tick(8)
assert(n('PELICAN WEAPON SOUND APPLIED')==1)
""")

    def test_a_bank_that_does_not_load_leaves_its_own_sound(self):
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
-- The Runtime cannot request the sound's package (no call-in package is known for its stratagem): the gate fails at
-- once.
local core_assets=require('hd2runtime/core/assets')
local dependencies=core_assets.dependencies_for_stratagem
core_assets.dependencies_for_stratagem=function(id,label)
    if id==MS.stratagemId then return nil end
    return dependencies(id,label)
end
local gun={};for k,v in pairs(FROZEN)do gun[k]=v end;gun.sound='maelstrom_main_gun'
local events={}
assert(gunship.arm(9501,{gun=gun,label='p'},function(e)events[#events+1]=e end))
tick(16)
local armed
for _,e in ipairs(events)do if e.kind=='armed'then armed=e end end
assert(armed and armed.sound==nil and armed.verified,table.concat(logged,' | '))
assert(n('pelican gunship p: the firing sound\'s package did not load (ASSET_UNAVAILABLE: no package is known for the '
    ..'TD-110 Maelstrom main gun sound): its own sound instead')==1 and n(', sound vehicle/maelstrom/main_gun NOT APPLIED: '
    ..'ASSET_UNAVAILABLE')==1,table.concat(logged,' | '))
assert(midi_of(inst)==0 and b.u32(W.read(PCOPIES+0x104,4),0)==0x8D4641BA)
""")


if __name__ == '__main__':
    unittest.main()
