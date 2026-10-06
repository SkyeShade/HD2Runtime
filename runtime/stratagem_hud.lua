-- The in-mission stratagem list's drawn arrows (docs/custom-stratagems.md#the-hud). Runtime-internal: the HUD sync of
-- hd2.fields.stratagem.calldown_code (runtime/calldown_codes.lua); not exported by api/hd2.lua, no SDK field.
--
-- The list (16 slots) copies each stratagem's code from its row every frame but redraws a slot's arrow sprites only
-- when the slot's stratagem type changes. A code written into the row later is matched but not drawn. refresh() redraws
-- the one slot of a stratagem type with exactly the data the game's own redraw writes (research: hud.rebuild and
-- hud.sprite), and nothing else:
--   * per sprite whose image region changes: the region (+0x114, cell x 0.2f wide, v 0..1), the derived region
--     (+0x124, through the sprite's sub-rect +0x134, in float32 as the game computes it) and flag 0x2;
--   * per sprite whose visibility changes: flag 0x10 (visible) and 0x20, +0xB8 bit 0x800 and flag 0x4;
--   * up the layout parents (+0xF0): 0x8 (after a region change) and 0x4 (after a visibility change) on each ancestor
--     until one already has it;
--   * the slot's +0x36F1 = 1, so the list lays it out again.
-- The slot's type, displayed type, timers and scrambler state, the other slots, the row and the record are only read.
-- Invisible sprites keep their image region: the game writes stale stack values there, which nothing draws.
--
-- Everything is read and written in one update tick, through the guarded transaction (exact expected bytes, each
-- touched element as its context, protection checked, rollback on failure). It fails closed on any structure, value or
-- pin that differs from the research.
local world_module=require('hd2runtime/runtime/event_world')
local transaction=require('hd2runtime/core/guarded_transaction')
local metrics=require('hd2runtime/runtime/metrics')
local b=require('hd2runtime/core/bytes')
local profile=require('hd2runtime/schemas/current')
local C=require('hd2runtime/domains/stratagem_calldown')
local H=C.hud
local M={}
local SL,SP,BIT,REC=H.slots,H.sprites,H.sprites.bits,H.records
local TAIL,TAIL_SIZE=SL.relayout-1,SL.displayedType+4-(SL.relayout-1)   -- slot +0x36F0 .. +0x3758
local ELEMENT=16                                                          -- an ancestor's context: its first bytes
local MAX_ANCESTORS,MAX_RECORDS=32,64

local function unhex(h)return(h:gsub('..',function(p)return string.char(tonumber(p,16))end))end
local function u32(n)return string.char(n%256,math.floor(n/256)%256,math.floor(n/65536)%256,math.floor(n/16777216)%256)end
local function has(flags,bit)return math.floor(flags/bit)%2==1 end
local function with(flags,bit,on)
    if on and not has(flags,bit)then return flags+bit end
    if not on and has(flags,bit)then return flags-bit end
    return flags
end

-- The float32 nearest to x, ties to even: what mulss and addss store. Finite values only.
local function f32(x)
    if x==0 then return 0 end
    local sign=1
    if x<0 then sign,x=-1,-x end
    local m,e=math.frexp(x)
    local scaled=m*16777216
    local whole=math.floor(scaled)
    local rest=scaled-whole
    if rest>0.5 or(rest==0.5 and whole%2==1)then whole=whole+1 end
    return sign*whole*2^(e-24)
end
M.f32=f32
-- The 4 bytes of a float32 value.
local function f32_bytes(x)
    if x==0 then return u32(0)end
    local sign=0
    if x<0 then sign,x=2147483648,-x end
    local m,e=math.frexp(x)
    local mantissa=(m*2-1)*8388608
    assert(e+126>0 and e+126<255 and mantissa%1==0,'not a normal float32 value')
    return u32(sign+(e+126)*8388608+mantissa)
end
local WIDTH=b.value(unhex(SP.cellBytes),0,'f32')
-- The image region of a cell, as the game computes it: u0 = cell x width, u1 = u0 + width, v 0..1.
function M.region(cell)
    local u0=f32(cell*WIDTH)
    return {u0,0,f32(u0+WIDTH),1}
end
-- The derived region through a sub-rect {x, y, width, height}.
function M.derived(region,sub)
    return {f32(f32(sub[3]*region[1])+sub[1]),f32(f32(sub[4]*region[2])+sub[2]),f32(f32(sub[3]*region[3])+sub[1]),
        f32(f32(sub[4]*region[4])+sub[2])}
end
local function floats(bytes,offset)
    local out={}
    for index=1,4 do
        local n=b.u32(bytes,offset+(index-1)*4)
        if math.floor(n/8388608)%256==255 then return nil end
        out[index]=b.value(bytes,offset+(index-1)*4,'f32')
    end
    return out
end
local function same(a,c)
    if #a~=#c then return false end
    for index=1,#a do if a[index]~=c[index]then return false end end
    return true
end

-- Every HUD pin, proven once per loaded game.dll. true, or nil and the first mismatch.
function M.prove(world)
    if world.stratagem_hud_proven then return true end
    if C.source.gameDllSha256~=profile.dll_sha then return nil,'the HUD research covers another game.dll build'end
    for _,pin in ipairs(H.pins)do
        if not world.view.proves(world.game+pin.rva,pin.hex)then
            return nil,'native HUD code changed ('..pin.label..' at game+'..string.format('%X',pin.rva)..')'
        end
    end
    world.stratagem_hud_proven=true
    return true
end

-- The local player's stratagem record: its entry types in order, or nil.
local function record_types(world)
    local lo,hi=world_module.local_peer(world)
    local records=world.view.pointer(world.game+REC.global)
    local count=records and world.view.u32(records+REC.count)
    if not(lo and records and count and count<=MAX_RECORDS)then return nil end
    for index=0,count-1 do
        local record=records+index*REC.stride
        if world.view.u32(record)==lo and world.view.u32(record+4)==hi then
            local entries=world.view.u32(record+REC.entryCount)
            if not entries or entries>SL.count then return nil end
            local types={}
            for entry=0,entries-1 do types[#types+1]=world.view.u32(record+REC.entries+entry*REC.entryStride)end
            return types
        end
    end
end

-- The slot of one stratagem type in the list and everything refresh() checks, read now. nil, code, reason otherwise.
-- {hud, owner, slot, index, tail, sprites = {{address, bytes, flags, mask, region, derived, sub, visible}},
--  shows (the drawn code), ancestors = {{address, bytes, flags}}}
function M.locate(world,kind)
    local proven,why=M.prove(world)
    if not proven then return nil,'HUD_UNAVAILABLE',why end
    local game=world_module.game_state(world)
    if not(game and game.mission)then return nil,'NOT_IN_MISSION','the stratagem list exists only in a mission'end
    local hud=world.view.pointer(world.game+H.global)
    local set_up=hud and world.view.read(hud+H.setUp,1)
    if not(set_up and set_up:byte()==1)then return nil,'NO_HUD','the mission HUD is not set up'end
    local region=world.runtime.query(hud)
    if not(region and region.type==0x20000 and region.protect==4 and region.state==0x1000)then
        return nil,'HUD_CHANGED','the HUD system is not in a private read-write allocation'
    end
    local base=region.allocation_base
    local first=hud+H.pathOffset
    local found,tails={},{}
    for index=0,SL.count-1 do
        local slot=first+index*SL.stride
        local tail=world.view.read(slot+TAIL,TAIL_SIZE)
        if not(tail and b.u32(tail,SL.index-TAIL)==index)then
            return nil,'HUD_CHANGED','stratagem list slot '..index..' does not carry its index'
        end
        tails[index]=tail
        if b.u32(tail,SL.type-TAIL)==kind then found[#found+1]=index end
    end
    if #found==0 then return nil,'SLOT_ABSENT','no stratagem list slot holds type '..kind end
    if #found>1 then return nil,'SLOT_AMBIGUOUS','more than one stratagem list slot holds type '..kind end
    local index=found[1]
    local slot,tail=first+index*SL.stride,tails[index]
    local types=record_types(world)
    if not types then return nil,'HUD_CHANGED','the local player\'s stratagem record is unreadable'end
    if types[index+1]~=kind then
        return nil,'SLOT_ABSENT','the local player\'s stratagem '..(index+1)..' is type '..tostring(types[index+1])
            ..', not '..kind
    end
    if b.u32(tail,SL.displayedType-TAIL)~=kind or tail:byte(SL.scrambled-TAIL+1)~=0 then
        return nil,'SCRAMBLED','the slot is scrambled (it draws another type\'s code)'
    end
    if tail:sub(SL.timers-TAIL+1,SL.timers-TAIL+8)~=string.rep('\0',8)then
        return nil,'SCRAMBLED','the slot\'s scramble animation is running'
    end
    -- The sprites: no flag parent, the next sprite as sibling, one row container (inside the slot) as layout parent.
    local sprites,container={},nil
    for number=0,SP.count-1 do
        local address=slot+SP.offset+number*SP.stride
        local bytes=world.view.read(address,SP.stride)
        if not bytes then return nil,'HUD_CHANGED','sprite '..number..' is unreadable'end
        local parent=b.pointer(bytes,SP.parent)
        container=container or parent
        local sibling=number<SP.count-1 and address+SP.stride or 0
        if b.pointer(bytes,SP.flagParent)~=0 or parent~=container or b.pointer(bytes,SP.sibling)~=sibling then
            return nil,'HUD_CHANGED','sprite '..number..' is not linked as researched'
        end
        local item={address=address,bytes=bytes,flags=b.u32(bytes,0),mask=b.u32(bytes,SP.mask),
            region=floats(bytes,SP.region),derived=floats(bytes,SP.derived),sub=floats(bytes,SP.subrect)}
        if not(item.region and item.derived and item.sub)then return nil,'HUD_CHANGED','sprite '..number..' is not finite'end
        item.visible=has(item.flags,BIT.visible)
        sprites[number+1]=item
    end
    if not(container and container>slot and container<slot+SL.stride)then
        return nil,'HUD_CHANGED','the arrow row is not inside its slot'
    end
    -- The drawn code: visible sprites 0 .. n-1, each exactly a cell's region and its derived region.
    local shows,ended={},false
    for number,item in ipairs(sprites)do
        if item.visible then
            if ended then return nil,'HUD_CHANGED','visible sprites are not contiguous'end
            local cell
            for candidate=1,4 do if same(item.region,M.region(candidate))then cell=candidate end end
            if not cell or not same(item.derived,M.derived(item.region,item.sub))then
                return nil,'HUD_CHANGED','sprite '..(number-1)..' does not hold a drawn arrow'
            end
            shows[#shows+1]=cell
        else
            ended=true
        end
    end
    if #shows==0 then return nil,'HUD_CHANGED','the slot draws no arrows'end
    -- The layout parents from the row container up to the root: through the slot and the list.
    local ancestors,at,seen={},container,{}
    while at and at~=0 do
        if #ancestors>=MAX_ANCESTORS or seen[at]then return nil,'HUD_CHANGED','the layout parents do not end'end
        seen[at]=true
        local bytes=world.view.read(at,ELEMENT)
        local parent=world.view.read(at+SP.parent,8)
        if not(bytes and parent)then return nil,'HUD_CHANGED','a layout parent is unreadable'end
        ancestors[#ancestors+1]={address=at,bytes=bytes,flags=b.u32(bytes,0)}
        at=b.pointer(parent,0)
    end
    if not(seen[slot]and seen[first-H.listSlot0])then
        return nil,'HUD_CHANGED','the layout parents do not pass through the slot and the list'
    end
    -- Every touched element lies in the HUD system's allocation, private and read-write.
    local last=0
    local function inside(address,size)
        local r=world.runtime.query(address)
        if not(r and r.allocation_base==base and r.type==0x20000 and r.protect==4 and r.state==0x1000
                and address+size<=r.base+r.size)then return false end
        last=math.max(last,r.base+r.size)    -- whole pages: the guarded write checks each target's page
        return true
    end
    if not inside(slot+TAIL,TAIL_SIZE)then return nil,'HUD_CHANGED','the slot is outside the HUD allocation'end
    for _,item in ipairs(sprites)do
        if not inside(item.address,SP.stride)then return nil,'HUD_CHANGED','a sprite is outside the HUD allocation'end
    end
    for _,item in ipairs(ancestors)do
        if not inside(item.address,ELEMENT)then return nil,'HUD_CHANGED','a layout parent is outside the HUD allocation'end
    end
    return {hud=hud,owner={base=base,size=last-base,type=0x20000,protect=4},slot=slot,index=index,tail=tail,
        sprites=sprites,shows=shows,ancestors=ancestors,record=types}
end

-- Whether the list has filled any slot yet (read-only): true once the local Helldiver exists in a mission, false
-- before, nil when the HUD is not set up or unreadable. A type absent from a filled list is not in the loadout.
function M.populated(world)
    if not M.prove(world)then return nil end
    local hud=world.view.pointer(world.game+H.global)
    local set_up=hud and world.view.read(hud+H.setUp,1)
    if not(set_up and set_up:byte()==1)then return nil end
    for index=0,SL.count-1 do
        local kind=world.view.u32(hud+H.pathOffset+index*SL.stride+SL.type)
        if kind==nil then return nil end
        if kind~=0 then return true end
    end
    return false
end

-- The writes of the game's own redraw of a located slot with the code draw: {{label, address, before, after}}.
function M.plan(located,draw)
    local writes={}
    local function put(label,address,before,after)
        if before~=after then writes[#writes+1]={label=label,address=address,before=before,after=after}end
    end
    local region_changed,layout_changed=false,false
    for number,item in ipairs(located.sprites)do
        local i=number-1
        local flags,mask=item.flags,item.mask
        if i<#draw then
            local region=M.region(draw[number])
            if not same(item.region,region)then
                local derived=M.derived(region,item.sub)
                for field=1,4 do
                    put(('sprite %d region %d'):format(i,field),item.address+SP.region+(field-1)*4,
                        item.bytes:sub(SP.region+(field-1)*4+1,SP.region+field*4),f32_bytes(region[field]))
                    put(('sprite %d derived %d'):format(i,field),item.address+SP.derived+(field-1)*4,
                        item.bytes:sub(SP.derived+(field-1)*4+1,SP.derived+field*4),f32_bytes(derived[field]))
                end
                flags=with(flags,BIT.regionChanged,true)
                region_changed=true
            end
        end
        local visible=i<#draw
        if visible~=item.visible then
            flags=with(with(flags,BIT.visible,visible),BIT.visibilityChanged,true)
            local marked=with(mask,BIT.maskBit,true)
            if marked~=mask then
                mask=marked
                if not has(flags,BIT.layoutChanged)then
                    flags=with(flags,BIT.layoutChanged,true)
                    layout_changed=true
                end
            end
        end
        put(('sprite %d flags'):format(i),item.address,u32(item.flags),u32(flags))
        put(('sprite %d +0xB8'):format(i),item.address+SP.mask,u32(item.mask),u32(mask))
    end
    -- Up the layout parents: each bit until an ancestor already has it (as the game's walks stop).
    local bits={}
    if region_changed then bits[#bits+1]=BIT.childChanged end
    if layout_changed then bits[#bits+1]=BIT.layoutChanged end
    local final={}
    for _,bit in ipairs(bits)do
        for position,item in ipairs(located.ancestors)do
            local flags=final[position]or item.flags
            if has(item.flags,bit)then break end
            final[position]=with(flags,bit,true)
        end
    end
    for position,item in ipairs(located.ancestors)do
        if final[position]then put('ancestor '..position..' flags',item.address,u32(item.flags),u32(final[position]))end
    end
    local relayout=located.tail:sub(SL.relayout-TAIL+1,SL.relayout-TAIL+1)
    put('slot +0x36F1',located.slot+SL.relayout,relayout,'\1')
    return writes
end

-- Redraws the slot of spec.type with spec.draw, which must be the code the row holds now (spec.row: the row's
-- address, read again here), from a drawn code in spec.from (the codes the slot may show now). One tick, no yield.
-- Returns {status = 'refreshed' | 'current', index, slot, before, after, writes, report}, or nil, code, reason.
function M.refresh(world,spec)
    local located,code,reason=M.locate(world,spec.type)
    if not located then return nil,code,reason end
    -- The row: the same type, and the code to draw is exactly the one it holds now (what the matcher accepts).
    local row=world.view.read(spec.row,C.row.stride)
    if not(row and b.u32(row,0)==spec.type)then return nil,'ROW_CHANGED','the row does not carry type '..spec.type end
    local pointer,count=b.pointer(row,C.row.sequence),b.u32(row,C.row.count)
    local live=count>=1 and count<=C.maxLength and world.view.read(pointer,count*4)
    local sequence={}
    if live then for index=1,count do sequence[index]=b.u32(live,(index-1)*4)end end
    if not(live and same(sequence,spec.draw))then
        return nil,'ROW_CHANGED','the row does not hold the code to draw'
    end
    for _,value in ipairs(spec.draw)do
        if value<1 or value>4 then return nil,'INVALID_SEQUENCE','a direction must be 1 to 4'end
    end
    if same(located.shows,spec.draw)then
        return {status='current',index=located.index,slot=located.slot,before=located.shows,after=located.shows,
            writes={}}
    end
    local known=false
    for _,candidate in ipairs(spec.from or{})do if same(located.shows,candidate)then known=true end end
    if not known then return nil,'HUD_SHOWS_OTHER','the slot draws a code that is neither expected one'end
    local writes=M.plan(located,spec.draw)
    local owner=located.owner
    local plan={snapshots={},changes={}}
    local function context(address,bytes)plan.snapshots[#plan.snapshots+1]={owner=owner,offset=address-owner.base,bytes=bytes}end
    for _,item in ipairs(located.sprites)do context(item.address,item.bytes)end
    for _,item in ipairs(located.ancestors)do context(item.address,item.bytes)end
    context(located.slot+TAIL,located.tail)
    for _,item in ipairs(writes)do
        plan.changes[#plan.changes+1]={label=item.label,owner=owner,offset=item.address-owner.base,expected=item.before,
            desired=item.after,before=item.before,already_desired=false,
            identity={component='StratagemList',record_type='slot',record_kind=spec.type,row=located.index,
                unique_owner=true,owner_count=1},chain={}}
    end
    local report=transaction.apply(world.runtime,plan)
    metrics.count('stratagem_hud.transactions')
    if report.status~='APPLIED'then
        return nil,'GUARD_REJECTED','the guarded HUD write was '..tostring(report.status)..': '..tostring(report.reason)
    end
    local after=M.locate(world,spec.type)
    if not(after and same(after.shows,spec.draw))then
        return nil,'HUD_REFRESH_FAILED','the slot does not read back the drawn code'
    end
    metrics.count('stratagem_hud.refreshed')
    return {status='refreshed',index=located.index,slot=located.slot,before=located.shows,after=after.shows,
        writes=writes,report=report}
end
return M
