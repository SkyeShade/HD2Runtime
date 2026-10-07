"""The client-write proof (runtime/multiplayer.lua host_guard; research/docs/runtime-peer-messaging-F5FEE03DCFDB.md
section 10): the four writes a non-host client may make for its OWN Gas EAT call, each on the offline world it is
already tested on as the host. For each write:
  * a client is refused NOT_HOST exactly as before unless BOTH the write carries the orchestrator's client mark and the
    proof is enabled for the mission (an unmarked write, or a marked one with the proof off, stays refused);
  * inside the proof the client writes exactly what the host writes (the same bytes, the same number of writes, the
    same read-back): the host flag is not an input of the write;
  * the guards that protect what the host guard did not stay: a beacon copy owned by another machine (NOT_OWNED), a
    projectile another player fired (NOT_LOCAL)."""
import unittest

from support import run
from test_stratagem_calldown_code import WORLD
from test_stratagem_slot_conversion import SLOT, VIRTUAL
from test_bombardment_payload import PAYLOAD
from test_beacon_redirect import BEACONS
from test_beacons import API
from test_gas_eat import IMPACT
from test_slot_cooldown import COOL

PROOF = r"""
local mpx=require('hd2runtime/runtime/multiplayer');mpx.reset_for_tests()
"""


class HostGuardTests(unittest.TestCase):
    def test_the_host_guard_accepts_only_a_marked_write_inside_the_proof(self):
        self.assertEqual(run(PROOF + r"""
assert(mpx.host_guard({host=true},false)==nil and mpx.host_guard({host=true},true)==nil,'the host')
local code,why=mpx.host_guard({host=false},false,'x')
assert(code=='NOT_HOST'and why=='x')
code,why=mpx.host_guard({host=false},true,'x')
assert(code=='NOT_HOST'and why:find('the client-write proof is not enabled',1,true),'marked, proof off')
mpx.enable_client_proof(true)
assert(mpx.host_guard({host=false},true)==nil,'marked, proof on')
assert(mpx.host_guard({host=false},false)=='NOT_HOST','unmarked, proof on')
assert(mpx.host_guard(nil,true)==nil and mpx.host_guard(nil,false)=='NOT_HOST')
mpx.enable_client_proof(false)
assert(mpx.host_guard({host=false},true)=='NOT_HOST','the proof ends with the mission')
-- The client families: support, expendable and sentry deliveries, native orbitals, host-spawned Pelicans; never an Eagle,
-- the Runtime bombardment or a callback-only definition.
assert(mpx.CLIENT_FAMILIES.support==true and mpx.CLIENT_FAMILIES.expendable and mpx.CLIENT_FAMILIES.sentry)
for _,kind in ipairs({'eagle','orbital','runtime'})do assert(not mpx.CLIENT_FAMILIES[kind],kind)end
assert(mpx.CLIENT_FAMILIES.orbital_native and mpx.CLIENT_FAMILIES.pelican)
assert(mpx.client_family({kind='orbital',orbital={native=true}})=='orbital_native'and mpx.client_family({kind='orbital',orbital={}})==nil)
return 'ok'
"""), b'ok')


class BeaconWriteTests(unittest.TestCase):
    def test_a_client_changes_its_own_beacon_exactly_as_the_host_does(self):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + BEACONS + API + PROOF + r"""
pworld()
local world=world_module.open()
local CHANGE={delivery='Orbital 120mm HE Barrage',call_in_time=4,lifetime_after_activation=22.444}
local function apply(entity,host,mark,with_state)
    BR.reset_for_tests()
    beacon(0,entity,25,8.715,8.715);counts(1,with_state==false and 0 or 1)
    W.write(STATE+0x8E4,string.char(0));W.write(STATE+0x8E0,W.u32(1))
    W.state(4,{host=host})
    local before=element(0)
    local writes=#W.runtime.writes
    local expect={type=25,timers=before:sub(1,8),client=mark}
    if with_state==false then expect.timers=nil end
    local change={};for k,v in pairs(CHANGE)do change[k]=v end
    local r,code,why=beacons.apply(world,entity,expect,change)
    return r,code,why,element(0),#W.runtime.writes-writes,before
end
local host,_,_,host_after,host_writes=apply(7801,true,nil)
assert(host and host.verified and host_writes==3 and type_at(0)==136)
-- A client: unmarked, or marked with the proof off: NOT_HOST, nothing written.
local r,code,_,after,n,before=apply(7802,false,nil)
assert(not r and code=='NOT_HOST'and n==0 and after==before)
r,code,_,after,n,before=apply(7803,false,true)
assert(not r and code=='NOT_HOST'and n==0 and after==before)
-- Inside the proof: the same transaction, the same bytes.
mpx.enable_client_proof(true)
local client,ccode,cwhy,client_after,client_writes=apply(7804,false,true)
assert(client and client.verified,tostring(ccode)..' '..tostring(cwhy))
assert(client_writes==host_writes and client_after==host_after,'the client wrote something else than the host')
assert(client.delivery.from==25 and client.delivery.to==136)
-- Another machine's copy (no state here) stays NOT_OWNED, proof or not.
r,code,_,_,n=apply(7805,false,true,false)
assert(not r and code=='NOT_OWNED'and n==0,tostring(code))
mpx.enable_client_proof(false)
return 'ok'
"""), b'ok')


class SlotConversionWriteTests(unittest.TestCase):
    def test_a_client_converts_its_own_record_entries_exactly_as_the_host_does(self):
        self.assertEqual(run(WORLD + SLOT + VIRTUAL + PROOF + r"""
local h=vworld()
mission({host=false})
local before=W.read(h.record+0x38+0x188,7*0x30)
local writes=#W.runtime.writes
-- Unmarked, then marked with the proof off: NOT_HOST, nothing written.
local job=settle_job(slots.convert_virtual(VSPEC))
assert(job.code=='NOT_HOST'and#W.runtime.writes==writes)
slots.reset_for_tests()
job=settle_job(slots.convert_virtual(copy(VSPEC,{client=true})))
assert(job.code=='NOT_HOST'and#W.runtime.writes==writes)
-- Inside the proof: exactly the host's conversion (tests/test_stratagem_slot_conversion.py, the same assertions).
slots.reset_for_tests()
mpx.enable_client_proof(true)
job=settle_job(slots.convert_virtual(copy(VSPEC,{client=true})))
assert(job.status=='converted',tostring(job.code)..' '..tostring(job.reason))
assert(job.indices[1]==2 and job.indices[2]==5 and#job.indices==2 and job.slots[1]==0 and job.slots[2]==3)
assert(entry_type(h,2)==136 and entry_type(h,5)==136 and entry_type(h,3)==118 and entry_type(h,4)==22)
assert(entry_type(h,0)==124 and entry_type(h,1)==33 and entry_type(h,6)==41)
assert(#W.runtime.writes==writes+2,'one transaction, two 4-byte writes')
local now=W.read(h.record+0x38+0x188,7*0x30)
for i=1,#now do
    local at=i-1
    assert(now:byte(i)==before:byte(i)or(at>=2*0x30 and at<2*0x30+4)or(at>=5*0x30 and at<5*0x30+4),'byte '..at)
end
mpx.enable_client_proof(false)
return 'ok'
"""), b'ok')


class CooldownWriteTests(unittest.TestCase):
    def test_a_client_overrides_its_own_entrys_cooldown_exactly_as_the_host_does(self):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + COOL + PROOF + r"""
local function one(mark,proof)
    cool.reset_for_tests();slots.reset_for_tests()
    local h=converted()
    W.state(4,{host=false})
    mpx.enable_client_proof(proof)
    local events=arm({definition='orbital_gas_barrage',seconds=60,client=mark})
    tick()
    local writes=#W.runtime.writes
    local before=record_bytes(h)
    local arrival=call(h,CLOCK-300000,6,205.2)
    tick()
    return h,events,#W.runtime.writes-writes,before,arrival
end
local _,events,n=one(nil,false)
assert(last(events,'refused')and last(events,'refused').code=='NOT_HOST'and n==0,kinds(events))
_,events,n=one(true,false)
assert(last(events,'refused')and last(events,'refused').code=='NOT_HOST'and n==0,kinds(events))
local h,before,arrival
h,events,n,before,arrival=one(true,true)
local o=last(events,'overridden')
assert(o and n==1 and o.desired==arrival+60*US and o.writes==1,kinds(events))
for _,key in ipairs({'finish','others','nonTarget','protection'})do assert(o.verify[key],key)end
assert(u64_at(entry_at(h)+0x18)==arrival+60*US)
local now=record_bytes(h)
for i=1,#now do
    local at=i-1
    assert(now:byte(i)==before:byte(i)or(at>=INDEX*0x30+0x10 and at<INDEX*0x30+0x28),'record byte '..at..' changed')
end
mpx.enable_client_proof(false)
return 'ok'
"""), b'ok')


class ProjectileImpactWriteTests(unittest.TestCase):
    def test_a_client_converts_its_own_launchers_rocket_exactly_as_the_host_does(self):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + IMPACT + PROOF + r"""
iworld()
W.state(4,{host=false})
tick()
local function refused(spec,code)
    local b0,c0=impacts.bind(spec)
    assert(not b0 and c0==code,code..' expected, got '..tostring(c0))
end
local SPEC={sources={5001,5002},projectile=132,donor='Orbital Gas Strike',entity_type=EAT_TYPE,label='Gas EAT client'}
refused(SPEC,'NOT_HOST')
local marked={};for k,v in pairs(SPEC)do marked[k]=v end;marked.client=true
refused(marked,'NOT_HOST')
mpx.enable_client_proof(true)
local events={}
local binding,code,why=impacts.bind(marked,function(e)events[#events+1]=e end)
assert(binding,tostring(code)..' '..tostring(why))
tick()
local writes=#W.runtime.writes
-- Another player's rocket from the bound launcher (its creditor is not this machine's player): NOT_LOCAL, vanilla.
local _,other=fire(5002,{creditor='5555666677778888'})
tick()
assert(impact_of(other)==376 and events[1].kind=='refused'and events[1].code=='NOT_LOCAL',tostring(events[1]and
    events[1].code))
-- This player's own rocket: ONE 4-byte write of its own copy, 376 -> 82, as on the host.
local slot1,hit1=fire(5001)
tick()
assert(impact_of(hit1)==82 and#W.runtime.writes==writes+1)
local c=events[#events]
assert(c.kind=='converted'and c.slot==slot1 and c.from==376 and c.to==82 and c.writes==1 and c.verify.readBack
    and c.verify.nonTarget and c.creditor==LOCAL_PEER)
mpx.enable_client_proof(false)
return 'ok'
"""), b'ok')


if __name__ == '__main__':
    unittest.main()
