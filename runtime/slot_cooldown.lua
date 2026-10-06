-- A converted slot's fixed cooldown (development only; docs/custom-stratagems.md, "The fixed cooldown"). Not exported by
-- api/hd2.lua and no public field reaches it.
--
-- research/slot-cooldown-F5FEE03DCFDB.json: a mission record entry's cooldown is its own. +0x10 is the activation, +0x18
-- the end (the entry is unavailable while it is above the game clock, 0x66D24A-0x66D25C) and +0x20 the call-in's
-- arrival: u64 game times in microseconds. A call writes end = arrival + the row's cooldown (+0x68) x the active
-- modifiers: the game counts a cooldown from the arrival. The HUD shows the slot inbound until the arrival, then cooling
-- while the end is above the clock; the bar takes the time left on its first cooling frame as its total.
-- rpc_sync_stratagems carries an entry's remaining cooldown to peers.
--
-- M.arm watches, every frame, the entries the slot conversion converted for one virtual definition
-- (stratagem_slot_conversion state). When the game starts a converted entry's cooldown (a NEW activation, its arrival
-- and an end after it above the clock), the same frame replaces that end with spec.seconds counted from the arrival
-- (the game's own rule), or with spec.from = 'now' from that frame's clock. An end that changes without that (no new
-- activation, or no cooldown after the arrival yet) is reported ('changed') and nothing is written: the game may write
-- a call in steps. One guarded 8-byte transaction, with the observed end as its exact
-- expectation and the record's peer id and whole entry block as context.
--
-- Guards (refused with nothing written; a refused call is never retried):
--   * the pins; in a mission, as host, solo;
--   * the conversion still holds the definition, its record (address and key) and the carrier in that entry;
--   * the carrier's row has cooldown type 0 (the entry's own, never copied between records) and unlimited uses, and so
--     has the entry;
--   * the game's write is coherent: activation <= clock <= activation + FRESH s, arrival >= activation, the end above
--     the arrival and the clock, at most twice the row's cooldown after the arrival;
--   * the new end is above the clock.
-- Afterwards the entry reads the new end and nothing else of the record changed. One write per call: a later change of
-- the end by the game is reported, never fought. Nothing is restored: the row's cooldown is never written, and the
-- record's ends are mission state that the game rebuilds.
local world_module=require('hd2runtime/runtime/event_world')
local transaction=require('hd2runtime/core/guarded_transaction')
local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
local loadout=require('hd2runtime/runtime/stratagem_loadout')
local scheduler=require('hd2runtime/runtime/scheduler')
local metrics=require('hd2runtime/runtime/metrics')
local log_module=require('hd2runtime/runtime/log')
local b=require('hd2runtime/core/bytes')
local profile=require('hd2runtime/schemas/current')
local catalog=require('hd2runtime/domains/stratagem_authoring')
local D=require('hd2runtime/domains/slot_cooldown')
local SD=require('hd2runtime/domains/stratagem_slots')
local HUD=require('hd2runtime/domains/stratagem_calldown').hud
local M={}
M.FRESH=10          -- seconds after the activation within which a call's cooldown is still overridden
M.MAX_SECONDS=3600
M.MAX_USES=100      -- calls per mission a slot may be limited to (spec.uses)
local R,ROWM,E=SD.record,SD.row,D.entry
local TABLE=profile.stratagem.table_rva
local US=D.clock.perSecond

local function log(text)log_module.emit('[HD2Runtime] slot cooldown '..text)end
local function u64(s,o)return b.u32(s,o)+b.u32(s,o+4)*4294967296 end
local function encode64(n)
    return b.encode(n%4294967296,'u32')..b.encode(math.floor(n/4294967296),'u32')
end
local function seconds(us)return us/US end
local function signed(n)return n and n>=2147483648 and n-4294967296 or n end

local proven={}
function M.prove(world)
    if D.source.gameDllSha256~=profile.dll_sha then return nil,'the slot cooldown research covers another game.dll build'end
    local ok,why=slots.prove(world)
    if not ok then return nil,why end
    if proven[world.game]then return true end
    for _,pin in ipairs(D.pins)do
        if not world.view.proves(world.game+pin.rva,pin.hex)then
            return nil,('slot cooldown code changed (%s at game+%X)'):format(pin.label,pin.rva)
        end
    end
    proven[world.game]=true
    return true
end

-- The game clock (microseconds), or nil.
function M.clock(world)
    local object=world.view.pointer(world.game+D.clock.global)
    local raw=object and world.view.read(object+D.clock.time,8)
    return raw and u64(raw,0)
end
-- An entry's times: {activation, finish, arrival, raw = the 8 end bytes}.
local function times(entry)
    return {activation=u64(entry.bytes,E.activation),finish=u64(entry.bytes,E.cooldownEnd),
        arrival=u64(entry.bytes,E.arrival),raw=entry.bytes:sub(E.cooldownEnd+1,E.cooldownEnd+8)}
end
local function row(world,kind)
    return type(kind)=='number'and kind>0 and kind<150 and world.view.pointer(world.game+TABLE+kind*8)or nil
end
-- Read-only: a stratagem type's cooldown (seconds) and cooldown type from its row, or nil.
function M.row_cooldown(world,kind)
    local r=row(world,kind)
    local raw=r and world.view.read(r+D.row.cooldown,4)
    if not raw then return nil end
    return b.value(raw,0,'f32'),world.view.u32(r+D.row.cooldownType)
end
local function name_of(world,kind)
    local id=loadout.id_of(world,kind)
    for name,entry in pairs(catalog.stratagems)do if entry.root and entry.root.id==id then return name end end
    return'type '..tostring(kind)
end

-- Read-only: what the in-mission HUD shows for record entry `index`: {type, inboundLeft, coolingLeft (seconds), state
-- (3 inbound, 4 cooling), total (the bar's total, taken on its first cooling frame)}, or nil and why.
function M.hud(world,index)
    local hud=world.view.pointer(world.game+HUD.global)
    local set_up=hud and world.view.read(hud+HUD.setUp,1)
    if not(set_up and set_up:byte()==1)then return nil,'the mission HUD is not set up'end
    local slot=hud+HUD.pathOffset+index*HUD.slots.stride
    local bar=slot+D.hud.bar
    if world.view.u32(slot+HUD.slots.index)~=index or world.view.u32(bar+D.hud.barIndex)~=index then
        return nil,'no HUD slot draws entry '..index
    end
    local function f32(at)
        local raw=world.view.read(at,4)
        local ok,value=pcall(b.value,raw or'',0,'f32')
        return ok and value or nil
    end
    return {type=world.view.u32(slot+HUD.slots.type),inboundLeft=f32(slot+D.hud.inboundLeft),
        coolingLeft=f32(slot+D.hud.coolingLeft),state=world.view.u32(bar+D.hud.barState),total=f32(bar+D.hud.barTotal)}
end

local function owner_of(world,address,size)
    local r=world.runtime.query and world.runtime.query(address)
    if not(r and r.state==0x1000 and r.type==0x20000 and r.protect==4 and address>=r.base and address+size<=r.base+r.size)
    then return nil end
    return {base=r.allocation_base,size=r.base+r.size-r.allocation_base,type=0x20000,protect=4}
end
-- The 8-byte end of entry `index`, with the record's peer id and its whole entry block and count as context.
local function plan_for(world,record,index,expected,desired)
    local first=record.state+R.entries
    local span=R.entryCount+4-R.entries
    local owner=owner_of(world,record.address,R.state+R.entryCount+4)
    local context=owner and world.view.read(first,span)
    local peer=owner and world.view.read(record.address,8)
    if not(owner and context and peer)then return nil end
    return {snapshots={{owner=owner,offset=record.address-owner.base,bytes=peer},
            {owner=owner,offset=first-owner.base,bytes=context}},
        changes={{label='stratagem.record.slot'..index..'.cooldownEnd',owner=owner,
            offset=record.entries[index+1].address+E.cooldownEnd-owner.base,expected=expected,desired=desired,
            before=expected,already_desired=false,
            identity={component='StratagemRecord',component_type='native',unique_owner=true,owner_count=1},chain={}}}}
end
-- Whether `after` equals `before` except entry `index`'s 8 end bytes.
local function only_the_end(before,after,index)
    if not after or after.count~=before.count then return false end
    for k,entry in ipairs(before.entries)do
        local now=after.entries[k].bytes
        if k-1==index then
            if now:sub(1,E.cooldownEnd)~=entry.bytes:sub(1,E.cooldownEnd)
                or now:sub(E.cooldownEnd+9)~=entry.bytes:sub(E.cooldownEnd+9)then return false end
        elseif now~=entry.bytes then return false end
    end
    return true
end

------------------------------------------------------------------------------------------------- the watch --
-- One armed override per virtual definition (several custom stratagems in one mission), by definition id: {spec,
-- callback, watch, record, key, carrier, carrier_name, slots = {[index] = loadout slot}, entries}.
local armed={}

local function emit(a,event)
    if a.callback then
        local ok,why=pcall(a.callback,event)
        if not ok then log('callback failed: '..tostring(why))end
    end
end

-- Every guard of one call's override, read in this frame. Returns the write context or nil, code, reason.
local function guards(world,a,index,now,clock,secs)
    local ok,why=M.prove(world)
    if not ok then return nil,'UNSUPPORTED_BUILD',tostring(why)end
    local game=world_module.game_state(world)
    if not(game and game.mission)then return nil,'NOT_IN_MISSION','the cooldown is written in a mission only'end
    -- This machine's OWN converted entry: the host, or a client inside the client-write proof.
    local hcode,hwhy=require('hd2runtime/runtime/multiplayer').host_guard(game,a.spec.client==true,
        'development proof: host only')
    if hcode then return nil,hcode,hwhy end
    local record,code,reason=slots.local_record(world)
    if not record then return nil,code,reason end
    -- The local player's own entry; the end reaches peers as a remaining time through the game's own sync.
    local scode,swhy=require('hd2runtime/runtime/multiplayer').solo_guard(record.records,a.spec.multiplayer==true,
        'the cooldown replicates to peers')
    if scode then return nil,scode,swhy end
    if record.address~=a.record or record.key~=a.key then
        return nil,'RECORD_CHANGED','the stratagem record is not the one the conversion wrote'
    end
    local entry=record.entries[index+1]
    if not(entry and entry.type==a.carrier)then
        return nil,'NOT_THE_CARRIER',('entry %d no longer holds the converted carrier %s'):format(index,a.carrier_name)
    end
    -- Unlimited, or (the carrier-in-slot probe) the slot's own native count, 0 to the number its adoption wrote.
    if not(entry.uses==-1 or(a.native_uses and entry.uses>=0 and entry.uses<=a.native_uses))then
        return nil,'USES_DIFFER','entry '..index..' does not have unlimited uses (nor its own native count)'
    end
    local r=row(world,a.carrier)
    if not(r and signed(world.view.u32(r+ROWM.maxUses))==-1)then
        return nil,'USES_DIFFER',a.carrier_name..' does not have unlimited uses'
    end
    local cooldown,kind=M.row_cooldown(world,a.carrier)
    if kind~=0 then
        return nil,'SHARED_COOLDOWN',a.carrier_name..'\'s cooldown type is '..tostring(kind)..' (shared between records)'
    end
    if not(cooldown and cooldown>0)then return nil,'NO_COOLDOWN',a.carrier_name..' has no row cooldown'end
    if not clock then return nil,'UNAVAILABLE','the game clock is unreadable'end
    if not(now.activation>0 and now.activation<=clock)then
        return nil,'NO_ACTIVATION','the entry\'s end changed without an activation before the clock'
    end
    if clock-now.activation>M.FRESH*US then
        return nil,'STALE',('the call was activated %.1f s ago (at most %d s)'):format(seconds(clock-now.activation),M.FRESH)
    end
    if not(now.arrival>=now.activation and now.finish>now.arrival and now.finish>clock)then
        return nil,'NOT_A_COOLDOWN','the game\'s write is not a cooldown after the arrival above the clock'
    end
    if now.finish-now.arrival>2*cooldown*US then
        return nil,'NOT_A_COOLDOWN',('the game\'s cooldown (%.3f s after the arrival) is more than twice %s\'s %g s')
            :format(seconds(now.finish-now.arrival),a.carrier_name,cooldown)
    end
    local base=a.spec.from=='now'and clock or now.arrival
    local desired=base+math.floor(secs*US+0.5)
    if desired<=clock then return nil,'TOO_LATE','the new end would not be above the clock'end
    return {record=record,entry=entry,cooldown=cooldown,base=base,desired=desired}
end

-- One call's override, in the frame it was seen: its end `secs` after the arrival (or the clock).
local function override(world,a,index,now,clock,secs)
    local event={kind='refused',index=index,slot=a.slots[index],carrier=a.carrier_name,activation=now.activation,
        arrival=now.arrival,gameEnd=now.finish,clock=clock,from=a.spec.from or'arrival',seconds=secs}
    event.rowCooldown=M.row_cooldown(world,a.carrier)
    local ctx,code,reason=guards(world,a,index,now,clock,secs)
    if not ctx then
        event.code,event.reason=code,reason
        log(('refused (entry %d, nothing written): %s: %s'):format(index,tostring(code),tostring(reason)))
        return event
    end
    local plan=plan_for(world,ctx.record,index,now.raw,encode64(ctx.desired))
    if not plan then
        event.code,event.reason='RECORD_CHANGED','the stratagem record is not in private read-write memory'
        return event
    end
    local report=transaction.apply(world.runtime,plan)
    metrics.count('slot_cooldown.transactions')
    if report.status~='APPLIED'then
        event.code,event.reason='GUARD_REJECTED',tostring(report.reason)
        log(('refused (entry %d): GUARD_REJECTED: %s'):format(index,tostring(report.reason)))
        return event
    end
    local after=slots.local_record(world)
    local written=after and after.entries[index+1]and u64(after.entries[index+1].bytes,E.cooldownEnd)
    event.kind,event.desired,event.writes,event.base='overridden',ctx.desired,report.writes,ctx.base
    event.verify={finish=written==ctx.desired,others=only_the_end(ctx.record,after,index),
        nonTarget=report.non_target_bytes_unchanged==true,protection=report.protection_restored==true}
    log(('OVERRIDDEN: entry %d (%s): end %d -> %d (%g s from the %s; the game\'s: %.3f s after the arrival, row %g s); '
        ..'%d write; the entry reads it: %s; nothing else changed: %s; non-target bytes unchanged %s; protection restored '
        ..'%s'):format(index,a.carrier_name,now.finish,ctx.desired,secs,event.from=='now'and'current game time'
        or'arrival',seconds(now.finish-now.arrival),ctx.cooldown,report.writes,tostring(event.verify.finish),
        tostring(event.verify.others),tostring(event.verify.nonTarget),tostring(event.verify.protection)))
    return event
end

local function finish(a,reason)
    emit(a,{kind='ended',reason=reason})
    a.watch.status='complete'
    if armed[a.spec.definition]==a then armed[a.spec.definition]=nil end
end

local function tick(a)
    local world=world_module.open()
    if not world then return end
    local game=world_module.game_state(world)
    local conv=slots.state(a.spec.definition)
    local held=conv and conv.converted and conv.definition==a.spec.definition
    if not held then
        if a.record then return finish(a,'the conversion is gone (the record was rebuilt or the slot returned)')end
        if not(game and game.mission)then return finish(a,'the mission ended before a conversion')end
        return
    end
    if not a.record then
        -- The conversion seen for the first time: its record, carrier and slots, and each entry's end as recorded.
        a.record,a.key,a.carrier,a.carrier_name=conv.record,conv.key,conv.carrier,conv.carrier_name
        -- The carrier-in-slot probe's native per-slot uses (stratagem_slot_conversion adopt_virtual spec.uses): its
        -- entries count down from that number by the game itself.
        a.native_uses=conv.adopted and conv.native_uses or nil
        a.slots,a.entries={},{}
        for k,index in ipairs(conv.indices)do
            a.slots[index]=conv.slots and conv.slots[k]
            a.entries[index]={phase='idle',raw=conv.cooldowns and conv.cooldowns[index]}
        end
        local cooldown,kind=M.row_cooldown(world,a.carrier)
        emit(a,{kind='armed',carrier=a.carrier_name,type=a.carrier,id=loadout.id_of(world,a.carrier),indices=conv.indices,
            slots=a.slots,rowCooldown=cooldown,cooldownType=kind,clock=M.clock(world),seconds=a.spec.seconds,
            from=a.spec.from or'arrival'})
        if a.spec.carrier and a.spec.carrier~=conv.carrier_name then
            emit(a,{kind='refused',code='NOT_THE_CARRIER',reason=('the conversion holds %s, not %s'):format(
                tostring(conv.carrier_name),a.spec.carrier)})
            return finish(a,'refused: not the expected carrier')
        end
    end
    if conv.record~=a.record or conv.carrier~=a.carrier then
        return finish(a,'the conversion changed')
    end
    local record=slots.local_record(world)
    if not record then return end
    local clock=M.clock(world)
    for index,s in pairs(a.entries)do
        local entry=record.entries[index+1]
        if entry and entry.type==a.carrier then
            local now=times(entry)
            if s.phase=='idle'then
                if s.raw==nil then s.raw=now.raw end
                if now.raw~=s.raw and clock and now.finish>clock then
                    -- A call's cooldown start is a NEW activation (after the last one handled) with its arrival and an
                    -- end after it. Anything less is not written and the watch goes on: the game may write in steps.
                    local new=now.activation>0 and now.activation<=clock and(s.activation==nil
                        or now.activation>s.activation)
                    local why=not new and'the end changed without a new activation'
                        or not(now.arrival>=now.activation and now.finish>now.arrival)
                        and'the arrival and the end are not a cooldown after the arrival (yet)'
                    if why then
                        emit(a,{kind='changed',index=index,slot=a.slots[index],reason=why,activation=now.activation,
                            arrival=now.arrival,finish=now.finish,clock=clock})
                        s.raw=now.raw
                    else
                        -- The game started this entry's cooldown: a call. With spec.uses, the call that uses the last
                        -- of them ends the slot's cooldown M.MAX_SECONDS after it (longer than any mission: the slot
                        -- stays unavailable); every earlier one takes spec.seconds, or the game's own cooldown.
                        a.calls=(a.calls or 0)+1
                        local depleted=a.spec.uses~=nil and a.calls>=a.spec.uses
                        local secs=depleted and M.MAX_SECONDS or a.spec.seconds
                        local event
                        if secs then
                            event=override(world,a,index,now,clock,secs)
                        else
                            event={kind='call',index=index,slot=a.slots[index],carrier=a.carrier_name,
                                activation=now.activation,arrival=now.arrival,gameEnd=now.finish,clock=clock}
                        end
                        event.calls,event.uses,event.depleted=a.calls,a.spec.uses,depleted
                        s.phase,s.activation=('cooling'),now.activation
                        s.call={activation=now.activation,arrival=now.arrival,gameEnd=now.finish,clock=clock,
                            finish=event.kind=='overridden'and event.desired or now.finish,
                            overridden=event.kind=='overridden',depleted=depleted}
                        s.raw=encode64(s.call.finish)
                        emit(a,event)
                    end
                elseif now.raw~=s.raw then
                    s.raw=now.raw   -- an end at or below the clock: no cooldown to override (nothing written)
                end
            elseif s.phase=='cooling'then
                local c=s.call
                if now.raw~=s.raw then
                    emit(a,{kind='rewritten',index=index,slot=a.slots[index],expected=c.finish,value=now.finish,
                        activation=now.activation,arrival=now.arrival,clock=clock})
                    log(('entry %d\'s end changed after the override: %d -> %d (not written again)'):format(index,
                        c.finish,now.finish))
                    s.raw,c.finish=now.raw,now.finish
                end
                if not c.hud then
                    local h=M.hud(world,index)
                    if h and h.state==D.hud.cooling and h.total and h.total>0 then
                        c.hud=true
                        emit(a,{kind='hud',index=index,slot=a.slots[index],total=h.total,coolingLeft=h.coolingLeft,
                            clock=clock,expected=clock and seconds(c.finish-clock),finish=c.finish,arrival=c.arrival,
                            overridden=c.overridden})
                    end
                end
                if clock and clock>=c.finish then
                    emit(a,{kind='ready',index=index,slot=a.slots[index],clock=clock,finish=c.finish,
                        activation=c.activation,arrival=c.arrival,writeClock=c.clock,overridden=c.overridden})
                    s.phase,s.call,s.raw='idle',nil,now.raw
                end
            end
        end
    end
end

-- Arms the fixed cooldown for the slots of one virtual definition. spec: {definition = id, seconds = (0, MAX_SECONDS],
-- from = 'arrival' (default: the game's rule) or 'now', carrier = name (optional: refused if the conversion holds
-- another), uses = 1..MAX_USES (optional: calls this mission; the last one's cooldown is MAX_SECONDS, so the slot is
-- spent for the mission; seconds may then be nil, every earlier call keeping the game's own cooldown)}. Calls are
-- counted from this machine's own entry: with several players each player's own calls. Watches every frame until the conversion is gone; may be armed before the conversion. callback(event):
-- 'armed' (the conversion seen: carrier, type, id, indices, slots, rowCooldown, cooldownType), 'changed' (the end
-- changed, not yet a cooldown start: reason, activation, arrival, finish; nothing written), 'overridden' or
-- 'refused' (one call: index, slot, activation, arrival, gameEnd, clock, rowCooldown, desired, verify or code,
-- reason), 'rewritten' (the end changed again after it), 'hud' (the first cooling frame: total, coolingLeft), 'ready'
-- (available again: clock, finish), 'ended'. Returns the watch, or nil and why.
function M.arm(spec,callback)
    if type(spec)~='table'or type(spec.definition)~='string'then return nil,'spec must name the virtual definition'end
    if spec.uses~=nil and not(type(spec.uses)=='number'and spec.uses%1==0 and spec.uses>=1 and spec.uses<=M.MAX_USES)then
        return nil,'spec.uses must be a whole number from 1 to '..M.MAX_USES
    end
    if not(spec.seconds==nil and spec.uses~=nil)
            and(type(spec.seconds)~='number'or spec.seconds<=0 or spec.seconds>M.MAX_SECONDS)then
        return nil,'spec.seconds must be in (0, '..M.MAX_SECONDS..']'..(spec.uses and' or nil (the game\'s own)'or'')
    end
    if spec.from~=nil and spec.from~='arrival'and spec.from~='now'then return nil,"spec.from must be 'arrival' or 'now'"end
    local before=armed[spec.definition]
    if before then before.watch.status='cancelled';armed[spec.definition]=nil end
    local a={spec=spec,callback=callback}
    local watch={status='active'}
    function watch.cancel()watch.status='cancelled';if armed[spec.definition]==a then armed[spec.definition]=nil end end
    function watch.tick()if watch.status=='active'then tick(a)end end
    a.watch=watch
    armed[spec.definition]=a
    scheduler.attach(watch)
    return watch
end
-- definition nil: whether ANY definition's override is armed (and disarm() disarms every one).
function M.armed(definition)
    if definition~=nil then local a=armed[definition];return a~=nil and a.watch.status=='active'end
    for _,a in pairs(armed)do if a.watch.status=='active'then return true end end
    return false
end
function M.disarm(definition)
    if definition~=nil then if armed[definition]then armed[definition].watch.cancel()end;return end
    local list={}
    for _,a in pairs(armed)do list[#list+1]=a end
    for _,a in ipairs(list)do a.watch.cancel()end
end
------------------------------------------------------------------------------------------------- the lockout --
-- FAIL CLOSED (0.30, the user's release rule): a custom stratagem slot that will not run in this mission (custom
-- stratagems disabled lobby-wide by an incompatible registry, or its setup refused) still holds its token, Orbital
-- Precision Strike, which must NEVER be called. Its own record entry's cooldown end is set far above the game clock
-- (the same guarded 8-byte write of this machine's OWN entry as the override above, live on clients) and set again
-- before it runs out; the game itself then refuses the call (an entry is unavailable while its end is above the clock,
-- 0x66D24A-0x66D25C). Guards: the pins; in a mission; the host, or a client with the orchestrator's lockout mark
-- (runtime/multiplayer.lua); the local record; the entry holds the token with unlimited uses; the token's row cooldown
-- type 0 (the entry's own, never shared between records); the game clock. Afterwards the entry reads the new end and
-- nothing else of the record changed. Nothing is restored: the record is mission state the game rebuilds.
M.LOCK_SECONDS=3600       -- the lock's length (re-applied before it runs out)
M.RELOCK_BELOW=900        -- seconds left below which the lock is set again
M.RELOCK_EVERY=5          -- seconds between two checks of a lock
-- One lock now. spec = {index (record entry), token (its stratagem type), client ('lockout' on a client), label}.
-- Returns {kind = 'locked' | 'held', desired, verified, writes} or nil, code, reason.
function M.lock_entry(world,spec)
    local ok,why=M.prove(world)
    if not ok then return nil,'UNSUPPORTED_BUILD',tostring(why)end
    local game=world_module.game_state(world)
    if not(game and game.mission)then return nil,'NOT_IN_MISSION','a lock is written in a mission only'end
    local hcode,hwhy=require('hd2runtime/runtime/multiplayer').host_guard(game,spec.client,
        'a lockout of this machine\'s own entry')
    if hcode then return nil,hcode,hwhy end
    local record,code,reason=slots.local_record(world)
    if not record then return nil,code,reason end
    local entry=record.entries[spec.index+1]
    if not(entry and entry.type==spec.token)then
        return nil,'NOT_THE_TOKEN',('entry %d does not hold the token (type %s)'):format(spec.index,tostring(spec.token))
    end
    if entry.uses~=-1 then return nil,'USES_DIFFER','entry '..spec.index..' does not have unlimited uses'end
    local _,kind=M.row_cooldown(world,spec.token)
    if kind~=0 then return nil,'SHARED_COOLDOWN','the token\'s cooldown type is '..tostring(kind)..' (shared)'end
    local clock=M.clock(world)
    if not clock then return nil,'UNAVAILABLE','the game clock is unreadable'end
    local now=times(entry)
    if now.finish>clock+M.RELOCK_BELOW*US then return {kind='held',desired=now.finish,verified=true,writes=0}end
    local desired=clock+M.LOCK_SECONDS*US
    local plan=plan_for(world,record,spec.index,now.raw,encode64(desired))
    if not plan then return nil,'RECORD_CHANGED','the stratagem record is not in private read-write memory'end
    local report=transaction.apply(world.runtime,plan)
    metrics.count('slot_cooldown.transactions')
    if report.status~='APPLIED'then return nil,'GUARD_REJECTED',tostring(report.reason)end
    local after=slots.local_record(world)
    local written=after and after.entries[spec.index+1]and u64(after.entries[spec.index+1].bytes,E.cooldownEnd)
    return {kind='locked',desired=desired,writes=report.writes,raw_before=now.raw,raw_desired=encode64(desired),
        verified=written==desired and only_the_end(record,after,spec.index)}
end
-- THE CARRIER-IN-SLOT PROBE's release (runtime/carrier_in_slot.lua): a lock it set at the mission's first update, while
-- the slot was not yet its custom stratagem's, written back once the custom stratagem is ready to call. spec = {index,
-- token (the entry's type: its carrier), locked (the 8 end bytes the lock wrote), original (the 8 end bytes before it),
-- label}. Only while the entry still reads exactly the lock's end (else nothing: the game or another writer changed
-- it). One guarded 8-byte write of this machine's OWN entry, the same as the lock. Returns {writes, verified} or nil,
-- code, reason.
function M.unlock_entry(world,spec)
    local ok,why=M.prove(world)
    if not ok then return nil,'UNSUPPORTED_BUILD',tostring(why)end
    local game=world_module.game_state(world)
    if not(game and game.mission)then return nil,'NOT_IN_MISSION','a lock is released in a mission only'end
    local hcode,hwhy=require('hd2runtime/runtime/multiplayer').host_guard(game,spec.client,
        'a release of this machine\'s own entry')
    if hcode then return nil,hcode,hwhy end
    local record,code,reason=slots.local_record(world)
    if not record then return nil,code,reason end
    local entry=record.entries[spec.index+1]
    if not(entry and entry.type==spec.token)then
        return nil,'NOT_THE_CARRIER',('entry %d does not hold type %s'):format(spec.index,tostring(spec.token))
    end
    local now=entry.bytes:sub(E.cooldownEnd+1,E.cooldownEnd+8)
    if now~=spec.locked then return nil,'NOT_LOCKED','entry '..spec.index..' no longer reads the lock\'s end'end
    local plan=plan_for(world,record,spec.index,now,spec.original)
    if not plan then return nil,'RECORD_CHANGED','the stratagem record is not in private read-write memory'end
    local report=transaction.apply(world.runtime,plan)
    metrics.count('slot_cooldown.transactions')
    if report.status~='APPLIED'then return nil,'GUARD_REJECTED',tostring(report.reason)end
    local after=slots.local_record(world)
    local written=after and after.entries[spec.index+1]and after.entries[spec.index+1].bytes:sub(E.cooldownEnd+1,
        E.cooldownEnd+8)
    return {writes=report.writes,verified=written==spec.original and only_the_end(record,after,spec.index)}
end
-- A lock kept for the mission: checked every RELOCK_EVERY s (set again before it runs out), ended with the mission.
-- on_event(e) gets {kind = 'locked' | 'refused' | 'ended', ...}. Returns the watch.
local locks={}
function M.lock(spec,on_event)
    local w={status='active',elapsed=0,spec=spec}
    local function emit(e)if on_event then pcall(on_event,e)end end
    local function check()
        local world=world_module.open()
        if not world then return end
        local game=world_module.game_state(world)
        if not(game and game.mission)then w.status='complete';emit({kind='ended'});return end
        local r,code,reason=M.lock_entry(world,spec)
        if r and r.kind=='locked'then emit({kind='locked',index=spec.index,desired=r.desired,verified=r.verified,
            writes=r.writes})
        -- Already held far ahead (another lock of this entry, e.g. the carrier-in-slot probe's early lock).
        elseif r and r.kind=='held'then emit({kind='held',index=spec.index,desired=r.desired,verified=true,writes=0})
        elseif not r then emit({kind='refused',index=spec.index,code=code,reason=reason})end
    end
    function w.tick(dt)
        if w.status~='active'then return end
        w.elapsed=w.elapsed+(dt or 0)
        if w.first==nil or w.elapsed-w.first>=M.RELOCK_EVERY then w.first=w.elapsed;check()end
    end
    function w.cancel()w.status='cancelled'end
    locks[#locks+1]=w
    -- The first lock in this very update (the slot must never be callable).
    w.first=0
    check()
    if w.status=='active'then scheduler.attach(w)end
    return w
end
function M.reset_for_tests()
    for _,a in pairs(armed)do a.watch.status='cancelled'end
    for _,w in ipairs(locks)do w.status='cancelled'end
    armed,locks,proven={},{},{}
end
return M
