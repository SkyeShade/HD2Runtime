"""The carrier payload, stage B (runtime/bombardment_payload.lua, docs/custom-stratagems.md "Payload stage B"): the
converted carrier's OWN BombardmentComponentData takes the Orbital 120mm HE Barrage's pattern and shells through one
guarded transaction, and is restored exactly. On the offline event world: a StratagemSettings buffer whose rows match
the catalogue's reviewed roots, the local stratagem record and the bombardment component built as the game's own lookup
reads it (W.bombardment, every reviewed record and shell row from the research). Nothing here touches a game process."""
import json
import unittest

from support import ROOT, run
from test_stratagem_calldown_code import WORLD
from test_stratagem_slot_conversion import SLOT

RESEARCH = json.loads((ROOT / 'research/bombardment-payload-F5FEE03DCFDB.json').read_text(encoding='utf-8'))

PAYLOAD = r"""
local payload=require('hd2runtime/runtime/bombardment_payload')
local PD=require('hd2runtime/domains/bombardment_payload')
payload.reset_for_tests()
local CAT=require('hd2runtime/domains/stratagem_authoring').stratagems
local CODES=require('hd2runtime/domains/stratagem_calldown').nativeCodes
local function rooted(name,kind)
    local r=CAT[name].root
    return {type=kind,id=r.id,package=r.package,payloads=r.payloads,sequence=CODES[tostring(r.id)],group=r.group,
        row=r.row,cooldown=240,fields=pres(r.id)}
end
-- The rows of the calldown world plus two orbitals at their reviewed roots: the 380mm (a compatible carrier) and the
-- Airburst Strike (a strike: another delivery).
settings=W.stratagem_settings({
    {type=136,id=1063322614,package='0x25B8CFF26C7C0112',payload='0x2D3BD00B1ED411B1',sequence=NATIVE[136],group=5,
        row=4,cooldown=180,fields=pres(1063322614)},
    {type=118,id=3523620028,package='0xDBAE525060F06D70',payload='0xC897C0D84448AB2C',sequence=NATIVE[118],group=5,
        row=0,cooldown=80,fields=pres(3523620028)},
    {type=41,id=3193297673,package='0x6369816737A36A40',payload='0x05F3C83A91075766',sequence=NATIVE[41],group=5,
        row=1,cooldown=75,fields=pres(3193297673)},
    {type=22,id=2281932031,package='0xFE0DB34AC2B9AC61',payloads={'0xED13DDC480EC6910','0x73F8498BFFDCF415'},
        sequence=NATIVE[22],group=3,row=1,cooldown=90},
    {type=130,id=1298599997,package='0x15EB7241C3616351',payloads={'0xDDEE9646723E09D3','0x73F8498BFFDCF415'},
        sequence=NATIVE[130],group=7,row=6,cooldown=480},
    rooted('Orbital 380mm HE Barrage',125),
    rooted('Orbital Airburst Strike',83),
})
for kind,r in pairs(settings.rows)do ROW[kind]=r.address end
for _,kind in ipairs({118,136,125,83})do
    W.write(ROW[kind]+0x50,W.u32(4294967295));W.write(ROW[kind]+0x80,W.u32(2));W.write(ROW[kind]+0xC0,W.u32(1))
end
local ID380,AIRBURST_ID,GAS_ID=3108516875,1560416221,3193297673
W.catalogue({[PRECISION_ID]=2,[BIG_ID]=2,[ID380]=2,[AIRBURST_ID]=2})
local BOMB=W.bombardment()
local ID22,ID130=2281932031,1298599997
local PRECORD={{type=124,uses=-1,granted=1},{type=33,uses=-1,granted=1},{type=118,uses=-1,granted=0},
    {type=22,uses=-1,granted=0},{type=130,uses=-1,granted=0},{type=41,uses=-1,granted=1}}
local PSPEC={definition='orbital_gas_barrage',token='Orbital Precision Strike',carrier='Orbital 380mm HE Barrage',
    slots={0},order={PRECISION_ID,ID22,ID130}}
-- A live mission's record: every entry's cooldown end one shared, non-zero time from the record's build (110331400 in
-- all four mission snapshots), below the game clock (165760761): never called, ready.
local BASELINE,CLOCK=110331400,165760761
local function pworld(record,opts)
    mission({host=not(opts and opts.client)})
    local hud={}
    for k,e in ipairs(record or PRECORD)do hud[k]={type=e.type,code={}}end
    local h=W.stratagem_hud({peer=LOCAL,slots=hud,record=record or PRECORD})
    for k=0,#(record or PRECORD)-1 do W.write(h.record+0x38+0x188+k*0x30+0x18,W.u64(BASELINE))end
    BOMB.set_clock(CLOCK)
    return h
end
local function cooldown_at(h,index)return h.record+0x38+0x188+index*0x30+0x18 end
local function converted(record,opts)
    local h=pworld(record,opts)
    local job=settle_job(slots.convert_virtual(PSPEC))
    assert(job.status=='converted',tostring(job.code)..' '..tostring(job.reason))
    return h
end
local function vanilla(id)return b.unhex(PD.records[tostring(id)].vanilla)end
-- The 380mm's vanilla record with the 120mm's pattern words: exactly the six words that differ.
local DESIRED=vanilla(ID380)
for _,w in ipairs(PD.compatibility[tostring(ID380)].words)do
    DESIRED=DESIRED:sub(1,w.offset)..vanilla(BIG_ID):sub(w.offset+1,w.offset+4)..DESIRED:sub(w.offset+5)
end
local CARRIER={carrier='Orbital 380mm HE Barrage'}
-- Stage C: the 380mm's vanilla record with the 120mm's pattern words (not its shells) and the shell list 197, 197, 197.
local GAS_SHELLS={carrier='Orbital 380mm HE Barrage',shells='Orbital Gas Strike'}
local PATTERN_ONLY=vanilla(ID380)
for _,w in ipairs(PD.compatibility[tostring(ID380)].words)do
    if not(w.offset>=0x40 and w.offset<0x60)then
        PATTERN_ONLY=PATTERN_ONLY:sub(1,w.offset)..vanilla(BIG_ID):sub(w.offset+1,w.offset+4)..PATTERN_ONLY:sub(w.offset+5)
    end
end
local DESIRED_C=PATTERN_ONLY:sub(1,0x40)..W.u32(197)..W.u32(197)..W.u32(197)..PATTERN_ONLY:sub(0x4D)
local function donors()return BOMB.read(BIG_ID)==vanilla(BIG_ID)and BOMB.read(GAS_ID)==vanilla(GAS_ID)end
-- The proof's definition with its donor, and the Runtime's virtual-slot record a selection would have left.
local function define_gas()
    local virtual=require('hd2runtime/runtime/virtual_stratagems')
    local selector=require('hd2runtime/runtime/stratagem_selector')
    virtual.reset_for_tests();selector.reset_for_tests()
    local texts=require('hd2runtime/runtime/text_resources')
    local NAME=texts.handle('gb_name','ORBITAL GAS BARRAGE','mods/test/payload')
    local ICON=require('hd2runtime/runtime/image_resources').handle('gb_icon','mods/test/payload')
    virtual.define({id='orbital_gas_barrage',display={name=NAME,description=NAME,icon=ICON},
        selection={token='Orbital Precision Strike'},mission={discover=true,exclude={'Orbital 120mm HE Barrage'}},
        payload={donor='Orbital 120mm HE Barrage'}},'mods/test/payload')
    selector.set_virtual_slots_for_tests({slots={[0]={definition='orbital_gas_barrage',token=PRECISION_ID,type=118}},
        pairs={PRECISION_ID,ID22,ID130}})
    return selector
end
-- Every tick: the carrier in the record means its record holds the 120mm pattern.
local function watch_carrier(h)
    local w={seen=0,violations=0}
    scheduler.attach({status='active',tick=function()
        if b.u32(W.read(h.record+0x38+0x188+2*0x30,4),0)==125 then
            w.seen=w.seen+1
            if BOMB.read(ID380)~=DESIRED then w.violations=w.violations+1 end
        end
    end})
    return w
end
"""


def lua(body):
    return run(WORLD + SLOT + PAYLOAD + body)


class BombardmentPayloadResearchTests(unittest.TestCase):
    def test_the_research_and_its_domain(self):
        self.assertEqual((RESEARCH['writes'], RESEARCH['protectionChanges']), (0, 0))
        self.assertFalse(any(RESEARCH['pinnedBytesMismatchPerSnapshot'].values()))
        self.assertEqual(len(RESEARCH['snapshots']), 7)
        for snap in RESEARCH['snapshots']:
            self.assertEqual((snap['instances'], snap['barrages'], snap['privateCopies'], snap['activeVariants']),
                (0, 0, 0, 0), snap['snapshot'])
            for name, record in snap['records'].items():
                self.assertEqual((len(record['owners']), record['rowsListing']), (1, [record['type']]), name)
        records = {r['name']: r for r in RESEARCH['records'].values()}
        self.assertEqual(records['Orbital 120mm HE Barrage']['shells'], [194, 137, 137])
        self.assertEqual(records['Orbital Gas Strike']['shells'], [197])
        self.assertEqual(records['Orbital 380mm HE Barrage']['shells'], [80, 266, 266])
        compatible = sorted(c['name'] for c in RESEARCH['compatibility'].values() if c['compatible'])
        self.assertEqual(compatible, ['Orbital 380mm HE Barrage', 'Orbital Napalm Barrage', 'Orbital Walking Barrage'])
        words = {c['name']: [(w['offset'], w['carrier'], w['donor']) for w in c['words']]
            for c in RESEARCH['compatibility'].values()}
        self.assertEqual(words['Orbital 380mm HE Barrage'], [(0x08, 1.5, 0.75), (0x1C, 3.0, 2.0), (0x24, 36.0, 27.0),
            (0x40, 80, 194), (0x44, 266, 137), (0x48, 266, 137)])
        reasons = {c['name']: c['reasons'] for c in RESEARCH['compatibility'].values()}
        self.assertIn('row +0x3C (call-in delivery) 1, the donor 5', reasons['Orbital Airburst Strike'])
        self.assertTrue(reasons['Orbital Gatling Barrage'][0].startswith('record words outside the pattern differ'))
        roles = {group: len(rows) for group, rows in RESEARCH['pins'].items()}
        self.assertEqual(set(roles), {'recordLookup', 'privateCopies', 'instances', 'shells', 'timing', 'spread',
            'readiness', 'gasChain', 'variants'})
        import sys
        sys.path.insert(0, str(ROOT / 'scripts'))
        import generate_bombardment_payload
        self.assertEqual(generate_bombardment_payload.generate(check=True), [])


class BombardmentPayloadTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(lua(body), b'ok')

    def test_only_after_the_conversion_the_carrier_takes_the_120mm_pattern_and_is_restored_exactly(self):
        self.check(r"""
-- Before the conversion: refused, nothing written.
local h=pworld()
local writes=#W.runtime.writes
local early=settle_job(payload.apply(CARRIER))
assert(early.status=='refused'and early.code=='NOT_CONVERTED'and#W.runtime.writes==writes,tostring(early.code))
-- After it: exactly the six differing words, in one guarded transaction, the record then the 120mm pattern.
local job=settle_job(slots.convert_virtual(PSPEC))
assert(job.status=='converted')
writes=#W.runtime.writes
local before=BOMB.read(ID380)
assert(before==vanilla(ID380))
local applied=settle_job(payload.apply(CARRIER))
assert(applied.status=='applied',tostring(applied.code)..' '..tostring(applied.reason))
assert(applied.writes==6 and applied.words==6 and#W.runtime.writes==writes+6)
assert(applied.verify.record and applied.verify.donor and applied.verify.shellCount==3 and applied.verify.nonTarget)
assert(BOMB.read(ID380)==DESIRED,'the carrier record holds the 120mm pattern')
for i=writes+1,#W.runtime.writes do
    local at=W.runtime.writes[i].address
    assert(at>=BOMB.record(ID380)and at+#W.runtime.writes[i].bytes<=BOMB.record(ID380)+192,'only the carrier record')
end
-- Every word outside the six is the carrier's own.
local now=BOMB.read(ID380)
for o=0,188,4 do
    local changed=now:sub(o+1,o+4)~=before:sub(o+1,o+4)
    local listed=false
    for _,w in ipairs(PD.compatibility[tostring(ID380)].words)do if w.offset==o then listed=true end end
    assert(changed==listed,'word +'..o)
end
local r=payload.inspect(require('hd2runtime/runtime/event_world').open(),'Orbital 380mm HE Barrage')
assert(r.desired and not r.vanilla and r.shellCount==3 and table.concat(r.shells,',')=='194,137,137')
assert(math.abs(r.shellDelay[1]-0.75)<1e-6 and math.abs(r.salvoDelay[1]-2)<1e-6 and math.abs(r.scatter-27)<1e-6)
assert(r.perSalvo==3 and r.salvos==5 and r.owners==1 and#r.rowsListing==1 and r.ownRow)
assert(donors(),'the 120mm and the Gas Strike records are never written')
assert(count('carrier payload APPLIED: Orbital 380mm HE Barrage takes Orbital 120mm HE Barrage\'s pattern on its own '
    ..'BombardmentComponentData: 6 writes; record verified true; shells 3; donor record vanilla true; package resident; '
    ..'non-target bytes unchanged true; protection restored true')==1,table.concat(logged,' | '))
-- Applying again changes nothing.
local again=settle_job(payload.apply(CARRIER))
assert(again.status=='applied'and again.already and#W.runtime.writes==writes+6)
-- The restore: the vanilla words back (shells in reverse order), the whole record exactly vanilla.
local restored=settle_job(payload.restore())
assert(restored.status=='restored'and restored.exact and restored.writes==6,tostring(restored.code))
assert(BOMB.read(ID380)==vanilla(ID380)and donors()and#W.runtime.writes==writes+12)
assert(count('the whole record equals its vanilla bytes: true')==1)
local none=settle_job(payload.restore())
assert(none.status=='refused'and none.code=='NOT_APPLIED')
return 'ok'
""")

    def test_wrong_family_and_unsupported_carriers_are_refused_with_nothing_written(self):
        self.check(r"""
local h=converted()
local writes=#W.runtime.writes
for name,code in pairs({['Orbital Airburst Strike']='NOT_COMPATIBLE',['Orbital Gatling Barrage']='NOT_COMPATIBLE',
        ['Orbital 120mm HE Barrage']='NOT_COMPATIBLE',['A/MG-43 Machine Gun Sentry']='NOT_COMPATIBLE',
        ['Orbital Napalm Barrage']='NOT_CONVERTED'})do
    local job=settle_job(payload.apply({carrier=name}))
    assert(job.status=='refused'and job.code==code,name..': '..tostring(job.code)..' '..tostring(job.reason))
end
assert(payload.compatible('Orbital Airburst Strike')==false and select(2,payload.compatible('Orbital Airburst Strike'))[1]
    =='row +0x3C (call-in delivery) 1, the donor 5')
assert(select(2,payload.compatible('A/MG-43 Machine Gun Sentry'))[1]=='no reviewed BombardmentComponentData record')
assert(payload.compatible('Orbital 380mm HE Barrage',"Orbital Gas Strike")==false,'only the 120mm\'s pattern is researched')
assert(#W.runtime.writes==writes and BOMB.read(ID380)==vanilla(ID380)and donors())
return 'ok'
""")

    def test_ownership_and_the_exact_vanilla_fingerprint_are_required(self):
        self.check(r"""
local h=converted()
local writes=#W.runtime.writes
local function refused(code)
    local job=settle_job(payload.apply(CARRIER))
    assert(job.status=='refused'and job.code==code,code..' expected, got '..tostring(job.code)..' '..tostring(job.reason))
    assert(#W.runtime.writes==writes,'nothing written')
end
-- A second index slot naming the carrier's record: shared.
BOMB.slot(43,'0x1111111111111111',PD.records[tostring(ID380)].record)
refused('SHARED')
BOMB.slot(43,'0x0000000000000000',0)
-- Another row listing the carrier's payload: shared.
local list=W.alloc(16);W.write(list,b.unhex('D6B1C3ED17B466EF'))
local saved=W.read(ROW[130]+0x98,12)
W.write(ROW[130]+0x98,W.u64(list)..W.u32(1))
refused('SHARED')
W.write(ROW[130]+0x98,saved)
-- One byte of the carrier's record not vanilla: a conflict.
local at=BOMB.record(ID380)+0x2C
local byte=W.read(at,1)
W.write(at,string.char((byte:byte()+1)%256))
refused('CONFLICT')
W.write(at,byte)
-- The donor's record not vanilla: refused (it is never written).
at=BOMB.record(BIG_ID)+0x24
byte=W.read(at,1)
W.write(at,string.char((byte:byte()+1)%256))
refused('DONOR_CHANGED')
W.write(at,byte)
-- A donor shell row changed: refused.
local shell=W.read(W.GAME+PD.shellTable+194*8,8)
local row=b.pointer(shell,0)
local first=W.read(row,4)
W.write(row,'XXXX')
refused('SHELL_CHANGED')
W.write(row,first)
-- The framing changed: refused.
local header=W.read(BOMB.index-28,4)
W.write(BOMB.index-28,'\0\0\0\0')
refused('FRAMING_CHANGED')
W.write(BOMB.index-28,header)
-- A changed pin: refused.
payload.reset_for_tests()
local pin=PD.pins[1]
local saved_pin=W.read(W.GAME+pin.rva,1)
W.write(W.GAME+pin.rva,'\204')
refused('UNSUPPORTED_BUILD')
W.write(W.GAME+pin.rva,saved_pin)
payload.reset_for_tests()
-- All restored: it applies.
local job=settle_job(payload.apply(CARRIER))
assert(job.status=='applied',tostring(job.code)..' '..tostring(job.reason))
return 'ok'
""")

    def test_solo_host_mission_and_before_the_first_call_in(self):
        self.check(r"""
local h=converted()
local writes=#W.runtime.writes
local function refused(code)
    local job=settle_job(payload.apply(CARRIER))
    assert(job.status=='refused'and job.code==code,code..' expected, got '..tostring(job.code)..' '..tostring(job.reason))
    assert(#W.runtime.writes==writes)
end
local R=require('hd2runtime/domains/stratagem_slots').record
-- Another player's stratagem record: not solo.
W.write(h.record+R.count,W.u32(2))
refused('NOT_SOLO')
W.write(h.record+R.count,W.u32(1))
-- A call-in of the converted entry in flight: a call; final for this conversion, even once the beacon is gone.
W.call_ins({{key=W.RECORD_KEY,slot=2,done=0}})
refused('ALREADY_CALLED')
W.call_ins({})
refused('ALREADY_CALLED')
-- A client: refused.
W.state(4,{host=false})
refused('NOT_HOST')
W.state(4,{host=true})
-- Aboard the ship: refused.
W.state(3)
refused('NOT_IN_MISSION')
return 'ok'
""")

    def test_no_barrage_no_variant_and_the_donor_package_first(self):
        self.check(r"""
local h=converted()
local writes=#W.runtime.writes
local function refused(code)
    local job=settle_job(payload.apply(CARRIER))
    assert(job.status=='refused'and job.code==code,code..' expected, got '..tostring(job.code)..' '..tostring(job.reason))
    assert(#W.runtime.writes==writes)
end
-- A running barrage of the carrier's payload: refused at once.
BOMB.set_instances({PD.records[tostring(ID380)].payload})
refused('IN_USE')
-- Another barrage running: waited for, then refused.
payload.BARRAGE_WAIT=1
BOMB.set_instances({PD.records[tostring(GAS_ID)].payload})
refused('BARRAGE_ACTIVE')
BOMB.set_instances({},0)
-- An active variant naming the carrier's payload: refused.
BOMB.set_variant({PD.records[tostring(ID380)].payload})
refused('VARIANT_ACTIVE')
BOMB.set_variant({PD.records[tostring(GAS_ID)].payload})
-- The donor's call-in package not resident: requested and loaded first, then the write.
local assets=require('hd2runtime/core/assets')
local RM=require('hd2runtime/domains/package_residency').loader.refcountMap
local map_header,map_entries=W.alloc(0x1000),W.alloc(0x1000)
W.write(map_header+RM.entries,W.u64(map_entries))
assets.reset()
assets.prove=function()return {instance=map_header,request=2,capacity=16}end
local PACKAGE=assets.dependency_for_stratagem(BIG_ID,'x').package
local requested=0
W.runtime.packages[PACKAGE]='absent'
W.runtime.package_request=function()requested=requested+1;W.runtime.packages[PACKAGE]=nil end
local job=settle_job(payload.apply(CARRIER))
assert(job.status=='applied'and requested==1 and tostring(job.package):find('loaded',1,true),tostring(job.code)..' '
    ..tostring(job.reason)..' '..tostring(job.package))
assert(BOMB.read(ID380)==DESIRED and donors())
-- A barrage of the carrier running: the restore waits (refused, retried by the caller); then exact.
BOMB.set_instances({PD.records[tostring(ID380)].payload})
local held=settle_job(payload.restore())
assert(held.status=='refused'and held.code=='IN_USE'and BOMB.read(ID380)==DESIRED)
BOMB.set_instances({},0)
local back=settle_job(payload.restore())
assert(back.status=='restored'and back.exact and BOMB.read(ID380)==vanilla(ID380)and donors())
return 'ok'
""")

    def test_the_restore_refuses_other_writers_and_the_lua_close_restores(self):
        self.check(r"""
local h=converted()
local job=settle_job(payload.apply(CARRIER))
assert(job.status=='applied')
-- Another writer changed the record after us: the restore refuses it (nothing written).
local at=BOMB.record(ID380)+0x24
local word=W.read(at,4)
W.write(at,W.u32(7))
local writes=#W.runtime.writes
local conflict=settle_job(payload.restore())
assert(conflict.status=='refused'and conflict.code=='CONFLICT'and#W.runtime.writes==writes)
W.write(at,word)
-- The Lua state closing: restored under the same guards.
payload.finalize_now()
assert(BOMB.read(ID380)==vanilla(ID380)and payload.state().applied==false and donors())
-- Already vanilla (the game reloaded it, say): nothing to write, exact.
local job2=settle_job(payload.apply(CARRIER))
assert(job2.status=='applied')
W.write(BOMB.record(ID380),vanilla(ID380))
writes=#W.runtime.writes
local back=settle_job(payload.restore())
assert(back.status=='restored'and back.writes==0 and back.exact and#W.runtime.writes==writes)
return 'ok'
""")

    def test_a_live_mission_entry_is_not_called_although_its_cooldown_end_is_not_zero(self):
        # 0.1.0's live run: a fresh entry's cooldown end is the record's shared build time, not 0; it was refused.
        self.check(r"""
local h=converted()
assert(b.u32(W.read(cooldown_at(h,2),4),0)==BASELINE,'a live-like, non-zero cooldown end on the fresh entry')
local writes=#W.runtime.writes
local applied=settle_job(payload.apply(CARRIER))
assert(applied.status=='applied'and applied.writes==6 and#W.runtime.writes==writes+6,tostring(applied.code)..' '
    ..tostring(applied.reason))
assert(BOMB.read(ID380)==DESIRED and donors())
return 'ok'
""")

    def test_a_call_after_the_conversion_refuses_the_payload_for_good(self):
        self.check(r"""
local h=converted()
local writes=#W.runtime.writes
-- The carrier is called: the game sets its cooldown end to a new time.
W.write(cooldown_at(h,2),W.u64(CLOCK+180000))
local job=settle_job(payload.apply(CARRIER))
assert(job.status=='refused'and job.code=='ALREADY_CALLED'and tostring(job.reason):find('changed since the conversion',1,true),
    tostring(job.code)..' '..tostring(job.reason))
-- Never retried in that mission, even if the value came back.
W.write(cooldown_at(h,2),W.u64(BASELINE))
job=settle_job(payload.apply(CARRIER))
assert(job.status=='refused'and job.code=='ALREADY_CALLED'and tostring(job.reason):find('not retried',1,true))
assert(#W.runtime.writes==writes and BOMB.read(ID380)==vanilla(ID380))
return 'ok'
""")

    def test_a_token_still_cooling_down_at_the_conversion_is_refused(self):
        self.check(r"""
local h=pworld()
-- The token was called before the conversion: its cooldown end is above the game clock.
W.write(cooldown_at(h,2),W.u64(CLOCK+60000))
local job=settle_job(slots.convert_virtual(PSPEC))
assert(job.status=='converted')
local writes=#W.runtime.writes
local refused=settle_job(payload.apply(CARRIER))
assert(refused.status=='refused'and refused.code=='ON_COOLDOWN'and#W.runtime.writes==writes,tostring(refused.code))
return 'ok'
""")

    def test_the_carrier_is_never_callable_before_its_payload(self):
        # The sequence: conversion -> packages resident -> payload pending -> the carrier NOT callable yet -> payload
        # APPLIED -> the carrier callable. The carrier only enters the record in the tick its payload is written.
        self.check(r"""
local selector=define_gas()
local h=pworld()
local w=watch_carrier(h)
-- Both call-in packages absent: the loader requests them; they become resident only when released.
local assets=require('hd2runtime/core/assets')
local RM=require('hd2runtime/domains/package_residency').loader.refcountMap
local map_header,map_entries=W.alloc(0x1000),W.alloc(0x1000)
W.write(map_header+RM.entries,W.u64(map_entries))
assets.reset()
assets.prove=function()return {instance=map_header,request=2,capacity=16}end
local P380=assets.dependency_for_stratagem(ID380,'x').package
local P120=assets.dependency_for_stratagem(BIG_ID,'x').package
W.runtime.packages[P380],W.runtime.packages[P120]='absent','absent'
local requested=0
W.runtime.package_request=function()requested=requested+1 end
local writes=#W.runtime.writes
local result
local handle=selector.convert_with_payload('orbital_gas_barrage',function(x)result=x end,'Orbital 380mm HE Barrage')
for _=1,40 do tick()end
-- Pending: the packages loading; the slot still the token (the carrier not in the record: not callable); nothing written.
assert(handle.status=='pending'and handle.phase=='packages'and result==nil,tostring(handle.status)..' '..tostring(handle.phase))
assert(entry_type(h,2)==118 and w.seen==0 and#W.runtime.writes==writes and requested>=1)
assert(BOMB.read(ID380)==vanilla(ID380))
-- Released: in ONE tick the conversion and the payload.
W.runtime.packages[P380],W.runtime.packages[P120]=nil,nil
for _=1,40 do tick()end
assert(handle.status=='applied'and result==handle,tostring(handle.status)..' '..tostring(handle.code)..' '
    ..tostring(handle.reason))
assert(handle.conversion.status=='converted'and handle.payload.status=='applied'and handle.payload.writes==6)
assert(entry_type(h,2)==125 and BOMB.read(ID380)==DESIRED and donors()and#W.runtime.writes==writes+7)
assert(w.seen>0 and w.violations==0,'the carrier was in the record without its payload in '..w.violations..' ticks of '
    ..w.seen)
assert(count('carrier payload APPLIED')==1 and count('stratagem slot CONVERTED')==1)
return 'ok'
""")

    def test_the_watch_catches_the_old_two_step_order(self):
        # Negative control for the watch above: 0.1.0's order (the conversion job, then the payload job) left the carrier
        # callable without its payload for at least one tick.
        self.check(r"""
local h=pworld()
local w=watch_carrier(h)
local job=slots.convert_virtual(PSPEC)
local applied
for _=1,40 do
    tick()
    if job.status=='converted'and not applied then applied=payload.apply(CARRIER)end
end
assert(job.status=='converted'and applied and applied.status=='applied'and BOMB.read(ID380)==DESIRED)
assert(w.violations>=1,'the two-step order exposed the carrier for '..w.violations..' ticks')
return 'ok'
""")

    def test_a_refused_payload_undoes_the_conversion_in_the_same_tick(self):
        self.check(r"""
local selector=define_gas()
local h=pworld()
local w=watch_carrier(h)
-- The token is still cooling down (called before): the preflight and the conversion pass, the payload refuses in the
-- conversion's tick, and the conversion is undone in that same tick.
W.write(cooldown_at(h,2),W.u64(CLOCK+60000))
local writes=#W.runtime.writes
local handle=selector.convert_with_payload('orbital_gas_barrage',nil,'Orbital 380mm HE Barrage')
for _=1,40 do tick()end
assert(handle.status=='refused'and handle.code=='ON_COOLDOWN'and handle.undone==true,tostring(handle.status)..' '
    ..tostring(handle.phase)..' '..tostring(handle.code)..' '..tostring(handle.reason)..' | '..table.concat(logged,' | '))
assert(entry_type(h,2)==118 and w.seen==0 and#W.runtime.writes==writes+2 and BOMB.read(ID380)==vanilla(ID380))
assert(count('carrier with payload REFUSED: ON_COOLDOWN')==1 and count('the conversion was undone in the same tick: true')==1)
-- A running barrage: waited for while the slot is still the token; then the write.
selector.set_virtual_slots_for_tests({slots={[0]={definition='orbital_gas_barrage',token=PRECISION_ID,type=118}},
    pairs={PRECISION_ID,ID22,ID130}})
W.write(cooldown_at(h,2),W.u64(BASELINE))
BOMB.set_instances({PD.records[tostring(GAS_ID)].payload})
local second=selector.convert_with_payload('orbital_gas_barrage',nil,'Orbital 380mm HE Barrage')
for _=1,40 do tick()end
assert(second.status=='pending'and second.phase=='barrage'and entry_type(h,2)==118 and w.seen==0)
BOMB.set_instances({},0)
for _=1,40 do tick()end
assert(second.status=='applied'and entry_type(h,2)==125 and BOMB.read(ID380)==DESIRED and w.violations==0,
    tostring(second.code)..' '..tostring(second.reason))
return 'ok'
""")

    def test_stage_c_the_gas_strike_shell_on_the_120mm_pattern_and_the_exact_restore(self):
        self.check(r"""
local h=converted()
local writes=#W.runtime.writes
local applied=settle_job(payload.apply(GAS_SHELLS))
assert(applied.status=='applied',tostring(applied.code)..' '..tostring(applied.reason))
-- The 120mm pattern first (3 words), then the shell list on it (3 words): 6 writes, two transactions in one call.
assert(applied.writes==6 and applied.patternWrites==3 and applied.shellWrites==3 and#W.runtime.writes==writes+6)
assert(table.concat(applied.shells,',')=='197,197,197'and applied.shellDonor=='Orbital Gas Strike')
assert(applied.verify.record and applied.verify.donor and applied.verify.shellDonor and applied.verify.chain
    and applied.verify.shellCount==3 and applied.verify.shells and applied.verify.nonTarget)
assert(BOMB.read(ID380)==DESIRED_C,'the 120mm pattern with shells 197, 197, 197')
-- The first three writes are the timing and spread words, the last three the shells, ascending.
local offsets={}
for i=writes+1,#W.runtime.writes do offsets[#offsets+1]=W.runtime.writes[i].address-BOMB.record(ID380)end
assert(table.concat(offsets,',')=='8,28,36,64,68,72',table.concat(offsets,','))
local r=payload.inspect(require('hd2runtime/runtime/event_world').open(),'Orbital 380mm HE Barrage',nil,'Orbital Gas Strike')
assert(r.desired and table.concat(r.shells,',')=='197,197,197'and r.shellCount==3 and r.perSalvo==3 and r.salvos==5)
assert(math.abs(r.shellDelay[1]-0.75)<1e-6 and math.abs(r.salvoDelay[1]-2)<1e-6 and math.abs(r.scatter-27)<1e-6)
local d=payload.donors(require('hd2runtime/runtime/event_world').open(),'Orbital Gas Strike')
assert(d.pattern and d.shells and d.chain and donors(),'the 120mm, the Gas Strike and its chain are never written')
local order={}
for _,line in ipairs(logged)do
    if line:find('120mm pattern applied:',1,true)then order[#order+1]='pattern'end
    if line:find('Gas Strike shell 197 applied:',1,true)then order[#order+1]='shells'end
end
assert(table.concat(order,'>')=='pattern>shells',table.concat(order,'>'))
assert(count('shell list = 197, 197, 197 (shell donor Orbital Gas Strike): 3 writes; APPLIED: 6 writes in all')==1,
    table.concat(logged,' | '))
-- The restore: the complete original record, exactly.
local back=settle_job(payload.restore())
assert(back.status=='restored'and back.exact and back.writes==6 and back.donors.pattern and back.donors.shells)
assert(BOMB.read(ID380)==vanilla(ID380)and donors()and#W.runtime.writes==writes+12)
assert(count('the whole record equals its vanilla bytes: true; Orbital 120mm HE Barrage record vanilla true; Orbital Gas '
    ..'Strike record vanilla true')==1,table.concat(logged,' | '))
return 'ok'
""")

    def test_stage_c_the_gas_strike_donor_and_its_chain_must_be_exactly_as_reviewed(self):
        self.check(r"""
local h=converted()
local writes=#W.runtime.writes
local function refused(code)
    local job=settle_job(payload.apply(GAS_SHELLS))
    assert(job.status=='refused'and job.code==code,code..' expected, got '..tostring(job.code)..' '..tostring(job.reason))
    assert(#W.runtime.writes==writes and BOMB.read(ID380)==vanilla(ID380))
end
local function poke(at)local saved=W.read(at,1);W.write(at,string.char((saved:byte()+1)%256));return saved end
-- The Gas Strike's own record not vanilla.
local at=BOMB.record(GAS_ID)+0x08
local saved=poke(at);refused('SHELL_DONOR_CHANGED');W.write(at,saved)
-- Its shell row, its explosion, its damage, its volume template, a status: each changed refuses.
for _,target in ipairs({{BOMB.shell_row(197),0x3C},{BOMB.chain_row('explosion',82),0x64},{BOMB.chain_row('damage',447),44},
        {BOMB.chain_row('template',16),4},{BOMB.chain_row('status',42),0}})do
    at=target[1]+target[2]
    saved=poke(at);refused('GAS_CHAIN_CHANGED');W.write(at,saved)
end
-- A word that holds a relocated pointer (masked) may differ.
local masked=BOMB.chain_row('explosion',82)+PD.gasChainRows[1].masked[1]
W.write(masked,W.u32(0x12345678))
-- Another shell donor than the researched one.
local other=settle_job(payload.apply({carrier='Orbital 380mm HE Barrage',shells='Orbital Smoke Strike'}))
assert(other.status=='refused'and other.code=='NOT_COMPATIBLE')
local job=settle_job(payload.apply(GAS_SHELLS))
assert(job.status=='applied'and BOMB.read(ID380)==DESIRED_C,tostring(job.code)..' '..tostring(job.reason))
return 'ok'
""")

    def test_stage_c_a_refused_shell_list_rolls_the_pattern_back(self):
        self.check(r"""
local h=converted()
local writes=#W.runtime.writes
-- The shell transaction refused (as a guard would): the 120mm pattern written first is rolled back.
local T=require('hd2runtime/core/guarded_transaction')
local apply=T.apply
T.apply=function(runtime,plan)
    if plan.changes[1]and plan.changes[1].label:find('+0x40',1,true)and not plan.changes[1].label:find('undo',1,true)then
        return {status='REJECTED',reason='test: the shell list refused',writes=0}
    end
    return apply(runtime,plan)
end
local job=settle_job(payload.apply(GAS_SHELLS))
T.apply=apply
assert(job.status=='refused'and job.code=='GUARD_REJECTED'and tostring(job.reason):find('the 120mm pattern undone: true',
    1,true),tostring(job.code)..' '..tostring(job.reason))
assert(BOMB.read(ID380)==vanilla(ID380)and#W.runtime.writes==writes+6 and donors(),'3 pattern writes, 3 undone')
assert(count('120mm pattern applied:')==1 and count('Gas Strike shell 197 applied:')==0)
assert(payload.state()==nil or payload.state().applied~=true)
return 'ok'
""")

    def test_stage_c_the_carrier_is_never_callable_before_its_gas_shells(self):
        self.check(r"""
local virtual=require('hd2runtime/runtime/virtual_stratagems')
local selector=define_gas()
virtual.reset_for_tests()
local texts=require('hd2runtime/runtime/text_resources')
local NAME=texts.handle('gb_name','ORBITAL GAS BARRAGE','mods/test/payload')
local ICON=require('hd2runtime/runtime/image_resources').handle('gb_icon','mods/test/payload')
virtual.define({id='orbital_gas_barrage',display={name=NAME,description=NAME,icon=ICON},
    selection={token='Orbital Precision Strike'},mission={discover=true,exclude={'Orbital 120mm HE Barrage'}},
    payload={donor='Orbital 120mm HE Barrage',shells='Orbital Gas Strike'}},'mods/test/payload')
local h=pworld()
local seen,bad=0,0
scheduler.attach({status='active',tick=function()
    if b.u32(W.read(h.record+0x38+0x188+2*0x30,4),0)==125 then
        seen=seen+1
        if BOMB.read(ID380)~=DESIRED_C then bad=bad+1 end
    end
end})
-- The Gas Strike's package absent: the step waits with the slot still the token.
local assets=require('hd2runtime/core/assets')
local RM=require('hd2runtime/domains/package_residency').loader.refcountMap
local map_header,map_entries=W.alloc(0x1000),W.alloc(0x1000)
W.write(map_header+RM.entries,W.u64(map_entries))
assets.reset()
assets.prove=function()return {instance=map_header,request=2,capacity=16}end
local PGAS=assets.dependency_for_stratagem(GAS_ID,'x').package
W.runtime.packages[PGAS]='absent'
W.runtime.package_request=function()end
local writes=#W.runtime.writes
local handle=selector.convert_with_payload('orbital_gas_barrage',nil,'Orbital 380mm HE Barrage')
for _=1,40 do tick()end
assert(handle.status=='pending'and handle.phase=='packages'and entry_type(h,2)==118 and seen==0
    and#W.runtime.writes==writes,tostring(handle.status)..' '..tostring(handle.phase))
W.runtime.packages[PGAS]=nil
for _=1,40 do tick()end
assert(handle.status=='applied'and handle.payload.writes==6 and handle.payload.shellDonor=='Orbital Gas Strike',
    tostring(handle.code)..' '..tostring(handle.reason))
assert(entry_type(h,2)==125 and BOMB.read(ID380)==DESIRED_C and#W.runtime.writes==writes+7 and donors())
assert(seen>0 and bad==0,'the carrier was in the record without its gas shells in '..bad..' ticks')
-- A refused shell list in the conversion's tick: the pattern and the conversion undone in that tick.
assert(settle_job(payload.restore()).exact and settle_job(slots.restore()).status=='restored')
selector.set_virtual_slots_for_tests({slots={[0]={definition='orbital_gas_barrage',token=PRECISION_ID,type=118}},
    pairs={PRECISION_ID,ID22,ID130}})
seen,bad=0,0
local T=require('hd2runtime/core/guarded_transaction')
local apply=T.apply
T.apply=function(runtime,plan)
    if plan.changes[1]and plan.changes[1].label:find('+0x40',1,true)and not plan.changes[1].label:find('undo',1,true)then
        return {status='REJECTED',reason='test: the shell list refused',writes=0}
    end
    return apply(runtime,plan)
end
local second=selector.convert_with_payload('orbital_gas_barrage',nil,'Orbital 380mm HE Barrage')
for _=1,40 do tick()end
T.apply=apply
assert(second.status=='refused'and second.undone==true and entry_type(h,2)==118 and seen==0
    and BOMB.read(ID380)==vanilla(ID380),tostring(second.code)..' '..tostring(second.reason))
return 'ok'
""")

    def test_a_definition_names_its_donor_and_the_selector_applies_only_after_its_conversion(self):
        self.check(r"""
local virtual=require('hd2runtime/runtime/virtual_stratagems')
local selector=require('hd2runtime/runtime/stratagem_selector')
virtual.reset_for_tests()
local texts=require('hd2runtime/runtime/text_resources')
local NAME=texts.handle('gb_name','ORBITAL GAS BARRAGE','mods/test/payload')
local ICON=require('hd2runtime/runtime/image_resources').handle('gb_icon','mods/test/payload')
local function define(spec)return pcall(virtual.define,spec,'mods/test/payload')end
local ok,why=define({id='a',display={name=NAME,description=NAME,icon=ICON},selection={token='Orbital Precision Strike'},
    mission={carrier='Orbital 380mm HE Barrage'},payload={donor='Orbital 120mm HE Barrage'}})
assert(not ok and tostring(why):find('payload needs mission.discover',1,true),tostring(why))
ok,why=define({id='b',display={name=NAME,description=NAME,icon=ICON},selection={token='Orbital Precision Strike'},
    mission={discover=true},payload={donor='Orbital 120mm HE Barrage',damage=300}})
assert(not ok and tostring(why):find('payload takes only donor and shells',1,true),tostring(why))
ok,why=define({id='b2',display={name=NAME,description=NAME,icon=ICON},selection={token='Orbital Precision Strike'},
    mission={discover=true},payload={donor='Orbital 120mm HE Barrage',shells={197}}})
assert(not ok and tostring(why):find('payload.shells must name a stratagem',1,true),tostring(why))
ok,why=define({id='b3',display={name=NAME,description=NAME,icon=ICON},selection={token='Orbital Precision Strike'},
    mission={discover=true},payload={donor='Orbital 120mm HE Barrage',shells='Orbital 120mm HE Barrage'}})
assert(not ok and tostring(why):find('the shell donor must differ',1,true),tostring(why))
ok,why=define({id='c',display={name=NAME,description=NAME,icon=ICON},selection={token='Orbital Precision Strike'},
    mission={discover=true},payload={donor='Orbital Precision Strike'}})
assert(not ok and tostring(why):find('the donor must differ from the token',1,true),tostring(why))
local GAS=virtual.define({id='orbital_gas_barrage',display={name=NAME,description=NAME,icon=ICON},selection={token='Orbital Precision Strike'},
    mission={discover=true,exclude={'Orbital 120mm HE Barrage'}},payload={donor='Orbital 120mm HE Barrage'}},
    'mods/test/payload')
assert(GAS.payload.donor=='Orbital 120mm HE Barrage'and GAS.payload.donorId==BIG_ID)
local plain=virtual.define({id='plain',display={name=NAME,description=NAME,icon=ICON},selection={token='Orbital Precision Strike'},
    mission={discover=true}},'mods/test/payload')
assert(plain.payload==nil)
-- The selector: no payload, or no conversion of that definition: refused with nothing written.
local h=pworld()
local writes=#W.runtime.writes
local none=selector.apply_payload('plain')
assert(none.status=='refused'and none.code=='NO_PAYLOAD')
local early=selector.apply_payload('orbital_gas_barrage')
assert(early.status=='refused'and early.code=='NOT_CONVERTED'and#W.runtime.writes==writes)
-- A discovered carrier that is not payload-compatible is refused by the conversion spec.
local spec,reason=selector.conversion_spec('orbital_gas_barrage','Orbital Airburst Strike')
assert(spec==nil and tostring(reason):find('is not payload-compatible',1,true),tostring(reason))
-- After the conversion of that definition: the selector applies the donor's pattern on the converted carrier.
local job=settle_job(slots.convert_virtual(PSPEC))
assert(job.status=='converted')
local applied=settle_job(selector.apply_payload('orbital_gas_barrage'))
assert(applied.status=='applied'and applied.carrier=='Orbital 380mm HE Barrage'and BOMB.read(ID380)==DESIRED,
    tostring(applied.code)..' '..tostring(applied.reason))
assert(selector.payload_state().applied==true)
local back=settle_job(selector.restore_payload())
assert(back.status=='restored'and back.exact and BOMB.read(ID380)==vanilla(ID380))
return 'ok'
""")

    def test_discovery_with_a_payload_takes_only_payload_compatible_carriers(self):
        self.check(r"""
local h=pworld()
local present={[PRECISION_ID]=true,[ID22]=true,[ID130]=true}
local found=slots.discover_carriers(require('hd2runtime/runtime/event_world').open(),'Orbital Precision Strike',{present=present,
    exclude={'Orbital 120mm HE Barrage'},payload={donor='Orbital 120mm HE Barrage'}})
assert(found.ready and found.chosen and found.chosen.name=='Orbital 380mm HE Barrage'and found.chosen.payloadCompatible
    and found.chosen.payloadWords==6)
local function find(name)for _,c in ipairs(found.candidates)do if c.name==name then return c end end end
local airburst=find('Orbital Airburst Strike')
assert(not airburst.eligible and table.concat(airburst.reasons,'; '):find('not payload-compatible with Orbital 120mm HE '
    ..'Barrage\'s pattern (row +0x3C (call-in delivery) 1, the donor 5)',1,true),table.concat(airburst.reasons,'; '))
local eligible=0
for _,c in ipairs(found.candidates)do if c.eligible then eligible=eligible+1;assert(c.payloadCompatible)end end
assert(eligible==1)
-- Without a payload the generic filter still accepts the strike.
local plain=slots.discover_carriers(require('hd2runtime/runtime/event_world').open(),'Orbital Precision Strike',{present=present,
    exclude={'Orbital 120mm HE Barrage'}})
local generic
for _,c in ipairs(plain.candidates)do if c.name=='Orbital Airburst Strike'then generic=c end end
assert(generic.eligible)
return 'ok'
""")


if __name__ == '__main__':
    unittest.main()
