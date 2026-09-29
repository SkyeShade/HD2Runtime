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
local function copy_position(p)return p and{x=p.x,y=p.y,z=p.z}or nil end

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
local function player_payload(item,entry)
    local player=handles.player(item)
    local avatar=entry.avatar and handles.entity({id=entry.avatar,type=entry.type,descriptor_pointer=entry.descriptor})
    return {player=player,local_player=item['local'],avatar=avatar,position=copy_position(entry.position),
        peer=item.peer}
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
            entry.unit=state and state.descriptor.unit
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
                events.queue('player_died',player_payload(item,entry))
            elseif state and want_positions and entry.unit then
                entry.position=world_module.unit_position(world,entry.unit)or entry.position
            elseif not state and item.lifecycle~=3 then
                entry.dead=true
                events.queue('player_died',player_payload(item,entry))
            end
        elseif not avatar and entry.avatar and not entry.dead then
            -- The avatar is gone before its dead state was seen.
            entry.dead=true
            events.queue('player_died',player_payload(item,entry))
        end
    end
    for peer in pairs(source.known)do if not seen[peer]then source.known[peer]=nil end end
    source.first=false
end
M.players=events.register_source(players)

------------------------------------------------------------------------------------------------------- health --
-- One bulk scan of the health manager per tick: header, hash buckets, records, ext records, descriptor pointers.
local health={name='health',events={'entity_spawned','entity_died','entity_killed','entity_damaged',
    'player_damaged','player_healed'},depends={'game_state'}}
function health.start(source)
    local ok,why=open(source)
    if not ok then return nil,why end
    local view=source.world.view
    source.header_block,source.bucket_block=view.slot(),view.slot()
    source.record_block,source.ext_block,source.pointer_block=view.slot(),view.slot(),view.slot()
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
local function entity_payload(entry)
    local handle=handles.entity({id=entry.entity,type=entry.type,descriptor_pointer=entry.descriptor})
    return {entity=handle,type=entry.type,name=handle.name,enemy=handle.enemy,faction=handle.faction,
        avatar=handle.avatar}
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
                        entry={entity=entity,descriptor=descriptor,type=string.format('%08X%08X',b.u32(d,4),b.u32(d,0)),
                            unit=b.u32(d,H.descriptor.unit),owned=b.u32(d,H.descriptor.flags)%2==1,life=life,health=amount}
                        local info=world_module.type_info(entry.type)
                        entry.avatar=info and info.avatar or false
                        known[entity]=entry
                        if want_spawn and not first and life<2 then events.queue('entity_spawned',entity_payload(entry))end
                    end
                end
                if entry then
                    entry.stamp=stamp
                    if life>=2 and entry.life<2 then
                        if want_death then
                            local payload=entity_payload(entry)
                            local lo,hi=records:u32(base+R.lastCreditor),records:u32(base+R.lastCreditor+4)
                            if lo==0 and hi==0 then lo,hi=records:u32(base+R.downCreditor),records:u32(base+R.downCreditor+4)end
                            local killer,local_killer,peer=killer_of(source,lo,hi)
                            payload.killer=killer;payload.local_killer=local_killer==true;payload.killer_peer=peer
                            payload.position=entry.unit and world_module.unit_position(world,entry.unit)or nil
                            payload.max_health=ext and ext:i32(index*H.extStride+H.extFields.maxHealth)or nil
                            events.queue('entity_died',payload)
                            if peer then
                                local killed={}
                                for k,v in pairs(payload)do killed[k]=v end
                                events.queue('entity_killed',killed)
                            end
                        end
                    elseif life<2 and amount<entry.health and want_damage then
                        local payload=entity_payload(entry)
                        payload.damage=entry.health-amount;payload.health=amount
                        payload.max_health=ext and ext:i32(index*H.extStride+H.extFields.maxHealth)or nil
                        local lo,hi=records:u32(base+R.lastCreditor),records:u32(base+R.lastCreditor+4)
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
    for entity,entry in pairs(known)do if entry.stamp~=stamp then known[entity]=nil end end
    source.first=false
    metrics.count('events.health_scans')
end
M.health=events.register_source(health)

-------------------------------------------------------------------------------------------------------- stats --
-- player_fired: the local player's projectiles_fired mission stat (main table plus source blocks, as the game's own
-- get_stat sums it) grew. Checked 10 times per second: one event per check that saw new shots, with the count.
local stats={name='stats',events={'player_fired'},depends={'game_state'},interval=0.1}
function stats.start(source)
    local ok,why=open(source)
    if not ok then return nil,why end
    source.block=source.world.view.slot();source.next=0;source.total=nil;source.entity=nil
    return true
end
function stats.stop(source)source.world=nil end
function stats.poll(source)
    local now=events.state.now
    if now<source.next then return end
    source.next=now+stats.interval
    local world=source.world
    local player
    for _,item in ipairs(world_module.players(world,false))do if item['local']then player=item end end
    if not player or not player.entity then source.total=nil;return end
    local total=world_module.stat_total(world,player.entity,natives.stats.keys.projectiles_fired,source.block)
    if not total then return end
    if source.entity~=player.entity or not source.total or total<source.total then
        source.entity,source.total=player.entity,total   -- (re)baseline: new player entity or a reset table
        return
    end
    if total>source.total then
        events.queue('player_fired',{player=handles.player(player),local_player=true,shots=total-source.total,
            total=total})
        source.total=total
    end
end
M.stats=events.register_source(stats)

function M.reset_for_tests()
    for _,source in ipairs({M.game_state,M.players,M.health,M.stats})do source.world=nil;source.known=nil end
end
return M
