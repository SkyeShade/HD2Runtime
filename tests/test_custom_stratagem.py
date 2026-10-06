"""Custom stratagem P0 (docs/custom-stratagems.md): a Runtime-owned calldown sequence on the vanilla Orbital 120mm HE
Barrage row, through the guarded transaction, on the offline fixture world. Nothing here touches a game process, and
nothing here shows what the HUD or the matcher do: that needs the live test. The P0 proof mod itself now tests the
public field (tests/test_stratagem_calldown_code.py, CalldownProofAddonTests); these cover the development module."""
import unittest

from support import run
from test_event_scripting import PRELUDE

WORLD = PRELUDE + r'''
local custom=require('hd2runtime/runtime/custom_stratagem')
local b=require('hd2runtime/core/bytes')
custom.reset_for_tests()
W.guarded_runtime()
local settings=W.stratagem_settings({
    {type=136,id=1063322614,package='0x25B8CFF26C7C0112',payload='0x2D3BD00B1ED411B1',sequence={2,2,3,4,2,3}},
    {type=71,id=1606251952,package='0x1111111111111111',payload='0x2222222222222222',sequence={1,1,3,3,2,3}},
})
world_module.set_runtime(W.runtime)
local ROW=settings.rows[136].address
local NEIGHBOUR=settings.rows[71].address
local ORIGINAL=settings.rows[136].sequence
local BEFORE=W.read(settings.base,settings.size)
local function settle(job)for _=1,50 do if job.status~='pending'then break end;tick()end;return job end
local function pointer(at)return b.pointer(W.read(at,8),0)end
local function u32_at(at)return b.u32(W.read(at,4),0)end
-- The settings bytes that differ from BEFORE, as offsets.
local function changed()
    local now,out=W.read(settings.base,settings.size),{}
    for i=1,#now do if now:byte(i)~=BEFORE:byte(i)then out[#out+1]=i-1 end end
    return out
end
'''


class SequenceEncodingTests(unittest.TestCase):
    def test_the_p0_sequence_is_four_u32_directions(self):
        self.assertEqual(run(WORLD + r'''
assert(custom.P0.stratagem=='Orbital 120mm HE Barrage')
local seq=custom.P0.sequence
assert(#seq==4 and seq[1]==1 and seq[2]==1 and seq[3]==3 and seq[4]==3)
local bytes=assert(custom.encode(seq))
assert(bytes=='\1\0\0\0\1\0\0\0\3\0\0\0\3\0\0\0'and#bytes==16)
assert(custom.names(seq)=='Up Up Down Down'and custom.names({2,2,3,4,2,3})=='Right Right Down Left Right Down')
assert(custom.decode(bytes)[4]==3)
-- 1 Up, 2 Right, 3 Down, 4 Left: nothing else, and 1 to 9 directions.
assert(custom.encode({})==nil and custom.encode({1,2,3,4,1,2,3,4,1,2})==nil and custom.encode({0})==nil
    and custom.encode({5})==nil and custom.encode({1.5})==nil and custom.encode({1,2,3,4,1,2,3,4,1})~=nil)
local domain=require('hd2runtime/domains/stratagem_calldown')
assert(domain.row.sequence==0x40 and domain.row.count==0x48 and domain.row.stride==400 and domain.maxLength==9)
assert(domain.directions.up==1 and domain.directions.right==2 and domain.directions.down==3 and domain.directions.left==4)
assert(domain.p0.nativeType==136 and domain.p0.id==1063322614 and#domain.pins==21)
return 'ok'
'''), b'ok')


class P0WriteTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(WORLD + body), b'ok')

    def test_apply_writes_only_the_pointer_and_count_and_restore_writes_the_originals_back(self):
        self.lua(r'''
mission({host=true})
local job=settle(custom.apply())
assert(job.status=='applied',tostring(job.code)..' '..tostring(job.reason))
-- The original pointer and count are preserved in the result and the state.
assert(job.original.pointer==ORIGINAL and job.original.count==6 and custom.names(job.original.sequence)
    =='Right Right Down Left Right Down')
assert(job.type==136 and job.id==1063322614)
-- Exactly two writes, the count first and then the pointer, through the guarded transaction.
local writes=W.runtime.writes
assert(#writes==2 and writes[1].address==ROW+0x48 and writes[1].bytes=='\4\0\0\0')
assert(writes[2].address==ROW+0x40 and#writes[2].bytes==8 and b.pointer(writes[2].bytes,0)==job.custom.pointer)
assert(job.report.status=='APPLIED'and job.report.non_target_bytes_unchanged and job.report.protection_restored)
-- The row points to a Runtime-owned block holding the sequence (and zeros up to its capacity).
local block=pointer(ROW+0x40)
assert(block==job.custom.pointer and u32_at(ROW+0x48)==4 and W.runtime.owned[block]==custom.CAPACITY*4)
assert(W.read(block,custom.CAPACITY*4)=='\1\0\0\0\1\0\0\0\3\0\0\0\3\0\0\0'..string.rep('\0',24))
-- No other StratagemSettings byte changed: only +0x40..+0x4B of the 120mm row.
for _,offset in ipairs(changed())do
    assert(offset>=ROW-settings.base+0x40 and offset<ROW-settings.base+0x4C,'byte '..offset..' changed')
end
assert(W.read(NEIGHBOUR,400)==BEFORE:sub(NEIGHBOUR-settings.base+1,NEIGHBOUR-settings.base+400))
-- The original array itself is never written.
assert(W.read(ORIGINAL,24)==BEFORE:sub(ORIGINAL-settings.base+1,ORIGINAL-settings.base+24))
local state=custom.state()
assert(state.applied and not state.restored and state.original.count==6 and state.custom.count==4)
-- Restore: the pointer first, then the count; afterwards the settings are byte-identical to before.
local restored=settle(custom.restore())
assert(restored.status=='restored',tostring(restored.code)..' '..tostring(restored.reason))
assert(#writes==4 and writes[3].address==ROW+0x40 and b.pointer(writes[3].bytes,0)==ORIGINAL)
assert(writes[4].address==ROW+0x48 and writes[4].bytes=='\6\0\0\0')
assert(#changed()==0 and custom.state().restored)
-- The block outlives the restore and is reused by the next apply (one allocation for the Lua state).
assert(W.read(block,16)=='\1\0\0\0\1\0\0\0\3\0\0\0\3\0\0\0')
local again=settle(custom.apply())
assert(again.status=='applied'and again.custom.pointer==block)
local blocks=0
for _ in pairs(W.runtime.owned)do blocks=blocks+1 end
assert(blocks==1,'one Runtime-owned block')
assert(settle(custom.restore()).status=='restored'and#changed()==0)
return 'ok'
''')

    def test_an_unexpected_original_is_refused_before_and_inside_the_guarded_write(self):
        self.lua(r'''
mission({host=true})
-- A count that is not the native one: the code no longer matches, nothing is written.
W.write(ROW+0x48,W.u32(5))
local job=settle(custom.apply())
assert(job.status=='refused'and job.code=='ROW_CHANGED'and job.reason:find('not the native',1,true),job.reason)
W.write(ROW+0x48,W.u32(6))
-- A pointer outside the settings allocation and outside Runtime.
W.write(ROW+0x40,W.u64(0x7000000))
job=settle(custom.apply())
assert(job.status=='refused'and job.code=='ROW_CHANGED',tostring(job.code))
W.write(ROW+0x40,W.u64(ORIGINAL))
assert(#W.runtime.writes==0 and#changed()==0)
-- The row changes between the capture and the write: the guarded transaction rejects it and writes nothing back.
local transaction=require('hd2runtime/core/guarded_transaction')
local apply=transaction.apply
transaction.apply=function(runtime,plan)W.write(ROW+0x48,W.u32(7));return apply(runtime,plan)end
job=settle(custom.apply())
transaction.apply=apply
assert(job.status=='refused'and job.code=='GUARD_REJECTED',tostring(job.code)..' '..tostring(job.reason))
assert(#W.runtime.writes==0 and u32_at(ROW+0x48)==7 and pointer(ROW+0x40)==ORIGINAL)
assert(not custom.state().applied)
W.write(ROW+0x48,W.u32(6))
-- Restore refuses a row that holds neither the custom nor the original sequence.
assert(settle(custom.apply()).status=='applied')
W.write(ROW+0x48,W.u32(3))
local restored=settle(custom.restore())
assert(restored.status=='refused'and restored.code=='ROW_CHANGED')
W.write(ROW+0x48,W.u32(4))
assert(settle(custom.restore()).status=='restored'and#changed()==0)
return 'ok'
''')

    def test_mission_host_and_proven_readers_are_required(self):
        self.lua(r'''
-- Aboard the ship.
local job=settle(custom.apply())
assert(job.status=='refused'and job.code=='NOT_IN_MISSION',tostring(job.code))
-- A client.
mission({host=false})
assert(settle(custom.apply()).code=='HOST_ONLY')
-- The Mission state without a game mode is not a mission yet.
W.state(4,{mode=false});tick()
assert(settle(custom.apply()).code=='NOT_IN_MISSION')
assert(#W.runtime.writes==0)
mission({host=true})
-- A changed calldown reader (re-proven once per loaded game.dll: a fresh world).
local pin=require('hd2runtime/domains/stratagem_calldown').pins[1]
W.write(W.GAME+pin.rva,string.char(0xCC))
world_module.set_runtime(W.runtime)
job=settle(custom.apply())
assert(job.status=='refused'and job.code=='CUSTOM_STRATAGEM_UNAVAILABLE'and job.reason:find('native calldown reader',1,
    true),job.reason)
W.write(W.GAME+pin.rva,b.unhex(pin.hex))
world_module.set_runtime(W.runtime)
-- An invalid sequence, and a second apply while applied.
assert(settle(custom.apply({stratagem='Orbital 120mm HE Barrage',sequence={1,9}})).code=='INVALID_SEQUENCE')
assert(settle(custom.apply()).status=='applied')
assert(settle(custom.apply()).code=='ALREADY_APPLIED')
assert(#W.runtime.writes==2)
-- read() reports the live row: what the matcher and the HUD read.
local read=settle(custom.read())
assert(read.status=='read'and read.runtime_owned and custom.names(read.sequence)=='Up Up Down Down'and read.type==136)
assert(settle(custom.restore()).status=='restored')
read=settle(custom.read())
assert(not read.runtime_owned and custom.names(read.sequence)=='Right Right Down Left Right Down')
return 'ok'
''')

    def test_p0_applies_before_the_local_avatar_exists_and_reports_whether_it_did(self):
        # The HUD's stratagem list fills its slots on the first frame the local avatar exists and only redraws a slot
        # when its stratagem type changes, so P0 must not wait for the avatar. Nothing in the write depends on it.
        self.lua(r'''
-- The mission has started (game state Mission, a game mode, host) but the Helldiver does not exist yet.
W.players({{peer=LOCAL}},LOCAL)
W.state(4,{host=true});tick()
local world=assert(world_module.open())
local avatar=custom.local_avatar(world)
assert(avatar.present==false and avatar.id==nil)
local job=settle(custom.apply())
assert(job.status=='applied',tostring(job.code)..' '..tostring(job.reason))
assert(job.avatar.present==false and job.avatar.id==nil,'no avatar at the write')
-- The same two writes as with an avatar, and nothing else.
local writes=W.runtime.writes
assert(#writes==2 and writes[1].address==ROW+0x48 and writes[1].bytes=='\4\0\0\0'and writes[2].address==ROW+0x40)
for _,offset in ipairs(changed())do
    assert(offset>=ROW-settings.base+0x40 and offset<ROW-settings.base+0x4C,'byte '..offset..' changed')
end
assert(custom.names(settle(custom.read()).sequence)=='Up Up Down Down')
-- The Helldiver lands: the row is unchanged, the restore writes the originals back.
mission({host=true})
assert(custom.local_avatar(world).present==true and custom.local_avatar(world).id==100)
assert(#W.runtime.writes==2 and custom.names(settle(custom.read()).sequence)=='Up Up Down Down')
assert(settle(custom.restore()).status=='restored'and#changed()==0)
-- Applied after the Helldiver exists (the late case): still applied, and reported as such.
job=settle(custom.apply())
assert(job.status=='applied'and job.avatar.present==true and job.avatar.id==100)
assert(settle(custom.restore()).status=='restored'and#changed()==0)
-- The local player missing from the player list: unknown.
W.players({},LOCAL)
assert(custom.local_avatar(world).present==nil)
job=settle(custom.apply())
assert(job.status=='applied'and job.avatar.present==nil)
assert(settle(custom.restore()).status=='restored'and#changed()==0)
return 'ok'
''')


HUD = r'''
local hud_module=require('hd2runtime/runtime/stratagem_hud')
local H=require('hd2runtime/domains/stratagem_calldown').hud
local SP=H.sprites
-- The list: slot 0 the cargo container (type 71), slot 1 the 120mm (type 136), drawn with the real HUD's bytes.
local HUD=W.stratagem_hud({peer=LOCAL,slots={{type=71,code={1,1,3,3,2,3}},{type=136,code={2,2,3,4,2,3}}}})
local SLOT=HUD.slots[1]
local function sprite(i)return SLOT.sprites[i+1]end
local function hexed(bytes)return(bytes:gsub('.',function(c)return string.format('%02x',c:byte())end))end
-- What the slot draws: the visible sprites' cells, from their image regions.
local function drawn(slot)
    local out={}
    for _,at in ipairs(slot.sprites)do
        if math.floor(u32_at(at)/16)%2==1 then out[#out+1]=math.floor(b.value(W.read(at+SP.region,4),0,'f32')/0.2+0.5)end
    end
    return table.concat(out,',')
end
-- Every byte of the HUD allocation and the record, to prove nothing else is written.
local HUD_BEFORE=W.read(HUD.hud,0x400000)
local function hud_changed()
    local now,out=W.read(HUD.hud,0x400000),{}
    for i=1,#now do if now:byte(i)~=HUD_BEFORE:byte(i)then out[#out+1]=HUD.hud+i-1 end end
    return out
end
'''


class HudRefreshTests(unittest.TestCase):
    """The development HUD refresh (runtime/stratagem_hud.lua): the 120mm's slot redrawn from the row with exactly the
    writes the game's own redraw makes, on a fixture HUD built from the real HUD's bytes."""

    def lua(self, body):
        self.assertEqual(run(WORLD + HUD + body), b'ok')

    def test_arrow_cells_and_derived_regions_are_the_games_float32_values(self):
        self.lua(r'''
-- Each cell's image region and its derived region through the real sub-rect, bit for bit as the game wrote them.
local sub={}
for i=0,3 do sub[i+1]=b.value(b.unhex(W.HUD_SUBRECT),i*4,'f32')end
for cell=0,4 do
    local region,derived=hud_module.region(cell),nil
    derived=hud_module.derived(region,sub)
    for i=0,3 do
        assert(region[i+1]==b.value(b.unhex(W.HUD_CELLS[cell][1]),i*4,'f32'),'cell '..cell..' region '..i)
        assert(derived[i+1]==b.value(b.unhex(W.HUD_CELLS[cell][2]),i*4,'f32'),'cell '..cell..' derived '..i)
    end
end
-- float32 rounding: nearest, ties to even.
local f32=hud_module.f32
assert(f32(1+2^-24)==1 and f32(1+3*2^-24)==1+2^-22 and f32(0.2)==b.value(b.unhex('cdcc4c3e'),0,'f32'))
assert(f32(0)==0 and f32(-0.75)==-0.75 and f32(1/3)~=1/3)
return 'ok'
''')

    def test_the_slot_is_found_by_the_players_record_and_its_drawn_code_is_read(self):
        self.lua(r'''
mission({host=true})
local world=assert(world_module.open())
local located,code,reason=hud_module.locate(world,136)
assert(located,tostring(code)..' '..tostring(reason))
assert(located.index==1 and located.slot==SLOT.address and table.concat(located.shows,',')=='2,2,3,4,2,3')
-- The 11 layout parents of the real list, in order.
assert(#located.ancestors==11)
for position,address in ipairs(SLOT.ancestors)do assert(located.ancestors[position].address==address)end
assert(located.ancestors[1].address==SLOT.container and located.ancestors[5].address==SLOT.address
    and located.ancestors[6].address==HUD.list and located.ancestors[11].address==HUD.root)
assert(table.concat(located.record,',')=='71,136')
assert(table.concat(hud_module.locate(world,71).shows,',')=='1,1,3,3,2,3')
assert(#W.runtime.writes==0)
return 'ok'
''')

    def test_refresh_redraws_only_the_120mm_slot_with_the_games_writes_and_back(self):
        self.lua(r'''
mission({host=true})
assert(settle(custom.apply()).status=='applied')
assert(#W.runtime.writes==2)
local other=W.read(HUD.slots[0].address,0x3760)
local job=settle(custom.refresh_hud())
assert(job.status=='refreshed',tostring(job.code)..' '..tostring(job.reason))
assert(job.index==1 and table.concat(job.before,',')=='2,2,3,4,2,3'and table.concat(job.after,',')=='1,1,3,3')
assert(job.report.status=='APPLIED'and job.report.non_target_bytes_unchanged and job.report.protection_restored)
-- Up Up Down Down drawn: sprites 0..3 visible with the real cell bytes, 4 and 5 hidden, 6..9 untouched.
assert(drawn(SLOT)=='1,1,3,3')
for i,cell in ipairs({1,1,3,3})do
    assert(hexed(W.read(sprite(i-1)+SP.region,16))==W.HUD_CELLS[cell][1]and hexed(W.read(sprite(i-1)+SP.derived,16))
        ==W.HUD_CELLS[cell][2],'sprite '..(i-1))
end
-- Sprites 0, 1 and 3 changed region (flag 0x2); 2 already drew Down. 4 and 5: 0x10 off, 0x20, 0x4 and +0xB8 0x800.
assert(u32_at(sprite(0))==0x000C1053 and u32_at(sprite(1))==0x000C1053 and u32_at(sprite(2))==0x000C1051
    and u32_at(sprite(3))==0x000C1053)
assert(u32_at(sprite(4))==0x000C1065 and u32_at(sprite(5))==0x000C1065 and u32_at(sprite(4)+SP.mask)==0x800
    and u32_at(sprite(5)+SP.mask)==0x800 and u32_at(sprite(6))==0x000C1043 and u32_at(sprite(6)+SP.mask)==0)
-- The layout parents up to the first that already had both (HUD +0x820) get 0x8 and 0x4; the slot is laid out again.
for position=1,9 do
    assert(u32_at(SLOT.ancestors[position])==(position==5 and 0x4501D or 0x4101D),'parent '..position)
end
assert(u32_at(SLOT.ancestors[10])==0x4101D and u32_at(HUD.root)==0x101D)
assert(W.read(SLOT.address+H.slots.relayout,1)=='\1')
-- Exactly the 29 writes of the live-verified redraw, byte for byte: sprites 0, 1 and 3 (u0 and u1 of the image and
-- derived regions, and flags), sprites 4 and 5 (flags and +0xB8), nine layout parents, the relayout flag.
local golden={}
local function expect(address,hex)golden[address]=hex end
for _,i in ipairs({0,1})do
    expect(sprite(i)+SP.region,'cdcc4c3e');expect(sprite(i)+SP.region+8,'cdcccc3e')
    expect(sprite(i)+SP.derived,'00902a3f');expect(sprite(i)+SP.derived+8,'00902e3f');expect(sprite(i),'53100c00')
end
expect(sprite(3)+SP.region,'9a99193f');expect(sprite(3)+SP.region+8,'cdcc4c3f')
expect(sprite(3)+SP.derived,'0090323f');expect(sprite(3)+SP.derived+8,'0090363f');expect(sprite(3),'53100c00')
for _,i in ipairs({4,5})do expect(sprite(i),'65100c00');expect(sprite(i)+SP.mask,'00080000')end
for position=1,9 do expect(SLOT.ancestors[position],position==5 and'1d500400'or'1d100400')end
expect(SLOT.address+H.slots.relayout,'01')
assert(#job.writes==29 and#W.runtime.writes==31,#job.writes..' '..#W.runtime.writes)
for index=3,#W.runtime.writes do
    local item=W.runtime.writes[index]
    assert(golden[item.address]==hexed(item.bytes),string.format('write %X %s',item.address,hexed(item.bytes)))
    golden[item.address]=nil
end
assert(next(golden)==nil,'every golden write happened')
-- Nothing else: the slot's type, displayed type, index, scrambler and timers, the other slot, the record, the row.
local first,last=SLOT.address+SP.offset,SLOT.address+SP.offset+SP.count*SP.stride
local allowed={[SLOT.address+H.slots.relayout]=true}
for position=1,9 do allowed[SLOT.ancestors[position]]=true end
for _,at in ipairs(hud_changed())do
    local word=at-(at-HUD.hud)%4
    assert((at>=first and at<last)or allowed[at]or allowed[word],string.format('HUD byte %X written',at))
end
assert(u32_at(SLOT.address+H.slots.type)==136 and u32_at(SLOT.address+H.slots.displayedType)==136
    and u32_at(SLOT.address+H.slots.index)==1)
assert(W.read(HUD.slots[0].address,0x3760)==other,'the other slot is untouched')
assert(u32_at(HUD.record+H.records.entries+H.records.entryStride)==136)
for _,offset in ipairs(changed())do
    assert(offset>=ROW-settings.base+0x40 and offset<ROW-settings.base+0x4C,'settings byte '..offset..' changed')
end
-- Again: already current, nothing written.
local again=settle(custom.refresh_hud())
assert(again.status=='current'and#W.runtime.writes==31)
-- Restore P0, then redraw the original: Right Right Down Left Right Down, all six visible again.
assert(settle(custom.restore()).status=='restored')
local back=settle(custom.refresh_hud())
assert(back.status=='refreshed'and table.concat(back.after,',')=='2,2,3,4,2,3',tostring(back.code)..' '..tostring(back.reason))
assert(drawn(SLOT)=='2,2,3,4,2,3')
for i,cell in ipairs({2,2,3,4,2,3})do
    assert(hexed(W.read(sprite(i-1)+SP.region,16))==W.HUD_CELLS[cell][1]and hexed(W.read(sprite(i-1)+SP.derived,16))
        ==W.HUD_CELLS[cell][2],'sprite '..(i-1))
end
assert(#changed()==0 and u32_at(SLOT.address+H.slots.type)==136)
return 'ok'
''')

    def test_closing_the_lua_state_restores_the_row_and_then_the_slot(self):
        self.lua(r'''
mission({host=true})
-- Applied but never redrawn: the close restores the row only.
assert(settle(custom.apply()).status=='applied')
custom.finalize_for_tests()
assert(custom.state().restored and#changed()==0 and#W.runtime.writes==4 and drawn(SLOT)=='2,2,3,4,2,3')
-- Applied and redrawn: the close restores the row, then the slot draws the original again.
assert(settle(custom.apply()).status=='applied')
assert(settle(custom.refresh_hud()).status=='refreshed'and drawn(SLOT)=='1,1,3,3')
local before=#W.runtime.writes
custom.finalize_for_tests()
assert(custom.state().restored and#changed()==0 and drawn(SLOT)=='2,2,3,4,2,3')
assert(#W.runtime.writes>before+2,'the row and the slot were written back')
for index=before+3,#W.runtime.writes do
    local at=W.runtime.writes[index].address
    assert(at>=SLOT.address and at<SLOT.address+H.slots.stride or at>=HUD.list-0x1040 and at<=HUD.list,
        string.format('close wrote %X',at))
end
-- The HUD gone at the close: the row is restored, the slot refused, nothing else written.
assert(settle(custom.apply()).status=='applied'and settle(custom.refresh_hud()).status=='refreshed')
W.write(HUD.hud+H.setUp,'\0')
before=#W.runtime.writes
custom.finalize_for_tests()
assert(custom.state().restored and#changed()==0 and#W.runtime.writes==before+2 and drawn(SLOT)=='1,1,3,3')
return 'ok'
''')

    def test_the_refresh_fails_closed_and_writes_nothing(self):
        self.lua(r'''
local function refused(expected)
    local job=settle(custom.refresh_hud())
    assert(job.status=='refused'and job.code==expected,expected..' expected, got '..tostring(job.code)..' '
        ..tostring(job.reason))
    return job
end
-- Before P0, and aboard the ship.
refused('NOT_APPLIED')
mission({host=true})
assert(settle(custom.apply()).status=='applied')
local writes=#W.runtime.writes
W.state(3);tick()
refused('NOT_IN_MISSION')
mission({host=true})
-- The HUD torn down.
W.write(HUD.hud+H.setUp,'\0');refused('NO_HUD');W.write(HUD.hud+H.setUp,'\1')
-- The record says another stratagem is in that slot; no slot holds the type; two slots hold it.
W.write(HUD.record+H.records.entries+H.records.entryStride,W.u32(71));refused('SLOT_ABSENT')
W.write(HUD.record+H.records.entries+H.records.entryStride,W.u32(136))
W.write(SLOT.address+H.slots.type,W.u32(140));refused('SLOT_ABSENT');W.write(SLOT.address+H.slots.type,W.u32(136))
W.write(HUD.slots[2].address+H.slots.type,W.u32(136));refused('SLOT_AMBIGUOUS')
W.write(HUD.slots[2].address+H.slots.type,W.u32(0))
-- Scrambled: the flag, another displayed type, a running animation.
W.write(SLOT.address+H.slots.scrambled,'\1');refused('SCRAMBLED');W.write(SLOT.address+H.slots.scrambled,'\0')
W.write(SLOT.address+H.slots.displayedType,W.u32(71));refused('SCRAMBLED')
W.write(SLOT.address+H.slots.displayedType,W.u32(136))
W.write(SLOT.address+H.slots.timers+4,W.f32(0.5));refused('SCRAMBLED');W.write(SLOT.address+H.slots.timers+4,W.u32(0))
-- A changed structure: a slot index, a flag parent, a sibling, a derived region one bit off, a gap in the arrows.
W.write(HUD.slots[5].address+H.slots.index,W.u32(9));refused('HUD_CHANGED')
W.write(HUD.slots[5].address+H.slots.index,W.u32(5))
W.write(sprite(2)+SP.flagParent,W.u64(HUD.list));refused('HUD_CHANGED');W.write(sprite(2)+SP.flagParent,W.u64(0))
W.write(sprite(2)+SP.sibling,W.u64(sprite(4)));refused('HUD_CHANGED');W.write(sprite(2)+SP.sibling,W.u64(sprite(3)))
local derived=W.read(sprite(1)+SP.derived,4)
W.write(sprite(1)+SP.derived,W.u32(u32_at(sprite(1)+SP.derived)+1));refused('HUD_CHANGED')
W.write(sprite(1)+SP.derived,derived)
W.write(sprite(2),W.u32(0x000C1043));refused('HUD_CHANGED');W.write(sprite(2),W.u32(0x000C1051))
-- The slot draws a third code.
local region=W.read(sprite(0)+SP.region,16)
W.write(sprite(0)+SP.region,b.unhex(W.HUD_CELLS[4][1]));W.write(sprite(0)+SP.derived,b.unhex(W.HUD_CELLS[4][2]))
refused('HUD_SHOWS_OTHER')
W.write(sprite(0)+SP.region,region);W.write(sprite(0)+SP.derived,b.unhex(W.HUD_CELLS[2][2]))
-- A changed HUD pin (re-proven once per loaded game.dll: a fresh world).
local pin=H.pins[1]
W.write(W.GAME+pin.rva,string.char(0xCC));world_module.set_runtime(W.runtime)
refused('HUD_UNAVAILABLE')
W.write(W.GAME+pin.rva,b.unhex(pin.hex));world_module.set_runtime(W.runtime)
assert(#W.runtime.writes==writes,'nothing written by a refusal')
-- A sprite changes between the read and the write: the guarded transaction rejects it and rolls back.
local transaction=require('hd2runtime/core/guarded_transaction')
local apply=transaction.apply
transaction.apply=function(runtime,plan)W.write(sprite(3)+SP.region,W.f32(0.4));return apply(runtime,plan)end
local job=settle(custom.refresh_hud())
transaction.apply=apply
assert(job.status=='refused'and job.code=='GUARD_REJECTED',tostring(job.code)..' '..tostring(job.reason))
assert(#W.runtime.writes==writes and drawn(SLOT)~='1,1,3,3')
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
