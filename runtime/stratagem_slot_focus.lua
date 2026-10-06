-- The native loadout slot highlight (development only; docs/custom-stratagems.md, "Moving the native slot highlight").
-- Not exported by api/hd2.lua and no public field reaches it.
--
-- The highlight is the local panel's focus (research slotFocus): P = ui + panel holds the focused slot (P+0xD96C) and the
-- previous one (P+0xD970); each slot widget's flags (+0x1288) carry bit 1 = focused (bit 2 disabled, bit 3 selection
-- open). The native focus setter (0x1895770) stores them and calls the widget visual update 0x18932F0 on both widgets,
-- a pure function of the flags; nothing redraws them per frame. But every frame in panel mode 0 the panel update ends a
-- frame flash for each slot widget whose byte +0x12A0 is set and whose frame has no colour tween running: it clears the
-- byte and calls 0x18932F0 itself (0x1894C30..0x1894C57). So the focus is moved by data, in one guarded transaction:
--   the focus and the previous focus; bit 1 off on the old widget and on on the new one; optionally the edited slot
--   (ui+0x281C, where the next pick lands); last, the flash byte on both widgets.
-- On its next update the game redraws both widgets from their flags with its own code. The move is then verified (the
-- bytes consumed, the frame thickness and gap and, with the selection open, the frame and selected-element opacities as
-- 0x18932F0 leaves them) together with every other loadout field unchanged (the record, the edited slot unless moved,
-- the selection byte, the slot types, the cached record pointer); bytes not consumed in time are reverted.
-- No native call (the advance's close of a full loadout is stratagem_selector.close_native's), no hook, no input; no
-- record, save, account or StratagemInfo write.
-- Guards (refused with nothing written): the selector's pinned code; the loadout screen open with the local record;
-- solo; not ready or launched; panel mode 0, the local panel group active, its container bound, the panel local; no
-- repaint pending (the cached record pointer is the record); the current focus and the target 0-3 and different; the
-- old widget focused, the new one neither focused nor disabled, both in the same selection state; no flash pending and
-- no colour tween on either frame; the memory private read-write.
local world_module=require('hd2runtime/runtime/event_world')
local transaction=require('hd2runtime/core/guarded_transaction')
local selector=require('hd2runtime/runtime/stratagem_selector')
local scheduler=require('hd2runtime/runtime/scheduler')
local metrics=require('hd2runtime/runtime/metrics')
local log_module=require('hd2runtime/runtime/log')
local b=require('hd2runtime/core/bytes')
local D=require('hd2runtime/domains/stratagem_selector')
local L,F=D.loadout,D.slotFocus
local M={}
local CONSUME_TIMEOUT=1

local function log(text)log_module.emit('[HD2Runtime] slot focus '..text)end
local function u32(n)n=n%4294967296;return string.char(n%256,math.floor(n/256)%256,math.floor(n/65536)%256,math.floor(n/16777216)%256)end
local function signed(n)return n and n>=2147483648 and n-4294967296 or n end
local function byte(world,at)local s=world.view.read(at,1);return s and s:byte()end
local function qword(world,at)
    local s=world.view.read(at,8)
    return s and b.u32(s,0)+b.u32(s,4)*4294967296
end
local function f32(world,at)
    local s=world.view.read(at,4)
    if not s then return nil end
    local ok,v=pcall(b.value,s,0,'f32')
    return ok and v or nil
end
local function bit(n,mask)return math.floor((n or 0)/mask)%2==1 end
local function owner_of(world,address,size)
    local r=world.runtime.query and world.runtime.query(address)
    if not(r and r.state==0x1000 and r.type==0x20000 and r.protect==4 and address>=r.base and address+size<=r.base+r.size)
    then return nil end
    return {base=r.allocation_base,size=r.base+r.size-r.allocation_base,type=0x20000,protect=4}
end
local function widget_of(ui,slot)return ui+L.panel0Widgets+slot*L.widgetStride end

-- The highlight state as the game holds it (read-only): {panel, focus, previous, bound, localFlag, activeGroup,
-- container, widgets = {[slot] = {address, flags, flash, tween, thickness, gap, frameOpacity, selectedOpacity}}}.
function M.read(world,view)
    if not(view and view.open and view.ui)then return nil,'the loadout screen is not open'end
    local P=view.ui+F.panel
    local out={panel=P,focus=signed(world.view.u32(P+F.focus)),previous=signed(world.view.u32(P+F.previous)),
        bound=qword(world,P+F.boundRecord),localFlag=byte(world,P+F.localFlag),
        activeGroup=world.view.u32(view.ui+F.activeGroup),container=qword(world,view.ui+F.containerBound),widgets={}}
    if out.focus==nil or out.previous==nil or out.bound==nil or out.localFlag==nil or out.activeGroup==nil
            or out.container==nil then
        return nil,'the panel focus is unreadable'
    end
    for slot=0,L.maxLoadoutEntries-1 do
        local W=widget_of(view.ui,slot)
        local frame=W+F.frame
        local flags_bytes=world.view.read(W+F.widgetFlags,2)
        local frame_flags=world.view.u32(frame)
        local tween=world.view.u32(frame+F.colourTween)
        local w={address=W,flags=flags_bytes and b.u16(flags_bytes,0),flash=byte(world,W+F.flash),
            tween=frame_flags~=nil and tween~=nil and bit(frame_flags,F.colourTweenFlag)and tween%(F.tweenMask+1)~=0,
            thickness=f32(world,W+F.thickness),gap=f32(world,W+F.gap),frameOpacity=f32(world,frame+F.opacity),
            selectedOpacity=f32(world,W+F.selectedElement+F.opacity)}
        if w.flags==nil or w.flash==nil or frame_flags==nil or tween==nil then
            return nil,'slot widget '..slot..' is unreadable'
        end
        out.widgets[slot]=w
    end
    return out
end

-- Every other loadout field, for the before/after comparison: the record's entries and count, the edited slot, the
-- selection byte, the slot types and the cached record pointer.
local function others(world,view,with_edited)
    local record=view.record
    local parts={world.view.read(record.address+L.entries,L.count+4-L.entries)or'?',
        world.view.read(view.ui+L.selectionOpen,1)or'?',world.view.read(view.ui+F.panel+F.boundRecord,8)or'?'}
    if with_edited then parts[#parts+1]=world.view.read(view.ui+L.editedSlot,4)or'?'end
    for slot=0,L.maxLoadoutEntries-1 do
        parts[#parts+1]=world.view.read(widget_of(view.ui,slot)+L.widgetType,4)or'?'
    end
    return table.concat(parts,'|')
end

-- The checks before a move from the current focus to `target`: returns view, state or nil, code, reason.
local function check(world,target,opts)
    local game=world_module.game_state(world)
    if game and game.mission then return nil,'IN_MISSION','the loadout is edited aboard the ship'end
    local view,why=selector.screen(world)
    if not view then return nil,'UNAVAILABLE',why end
    if not view.open then return nil,'SCREEN_CLOSED','the loadout screen is not open'end
    if not view.record then return nil,'NO_RECORD','the local loadout record is not set'end
    if view.ready or view.launched then return nil,'READY','the player is ready or launched'end
    -- Several players: the local panel's focus only (the local group, the local flag and the bound record below).
    if view.panelMode~=0 then return nil,'PANEL_MODE','panel mode '..tostring(view.panelMode)..' (the update path differs)'end
    local st,st_why=M.read(world,view)
    if not st then return nil,'UNAVAILABLE',st_why end
    if st.activeGroup~=0 then return nil,'NOT_LOCAL_GROUP','the active panel group is '..st.activeGroup end
    if st.container==0 then return nil,'UNBOUND','the panel container is not bound (the panel update does not run)'end
    if st.localFlag~=1 then return nil,'NOT_LOCAL','the panel is not the local one'end
    if st.bound~=view.record.address then return nil,'REPAINT_PENDING','a slot repaint is pending'end
    local from=st.focus
    if not(type(target)=='number'and target%1==0 and target>=0 and target<L.maxLoadoutEntries)then
        return nil,'BAD_SLOT','the target slot must be 0-3'
    end
    if not(from>=0 and from<L.maxLoadoutEntries)then return nil,'NO_FOCUS','the focus is on slot '..from..', not 0-3'end
    if from==target then return nil,'SAME_SLOT','slot '..target..' already has the focus'end
    local a,z=st.widgets[from],st.widgets[target]
    if not bit(a.flags,F.focusedBit)then return nil,'STATE','the focused widget does not carry the focused bit'end
    if bit(z.flags,F.focusedBit)then return nil,'STATE','the target widget already carries the focused bit'end
    if bit(z.flags,F.disabledBit)then return nil,'DISABLED','slot '..target..' is disabled'end
    if bit(a.flags,F.selectionBit)~=bit(z.flags,F.selectionBit)then
        return nil,'STATE','the two widgets are in different selection states'
    end
    if a.flash~=0 or z.flash~=0 then return nil,'FLASH_PENDING','a frame flash is pending'end
    if a.tween or z.tween then return nil,'TWEEN','a frame colour tween is running'end
    if opts.edited then
        if not view.selecting then return nil,'NO_SELECTION','the edited slot moves only while a selection is open'end
        if view.editedSlot<0 or view.editedSlot>=L.maxLoadoutEntries then
            return nil,'NO_SELECTION','the edited slot is '..tostring(view.editedSlot)
        end
    end
    return view,st
end

local function plan_for(world,view,st,target,opts)
    local ui=view.ui
    local owner=owner_of(world,ui,F.containerBound+8)
    if not owner then return nil,'the loadout UI is not in private read-write memory'end
    local from=st.focus
    local a,z=st.widgets[from],st.widgets[target]
    local snapshots,changes={},{}
    local function snap(at,n)
        local bytes=world.view.read(at,n)
        if not bytes then error('unreadable context',0)end
        snapshots[#snapshots+1]={owner=owner,offset=at-owner.base,bytes=bytes}
    end
    local function change(label,at,expected,desired)
        if expected==desired then return end
        changes[#changes+1]={label=label,owner=owner,offset=at-owner.base,expected=expected,desired=desired,
            before=expected,already_desired=false,identity={component='LoadoutPanelFocus',component_type='native',
            unique_owner=true,owner_count=1},chain={}}
    end
    local ok,err=pcall(function()
        -- Contexts: the focus pair, both widgets' flags (with the type after them) and flash bytes, both frames' flags and
        -- colour-tween index, the cached record pointer, the local flag, the selection byte, the panel mode, the active
        -- group, the container, and with the edited slot the sub-state pair.
        snap(st.panel+F.focus,8)
        for _,w in ipairs({a,z})do
            snap(w.address+F.widgetFlags,8);snap(w.address+F.flash,4)
            snap(w.address+F.frame,4);snap(w.address+F.frame+F.colourTween,4)
        end
        snap(st.panel+F.boundRecord,8);snap(st.panel+F.localFlag,1)
        snap(ui+L.selectionOpen,1);snap(ui+L.panelMode,4);snap(ui+F.activeGroup,4);snap(ui+F.containerBound,8)
        if opts.edited then snap(ui+L.subState,8)end
    end)
    if not ok then return nil,tostring(err)end
    change('loadout.panel.focus',st.panel+F.focus,u32(from),u32(target))
    change('loadout.panel.previous_focus',st.panel+F.previous,u32(st.previous),u32(from))
    local fa,fz=a.flags%256,z.flags%256
    change('loadout.slot'..from..'.flags',a.address+F.widgetFlags,string.char(fa),string.char(fa-F.focusedBit))
    change('loadout.slot'..target..'.flags',z.address+F.widgetFlags,string.char(fz),string.char(fz+F.focusedBit))
    if opts.edited then change('loadout.selection.edited_slot',ui+L.editedSlot,u32(view.editedSlot),u32(target))end
    -- Last: the bytes the panel update consumes.
    change('loadout.slot'..from..'.flash',a.address+F.flash,string.char(0),string.char(1))
    change('loadout.slot'..target..'.flash',z.address+F.flash,string.char(0),string.char(1))
    return {snapshots=snapshots,changes=changes}
end

local function near(a,b_)return a~=nil and math.abs(a-b_)<1e-4 end
-- The widget state 0x18932F0 leaves: a focused frame 3 units with no gap, an unfocused one with a 16-unit gap; with the
-- selection open, the focused frame hidden and its selected element shown, the unfocused frame shown.
local function drawn(w,focused)
    if focused then
        if not(near(w.thickness,F.focusedThickness)and near(w.gap,F.focusedGap))then return false end
        if bit(w.flags,F.selectionBit)then return near(w.frameOpacity,0)and near(w.selectedOpacity,1)end
        return true
    end
    if not near(w.gap,F.unfocusedGap)then return false end
    if bit(w.flags,F.selectionBit)then return near(w.frameOpacity,1)and near(w.selectedOpacity,0)end
    return true
end

local function job(body,callback)
    local handle={status='pending'}
    local co=coroutine.create(body)
    local watch={status='active'}
    function watch.cancel()watch.status='cancelled'end
    function watch.tick(dt)
        local ok,result,code,reason=coroutine.resume(co,dt)
        if ok and coroutine.status(co)~='dead'then return end
        watch.status='complete'
        if not ok then handle.status,handle.code,handle.reason='failed','FOCUS_FAILED',tostring(result)
        elseif result then for key,value in pairs(result)do handle[key]=value end
        else handle.status,handle.code,handle.reason='refused',code,reason end
        if handle.status=='refused'or handle.status=='failed'then
            log('REFUSED (nothing written): '..tostring(handle.code)..': '..tostring(handle.reason))
        end
        if callback then callback(handle)end
    end
    scheduler.attach(watch)
    return handle
end

-- Moves the native highlight from the current focus to `target` (0-3). opts.edited: also move the edited slot (where the
-- next pick lands), only while a selection is open. Runs inside a job's coroutine (it waits for the game across frames):
-- returns {status = 'moved', from, to, edited, report, verified, all, others}, {status = 'reverted', ...} (the game did
-- not consume the bytes in time; everything put back), or nil, code, reason (refused, nothing written).
local function move_now(target,opts)
    opts=opts or{}
    local world,why=world_module.open()
    if not world then return nil,'UNAVAILABLE',tostring(why)end
    local ok,proof_why=selector.prove(world)
    if not ok then return nil,'UNSUPPORTED_BUILD',tostring(proof_why)end
    local view,st,reason=check(world,target,opts)
    if not view then return nil,st,reason end
    local before=others(world,view,not opts.edited)
    local plan,plan_why=plan_for(world,view,st,target,opts)
    if not plan then return nil,'RECORD_CHANGED',plan_why end
    local report=transaction.apply(world.runtime,plan)
    metrics.count('stratagem_slot_focus.transactions')
    if report.status~='APPLIED'then return nil,'GUARD_REJECTED',tostring(report.reason)end
    local from=st.focus
    -- The game's next panel updates consume the bytes and redraw both widgets.
    local waited,consumed,now=0,false,nil
    while waited<CONSUME_TIMEOUT do
        waited=waited+(coroutine.yield()or 0)
        local v=selector.screen(world)
        if not(v and v.open and v.ui==view.ui)then break end
        now=M.read(world,v)
        if now and now.widgets[from].flash==0 and now.widgets[target].flash==0 then consumed=true;break end
    end
    if not consumed then
        -- Put back what was written, while it is still what was written.
        local back={snapshots=plan.snapshots,changes={}}
        local v=selector.screen(world)
        local current=v and v.open and v.ui==view.ui and M.read(world,v)
        if current and current.focus==target then
            for _,c in ipairs(plan.changes)do
                local at=c.owner.base+c.offset
                local value=world.view.read(at,#c.desired)
                if value==c.desired then
                    back.changes[#back.changes+1]={label=c.label,owner=c.owner,offset=c.offset,expected=c.desired,
                        desired=c.expected,before=c.desired,already_desired=false,identity=c.identity,chain={}}
                end
            end
            -- The contexts are re-read now: they include the bytes being put back.
            for _,s in ipairs(back.snapshots)do
                s.bytes=world.view.read(s.owner.base+s.offset,#s.bytes)or s.bytes
            end
        end
        local undo=#back.changes>0 and transaction.apply(world.runtime,back)or nil
        log(('NOT CONSUMED: the panel update did not redraw the widgets within %d s; put back: %s'):format(
            CONSUME_TIMEOUT,undo and undo.status or'nothing to put back'))
        return {status='reverted',from=from,to=target,report=report,undo=undo}
    end
    local a,z=now.widgets[from],now.widgets[target]
    local verified={focus=now.focus==target,previous=now.previous==from,
        flags=not bit(a.flags,F.focusedBit)and bit(z.flags,F.focusedBit),oldDrawn=drawn(a,false),newDrawn=drawn(z,true)}
    local final=selector.screen(world)
    if opts.edited then verified.edited=final and final.editedSlot==target end
    local unchanged=final and others(world,final,not opts.edited)==before
    local all=true
    for _,v in pairs(verified)do if v~=true then all=false end end
    log(('MOVED: the native highlight went from slot %d to slot %d%s (%d writes: the focus, bit 1 on both widgets%s, '
        ..'the frame-flash byte on both); the game redrew both widgets: %s (focus %s, previous %s, flags %s, old '
        ..'frame %s, new frame %s%s); every other loadout field unchanged (record, %sselection, slot types, cached '
        ..'record pointer): %s; non-target bytes unchanged %s; protection restored %s'):format(from,target,
        opts.edited and' with the edited slot'or'',report.writes,opts.edited and', the edited slot'or'',
        tostring(all),tostring(verified.focus),tostring(verified.previous),tostring(verified.flags),
        tostring(verified.oldDrawn),tostring(verified.newDrawn),
        opts.edited and(', edited slot '..tostring(verified.edited))or'',opts.edited and''or'edited slot, ',
        tostring(unchanged),tostring(report.non_target_bytes_unchanged),tostring(report.protection_restored)))
    return {status='moved',from=from,to=target,edited=opts.edited==true,report=report,verified=verified,
        all=all,others=unchanged==true}
end
M.move_now=move_now
-- The same as a job: 'pending', then 'moved', 'reverted', or 'refused' / 'failed' with code and reason.
function M.move(target,callback,opts)
    return job(function()return move_now(target,opts)end,callback)
end

-- Refusals that can clear within a few frames (a flash or tween still running, the repaint not yet consumed).
local TRANSIENT={FLASH_PENDING=true,TWEEN=true,REPAINT_PENDING=true}
local RETRY=0.5
local function move_retrying(target,opts)
    local waited=0
    while true do
        local result,code,reason=move_now(target,opts)
        if result or not TRANSIENT[code]or waited>=RETRY then return result,code,reason end
        waited=waited+(coroutine.yield()or 0)
    end
end

-- The highlight back on the edited slot when they differ (the Runtime's record writes make the game's repaint put the
-- focus on slot 0): a highlight-only move. Inside a job's coroutine; returns the move's result, {status = 'in step'} or
-- nil, code, reason.
local function sync_now()
    local world=world_module.open()
    local view=world and selector.screen(world)
    if not(view and view.open and view.selecting)then return {status='in step',reason='no selection open'}end
    local st=M.read(world,view)
    if not st then return {status='in step',reason='the panel focus is unreadable'}end
    local edited=view.editedSlot
    if not(edited>=0 and edited<L.maxLoadoutEntries)or st.focus==edited then return {status='in step',slot=edited}end
    return move_retrying(edited,{})
end
M.sync_now=sync_now
function M.sync(callback)return job(sync_now,callback)end

-- The advance after a Runtime selection (stratagem_selector.select's opts.advance; inside its job): the native selector
-- moves on to the next empty slot after the one written (handle.next; never wrapping) with the proven slot-focus write:
-- the native highlight AND the edited slot, redrawn by the game's own panel update. The selection's record write has
-- made the game's repaint put the highlight on slot 0 first (its first bind), so the move goes from there. With no
-- empty slot left (the selection filled the last empty slot, or replaced one in a full loadout) the highlight is put
-- back on the edited slot (the last one written) and the native selector is closed as Back closes it
-- (stratagem_selector.close_native: the picker-close sound and the game's own close handler); when the close is
-- refused it stays open for Back. Returns {status = 'advanced' | 'closed' | 'full' | 'refused', slot, from, focus (the
-- move's result), close (the close's result), reason}.
function M.advance(world,view,handle)
    local from=handle.edited
    if handle.next==nil then
        local synced,code,reason=sync_now()
        local unsynced=synced and''or('; the highlight was not put back: '..tostring(code)..': '..tostring(reason))
        local closed=selector.close_native(world,view,handle)
        if closed.status=='closed'then
            return {status='closed',from=from,focus=synced,close=closed,verified=closed.verified,reason='no empty slot '
                ..'left after slot '..handle.index..': the native selector was closed as Back closes it'..unsynced}
        end
        return {status='full',from=from,focus=synced,close=closed,reason='no empty slot after slot '..handle.index
            ..': the native selector stays open; press Back (the close was refused: '..tostring(closed.reason)..')'
            ..unsynced}
    end
    local now=selector.screen(world)
    if not(now and now.open and now.ui==view.ui and now.selecting and now.editedSlot==from)then
        return {status='refused',from=from,reason='the native selector is no longer open for slot '..tostring(from)}
    end
    local st=M.read(world,now)
    if st and st.focus==handle.next then
        -- The highlight is already there: only the edited slot moves (the proven edited-slot write).
        local only=selector.advance(world,now,handle)
        only.focus={status='in step'}
        return only
    end
    local moved,code,reason=move_retrying(handle.next,{edited=true})
    if not moved then
        return {status='refused',from=from,reason=tostring(code)..': '..tostring(reason)}
    end
    if moved.status~='moved'then
        return {status='refused',from=from,focus=moved,reason='the game did not redraw the highlight in time (put back)'}
    end
    log(('ADVANCED: the native selector moved on from slot %d to slot %d, the next empty slot: the native highlight and '
        ..'the edited slot, redrawn by the game (verified %s)'):format(from,handle.next,tostring(moved.all)))
    return {status='advanced',slot=handle.next,from=from,focus=moved,verified=moved.all}
end

-- The state as text (the proof's F9).
function M.describe(world,view)
    local st,why=M.read(world,view)
    if not st then return'unavailable: '..tostring(why)end
    local parts={}
    for slot=0,L.maxLoadoutEntries-1 do
        local w=st.widgets[slot]
        parts[#parts+1]=('slot %d flags 0x%04X%s flash %d frame %.1f/%.1f opacity %s/%s'):format(slot,w.flags,
            bit(w.flags,F.focusedBit)and' (focused)'or'',w.flash,w.thickness or-1,w.gap or-1,
            w.frameOpacity and('%.2f'):format(w.frameOpacity)or'?',w.selectedOpacity and('%.2f'):format(w.selectedOpacity)or'?')
    end
    return('focus %d (previous %d), edited slot %s, selection %s, mode %s, group %d; %s'):format(st.focus,st.previous,
        tostring(view.editedSlot),tostring(view.selecting),tostring(view.panelMode),st.activeGroup,table.concat(parts,'; '))
end
return M
