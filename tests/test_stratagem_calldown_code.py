"""hd2.fields.stratagem.calldown_code (docs/stratagem-calldown-code.md): the calldown code as a guarded stratagem field
through patch, transaction, plan and ensure, its Runtime-owned arrays, and the automatic HUD redraw of only the
stratagem's own slot, on the offline event world (a StratagemSettings buffer whose rows match the catalogue's reviewed
roots, and a HUD stratagem list built from the real HUD's bytes). Nothing here touches a game process."""
import json
import unittest

from support import ROOT, lua, run
from test_event_scripting import PRELUDE, SDK

WORLD = PRELUDE + r'''
local b=require('hd2runtime/core/bytes')
local calldown=require('hd2runtime/runtime/calldown_codes')
local H=require('hd2runtime/domains/stratagem_calldown').hud
local SP=H.sprites
local ensure_api=require('hd2runtime/api/ensure')
local scheduler=require('hd2runtime/runtime/scheduler')
calldown.reset_for_tests()
W.guarded_runtime()
-- Three catalogued stratagems at their reviewed roots (id, package, group, row, payloads), with their native codes.
local NATIVE={[136]={2,2,3,4,2,3},[118]={2,2,1},[22]={3,3,4,2,4,2},[130]={3,4,2,2,4},[41]={2,2,3,2}}
-- Every row carries its reviewed native presentation (name, cased name, description, icon).
local presentation_module=require('hd2runtime/runtime/stratagem_presentation')
presentation_module.reset_for_tests()
local function pres(id)
    local v=require('hd2runtime/domains/stratagem_calldown').presentation.values[tostring(id)]
    return {[0x28]=W.u32(v.name),[0x2C]=W.u32(v.nameCased),[0x30]=W.u32(v.description),
        [0xB0]=presentation_module.encode('icon',v.icon)}
end
local settings=W.stratagem_settings({
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
})
world_module.set_runtime(W.runtime)
local ROW,ARRAY={},{}
for kind in pairs(NATIVE)do ROW[kind],ARRAY[kind]=settings.rows[kind].address,settings.rows[kind].sequence end
local BEFORE=W.read(settings.base,settings.size)
local session=require('hd2runtime/api/session').new(W.runtime,function(line)logged[#logged+1]=line end)
local F,COOLDOWN=session.fields.stratagem.calldown_code,session.fields.stratagem.definition_cooldown
local BIG,PRECISION,RELAY='Orbital 120mm HE Barrage','Orbital Precision Strike','FX-12 Shield Generator Relay'
local NAMES={[136]={'right','right','down','left','right','down'},[118]={'right','right','up'},
    [22]={'down','down','left','right','left','right'}}
local P0={'up','up','down','down'}
local function hexed(s)return(s:gsub('.',function(c)return string.format('%02x',c:byte())end))end
local function u32_at(at)return b.u32(W.read(at,4),0)end
local function pointer(at)return b.pointer(W.read(at,8),0)end
-- The code a row holds now, as direction names.
local function code(kind)
    local count=u32_at(ROW[kind]+0x48)
    local out={}
    for i=1,count do out[i]=calldown.DIRECTIONS[u32_at(pointer(ROW[kind]+0x40)+(i-1)*4)]end
    return table.concat(out,' ')
end
-- Offsets of settings bytes that differ from BEFORE.
local function changed()
    local now,out=W.read(settings.base,settings.size),{}
    for i=1,#now do if now:byte(i)~=BEFORE:byte(i)then out[#out+1]=i-1 end end
    return out
end
-- Run one operation to its end without ticking the global update (the HUD check runs only from idle()).
local function settle(op,limit)
    for _=1,limit or 400 do
        op.tick(0.125)
        if op.status=='complete'or op.status=='rejected'or op.status=='failed'then break end
    end
    return op
end
-- Tick the global update (the calldown HUD check runs every 0.25 s from it).
local function idle(n)for _=1,n or 8 do tick()end end
local function writes()return#W.runtime.writes end
-- The HUD list: slot 0 the Precision Strike, slot 1 the 120mm.
local HUD
local function hud(slots)
    HUD=W.stratagem_hud({peer=LOCAL,slots=slots or{{type=118,code=NATIVE[118]},{type=136,code=NATIVE[136]}}})
    return HUD
end
local function drawn(index)
    local out={}
    for _,at in ipairs(HUD.slots[index].sprites)do
        if math.floor(u32_at(at)/16)%2==1 then
            out[#out+1]=calldown.DIRECTIONS[math.floor(b.value(W.read(at+SP.region,4),0,'f32')/0.2+0.5)]
        end
    end
    return table.concat(out,' ')
end
local HUD_BEFORE
local function hud_snapshot()HUD_BEFORE=W.read(HUD.hud,0x400000)end
local function hud_changed()
    local now,out=W.read(HUD.hud,0x400000),{}
    for i=1,#now do if now:byte(i)~=HUD_BEFORE:byte(i)then out[#out+1]=HUD.hud+i-1 end end
    return out
end
'''


def lua_run(body):
    return run(WORLD + body)


class CalldownModelTests(unittest.TestCase):
    """The published field: one descriptor per call-in stratagem, its native baseline, its guards."""

    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT / 'sdk/StratagemAuthoringCapabilities.json').read_text())
        cls.research = json.loads((ROOT / 'research/stratagem-calldown-F5FEE03DCFDB.json').read_text())

    def test_every_call_in_stratagem_publishes_its_native_code(self):
        fields = [x for x in self.catalog['fieldInstances'] if x['semanticFieldId'] == 'stratagem.calldown_code']
        self.assertEqual(len(fields), 94)
        self.assertEqual(self.catalog['summary']['calldownWritable'], 94)
        names = ['up', 'right', 'down', 'left']
        by_id = {row['id']: [names[v - 1] for v in row['sequence']] for row in self.research['nativeRows']}
        internal = json.loads((ROOT / 'schemas/stratagem_authoring_catalog.json').read_text())['stratagems']
        for field in fields:
            name = field['target']['stratagem']
            self.assertTrue(field['editable'], name)
            self.assertEqual(field['currentDefault'], by_id[internal[name]['root']['id']], name)
            self.assertTrue(1 <= len(field['currentDefault']) <= 9)
            self.assertEqual((field['type'], field['minLength'], field['maxLength']), ('calldown_code', 1, 9))
            self.assertEqual(field['directions'], names)
            self.assertEqual(field['apiFieldConstant'], 'hd2.fields.stratagem.calldown_code')
            self.assertEqual(field['backingObjectKind'], 'StratagemDefinition')
            # 20: one consumer, never shared; no acknowledgement for the field itself.
            self.assertFalse(field['shared'] or field['allowSharedRequired'], name)
            self.assertNotIn('acknowledgement', field)
            self.assertTrue(field['hudSynchronization'] and field['acknowledgementRule'])
            # The same operation group as the cooldown: one transaction can change both.
            cooldown = [x for x in self.catalog['fieldInstances'] if x['semanticFieldId'] == 'stratagem.cooldown'
                and x['target'] == field['target']]
            self.assertEqual(cooldown[0]['operationGroup'], field['operationGroup'])
            # No native layout in the public contract.
            self.assertNotIn('backing', field)
        # 1: several types read their own native codes.
        by_name = {x['name']: x for x in self.catalog['stratagems']}
        self.assertEqual(by_name['Orbital 120mm HE Barrage']['calldownCapability']['value'],
            ['right', 'right', 'down', 'left', 'right', 'down'])
        self.assertEqual(by_name['Orbital Precision Strike']['calldownCapability']['value'], ['right', 'right', 'up'])
        self.assertEqual(by_name['FX-12 Shield Generator Relay']['calldownCapability']['value'],
            ['down', 'down', 'left', 'right', 'left', 'right'])
        self.assertEqual(by_name['Eagle Airstrike']['calldownCapability']['value'], ['up', 'right', 'down', 'right'])
        # Live evidence: only the tested target.
        proven = [x['target']['stratagem'] for x in fields if x.get('liveEvidence')]
        self.assertEqual(sorted(proven), ['GR-8 Recoilless Rifle', 'Orbital 120mm HE Barrage'])
        unavailable = [x['name'] for x in self.catalog['stratagems'] if not x['calldownCapability']['writable']]
        self.assertEqual(sorted(unavailable), ['CQC-72 Entrenchment Tool', 'SG-88 Break-Action Shotgun'])

    def test_validation_encodes_and_refuses(self):
        self.assertEqual(lua_run(r'''
-- 2: every direction both ways.
local values=assert(calldown.values({'up','right','down','left'}))
assert(table.concat(values,',')=='1,2,3,4'and table.concat(calldown.names(values),',')=='up,right,down,left')
assert(calldown.bytes(values)=='\1\0\0\0\2\0\0\0\3\0\0\0\4\0\0\0'..string.rep('\0',24))
assert(table.concat(calldown.decode('\4\0\0\0\1\0\0\0'),',')=='4,1')
-- How two codes relate for the matcher: equal, one the start of the other, or parting.
assert(calldown.relation({1,1,3,3},{1,1,3,3})=='equal'and calldown.relation({1,1,3,3},{1,1,3,3,2,3})=='prefix')
assert(calldown.relation({1,1,3,3,2,3},{1,1,3,3})=='extends'and calldown.relation({1,1,3,3},{1,1,3,2})==nil)
assert(calldown.relation({3,3,1,4},{3,3,1,4,2})=='prefix'and calldown.relation({2},{3})==nil)
-- Every reviewed native code related to UP UP DOWN DOWN: none equal; three mission objectives start with it.
local related={}
for _,r in ipairs(calldown.native_relations({1,1,3,3}))do related[#related+1]=r.relation..':'..calldown.key(r.values)end
table.sort(related)
assert(table.concat(related,' ')=='prefix:1,1,3,3,2,2,3 prefix:1,1,3,3,2,3 prefix:1,1,3,3,4,2,4,2',
    table.concat(related,' '))
assert(#calldown.native_relations({2,2,1})>=1 and#calldown.native_relations({2,2,1},{[3523620028]=true})
    ==#calldown.native_relations({2,2,1})-1,'skip leaves a stable id out')
local function rejects(request,text)
    local ok,why=pcall(require('hd2runtime/domains/patches').validate,request)
    assert(not ok and tostring(why):find(text,1,true),text..' expected, got '..tostring(why))
end
local big=session.stratagem(BIG)
local spec=require('hd2runtime/domains/patches').validate{id='p0',target=big,field=F,expect=NAMES[136],value=P0}
assert(spec.changes[1].expected=='calldown:2,2,3,4,2,3'and spec.changes[1].desired=='calldown:1,1,3,3')
-- 3, 4: at most nine, only the four directions, a plain list.
rejects({id='a',target=big,field=F,expect=NAMES[136],value={'up','up','up','up','up','up','up','up','up','up'}},
    '1 to 9 directions')
rejects({id='b',target=big,field=F,expect=NAMES[136],value={}},'1 to 9 directions')
rejects({id='c',target=big,field=F,expect=NAMES[136],value={'up','north'}},'"up", "right", "down" or "left"')
rejects({id='d',target=big,field=F,expect=NAMES[136],value={'Up'}},'"up", "right", "down" or "left"')
rejects({id='e',target=big,field=F,expect=NAMES[136],value={1,1,3,3}},'"up", "right", "down" or "left"')
rejects({id='f',target=big,field=F,expect=NAMES[136],value='up up'},'list of 1 to 9')
rejects({id='g',target=big,field=F,expect=NAMES[136],value={'up',nil,'down'}},'list')
-- The expected code is the reviewed native one.
rejects({id='h',target=big,field=F,expect=P0,value=P0},'reviewed current value')
-- A code equal to another stratagem's native code needs allow_unverified_effect.
rejects({id='i',target=big,field=F,expect=NAMES[136],value={'right','right','up'}},
    'equals the native code of Orbital Precision Strike')
require('hd2runtime/domains/patches').validate{id='i',allow_unverified_effect=true,target=big,field=F,
    expect=NAMES[136],value={'right','right','up'}}
-- 20: shared-value protection is unchanged elsewhere.
local eagle=session.stratagem('Eagle Airstrike')
assert(not pcall(require('hd2runtime/domains/patches').validate,{id='r',target=eagle:eagle_rearm(),
    field=session.fields.eagle.rearm_time,expect=150,value=30}))
require('hd2runtime/domains/transactions').validate{id='both',target=big,changes={{field=F,expect=NAMES[136],value=P0},
    {field=COOLDOWN,expect=180,value=100}}}
return 'ok'
'''), b'ok')


class CalldownWriteTests(unittest.TestCase):
    """The row write: guards, exact bytes, arrays, transactions, plans and ensures (no HUD in these)."""

    def lua(self, body):
        self.assertEqual(lua_run(body), b'ok')

    def test_patch_writes_exactly_the_count_and_pointer_and_guards_the_original(self):
        self.lua(r'''
-- 5: the original pointer and count are guarded: a count, a pointer or a native code that differs is a conflict.
local function refused(mutate,restore,text)
    mutate()
    local op=settle(session.patch{id='g',target=session.stratagem(BIG),field=F,expect=NAMES[136],value=P0})
    restore()
    assert(op.status=='rejected'and tostring(op.error):find(text,1,true),text..': '..tostring(op.error))
end
refused(function()W.write(ROW[136]+0x48,W.u32(5))end,function()W.write(ROW[136]+0x48,W.u32(6))end,'CONFLICT')
refused(function()W.write(ROW[136]+0x40,W.u64(0x7000000))end,function()W.write(ROW[136]+0x40,W.u64(ARRAY[136]))end,
    'outside the StratagemSettings allocation')
refused(function()W.write(ARRAY[136],W.u32(1))end,function()W.write(ARRAY[136],W.u32(2))end,'CONFLICT')
assert(writes()==0 and#changed()==0)
-- 6: exactly two writes: the count (shrinking: first), then the pointer to the Runtime-owned array.
local op=settle(session.patch{id='p0',target=session.stratagem(BIG),field=F,expect=NAMES[136],value=P0})
assert(op.status=='complete',tostring(op.error))
assert(writes()==2 and W.runtime.writes[1].address==ROW[136]+0x48 and W.runtime.writes[1].bytes=='\4\0\0\0')
assert(W.runtime.writes[2].address==ROW[136]+0x40 and#W.runtime.writes[2].bytes==8)
local array=pointer(ROW[136]+0x40)
assert(calldown.owned(array,4)and W.read(array,40)=='\1\0\0\0\1\0\0\0\3\0\0\0\3\0\0\0'..string.rep('\0',24))
for _,offset in ipairs(changed())do
    assert(offset>=ROW[136]-settings.base+0x40 and offset<ROW[136]-settings.base+0x4C,'settings byte '..offset)
end
assert(code(136)=='up up down down'and code(118)=='right right up'and code(22)=='down down left right left right')
assert(W.read(ARRAY[136],24)==BEFORE:sub(ARRAY[136]-settings.base+1,ARRAY[136]-settings.base+24),'native array')
assert(count('stratagem.calldown_code {right, right, down, left, right, down} -> {up, up, down, down}')==1)
-- Again: already desired, nothing written.
op=settle(session.patch{id='p0b',target=session.stratagem(BIG),field=F,expect=NAMES[136],value=P0})
assert(op.status=='complete'and writes()==2)
-- A different code over a code this operation did not write is a conflict.
op=settle(session.patch{id='p0c',target=session.stratagem(BIG),field=F,expect=NAMES[136],value={'up','down'}})
assert(op.status=='rejected'and tostring(op.error):find('neither expected',1,true),tostring(op.error))
-- Growing (3 -> 7): the pointer first, then the count.
op=settle(session.patch{id='grow',target=session.stratagem(PRECISION),field=F,expect=NAMES[118],
    value={'up','down','up','down','left','right','left'}})
assert(op.status=='complete'and writes()==4)
assert(W.runtime.writes[3].address==ROW[118]+0x40 and W.runtime.writes[4].address==ROW[118]+0x48
    and W.runtime.writes[4].bytes=='\7\0\0\0')
assert(code(118)=='up down up down left right left')
return 'ok'
''')

    def test_arrays_are_one_per_code_immutable_and_outlive_their_adapter(self):
        self.lua(r'''
-- 7: one array per code, reused across operations and rows; its bytes never change; it keeps the adapter that
-- allocated it (each operation runs on its own adapter in game).
local op=settle(session.patch{id='a',target=session.stratagem(BIG),field=F,expect=NAMES[136],value=P0})
local array=pointer(ROW[136]+0x40)
op=settle(session.patch{id='b',target=session.stratagem(RELAY),field=F,expect=NAMES[22],value=P0})
assert(op.status=='complete'and pointer(ROW[22]+0x40)==array,'the same code shares one array')
assert(W.read(array,16)=='\1\0\0\0\1\0\0\0\3\0\0\0\3\0\0\0')
local blocks=0;for _ in pairs(W.runtime.owned)do blocks=blocks+1 end
assert(blocks==1)
-- An adapter that allocated an array is kept alive by it.
local weak=setmetatable({},{__mode='v'})
do
    local adapter={owned={},read=W.runtime.read}
    function adapter.owned_block(size)local at=W.runtime.owned_block(size);adapter.owned[at]=true;return at end
    function adapter.owned_write(at,bytes)return W.runtime.owned_write(at,bytes)end
    weak[1]=adapter
    calldown.array(adapter,{4,4,4})
end
collectgarbage('collect');collectgarbage('collect')
assert(weak[1]~=nil,'the array keeps its adapter')
return 'ok'
''')

    def test_transaction_and_plan(self):
        self.lua(r'''
-- 17: the code and the cooldown of one stratagem in one transaction (one operation group): three writes.
local op=settle(session.transaction{id='t',target=session.stratagem(BIG),changes={{field=F,expect=NAMES[136],value=P0},
    {field=COOLDOWN,expect=180,value=100}}})
assert(op.status=='complete'and writes()==3,tostring(op.error)..' '..writes())
assert(code(136)=='up up down down'and b.value(W.read(ROW[136]+104,4),0,'f32')==100)
-- 18: a plan over two stratagems.
op=settle(session.plan{id='pl',operations={
    {id='precision',target=session.stratagem(PRECISION),field=F,expect=NAMES[118],value={'left','left','left'}},
    {id='relay',target=session.stratagem(RELAY),changes={{field=F,expect=NAMES[22],value={'up','up'}},
        {field=COOLDOWN,expect=90,value=45}}}}})
assert(op.status=='complete',tostring(op.error))
assert(code(118)=='left left left'and code(22)=='up up'and code(136)=='up up down down')
-- Three directions to three: only the pointer changes. Six to two: count and pointer, and the cooldown.
assert(writes()==3+1+3,writes())
-- A plan that conflicts writes nothing at all.
local before=writes()
op=settle(session.plan{id='bad',operations={
    {id='ok',target=session.stratagem(BIG),field=COOLDOWN,expect=180,value=90},
    {id='stale',target=session.stratagem(PRECISION),field=F,expect=NAMES[118],value={'up','up','up'}}}})
assert(op.status=='rejected'and writes()==before,tostring(op.error))
return 'ok'
''')

    def test_unknown_build_refuses_safely(self):
        self.lua(r'''
-- 21: a changed calldown reader refuses the write (nothing written); the cooldown on the same build still works.
local pin=require('hd2runtime/domains/stratagem_calldown').pins[1]
W.write(W.GAME+pin.rva,string.char(0xCC))
local op=settle(session.patch{id='x',target=session.stratagem(BIG),field=F,expect=NAMES[136],value=P0})
assert(op.status=='rejected'and tostring(op.error):find('calldown code unavailable on this game build',1,true),
    tostring(op.error))
assert(writes()==0)
op=settle(session.patch{id='y',target=session.stratagem(BIG),field=COOLDOWN,expect=180,value=100})
assert(op.status=='complete'and writes()==1)
return 'ok'
''')


class CalldownHudTests(unittest.TestCase):
    """The HUD stays in step with the row: one redraw of only that stratagem's slot per change."""

    def lua(self, body):
        self.assertEqual(lua_run(body), b'ok')

    def test_apply_redraws_only_the_slot_with_the_live_verified_writes(self):
        self.lua(r'''
mission({host=true});hud();hud_snapshot()
local op=settle(session.patch{id='p0',target=session.stratagem(BIG),field=F,expect=NAMES[136],value=P0})
assert(op.status=='complete'and writes()==2)
idle(8)
-- 8, 9: the 120mm's slot (slot 1, found through the player's record) redrawn in exactly the live-verified 29 writes.
assert(drawn(1)=='up up down down'and drawn(0)=='right right up')
assert(writes()==2+29,writes())
assert(count('stratagem calldown Orbital 120mm HE Barrage: HUD slot 1 redrawn right right down left right down -> '
    ..'up up down down (29 writes, guard APPLIED)')==1)
local slot=HUD.slots[1]
local function sprite(i)return slot.sprites[i+1]end
local golden={}
for _,i in ipairs({0,1})do
    golden[sprite(i)+SP.region]='cdcc4c3e';golden[sprite(i)+SP.region+8]='cdcccc3e'
    golden[sprite(i)+SP.derived]='00902a3f';golden[sprite(i)+SP.derived+8]='00902e3f';golden[sprite(i)]='53100c00'
end
golden[sprite(3)+SP.region]='9a99193f';golden[sprite(3)+SP.region+8]='cdcc4c3f'
golden[sprite(3)+SP.derived]='0090323f';golden[sprite(3)+SP.derived+8]='0090363f';golden[sprite(3)]='53100c00'
-- 10: the arrows past the new count hidden.
for _,i in ipairs({4,5})do golden[sprite(i)]='65100c00';golden[sprite(i)+SP.mask]='00080000'end
-- 11: the layout parents marked up to the first that already had both bits.
for position=1,9 do golden[slot.ancestors[position]]=position==5 and'1d500400'or'1d100400'end
-- 12: the slot laid out again.
golden[slot.address+H.slots.relayout]='01'
for index=3,writes()do
    local item=W.runtime.writes[index]
    assert(golden[item.address]==hexed(item.bytes),string.format('HUD write %X %s',item.address,hexed(item.bytes)))
    golden[item.address]=nil
end
assert(next(golden)==nil,'every live-verified write happened')
-- 13: nothing else in the HUD: the other slot, the slot's type, displayed type, scrambler state, the record.
local first,last=slot.address+SP.offset,slot.address+SP.offset+SP.count*SP.stride
local allowed={[slot.address+H.slots.relayout]=true}
for position=1,9 do allowed[slot.ancestors[position]]=true end
for _,at in ipairs(hud_changed())do
    local word=at-(at-HUD.hud)%4
    assert((at>=first and at<last)or allowed[at]or allowed[word],string.format('HUD byte %X written',at))
end
assert(u32_at(slot.address+H.slots.type)==136 and u32_at(slot.address+H.slots.displayedType)==136)
-- 16: no continuous redraw.
idle(200)
assert(writes()==31,'one redraw per change')
assert(calldown.watching(),'the changed row stays watched (two reads every 0.25 s; no writes)')
return 'ok'
''')

    def test_a_refused_redraw_keeps_the_code_and_retries(self):
        self.lua(r'''
-- 14: the HUD differs from the research: the code is applied, the redraw refused (once), nothing written in the HUD.
mission({host=true});hud();hud_snapshot()
local odd=HUD.slots[1].sprites[3]+SP.flagParent
W.write(odd,W.u64(HUD.list))
local op=settle(session.patch{id='p0',target=session.stratagem(BIG),field=F,expect=NAMES[136],value=P0})
assert(op.status=='complete'and code(136)=='up up down down')
idle(40)
assert(writes()==2 and drawn(1)=='right right down left right down')
assert(count('stratagem calldown Orbital 120mm HE Barrage: calldown applied; HUD refresh refused: HUD_CHANGED')==1)
-- The structure as researched again: the next check redraws.
W.write(odd,W.u64(0));idle(4)
assert(drawn(1)=='up up down down'and writes()==31)
return 'ok'
''')

    def test_a_hud_the_research_does_not_cover_is_never_written(self):
        self.lua(r'''
-- 21: a changed HUD pin: the code applies, the redraw is refused (once) and not retried; the HUD is untouched.
mission({host=true});hud();hud_snapshot()
W.write(W.GAME+H.pins[1].rva,string.char(0xCC))
local op=settle(session.patch{id='p0',target=session.stratagem(BIG),field=F,expect=NAMES[136],value=P0})
assert(op.status=='complete'and code(136)=='up up down down')
idle(40)
assert(writes()==2 and#hud_changed()==0 and drawn(1)=='right right down left right down')
assert(count('calldown applied; HUD refresh refused: HUD_UNAVAILABLE')==1)
return 'ok'
''')

    def test_restore_ensure_and_option_toggle(self):
        self.lua(r'''
mission({host=true});hud()
local options=require('hd2runtime/api/options')
options.reset()
local page=session.options and session.options({id='calldown',title='Calldown'})or hd2.options({id='calldown',
    title='Calldown'})
local on=page:toggle({id='on',label='On',default=true})
local callbacks={}
rawset(_G,'ModOptionsMenu',{api=1,register_option=function()return true end,get=function()return nil end,
    on_change=function(id,fn)callbacks[id]=fn;return true end,ready=function()return true end})
local e=scheduler.attach(ensure_api.start(W.runtime,function(line)logged[#logged+1]=line end,{enabled=on,
    interval=1,startup_delay=0,patch={id='p0',target=session.stratagem(BIG),field=F,expect=NAMES[136],value=P0}}))
for _=1,60 do tick()end
assert(code(136)=='up up down down'and drawn(1)=='up up down down',code(136)..' / '..drawn(1))
local after_apply=writes()
assert(after_apply==31,after_apply)
-- 16: the ensure keeps it: something else writes the native code back; the ensure re-applies once, the slot is
-- redrawn once, and then nothing more.
W.write(ROW[136]+0x40,W.u64(ARRAY[136]));W.write(ROW[136]+0x48,W.u32(6))
for _=1,200 do tick()end
assert(code(136)=='up up down down'and drawn(1)=='up up down down')
local after_drift=writes()
assert(after_drift>after_apply)
for _=1,200 do tick()end
assert(writes()==after_drift,'no continuous rewrite or redraw')
-- 15: the option off restores the reviewed baseline: the native pointer and count, and the slot's original arrows.
callbacks['calldown.on'](false,'calldown.on')
for _=1,60 do tick()end
assert(code(136)=='right right down left right down'and drawn(1)=='right right down left right down',
    code(136)..' / '..drawn(1))
assert(pointer(ROW[136]+0x40)==ARRAY[136]and u32_at(ROW[136]+0x48)==6 and#changed()==0)
assert(count('restored the reviewed baseline and is disabled')==1)
-- The slot followed the row both times it went back to the native code: the third-party write and the restore.
assert(count('HUD slot 1 redrawn up up down down -> right right down left right down')==2)
return 'ok'
''')

    def test_two_stratagems_stay_independent_and_close_restores_both(self):
        self.lua(r'''
-- 19: two stratagems, two codes, two slots; restoring one leaves the other.
mission({host=true});hud()
settle(session.patch{id='a',target=session.stratagem(BIG),field=F,expect=NAMES[136],value=P0})
settle(session.patch{id='b',target=session.stratagem(PRECISION),field=F,expect=NAMES[118],value={'left','down'}})
idle(8)
assert(drawn(1)=='up up down down'and drawn(0)=='left down')
assert(count('HUD slot 1 redrawn')==1 and count('HUD slot 0 redrawn')==1)
-- The Lua state closes: every changed row is restored, then its slot.
calldown.finalize_for_tests()
assert(code(136)=='right right down left right down'and code(118)=='right right up'and#changed()==0)
assert(drawn(1)=='right right down left right down'and drawn(0)=='right right up')
return 'ok'
''')

    def test_a_check_between_planning_and_writing_still_redraws(self):
        self.lua(r'''
-- An operation may yield between planning its writes and making them; the HUD check can run in between, while the
-- row still holds its native code. The planned code is awaited, so the write is still seen and drawn.
mission({host=true});hud()
local domain=require('hd2runtime/domains/stratagem_writes')
local Reader=require('hd2runtime/runtime/reader')
local transaction=require('hd2runtime/core/guarded_transaction')
local function planned(name,expect,value)
    local spec=domain.validate_patch{id='race',target={resource='stratagem',stratagem=name,path='stratagem'},
        field='stratagem.calldown_code',expect=expect,value=value}
    local reader=Reader.new(W.runtime)
    return domain.prepare(domain.capture_many(W.runtime,reader,{spec})[1],reader,spec)
end
local plan=planned(BIG,NAMES[136],P0)
idle(20)
assert(calldown.watching()and writes()==0,'a planned write is awaited')
assert(transaction.apply(W.runtime,plan).status=='APPLIED')
idle(8)
assert(drawn(1)=='up up down down'and writes()==31,writes())
-- Undone by the transaction's own inverse: the slot follows back.
assert(transaction.apply(W.runtime,transaction.inverse(plan)).status=='APPLIED')
assert(code(136)=='right right down left right down')
idle(8)
assert(drawn(1)=='right right down left right down',drawn(1))
idle(8)
assert(not calldown.watching(),'native again and drawn: nothing to watch')
-- A planned write that never happens (refused, rejected) is awaited for PLAN_GRACE seconds at most.
planned(PRECISION,NAMES[118],{'left','down'})
tick(math.floor(calldown.PLAN_GRACE/0.125)-8)
assert(calldown.watching())
tick(16)
assert(not calldown.watching()and code(118)=='right right up'and drawn(0)=='right right up')
return 'ok'
''')

    def test_a_code_written_before_the_mission_needs_no_redraw(self):
        self.lua(r'''
-- Aboard the ship (no mission, no HUD): the code applies; the check waits.
local op=settle(session.patch{id='ship',target=session.stratagem(BIG),field=F,expect=NAMES[136],value=P0})
assert(op.status=='complete'and writes()==2)
idle(20)
assert(writes()==2)
-- The mission's list is built from the row, so it already draws the new code: confirmed, nothing written.
mission({host=true})
hud({{type=118,code=NATIVE[118]},{type=136,code={1,1,3,3}}})
idle(8)
assert(drawn(1)=='up up down down'and writes()==2 and count('redrawn')==0)
-- A stratagem not in the loadout: nothing to draw, nothing written.
op=settle(session.patch{id='relay',target=session.stratagem(RELAY),field=F,expect=NAMES[22],value={'up','up'}})
idle(8)
assert(writes()==4 and count('redrawn')==0)
return 'ok'
''')


def proof_addon():
    """The CustomStratagemP0Proof addon exactly as the SDK wraps it."""
    folder = ROOT / 'proof/CustomStratagemP0Proof'
    spec = json.loads((folder / 'hd2runtime.json').read_text(encoding='utf-8'))
    body = (folder / 'src/addon.lua').read_text(encoding='utf-8-sig')
    return spec['resource'], SDK.wrap_addon(spec['resource'], spec['requires']['hd2runtime']['min_version'], body)


# The proof addon on the offline world: hd2's write adapter is the fixture's, Mod Options Menu a stub whose on_change
# callbacks the test calls as the menu does on APPLY, and F9 a simulated key.
PROOF = r'''
package.loaded['hd2runtime/runtime/windows_write']={create=function()return W.runtime end}
local options=require('hd2runtime/api/options')
options.reset()
local callbacks={}
local MENU={api=1,register_option=function()return true end,get=function()return nil end,
    on_change=function(id,fn)callbacks[id]=fn;return true end,ready=function()return true end}
local input=require('hd2runtime/runtime/input')
local keys={}
input.set_backend({focused=function()return true end,down=function(code)return keys[code]==true end})
local function press(key)keys[input.keys[key]]=true;tick();keys[input.keys[key]]=false;tick()end
local function proof()assert(loadstring(ADDON,'@'..RESOURCE))()end
'''


class CustomTextProofAddonTests(unittest.TestCase):
    '''proof/CustomStratagemP0Proof 0.12.0: the custom text write proof. The 120mm's name, cased name and description
    become Runtime-owned text through the guarded development path (runtime/stratagem_presentation.lua apply_text); its
    icon (hd2.resources.image) and calldown code go through the public fields in one ensure; the toggles restore each
    exactly (docs/custom-text.md).'''

    IMAGE = "images.name('mods/skyeshade/hd2runtime_custom_stratagem_p0_proof','orbital_gas_barrage_icon')"

    def lua(self, body):
        resource, addon = proof_addon()
        self.assertEqual(resource, 'mods/skyeshade/hd2runtime_custom_stratagem_p0_proof')
        self.assertEqual(run(WORLD + 'local ADDON=' + lua(addon) + '\nlocal RESOURCE=' + lua(resource) + PROOF
            + "local images=require('hd2runtime/runtime/image_resources')\nimages.reset_for_tests()\n"
            + "local texts=require('hd2runtime/runtime/text_resources')\ntexts.reset_for_tests()\n"
            + 'local IMAGE=' + self.IMAGE + "\nlocal CONTROL={hash='0x9C9B3DCE316F1256'}\n"
            + "local FAMILY={textures={IMAGE},materials={IMAGE,CONTROL},sprites={{hash=CONTROL.hash}}}\n"
            + "local VANILLA={us={[0x4FAAD695]='ORBITAL 120MM HE BARRAGE',[0x628B5A83]='Orbital 120mm HE Barrage'}}\n"
            + body), b'ok')

    def test_the_build_uses_the_development_text_path_and_the_public_icon_and_code(self):
        import sys
        sys.path.insert(0, str(ROOT / 'scripts'))
        import hd2_image
        folder = ROOT / 'proof/CustomStratagemP0Proof'
        self.assertEqual((folder / 'VERSION').read_text(encoding='utf-8').strip(), '0.12.0')
        body = (folder / 'src/addon.lua').read_text(encoding='utf-8-sig')
        self.assertIn("local BUILD='0.12.0 CUSTOM-TEXT-WRITE'", body)
        code = '\n'.join(line.split('--')[0] for line in body.splitlines())
        self.assertEqual(code.count('presentation.apply_text('), 1)
        self.assertEqual(code.count('presentation.restore('), 1)
        self.assertEqual(code.count('hd2.ensure('), 1)
        self.assertEqual(code.count("hd2.resources.image('orbital_gas_barrage_icon')"), 1)
        for needed in ('hd2.fields.stratagem.presentation_icon', 'hd2.fields.stratagem.calldown_code',
                "value={'up','up','down','down'}"):
            self.assertIn(needed, code)
        for forbidden in ('hd2.patch(', 'hd2.transaction(', 'hd2.plan(', '.write(', 'owned_write', 'transaction.apply',
                'presentation.apply(', 'apply_icon', 'presentation_name', 'presentation_description',
                'CUSTOM-ICON-WRITE', 'READ-ONLY-FAMILY-PROBE BUILD'):
            self.assertNotIn(forbidden, code)
        self.assertEqual(sorted(p.name for p in (folder / 'images').iterdir()), ['orbital_gas_barrage_icon.png'])
        hd2_image.icon_texture((folder / 'images/orbital_gas_barrage_icon.png').read_bytes())

    def test_the_carrier_presents_as_the_gas_barrage_into_the_mission_and_is_restored_exactly(self):
        self.lua(r'''
rawset(_G,'ModOptionsMenu',MENU)
require('hd2runtime/runtime/stratagem_loadout').reset_for_tests()
W.icon_resources(FAMILY)
local reg=W.text_registry({tables={VANILLA,VANILLA},capacity=3})
W.saved_loadout({{id=3523620028},{id=2281932031}})
local ROW136=ROW[136]
local NATIVE_ROW=W.read(ROW136,400)
local h,l=images.hash(IMAGE)
local CUSTOM=W.u32(l)..W.u32(h)
proof()
tick(80)
assert(count('CustomStratagemP0Proof 0.12.0 CUSTOM-TEXT-WRITE BUILD')==1)
assert(count('  game text registry: 2 of 3 tables, 1 spare; current language us')==1)
assert(count('  TEXT PROBE RESULT: PASS: room for the Runtime text table, no id clash, a known language')==1)
-- The public ensure: the icon and the code. The development path: the text (2 registry writes, 3 members).
assert(count('custom icon and code (public ensure): waiting APPLIED')==1)
assert(count('[HD2Runtime] stratagem presentation custom text APPLIED: Orbital 120mm HE Barrage (type 136, stable id '
    ..'1063322614): name 0x4FAAD695 -> ')==1)
assert(count('"ORBITAL GAS BARRAGE"; nameCased 0x628B5A83 -> ')==1)
assert(count('"Calls down a barrage of gas shells."; 3 write; Runtime text table appended (table 3 of 3, language us); '
    ..'read back true; each resolves to exactly its text: true; identity unchanged: true; icon unchanged: true; other '
    ..'text members native: true; non-target bytes unchanged true; protection restored true')==1)
assert(count('custom text APPLIED aboard the ship: the 120mm row holds the Runtime text and the custom icon; its text '
    ..'shows: name "ORBITAL GAS BARRAGE", nameCased "Orbital Gas Barrage", description "Calls down a barrage of gas '
    ..'shells."')==1)
assert(W.read(ROW136+0xB0,8)==CUSTOM and code(136)=='up up down down'and reg.count()==3)
local now=W.read(ROW136,400)
for i=1,400 do
    local at=i-1
    assert(now:byte(i)==NATIVE_ROW:byte(i)or(at>=0x28 and at<0x34)or(at>=0x40 and at<0x4C)or(at>=0xB0 and at<0xB8),
        'row byte '..at..' changed')
end
local applied=writes()
-- Picked in the loadout screen; a solo mission: the slot draws the custom code already.
W.saved_loadout({{id=3523620028},{id=1063322614}})
tick(20)
assert(count('the 120mm row holds the Runtime text and the custom icon -> the 120mm is selected')==1)
mission({host=true});hud({{type=118,code=NATIVE[118]},{type=136,code={1,1,3,3}}})
tick(40)
assert(count('the 120mm is record entry 1: Orbital 120mm HE Barrage (type 136, stable id 1063322614), uses 0; its row '
    ..'holds the Runtime text and the custom icon; its text shows: name "ORBITAL GAS BARRAGE"')==1)
assert(count('HUD slot 1 draws record entry 1: Orbital 120mm HE Barrage (type 136, stable id 1063322614)')==1)
tick(200)
assert(writes()==applied,'no continuous rewrite')
press('F9')
assert(count('F9 [0.12.0 CUSTOM-TEXT-WRITE]: custom text applied (attempts 1), toggle on; icon and code ensure waiting '
    ..'APPLIED, toggle on; the 120mm row holds the Runtime text and the custom icon; language us, Runtime text table '
    ..'registered (table 3 of 3); mission true')==1)
-- Back aboard the ship: each toggle restores its own part exactly.
W.state(3);tick(4)
callbacks['custom_stratagem_proof.text'](false,'custom_stratagem_proof.text')
tick(20)
assert(count('RESTORED: Orbital 120mm HE Barrage presents as itself again: 3 writes; restored values read back exactly: '
    ..'true; name, cased name and description native: true; identity unchanged (type 136, stable id 1063322614): true; '
    ..'non-target bytes unchanged true; protection restored true; Runtime text table unregistered')==1)
assert(count('custom text RESTORED: the 120mm row holds its native text and the custom icon')==1 and reg.count()==2)
callbacks['custom_stratagem_proof.look'](false,'custom_stratagem_proof.look')
tick(40)
assert(count('ensure gas-barrage-look restored the reviewed baseline and is disabled')==1)
assert(W.read(ROW136,400)==NATIVE_ROW and code(136)=='right right down left right down')
assert(count('callback failed')==0)
return 'ok'
''')

    def test_a_language_change_registers_the_text_again(self):
        self.lua(r'''
rawset(_G,'ModOptionsMenu',MENU)
W.icon_resources(FAMILY)
local reg=W.text_registry({tables={VANILLA,VANILLA},capacity=3})
proof()
tick(80)
assert(count('custom text APPLIED aboard the ship')==1)
reg.set_language('fr')
reg.rebuild({{fr={[0x4FAAD695]='FRAPPE'}}})
tick(10)
assert(count('the game rebuilt its text registry (language us -> fr); Runtime text registered again (table 2 of 2)')==1)
assert(reg.count()==2 and count('custom text LOST')==0)
press('F9')
assert(count('language fr, Runtime text table registered (table 2 of 2)')==1)
return 'ok'
''')

    def test_no_spare_registry_capacity_refuses_the_text_with_nothing_written(self):
        self.lua(r'''
rawset(_G,'ModOptionsMenu',MENU)
W.icon_resources(FAMILY)
local reg=W.text_registry({tables={VANILLA,VANILLA},capacity=2})
local ROW136=ROW[136]
local NATIVE_TEXT=W.read(ROW136+0x28,12)
proof()
tick(80)
assert(count('  TEXT PROBE RESULT: FAIL: the custom text would be refused')==1)
assert(count("custom text REFUSED (nothing written): REGISTRY_FULL: the game's text registry has no spare capacity "
    ..'(2 of 2)')==1)
assert(W.read(ROW136+0x28,12)==NATIVE_TEXT and reg.count()==2 and#W.runtime.permanent==0)
-- The public icon and code still apply: they do not depend on the text.
assert(count('custom icon and code (public ensure): waiting APPLIED')==1 and code(136)=='up up down down')
return 'ok'
''')

    def test_without_mod_options_menu_nothing_is_applied(self):
        self.lua(r'''
rawset(_G,'ModOptionsMenu',nil)
W.icon_resources(FAMILY)
W.text_registry({tables={VANILLA,VANILLA},capacity=3})
proof()
tick(200)
assert(count('Mod Options Menu unavailable: nothing is applied')==1)
assert(count('custom text APPLIED aboard')==0 and writes()==0)
return 'ok'
''')

    def test_the_text_waits_for_the_registry_then_applies_with_the_same_guards(self):
        self.lua(r'''
rawset(_G,'ModOptionsMenu',MENU)
W.icon_resources(FAMILY)
proof()
tick(100)
assert(count('text probe not ready: the game has not registered its text yet')>=1 and count('custom text APPLIED aboard')==0)
W.text_registry({tables={VANILLA},capacity=2})
tick(80)
assert(count('  TEXT PROBE RESULT: PASS')==1 and count('custom text APPLIED aboard the ship')==1)
return 'ok'
''')


class LoadoutReaderTests(unittest.TestCase):
    '''runtime/stratagem_loadout.lua: the saved ship loadout and the mission record, read-only and fail-closed.'''

    def test_saved_loadout_record_and_refusals(self):
        self.assertEqual(lua_run(r'''
local loadout=require('hd2runtime/runtime/stratagem_loadout')
loadout.reset_for_tests()
local world=assert(world_module.open())
W.saved_loadout({{id=1063322614,uses=0xFFFFFFFF},{id=3523620028,uses=5},{id=0x7777}})
local saved=assert(loadout.saved(world))
assert(saved.saved and#saved.pairs==3)
assert(saved.pairs[1].type==136 and saved.pairs[2].type==118 and saved.pairs[2].uses==5)
assert(saved.pairs[3].type==nil,'an id no row carries resolves to nothing')
assert(loadout.type_of(world,1063322614)==136 and loadout.id_of(world,118)==3523620028)
-- Nothing saved yet (the store's flag): reported as such.
W.saved_loadout({},false)
assert(loadout.saved(world).saved==false)
-- The record, in a mission.
mission({host=true});hud()
local record=assert(loadout.record(world))
assert(#record==2 and record[1].type==118 and record[2].type==136 and record[2].id==1063322614 and record[2].index==1)
-- A changed save routine: refused, nothing read from the store.
local L=require('hd2runtime/domains/stratagem_calldown').loadout
loadout.reset_for_tests()
W.write(W.GAME+L.pins[1].rva,string.char(0xCC))
local none,code=loadout.saved(world)
assert(none==nil and code=='LOADOUT_UNAVAILABLE',tostring(code))
return 'ok'
'''), b'ok')

if __name__ == '__main__':
    unittest.main()
