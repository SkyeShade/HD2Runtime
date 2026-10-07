-- Native event sources (docs/events.md#sources). Each is polled once per update tick while one of its events has a
-- subscriber (game_state also while another source or a mod context needs mission boundaries). A source that cannot
-- open the proven world (runtime/event_world.lua) is unavailable and says why once.
local events=require('hd2runtime/runtime/events')
local world_module=require('hd2runtime/runtime/event_world')
local handles=require('hd2runtime/runtime/handles')
local natives=require('hd2runtime/domains/event_natives')
local metrics=require('hd2runtime/runtime/metrics')
local b=require('hd2runtime/core/bytes')
local M={}
local H=natives.health
local R=H.record

local function open(source)
    local world,why=world_module.open()
    if not world then return nil,why end
    source.world=world
    return true
end
local position=handles.position   -- read-only position snapshots (runtime/handles.lua)

--------------------------------------------------------------------------------------------------- game state --
-- mission_started when the game enters its Mission state with a game_mode object; mission_ended when it leaves.
local game_state={name='game_state',events={'mission_started','mission_ended'}}
function game_state.start(source)
    local ok,why=open(source)
    if not ok then return nil,why end
    source.current=nil;source.started_at=nil
    return true
end
function game_state.stop(source)source.world=nil end
function game_state.poll(source)
    local state=world_module.game_state(source.world)
    if not state then return end
    local previous=source.current
    source.current=state
    events.state.game_state=state
    local was=previous and previous.mission or false
    if state.mission and not was then
        local epoch=events.begin_mission()
        source.started_at=events.state.now
        events.queue('mission_started',{mission=epoch,host=state.host,mode=state.mode,game_state=state.name,
            first_observation=previous==nil})
    elseif was and not state.mission then
        local _,epoch=events.mission()
        events.queue('mission_ended',{mission=epoch,duration=events.state.now-(source.started_at or events.state.now),
            game_state=state.name})
        -- Cleanup runs after mission_ended is dispatched (end of this tick's flush).
        events.after_flush(function()events.end_mission()end)
    end
end
M.game_state=events.register_source(game_state)

------------------------------------------------------------------------------------------------------ players --
-- player_spawned: a player's avatar entity appears (or changes) while the player is spawned.
-- player_died: that avatar's health record reaches the dead state, or the avatar disappears while the player
-- leaves the spawned lifecycle. The death position is the avatar's last position read while it was alive.
local players={name='players',events={'player_spawned','player_died'},depends={'game_state'}}
function players.start(source)
    local ok,why=open(source)
    if not ok then return nil,why end
    source.known={};source.first=true
    return true
end
function players.stop(source)source.world=nil;source.known=nil end
local function player_payload(item,entry,observed)
    local player=handles.player(item)
    local avatar=entry.avatar and handles.entity({id=entry.avatar,type=entry.type,descriptor_pointer=entry.descriptor,
        unit=entry.unit,network_id=entry.network_id})
    return {player=player,local_player=item['local'],avatar=avatar,avatar_id=entry.avatar,
        avatar_semantic_id=avatar and avatar.semantic_id or nil,position=position(entry.position),peer=item.peer,
        observed=observed}
end
function players.poll(source)
    local world=source.world
    local list=world_module.players(world,true)
    local want_positions=events.wanted('player_died')or events.wanted('player_spawned')
    local seen={}
    for _,item in ipairs(list)do
        seen[item.peer]=true
        local entry=source.known[item.peer]
        if not entry then entry={};source.known[item.peer]=entry end
        local avatar=item.avatar
        if avatar and avatar~=entry.avatar then
            -- A new avatar: remember its identity, report the spawn (not for the population seen on the first poll).
            local state=world_module.entity_state(world,avatar)
            entry.avatar=avatar;entry.dead=false
            entry.type=state and state.descriptor.type;entry.descriptor=state and state.descriptor.pointer
            entry.unit=state and state.descriptor.unit;entry.network_id=item.avatar_network_id
            entry.position=entry.unit and want_positions and world_module.unit_position(world,entry.unit)or nil
            if state and state.life<2 and not source.first then
                events.queue('player_spawned',player_payload(item,entry))
            elseif state and state.life>=2 then entry.dead=true end
        elseif avatar and not entry.dead then
            local state=world_module.entity_state(world,avatar)
            if state and state.life>=2 then
                entry.dead=true
                -- Read the position now if the unit still exists; otherwise the last position read alive.
                local now=entry.unit and world_module.unit_position(world,entry.unit)
                if now then entry.position=now end
                events.queue('player_died',player_payload(item,entry,'dead_state'))
            elseif state and want_positions and entry.unit then
                entry.position=world_module.unit_position(world,entry.unit)or entry.position
            elseif not state and item.lifecycle~=3 then
                entry.dead=true
                events.queue('player_died',player_payload(item,entry,'avatar_removed'))
            end
        elseif not avatar and entry.avatar and not entry.dead then
            -- The avatar is gone before its dead state was seen.
            entry.dead=true
            events.queue('player_died',player_payload(item,entry,'avatar_removed'))
        end
    end
    for peer in pairs(source.known)do if not seen[peer]then source.known[peer]=nil end end
    source.first=false
end
M.players=events.register_source(players)

------------------------------------------------------------------------------------------------------- health --
-- One bulk scan of the health manager per tick: header, hash buckets, records, ext records, descriptor pointers.
-- A death is seen either as the record reaching the dead state, or (the game may replace a dead entity by its corpse
-- between two polls) as the record disappearing while a corpse that took over the entity's unit names the entity as
-- its origin. A record that disappears without such a corpse (despawned, or destroyed outright) is not a death.
local health={name='health',events={'entity_spawned','entity_died','entity_killed','entity_damaged',
    'player_damaged','player_healed'},depends={'game_state'}}
function health.start(source)
    local ok,why=open(source)
    if not ok then return nil,why end
    local view=source.world.view
    source.header_block,source.bucket_block=view.slot(),view.slot()
    source.record_block,source.ext_block,source.pointer_block=view.slot(),view.slot(),view.slot()
    source.corpse_block=view.slot()
    source.known={};source.stamp=0;source.first=true
    return true
end
function health.stop(source)source.world=nil;source.known=nil end

local function killer_of(source,lo,hi)
    if lo==0 and hi==0 then return nil end
    local peer=world_module.peer_hex(lo,hi)
    local list=source.players_cache
    if not list or source.players_stamp~=source.stamp then
        list=world_module.players(source.world,false)
        source.players_cache,source.players_stamp=list,source.stamp
    end
    for _,item in ipairs(list)do if item.peer==peer then return handles.player(item),item['local'],peer end end
    return nil,false,peer   -- credited to a peer no longer in the player list
end
-- Every health event carries the entity handle and its identity snapshot as plain fields, so a callback (or a timer
-- it starts) never needs the live entity to know what it was.
local function entity_payload(entry)
    -- One handle per tracked entity (its fields are a snapshot of the same identity), made on its first event.
    local handle=entry.handle
    if not handle or handle.epoch~=events.state.epoch then
        handle=handles.entity({id=entry.entity,type=entry.type,descriptor_pointer=entry.descriptor,unit=entry.unit,
            network_id=entry.network_id})
        entry.handle=handle
    end
    return {entity=handle,entity_id=entry.entity,type=entry.type,semantic_id=handle.semantic_id,name=handle.name,
        display_name=handle.display_name,enemy=handle.enemy,faction=handle.faction,kind=handle.kind,
        avatar=handle.avatar,unit_id=entry.unit,network_id=entry.network_id}
end
-- entity_died (and entity_killed when a player is credited) for one death.
local function queue_death(source,entry,lo,hi,position,max_health,observed,corpse)
    local payload=entity_payload(entry)
    local killer,local_killer,peer=killer_of(source,lo,hi)
    payload.killer=killer;payload.local_killer=local_killer==true;payload.killer_peer=peer
    payload.position=position and handles.position(position)or nil;payload.max_health=max_health
    payload.observed=observed;payload.corpse_id=corpse
    events.queue('entity_died',payload)
    if peer then
        local killed={}
        for k,v in pairs(payload)do killed[k]=v end
        events.queue('entity_killed',killed)
    end
end
local function owning_player(source,entity)
    local list=world_module.players(source.world,true)
    for _,item in ipairs(list)do if item.avatar==entity then return handles.player(item),item['local']end end
    return nil,false
end

function health.poll(source)
    local world=source.world
    local header=world_module.health_header(world,source.header_block)
    if not header or not header.buckets or not header.records or not header.descriptors then return end
    local live=header.live
    source.stamp=source.stamp+1
    local stamp=source.stamp
    local view=world.view
    local buckets=view.fill(source.bucket_block,header.buckets,header.hash_capacity*8)
    if not buckets then return end
    local records=live>0 and view.fill(source.record_block,header.records,live*H.stride)
    local ext=live>0 and header.ext and view.fill(source.ext_block,header.ext,live*H.extStride)
    local pointers=live>0 and view.fill(source.pointer_block,header.descriptors,live*8)
    if live>0 and(not records or not pointers)then return end
    local want_spawn,want_death=events.wanted('entity_spawned'),events.wanted('entity_died')or events.wanted('entity_killed')
    local want_damage=events.wanted('entity_damaged')or events.wanted('player_damaged')
    local want_heal=events.wanted('player_healed')
    local known,empty,first=source.known,header.hash_empty,source.first
    for slot=0,header.hash_capacity-1 do
        local entity=buckets:u32(slot*8)
        if entity~=empty then
            local index=buckets:u32(slot*8+4)
            if index<live then
                local base=index*H.stride
                local descriptor=pointers:ptr(index*8)
                local life=records:u32(base+R.life)
                local amount=records:i32(base+R.health)
                local entry=known[entity]
                if entry and entry.descriptor~=descriptor then entry=nil end   -- the id now names another object
                if not entry then
                    local d=descriptor and view.read(descriptor,H.descriptor.size)
                    if d and b.u32(d,H.descriptor.entity)==entity then
                        local network=b.u32(d,H.descriptor.goid)
                        entry={entity=entity,descriptor=descriptor,type=string.format('%08X%08X',b.u32(d,4),b.u32(d,0)),
                            unit=b.u32(d,H.descriptor.unit),owned=b.u32(d,H.descriptor.flags)%2==1,life=life,health=amount,
                            network_id=network~=0x7FFF and network or nil}
                        local info=world_module.type_info(entry.type)
                        entry.avatar=info and info.avatar or false
                        entry.max_health=ext and ext:i32(index*H.extStride+H.extFields.maxHealth)or nil
                        known[entity]=entry
                        if want_spawn and not first and life<2 then events.queue('entity_spawned',entity_payload(entry))end
                    end
                end
                if entry then
                    entry.stamp=stamp
                    -- An unchanged entity costs this one comparison per tick.
                    if amount~=entry.health or life~=entry.life then
                        local lo,hi=records:u32(base+R.lastCreditor),records:u32(base+R.lastCreditor+4)
                        if want_death then
                            -- Kept for a death only seen through the corpse (the record is gone by then). The
                            -- creditor and maximum change only with a hit, so they are refreshed only here.
                            local clo,chi=lo,hi
                            if clo==0 and chi==0 then
                                clo,chi=records:u32(base+R.downCreditor),records:u32(base+R.downCreditor+4)
                            end
                            entry.credit_lo,entry.credit_hi=clo,chi
                            entry.max_health=ext and ext:i32(index*H.extStride+H.extFields.maxHealth)or entry.max_health
                        end
                        if life>=2 and entry.life<2 then
                            if want_death then
                                queue_death(source,entry,entry.credit_lo,entry.credit_hi,
                                    entry.unit and world_module.unit_position(world,entry.unit)or nil,entry.max_health,
                                    'dead_state',nil)
                            end
                        elseif life<2 and amount<entry.health and want_damage then
                            local payload=entity_payload(entry)
                            payload.damage=entry.health-amount;payload.health=amount
                            payload.max_health=ext and ext:i32(index*H.extStride+H.extFields.maxHealth)or nil
                            local attacker,local_attacker,peer=killer_of(source,lo,hi)
                            payload.attacker=attacker;payload.local_attacker=local_attacker==true;payload.attacker_peer=peer
                            payload.downed=life==1
                            events.queue('entity_damaged',payload)
                            if entry.avatar then
                                local player,is_local=owning_player(source,entity)
                                local copy={}
                                for k,v in pairs(payload)do copy[k]=v end
                                copy.player=player;copy.local_player=is_local
                                events.queue('player_damaged',copy)
                            end
                        elseif life<2 and amount>entry.health and entry.avatar and want_heal then
                            local player,is_local=owning_player(source,entity)
                            local payload=entity_payload(entry)
                            payload.player=player;payload.local_player=is_local
                            payload.amount=amount-entry.health;payload.health=amount
                            payload.max_health=ext and ext:i32(index*H.extStride+H.extFields.maxHealth)or nil
                            payload.cause=handles.claim_heal(entity)
                            events.queue('player_healed',payload)
                        end
                        entry.life,entry.health=life,amount
                    end
                end
            end
        end
    end
    local corpses
    for entity,entry in pairs(known)do
        if entry.stamp~=stamp then
            known[entity]=nil
            if want_death and entry.life<2 and not first then
                if corpses==nil then corpses=world_module.corpses(world,source.corpse_block)or false end
                local index=corpses and corpses.origins[entity]
                local corpse=index and entry.unit and world_module.corpse_entity(world,corpses,index,entry.unit)
                if corpse then
                    -- The corpse owns the unit now: its position is where the entity died.
                    queue_death(source,entry,entry.credit_lo or 0,entry.credit_hi or 0,
                        world_module.unit_position(world,entry.unit),entry.max_health,'corpse',corpse)
                end
            end
        end
    end
    source.first=false
    metrics.count('events.health_scans')
end
M.health=events.register_source(health)

-------------------------------------------------------------------------------------------------------- stats --
-- The local player's mission stats as the game keeps them (main table plus one block per source type; the game's own
-- get_stat sums both). Checked 10 times per second: one event per check that saw growth, with the count.
-- player_fired: projectiles_fired grew. player_kill_credited: dealt_kills grew (the game credited kills).
-- player_hit: projectiles_hit grew (the projectile system adds it once per projectile that hits).
-- player_damage_dealt: dealt_damage grew by the damage the game recorded (the damage-stats path, 0x12A0F50).
-- Each carries `sources`: the growth per source type (the weapon, throwable or stratagem payload the game recorded
-- the stat under), and `unattributed`: growth of the main table, which has no source.
local stats={name='stats',events={'player_fired','player_kill_credited','player_hit','player_damage_dealt'},
    depends={'game_state'},interval=0.1}
local STAT_EVENTS={{'projectiles_fired','player_fired','shots'},{'dealt_kills','player_kill_credited','kills'},
    {'projectiles_hit','player_hit','hits'},{'dealt_damage','player_damage_dealt','damage'}}
function stats.start(source)
    local ok,why=open(source)
    if not ok then return nil,why end
    source.block=source.world.view.slot();source.next=0;source.last=nil;source.entity=nil
    return true
end
function stats.stop(source)source.world=nil end
local function growth(now,last,key,field)
    local list={}
    for type_hex,values in pairs(now.sources)do
        local before=last.sources[type_hex]and last.sources[type_hex][key]or 0
        local added=(values[key]or 0)-before
        if added>0 then list[#list+1]={type=type_hex,name=world_module.source_name(type_hex),[field]=added}end
    end
    table.sort(list,function(a,c)return a[field]>c[field]or(a[field]==c[field]and a.type<c.type)end)
    return list,math.max(0,now.main[key]-last.main[key])
end
function stats.poll(source)
    local now=events.state.now
    if now<source.next then return end
    source.next=now+stats.interval
    local world=source.world
    local player
    for _,item in ipairs(world_module.players(world,false))do if item['local']then player=item end end
    if not player or not player.entity then source.last=nil;return end
    local K=natives.stats.keys
    -- Only the stats someone subscribed to are read: all four share the same bulk read of the source blocks.
    local wanted={}
    for _,item in ipairs(STAT_EVENTS)do
        if events.wanted(item[2])then wanted[#wanted+1]=K[item[1]]end
    end
    if #wanted==0 then source.last=nil;return end
    local current=world_module.stat_breakdown(world,player.entity,wanted,source.block)
    if not current then return end
    local last=source.last
    local reset=source.entity~=player.entity or not last
    if not reset then
        for _,key in ipairs(wanted)do
            if last.totals[key]==nil or current.totals[key]<last.totals[key]then reset=true end
        end
    end
    if reset then
        source.entity,source.last=player.entity,current   -- (re)baseline: new player entity, new stats or a reset table
        return
    end
    source.last=current
    for _,item in ipairs(STAT_EVENTS)do
        local key=K[item[1]]
        local added=current.totals[key]and current.totals[key]-last.totals[key]or 0
        if added>0 then
            local list,unattributed=growth(current,last,key,item[3])
            events.queue(item[2],{player=handles.player(player),local_player=true,[item[3]]=added,
                total=current.totals[key],sources=list,unattributed=unattributed})
        end
    end
end
M.stats=events.register_source(stats)

------------------------------------------------------------------------------------------------------ weapons --
-- weapon_equipped / weapon_unequipped / weapon_changed: what the local player's avatar holds (its wielder slot 0,
-- research/event-wielder-F5FEE03DCFDB.json), checked 10 times per second. The game's weapon switch writes the
-- selection and slot 0 in one call, so a check never sees a half-switched state. A new avatar (respawn) holds
-- nothing until the game wields its first item; death removes the wielder (weapon_unequipped). What is held when
-- Runtime starts watching is the baseline (no event).
local weapons={name='weapons',events={'weapon_equipped','weapon_unequipped','weapon_changed'},depends={'game_state'},
    interval=0.1}
function weapons.start(source)
    local ok,why=open(source)
    if not ok then return nil,why end
    source.next=0;source.current=nil;source.key=nil;source.first=true
    return true
end
function weapons.stop(source)source.world=nil end
local function held_snapshot(held,avatar)
    if not(held and held.entity)then return nil end
    return {name=world_module.source_name(held.type),type=held.type,entity_id=held.entity,slot=held.slot,
        slot_proven=held.slot_proven,selection=held.selection,avatar_id=avatar}
end
function weapons.poll(source)
    local now=events.state.now
    if now<source.next then return end
    source.next=now+weapons.interval
    local world=source.world
    local player
    for _,item in ipairs(world_module.players(world,true))do if item['local']then player=item end end
    local avatar=player and player.avatar
    local current
    if avatar then
        local held=world_module.equipped(world,avatar)
        if not held then return end   -- unreadable this tick: keep the last stable state
        current=held_snapshot(held,avatar)
    end
    local previous,previous_key=source.current,source.key
    local key=current and(current.avatar_id..':'..current.entity_id..':'..current.type)or''
    source.current,source.key=current,key
    if source.first then source.first=false;return end
    if key==previous_key or not player then return end
    local handle=handles.player(player)
    if previous then
        local why=not current and(avatar==previous.avatar_id and'emptied'or'avatar_changed')or'switched'
        events.queue('weapon_unequipped',{player=handle,local_player=true,weapon=previous,reason=why})
    end
    if current then events.queue('weapon_equipped',{player=handle,local_player=true,weapon=current})end
    events.queue('weapon_changed',{player=handle,local_player=true,previous=previous,current=current})
end
M.weapons=events.register_source(weapons)

--------------------------------------------------------------------------------------------------- explosions --
-- explosion: a request in this machine's explosion queue (research/event-explosions-F5FEE03DCFDB.json). The world
-- update kicks min(count, 8) requests and later gathers exactly those, in order, moving the rest to the front: first
-- in, first out, and a request leaves the queue only when a gather processes it. A request made after the frame's
-- kick (projectile impacts, explosives, a blast's chained explosions) is still queued at the next poll, so one read of
-- the queue per tick sees it. Each poll reports the entries the previous poll did not hold: the previous entries still
-- queued are a prefix of this poll's (the longest suffix of the previous window equal, byte for byte, to a prefix of
-- this one), whatever number of game updates ran in between.
-- Runtime's own requests (event_world.explode) are made in the Lua update, after the poll, and the next frame's kick
-- takes them first: they are reported from the request (observed = 'request', the requester's cause) at the next
-- poll, and a queued entry equal to one of them is not reported again. An idle tick costs two reads.
local explosions={name='explosions',events={'explosion'},depends={'game_state'}}
explosions.WINDOW=64         -- entries read per poll at most (later ones are reported once the queue moves them up)
explosions.REQUEST_SECONDS=2 -- a Runtime request is matched to a queued entry this long
local explosion_names=require('hd2runtime/runtime/explosion_names')
local STRIDE=natives.explosion.stride
-- The cause of a Runtime request reported from the request: the requester's own (spec.cause), else the mod whose
-- callback, timer or startup scope is running (its reaction to the current event), else Runtime itself.
local function request_cause(spec)
    if type(spec.cause)=='table'then return spec.cause end
    local state=events.state
    local owner=state.current and state.current.owner
    if not owner or owner=='unknown'then owner=state.scopes[#state.scopes]end
    if not owner or owner=='unknown'then return {source='runtime',kind='explosion'}end
    local event=state.current_event
    local parent=event and event.cause
    return {source='mod',mod=owner,kind='explosion',depth=((parent and parent.depth)or 0)+1,
        parent=event and{event=event.event,cause=parent}or nil}
end
function explosions.start(source)
    local ok,why=open(source)
    if not ok then return nil,why end
    source.window={};source.requests={};source.types={};source.epoch=events.state.epoch
    world_module.observe_explosion_requests('explosion_event',function(spec)
        local list=source.requests
        if list and#list<64 then
            list[#list+1]={type=spec.type,x=spec.x,y=spec.y,z=spec.z,source=spec.source,owner=spec.owner,
                peer_lo=spec.peer_lo or 0,peer_hi=spec.peer_hi or 0,cause=request_cause(spec),time=events.state.now}
        end
    end)
    return true
end
function explosions.stop(source)
    world_module.observe_explosion_requests('explosion_event',nil)
    source.world=nil;source.window=nil;source.requests=nil;source.types=nil
end
-- An entity's type through the game's entity map, remembered per mission (an id names one entity: a destroyed
-- entity's id comes back with another generation). nil when it does not resolve (an explosive is often gone already).
local function type_of(source,id)
    if id==0 then return nil end
    if source.epoch~=events.state.epoch then source.types={};source.epoch=events.state.epoch end
    local known=source.types[id]
    if known==nil then
        known=world_module.entity_type(source.world,id)or false
        if known then source.types[id]=known end
    end
    return known or nil
end
local function explosion_payload(source,entry,observed,cause)
    local source_type,owner_type=type_of(source,entry.source),type_of(source,entry.owner)
    local payload={name=explosion_names.name(entry.type),position=position(entry),observed=observed,cause=cause,
        source_id=entry.source~=0 and entry.source or nil,source_type=source_type,
        source_name=source_type and world_module.source_name(source_type)or nil,
        owner_id=entry.owner~=0 and entry.owner or nil,owner_type=owner_type,
        owner_name=owner_type and world_module.source_name(owner_type)or nil,local_player=false}
    if entry.peer_lo~=0 or entry.peer_hi~=0 then
        payload.creditor_peer=world_module.peer_hex(entry.peer_lo,entry.peer_hi)
        for _,item in ipairs(world_module.players(source.world,false))do
            if item.peer==payload.creditor_peer then
                payload.player=handles.player(item);payload.local_player=item['local']==true
            end
        end
    end
    return payload
end
-- A queued entry equal to a reported Runtime request (the same type, entities, creditor and position; the queue keeps
-- the position as f32): claimed once.
local function near(a,b)return math.abs(a-b)<=1e-3+math.abs(a)*1e-6 end
local function claim_request(source,entry)
    for index,r in ipairs(source.requests)do
        if r.reported and r.type==entry.type and r.source==entry.source and r.owner==entry.owner
            and r.peer_lo==entry.peer_lo and r.peer_hi==entry.peer_hi and near(r.x,entry.x) and near(r.y,entry.y)
            and near(r.z,entry.z)then
            table.remove(source.requests,index)
            return true
        end
    end
    return false
end
function explosions.poll(source)
    local world=source.world
    local now=events.state.now
    -- Runtime's own requests since the last poll, in request order; kept a while to recognise them queued.
    local requests=source.requests
    for index=#requests,1,-1 do
        if now-requests[index].time>explosions.REQUEST_SECONDS then table.remove(requests,index)end
    end
    for _,r in ipairs(requests)do
        if not r.reported then
            r.reported=true
            events.queue('explosion',explosion_payload(source,r,'request',r.cause))
        end
    end
    local pending=world_module.explosion_pending(world,explosions.WINDOW)
    if not pending then return end
    local previous,current=source.window,{}
    for index=0,pending.n-1 do current[index+1]=pending.raw:sub(index*STRIDE+1,(index+1)*STRIDE)end
    source.window=current
    -- The previous entries still queued: the longest suffix of the previous window that is a prefix of this one.
    local carried=0
    for shift=0,#previous-1 do
        local length=#previous-shift
        if length<=#current then
            local same=true
            for i=1,length do if previous[shift+i]~=current[i]then same=false;break end end
            if same then carried=length;break end
        end
    end
    if carried==#current then return end
    metrics.count('events.explosions_observed',#current-carried)
    for index=carried,#current-1 do
        local entry=world_module.explosion_entry(pending.raw,index)
        if not claim_request(source,entry)then events.queue('explosion',explosion_payload(source,entry,'queue'))end
    end
end
M.explosions=events.register_source(explosions)

function M.reset_for_tests()
    for _,source in ipairs({M.game_state,M.players,M.health,M.stats,M.weapons,M.explosions})do
        source.world=nil;source.known=nil
    end
    world_module.observe_explosion_requests('explosion_event',nil)
end
return M
