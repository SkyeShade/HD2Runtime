"""Mission-time slot conversion (development; docs/custom-stratagems.md, "Mission-time slot conversion";
research/stratagem-slot-conversion-F5FEE03DCFDB.json): the later of two loadout entries of a token type becomes an
owned, unselected carrier type in the local player's mission stratagem record, through one guarded 4-byte write, and
back. Offline: the event world with the record, the HUD list, the account catalogue and the in-flight call-ins."""
import json
import unittest

from support import ROOT, run
from test_stratagem_calldown_code import WORLD

RESEARCH = json.loads((ROOT / 'research/stratagem-slot-conversion-F5FEE03DCFDB.json').read_text(encoding='utf-8'))

SLOT = r"""
local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
local SLOTS=require('hd2runtime/domains/stratagem_slots')
slots.reset_for_tests()
local PRECISION_ID,BIG_ID=3523620028,1063322614
local SPEC={token='Orbital Precision Strike',carrier='Orbital 120mm HE Barrage'}
local function settle_job(handle)for _=1,400 do if handle.status~='pending'then break end;tick()end;return handle end
-- Unlimited uses, enabled and selectable rows for the token (118) and the carrier (136).
for _,kind in ipairs({118,136})do
    W.write(ROW[kind]+0x50,W.u32(4294967295))
    W.write(ROW[kind]+0x80,W.u32(2))
    W.write(ROW[kind]+0xC0,W.u32(1))
end
W.catalogue({[PRECISION_ID]=2,[BIG_ID]=2})
-- The mission record: defaults (granted), the loadout with two Precision Strikes, a mission-granted entry.
local RECORD={{type=124,uses=-1,granted=1},{type=33,uses=-1,granted=1},
    {type=118,uses=-1,granted=0},{type=118,uses=-1,granted=0},{type=22,uses=-1,granted=0},{type=130,uses=-1,granted=0},
    {type=41,uses=-1,granted=1}}
local function world_with(record)
    mission({host=true})
    local h=W.stratagem_hud({peer=LOCAL,slots={{type=124,code={}},{type=33,code={}},{type=118,code=NATIVE[118]},
        {type=118,code=NATIVE[118]},{type=22,code=NATIVE[22]},{type=130,code=NATIVE[130]},{type=41,code=NATIVE[41]}},
        record=record or RECORD})
    return h
end
local function entry_type(h,index)return b.u32(W.read(h.record+0x38+0x188+index*0x30,4),0)end
local function entries(h)return W.read(h.record+0x38+0x188,7*0x30)..W.read(h.record+0x38+0x788,4)end
"""


def lua(body):
    return run(WORLD + SLOT + body)


class SlotConversionResearchTests(unittest.TestCase):
    def test_the_research_and_its_domain(self):
        self.assertEqual((RESEARCH['writes'], RESEARCH['protectionChanges']), (0, 0))
        self.assertFalse(any(RESEARCH['pinnedBytesMismatchPerSnapshot'].values()))
        mission = [s for s in RESEARCH['snapshots'] if s['phase'] in ('alive', 'reinforced')]
        self.assertEqual(len(mission), 3)
        for s in mission:
            self.assertTrue(s['recordTypesHeld'])
            self.assertEqual(s['loadoutOrder'], 'saved order')
            self.assertFalse(s['carrier120mm']['packageResident'] or s['carrier120mm']['inRecord'])
            self.assertEqual(s['carrier120mm']['owned'], [1, 2])
        ended = next(s for s in RESEARCH['snapshots'] if s['phase'] == 'ended')
        self.assertEqual(ended['loadoutOrder'], 'reversed')                # rebuilt for the ship at the mission end
        self.assertIn('0x66E1E3', {('0x%X' % p['rva']) for p in RESEARCH['pins']['matcherResult']})
        import sys
        sys.path.insert(0, str(ROOT / 'scripts'))
        import generate_stratagem_slots
        self.assertEqual(generate_stratagem_slots.generate(check=True), [])


class SlotConversionTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(lua(body), b'ok')

    def test_the_later_token_entry_becomes_the_carrier_and_is_restored(self):
        self.check(r'''
local h=world_with()
local before=entries(h)
local SAVE=W.save_store and W.read(W.save_store,0x200)
local view=slots.inspect(world_module.open(),SPEC)
assert(#view.tokenEntries==2 and view.tokenEntries[1]==2 and view.tokenEntries[2]==3)
assert(view.carrierOwned and view.carrierSelectable and view.carrierEnabled and view.carrierUnlimited)
assert(not view.carrierInRecord and view.carrierPackage=='resident')
local job=settle_job(slots.convert(SPEC))
assert(job.status=='converted',tostring(job.code)..': '..tostring(job.reason))
assert(job.index==3 and entry_type(h,3)==136 and entry_type(h,2)==118)       -- the later duplicate only
assert(#W.runtime.writes==1 and W.runtime.writes[1].address==h.record+0x38+0x188+3*0x30)
for _,key in ipairs({'type','others','nonTarget','protection'})do assert(job.verify[key],key)end
local now=entries(h)
for i=1,#now do
    local at=i-1
    assert(now:byte(i)==before:byte(i)or(at>=3*0x30 and at<3*0x30+4),'record byte '..at..' changed')
end
assert(count('stratagem slot CONVERTED: entry 3 Orbital Precision Strike (type 118) -> Orbital 120mm HE Barrage (type 136), '
    ..'the local record of 7 entries: 1 write; entry reads the carrier: true; every other entry and the count unchanged: '
    ..'true; non-target bytes unchanged true; protection restored true; the saved loadout is not written')==1)
-- The vanilla HUD refreshes the slot from the type change: offline, the HUD slot is written as the game would.
assert(slots.hud_follows(world_module.open())==false)
local HS=require('hd2runtime/domains/stratagem_calldown').hud.slots
W.write(h.slots[3].address+HS.type,W.u32(136));W.write(h.slots[3].address+HS.displayedType,W.u32(136))
assert(slots.hud_follows(world_module.open())==true)
-- Restore: the token back, the record byte-identical.
local restored=settle_job(slots.restore())
assert(restored.status=='restored'and restored.exact and entries(h)==before and#W.runtime.writes==2,
    tostring(restored.code)..': '..tostring(restored.reason))
assert(count('stratagem slot RESTORED: entry 3 Orbital 120mm HE Barrage -> Orbital Precision Strike: 1 write; exact: true')==1)
-- The finalizer restores a conversion before the Lua state closes.
assert(settle_job(slots.convert(SPEC)).status=='converted')
slots.finalize_for_tests()
assert(entries(h)==before)
return 'ok'
''')

    def test_every_failed_guard_refuses_with_nothing_written(self):
        self.check(r'''
local function refused(code,text,spec)
    slots.reset_for_tests()
    local before=#(W.runtime.writes or{})
    local job=settle_job(slots.convert(spec or SPEC))
    assert(job.status=='refused'and job.code==code and(text==nil or tostring(job.reason):find(text,1,true)),
        code..' expected, got '..tostring(job.code)..': '..tostring(job.reason))
    assert(#(W.runtime.writes or{})==before,code)
end
-- Aboard the ship.
W.state(3)
local h=W.stratagem_hud({peer=LOCAL,slots={{type=118,code={}}},record=RECORD})
refused('NOT_IN_MISSION')
-- A client.
mission({host=false});h=world_with();mission({host=false})
refused('NOT_HOST')
-- One token only, the carrier already in the record, the token entry with limited uses.
local one={{type=124,uses=-1,granted=1},{type=118,uses=-1,granted=0},{type=22,uses=-1,granted=0},
    {type=118,uses=-1,granted=1}}
h=world_with(one);refused('NO_DUPLICATE_TOKEN','the loadout holds 1 Orbital Precision Strike')
local with_carrier={{type=118,uses=-1,granted=0},{type=118,uses=-1,granted=0},{type=136,uses=-1,granted=0}}
h=world_with(with_carrier);refused('CARRIER_IN_RECORD','already in the stratagem record (entry 2)')
local limited={{type=118,uses=-1,granted=0},{type=118,uses=3,granted=0}}
h=world_with(limited);refused('USES_DIFFER','the token entry has 3 uses')
-- A call-in of the token entry is in flight.
h=world_with()
W.call_ins({{key=W.RECORD_KEY,slot=3,done=0}})
refused('IN_USE','a call-in of entry 3 is in flight')
W.call_ins({{key=W.RECORD_KEY,slot=3,done=1}})
-- Not owned; not selectable; limited carrier uses.
W.catalogue({[PRECISION_ID]=2,[BIG_ID]=1})
refused('CARRIER_NOT_OWNED')
W.catalogue({[PRECISION_ID]=2,[BIG_ID]=4})
W.write(ROW[136]+0x80,W.u32(0));refused('CARRIER_NOT_SELECTABLE');W.write(ROW[136]+0x80,W.u32(2))
W.write(ROW[136]+0x50,W.u32(1));refused('USES_DIFFER','both have unlimited uses');W.write(ROW[136]+0x50,W.u32(4294967295))
-- The carrier's call-in package is not resident and this adapter cannot load it.
local package=require('hd2runtime/core/assets').dependency_for_stratagem(BIG_ID,'x').package
W.runtime.packages[package]='absent'
refused('ASSET_UNAVAILABLE')
W.runtime.packages[package]=nil
-- The same stratagem; an uncatalogued one; another build.
refused('SAME_STRATAGEM',nil,{token='Orbital 120mm HE Barrage',carrier='Orbital 120mm HE Barrage'})
refused('UNKNOWN_STRATAGEM',nil,{token='Orbital Precision Strike',carrier='No Such Stratagem'})
local pin=SLOTS.pins[1]
local original=W.read(W.GAME+pin.rva,1)
W.write(W.GAME+pin.rva,string.char(0xCC))
refused('UNSUPPORTED_BUILD','stratagem record code changed')
W.write(W.GAME+pin.rva,original)
-- Converted once: a second conversion is refused until restored.
slots.reset_for_tests()
assert(settle_job(slots.convert(SPEC)).status=='converted')
local job=settle_job(slots.convert(SPEC))
assert(job.status=='refused'and job.code=='ALREADY_CONVERTED')
return 'ok'
''')

    def test_a_game_rebuild_discards_the_conversion_and_nothing_is_restored(self):
        self.check(r'''
local h=world_with()
assert(settle_job(slots.convert(SPEC)).status=='converted')
-- The game rebuilds the record (the mission end transition: the loadout only, reversed).
W.write(h.record+0x38+0x188,W.u32(130));W.write(h.record+0x38+0x188+0x30,W.u32(22))
W.write(h.record+0x38+0x188+0x60,W.u32(118));W.write(h.record+0x38+0x188+0x90,W.u32(118))
W.write(h.record+0x38+0x788,W.u32(4))
for _=1,10 do tick()end
assert(count('stratagem slot entry 3 no longer holds Orbital 120mm HE Barrage (the record changed): the game rebuilt the '
    ..'stratagem record; nothing to restore')==1)
local writes=#W.runtime.writes
local job=settle_job(slots.restore())
assert(job.status=='refused'and job.code=='NOT_CONVERTED'and#W.runtime.writes==writes)
return 'ok'
''')

    def test_not_public(self):
        self.check(r'''
local api=require('mods/skyeshade/hd2runtime')
for key in pairs(api)do assert(not tostring(key):find('slot_conversion',1,true),key)end
return 'ok'
''')



def virtual_proof_addon():
    from test_event_scripting import SDK
    folder = ROOT / 'proof/VirtualSlotProof'
    spec = json.loads((folder / 'hd2runtime.json').read_text(encoding='utf-8'))
    body = (folder / 'src/addon.lua').read_text(encoding='utf-8-sig')
    return spec['resource'], SDK.wrap_addon(spec['resource'], spec['requires']['hd2runtime']['min_version'], body)


class VirtualSlotProofAddonTests(unittest.TestCase):
    '''proof/VirtualSlotProof 0.1.0: the second Precision Strike slot becomes the 120mm in a solo mission, through the
    development slot conversion only; read-only probe and HUD follow check; its toggle restores.'''

    def lua(self, body):
        from support import lua as lua_literal
        from test_stratagem_calldown_code import PROOF
        resource, addon = virtual_proof_addon()
        self.assertEqual(resource, 'mods/skyeshade/hd2runtime_virtual_slot_proof')
        self.assertEqual(run(WORLD + SLOT + 'local ADDON=' + lua_literal(addon) + '\nlocal RESOURCE='
            + lua_literal(resource) + PROOF + body), b'ok')

    def test_the_build_uses_only_the_development_conversion(self):
        folder = ROOT / 'proof/VirtualSlotProof'
        self.assertEqual((folder / 'VERSION').read_text(encoding='utf-8').strip(), '0.1.0')
        body = (folder / 'src/addon.lua').read_text(encoding='utf-8-sig')
        self.assertIn("local BUILD='0.1.0 VIRTUAL-SLOT-CONVERSION'", body)
        code = '\n'.join(line.split('--')[0] for line in body.splitlines())
        self.assertEqual(code.count('slots.convert('), 1)
        self.assertEqual(code.count('slots.restore('), 1)
        for forbidden in ('hd2.ensure(', 'hd2.patch(', 'hd2.transaction(', 'hd2.plan(', '.write(', 'owned_write',
                'transaction.apply', 'presentation', 'calldown_code', 'hd2.resources'):
            self.assertNotIn(forbidden, code)

    def test_the_second_precision_strike_becomes_the_120mm_and_is_restored(self):
        self.lua(r'''
rawset(_G,'ModOptionsMenu',MENU)
require('hd2runtime/runtime/stratagem_loadout').reset_for_tests()
W.saved_loadout({{id=PRECISION_ID},{id=PRECISION_ID},{id=2281932031}})
proof()
tick(20)
assert(count('VirtualSlotProof 0.1.0 VIRTUAL-SLOT-CONVERSION BUILD')==1)
assert(count('two Orbital Precision Strikes saved: the second becomes the 120mm in the mission')==1)
local h=world_with()
local before=entries(h)
tick(120)
assert(count('slot probe: 2 Orbital Precision Strike loadout entries; carrier Orbital 120mm HE Barrage: owned true, '
    ..'selectable true, enabled true, unlimited true, in the record false, call-in package resident; 1 stratagem records')==1)
assert(count('stratagem slot CONVERTED: entry 3 Orbital Precision Strike (type 118) -> Orbital 120mm HE Barrage (type 136)')==1)
assert(count('CONVERTED in the mission: record entry 3')==1)
assert(entry_type(h,3)==136 and entry_type(h,2)==118 and#W.runtime.writes==1)
-- The vanilla HUD refreshes the slot (offline: written as the game would); the proof only reads it.
local HS=require('hd2runtime/domains/stratagem_calldown').hud.slots
W.write(h.slots[3].address+HS.type,W.u32(136));W.write(h.slots[3].address+HS.displayedType,W.u32(136))
tick(20)
assert(count('HUD slot 3 now holds Orbital 120mm HE Barrage (the vanilla HUD refreshed it from the type change')==1)
press('F9')
assert(count('F9 [0.1.0 VIRTUAL-SLOT-CONVERSION]: conversion converted (attempts 1), toggle on; converted entry 3')==1)
-- The toggle off restores the token in the mission.
callbacks['virtual_slot_proof.convert'](false,'virtual_slot_proof.convert')
tick(20)
assert(count('stratagem slot RESTORED: entry 3 Orbital 120mm HE Barrage -> Orbital Precision Strike: 1 write; exact: true')==1)
assert(entries(h)==before and#W.runtime.writes==2 and count('callback failed')==0)
return 'ok'
''')

    def test_one_precision_strike_refuses_and_writes_nothing(self):
        self.lua(r'''
rawset(_G,'ModOptionsMenu',MENU)
local h=world_with({{type=124,uses=-1,granted=1},{type=118,uses=-1,granted=0},{type=22,uses=-1,granted=0}})
proof()
tick(140)
assert(count('conversion REFUSED (nothing written): NO_DUPLICATE_TOKEN')==1 and#(W.runtime.writes or{})==0)
return 'ok'
''')

    def test_without_mod_options_menu_nothing_is_converted(self):
        self.lua(r'''
rawset(_G,'ModOptionsMenu',nil)
local h=world_with()
proof()
tick(140)
assert(count('Mod Options Menu unavailable: nothing is converted')==1 and#(W.runtime.writes or{})==0)
return 'ok'
''')


# The custom stratagem selector's conversion (convert_virtual): exactly the loadout slots the Runtime records as virtual
# instances, in a mission loadout that is exactly the recorded order. Loadout: GAS / native PRECISION / Eagle (22) / GAS.
VIRTUAL = r"""
local ID22,ID130=2281932031,1298599997
local VSPEC={definition='orbital_gas_barrage',token='Orbital Precision Strike',carrier='Orbital 120mm HE Barrage',
    slots={0,3},order={PRECISION_ID,PRECISION_ID,ID22,PRECISION_ID}}
local VRECORD={{type=124,uses=-1,granted=1},{type=33,uses=-1,granted=1},
    {type=118,uses=-1,granted=0},{type=118,uses=-1,granted=0},{type=22,uses=-1,granted=0},{type=118,uses=-1,granted=0},
    {type=41,uses=-1,granted=1}}
local function vworld(record)
    mission({host=true})
    local hud={}
    for k,e in ipairs(record or VRECORD)do hud[k]={type=e.type,code={}}end
    return W.stratagem_hud({peer=LOCAL,slots=hud,record=record or VRECORD})
end
local function copy(spec,changes)local out={};for k,v in pairs(spec)do out[k]=v end
    for k,v in pairs(changes or{})do out[k]=v end;return out end
"""


def virtual(body):
    return run(WORLD + SLOT + VIRTUAL + body)


class VirtualSlotConversionTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(virtual(body), b'ok')

    def test_exactly_the_virtual_slots_become_the_carrier_in_one_transaction(self):
        self.check(r"""
local h=vworld()
local before=W.read(h.record+0x38+0x188,7*0x30)
local rows=W.read(settings.base,settings.size)
local writes=#W.runtime.writes
local job=settle_job(slots.convert_virtual(VSPEC))
assert(job.status=='converted',tostring(job.code)..' '..tostring(job.reason))
assert(job.indices[1]==2 and job.indices[2]==5 and#job.indices==2 and job.slots[1]==0 and job.slots[2]==3)
-- Loadout slots 0 and 3 (record entries 2 and 5) are the 120mm; the native Precision Strike (slot 1, entry 3), the
-- Eagle and the granted entries are untouched.
assert(entry_type(h,2)==136 and entry_type(h,5)==136 and entry_type(h,3)==118 and entry_type(h,4)==22)
assert(entry_type(h,0)==124 and entry_type(h,1)==33 and entry_type(h,6)==41)
assert(#W.runtime.writes==writes+2,'one transaction, two 4-byte writes')
local now=W.read(h.record+0x38+0x188,7*0x30)
for i=1,#now do
    local at=i-1
    assert(now:byte(i)==before:byte(i)or(at>=2*0x30 and at<2*0x30+4)or(at>=5*0x30 and at<5*0x30+4),'byte '..at)
end
assert(count('stratagem slot CONVERTED: virtual orbital_gas_barrage: loadout slots 0, 3 = record entries 2, 5: Orbital '
    ..'Precision Strike (type 118) -> Orbital 120mm HE Barrage (type 136, stable id 1063322614), the local record of 7 '
    ..'entries: 2 writes; each entry reads the carrier: true; every other entry and the count unchanged: true; '
    ..'non-target bytes unchanged true; protection restored true; the carrier\'s call-in package resident; the saved '
    ..'loadout is not written')==1,table.concat(logged,' | '))
-- The HUD draws entry k in its slot k: both converted slots now hold the carrier (written as the game would).
local HS=require('hd2runtime/domains/stratagem_calldown').hud.slots
for _,index in ipairs({2,5})do W.write(h.slots[index].address+HS.type,W.u32(136))end
local types=slots.hud_types(world_module.open())
assert(types[2]==136 and types[5]==136)
-- Observed: a call-in of slot 3's entry in flight, then its cooldown.
local seen=slots.observe(world_module.open())
assert(#seen==2 and seen[1].index==2 and seen[1].type==136 and seen[1].flying==false)
W.call_ins({{key=W.RECORD_KEY,slot=5,done=0}})
seen=slots.observe(world_module.open())
assert(seen[2].index==5 and seen[2].flying==true and seen[1].flying==false)
W.call_ins({{key=W.RECORD_KEY,slot=5,done=1}})
-- Restore (the finalizer's path): both back to the token in one transaction, exactly.
local restored=settle_job(slots.restore())
assert(restored.status=='restored'and restored.exact and entry_type(h,2)==118 and entry_type(h,5)==118)
assert(W.read(h.record+0x38+0x188,7*0x30)==before)
assert(W.read(settings.base,settings.size)==rows,'no StratagemInfo write')
return 'ok'
""")

    def test_one_virtual_slot_needs_no_duplicate(self):
        self.check(r"""
local record={{type=124,uses=-1,granted=1},{type=118,uses=-1,granted=0},{type=22,uses=-1,granted=0}}
local h=vworld(record)
local job=settle_job(slots.convert_virtual(copy(VSPEC,{slots={0},order={PRECISION_ID,ID22}})))
assert(job.status=='converted'and job.indices[1]==1 and entry_type(h,1)==136 and entry_type(h,2)==22,
    tostring(job.code)..' '..tostring(job.reason))
return 'ok'
""")

    def test_every_failed_guard_refuses_with_nothing_written_and_never_another_slot(self):
        self.check(r"""
local function refused(code,text,spec,record)
    slots.reset_for_tests()
    local h=vworld(record)
    local before=#W.runtime.writes
    local job=settle_job(slots.convert_virtual(spec or VSPEC))
    assert(job.status=='refused'and job.code==code and(text==nil or tostring(job.reason):find(text,1,true)),
        code..' expected, got '..tostring(job.code)..': '..tostring(job.reason))
    assert(#W.runtime.writes==before,code..' wrote')
    for k=0,#(record or VRECORD)-1 do
        assert(entry_type(h,k)==(record or VRECORD)[k+1].type,code..': entry '..k..' changed')
    end
end
refused('NO_VIRTUAL_SLOT','no virtual slot holds orbital_gas_barrage',{definition='orbital_gas_barrage',
    reason='no virtual slot holds orbital_gas_barrage'})
refused('BAD_SPEC','ascending',copy(VSPEC,{slots={3,0}}))
refused('BAD_SPEC','ascending',copy(VSPEC,{slots={4}}))
refused('BAD_SPEC','does not hold the token at loadout slot 2',copy(VSPEC,{slots={2}}))
-- The mission loadout is not the recorded order: another stratagem in a slot; one stratagem more.
refused('IDENTITY_CHANGED','loadout slot 2 holds',copy(VSPEC,{order={PRECISION_ID,PRECISION_ID,ID130,PRECISION_ID}}))
refused('IDENTITY_CHANGED','the virtual slots were recorded in a loadout of 3',copy(VSPEC,{slots={0},
    order={PRECISION_ID,PRECISION_ID,ID22}}))
-- A native 120mm in the record; a virtual entry with limited uses; a call-in of a virtual entry in flight.
local with_carrier={{type=118,uses=-1,granted=0},{type=118,uses=-1,granted=0},{type=22,uses=-1,granted=0},
    {type=118,uses=-1,granted=0},{type=136,uses=-1,granted=1}}
refused('CARRIER_IN_RECORD','already in the stratagem record (entry 4)',nil,with_carrier)
local limited={{type=118,uses=-1,granted=0},{type=118,uses=-1,granted=0},{type=22,uses=-1,granted=0},
    {type=118,uses=2,granted=0}}
refused('USES_DIFFER','entry 3 has 2 uses',nil,limited)
W.call_ins({{key=W.RECORD_KEY,slot=5,done=0}})
refused('IN_USE','a call-in of entry 5 is in flight')
W.call_ins({{key=W.RECORD_KEY,slot=5,done=1}})
-- Aboard the ship; a client.
slots.reset_for_tests()
W.state(3)
local before=#W.runtime.writes
local job=settle_job(slots.convert_virtual(VSPEC))
assert(job.code=='NOT_IN_MISSION'and#W.runtime.writes==before)
mission({host=false})
job=settle_job(slots.convert_virtual(VSPEC))
assert(job.code=='NOT_HOST'and#W.runtime.writes==before)
return 'ok'
""")

    def test_the_mission_end_rebuild_discards_every_converted_entry(self):
        self.check(r"""
local h=vworld()
assert(settle_job(slots.convert_virtual(VSPEC)).status=='converted')
-- The game rebuilds the record (the mission end transition: the loadout only, reversed).
W.write(h.record+0x38+0x188,W.u32(118));W.write(h.record+0x38+0x188+0x30,W.u32(22))
W.write(h.record+0x38+0x188+0x60,W.u32(118));W.write(h.record+0x38+0x188+0x90,W.u32(118))
W.write(h.record+0x38+0x788,W.u32(4))
for _=1,10 do tick()end
assert(count('stratagem slot entries 2, 5 no longer hold Orbital 120mm HE Barrage (the record changed): the game '
    ..'rebuilt the stratagem record; nothing to restore')==1,table.concat(logged,' | '))
assert(not slots.state().converted)
local writes=#W.runtime.writes
assert(settle_job(slots.restore()).code=='NOT_CONVERTED'and#W.runtime.writes==writes)
return 'ok'
""")


class CarrierChoiceTests(unittest.TestCase):
    """The carrier is not the donor: a definition lists candidate carriers and the first one every carrier guard accepts,
    and that the player does not have, is chosen (stratagem_slot_conversion.choose_carrier). Offline the Orbital Gas
    Strike (type 41) stands in for a candidate carrier other than the 120mm."""

    def check(self, body):
        self.assertEqual(virtual(body), b'ok')

    def test_the_first_eligible_candidate_is_chosen_and_the_virtual_slot_converts_to_it(self):
        self.check(r"""
local GAS_STRIKE=3193297673
W.write(ROW[41]+0x50,W.u32(4294967295));W.write(ROW[41]+0x80,W.u32(2));W.write(ROW[41]+0xC0,W.u32(1))
W.catalogue({[PRECISION_ID]=2,[BIG_ID]=2,[GAS_STRIKE]=2})
local CANDIDATES={'Orbital 120mm HE Barrage','Orbital Gas Strike'}
local w=world_module.open()
-- The player has the first candidate: the next one.
local name,types,passed=slots.choose_carrier(w,'Orbital Precision Strike',CANDIDATES,{[BIG_ID]=true})
assert(name=='Orbital Gas Strike'and types.carrier==41 and types.carrierId==GAS_STRIKE)
assert(#passed==1 and passed[1].carrier=='Orbital 120mm HE Barrage'and passed[1].code=='CARRIER_PRESENT')
-- The first candidate not owned: the next one; none eligible: nothing, every reason kept.
W.catalogue({[PRECISION_ID]=2,[BIG_ID]=1,[GAS_STRIKE]=2})
name,types,passed=slots.choose_carrier(w,'Orbital Precision Strike',CANDIDATES)
assert(name=='Orbital Gas Strike'and passed[1].code=='CARRIER_NOT_OWNED')
W.write(ROW[41]+0x80,W.u32(0))
name,types,passed=slots.choose_carrier(w,'Orbital Precision Strike',CANDIDATES)
assert(name==nil and#passed==2 and passed[2].code=='CARRIER_NOT_SELECTABLE')
W.write(ROW[41]+0x80,W.u32(2))
-- The token is never a carrier.
name,types,passed=slots.choose_carrier(w,'Orbital Precision Strike',{'Orbital Precision Strike'})
assert(name==nil and passed[1].code=='SAME_STRATAGEM')
-- The virtual slot becomes the chosen carrier (not the 120mm); the native Precision Strike stays.
local record={{type=124,uses=-1,granted=1},{type=118,uses=-1,granted=0},{type=118,uses=-1,granted=0},
    {type=22,uses=-1,granted=0}}
local h=vworld(record)
local job=settle_job(slots.convert_virtual(copy(VSPEC,{carrier='Orbital Gas Strike',slots={0},
    order={PRECISION_ID,PRECISION_ID,ID22}})))
assert(job.status=='converted'and job.carrier==41 and job.carrierId==GAS_STRIKE,tostring(job.code)..' '..tostring(job.reason))
assert(entry_type(h,1)==41 and entry_type(h,2)==118 and entry_type(h,3)==22)
assert(count('stratagem slot CONVERTED: virtual orbital_gas_barrage: loadout slot 0 = record entry 1: Orbital Precision '
    ..'Strike (type 118) -> Orbital Gas Strike (type 41, stable id 3193297673)')==1)
return 'ok'
""")

    def test_a_definition_lists_carriers_and_the_selector_converts_to_the_chosen_one(self):
        self.check(r"""
local virtual=require('hd2runtime/runtime/virtual_stratagems')
virtual.reset_for_tests()
local texts=require('hd2runtime/runtime/text_resources')
local images=require('hd2runtime/runtime/image_resources')
local MOD='mods/skyeshade/carrier_test'
local D=virtual.define({id='orbital_gas_barrage',display={name=texts.handle('n','Orbital Gas Barrage',MOD),
    description=texts.handle('d','Gas.',MOD),icon=images.handle('i',MOD)},selection={token='Orbital Precision Strike'},
    mission={carriers={'Orbital Gas Strike','Orbital 120mm HE Barrage'}}},MOD)
assert(D.mission.carrier=='Orbital Gas Strike'and#D.mission.carriers==2 and D.mission.carriers[2]=='Orbital 120mm HE Barrage')
assert(D.mission.carrierIds[1]==3193297673 and D.mission.carrierIds[2]==BIG_ID)
-- Refused definitions: no carrier, both forms, the token as a carrier, a repeat.
local function refused(mission,text)
    virtual.reset_for_tests()
    local ok,why=pcall(virtual.define,{id='x',display={name=texts.handle('n2','N',MOD),description=texts.handle('d2','D',MOD),
        icon=images.handle('i2',MOD)},selection={token='Orbital Precision Strike'},mission=mission},MOD)
    assert(not ok and tostring(why):find(text,1,true),tostring(why))
end
refused({},'mission needs carrier or carriers')
refused({carrier='Orbital Gas Strike',carriers={'Orbital Gas Strike'}},'mission needs carrier or carriers')
refused({carriers={'Orbital Precision Strike'}},'the carrier must differ from the token')
refused({carriers={'Orbital Gas Strike','Orbital Gas Strike'}},'lists Orbital Gas Strike twice')
-- The selector's spec takes only a listed carrier.
virtual.reset_for_tests()
virtual.define({id='orbital_gas_barrage',display={name=texts.handle('n3','Orbital Gas Barrage',MOD),
    description=texts.handle('d3','Gas.',MOD),icon=images.handle('i3',MOD)},selection={token='Orbital Precision Strike'},
    mission={carriers={'Orbital Gas Strike','Orbital 120mm HE Barrage'}}},MOD)
local selector=require('hd2runtime/runtime/stratagem_selector')
local spec,why=selector.conversion_spec('orbital_gas_barrage','Orbital Napalm Barrage')
assert(spec==nil and why:find('is not a carrier of orbital_gas_barrage',1,true))
return 'ok'
""")

    def test_the_discovery_checks_every_owned_stratagem_and_ranks_orbitals_first(self):
        self.check(r"""
local GAS_STRIKE,RELAY,RECOILLESS=3193297673,2281932031,1298599997
for _,kind in ipairs({41,22,130})do
    W.write(ROW[kind]+0x50,W.u32(4294967295));W.write(ROW[kind]+0x80,W.u32(2));W.write(ROW[kind]+0xC0,W.u32(1))
end
local w=world_module.open()
local function find(found,name)for _,c in ipairs(found.candidates)do if c.name==name then return c end end end
-- Not ready while the account catalogue does not show the token as owned: nothing is trusted.
W.catalogue({[BIG_ID]=2,[GAS_STRIKE]=2,[RELAY]=2,[RECOILLESS]=2})
local found=slots.discover_carriers(w,'Orbital Precision Strike',{exclude={'Orbital 120mm HE Barrage'}})
assert(not found.ready and found.reason:find('does not show the token Orbital Precision Strike as owned',1,true)
    and#found.candidates==0 and found.chosen==nil)
-- Ready: every catalogued stratagem with a row is checked; the token is never a candidate; the donor is excluded.
W.catalogue({[PRECISION_ID]=2,[BIG_ID]=2,[GAS_STRIKE]=2,[RELAY]=2,[RECOILLESS]=2})
found=slots.discover_carriers(w,'Orbital Precision Strike',{exclude={'Orbital 120mm HE Barrage'}})
assert(found.ready and find(found,'Orbital Precision Strike')==nil)
local donor=find(found,'Orbital 120mm HE Barrage')
assert(not donor.eligible and donor.reasons[1]:find('excluded',1,true))
-- Ranked: the orbital bombardment first, then the emplacement, then the support weapon.
local gas,relay,rr=find(found,'Orbital Gas Strike'),find(found,'FX-12 Shield Generator Relay'),find(found,'GR-8 Recoilless Rifle')
assert(gas.eligible and gas.class==1 and gas.component=='BombardmentComponentData')
assert(relay.class==3 and rr.class==4)
assert(found.chosen==gas and found.candidates[1]==gas)
-- In the loadout: rejected, the next one chosen; not owned: rejected with the catalogue's evidence.
found=slots.discover_carriers(w,'Orbital Precision Strike',{present={[GAS_STRIKE]=true},exclude={'Orbital 120mm HE Barrage'}})
assert(not find(found,'Orbital Gas Strike').eligible and find(found,'Orbital Gas Strike').inLoadout)
assert(found.chosen and found.chosen.class>1)
W.catalogue({[PRECISION_ID]=2,[BIG_ID]=2,[GAS_STRIKE]=1})
found=slots.discover_carriers(w,'Orbital Precision Strike',{exclude={'Orbital 120mm HE Barrage'}})
local g=find(found,'Orbital Gas Strike')
assert(not g.eligible and not g.owned and g.ownership.found and g.ownership.state==1)
assert(#W.runtime.writes==0,'read-only')
return 'ok'
""")


    def test_a_cached_carrier_is_validated_with_the_discoverys_own_guards(self):
        self.check(r"""
local GAS_STRIKE=3193297673
W.write(ROW[41]+0x50,W.u32(4294967295));W.write(ROW[41]+0x80,W.u32(2));W.write(ROW[41]+0xC0,W.u32(1))
W.catalogue({[PRECISION_ID]=2,[BIG_ID]=2,[GAS_STRIKE]=2})
local w=world_module.open()
local OPTS={exclude={'Orbital 120mm HE Barrage'}}
local function v(present)
    return slots.validate_carrier(w,'Orbital Precision Strike','Orbital Gas Strike',{present=present,exclude=OPTS.exclude})
end
local function codes(r)return table.concat(r.codes,',')end
-- Valid now: the same verdict as the discovery's.
local r=v()
local found=slots.discover_carriers(w,'Orbital Precision Strike',OPTS)
assert(r.ready and r.valid and#r.codes==0 and found.chosen.name=='Orbital Gas Strike')
-- Every invalidation reason, one at a time, each with its code (read now, nothing cached).
assert(codes(v({[GAS_STRIKE]=true}))=='in_loadout')
W.write(ROW[41]+0x80,W.u32(0));assert(codes(v())=='not_selectable');W.write(ROW[41]+0x80,W.u32(2))
W.write(ROW[41]+0xC0,W.u32(0));assert(codes(v())=='disabled');W.write(ROW[41]+0xC0,W.u32(1))
W.write(ROW[41]+0x50,W.u32(3));assert(codes(v())=='limited_use');W.write(ROW[41]+0x50,W.u32(4294967295))
W.catalogue({[PRECISION_ID]=2,[BIG_ID]=2,[GAS_STRIKE]=1});assert(codes(v())=='not_owned')
W.catalogue({[PRECISION_ID]=2,[BIG_ID]=2,[GAS_STRIKE]=2})
assert(v().valid)
-- The donor, the token, and a payload the carrier is not compatible with.
local donor=slots.validate_carrier(w,'Orbital Precision Strike','Orbital 120mm HE Barrage',OPTS)
assert(donor.ready and not donor.valid and codes(donor):find('donor',1,true))
local token=slots.validate_carrier(w,'Orbital Precision Strike','Orbital Precision Strike',OPTS)
assert(not token.valid and codes(token)=='token')
local paid=slots.validate_carrier(w,'Orbital Precision Strike','Orbital Gas Strike',{exclude=OPTS.exclude,
    payload={donor='Orbital 120mm HE Barrage'}})
assert(not paid.valid and codes(paid)=='not_payload_compatible')
-- Not ready (the catalogue does not show the token as owned): nothing to trust, never a verdict.
W.catalogue({[BIG_ID]=2,[GAS_STRIKE]=2})
r=v()
assert(not r.ready and not r.valid and r.reason:find('does not show the token',1,true))
assert(#W.runtime.writes==0,'read-only')
return 'ok'
""")

if __name__ == '__main__':
    unittest.main()
