"""The game's own BLOCKED stratagem card state for carriers a custom stratagem reserves (runtime/stratagem_blocking.lua;
research/stratagem-blocking-F5FEE03DCFDB.json; research/docs/stratagem-blocking-F5FEE03DCFDB.md). Offline: the event
world with a loadout screen whose stratagem grid is built, realized and refreshed as the game's code does it (the grid
builder copies the catalogue's server-disabled flag into each card's blocked byte; the per-frame list update realizes
once on the one-shot request), and the account catalogue with card keys that differ from the stable ids, as in game.
Nothing here touches a game process."""
import json
import unittest

from support import ROOT, run
from test_stratagem_calldown_code import WORLD

RESEARCH = json.loads((ROOT / 'research/stratagem-blocking-F5FEE03DCFDB.json').read_text(encoding='utf-8'))

SETUP = r"""
local blocking=require('hd2runtime/runtime/stratagem_blocking')
local B=require('hd2runtime/domains/stratagem_blocking')
local CAT,GR,LO=B.catalogue,B.grid,B.loadout
blocking.reset_for_tests()
local function unhex(h)return(h:gsub('..',function(p)return string.char(tonumber(p,16))end))end
for _,pin in ipairs(B.pins)do W.write(W.GAME+pin.rva,unhex(pin.hex))end
local LEVELLER,EAT,AIRBURST,PRECISION,BIG=2934950455,3413606544,1560416221,3523620028,1063322614
local ORDER={PRECISION,LEVELLER,BIG,AIRBURST,EAT}
-- The account catalogue: every id owned (state 2), each record's card key (+4) different from its stable id.
local cat=W.catalogue({[LEVELLER]=2,[EAT]=2,[AIRBURST]=2,[PRECISION]=2,[BIG]=2})
local SORTED={LEVELLER,EAT,AIRBURST,PRECISION,BIG}
table.sort(SORTED)
local KEY,POS={},{}
for position,id in ipairs(SORTED)do
    KEY[id]=(id+0x01010101)%4294967296
    POS[id]=position-1
    W.write(cat+CAT.records+(position-1)*CAT.recordStride+CAT.recordKey,W.u32(KEY[id]))
end
-- Arrowhead's switch (the online override): the definition's disabled byte.
local function server_disable(id,on)
    W.write(cat+CAT.definitions+POS[id]*CAT.definitionStride+CAT.disabled,string.char(on and 1 or 0))
end
local SCREEN=W.loadout_screen({entries={{type=136}},editedSlot=1})
local UI=SCREEN.ui
local LIST=UI+LO.list
local world=assert(world_module.open())
local function byte_at(at)return W.read(at,1):byte()end
local function blocked(i)return byte_at(LIST+GR.blocked+i)end
local function index_of(id)for i,x in ipairs(ORDER)do if x==id then return i-1 end end end
-- The realize (0x18D2B60): every visible card drawn from its list bytes (the blocked byte -> card flag bit 0x100).
local drawn,realizes={},0
local function realize()
    drawn={}
    local n=W.read(LIST+GR.count,4)
    n=n:byte(1)+n:byte(2)*256
    for i=0,n-1 do drawn[i]=blocked(i)end
    realizes=realizes+1
end
-- The grid builder (0x18D8710) for a slot: clear (count 0, the realize request zeroed), list mode 3, one card per type:
-- its key, enabled, and the catalogue's disabled flag as its blocked byte; then the layout and the realize.
local function build(ids)
    ids=ids or ORDER
    W.write(LIST+GR.count,W.u32(0))
    W.write(LIST+GR.scrollMoved,'\0\0\0')
    W.write(LIST+GR.mode,W.u32(GR.stratagemMode))
    for i,id in ipairs(ids)do
        W.write(LIST+GR.keys+(i-1)*4,W.u32(KEY[id]))
        W.write(LIST+GR.enabled+(i-1),'\1')
        W.write(LIST+GR.blocked+(i-1),string.char(byte_at(cat+CAT.definitions+POS[id]*CAT.definitionStride+CAT.disabled)))
    end
    W.write(LIST+GR.count,W.u32(#ids))
    W.write(UI+LO.screen+GR.shown,'\1')
    realize()
end
-- The per-frame list update (0x18D5770): the request (or a dragged scrollbar) realizes once; the drag byte replaces it.
local function frame()
    local request,drag=byte_at(LIST+GR.realizeRequest),byte_at(LIST+GR.scrollbarActive)
    W.write(LIST+GR.realizeRequest,string.char(drag))
    if request~=0 or drag~=0 then realize()end
end
-- The list's state arrays and flags (keys, enabled, blocked; the scroll and request bytes), for exact comparisons.
local function list_state()
    return W.read(LIST+GR.keys,GR.blocked+GR.maxCards-GR.keys)..W.read(LIST+GR.scrollMoved,GR.requestContext)
end
local function writes_from(first)
    local out={}
    for k=first+1,#W.runtime.writes do out[#out+1]=W.runtime.writes[k]end
    return out
end
local SETTINGS=W.read(settings.base,settings.size)
local CATALOGUE=W.read(cat,CAT.index+0x200)
"""


def lua(body):
    return run(WORLD + SETUP + body)


class DoublesTests(unittest.TestCase):
    def test_the_carrier_a_custom_slot_holds_stays_pickable(self):
        # The carrier-in-slot probe 0.3.0: the game greys a type the edited record holds (the enabled byte 0); the
        # Runtime lifts it for the carrier its own carrier slot holds, never while the grid edits that slot, never on a
        # blocked card; re-applied after the game re-greys; greyed back when it leaves the set (the record holds it).
        self.assertEqual(lua(r'''
local function enabled(i)return byte_at(LIST+GR.enabled+i)end
-- The grid for slot 1 with the record holding the 120mm (BIG, type 136) in slot 0: the game greys it.
build()
local I=index_of(BIG)
local function grey()W.write(LIST+GR.enabled+I,'\0')end
grey()
local SET={[BIG]={definition='carrier_slot_probe',slots={0}}}
local before,state0=#W.runtime.writes,list_state()
local r=blocking.enable(world,SET)
assert(r.status=='applied'and r.wrote==1 and enabled(I)==1,tostring(r.status)..' '..tostring(r.reason))
-- Only that byte (and the one-shot realize request).
for i=0,#ORDER-1 do if i~=I then assert(enabled(i)==1 and blocked(i)==0)end end
local w=writes_from(before)
assert(#w==2,'the enabled byte and the realize request')
frame();assert(realizes>=2)
assert(count('STRATAGEM PICKABLE (native, the carrier-in-slot probe): Orbital 120mm HE Barrage')==1)
assert(count('stratagem doubles: native grid (slot 1): pickable 1 card (Orbital 120mm HE Barrage)')==1)
-- Idempotent.
before=#W.runtime.writes
assert(blocking.enable(world,SET).wrote==0 and#W.runtime.writes==before)
-- The game re-greys after a pick: lifted again.
grey()
assert(blocking.enable(world,SET).wrote==1 and enabled(I)==1)
-- The grid edits the custom slot itself: greyed back (the record holds it), and never lifted there.
SCREEN.set('editedSlot',0)
local g=blocking.enable(world,SET)
assert(g.greyed==1 and enabled(I)==0,'greyed back while the custom slot is edited')
assert(blocking.enable(world,SET).wrote==0 and enabled(I)==0)
SCREEN.set('editedSlot',1)
assert(blocking.enable(world,SET).wrote==1 and enabled(I)==1)
-- Leaving the set: greyed back (the record still holds it).
assert(blocking.enable(world,{}).greyed==1 and enabled(I)==0)
-- A blocked card (Arrowhead's switch) is never lifted.
server_disable(BIG,true);build();grey()
before=#W.runtime.writes
assert(blocking.enable(world,SET).wrote==0 and enabled(I)==0 and#W.runtime.writes==before)
server_disable(BIG,false);build();grey()
-- Closed: idle, nothing written.
SCREEN.set('selecting',false)
assert(blocking.enable(world,SET).status=='idle')
-- No StratagemInfo or catalogue write at any point.
assert(W.read(settings.base,settings.size)==SETTINGS and W.read(cat,CAT.index+0x200)==CATALOGUE)
return 'ok'
'''), b'ok')


    def test_the_grey_is_lifted_by_the_games_own_per_card_helper(self):
        # 0.3.1: the game's per-card grey helper (cardEnable: its whole body re-proved) lifts the grey AND redraws the
        # card; only inside the Runtime's update; the guarded byte write when it cannot be called; never a changed body.
        self.assertEqual(lua(r'''
local function enabled(i)return byte_at(LIST+GR.enabled+i)end
local function in_update(fn)
    local out
    local w={status='active'};function w.cancel()w.status='cancelled'end
    function w.tick()out={fn()};w.status='complete'end
    scheduler.attach(w);tick()
    return unpack(out)
end
local H=B.cardEnable
assert(H and H.rva==0x18D1440 and#H.code==2*267)
W.write(W.GAME+H.rva,unhex(H.code))
-- The adapter as the game's helper does it: that card's enabled byte (and, realized, its grey bit and redraw).
local calls={}
W.runtime.native_card_enable=function(entry,list,key,value)
    assert(entry==W.GAME+H.rva and list==LIST and(value==0 or value==1))
    calls[#calls+1]={key=key,value=value}
    for i=0,#ORDER-1 do
        if W.read(LIST+GR.keys+i*4,4)==W.u32(key)then W.write(LIST+GR.enabled+i,string.char(value))end
    end
    return true
end
build()
local I=index_of(BIG)
W.write(LIST+GR.enabled+I,'\0')
local SET={[BIG]={definition='carrier_slot_probe',slots={0}}}
local before=#W.runtime.writes
local HELPER={helper=require('hd2runtime/runtime/stratagem_card_enable')}
local r=in_update(function()return blocking.enable(world,SET,nil,HELPER)end)
assert(r.status=='applied'and r.helper and r.wrote==1 and enabled(I)==1,tostring(r.reason))
assert(#calls==1 and calls[1].key==KEY[BIG]and calls[1].value==1)
assert(#W.runtime.writes==before,'no Runtime byte write and no realize request: the game\'s helper did it')
assert(count("stratagem doubles: native grid (slot 1): pickable 1 card (Orbital 120mm HE Barrage), by the game's "
    ..'per-card grey helper (game+18D1440, re-proved; 1 call')==1)
-- Editing the custom slot: greyed back by the helper with 0 (the game's own grey).
SCREEN.set('editedSlot',0)
local g=in_update(function()return blocking.enable(world,SET,nil,HELPER)end)
assert(g.helper and g.greyed==1 and#calls==2 and calls[2].value==0 and enabled(I)==0)
SCREEN.set('editedSlot',1)
-- Outside the Runtime's update: never called; the guarded byte write (pickable, drawn grey), the reason logged once.
local f=blocking.enable(world,SET,nil,HELPER)
assert(f.wrote==1 and not f.helper and enabled(I)==1 and#calls==2)
assert(count("the game's per-card grey helper is not used (the card is pickable but drawn grey until the game "
    ..'redraws it): not inside the Runtime')==1)
-- A changed body (one byte): never called.
blocking.enable(world,{})
W.write(LIST+GR.enabled+I,'\0')
W.write(W.GAME+H.rva+0x50,'\0')
local c=in_update(function()return blocking.enable(world,SET,nil,HELPER)end)
assert(c.wrote==1 and not c.helper and#calls==2,'a changed helper is never called')
assert(count("is not used (the card is pickable but drawn grey until the game redraws it): the game's per-card grey "
    ..'helper changed (game+18D1440)')==1)
return 'ok'
'''), b'ok')


class StratagemBlockingResearchTests(unittest.TestCase):
    def test_the_research_and_its_domain(self):
        self.assertEqual((RESEARCH['writes'], RESEARCH['protectionChanges']), (0, 0))
        self.assertFalse(any(RESEARCH['pinnedBytesMismatchPerSnapshot'].values()))
        self.assertEqual(len(RESEARCH['snapshots']), 7)
        for facts in RESEARCH['snapshots'].values():
            self.assertFalse(facts['loadoutUi'])                       # no snapshot holds a loadout UI
            self.assertEqual((facts['disabledListCount'], facts['catalogueDefinitionsFlagged']), (0, 0))
            self.assertLess(facts['keyEqualsStableId'], facts['stratagemRecordsWithKey'])   # keys are not stable ids
        access = RESEARCH['access']
        self.assertEqual([r.split(':')[0] for r in access['blockedByte']['writers']], ['0x18D444B'])
        self.assertEqual([r.split(':')[0] for r in access['catalogueDisabled']['writers']], ['0x12E80FC', '0x12E81AE'])
        self.assertIn('0x18D279F: movzx eax, byte ptr [rax + rcx + 0x92ec2]', access['blockedByte']['readers'])
        self.assertIn('0x18D1BE2: mov byte ptr [rbx + 0x928fa], 1', access['realizeRequest']['writers'])
        self.assertIn('0x18D293F: mov word ptr [rdi + 0x928f9], bp', access['listClearWord']['writers'])
        pins = {p['rva']: p for rows in RESEARCH['pins'].values() for p in rows}
        self.assertEqual(pins[0x18CFDF1]['asm'], 'mov eax, 6')                          # the refusal
        self.assertEqual(pins[0x18D8BA9]['asm'], 'movzx eax, byte ptr [rcx + r14 + 0x1d99]')   # flag -> card byte
        self.assertEqual(pins[0x12E803B]['ripTarget'], 0x22C2248)                        # "OnlineOverrideData"
        self.assertEqual(RESEARCH['disabledText']['us'], 'DISABLED')
        self.assertEqual(RESEARCH['constants']['blockedFrame']['value'], [0.6, 0.694, 0.078, 0.0])
        mechanisms = {m['id']: m for m in RESEARCH['mechanisms']}
        self.assertTrue(mechanisms['card-blocked-byte']['implemented'])
        self.assertTrue(mechanisms['card-blocked-byte']['nativeRefusal'])
        for name in ('catalogue-disabled-flag', 'row-enabled-selectable', 'details-panel-notice'):
            self.assertFalse(mechanisms[name]['implemented'], name)
        # The enabled byte: never a block; only the grey lifted (the carrier-in-slot probe's doubles, 0.3.0).
        self.assertTrue(mechanisms['card-enabled-byte']['implemented'])
        self.assertIn('0 -> 1', mechanisms['card-enabled-byte']['safety'])
        self.assertTrue(mechanisms['catalogue-disabled-flag']['safety'].startswith('NOT ALLOWED'))
        self.assertTrue(mechanisms['row-enabled-selectable']['safety'].startswith('NOT ALLOWED'))
        import sys
        sys.path.insert(0, str(ROOT / 'scripts'))
        import generate_stratagem_blocking
        self.assertEqual(generate_stratagem_blocking.generate(check=True), [])
        doc = (ROOT / 'research/docs/stratagem-blocking-F5FEE03DCFDB.md').read_text(encoding='utf-8')
        self.assertIn('needs the user\'s decision', doc)

    def test_the_module_writes_only_through_guarded_transactions(self):
        source = (ROOT / 'runtime/stratagem_blocking.lua').read_text(encoding='utf-8')
        code = '\n'.join(line.split('--')[0] for line in source.splitlines())
        for forbidden in ('ffi', 'runtime.native', 'runtime.write(', 'table_rva', 'protect('):
            self.assertNotIn(forbidden, code, forbidden)
        self.assertIn("require('hd2runtime/core/guarded_transaction')", code)
        self.assertEqual(code.count('transaction.apply('), 2)                    # the card bytes; the realize request
        callers = sorted(p.name for p in (ROOT / 'runtime').glob('*.lua')
            if "require('hd2runtime/runtime/stratagem_blocking')" in p.read_text(encoding='utf-8'))
        self.assertEqual(callers, [])                                            # not wired: the owner decides

    def test_the_card_helper_module_makes_exactly_the_one_reviewed_call(self):
        source = (ROOT / 'runtime/stratagem_card_enable.lua').read_text(encoding='utf-8')
        code = '\n'.join(line.split('--')[0] for line in source.splitlines())
        for forbidden in ('ffi', 'runtime.write(', 'transaction', 'protect('):
            self.assertNotIn(forbidden, code, forbidden)
        self.assertEqual(code.count('runtime.native'), 2)                       # the check and the one call
        self.assertEqual(code.count('runtime.native_card_enable('), 1)
        self.assertIn('world.view.proves(world.game+H.rva,H.code)', code)       # the whole body, every call
        self.assertIn('scheduler.in_update()', code)
        adapter = (ROOT / 'runtime/windows_write.lua').read_text(encoding='utf-8')
        self.assertIn("and(enabled==0 or enabled==1),'unsupported card enable call')", adapter)


class StratagemBlockingTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(lua(body), b'ok')

    def test_exactly_the_reserved_carriers_are_blocked_natively_and_restored_exactly(self):
        self.check(r'''
build()
local before=list_state()
local first=#W.runtime.writes
local set=blocking.collect({
    {carrier=LEVELLER,holder='EAT-17G (you, slot 1)',reason='the carrier of EAT-17G'},
    {carrier=AIRBURST,holder='Gas Barrage (peer 2, slot 0)',reason='the carrier of Gas Barrage'}})
local r=blocking.apply(world,set)
assert(r.status=='applied'and r.wrote==2 and r.blocked==2 and r.realize=='requested',tostring(r.code)..' '..tostring(r.reason))
for i,id in ipairs(ORDER)do
    local want=(id==LEVELLER or id==AIRBURST)and 1 or 0
    assert(blocked(i-1)==want,'card '..(i-1)..' blocked byte '..blocked(i-1))
    assert(byte_at(LIST+GR.enabled+i-1)==1,'the enabled bytes are untouched')
end
-- Exactly the two blocked bytes and the one-shot realize request were written; nothing else anywhere.
local allowed={[LIST+GR.blocked+index_of(LEVELLER)]='\1',[LIST+GR.blocked+index_of(AIRBURST)]='\1',
    [LIST+GR.realizeRequest]='\1'}
local written=writes_from(first)
assert(#written==3,'writes: '..#written)
for _,w in ipairs(written)do assert(allowed[w.address]==w.bytes,string.format('unexpected write at %X',w.address))end
assert(W.read(settings.base,settings.size)==SETTINGS,'no StratagemInfo row changed')
assert(W.read(cat,CAT.index+0x200)==CATALOGUE,'the catalogue is untouched (no server-disabled flag written)')
-- The visible cards still show the build's look until the game's next frame realizes them.
assert(drawn[index_of(LEVELLER)]==0 and byte_at(LIST+GR.realizeRequest)==1)
frame()
assert(realizes==2 and drawn[index_of(LEVELLER)]==1 and drawn[index_of(AIRBURST)]==1 and drawn[index_of(EAT)]==0)
assert(byte_at(LIST+GR.realizeRequest)==0,'the game consumed the request')
-- Idempotent: the same set again writes nothing.
local again=#W.runtime.writes
r=blocking.apply(world,set)
assert(r.status=='applied'and r.wrote==0 and r.blocked==2 and #W.runtime.writes==again)
assert(count('stratagem blocking: the native grid consumed the realize request')==1)
assert(count('STRATAGEM BLOCKED (native): EAT-411 Leveller (0xAEEFCA37): the carrier of EAT-17G; reserved by EAT-17G '
    ..'(you, slot 1) (1)')==1)
assert(count('STRATAGEM BLOCKED (native): Orbital Airburst Strike')==1)
assert(count('stratagem blocking: native grid (slot 1): blocked 2 cards (EAT-411 Leveller, Orbital Airburst Strike); '
    ..'blocked byte card list+0x92EC2 (guarded, 2 writes, non-target bytes unchanged true, protection restored true); '
    ..'realize requested')==1)
-- One carrier released: only its card is restored (and redrawn next frame); the other stays blocked.
r=blocking.apply(world,blocking.collect({{carrier=AIRBURST,holder='Gas Barrage (peer 2, slot 0)'}}))
assert(r.restored==1 and r.wrote==0 and blocked(index_of(LEVELLER))==0 and blocked(index_of(AIRBURST))==1)
assert(count('STRATAGEM UNBLOCKED (native): EAT-411 Leveller (0xAEEFCA37): no reservation left (1 card restored)')==1)
assert(count('STRATAGEM UNBLOCKED (native): Orbital Airburst Strike')==0)
frame()
assert(drawn[index_of(LEVELLER)]==0 and drawn[index_of(AIRBURST)]==1)
-- Release: every byte back exactly as the game built it.
r=blocking.release(world)
assert(r.restored==1 and r.blocked==0)
frame()
assert(list_state()==before,'the list is exactly as the game built it')
assert(next(blocking.state().cards)==nil and next(blocking.state().blocked)==nil)
assert(count('STRATAGEM UNBLOCKED (native): Orbital Airburst Strike (0x5D020FDD): no reservation left (1 card restored)')==1)
assert(count('REFUSED')==0)
return 'ok'
''')

    def test_reservations_are_ref_counted_by_distinct_holder(self):
        self.check(r'''
build()
local A={carrier=LEVELLER,holder='EAT-17G (you, slot 1)',reason='the carrier of EAT-17G'}
local A2={carrier=LEVELLER,holder='EAT-17G (you, slot 3)'}
local P={carrier=LEVELLER,holder='EAT-17G (peer 2, slot 0)'}
local set=blocking.collect({A,A2,P,A})
assert(#set[LEVELLER].holders==3 and set[LEVELLER].reason=='the carrier of EAT-17G','three distinct holders')
assert(blocking.apply(world,set).wrote==1)
-- Holders leave one by one: the carrier stays blocked while any remains.
assert(blocking.apply(world,blocking.collect({A2,P})).restored==0 and blocked(index_of(LEVELLER))==1)
assert(blocking.apply(world,blocking.collect({P})).restored==0 and blocked(index_of(LEVELLER))==1)
assert(count('STRATAGEM BLOCKED (native): EAT-411 Leveller')==1,'blocked once, whatever the holders do')
assert(count('stratagem blocking: EAT-411 Leveller (0xAEEFCA37): reserved by EAT-17G (peer 2, slot 0) (1)')==1)
assert(blocking.apply(world,blocking.collect({})).restored==1 and blocked(index_of(LEVELLER))==0)
assert(count('STRATAGEM UNBLOCKED (native): EAT-411 Leveller')==1)
assert(next(blocking.collect({{carrier=0,holder='x'},{holder='y'}}))==nil,'no carrier, no reservation')
return 'ok'
''')

    def test_the_game_rebuilding_or_closing_the_grid_is_followed_and_reapplied(self):
        self.check(r'''
build()
local set=blocking.collect({{carrier=LEVELLER,holder='EAT-17G (you, slot 1)'}})
assert(blocking.apply(world,set).wrote==1)
frame()
-- The player opens the grid for another slot: the game clears and rebuilds the list from the catalogue.
SCREEN.set('editedSlot',2)
build({EAT,LEVELLER,PRECISION})
assert(blocked(1)==0 and drawn[1]==0,'the rebuild dropped the Runtime byte')
local r=blocking.apply(world,set)
assert(r.wrote==1 and blocked(1)==1 and blocked(0)==0 and blocked(2)==0 and r.realize=='requested')
frame()
assert(drawn[1]==1)
-- Closed: the game cleared the list; nothing is written while it is closed.
SCREEN.native_close()
W.write(LIST+GR.count,W.u32(0))
local first=#W.runtime.writes
r=blocking.apply(world,set)
assert(r.status=='idle'and not r.grid and #W.runtime.writes==first and next(blocking.state().cards)==nil)
-- Released while closed: UNBLOCKED at once, nothing to restore.
r=blocking.release(world)
assert(r.status=='idle'and #W.runtime.writes==first)
assert(count('STRATAGEM UNBLOCKED (native): EAT-411 Leveller (0xAEEFCA37): no reservation left')==1)
-- Reopened and reserved again: blocked again (a new change: logged again).
SCREEN.set('selecting',true);W.write(UI+LO.subState,W.u32(LO.gridSubState));SCREEN.set('editedSlot',0)
build()
assert(blocking.apply(world,set).wrote==1 and blocked(index_of(LEVELLER))==1)
assert(count('STRATAGEM BLOCKED (native): EAT-411 Leveller')==2)
assert(count('stratagem blocking: native grid (slot 2): blocked 1 card (EAT-411 Leveller)')==1)
return 'ok'
''')

    def test_a_card_arrowhead_disabled_stays_as_the_game_has_it(self):
        self.check(r'''
server_disable(AIRBURST,true)
build()
assert(blocked(index_of(AIRBURST))==1,'the build copied the server flag')
local first=#W.runtime.writes
local r=blocking.apply(world,blocking.collect({{carrier=AIRBURST,holder='Gas Barrage (you, slot 0)'}}))
assert(r.wrote==0 and r.native[1]==AIRBURST and #W.runtime.writes==first,'nothing written: the game already blocks it')
assert(count('stratagem blocking: Orbital Airburst Strike (0x5D020FDD) is already blocked by the game (Arrowhead\'s '
    ..'online override): left as the game has it')==1)
blocking.release(world)
assert(blocked(index_of(AIRBURST))==1 and #W.runtime.writes==first,'never cleared by the Runtime')
-- Blocked by the Runtime first, then disabled by Arrowhead: the release leaves the game's state.
assert(blocking.apply(world,blocking.collect({{carrier=LEVELLER,holder='EAT-17G (you, slot 1)'}})).wrote==1)
server_disable(LEVELLER,true)
first=#W.runtime.writes
r=blocking.release(world)
assert(r.restored==0 and blocked(index_of(LEVELLER))==1 and #W.runtime.writes==first)
assert(W.read(settings.base,settings.size)==SETTINGS)
return 'ok'
''')

    def test_refusals_and_skips_write_nothing_they_should_not(self):
        self.check(r'''
build()
local set=blocking.collect({{carrier=LEVELLER,holder='EAT-17G (you, slot 1)'},{carrier=2239174926,holder='x'}})
-- No open grid (a focused slot only): idle.
SCREEN.set('selecting',false)
local first=#W.runtime.writes
assert(blocking.apply(world,set).status=='idle'and #W.runtime.writes==first)
SCREEN.set('selecting',true)
-- Another list mode in the same control: refused.
W.write(LIST+GR.mode,W.u32(2))
local r=blocking.apply(world,set)
assert(r.status=='refused'and r.code=='LIST_MODE'and #W.runtime.writes==first)
W.write(LIST+GR.mode,W.u32(GR.stratagemMode))
-- The card list not in private read-write memory: refused before any write.
local page=LIST-LIST%4096
W.runtime.protections[page]=2
r=blocking.apply(world,set)
assert(r.status=='refused'and r.code=='NOT_PRIVATE'and blocked(index_of(LEVELLER))==0,tostring(r.code))
W.runtime.protections[page]=nil
-- The target page read-only: the guarded transaction refuses it; nothing written.
page=(LIST+GR.blocked)-(LIST+GR.blocked)%4096
W.runtime.protections[page]=2
r=blocking.apply(world,set)
assert(r.status=='refused'and r.code=='GUARD_REJECTED'and blocked(index_of(LEVELLER))==0,tostring(r.code))
assert(#W.runtime.writes==first)
W.runtime.protections[page]=nil
-- A dragged scrollbar realizes every frame: the byte is written, no request.
W.write(LIST+GR.scrollbarActive,'\1')
r=blocking.apply(world,set)
assert(r.wrote==1 and r.realize:find('not needed',1,true)and byte_at(LIST+GR.realizeRequest)==0)
assert(r.missing[2239174926]and next(r.missing,2239174926)==nil,'an unowned carrier has no card: reported')
frame()
assert(drawn[index_of(LEVELLER)]==1)
W.write(LIST+GR.scrollbarActive,'\0');frame()
-- The screen not showing its grid: blocked bytes still written (the refusal applies), no request.
blocking.release(world);frame()
W.write(UI+LO.screen+GR.shown,'\0')
r=blocking.apply(world,set)
assert(r.wrote==1 and r.realize:find('skipped',1,true)and byte_at(LIST+GR.realizeRequest)==0)
W.write(UI+LO.screen+GR.shown,'\1')
-- A request the game has not consumed is reported once.
blocking.release(world);frame()
r=blocking.apply(world,set)
assert(r.realize=='requested')
for _=1,40 do blocking.apply(world,set)end
assert(count('stratagem blocking: the realize request was not consumed within 1 s')==1)
-- Changed code: nothing read further, nothing written, nothing announced.
blocking.reset_for_tests()
local pin=B.pins[1]
W.write(W.GAME+pin.rva,'\204')
first=#W.runtime.writes
r=blocking.apply(world,blocking.collect({{carrier=EAT,holder='y'}}))
assert(r.status=='refused'and r.code=='UNPROVEN'and #W.runtime.writes==first)
assert(count('STRATAGEM BLOCKED (native): EAT-17 Expendable Anti-Tank')==0)
assert(W.read(settings.base,settings.size)==SETTINGS and W.read(cat,CAT.index+0x200)==CATALOGUE)
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
