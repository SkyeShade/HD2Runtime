"""The carrier-in-slot probe (2026-10-07; runtime/carrier_in_slot.lua, stratagem_selector.select opts.carrier and
adopt_virtual, stratagem_slot_conversion.adopt_virtual, custom_stratagems selection = 'carrier'): a custom stratagem
picked into its loadout slot as its CARRIER itself, not the Orbital Precision Strike token:
  * the pick: the same guarded loadout-record write, the carrier's type and unlimited uses; the virtual slot records
    the carrier's stable id (tracking and reconstruction unchanged); a carrier that is not owned is refused;
  * the allocation: a carrier held only in the player's own carrier slots is not a native pick (never invalidating
    itself); held anywhere else (another slot, another player) it still is;
  * the mission: nothing converted: the slots are verified and adopted (cooldowns find them), a token in the slot,
    another order or limited uses refused; the restore writes nothing back;
  * the timing: the presentation is applied on the loading screen or before the HUD is populated, once; the HUD's
    population is logged against it; nothing without carrier slots;
  * the orchestrator: selection = 'carrier' registers (and anything else is refused); a mission refuses it with
    several players, mixed slots, or a slot carrier that is no longer its carrier."""
import unittest

from support import run
from test_stratagem_calldown_code import WORLD
from test_stratagem_selector import SELECT
from test_stratagem_slot_conversion import SLOT, VIRTUAL


class ProbeModuleTests(unittest.TestCase):
    def test_own_carriers_discount_and_slots(self):
        self.assertEqual(run(WORLD + r'''
local probe=require('hd2runtime/runtime/carrier_in_slot');probe.reset_for_tests()
local C,T,X=1063322614,3523620028,2281932031
local set={slots={[0]={definition='p',token=C,type=136,carrier=true},[2]={definition='q',token=T,type=118}},pairs={}}
-- Slot 0 holds the carrier for p (a carrier slot); slot 2 the token for q; slot 1 a native pick.
local own=probe.own_carriers({C,X,T},set)
assert(own[C]and not own[T]and not own[X])
-- Also natively picked in another slot, or by another player: still a native pick.
assert(next(probe.own_carriers({C,C,T},set))==nil)
assert(next(probe.own_carriers({C,X,T},set,{[C]=true}))==nil)
local present,removed=probe.discount({[C]=true,[X]=true,[T]=true},own)
assert(not present[C]and present[X]and present[T]and#removed==1 and removed[1]==C)
local by=probe.slots_by_definition(set)
assert(by.p and by.p.id==C and by.p.slots[1]==0 and by.q==nil)
assert(probe.enabled({selection='carrier'})and not probe.enabled({}))
return 'ok'
'''), b'ok')

    def test_the_early_presentation_and_the_timing(self):
        self.assertEqual(run(WORLD + r'''
local probe=require('hd2runtime/runtime/carrier_in_slot');probe.reset_for_tests()
local cp=require('hd2runtime/runtime/carrier_presentation')
local applied,callbacks={},{}
cp.applied=function(name)return applied[name]==true end
cp.apply=function(spec,cb)callbacks[#callbacks+1]={spec=spec,cb=cb};return {status='pending'}end
local log_module=require('hd2runtime/runtime/log')
local lines={}
log_module.emit=function(t)lines[#lines+1]=t end
local function said(text)for _,l in ipairs(lines)do if l:find(text,1,true)then return true end end return false end
local C=1063322614
local set={slots={[1]={definition='p',token=C,type=136,carrier=true}},pairs={}}
local defs={p={id='p',texts={name='T'},icon='I',code={'up'}}}
local hud=false
local function ctx(name,mission,clock,players)
    return {game={name=name,mission=mission},clock=clock,definitions=defs,set=set,players=players or 1,
        carrier_name=function(id)return id==C and'Orbital 120mm HE Barrage'or nil end,hud=function()return hud end}
end
-- Aboard the ship: only the timing (no presentation: the carrier is native there).
probe.step(ctx('Ship',false,1))
assert(#callbacks==0)
-- The loading screen: the presentation is applied once, on the slot's carrier.
probe.step(ctx('PrepareMission',false,2))
probe.step(ctx('PrepareMission',false,2.5))
assert(#callbacks==1 and callbacks[1].spec.carrier=='Orbital 120mm HE Barrage'and callbacks[1].spec.code[1]=='up')
assert(probe.waiting('p')and probe.entering()and not probe.early('p','Orbital 120mm HE Barrage'))
callbacks[1].cb({status='applied'})
applied['Orbital 120mm HE Barrage']=true
assert(probe.early('p','Orbital 120mm HE Barrage')and not probe.waiting('p'))
assert(said('TIMING: game state Ship -> PrepareMission at 2.00 s'))
assert(said('p: applying the presentation on its carrier Orbital 120mm HE Barrage during PrepareMission at 2.00 s'))
-- The mission: nothing applied again; the HUD's population is logged against it.
probe.step(ctx('Mission',true,4))
hud=true
probe.step(ctx('Mission',true,5))
assert(#callbacks==1)
assert(said('TIMING: the mission HUD is populated at 5.00 s; p presented at 2.00 s during PrepareMission'))
-- Back aboard the ship: forgotten.
probe.step(ctx('Ship',false,9))
assert(not probe.entering())
-- Without a loading-screen update: applied in the mission before the HUD; never with several players.
probe.reset_for_tests();applied={};callbacks={};hud=false
probe.step(ctx('Mission',true,1,2))
assert(#callbacks==0,'several players: nothing')
probe.step(ctx('Mission',true,1))
assert(#callbacks==1)
-- No carrier slot: nothing at all.
probe.reset_for_tests();callbacks={};lines={}
set={slots={[1]={definition='p',token=3523620028,type=118}},pairs={}}
probe.step(ctx('PrepareMission',false,1))
assert(#callbacks==0 and#lines==0)
return 'ok'
'''), b'ok')


class SelectorTests(unittest.TestCase):
    def test_the_pick_writes_the_carrier_itself(self):
        self.assertEqual(run(WORLD + SELECT + r'''
SCREEN=W.loadout_screen({entries={{type=22},{type=41}},editedSlot=2})
tick(2)
local job=settle_job(selector.select('orbital_gas_barrage',nil,{carrier={id=BIG_ID,name='Orbital 120mm HE Barrage'}}))
assert(job.status=='selected'and job.index==2 and job.appended,tostring(job.code)..' '..tostring(job.reason))
local kind,uses=SCREEN.entry(2)
assert(kind==136 and uses==4294967295,'slot 2 holds the carrier itself, unlimited')
assert(SCREEN.count()==3 and SCREEN.widget(2)==136)
for key,value in pairs(job.verify)do assert(value==true,key)end
local set=selector.virtual_slots()
assert(set.slots[2].definition=='orbital_gas_barrage'and set.slots[2].token==BIG_ID and set.slots[2].type==136
    and set.slots[2].carrier==true)
assert(count('stratagem selector SELECTED: orbital_gas_barrage -> slot 2 holds Orbital 120mm HE Barrage (type 136, the '
    ..'CARRIER itself: the carrier-in-slot probe): 4 writes; the entry reads the carrier: true')==1)
-- The reconstruction follows the carrier's stable id.
local slots,n=selector.reconstruct({2281932031,3193297673,BIG_ID})
assert(n==1 and slots[2]=='orbital_gas_barrage')
assert(selector.reconstruct({2281932031,3193297673,PRECISION_ID})==nil,'the token there: not this carrier slot')
-- A carrier that is not owned is refused, nothing written.
SCREEN=W.loadout_screen({entries={{type=22}},editedSlot=1})
selector.reset_for_tests()
tick(2)
local before=#W.runtime.writes
local refused=settle_job(selector.select('orbital_gas_barrage',nil,{carrier={id=2281932031,name='Eagle'}}))
assert(refused.status=='refused'and refused.code=='TOKEN_NOT_OWNED'and#W.runtime.writes==before,tostring(refused.code))
return 'ok'
'''), b'ok')


class AdoptTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(run(WORLD + SLOT + VIRTUAL + body), b'ok')

    def test_carrier_slots_are_adopted_with_nothing_written(self):
        self.check(r"""
-- Loadout: the carrier (slot 0) / native Precision Strike / Eagle (22) / the carrier (slot 3).
local record={{type=124,uses=-1,granted=1},{type=33,uses=-1,granted=1},
    {type=136,uses=-1,granted=0},{type=118,uses=-1,granted=0},{type=22,uses=-1,granted=0},{type=136,uses=-1,granted=0},
    {type=41,uses=-1,granted=1}}
local h=vworld(record)
local before=W.read(h.record+0x38+0x188,7*0x30)
local writes=#W.runtime.writes
local spec={definition='orbital_gas_barrage',carrier='Orbital 120mm HE Barrage',slots={0,3},
    order={BIG_ID,PRECISION_ID,ID22,BIG_ID}}
local job=settle_job(slots.adopt_virtual(spec))
assert(job.status=='converted'and job.adopted and job.writes==0 and job.indices[1]==2 and job.indices[2]==5,
    tostring(job.code)..' '..tostring(job.reason))
assert(#W.runtime.writes==writes and W.read(h.record+0x38+0x188,7*0x30)==before,'nothing written')
local st=slots.state('orbital_gas_barrage')
assert(st.converted and st.adopted and st.carrier==136 and st.indices[2]==5,'the cooldowns find its entries')
assert(count('ADOPTED (carrier-in-slot probe): virtual orbital_gas_barrage: loadout slots 0, 3 = record entries 2, 5 '
    ..'already hold the carrier Orbital 120mm HE Barrage (type 136) with unlimited uses: no write')==1,
    table.concat(logged,' | '))
-- Twice: refused.
assert(settle_job(slots.adopt_virtual(spec)).code=='ALREADY_CONVERTED')
-- The restore writes nothing back.
local restored=settle_job(slots.restore(nil,'orbital_gas_barrage'))
assert(restored.status=='restored'and restored.adopted and#W.runtime.writes==writes and entry_type(h,2)==136)
assert(not slots.state('orbital_gas_barrage').converted)
return 'ok'
""")

    def test_every_refusal(self):
        self.check(r"""
local function try(record,spec_changes)
    slots.reset_for_tests()
    local h=vworld(record)
    local spec={definition='orbital_gas_barrage',carrier='Orbital 120mm HE Barrage',slots={0},order={BIG_ID,ID22}}
    for k,v in pairs(spec_changes or{})do spec[k]=v end
    local writes=#W.runtime.writes
    local job=settle_job(slots.adopt_virtual(spec))
    assert(#W.runtime.writes==writes,'nothing written')
    return job
end
local base={{type=124,uses=-1,granted=1},{type=136,uses=-1,granted=0},{type=22,uses=-1,granted=0}}
assert(try(base).status=='converted')
-- The token in the slot (a token pick), another order, limited uses, no slot.
assert(try({{type=124,uses=-1,granted=1},{type=118,uses=-1,granted=0},{type=22,uses=-1,granted=0}},
    {order={PRECISION_ID,ID22}}).code=='NOT_CARRIER')
assert(try(base,{order={ID22,BIG_ID}}).code=='IDENTITY_CHANGED')
assert(try({{type=124,uses=-1,granted=1},{type=136,uses=3,granted=0},{type=22,uses=-1,granted=0}}).code=='USES_DIFFER')
assert(try(base,{slots={}}).code=='BAD_SPEC')
return 'ok'
""")


class OrchestratorTests(unittest.TestCase):
    def test_registration_and_the_mission_refusals(self):
        self.assertEqual(run(WORLD + r'''
local custom=require('hd2runtime/runtime/custom_stratagems');custom.reset_for_tests()
local selector=require('hd2runtime/runtime/stratagem_selector');selector.reset_for_tests()
local log_module=require('hd2runtime/runtime/log')
local lines={}
log_module.emit=function(t)lines[#lines+1]=t end
local function spec(over)
    local s={id='probe_gas',name='PROBE',description='d',icon='x',code={'up','right','down','left','up','right','down'},
        carrier={beacon='offensive',prefer_families={'orbital'}},
        orbital={native=true,pattern='Orbital 120mm HE Barrage',impact_explosion='Orbital Gas Strike'},selection='carrier'}
    for k,v in pairs(over or{})do s[k]=v end
    return s
end
local d=custom.register(spec(),'mods/test/probe')
assert(d.selection=='carrier')
local reg
for _,l in ipairs(lines)do if l:find('REGISTERED probe_gas',1,true)then reg=l end end
assert(reg and reg:find('SELECTION: its loadout slot holds the carrier itself, not the token',1,true),tostring(reg))
local ok,why=pcall(custom.register,spec({id='probe_bad',code={'down','down','down','down','up','up'},selection='slot'}),
    'mods/test/probe')
assert(not ok and tostring(why):find("selection must be 'token'",1,true),tostring(why))
assert(custom.register(spec({id='probe_token',code={'down','down','down','down','up','left'},selection='token'}),
    'mods/test/probe').selection==nil)
-- The mission refusals: several players, mixed slots, a slot carrier that is not its carrier now; none for a token slot.
local C,T=1063322614,3523620028
local a={stable_id=C,carrier='Orbital 120mm HE Barrage'}
selector.set_virtual_slots_for_tests({slots={[0]={definition='probe_gas',token=C,type=136,carrier=true}},pairs={C}})
assert(custom.probe_refusal(d,a,1)==nil)
local text,carrier=custom.probe_refusal(d,a,2)
assert(text:find('the probe runs solo only',1,true)and carrier=='Orbital 120mm HE Barrage')
text=custom.probe_refusal(d,{stable_id=999,carrier='Orbital 380mm HE Barrage'},1)
assert(text:find('its carrier now is Orbital 380mm HE Barrage',1,true),text)
selector.set_virtual_slots_for_tests({slots={[0]={definition='probe_gas',token=C,type=136,carrier=true},
    [1]={definition='probe_gas',token=T,type=118}},pairs={C,T}})
assert(custom.probe_refusal(d,a,1)=='its slots mix the token and the carrier')
selector.set_virtual_slots_for_tests({slots={[0]={definition='probe_gas',token=T,type=118}},pairs={T}})
assert(custom.probe_refusal(d,a,1)==nil,'a token slot runs as before')
-- Another selection mode or several players: the pick writes the token.
assert(custom.probe_carrier('probe_token')==nil)
return 'ok'
'''), b'ok')


class FlowTests(unittest.TestCase):
    def test_from_the_pick_to_ready_to_call_with_nothing_converted(self):
        # The Orbital Gas Barrage example (frozen 0.1.7 source), registered with selection = 'carrier', alone.
        from support import lua as lua_literal
        from test_stratagem_calldown_code import PROOF
        from test_custom_stratagem_flow import addon, FLOW_HARNESS, CAS_CARRIERS
        from test_gas_barrage_payload_proof import PAYLOAD_FLOW
        from test_pelican_cas_proof import CAS_WORLD
        pelican, pelican_addon = addon('PelicanCasExample')
        gas, gas_addon = addon('GasBarrageExample')
        eat, eat_addon = addon('GasEatExample')
        anchor = "    code={'up','up','down','down'},\n"
        self.assertEqual(gas_addon.count(anchor), 1)
        gas_addon = gas_addon.replace(anchor, anchor + "    selection='carrier',\n")
        body = r'''
rawset(_G,'ModOptionsMenu',MENU)
assert(loadstring(GAS_ADDON,'@'..GAS_RESOURCE))()
local d=custom.get('orbital_gas_barrage')
assert(d and d.selection=='carrier')
tick(40)
ship({})
tick(4)
select_into(0)
native_append(22);native_append(130)
SCREEN.set('selecting',false);tick(8)
SCREEN.close();tick(4)
local selector=require('hd2runtime/runtime/stratagem_selector')
local V=selector.virtual_slots()
assert(V and V.slots[0]and V.slots[0].definition=='orbital_gas_barrage'and V.slots[0].carrier==true,
    selector.slots_text(V)..' | '..lines('CARRIER-IN-SLOT')..' | '..lines('SELECTED'))
local kind,cid=V.slots[0].type,V.slots[0].token
assert(kind~=118 and cid~=PRECISION_ID,'the carrier itself, not the token')
assert(count('the CARRIER itself: the carrier-in-slot probe')==1,lines('SELECTED'))
-- Aboard the ship its own carrier is never invalidated as a native pick.
W.saved_loadout({{id=cid},{id=ID22},{id=1298599997}})
tick(80)
assert(count('PRE-MISSION (orbital_gas_barrage): READY')>=1,lines('PRE-MISSION')..' | '..lines('CARRIER'))
assert(count('CARRIER INVALIDATED')==0,lines('CARRIER INVALIDATED'))
-- MISSION: the record holds the carrier itself in slot 0; nothing is converted.
mission({host=true})
local record,hud=mission_record({kind,22,130})
local h=W.stratagem_hud({peer=LOCAL,slots=hud,record=record})
live_cooldowns(h,#record)
CT.player(0,0,0)
local writes_before=W.read(h.record+0x38+0x188+2*0x30,4)
tick(120)
assert(count('MISSION (orbital_gas_barrage): READY TO CALL: loadout slot 0 = ')==1,lines('MISSION')..' | '
    ..lines('CARRIER-IN-SLOT')..' | '..lines('REFUSED'))
assert(count('ADOPTED (carrier-in-slot probe): virtual orbital_gas_barrage: loadout slot 0 = record entry 2')==1,
    lines('ADOPTED'))
assert(W.read(h.record+0x38+0x188+2*0x30,4)==writes_before,'the slot entry is not written')
assert(count('stratagem slot CONVERTED')==0)
assert(count('CARRIER-IN-SLOT PROBE orbital_gas_barrage: applying the presentation on its carrier')==1,
    lines('CARRIER-IN-SLOT'))
assert(count('its presentation on ')==1 and count('was applied early (the carrier-in-slot probe): kept')==1,
    lines('MISSION'))
assert(count('held only in this player\'s custom slots, is not a native pick')==1,lines('CARRIER-IN-SLOT'))
return 'ok'
'''
        self.assertEqual(run(WORLD + SLOT + 'local ADDON=' + lua_literal(pelican_addon) + '\nlocal RESOURCE='
            + lua_literal(pelican) + '\nlocal GAS_ADDON=' + lua_literal(gas_addon) + '\nlocal GAS_RESOURCE='
            + lua_literal(gas) + '\nlocal EAT_ADDON=' + lua_literal(eat_addon) + '\nlocal EAT_RESOURCE='
            + lua_literal(eat) + PROOF + FLOW_HARNESS + CAS_CARRIERS + PAYLOAD_FLOW + CAS_WORLD
            + 'return (function()\nlocal lines=CT.lines\n'
            + "local custom=require('hd2runtime/runtime/custom_stratagems');custom.reset_for_tests()\n"
            + "require('hd2runtime/runtime/spawned_instances').reset_for_tests()\n"
            + "require('hd2runtime/runtime/carrier_in_slot').reset_for_tests()\n"
            + body + '\nend)()\n'), b'ok')


if __name__ == '__main__':
    unittest.main()
