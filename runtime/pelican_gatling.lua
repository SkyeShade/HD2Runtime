-- The Pelican Gatling turret experiment (development only; PelicanGatlingProof; docs/research/pelican-cas-F5FEE03DCFDB.md
-- section 16). Not exported by api/hd2.lua.
--
-- One Runtime-spawned Pelican's chin turret (shuttle_gunship_turret_hmg, a mounted child at the Pelican's
-- attach_front_turret node) becomes a Gatling turret, per instance, through the game's own routines
-- (research/pelican-F5FEE03DCFDB.json "gatlingTurret" and "gatling"):
--   * M.replace: a gatling_turret entity takes the chin turret's place, the way the mount system attaches a child:
--       1. the game's spawn request creates one gatling_turret (no context, no modifier block);
--       2. the game's attach routine (0x812540) attaches it to the Pelican's unit at the chin turret's node, with the
--          chin turret's own local offset and rotation;
--       3. the Pelican's mount record names it in the chin turret's slot (one guarded 4-byte write of the Pelican's own
--          record), so the game's own teardown removes it with the Pelican;
--       4. the chin turret is unlinked (the relation unlink 0xB0B020, as the teardown does) and removed (0xFDC310).
--     The Gatling keeps its own type: its AI (behaviour 213), weapon, ammo pattern and wind-up.
--   * M.weapon (the fallback): the chin turret keeps its entity; the game's copy routine (0x61AF10) gives it its own
--     ProjectileWeapon record (an unmodified copy of its type's), then one guarded transaction writes that copy's
--     projectile type (120 -> 148) and the turret's own current RPM (300 -> 1600; the engine re-derives the shot interval
--     from it). The ammo pattern and spin-up are type data / a component: not reachable per instance.
-- Live (PelicanGatlingProof 0.1.0): REPLACE spawned, attached and drove the Gatling (it followed the Pelican, ran its AI,
-- fired 148 at 1600 RPM with its pattern and spin-up, and the game's teardown removed it with the Pelican), but the
-- chin turret stayed: the removal 0xFDC310 only sends a request for a networked entity whose network object is flagged.
-- Since then (0.2.0): M.assets loads the Gatling's package through the Runtime's asset loader (no loadout needed);
-- M.removal_state reads why a removal is deferred; M.destroy_original makes the second attempt with the game's own
-- destroy routine (0xFDC820, not forced: the game's ownership check stays); M.gatling_unit / M.hide_mesh explore the
-- engine's scripting API on the Gatling's own unit (its ground base). WEAPON is live-proven: the chin turret fired the
-- Gatling projectile at 1600 RPM continuously (no pattern, no spin-up).
-- Refused, with nothing called or written, unless: every Pelican and Gatling pin and each routine's exact entry bytes
-- prove; inside the Runtime's own update; in a mission, as the solo host; the Pelican is Runtime-spawned, alive,
-- behaviour 667 and hovering (stage 6); exactly one chin turret names it by its attachable link; the Pelican's mount
-- record names that turret in one slot. M.replace also needs the Gatling Sentry's package resident (bring it). No shared
-- definition is written: M.shared reads the chin turret's and Gatling's type records so a caller can compare them.
-- Runs interpreted. The game's LuaJIT (2.1.0-alpha) mis-restores a sunk table at a trace exit (allocation sinking): a
-- table this module built and returned from a compiled trace came back without its last fields (the chin turret's AI
-- state without its record, tests/test_pelican_gatling_proof.py; correct with the JIT or its sinking off). So the JIT
-- is off for this development module and every function in it; the work it does is a few reads a frame.
if rawget(_G,'jit')then jit.off(true,true)end
local world_module=require('hd2runtime/runtime/event_world')
local transaction=require('hd2runtime/core/guarded_transaction')
local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
local scheduler=require('hd2runtime/runtime/scheduler')
local metrics=require('hd2runtime/runtime/metrics')
local log_module=require('hd2runtime/runtime/log')
local core_assets=require('hd2runtime/core/assets')
local pelicans=require('hd2runtime/runtime/pelicans')
local b=require('hd2runtime/core/bytes')
local D=require('hd2runtime/domains/pelican')
local M={}
local G,TW,A,SP=D.gatling,D.turretWeapon,D.attachment,D.spawn
local CHIN,GATLING=G.chinTurretResource,G.gatlingResource
local CHIN_BEHAVIOUR,GATLING_BEHAVIOUR,PELICAN_BEHAVIOUR,HOVER=645,213,667,6
M.GATLING_PROJECTILE,M.GATLING_RPM=TW.observed.gatlingSentry.projectileType,TW.observed.gatlingSentry.rpmSlots[2]

local function log(text)log_module.emit('[HD2Runtime] PELICAN GATLING '..text)end
local function f32(bytes,o)local ok,v=pcall(b.value,bytes,o,'f32');return ok and v or nil end
local function finite(v)return type(v)=='number'and v==v and v~=math.huge and v~=-math.huge end
local function u32(n)return b.encode(n,'u32')end
local function f32e(v)return b.encode(v,'f32')end
local function map_at(at)return {keys=at,capacity=at+8,empty=at+0xC,multiplier=at+0x10}end
local function text(p)return p and('(%.1f, %.1f, %.1f)'):format(p.x,p.y,p.z)or'(?)'end

-- Every Pelican pin (the Gatling group included) and each routine's exact entry bytes.
function M.prove(world)
    local ok,why=pelicans.prove(world)
    if not ok then return nil,why end
    for _,name in ipairs({'attach','remove','unlink','copy','destroy'})do
        if not world.view.proves(world.game+G[name].rva,G[name].prologue)then
            return nil,('the game\'s %s routine changed (game+%X)'):format(name,G[name].rva)
        end
    end
    if not world.view.proves(world.game+SP.rva,SP.prologue)then return nil,'the game\'s spawn request changed'end
    return true
end

-- A type's record in one of the component world's type tables (key = the 64-bit resource, mod `slots`), or nil.
local function type_record(world,t,hex,size)
    local cworld=world.view.pointer(world.game+SP.world)
    local tab=cworld and world.view.pointer(cworld+t.offset)
    if not tab or tab==0 then return nil end
    local key=b.unhex(hex):reverse()
    local lo,hi=b.u32(key,0),b.u32(key,4)
    local slot=((hi%t.slots)*(4294967296%t.slots)+lo%t.slots)%t.slots
    for _=1,t.slots do
        local raw=world.view.read(tab+slot*16,16)
        if not raw then return nil end
        if raw:sub(1,8)==key then
            return world.view.read(tab+t.records+b.u32(raw,8)*t.stride,size or t.stride),
                tab+t.records+b.u32(raw,8)*t.stride
        end
        if raw:sub(1,8)==string.rep('\0',8)then return nil end
        slot=(slot+1)%t.slots
    end
end
M.type_record=type_record
-- The shared (type) values a Gatling configuration concerns, read-only: {chin, gatling} = {projectile, rpm (Y slot),
-- pattern (on/off), first (the pattern's first five types), raw = {pw, magazine, weapon_data: the whole ProjectileWeapon,
-- magazine and WeaponData type records}}, or nil. M.shared_same compares the whole records.
function M.shared(world)
    local out={}
    for key,hex in pairs({chin=CHIN,gatling=GATLING})do
        local pw=type_record(world,G.pwTypes,hex)
        local mag=type_record(world,G.magazineTypes,hex)
        if not(pw and mag)then return nil end
        local wd=D.aim and type_record(world,D.aim.weaponData.types,hex)
        out[key]={projectile=b.u32(pw,0),rpm=f32(pw,8),pattern=b.u32(mag,0)~=0,
            first={b.u32(mag,4),b.u32(mag,8),b.u32(mag,12),b.u32(mag,16),b.u32(mag,20)},raw={pw=pw,magazine=mag,
            weapon_data=wd}}
    end
    return out
end
function M.shared_text(s)
    if not s then return'(unreadable)'end
    local function one(v)return('projectile %d, %s RPM, pattern %s [%s]'):format(v.projectile,tostring(v.rpm),
        v.pattern and'on'or'off',table.concat(v.first,','))end
    return 'chin turret type: '..one(s.chin)..'; Gatling type: '..one(s.gatling)
end
function M.shared_same(a,c)
    if not(a and c)then return false end
    for _,k in ipairs({'chin','gatling'})do
        local x,y=a[k],c[k]
        if x.projectile~=y.projectile or x.rpm~=y.rpm or x.pattern~=y.pattern then return false end
        for i=1,5 do if x.first[i]~=y.first[i]then return false end end
        if x.raw and y.raw and(x.raw.pw~=y.raw.pw or x.raw.magazine~=y.raw.magazine
            or x.raw.weapon_data~=y.raw.weapon_data)then return false end
    end
    return true
end

-- The Pelican's mount record: {index, address (its 6 child entities), children = {...}}, or nil.
local function mount_record(world,pelican)
    local MT=G.mount
    local component=world.view.pointer(world.game+MT.global)
    local index=component and pelicans.index_of(world,component,map_at(MT.map),pelican)
    local base=index and world.view.pointer(component+MT.children)
    local raw=base and base~=0 and world.view.read(base+index*MT.stride,MT.stride)
    if not raw then return nil end
    local children={}
    for k=0,5 do children[k]=b.u32(raw,k*4)end
    return {index=index,address=base+index*MT.stride,raw=raw,children=children,component=component}
end
M.mount_record=mount_record

-- What is mounted on one Pelican now, read-only: {pelican = {entity, link, stage, behaviour, position}, turret = {entity,
-- resource, behaviour, link, node, offset, rotation, position, weapon}, mount = {index, address, slot, children}}, or
-- nil, code, reason.
function M.inspect(world,pelican)
    local p=pelicans.behaviours(world,{[PELICAN_BEHAVIOUR]=true})
    p=p and p[pelican]
    if not p then return nil,'GONE','Pelican '..tostring(pelican)..' is not a behaviour-667 Pelican now'end
    local handle=pelicans.handle(world,pelican)
    if not(handle and handle.link and handle.link~=0)then return nil,'NO_UNIT','the Pelican has no unit link'end
    local found={}
    local turrets=pelicans.behaviours(world,{[CHIN_BEHAVIOUR]=true,[GATLING_BEHAVIOUR]=true})or{}
    for entity,t in pairs(turrets)do
        local att=pelicans.attachable(world,entity)
        if att and att.link==handle.link then found[#found+1]={entity=entity,t=t,att=att}end
    end
    table.sort(found,function(x,y)return x.entity<y.entity end)
    local state={pelican={entity=pelican,link=handle.link,stage=p.stage,behaviour=p.behaviour,position=p.position},
        attached=found}
    local mount=mount_record(world,pelican)
    state.mount=mount
    if #found==1 then
        local f=found[1]
        local raw=f.att.raw
        state.turret={entity=f.entity,resource=f.t.resource,behaviour=f.t.behaviour,link=f.att.link,node=f.att.node,
            position=f.att.position,offset={x=f32(raw,G.attachable.offset),y=f32(raw,G.attachable.offset+4),
                z=f32(raw,G.attachable.offset+8)},
            rotation={x=f32(raw,G.attachable.rotation),y=f32(raw,G.attachable.rotation+4),
                z=f32(raw,G.attachable.rotation+8),w=f32(raw,G.attachable.rotation+12)},
            weapon=pelicans.weapon_config(world,f.entity)}
        if mount then
            for k=0,G.mount.slots-1 do if mount.children[k]==f.entity then mount.slot=k end end
        end
    end
    return state
end
local function weapon_text(w)
    if not w then return'not a projectile weapon'end
    local m=w.magazine
    return ('path %s, own ProjectileWeapon %s, %s RPM (current %s), magazine %s, wind-up %s'):format(w.path,
        w.copy and('copy (projectile '..w.copy.projectileType..')')or'none (type record)',
        w.rpm and('%.0f'):format(w.rpm)or'?',w.currentRpm and('%.0f'):format(w.currentRpm)or'?',
        m and(('%d rounds, pattern %s, chambered %d'):format(m.rounds,m.pattern and'on'or'off',m.chambered))or'none',
        w.windUp and'yes'or'no')
end
M.weapon_text=weapon_text
function M.state_text(s)
    local t=s.turret
    return ('Pelican %d (behaviour %d, stage %d, unit link 0x%X) at %s; %d turret(s) attached%s; mount record %s')
        :format(s.pelican.entity,s.pelican.behaviour,s.pelican.stage,s.pelican.link,text(s.pelican.position),
        #s.attached,t and((': entity %d (%s, behaviour %d) at node %d, local offset %s, rotation (%.3f, %.3f, %.3f, %.3f); '
            ..'weapon: %s'):format(t.entity,tostring(t.resource),t.behaviour,t.node,text(t.offset),t.rotation.x or 0,
            t.rotation.y or 0,t.rotation.z or 0,t.rotation.w or 0,weapon_text(t.weapon)))or'',
        s.mount and(('#%d, slot %s, children %d %d %d %d %d'):format(s.mount.index,tostring(s.mount.slot),
            s.mount.children[0],s.mount.children[1],s.mount.children[2],s.mount.children[3],s.mount.children[4]))
            or'unreadable')
end

local spawned={}   -- Gatling entity -> {pelican, removed}
local replaced={}  -- Pelican -> {original, gatling}
function M.spawned(entity)return spawned[entity]end
function M.replaced(pelican)return replaced[pelican]end

-- The Gatling Sentry's package (its call-in package: it holds gatling_turret), through the Runtime's own asset loader:
-- M.assets(world, dt) ticks one gate (requested on the first tick; logs "assets for pelican-gatling requested" and
-- "... resident") and returns 'ready', 'waiting' or 'failed' and why. A mission's loadout need not carry the Gatling.
M.ASSET_ID='pelican-gatling'
local gate
function M.asset_dependency()return core_assets.dependency_for_stratagem(G.gatlingStratagem,'A/G-16 Gatling Sentry')end
function M.assets(world,dt)
    if not gate then
        local dependency=M.asset_dependency()
        if not dependency then return'failed','ASSET_UNAVAILABLE: no call-in package is known for the Gatling Sentry'end
        gate=core_assets.gate(world.runtime,{id=M.ASSET_ID,asset_dependencies={dependency}},log_module.emit)
    end
    return gate.tick(dt or 0)
end

-- An entity's removal state, read-only: {alive, record (its world record), network (id or nil), createdHere, flagged
-- (its network object's flag: a removal then only sends a request), pending (the world's pending removals)}.
function M.removal_state(world,entity)
    local out={entity=entity}
    local record,raw=pelicans.record_address(world,entity)
    out.alive=record~=nil
    out.record=record
    local world_object=world.view.pointer(world.game+G.world)
    local pending=world_object and world.view.read(world_object+G.pending.count,4)
    out.pending=pending and b.u32(pending,0)
    if raw then
        local ER=G.entityRecords
        local network=b.u32(raw,ER.network)
        out.network=network~=ER.noNetwork and network or nil
        out.createdHere=b.u32(raw,ER.flags)%2==1
        local manager=world_object and world.view.pointer(world_object+G.network.manager)
        if out.network and manager and manager~=0 then
            local N=G.network
            local index=pelicans.index_of(world,manager,{keys=N.map,capacity=N.map+8,empty=N.map+0xC,
                multiplier=N.map+0x10},out.network)
            local flag=index and world.view.read(manager+N.flags+index,1)
            out.flagged=flag and flag:byte(1)~=0
        end
    end
    return out
end
function M.removal_text(r)
    return ('entity %d %s; network id %s; created here %s; network flag %s; pending removals %s'):format(r.entity,
        r.alive and'ALIVE'or'gone',r.network and('0x%X'):format(r.network)or'none',tostring(r.createdHere),
        r.flagged==nil and'n/a'or(r.flagged and'SET (a removal only sends a request)'or'clear (a removal queues it)'),
        tostring(r.pending))
end

-- The guards common to both operations. Returns the state or nil, code, reason.
local function guards(world,pelican,needs)
    local runtime=world.runtime
    for _,name in ipairs(needs)do
        if not runtime[name]then return nil,'UNAVAILABLE','this Runtime adapter cannot call game functions'end
    end
    if not scheduler.in_update()then return nil,'NOT_GAME_THREAD','only inside the Runtime\'s own update'end
    local ok,why=M.prove(world)
    if not ok then return nil,'UNSUPPORTED_BUILD',tostring(why)end
    local game=world_module.game_state(world)
    if not(game and game.mission)then return nil,'NOT_IN_MISSION','in a mission only'end
    if game.host~=true then return nil,'NOT_HOST','development experiment: host only'end
    local record_list,code,reason=slots.local_record(world)
    if not record_list then return nil,code,reason end
    if record_list.records~=1 then return nil,'NOT_SOLO','solo only: '..record_list.records..' stratagem records'end
    if not pelicans.owned(pelican)then
        return nil,'NOT_RUNTIME_PELICAN','Pelican '..tostring(pelican)..' was not spawned by the Runtime'
    end
    local state,scode,sreason=M.inspect(world,pelican)
    if not state then return nil,scode,sreason end
    if state.pelican.stage~=HOVER then
        return nil,'NOT_HOVERING',('Pelican %d is in stage %d, not hovering (6)'):format(pelican,state.pelican.stage)
    end
    if #state.attached~=1 then
        return nil,'TURRET_UNEXPECTED',('%d turrets name Pelican %d by its unit link, not 1'):format(#state.attached,pelican)
    end
    local t=state.turret
    if t.behaviour~=CHIN_BEHAVIOUR or t.resource~=CHIN then
        return nil,'TURRET_UNEXPECTED',('the attached turret %d is %s (behaviour %d), not the chin turret'):format(t.entity,
            tostring(t.resource),t.behaviour)
    end
    if not(state.mount and state.mount.slot)then
        return nil,'MOUNT_UNEXPECTED','the Pelican\'s mount record does not name its chin turret'
    end
    return state
end

-- M.replace(world, pelican, label): returns {pelican, original, gatling, node, slot, writes, verify, verified} or nil,
-- code, reason. Logs PELICAN GATLING ... lines for every step.
function M.replace(world,pelican,label)
    label=tostring(label or'?')
    local function refuse(code,reason)
        log(('REFUSED (%s): replace on Pelican %s: %s: %s'):format(label,tostring(pelican),code,reason))
        metrics.count('pelican_gatling.refused')
        return nil,code,reason
    end
    local state,code,reason=guards(world,pelican,{'native_spawn_gatling','native_attach','native_relation_unlink',
        'native_remove_entity'})
    if not state then return refuse(code,reason)end
    local runtime=world.runtime
    local dependency=core_assets.dependency_for_stratagem(G.gatlingStratagem,'A/G-16 Gatling Sentry')
    local pok,resident=pcall(core_assets.state,runtime,dependency and dependency.package)
    if not(dependency and pok and resident=='resident')then
        return refuse('GATLING_NOT_LOADED','the Gatling Sentry\'s package is not resident ('
            ..tostring(pok and resident or'unreadable')..'): request it first (M.assets, "'..M.ASSET_ID..'")')
    end
    if pelicans.type_behaviour(world,GATLING)~=GATLING_BEHAVIOUR then
        return refuse('GATLING_NOT_LOADED','the gatling_turret type is not registered with behaviour 213')
    end
    local t=state.turret
    local rot=t.rotation
    if not(finite(rot.x)and finite(rot.y)and finite(rot.z)and finite(rot.w)
        and math.abs(rot.x^2+rot.y^2+rot.z^2+rot.w^2-1)<1e-2)then rot={x=0,y=0,z=0,w=1}end
    local off=t.offset
    if not(finite(off.x)and finite(off.y)and finite(off.z)and math.abs(off.x)<50 and math.abs(off.y)<50
        and math.abs(off.z)<50)then off={x=0,y=0,z=0}end
    local pose=pelicans.pose(world,pelican)
    local fx,fy=1,0
    if pose and pose.forward then
        local flat=math.sqrt(pose.forward.x^2+pose.forward.y^2)
        if flat>1e-3 then fx,fy=pose.forward.x/flat,pose.forward.y/flat end
    end
    local at=t.position or state.pelican.position
    if not at then return refuse('UNAVAILABLE','the chin turret\'s position is unreadable')end
    local manager=world.view.pointer(world.game+A.global)
    local mount_manager=state.mount.component
    local world_object=world.view.pointer(world.game+G.world)
    if not(manager and manager~=0 and mount_manager and world_object and world_object~=0)then
        return refuse('UNAVAILABLE','the attachable, mount or world object is unreadable')
    end
    local before_shared=M.shared(world)
    log(('BEFORE (%s): %s'):format(label,M.state_text(state)))
    log(('BEFORE (%s): shared types: %s'):format(label,M.shared_text(before_shared)))
    log(('ATTEMPT (%s): 1. spawn request (game+%X) for gatling_turret at %s; 2. attach routine (game+%X) to unit link '
        ..'0x%X node %d, offset %s; 3. guarded write of the Pelican\'s mount record slot %d: %d -> the Gatling; 4. relation '
        ..'unlink (game+%X) and removal (game+%X) of chin turret %d'):format(label,SP.rva,text(at),G.attach.rva,
        state.pelican.link,t.node,text(off),state.mount.slot,t.entity,G.unlink.rva,G.remove.rva,t.entity))
    metrics.count('pelican_gatling.native_calls')
    -- 1. The Gatling.
    local gatling=runtime.native_spawn_gatling(world.game+SP.rva,at.x,at.y,at.z,fx,fy)
    local made=type(gatling)=='number'and gatling>0 and(pelicans.behaviours(world,{[GATLING_BEHAVIOUR]=true})or{})[gatling]
    local gh=made and pelicans.handle(world,gatling)
    if not(made and gh and gh.resource==GATLING and gh.link and gh.link~=0 and pelicans.attachable(world,gatling))then
        if type(gatling)=='number'and gatling>0 then
            runtime.native_remove_entity(world.game+G.remove.rva,world_object,gatling)
        end
        return refuse('GATLING_SPAWN_FAILED',('the spawn returned %s: not an attachable gatling_turret with behaviour 213 '
            ..'(removed again if it existed)'):format(tostring(gatling)))
    end
    spawned[gatling]={pelican=pelican}
    log(('SPAWNED (%s): Gatling entity %d (unit link 0x%X, behaviour 213, stage %d); weapon: %s'):format(label,gatling,
        gh.link,made.stage,weapon_text(pelicans.weapon_config(world,gatling))))
    -- 2. Attach it where the chin turret is.
    runtime.native_attach(world.game+G.attach.rva,manager,gatling,state.pelican.link,t.node,off,rot)
    local att=pelicans.attachable(world,gatling)
    if not(att and att.link==state.pelican.link and att.node==t.node)then
        runtime.native_remove_entity(world.game+G.remove.rva,world_object,gatling)
        spawned[gatling].removed='attach failed'
        return refuse('ATTACH_FAILED',('the Gatling\'s attachable record reads link %s node %s, not 0x%X node %d; the '
            ..'Gatling was removed and the chin turret left as it was'):format(att and('0x%X'):format(att.link)or'?',
            att and tostring(att.node)or'?',state.pelican.link,t.node))
    end
    log(('ATTACHED (%s): Gatling %d: attachable link 0x%X node %d (the Pelican\'s unit, the chin turret\'s node)')
        :format(label,gatling,att.link,att.node))
    -- 3. The Pelican's own mount record names the Gatling in the chin turret's slot.
    local MT=G.mount
    local slot_at=state.mount.address+state.mount.slot*4
    local owner=pelicans.owner_of(world,state.mount.address,MT.stride)
    local function undo(code,reason)
        runtime.native_remove_entity(world.game+G.remove.rva,world_object,gatling)
        spawned[gatling].removed=code
        return refuse(code,reason..'; the Gatling was removed again and the chin turret left as it was')
    end
    if not owner then return undo('NOT_PRIVATE','the mount records are not in private read-write memory')end
    local identity={component='Mount',component_type='native',unique_owner=true,owner_count=1}
    -- The context: the Pelican's whole mount record (its other slots are guarded unchanged with it).
    local plan={snapshots={{owner=owner,offset=state.mount.address-owner.base,bytes=state.mount.raw}},
        changes={{label='pelican.'..pelican..'.mount.slot'..state.mount.slot,owner=owner,offset=slot_at-owner.base,
            expected=u32(t.entity),desired=u32(gatling),before=u32(t.entity),already_desired=false,identity=identity,
            chain={}}}}
    local report=transaction.apply(runtime,plan)
    metrics.count('pelican_gatling.transactions')
    if report.status~='APPLIED'then
        return undo('GUARD_REJECTED','the mount slot write was refused: '..tostring(report.reason))
    end
    local after=mount_record(world,pelican)
    -- 4. The chin turret: unlinked and removed, as the teardown does.
    local before_removal=M.removal_state(world,t.entity)
    log(('REMOVAL (%s): before: chin turret %s'):format(label,M.removal_text(before_removal)))
    runtime.native_relation_unlink(world.game+G.unlink.rva,t.entity,mount_manager,pelican)
    runtime.native_remove_entity(world.game+G.remove.rva,world_object,t.entity)
    log(('REMOVAL (%s): after the removal call: chin turret %s'):format(label,
        M.removal_text(M.removal_state(world,t.entity))))
    replaced[pelican]={original=t.entity,gatling=gatling}
    local result={pelican=pelican,original=t.entity,gatling=gatling,node=t.node,slot=state.mount.slot,
        writes=report.writes,shared_before=before_shared,verify={spawned=true,attached=true,
            slot=after~=nil and after.children[state.mount.slot]==gatling,
            otherSlots=after~=nil and after.raw:sub(1,state.mount.slot*4)==state.mount.raw:sub(1,state.mount.slot*4)
                and after.raw:sub(state.mount.slot*4+5)==state.mount.raw:sub(state.mount.slot*4+5),
            nonTarget=report.non_target_bytes_unchanged==true,protection=report.protection_restored==true}}
    local verified=true
    for _,v in pairs(result.verify)do if v~=true then verified=false end end
    result.verified=verified
    log(('APPLIED (%s): Pelican %d: chin turret %d unlinked and removal requested; Gatling %d attached at node %d and '
        ..'named in mount slot %d (%d write); verified %s (slot %s, other slots %s, non-target bytes %s, protection %s)')
        :format(label,pelican,t.entity,gatling,t.node,state.mount.slot,report.writes,tostring(verified),
        tostring(result.verify.slot),tostring(result.verify.otherSlots),tostring(result.verify.nonTarget),
        tostring(result.verify.protection)))
    return result
end

-- The Runtime's own removal of a Gatling it spawned (cleanup when the game's teardown did not remove it).
function M.remove_gatling(world,entity,label)
    local s=spawned[entity]
    if not s then return nil,'NOT_OURS','entity '..tostring(entity)..' is not a Gatling this experiment spawned'end
    if not world.runtime.native_remove_entity then return nil,'UNAVAILABLE','no native calls'end
    if not scheduler.in_update()then return nil,'NOT_GAME_THREAD','only inside the Runtime\'s own update'end
    local ok,why=M.prove(world)
    if not ok then return nil,'UNSUPPORTED_BUILD',tostring(why)end
    local h=pelicans.handle(world,entity)
    if not(h and h.resource==GATLING)then return nil,'GONE','the Gatling is gone'end
    local world_object=world.view.pointer(world.game+G.world)
    world.runtime.native_remove_entity(world.game+G.remove.rva,world_object,entity)
    s.removed='runtime cleanup'
    log(('CLEANUP (%s): removal requested for Gatling %d (its Pelican %d is gone)'):format(tostring(label),entity,s.pelican))
    return true
end

-- The second attempt for one replaced Pelican's original chin turret, when the game's removal request left it alive:
-- the game's own destroy routine (what the pending-removal pass calls), not forced (the game's own ownership check
-- stays). Returns the removal state after, or nil, code, reason.
function M.destroy_original(world,pelican,label)
    label=tostring(label or'?')
    local function refuse(code,reason)
        log(('DESTROY REFUSED (%s): Pelican %s: %s: %s'):format(label,tostring(pelican),code,reason))
        return nil,code,reason
    end
    local r=replaced[pelican]
    if not r then return refuse('NOT_REPLACED','this Pelican\'s chin turret was not replaced')end
    if not world.runtime.native_destroy_entity then return refuse('UNAVAILABLE','no native calls')end
    if not scheduler.in_update()then return refuse('NOT_GAME_THREAD','only inside the Runtime\'s own update')end
    local ok,why=M.prove(world)
    if not ok then return refuse('UNSUPPORTED_BUILD',tostring(why))end
    local game=world_module.game_state(world)
    if not(game and game.mission and game.host==true)then return refuse('NOT_HOST','in a mission, as host only')end
    local record_list=slots.local_record(world)
    if not(record_list and record_list.records==1)then return refuse('NOT_SOLO','solo only')end
    local h=pelicans.handle(world,r.original)
    local record=pelicans.record_address(world,r.original)
    if not(h and record)then return refuse('GONE','the original chin turret is already gone')end
    if h.resource~=CHIN then return refuse('NOT_ORIGINAL','entity '..r.original..' is not the chin turret now')end
    local world_object=world.view.pointer(world.game+G.world)
    log(('DESTROY (%s): Pelican %d: the game\'s destroy routine (game+%X), not forced, for its original chin turret: %s')
        :format(label,pelican,G.destroy.rva,M.removal_text(M.removal_state(world,r.original))))
    metrics.count('pelican_gatling.native_calls')
    world.runtime.native_destroy_entity(world.game+G.destroy.rva,world_object,record)
    local after=M.removal_state(world,r.original)
    log(('DESTROY (%s): after: chin turret %s'):format(label,M.removal_text(after)))
    return after
end

-- The engine's scripting API on one Gatling's unit (development exploration; nothing native): which unit functions
-- exist, the Gatling's unit (the gatling_turret unit nearest its attachable position) and its mesh count. M.hide_mesh
-- hides one mesh of that unit (render state of that one unit; it goes with the unit).
local UNIT_PATH='content/fac_helldivers/hellpod/turret/gatling_turret'
local WORLD_API={'units_by_resource','units'}
local UNIT_API={'world_position','num_meshes','mesh','set_mesh_visibility','set_visibility','is_a'}
local function engine()
    local S=rawget(_G,'stingray')
    if type(S)~='table'or type(S.Application)~='table'or type(S.World)~='table'or type(S.Unit)~='table'then
        return nil,'stingray.Application, World or Unit is unavailable'
    end
    return S
end
function M.unit_api()
    local S,why=engine()
    if not S then return nil,why end
    local out={}
    for _,name in ipairs(WORLD_API)do out['World.'..name]=type(S.World[name])=='function'end
    for _,name in ipairs(UNIT_API)do out['Unit.'..name]=type(S.Unit[name])=='function'end
    return out
end
local function vector(S,v)
    if v==nil then return nil end
    local ok,x,y,z=pcall(function()return S.Vector3.to_elements(v)end)
    if ok and x then return {x=x,y=y,z=z}end
    local ok2,t=pcall(function()return {x=v.x,y=v.y,z=v.z}end)
    return ok2 and t or nil
end
function M.gatling_unit(world,gatling)
    local S,why=engine()
    if not S then return nil,why end
    local att=pelicans.attachable(world,gatling)
    if not(att and att.position)then return nil,'the Gatling\'s attachable position is unreadable'end
    local ok,w=pcall(S.Application.main_world)
    if not(ok and w)then return nil,'no main world'end
    local list
    if type(S.World.units_by_resource)=='function'then
        local lok,l=pcall(S.World.units_by_resource,w,UNIT_PATH)
        list=lok and l or nil
    elseif type(S.World.units)=='function'and type(S.Unit.is_a)=='function'then
        local aok,all=pcall(S.World.units,w)
        list={}
        for _,u in ipairs(aok and all or{})do
            local iok,yes=pcall(S.Unit.is_a,u,UNIT_PATH)
            if iok and yes then list[#list+1]=u end
        end
    end
    if type(list)~='table'or#list==0 then return nil,'no gatling_turret unit found through the engine API'end
    local best,bd
    for _,u in ipairs(list)do
        local pok,v=pcall(S.Unit.world_position,u,1)
        local p=pok and vector(S,v)
        local d=p and math.sqrt((p.x-att.position.x)^2+(p.y-att.position.y)^2+(p.z-att.position.z)^2)
        if d and(not bd or d<bd)then best,bd=u,d end
    end
    if not best then return nil,'no gatling_turret unit has a readable position'end
    local meshes
    if type(S.Unit.num_meshes)=='function'then
        local mok,n=pcall(S.Unit.num_meshes,best)
        meshes=mok and n or nil
    end
    return {unit=best,distance=bd,meshes=meshes,candidates=#list}
end
function M.hide_mesh(world,gatling,index)
    local S,why=engine()
    if not S then return nil,why end
    if not spawned[gatling]then return nil,'not a Gatling this experiment spawned'end
    if type(S.Unit.set_mesh_visibility)~='function'then return nil,'stingray.Unit.set_mesh_visibility is unavailable'end
    local u,uwhy=M.gatling_unit(world,gatling)
    if not u then return nil,uwhy end
    local ok,err=pcall(S.Unit.set_mesh_visibility,u.unit,index,false)
    if not ok then return nil,tostring(err)end
    return u
end

-- M.weapon(world, pelican, label): the fallback. Returns {pelican, turret, copy, writes, verify, verified} or nil, code,
-- reason.
function M.weapon(world,pelican,label)
    label=tostring(label or'?')
    local function refuse(code,reason)
        log(('REFUSED (%s): weapon on Pelican %s: %s: %s'):format(label,tostring(pelican),code,reason))
        metrics.count('pelican_gatling.refused')
        return nil,code,reason
    end
    local state,code,reason=guards(world,pelican,{'native_weapon_copy'})
    if not state then return refuse(code,reason)end
    local runtime=world.runtime
    local t=state.turret
    local w=t.weapon
    if not(w and w.path=='magazine'and w.magazine and not w.magazine.pattern)then
        return refuse('TURRET_UNEXPECTED','the chin turret is not a magazine weapon without a pattern')
    end
    if w.copy then return refuse('COPY_EXISTS','the chin turret already has its own ProjectileWeapon record')end
    local PW=TW.projectileWeapon
    local manager=world.view.pointer(world.game+PW.global)
    local count=manager and world.view.read(manager+PW.copyCount,4)
    local capacity=manager and world.view.read(manager+G.copyCapacity,4)
    if not(count and capacity)then return refuse('UNAVAILABLE','the projectile weapon manager is unreadable')end
    count,capacity=b.u32(count,0),b.u32(capacity,0)
    if not(capacity>0 and count+1<capacity)then
        return refuse('NO_CAPACITY',('%d of %d per-instance copies used (the routine does not check)'):format(count,
            capacity))
    end
    local handles=world.view.pointer(manager+0x68)
    local handle=handles and handles~=0 and world.view.pointer(handles+w.index*8)
    local hraw=handle and handle~=0 and world.view.read(handle,0x10)
    if not(hraw and b.u32(hraw,8)==t.entity and b.hex(hraw:sub(1,8):reverse()):upper()==CHIN)then
        return refuse('TURRET_UNEXPECTED','the projectile weapon handle does not name the chin turret')
    end
    local type_raw=type_record(world,G.pwTypes,CHIN,PW.copyStride)
    if not type_raw then return refuse('UNAVAILABLE','the chin turret\'s type record is unreadable')end
    local before_shared=M.shared(world)
    log(('BEFORE (%s): %s'):format(label,M.state_text(state)))
    log(('BEFORE (%s): shared types: %s'):format(label,M.shared_text(before_shared)))
    log(('ATTEMPT (%s): 1. copy routine (game+%X) for chin turret %d (an unmodified copy of its type record; copies %d of '
        ..'%d); 2. guarded writes: the copy\'s projectile type %d -> %d, the turret\'s current RPM %.0f -> %.0f')
        :format(label,G.copy.rva,t.entity,count,capacity,b.u32(type_raw,0),M.GATLING_PROJECTILE,w.currentRpm or 0,
        M.GATLING_RPM))
    metrics.count('pelican_gatling.native_calls')
    runtime.native_weapon_copy(world.game+G.copy.rva,manager,handle)
    local ci=pelicans.index_of(world,manager,map_at(PW.copies),t.entity)
    local records=ci and world.view.pointer(manager+PW.copyRecords)
    local copy_at=records and records~=0 and records+ci*PW.copyStride
    local copy=copy_at and world.view.read(copy_at,PW.copyStride)
    if not copy then return refuse('COPY_FAILED','no per-instance copy for the chin turret after the call')end
    if copy~=type_raw then return refuse('COPY_UNEXPECTED','the copy differs from the type record (left unwritten)')end
    log(('COPIED (%s): chin turret %d has its own ProjectileWeapon record #%d (equal to its type record)'):format(label,
        t.entity,ci))
    local current=world.view.pointer(manager+PW.current)
    local rpm_at=current and current~=0 and current+w.index*PW.currentStride+PW.currentRpm
    local rpm_raw=rpm_at and world.view.read(rpm_at,4)
    local copy_owner=pelicans.owner_of(world,copy_at,PW.copyStride)
    local rpm_owner=rpm_at and pelicans.owner_of(world,rpm_at,4)
    if not(rpm_raw and copy_owner and rpm_owner)then
        return refuse('NOT_PRIVATE','the copy or the current RPM is not in private read-write memory (the copy stays, '
            ..'unchanged)')
    end
    local identity={component='ProjectileWeapon',component_type='native',unique_owner=true,owner_count=1}
    -- The contexts: the copy's projectile type and RPM slots, and the turret's whole current-RPM entry.
    local entry_at=rpm_at-PW.currentRpm
    local entry=world.view.read(entry_at,PW.currentStride)
    if not(entry and pelicans.owner_of(world,entry_at,PW.currentStride))then
        return refuse('NOT_PRIVATE','the current-RPM entry is unreadable (the copy stays, unchanged)')
    end
    local plan={snapshots={{owner=copy_owner,offset=copy_at-copy_owner.base,bytes=copy:sub(1,0x10)},
            {owner=rpm_owner,offset=entry_at-rpm_owner.base,bytes=entry}},
        changes={{label='turret.'..t.entity..'.copy.projectile',owner=copy_owner,offset=copy_at-copy_owner.base,
                expected=copy:sub(1,4),desired=u32(M.GATLING_PROJECTILE),before=copy:sub(1,4),already_desired=false,
                identity=identity,chain={}},
            {label='turret.'..t.entity..'.current_rpm',owner=rpm_owner,offset=rpm_at-rpm_owner.base,expected=rpm_raw,
                desired=f32e(M.GATLING_RPM),before=rpm_raw,already_desired=false,identity=identity,chain={}}}}
    local report=transaction.apply(runtime,plan)
    metrics.count('pelican_gatling.transactions')
    if report.status~='APPLIED'then
        return refuse('GUARD_REJECTED','the writes were refused: '..tostring(report.reason)..' (the copy stays, unchanged)')
    end
    local again=pelicans.weapon_config(world,t.entity)
    local result={pelican=pelican,turret=t.entity,copy=ci,writes=report.writes,shared_before=before_shared,
        verify={projectile=again~=nil and again.copy~=nil and again.copy.projectileType==M.GATLING_PROJECTILE,
            rpm=again~=nil and again.currentRpm==M.GATLING_RPM,
            nonTarget=report.non_target_bytes_unchanged==true,protection=report.protection_restored==true}}
    local verified=true
    for _,v in pairs(result.verify)do if v~=true then verified=false end end
    result.verified=verified
    log(('APPLIED (%s): chin turret %d: own projectile %s, current RPM %s (%d writes); verified %s; the engine derives the '
        ..'shot interval next update; ammo pattern and spin-up stay the chin turret\'s (type data / no component)')
        :format(label,t.entity,tostring(again and again.copy and again.copy.projectileType),
        tostring(again and again.currentRpm),report.writes,tostring(verified)))
    return result
end

function M.reset()spawned={};replaced={};gate=nil end
return M
