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
    several players, mixed slots, or a slot carrier that is no longer its carrier;
  * no lockout (0.2.1): a carrier slot never blocks its carrier natively; when anyone else picks it, the slot moves to
    its next carrier aboard the ship (the pick's guarded write at the slot's own index; refused with nothing written
    unless the slot still reads its carrier and the new one is in no slot), the native pick untouched;
  * the doubles (0.3.0): its carrier stays pickable natively in the other slots (the doubles set handed to the grid);
  * the launch fallback (0.3.0): a recorded native pick of its carrier whose slot could not move is swapped in the
    mission record (its own entry, while locked), the native pick untouched; an unrecorded one is refused with nothing
    written and the slot locked all mission."""
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


class MoveTests(unittest.TestCase):
    def test_a_carrier_slot_moves_to_another_carrier_and_every_guard_refuses(self):
        self.assertEqual(run(WORLD + SELECT + r'''
SCREEN=W.loadout_screen({entries={{type=22},{type=41}},editedSlot=2})
W.catalogue({[PRECISION_ID]=2,[BIG_ID]=2,[3193297673]=2})
tick(2)
assert(settle_job(selector.select('orbital_gas_barrage',nil,{carrier={id=BIG_ID,name='Orbital 120mm HE Barrage'}}))
    .status=='selected')
-- The grid closes; the loadout screen stays open.
SCREEN.set('selecting',false);tick(2)
local TO={id=PRECISION_ID,name='Orbital Precision Strike'}
local function refused(code,slot,to,definition)
    local before,record=#W.runtime.writes,W.read(SCREEN.record,0x80)
    local job=settle_job(selector.move_carrier(slot or 2,definition or'orbital_gas_barrage',to or TO))
    assert(job.status=='refused'and job.code==code,code..' expected, got '..tostring(job.code)..': '..tostring(job.reason))
    assert(#W.runtime.writes==before and W.read(SCREEN.record,0x80)==record,'nothing written: '..code)
end
-- Never into a carrier another slot holds (a real pick), never onto itself, never a slot that is not its carrier slot.
refused('CARRIER_IN_LOADOUT',2,{id=3193297673,name='Orbital Gas Strike'})
refused('SAME_CARRIER',2,{id=BIG_ID,name='Orbital 120mm HE Barrage'})
refused('NOT_CARRIER_SLOT',0)
refused('NOT_CARRIER_SLOT',2,nil,'another_definition')
-- Ready, launched, closed, or not aboard the ship.
SCREEN.set('ready',true);refused('READY');SCREEN.set('ready',false)
SCREEN.set('launched',true);refused('LAUNCHED');SCREEN.set('launched',false)
W.state(6);refused('NOT_ABOARD');W.state(3)
-- The slot no longer reads its carrier exactly (here: limited uses): refused.
local LO=SEL.loadout
local at=SCREEN.record+LO.entries+2*LO.entryStride+LO.entryUses
W.write(at,W.u32(3));refused('SLOT_CHANGED');W.write(at,W.u32(4294967295))
-- The move: only the slot's type changes; the virtual slot records the new carrier.
local before=#W.runtime.writes
local job=settle_job(selector.move_carrier(2,'orbital_gas_barrage',TO))
assert(job.status=='moved',tostring(job.code)..' '..tostring(job.reason))
for key,value in pairs(job.verify)do assert(value==true,key)end
local k0,u0=SCREEN.entry(0)
local k1,u1=SCREEN.entry(1)
local k2,u2=SCREEN.entry(2)
assert(k0==22 and k1==41 and k2==118 and u2==4294967295 and SCREEN.count()==3 and SCREEN.widget(2)==118)
assert(#W.runtime.writes-before==2,'the type and the panel\'s cached record pointer')
local set=selector.virtual_slots()
assert(set.slots[2].definition=='orbital_gas_barrage'and set.slots[2].token==PRECISION_ID and set.slots[2].type==118
    and set.slots[2].carrier==true)
assert(count('stratagem selector MOVED (carrier-in-slot probe): virtual slot 2 (orbital_gas_barrage): its carrier ')==1)
assert(count('(type 136) -> Orbital Precision Strike (type 118): 2 writes; the entry reads the new carrier: true; every '
    ..'other entry unchanged: true; count unchanged: true; the game repainted the slots from the record: true')==1)
-- Closed: refused.
SCREEN.close();refused('SCREEN_CLOSED',2,{id=BIG_ID,name='Orbital 120mm HE Barrage'})
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
    ..'already hold the carrier Orbital 120mm HE Barrage (type 136) with unlimited uses: no slot write')==1,
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


class NativeUsesTests(unittest.TestCase):
    """Probe 0.2.0: the native per-slot uses (research carrier-max-uses option A): only this player's own adopted
    entries, -1 -> N, never the row, never another entry; every guard refuses with nothing written."""
    def check(self, body):
        self.assertEqual(run(WORLD + SLOT + VIRTUAL + r"""
-- Loadout: the carrier (slot 0) / native Precision Strike / Eagle (22).
local RECORD3={{type=124,uses=-1,granted=1},{type=136,uses=-1,granted=0},{type=118,uses=-1,granted=0},
    {type=22,uses=-1,granted=0},{type=41,uses=-1,granted=1}}
local SPEC3={definition='orbital_gas_barrage',carrier='Orbital 120mm HE Barrage',slots={0},
    order={BIG_ID,PRECISION_ID,ID22},uses=3}
local function entry_uses(h,index)return b.u32(W.read(h.record+0x38+0x188+index*0x30+4,4),0)end
""" + body), b'ok')

    def test_the_slot_gets_its_native_uses_and_nothing_else_changes(self):
        self.check(r"""
local h=vworld(RECORD3)
local rows=W.read(settings.base,settings.size)
local before=W.read(h.record+0x38+0x188,5*0x30)
local writes=#W.runtime.writes
local job=settle_job(slots.adopt_virtual(SPEC3))
assert(job.status=='converted'and job.native_uses==3 and job.writes==1,tostring(job.code)..' '..tostring(job.reason))
assert(entry_uses(h,1)==3,'the slot entry has 3 uses')
assert(entry_uses(h,2)==4294967295 and entry_uses(h,3)==4294967295,'the other entries keep theirs')
assert(#W.runtime.writes==writes+1,'one 4-byte write')
local now=W.read(h.record+0x38+0x188,5*0x30)
for i=1,#now do
    local at=i-1
    assert(now:byte(i)==before:byte(i)or(at>=1*0x30+4 and at<1*0x30+8),'byte '..at)
end
assert(W.read(settings.base,settings.size)==rows,'no StratagemInfo row written (the carrier row keeps unlimited)')
assert(slots.state('orbital_gas_barrage').native_uses==3)
assert(count('NATIVE USES (carrier-in-slot probe): virtual orbital_gas_barrage: record entry 1 (Orbital 120mm HE '
    ..'Barrage) uses -1 -> 3')==1,table.concat(logged,' | '))
-- The game counts down (written here as it would); the restore while the record stands writes -1 back.
W.write(h.record+0x38+0x188+1*0x30+4,W.u32(1))
local restored=settle_job(slots.restore(nil,'orbital_gas_barrage'))
assert(restored.status=='restored'and restored.adopted and entry_uses(h,1)==4294967295)
assert(entry_type(h,1)==136,'the carrier stays in its slot')
assert(count('NATIVE USES RELEASED (carrier-in-slot probe): entry 1 (Orbital 120mm HE Barrage): 1 write back to '
    ..'unlimited')==1,table.concat(logged,' | '))
return 'ok'
""")

    def test_a_rebuilt_record_is_never_written(self):
        self.check(r"""
local h=vworld(RECORD3)
assert(settle_job(slots.adopt_virtual(SPEC3)).status=='converted')
-- The mission ends: the game rebuilds the record (the slot back to the row's uses); the keeper lets the adoption go.
W.write(h.record+0x38+0x188+1*0x30,W.u32(22))
tick(3)
assert(not slots.state('orbital_gas_barrage').converted)
local writes=#W.runtime.writes
local restored=slots.restore(nil,'orbital_gas_barrage')
for _=1,20 do tick()end
assert(#W.runtime.writes==writes,'nothing written into a rebuilt record')
return 'ok'
""")

    def test_every_guard_refuses_with_nothing_written(self):
        self.check(r"""
local function try(record,changes,prep)
    slots.reset_for_tests()
    local h=vworld(record or RECORD3)
    if prep then prep(h)end
    local spec={}
    for k,v in pairs(SPEC3)do spec[k]=v end
    for k,v in pairs(changes or{})do spec[k]=v end
    local writes=#W.runtime.writes
    local job=settle_job(slots.adopt_virtual(spec))
    assert(job.status=='converted'or#W.runtime.writes==writes,'a refusal writes nothing: '..tostring(job.code))
    return job
end
assert(try(nil,{uses=0}).code=='BAD_SPEC')
assert(try(nil,{uses=101}).code=='BAD_SPEC')
-- The carrier also natively in another slot: never written (that entry is a real pick).
local twice={{type=124,uses=-1,granted=1},{type=136,uses=-1,granted=0},{type=136,uses=-1,granted=0},
    {type=22,uses=-1,granted=0},{type=41,uses=-1,granted=1}}
assert(try(twice,{order={BIG_ID,BIG_ID,ID22}}).code=='CARRIER_ELSEWHERE')
-- A carrier with limited uses of its own, or a team-shared cooldown type: its uses are not per entry.
local CD=require('hd2runtime/domains/slot_cooldown').row
assert(try(nil,nil,function()W.write(ROW[136]+0x50,W.u32(4))end).code=='USES_DIFFER')
W.write(ROW[136]+0x50,W.u32(4294967295))
assert(try(nil,nil,function()W.write(ROW[136]+CD.cooldownType,W.u32(2))end).code=='SHARED_COOLDOWN')
W.write(ROW[136]+CD.cooldownType,W.u32(0))
-- The slot entry not unlimited now (another writer): refused by the adoption itself.
assert(try({{type=124,uses=-1,granted=1},{type=136,uses=2,granted=0},{type=118,uses=-1,granted=0},
    {type=22,uses=-1,granted=0},{type=41,uses=-1,granted=1}}).code=='USES_DIFFER')
assert(try().status=='converted','and with every guard holding it is written')
return 'ok'
""")


class LockTests(unittest.TestCase):
    def test_the_slot_is_locked_until_ready_and_released(self):
        from test_bombardment_payload import PAYLOAD
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + VIRTUAL + r"""
local probe=require('hd2runtime/runtime/carrier_in_slot');probe.reset_for_tests()
local cooldowns=require('hd2runtime/runtime/slot_cooldown')
BOMB.set_clock(500000000)
local RECORD3={{type=124,uses=-1,granted=1},{type=136,uses=-1,granted=0},{type=118,uses=-1,granted=0},
    {type=22,uses=-1,granted=0},{type=41,uses=-1,granted=1}}
local h=vworld(RECORD3)
local function end_bytes(index)return W.read(h.record+0x38+0x188+index*0x30+0x18,8)end
local original=end_bytes(1)
local world=world_module.open()
local x={slots={0},id=BIG_ID}
probe.lock(world,'orbital_gas_barrage',x)
local l=probe.lock_state('orbital_gas_barrage')
assert(l and l.entries and#l.entries==1 and l.entries[1].index==1,tostring(l and l.failed))
assert(end_bytes(1)~=original,'locked: its end far ahead')
assert(end_bytes(2)==W.read(h.record+0x38+0x188+2*0x30+0x18,8))
assert(count('orbital_gas_barrage: LOCKED record entry 1')==1,table.concat(logged,' | '))
-- Released: exactly the end it had.
assert(probe.release(world,'orbital_gas_barrage'))
assert(end_bytes(1)==original,'released: the end written back')
assert(count('orbital_gas_barrage: RELEASED record entry 1')==1)
-- A slot that does not hold its carrier is never locked.
probe.reset_for_tests()
probe.lock(world,'orbital_gas_barrage',{slots={1},id=BIG_ID})
assert(probe.lock_state('orbital_gas_barrage').failed:find('does not hold its carrier',1,true))
return 'ok'
"""), b'ok')


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
    def flow(self, body):
        # The Orbital Gas Barrage example (frozen 0.1.7 source), registered with selection = 'carrier' and 3 uses, alone.
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
        gas_addon = gas_addon.replace(anchor, anchor + "    selection='carrier',\n    uses=3,\n")
        self.assertEqual(run(WORLD + SLOT + 'local ADDON=' + lua_literal(pelican_addon) + '\nlocal RESOURCE='
            + lua_literal(pelican) + '\nlocal GAS_ADDON=' + lua_literal(gas_addon) + '\nlocal GAS_RESOURCE='
            + lua_literal(gas) + '\nlocal EAT_ADDON=' + lua_literal(eat_addon) + '\nlocal EAT_RESOURCE='
            + lua_literal(eat) + PROOF + FLOW_HARNESS + CAS_CARRIERS + PAYLOAD_FLOW + CAS_WORLD
            + 'return (function()\nlocal lines=CT.lines\n'
            + "local custom=require('hd2runtime/runtime/custom_stratagems');custom.reset_for_tests()\n"
            + "require('hd2runtime/runtime/spawned_instances').reset_for_tests()\n"
            + "require('hd2runtime/runtime/carrier_in_slot').reset_for_tests()\n"
            + body + '\nend)()\n'), b'ok')

    def test_from_the_pick_to_ready_to_call_with_nothing_converted(self):
        self.flow(r'''
rawset(_G,'ModOptionsMenu',MENU)
-- The native picker's block set, as the orchestrator hands it over every ship update.
local blocked_seen={}
require('hd2runtime/runtime/stratagem_blocking').apply=function(world,set)
    for id,b in pairs(set or{})do blocked_seen[id]=b end
    return {status='applied'}
end
-- The doubles set (0.3.0), as the orchestrator hands it over every ship update.
local enable_seen={}
require('hd2runtime/runtime/stratagem_blocking').enable=function(world,set)
    for id,e in pairs(set or{})do enable_seen[id]=e end
    return {status='applied'}
end
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
-- 0.2.1: no lockout: the carrier the slot holds is never blocked natively for being in a carrier slot (only by the
-- regular rule: the last viable carrier of a selected custom stratagem).
tick(4)
assert(not(blocked_seen[cid]and blocked_seen[cid].reason:find('held by your custom stratagem',1,true)),'no lockout')
-- 0.3.0: its carrier stays pickable natively in the other slots (the doubles), named with its custom slot.
assert(enable_seen[cid]and enable_seen[cid].definition=='orbital_gas_barrage'and enable_seen[cid].slots[1]==0
    and#enable_seen[cid].slots==1,'the doubles set holds its carrier')
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
-- 0.2.0: locked from the first mission update until ready; its native uses written; released; its cooldown armed.
assert(count('orbital_gas_barrage: LOCKED record entry 2')==1,lines('CARRIER-IN-SLOT')..' | '..lines('LOCK'))
assert(count('NATIVE USES (carrier-in-slot probe): virtual orbital_gas_barrage: record entry 2')==1,lines('NATIVE'))
assert(b.u32(W.read(h.record+0x38+0x188+2*0x30+4,4),0)==3,'the slot entry has 3 native uses')
assert(count('orbital_gas_barrage: RELEASED record entry 2')==1,lines('RELEASED'))
assert(count('MISSION (orbital_gas_barrage): NATIVE USES: 3 per slot')==1,lines('MISSION'))
for _,i in ipairs({0,1,3,4,5})do
    assert(b.u32(W.read(h.record+0x38+0x188+i*0x30+4,4),0)==4294967295,'a native entry keeps unlimited')
end
assert(count('stratagem selector MOVED')==0,'nothing moved: nobody else holds its carrier')
return 'ok'
''')

    def test_anyone_else_picking_its_carrier_moves_the_slot_before_the_mission(self):
        self.flow(r'''
rawset(_G,'ModOptionsMenu',MENU)
assert(loadstring(GAS_ADDON,'@'..GAS_RESOURCE))()
tick(40)
ship({})
tick(4)
select_into(0)
native_append(22);native_append(130)
SCREEN.set('selecting',false);tick(8)
local selector=require('hd2runtime/runtime/stratagem_selector')
local V=selector.virtual_slots()
local kind,cid=V.slots[0].type,V.slots[0].token
assert(V.slots[0].carrier and kind~=118)
tick(80)
assert(count('stratagem selector MOVED')==0,'its slot keeps its carrier while nobody else holds it')
-- Its carrier picked natively (into slot 3, as the game's pick writes the record), the loadout screen open, the grid
-- closed: the slot moves to its next carrier; the native pick is untouched.
native_append(kind)
tick(120)
assert(count('stratagem selector MOVED (carrier-in-slot probe): virtual slot 0 (orbital_gas_barrage): its carrier ')==1,
    lines('MOVED')..' | '..lines('SHIP (orbital_gas_barrage)')..' | '..lines('REFUSED'))
assert(count('SHIP (orbital_gas_barrage): loadout slot 0 MOVED from ')==1
    and count('(you picked it natively into loadout slot 3), before the mission')==1,lines('SHIP (orbital_gas_barrage)'))
V=selector.virtual_slots()
local nkind,nid=V.slots[0].type,V.slots[0].token
assert(V.slots[0].carrier and nid~=cid and nkind~=kind and nkind~=118)
local k0=SCREEN.entry(0)
local k3,u3=SCREEN.entry(3)
assert(k0==nkind and k3==kind and u3==4294967295,'slot 0 moved; the native pick in slot 3 untouched')
tick(120)
assert(count('stratagem selector MOVED')==1,'once: the new carrier is kept (its pin)')
-- The launch: the saved loadout, then the mission.
W.saved_loadout({{id=nid},{id=ID22},{id=1298599997},{id=cid}})
SCREEN.close();tick(80)
mission({host=true})
local record,hud=mission_record({nkind,22,130,kind})
local h=W.stratagem_hud({peer=LOCAL,slots=hud,record=record})
live_cooldowns(h,#record)
CT.player(0,0,0)
tick(120)
assert(count('MISSION (orbital_gas_barrage): READY TO CALL: loadout slot 0 = ')==1,lines('MISSION')..' | '
    ..lines('CARRIER-IN-SLOT')..' | '..lines('REFUSED'))
-- Its native uses on its own entry (2); the native pick's entry (5) keeps unlimited, its row its own look.
assert(count('NATIVE USES (carrier-in-slot probe): virtual orbital_gas_barrage: record entry 2')==1,lines('NATIVE'))
assert(b.u32(W.read(h.record+0x38+0x188+2*0x30+4,4),0)==3)
assert(b.u32(W.read(h.record+0x38+0x188+5*0x30,4),0)==kind)
assert(b.u32(W.read(h.record+0x38+0x188+5*0x30+4,4),0)==4294967295,'the native pick keeps unlimited uses')
assert(count('applying the presentation on its carrier ')==1 and count('NO early presentation')==0,
    lines('CARRIER-IN-SLOT'))
local to_name=lines('loadout slot 0 MOVED from '):match(' to (.-) %(you picked')
assert(to_name and lines('applying the presentation on its carrier '):find('its carrier '..to_name,1,true),
    tostring(to_name)..' | '..lines('applying the presentation'))
return 'ok'
''')

    def test_a_slot_that_could_not_move_is_swapped_at_launch(self):
        # 0.3.0, the launch fallback: the native pick of its carrier is recorded aboard the ship, but the slot does not
        # move before the launch (held here: the move's settle never elapses, as when the player readies at once).
        self.flow(r'''
rawset(_G,'ModOptionsMenu',MENU)
assert(loadstring(GAS_ADDON,'@'..GAS_RESOURCE))()
tick(40)
ship({})
tick(4)
select_into(0)
native_append(22);native_append(130)
SCREEN.set('selecting',false);tick(8)
local selector=require('hd2runtime/runtime/stratagem_selector')
local V=selector.virtual_slots()
local kind,cid=V.slots[0].type,V.slots[0].token
local old_name=lines('stratagem selector SELECTED'):match('holds (.-) %(type')
tick(80)
custom.PROBE_MOVE_SETTLE=1e9
native_append(kind)
tick(120)
assert(count('stratagem selector MOVED')==0)
assert(table.concat(selector.virtual_slots().pairs,',')==table.concat({cid,ID22,1298599997,cid},','),
    'the native pick is recorded')
SCREEN.set('ready',true);tick(4)
W.saved_loadout({{id=cid},{id=ID22},{id=1298599997},{id=cid}})
SCREEN.close();tick(80)
mission({host=true})
local record,hud=mission_record({kind,22,130,kind})
local h=W.stratagem_hud({peer=LOCAL,slots=hud,record=record})
live_cooldowns(h,#record)
CT.player(0,0,0)
local native_before=W.read(h.record+0x38+0x188+5*0x30,0x30)
tick(200)
-- Swapped in its own entry (2), old carrier -> its carrier, while locked; then released and ready.
assert(count('LAUNCH FALLBACK (the carrier-in-slot probe): its slot holds the carrier '..old_name)==1,lines('MISSION'))
assert(count('CONVERTED: virtual orbital_gas_barrage: loadout slot 0 = record entry 2: '..old_name)==1,
    lines('CONVERTED')..' | '..lines('REFUSED'))
local now=b.u32(W.read(h.record+0x38+0x188+2*0x30,4),0)
assert(now~=kind and now~=118,'entry 2 holds its new carrier')
assert(count('orbital_gas_barrage: LOCKED record entry 2')==1 and count('orbital_gas_barrage: RELEASED record entry 2')==1,
    lines('LOCKED')..' | '..lines('RELEASED'))
assert(count('MISSION (orbital_gas_barrage): READY TO CALL: loadout slot 0 = ')==1,lines('MISSION'))
-- The native pick's entry (5) never written; no presentation, no native uses on the old carrier.
assert(W.read(h.record+0x38+0x188+5*0x30,0x30)==native_before,'the native pick\'s record entry is untouched')
assert(not lines('custom text APPLIED'):find(old_name,1,true),lines('custom text APPLIED'))
assert(count('orbital_gas_barrage NOT presented early (')==1,lines('TIMING'))
assert(count('NATIVE USES (carrier-in-slot probe)')==0,lines('NATIVE'))
return 'ok'
''')

    def test_an_unrecorded_native_pick_refuses_with_nothing_written(self):
        # The native pick of its carrier made while the player is ready is never recorded (the loadout is the game's
        # then): the mission loadout differs from the recorded order, so the fallback's identity guard refuses.
        self.flow(r'''
rawset(_G,'ModOptionsMenu',MENU)
assert(loadstring(GAS_ADDON,'@'..GAS_RESOURCE))()
tick(40)
ship({})
tick(4)
select_into(0)
native_append(22);native_append(130)
SCREEN.set('selecting',false);tick(8)
local selector=require('hd2runtime/runtime/stratagem_selector')
local V=selector.virtual_slots()
local kind,cid=V.slots[0].type,V.slots[0].token
local old_name=lines('stratagem selector SELECTED'):match('holds (.-) %(type')
tick(80)
SCREEN.set('ready',true)
native_append(kind)
tick(120)
assert(count('stratagem selector MOVED')==0)
W.saved_loadout({{id=cid},{id=ID22},{id=1298599997},{id=cid}})
SCREEN.close();tick(80)
mission({host=true})
local record,hud=mission_record({kind,22,130,kind})
local h=W.stratagem_hud({peer=LOCAL,slots=hud,record=record})
live_cooldowns(h,#record)
CT.player(0,0,0)
local before=W.read(h.record+0x38+0x188,7*0x30)
tick(200)
assert(count('MISSION (orbital_gas_barrage): READY TO CALL')==0,lines('MISSION'))
assert(count('the slot conversion was refused: IDENTITY_CHANGED')>=1,lines('REFUSED'))
-- Nothing written but its own lock (entry 2's cooldown end): every type and every other entry unchanged.
local now=W.read(h.record+0x38+0x188,7*0x30)
for i=0,6 do
    local a,c=before:sub(i*0x30+1,i*0x30+0x30),now:sub(i*0x30+1,i*0x30+0x30)
    if i~=2 then assert(a==c,'entry '..i..' untouched')else assert(a:sub(1,8)==c:sub(1,8),'entry 2 type and uses')end
end
assert(count('orbital_gas_barrage: LOCKED record entry 2')==1 and count('RELEASED record entry')==0,
    'locked all mission: never the carrier\'s own call')
assert(not lines('custom text APPLIED'):find(old_name,1,true),lines('custom text APPLIED'))
assert(count('NATIVE USES (carrier-in-slot probe)')==0,lines('NATIVE'))
return 'ok'
''')

if __name__ == '__main__':
    unittest.main()
