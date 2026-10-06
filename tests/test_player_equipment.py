"""player:loadout() / :held_weapon() / :backpack() / :ammo() and hd2.actions.resupply_from_pack: what the local Helldiver
holds and wears, and the Supply Pack's own self-use (research/player-equipment-F5FEE03DCFDB.json,
runtime/player_equipment.lua, api/player_equipment.lua). Research facts are checked against the retained-snapshot
observations the research script recorded; the runtime is exercised on the offline event world
(tests/event_world_fixture.lua) with the inventory, deposit, magazine, avatar and ability managers laid out as the
domain describes, and fake native calls that record what Runtime would pass (nothing is ever executed)."""
import json
import re
import unittest

from support import ROOT, run
import test_player_injury as injury_tests

RESEARCH = json.loads((ROOT / 'research/player-equipment-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
SOURCE = (ROOT / 'runtime/player_equipment.lua').read_text(encoding='utf-8')
API_SOURCE = (ROOT / 'api/player_equipment.lua').read_text(encoding='utf-8')

PRELUDE = injury_tests.PRELUDE + r'''
local equipment=require('hd2runtime/runtime/player_equipment')
local pack_api=require('hd2runtime/api/player_equipment')
local D=require('hd2runtime/domains/player_equipment')
equipment.reset_for_tests();pack_api.reset_for_tests()
for _,pin in ipairs(D.pins)do W.write(W.GAME+pin.rva,unhex(pin.hex))end
for _,n in pairs(D.natives)do W.write(W.GAME+n.rva,unhex(n.prologue))end
local function ptr(a)return le64(W.read(a,8))end
local function type_bytes(h)return W.u32(tonumber(h:sub(9),16))..W.u32(tonumber(h:sub(1,8),16))end
local function type_of(name,kind)
    for key,item in pairs(D.items)do if item.name==name and(kind==nil or item.kind==kind)then return key end end
    error('no catalogued '..name)
end
local ERUPTOR,VERDICT=type_of('R-36 Eruptor'),type_of('P-113 Verdict')
local SUPPLY,DOG,GAS=D.supplyPack.type,type_of('AX/AR-23 Guard Dog'),type_of('G-4 Gas')
local MAXIGUN,MAXIGUN_PACK=type_of('M-1000 Maxigun','support'),type_of('M-1000 Maxigun Backpack')
-- A u32 hash {buckets, 64, empty 0, multiplier 1} like the fixture's.
local function hash_put(buckets,key,value)
    local slot=key%64
    while W.read(buckets+slot*8,4)~=W.u32(0)and W.read(buckets+slot*8,4)~=W.u32(key)do slot=(slot+1)%64 end
    W.write(buckets+slot*8,W.u32(key)..W.u32(value))
end
local function hash_get(buckets,key)
    for i=0,63 do
        local slot=(key+i)%64
        local raw=W.read(buckets+slot*8,8)
        if raw:sub(1,4)==W.u32(key)then return le64(raw:sub(5,8)..'\0\0\0\0')end
        if raw:sub(1,4)==W.u32(0)then return nil end
    end
end
local function descriptor(type_hex,entity,owned)
    local d=W.alloc(0x18)
    W.write(d,type_bytes(type_hex)..W.u32(entity)..W.u32(0)..W.u32(0x7FFF)..W.u32(owned==false and 0 or 1))
    return d
end
local function manager(layout,size,inline)
    local m=W.alloc(size)
    W.write(W.GAME+layout.global,W.u64(m))
    local buckets=W.alloc(64*8)
    W.write(m+layout.hash,W.u64(buckets)..W.u32(64)..W.u32(0)..W.u32(1))
    local mgr={base=m,buckets=buckets,count=0,inline=inline,layout=layout}
    if not inline then mgr.descs=W.alloc(64*8);W.write(m+layout.descriptors,W.u64(mgr.descs))end
    return mgr
end
local function put(mgr,entity,type_hex,owned)
    local index=mgr.count;mgr.count=index+1
    hash_put(mgr.buckets,entity,index)
    local d=descriptor(type_hex,entity,owned)
    if mgr.inline then W.write(mgr.base+mgr.layout.descriptors+index*8,W.u64(d))
    else W.write(mgr.descs+index*8,W.u64(d))end
    return index
end
-- Inventory: the fixture's manager, plus its descriptors (+0x40) and counts (+0x58).
local I=D.inventory
local INV=ptr(W.GAME+I.global)
local inv_descs,inv_counts=W.alloc(64*8),W.alloc(64*8)
W.write(INV+I.descriptors,W.u64(inv_descs));W.write(INV+I.counts,W.u64(inv_counts))
local function wear(avatar,spec)
    W.hold(avatar,spec.hand or 0,spec.hand_type,spec.selection or 0)
    local index=assert(hash_get(ptr(INV+I.hash),avatar))
    W.write(inv_descs+index*8,W.u64(descriptor(W.AVATAR,avatar,spec.owned)))
    local record=ptr(INV+I.records)+index*I.stride
    for _,slot in ipairs({'primary','secondary','support','backpack','held'})do
        W.write(record+I.slots[slot],W.u32(spec[slot]or 0))
    end
    W.write(record+I.throwable,spec.throwable and type_bytes(spec.throwable)or W.u64(0))
    W.write(inv_counts+index*I.countStride,W.u32(spec.count or 0))
end
-- Deposit: instances, and the per-type definition table the entity manager points at.
local DP=D.deposit
local deposits=manager(DP,0x100)
local live=W.alloc(64*8)
W.write(deposits.base+DP.live,W.u64(live))
local settings=W.alloc(DP.settings.records+32*DP.definitionStride)
W.write(ptr(W.GAME+DP.settings.entityManager)+DP.settings.table,W.u64(settings))
local definitions=0
local function define(type_hex,capacity,start,refill,other,own)
    local hi,lo=tonumber(type_hex:sub(1,8),16),tonumber(type_hex:sub(9),16)
    local slot=((hi%58)*(4294967296%58)+lo%58)%58
    while W.read(settings+slot*16,8)~=W.u64(0)do slot=(slot+1)%58 end
    W.write(settings+slot*16,type_bytes(type_hex)..W.u32(definitions))
    W.write(settings+DP.settings.records+definitions*DP.definitionStride,W.u32(capacity)..W.u32(start%4294967296)
        ..W.u32(refill))
    W.write(settings+DP.settings.records+definitions*DP.definitionStride+DP.definition.otherAbility,W.u32(other)..W.u32(own))
    definitions=definitions+1
end
define(SUPPLY,4,4,1,2628,2629);define(DOG,8,8,8,0,0);define(MAXIGUN_PACK,1000,1000,500,0,0)
local function deposit(entity,type_hex,amount,owned)
    local index=put(deposits,entity,type_hex,owned)
    W.write(live+index*8,W.u32(amount)..W.u32(0))
    return function(n)W.write(live+index*8,W.u32(n))end
end
-- Magazines.
local MG=D.magazine
local magazines=manager(MG,0x100)
local mag_records=W.alloc(64*MG.stride)
W.write(magazines.base+MG.records,W.u64(mag_records))
local function magazine(entity,type_hex,spare,rounds)
    local index=put(magazines,entity,type_hex)
    W.write(mag_records+index*MG.stride,W.u32(spare)..W.u32(rounds)..W.u32(0))
end
-- The avatar manager (descriptors inline at +0x110, action context and flags per record) and the ability manager.
local AV,AB=D.avatar,D.ability
local avatars=manager(AV,AV.flags+4*AV.stride+0x100,true)
local abilities=manager(AB,0x100)
local ability_records=W.alloc(64*AB.stride)
W.write(abilities.base+AB.records,W.u64(ability_records))
W.write(W.GAME+AV.noTarget,W.u32(0))
local contexts={}
local function avatar_context(avatar,flags)
    local index=put(avatars,avatar,W.AVATAR)
    contexts[avatar]=avatars.base+AV.context+index*AV.stride
    W.write(contexts[avatar],W.u32(avatar)..W.u32(0)..W.u32(0)..W.u32(0x55))
    local f=flags or{}
    W.write(avatars.base+AV.flags+index*AV.stride,W.u32(f.f0lo or 0x20A)..W.u32(f.f0hi or 0x08040000)
        ..W.u32(f.f1lo or 0x8401)..W.u32(f.f1hi or 0))
    local slot=put(abilities,avatar,W.AVATAR)
    return function(new)W.write(avatars.base+AV.flags+index*AV.stride,W.u32(new.f0lo or 0x20A)
        ..W.u32(new.f0hi or 0x08040000)..W.u32(new.f1lo or 0x8401)..W.u32(new.f1hi or 0))end,slot
end
-- The fake game: needs_ammo answers `needs`; start_action records the request and runs the ability like the game.
local calls={queries={},starts={}}
local needs,starts_ok,runs=true,true,true
local ability_slot={}
equipment.set_adapter({
    needs_ammo=function(entry,user)
        assert(entry==W.GAME+D.natives.needsAmmo.rva,'needs_ammo through the wrong function')
        calls.queries[#calls.queries+1]=user
        return needs
    end,
    start_action=function(entry,context,ability,target,extra)
        assert(entry==W.GAME+D.natives.tryStartAction.rva,'the action was started through the wrong function')
        calls.starts[#calls.starts+1]={context=context,ability=ability,target=target,extra=extra}
        if starts_ok and runs then
            for avatar,address in pairs(contexts)do
                if address==context then
                    W.write(ability_records+ability_slot[avatar]*AB.stride,W.u32(ability))
                    W.write(ability_records+ability_slot[avatar]*AB.stride+AB.active,string.char(1))
                end
            end
        end
        return starts_ok
    end})
local set_flags,set_supplies
local function mission(opts)
    opts=opts or{}
    W.players({{peer=LOCAL,avatar=100},{peer=OTHER,avatar=101}},LOCAL)
    W.add{entity=100,type=W.AVATAR,unit=7100,health=125,owned=true,goid=100,life=opts.life}
    W.add{entity=101,type=W.AVATAR,unit=7101,health=125,owned=false,goid=101}
    for entity,kind in pairs({[605]=ERUPTOR,[607]=VERDICT,[700]=opts.pack or SUPPLY,[610]=MAXIGUN})do
        W.register_entity(entity,kind)
    end
    wear(100,{primary=605,secondary=607,support=opts.support,backpack=opts.no_pack and 0 or 700,throwable=GAS,count=4,
        hand=opts.hand,hand_type=opts.hand_type,selection=opts.selection})
    magazine(605,ERUPTOR,opts.spare or 2,3)
    magazine(607,VERDICT,10,9)
    set_supplies=deposit(700,opts.pack or SUPPLY,opts.supplies or 3)
    local slot
    set_flags,slot=avatar_context(100,opts.flags)
    ability_slot[100]=slot
    W.state(opts.state or 4,{host=true});tick()
end
local function resupply(player,opts)
    return in_update(function()
        local action
        hd2.events.run_as('mods/t/supply',function()action=hd2.actions.resupply_from_pack(player,opts)end)
        return action
    end)
end
'''


class PlayerEquipmentResearchTests(unittest.TestCase):
    def test_the_research_is_read_only_and_every_pin_holds_in_every_snapshot(self):
        self.assertEqual((RESEARCH['writes'], RESEARCH['nativeCalls'], RESEARCH['protectionChanges']), (0, 0, 0))
        self.assertFalse(any(RESEARCH['pinnedBytesMismatchPerSnapshot'].values()))
        self.assertEqual(len(RESEARCH['pinnedBytesMismatchPerSnapshot']), 7)
        self.assertTrue(RESEARCH['purity']['needsAmmo']['pure'])
        self.assertEqual(len(RESEARCH['purity']['needsAmmo']['functions']), 16)

    def test_the_inventory_slots_match_each_snapshots_actual_loadout(self):
        loadouts = {}
        for item in RESEARCH['observations']:
            for player in item['players']:
                if player.get('slots'):
                    loadouts[item['snapshot'][13:28]] = ({k: v['name'] for k, v in player['slots'].items()},
                        player['throwable']['name'], player['throwable']['count'])
        mission = ({'primary': 'R-36 Eruptor', 'secondary': 'P-113 Verdict', 'support': None, 'backpack': None,
            'held': None}, 'G-4 Gas', 4)
        self.assertEqual(loadouts['20260929T172647'], mission)
        self.assertEqual(loadouts['20260929T172918'], mission)
        self.assertEqual(loadouts['20260926T222226'][0]['primary'], 'JAR-5 Dominator')
        self.assertEqual(loadouts['20260927T155654'][0]['primary'], 'AR-23C Liberator Concussive')
        alive = next(o for o in RESEARCH['observations'] if 'host-alive' in o['snapshot'])['players'][0]
        self.assertEqual((alive['slots']['primary']['magazine']['spare'], alive['slots']['primary']['magazine']['rounds']),
            (6, 3))
        self.assertEqual(alive['actionContext']['fields'][:3], [602, 0, 0])
        self.assertTrue(alive['actionContext']['mayAct'])
        self.assertFalse(alive['actionContext']['busy'])

    def test_the_supply_pack_self_use_is_its_own_deposit_ability(self):
        supply = RESEARCH['supplyPack']
        self.assertEqual((supply['name'], supply['selfAbility'], supply['otherAbility'], supply['capacity'],
            supply['equipmentType']), ('B-1 Supply Pack', 2629, 2628, 4, 23))
        self.assertEqual(RESEARCH['tableMembers']['depositAbilityMembers'], {'32': ['AbilityId', 25],
            '36': ['AbilityId', 21]})
        self.assertFalse(RESEARCH['tableFacts'][supply['type']]['behavior'])
        for item in RESEARCH['observations']:
            resident = item['depositSettings'][supply['type']]
            self.assertEqual((resident['selfAbility'], resident['otherAbility'], resident['capacity']), (2629, 2628, 4))
        roles = {p['rva']: p['role'] for rows in RESEARCH['proofs'].values() for p in rows}
        self.assertIn('definition +0x24: the self-use ability', roles.values())
        self.assertEqual({p['role'] for p in RESEARCH['dataPins']}, {'ability dispatch table entry 2628 -> 0x115B79F',
            'ability dispatch table entry 2629 -> 0x115B7B0'})

    def test_confidence_labels_and_research_only_items(self):
        labels = {f['item']: f['confidence'] for f in RESEARCH['findings']}
        self.assertEqual(labels['inventory +0x0C worn backpack'], 'STRONG')
        self.assertEqual(labels['inventory +0x00 / +0x04 primary and secondary weapon'], 'CONFIRMED')
        self.assertTrue(set(labels.values()) <= {'CONFIRMED', 'STRONG', 'PLAUSIBLE', 'UNKNOWN'})
        self.assertEqual(set(RESEARCH['researchOnly']), {'shieldCharge', 'jumpPackRecharge', 'guardDogAmmo',
            'depositWrites', 'remotePlayers'})

    def test_the_domain_is_generated_from_the_research(self):
        import generate_player_equipment
        self.assertEqual(generate_player_equipment.generate(check=True), [])

    def test_runtime_never_writes_game_memory(self):
        for text in (SOURCE, API_SOURCE):
            for forbidden in ('runtime.write', 'WriteProcessMemory', 'ffi.copy', 'VirtualProtect', 'owned_block'):
                self.assertNotIn(forbidden, text)
        # The two native calls are the only casts, each guarded by its arguments.
        self.assertEqual(len(re.findall(r'ffi\.cast\(\'uint8_t \(\*\)', SOURCE)), 2)
        self.assertIn("ability==SP.selfAbility", SOURCE)


class PlayerEquipmentRuntimeTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(PRELUDE + body), b'ok')

    def test_loadout_reads_every_slot_structurally(self):
        self.lua(r'''
mission()
local me=hd2.local_player()
local l=assert(me:loadout())
assert(l.avatar_id==100 and l.primary.name=='R-36 Eruptor'and l.primary.kind=='primary'and l.primary.api=='hd2.weapon'
    and l.primary.entity_id==605,tostring(l.primary and l.primary.name))
assert(l.secondary.name=='P-113 Verdict'and l.secondary.kind=='secondary')
assert(l.support==nil and l.held==nil)
assert(l.backpack.name=='B-1 Supply Pack'and l.backpack.api=='hd2.backpack'and l.backpack.supply_pack==true)
local d=l.backpack.deposit
assert(d.amount==3 and d.capacity==4 and d.self_ability==2629 and d.other_ability==2628 and d.definition=='type'
    and d.owned==true,tostring(d.amount))
assert(l.throwable.name=='G-4 Gas'and l.throwable.count==4 and l.throwable.api=='hd2.throwable')
local pack=assert(me:backpack())
assert(pack.name=='B-1 Supply Pack'and pack.deposit.amount==3)
set_supplies(1)
assert(me:backpack().deposit.amount==1,'re-read on every call')
-- Another player's equipment is not read (unproven).
local other
for _,p in ipairs(hd2.players())do if not p:is_local_player()then other=p end end
local none,why=other:loadout()
assert(none==nil and why:find('NOT_LOCAL_PLAYER',1,true),why)
return 'ok'
''')

    def test_held_weapon_and_ammo(self):
        self.lua(r'''
mission({hand=605,hand_type=ERUPTOR,selection=1})
local me=hd2.local_player()
local held=assert(me:held_weapon())
assert(held.name=='R-36 Eruptor'and held.slot=='primary'and held.slot_proven and held.selection==1
    and held.entity_id==605,tostring(held.slot))
local ammo=assert(me:ammo())
assert(ammo.slot=='primary'and ammo.feed=='magazine'and ammo.rounds==3 and ammo.spare_magazines==2
    and ammo.capacity==5 and ammo.max_spare_magazines==6,tostring(ammo.capacity))
local side=assert(me:ammo('secondary'))
assert(side.name=='P-113 Verdict'and side.rounds==9 and side.spare_magazines==10)
local bad,why=me:ammo('backpack')
assert(bad==nil and why:find('INVALID_SLOT',1,true))
local empty,why2=me:ammo('support')
assert(empty==nil and why2:find('EMPTY_SLOT',1,true),why2)
return 'ok'
''')

    def test_a_backpack_fed_support_weapon_reads_its_backpack(self):
        self.lua(r'''
mission({support=610,pack=MAXIGUN_PACK,supplies=640})
local me=hd2.local_player()
local ammo=assert(me:ammo('support'))
assert(ammo.name=='M-1000 Maxigun'and ammo.feed=='backpack'and ammo.rounds==640 and ammo.capacity==1000,
    tostring(ammo.feed))
local l=me:loadout()
assert(l.support.kind=='support'and l.support.api=='hd2.support_weapon'and l.backpack.supply_pack==false)
return 'ok'
''')

    def test_the_self_use_is_requested_exactly_as_the_game_input_does(self):
        self.lua(r'''
mission()
local me=hd2.local_player()
local a=resupply(me)
assert(a.status=='requested',tostring(a.code)..' '..tostring(a.reason))
assert(a.owner=='mods/t/supply'and a.supplies==3 and a.capacity==4 and a.ability==2629 and a.backpack==700)
assert(#calls.queries==1 and calls.queries[1]==100,'needs_ammo(the wearer) asked first')
local s=calls.starts[1]
assert(#calls.starts==1 and s.context==contexts[100]and s.ability==2629 and s.target==0 and s.extra==0x55,
    'the request keeps the context\'s own extra value and no target')
assert(count('Supply Pack self-use requested on the local avatar 100 by mods/t/supply (3/4 supplies before)')==1)
local d=a:describe()
assert(d.kind=='resupply_from_pack'and d.status=='requested')
-- player:resupply_from_pack is the same action.
for _=1,20 do tick()end
local b=in_update(function()local r;hd2.events.run_as('mods/t/method',function()r=me:resupply_from_pack()end);return r end)
assert(b.status=='requested'and b.owner=='mods/t/method',tostring(b.code))
return 'ok'
''')

    def test_every_refusal_calls_nothing(self):
        self.lua(r'''
local function refused(a,code)
    assert(a.status=='refused'and a.code==code,'expected '..code..', got '..tostring(a.code)..': '..tostring(a.reason))
end
mission({state=3})
local me=hd2.local_player()
refused(resupply(me),'NOT_IN_MISSION')
W.state(4,{host=true});tick()
-- Outside the game update.
local outside
hd2.events.run_as('mods/t/out',function()outside=hd2.actions.resupply_from_pack(me)end)
refused(outside,'NOT_GAME_THREAD')
local other
for _,p in ipairs(hd2.players())do if not p:is_local_player()then other=p end end
refused(resupply(other),'NOT_LOCAL_PLAYER')
refused(resupply(me,{speed=2}),'INVALID_OPTION')
refused(resupply({}),'INVALID_TARGET')
assert(#calls.starts==0 and #calls.queries==0)
return 'ok'
''')

    def test_the_game_refusals_are_mirrored_before_any_call(self):
        self.lua(r'''
local function refused(a,code)
    assert(a.status=='refused'and a.code==code,'expected '..code..', got '..tostring(a.code)..': '..tostring(a.reason))
end
local n=0
local function try(code)
    n=n+1
    hd2.events.run_as('mods/t/'..n,function()end)
    local a=in_update(function()local r;hd2.events.run_as('mods/t/'..n,function()r=hd2.actions.resupply_from_pack(
        hd2.local_player())end);return r end)
    refused(a,code)
end
mission({supplies=0})
try('NO_SUPPLIES')
set_supplies(2)
set_flags({f1lo=0x8401+2^21})
try('BUSY')
set_flags({f0lo=0x208})
try('CANNOT_ACT')
set_flags({f1lo=0x8401+0x200})
try('CANNOT_ACT')
set_flags({})
needs=false
try('NO_AMMO_NEEDED')
assert(#calls.queries==1 and #calls.starts==0,'the only call so far is the pure query')
needs=true;starts_ok=false
try('NOT_STARTED')
starts_ok=true;runs=false
try('NOT_STARTED')
runs=true
-- A pin that no longer holds refuses everything, without a call.
local pin=D.pins[1]
W.write(W.GAME+pin.rva,'\204')
equipment.reset_for_tests()
equipment.set_adapter({needs_ammo=function()error('called')end,start_action=function()error('called')end})
try('RESUPPLY_UNAVAILABLE')
return 'ok'
''')

    def test_the_wrong_backpack_or_none(self):
        self.lua(r'''
mission({pack=DOG})
local a=resupply(hd2.local_player())
assert(a.code=='NOT_A_SUPPLY_PACK'and a.reason:find('AX/AR-23 Guard Dog',1,true),tostring(a.reason))
local pack=hd2.local_player():backpack()
assert(pack.name=='AX/AR-23 Guard Dog'and pack.deposit.amount==3 and pack.deposit.capacity==8 and not pack.supply_pack)
return 'ok'
''')

    def test_no_backpack_and_rate_limit(self):
        self.lua(r'''
mission({no_pack=true})
local me=hd2.local_player()
local a=resupply(me)
assert(a.code=='NO_BACKPACK',tostring(a.code))
local none,why=me:backpack()
assert(none==nil and why:find('NO_BACKPACK',1,true))
assert(me:loadout().backpack==nil)
-- The rate limit: one request at once per mod (the refused one above spent the token).
local b=resupply(me)
assert(b.code=='RATE_LIMITED',tostring(b.code))
return 'ok'
''')

    def test_without_a_live_process_nothing_is_called(self):
        self.lua(r'''
mission()
equipment.set_adapter(nil)
local a=resupply(hd2.local_player())
assert(a.code=='RESUPPLY_UNAVAILABLE'and a.reason:find('not a live game process',1,true),tostring(a.reason))
return 'ok'
''')


import build_profile  # noqa: E402


@unittest.skipUnless((build_profile.snapshot_directory() / 'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap')
    .is_file(), 'retained mission snapshots not available')
class PlayerEquipmentSnapshotTests(unittest.TestCase):
    """The production module on the retained snapshots: the same loadout the research observed, no native call."""

    def test_the_runtime_reads_each_snapshots_loadout(self):
        import validate_player_equipment_snapshot as validator
        result = validator.validate(['F5FEE03DCFDB-20260926T222226Z.hd2snap',
            'F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap',
            'F5FEE03DCFDB-20260929T173443Z-mission-end-transition.hd2snap'])
        self.assertEqual(result['status'], 'VALIDATED', json.dumps(result['failed']))
        alive = result['results']['F5FEE03DCFDB-20260929T172918Z-mission-host-alive.hd2snap']['report']
        self.assertEqual(alive['held'], {'entity': 605, 'name': 'R-36 Eruptor', 'slot': 'primary'})
        self.assertEqual(alive['ammo'], {'capacity': 5, 'feed': 'magazine', 'rounds': 3, 'spare': 6})
        self.assertIn('NO_BACKPACK', alive['inside'])

    def test_the_recorded_validation_covers_every_snapshot(self):
        recorded = json.loads((ROOT / 'validation/player-equipment-snapshot.json').read_text(encoding='utf-8'))
        self.assertEqual((recorded['status'], recorded['snapshots'], recorded['writes'], recorded['nativeCalls']),
            ('VALIDATED', 7, 0, 0))


if __name__ == '__main__':
    unittest.main()
