"""The custom stratagem payload families (docs/custom-stratagem-api.md; docs/research/custom-payloads-F5FEE03DCFDB.md),
offline:
  * the research and its domain (the Eagle jet and its rockets, the EMS donor chain, Eagle rows and Eagle Rearm);
  * support deliveries of any reviewed support weapon or backpack (the rack's own items and count);
  * runtime/custom_weapons.lua: ONE exact associated sentry's own weapon configured (projectile, rate, spread, magazine),
    a vanilla Gatling Sentry beside it untouched, the shared type records unchanged;
  * runtime/custom_eagles.lua: a call's exact jet (first seen at its activation; ambiguity and no jet refused), its
    rockets converted, a vanilla jet's rockets and a reused entity id never touched; the slot's uses rearmed by the
    Runtime only without Eagle Rearm in the record;
  * the Eagle carrier mode of the discovery and the allocator (Eagles only, sentries only);
  * the orbital: explicit salvos and shell counts, each shell's own impact explosion, exact slots only."""
import json
import unittest

from support import ROOT, run
from test_stratagem_calldown_code import WORLD
from test_stratagem_slot_conversion import SLOT
from test_bombardment_payload import PAYLOAD
from test_pelicans import PELICANS
from test_pelican_gatling import GATLING
from test_pelican_weapon import WEAPON
from test_gas_eat import IMPACT

RESEARCH = json.loads((ROOT / 'research/custom-payloads-F5FEE03DCFDB.json').read_text(encoding='utf-8'))


class CustomPayloadResearchTests(unittest.TestCase):
    def test_the_research_and_its_domain(self):
        self.assertEqual((RESEARCH['writes'], RESEARCH['protectionChanges']), (0, 0))
        self.assertFalse(any(RESEARCH['pinnedBytesMismatchPerSnapshot'].values()))
        self.assertEqual(sum(len(rows) for rows in RESEARCH['proofs'].values()), 60 + 73 + 109)  # + the aim override (pelicanAim), behaviour 213 idle (pelicanIdle)
        # The 110mm's rockets come from the two pods mounted on its jet (live 2026-10-04: source a pod, owner the jet):
        # the jet's mount slots and the mount component's layout (each child at +0x48, six per mount).
        self.assertEqual(RESEARCH['eagles']['Eagle 110mm Rocket Pods']['mounts'], [
            {'slot': 0, 'resource': '0E8C2515261E0325', 'node': 'payload_right', 'weapon': True},
            {'slot': 1, 'resource': '486522867199D7F3', 'node': 'payload_left', 'weapon': True}])
        self.assertEqual((RESEARCH['mount']['global'], RESEARCH['mount']['children'], RESEARCH['mount']['stride']),
            (0x3326438, 0x48, 24))
        self.assertEqual([p['asm'] for p in RESEARCH['proofs']['eagleMount']][3:6], ['mov rax, qword ptr [rbp + 0x48]',
            'lea rdx, [r15 + rcx*2]', 'mov ecx, dword ptr [rax + rdx*4]'])
        # Who fires the rockets: the EagleComponent update strikes per ACTIVE entry [0, +0x20) with its own handle.
        self.assertEqual([p['asm'] for p in RESEARCH['proofs']['eagleUpdate']][2:6], ['cmp dword ptr [r14 + 0x20], r12d',
            'mov rax, qword ptr [r14 + 0x48]', 'mov r13, qword ptr [rax + rbx*8]', 'call 0x8a4410'])
        self.assertEqual(RESEARCH['eagleLayout']['active'], 0x20)
        # The explosion request queue: 0x98-byte requests from +0x28 (type +0xC, source +0x10, owner +0x14).
        q = RESEARCH['explosionQueue']
        self.assertEqual((q['global'], q['count'], q['entries'], q['stride'], q['type'], q['source'], q['owner']),
            (0x346D558, 0x20, 0x28, 0x98, 0xC, 0x10, 0x14))
        # The sentry donors: the MG-43 Sentry binds no rate-of-fire selector (its 630 / 900 slots are dormant); the
        # MG-206 does.
        sw = RESEARCH['sentryWeapons']
        self.assertEqual((sw['A/MG-43 Machine Gun Sentry']['rateSlots'], sw['A/MG-43 Machine Gun Sentry']['capacity'],
            sw['A/MG-43 Machine Gun Sentry']['inputs'], sw['A/MG-43 Machine Gun Sentry']['spread']),
            ([630.0, 630.0, 900.0], 175, [0, 0], [10.0, 10.0]))
        self.assertEqual((sw['MG-206 Heavy Machine Gun']['inputs'], sw['MG-206 Heavy Machine Gun']['spread']),
            ([0, 2], [5.0, 5.0]))
        self.assertEqual(RESEARCH['weaponFunction'], {'left': 184, 'right': 188, 'rateOfFire': 2})
        # A projectile weapon's own world record: the ProjectileWeapon manager's handles +0x68 (any weapon, AI or not).
        self.assertEqual(RESEARCH['weaponHandle']['handles'], 0x68)
        self.assertEqual(RESEARCH['proofs']['weaponHandle'][2]['asm'], 'mov rax, qword ptr [rdi + 0x68]')
        game = {pin['rva']: pin for rows in RESEARCH['proofs'].values() for pin in rows}
        # The jet's strike: its handle, its EagleComponentData's projectile, the jet's entity as every rocket's source.
        self.assertEqual(game[0x8A4591]['asm'], 'mov eax, dword ptr [r14 + 0x18]')
        self.assertEqual(game[0x8A5748]['asm'], 'mov dword ptr [rbp + 0x88], ecx')
        self.assertEqual(game[0x8A57EB]['asm'], 'call 0x13a9830')
        self.assertEqual(game[0x6AC007]['asm'], 'cmp dword ptr [r14 + 0x3c], r15d')
        layout = RESEARCH['eagleLayout']
        self.assertEqual((layout['global'], layout['count'], layout['handles'], layout['records'], layout['stride']),
            (0x3326650, 0x1C, 0x48, 0x58, 0xFC))
        pods = RESEARCH['eagles']['Eagle 110mm Rocket Pods']
        self.assertEqual((pods['type'], pods['uses'], pods['strikeProjectile'], pods['rocket'], pods['payload']),
            (140, 3, 82, {'impact': 229, 'expiry': 0}, '0x397792815583DA29'))
        for name, e in RESEARCH['eagles'].items():
            self.assertEqual((e['deliveryKind'], e['linkedType']), (0, 49), name)
        self.assertEqual(RESEARCH['eagleRearm'], {'type': 49, 'stableId': 3837064536, 'cooldown': 150.0})
        ems = RESEARCH['explosionDonors']['Orbital EMS Strike']
        self.assertEqual((ems['shell'], ems['explosion'], ems['links']), (74, 188, {'damage': 451, 'template': 15,
            'seconds': 15.0, 'statuses': [38]}))
        self.assertEqual([(r['kind'], r['id'], r['masked']) for r in ems['rows']], [('explosion', 188, [40, 44]),
            ('damage', 451, []), ('template', 15, []), ('status', 38, [8, 12])])
        self.assertEqual(len(RESEARCH['observations']), 7)
        import sys
        sys.path.insert(0, str(ROOT / 'scripts'))
        import generate_custom_payloads
        self.assertEqual(generate_custom_payloads.generate(check=True), [])
        self.assertIn("'generate_custom_payloads'", (ROOT / 'scripts/regenerate_domains.py').read_text(encoding='utf-8'))

    def test_the_rack_deliveries(self):
        self.assertEqual(run(WORLD + r'''
local custom=require('hd2runtime/runtime/custom_stratagems')
local eat=assert(custom.support_delivery('EAT-17 Expendable Anti-Tank'))
assert(eat.count==2 and eat.items['80932FA0ED6901D3'].kind=='weapon'and eat.items['80932FA0ED6901D3'].projectile==132)
local ac=assert(custom.support_delivery('AC-8 Autocannon'))
assert(ac.count==2 and ac.items['A8CFFB316F0B5C5F'].kind=='weapon'and ac.items['E60AE045E0090F4C'].kind=='backpack')
local mg=assert(custom.support_delivery('MG-43 Machine Gun'))
assert(mg.count==1 and mg.items['11C27D3BABB38956'].kind=='weapon'and mg.items['11C27D3BABB38956'].projectile==148)
local pack=assert(custom.support_delivery('B-1 Supply Pack'))
assert(pack.count==1 and pack.items['4EF9A47109239A58'].kind=='backpack'and pack.family=='backpack')
assert(select(2,custom.support_delivery('Orbital Gas Strike')):find('is not a support weapon or backpack',1,true))
assert(select(2,custom.support_delivery('No Such Thing')):find('is not a catalogued stratagem',1,true))
-- The older form still names the EAT-17's launcher, its round and its stable id.
assert(custom.DELIVERIES['EAT-17 Expendable Anti-Tank'].item=='80932FA0ED6901D3'
    and custom.DELIVERIES['EAT-17 Expendable Anti-Tank'].projectile==132)
return 'ok'
'''), b'ok')


SENTRY = r"""
local weapons=require('hd2runtime/runtime/custom_weapons');weapons.reset_for_tests()
for _,pin in ipairs(require('hd2runtime/domains/custom_payloads').pins)do W.write(W.GAME+pin.rva,b.unhex(pin.hex))end
local instances=require('hd2runtime/runtime/spawned_instances');instances.reset_for_tests()
-- The A/MG-43 Machine Gun Sentry's own types (research custom-payloads "sentryWeapons"), index 2 in each type table:
-- ProjectileWeapon 148 at 630 / 630 / 900, magazine pattern 148 x4, 242 (175 rounds), WeaponData spread 10 and no
-- weapon-function input (+184 / +188).
local MGS={key=b.unhex('37CDE43876BA26BB'):reverse(),hex='37CDE43876BA26BB'}
function MGS.add(t,bytes)
    local tab=b.pointer(W.read(CW+t.offset,8),0)
    local lo,hi=b.u32(MGS.key,0),b.u32(MGS.key,4)
    local slot=((hi%t.slots)*(4294967296%t.slots)+lo%t.slots)%t.slots
    while W.read(tab+slot*16,8)~=string.rep('\0',8)do slot=(slot+1)%t.slots end
    W.write(tab+slot*16,MGS.key..W.u32(2)..W.u32(0))
    W.write(tab+t.records+2*t.stride,bytes..string.rep('\0',t.stride-#bytes))
    return tab+t.records+2*t.stride
end
MGS.pw=MGS.add(GD.pwTypes,W.u32(148)..f32(630)..f32(630)..f32(900))
MGS.mag=MGS.add(GD.magazineTypes,magrec(W.u32(1)..W.u32(148)..W.u32(148)..W.u32(148)..W.u32(148)..W.u32(242),
    {capacity=175,spareMagazines=0,perResupply=6,maxSpareMagazines=0,chamber=1}))
MGS.wd=MGS.add(AIMD.weaponData.types,wdrec({blockA={20,2,90,90,0,0.1,1},blockB={0,0,90,90,0,0.1,1},spread={10,10}}))
-- An MG-43 Machine Gun Sentry entity, as deployed: weapon index wi, 630 RPM (its type's x the game's factor), its tracer
-- pattern, 174 rounds and one chambered, its type's spread and recoil, its world record the host's.
function MGS.sentry(wi,id,factor)
    weapon_entity(id,wi,{resource=MGS.key,rpm=630*(factor or 1),pattern=true,chambered=148})
    W.write(PROF+wi*PW.rofStride+PW.rofSlots,f32(630)..f32(630)..f32(900)..W.u32(1))
    W.write(MGRECS+wi*MG.stride,W.u32(174));W.write(MGENTS+wi*AMD.entryStride+AMD.entryRounds,W.u32(174))
    W.write(WDRECS+wi*AIMD.weaponData.stride+AIMD.weaponData.recoilB,f32(0)..f32(0)..f32(90)..f32(90)..f32(0)
        ..f32(0.1)..f32(1))
    W.write(b.pointer(W.read(PHANDLES+wi*8,8),0),MGS.key..W.u32(id)..W.u32(0)..W.u32(800+wi)..W.u32(1))
end
-- The game's copy routines, per type: each entity gets a copy of ITS OWN type's record in the next free copy slot.
local function type_index(key)return key==CHIN and 0 or key==MGS.key and 2 or 1 end
W.runtime.native_weapon_copy=function(entry,manager_,handle)
    GX.calls[#GX.calls+1]={'copy',entry,manager_,handle}
    local raw=W.read(handle,12)
    local n=b.u32(W.read(PCOMP+PW.copyCount,4),0)
    ckey(b.u32(raw,8),n)
    W.write(PCOPIES+n*PW.copyStride,W.read(PWTAB+GD.pwTypes.records+type_index(raw:sub(1,8))*GD.pwTypes.stride,
        PW.copyStride))
    W.write(PCOMP+PW.copyCount,W.u32(n+1))
    return true
end
W.runtime.native_magazine_copy=function(entry,manager_,handle)
    GX.calls[#GX.calls+1]={'magazine_copy',entry,manager_,handle}
    local raw=W.read(handle,12)
    local n=b.u32(W.read(MGCOMP+MC.count,4),0)
    mckey(b.u32(raw,8),n)
    W.write(MGCOPIES+n*MC.stride,W.read(MAGTAB+GD.magazineTypes.records+type_index(raw:sub(1,8))
        *GD.magazineTypes.stride,MC.stride))
    W.write(MGCOMP+MC.count,W.u32(n+1))
    return true
end
-- A Gatling Sentry entity (behaviour 213): its world record (the host's), its weapon at weapon index wi, as deployed.
local function sentry(i,wi,id)
    transport(i,id,{resource=GAT,behaviour=213});stage(i,1,0)
    W.write(b.pointer(W.read(BHANDLES+i*8,8),0),GAT..W.u32(id)..W.u32(0x400300+i)..W.u32(900+i)..W.u32(1))
    weapon_entity(id,wi,{resource=GAT,rpm=1600,pattern=true,chambered=148,windUp=true})
    -- Its world record as the ProjectileWeapon manager holds it (+0x68): resource, entity, network id, flags (the host's).
    W.write(b.pointer(W.read(PHANDLES+wi*8,8),0),GAT..W.u32(id)..W.u32(0)..W.u32(900+i)..W.u32(1))
end
local CALL={definition='hmg_sentry',call_id='hmg_sentry#1',n=1,player='p'}
local function types()
    return W.read(PWTAB+GD.pwTypes.records,3*GD.pwTypes.stride)..W.read(MAGTAB+GD.magazineTypes.records,
        3*GD.magazineTypes.stride)..W.read(MGS.wd,AIMD.weaponData.types.stride)
end
"""


class SentryWeaponTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + PELICANS + 'return (function()\n' + GATLING + WEAPON + SENTRY
            + body + '\nend)()\n'), b'ok')

    def test_only_the_calls_sentry_takes_the_heavy_machine_gun(self):
        self.check(r"""
pworld()
BOMB.set_clock(T0)
local world=world_module.open()
sentry(5,1,9801)          -- the HMG Sentry call's own sentry
sentry(6,2,9802)          -- a vanilla A/G-16 Gatling Sentry called in the same mission
assert(instances.associate(9801,CALL,'sentry'))
local shared=types()
local SPEC={projectile=275,rpm=600,spread=6,ammo=300}
-- The vanilla sentry is never configured: it belongs to no custom stratagem call.
local r,code=in_update(function()return weapons.configure(world,9802,SPEC,'test')end)
assert(r==nil and code=='NOT_ASSOCIATED','a vanilla sentry was configured: '..tostring(code))
assert(#GX.calls==0)
local writes=#W.runtime.writes
r,code,reason=in_update(function()return weapons.configure(world,9801,SPEC,'test')end)
assert(r and r.verified,tostring(code)..' '..tostring(reason))
for _,k in ipairs({'projectile','magazine','rpm','spread','ammo','shared'})do assert(r.verify[k]==true,k)end
-- One copy of each routine, for 9801's own world record (the one its ProjectileWeapon manager names, +0x68).
assert(#GX.calls==2 and GX.calls[1][1]=='copy'and GX.calls[2][1]=='magazine_copy')
assert(GX.calls[1][4]==b.pointer(W.read(PHANDLES+1*8,8),0)and GX.calls[2][4]==GX.calls[1][4])
-- 9801: its own ProjectileWeapon (275), current RPM 600, its own magazine (no pattern; 275 chambered; 300 rounds).
local w=pelicans.weapon_config(world,9801)
assert(w.copy and w.copy.projectileType==275 and w.currentRpm==600)
assert(not w.magazine.pattern and w.magazine.chambered==275 and w.magazine.length==0 and w.magazine.copy)
local s=weapons.state(world,9801)
assert(s.magazine.capacity==300 and s.magazine.rounds==299 and s.magazine.working==299 and s.magazine.from=='copy')
assert(s.spread.x==6 and s.spread.y==6 and s.spread.word==0)
-- 9802, the vanilla Gatling Sentry: exactly as deployed.
local v=pelicans.weapon_config(world,9802)
assert(not v.copy and v.currentRpm==1600 and v.magazine.pattern and v.magazine.chambered==148 and not v.magazine.copy)
local vs=weapons.state(world,9802)
assert(vs.magazine.capacity==500 and vs.magazine.rounds==499 and vs.spread.x==10 and vs.magazine.from=='type')
-- The shared type records (ProjectileWeapon and magazine of both types) never written.
assert(types()==shared,'a shared type record changed')
assert(count('custom weapon CONFIGURED (test): entity 9801 (EF85D6CF58E31D70): projectile 275, rpm 600, spread 6, ammo '
    ..'300')==1,table.concat(logged,' | '))
-- Refusals, nothing written: twice the magazine; the spread again; outside the update; invalid values.
local n=#W.runtime.writes
assert(select(2,in_update(function()return weapons.configure(world,9801,{ammo=200},'test')end))=='ALREADY_CONFIGURED')
assert(select(2,in_update(function()return weapons.configure(world,9801,{spread=4},'test')end))=='SPREAD_UNEXPECTED')
assert(select(2,weapons.configure(world,9801,{rpm=500},'test'))=='NOT_GAME_THREAD')
assert(select(2,in_update(function()return weapons.configure(world,9801,{rpm=5},'test')end))=='INVALID')
assert(select(2,in_update(function()return weapons.configure(world,9801,{ammo=5000},'test')end))=='INVALID')
assert(#W.runtime.writes==n)
return 'ok'
""")

    def test_the_hmg_sentry_on_the_mg43_chassis_at_400_rpm(self):
        # HmgSentryExample 0.2.0: the call's own MG-43 Machine Gun Sentry takes the MG-206's round 275, 400 RPM, 5 mrad
        # and 300 rounds on its own records. A vanilla MG-43 Sentry and a vanilla Gatling Sentry beside it, the MG-43
        # Sentry's, the Gatling's and the MG-206's shared records: untouched.
        self.check(r"""
pworld()
BOMB.set_clock(T0)
local world=world_module.open()
MGS.sentry(1,9801)        -- the HMG Sentry call's own MG-43 Sentry
MGS.sentry(2,9803)        -- a vanilla MG-43 Machine Gun Sentry
sentry(6,3,9802)          -- a vanilla A/G-16 Gatling Sentry
assert(instances.associate(9801,CALL,'sentry'))
local shared,row275,row148=types(),W.read(ROW275,272),W.read(ROW148,272)
local r,code,reason=in_update(function()return weapons.configure(world,9801,{projectile=275,rpm=400,spread=5,ammo=300},
    'test')end)
assert(r and r.verified,tostring(code)..' '..tostring(reason))
for _,k in ipairs({'projectile','magazine','rpm','spread','ammo','shared'})do assert(r.verify[k]==true,k)end
-- 9801: its own ProjectileWeapon (275; its Y slot 400, its dormant X and Z kept), current RPM 400, its own magazine.
local w=pelicans.weapon_config(world,9801)
assert(w.copy and w.copy.projectileType==275 and w.currentRpm==400)
assert(w.copy.rpm.x==630 and w.copy.rpm.y==400 and w.copy.rpm.z==900,tostring(w.copy.rpm.y))
local s=weapons.state(world,9801)
assert(s.magazine.capacity==300 and s.magazine.rounds==299 and s.magazine.chambered==275 and s.magazine.pattern==0)
assert(s.spread.x==5 and s.spread.y==5)
-- The vanilla MG-43 Sentry: exactly as deployed.
local v=pelicans.weapon_config(world,9803)
local vs=weapons.state(world,9803)
assert(not v.copy and v.currentRpm==630 and v.magazine.pattern and v.magazine.chambered==148 and not v.magazine.copy)
assert(vs.magazine.capacity==175 and vs.magazine.rounds==174 and vs.spread.x==10 and vs.magazine.from=='type')
-- The vanilla Gatling Sentry: exactly as deployed.
local g=pelicans.weapon_config(world,9802)
assert(not g.copy and g.currentRpm==1600 and g.magazine.chambered==148)
-- No shared record: the MG-43 Sentry's, the Gatling's and the chin turret's types; the MG-206's round 275 and 148.
assert(types()==shared and W.read(ROW275,272)==row275 and W.read(ROW148,272)==row148,'a shared record changed')
assert(count('custom weapon CONFIGURED (test): entity 9801 (37CDE43876BA26BB): projectile 275, rpm 400, spread 5, '
    ..'ammo 300')==1,table.concat(logged,' | '))
-- Under the mission rate factor (0.9): 567 -> 360, its slot 400.
MGS.sentry(4,9804,0.9)
assert(instances.associate(9804,CALL,'sentry'))
r=assert(in_update(function()return weapons.configure(world,9804,{rpm=400},'test')end))
w=pelicans.weapon_config(world,9804)
assert(math.abs(w.currentRpm-360)<0.01 and w.copy.rpm.y==400,tostring(w.currentRpm))
-- A type that binds the rate-of-fire selector (as the MG-206 does, +188 = 2): refused, nothing written.
W.write(MGS.wd+188,W.u32(2))
MGS.sentry(5,9805)
assert(instances.associate(9805,CALL,'sentry'))
local n=#W.runtime.writes
assert(select(2,in_update(function()return weapons.configure(world,9805,{rpm=400},'test')end))=='RPM_SELECTOR')
assert(#W.runtime.writes==n)
return 'ok'
""")

    def test_the_hmg_sentry_fires_the_mg206_sound_from_its_own_copy(self):
        # sentry.weapon.sound (2026-10-07, HeavyMgSentry 0.3.2): the call's own MG-43 Sentry's own weapon copy fires
        # the MG-206's per-shot MIDI sound instead of the MG-43 Sentry's loop; the vanilla MG-43 Sentry beside it keeps
        # its loop; no shared record changes; each refusal writes nothing.
        self.check(r"""
pworld()
BOMB.set_clock(T0)
local world=world_module.open()
local WSD=require('hd2runtime/domains/weapon_sounds')
local SDX=require('hd2runtime/domains/pelican').sound
for _,pin in ipairs(WSD.pins)do W.write(W.GAME+pin.rva,b.unhex(pin.hex))end
local function put_sound(at,hex)
    local raw,cursor=b.unhex(hex),0
    for _,blk in ipairs(SDX.record.blocks)do W.write(at+blk[1],raw:sub(cursor+1,cursor+blk[2]));cursor=cursor+blk[2]end
end
local BASE,HMG=WSD.sounds['sentry/machine_gun'],WSD.sounds['support/mg206']
put_sound(MGS.pw,BASE.blockBytes)
-- The HMG bank's packages: resident unless listed absent.
local previous=W.runtime.package_state
local absent={}
W.runtime.package_state=function(hex)
    if absent[hex]then return'absent'end
    for _,pk in ipairs(HMG.packages)do if hex==pk.package then return'resident'end end
    return previous(hex)
end
MGS.sentry(1,9801)        -- the HMG Sentry call's own MG-43 Sentry
MGS.sentry(2,9803)        -- a vanilla MG-43 Machine Gun Sentry
MGS.sentry(3,9804)        -- another call's sentry, for the refusals
-- The weapons' instance records in a page-backed allocation (the game's heap is).
local inst=W.alloc(0x1000);W.write(inst,W.read(PINST,0x800));W.write(PCOMP+PW.instances,W.u64(inst))
assert(instances.associate(9801,CALL,'sentry'))
assert(instances.associate(9804,CALL,'sentry'))
local shared=types()
local pwm=require('hd2runtime/runtime/pelican_weapon')
local r,code,reason=in_update(function()return weapons.configure(world,9801,{projectile=275,rpm=400,spread=5,ammo=300,
    sound='support/mg206'},'test')end)
local function vtext(x)local o={};for k,v in pairs(x and x.verify or{})do o[#o+1]=k..'='..tostring(v)end;return table.concat(o,',')end
assert(r and r.verified and r.verify.sound==true,tostring(code)..' '..tostring(reason)..' '..vtext(r)..' | '..table.concat(logged,' | '))
-- Its own copy: the MG-206's per-shot event as MIDI notes, no loop; its instance's MIDI source 1.
local st=pwm.sound_state(world,9801,MGS.hex)
assert(st.from=='copy'and st.block==b.unhex(HMG.blockBytes)and st.instance.midi==1)
assert(st.event==HMG.event and st.loop_start=='00000000'and st.loop_stop=='00000000',st.event)
-- The vanilla MG-43 Sentry keeps its own loop; no shared record changed.
local v=pwm.sound_state(world,9803,MGS.hex)
assert(v.from=='type'and v.block==b.unhex(BASE.blockBytes)and v.instance.midi==0)
assert(types()==shared,'a shared record changed')
assert(count('its firing sound sentry/machine_gun -> support/mg206 (event 825E6711 as MIDI notes; bank '
    ..'content/audio/wep_heavy_machinegun')==1,table.concat(logged,' | '))
-- Refusals, nothing written: its bank not resident; an unknown sound; firing.
local n=#W.runtime.writes
for _,pk in ipairs(HMG.packages)do absent[pk.package]=true end
assert(select(2,in_update(function()return weapons.configure(world,9804,{sound='support/mg206'},'t')end))
    =='ASSET_UNAVAILABLE')
absent={}
assert(select(2,in_update(function()return weapons.configure(world,9804,{sound='no/such_sound'},'t')end))=='INVALID')
W.write(inst+3*PW.instanceStride+SDX.instance.trigger,'\1')
assert(select(2,in_update(function()return weapons.configure(world,9804,{sound='support/mg206'},'t')end))=='NOT_QUIET')
W.write(inst+3*PW.instanceStride+SDX.instance.trigger,'\0')
assert(#W.runtime.writes==n,'a refusal writes nothing')
-- Quiet again: applied.
assert(in_update(function()return weapons.configure(world,9804,{sound='support/mg206'},'t')end).verify.sound==true)
return 'ok'
""")

    def test_with_several_players_the_creator_configures_and_every_other_machine_mirrors(self):
        # The roles of runtime/custom_weapons.lua configure (2026-10-06, the user's request that every example work with
        # several players; NOT live-tested). A client's own call's sentry, created on that client: configured whole
        # (role client, inside the client-write proof). Another machine's published sentry (its world record not created
        # here): its round (its own ProjectileWeapon copy, its own magazine copy with the pattern off and the chambered
        # round), its spread and recoil only; never its rate or ammunition, which the game replicates from its creator.
        self.check(r"""
local mpx=require('hd2runtime/runtime/multiplayer');mpx.reset_for_tests()
pworld(nil,{client=true})
BOMB.set_clock(T0)
local world=world_module.open()
local function not_created_here(wi)W.write(b.pointer(W.read(PHANDLES+wi*8,8),0)+20,W.u32(0))end
MGS.sentry(1,9801)            -- this client's own call's sentry, created here
MGS.sentry(2,9803)            -- another player's custom sentry: created on its machine
not_created_here(2)
assert(instances.associate(9801,CALL,'sentry'))
local shared=types()
local SPEC={projectile=275,rpm=400,spread=5,ammo=300}
local function cfg(entity,spec,opts)return in_update(function()return weapons.configure(world,entity,spec,'t',opts)end)end
-- A client: as the host's own call, or its own call without the client-write proof: refused, nothing written.
local n=#W.runtime.writes
assert(select(2,cfg(9801,SPEC))=='NOT_HOST')
assert(select(2,cfg(9801,SPEC,{role='client'}))=='NOT_HOST')
assert(#W.runtime.writes==n and#GX.calls==0)
-- Inside the proof: its own sentry, created here, configured whole.
mpx.enable_client_proof(true)
local r,code,reason=cfg(9801,SPEC,{role='client'})
assert(r and r.verified and not r.mirror,tostring(code)..' '..tostring(reason))
for _,k in ipairs({'projectile','magazine','rpm','spread','ammo','shared'})do assert(r.verify[k]==true,k)end
-- The published sentry: only as a published call item; then a MIRROR of its round, spread and recoil.
assert(select(2,cfg(9803,SPEC,{role='published'}))=='NOT_PUBLISHED')
local before=pelicans.weapon_config(world,9803)
local m
m,code,reason=cfg(9803,SPEC,{role='published',published=true})
assert(m and m.mirror and m.verified,tostring(code)..' '..tostring(reason))
assert(m.spec.projectile==275 and m.spec.spread==5 and m.spec.rpm==nil and m.spec.ammo==nil)
local w=pelicans.weapon_config(world,9803)
assert(w.copy and w.copy.projectileType==275 and w.currentRpm==before.currentRpm and w.currentRpm==630)
assert(not w.magazine.pattern and w.magazine.chambered==275 and w.magazine.copy)
local s=weapons.state(world,9803)
assert(s.magazine.capacity==175 and s.magazine.rounds==174 and s.magazine.working==174 and s.spread.x==5)
assert(count('MIRRORED (another machine created it: the round, spread and recoil on this machine\'s own copy) (t): '
    ..'entity 9803')==1,table.concat(logged,' | '))
-- A published sentry created HERE (the creator's machine): configured whole.
MGS.sentry(3,9804)
local c=cfg(9804,SPEC,{role='published',published=true})
assert(c and not c.mirror and c.verify.rpm and c.verify.ammo)
-- Another machine's sentry with nothing this machine mirrors (its rate and ammunition only): refused.
MGS.sentry(4,9805)
not_created_here(4)
assert(select(2,cfg(9805,{rpm=400,ammo=300},{role='published',published=true}))=='NOT_CREATED_HERE')
assert(types()==shared,'a shared type record changed')
mpx.reset_for_tests()
return 'ok'
""")

    def test_a_pelican_after_a_modified_custom_sentry_gets_exactly_its_frozen_gun(self):
        # The live regression (2026-10-04): the custom HMG Sentry (the Gatling's type, its own 540 RPM and round 275) was
        # deployed and configured; a Pelican called after it was refused (RATE_UNEXPECTED). Now the Pelican's chin gun gets
        # its frozen configuration, and the custom sentry and every shared record stay as they are.
        self.check(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
scene()
local world=world_module.open()
sentry(5,1,9801)
W.write(PCUR+1*PW.currentStride+PW.currentRpm,f32(1440))      -- made under the mission rate factor
assert(instances.associate(9801,CALL,'sentry'))
assert(in_update(function()return weapons.configure(world,9801,{projectile=275,rpm=600,spread=6,ammo=300},'test')end))
local sentry_after=pelicans.weapon_config(world,9801)
assert(math.abs(sentry_after.currentRpm-540)<0.01 and sentry_after.copy.projectileType==275)
local shared=types()
local weapon=require('hd2runtime/runtime/pelican_weapon')
local r,code,reason=in_update(function()return weapon.configure(world,9501,{projectile=275,rpm='gatling',rate_factor=2,
    casing=true,recoil='zero',spread=100},'pelican')end)
assert(r and r.verified,tostring(code)..' '..tostring(reason))
assert(r.spec.rpm==3200 and r.rpm_source:find('frozen Gatling rate 1600',1,true))
local chin=pelicans.weapon_config(world,8102)
assert(chin.copy.projectileType==275 and chin.currentRpm==3200 and chin.copy.rpm.y==3200)
-- The custom sentry: still its own 540 and 275; the shared records: unchanged.
local again=pelicans.weapon_config(world,9801)
assert(again.currentRpm==sentry_after.currentRpm and again.copy.projectileType==275)
assert(types()==shared)
assert(count('RATE_UNEXPECTED')==0 and count('deployed Gatling')==0)
return 'ok'
""")

    def test_the_rate_follows_the_games_factor_and_a_gone_or_unknown_entity_is_refused(self):
        self.check(r"""
pworld()
BOMB.set_clock(T0)
local world=world_module.open()
sentry(5,1,9801)
assert(instances.associate(9801,CALL,'sentry'))
-- A rate the game does not give (not its type's x 1 or 0.9): refused.
W.write(PCUR+1*PW.currentStride+PW.currentRpm,f32(1234))
assert(select(2,in_update(function()return weapons.configure(world,9801,{rpm=600},'test')end))=='RATE_UNEXPECTED')
-- Under the mission rate modifier (0.9): the game's factor is kept, the copy's slot takes the requested rate.
W.write(PCUR+1*PW.currentStride+PW.currentRpm,f32(1440))
local r=assert(in_update(function()return weapons.configure(world,9801,{rpm=600},'test')end))
local w=pelicans.weapon_config(world,9801)
assert(math.abs(w.currentRpm-540)<0.01 and math.abs(w.copy.rpm.y-600)<0.01,tostring(w.currentRpm))
-- An entity that is no projectile weapon, an id with no association.
assert(select(2,in_update(function()return weapons.configure(world,4242,{rpm=600},'test')end))=='NOT_ASSOCIATED')
return 'ok'
""")


EAGLE = r"""
local eagles=require('hd2runtime/runtime/custom_eagles');eagles.reset_for_tests()
local CP=require('hd2runtime/domains/custom_payloads')
for _,pin in ipairs(CP.pins)do W.write(W.GAME+pin.rva,b.unhex(pin.hex))end
local E=CP.eagle
local EMGR=W.alloc(0x100);W.write(W.GAME+E.global,W.u64(EMGR))
local EHANDLES=W.alloc(0x200);W.write(EMGR+E.handles,W.u64(EHANDLES))
local JET='397792815583DA29'                       -- the Eagle 110mm Rocket Pods' jet
-- The Eagle manager's jets now: {{entity, network, resource}}.
local function jets(list)
    for k,j in ipairs(list)do
        local h=W.alloc(0x18)
        W.write(h,b.unhex(j.resource or JET):reverse()..W.u32(j.entity)..W.u32(0)..W.u32(j.network))
        W.write(EHANDLES+(k-1)*8,W.u64(h))
        W.register_entity(j.entity,j.resource or JET)
        if not j.keep then W.add{entity=j.entity,type=j.resource or JET,unit=0,health=1}end
    end
    W.write(EMGR+E.count,W.u32(#list));W.write(EMGR+E.active,W.u32(#list))
end
-- The mount component (research "eagleMount"): each jet's mounted children, six per mount at +0x48. jet(entity, network,
-- pods) also registers the jet's two pods (0x0E8C2515261E0325 at payload_right, slot 0; 0x486522867199D7F3 at
-- payload_left, slot 1) in its mount record.
local MT=CP.mount
local RIGHT,LEFT='0E8C2515261E0325','486522867199D7F3'
local MCOMP=W.alloc(0x100);W.write(W.GAME+MT.global,W.u64(MCOMP))
local MKEYS=W.alloc(64*8)
for k=0,63 do W.write(MKEYS+k*8,W.u32(4294967295)..W.u32(0))end
W.write(MCOMP+MT.map,W.u64(MKEYS));W.write(MCOMP+MT.map+8,W.u32(64)..W.u32(4294967295)..W.u32(1))
local MCHILD=W.alloc(0x400);W.write(MCOMP+MT.children,W.u64(MCHILD))
local mounts_n=0
local function mount(entity,children)
    local slot=entity%64
    while b.u32(W.read(MKEYS+slot*8,4),0)~=4294967295 do slot=(slot+1)%64 end
    W.write(MKEYS+slot*8,W.u32(entity)..W.u32(mounts_n))
    local raw=''
    for k=0,5 do raw=raw..W.u32(children[k]or 0)end
    W.write(MCHILD+mounts_n*MT.stride,raw)
    mounts_n=mounts_n+1
end
local function pods(right,left)
    for _,p in ipairs({{right,RIGHT},{left,LEFT}})do
        W.register_entity(p[1],p[2]);W.add{entity=p[1],type=p[2],unit=0,health=1}
    end
end
-- The game's explosion request queue (research "explosionQueue"): requests {type, source, owner, x, y, z}.
local Q=CP.explosionQueue
local EQUEUE=W.alloc(Q.entries+8*Q.stride);W.write(W.GAME+Q.global,W.u64(EQUEUE))
local function requests(list)
    for k,r in ipairs(list)do
        W.write(EQUEUE+Q.entries+(k-1)*Q.stride,W.f32(r.x or 1)..W.f32(r.y or 2)..W.f32(r.z or 3)..W.u32(r.type)
            ..W.u32(r.source)..W.u32(r.owner or 100)..W.u64(0))
    end
    W.write(EQUEUE+Q.count,W.u32(#list))
end
-- The 110mm rocket row (projectile 82: impact explosion 229, no expiry) and the EMS donor's chain exactly as reviewed.
local rocket82=W.projectile_row(82,W.u32(82)..string.rep('\0',0x8C)..W.u32(229)..string.rep('\0',8)..W.u32(0)
    ..string.rep('\0',0x110-0xA0))
local ROCKET82=W.read(rocket82,0x110)
local function ems_chain()
    local out={}
    for _,item in ipairs(CP.explosionDonors['Orbital EMS Strike'].rows)do
        out[#out+1]=W.read(b.pointer(W.read(W.GAME+tonumber(item.table:sub(3),16)+item.id*8,8),0),item.stride)
    end
    return table.concat(out)
end
for _,item in ipairs(CP.explosionDonors['Orbital EMS Strike'].rows)do
    local at=W.alloc(item.stride);W.write(at,b.unhex(item.reviewed))
    W.write(W.GAME+tonumber(item.table:sub(3),16)+item.id*8,W.u64(at))
end
local US=1e6
"""


def eagle_lua(body):
    return run(WORLD + SLOT + PAYLOAD + IMPACT + EAGLE + body)


class EagleTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(eagle_lua(body), b'ok')

    def test_the_calls_rockets_through_its_jets_mounted_pods_and_owner(self):
        # Live 2026-10-04: the 110mm's rockets name a pod mounted on the jet as their source and the jet as their owner.
        # The call's rockets are exactly those of ITS jet's pods (its own mount record) owned by ITS jet; a vanilla 110mm's
        # rockets (its own pods, its own jet) and every forged mix stay vanilla. Verbose: the per-rocket trace too.
        self.check(r'''
iworld()
eagles.verbose=true
local C0=CLOCK
BOMB.set_clock(C0)
jets({{entity=7001,network=401}})                 -- a vanilla 110mm jet already flying (another call) ...
pods(7101,7102);mount(7001,{[0]=7101,[1]=7102})   -- ... with its own pods
eagles.arm()
tick()
-- The custom call's beacon activates; its jet and its pods appear in that update.
local C1=C0+5*US
BOMB.set_clock(C1)
eagles.note_activation(140,9100,C1)
local events={}
assert(eagles.capture({activation=C1,beacon=9100,donor_type=140,resource=JET,label='stun#1'},
    function(e)events[#events+1]=e end))
jets({{entity=7001,network=401},{entity=7002,network=402}})
pods(7201,7202);mount(7002,{[0]=7201,[1]=7202})
tick()
BOMB.set_clock(C1+0.3*US)
tick()
assert(events[1]and events[1].kind=='captured'and events[1].jet==7002,table.concat(logged,' | '))
local r={}
local binding=assert(eagles.bind_rockets({jet=7002,network=402,resource=JET,projectile=82,donor='Orbital EMS Strike',
    activation=C1,donor_type=140,beacon=9100,label='stun#1 rockets'},function(e)r[#r+1]=e end))
assert(binding.from==229 and binding.to==188)
-- Its two pods, from its own mount record, of exactly their slots' resources.
assert(binding.pods[7201]and binding.pods[7201].node=='payload_right'and binding.pods[7202].node=='payload_left')
assert(not binding.pods[7101]and not binding.pods[7102])
assert(count('PAYLOAD POD (stun#1 rockets): entity 7201 ('..RIGHT..', payload_right) of jet 7002, its mount record\'s '
    ..'slot 0')==1,
    table.concat(logged,' | '))
local podded={}
for _,e in ipairs(r)do if e.kind=='pod'then podded[e.pod]=e.node end end
assert(podded[7201]=='payload_right'and podded[7202]=='payload_left')
tick()
local writes=#W.runtime.writes
-- The call's rockets: source its pods, owner its jet. The vanilla run's: source its pods, owner its jet.
local _,h1=fire(7201,{type=82,impact=229,owner=7002})
local _,h2=fire(7202,{type=82,impact=229,owner=7002})
local _,v1=fire(7101,{type=82,impact=229,owner=7001})
local _,v2=fire(7102,{type=82,impact=229,owner=7001})
-- Forged mixes: this call's pod with the vanilla jet as its owner; the vanilla pod with this call's jet as its owner.
local _,x1=fire(7201,{type=82,impact=229,owner=7001})
local _,x2=fire(7101,{type=82,impact=229,owner=7002})
tick()
assert(impact_of(h1)==188 and impact_of(h2)==188,impact_of(h1)..' '..impact_of(h2))
assert(impact_of(v1)==229 and impact_of(v2)==229,'a vanilla rocket was converted')
assert(impact_of(x1)==229 and impact_of(x2)==229,'a forged rocket was converted')
assert(#W.runtime.writes==writes+2)
assert(count('ROCKET CAPTURED: projectile 82 (pool slot')==2 and count('source child 7201 (payload_right pod), owner '
    ..'custom jet 7002')==1 and count('IMPACT CONVERTED 229 -> 188 (read back true')==2,table.concat(logged,' | '))
assert(count('ROCKET CAPTURED but NOT converted: projectile 82')==1 and count('owner 7001: OWNER_MISMATCH: its owner is 7001, not 7002')==1,
    table.concat(logged,' | '))
assert(count('NOT THIS CALL\'S: projectile 82')==3,table.concat(logged,' | '))
-- A rocket of the call credited to another peer: refused, traced, vanilla.
local _,h4=fire(7201,{type=82,impact=229,owner=7002,creditor='9999888877776666'})
tick()
assert(impact_of(h4)==229 and count('owner custom jet 7002: NOT_LOCAL')==1,table.concat(logged,' | '))
-- The jet out of the Eagle manager while its entity exists: the binding stays (it follows the entity).
jets({{entity=7001,network=401}})
tick()
assert(binding.status=='active'and count('jet 7002 LEFT the Eagle manager; the entity still exists')==1)
-- The impacts: h1 requested with 188 in its own copy; the game's queue holds its request (source the pod).
W.write(h1+H.impactRequested,string.char(1))
requests({{type=188,source=7201,owner=7002},{type=229,source=7101,owner=7001}})
tick()
assert(count('IMPACT REQUESTED: rocket in pool slot')==1 and count('requested explosion 188 from its own copy (the '
    ..'donor\'s)')==1,table.concat(logged,' | '))
assert(count('EXPLOSION REQUEST observed in the game\'s queue: explosion 188')==1)
assert(count('EXPLOSION REQUEST observed in the game\'s queue: explosion 229')==0)
-- The jet goes; h2 still flies: the binding waits for it, then ends.
W.remove(7002)
requests({})
tick()
assert(binding.status=='active')
W.write(h2+H.impactRequested,string.char(1))
tick()
BOMB.set_clock(C1+2*US)
tick()
BOMB.set_clock(C1+3.5*US)
tick()
assert(binding.status~='active','the binding outlived its jet and its rockets')
local result
for _,e in ipairs(r)do if e.kind=='ended'then result=e end end
assert(result and result.proven and result.converted==2 and result.impacts_to==2 and result.pods==2,
    table.concat(logged,' | '))
assert(count('custom eagle ROCKETS RESULT (stun#1 rockets): the jet of this call is gone; jet 7002, 2 pods; 3 rockets '
    ..'of this call (2 converted 229 -> 188, 2 refused)')==1,table.concat(logged,' | '))
assert(count('NOT PROVEN')==0)
-- After the binding: a pod's rocket is never followed.
local _,h3=fire(7201,{type=82,impact=229,owner=7002})
tick()
assert(impact_of(h3)==229,'a rocket was converted after the binding')
-- No row was written: the rocket's, the EMS chain's.
assert(W.read(rocket82,0x110)==ROCKET82)
return 'ok'
''')

    def test_by_default_only_state_transitions_are_logged_and_the_trace_probes_never_run(self):
        # 0.30: the association is live-proven. The default log keeps the call's state transitions (bound, its pods,
        # each rocket's guarded write, the result); it neither observes other projectiles nor reads the game's
        # explosion queue or the jet's presence for a trace.
        self.check(r'''
iworld()
assert(eagles.verbose==false)
local C0=CLOCK
BOMB.set_clock(C0)
jets({})
eagles.arm()
tick()
local C1=C0+60*US
BOMB.set_clock(C1)
eagles.note_activation(140,9100,C1)
jets({{entity=7002,network=402}})
pods(7201,7202);mount(7002,{[0]=7201,[1]=7202})
tick()
local reads=0
local queue=eagles.explosion_requests
eagles.explosion_requests=function(...)reads=reads+1;return queue(...)end
local binding=assert(eagles.bind_rockets({jet=7002,network=402,resource=JET,projectile=82,donor='Orbital EMS Strike',
    activation=C1,donor_type=140,beacon=9100,label='stun#7 rockets'}))
tick()
local _,h1=fire(7201,{type=82,impact=229,owner=7002})
local _,v=fire(7101,{type=82,impact=229,owner=7001})
tick()
assert(impact_of(h1)==188 and impact_of(v)==229)
W.write(h1+H.impactRequested,string.char(1))
requests({{type=188,source=7201,owner=7002}})
tick()
jets({})
tick()
W.remove(7002)
tick()
BOMB.set_clock(C1+2*US)
tick()
assert(binding.status~='active')
assert(reads==0,'the explosion queue was read without verbose')
assert(count('TRACE (')==0 and count('NOT THIS CALL')==0 and count('EXPLOSION REQUEST')==0
    and count('the Eagle manager')==0,table.concat(logged,' | '))
assert(count('custom eagle ROCKETS BOUND (stun#7 rockets): jet 7002')==1 and count('PAYLOAD POD (stun#7 rockets)')==2,
    table.concat(logged,' | '))
assert(count('projectile impact CONVERTED (stun#7 rockets)')==1,table.concat(logged,' | '))
assert(count('custom eagle ROCKETS RESULT (stun#7 rockets): the jet of this call is gone; jet 7002, 2 pods; 1 rocket '
    ..'converted 229 -> 188, 0 refused; 1 impact requested (1 with explosion 188)')==1,table.concat(logged,' | '))
return 'ok'
''')

    def test_without_a_readable_mount_record_only_the_pod_type_and_the_owner_admit_a_rocket(self):
        self.check(r'''
iworld()
local C0=CLOCK
BOMB.set_clock(C0)
jets({})
eagles.arm()
tick()
local C1=C0+60*US
BOMB.set_clock(C1)
eagles.note_activation(140,9100,C1)
jets({{entity=7002,network=402}})            -- no mount record names its pods
pods(7301,7302)
tick()
local binding=assert(eagles.bind_rockets({jet=7002,network=402,resource=JET,projectile=82,donor='Orbital EMS Strike',
    activation=C1,donor_type=140,beacon=9100,label='stun#5 rockets'}))
tick()
local _,h=fire(7301,{type=82,impact=229,owner=7002})
local _,v=fire(7302,{type=82,impact=229,owner=7001})            -- a pod type, another owner
local _,w=fire(9999,{type=82,impact=229,owner=7002})            -- this owner, not a pod type
tick()
assert(impact_of(h)==188 and impact_of(v)==229 and impact_of(w)==229)
assert(count('PAYLOAD POD (stun#5 rockets): entity 7301 ('..RIGHT..', payload_right) of jet 7002, by its pod type and '
    ..'the projectile\'s '
    ..'owner (the jet\'s mount record is unreadable)')==1,table.concat(logged,' | '))
return 'ok'
''')

    def test_a_captured_jet_without_a_converted_rocket_is_not_proven(self):
        self.check(r'''
iworld()
local C0=CLOCK
BOMB.set_clock(C0)
jets({})
eagles.arm()
tick()
local C1=C0+60*US
BOMB.set_clock(C1)
eagles.note_activation(140,9100,C1)
jets({{entity=7002,network=402}})
pods(7201,7202);mount(7002,{[0]=7201,[1]=7202})
tick()
local r={}
local binding=assert(eagles.bind_rockets({jet=7002,network=402,resource=JET,projectile=82,donor='Orbital EMS Strike',
    activation=C1,donor_type=140,beacon=9100,label='stun#2 rockets'},function(e)r[#r+1]=e end))
tick()
-- No rocket of the call ever appears (a vanilla jet's do); the jet goes.
local _,v=fire(7101,{type=82,impact=229,owner=7001})
tick()
W.remove(7002);jets({})
tick()
BOMB.set_clock(C1+2*US)
tick()
local result
for _,e in ipairs(r)do if e.kind=='ended'then result=e end end
assert(result and result.proven==false and result.converted==0 and impact_of(v)==229)
assert(count('NOT PROVEN: no rocket of this call was converted; the run was vanilla')==1,table.concat(logged,' | '))
-- The mission's end ends a live binding and its trace: nothing stays bound or observed into the next mission.
BOMB.set_clock(C1+10*US)
eagles.note_activation(140,9300,C1+10*US)
W.add{entity=7003,type=JET,unit=0,health=1}
jets({{entity=7003,network=403}})
pods(7401,7402);mount(7003,{[0]=7401,[1]=7402})
tick()
local r3={}
local b3=assert(eagles.bind_rockets({jet=7003,network=403,resource=JET,projectile=82,donor='Orbital EMS Strike',
    activation=C1+10*US,donor_type=140,beacon=9300,label='stun#3 rockets'},function(e)r3[#r3+1]=e end))
tick()
W.state(3)
tick();tick()
assert(b3.status~='active'and b3.guard.status~='active')
local ended
for _,e in ipairs(r3)do if e.kind=='ended'then ended=e end end
assert(ended and ended.reason:find('the mission ended',1,true),table.concat(logged,' | '))
W.state(4)
local _,h=fire(7401,{type=82,impact=229,owner=7003})
tick()
assert(impact_of(h)==229,'a rocket was converted after the mission ended')
return 'ok'
''')

    def test_a_custom_and_a_vanilla_110mm_in_the_same_mission(self):
        # Simultaneous: both activate in one window: the capture refuses (AMBIGUOUS), every rocket stays vanilla.
        # Sequential: the vanilla run before and after the custom one: only the custom jet's pods' rockets convert.
        self.check(r'''
iworld()
local C0=CLOCK
BOMB.set_clock(C0)
jets({})
eagles.arm()
tick()
-- The vanilla run first.
local V=C0+10*US
BOMB.set_clock(V)
eagles.note_activation(140,9200,V)
jets({{entity=7001,network=401}})
pods(7101,7102);mount(7001,{[0]=7101,[1]=7102})
tick()
-- The custom call 3 s later, while the vanilla jet still flies.
local C1=V+3*US
BOMB.set_clock(C1)
eagles.note_activation(140,9100,C1)
local ev={}
assert(eagles.capture({activation=C1,beacon=9100,donor_type=140,resource=JET,label='stun#6'},function(e)ev[#ev+1]=e end))
jets({{entity=7001,network=401},{entity=7002,network=402}})
pods(7201,7202);mount(7002,{[0]=7201,[1]=7202})
tick()
BOMB.set_clock(C1+0.3*US)
tick()
assert(ev[1]and ev[1].kind=='captured'and ev[1].jet==7002,'the custom jet was not told from the vanilla one')
local binding=assert(eagles.bind_rockets({jet=7002,network=402,resource=JET,projectile=82,donor='Orbital EMS Strike',
    activation=C1,donor_type=140,beacon=9100,label='stun#6 rockets'}))
tick()
-- Both runs fire in the same update.
local _,v1=fire(7101,{type=82,impact=229,owner=7001})
local _,c1=fire(7201,{type=82,impact=229,owner=7002})
local _,v2=fire(7102,{type=82,impact=229,owner=7001})
local _,c2=fire(7202,{type=82,impact=229,owner=7002})
tick()
assert(impact_of(c1)==188 and impact_of(c2)==188 and impact_of(v1)==229 and impact_of(v2)==229)
-- A second vanilla run after it: never converted.
local V2=C1+4*US
BOMB.set_clock(V2)
eagles.note_activation(140,9300,V2)
jets({{entity=7001,network=401},{entity=7002,network=402},{entity=7005,network=405}})
pods(7501,7502);mount(7005,{[0]=7501,[1]=7502})
tick()
local _,v3=fire(7501,{type=82,impact=229,owner=7005})
tick()
assert(impact_of(v3)==229)
-- Both in one window: the capture refuses; the strike stays vanilla.
local C2=V2+60*US
BOMB.set_clock(C2)
eagles.note_activation(140,9400,C2)
eagles.note_activation(140,9500,C2)
local ev2={}
eagles.capture({activation=C2,beacon=9400,donor_type=140,resource=JET,label='stun#7'},function(e)ev2[#ev2+1]=e end)
tick()
assert(ev2[1]and ev2[1].kind=='refused'and ev2[1].code=='AMBIGUOUS')
assert(W.read(rocket82,0x110)==ROCKET82)
return 'ok'
''')

    def test_an_ambiguous_or_missing_jet_leaves_the_strike_vanilla(self):
        self.check(r'''
iworld()
local C0=CLOCK
BOMB.set_clock(C0)
jets({})
eagles.arm()
tick()
-- Another beacon of the donor's type activates in the same window: refused.
local C1=C0+5*US
BOMB.set_clock(C1)
eagles.note_activation(140,9100,C1)
eagles.note_activation(140,9200,C1)
local ev={}
eagles.capture({activation=C1,beacon=9100,donor_type=140,resource=JET,label='a'},function(e)ev[#ev+1]=e end)
jets({{entity=7002,network=402}})
tick()
assert(ev[1].kind=='refused'and ev[1].code=='AMBIGUOUS',tostring(ev[1]and ev[1].code))
-- Two jets of the donor appear after one activation: refused.
local C2=C1+10*US
BOMB.set_clock(C2)
eagles.note_activation(140,9300,C2)
local ev2={}
eagles.capture({activation=C2,beacon=9300,donor_type=140,resource=JET,label='b'},function(e)ev2[#ev2+1]=e end)
jets({{entity=7002,network=402},{entity=7003,network=403},{entity=7004,network=404}})
tick()
assert(ev2[1].kind=='refused'and ev2[1].code=='AMBIGUOUS')
-- No jet within the window: refused.
local C3=C2+10*US
BOMB.set_clock(C3)
local ev3={}
eagles.capture({activation=C3,beacon=9400,donor_type=140,resource=JET,label='c'},function(e)ev3[#ev3+1]=e end)
tick()
BOMB.set_clock(C3+4*US)
tick()
assert(ev3[1].kind=='refused'and ev3[1].code=='NO_JET')
-- The tracker must run before the call.
eagles.reset_for_tests()
assert(select(2,eagles.capture({activation=C3,beacon=1,donor_type=140,resource=JET}))=='the jet tracker is not armed')
return 'ok'
''')


USES = r"""
-- An Eagle row in the settings (Eagle Smoke Strike, type 38: 2 uses per rearm, linked to Eagle Rearm), owned.
local SMOKE_ID=CAT['Eagle Smoke Strike'].root.id
local list={rooted('Eagle Smoke Strike',38)}
for kind,r in pairs(settings.rows)do list[#list+1]={type=kind,id=r.id,package=r.package,payload=r.payload,
    payloads=r.payloads,sequence=r.sequence,group=r.group,row=r.row,cooldown=r.cooldown,fields=r.fields}end
"""


class EagleUsesTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + r"""
local eagles=require('hd2runtime/runtime/custom_eagles');eagles.reset_for_tests()
local CP=require('hd2runtime/domains/custom_payloads')
for _,pin in ipairs(CP.pins)do W.write(W.GAME+pin.rva,b.unhex(pin.hex))end
local SMOKE_ID=CAT['Eagle Smoke Strike'].root.id
settings=W.stratagem_settings({rooted('Orbital Precision Strike',118),rooted('Orbital 120mm HE Barrage',136),
    rooted('Eagle Smoke Strike',38)})
for kind,r in pairs(settings.rows)do ROW[kind]=r.address end
for _,kind in ipairs({118,136})do
    W.write(ROW[kind]+0x50,W.u32(4294967295));W.write(ROW[kind]+0x80,W.u32(2));W.write(ROW[kind]+0xC0,W.u32(1))
end
W.write(ROW[38]+0x50,W.u32(2));W.write(ROW[38]+0x80,W.u32(2));W.write(ROW[38]+0xC0,W.u32(1))
W.catalogue({[PRECISION_ID]=2,[BIG_ID]=2,[SMOKE_ID]=2})
local US=1e6
local function entry(h,index)
    local raw=W.read(h.record+0x38+0x188+index*0x30,8)
    local uses=b.u32(raw,4)
    return b.u32(raw,0),uses>=2147483648 and uses-4294967296 or uses
end
""" + body), b'ok')

    def test_the_eagle_slot_gets_its_own_uses_and_the_runtime_rearms_it_without_eagle_rearm(self):
        self.check(r'''
assert(ROW[38],'no Eagle Smoke Strike row in the world')
local h=world_with()
BOMB.set_clock(CLOCK)
-- A limited Eagle is refused as a plain carrier, accepted with its slot's own uses.
local plain=settle_job(slots.convert({token='Orbital Precision Strike',carrier='Eagle Smoke Strike'}))
assert(plain.status=='refused'and plain.code=='USES_DIFFER')
local job=settle_job(slots.convert({token='Orbital Precision Strike',carrier='Eagle Smoke Strike',uses=5}))
assert(job.status=='converted',tostring(job.code)..' '..tostring(job.reason))
local t,u=entry(h,3)
assert(t==38 and u==5,'entry 3: '..t..' '..u)
assert(entry(h,2)==118,'the other token entry is untouched')
-- The game spends the five uses; at 0 the Runtime rearms the slot after the rearm time (no Eagle Rearm in the record).
local events={}
local w=eagles.uses_watch({definition='*',carrier_type=38,uses=5,seconds=10,label='stun'},function(e)events[#events+1]=e end)
W.write(h.record+0x38+0x188+3*0x30+4,W.u32(0))
tick()
assert(events[1]and events[1].kind=='depleted'and events[1].index==3,tostring(events[1]and events[1].kind))
BOMB.set_clock(CLOCK+5*US);tick()
assert(#events==1 and select(2,entry(h,3))==0,'rearmed early')
BOMB.set_clock(CLOCK+10.5*US);tick()
assert(events[2]and events[2].kind=='rearmed'and events[2].uses==5 and events[2].verified,tostring(events[2]and events[2].kind))
assert(select(2,entry(h,3))==5)
assert(count('custom eagle REARMED (stun): loadout entry 3 uses 0 -> 5 (1 write; read back 5')==1,table.concat(logged,' | '))
w.cancel()
-- The restore: the token and unlimited uses back.
local back=settle_job(slots.restore(nil,'*'))
assert(back.status=='restored'and back.exact,tostring(back.code))
local t2,u2=entry(h,3)
assert(t2==118 and u2==-1)
return 'ok'
''')

    def test_with_eagle_rearm_in_the_record_the_game_rearms(self):
        self.check(r'''
local record={}
for k,e in ipairs(RECORD)do record[k]={type=e.type,uses=e.uses,granted=e.granted}end
record[#record+1]={type=49,uses=1,granted=1}         -- Eagle Rearm (a real Eagle in the loadout)
local h=world_with(record)
BOMB.set_clock(CLOCK)
local job=settle_job(slots.convert({token='Orbital Precision Strike',carrier='Eagle Smoke Strike',uses=5}))
assert(job.status=='converted',tostring(job.reason))
local events={}
local w=eagles.uses_watch({definition='*',carrier_type=38,uses=5,seconds=10,label='stun'},function(e)events[#events+1]=e end)
local writes=#W.runtime.writes
W.write(h.record+0x38+0x188+3*0x30+4,W.u32(0))
tick();BOMB.set_clock(CLOCK+20*US);tick()
assert(events[1].kind=='native'and#events==1,tostring(events[2]and events[2].kind))
assert(#W.runtime.writes==writes,'the Runtime wrote beside the game\'s own rearm')
w.cancel()
return 'ok'
''')


class EagleCarrierTests(unittest.TestCase):
    def test_the_discovery_takes_eagles_only_in_eagle_mode(self):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + r'''
local SMOKE_ID=CAT['Eagle Smoke Strike'].root.id
settings=W.stratagem_settings({rooted('Orbital Precision Strike',118),rooted('Orbital 120mm HE Barrage',136),
    rooted('Eagle Smoke Strike',38)})
for kind,r in pairs(settings.rows)do ROW[kind]=r.address end
for _,kind in ipairs({118,136})do
    W.write(ROW[kind]+0x50,W.u32(4294967295));W.write(ROW[kind]+0x80,W.u32(2));W.write(ROW[kind]+0xC0,W.u32(1))
end
W.write(ROW[38]+0x50,W.u32(2));W.write(ROW[38]+0x80,W.u32(2));W.write(ROW[38]+0xC0,W.u32(1))
W.catalogue({[PRECISION_ID]=2,[BIG_ID]=2,[SMOKE_ID]=2})
world_with()
local world=world_module.open()
local plain=slots.validate_carrier(world,'Orbital Precision Strike','Eagle Smoke Strike',{present={}})
assert(plain.ready and not plain.valid)
local codes=table.concat(plain.codes,',')
assert(codes:find('special_case',1,true)and codes:find('limited_use',1,true),codes)
local eagle=slots.validate_carrier(world,'Orbital Precision Strike','Eagle Smoke Strike',{present={},eagle=true})
assert(eagle.ready and eagle.valid,table.concat(eagle.reasons or{},'; '))
assert(eagle.candidate.eagle and eagle.candidate.usesPerRearm==2)
-- In Eagle mode an orbital is never a carrier.
local orbital=slots.validate_carrier(world,'Orbital Precision Strike','Orbital 120mm HE Barrage',{present={},eagle=true})
assert(not orbital.valid and table.concat(orbital.codes,','):find('not_an_eagle',1,true))
return 'ok'
'''), b'ok')

    def test_the_allocator_keeps_eagles_and_sentries_to_their_families(self):
        self.assertEqual(run(WORLD + r'''
local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
local A=require('hd2runtime/runtime/carrier_allocator')
local function cand(name,id,family,beacon,class,eagle_only)
    return {name=name,id=id,type=id,family=family,class=class,beaconCategory=beacon,
        beamColour=beacon=='offensive'and'red'or'blue',pingColour='red',eligible=true,reasons={},codes={},
        eagle=family=='eagle'}
end
local ALL={cand('Orbital 380mm HE Barrage',1,'orbital','offensive',1),cand('Eagle Smoke Strike',2,'eagle','offensive',1),
    cand('Eagle Airstrike',3,'eagle','offensive',1),cand('A/MG-43 Machine Gun Sentry',4,'sentry','support',3),
    cand('A/M-12 Mortar Sentry',5,'sentry','support',3),cand('MG-43 Machine Gun',6,'support','support',4),
    cand('E/MG-101 HMG Emplacement',7,'emplacement','support',3)}
local modes={}
-- The discovery as the Runtime's: Eagles eligible only in Eagle mode, and then nothing else.
slots.discover_carriers=function(world,token,opts)
    modes[#modes+1]=opts.eagle and'eagle'or'plain'
    local out={ready=true,candidates={}}
    for _,c in ipairs(ALL)do
        local copy={};for k,v in pairs(c)do copy[k]=v end
        copy.reasons={}
        if opts.eagle then copy.eligible=c.family=='eagle'else copy.eligible=c.family~='eagle'end
        if not copy.eligible then copy.reasons[1]='not for this mode'end
        out.candidates[#out.candidates+1]=copy
    end
    return out
end
local defs={
    {id='hmg_sentry',label='HMG Sentry',token='Orbital Precision Strike',
        policy={beacon='support',prefer_families={'sentry'},allow_families={'sentry'}}},
    {id='stun_pods',label='Stun Pods',token='Orbital Precision Strike',eagle=true,
        policy={beacon='offensive',prefer_families={'eagle'},allow_families={'eagle'}}},
    {id='gas_barrage',label='Gas Barrage',token='Orbital Precision Strike',
        policy={beacon='offensive',prefer_families={'orbital'}}}}
local a=A.allocate_policies(world_module.open(),defs,{},{})
assert(a.ready and a.distinct)
assert(a.assignments.hmg_sentry.family=='sentry','sentry got '..tostring(a.assignments.hmg_sentry.family))
assert(a.assignments.stun_pods.family=='eagle','eagle got '..tostring(a.assignments.stun_pods.family))
assert(a.assignments.gas_barrage.family=='orbital')
-- Discovered in id order (gas_barrage, hmg_sentry, stun_pods), whatever the input order.
assert(table.concat(modes,',')=='plain,plain,eagle',table.concat(modes,','))
-- No Eagle left: refused, never an orbital; no sentry left: refused, never an emplacement or a support weapon.
local busy={[2]=true,[3]=true,[4]=true,[5]=true}
for _,c in ipairs(ALL)do if busy[c.id]then c.family=c.family..'-gone'end end
local b2=A.allocate_policies(world_module.open(),defs,{},{})
assert(not b2.assignments.stun_pods and b2.refused.stun_pods:find('of the families eagle',1,true),b2.refused.stun_pods)
assert(not b2.assignments.hmg_sentry and b2.refused.hmg_sentry:find('of the families sentry',1,true))
return 'ok'
'''), b'ok')


class OrbitalTests(unittest.TestCase):
    def test_explicit_salvos_shell_counts_and_intervals_over_a_reviewed_pattern(self):
        from test_bombardment_executor import EXECUTOR
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + EXECUTOR + r'''
pworld();host_avatar()
local events={}
local h=assert(executor.start({shell_donor='Orbital Gas Strike',pattern='Orbital 120mm HE Barrage',
    overrides={salvos=3,shells_per_salvo=2,shell_delay=0.5,shell_delay_random=0,salvo_delay=1.5,salvo_delay_random=0,
    scatter=10},target={x=100,y=200,z=10},random=lcg(3),label='test'},function(e)events[#events+1]=e end))
assert(events[1].kind=='started'and events[1].shells==6)
tick(200)
assert(shells()==6,'shells '..shells())
local times={}
for _,e in ipairs(events)do if e.kind=='shell'then times[#times+1]=e.seconds end end
-- Salvo k's shells at 2 k and 2 k + 0.5 s (within one 0.125 s update).
for k=0,2 do for j=0,1 do
    local want=2*k+0.5*j
    local got=times[k*2+j+1]
    assert(got>=want and got<want+0.125+1e-6,('shell %d at %.3f, wanted %.3f'):format(k*2+j+1,got,want))
end end
for _,s in ipairs(W.runtime.projectiles)do assert(math.abs(s.x-100)<=10 and math.abs(s.y-200)<=10)end
assert(events[#events].kind=='ended'and events[#events].shells==6 and events[#events].salvos==3)
return 'ok'
'''), b'ok')

    def test_explicit_salvos_and_each_shells_own_impact_explosion(self):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + IMPACT + EAGLE + r'''
local executor=require('hd2runtime/runtime/bombardment_executor')
iworld()
require('hd2runtime/runtime/handles').local_avatar=function()return {id=100}end
-- The game's FireProjectile spawns into the pool with the row's own impact explosion copy (197: 82).
local fire_native=W.runtime.native_projectile
W.runtime.native_projectile=function(entry,system,kind,x,y,z,dx,dy,dz,entity)
    fire_native(entry,system,kind,x,y,z,dx,dy,dz,entity)
    local slot=W.spawn_projectile({type=kind,source=entity,owner=entity,creditor=LOCAL_PEER})
    local hit=W.projectile_system+H.base+slot*H.stride
    W.write(hit+H.impactExplosion,W.u32(82)..W.u32(0))
    W.write(hit+H.impactRequested,string.char(0))
    return true
end
local events={}
local h=assert(executor.start({shell_donor='Orbital Gas Strike',pattern=false,
    overrides={salvos=2,shells_per_salvo=4,shell_delay=0.25,salvo_delay=1,scatter=5,distance=3000},
    impact_explosion='Orbital EMS Strike',target={x=100,y=200,z=10},label='stun shells'},
    function(e)events[#events+1]=e end))
assert(events[1].kind=='started'and events[1].shells==8)
tick(80)
local shells,converted=0,0
for _,e in ipairs(events)do
    if e.kind=='shell'then shells=shells+1;if e.converted then converted=converted+1 end end
end
assert(shells==8 and converted==8,shells..' '..converted)
assert(events[#events].kind=='ended'and events[#events].shells==8 and events[#events].salvos==2
    and events[#events].converted==8)
-- Every pool slot the executor spawned now requests the EMS explosion; nothing else changed.
local n=0
for slot=0,PO.slots-1 do
    local kind=b.u32(W.read(W.projectile_system+PO.types.base+slot*PO.types.stride,4),0)
    if kind==197 then
        n=n+1
        assert(b.u32(W.read(W.projectile_system+H.base+slot*H.stride+H.impactExplosion,4),0)==188)
    end
end
assert(n==8)
-- An unreviewed donor or one whose package is not resident: refused before anything is fired.
assert(select(2,executor.start({shell_donor='Orbital Gas Strike',impact_explosion='Big Boom',target={x=0,y=0,z=0}}))
    =='UNREVIEWED_DONOR')
return 'ok'
'''), b'ok')


NEW_EXAMPLES = {'HmgSentryExample': ('0.2.1 DEV LINE BUILD', 'hmg_sentry'),
    'EagleStunRocketPodsExample': ('0.3.1 DEV LINE BUILD', 'eagle_stun_rocket_pods')}


# HmgSentryExample 0.2.1, frozen when the example became a custom_stratagems.json project (2026-10-06; same resource
# id): these payload tests were written against it.
FROZEN = {'HmgSentryExample': ROOT / 'tests/fixtures/example_addons/HmgSentryExample-0.2.1.lua'}


def example_source(name):
    return (FROZEN.get(name) or ROOT / 'proof' / name / 'src/addon.lua').read_text(encoding='utf-8')


def example_addon(name):
    from test_event_scripting import SDK
    folder = ROOT / 'proof' / name
    spec = json.loads((folder / 'hd2runtime.json').read_text(encoding='utf-8'))
    body = example_source(name)
    return spec['resource'], SDK.wrap_addon(spec['resource'], spec['requires']['hd2runtime']['min_version'], body)


def examples_lua(body):
    from support import lua as lua_literal
    (sentry, sentry_addon), (eagle, eagle_addon) = (example_addon('HmgSentryExample'),
        example_addon('EagleStunRocketPodsExample'))
    return run(WORLD + 'local SENTRY_ADDON=' + lua_literal(sentry_addon) + '\nlocal SENTRY_RESOURCE='
        + lua_literal(sentry) + '\nlocal EAGLE_ADDON=' + lua_literal(eagle_addon) + '\nlocal EAGLE_RESOURCE='
        + lua_literal(eagle) + r'''
local custom=require('hd2runtime/runtime/custom_stratagems');custom.reset_for_tests()
require('hd2runtime/runtime/spawned_instances').reset_for_tests()
assert(loadstring(SENTRY_ADDON,'@'..SENTRY_RESOURCE))()
assert(loadstring(EAGLE_ADDON,'@'..EAGLE_RESOURCE))()
''' + body)


class NewExampleTests(unittest.TestCase):
    def test_the_example_sources_use_the_public_api_only(self):
        import sys
        sys.path.insert(0, str(ROOT / 'scripts'))
        import hd2_image
        for name, (banner, icon) in NEW_EXAMPLES.items():
            folder = ROOT / 'proof' / name
            body = example_source(name)
            code = '\n'.join(line.split('--')[0] for line in body.splitlines())
            if name not in FROZEN:
                self.assertEqual((folder / 'VERSION').read_text(encoding='utf-8').strip(), banner.split()[0])
            self.assertIn("local BUILD='%s'" % banner, code)
            self.assertIn("icon=hd2.resources.image('%s')," % icon, code)
            self.assertEqual(sorted(p.name for p in (folder / 'images').iterdir()), [icon + '.png'])
            for forbidden in ("require('hd2runtime", 'ffi', 'VirtualProtect', 'WriteProcessMemory', '.write(',
                    'transaction', 'native_', 'on_activate', 'on_delivered'):
                self.assertNotIn(forbidden, code, name)
            self.assertEqual(code.count('hd2.custom_stratagem.register('), 1, name)
            rgba, prepared = hd2_image.prepare_icon((folder / 'images' / (icon + '.png')).read_bytes())
            self.assertEqual(prepared, 'masks (as given)')

    def test_they_register_their_payload_families_as_data(self):
        self.assertEqual(examples_lua(r'''
local s=custom.get('hmg_sentry')
assert(s.kind=='sentry'and s.delivery.stratagem=='A/MG-43 Machine Gun Sentry'
    and s.delivery.content_type=='37CDE43876BA26BB')
assert(s.sentry.weapon.projectile==275 and s.sentry.weapon.rpm==400 and s.sentry.weapon.spread==5
    and s.sentry.weapon.ammo==300)
assert(table.concat(s.assets,',')=='MG-206 Heavy Machine Gun'and s.cooldown==150)
assert(table.concat(s.exclude,',')=='MG-206 Heavy Machine Gun,A/MG-43 Machine Gun Sentry')
assert(s.policy.beacon=='support'and s.policy.allow_families[1]=='sentry'and#s.policy.allow_families==1)
assert(s.colours=='A/MG-43 Machine Gun Sentry','its ship icon takes its sentry\'s own colours')
local e=custom.get('eagle_stun_rocket_pods')
assert(e.kind=='eagle'and e.eagle.stratagem=='Eagle 110mm Rocket Pods'and e.eagle.uses==5 and e.eagle.projectile==82
    and e.eagle.jet=='397792815583DA29'and e.eagle.impact=='Orbital EMS Strike')
assert(table.concat(e.assets,',')=='Orbital EMS Strike'and e.cooldown==nil)
assert(e.policy.beacon=='offensive'and e.policy.allow_families[1]=='eagle')
assert(count('custom stratagem REGISTERED hmg_sentry (A/HMG-206 Heavy Machine Gun Sentry) by '
    ..'mods/skyeshade/hd2runtime_hmg_sentry_example: code down up left left down up, cooldown 150 s, carrier policy: '
    ..'support beacon, prefer sentry, allow sentry; delivery the vanilla A/MG-43 Machine Gun Sentry pod; its sentry\'s '
    ..'own weapon: ammo 300, projectile 275, rpm 400, spread 5; assets MG-206 Heavy Machine Gun')==1,
    table.concat(logged,' | '))
assert(count('custom stratagem REGISTERED eagle_stun_rocket_pods (Eagle Stun Rocket Pods) by '
    ..'mods/skyeshade/hd2runtime_eagle_stun_rocket_pods_example: code up left up right down right, cooldown the '
    ..'carrier\'s own, carrier policy: offensive beacon, prefer eagle, allow eagle; delivery the Eagle 110mm Rocket Pods '
    ..'strike from an Eagle carrier, 5 uses per rearm; its rockets explode as Orbital EMS Strike\'s; assets Orbital EMS '
    ..'Strike')==1,table.concat(logged,' | '))
return 'ok'
'''), b'ok')

    def test_an_arbitrary_support_delivery_modifies_only_its_own_weapon(self):
        self.assertEqual(examples_lua(r'''
local I=custom.internals_for_tests()
local pods=require('hd2runtime/runtime/support_pods')
local weapons=require('hd2runtime/runtime/custom_weapons')
-- The AC-8 Autocannon's pod: its rack holds the weapon and its backpack. The weapon gets a faster, smaller magazine.
local d=custom.register({id='quick_autocannon',name='QUICK AUTOCANNON',name_cased='Quick Autocannon',
    description='An AC-8 with a faster cycle.',icon='quick_autocannon',code={'right','right','up','down','left'},
    carrier={beacon='support',prefer_families={'support','backpack'}},
    delivery={family='support',items={{donor='AC-8 Autocannon',count=2,modify={rpm=150,ammo=6}}}}},'mods/test/ac')
assert(d.kind=='support'and d.delivery.count==2 and d.delivery.modify.rpm==150 and d.delivery.modify.ammo==6)
local G=require('hd2runtime/domains/stratagem_authoring').stratagems['AC-8 Autocannon'].root
settings=W.stratagem_settings({{type=25,id=G.id,package=G.package,payloads=G.payloads,sequence={3,4,3,1,2},
    group=G.group,row=G.row,cooldown=480}})
local spec_seen,configured
pods.capture=function(spec,cb)
    spec_seen=spec
    cb({kind='pod',pod=501})
    cb({kind='captured',pod=501,rack=6000,items={6001,6002},types={'A8CFFB316F0B5C5F','E60AE045E0090F4C'},slots={0,1}})
    return {status='complete'}
end
configured={}
weapons.configure=function(world,entity,spec,label)
    configured[#configured+1]={entity=entity,spec=spec}
    return {writes=4,verified=true,verify={}}
end
local ctx=I.new_call(d,{carrier='MG-43 Machine Gun',stable_id=3,type=60},0)
ctx.beacon={entity=7006,network=802}
I.start_capture(ctx,d)
assert(spec_seen and spec_seen.item_types['A8CFFB316F0B5C5F']and spec_seen.item_types['E60AE045E0090F4C']
    and spec_seen.type==25)
assert(#ctx.items==2 and#ctx.weapons==1 and ctx.weapons[1].entity==6001 and ctx.weapons[1].projectile==115)
assert(#configured==1 and configured[1].entity==6001 and configured[1].spec.rpm==150,'only the weapon is configured')
assert(custom.instance_of(6001).role=='weapon'and custom.instance_of(6002).role=='backpack')
assert(count('quick_autocannon#1: DELIVERED: pod 501, rack 6000: weapons 6001, other items backpack 6002')==1,
    table.concat(logged,' | '))
return 'ok'
'''), b'ok')

    def test_the_sentry_and_eagle_call_glue(self):
        self.assertEqual(examples_lua(r'''
local I=custom.internals_for_tests()
local pods=require('hd2runtime/runtime/support_pods')
local weapons=require('hd2runtime/runtime/custom_weapons')
local eagles=require('hd2runtime/runtime/custom_eagles')
-- The sentry: the pod's content is the sentry; its own weapon configured from the definition's data.
local s=custom.get('hmg_sentry')
local pod_spec,configured
pods.capture=function(spec,cb)
    pod_spec=spec
    cb({kind='pod',pod=500})
    cb({kind='captured',pod=500,rack=9801,content=9801,items={9801},types={'37CDE43876BA26BB'}})
    return {status='complete'}
end
weapons.configure=function(world,entity,spec,label)
    configured={entity=entity,spec=spec,label=label}
    return {writes=7,verified=true,verify={}}
end
-- The MG-43 Machine Gun Sentry's row (the delivery's type, resolved by its stable id).
local G=require('hd2runtime/domains/stratagem_authoring').stratagems['A/MG-43 Machine Gun Sentry'].root
settings=W.stratagem_settings({{type=60,id=G.id,package=G.package,payloads=G.payloads,sequence={3,1,2,4},
    group=G.group,row=G.row,cooldown=150}})
local ctx=I.new_call(s,{carrier='A/FLAM-40 Flame Sentry',stable_id=1,type=8},0)
ctx.beacon={entity=7005,network=801}
I.start_capture(ctx,s)
assert(pod_spec,'no capture: '..table.concat(logged,' | '))
assert(pod_spec.content_type=='37CDE43876BA26BB'and pod_spec.beacon_network==801 and pod_spec.type==60
    and not pod_spec.item_types)
assert(configured and configured.entity==9801 and configured.spec.projectile==275 and configured.spec.rpm==400
    and configured.spec.spread==5 and configured.spec.ammo==300)
assert(ctx.sentry.entity==9801 and ctx.state=='delivered'and custom.instance_of(9801).role=='sentry')
assert(count('hmg_sentry#1: DELIVERED: pod 500: sentry 9801 (37CDE43876BA26BB; exactly this pod\'s sentry; every other '
    ..'A/MG-43 Machine Gun Sentry stays vanilla)')==1,table.concat(logged,' | '))
-- The Eagle: the call's jet, then its rockets bound to the EMS explosion.
local e=custom.get('eagle_stun_rocket_pods')
local cap,bound
eagles.capture=function(spec,cb)
    cap=spec
    cb({kind='captured',jet=7002,network=402,resource='397792815583DA29',seconds=0})
    return {status='complete'}
end
local bound_cb
eagles.bind_rockets=function(spec,cb)bound,bound_cb=spec,cb;return {from=229,to=188,status='active'}end
local ctx2=I.new_call(e,{carrier='Eagle Smoke Strike',stable_id=2,type=38},1)
ctx2.beacon={entity=9100}
I.start_eagle(ctx2,e,{clock=123,entity=9100,type=140})
assert(cap.activation==123 and cap.beacon==9100 and cap.donor_type==140 and cap.resource=='397792815583DA29')
assert(bound.jet==7002 and bound.network==402 and bound.projectile==82 and bound.donor=='Orbital EMS Strike')
assert(bound.activation==123 and bound.donor_type==140 and bound.beacon==9100)
assert(ctx2.jet==7002 and ctx2.state=='delivered'and custom.instance_of(7002).role=='eagle_jet')
assert(count('eagle_stun_rocket_pods#1: ROCKETS: projectiles 82 of jet 7002\'s mounted pods (owner this jet) explode as '
    ..'Orbital EMS Strike\'s on impact (explosion 188 instead of 229)')==1,table.concat(logged,' | '))
-- A pod mounted on the call's jet is associated with it; the result is the call's.
bound_cb({kind='pod',pod=7003,slot=0,node='payload_right',resource='0E8C2515261E0325',how='its mount record\'s slot 0'})
assert(custom.instance_of(7003)and custom.instance_of(7003).role=='eagle_pod')
bound_cb({kind='ended',converted=0,impacts_to=0,proven=false})
assert(ctx2.payload_result and ctx2.payload_result.proven==false)
assert(count('eagle_stun_rocket_pods#1: PAYLOAD RESULT: 0 rockets converted to Orbital EMS Strike\'s explosion, 0 '
    ..'impacts requested it (NOT PROVEN: the run was vanilla)')==1,table.concat(logged,' | '))
return 'ok'
'''), b'ok')


if __name__ == '__main__':
    unittest.main()
