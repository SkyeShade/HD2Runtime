"""proof/GasBarragePayloadProof 0.2.2, carrier revalidation (docs/custom-stratagems.md, "Carrier revalidation"): the
discovered carrier is a cache validated against the current loadout before every mission; invalid, it is discarded and
the discovery runs again (three carriers offline: the 380mm, the Napalm and the Walking Barrage).
0.2.1, the carrier lifecycle (docs/custom-stratagems.md, "The carrier presentation
lifecycle"): aboard the ship the carrier is native (its own card in the loadout picker); at mission start its Gas Barrage
look and code are applied and verified before the conversion and the payload (runtime/carrier_presentation.lua); on the
return to the ship they are restored exactly once the mission HUD is torn down (at the latest after a deadline), and the
loadout screen opening restores any stale look in its own frame, before the native UI paints. Stage C as before.
0.2.0, stage C (docs/custom-stratagems.md, "Payload stage C"): stage B with the
carrier's shell list pointing at the Orbital Gas Strike's shell 197 ([197, 197, 197]) on the 120mm's pattern.
Stage B (0.1.1, docs "Payload stage B"): GasBarrageMissionProof 0.5.0's
live-proven flow (the discovered carrier, its Gas Barrage look and code) unchanged, plus the 120mm's bombardment pattern
and shells on the carrier's OWN BombardmentComponentData. The carrier is never callable without it: both packages are
loaded while the virtual slot is still its token ("NOT READY"), then the conversion and the payload happen in one tick
("READY TO CALL"); restored exactly at the mission end. Offline, the proof's own addon end to end on the event world with the bombardment
component as the game's lookup reads it (W.bombardment)."""
import json
import re
import unittest

from support import ROOT, run
from test_stratagem_calldown_code import WORLD, PROOF
from test_stratagem_slot_conversion import SLOT
from test_gas_barrage_mission_proof import HARNESS, FLOW

FOLDER = ROOT / 'proof/GasBarragePayloadProof'

PAYLOAD_FLOW = r"""
local PD=require('hd2runtime/domains/bombardment_payload')
require('hd2runtime/runtime/bombardment_payload').reset_for_tests()
local BOMB=W.bombardment()
local GAS_ID=3193297673
local function vanilla(id)return b.unhex(PD.records[tostring(id)].vanilla)end
-- Stage C: the Napalm's vanilla record with the 120mm's pattern words (not its shells) and the shells 197, 197, 197.
local DESIRED=vanilla(NAPALM_ID)
for _,w in ipairs(PD.compatibility[tostring(NAPALM_ID)].words)do
    if not(w.offset>=0x40 and w.offset<0x60)then
        DESIRED=DESIRED:sub(1,w.offset)..vanilla(BIG_ID):sub(w.offset+1,w.offset+4)..DESIRED:sub(w.offset+5)
    end
end
DESIRED=DESIRED:sub(1,0x40)..W.u32(197)..W.u32(197)..W.u32(197)..DESIRED:sub(0x4D)
local function donors()return BOMB.read(BIG_ID)==vanilla(BIG_ID)and BOMB.read(GAS_ID)==vanilla(GAS_ID)end
-- A live mission's record: every entry's cooldown end one shared, non-zero time from the record's build (110331400 in
-- all four mission snapshots), below the game clock (W.bombardment's default 165760761).
local function live_cooldowns(h,n)for k=0,n-1 do W.write(h.record+0x38+0x188+k*0x30+0x18,W.u64(110331400))end end
-- Every tick: the carrier (the Napalm Barrage, 106) in the record means its record holds the 120mm pattern.
local function watch_carrier(h)
    local w={seen=0,violations=0}
    scheduler.attach({status='active',tick=function()
        if b.u32(W.read(h.record+0x38+0x188+2*0x30,4),0)==106 then
            w.seen=w.seen+1
            if BOMB.read(NAPALM_ID)~=DESIRED then w.violations=w.violations+1 end
        end
    end})
    return w
end
-- The carrier lifecycle: the mission presentation module, the mission HUD torn down, the loadout screen reopened.
local CP=require('hd2runtime/runtime/carrier_presentation');CP.reset_for_tests()
local HUDD=require('hd2runtime/domains/stratagem_calldown').hud
local LOADOUT={{type=118},{type=41},{type=22},{type=130}}
local function teardown_hud()W.write(b.pointer(W.read(W.GAME+HUDD.global,8),0)+HUDD.setUp,string.char(0))end
local function reopen()W.write(SCREEN.owner+SEL.loadout.root,W.u64(SCREEN.ui))end
local function code106()
    local count=b.u32(W.read(ROW106+0x48,4),0)
    local array=b.pointer(W.read(ROW106+0x40,8),0)
    local out={}
    for i=0,count-1 do out[#out+1]=b.u32(W.read(array+i*4,4),0)end
    return table.concat(out,',')
end
-- The carrier row holds the Gas Barrage look and code: the custom icon, UUDD and Runtime text (not its own).
local function gas_look()
    local row=W.read(ROW106,400)
    return row:sub(0xB1,0xB8)==CUSTOM and code106()=='1,1,3,3'and row:sub(0x29,0x2C)~=CARRIER_ROW:sub(0x29,0x2C)
        and row:sub(0x2D,0x30)~=CARRIER_ROW:sub(0x2D,0x30)and row:sub(0x31,0x34)~=CARRIER_ROW:sub(0x31,0x34)
end
local function native106()return W.read(ROW106,400)==CARRIER_ROW end
-- Every tick: the carrier (106) in the record means its row holds the Gas Barrage look and code.
local function watch_look(h)
    local w={seen=0,violations=0}
    scheduler.attach({status='active',tick=function()
        if b.u32(W.read(h.record+0x38+0x188+2*0x30,4),0)==106 then
            w.seen=w.seen+1
            if not gas_look()then w.violations=w.violations+1 end
        end
    end})
    return w
end
-- The order of the proof's lines with these keys.
local function order_of(keys)
    local out={}
    for _,line in ipairs(logged)do
        for _,key in ipairs(keys)do if line:find('] '..key,1,true)then out[#out+1]=key end end
    end
    return table.concat(out,' > ')
end
-- The mission and its end, as the game does them: the record rebuilt for the ship, then the ship state (with the
-- mission HUD torn down, as in the mission-end transition snapshot, unless kept).
local function start_mission()
    mission({host=true})
    local record,hud=mission_record({118,41,22,130})
    local h=W.stratagem_hud({peer=LOCAL,slots=hud,record=record})
    live_cooldowns(h,#record)
    return h
end
local function end_mission(h,keep_hud)
    W.call_ins({})
    for k,kind in ipairs({130,22,41,118})do W.write(h.record+0x38+0x188+(k-1)*0x30,W.u32(kind))end
    W.write(h.record+0x38+0x788,W.u32(4))
    tick(4)
    if not keep_hud then teardown_hud()end
    W.state(3)
end
-- The native loadout UI's paint (the harness's per-frame bind) records whether the carrier was native each time.
local painted={}
local function watch_paint()
    local original=SCREEN.frame
    SCREEN.frame=function()painted[#painted+1]=native106();return original()end
end
local function to_mission()
    proof()
    tick(40)
    ship({})
    tick(4)
    select_into(0)
    native_append(41);native_append(22);native_append(130)
    SCREEN.set('selecting',false);tick(8)
    SCREEN.close();tick(4)
    W.saved_loadout({{id=PRECISION_ID},{id=3193297673},{id=ID22},{id=1298599997}})
    tick(80)
end
"""


# Three payload-compatible carriers owned: the 380mm (type 125, as live), the Napalm (106) and the Walking Barrage (127,
# a fixture type), each at its catalogue root with its reviewed presentation and native code. Discovery ranks them
# 380mm, Napalm (6 pattern words each, by name), Walking (7).
FLOW3 = FLOW.replace('''local NAPALM_ID=2902516083
''', '''local NAPALM_ID=2902516083
local BIG380_ID,WALK_ID=3108516875,3279813377
''').replace('''        row=5,cooldown=240,fields=pres(NAPALM_ID)},
''', '''        row=5,cooldown=240,fields=pres(NAPALM_ID)},
    {type=125,id=BIG380_ID,package='0xFE3EF44300E4A1E2',payload='0xEF66B417EDC3B1D6',sequence={2,3,1,1,4,3,3},group=5,
        row=6,cooldown=240,fields=pres(BIG380_ID)},
    {type=127,id=WALK_ID,package='0xC0C7278D9F015EE7',payload='0xCB7F154719F331EC',sequence={2,3,2,3,2,3},group=5,
        row=7,cooldown=240,fields=pres(WALK_ID)},
''').replace('''for _,kind in ipairs({118,136,106})do''', '''for _,kind in ipairs({118,136,106,125,127})do''').replace(
    '''W.catalogue({[PRECISION_ID]=2,[BIG_ID]=2,[NAPALM_ID]=2})''',
    '''W.catalogue({[PRECISION_ID]=2,[BIG_ID]=2,[NAPALM_ID]=2,[BIG380_ID]=2,[WALK_ID]=2})''')
assert FLOW3.count('BIG380_ID') == 4 and '125,127})do' in FLOW3


def addon():
    from test_event_scripting import SDK
    spec = json.loads((FOLDER / 'hd2runtime.json').read_text(encoding='utf-8'))
    body = (FOLDER / 'src/addon.lua').read_text(encoding='utf-8-sig')
    return spec['resource'], SDK.wrap_addon(spec['resource'], spec['requires']['hd2runtime']['min_version'], body)


class GasBarragePayloadProofTests(unittest.TestCase):
    def lua(self, body):
        from support import lua as lua_literal
        resource, wrapped = addon()
        self.assertEqual(resource, 'mods/skyeshade/hd2runtime_gas_barrage_payload_proof')
        self.assertEqual(run(WORLD + SLOT + 'local ADDON=' + lua_literal(wrapped) + '\nlocal RESOURCE='
            + lua_literal(resource) + PROOF + HARNESS + FLOW + PAYLOAD_FLOW + body), b'ok')

    def lua3(self, body):
        from support import lua as lua_literal
        resource, wrapped = addon()
        self.assertEqual(run(WORLD + SLOT + 'local ADDON=' + lua_literal(wrapped) + '\nlocal RESOURCE='
            + lua_literal(resource) + PROOF + HARNESS + FLOW3 + PAYLOAD_FLOW + body), b'ok')

    def test_a_cached_carrier_put_in_the_loadout_is_invalidated_and_the_next_carrier_is_discovered(self):
        self.lua3(r'''
rawset(_G,'ModOptionsMenu',MENU)
local payload_module=require('hd2runtime/runtime/bombardment_payload')
local IDS={[125]=BIG380_ID,[106]=NAPALM_ID,[127]=WALK_ID}
local NAMES={[125]='Orbital 380mm HE Barrage',[106]='Orbital Napalm Barrage',[127]='Orbital Walking Barrage'}
local NATIVE_ROWS={}
for kind in pairs(IDS)do NATIVE_ROWS[kind]=W.read(ROW[kind],400)end
local function vanilla_all()
    for _,id in pairs(IDS)do if BOMB.read(id)~=vanilla(id)then return false end end
    return donors()
end
local function natives_all()
    for kind in pairs(IDS)do if W.read(ROW[kind],400)~=NATIVE_ROWS[kind]then return false end end
    return W.read(ROW118,400)==PRECISION_ROW and W.read(ROW136,400)==DONOR_ROW
end
-- Every tick: a carrier in the current loadout (natively, not the converted Gas Barrage entry) keeps its vanilla
-- bombardment record and its native row: no payload, look or code is ever written on it.
local guard={kinds={},violations=0,seen=0}
scheduler.attach({status='active',tick=function()
    for kind in pairs(guard.kinds)do
        guard.seen=guard.seen+1
        if BOMB.read(IDS[kind])~=vanilla(IDS[kind])or W.read(ROW[kind],400)~=NATIVE_ROWS[kind]then
            guard.violations=guard.violations+1
        end
    end
end})
local entries={118,41,22,130}
-- The player changes loadout slots natively aboard the ship ({[slot] = type}, the screen open), then the game saves.
local function change_slots(changes)
    local list={}
    for k,v in ipairs(entries)do list[k]={type=v}end
    ship(list);tick(4)
    for slot=0,3 do
        if changes[slot]then
            W.write(SCREEN.record+SEL.loadout.entries+slot*SEL.loadout.entryStride+SEL.loadout.entryType,
                W.u32(changes[slot]));repaint();tick(4)
            entries[slot+1]=changes[slot]
        end
    end
    SCREEN.close();tick(4)
    local ids={}
    for k,v in ipairs(entries)do ids[k]={id=require('hd2runtime/runtime/stratagem_loadout').id_of(
        require('hd2runtime/runtime/event_world').open(),v)}end
    W.saved_loadout(ids)
    tick(24)
end
-- One mission with the current loadout; natively present carriers guarded every tick.
local function play(expected_kind)
    guard.kinds={}
    for _,v in ipairs(entries)do if IDS[v]then guard.kinds[v]=true end end
    mission({host=true})
    local record,hud=mission_record(entries)
    local h=W.stratagem_hud({peer=LOCAL,slots=hud,record=record})
    live_cooldowns(h,#record)
    tick(64)
    local ok=entry_type(h,2)==expected_kind and payload_module.inspect(require('hd2runtime/runtime/event_world').open(),
        NAMES[expected_kind],nil,'Orbital Gas Strike').desired
    end_mission(h)
    tick(16)
    guard.kinds={}
    return ok
end
local function n(text)return count(text)end
to_mission()
-- MISSION 1: the loadout without the 380mm: the 380mm is the carrier; the Gas Barrage succeeds; restored.
assert(n('CARRIER: Orbital 380mm HE Barrage SELECTED (type 125, stable id 3108516875, orbital/BombardmentComponentData): '
    ..'the first of 3 eligible carriers')==1,table.concat(logged,' | '))
assert(play(125),table.concat(logged,' | '))
assert(n('] READY TO CALL: the virtual Gas Barrage slot is the carrier Orbital 380mm HE Barrage')==1
    and n('PAYLOAD: RESTORED: the carrier Orbital 380mm HE Barrage')==1
    and n('RETURN TO SHIP: carrier presentation RESTORED: 6 writes; exact = true')==1 and vanilla_all()and natives_all(),
    table.concat(logged,' | '))
-- BETWEEN MISSIONS: the 380mm put in the loadout: the cached carrier is invalidated aboard the ship (in_loadout) and
-- the discovery runs again: the Napalm.
change_slots({[3]=125})
assert(n('CARRIER INVALIDATED: Orbital 380mm HE Barrage reason: in_loadout (in the loadout; checked aboard the ship '
    ..'against the saved loadout')==1,table.concat(logged,' | '))
assert(n('CARRIER: Orbital Napalm Barrage SELECTED (type 106, stable id 2902516083, orbital/BombardmentComponentData): '
    ..'the first of 2 eligible carriers')==1,table.concat(logged,' | '))
local order={}
for _,line in ipairs(logged)do
    for _,key in ipairs({'CARRIER INVALIDATED: Orbital 380mm','CARRIER CANDIDATE: Orbital 380mm HE Barrage (type 125',
            'CARRIER: Orbital Napalm Barrage SELECTED'})do
        if line:find('] '..key,1,true)then order[#order+1]=key end
    end
end
assert(table.concat(order,' > '):find('CARRIER INVALIDATED: Orbital 380mm > CARRIER CANDIDATE: Orbital 380mm HE Barrage '
    ..'(type 125 > CARRIER: Orbital Napalm Barrage SELECTED',1,true),table.concat(order,' > '))
assert(n('in_loadout=true special_case=false package_available=true presentation=true code=true payload_compatible=true '
    ..'(6 words) -> rejected: in the loadout')>=1,table.concat(logged,' | '))
assert(n('carrier = Orbital Napalm Barrage (stable id 2902516083); carrier present in saved loadout = false')>=1
    and n('-> READY: start a solo mission')>=2,table.concat(logged,' | '))
-- MISSION 2: the 380mm natively in the loadout (never written); the Napalm carries the Gas Barrage.
assert(play(106),table.concat(logged,' | '))
assert(n('] READY TO CALL: the virtual Gas Barrage slot is the carrier Orbital Napalm Barrage')==1
    and n('PAYLOAD: RESTORED: the carrier Orbital Napalm Barrage')==1
    and n('RETURN TO SHIP: carrier presentation RESTORED: 6 writes; exact = true')==2 and vanilla_all()and natives_all(),
    table.concat(logged,' | '))
-- BETWEEN MISSIONS: the 380mm out, the Napalm in: the Napalm is invalidated; the 380mm is eligible again.
change_slots({[3]=106})
assert(n('CARRIER INVALIDATED: Orbital Napalm Barrage reason: in_loadout')==1
    and n('CARRIER: Orbital 380mm HE Barrage SELECTED (type 125')==2,table.concat(logged,' | '))
-- MISSION 3.
assert(play(125),table.concat(logged,' | '))
assert(n('] READY TO CALL: the virtual Gas Barrage slot is the carrier Orbital 380mm HE Barrage')==2
    and vanilla_all()and natives_all(),table.concat(logged,' | '))
-- BETWEEN MISSIONS: both the 380mm and the Napalm in the loadout: the next valid candidate, the Walking Barrage.
change_slots({[2]=125})
assert(n('CARRIER INVALIDATED: Orbital 380mm HE Barrage reason: in_loadout')==2
    and n('CARRIER: Orbital Walking Barrage SELECTED (type 127')==1,table.concat(logged,' | '))
assert(play(127),table.concat(logged,' | '))
assert(n('] READY TO CALL: the virtual Gas Barrage slot is the carrier Orbital Walking Barrage')==1
    and vanilla_all()and natives_all(),table.concat(logged,' | '))
assert(guard.seen>0 and guard.violations==0,'a carrier in the loadout was written in '..guard.violations..' ticks')
assert(n('TEST REFUSED')==0 and n('callback failed')==0,table.concat(logged,' | '))
done()
return 'ok'
''')

    def test_the_final_check_at_mission_start_replaces_a_carrier_found_in_the_mission_record(self):
        self.lua3(r'''
rawset(_G,'ModOptionsMenu',MENU)
local payload_module=require('hd2runtime/runtime/bombardment_payload')
to_mission()
assert(count('CARRIER: Orbital 380mm HE Barrage SELECTED')==1)
-- The 380mm picked natively into slot 3 and the game saving it only as the mission starts: no revalidation aboard the
-- ship could see it; the final check at mission start invalidates it and discovers the Napalm.
local before=BOMB.read(BIG380_ID)
local row125=W.read(ROW[125],400)
ship({{type=118},{type=41},{type=22},{type=130}});tick(4)
W.write(SCREEN.record+SEL.loadout.entries+3*SEL.loadout.entryStride+SEL.loadout.entryType,W.u32(125));repaint();tick(4)
SCREEN.close();tick(8)
assert(count('] CARRIER INVALIDATED')==0)
W.saved_loadout({{id=PRECISION_ID},{id=3193297673},{id=ID22},{id=BIG380_ID}})
mission({host=true})
local record,hud=mission_record({118,41,22,125})
local h=W.stratagem_hud({peer=LOCAL,slots=hud,record=record})
live_cooldowns(h,#record)
tick(64)
assert(count('CARRIER INVALIDATED: Orbital 380mm HE Barrage reason: in_loadout (in the loadout; checked at mission start '
    ..'against the saved loadout and this mission record)')==1,table.concat(logged,' | '))
assert(count('CARRIER: Orbital Napalm Barrage SELECTED (type 106')==1 and entry_type(h,2)==106
    and count('] READY TO CALL: the virtual Gas Barrage slot is the carrier Orbital Napalm Barrage')==1,
    table.concat(logged,' | '))
assert(BOMB.read(BIG380_ID)==before and W.read(ROW[125],400)==row125,'the 380mm in the record is never written')
done()
return 'ok'
''')

    def test_no_eligible_carrier_refuses_and_a_refused_conversion_never_writes_a_payload_on_a_carrier_in_the_record(self):
        self.lua3(r'''
rawset(_G,'ModOptionsMenu',MENU)
local selector=require('hd2runtime/runtime/stratagem_selector')
to_mission()
-- Every compatible carrier in the mission record: none eligible: refused, nothing written.
local writes=#W.runtime.writes
mission({host=true})
local record,hud=mission_record({118,125,106,127})
local h=W.stratagem_hud({peer=LOCAL,slots=hud,record=record})
live_cooldowns(h,#record)
tick(64)
assert(count('CARRIER: none eligible')==1 and count('MISSION START: TEST REFUSED (nothing converted, nothing written): '
    ..'no carrier is eligible for the current loadout')==1 and entry_type(h,2)==118 and#W.runtime.writes==writes,
    table.concat(logged,' | '))
-- The runtime's own guard, asked directly for a carrier that is in the record: refused, no conversion, no payload.
local handle=selector.convert_with_payload('orbital_gas_barrage',nil,'Orbital 380mm HE Barrage')
for _=1,200 do if handle.status~='pending'then break end;tick()end
assert(handle.status~='applied'and#W.runtime.writes==writes and BOMB.read(BIG380_ID)==vanilla(BIG380_ID),
    tostring(handle.status)..' '..tostring(handle.code)..' '..tostring(handle.reason))
done()
return 'ok'
''')

    def test_a_mission_without_a_virtual_slot_discovers_and_writes_nothing(self):
        self.lua3(r'''
rawset(_G,'ModOptionsMenu',MENU)
proof()
tick(40)
W.saved_loadout({{id=3193297673},{id=ID22},{id=1298599997}})
tick(40)
local writes=#W.runtime.writes
mission({host=true})
local record,hud=mission_record({41,22,130})
local h=W.stratagem_hud({peer=LOCAL,slots=hud,record=record})
tick(64)
assert(count('MISSION START: TEST REFUSED (nothing converted, nothing written): no virtual Gas Barrage slot in this '
    ..'mission')==1 and count('] CARRIER: ')==0 and count('] CARRIER CANDIDATE')==0 and#W.runtime.writes==writes,
    table.concat(logged,' | '))
done()
return 'ok'
''')

    def test_the_build_is_stage_c_with_the_carrier_lifecycle(self):
        self.assertEqual((FOLDER / 'VERSION').read_text(encoding='utf-8').strip(), '0.2.2')
        manifest = json.loads((FOLDER / 'hd2runtime.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['name'], 'GasBarragePayloadProof')
        mission = json.loads((ROOT / 'proof/GasBarrageMissionProof/hd2runtime.json').read_text(encoding='utf-8'))
        self.assertNotEqual(manifest['guid'], mission['guid'])
        body = (FOLDER / 'src/addon.lua').read_text(encoding='utf-8-sig')
        self.assertIn("local BUILD='0.2.2 CARRIER REVALIDATION'", body)
        code = '\n'.join(line.split('--')[0] for line in body.splitlines())
        # The carrier: a cache revalidated with the discovery's guards, aboard the ship and at mission start.
        self.assertEqual(code.count('selector.validate_carrier('), 1)
        self.assertEqual(code.count('check_carrier('), 3)
        self.assertIn("payload={donor=DONOR,shells='Orbital Gas Strike'}", code)
        # The payload: once, with the conversion in one tick (never the two-step apply after a separate conversion);
        # the restore at the mission end.
        self.assertEqual(code.count('selector.convert_with_payload('), 1)
        self.assertEqual(code.count('selector.apply_payload('), 0)
        self.assertEqual(code.count('selector.restore_payload('), 1)
        self.assertIn('NOT READY: carrier payload is still being applied', code)
        self.assertIn('READY TO CALL', code)
        # The shell is named only through the definition's shell donor: no shell, explosion or record value of its own.
        for forbidden in ('shells={', 'hd2.stratagem(TOKEN)', 'hd2.stratagem(DONOR)', 'hd2.stratagem(GAS_STRIKE)',
                'allow_unverified', 'transaction.apply', '.write(', 'owned_write', 'hd2.patch(', 'hd2.transaction(',
                'apply_body', 'bombardment_payload'):
            self.assertNotIn(forbidden, code)
        # The look and code: never the public ensures (toggle-only restores); the lifecycle module, applied once at
        # mission start, restored by the job aboard the ship and in one tick at the loadout screen opening.
        self.assertEqual(code.count('hd2.ensure('), 0)
        self.assertEqual(code.count('carrier_presentation.apply('), 1)
        self.assertEqual(code.count('carrier_presentation.restore('), 2)
        self.assertEqual(code.count('carrier_presentation.restore_now('), 1)
        self.assertEqual(code.count('selector.watch('), 1)
        self.assertIsNone(re.search(r'(?<!carrier_)presentation\.(apply_text|restore|apply)\(', code))
        self.assertEqual(sorted(p.name for p in (FOLDER / 'images').iterdir()), ['orbital_gas_barrage_masks.png'])

    def test_the_carrier_takes_the_120mm_pattern_after_the_conversion_and_is_restored_exactly(self):
        self.lua(r'''
rawset(_G,'ModOptionsMenu',MENU)
to_mission()
assert(count('GasBarragePayloadProof 0.2.2 CARRIER REVALIDATION BUILD')==1)
-- SHIP: the carrier is chosen and stays NATIVE: its whole row, its own text, icon and code; the token untouched.
assert(native106()and W.read(ROW118,400)==PRECISION_ROW and W.read(ROW136,400)==DONOR_ROW)
assert(CP.state()==nil and count('[HD2Runtime] carrier presentation APPLIED')==0)
assert(count('SAFE: applied at mission start (aboard the ship the carrier keeps its own code)')==1,table.concat(logged,' | '))
assert(count('the carrier row holds its native text and its native icon and its native code (right right down left '
    ..'right up) (aboard the ship the carrier is native; its Gas Barrage look and code are applied at mission start)')>=1,
    table.concat(logged,' | '))
-- The discovery takes only a payload-compatible carrier; its record reported read-only.
assert(count('CARRIER CANDIDATE: Orbital Napalm Barrage (type 106, stable id 2902516083, orbital/'
    ..'BombardmentComponentData): owned=true selectable=true enabled=true unlimited=true in_loadout=false '
    ..'special_case=false package_available=true presentation=true code=true payload_compatible=true (6 words) -> '
    ..'SELECTED')==1,table.concat(logged,' | '))
assert(count('not payload-compatible with Orbital 120mm HE Barrage\'s pattern (the donor itself)')==1)
assert(count('PAYLOAD RECORD: Orbital Napalm Barrage BombardmentComponentData at 0x')==1
    and count('(record 13 of index slot 37, reviewed 13/37; owners 1; 192 bytes; rows listing its payload: 1, its own '
    ..'true; own row\'s payloads catalogued true): shell list at +0x40 = 234, 238, 238 (count 3), 5 shells per salvo, 5 '
    ..'salvos, delay between shells 0.5 (+0 random), between salvos 2 (+0 random), scatter 25')==1
    and count('exactly vanilla true; holds the Gas Barrage payload false; payload-compatible true; differs from the 120mm at: '
    ..'+0x04 shells per salvo (read at creation) 5 -> 3; +0x08 delay between shells 0.5 -> 0.75; +0x24 per-shell '
    ..'scatter 25 -> 27; +0x40 shell 0 234 -> 194; +0x44 shell 1 238 -> 137; +0x48 shell 2 238 -> 137; instances of it '
    ..'0; active variant naming it false')==1,table.concat(logged,' | '))
assert(count('the 120mm record vanilla = true; the Gas Strike record vanilla = true')>=1)
assert(count('payload: payload-compatible true (6 pattern words differ from the 120mm); its record exactly vanilla true; '
    ..'the 120mm record vanilla = true; the Gas Strike record vanilla = true; 120mm donor unchanged = true; Gas Strike '
    ..'donor unchanged = true (its record, and its shell 197, explosion 82, damage 447, gas volume template 16 and statuses '
    ..'42/44 as reviewed: true); the 120mm pattern and the Gas Strike shell ON (written in the mission) -> READY: start a '
    ..'solo mission')==1,table.concat(logged,' | '))
assert(BOMB.read(NAPALM_ID)==vanilla(NAPALM_ID)and donors(),'nothing written aboard the ship')
-- MISSION: NOT READY while the packages load (the slot still the token); then the conversion and the payload in one
-- tick; only then READY TO CALL.
local writes=#W.runtime.writes
local h=start_mission()
local w,g=watch_carrier(h),watch_look(h)
tick(64)
-- MISSION START: the native carrier verified, then its look and code applied and verified, before the conversion.
assert(count('MISSION START: the carrier Orbital Napalm Barrage is native (its native text and its native icon and its '
    ..'native code (right right down left right up)); applying the Gas Barrage look and code before the conversion')==1,
    table.concat(logged,' | '))
assert(count('MISSION START: carrier presentation APPLIED (before the conversion; the carrier was native and its exact '
    ..'native values are kept for the restore): 6 writes; the carrier Orbital Napalm Barrage row holds the Gas Barrage text '
    ..'and the Gas Barrage icon and the Gas Barrage code (up up down down); Orbital Precision Strike presentation native = '
    ..'true, code native = true')==1,table.concat(logged,' | '))
assert(gas_look()and g.seen>0 and g.violations==0,'the carrier was callable without its look and code in '
    ..g.violations..' ticks')
assert(count('NOT READY: carrier payload is still being applied (the carrier\'s, the 120mm\'s and the Gas Strike\'s '
    ..'call-in packages are loading); the virtual slot is still an Orbital Precision Strike, the carrier is not callable '
    ..'yet: do NOT call it')==1,
    table.concat(logged,' | '))
assert(count('MISSION START: conversion APPLIED: loadout slot 0 = record entry 2 -> the carrier Orbital Napalm Barrage')==1)
assert(count('READY TO CALL: the virtual Gas Barrage slot is the carrier Orbital Napalm Barrage, and its own bombardment '
    ..'record holds the 120mm pattern with the Gas Strike shell 197 (the conversion, the 120mm pattern, the Gas Strike '
    ..'shell and PAYLOAD: APPLIED in the same tick')==1,table.concat(logged,' | '))
assert(w.seen>0 and w.violations==0,'the carrier was callable without its payload in '..w.violations..' ticks')
local order={}
for _,line in ipairs(logged)do
    for _,key in ipairs({'MISSION START: carrier presentation APPLIED','NOT READY: carrier payload',
            'MISSION START: conversion APPLIED','PAYLOAD: APPLIED','READY TO CALL'})do
        if line:find('] '..key,1,true)then order[#order+1]=key end
    end
end
assert(table.concat(order,' > ')=='MISSION START: carrier presentation APPLIED > NOT READY: carrier payload > MISSION '
    ..'START: conversion APPLIED > PAYLOAD: APPLIED > READY TO CALL',
    table.concat(order,' > '))
assert(count('PAYLOAD: APPLIED: the carrier Orbital Napalm Barrage\'s own BombardmentComponentData: the 120mm pattern '
    ..'(3 writes), then the Gas Strike shell (3 writes), 6 writes in all; shell list = 197, 197, 197; shell donor = '
    ..'Orbital Gas Strike; the record verified true; packed with 3 shells; Gas Strike donor unchanged = true; 120mm donor '
    ..'unchanged = true; non-target bytes unchanged true; the packages resident')==1,table.concat(logged,' | '))
-- The runtime's own order: the pattern, then the shell list.
local inner={}
for _,line in ipairs(logged)do
    if line:find('carrier payload 120mm pattern applied:',1,true)then inner[#inner+1]='pattern'end
    if line:find('carrier payload Gas Strike shell 197 applied:',1,true)then inner[#inner+1]='shells'end
end
assert(table.concat(inner,'>')=='pattern>shells',table.concat(inner,'>'))
assert(BOMB.read(NAPALM_ID)==DESIRED and donors()and#W.runtime.writes==writes+8+7,'record '..tostring(BOMB.read(NAPALM_ID)==DESIRED)..' donors '..tostring(donors())..' writes '..(#W.runtime.writes-writes))
-- The carrier's own record: the 120mm's pattern with the Gas Strike shell.
local carrier_line
for _,line in ipairs(logged)do
    if line:find('PAYLOAD RECORD: Orbital Napalm Barrage BombardmentComponentData',1,true)
        and line:find('holds the Gas Barrage payload true',1,true)then carrier_line=line end
end
assert(carrier_line and carrier_line:find('shell list at +0x40 = 197, 197, 197 (count 3), 3 shells per salvo, 5 salvos, '
    ..'delay between shells 0.75 (+0 random), between salvos 2 (+0 random), scatter 27',1,true)
    and carrier_line:find('exactly vanilla false',1,true)and carrier_line:find('differs from the 120mm at: +0x40 shell 0 '
    ..'197 -> 194; +0x44 shell 1 197 -> 137; +0x48 shell 2 197 -> 137;',1,true),tostring(carrier_line))
assert(entry_type(h,2)==106 and entry_type(h,3)==41 and W.read(ROW118,400)==PRECISION_ROW and W.read(ROW136,400)==DONOR_ROW)
-- CALL-IN with Up Up Down Down (only now): a 120mm-style barrage expected.
tick(8)
W.call_ins({{key=W.RECORD_KEY,slot=2,done=0}})
tick(8)
assert(count('CALL-IN: the virtual Gas Barrage slot (loadout slot 0, record entry 2) was called')==1
    and count('expect a GAS BARRAGE: 5 salvos of 3 Orbital Gas Strike shells (197), 0.75 s between shells, 2 s between '
    ..'salvos, scatter 27; each shell\'s gas cloud (15 s, 15 m) with gas and confusion')==1,table.concat(logged,' | '))
-- MISSION: the look and code kept for the whole mission.
assert(gas_look()and g.violations==0)
-- MISSION END: the record rebuilt for the ship and the mission HUD torn down; aboard, the carrier's record and its
-- look and code restored exactly.
end_mission(h)
tick(16)
assert(count('MISSION END: state Ship; payload applied: restoring aboard the ship')==1,table.concat(logged,' | '))
assert(count('the carrier presentation applied: restored aboard the ship once the mission HUD is torn down (at the '
    ..'latest when the loadout screen opens)')==1,table.concat(logged,' | '))
assert(count('RETURN TO SHIP: carrier presentation RESTORED: 6 writes; exact = true (the name, cased name, description, '
    ..'icon and code back to the bytes captured at mission start); native = true; the carrier Orbital Napalm Barrage row '
    ..'holds its native text and its native icon and its native code (right right down left right up); Orbital Precision '
    ..'Strike presentation native = true, code native = true')==1,table.concat(logged,' | '))
-- The whole carrier row byte-identical to its native row; the token and the donor byte-identical; no Runtime text left
-- registered.
assert(native106()and W.read(ROW118,400)==PRECISION_ROW and W.read(ROW136,400)==DONOR_ROW)
assert(require('hd2runtime/runtime/text_resources').state().index==nil and not CP.applied())
assert(count('PAYLOAD: RESTORED: the carrier Orbital Napalm Barrage\'s BombardmentComponentData: 6 writes; exact vanilla '
    ..'carrier record = true (after restoration the whole record equals the exact vanilla record before modification); '
    ..'the 120mm record vanilla = true; the Gas Strike record vanilla = true; 120mm donor unchanged = true; Gas Strike '
    ..'donor unchanged = true')==1,table.concat(logged,' | '))
assert(BOMB.read(NAPALM_ID)==vanilla(NAPALM_ID)and donors()and#W.runtime.writes==writes+8+7+6+7)
-- 1. The loadout screen opened aboard the ship: the carrier native, nothing written; the native UI paints it native.
local n=#W.runtime.writes
ship(LOADOUT)
watch_paint()
tick(4)
assert(count('LOADOUT OPEN #1: the carrier Orbital Napalm Barrage row holds its native text and its native icon and its '
    ..'native code (right right down left right up); Orbital Precision Strike presentation native = true, code native = '
    ..'true')==1 and count('-> NATIVE: nothing to restore')==1,table.concat(logged,' | '))
assert(#W.runtime.writes==n and native106()and#painted>0)
for _,ok in ipairs(painted)do assert(ok,'the native loadout UI painted a non-native carrier')end
assert(count('callback failed')==0)
done()
return 'ok'
''')

    def test_the_loadout_opening_restores_a_stale_look_in_its_own_frame_before_the_native_ui_paints(self):
        self.lua(r'''
rawset(_G,'ModOptionsMenu',MENU)
to_mission()
local h=start_mission()
tick(64)
assert(gas_look()and count('] READY TO CALL')==1,table.concat(logged,' | '))
-- 2. The mission ends with the HUD still set up (not torn down): the restore waits for it...
end_mission(h,true)
tick(8)
assert(count('MISSION END: state Ship')==1 and CP.applied()and gas_look()and count('] RETURN TO SHIP')==0,
    table.concat(logged,' | '))
-- ...and the loadout screen opens at once: restored in that very frame, before the native loadout UI paints.
ship(LOADOUT)
watch_paint()
local n=#W.runtime.writes
tick(1)
assert(native106()and not CP.applied(),'restored in the frame of the opening')
assert(#painted>=1,'the native UI painted in that frame')
for _,ok in ipairs(painted)do assert(ok,'the native loadout UI painted the stale carrier')end
assert(count('LOADOUT OPEN #1: a STALE carrier presentation was found and RESTORED in this frame, before the native '
    ..'loadout UI uses the carrier: 6 writes; exact = true; native = true; the carrier Orbital Napalm Barrage row holds '
    ..'its native text and its native icon and its native code (right right down left right up); Orbital Precision '
    ..'Strike presentation native = true, code native = true')==1,table.concat(logged,' | '))
assert(#W.runtime.writes==n+7 and W.read(ROW118,400)==PRECISION_ROW and W.read(ROW136,400)==DONOR_ROW)
-- Idempotent: the HUD deadline and further openings find nothing to restore.
tick(60)
SCREEN.close();tick(2);reopen();tick(2)
assert(count('] RETURN TO SHIP')==0 and count('LOADOUT OPEN #2: ')==1 and count('-> NATIVE: nothing to restore')==1
    and#W.runtime.writes==n+7 and native106(),table.concat(logged,' | '))
assert(count('callback failed')==0)
done()
return 'ok'
''')

    def test_without_any_loadout_opening_the_deadline_restores_aboard_the_ship(self):
        self.lua(r'''
rawset(_G,'ModOptionsMenu',MENU)
to_mission()
local h=start_mission()
tick(64)
-- 3. The HUD never reads torn down and the loadout screen is not opened: restored at the deadline anyway.
end_mission(h,true)
tick(12)
assert(CP.applied()and gas_look())
tick(40)
assert(not CP.applied()and native106()and count('RETURN TO SHIP: carrier presentation RESTORED: 6 writes; exact = '
    ..'true')==1,table.concat(logged,' | '))
-- Then opened: native, nothing written.
local n=#W.runtime.writes
ship(LOADOUT)
tick(4)
assert(count('LOADOUT OPEN #1: ')==1 and count('-> NATIVE: nothing to restore')==1 and#W.runtime.writes==n)
done()
return 'ok'
''')

    def test_reopening_the_loadout_and_native_picks_write_nothing_and_a_second_mission_applies_again(self):
        self.lua(r'''
rawset(_G,'ModOptionsMenu',MENU)
to_mission()
local h=start_mission()
tick(64)
end_mission(h)
tick(16)
assert(count('RETURN TO SHIP: carrier presentation RESTORED: 6 writes; exact = true')==1 and native106())
-- 4/5. The loadout screen opened, closed and reopened; the native picker opened on slots: nothing to restore each time.
local n=#W.runtime.writes
ship(LOADOUT)
watch_paint()
tick(4)
for _=1,4 do SCREEN.close();tick(2);reopen();tick(3)end
for slot=1,3 do
    SCREEN.set('editedSlot',slot);SCREEN.set('selecting',true);tick(4)
    SCREEN.set('selecting',false);tick(4)
end
-- 6. A native stratagem picked into slot 3 (the 120mm), then the original back: the carrier stays native.
W.write(SCREEN.record+SEL.loadout.entries+3*SEL.loadout.entryStride+SEL.loadout.entryType,W.u32(136));repaint();tick(4)
W.write(SCREEN.record+SEL.loadout.entries+3*SEL.loadout.entryStride+SEL.loadout.entryType,W.u32(130));repaint();tick(4)
assert(count('LOADOUT OPEN #5: ')==1 and count('LOADOUT PICKER OPEN #3 (loadout slot 3): ')==1
    and count('-> NATIVE: nothing to restore')==8 and count('STALE')==0,table.concat(logged,' | '))
assert(#W.runtime.writes==n and native106()and W.read(ROW118,400)==PRECISION_ROW)
for _,ok in ipairs(painted)do assert(ok,'the native loadout UI painted a non-native carrier')end
SCREEN.close();tick(8)
-- 7. Another mission: the look and code applied again before the conversion, kept, restored again.
local h2=start_mission()
local g=watch_look(h2)
tick(64)
assert(count('] MISSION START: carrier presentation APPLIED')==2 and count('] READY TO CALL')==2 and entry_type(h2,2)==106
    and gas_look()and g.seen>0 and g.violations==0,table.concat(logged,' | '))
end_mission(h2)
tick(16)
assert(count('RETURN TO SHIP: carrier presentation RESTORED: 6 writes; exact = true')==2 and native106()
    and count('PAYLOAD: RESTORED: ')==2 and BOMB.read(NAPALM_ID)==vanilla(NAPALM_ID)and donors()
    and W.read(ROW118,400)==PRECISION_ROW,table.concat(logged,' | '))
assert(count('callback failed')==0)
done()
return 'ok'
''')

    def test_another_writers_look_is_never_overwritten_and_the_next_mission_is_refused(self):
        self.lua(r'''
rawset(_G,'ModOptionsMenu',MENU)
to_mission()
local h=start_mission()
tick(64)
-- Another writer replaces the carrier's icon during the mission: the restore takes back only this proof's text.
local OTHER=W.u32(0x11111111)..W.u32(0x22222222)
W.write(ROW106+0xB0,OTHER)
end_mission(h)
tick(16)
assert(count('RETURN TO SHIP: carrier presentation restore REFUSED (nothing overwritten; retried when the loadout screen '
    ..'opens): CONFLICT: the icon and code: CONFLICT: the carrier Orbital Napalm Barrage stratagem.presentation.icon no '
    ..'longer holds what this presentation wrote (another writer owns it): not restored; the other part restored')==1,
    table.concat(logged,' | '))
assert(W.read(ROW106+0xB0,8)==OTHER and W.read(ROW118,400)==PRECISION_ROW)
ship(LOADOUT)
tick(4)
assert(count('LOADOUT OPEN #1: a STALE carrier presentation could NOT be restored (nothing overwritten): CONFLICT')==1
    and W.read(ROW106+0xB0,8)==OTHER,table.concat(logged,' | '))
SCREEN.close();tick(8)
-- The next mission: the carrier is not native, so nothing is applied or converted.
local h2=start_mission()
tick(64)
assert(count('MISSION START: TEST REFUSED (nothing converted, nothing written): the carrier Orbital Napalm Barrage is '
    ..'not native at mission start')==1 and entry_type(h2,2)==118 and count('] READY TO CALL')==1,table.concat(logged,' | '))
done()
return 'ok'
''')

    def test_a_full_text_registry_keeps_the_carrier_text_and_the_test_runs(self):
        # 0.30.2: the game's text registry full at mission start (a report: 18 of 18). The carrier keeps its own name
        # and description; the custom icon and code are applied and the slot converts (before: the whole test refused).
        self.lua(r'''
rawset(_G,'ModOptionsMenu',MENU)
to_mission()
W.text_registry({tables={VANILLA,VANILLA,VANILLA},capacity=3})
local writes=#W.runtime.writes
local h=start_mission()
tick(64)
assert(count('carrier presentation TEXT FALLBACK: Orbital Napalm Barrage keeps its own name and description')==1,
    table.concat(logged,' | '))
assert(count('text REGISTRY FULL (read-only diagnostic')==1,'what holds the registry is logged')
assert(count('MISSION START: carrier presentation APPLIED')>=1,'applied')
assert(count('] READY TO CALL')==1,'ready: '..count('] READY TO CALL'))
assert(entry_type(h,2)==106,'converted: '..tostring(entry_type(h,2)))
assert(#W.runtime.writes>writes,'written')
assert(count('TEST REFUSED')==0,'not refused')
done()
return 'ok'
''')

    def test_the_pattern_switched_off_writes_no_payload(self):
        self.lua(r'''
rawset(_G,'ModOptionsMenu',MENU)
to_mission()
callbacks['gas_barrage_payload_proof.pattern'](false,'gas_barrage_payload_proof.pattern')
tick(8)
local writes=#W.runtime.writes
local h=start_mission()
tick(64)
assert(entry_type(h,2)==106 and count('PAYLOAD: the Gas Barrage payload is switched off')==1 and count('READY TO CALL: the '
    ..'carrier with its own payload')==1,table.concat(logged,' | '))
assert(#W.runtime.writes==writes+8+1 and gas_look()and BOMB.read(NAPALM_ID)==vanilla(NAPALM_ID)and donors())
done()
return 'ok'
''')

    def test_a_running_barrage_refuses_before_anything_is_converted(self):
        self.lua(r'''
rawset(_G,'ModOptionsMenu',MENU)
require('hd2runtime/runtime/bombardment_payload').BARRAGE_WAIT=1
to_mission()
local writes=#W.runtime.writes
mission({host=true})
BOMB.set_instances({PD.records[tostring(GAS_ID)].payload})
local record,hud=mission_record({118,41,22,130})
local h=W.stratagem_hud({peer=LOCAL,slots=hud,record=record})
live_cooldowns(h,#record)
tick(80)
-- Waited for while the slot is still the token, then refused: nothing converted, the carrier never callable.
assert(count('NOT READY: carrier payload is still being applied (waiting for running barrages to end before the '
    ..'write)')==1,table.concat(logged,' | '))
assert(count('NOT READY: the carrier payload was REFUSED (BARRAGE_ACTIVE: a bombardment is running (1 instances)); '
    ..'nothing was converted or written; the virtual slot stays an Orbital Precision Strike: do NOT call it')==1,
    table.concat(logged,' | '))
assert(count('PRESENTATION (the payload was refused): carrier presentation RESTORED: 6 writes; exact = true')==1
    and native106(),table.concat(logged,' | '))
assert(entry_type(h,2)==118 and#W.runtime.writes==writes+8+7 and BOMB.read(NAPALM_ID)==vanilla(NAPALM_ID)and donors(),
    'writes '..(#W.runtime.writes-writes))
assert(count('] READY TO CALL')==0,table.concat(logged,' | '))
BOMB.set_instances({},0)
W.state(3)
tick(16)
assert(count('PAYLOAD: RESTORED: ')==0 and count('MISSION END: state Ship; payload refused')==1
    and count('the carrier presentation not applied')==1 and count('] RETURN TO SHIP')==0,table.concat(logged,' | '))
done()
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
