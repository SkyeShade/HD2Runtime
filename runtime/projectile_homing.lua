-- Projectile homing (docs/projectile-homing.md; research/projectile-homing-F5FEE03DCFDB.json; domains/projectile_homing.lua).
-- Not exported directly: hd2.projectiles.homing (api/homing.lua) configures it.
--
-- A homing configuration names one catalogued projectile output (its vanilla type and, when the catalogue knows it, the
-- entity type of the weapon that fires it) and what its shots home on: 'enemy' (a living catalogued enemy) or
-- 'friendly' (another player's living Helldiver). Each update the watch reads the projectiles spawned since its last look
-- (the pool's spawn counter, read-only, as runtime/projectile_impact.lua does) and follows the shots that are this
-- machine's player's own: the configured type, fired by the configured weapon, credited to the local peer, in flight
-- and not driven by a unit.
--
-- Steering is ONE member of that one projectile: its own velocity copy (flight record +0x0C, 3 x f32). The projectile
-- update hands exactly that vector to the ballistic integrator, which integrates the position from it and hit-tests the
-- step from where it was to where it went (the research's proofs 1..3), so a velocity written before the update is the
-- direction the shot flies and hits along. Runtime turns the velocity toward the target by at most turn_rate x dt and
-- keeps its length (the update's speed rule is a ratio to the spawn speed, proof 4). Gravity, drag, ricochets and the
-- impact stay the game's: the next step simply starts from the turned vector. A Lua update runs before the game update
-- that steps projectiles (projectile_impact: measured 0.00 m travelled at the first read).
--
-- Every write is a guarded transaction over that projectile's records read this update (its flight record with the
-- target, its hit record, its type entry and its flags), on private read-write memory only, with the exact velocity
-- bytes just read as the expected bytes and a read-back. A shot whose records no longer say the same projectile (another
-- type, another owner or creditor, no longer in flight, its impact requested, a shorter distance travelled than last
-- time: the slot was reused) is dropped and never written again.
--
-- Targets: enemies come from the game's health records (the entity hash and descriptors, as the health event source
-- reads them; catalogued kind 'enemy', alive), players from the player list (an avatar that is not this machine's,
-- alive). The aim point is the target's unit root plus aim_height metres up (+Z). A shot acquires the target with the
-- smallest angle off its direction inside the cone and the range, and keeps it while it lives (retarget: another when it
-- dies). The enemy list is built incrementally, SCAN_SLOTS hash slots and POSITIONS_PER_UPDATE positions per update, and
-- only while it can be needed: the local player holds a configured weapon, or a configured shot flew within
-- ACTIVE_WINDOW seconds. A locked target's position is re-read every update.
--
-- Scope: this machine's own pool and its own player's shots. Solo by default; with several players a configuration
-- needs multiplayer = true (experimental): every machine flies its own copy of a shot, and the shooter's impact message
-- makes the others explode their copy where the shooter's copy hit (research proof 8, traced), so other machines draw
-- the shot flying straight with its hit where it homed. Another player's shots are never touched.
if rawget(_G,'jit')then jit.off(true,true)end
local world_module=require('hd2runtime/runtime/event_world')
local transaction=require('hd2runtime/core/guarded_transaction')
local scheduler=require('hd2runtime/runtime/scheduler')
local metrics=require('hd2runtime/runtime/metrics')
local log_module=require('hd2runtime/runtime/log')
local b=require('hd2runtime/core/bytes')
local natives=require('hd2runtime/domains/event_natives')
local PO=require('hd2runtime/domains/projectile_rows').pool
local HD=require('hd2runtime/domains/projectile_homing')
local M={}
M.MAX_CONFIGS=128        -- one per weapon and projectile type
M.MAX_TRACKED=16          -- shots steered at once (more fly straight, counted BUSY)
M.MAX_READS=64            -- new slots examined per update at most (the newest are kept)
M.MAX_FOLLOW=10           -- seconds a shot is followed at most
M.MAX_CANDIDATES=256      -- enemies kept per scan pass
M.SCAN_SLOTS=512          -- health hash slots scanned per update
M.POSITIONS_PER_UPDATE=12 -- enemy positions re-read per update (round robin)
M.POSITION_AGE=0.5        -- seconds an enemy position stays usable for acquisition
M.FRIENDS_EVERY=0.2       -- seconds between two reads of the other players' avatars
M.ACQUIRE_EVERY=0.1       -- seconds between two acquisition attempts of one shot
M.ACTIVE_WINDOW=5         -- the enemy list stays warm this long after the last configured shot
M.HELD_EVERY=0.5          -- seconds between two checks of what the local player holds
M.MIN_TURN=math.rad(0.05) -- a smaller correction is not written
M.MIN_SPEED=1             -- m/s; a slower shot is not steered
M.PLAYERS_EVERY=0.5
local F,H,FL=HD.flight,PO.hit,PO.flags
local HL=natives.health
local COUNTER_RANGE=4294967296
local PAGE=4096

local configs={}          -- in order
local by_type={}          -- projectile type -> {config, ...}
local tracked={}          -- pool slot -> shot
local tracked_count=0
local pool={}
local clock=0
local last_shot=-math.huge
local next_id=0
local watch
local unavailable_logged
local multiplayer_logged=false
local function fresh_cache()
    return {enemies={list={},by={},pass={},cursor=0,round=0,complete=false},friends=nil,players=nil,known={},
        blocks=nil,held=nil}
end
local cache=fresh_cache()

local function log(text)log_module.emit('[HD2Runtime] homing '..text)end
local function detail(text)log_module.detail('[HD2Runtime] homing '..text)end

-- The pins homing relies on, with the pool's, proven once per loaded game.dll. true, or nil and the first mismatch.
function M.prove(world)
    if world.projectile_homing_proven then return true end
    if HD.source.gameDllSha256~=natives.source.gameDllSha256 then
        return nil,'the projectile homing research covers another game.dll build'
    end
    local ok,why=world_module.prove_projectile_pool(world)
    if not ok then return nil,why end
    for _,pin in ipairs(HD.pins)do
        if not world.view.proves(world.game+pin.rva,pin.hex)then
            return nil,'native projectile update changed ('..pin.label..' at game+'..string.format('%X',pin.rva)..')'
        end
    end
    world.projectile_homing_proven=true
    return true
end

------------------------------------------------------------------------------------------------------- vectors --
local function length(x,y,z)return math.sqrt(x*x+y*y+z*z)end
local function finite(v)return type(v)=='number'and v==v and v>-1e9 and v<1e9 end
-- An f32 member, or nil when it is not finite (b.value refuses those).
local function f32(bytes,offset)
    local n=b.u32(bytes,offset)
    if math.floor(n/8388608)%256==255 then return nil end
    return b.value(bytes,offset,'f32')
end
-- The unit vector `angle` radians from unit vector a toward unit vector c (the shortest arc), and the angle between a
-- and c. c itself is returned when it is within angle.
local function turn_toward(ax,ay,az,cx,cy,cz,angle)
    local cosine=math.max(-1,math.min(1,ax*cx+ay*cy+az*cz))
    local between=math.acos(cosine)
    if between<=angle then return cx,cy,cz,between end
    local s=math.sin(between)
    if s<1e-6 then
        -- Opposite directions: turn about any axis perpendicular to a.
        local px,py,pz=-ay,ax,0
        if length(px,py,pz)<1e-6 then px,py,pz=0,-az,ay end
        local n=length(px,py,pz)
        px,py,pz=px/n,py/n,pz/n
        local c2,s2=math.cos(angle),math.sin(angle)
        return ax*c2+px*s2,ay*c2+py*s2,az*c2+pz*s2,between
    end
    local wa,wc=math.sin(between-angle)/s,math.sin(angle)/s
    local x,y,z=ax*wa+cx*wc,ay*wa+cy*wc,az*wa+cz*wc
    local n=length(x,y,z)
    return x/n,y/n,z/n,between
end
M.turn_toward=turn_toward

------------------------------------------------------------------------------------------------------ targets --
local function u32(bytes,offset)return b.u32(bytes,offset)end

-- This machine's player list (cached PLAYERS_EVERY): {count, local_avatar, others = {{peer, avatar}}}.
local function players(world)
    local p=cache.players
    if p and clock-p.at<M.PLAYERS_EVERY then return p end
    local list=world_module.players(world,true)
    p={at=clock,count=#list,others={}}
    for _,item in ipairs(list)do
        if item['local']then p.local_avatar=item.avatar
        elseif item.avatar then p.others[#p.others+1]={peer=item.peer,avatar=item.avatar}end
    end
    cache.players=p
    return p
end

local function blocks(world)
    if not cache.blocks then
        local v=world.view
        cache.blocks={header=v.slot(),buckets=v.slot(),pointers=v.slot()}
    end
    return cache.blocks
end

-- One update's share of the enemy list. The health manager is read the way the health event source reads it (the
-- entity hash, the descriptor pointers, a descriptor only for an entity not seen with that descriptor before):
-- SCAN_SLOTS hash slots per update; every living catalogued enemy of a finished pass (at most MAX_CANDIDATES) is the
-- list, {entity, unit, type, name, x, y, z, at}. Then POSITIONS_PER_UPDATE of the listed enemies' positions are
-- re-read (round robin); an enemy whose unit no longer resolves leaves the list.
local function scan_enemies(world)
    local e=cache.enemies
    local bl=blocks(world)
    local header=world_module.health_header(world,bl.header)
    if not(header and header.buckets and header.records and header.descriptors)then return end
    local live,capacity=header.live,header.hash_capacity
    if e.cursor>=capacity then e.cursor=0 end
    local first=e.cursor
    local n=math.min(M.SCAN_SLOTS,capacity-first)
    local view=world.view
    local buckets=view.fill(bl.buckets,header.buckets+first*8,n*8)
    local pointers=live>0 and view.fill(bl.pointers,header.descriptors,live*8)
    if buckets and pointers then
        local known=cache.known
        local D,R=HL.descriptor,HL.record
        for k=0,n-1 do
            local entity=buckets:u32(k*8)
            if entity~=header.hash_empty then
                local index=buckets:u32(k*8+4)
                if index<live then
                    local descriptor=pointers:ptr(index*8)
                    local entry=known[entity]
                    if entry and entry.descriptor~=descriptor then entry=nil end
                    if not entry and descriptor then
                        local d=view.read(descriptor,D.size)
                        if d and u32(d,D.entity)==entity then
                            local kind=string.format('%08X%08X',u32(d,D.type+4),u32(d,D.type))
                            local info=world_module.type_info(kind)
                            entry={descriptor=descriptor,unit=u32(d,D.unit),type=kind,
                                enemy=info~=nil and info.kind=='enemy',name=info and(info.display or info.name)or kind}
                            known[entity]=entry
                        end
                    end
                    if entry then
                        entry.round=e.round
                        if entry.enemy and entry.unit~=0 and#e.pass<M.MAX_CANDIDATES then
                            local life=view.u32(header.records+index*HL.stride+R.life)
                            if life and life<2 then
                                local prior=e.by[entity]
                                e.pass[#e.pass+1]=prior or{entity=entity,unit=entry.unit,type=entry.type,name=entry.name}
                            end
                        end
                    end
                end
            end
        end
    end
    e.cursor=first+n
    if e.cursor>=capacity then
        -- A finished pass: its enemies are the list; entities not seen in it are forgotten.
        local list,by={},{}
        for _,item in ipairs(e.pass)do list[#list+1]=item;by[item.entity]=item end
        e.list,e.by,e.pass,e.cursor,e.complete=list,by,{},0,true
        for entity,entry in pairs(cache.known)do if entry.round~=e.round then cache.known[entity]=nil end end
        e.round=e.round+1
        metrics.count('projectile_homing.enemy_passes')
    end
    metrics.count('projectile_homing.enemy_scan_slots',n)
end

-- POSITIONS_PER_UPDATE listed enemies' root positions, re-read in turn.
local function refresh_positions(world)
    local e=cache.enemies
    local list=e.list
    for _=1,math.min(M.POSITIONS_PER_UPDATE,#list)do
        if not e.position_cursor or e.position_cursor>#list then e.position_cursor=1 end
        local item=list[e.position_cursor]
        local p=world_module.unit_position(world,item.unit)
        if p then item.x,item.y,item.z,item.at=p.x,p.y,p.z,clock else item.at=nil end
        e.position_cursor=e.position_cursor+1
    end
end

-- Every other player's living avatar now: {{entity, unit, peer, name, x, y, z}}.
local function scan_friends(world)
    local out={}
    for _,other in ipairs(players(world).others)do
        local state=world_module.entity_state(world,other.avatar)
        local unit=state and state.life==0 and state.descriptor.unit
        local p=unit and unit~=0 and world_module.unit_position(world,unit)
        if p then
            out[#out+1]={entity=other.avatar,unit=unit,peer=other.peer,name='player '..other.peer,x=p.x,y=p.y,z=p.z}
        end
    end
    return out
end

-- The candidates of a target kind: {list, by (entity -> item)}. Enemies: the incremental list (an item is usable for
-- acquisition while its position is at most POSITION_AGE old). Friends: re-read every FRIENDS_EVERY seconds.
local function candidates(world,kind)
    if kind~='friendly'then return cache.enemies end
    local c=cache.friends
    if not c or clock-c.at>=M.FRIENDS_EVERY then
        c={at=clock,list=scan_friends(world),by={}}
        for _,item in ipairs(c.list)do item.at=clock;c.by[item.entity]=item end
        cache.friends=c
    end
    return c
end

-- The target's aim point now (its unit root + aim_height up), or nil when it is gone or dead.
local function aim_point(world,shot,config,positions)
    local target=shot.target
    if world_module.entity_exists(world,target.entity)~=true then return nil end
    local c=candidates(world,config.target)
    if not c.by[target.entity]then return nil end
    local p=positions[target.unit]
    if p==nil then
        p=world_module.unit_position(world,target.unit)or false
        positions[target.unit]=p
    end
    if not p then return nil end
    return p.x,p.y,p.z+config.aim_height
end

-- The candidate with the smallest angle off the shot's direction (dx, dy, dz: a unit vector) inside the cone and the
-- range, or nil.
local function acquire(world,config,px,py,pz,dx,dy,dz)
    local best,best_cos,best_distance
    for _,item in ipairs(candidates(world,config.target).list)do
        local tx,ty,tz,distance
        if item.at and clock-item.at<=M.POSITION_AGE then
            tx,ty,tz=item.x-px,item.y-py,item.z+config.aim_height-pz
            distance=length(tx,ty,tz)
        end
        if distance and distance>0.5 and distance<=config.range then
            local cosine=(tx*dx+ty*dy+tz*dz)/distance
            if cosine>=config.cone_cos and(not best or cosine>best_cos)then
                best,best_cos,best_distance=item,cosine,distance
            end
        end
    end
    return best,best_distance
end

----------------------------------------------------------------------------------------------------- refusals --
local function count(config,code,reason,slot)
    config.refused[code]=(config.refused[code]or 0)+1
    if config.refused[code]==1 then
        log(('(%s): %s shot%s flies straight: %s: %s'):format(config.label,config.weapon,
            slot and(' in pool slot '..slot)or'',code,reason))
    end
end

local function owner_of(world,address,size)
    local r=world.runtime.query and world.runtime.query(address)
    if not(r and r.state==0x1000 and r.type==0x20000 and r.protect==4 and address>=r.base and address+size<=r.base+r.size)
    then return nil end
    return {base=r.allocation_base,size=r.base+r.size-r.allocation_base,type=0x20000,protect=4}
end

-- The velocity change as aligned pieces that never cross a page (a transaction change stays inside one page).
local function velocity_changes(owner,address,before,desired,slot)
    local out={}
    local at,offset=address,0
    while offset<12 do
        local room=PAGE-at%PAGE
        local width=math.min(12-offset,room)
        if width>=12 then width=12 elseif width>=8 then width=8 else width=4 end
        out[#out+1]={label=('projectile.pool.slot%d.velocity+%d'):format(slot,offset),owner=owner,
            offset=at-owner.base,expected=before:sub(offset+1,offset+width),desired=desired:sub(offset+1,offset+width),
            before=before:sub(offset+1,offset+width),already_desired=false,
            identity={component='ProjectileSystem',component_type='native',record_type='projectile flight record',
                unique_owner=true,owner_count=1},chain={}}
        at,offset=at+width,offset+width
    end
    return out
end

------------------------------------------------------------------------------------------------------- shots --
local function shot_records(world,system,slot)
    local flight=world.view.read(system+PO.flight.base+slot*PO.flight.stride,F.read)
    local hit=world.view.read(system+H.base+slot*H.stride,H.stride)
    local kind=world.view.read(system+PO.types.base+slot*PO.types.stride,PO.types.stride)
    local flags=world.view.read(system+FL.base+slot*FL.stride,FL.stride)
    if not(flight and hit and kind and flags)then return nil end
    return {flight=flight,hit=hit,kind=kind,flags=flags,flag_word=flags:byte(1)+flags:byte(2)*256}
end

local function drop(slot,shot,why)
    if tracked[slot]~=shot then return end
    tracked[slot]=nil
    tracked_count=tracked_count-1
    local config=shot.config
    if shot.writes>0 then
        config.steered=config.steered+1
        detail(('(%s): shot in pool slot %d done after %.2f s: %d write%s, %s'):format(config.label,slot,
            clock-shot.at,shot.writes,shot.writes==1 and''or's',why))
    end
end

-- One new slot of a configured type: is it this machine's player's own shot of a configured weapon? Starts following
-- it, or counts why not.
local function consider(world,system,slot,kind,local_lo,local_hi,player_count)
    local list=by_type[kind]
    if not list then return end
    local r=shot_records(world,system,slot)
    if not r or u32(r.kind,0)~=kind then return end
    if math.floor(r.flag_word/FL.inFlight)%2~=1 then return end
    -- Not this machine's player's shot (another player's, or an enemy's of the same type): never touched, never
    -- looked at further.
    local clo,chi=u32(r.hit,H.creditor),u32(r.hit,H.creditor+4)
    if not(local_lo~=nil and clo==local_lo and chi==local_hi)then
        for _,c in ipairs(list)do if c.status=='active'then c.others=c.others+1;break end end
        return
    end
    local source=world.view.u32(system+PO.source.base+slot*PO.source.stride+PO.source.entity)
    local source_type=source and world_module.entity_type(world,source)
    local config
    for _,c in ipairs(list)do
        if c.status=='active'and source_type and c.sources[source_type]then config=c;break end
    end
    if not config then
        -- The same projectile type from another weapon of this player's.
        for _,c in ipairs(list)do if c.status=='active'then c.other_sources=c.other_sources+1;break end end
        return
    end
    config.shots=config.shots+1
    last_shot=clock
    if player_count>1 and not config.multiplayer then
        return count(config,'NOT_SOLO',player_count..' players: this configuration is solo only (multiplayer = true '
            ..'opts in; other machines draw the shot flying straight)',slot)
    end
    if u32(r.flight,F.unit)~=0 then
        return count(config,'UNIT_DRIVEN','a unit drives this projectile (its velocity is recomputed from the unit)',slot)
    end
    if tracked_count>=M.MAX_TRACKED then
        return count(config,'BUSY','already steering '..M.MAX_TRACKED..' shots',slot)
    end
    if tracked[slot]then drop(slot,tracked[slot],'its slot was reused')end
    tracked[slot]={config=config,type=kind,owner=u32(r.hit,H.owner),creditor_lo=clo,creditor_hi=chi,source=source,
        at=clock,distance=f32(r.flight,F.distance)or 0,writes=0,next_acquire=clock}
    tracked_count=tracked_count+1
    metrics.count('projectile_homing.shots')
end

-- One followed shot, this update: re-read and re-check it, find or keep its target, and steer it.
local function steer(world,system,slot,shot,dt,positions)
    local config=shot.config
    if config.status~='active'then return drop(slot,shot,'its configuration stopped')end
    local r=shot_records(world,system,slot)
    if not r then return drop(slot,shot,'its records are unreadable')end
    if u32(r.kind,0)~=shot.type or u32(r.hit,H.owner)~=shot.owner or u32(r.hit,H.creditor)~=shot.creditor_lo
            or u32(r.hit,H.creditor+4)~=shot.creditor_hi then
        return drop(slot,shot,'its slot holds another projectile now')
    end
    if math.floor(r.flag_word/FL.inFlight)%2~=1 then return drop(slot,shot,'it ended')end
    if r.hit:byte(H.impactRequested+1)~=0 then return drop(slot,shot,'it hit')end
    if r.flag_word%2==1 then return drop(slot,shot,'it stopped moving')end
    if u32(r.flight,F.unit)~=0 then return drop(slot,shot,'a unit drives it now')end
    local distance=f32(r.flight,F.distance)
    if not finite(distance)or distance<shot.distance-0.01 then return drop(slot,shot,'its slot was reused')end
    shot.distance=distance
    if clock-shot.at>M.MAX_FOLLOW then return drop(slot,shot,'followed for '..M.MAX_FOLLOW..' s')end
    if distance<config.arm_distance then return end
    local px,py,pz=f32(r.flight,F.position),f32(r.flight,F.position+4),f32(r.flight,F.position+8)
    local vx,vy,vz=f32(r.flight,F.velocity),f32(r.flight,F.velocity+4),f32(r.flight,F.velocity+8)
    if not(finite(px)and finite(py)and finite(pz)and finite(vx)and finite(vy)and finite(vz))then
        return drop(slot,shot,'its flight is not finite')
    end
    local speed=length(vx,vy,vz)
    if speed<M.MIN_SPEED then return end
    local dx,dy,dz=vx/speed,vy/speed,vz/speed
    local ax,ay,az
    if shot.target then
        ax,ay,az=aim_point(world,shot,config,positions)
        if not ax then
            detail(('(%s): shot in pool slot %d lost its target %s'):format(config.label,slot,shot.target.name))
            shot.target=nil
            if not config.retarget then shot.done=true end
        end
    end
    if shot.done then return end
    if not shot.target then
        if clock<shot.next_acquire then return end
        shot.next_acquire=clock+M.ACQUIRE_EVERY
        local found,range=acquire(world,config,px,py,pz,dx,dy,dz)
        if not found then
            config.no_target=config.no_target+1
            return
        end
        shot.target=found
        ax,ay,az=found.x,found.y,found.z+config.aim_height
        local first=config.locks==0
        config.locks=config.locks+1
        local text=('(%s): %s shot in pool slot %d locked on %s at %.1f m (%s; turn %g deg/s)'):format(config.label,
            config.weapon,slot,found.name,range,config.target,math.deg(config.turn_rate))
        if first then log(text)else detail(text)end
    end
    local tx,ty,tz=ax-px,ay-py,az-pz
    local to=length(tx,ty,tz)
    if to<0.25 then return end
    local nx,ny,nz,between=turn_toward(dx,dy,dz,tx/to,ty/to,tz/to,config.turn_rate*math.max(0,dt or 0))
    if between<M.MIN_TURN then return end
    local before=r.flight:sub(F.velocity+1,F.velocity+12)
    local desired=b.encode(nx*speed,'f32')..b.encode(ny*speed,'f32')..b.encode(nz*speed,'f32')
    if desired==before then return end
    -- The bytes must say exactly the turned velocity at the same speed.
    local ex,ey,ez=b.value(desired,0,'f32'),b.value(desired,4,'f32'),b.value(desired,8,'f32')
    if math.abs(length(ex,ey,ez)-speed)>speed*1e-4+1e-4 or ex*nx+ey*ny+ez*nz<speed*0.9999 then
        count(config,'ENCODING','the turned velocity did not encode exactly',slot)
        return drop(slot,shot,'encoding')
    end
    local flight_address=system+PO.flight.base+slot*PO.flight.stride
    local hit_address=system+H.base+slot*H.stride
    local type_address=system+PO.types.base+slot*PO.types.stride
    local flags_address=system+FL.base+slot*FL.stride
    local owner=owner_of(world,flight_address,F.read)
    if not(owner and owner_of(world,hit_address,H.stride)and owner_of(world,type_address,PO.types.stride)
            and owner_of(world,flags_address,FL.stride))then
        count(config,'NOT_PRIVATE','the projectile pool is not in private read-write memory',slot)
        return drop(slot,shot,'not private memory')
    end
    local function context(address,bytes)return {owner=owner,offset=address-owner.base,bytes=bytes}end
    local plan={snapshots={context(flight_address,r.flight),context(hit_address,r.hit),context(type_address,r.kind),
            context(flags_address,r.flags)},
        changes=velocity_changes(owner,flight_address+F.velocity,before,desired,slot)}
    local report=transaction.apply(world.runtime,plan)
    metrics.count('projectile_homing.transactions')
    if report.status~='APPLIED'then
        count(config,'GUARD_REJECTED',tostring(report.reason),slot)
        return drop(slot,shot,'guard rejected')
    end
    shot.writes=shot.writes+1
    config.writes=config.writes+1
    if config.writes==1 then
        log(('(%s): first steering write: pool slot %d velocity turned %.2f deg toward %s (%d write%s, %d bytes; '
            ..'non-target bytes unchanged %s; protection restored %s; speed kept %.1f m/s)'):format(config.label,slot,
            math.deg(math.min(between,config.turn_rate*(dt or 0))),shot.target.name,report.writes,
            report.writes==1 and''or's',report.bytes_written,tostring(report.non_target_bytes_unchanged==true),
            tostring(report.protection_restored==true),speed))
    end
end

local function summary(config,why)
    if config.shots==0 and config.writes==0 then return end
    local parts={}
    for code,n in pairs(config.refused)do parts[#parts+1]=('%s x %d'):format(code,n)end
    table.sort(parts)
    log(('(%s): %s: projectile %d: %d own shot%s seen, %d steered (%d writes, %d locks, %d acquisitions without a '
        ..'target), %d not this player\'s and %d from another weapon untouched%s'):format(config.label,why,config.type,
        config.shots,config.shots==1 and''or's',config.steered,config.writes,config.locks,config.no_target,config.others,
        config.other_sources,#parts>0 and('; flew straight: '..table.concat(parts,', '))or''))
end

local function reset_mission(why)
    for slot,shot in pairs(tracked)do drop(slot,shot,why)end
    tracked,tracked_count,pool={},0,{}
    cache=fresh_cache()
    last_shot=-math.huge
    for _,config in ipairs(configs)do
        summary(config,why)
        config.shots,config.steered,config.writes,config.locks,config.others,config.no_target=0,0,0,0,0,0
        config.other_sources=0
        config.refused={}
    end
    multiplayer_logged=false
end

-- Whether the local player holds a weapon of a configured entity type (checked every HELD_EVERY seconds).
local source_types={}
local wants_enemies=false
local function holds_configured(world)
    local h=cache.held
    if h and clock-h.at<M.HELD_EVERY then return h.match end
    h={at=clock,match=false}
    local avatar=players(world).local_avatar
    local held=avatar and world_module.equipped(world,avatar)
    if held and held.type and source_types[held.type]then h.match=true end
    cache.held=h
    return h.match
end

local in_mission=false
-- Outside a mission nothing homes: the game state is checked every OFF_MISSION_EVERY seconds only (homing starts at
-- most that long into a mission, while the players drop in).
M.OFF_MISSION_EVERY=0.5
local off_mission_at=-math.huge
local function step(dt)
    clock=clock+(dt or 0)
    if not in_mission and clock-off_mission_at<M.OFF_MISSION_EVERY then return end
    local world,why=world_module.open()
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
            log('UNAVAILABLE: every homing shot flies straight: '..tostring(reason))
        end
        return
    end
    local counter,system=world_module.projectile_counter(world)
    if not counter then pool={};return end
    if pool.system~=system or not pool.counter then
        pool.system,pool.counter=system,counter
        for slot,shot in pairs(tracked)do drop(slot,shot,'the projectile system changed')end
        return
    end
    local n=(counter-pool.counter)%COUNTER_RANGE
    local from=pool.counter
    pool.counter=counter
    if n>0 and n<=PO.slots then
        if n>M.MAX_READS then from=(from+n-M.MAX_READS)%COUNTER_RANGE;n=M.MAX_READS end
        local slots=world_module.projectile_types(world,system,from,n)
        local lo,hi
        local player_count
        for _,item in ipairs(slots or{})do
            if by_type[item.type]then
                if player_count==nil then
                    lo,hi=world_module.local_peer(world)
                    player_count=players(world).count
                    if player_count>1 and not multiplayer_logged then
                        multiplayer_logged=true
                        log(('MULTIPLAYER EXPERIMENTAL: %d players; only this machine\'s player\'s own shots are steered '
                            ..'(configurations with multiplayer = true); other machines draw them flying straight, with '
                            ..'the hit where they homed (docs/projectile-homing.md)'):format(player_count))
                    end
                end
                consider(world,system,item.slot,item.type,lo,hi,player_count)
            end
        end
    end
    -- The enemy list stays warm while it can be needed: a configured weapon in hand, or a configured shot lately.
    if wants_enemies and(tracked_count>0 or clock-last_shot<=M.ACTIVE_WINDOW or holds_configured(world))then
        scan_enemies(world)
        refresh_positions(world)
    end
    if tracked_count==0 then return end
    local positions={}
    for slot,shot in pairs(tracked)do steer(world,system,slot,shot,dt,positions)end
end

local function tick(dt)
    local started=metrics.now()
    local ok,why=pcall(step,dt)
    if not ok then log('update failed: '..tostring(why))end
    metrics.elapsed('projectile_homing.tick',started)
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
        tick(dt)
        if active_count()==0 then watch.status='complete';reset_mission('homing stopped')end
    end
    function watch.cancel()watch.status='cancelled'end
    scheduler.attach(watch)
end

local function rebuild_types()
    by_type,source_types,wants_enemies={},{},false
    for _,config in ipairs(configs)do
        if config.status=='active'then
            local list=by_type[config.type]or{}
            list[#list+1]=config
            by_type[config.type]=list
            for kind in pairs(config.sources)do source_types[kind]=true end
            if config.target=='enemy'then wants_enemies=true end
        end
    end
end

-- Adds (or, for the same owner and output, replaces) a configuration. spec = {owner, output (a key: the weapon and the
-- type), weapon, type, sources (the entity types that fire it, 16 hex digits each), target ('enemy' | 'friendly'),
-- turn_rate (rad/s), cone (rad, half angle), range, arm_distance, aim_height, retarget, multiplayer, label}; already
-- validated by api/homing.lua. Returns the configuration, or nil, code, reason.
function M.configure(spec)
    for index,config in ipairs(configs)do
        if config.output==spec.output and config.status=='active'then
            if config.owner~=spec.owner then
                return nil,'ALREADY_HOMING',spec.weapon..' shots already home for '..config.owner
            end
            config.status='replaced'
            table.remove(configs,index)
            break
        end
    end
    if active_count()>=M.MAX_CONFIGS then return nil,'LIMIT','at most '..M.MAX_CONFIGS..' homing configurations'end
    next_id=next_id+1
    local sources={}
    for _,kind in ipairs(spec.sources or{})do sources[kind]=true end
    if not next(sources)then return nil,'UNKNOWN_WEAPON','no entity type fires '..tostring(spec.weapon)end
    local config={id=next_id,status='active',owner=spec.owner,output=spec.output,weapon=spec.weapon,type=spec.type,
        sources=sources,target=spec.target,turn_rate=spec.turn_rate,cone=spec.cone,
        cone_cos=math.cos(spec.cone),range=spec.range,arm_distance=spec.arm_distance,aim_height=spec.aim_height,
        retarget=spec.retarget,multiplayer=spec.multiplayer,label=spec.label or(spec.owner..' '..spec.weapon),
        shots=0,steered=0,writes=0,locks=0,others=0,no_target=0,other_sources=0,refused={}}
    configs[#configs+1]=config
    rebuild_types()
    ensure_watch()
    return config
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
-- The enemy list as the last finished scan pass left it (read-only diagnostics and validation).
function M.enemies()return cache.enemies.list,cache.enemies.complete end
function M.tracked()return tracked,tracked_count end
function M.reset_for_tests()
    configs,by_type,tracked,tracked_count,pool,source_types,wants_enemies={},{},{},0,{},{},false
    clock,last_shot,next_id,unavailable_logged,multiplayer_logged,in_mission=0,-math.huge,0,nil,false,false
    cache=fresh_cache()
    off_mission_at=-math.huge
    if watch then watch.status='cancelled'end
    watch=nil
end
return M
