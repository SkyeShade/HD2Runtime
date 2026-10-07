-- PER-SHOT MODIFICATION (development, solo; the user's request of 2026-10-07; research/projectile-ballistics-
-- F5FEE03DCFDB.json, domains/projectile_ballistics.lua). Not exported directly: hd2.projectiles.modify_shots
-- (api/shots.lua) configures it.
--
-- A weapon fires its own vanilla projectile, aimed, spread, timed and networked by the game. SpawnProjectile copies the
-- row's stats into that one projectile's own pool records, and the projectile update, the ballistic integrator and hit
-- processing read those copies, never the row again (the research's verdicts, every retained snapshot):
--   * hit +0x34 the DAMAGE MULTIPLIER (f32, 1.0 at spawn): each direct hit's damage event x it (0x13AD524), before the
--     damage values are built; hit +0x38 the PENETRATION MULTIPLIER (x each of the event's four penetration lanes,
--     rounded; 0x13AD550). Explosions are separate and never scaled;
--   * flight +0x0C the velocity and +0x2C the reference speed (both x `speed`: the update ends a shot below 0.1 x the
--     reference and scales a direct hit by 0.25 + 0.75 (|v| / reference)^2, so both move together and the damage
--     factor stays the game's); +0x1C the gravity multiplier, +0x28 the drag constant.
-- So a configuration names a weapon (its projectile types and the entity types that fire them: the projectile homing
-- research's list) and multipliers; each update the watch reads the projectiles spawned since its last look (the pool's
-- spawn counter, read-only) and, for each that is this machine's player's own shot of that weapon (the type, the source
-- entity's type, credited to the local peer, in flight, not driven by a unit), writes its members ONCE: one guarded
-- transaction over its flight, hit, type and flags records read this update (private read-write memory only, the exact
-- bytes just read as expected, a read-back). Every other projectile, every row, every DamageInfo row and the weapon
-- itself are never written: another weapon firing the same projectile type (the Liberator Carbine, the Stalwart) stays
-- vanilla. A Lua update runs before the game update that steps projectiles (projectile_impact: 0.00 m travelled at the
-- first read); the distance a shot had travelled when it was written is reported.
--
-- Scope: SOLO (several players: NOT_SOLO, the shot stays vanilla): every machine simulates its own copy of a shot, and
-- which copy's hit decides damage with several players is not established. NOT LIVE-PROVEN: the write's effect (a
-- damage multiplier on the hit record), any clamp further down the damage path, the timing.
if rawget(_G,'jit')then jit.off(true,true)end
local world_module=require('hd2runtime/runtime/event_world')
local transaction=require('hd2runtime/core/guarded_transaction')
local scheduler=require('hd2runtime/runtime/scheduler')
local metrics=require('hd2runtime/runtime/metrics')
local log_module=require('hd2runtime/runtime/log')
local b=require('hd2runtime/core/bytes')
local natives=require('hd2runtime/domains/event_natives')
local PO=require('hd2runtime/domains/projectile_rows').pool
local DB=require('hd2runtime/domains/projectile_ballistics')
local DD=require('hd2runtime/domains/direct_damage')
local M={}
M.MAX_CONFIGS=64
M.MAX_READS=64            -- new slots examined per update at most (the newest are kept)
M.CHANGES={damage=true,armor_penetration=true,speed=true,gravity=true,drag=true}
local F,H,FL=DB.flight,DB.hit,PO.flags
local COUNTER_RANGE=4294967296
local DAMAGE_TABLE=tonumber(DD.table:sub(3),16)

local configs={}
local by_type={}
local pool={}
local clock=0
local next_id=0
local watch
local unavailable_logged
local in_mission=false

local function log(text)log_module.emit('[HD2Runtime] shots '..text)end
local function detail(text)log_module.detail('[HD2Runtime] shots '..text)end

-- The pins of the research and the pool's, proven once per loaded game.dll. true, or nil and the first mismatch.
function M.prove(world)
    if world.projectile_shots_proven then return true end
    if DB.source.gameDllSha256~=natives.source.gameDllSha256 then
        return nil,'the projectile ballistics research covers another game.dll build'
    end
    local ok,why=world_module.prove_projectile_pool(world)
    if not ok then return nil,why end
    for _,pin in ipairs(DB.pins)do
        if not world.view.proves(world.game+pin.rva,pin.hex)then
            return nil,('native projectile code changed (%s at game+%X)'):format(pin.label,pin.rva)
        end
    end
    world.projectile_shots_proven=true
    return true
end

local function f32(bytes,offset)
    local n=b.u32(bytes,offset)
    if math.floor(n/8388608)%256==255 then return nil end
    return b.value(bytes,offset,'f32')
end
local function enc(v)return b.encode(v,'f32')end
local function finite(v)return type(v)=='number'and v==v and v>-1e9 and v<1e9 end

-- A DamageInfo row's values, read only: {id, standard, durable, armor_penetration = {4}}, or {id} when unreadable.
local function damage_info(world,id)
    local out={id=id}
    local row=type(id)=='number'and id>0 and id<4096 and world.view.pointer(world.game+DAMAGE_TABLE+id*8)
    local raw=row and world.view.read(row,DD.stride)
    if raw and b.u32(raw,0)==id then
        out.standard,out.durable=b.u32(raw,4),b.u32(raw,8)
        out.armor_penetration={b.u32(raw,0xC),b.u32(raw,0x10),b.u32(raw,0x14),b.u32(raw,0x18)}
    end
    return out
end
M.damage_info=damage_info

local function owner_of(world,address,size)
    local r=world.runtime.query and world.runtime.query(address)
    if not(r and r.state==0x1000 and r.type==0x20000 and r.protect==4 and address>=r.base and address+size<=r.base+r.size)
    then return nil end
    return {base=r.allocation_base,size=r.base+r.size-r.allocation_base,type=0x20000,protect=4}
end

local function count(config,code,reason,slot)
    config.refused[code]=(config.refused[code]or 0)+1
    if config.refused[code]==1 then
        log(('(%s): %s shot%s stays vanilla: %s: %s'):format(config.label,config.weapon,
            slot and(' in pool slot '..slot)or'',code,reason))
    end
end

local function emit(config,event)
    if not config.callback then return end
    local ok,why=pcall(config.callback,event)
    if not ok and not config.callback_failed then
        config.callback_failed=true
        log(('(%s): on_shot failed: %s'):format(config.label,tostring(why)))
    end
end

-- The shot's stats as its records hold them: {damage_multiplier, penetration_multiplier, velocity = {x, y, z}, speed
-- (|velocity|), reference_speed, gravity, drag, distance, damage = {id, standard, durable, armor_penetration},
-- armor_penetration = {4 lanes of the hit record}}, or nil and why.
local function stats_of(world,flight,hit)
    local s={damage_multiplier=f32(hit,H.damageMultiplier),penetration_multiplier=f32(hit,H.penetrationMultiplier),
        reference_speed=f32(flight,F.speed),gravity=f32(flight,F.gravity),drag=f32(flight,F.drag),
        distance=f32(flight,F.distance),velocity={f32(flight,F.velocity),f32(flight,F.velocity+4),f32(flight,F.velocity+8)}}
    for _,k in ipairs({'damage_multiplier','penetration_multiplier','reference_speed','gravity','drag','distance'})do
        if not finite(s[k])then return nil,k..' is not a finite number'end
    end
    for k=1,3 do if not finite(s.velocity[k])then return nil,'the velocity is not finite'end end
    s.speed=math.sqrt(s.velocity[1]^2+s.velocity[2]^2+s.velocity[3]^2)
    s.damage=damage_info(world,b.u32(hit,H.directDamage))
    s.armor_penetration={}
    for k=0,3 do
        local at=H.armorPenetration+k*2
        s.armor_penetration[k+1]=hit:byte(at+1)+hit:byte(at+2)*256
    end
    return s
end
M.stats_of=stats_of

-- One new slot of a configured type: this machine's player's own shot of a configured weapon? Writes it once.
local function consider(world,system,slot,kind,local_lo,local_hi,player_count)
    local list=by_type[kind]
    if not list then return end
    local flight_address=system+F.base+slot*F.stride
    local hit_address=system+H.base+slot*H.stride
    local type_address=system+PO.types.base+slot*PO.types.stride
    local flags_address=system+FL.base+slot*FL.stride
    local flight=world.view.read(flight_address,F.read)
    local hit=world.view.read(hit_address,H.stride)
    local kind_bytes=world.view.read(type_address,PO.types.stride)
    local flags=world.view.read(flags_address,FL.stride)
    if not(flight and hit and kind_bytes and flags)or b.u32(kind_bytes,0)~=kind then return end
    local flag_word=flags:byte(1)+flags:byte(2)*256
    if math.floor(flag_word/FL.inFlight)%2~=1 then return end
    local clo,chi=b.u32(hit,PO.hit.creditor),b.u32(hit,PO.hit.creditor+4)
    if not(local_lo~=nil and clo==local_lo and chi==local_hi)then
        for _,c in ipairs(list)do c.others=c.others+1 end
        return
    end
    local source=world.view.u32(system+PO.source.base+slot*PO.source.stride+PO.source.entity)
    local source_type=source and world_module.entity_type(world,source)
    local config
    for _,c in ipairs(list)do if source_type and c.sources[source_type]then config=c;break end end
    if not config then
        for _,c in ipairs(list)do c.other_sources=c.other_sources+1 end
        return
    end
    config.shots=config.shots+1
    if player_count>1 then
        return count(config,'NOT_SOLO',player_count..' players: per-shot modification is solo only (every machine '
            ..'simulates its own copy; which one decides the damage is not established)',slot)
    end
    if b.u32(flight,F.unit)~=0 then
        return count(config,'UNIT_DRIVEN','a unit drives this projectile',slot)
    end
    if hit:byte(PO.hit.impactRequested+1)~=0 then return count(config,'MISSED','its impact was already requested',slot)end
    local before,why=stats_of(world,flight,hit)
    if not before then return count(config,'UNEXPECTED_STATE',why,slot)end
    if before.damage_multiplier<=0 or before.damage_multiplier>1000 or before.penetration_multiplier<=0
            or before.penetration_multiplier>1000 or before.reference_speed<=0 then
        return count(config,'UNEXPECTED_STATE',('multipliers %g / %g, reference speed %g'):format(
            before.damage_multiplier,before.penetration_multiplier,before.reference_speed),slot)
    end
    local ch=config.changes
    local owner=owner_of(world,flight_address,F.read)
    if not(owner and owner_of(world,hit_address,H.stride)and owner_of(world,type_address,PO.types.stride)
            and owner_of(world,flags_address,FL.stride))then
        return count(config,'NOT_PRIVATE','the projectile pool is not in private read-write memory',slot)
    end
    local changes={}
    local function change(name,address,bytes_now,value)
        local desired=enc(value)
        if desired==bytes_now then return end
        changes[#changes+1]={label=('projectile.pool.slot%d.%s'):format(slot,name),owner=owner,
            offset=address-owner.base,expected=bytes_now,desired=desired,before=bytes_now,already_desired=false,
            identity={component='ProjectileSystem',component_type='native',record_type='projectile pool record',
                unique_owner=true,owner_count=1},chain={}}
    end
    local function hit4(o)return hit:sub(o+1,o+4)end
    local function flight4(o)return flight:sub(o+1,o+4)end
    if ch.damage then change('damageMultiplier',hit_address+H.damageMultiplier,hit4(H.damageMultiplier),
        before.damage_multiplier*ch.damage)end
    if ch.armor_penetration then change('penetrationMultiplier',hit_address+H.penetrationMultiplier,
        hit4(H.penetrationMultiplier),before.penetration_multiplier*ch.armor_penetration)end
    if ch.speed then
        for k=0,2 do change('velocity+'..(k*4),flight_address+F.velocity+k*4,flight4(F.velocity+k*4),
            before.velocity[k+1]*ch.speed)end
        change('referenceSpeed',flight_address+F.speed,flight4(F.speed),before.reference_speed*ch.speed)
    end
    if ch.gravity then change('gravity',flight_address+F.gravity,flight4(F.gravity),before.gravity*ch.gravity)end
    if ch.drag then change('drag',flight_address+F.drag,flight4(F.drag),before.drag*ch.drag)end
    local event={kind='modified',slot=slot,source=source,type=kind,weapon=config.weapon,before=before,
        distance=before.distance,changes=ch}
    if#changes==0 then
        event.kind='untouched';event.after=before;event.writes=0
        config.untouched=config.untouched+1
        emit(config,event)
        return
    end
    local function context(address,bytes)return {owner=owner,offset=address-owner.base,bytes=bytes}end
    local plan={snapshots={context(flight_address,flight),context(hit_address,hit),context(type_address,kind_bytes),
        context(flags_address,flags)},changes=changes}
    local report=transaction.apply(world.runtime,plan)
    metrics.count('projectile_shots.transactions')
    if report.status~='APPLIED'then return count(config,'GUARD_REJECTED',tostring(report.reason),slot)end
    local after_flight=world.view.read(flight_address,F.read)
    local after_hit=world.view.read(hit_address,H.stride)
    local after=after_flight and after_hit and stats_of(world,after_flight,after_hit)
    local verified=after~=nil
    for _,c in ipairs(changes)do
        local now=world.view.read(owner.base+c.offset,4)
        verified=verified and now==c.desired
    end
    event.after=after
    event.writes=report.writes
    event.verify={readBack=verified,nonTarget=report.non_target_bytes_unchanged==true,
        protection=report.protection_restored==true}
    config.modified=config.modified+1
    config.writes=config.writes+report.writes
    if config.modified==1 then
        log(('(%s): first %s shot modified: pool slot %d (projectile %d, %.2f m travelled): damage multiplier %g -> %g, '
            ..'penetration multiplier %g -> %g, speed %.1f -> %.1f m/s, gravity %g -> %g, drag %g -> %g; its direct hit '
            ..'DamageInfo %s (%s / %s); %d write%s, read back %s, non-target bytes unchanged %s, protection restored %s')
            :format(config.label,config.weapon,slot,kind,before.distance,before.damage_multiplier,
            after and after.damage_multiplier or-1,before.penetration_multiplier,after and after.penetration_multiplier or-1,
            before.speed,after and after.speed or-1,before.gravity,after and after.gravity or-1,before.drag,
            after and after.drag or-1,tostring(before.damage.id),tostring(before.damage.standard),
            tostring(before.damage.durable),report.writes,report.writes==1 and''or's',tostring(verified),
            tostring(event.verify.nonTarget),tostring(event.verify.protection)))
    else
        detail(('(%s): pool slot %d modified (%d writes, read back %s)'):format(config.label,slot,report.writes,
            tostring(verified)))
    end
    emit(config,event)
end

local function summary(config,why)
    if config.shots==0 then return end
    local parts={}
    for code,n in pairs(config.refused)do parts[#parts+1]=('%s x %d'):format(code,n)end
    table.sort(parts)
    log(('(%s): %s: %d own %s shot%s seen, %d modified (%d writes), %d untouched (multipliers 1), %d not this player\'s '
        ..'and %d from another weapon left vanilla%s'):format(config.label,why,config.shots,config.weapon,
        config.shots==1 and''or's',config.modified,config.writes,config.untouched,config.others,config.other_sources,
        #parts>0 and('; vanilla: '..table.concat(parts,', '))or''))
end
local function reset_mission(why)
    pool={}
    for _,config in ipairs(configs)do
        summary(config,why)
        config.shots,config.modified,config.writes,config.untouched,config.others,config.other_sources=0,0,0,0,0,0
        config.refused={}
    end
end

M.OFF_MISSION_EVERY=0.5
local off_mission_at=-math.huge
local function step(dt)
    clock=clock+(dt or 0)
    if not in_mission and clock-off_mission_at<M.OFF_MISSION_EVERY then return end
    local world=world_module.open()
    if not world then return end
    local game=world_module.game_state(world)
    if not(game and game.mission)then
        if in_mission then reset_mission('the mission ended')end
        in_mission=false
        off_mission_at=clock
        return
    end
    in_mission=true
    local ok,reason=M.prove(world)
    if not ok then
        if unavailable_logged~=reason then
            unavailable_logged=reason
            log('UNAVAILABLE: every shot stays vanilla: '..tostring(reason))
        end
        return
    end
    local counter,system=world_module.projectile_counter(world)
    if not counter then pool={};return end
    if pool.system~=system or not pool.counter then pool.system,pool.counter=system,counter;return end
    local n=(counter-pool.counter)%COUNTER_RANGE
    local from=pool.counter
    pool.counter=counter
    if n<=0 or n>PO.slots then return end
    if n>M.MAX_READS then from=(from+n-M.MAX_READS)%COUNTER_RANGE;n=M.MAX_READS end
    local slots=world_module.projectile_types(world,system,from,n)
    local lo,hi,player_count
    for _,item in ipairs(slots or{})do
        if by_type[item.type]then
            if player_count==nil then
                lo,hi=world_module.local_peer(world)
                player_count=#(world_module.players(world)or{})
            end
            consider(world,system,item.slot,item.type,lo,hi,player_count)
        end
    end
end
M.step=step

local function active_count()
    local n=0
    for _,config in ipairs(configs)do if config.status=='active'then n=n+1 end end
    return n
end
local function ensure_watch()
    if watch and watch.status=='active'then return end
    watch={status='active'}
    function watch.tick(dt)
        if watch.status~='active'then return end
        local started=metrics.now()
        local ok,why=pcall(step,dt)
        if not ok then log('update failed: '..tostring(why))end
        metrics.elapsed('projectile_shots.tick',started)
        if active_count()==0 then watch.status='complete';reset_mission('stopped')end
    end
    function watch.cancel()watch.status='cancelled'end
    scheduler.attach(watch)
end
local function rebuild_types()
    by_type={}
    for _,config in ipairs(configs)do
        if config.status=='active'then
            for _,kind in ipairs(config.types)do
                local list=by_type[kind]or{}
                list[#list+1]=config
                by_type[kind]=list
            end
        end
    end
end

-- Adds (or, for the same owner and weapon, replaces) a configuration. spec = {owner, weapon, types (projectile types),
-- sources (entity types, 16 hex digits), changes = {damage, armor_penetration, speed, gravity, drag: multipliers},
-- label, callback(event)}; already validated by api/shots.lua. Returns the configuration, or nil, code, reason.
function M.configure(spec)
    for index,config in ipairs(configs)do
        if config.weapon==spec.weapon and config.status=='active'then
            if config.owner~=spec.owner then
                return nil,'ALREADY_MODIFIED',spec.weapon..' shots are already modified for '..config.owner
            end
            config.status='replaced'
            table.remove(configs,index)
            break
        end
    end
    if active_count()>=M.MAX_CONFIGS then return nil,'LIMIT','at most '..M.MAX_CONFIGS..' shot configurations'end
    local sources={}
    for _,kind in ipairs(spec.sources or{})do sources[kind]=true end
    if not next(sources)then return nil,'UNKNOWN_WEAPON','no entity type fires '..tostring(spec.weapon)end
    next_id=next_id+1
    local config={id=next_id,status='active',owner=spec.owner,weapon=spec.weapon,types=spec.types,sources=sources,
        changes=spec.changes,label=spec.label or(spec.owner..' '..spec.weapon),callback=spec.callback,
        shots=0,modified=0,writes=0,untouched=0,others=0,other_sources=0,refused={}}
    configs[#configs+1]=config
    rebuild_types()
    ensure_watch()
    return config
end
-- New multipliers for the next shots (shots already written keep theirs).
function M.set(config,changes)
    if not config or config.status~='active'then return false end
    config.changes=changes
    return true
end
function M.stop(config)
    if not config or config.status~='active'then return false end
    summary(config,'stopped')
    config.status='stopped'
    for index,item in ipairs(configs)do if item==config then table.remove(configs,index)break end end
    rebuild_types()
    return true
end
function M.configs()return configs end
function M.reset_for_tests()
    configs,by_type,pool={},{},{}
    clock,next_id,unavailable_logged,in_mission=0,0,nil,false
    off_mission_at=-math.huge
    if watch then watch.status='cancelled'end
    watch=nil
end
return M
