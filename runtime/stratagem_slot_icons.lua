-- Slot-local loadout icons (development only; docs/custom-stratagems.md, "Slot-local loadout icons"). Not exported by
-- api/hd2.lua and no public field reaches it.
--
-- FALLBACK ONLY (0.7.0): a virtual slot's icon is drawn by a Runtime overlay in the Ui World by default
-- (runtime/stratagem_slot_overlay.lua virtual_slots; live-proven by SlotOverlayProof 0.1.0), which never writes the
-- native slot. These borrowed-icon writes into the native slot's icon element are kept, live-proven (0.5.0/0.6.0), as a
-- documented fallback: nothing starts them; a caller must call M.follow() itself.
--
-- A virtual slot (runtime/stratagem_selector.lua virtual_slots) holds a vanilla token, so the native loadout slot shows
-- the token's icon. When its definition names a slot icon (display.slot_icon: a vanilla stratagem whose icon sits on the
-- SAME atlas page as the token's), this module shows that icon in that one slot only (research slotIcon):
--   * each slot widget's icon element (widget + 0x380, an image element) holds the sprite rectangle (+0x134) and UV
--     (+0x124) the game's image setter computed; its material samples the atlas page; the scene update pushes a dirty
--     element's material and UV to its GUI primitive. One guarded transaction writes the borrowed sprite's rectangle and
--     UV (computed as the setter computes it, in single precision) and the dirty bits exactly as the setter sets them
--     (the element's bit 1 unless set, then bit 3 on each ancestor through +0xF0 until one has it). Nothing else.
--   * every repaint resets all four slots from their types (no early return), so a virtual slot's icon is re-applied
--     on the next frame after one (the token's icon may show for that frame); a slot that is no longer virtual gets its
--     token's rectangle back if no repaint did it already.
--   * no StratagemInfo write: another slot holding the same token keeps the token's icon. No native call.
-- Limits: only an icon on the token's atlas page with the token's colour set (its mask colours are the slot's own); a
-- custom image (a texture of its own) cannot be shown this way: binding a texture is an engine call (a render command).
-- Guards (refused with nothing written): the selector's pinned code; the loadout screen open with the local record;
-- solo; the widget holding the token; the element an image whose name is the token's icon and whose rectangle is the
-- token sprite's (the atlas data the research saw); both sprites on one page; the element, its parents and their memory
-- private read-write.
local world_module=require('hd2runtime/runtime/event_world')
local transaction=require('hd2runtime/core/guarded_transaction')
local loadout=require('hd2runtime/runtime/stratagem_loadout')
local virtual=require('hd2runtime/runtime/virtual_stratagems')
local images=require('hd2runtime/runtime/image_resources')
local selector=require('hd2runtime/runtime/stratagem_selector')
local scheduler=require('hd2runtime/runtime/scheduler')
local metrics=require('hd2runtime/runtime/metrics')
local log_module=require('hd2runtime/runtime/log')
local b=require('hd2runtime/core/bytes')
local D=require('hd2runtime/domains/stratagem_selector')
local L,I=D.loadout,D.slotIcon
local TABLE=require('hd2runtime/schemas/current').stratagem.table_rva
local M={}
local REAPPLY_LIMIT=8          -- re-applications per slot within REAPPLY_WINDOW seconds before pausing
local REAPPLY_WINDOW=2

local function log(text)log_module.emit('[HD2Runtime] slot icons '..text)end
local function u32(n)n=n%4294967296;return string.char(n%256,math.floor(n/256)%256,math.floor(n/65536)%256,math.floor(n/16777216)%256)end
local function qword(world,at)
    local s=world.view.read(at,8)
    return s and b.u32(s,0)+b.u32(s,4)*4294967296
end
local function f32s(s)
    local out={}
    for i=0,3 do
        local ok,v=pcall(b.value,s,i*4,'f32')
        if not ok then return nil end
        out[i+1]=v
    end
    return out
end
local function enc(v)return b.encode(v,'f32')end
local function round32(v)return b.value(enc(v),0,'f32')end
local function row(world,kind)
    return type(kind)=='number'and kind>0 and kind<150 and world.view.pointer(world.game+TABLE+kind*8)or nil
end
local function owner_of(world,address,size)
    local r=world.runtime.query and world.runtime.query(address)
    if not(r and r.state==0x1000 and r.type==0x20000 and r.protect==4 and address>=r.base and address+size<=r.base+r.size)
    then return nil end
    return {base=r.allocation_base,size=r.base+r.size-r.allocation_base,type=0x20000,protect=4}
end

-- A stratagem's icon: its row's icon name (+0xB0), colour set (+0xB8) and atlas sprite {record, page, rect}; or nil, why.
local function icon_of(world,stable_id)
    local kind=loadout.type_of(world,stable_id)
    local r=kind and row(world,kind)
    if not r then return nil,'no StratagemInfo row carries stable id '..tostring(stable_id)end
    -- The icon name as its 8 raw bytes (a 64-bit hash does not fit a Lua number exactly) and its two halves.
    local name=world.view.read(r+0xB0,8)
    if not name or#name~=8 or name==string.char(0):rep(8)then return nil,'the stratagem has no icon'end
    local done,record,page=pcall(images.sprite_record,world.runtime,b.u32(name,4),b.u32(name,0))
    if not done then return nil,tostring(record)end
    if not record then return nil,'its icon is not an atlas sprite: '..tostring(page)end
    local raw=world.view.read(record+I.spriteRect,16)
    local rect=raw and#raw==16 and f32s(raw)
    if not rect then return nil,'its sprite rectangle is unreadable'end
    return {kind=kind,name=name,colourSet=world.view.u32(r+0xB8),page=page,rect=rect,rectBytes=raw}
end
-- The UV the image setter computes from the element's base UV and a sprite rectangle (0x143F3C0, single precision).
local function uv_for(base,rect)
    return {round32(round32(base[1]*rect[3])+rect[1]),round32(round32(base[2]*rect[4])+rect[2]),
        round32(round32(base[3]*rect[3])+rect[1]),round32(round32(base[4]*rect[4])+rect[2])}
end
local function same(a,b_)
    if not(a and b_)then return false end
    for i=1,4 do if a[i]~=b_[i]then return false end end
    return true
end
local function vec_bytes(v)return enc(v[1])..enc(v[2])..enc(v[3])..enc(v[4])end

-- One slot's icon element, read: {address, flags, kind, rect, uv, base, name, material, parents = {addresses}}.
local function element(world,view,slot)
    local at=view.ui+L.panel0Widgets+slot*L.widgetStride+I.element
    local flags=world.view.u32(at+I.flags)
    local rect,uv,base=world.view.read(at+I.rect,16),world.view.read(at+I.uv,16),world.view.read(at+I.base,16)
    if not(flags and rect and uv and base)then return nil,'the slot icon element is unreadable'end
    local e={address=at,flags=flags,kind=math.floor(flags/2^I.kindShift)%(I.kindMask+1),rect=f32s(rect),uv=f32s(uv),
        base=f32s(base),name=world.view.read(at+I.name,8),material=qword(world,at+I.material),parents={}}
    if not(e.rect and e.uv and e.base)then return nil,'the slot icon element holds non-finite values'end
    local p=qword(world,at+I.parent)
    while p and p~=0 do
        if#e.parents>=I.maxAncestors then return nil,'the element has too many ancestors'end
        e.parents[#e.parents+1]=p
        p=qword(world,p+I.parent)
    end
    if p==nil then return nil,'an ancestor of the element is unreadable'end
    return e
end

-- The guarded transaction putting `rect` (and its UV) into a slot's icon element and marking it dirty as the image
-- setter does. Returns the report, or nil and why.
local function write_rect(world,e,rect,label)
    local uv=uv_for(e.base,rect)
    local owner=owner_of(world,e.address,I.name+8)
    if not owner then return nil,'the slot icon element is not in private read-write memory'end
    local snapshots={{owner=owner,offset=e.address+I.flags-owner.base,bytes=world.view.read(e.address+I.flags,4)},
        {owner=owner,offset=e.address+I.primitive-owner.base,
            bytes=world.view.read(e.address+I.primitive,I.name+8-I.primitive)}}
    local changes={}
    local function change(name,address,own,expected,desired)
        changes[#changes+1]={label=name,owner=own,offset=address-own.base,expected=expected,desired=desired,
            before=expected,already_desired=false,identity={component='LoadoutSlotIcon',component_type='native',
            unique_owner=true,owner_count=1},chain={}}
    end
    local old_rect,new_rect=vec_bytes(e.rect),vec_bytes(rect)
    local old_uv,new_uv=vec_bytes(e.uv),vec_bytes(uv)
    for i=0,3 do
        local o,n=old_rect:sub(i*4+1,i*4+4),new_rect:sub(i*4+1,i*4+4)
        if o~=n then change(label..'.rect'..i,e.address+I.rect+i*4,owner,o,n)end
        o,n=old_uv:sub(i*4+1,i*4+4),new_uv:sub(i*4+1,i*4+4)
        if o~=n then change(label..'.uv'..i,e.address+I.uv+i*4,owner,o,n)end
    end
    if#changes==0 then return {status='UNCHANGED',writes=0,non_target_bytes_unchanged=true,protection_restored=true}end
    if math.floor(e.flags/I.dirty)%2==0 then
        change(label..'.dirty',e.address+I.flags,owner,u32(e.flags),u32(e.flags+I.dirty))
    end
    for _,a in ipairs(e.parents)do
        local flags=world.view.u32(a+I.flags)
        if not flags then return nil,'an ancestor of the element is unreadable'end
        if math.floor(flags/I.childDirty)%2==1 then break end
        local own=owner_of(world,a,4)
        if not own then return nil,'an ancestor of the element is not in private read-write memory'end
        snapshots[#snapshots+1]={owner=own,offset=a+I.flags-own.base,bytes=world.view.read(a+I.flags,4)}
        change(label..'.ancestor_child_dirty',a+I.flags,own,u32(flags),u32(flags+I.childDirty))
    end
    for _,s in ipairs(snapshots)do if not s.bytes then return nil,'the slot icon element is unreadable'end end
    local report=transaction.apply(world.runtime,{snapshots=snapshots,changes=changes})
    metrics.count('stratagem_slot_icons.transactions')
    if report.status~='APPLIED'then return nil,'guard rejected: '..tostring(report.reason)end
    return report
end

-- The follower: every frame while the loadout screen is open, each virtual slot whose definition names a slot icon shows
-- it, and a slot that is no longer virtual is put back if no repaint did it. opts.enabled (default true). Returns S
-- {status(), set_enabled(on), stop(), slots = {[slot] = state}}.
function M.follow(opts)
    opts=opts or{}
    local S={enabled=opts.enabled~=false,slots={},paused={},clock=0}
    local cache={}              -- stable id -> icon (per screen visit)
    local ui_seen
    local function icon(world,id)
        local hit=cache[id]
        if hit==nil then
            local value,why=icon_of(world,id)
            hit=value or{failed=why}
            cache[id]=hit
        end
        if hit.failed then return nil,hit.failed end
        return hit
    end
    local function reason_once(slot,why)
        local state=S.slots[slot]or{}
        if state.reason~=why then log(('slot %d: not shown: %s'):format(slot,tostring(why)))end
        state.reason=why
        S.slots[slot]=state
    end
    local function restore(world,view,slot,state)
        local e=element(world,view,slot)
        if not e then S.slots[slot]=nil;return end
        if state.borrowed and e.name==state.token.name and same(e.rect,state.borrowed.rect)then
            local report,why=write_rect(world,e,state.token.rect,'loadout.slot'..slot..'.icon')
            log(report and('slot %d is no longer virtual: its own icon put back (%d writes)'):format(slot,report.writes)
                or('slot %d: its own icon NOT put back: %s'):format(slot,tostring(why)))
        end
        S.slots[slot]=nil
    end
    local function tick(dt)
        S.clock=S.clock+(dt or 0)
        local world=world_module.open()
        if not world then return end
        local ok,view=pcall(selector.screen,world)
        if not(ok and view and view.open and view.record)then cache,ui_seen,S.slots,S.paused={},nil,{},{};return end
        if view.ui~=ui_seen then cache,ui_seen,S.slots,S.paused={},view.ui,{},{}end
        local proven=selector.prove(world)
        if not proven or view.players~=1 then return end
        local set=selector.virtual_slots()
        local now=S.clock
        for slot=0,L.maxLoadoutEntries-1 do
            local v=set and set.slots[slot]
            local definition=v and virtual.get(v.definition)
            local wanted=S.enabled and definition and definition.display.slotIcon
            local state=S.slots[slot]
            if not wanted then
                if state and state.borrowed then restore(world,view,slot,state)end
            elseif S.paused[slot]then
                -- paused: the game repaints this slot continuously
            else
                local token,why=icon(world,v.token)
                local borrowed,bwhy=icon(world,wanted.id)
                local e,ewhy=element(world,view,slot)
                if not token then reason_once(slot,'the token\'s icon: '..tostring(why))
                elseif not borrowed then reason_once(slot,wanted.stratagem..'\'s icon: '..tostring(bwhy))
                elseif borrowed.page~=token.page then
                    reason_once(slot,('%s\'s icon is on atlas page %s, the token\'s on %s: only an icon on the same page '
                        ..'can be shown by data'):format(wanted.stratagem,borrowed.page,token.page))
                elseif borrowed.colourSet~=token.colourSet then
                    reason_once(slot,wanted.stratagem..' has another colour set than the token (its mask colours differ)')
                elseif not e then reason_once(slot,ewhy)
                elseif view.widgets[slot+1]~=token.kind then reason_once(slot,'the slot does not show the token')
                elseif e.kind~=I.imageKind or e.material==0 or e.material==nil then
                    reason_once(slot,'the slot icon element is not an image with a material')
                elseif e.name~=token.name then reason_once(slot,'the slot icon element does not hold the token\'s icon')
                elseif same(e.rect,borrowed.rect)then
                    state=state or{}
                    state.token,state.borrowed,state.reason=token,borrowed,nil
                    S.slots[slot]=state
                elseif not same(e.rect,token.rect)then
                    reason_once(slot,'the slot icon element\'s rectangle is not the token sprite\'s (atlas data changed)')
                else
                    state=state or{times={}}
                    state.times=state.times or{}
                    local recent={}
                    for _,t in ipairs(state.times)do if now-t<REAPPLY_WINDOW then recent[#recent+1]=t end end
                    if#recent>=REAPPLY_LIMIT then
                        S.paused[slot]=true
                        log(('slot %d: paused: the game repainted it %d times within %d s'):format(slot,#recent,
                            REAPPLY_WINDOW))
                    else
                        local report,wwhy=write_rect(world,e,borrowed.rect,'loadout.slot'..slot..'.icon')
                        if report then
                            recent[#recent+1]=now
                            state.applied=(state.applied or 0)+1
                            if state.applied==1 then
                                log(('SLOT ICON: slot %d (virtual %s) shows %s\'s icon (vanilla, borrowed: atlas page %s, '
                                    ..'rectangle %.5f, %.5f, %.5f x %.5f) instead of the token\'s; %d writes (the element\'s '
                                    ..'rectangle and UV, its dirty bits); non-target bytes unchanged %s; protection '
                                    ..'restored %s; no StratagemInfo write: other slots holding %s keep its icon'):format(
                                    slot,v.definition,wanted.stratagem,borrowed.page,borrowed.rect[1],borrowed.rect[2],
                                    borrowed.rect[3],borrowed.rect[4],report.writes,
                                    tostring(report.non_target_bytes_unchanged),tostring(report.protection_restored),
                                    definition.selection.token))
                            elseif state.applied<=4 then
                                log(('slot %d icon re-applied after the game repainted the slots (%d)'):format(slot,
                                    state.applied))
                            end
                        else
                            reason_once(slot,wwhy)
                        end
                        state.times,state.token,state.borrowed=recent,token,borrowed
                        S.slots[slot]=state
                    end
                end
            end
        end
    end
    S.watch={status='active'}
    function S.watch.cancel()S.watch.status='cancelled'end
    function S.watch.tick(dt)if S.watch.status=='active'then tick(dt)end end
    scheduler.attach(S.watch)
    function S.set_enabled(on)
        S.enabled=on==true
        S.paused={}
        log(S.enabled and'on'or'off (each slot gets its own icon back)')
        return S.enabled
    end
    function S.status()
        local parts={}
        for slot=0,L.maxLoadoutEntries-1 do
            local state=S.slots[slot]
            if state and state.borrowed then parts[#parts+1]=('slot %d borrowed (%d applied)'):format(slot,state.applied or 0)
            elseif state and state.reason then parts[#parts+1]=('slot %d: %s'):format(slot,state.reason)end
            if S.paused[slot]then parts[#parts+1]=('slot %d paused'):format(slot)end
        end
        return(S.enabled and'on'or'off')..(#parts>0 and(': '..table.concat(parts,'; '))or'')
    end
    function S.stop()
        S.enabled=false
        tick(0)
        S.watch.cancel()
    end
    return S
end
M.uv_for=uv_for
-- A stratagem's icon as the slot icons read it (read-only; validation): {kind, name (8 bytes), colourSet, page, rect}.
M.icon=icon_of
return M
