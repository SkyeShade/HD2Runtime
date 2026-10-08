"""The Runtime-owned custom stratagem selector (development; docs/custom-stratagems.md, "A Runtime-owned custom
stratagem selector"; research/runtime-stratagem-ui-F5FEE03DCFDB.json): a virtual stratagem's card is drawn through the
engine's Lua GUI API while the stratagem grid is open, and selecting it writes the vanilla token into that slot of the
local loadout record, with the game's own per-frame bind repainting the slots. Offline: the event world with a loadout
screen, the account catalogue, the Runtime image and the engine font loaded, and a recording stand-in for the engine
GUI API (nothing is drawn)."""
import json
import unittest

from support import ROOT, run
from test_stratagem_calldown_code import WORLD

RESEARCH = json.loads((ROOT / 'research/runtime-stratagem-ui-F5FEE03DCFDB.json').read_text(encoding='utf-8'))

SELECT = r"""
local selector=require('hd2runtime/runtime/stratagem_selector')
local virtual=require('hd2runtime/runtime/virtual_stratagems')
local texts=require('hd2runtime/runtime/text_resources')
local images=require('hd2runtime/runtime/image_resources')
local SEL=require('hd2runtime/domains/stratagem_selector')
selector.reset_for_tests();virtual.reset_for_tests();images.reset_for_tests()
local MOD='mods/skyeshade/selector_test'
local PRECISION_ID,BIG_ID=3523620028,1063322614
for _,kind in ipairs({118,136,22,41})do
    W.write(ROW[kind]+0x50,W.u32(4294967295));W.write(ROW[kind]+0x80,W.u32(2));W.write(ROW[kind]+0xC0,W.u32(1))
end
W.catalogue({[PRECISION_ID]=2,[BIG_ID]=2})
local ICON=images.handle('orbital_gas_barrage_icon',MOD)
local ICON_NAME=images.name(MOD,'orbital_gas_barrage_icon')
local FONT='core/performance_hud/monaco'
local resources=W.icon_resources({textures={ICON_NAME},materials={ICON_NAME,FONT},fonts={FONT}})
local GAS=virtual.define({id='orbital_gas_barrage',display={name=texts.handle('ogb_name','Orbital Gas Barrage',MOD),
    description=texts.handle('ogb_description','Calls down a barrage of gas shells.',MOD),icon=ICON},
    selection={token='Orbital Precision Strike'},mission={carrier='Orbital 120mm HE Barrage'}},MOD)
-- The engine GUI API, recorded: every call and its arguments. Its types and returns are the engine's own: Vector2 and
-- Vector3 are module tables with a __call constructor (exe 0x430F3F, 0x43517F), Color a plain function;
-- create_screen_gui, rect, bitmap and text return one value (the GUI or an id: the call number), update_rect and
-- destroy_gui return NOTHING (0x3E1F90, 0x3F105D).
local calls={}
local MAIN=newproxy(true)
local alive={MAIN}
local function rec(name,result)return function(...)calls[#calls+1]={name=name,args={...}};return result or#calls end end
local function nothing(name)return function(...)calls[#calls+1]={name=name,args={...}}end end
local function constructor(kind)return setmetatable({},{__call=function(_,...)return {kind=kind,...}end})end
local engine={Application={main_world=function()return MAIN end,worlds=function()return alive end},
    World={create_screen_gui=rec('create_screen_gui'),destroy_gui=nothing('destroy_gui')},
    Gui={resolution=function()return 1920,1080 end,rect=rec('rect'),bitmap=rec('bitmap'),text=rec('text'),
        update_rect=nothing('update_rect')},
    Vector2=constructor('Vector2'),Vector3=constructor('Vector3'),Color=function(a,r,g,b)return {kind='Color',a,r,g,b}end}
rawset(_G,'stingray',engine)
local function called(name)local n=0;for _,c in ipairs(calls)do if c.name==name then n=n+1 end end;return n end
local function find(name,arg,value)for _,c in ipairs(calls)do if c.name==name and c.args[arg]==value then return c end end end
-- The game's per-frame bind of the local panel, every update.
local SCREEN
scheduler.attach({status='active',tick=function()if SCREEN then SCREEN.frame()end end})
local function settle_job(handle)for _=1,400 do if handle.status~='pending'then break end;tick()end;return handle end
local function near(a,b)return math.abs(a-b)<1e-3 end
local function writes_from(first)
    local out={}
    for k=first+1,#W.runtime.writes do out[#out+1]=W.runtime.writes[k]end
    return out
end
local SETTINGS=W.read(settings.base,settings.size)
"""


def lua(body):
    return run(WORLD + SELECT + body)


class SelectorResearchTests(unittest.TestCase):
    def test_the_research_and_its_domain(self):
        self.assertEqual((RESEARCH['writes'], RESEARCH['protectionChanges']), (0, 0))
        self.assertFalse(any(RESEARCH['pinnedBytesMismatchPerSnapshot'].values()))
        self.assertEqual(len(RESEARCH['snapshots']), 7)
        for evidence in RESEARCH['snapshots'].values():
            self.assertFalse(evidence['loadoutUi'])                        # no snapshot holds a loadout screen
            self.assertEqual((evidence['font'], evidence['fontMaterial']), ('present', 'present'))
            self.assertEqual(evidence['precisionMaxUses'], -1)
        exe = {pin['rva']: pin for rows in RESEARCH['pins']['exe'].values() for pin in rows}
        game = {pin['rva']: pin for rows in RESEARCH['pins']['game'].values() for pin in rows}
        self.assertEqual(exe[0x2646C5]['asm'], 'movabs rax, 0xeac0b497876adedf')      # the GUI material lookup
        self.assertEqual(game[0x1895A6B]['asm'], 'cmp qword ptr [rcx + 0xd960], rdx')  # the bind's cache
        self.assertEqual(game[0x18962C3]['asm'], 'jmp 0x18962cc')                       # the local panel repaints too
        self.assertEqual(game[0xAE6B6C]['asm'], 'mov dword ptr [r14 + 0x54], 0xa')      # Menu.Select = 10
        self.assertTrue(RESEARCH['determinations']['runtimeUi'].startswith('Possible only through the engine'))
        # The game's own selection close: one argument (the loadout UI), and Back and a pick filling the last slot are
        # its callers, each after the picker-close sound; the pick sound the card list posts for every pick.
        self.assertEqual(game[0x146F3D1]['asm'], 'mov rsi, rcx')
        self.assertEqual(game[0x146F3DA]['asm'], 'mov byte ptr [rcx + 0x273990], 0')
        self.assertEqual(game[0x146F503]['asm'], 'ret ')
        self.assertEqual((game[0x146E66F]['asm'], game[0x146E672]['asm']), ('mov rcx, rdi', 'call 0x146f3b0'))
        self.assertEqual((game[0x146E972]['asm'], game[0x146E975]['asm']), ('mov rcx, rdi', 'call 0x146f3b0'))
        self.assertEqual(game[0x18CFDD3]['asm'], 'mov edx, 0xbe9303b7')
        close = RESEARCH['layout']['selectorClose']
        self.assertEqual((close['rva'], close['prologue'][:10]), (0x146F3B0, game[0x146F3B0]['bytes']))
        for evidence in RESEARCH['snapshots'].values():
            self.assertEqual(evidence['uiSoundRemap'], {'0xBE9303B7': '0x6A84A787', '0x97753411': '0x0DBB2A14',
                '0xA31D0645': '0x3C38FC71'})
        import sys
        sys.path.insert(0, str(ROOT / 'scripts'))
        import generate_stratagem_selector
        self.assertEqual(generate_stratagem_selector.generate(check=True), [])
        doc = (ROOT / 'docs/custom-stratagems.md').read_text(encoding='utf-8')
        self.assertIn('## A Runtime-owned custom stratagem selector: research (2026-10-02, offline)', doc)


    def test_the_close_adapter_is_narrow_and_has_one_caller(self):
        source = (ROOT / 'runtime/windows_write.lua').read_text(encoding='utf-8')
        self.assertIn('function runtime.native_selector_close(entry,ui)', source)
        self.assertIn("address(entry)and address(ui),'unsupported selector close call'", source)
        self.assertIn("ffi.cast(win.fn('void (*)(void *)'),entry)", source)
        callers = sorted(p.name for p in (ROOT / 'runtime').glob('*.lua') if p.name != 'windows_write.lua'
            and 'native_selector_close(' in p.read_text(encoding='utf-8'))
        self.assertEqual(callers, ['stratagem_selector.lua'])


class SelectorTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(lua(body), b'ok')

    def test_the_card_is_drawn_while_the_grid_is_open_and_selecting_it_writes_the_token(self):
        self.check(r'''
SCREEN=W.loadout_screen({entries={{type=136},{type=22},{type=41}},editedSlot=1})
local S=selector.selector({placement='float'})
tick(3)
-- The card: one screen GUI in the main world, the Runtime icon's material by name and the Runtime texts in the font.
assert(called('create_screen_gui')==1 and calls[1].args[1]==MAIN,'one screen GUI in the main world')
assert(calls[1].args[2]=='scale'and calls[1].args[3]==1 and calls[1].args[4]==1,'created as the reference mod does')
assert(calls[2].name=='rect'and calls[2].args[2].kind=='Vector3'and calls[2].args[3].kind=='Vector2'
    and calls[2].args[4].kind=='Color','positions are Vector3 (x, y, layer), sizes Vector2, colours Color')
local icon=find('bitmap',2,ICON_NAME)
assert(icon,'the icon is the Runtime image material')
assert(find('text',2,'Orbital Gas Barrage')and find('text',2,'Calls down a barrage of gas shells.'),'the texts')
assert(find('text',2,'Orbital Gas Barrage').args[3]==FONT and find('text',2,'Orbital Gas Barrage').args[5]==FONT)
assert(called('rect')==1 and called('bitmap')==1 and called('text')==2 and called('update_rect')==0,
    'the card alone: background, icon, name, description; no focus frame by default')
assert(S.renderer().state=='shown'and S.renderer().focusFrame=='off')
assert(count('stratagem selector shown for slot 1: 1 card (orbital_gas_barrage)')==1)
assert(#W.runtime.writes==0,'drawing writes nothing')
-- Select: the token into slot 1 of the local record; the game repaints the slots from the record.
local first=#W.runtime.writes
assert(S.action('confirm'))
local job=settle_job(S.handles[1])
assert(job.status=='selected'and job.index==1 and not job.appended,tostring(job.code)..' '..tostring(job.reason))
local kind,uses=SCREEN.entry(1)
assert(kind==118 and uses==4294967295,'slot 1 holds the Precision Strike token, unlimited')
assert(SCREEN.count()==3 and SCREEN.entry(0)==136 and SCREEN.entry(2)==41,'the other slots unchanged')
assert(SCREEN.widget(1)==118 and SCREEN.bound()==SCREEN.record and SCREEN.repaints==1,'the game repainted the slots')
for key,value in pairs(job.verify)do assert(value==true,key)end
local written=writes_from(first)
assert(#written==2,'type and cached pointer (the uses are already unlimited): '..#written)
local allowed={[SCREEN.record+0x188+0x30]=true,[SCREEN.record+0x188+0x34]=true,[SCREEN.ui+SEL.loadout.panel0BoundRecord]=true}
for _,w in ipairs(written)do assert(allowed[w.address],string.format('write outside the slot: %X',w.address))end
assert(W.read(settings.base,settings.size)==SETTINGS,'no StratagemInfo row changed')
assert(count('stratagem selector SELECTED: orbital_gas_barrage -> slot 1 holds Orbital Precision Strike (type 118, the '
    ..'token) replacing type 22: 2 writes; the entry reads the token: true; count 3: true; every other entry unchanged: true; the game '
    ..'repainted the slots from the record: true; non-target bytes unchanged true; protection restored true')==1)
-- Identity: the Runtime's own record of which slot is virtual, checked against a saved order.
local set=selector.virtual_slots()
assert(set.slots[1].definition=='orbital_gas_barrage'and set.slots[1].token==PRECISION_ID and set.slots[1].type==118)
assert(set.pairs[1]==BIG_ID and set.pairs[2]==PRECISION_ID and set.pairs[3]==3193297673)
assert(job.identity.slot==1 and job.identity.definition=='orbital_gas_barrage','the handle names its own slot')
local slots,n=selector.reconstruct({BIG_ID,PRECISION_ID,3193297673})
assert(n==1 and slots[1]=='orbital_gas_barrage')
assert(selector.reconstruct({BIG_ID,3193297673,PRECISION_ID})==nil,'another order is not guessed')
assert(selector.reconstruct({BIG_ID,2281932031,3193297673})==nil,'the token gone: not virtual')
-- Restore: slot 1 back to its own stratagem, repainted.
local back=settle_job(selector.restore())
assert(back.status=='restored'and back.exact,tostring(back.code))
tick(2)
assert(SCREEN.entry(1)==22 and SCREEN.widget(1)==22 and SCREEN.count()==3 and selector.virtual_slots()==nil)
assert(W.read(settings.base,settings.size)==SETTINGS)
return 'ok'
''')

    def test_an_empty_slot_is_appended_and_the_count_grows(self):
        self.check(r'''
SCREEN=W.loadout_screen({entries={{type=136},{type=22}},editedSlot=3})
local first=#W.runtime.writes
local job=settle_job(selector.select('orbital_gas_barrage'))
assert(job.status=='selected'and job.index==2 and job.appended,tostring(job.code))
assert(SCREEN.count()==3 and SCREEN.entry(2)==118 and SCREEN.widget(2)==118 and SCREEN.widget(3)==0)
assert(#writes_from(first)==4,'type, uses, count, cached pointer')
local back=settle_job(selector.restore())
assert(back.status=='restored'and back.exact)
tick(2)
assert(SCREEN.count()==2 and SCREEN.widget(2)==0)
return 'ok'
''')

    def test_one_definition_fills_several_slots_and_each_reconstructs(self):
        self.check(r'''
SCREEN=W.loadout_screen({entries={},editedSlot=0})
local EAGLE_ID=2281932031
local before_list=#virtual.list()
-- Four selections of the same definition, each into the slot the native selector is open for: no singleton.
for slot=0,3 do
    SCREEN.set('editedSlot',slot)
    local job=settle_job(selector.select('orbital_gas_barrage'))
    assert(job.status=='selected'and job.index==slot and job.appended and job.written,
        slot..': '..tostring(job.code)..' '..tostring(job.reason))
    assert(job.next==(slot<3 and slot+1 or nil),'the next empty slot after '..slot..': '..tostring(job.next))
end
assert(SCREEN.count()==4)
for k=0,3 do assert(SCREEN.entry(k)==118 and SCREEN.widget(k)==118,'slot '..k)end
local set=selector.virtual_slots()
for k=0,3 do assert(set.slots[k].definition=='orbital_gas_barrage'and set.slots[k].token==PRECISION_ID)end
assert(#virtual.list()==before_list,'one shared definition: no per-slot definitions')
local slots,n=selector.reconstruct({PRECISION_ID,PRECISION_ID,PRECISION_ID,PRECISION_ID})
assert(n==4 and slots[0]and slots[3],'all four instances reconstruct')
assert(count('virtual slots: 0 = orbital_gas_barrage, 1 = orbital_gas_barrage, 2 = orbital_gas_barrage, 3 = '
    ..'orbital_gas_barrage')==1)
-- Undo (Ctrl+F7) takes back the newest selection only.
local back=settle_job(selector.restore())
assert(back.status=='restored'and back.exact and back.index==3)
tick(2)
assert(SCREEN.count()==3 and selector.virtual_slots().slots[3]==nil and selector.virtual_slots().slots[2])
assert(W.read(settings.base,settings.size)==SETTINGS,'no StratagemInfo row changed (no global presentation)')
return 'ok'
''')

    def test_an_occupied_slot_is_replaced_and_mixed_native_and_virtual_slots_stay_apart(self):
        self.check(r'''
-- Slot 0 holds the REAL Precision Strike (native), slot 1 Eagle Airstrike, slot 2 Orbital Gas Strike, slot 3 empty.
local EAGLE_ID,GAS_ID=2281932031,3193297673
SCREEN=W.loadout_screen({entries={{type=118},{type=22},{type=41}},editedSlot=1})
local first=#W.runtime.writes
local job=settle_job(selector.select('orbital_gas_barrage'))
assert(job.status=='selected'and job.index==1 and not job.appended and job.written,tostring(job.code))
assert(SCREEN.entry(1)==118 and SCREEN.widget(1)==118 and SCREEN.count()==3,'Eagle Airstrike replaced')
assert(job.next==3,'the next empty slot is 3: '..tostring(job.next))
assert(count('replacing type 22')==1)
-- Slot 3 (empty): appended.
SCREEN.set('editedSlot',3)
job=settle_job(selector.select('orbital_gas_barrage'))
assert(job.status=='selected'and job.index==3 and job.appended and job.next==nil,'full: no next slot')
-- Saved [Precision, Precision, Gas Strike, Precision]: slots 1 and 3 are virtual, slot 0 is the native Precision Strike.
local set=selector.virtual_slots()
assert(set.slots[0]==nil and set.slots[1]and set.slots[3],'the native Precision Strike stays native')
local slots,n=selector.reconstruct({PRECISION_ID,PRECISION_ID,GAS_ID,PRECISION_ID})
assert(n==2 and slots[1]=='orbital_gas_barrage'and slots[3]=='orbital_gas_barrage'and slots[0]==nil)
-- Selecting into the native Precision Strike slot: it already holds the token, so nothing is written and it becomes
-- virtual too ([Gas, Gas, Gas Strike, Gas] as the Runtime sees it).
SCREEN.set('editedSlot',0)
local writes=#W.runtime.writes
job=settle_job(selector.select('orbital_gas_barrage'))
assert(job.status=='selected'and job.index==0 and not job.written and #W.runtime.writes==writes,'no write')
assert(count('slot 0 already holds Orbital Precision Strike (type 118, the token, unlimited): no write')==1)
slots,n=selector.reconstruct({PRECISION_ID,PRECISION_ID,GAS_ID,PRECISION_ID})
assert(n==3 and slots[0]and slots[1]and slots[3]and slots[2]==nil,'three instances, not collapsed')
-- Undo the no-write selection: slot 0 is native again, still the token.
local back=settle_job(selector.restore())
assert(back.status=='restored'and back.report.writes==0 and SCREEN.entry(0)==118)
assert(selector.virtual_slots().slots[0]==nil and selector.virtual_slots().slots[1])
-- Another order is never guessed; the save holds only vanilla tokens.
assert(selector.reconstruct({PRECISION_ID,GAS_ID,PRECISION_ID,PRECISION_ID})==nil)
for k=0,3 do assert(({[0]=118,118,41,118})[k]==SCREEN.entry(k))end
assert(W.read(settings.base,settings.size)==SETTINGS,'no StratagemInfo row changed (no global presentation)')
return 'ok'
''')

    def test_virtual_slots_follow_a_native_change_and_a_compacted_record(self):
        self.check(r'''
local EAGLE_ID=2281932031
SCREEN=W.loadout_screen({entries={{type=136},{type=22}},editedSlot=1})
-- The record follows the loadout as the panel's watch does it.
local event_world=require('hd2runtime/runtime/event_world')
selector.watch(function(event,view)if event=='record_changed'then selector.track(event_world.open(),view)end end)
assert(settle_job(selector.select('orbital_gas_barrage')).status=='selected')
SCREEN.set('editedSlot',2)
assert(settle_job(selector.select('orbital_gas_barrage')).status=='selected')
SCREEN.set('editedSlot',3)
-- The player puts Eagle Airstrike into slot 3 natively: [Big, Gas, Gas, Eagle]; both virtual slots kept.
W.write(SCREEN.record+0x188+3*0x30,W.u32(22));W.write(SCREEN.record+0x188+3*0x30+4,W.u32(4294967295))
W.write(SCREEN.record+0x788,W.u32(4));W.write(SCREEN.ui+SEL.loadout.panel0BoundRecord,W.u64(0))
SCREEN.frame();tick(3)
local set=selector.virtual_slots()
assert(set.slots[1]and set.slots[2]and#set.pairs==4,table.concat(logged,' | '))
-- The game removes slot 0 and compacts the record: [Gas, Gas, Eagle]; the virtual slots move down with it.
for k=0,2 do
    local from=SCREEN.record+0x188+(k+1)*0x30
    W.write(SCREEN.record+0x188+k*0x30,W.read(from,8))
end
W.write(SCREEN.record+0x188+3*0x30,W.u64(0));W.write(SCREEN.record+0x788,W.u32(3))
W.write(SCREEN.ui+SEL.loadout.panel0BoundRecord,W.u64(0))
SCREEN.frame();tick(3)
set=selector.virtual_slots()
assert(set.slots[0]and set.slots[1]and set.slots[2]==nil,table.concat(logged,' | '))
assert(count('virtual slot 1 (orbital_gas_barrage) is now slot 0: the game removed slot 0')==1)
local slots,n=selector.reconstruct({PRECISION_ID,PRECISION_ID,EAGLE_ID})
assert(n==2 and slots[0]and slots[1])
-- One virtual slot changed natively: only that one becomes plain.
W.write(SCREEN.record+0x188+1*0x30,W.u32(41));W.write(SCREEN.ui+SEL.loadout.panel0BoundRecord,W.u64(0))
SCREEN.frame();tick(3)
set=selector.virtual_slots()
assert(set.slots[0]and set.slots[1]==nil)
assert(count('virtual slot 1 (orbital_gas_barrage) no longer holds its token: it now holds ')==1
    and count('; that slot is plain again (the loadout order was ')==1,table.concat(logged,' | '))
return 'ok'
''')

    def test_each_selection_moves_the_native_selector_on_and_the_last_one_leaves_it_open(self):
        self.check(r"""
SCREEN=W.loadout_screen({entries={},editedSlot=0})
local function edited()return W.u32 and(function()
    local s=W.read(SCREEN.ui+SEL.loadout.editedSlot,4)
    return s:byte(1)+s:byte(2)*256+s:byte(3)*65536+s:byte(4)*16777216
end)()end
local function selecting()return W.read(SCREEN.ui+SEL.loadout.selectionOpen,1):byte()end
-- [empty] x4, the selector on slot 0: each selection writes the token, then moves the selector to the next empty slot
-- (one write of the edited slot ui+0x281C); the selection stays open.
for slot=0,2 do
    local first=#W.runtime.writes
    local job=settle_job(selector.select('orbital_gas_barrage',nil,{advance=selector.advance}))
    assert(job.status=='selected'and job.index==slot and job.edited==slot,tostring(job.code)..' '..tostring(job.reason))
    assert(job.advance and job.advance.status=='advanced'and job.advance.slot==slot+1 and job.advance.verified,
        tostring(job.advance and job.advance.reason))
    assert(edited()==slot+1 and selecting()==1,'the selector is open on slot '..(slot+1))
    local written=writes_from(first)
    assert(written[#written].address==SCREEN.ui+SEL.loadout.editedSlot,'the last write is the edited slot')
    local advance_writes=0
    for _,w in ipairs(written)do if w.address==SCREEN.ui+SEL.loadout.editedSlot then advance_writes=advance_writes+1 end end
    assert(advance_writes==1)
end
assert(count('stratagem selector ADVANCED: the native selector moved from slot 0 to slot 1, the next empty slot')==1)
-- The fourth: no empty slot remains. Nothing more is written: the selection cannot be closed by data, so it stays open.
local first=#W.runtime.writes
local job=settle_job(selector.select('orbital_gas_barrage',nil,{advance=selector.advance}))
assert(job.status=='selected'and job.index==3 and job.next==nil)
assert(job.advance.status=='full'and job.advance.reason:find('the native selector stays open',1,true))
for _,w in ipairs(writes_from(first))do assert(w.address~=SCREEN.ui+SEL.loadout.editedSlot,'no advance write')end
assert(edited()==3 and selecting()==1)
for k=0,3 do assert(SCREEN.entry(k)==118 and SCREEN.widget(k)==118)end
assert(select(2,selector.reconstruct({PRECISION_ID,PRECISION_ID,PRECISION_ID,PRECISION_ID}))==4)
assert(W.read(settings.base,settings.size)==SETTINGS,'no StratagemInfo row changed')
return 'ok'
""")

    def test_a_replaced_slot_moves_on_to_the_next_empty_slot_and_the_advance_is_guarded(self):
        self.check(r"""
local function edited()
    local s=W.read(SCREEN.ui+SEL.loadout.editedSlot,4)
    return s:byte(1)+s:byte(2)*256+s:byte(3)*65536+s:byte(4)*16777216
end
-- [Precision Strike] [Eagle Airstrike] [120mm] [empty]; the selector on slot 1: replaced, then on to slot 3.
SCREEN=W.loadout_screen({entries={{type=118},{type=22},{type=136}},editedSlot=1})
local job=settle_job(selector.select('orbital_gas_barrage',nil,{advance=selector.advance}))
assert(job.status=='selected'and job.index==1 and not job.appended and job.next==3)
assert(job.advance.status=='advanced'and job.advance.slot==3 and edited()==3)
assert(SCREEN.entry(0)==118 and SCREEN.entry(1)==118 and SCREEN.entry(2)==136)
-- The advance is refused (nothing written) when the panel mode is 1 (a native pick there closes) ...
selector.reset_for_tests()
SCREEN=W.loadout_screen({entries={{type=136}},editedSlot=1})
W.write(SCREEN.ui+SEL.loadout.panelMode,W.u32(1))
local first=#W.runtime.writes
job=settle_job(selector.select('orbital_gas_barrage',nil,{advance=selector.advance}))
assert(job.status=='selected'and job.advance.status=='refused'and job.advance.reason:find('panel mode 1',1,true))
for _,w in ipairs(writes_from(first))do assert(w.address~=SCREEN.ui+SEL.loadout.editedSlot)end
assert(edited()==1)
-- ... and when the selector moved meanwhile (the advance re-checks the edited slot).
selector.reset_for_tests()
SCREEN=W.loadout_screen({entries={{type=136}},editedSlot=1})
local moved=function(world,view,handle)SCREEN.set('editedSlot',2);return selector.advance(world,view,handle)end
job=settle_job(selector.select('orbital_gas_barrage',nil,{advance=moved}))
assert(job.advance.status=='refused'and job.advance.reason:find('no longer open for slot 1',1,true))
assert(edited()==2)
-- The next empty slot follows the native rule after slot N only: no wrap, the skip bit passed over.
assert(selector.next_empty({widgets={0,5,6,7},widgetFlags={0,0,0,0}},1)==nil,'an empty slot before N is not used')
assert(selector.next_empty({widgets={5,0,0,0},widgetFlags={0,4,0,0}},0)==2,'a widget with the skip bit is passed')
assert(selector.next_empty({widgets={5,6,7,8},widgetFlags={0,0,0,0}},0)==nil)
return 'ok'
""")

    def test_the_native_close_runs_only_for_a_filled_loadout_and_every_refusal_calls_nothing(self):
        self.check(r'''
local scheduler=require('hd2runtime/runtime/scheduler')
local world=require('hd2runtime/runtime/event_world').open()
-- Runs fn inside the Runtime's own update (a job's coroutine, as the selection's advance runs) to its end.
local function in_update(fn)
    local co,out,done=coroutine.create(fn),nil,false
    local w={status='active'}
    function w.tick(dt)
        local ok,r=coroutine.resume(co,dt)
        assert(ok,r)
        if coroutine.status(co)=='dead'then out,done=r,true;w.status='complete'end
    end
    scheduler.attach(w)
    for _=1,200 do if done then break end;tick()end
    return out
end
-- A full loadout, the selection open on slot 1, which the Runtime selection just filled with the token (118).
local FULL={{type=136},{type=118},{type=41},{type=22}}
local HANDLE={index=1,edited=1,token=118}
local function refused(code,spec,setup,handle)
    selector.reset_for_tests()
    SCREEN=W.loadout_screen(spec or{entries=FULL,editedSlot=1})
    if setup then setup()end
    local before,writes=#W.runtime.selector_closes,#W.runtime.writes
    local r=in_update(function()return selector.close_native(world,selector.screen(world),handle or HANDLE)end)
    assert(r.status=='refused'and r.code==code,code..' expected, got '..tostring(r.code)..' '..tostring(r.reason))
    assert(#W.runtime.selector_closes==before and#W.runtime.writes==writes,code..' called or wrote')
    assert(W.read(SCREEN.ui+SEL.loadout.selectionOpen,1):byte()==(spec and spec.selecting==false and 0 or 1))
    assert(count('SELECTOR CLOSE REFUSED (nothing called; the native selector stays open: close it with Back): '..code)>=1)
end
refused('NOT_FULL',{entries={{type=136},{type=118},{type=41}},editedSlot=1})
refused('NOT_OPEN',{entries=FULL,editedSlot=1,selecting=false})
refused('NOT_OPEN',nil,function()SCREEN.set('editedSlot',2)end)
refused('NOT_OPEN',nil,function()SCREEN.set('subState',5)end)
refused('READY',{entries=FULL,editedSlot=1,ready=true})
refused('PANEL_MODE',nil,function()W.write(SCREEN.ui+SEL.loadout.panelMode,W.u32(1))end)
refused('NOT_BOUND',nil,function()W.write(SCREEN.ui+SEL.loadout.panel0BoundRecord,W.u64(0))end)
refused('RECORD_CHANGED',nil,nil,{index=1,edited=1,token=22})
refused('SCREEN_CHANGED',nil,function()SCREEN.close()end)
-- The handler's exact first bytes are re-proved before every call (one byte outside every pin changed here).
local C=SEL.selectorClose
local at=W.GAME+C.rva+0x1A
local byte=W.read(at,1)
refused('UNSUPPORTED_BUILD',nil,function()W.write(at,string.char((byte:byte()+1)%256))end)
W.write(at,byte)
refused('IN_MISSION',nil,function()mission({host=true})end)
W.state(3)
-- Outside the Runtime's update, or with an adapter that cannot call game functions: refused too.
selector.reset_for_tests()
SCREEN=W.loadout_screen({entries=FULL,editedSlot=1})
local r=selector.close_native(world,selector.screen(world),HANDLE)
assert(r.status=='refused'and r.code=='NOT_GAME_THREAD'and#W.runtime.selector_closes==0)
local real=W.runtime.native_selector_close
W.runtime.native_selector_close=nil
r=in_update(function()return selector.close_native(world,selector.screen(world),HANDLE)end)
assert(r.status=='refused'and r.code=='UNAVAILABLE')
W.runtime.native_selector_close=real
-- Every guard holds: the picker-close sound is asked for first (no Wwise here: not played, logged), then one call of the
-- game's close handler with this loadout UI; verified at once and over the next frames. Nothing written.
local writes=#W.runtime.writes
r=in_update(function()return selector.close_native(world,selector.screen(world),HANDLE)end)
assert(r.status=='closed'and r.verified and r.verify.selection and r.verify.subState and r.verify.list and r.verify.record
    and r.verify.stays,table.concat(logged,' | '))
assert(#W.runtime.selector_closes==1 and W.runtime.selector_closes[1].ui==SCREEN.ui and#W.runtime.writes==writes)
assert(W.read(SCREEN.ui+SEL.loadout.selectionOpen,1):byte()==0)
assert(count('stratagem selector sound picker_close not played: NO_API')==1)
assert(count('SELECTOR CLOSE VERIFIED: the native selector (open for slot 1) closed by the game\'s own close handler '
    ..'(game+146F3B0, the call Back makes)')==1,table.concat(logged,' | '))
for k=0,3 do assert(SCREEN.entry(k)==FULL[k+1].type)end
-- A call that changes nothing (the selection still open after it): reported, never taken for a close.
selector.reset_for_tests()
SCREEN=W.loadout_screen({entries=FULL,editedSlot=1})
W.SELECTOR_CLOSE_INERT=true
r=in_update(function()return selector.close_native(world,selector.screen(world),HANDLE)end)
W.SELECTOR_CLOSE_INERT=nil
assert(r.status=='not closed'and not r.verified and#W.runtime.selector_closes==2)
assert(count('SELECTOR CLOSE NOT CLOSED: the native selector (open for slot 1) NOT closed by the game')==1)
assert(W.read(settings.base,settings.size)==SETTINGS)
-- Several players (EXPERIMENTAL multiplayer): the local selector is closed all the same (no NOT_SOLO).
do
    selector.reset_for_tests()
    SCREEN=W.loadout_screen({entries=FULL,editedSlot=1,players=2})
    local r=in_update(function()return selector.close_native(world,selector.screen(world),HANDLE)end)
    assert(r.status=='closed'and r.code==nil,tostring(r.status)..' '..tostring(r.code)..' '..tostring(r.reason))
end
return 'ok'
''')

    def test_slots_on_screen_with_a_gap_are_never_written_by_record_index(self):
        self.check(r"""
-- A native pick into slot 3 while slot 2 was empty: the widgets show [Big, Eagle, empty, Gas Strike]; the record was
-- rebuilt compacted [Big, Eagle, Gas Strike]. A write by record index would land in another slot: refused.
SCREEN=W.loadout_screen({entries={{type=136},{type=22},{type=41}},editedSlot=2})
W.write(SCREEN.ui+SEL.loadout.panel0Widgets+2*SEL.loadout.widgetStride+SEL.loadout.widgetType,W.u32(0))
W.write(SCREEN.ui+SEL.loadout.panel0Widgets+3*SEL.loadout.widgetStride+SEL.loadout.widgetType,W.u32(41))
local first=#W.runtime.writes
local job=settle_job(selector.select('orbital_gas_barrage'))
assert(job.status=='refused'and job.code=='SLOTS_DIFFER'and job.reason:find('slot 2 on screen',1,true),tostring(job.code))
assert(#W.runtime.writes==first)
return 'ok'
""")

    def test_every_refusal_writes_nothing(self):
        self.check(r'''
local function refused(spec,code,setup)
    selector.reset_for_tests()
    SCREEN=W.loadout_screen(spec)
    if setup then setup()end
    local first=#W.runtime.writes
    local job=settle_job(selector.select('orbital_gas_barrage'))
    assert(job.status=='refused'and job.code==code,code..' expected, got '..tostring(job.code)..' '..tostring(job.reason))
    assert(#W.runtime.writes==first,code..' wrote')
end
local E={{type=136},{type=22},{type=41}}
-- Several players (EXPERIMENTAL multiplayer): this machine's own loadout record is written all the same; announced once.
do
    selector.reset_for_tests()
    SCREEN=W.loadout_screen({entries=E,players=2})
    local job=settle_job(selector.select('orbital_gas_barrage'))
    assert(job.status=='selected',tostring(job.code)..' '..tostring(job.reason))
    assert(count('CUSTOM STRATAGEMS MULTIPLAYER EXPERIMENTAL: 2 players (the loadout selection)')==1)
end
refused({entries=E,ready=true},'READY')
refused({entries=E,launched=true},'LAUNCHED')
refused({entries=E,subState=0},'NO_SLOT')
refused({entries=E},'NOT_BOUND',function()W.write(SCREEN.ui+SEL.loadout.panel0BoundRecord,W.u64(0))end)
refused({entries={{type=136},{type=0},{type=41}}},'RECORD_SHAPE')
refused({entries=E},'TOKEN_LIMITED',function()W.write(ROW[118]+0x50,W.u32(3))end)
W.write(ROW[118]+0x50,W.u32(4294967295))
refused({entries=E},'TOKEN_NOT_OWNED',function()W.catalogue({[BIG_ID]=2,[PRECISION_ID]=0})end)
W.catalogue({[PRECISION_ID]=2,[BIG_ID]=2})
refused({entries=E},'TOKEN_VEHICLE',function()W.write(ROW[118]+0x104,W.u32(0x100000))end)
W.write(ROW[118]+0x104,W.u32(0))
refused({entries=E},'SCREEN_CLOSED',function()SCREEN.close()end)
refused({entries=E},'IN_MISSION',function()mission({host=true})end)
W.state(3)
local unknown=settle_job(selector.select('no_such_stratagem'))
assert(unknown.status=='refused'and unknown.code=='UNKNOWN_DEFINITION')
return 'ok'
''')

    def test_the_optional_focus_frame_never_suppresses_the_card(self):
        self.check(r'''
SCREEN=W.loadout_screen({entries={{type=136}},editedSlot=0})
-- On: a frame rectangle behind the card, recoloured by update_rect, which returns nothing and still succeeds.
local S=selector.selector({placement='float',focus_frame=true})
tick(3)
assert(called('rect')==2 and called('update_rect')==1 and called('destroy_gui')==0,'card and frame drawn')
assert(S.renderer().state=='shown'and S.renderer().focusFrame=='shown')
assert(S.action('next')and called('update_rect')==2 and S.renderer().focusFrame=='shown','focus moves')
assert(count('focus frame unavailable')==0)
S.stop()
assert(called('destroy_gui')==1)
-- The frame update raises: logged once, the frame is dropped, the card stays (no destroy).
selector.reset_for_tests();calls={}
SCREEN=W.loadout_screen({entries={{type=136}},editedSlot=0})
engine.Gui.update_rect=function()error('update refused',0)end
local S2=selector.selector({placement='float',focus_frame=true})
tick(3)
assert(S2.renderer().state=='shown'and S2.shown,'the card is still shown')
assert(called('destroy_gui')==0 and called('bitmap')==1 and called('text')==2,'the card was not destroyed')
assert(count('focus frame unavailable (update refused); the card stays drawn without it')==1)
assert(S2.action('next')and count('focus frame unavailable')==1,'no frame left to update, logged once')
assert(count('drawing disabled')==0)
S2.stop()
engine.Gui.update_rect=nothing('update_rect')
-- The frame rectangle itself is refused (no id): the same, the card stays.
selector.reset_for_tests();calls={}
SCREEN=W.loadout_screen({entries={{type=136}},editedSlot=0})
local rect=engine.Gui.rect
engine.Gui.rect=function(gui,position,...)if position[3]==20 then return nil end;return rect(gui,position,...)end
local S3=selector.selector({placement='float',focus_frame=true})
tick(3)
assert(S3.renderer().state=='shown'and S3.renderer().focusFrame=='unavailable'and called('destroy_gui')==0)
assert(count('focus frame unavailable (the engine returned no id)')==1)
-- A required part refused (the background returns no id): the whole GUI is destroyed, drawing disabled.
S3.stop()
selector.reset_for_tests();calls={}
SCREEN=W.loadout_screen({entries={{type=136}},editedSlot=0})
engine.Gui.rect=function(gui,position,...)if position[3]==21 then return nil end;return rect(gui,position,...)end
local S4=selector.selector({placement='float'})
tick(3)
assert(S4.renderer().state=='failed'and called('destroy_gui')==1 and called('bitmap')==0,'aborted before the icon')
assert(count('drawing disabled: the engine returned no id')==1)
engine.Gui.rect=rect
assert(#W.runtime.writes==0,'drawing never writes')
return 'ok'
''')

    def test_the_card_follows_the_screen_and_drawing_failures_draw_nothing(self):
        self.check(r'''
SCREEN=W.loadout_screen({entries={{type=136}},subState=0})
local S=selector.selector({placement='float'})
tick(3)
assert(called('create_screen_gui')==0,'the overview shows no card')
SCREEN.set('subState',10);SCREEN.set('editedSlot',2);tick(2)
assert(called('create_screen_gui')==1)
assert(S.action('next')and S.action('previous'),'focus moves (one card)')
SCREEN.set('subState',0);tick(2)
assert(called('destroy_gui')==1 and calls[#calls].args[1]==MAIN,'hidden when the grid closes')
SCREEN.set('subState',10);tick(2)
assert(called('create_screen_gui')==2,'shown again')
alive={}                      -- the game released the world: its GUIs went with it, nothing is destroyed twice
SCREEN.close();tick(2)
assert(called('destroy_gui')==1 and count('stratagem selector hidden (the loadout screen closed)')==1)
S.stop()
alive={MAIN}
-- The engine font missing: nothing is created, drawing is disabled for the session.
local function attempt(prepare,reason)
    selector.reset_for_tests();calls={}
    SCREEN=W.loadout_screen({entries={{type=136}}})
    local undo=prepare()
    local S2=selector.selector({placement='float'})
    tick(3)
    assert(called('create_screen_gui')==0 and called('bitmap')==0 and called('text')==0,reason..': drew')
    assert(count('drawing disabled: '..reason)>=1,reason)
    S2.stop()
    if undo then undo()end
end
attempt(function()resources.set('material',FONT,'unloaded')
    return function()resources.set('material',FONT)end end,'the engine font is not loaded')
attempt(function()resources.set('texture',ICON_NAME,'unloaded')
    return function()resources.set('texture',ICON_NAME)end end,'a card icon is not loaded')
attempt(function()rawset(_G,'stingray',nil);return function()rawset(_G,'stingray',engine)end end,
    'the engine scripting API (stingray) is unavailable')
-- A failing engine call: the partial GUI is destroyed and drawing stops.
selector.reset_for_tests();calls={}
SCREEN=W.loadout_screen({entries={{type=136}}})
engine.Gui.text=function()error('engine refused',0)end
local S3=selector.selector({placement='float'})
tick(3)
assert(called('create_screen_gui')==1 and called('destroy_gui')==1 and count('drawing disabled: engine refused')==1)
assert(#W.runtime.writes==0,'drawing never writes')
return 'ok'
''')

    def test_the_drawing_proof_draws_a_rectangle_a_text_and_an_image_and_closes(self):
        self.check(r'''
local gui=require('hd2runtime/runtime/engine_gui')
local runtime=world_module.open().runtime
local LABEL=texts.handle('ogb_label','Orbital Gas Barrage',MOD)
local overlay,why=selector.overlay(runtime,{text=LABEL,icon=ICON})
assert(overlay,tostring(why))
assert(called('create_screen_gui')==1 and called('rect')==1 and called('bitmap')==1 and called('text')==1)
assert(find('bitmap',2,ICON_NAME),'the Runtime icon material')
local text=find('text',2,'Orbital Gas Barrage')
assert(text and text.args[3]==FONT and text.args[5]==FONT and text.args[6].kind=='Vector3'and text.args[7].kind=='Color')
assert(overlay.calls==3)
overlay.close()
assert(called('destroy_gui')==1 and calls[#calls].args[1]==MAIN,'removed cleanly')
overlay.close()
assert(called('destroy_gui')==1,'closing twice destroys once')
assert(#W.runtime.writes==0,'drawing writes nothing')
-- Not drawn: an unloaded icon or font, or a constructor that is not callable (nothing is created).
local function refused(prepare,text)
    calls={}
    local undo=prepare()
    local o,reason=selector.overlay(runtime,{text=LABEL,icon=ICON})
    if undo then undo()end
    assert(o==nil and tostring(reason):find(text,1,true),tostring(reason))
    assert(called('create_screen_gui')==0,text..': created a GUI')
end
refused(function()resources.set('texture',ICON_NAME,'unloaded');return function()resources.set('texture',ICON_NAME)end end,
    'the icon is not loaded')
refused(function()resources.set('material',FONT,'unloaded');return function()resources.set('material',FONT)end end,
    'the engine font is not loaded')
refused(function()local v=engine.Vector3;engine.Vector3={};return function()engine.Vector3=v end end,
    'stingray.Vector3 is not callable')
refused(function()local w=alive;alive={};return function()alive=w end end,'the main world is not among the worlds')
-- The callable test itself: functions and tables or userdata with a __call metamethod.
assert(gui.callable(print)and gui.callable(engine.Vector3)and not gui.callable({})and not gui.callable(3))
return 'ok'
''')

    def test_the_engine_gui_validates_every_value_before_calling(self):
        self.check(r'''
local gui=require('hd2runtime/runtime/engine_gui')
local screen=assert(gui.open())
assert(screen.width==1920 and screen.height==1080)
local before=#calls
assert(screen.rect(10,10,1,100,50,{300,0,0,0})==nil,'a colour component above 255')
assert(screen.rect(10,10,1.5,100,50,{255,0,0,0})==nil,'a fractional layer')
assert(screen.rect(0/0,10,1,100,50,{255,0,0,0})==nil,'NaN')
assert(screen.rect(10,10,1,99999,50,{255,0,0,0})==nil,'wider than the screen')
assert(screen.text('line'..string.char(10)..'break','core/performance_hud/monaco',20,'core/performance_hud/monaco',10,10,1,
    {255,255,255,255})==nil,'a control character')
assert(screen.text('ok','core/performance_hud/monaco',1000,'core/performance_hud/monaco',10,10,1,{255,255,255,255})==nil)
assert(screen.bitmap('bad name!',10,10,1,64,64,{255,255,255,255})==nil,'a resource name with spaces')
assert(#calls==before,'nothing invalid reaches the engine')
local id=assert(screen.rect(10,10,1,100,50,{255,0,0,0}))
assert(screen.update_rect(id,10,10,1,100,50,{0,0,0,0})==true,'an update that returns nothing succeeded')
local saved=engine.Gui.update_rect
engine.Gui.update_rect=function()error('busy',0)end
local done,why=screen.update_rect(id,10,10,1,100,50,{0,0,0,0},{optional=true})
assert(done==nil and why=='busy'and screen.state=='open','an optional failure leaves the GUI open')
engine.Gui.update_rect=saved
engine.Gui.text=function()error('engine refused',0)end
assert(screen.text('ok','core/performance_hud/monaco',20,'core/performance_hud/monaco',10,10,1,{255,255,255,255})==nil)
assert(screen.state=='failed'and screen.reason=='engine refused'and called('destroy_gui')==1,'a failed call closes the GUI')
assert(screen.rect(10,10,1,100,50,{255,0,0,0})==nil,'nothing more after a failure')
return 'ok'
''')

    def test_the_virtual_card_follows_the_scroll_to_the_end_of_the_list(self):
        self.check(r'''
-- A long list: 10 rows in three sections (headers 30 units), the final row holding 2 cards. Content 940 units, limit 432.
local ROWS,SECTIONS={4,4,4,4,4,4,4,4,4,2},{0,4,7}
SCREEN=W.loadout_screen({entries={{type=136},{type=22},{type=41}},editedSlot=1})
local g=W.native_grid(SCREEN,{rows=ROWS,sections=SECTIONS,scroll=0})
assert(g.content==940 and g.limit==432)
local S=selector.selector({placement='grid'})
tick(4)
-- Top: the final cell (row 9, column 2) is below the viewport: hidden, logged once with its cell.
assert(not S.shown and called('create_screen_gui')==0)
assert(count('stratagem selector not shown for slot 1: outside the viewport (its cell: end, row 9, column 2)')==1,
    table.concat(logged,' | '))
-- Middle: still hidden, nothing logged again, nothing drawn.
W.native_grid(SCREEN,{rows=ROWS,sections=SECTIONS,scroll=216})
tick(4)
assert(not S.shown and called('create_screen_gui')==0 and count('outside the viewport')==1)
-- Bottom (the clamped limit): the card enters the viewport in the final cell, at the native size and pitch.
g=W.native_grid(SCREEN,{rows=ROWS,sections=SECTIONS,scroll='bottom'})
tick(1)
assert(not S.shown,'not while it moves')
tick(3)
assert(S.shown,table.concat(logged,' | '))
local p=S.placement
local last=g.rows[9]
assert(p.target.kind=='end'and p.target.row==9 and p.target.column==2)
assert(near(p.card.x,last[2].x+102)and near(p.card.y,last[1].y)and near(p.card.w,96)and near(p.card.h,96),
    'exactly the next cell of the final row')
assert(near(p.card.x,590+(12+2*85)*1.2)and near(p.card.y,200+528*1.2-(935-432)*1.2),'its content position, scrolled')
assert(p.text==nil,'one free cell and no row below inside the frame: no name or description')
assert(count('in the grid: end cell, row 9, column 2')==1 and count('no free area for the name and description')==1)
local f={x=590,y=200,w=395*1.2,h=528*1.2}
assert(p.card.x>=f.x and p.card.y>=f.y and p.card.x+p.card.w<=f.x+f.w+1e-6 and p.card.y+p.card.h<=f.y+f.h+1e-6,
    'inside the grid frame')
for _,row in pairs(g.rows)do for _,c in ipairs(row)do
    assert(not(p.card.x<c.x+c.w-0.5 and c.x<p.card.x+p.card.w-0.5 and p.card.y<c.y+c.h-0.5 and c.y<p.card.y+p.card.h-0.5),
        'no native card covered')
end end
assert(called('rect')==2 and called('bitmap')==1 and called('text')==0,'the tile: edge, inner frame, icon')
-- Still: nothing redrawn.
local before=#calls
tick(10)
assert(#calls==before)
-- Scrolling back up: hidden at once.
W.native_grid(SCREEN,{rows=ROWS,sections=SECTIONS,scroll=100})
tick(4)
assert(not S.shown and called('destroy_gui')==1)
assert(#W.runtime.writes==0,'placement writes nothing')
S.stop()
-- A partial final row with room to its right (1 card): the name and description in the free cells beside it.
selector.reset_for_tests();calls={}
SCREEN=W.loadout_screen({entries={{type=136}},editedSlot=0})
g=W.native_grid(SCREEN,{rows={4,4,4,4,4,4,4,4,4,1},sections=SECTIONS,scroll='bottom'})
local S2=selector.selector({placement='grid'})
tick(4)
p=S2.placement
assert(S2.shown and p.target.column==1 and p.text and near(p.text.x,p.card.x+102)and near(p.text.w,102+96))
assert(find('text',2,'Orbital Gas Barrage')and find('text',2,'Calls down a barrage of gas shells.'))
S2.stop()
return 'ok'
''')

    def test_coordinate_diagnostics_calibrate_against_the_native_cards(self):
        self.check(r'''
-- The calibration build: the tile alone at layer 900, the diagnostics on. A long list whose final row holds 1 card, so a
-- name and description would have room beside the card: tile only draws neither.
local ROWS,SECTIONS={4,4,4,4,4,4,4,4,4,1},{0,4,7}
SCREEN=W.loadout_screen({entries={{type=136}},editedSlot=0})
local g=W.native_grid(SCREEN,{rows=ROWS,sections=SECTIONS,scroll='bottom'})
local S=selector.selector({placement='grid',tile_only=true,layer=900,diagnostics=true})
tick(4)
assert(S.shown and S.placement.text==nil,table.concat(logged,' | '))
assert(not find('text',2,'Orbital Gas Barrage')and not find('text',2,'Calls down a barrage of gas shells.'),
    'no name or description beside the tile')
-- The tile: edge and inner frame at 900 and 901, the icon at 902.
local tile={}
-- (Gui.rect(gui, position, ...), Gui.bitmap(gui, material, position, ...), Gui.text(gui, s, font, size, material,
-- position, ...).)
local function at(c)return c.name=='rect'and c.args[2]or c.name=='bitmap'and c.args[3]or c.name=='text'and c.args[6]end
for _,c in ipairs(calls)do
    if(c.name=='rect'or c.name=='bitmap')and at(c)[3]>=900 and at(c)[3]<=902 then tile[#tile+1]=c end
end
assert(#tile==3 and at(tile[1])[3]==900 and at(tile[2])[3]==901 and tile[3].name=='bitmap'and at(tile[3])[3]==902,
    'the tile on its own layers')
-- The calibration lines: the engine facts, three native cards in different rows and columns, every stage, and V.
assert(count('calibration (slot 0): GUI resolution 1920 x 1080, back buffer ?, worlds 1 (main #1); frame 590.0, 200.0, '
    ..'474.0 x 633.6 px (1.2000 px/unit for its 395 x 528 units); card scale 1.2000 px/unit; scroll 432.00 of limit '
    ..'432.00, content 940.00 units; column 0 at 12.00 units')==1,table.concat(logged,' | '))
local rows,columns={},{}
for k=0,2 do
    local line
    for _,l in ipairs(logged)do if l:find('calibration N'..k..' row',1,true)then line=l end end
    assert(line,'sample N'..k)
    local r,c=line:match('row (%d+) column (%d+)')
    rows[tonumber(r)],columns[tonumber(c)]=true,true
    assert(line:find('content (',1,true)and line:find('after scroll (',1,true)and line:find('model (',1,true)
        and line:find('native transform (',1,true)and line:find('Runtime GUI (',1,true),line)
    assert(line:find('model - native (0.00, 0.00)',1,true),'the fixture lays the cards out by the model: '..line)
end
local n=0;for _ in pairs(rows)do n=n+1 end
local m=0;for _ in pairs(columns)do m=m+1 end
assert(n==3 and m>=2,'three rows and more than one column')
-- N0: the first card of the first fully visible row; its stages agree with the fixture's own layout.
local cal=selector.calibration(require('hd2runtime/runtime/event_world').open(),selector.screen(
    require('hd2runtime/runtime/event_world').open()),selector.grid(require('hd2runtime/runtime/event_world').open(),
    selector.screen(require('hd2runtime/runtime/event_world').open())),S.placement)
local n0=cal.samples[1]
assert(near(n0.scrolled.y,n0.content.y-432)and near(n0.native.x,g.rows[n0.row][1].x)and near(n0.native.y,
    g.rows[n0.row][1].y)and near(n0.runtime.x,n0.native.x)and near(n0.runtime.y,n0.native.y))
assert(count('calibration V row 9 column 1: content (97.00, 935.00) -> after scroll (97.00, 503.00)')==1
    and count('inside the viewport')==1)
-- The markers, in their own screen GUI: the frame F, N0..N2, V, the screen corners and centre, the low-layer probes.
assert(called('create_screen_gui')==2,'the tile and the markers')
for _,label in ipairs({'F','V r9 c1','BL 0,0','BR','TL','TR 1920,1080','C','L'})do
    assert(find('text',2,label),'marker '..label)
end
for k=0,2 do
    local found=false
    for _,c in ipairs(calls)do if c.name=='text'and tostring(c.args[2]):find('^N'..k..' r')then found=true end end
    assert(found,'marker N'..k)
end
local probes=0
for _,c in ipairs(calls)do if c.name=='rect'and at(c)[3]==21 then probes=probes+1 end end
assert(probes==2,'a low-layer probe at N0 and at V')
for _,c in ipairs(calls)do
    if c.name=='rect'or c.name=='bitmap'or c.name=='text'then
        local v=at(c)
        assert(v[1]>=0 and v[2]>=0 and v[1]<=1920 and v[2]<=1080,'every marker inside the GUI')
    end
end
-- Still: nothing redrawn, nothing logged again.
local before,lines=#calls,#logged
tick(10)
assert(#calls==before and#logged==lines)
-- Scrolling away: the tile and the markers close; at the top V is outside the viewport, the markers still drawn.
W.native_grid(SCREEN,{rows=ROWS,sections=SECTIONS,scroll=0})
tick(1)
assert(called('destroy_gui')==2 and not S.shown)
tick(3)
assert(called('create_screen_gui')==3 and count('calibration V row 9 column 1')==2 and count(
    'outside the viewport')>=1,table.concat(logged,' | '))
-- F8 in the proof: off closes the markers and stops the calibration; on again draws them at the next stillness.
assert(S.diagnostics()==false and called('destroy_gui')==3 and count('coordinate diagnostics off')==1)
tick(6)
assert(called('create_screen_gui')==3)
assert(S.diagnostics(true)==true)
tick(1)
assert(called('create_screen_gui')==4,'drawn again')
S.stop()
assert(called('destroy_gui')==4)
-- The mismatch is measured, never absorbed: every native card 7 px higher than the model shows as model - native -7.
selector.reset_for_tests()
SCREEN=W.loadout_screen({entries={{type=136}},editedSlot=0})
W.native_grid(SCREEN,{rows=ROWS,sections=SECTIONS,scroll='bottom'})
local world=require('hd2runtime/runtime/event_world').open()
local view=selector.screen(world)
local grid=selector.grid(world,view)
for _,row in pairs(grid.rows)do for _,c in ipairs(row)do c.y=c.y+7 end end
local target=selector.target(grid,nil)
cal=selector.calibration(world,view,grid,nil,target,'refused for the test')
assert(#cal.samples==3)
for _,item in ipairs(cal.samples)do assert(near(item.delta.y,-7)and near(item.delta.x,0))end
assert(cal.virtual and not cal.virtual.visible and cal.virtual.reason:find('V is the unanchored model',1,true))
assert(#W.runtime.writes==0,'the diagnostics write nothing')
return 'ok'
''')

    def test_a_full_final_row(self):
        self.check(r'''
-- A short list (no scrolling) with a full final row: a new row fits below it inside the viewport.
SCREEN=W.loadout_screen({entries={{type=136}},editedSlot=0})
local g=W.native_grid(SCREEN,{rows={4,4},scroll=0})
assert(g.content==200 and g.limit==0)
local S=selector.selector({placement='grid'})
tick(4)
local p=S.placement
assert(S.shown and p.target.kind=='end-new-row'and p.target.row==2 and p.target.column==0)
assert(near(p.card.x,g.rows[1][1].x)and near(p.card.y,g.rows[1][1].y-102),'column 0, one row pitch below')
assert(p.text and near(p.text.x,p.card.x+102)and near(p.text.w,2*102+96),'its text in the free cells to its right')
S.stop()
-- A scrolling list with a full final row: a new row cannot come into view (the list stops 20 units below its
-- content), so the card takes the free cell at the end of the token's category section (the Orbital section: 9).
selector.reset_for_tests();calls={}
SCREEN=W.loadout_screen({entries={{type=136}},editedSlot=0})
local ROWS,SECTIONS,IDS={4,4,4,3,4,4,2,4,4,4},{0,4,7},{5,9,7}
W.write(ROW[118]+0xB8,W.u32(9))
g=W.native_grid(SCREEN,{rows=ROWS,sections=SECTIONS,sectionIds=IDS,scroll=0})
local S2=selector.selector({placement='grid'})
tick(4)
assert(not S2.shown and count('not shown for slot 0: outside the viewport (its cell: section, row 6, column 2)')==1,
    table.concat(logged,' | '))
g=W.native_grid(SCREEN,{rows=ROWS,sections=SECTIONS,sectionIds=IDS,scroll=300})
tick(4)
p=S2.placement
assert(S2.shown and p.target.kind=='section'and near(p.card.x,g.rows[6][2].x+102)and near(p.card.y,g.rows[6][1].y))
assert(p.text==nil or p.text.x>p.card.x,'never below a section (the next one starts there)')
g=W.native_grid(SCREEN,{rows=ROWS,sections=SECTIONS,sectionIds=IDS,scroll='bottom'})
tick(4)
assert(S2.shown,'still in view at the bottom')
S2.stop()
-- No section of the token's category has a free cell: the last section that has one.
selector.reset_for_tests()
W.write(ROW[118]+0xB8,W.u32(42))
SCREEN=W.loadout_screen({entries={{type=136}},editedSlot=0})
W.native_grid(SCREEN,{rows=ROWS,sections=SECTIONS,sectionIds=IDS,scroll=300})
local S3=selector.selector({placement='grid'})
tick(4)
assert(S3.shown and S3.placement.target.kind=='any-section'and S3.placement.target.row==6)
S3.stop()
-- Every row full and the list scrolls: no cell anywhere; the limitation is reported, nothing is drawn.
selector.reset_for_tests();calls={}
SCREEN=W.loadout_screen({entries={{type=136}},editedSlot=0})
W.native_grid(SCREEN,{rows={4,4,4,4,4,4,4,4},sections={0,4},scroll='bottom'})
local S4=selector.selector({placement='grid'})
tick(4)
assert(not S4.shown and called('create_screen_gui')==0)
assert(count('not shown for slot 0: the final row is full and the list scrolls (it stops 20 units below its content, '
    ..'less than a 80-unit card), and no section has a free cell')==1,table.concat(logged,' | '))
S4.stop()
W.write(ROW[118]+0xB8,W.u32(0))
return 'ok'
''')

    def test_the_model_is_checked_against_every_native_card(self):
        self.check(r'''
local ROWS,SECTIONS={4,4,4,4,4,4,4,4,4,2},{0,4,7}
-- A native card off its column: refused, nothing drawn.
SCREEN=W.loadout_screen({entries={{type=136}},editedSlot=0})
local g=W.native_grid(SCREEN,{rows=ROWS,sections=SECTIONS,scroll='bottom'})
local E=SEL.grid.element
local list=SCREEN.ui+SEL.grid.list
local card=list+(9-g.first)*SEL.grid.rowWidgetStride+SEL.grid.cardWidget
W.write(card+E.tx,W.f32(g.rows[9][1].x+7))
local S=selector.selector({placement='grid'})
tick(4)
assert(not S.shown and count('not shown for slot 0: the native cards do not match the grid model')==1,
    table.concat(logged,' | '))
S.stop()
-- Row heights that do not add up to the content height: refused.
selector.reset_for_tests()
SCREEN=W.loadout_screen({entries={{type=136}},editedSlot=0})
W.native_grid(SCREEN,{rows=ROWS,sections=SECTIONS,scroll='bottom'})
W.write(SCREEN.ui+SEL.grid.list+SEL.grid.scroll.content,W.f32(999))
local S2=selector.selector({placement='grid'})
tick(4)
assert(not S2.shown and count('the row heights do not add up to the content height')==1)
S2.stop()
-- A frame whose scale differs from its cards: refused.
selector.reset_for_tests()
SCREEN=W.loadout_screen({entries={{type=136}},editedSlot=0})
W.native_grid(SCREEN,{rows=ROWS,sections=SECTIONS,scroll='bottom'})
W.write(SCREEN.ui+SEL.grid.list+E.m22,W.f32(1.5))
local S3=selector.selector({placement='grid'})
tick(4)
assert(not S3.shown and count('the grid frame and its cards differ in scale')==1)
S3.stop()
-- The rules on their own: a cell overlapping a native card is not visible; a target never comes from what is shown.
local grid={rowCount=2,lastCards=1,firstRow=0,realized=2,content=200,scroll=0,limit=0,sections={{first=0,id=1}},
    viewport={x=0,y=0,w=395,h=528},rowCards={[0]=4,[1]=1},heights={[0]=115,[1]=85},
    rows={[0]={{x=12,y=528-110,w=80,h=80},{x=97,y=528-110,w=80,h=80},{x=182,y=528-110,w=80,h=80},
        {x=267,y=528-110,w=80,h=80}},[1]={{x=12,y=528-195,w=80,h=80}}},cards={}}
for _,row in pairs(grid.rows)do for _,c in ipairs(row)do grid.cards[#grid.cards+1]=c end end
local target=selector.target(grid,nil)
assert(target.kind=='end'and target.row==1 and target.column==1)
local place=selector.placement(grid,target)
assert(place.visible and near(place.card.x,97)and near(place.card.y,528-195))
grid.cards[#grid.cards+1]={x=100,y=528-195,w=80,h=80}
place=selector.placement(grid,target)
assert(not place.visible and place.reason=='it would overlap a native card')
assert(#W.runtime.writes==0)
return 'ok'
''')

    def test_selecting_the_grid_card_writes_the_token_and_identity_follows_the_loadout(self):
        self.check(r'''
SCREEN=W.loadout_screen({entries={{type=136},{type=22},{type=41}},editedSlot=1})
W.native_grid(SCREEN,{rows={4,4,2}})
local S=selector.selector({placement='grid'})
tick(4)
assert(S.shown)
assert(S.action('confirm'))
local job=settle_job(S.handles[1])
assert(job.status=='selected'and job.index==1,tostring(job.code)..' '..tostring(job.reason))
assert(SCREEN.entry(1)==118 and SCREEN.widget(1)==118,'slot 1 holds the token, repainted by the game')
local set=selector.virtual_slots()
assert(set.slots[1].definition=='orbital_gas_barrage'and set.slots[1].token==PRECISION_ID)
assert(table.concat(set.pairs,',')==table.concat({BIG_ID,PRECISION_ID,3193297673},','))
-- Another slot changed with the native picker (slot 2 becomes type 22): the identity follows the new order.
W.write(SCREEN.record+0x188+2*0x30,W.u32(22))
SCREEN.frame()
tick(3)
set=selector.virtual_slots()
assert(set and table.concat(set.pairs,',')==table.concat({BIG_ID,PRECISION_ID,2281932031},','),'the new order is recorded')
assert(count('virtual slots kept: 1 = orbital_gas_barrage; the loadout order is now recorded as')==1)
-- The save then holds that order: the virtual slot is recognised; any other order is not.
assert(select(2,selector.reconstruct({BIG_ID,PRECISION_ID,2281932031}))==1)
assert(selector.reconstruct({BIG_ID,PRECISION_ID,3193297673})==nil)
-- Undo (Ctrl+F7) puts slot 1 back.
local back=settle_job(selector.restore())
assert(back.status=='restored'and back.exact)
tick(2)
assert(SCREEN.entry(1)==22 and SCREEN.widget(1)==22 and selector.virtual_slots()==nil)
-- Select again, then the virtual slot itself changed natively: the identity is dropped, never guessed.
assert(S.action('confirm'))
assert(settle_job(S.handles[2]).status=='selected')
W.write(SCREEN.record+0x188+1*0x30,W.u32(41))
SCREEN.frame()
tick(3)
assert(selector.virtual_slots()==nil and count('virtual slot 1 (orbital_gas_barrage) no longer holds its token: it '
    ..'now holds ')==1 and count('that slot is plain again (the loadout order was ')==1)
assert(W.read(settings.base,settings.size)==SETTINGS,'no StratagemInfo row changed')
return 'ok'
''')

    def test_menu_actions_are_read_as_data(self):
        self.check(r'''
local world=world_module.open()
assert(selector.menu_actions(world)==nil,'no input owner yet')
W.input_actions({[SEL.input.menu.select]=true,[SEL.input.menu.down]=true})
local a=selector.menu_actions(world)
assert(a.select and a.down and not a.up and not a.back and not a.left and not a.right)
return 'ok'
''')

    def test_a_virtual_definition_is_validated(self):
        self.check(r'''
local function bad(spec,text)
    local ok,err=pcall(virtual.define,spec,MOD)
    assert(not ok and tostring(err):find(text,1,true),tostring(err))
end
local name=texts.handle('ogb_name','Orbital Gas Barrage',MOD)
local description=texts.handle('ogb_description','Calls down a barrage of gas shells.',MOD)
local display={name=name,description=description,icon=ICON}
bad({id='orbital_gas_barrage',display=display,selection={token='Orbital Precision Strike'},
    mission={carrier='Orbital 120mm HE Barrage'}},'already defined')
bad({id='Bad Id',display=display,selection={token='Orbital Precision Strike'},
    mission={carrier='Orbital 120mm HE Barrage'}},'id must be')
bad({id='x',display={name='plain',description=description,icon=ICON},selection={token='Orbital Precision Strike'},
    mission={carrier='Orbital 120mm HE Barrage'}},'Runtime texts')
bad({id='x',display=display,selection={token='Orbital Precision Strike'},mission={carrier='Orbital Precision Strike'}},
    'must differ')
bad({id='x',display=display,selection={token='Not A Stratagem'},mission={carrier='Orbital 120mm HE Barrage'}},
    'catalogued stratagem')
bad({id='x',display=display,selection={token='Orbital Precision Strike'},mission={carrier='Orbital 120mm HE Barrage'},
    payload={}},'payload needs mission.discover')
local plasma=virtual.define({id='second',display=display,selection={token='Orbital Precision Strike'},
    mission={carrier='Orbital 120mm HE Barrage'},calldown={code={'up','up','down'}}},MOD)
assert(#virtual.list()==2 and virtual.list()[2]==plasma and plasma.calldown.code[3]=='down')
local n,d=virtual.strings(GAS,'us')
assert(n=='Orbital Gas Barrage'and d=='Calls down a barrage of gas shells.')
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
