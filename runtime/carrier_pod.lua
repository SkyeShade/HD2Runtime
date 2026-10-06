-- A custom stratagem's CARRIER POD: what its carrier's OWN hellpod rack holds for one mission (development;
-- docs/research/carrier-pod-items-F5FEE03DCFDB.md, sections 1, 2, 6 and 11; docs/custom-stratagem-api.md "Carrier
-- groups" and "pod"). Not exported by api/hd2.lua.
--
-- The carrier is a support (or backpack) stratagem nobody in the lobby brings, and its rack record
-- (HellpodRackComponentData) has exactly ONE owner entity and ONE consumer row, the carrier itself
-- (domains/carrier_pod_items.lua: the exclusive carrier racks). Under the carrier rule its item list is then
-- carrier-local, so it is written for the mission:
--   * only the RackAttach item (+0, a u64 as two aligned dwords) of each slot: the custom stratagem's items fill the
--     rack's USABLE slots (inside spawn_payload_size, a node of the rack unit, distinct nodes) in order, each in a slot
--     whose ROLE takes its kind (weapon: support weapons, the clone, primaries; backpack: backpacks); every other slot
--     that holds an item is written EMPTY (so a count raised by an upgrade spawns nothing extra); nodes, sides,
--     apply_deltas, the sizes and +560 are never written (no spawn-count write in this pass);
--   * at mission start, before the carrier can be called (no pod of the carrier type may exist: the spawner reads the
--     list only inside a rack's creation, research "rackSpawner"), never after a call;
--   * re-proved right before the write: the build pins, the record identity (record index, index row) and ONE owner,
--     random_payload_size 0, +560 clear, every slot exactly its reviewed vanilla bytes (item and node: no other writer),
--     exactly one live StratagemInfo row naming the rack (its carrier, as its primary payload), every item package
--     resident;
--   * restored byte for byte aboard the ship (restore() a job, restore_now() in one tick for the loadout-screen
--     boundary), only where a slot still holds what was written (CONFLICT otherwise), then verified exactly the vanilla
--     bytes; a finalizer restores before this Lua state closes.
-- One guarded transaction (the entity region's PAGE_READONLY handling, read-back, non-target bytes unchanged,
-- protection restored).
if rawget(_G,'jit')then jit.off(true,true)end
local world_module=require('hd2runtime/runtime/event_world')
local transaction=require('hd2runtime/core/guarded_transaction')
local Reader=require('hd2runtime/runtime/reader')
local scheduler=require('hd2runtime/runtime/scheduler')
local metrics=require('hd2runtime/runtime/metrics')
local log_module=require('hd2runtime/runtime/log')
local core_assets=require('hd2runtime/core/assets')
local b=require('hd2runtime/core/bytes')
local D=require('hd2runtime/domains/carrier_pod_items')
local M={}
M.EMPTY='0x0000000000000000'
M.CLONE='clone'
local R=D.record

local function log(text)log_module.emit('[HD2Runtime] carrier pod '..text)end
local function u64(resource)
    local hex=tostring(resource):gsub('^0x','')
    local out={}
    for index=15,1,-2 do out[#out+1]=string.char(tonumber(hex:sub(index,index+1),16))end
    return table.concat(out)
end
local function hex_of(bytes)return('0x%08X%08X'):format(b.u32(bytes,4),b.u32(bytes,0))end

----------------------------------------------------------------------------------------------- the catalogue --
-- The exclusive carrier rack of a carrier stratagem (its reviewed slots, roles and capacity), or nil.
function M.rack(carrier)return D.racks[carrier]end
-- Its capacity: usable slots inside the spawn count (0 when it has no exclusive rack).
function M.capacity(carrier)local r=D.racks[carrier];return r and r.capacity or 0 end
-- Every carrier with an exclusive rack, sorted.
function M.carriers()
    local out={}
    for name in pairs(D.racks)do out[#out+1]=name end
    table.sort(out)
    return out
end
function M.kinds()return D.kinds end
-- A pod item reference -> {key, label, kind, role, resource, status} or nil and why. ref: a typed handle
-- (hd2.support_weapon(name), hd2.backpack(name), hd2.weapon(name) for a primary), or a name (a support weapon, else a
-- backpack). 'clone' is the orchestrator's (an expendable carrier weapon), never resolved here.
function M.item(ref)
    local key
    if type(ref)=='table'then
        local resource=rawget(ref,'resource')
        if resource=='support_weapon'then key='support_weapon/'..tostring(rawget(ref,'weapon'))
        elseif resource=='backpack'then key='backpack/'..tostring(rawget(ref,'backpack'))
        elseif resource=='player_weapon'or resource=='weapon'then key='player_weapon/'..tostring(rawget(ref,'weapon'))
        elseif rawget(ref,'backpack')then key='backpack/'..tostring(rawget(ref,'backpack'))
        elseif rawget(ref,'weapon')then key='support_weapon/'..tostring(rawget(ref,'weapon'))end
    elseif type(ref)=='string'then
        key=D.items['support_weapon/'..ref]and('support_weapon/'..ref)or('backpack/'..ref)
    end
    local entry=key and D.items[key]
    if not entry then
        return nil,'not a catalogued pod item (a typed handle: hd2.support_weapon(name), hd2.backpack(name), or '
            ..'hd2.weapon(name) for a primary): '..tostring(key or ref)
    end
    local kind=D.kinds[entry.kind]
    if not entry.supported then
        return nil,('%s cannot be a pod item: %s (%s, %s)'):format(entry.label,kind and kind.doc or entry.kind,
            entry.verdict,entry.confidence)
    end
    return {key=key,label=entry.label,kind=entry.kind,role=kind.role,resource=entry.resource,status=kind.status}
end

-- The slot plan of a carrier's rack for an ordered list of item units ({{role, resource, label, key}}, one per spawned
-- item): {carrier, rack, slots = {[index] = {resource, label, role}}, desired = {[index] = resource} (every slot
-- written), layout = {{slot, resource, label}}, writes (slots whose item changes), capacity}, or nil, code, reason.
function M.plan(carrier,units)
    local rack=D.racks[carrier]
    if not rack then return nil,'NO_EXCLUSIVE_RACK',tostring(carrier)..' has no exclusive carrier rack'end
    if type(units)~='table'or#units==0 then return nil,'INVALID','a pod holds at least one item'end
    if#units>rack.capacity then
        return nil,'CAPACITY',('%s\'s pod holds at most %d item%s (its usable rack slots); %d asked'):format(carrier,
            rack.capacity,rack.capacity==1 and''or's',#units)
    end
    local taken,layout={},{}
    for k,unit in ipairs(units)do
        local placed
        for _,index in ipairs(rack.usable)do
            local slot=rack.slots[index+1]
            if not placed and not taken[index]and slot.role==unit.role then placed=index end
        end
        if not placed then
            return nil,'ROLE',('%s\'s pod has no free %s slot for item %d (%s): its usable slots hold %s'):format(carrier,
                tostring(unit.role),k,tostring(unit.label),table.concat(rack.roles,', '))
        end
        taken[placed]={resource=unit.resource,label=unit.label,role=unit.role,key=unit.key}
        layout[#layout+1]={slot=placed,resource=unit.resource,label=unit.label}
    end
    table.sort(layout,function(a,c)return a.slot<c.slot end)
    local desired,writes={},0
    for _,slot in ipairs(rack.slots)do
        local want=taken[slot.index]and taken[slot.index].resource or M.EMPTY
        desired[slot.index]=want
        if want~=slot.item then writes=writes+1 end
    end
    return {carrier=carrier,rack=rack,slots=taken,desired=desired,layout=layout,writes=writes,capacity=rack.capacity}
end

---------------------------------------------------------------------------------------------------- state --
local states={}           -- by carrier: {applied, restored, carrier, plan, changes, record = {owner, offset, size}}
local sentinel
local restoring={}
local function held(s)return s~=nil and s.applied and not s.restored end
local function run(body,now)
    local co=coroutine.create(body)
    for _=1,100000 do
        local ok,result,code,reason=coroutine.resume(co)
        if not ok then return nil,'FAILED',tostring(result)end
        if coroutine.status(co)=='dead'then return result,code,reason end
        if not now then coroutine.yield()end
    end
    return nil,'FAILED','the operation did not finish'
end
local function job(body,callback)
    local handle={status='pending'}
    local co=coroutine.create(body)
    local watch={status='active'}
    function watch.cancel()watch.status='cancelled'end
    handle.watch=watch
    function watch.tick()
        if watch.status~='active'then return end
        local ok,result,code,reason=coroutine.resume(co)
        if ok and coroutine.status(co)~='dead'then return end
        watch.status='complete'
        if not ok then handle.status,handle.code,handle.reason='failed','FAILED',tostring(result)
        elseif result then for key,value in pairs(result)do handle[key]=value end
        else handle.status,handle.code,handle.reason='refused',code,reason end
        if handle.status~='applied'and handle.status~='restored'then
            log('refused: '..tostring(handle.code)..': '..tostring(handle.reason))
        end
        if callback then callback(handle)end
    end
    scheduler.attach(watch)
    return handle
end
local restore_body
local function finalize()
    local list={}
    for carrier,s in pairs(states)do if held(s)then list[#list+1]=carrier end end
    table.sort(list)
    for _,carrier in ipairs(list)do pcall(run,function()return restore_body(true,carrier)end,true)end
end
local function arm()
    if sentinel then return end
    local ok,ffi=pcall(require,'ffi')
    if ok then sentinel=ffi.gc(ffi.new('uint8_t[1]'),function()pcall(finalize)end)end
end
local function disarm()
    for _,s in pairs(states)do if held(s)then return end end
    if sentinel then pcall(function()require('ffi').gc(sentinel,nil)end);sentinel=nil end
end

---------------------------------------------------------------------------------------------------- proofs --
-- The rack record as the game holds it now, every guard re-proved: {record (bytes, owner, offset), rack} or nil,
-- code, reason. Inside a coroutine (the reader yields): the catalog captures run in a nested coroutine.
local function capture(world,carrier)
    local rack=D.racks[carrier]
    local PP=require('hd2runtime/domains/pod_payload_authoring')
    local name=PP.byStratagem[carrier]
    if not(name and PP.racks[name]and PP.racks[name].resource==rack.resource)then
        return nil,'UNREVIEWED',carrier..'\'s pod rack is not the reviewed pod payload rack'
    end
    local result,code,reason=run(function()
        local reader=Reader.new(world.runtime)
        local writes=require('hd2runtime/domains/pod_payload_writes')
        local resolved=writes.capture(world.runtime,reader,{rack=name,changes={}})
        local records=require('hd2runtime/core/stratagem').capture_all(world.runtime,reader,
            require('hd2runtime/schemas/current'))
        return {record=resolved.record,records=records}
    end,false)
    if not result then
        local why=tostring(reason):gsub('^[^%s:]+:%d+: ','')
        return nil,'IDENTITY_CHANGED',why
    end
    local record=result.record
    local id=record.identity
    if id.recordIndex~=rack.recordIndex or id.indexRow~=rack.indexRow or id.ownerCount~=1 then
        return nil,'SHARED',('%s\'s rack record has %s owners (record %s, row %s): not exclusively the carrier\'s')
            :format(carrier,tostring(id.ownerCount),tostring(id.recordIndex),tostring(id.indexRow))
    end
    local bytes=record.bytes
    if b.u32(bytes,R.randomPayloadSize)~=0 then return nil,'NOT_NATIVE',carrier..'\'s rack draws random payloads'end
    if bytes:byte(R.byte560+1)~=0 then return nil,'NOT_NATIVE',carrier..'\'s rack record +560 is set'end
    if b.u32(bytes,R.spawnPayloadSize)~=rack.spawnPayloadSize then
        return nil,'NOT_NATIVE',('%s\'s spawn count is %d, not its reviewed %d (another writer)'):format(carrier,
            b.u32(bytes,R.spawnPayloadSize),rack.spawnPayloadSize)
    end
    for _,slot in ipairs(rack.slots)do
        local at=slot.index*R.slotStride
        if hex_of(bytes:sub(at+R.item+1,at+R.item+8))~=slot.item or b.u32(bytes,at+R.node)~=slot.node then
            return nil,'NOT_NATIVE',('%s\'s rack slot %d is not its reviewed vanilla item and node (another writer owns '
                ..'it): nothing written'):format(carrier,slot.index)
        end
    end
    -- Exactly one live row names the rack: its carrier, as its primary payload.
    local naming={}
    for _,r in ipairs(result.records or{})do
        for _,p in ipairs(r.payloads or{})do if p==rack.resource then naming[#naming+1]=r end end
    end
    if#naming~=1 or naming[1].id~=rack.stableId or naming[1].payloads[1]~=rack.resource then
        return nil,'SHARED',('%d live stratagem rows name %s\'s rack (exactly its carrier must)'):format(#naming,carrier)
    end
    return {record=record,rack=rack}
end

-- Whether every item's package is resident (the carrier's own call-in packages for its own weapon): true or nil, why.
local function resident(world,carrier,plan)
    local deps={}
    for _,unit in pairs(plan.slots)do
        if unit.key then
            local dep=core_assets.dependency(unit.key)
            if not dep then return nil,'no known package for '..tostring(unit.key)end
            deps[#deps+1]=dep
        end
    end
    local id=D.racks[carrier].stableId
    for _,dep in ipairs(core_assets.dependencies_for_stratagem(id,carrier)or{})do deps[#deps+1]=dep end
    for _,dep in ipairs(deps)do
        local ok,state=pcall(core_assets.state,world.runtime,dep.package)
        if not ok then return nil,'the package state of '..tostring(dep.label)..' is unreadable'end
        if state~='resident'then return nil,tostring(dep.label)..'\'s package is '..tostring(state)end
    end
    return true
end

-- Whether a pod of the carrier type exists in this world (the carrier was called): true / false, or nil and why.
local function called(world,carrier)
    local pods,why=require('hd2runtime/runtime/support_pods').pods(world)
    if not pods then return nil,why end
    local loadout=require('hd2runtime/runtime/stratagem_loadout')
    local kind=loadout.type_of(world,D.racks[carrier].stableId)
    if not kind then return nil,'the carrier has no stratagem type'end
    for _,p in ipairs(pods)do if p.type==kind then return true end end
    return false
end

------------------------------------------------------------------------------------------------------ apply --
-- Writes a carrier's rack for this mission. spec = {carrier, items = {{role, resource, label, key}} (one per spawned
-- item, in order; key: the item's package key, nil for the carrier's own weapon), label, multiplayer = true (a custom
-- stratagem's synchronized write with several players)}. A job: 'applied' {carrier, writes, layout, verify} (or
-- 'refused' / 'failed' with code and reason; nothing is then left written).
function M.apply(spec,callback)
    return job(function()
        if type(spec)~='table'then return nil,'INVALID','spec must be a table'end
        for key in pairs(spec)do
            if key~='carrier'and key~='items'and key~='label'and key~='multiplayer'then
                return nil,'INVALID','unsupported carrier pod option: '..tostring(key)
            end
        end
        local plan,pcode,preason=M.plan(spec.carrier,spec.items)
        if not plan then return nil,pcode,preason end
        if held(states[spec.carrier])then return nil,'ALREADY_APPLIED',spec.carrier..'\'s pod is already written'end
        local world,why=world_module.open()
        if not world then return nil,'UNAVAILABLE',tostring(why)end
        local game=world_module.game_state(world)
        if not(game and game.mission)then return nil,'NOT_IN_MISSION','a carrier pod is written in a mission only'end
        local players=#(world_module.players(world)or{})
        if players>1 and spec.multiplayer~=true then
            return nil,'NOT_SOLO','with several players only a custom stratagem\'s synchronized write runs'
        end
        local present,cwhy=called(world,spec.carrier)
        if present==nil then return nil,'UNAVAILABLE',tostring(cwhy)end
        if present then
            return nil,'CARRIER_CALLED',spec.carrier..'\'s pod already exists in this world: a rack is never written '
                ..'after a call'
        end
        local ok,rwhy=resident(world,spec.carrier,plan)
        if not ok then return nil,'ASSET_UNAVAILABLE',rwhy end
        local captured,ccode,creason=capture(world,spec.carrier)
        if not captured then return nil,ccode,creason end
        local record=captured.record
        local changes={}
        for _,slot in ipairs(plan.rack.slots)do
            local want=plan.desired[slot.index]
            if want~=slot.item then
                local before,desired=u64(slot.item),u64(want)
                for at=0,4,4 do
                    local was,now=before:sub(at+1,at+4),desired:sub(at+1,at+4)
                    if was~=now then
                        changes[#changes+1]={label=('carrier_pod.slot %d item%s'):format(slot.index,at==0 and''or' +4'),
                            owner=record.owner,offset=record.offset+slot.index*R.slotStride+R.item+at,expected=was,
                            desired=now,before=was,already_desired=false,identity={component='HellpodRackComponentData',
                            component_type='carrier pod',record_index=plan.rack.recordIndex,unique_owner=true,
                            owner_count=1},chain={}}
                    end
                end
            end
        end
        local report={status='APPLIED',writes=0,non_target_bytes_unchanged=true,protection_restored=true}
        if#changes>0 then
            report=transaction.apply(world.runtime,{changes=changes,snapshots={{owner=record.owner,offset=record.offset,
                bytes=record.bytes}}})
            metrics.count('carrier_pod.transactions')
            if report.status~='APPLIED'then return nil,'GUARD_REJECTED',tostring(report.reason)end
        end
        local state={applied=true,restored=false,carrier=spec.carrier,plan=plan,changes=changes,
            record={owner=record.owner,offset=record.offset,size=#record.bytes,bytes=record.bytes}}
        states[spec.carrier]=state
        arm()
        local after=world.runtime.read(record.owner.base+record.offset,#record.bytes)
        local exact=after~=nil
        for _,slot in ipairs(plan.rack.slots)do
            local at=slot.index*R.slotStride
            if not after or hex_of(after:sub(at+R.item+1,at+R.item+8))~=plan.desired[slot.index]then exact=false end
        end
        local parts={}
        for _,l in ipairs(plan.layout)do parts[#parts+1]=('slot %d %s'):format(l.slot,tostring(l.label))end
        local emptied={}
        for _,slot in ipairs(plan.rack.slots)do
            if slot.item~=M.EMPTY and plan.desired[slot.index]==M.EMPTY then emptied[#emptied+1]=tostring(slot.index)end
        end
        log(('APPLIED (%s): %s\'s own pod rack holds %s for this mission (%d slot%s written%s; spawn count %d, nodes, '
            ..'sides and sizes untouched); the record had one owner and one consumer row and its exact vanilla slots; '
            ..'read back %s; non-target bytes unchanged %s, protection restored %s'):format(tostring(spec.label or
            spec.carrier),spec.carrier,table.concat(parts,', '),plan.writes,plan.writes==1 and''or's',#emptied>0
            and('; emptied slot'..(#emptied==1 and' 'or's ')..table.concat(emptied,', '))or'',plan.rack.spawnPayloadSize,
            tostring(exact),tostring(report.non_target_bytes_unchanged),tostring(report.protection_restored)))
        if not exact then
            local back,bcode,breason=restore_body(false,spec.carrier)
            return nil,'VERIFY_FAILED','a written slot does not read back'..(back and'; restored'or('; restore '
                ..tostring(bcode)..': '..tostring(breason)))
        end
        return {status='applied',carrier=spec.carrier,writes=report.writes,slots=plan.writes,layout=plan.layout,
            verify={exact=exact,nonTarget=report.non_target_bytes_unchanged,protection=report.protection_restored}}
    end,callback)
end

-- The restore (inside a coroutine; now = from restore_now or the finalizer).
function restore_body(now,carrier)
    local state=states[carrier]
    if not held(state)then return nil,'NOT_APPLIED','the carrier\'s pod is its own: nothing to restore'end
    local world,why=world_module.open()
    if not world then return nil,'UNAVAILABLE',tostring(why)end
    local rec=state.record
    local live=world.runtime.read(rec.owner.base+rec.offset,rec.size)
    if not live or#live~=rec.size then return nil,'UNAVAILABLE','the '..carrier..' rack record is unreadable'end
    local changes={}
    for index=#state.changes,1,-1 do
        local ch=state.changes[index]
        local now_bytes=live:sub(ch.offset-rec.offset+1,ch.offset-rec.offset+#ch.desired)
        if now_bytes~=ch.desired then
            return nil,'CONFLICT',carrier..' '..ch.label..' no longer holds what the carrier pod wrote (another writer '
                ..'owns it): not restored'
        end
        changes[#changes+1]={label=ch.label..' (restore)',owner=ch.owner,offset=ch.offset,expected=ch.desired,
            desired=ch.before,before=ch.desired,already_desired=false,identity=ch.identity,chain={}}
    end
    local report={status='APPLIED',writes=0,non_target_bytes_unchanged=true,protection_restored=true}
    if#changes>0 then
        report=transaction.apply(world.runtime,{changes=changes,snapshots={{owner=rec.owner,offset=rec.offset,
            bytes=live}}})
        metrics.count('carrier_pod.transactions')
        if report.status~='APPLIED'then return nil,'GUARD_REJECTED',tostring(report.reason)end
    end
    state.restored=true
    disarm()
    local after=world.runtime.read(rec.owner.base+rec.offset,rec.size)
    local exact=after==rec.bytes
    log(('RESTORED%s: %s\'s own pod rack holds its vanilla items again: %d writes; the record is exactly its vanilla '
        ..'bytes: %s; non-target bytes unchanged %s, protection restored %s'):format(now and' (in one tick)'or'',carrier,
        report.writes,tostring(exact),tostring(report.non_target_bytes_unchanged),tostring(report.protection_restored)))
    return {status='restored',carrier=carrier,writes=report.writes,verify={exact=exact}}
end

-- Restores as a job: 'restored' (or 'refused' with code and reason).
function M.restore(callback,carrier)
    restoring[carrier]=job(function()return restore_body(false,carrier)end,callback)
    return restoring[carrier]
end
-- Restores within this tick (the loadout-screen boundary): a result table, or nil and code, reason.
function M.restore_now(carrier)
    local pending=restoring[carrier]
    if pending and pending.status=='pending'then pending.watch.cancel();pending.status='superseded'end
    restoring[carrier]=nil
    return run(function()return restore_body(true,carrier)end,true)
end
function M.applied(carrier)
    if carrier~=nil then return held(states[carrier])end
    for _,s in pairs(states)do if held(s)then return true end end
    return false
end
function M.applied_carriers()
    local out={}
    for carrier,s in pairs(states)do if held(s)then out[#out+1]=carrier end end
    table.sort(out)
    return out
end
function M.state(carrier)return states[carrier]end
-- Read-only, within this call: whether a carrier's rack record is where the research found it, exclusively its own and
-- exactly its vanilla bytes. {native = true, slots = 8, capacity}, or nil, code, reason.
function M.inspect(world,carrier)
    if not D.racks[carrier]then return nil,'NO_EXCLUSIVE_RACK',tostring(carrier)..' has no exclusive carrier rack'end
    return run(function()
        local captured,code,reason=capture(world,carrier)
        if not captured then return nil,code,reason end
        return {native=true,slots=8,capacity=D.racks[carrier].capacity}
    end,true)
end
function M.finalize_for_tests()finalize()end
function M.reset_for_tests()states,restoring={},{};disarm()end
return M
