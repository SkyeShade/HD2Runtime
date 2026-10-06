"""proof/GasBarrageMissionProof 0.5.0 (docs/custom-stratagems.md, "The custom stratagem in a mission"): the custom
stratagem selector's virtual Gas Barrage slots become a carrier DISCOVERED from what the account owns in a solo mission,
by the Runtime's own identity (runtime/stratagem_selector.lua conversion_spec -> runtime/stratagem_slot_conversion.lua
convert_virtual), with the carrier presented as Orbital Gas Barrage aboard the ship, answering to the Gas Barrage code
UP UP DOWN DOWN (the public calldown_code field on the carrier only) and calling in its own normal payload.
Offline, the proof's own addon end to end: the ship loadout screen and the panel, the save, the carrier's presentation and
code, the code checks, the mission record and HUD list, a call-in, the mission-end rebuild, the reconstruction and the
code's restore."""
import json
import unittest

from support import ROOT, run
from test_stratagem_calldown_code import WORLD, PROOF
from test_stratagem_slot_conversion import SLOT

FOLDER = ROOT / 'proof/GasBarrageMissionProof'

HARNESS = r"""
-- The engine GUI stand-in (recorded calls; the engine's own types and returns, as test_stratagem_selector's).
local calls={}
local MAIN,UW=newproxy(true),newproxy(true)
local alive={MAIN,UW}
local function rec(name)return function(...)calls[#calls+1]={name=name,args={...}};return#calls end end
local function nothing(name)return function(...)calls[#calls+1]={name=name,args={...}}end end
local function constructor(kind)return setmetatable({},{__call=function(_,...)return {kind=kind,...}end})end
rawset(_G,'stingray',{Application={main_world=function()return MAIN end,worlds=function()return alive end},
    World={create_screen_gui=rec('create_screen_gui'),destroy_gui=nothing('destroy_gui')},
    Gui={resolution=function()return 1920,1080 end,rect=rec('rect'),bitmap=rec('bitmap'),text=rec('text'),
        update_rect=nothing('update_rect'),update_bitmap=nothing('update_bitmap'),
        material=function(gui,m)calls[#calls+1]={name='gui_material',args={gui,m}};return {kind='Material',gui=gui,material=m}end},
    Material={set_vector4=nothing('set_vector4')},
    Quaternion={from_elements=function(x,y,z,w)return {kind='Quaternion',x,y,z,w}end},
    Vector2=constructor('Vector2'),Vector3=constructor('Vector3'),Color=function(a,r,g,b)return {kind='Color',a,r,g,b}end})
-- The Ui World: named by the game context, second in the engine's world array.
local SEL=require('hd2runtime/domains/stratagem_selector')
local OV=SEL.slotOverlay
local CONTEXT=(function()local s=W.read(W.GAME+OV.gameContext,8);local lo,hi=0,0
    for i=4,1,-1 do lo=lo*256+s:byte(i);hi=hi*256+s:byte(i+4)end;return lo+hi*4294967296 end)()
local UI_WORLD=0x24A97280080
W.write(CONTEXT+OV.uiWorld,W.u32(UI_WORLD%4294967296)..W.u32(math.floor(UI_WORLD/4294967296)))
W.engine_worlds({0x24A96260080,UI_WORLD})
-- The proof's masked icon and the engine font resident; the game's text registry with room for one more table.
local images=require('hd2runtime/runtime/image_resources');images.reset_for_tests()
local texts=require('hd2runtime/runtime/text_resources');texts.reset_for_tests()
require('hd2runtime/runtime/virtual_stratagems').reset_for_tests()
local selector=require('hd2runtime/runtime/stratagem_selector');selector.reset_for_tests()
require('hd2runtime/runtime/stratagem_loadout').reset_for_tests()
local ICON_NAME=images.name(RESOURCE,'orbital_gas_barrage_masks')
local FONT='core/performance_hud/monaco'
W.icon_resources({textures={ICON_NAME},materials={ICON_NAME,FONT},fonts={FONT}})
local VANILLA={us={[0x4FAAD695]='ORBITAL 120MM HE BARRAGE',[0x628B5A83]='Orbital 120mm HE Barrage'}}
local REG=W.text_registry({tables={VANILLA,VANILLA},capacity=3})
local ID22=2281932031
-- The ship loadout screen with its native grid and details panel, and the game's per-frame bind.
local SCREEN
scheduler.attach({status='active',tick=function()if SCREEN then SCREEN.frame()end end})
local function ship(entries)
    SCREEN=W.loadout_screen({entries=entries,editedSlot=0,selecting=false})
    W.native_grid(SCREEN,{rows={4,4,2},sections={0},scroll=0,scale=1,frame={x=75,y=104}})
    W.native_details(SCREEN,{x=500,y=232,scale=1})
end
-- The player opens the native selector on a slot and picks Orbital Gas Barrage in the custom panel (F7: focus, select).
local function select_into(slot)
    SCREEN.set('selecting',false);tick(2)
    SCREEN.set('editedSlot',slot);SCREEN.set('selecting',true);tick(6)
    press('F7');press('F7')
    tick(30)
end
local HS=require('hd2runtime/domains/stratagem_calldown').hud.slots
"""


def addon():
    from test_event_scripting import SDK
    spec = json.loads((FOLDER / 'hd2runtime.json').read_text(encoding='utf-8'))
    body = (FOLDER / 'src/addon.lua').read_text(encoding='utf-8-sig')
    return spec['resource'], SDK.wrap_addon(spec['resource'], spec['requires']['hd2runtime']['min_version'], body)


# The ship as in the first live test: Orbital Gas Barrage from the custom panel into slot 0, then three stratagems picked
# natively; the save. The proof's first carrier candidate, the Orbital Napalm Barrage (type 106), is a reviewed row at
# its catalogue root (group 5, row 5) beside the others; its package is not resident until the conversion requests it
# (the loader's own gate, with a simulated loader as tests/test_asset_loading.py does).
FLOW = r"""
local NAPALM_ID=2902516083
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
    {type=106,id=NAPALM_ID,package='0x96CEDF4706334C5F',payload='0xA16AB4FF66AE6970',sequence={2,2,3,4,2,1},group=5,
        row=5,cooldown=240,fields=pres(NAPALM_ID)},
    {type=71,id=1606251952,package='0x0000000000071071',payloads={},sequence={1,1,3,3,2,3},group=0,row=0},
    {type=102,id=705279885,package='0x0000000000102102',payloads={},sequence={1,1,3,3,2,2,3},group=0,row=1},
    {type=123,id=4177070437,package='0x0000000000123123',payloads={},sequence={1,1,3,3,4,2,4,2},group=0,row=2},
})
for kind,r in pairs(settings.rows)do ROW[kind]=r.address end
for _,kind in ipairs({118,136,106})do
    W.write(ROW[kind]+0x50,W.u32(4294967295));W.write(ROW[kind]+0x80,W.u32(2));W.write(ROW[kind]+0xC0,W.u32(1))
end
W.catalogue({[PRECISION_ID]=2,[BIG_ID]=2,[NAPALM_ID]=2})
local LO=SEL.loadout
local function entry_at(k)return SCREEN.record+LO.entries+k*LO.entryStride end
local function repaint()W.write(SCREEN.ui+LO.panel0BoundRecord,W.u64(0))end
local function native_append(kind)
    local n=SCREEN.count()
    W.write(entry_at(n)+LO.entryType,W.u32(kind));W.write(entry_at(n)+LO.entryUses,W.u32(4294967295))
    W.write(SCREEN.record+LO.count,W.u32(n+1));repaint();tick(2)
end
local ROW118,ROW136,ROW106=ROW[118],ROW[136],ROW[106]
local PRECISION_ROW,DONOR_ROW,CARRIER_ROW=W.read(ROW118,400),W.read(ROW136,400),W.read(ROW106,400)
local h_,l_=images.hash(ICON_NAME)
local CUSTOM=W.u32(l_)..W.u32(h_)
local assets=require('hd2runtime/core/assets')
local RM=require('hd2runtime/domains/package_residency').loader.refcountMap
local map_header,map_entries=W.alloc(0x1000),W.alloc(0x1000)
W.write(map_header+RM.entries,W.u64(map_entries))
assets.reset()
local original_prove=assets.prove
assets.prove=function()return {instance=map_header,request=2,capacity=16}end
local PACKAGE=assets.dependency_for_stratagem(NAPALM_ID,'x').package
local requested=0
W.runtime.packages[PACKAGE]='absent'
W.runtime.package_request=function()requested=requested+1;W.runtime.packages[PACKAGE]=nil end
local function mission_record(loadout)
    local record={{type=124,uses=-1,granted=1},{type=33,uses=-1,granted=1}}
    for _,kind in ipairs(loadout)do record[#record+1]={type=kind,uses=-1,granted=0}end
    record[#record+1]={type=41,uses=-1,granted=1}
    local hud={}
    for k,e in ipairs(record)do hud[k]={type=e.type,code={}}end
    return record,hud
end
local function untouched(row,native,ranges)
    local now=W.read(row,400)
    for i=1,400 do
        local at,inside=i-1,false
        for _,r in ipairs(ranges or{})do if at>=r[1]and at<r[2]then inside=true end end
        if now:byte(i)~=native:byte(i)and not inside then return false end
    end
    return true
end
local function done()assets.prove=original_prove;W.runtime.package_request=nil end
-- The game rebuilding a HUD slot after its record entry's type changed: the type, the displayed type and the arrows of
-- the row's code (offline: written as the game would, with the real HUD's cell bytes).
local function unhex(h)return(h:gsub('..',function(x)return string.char(tonumber(x,16))end))end
local function game_redraw(h,index,kind,code)
    local slot=h.slots[index].address
    W.write(slot+HS.type,W.u32(kind));W.write(slot+HS.displayedType,W.u32(kind))
    local SP=require('hd2runtime/domains/stratagem_calldown').hud.sprites
    for number=0,SP.count-1 do
        local sprite=slot+SP.offset+number*SP.stride
        local cell=code[number+1]
        W.write(sprite,W.u32(cell and 0x000C1051 or 0x000C1043))
        W.write(sprite+SP.region,unhex(W.HUD_CELLS[cell or 0][1]))
        W.write(sprite+SP.derived,unhex(W.HUD_CELLS[cell or 0][2]))
    end
end
-- Another stratagem's code (a mission objective's, say): its row pointed at a new array (fixture memory, not a Runtime
-- write).
local function set_code(kind,code)
    local array=W.alloc(64)
    local bytes={}
    for k,v in ipairs(code)do bytes[k]=W.u32(v)end
    W.write(array,table.concat(bytes))
    W.write(ROW[kind]+0x40,W.u64(array));W.write(ROW[kind]+0x48,W.u32(#code))
end
local function code_at(kind)
    local n=string.byte(W.read(ROW[kind]+0x48,1))
    local raw=W.read(ROW[kind]+0x40,8)
    local array=0
    for i=8,1,-1 do array=array*256+raw:byte(i)end
    local out={}
    for k=0,n-1 do out[k+1]=string.byte(W.read(array+k*4,1))end
    return table.concat(out,',')
end
local GAS_CODE='1,1,3,3'
local CODE_ROW={{0x40,0x4C}}
"""


class GasBarrageMissionProofTests(unittest.TestCase):
    def lua(self, body):
        from support import lua as lua_literal
        resource, wrapped = addon()
        self.assertEqual(resource, 'mods/skyeshade/hd2runtime_gas_barrage_mission_proof')
        self.assertEqual(run(WORLD + SLOT + 'local ADDON=' + lua_literal(wrapped) + '\nlocal RESOURCE='
            + lua_literal(resource) + PROOF + HARNESS + FLOW + body), b'ok')

    def test_the_build_discovers_its_carrier_and_gives_it_the_code_through_the_public_field(self):
        self.assertEqual((FOLDER / 'VERSION').read_text(encoding='utf-8').strip(), '0.5.0')
        self.assertEqual(json.loads((FOLDER / 'hd2runtime.json').read_text(encoding='utf-8'))['name'],
            'GasBarrageMissionProof')
        body = (FOLDER / 'src/addon.lua').read_text(encoding='utf-8-sig')
        self.assertIn("local BUILD='0.5.0 CUSTOM CALLDOWN'", body)
        code = '\n'.join(line.split('--')[0] for line in body.splitlines())
        self.assertIn('mission={discover=true,exclude={DONOR}}', code)
        self.assertIn('selector.discover_carrier(GAS.id,present_set)', code)
        for named in ('Napalm', '380mm', 'Walking', 'Airburst', 'Gatling', 'CARRIERS='):
            self.assertNotIn(named, code)
        self.assertEqual(code.count('selector.convert_virtual('), 1)
        self.assertEqual(code.count('presentation.apply_text('), 1)
        # Two public ensures, both on the discovered carrier: its icon and its code (never acknowledged).
        self.assertEqual(code.count('hd2.ensure('), 2)
        self.assertEqual(code.count('target=hd2.stratagem(c.name)'), 2)
        self.assertEqual(code.count('hd2.fields.stratagem.calldown_code'), 1)
        self.assertIn("local CODE={'up','up','down','down'}", code)
        self.assertIn('expect=calldown.names(native_now),value=CODE},enabled=code_on', code)
        self.assertIn('presentation.apply_text({carrier=carrier.name,', code)
        # The only other write path: the conversion's own guarded restore when a related entry appears mid-mission.
        self.assertEqual(code.count('slots.restore('), 1)
        self.assertIn('slots.restore(unconverted)', code)
        for forbidden in ('hd2.stratagem(TOKEN)', 'hd2.stratagem(DONOR)', 'carrier=TOKEN', 'carrier=DONOR',
                'allow_unverified', 'calldown.array(', 'slots.convert(', 'slot_icons',
                'hd2.patch(', 'hd2.transaction(', 'hd2.plan(', '.write(', 'owned_write', 'transaction.apply',
                'presentation_name', 'presentation_description', 'payload', 'stratagem_hud.refresh',
                'calldown.check_now'):
            self.assertNotIn(forbidden, code)
        self.assertEqual(sorted(p.name for p in (FOLDER / 'images').iterdir()), ['orbital_gas_barrage_masks.png'])
        self.assertTrue((FOLDER / 'source/orbital_gas_barrage.png').is_file())

    def test_the_discovered_carrier_takes_the_virtual_slot_with_its_own_call_in_and_back(self):
        self.lua(r'''
rawset(_G,'ModOptionsMenu',MENU)
proof()
tick(40)
assert(count('GasBarrageMissionProof 0.5.0 CUSTOM CALLDOWN BUILD')==1)
-- SHIP: [GAS, three native stratagems]; nothing is discovered before the virtual slot is saved.
ship({})
tick(4)
select_into(0)
native_append(41);native_append(22);native_append(130)
SCREEN.set('selecting',false);tick(8)
SCREEN.close();tick(4)
assert(count('CARRIER CANDIDATE: ')==0 and count('SELECTED: the first of')==0,'no discovery before the save')
W.saved_loadout({{id=PRECISION_ID},{id=3193297673},{id=ID22},{id=1298599997}})
tick(80)
-- Every candidate logged with its checks; the donor excluded; the first eligible one SELECTED.
assert(count('CARRIER CANDIDATE: Orbital Napalm Barrage (type 106, stable id 2902516083, orbital/'
    ..'BombardmentComponentData): owned=true selectable=true enabled=true unlimited=true in_loadout=false '
    ..'special_case=false package_available=true presentation=true code=true -> SELECTED')==1,table.concat(logged,' | '))
assert(count('CARRIER CANDIDATE: Orbital 120mm HE Barrage (type 136, stable id 1063322614, orbital/'
    ..'BombardmentComponentData): owned=true selectable=true enabled=true unlimited=true in_loadout=false '
    ..'special_case=false package_available=true presentation=true code=true -> rejected: excluded (Orbital 120mm HE '
    ..'Barrage: the donor, not a carrier)')==1)
assert(count('CARRIER CANDIDATE: Orbital Gas Strike (type 41, stable id 3193297673, orbital/BombardmentComponentData): '
    ..'owned=false (not in the catalogue range')==1 and count('in_loadout=true')>=1)
assert(count('CARRIER: Orbital Napalm Barrage (type 106, stable id 2902516083, orbital/BombardmentComponentData) '
    ..'SELECTED: the first of 1 eligible carriers (orbital bombardments first); owned, not in the saved loadout, not the '
    ..'donor; its native code: right right down left right up; the donor Orbital 120mm HE Barrage is not written. Do NOT '
    ..'select Orbital Napalm Barrage natively: while this proof runs its own card presents as Orbital Gas Barrage and '
    ..'answers to up up down down')==1,table.concat(logged,' | '))
-- The code: the carrier's native code read from its row first, checked against every native code, then applied
-- through the public field on the carrier only.
assert(count('CODE CHECK: the Gas Barrage code up up down down for the carrier Orbital Napalm Barrage (stable id '
    ..'2902516083): its native code read from its row first: right right down left right up (the reviewed native code: '
    ..'right right down left right up; equal: true); native codes equal to it or related to a selectable stratagem: '
    ..'none; mission-only stratagems related to it: ')==1,table.concat(logged,' | '))
assert(count('DropoffCargoContainer (up up down down right down, mission only) starts with it')==1
    and count('MobileCommsRelay (up up down down right right down, mission only) starts with it')==1
    and count('CallInDestroyer (up up down down left right left right, mission only) starts with it')==1
    and count('(guarded: a mission record holding one refuses the conversion) -> SAFE: applying it')==1,
    table.concat(logged,' | '))
assert(count('PRESENTATION: the carrier Orbital Napalm Barrage text APPLIED aboard the ship: its row holds the Gas '
    ..'Barrage text and the Gas Barrage icon')==1,table.concat(logged,' | '))
assert(count('CODE: the carrier Orbital Napalm Barrage code (public calldown_code ensure): ')>=1
    and count('the carrier row holds the Gas Barrage code (up up down down); Orbital Precision Strike presentation '
    ..'native = true, code native = true; donor Orbital 120mm HE Barrage presentation native = true, code native = '
    ..'true')>=1,table.concat(logged,' | '))
assert(code_at(106)==GAS_CODE and W.read(ROW106+0xB0,8)==CUSTOM)
assert(W.read(ROW118,400)==PRECISION_ROW and W.read(ROW136,400)==DONOR_ROW,'the token and the donor never written')
assert(count('PRE-MISSION CHECK: virtual Gas Barrage slots = 1 (loadout slot 0); saved tokens = Orbital Precision '
    ..'Strike; ')>=1 and count('carrier = Orbital Napalm Barrage (stable id 2902516083); carrier present in saved '
    ..'loadout = false; 120mm present in saved loadout = false; saved order matches the virtual identity = true '
    ..'(reconstructed: 1 slot); Orbital Precision Strike presentation native = true, code native = true; donor Orbital '
    ..'120mm HE Barrage presentation native = true, code native = true; the carrier row holds the Gas Barrage text and '
    ..'the Gas Barrage icon and the Gas Barrage code (up up down down); the Gas Barrage code against the saved loadout: '
    ..'no conflict -> READY: start a solo mission')==1,table.concat(logged,' | '))
-- MISSION: only the virtual slot becomes the carrier, after its package is requested and loaded.
local writes=#W.runtime.writes
mission({host=true})
local record,hud=mission_record({118,41,22,130})
local h=W.stratagem_hud({peer=LOCAL,slots=hud,record=record})
tick(64)
assert(count('CODE CHECK: the Gas Barrage code up up down down against this mission record (')==1
    and count('no entry has an equal code, a code that starts with it or a code that is its start')==1,
    table.concat(logged,' | '))
assert(requested==1 and count('MISSION START: conversion APPLIED: loadout slot 0 = record entry 2 -> the carrier '
    ..'Orbital Napalm Barrage (type 106, stable id 2902516083; its own type and stable id, unchanged); carrier package '
    ..'loaded (')==1,table.concat(logged,' | '))
assert(count('CODE: the carrier Orbital Napalm Barrage row holds the Gas Barrage code (up up down down) (its native '
    ..'code: right right down left right up); Orbital Precision Strike presentation native = true, code native = true')
    ==1,table.concat(logged,' | '))
assert(count('1 writes; every other record entry and the count unchanged: true')==1)
assert(entry_type(h,2)==106 and entry_type(h,3)==41 and entry_type(h,4)==22 and entry_type(h,5)==130)
assert(entry_type(h,0)==124 and entry_type(h,1)==33 and entry_type(h,6)==41 and#W.runtime.writes==writes+1)
assert(count("IDENTITY: loadout slot 0 = orbital_gas_barrage (the Runtime's record: kept) is record entry 2, now "
    ..'Orbital Napalm Barrage (type 106, stable id 2902516083)')==1)
-- HUD: the game rebuilds the converted slot from the carrier's row (offline: written as the game would), arrows included.
game_redraw(h,2,106,{1,1,3,3})
W.write(h.slots[2].address+OV.widget+OV.hudIcon+SEL.slotIcon.name,CUSTOM)
tick(8)
assert(count('HUD: HUD slot 2 (loadout slot 0, record entry 2): Orbital Napalm Barrage (type 106, stable id '
    ..'2902516083); icon element shows the Gas Barrage icon; its arrows draw up up down down; the carrier row holds the '
    ..'Gas Barrage text and the Gas Barrage icon and the Gas Barrage code (up up down down); its text shows: name '
    ..'"ORBITAL GAS BARRAGE"')==1,table.concat(logged,' | '))
-- CALL-IN with the Gas Barrage code: the carrier's own call-in.
W.call_ins({{key=W.RECORD_KEY,slot=2,done=0}})
tick(4)
assert(count('CALL-IN: the virtual Gas Barrage slot (loadout slot 0, record entry 2) was called: a call-in of Orbital '
    ..'Napalm Barrage (type 106, stable id 2902516083) is in flight (the game\'s own beacon); the carrier row holds the '
    ..'Gas Barrage code (up up down down), the only code that calls it')==1,table.concat(logged,' | '))
assert(count('CODE CONFLICT')==0)
-- MISSION END: the game rebuilds the record for the ship; the conversion is gone; the identity is reconstructed.
W.call_ins({})
for k,kind in ipairs({130,22,41,118})do W.write(h.record+0x38+0x188+(k-1)*0x30,W.u32(kind))end
W.write(h.record+0x38+0x788,W.u32(4))
tick(4)
assert(count('stratagem slot entry 2 no longer holds Orbital Napalm Barrage')==1,table.concat(logged,' | '))
W.state(3)
tick(12)
assert(count('MISSION END: state Ship; conversion gone: the game rebuilt the record (see "no longer hold"); the '
    ..'carrier row holds the Gas Barrage code (up up down down)')==1,table.concat(logged,' | '))
assert(count('saved order matches the virtual identity = true (reconstructed: 1 slot)')>=2)
assert(W.read(ROW118,400)==PRECISION_ROW and W.read(ROW136,400)==DONOR_ROW)
assert(untouched(ROW106,CARRIER_ROW,{{0x28,0x34},{0xB0,0xB8},{0x40,0x4C}}),'the carrier row beyond its look and code')
assert(#W.runtime.writes==writes+1 and count('stratagem slot RESTORED')==0 and count('callback failed')==0)
-- Afterwards: the code toggle off restores the carrier's native code (pointer first: the count grows), nothing else.
callbacks['gas_barrage_mission_proof.code'](false,'gas_barrage_mission_proof.code')
tick(30)
assert(code_at(106)=='2,2,3,4,2,1' and untouched(ROW106,CARRIER_ROW,{{0x28,0x34},{0xB0,0xB8}}),
    'the native code back exactly')
assert(count('the carrier row holds its native code (right right down left right up)')>=1,table.concat(logged,' | '))
assert(#W.runtime.writes==writes+3 and W.read(ROW118,400)==PRECISION_ROW and W.read(ROW136,400)==DONOR_ROW)
done()
return 'ok'
''')

    def test_nothing_is_trusted_until_the_catalogue_shows_the_token_owned(self):
        self.lua(r'''
rawset(_G,'ModOptionsMenu',MENU)
proof()
tick(40)
ship({})
tick(4)
select_into(0)
native_append(22)
SCREEN.close();tick(4)
-- The account catalogue not filled (yet): even the token reads "not owned".
W.catalogue({[BIG_ID]=2,[NAPALM_ID]=2})
W.saved_loadout({{id=PRECISION_ID},{id=ID22}})
tick(40)
assert(count('CARRIER: waiting: the account catalogue does not show the token Orbital Precision Strike as owned yet')==1,
    table.concat(logged,' | '))
assert(count('CARRIER CANDIDATE: ')==0 and count('SELECTED: the first of')==0 and W.read(ROW106,400)==CARRIER_ROW,
    'nothing chosen')
-- Filled: the discovery runs and chooses.
W.catalogue({[PRECISION_ID]=2,[BIG_ID]=2,[NAPALM_ID]=2})
tick(80)
assert(count('CARRIER: Orbital Napalm Barrage (type 106')==1 and count('-> READY: start a solo mission')==1,
    table.concat(logged,' | '))
done()
return 'ok'
''')

    def test_only_the_virtual_precision_strike_becomes_the_carrier(self):
        self.lua(r'''
rawset(_G,'ModOptionsMenu',MENU)
proof()
tick(40)
-- [GAS, a NATIVE Precision Strike, two others]
ship({})
tick(4)
select_into(0)
native_append(118);native_append(22);native_append(130)
tick(8)
SCREEN.close();tick(4)
W.saved_loadout({{id=PRECISION_ID},{id=PRECISION_ID},{id=ID22},{id=1298599997}})
tick(80)
assert(count('-> READY: start a solo mission')==1,table.concat(logged,' | '))
local writes=#W.runtime.writes
mission({host=true})
local record,hud=mission_record({118,118,22,130})
local h=W.stratagem_hud({peer=LOCAL,slots=hud,record=record})
tick(64)
assert(entry_type(h,2)==106 and entry_type(h,3)==118,'the virtual one is the carrier, the native one a Precision Strike')
assert(entry_type(h,4)==22 and entry_type(h,5)==130 and#W.runtime.writes==writes+1)
assert(W.read(ROW118,400)==PRECISION_ROW,'the native Precision Strike stays vanilla')
done()
return 'ok'
''')

    def test_the_carrier_in_the_loadout_refuses_the_test(self):
        self.lua(r'''
rawset(_G,'ModOptionsMenu',MENU)
proof()
tick(40)
ship({})
tick(4)
select_into(0)
native_append(22)
tick(8)
SCREEN.close();tick(4)
W.saved_loadout({{id=PRECISION_ID},{id=ID22}})
tick(80)
assert(count('CARRIER: Orbital Napalm Barrage (type 106')==1)
-- The player then picks the carrier natively (it looks like Orbital Gas Barrage while the proof runs).
W.saved_loadout({{id=PRECISION_ID},{id=ID22},{id=NAPALM_ID}})
tick(8)
assert(count('carrier present in saved loadout = true')==1 and count('NOT READY: TEST REFUSED: the carrier Orbital '
    ..'Napalm Barrage is in the saved loadout')==1,table.concat(logged,' | '))
local writes=#W.runtime.writes
mission({host=true})
local record,hud=mission_record({118,22,106})
local h=W.stratagem_hud({peer=LOCAL,slots=hud,record=record})
tick(64)
assert(count('MISSION START: TEST REFUSED (nothing converted, nothing written): the carrier Orbital Napalm Barrage is '
    ..'in the saved loadout')==1,table.concat(logged,' | '))
assert(#W.runtime.writes==writes and entry_type(h,2)==118 and entry_type(h,4)==106 and requested==0)
done()
return 'ok'
''')

    def test_no_eligible_carrier_refuses_safely(self):
        self.lua(r'''
rawset(_G,'ModOptionsMenu',MENU)
proof()
tick(40)
-- The player already has the only eligible carrier in the loadout.
ship({})
tick(4)
select_into(0)
native_append(106)
tick(8)
SCREEN.close();tick(4)
W.saved_loadout({{id=PRECISION_ID},{id=NAPALM_ID}})
tick(80)
assert(count('CARRIER CANDIDATE: Orbital Napalm Barrage (type 106')==1 and count('in_loadout=true')>=1
    and count('CARRIER: none eligible (')==1 and count('carrier = nil; the test refuses safely')==1,
    table.concat(logged,' | '))
assert(W.read(ROW106,400)==CARRIER_ROW and W.read(ROW118,400)==PRECISION_ROW and W.read(ROW136,400)==DONOR_ROW,
    'no presentation written anywhere')
local writes=#W.runtime.writes
mission({host=true})
local record,hud=mission_record({118,106})
local h=W.stratagem_hud({peer=LOCAL,slots=hud,record=record})
tick(64)
assert(count('MISSION START: TEST REFUSED (nothing converted, nothing written): no carrier was chosen aboard the '
    ..'ship')==1,table.concat(logged,' | '))
assert(#W.runtime.writes==writes)
done()
return 'ok'
''')

    def test_a_failed_guard_writes_nothing_and_the_mission_goes_on(self):
        self.lua(r'''
rawset(_G,'ModOptionsMenu',MENU)
proof()
tick(40)
ship({})
tick(4)
select_into(0)
native_append(22)
tick(8)
SCREEN.close();tick(4)
W.saved_loadout({{id=PRECISION_ID},{id=ID22}})
tick(80)
-- The mission loadout is not the recorded order (another stratagem in slot 1): never another slot.
local writes=#W.runtime.writes
mission({host=true})
local record,hud=mission_record({118,130})
local h=W.stratagem_hud({peer=LOCAL,slots=hud,record=record})
tick(64)
assert(count('MISSION START: conversion REFUSED (nothing written; the mission goes on normally): IDENTITY_CHANGED: '
    ..'loadout slot 1 holds')==1,table.concat(logged,' | '))
assert(#W.runtime.writes==writes and entry_type(h,2)==118 and entry_type(h,3)==130)
done()
return 'ok'
''')

    def test_a_saved_stratagem_whose_code_relates_refuses_the_test(self):
        self.lua(r'''
rawset(_G,'ModOptionsMenu',MENU)
proof()
tick(40)
ship({})
tick(4)
select_into(0)
native_append(22)
tick(8)
SCREEN.close();tick(4)
-- The other saved stratagem's code starts with the Gas Barrage code.
set_code(22,{1,1,3,3,2,3})
W.saved_loadout({{id=PRECISION_ID},{id=ID22}})
tick(80)
assert(count('-> SAFE: applying it')==1 and code_at(106)==GAS_CODE)
assert(count('the Gas Barrage code against the saved loadout: FX-12 Shield Generator Relay (up up down down right down) '
    ..'starts with it -> NOT READY: TEST REFUSED: the Gas Barrage code up up down down conflicts with your loadout')==1,
    table.concat(logged,' | '))
local writes=#W.runtime.writes
mission({host=true})
local record,hud=mission_record({118,22})
local h=W.stratagem_hud({peer=LOCAL,slots=hud,record=record})
tick(64)
assert(count('MISSION START: TEST REFUSED (nothing converted, nothing written): the Gas Barrage code up up down down '
    ..'conflicts with this mission record: record entry 3 FX-12 Shield Generator Relay (type 22, up up down down right '
    ..'down) starts with it')==1,table.concat(logged,' | '))
assert(#W.runtime.writes==writes and entry_type(h,2)==118 and requested==0)
done()
return 'ok'
''')

    def test_a_mission_granted_stratagem_whose_code_relates_refuses_the_conversion(self):
        self.lua(r'''
rawset(_G,'ModOptionsMenu',MENU)
proof()
tick(40)
ship({})
tick(4)
select_into(0)
native_append(22)
tick(8)
SCREEN.close();tick(4)
W.saved_loadout({{id=PRECISION_ID},{id=ID22}})
tick(80)
assert(count('-> READY: start a solo mission')==1,table.concat(logged,' | '))
-- The mission grants a stratagem (here type 130, granted) whose code starts with the Gas Barrage code.
set_code(130,{1,1,3,3,4,2,4,2})
local writes=#W.runtime.writes
mission({host=true})
local record={{type=124,uses=-1,granted=1},{type=33,uses=-1,granted=1},{type=118,uses=-1,granted=0},
    {type=22,uses=-1,granted=0},{type=130,uses=-1,granted=1}}
local hud={}
for k,e in ipairs(record)do hud[k]={type=e.type,code={}}end
local h=W.stratagem_hud({peer=LOCAL,slots=hud,record=record})
tick(64)
assert(count('MISSION START: TEST REFUSED (nothing converted, nothing written): the Gas Barrage code up up down down '
    ..'conflicts with this mission record: record entry 4 GR-8 Recoilless Rifle (type 130, up up down down left right '
    ..'left right) starts with it')==1,table.concat(logged,' | '))
assert(#W.runtime.writes==writes and entry_type(h,2)==118 and requested==0)
done()
return 'ok'
''')

    def test_a_related_stratagem_granted_later_is_reported_and_nothing_changes(self):
        self.lua(r'''
rawset(_G,'ModOptionsMenu',MENU)
proof()
tick(40)
ship({})
tick(4)
select_into(0)
native_append(22)
tick(8)
SCREEN.close();tick(4)
W.saved_loadout({{id=PRECISION_ID},{id=ID22}})
tick(80)
local writes=#W.runtime.writes
mission({host=true})
local record,hud=mission_record({118,22})
local h=W.stratagem_hud({peer=LOCAL,slots=hud,record=record})
tick(64)
assert(entry_type(h,2)==106 and#W.runtime.writes==writes+1,table.concat(logged,' | '))
-- Later the record holds an objective stratagem whose code starts with the Gas Barrage code (the mission comms relay).
W.write(h.record+0x38+0x188+5*0x30,W.u32(102));W.write(h.record+0x38+0x188+5*0x30+9,string.char(1))
W.write(h.record+0x38+0x788,W.u32(6))
tick(4)
assert(count('CODE CONFLICT: the mission record now holds record entry 5 MobileCommsRelay (type 102, up up down down '
    ..'right right down) starts with it; the carrier answers to up up down down and the game would select it first: '
    ..'returning the virtual slot to its token')==1,table.concat(logged,' | '))
tick(8)
-- The conversion's own guarded restore: the slot holds the token again (1 write); the code stays on the carrier row.
assert(count('CODE CONFLICT: the virtual slot returned to its token Orbital Precision Strike (1 write, exact: true): the '
    ..'related stratagem stays callable')==1,table.concat(logged,' | '))
assert(entry_type(h,2)==118 and entry_type(h,5)==102 and#W.runtime.writes==writes+2 and code_at(106)==GAS_CODE)
tick(8)
assert(count('CODE CONFLICT: the mission record now holds')==1 and count('returned to its token')==1,'once')
done()
return 'ok'
''')

    def test_a_code_equal_to_a_native_code_is_never_applied(self):
        self.lua(r'''
-- Suppose another stratagem's reviewed native code were UP UP DOWN DOWN: the code is refused, never acknowledged.
require('hd2runtime/domains/stratagem_calldown').nativeCodes['1298599997']={1,1,3,3}
rawset(_G,'ModOptionsMenu',MENU)
proof()
tick(40)
ship({})
tick(4)
select_into(0)
native_append(22)
tick(8)
SCREEN.close();tick(4)
W.saved_loadout({{id=PRECISION_ID},{id=ID22}})
tick(80)
assert(count('native codes equal to it or related to a selectable stratagem: GR-8 Recoilless Rifle (up up down down, '
    ..'mission only) is EQUAL to it')==1,table.concat(logged,' | '))
assert(count('-> REFUSED: the code is not applied')==1 and count('CODE: the carrier')==0)
assert(code_at(106)=='2,2,3,4,2,1','the carrier keeps its native code')
assert(count('NOT READY: the Gas Barrage code was refused (see CODE CHECK)')==1,table.concat(logged,' | '))
done()
return 'ok'
''')

    def test_a_code_related_to_a_selectable_stratagem_is_never_applied(self):
        self.lua(r'''
-- Suppose a stratagem a player can select had a code that starts with UP UP DOWN DOWN: refused at registration.
require('hd2runtime/domains/stratagem_calldown').nativeCodes['1298599997']={1,1,3,3,2}
rawset(_G,'ModOptionsMenu',MENU)
proof()
tick(40)
W.write(ROW[130]+0x80,W.u32(2))
ship({})
tick(4)
select_into(0)
native_append(22)
tick(8)
SCREEN.close();tick(4)
W.saved_loadout({{id=PRECISION_ID},{id=ID22}})
tick(80)
assert(count('native codes equal to it or related to a selectable stratagem: GR-8 Recoilless Rifle (up up down down '
    ..'right, selectable) starts with it')==1 and count('-> REFUSED: the code is not applied')==1,
    table.concat(logged,' | '))
assert(code_at(106)=='2,2,3,4,2,1' and count('CODE: the carrier')==0)
done()
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
