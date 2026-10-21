-- The event sources on HellForge (runtime/hellforge.lua, docs/hellforge.md): HellForge's event hooks say when, the
-- Runtime builds the same payloads as its own sources (runtime/event_sources.lua) from the same reads. Events HellForge
-- has no hook for yet are unavailable there (their source says so once, when a mod subscribes):
--   from HellForge   mission_started, mission_ended (its game state); player_spawned, player_died (its player
--                    lifecycle); entity_spawned (its spawner), entity_died, entity_killed (its kill dispatch),
--                    entity_damaged, player_damaged (its damage consumer); player_healed (its heal event);
--                    player_fired, player_kill_credited, player_hit, player_damage_dealt (its stat event);
--                    weapon_equipped, weapon_unequipped, weapon_changed (its weapon event); explosion (its explosion
--                    request hook: every request, the Runtime's own included); bughole_destroyed (its bug hole event)
-- key_down and key_up stay the Runtime's own (the keyboard, not the game).
--
-- Differences from the Runtime's own sources: entity_damaged's damage is the hit as the game queues it, before armour
-- and multipliers (the Runtime's own measured the health lost), with health read after; HellForge's hooks see this
-- machine's own simulation, as the Runtime's own sources did.
local events=require('hd2runtime/runtime/events')
local world_module=require('hd2runtime/runtime/event_world')
local handles=require('hd2runtime/runtime/handles')
local hellforge=require('hd2runtime/runtime/hellforge')
local b=require('hd2runtime/core/bytes')
local log=require('hd2runtime/runtime/log')
local M={}
local ON=hellforge.ON
M.UNAVAILABLE={}

-- HellForge's queued events, sorted by kind once per update: inbox[kind] = {data, ...} (raw HfEvent structs).
local inbox,drained,said={},nil,{}
local function backend()return hellforge.backend()end
local function listen(kinds)
    local mod=hellforge.mod('hd2runtime')
    for _,kind in ipairs(kinds)do
        if not inbox[kind]then
            if not mod or not backend().listen(mod,kind)then
                return nil,'HellForge does not deliver event kind '..kind..': '..(mod and backend().last(mod)or'no Lua mod')
            end
            inbox[kind]={}
        end
    end
    return true
end
local function drain()
    local frame=events.state.frame
    if drained==frame then return end
    drained=frame
    local list,lost=backend().poll()
    for _,data in ipairs(list)do
        local q=inbox[b.u32(data,4)]
        if q then q[#q+1]=data end
    end
    if lost>0 then log.emit('[HD2Runtime] HellForge dropped '..lost..' events (its queue was full)')end
end
local function take(kind)
    local q=inbox[kind]or{}
    if #q>0 then inbox[kind]={}end
    return q
end
local function open(source,kinds)
    local world,why=world_module.open()
    if not world then return nil,why end
    local ok,reason=listen(kinds)
    if not ok then return nil,reason end
    source.world=world
    return true
end
local function i32(data,at)local v=b.u32(data,at);return v>=2147483648 and v-4294967296 or v end
local function hex64(data,at)return string.format('%08X%08X',b.u32(data,at+4),b.u32(data,at))end
local function zero64(data,at)return b.u32(data,at)==0 and b.u32(data,at+4)==0 end
local function peer(data,at)
    local lo,hi=b.u32(data,at),b.u32(data,at+4)
    return world_module.peer_hex(lo,hi),lo,hi
end

------------------------------------------------------------------------------------------------- game state --
local function game_state_source(source)
    function source.start(s)
        local ok,why=open(s,{ON.state,ON.mission_start,ON.mission_end})
        if not ok then return nil,why end
        s.current=nil;s.started_at=nil;s.first=true
        return true
    end
    function source.stop(s)s.world=nil end
    function source.poll(s)
        drain()
        local changed=#take(ON.state)>0
        local starts,ends=take(ON.mission_start),take(ON.mission_end)
        if not(changed or s.first or #starts>0 or #ends>0)then return end
        local state=world_module.game_state(s.world)
        if state then events.state.game_state=state;s.current=state end
        local in_mission=events.mission()
        if (#starts>0 or(s.first and state and state.mission))and not in_mission then
            local epoch=events.begin_mission()
            s.started_at=events.state.now
            events.queue('mission_started',{mission=epoch,host=state and state.host,mode=state and state.mode,
                game_state=state and state.name,first_observation=s.first and #starts==0})
        elseif #ends>0 and in_mission then
            local _,epoch=events.mission()
            events.queue('mission_ended',{mission=epoch,duration=events.state.now-(s.started_at or events.state.now),
                game_state=state and state.name})
            events.after_flush(function()events.end_mission()end)
        end
        s.first=false
    end
end

---------------------------------------------------------------------------------------------------- players --
local function snapshot(world,entity)
    local state=entity and world_module.entity_state(world,entity)
    if not state then return nil end
    local d=state.descriptor
    return {entity=entity,type=d.type,descriptor=d.pointer,unit=d.unit,network_id=d.goid~=0x7FFF and d.goid or nil,
        life=state.life,health=state.health,max_health=state.max_health}
end
local function player_payload(world,item,entry,observed)
    local avatar=entry.entity and handles.entity({id=entry.entity,type=entry.type,descriptor_pointer=entry.descriptor,
        unit=entry.unit,network_id=entry.network_id})
    local at=entry.unit and world_module.unit_position(world,entry.unit)
    if at then entry.position=at end
    return {player=handles.player(item),local_player=item['local'],avatar=avatar,avatar_id=entry.entity,
        avatar_semantic_id=avatar and avatar.semantic_id or nil,position=handles.position(entry.position),peer=item.peer,
        observed=observed}
end
local function player_item(world,hex)
    for _,item in ipairs(world_module.players(world,true))do if item.peer==hex then return item end end
end
local function players_source(source)
    function source.start(s)
        local ok,why=open(s,{ON.player_spawn,ON.player_down})
        if not ok then return nil,why end
        s.known={}
        return true
    end
    function source.stop(s)s.world=nil;s.known=nil end
    function source.poll(s)
        drain()
        for _,data in ipairs(take(ON.player_spawn))do
            local hex=peer(data,16)
            local item=player_item(s.world,hex)
            local entry=item and snapshot(s.world,item.avatar or b.u32(data,24))
            if entry then
                s.known[hex]=entry
                events.queue('player_spawned',player_payload(s.world,item,entry))
            end
        end
        for _,data in ipairs(take(ON.player_down))do
            local hex=peer(data,16)
            local item=player_item(s.world,hex)
            local entry=s.known[hex]or(item and snapshot(s.world,item.avatar or b.u32(data,24)))
            if item and entry then
                s.known[hex]=nil
                events.queue('player_died',player_payload(s.world,item,entry,'dead_state'))
            end
        end
    end
end

----------------------------------------------------------------------------------------------------- health --
local function entity_payload(entry)
    local handle=handles.entity({id=entry.entity,type=entry.type,descriptor_pointer=entry.descriptor,unit=entry.unit,
        network_id=entry.network_id})
    return {entity=handle,entity_id=entry.entity,type=entry.type,semantic_id=handle.semantic_id,name=handle.name,
        display_name=handle.display_name,enemy=handle.enemy,faction=handle.faction,kind=handle.kind,
        avatar=handle.avatar,unit_id=entry.unit,network_id=entry.network_id}
end
local function credited(world,data,at)
    local hex,lo,hi=peer(data,at)
    if lo==0 and hi==0 then return nil,false,nil end
    local item=player_item(world,hex)
    if item then return handles.player(item),item['local'],hex end
    return nil,false,hex
end
local function owning_player(world,entity)
    for _,item in ipairs(world_module.players(world,true))do if item.avatar==entity then return handles.player(item),item['local']end end
    return nil,false
end
local function health_source(source)
    function source.start(s)
        local ok,why=open(s,{ON.spawn,ON.kill,ON.damage,ON.heal})
        if not ok then return nil,why end
        s.known={}
        return true
    end
    function source.stop(s)s.world=nil;s.known=nil end
    function source.poll(s)
        drain()
        local world=s.world
        for _,data in ipairs(take(ON.heal))do
            local entity=b.u32(data,16)
            local entry=snapshot(world,entity)or s.known[entity]
            if entry then
                local payload=entity_payload(entry)
                local player,is_local=owning_player(world,entity)
                local max=i32(data,28)
                payload.player=player;payload.local_player=is_local==true
                payload.amount=i32(data,20);payload.health=i32(data,24);payload.max_health=max>0 and max or entry.max_health
                events.queue('player_healed',payload)
            end
        end
        for _,data in ipairs(take(ON.spawn))do
            local entity=b.u32(data,16)
            local entry=snapshot(world,entity)
            if entry and entry.life<2 then
                s.known[entity]=entry
                events.queue('entity_spawned',entity_payload(entry))
            end
        end
        for _,data in ipairs(take(ON.damage))do
            local entity=b.u32(data,16)
            local entry=snapshot(world,entity)or s.known[entity]
            local amount=i32(data,36)
            if entry and amount>0 then
                s.known[entity]=entry
                local payload=entity_payload(entry)
                payload.damage=amount;payload.health=entry.health;payload.max_health=entry.max_health
                local attacker,local_attacker,hex=credited(world,data,40)
                payload.attacker=attacker;payload.local_attacker=local_attacker==true;payload.attacker_peer=hex
                payload.downed=entry.life==1
                payload.position=handles.position({x=b.value(data,48,'f32'),y=b.value(data,52,'f32'),z=b.value(data,56,'f32')})
                events.queue('entity_damaged',payload)
                local info=world_module.type_info(entry.type)
                if info and info.avatar then
                    local player,is_local=owning_player(world,entity)
                    local copy={}
                    for k,v in pairs(payload)do copy[k]=v end
                    copy.player=player;copy.local_player=is_local
                    events.queue('player_damaged',copy)
                end
            end
        end
        for _,data in ipairs(take(ON.kill))do
            local entity=b.u32(data,16)
            local entry=snapshot(world,entity)or s.known[entity]
            if entry then
                s.known[entity]=nil
                local payload=entity_payload(entry)
                local killer,local_killer,hex=credited(world,data,24)
                payload.killer=killer;payload.local_killer=local_killer==true;payload.killer_peer=hex
                local at=entry.unit and world_module.unit_position(world,entry.unit)
                payload.position=at and handles.position(at)or nil
                payload.max_health=entry.max_health;payload.observed='kill'
                events.queue('entity_died',payload)
                if hex then
                    local killed={}
                    for k,v in pairs(payload)do killed[k]=v end
                    events.queue('entity_killed',killed)
                end
            end
        end
    end
end

------------------------------------------------------------------------------------------------------ stats --
local STAT_EVENTS={[hellforge.STAT.shots]={'player_fired','shots'},[hellforge.STAT.kills]={'player_kill_credited','kills'},
    [hellforge.STAT.hits]={'player_hit','hits'},[hellforge.STAT.damage]={'player_damage_dealt','damage'}}
local function local_player(world,with_avatars)
    for _,item in ipairs(world_module.players(world,with_avatars))do if item['local']then return item end end
end
local function stats_source(source)
    function source.start(s)
        local ok,why=open(s,{ON.stat})
        if not ok then return nil,why end
        return true
    end
    function source.stop(s)s.world=nil end
    function source.poll(s)
        drain()
        for _,data in ipairs(take(ON.stat))do
            local which=STAT_EVENTS[b.u32(data,16)]
            local item=which and events.wanted(which[1])and local_player(s.world,false)
            if item then
                local list={}
                for i=0,math.min(b.u32(data,36),5)-1 do
                    local at=40+i*16
                    local type_hex=hex64(data,at)
                    list[#list+1]={type=type_hex,name=world_module.source_name(type_hex),[which[2]]=i32(data,at+8)}
                end
                events.queue(which[1],{player=handles.player(item),local_player=true,[which[2]]=i32(data,20),
                    total=i32(data,24),sources=list,unattributed=i32(data,28)})
            end
        end
    end
end

---------------------------------------------------------------------------------------------------- weapons --
local SELECTIONS={'primary','secondary','support','held_item','held_item','unknown'}
local function weapon(data,entity_at,resource_at,selection_at,avatar)
    local entity=b.u32(data,entity_at)
    if entity==0 then return nil end
    local selection=b.u32(data,selection_at)
    local type_hex=hex64(data,resource_at)
    return {name=world_module.source_name(type_hex),type=type_hex,entity_id=entity,slot=SELECTIONS[selection],
        slot_proven=selection==1 or selection==2,selection=selection~=0 and selection or nil,avatar_id=avatar}
end
local function weapons_source(source)
    function source.start(s)
        local ok,why=open(s,{ON.weapon})
        if not ok then return nil,why end
        return true
    end
    function source.stop(s)s.world=nil end
    function source.poll(s)
        drain()
        for _,data in ipairs(take(ON.weapon))do
            local item=local_player(s.world,true)
            if item then
                local avatar,previous_avatar=b.u32(data,16),b.u32(data,20)
                local current=weapon(data,24,32,48,avatar)
                local previous=weapon(data,28,40,52,previous_avatar)
                local player=handles.player(item)
                if previous then
                    events.queue('weapon_unequipped',{player=player,local_player=true,weapon=previous,
                        reason=current and'switched'or(avatar==previous_avatar and'emptied'or'avatar_changed')})
                end
                if current then events.queue('weapon_equipped',{player=player,local_player=true,weapon=current})end
                events.queue('weapon_changed',{player=player,local_player=true,previous=previous,current=current})
            end
        end
    end
end

------------------------------------------------------------------------------------------------- explosions --
local function explosions_source(source)
    local names=require('hd2runtime/runtime/explosion_names')
    function source.start(s)
        local ok,why=open(s,{ON.explosion})
        if not ok then return nil,why end
        s.types={};s.epoch=events.state.epoch
        return true
    end
    function source.stop(s)s.world=nil end
    local function type_of(s,id)
        if id==0 then return nil end
        if s.epoch~=events.state.epoch then s.types={};s.epoch=events.state.epoch end
        local known=s.types[id]
        if known==nil then
            known=world_module.entity_type(s.world,id)or false
            if known then s.types[id]=known end
        end
        return known or nil
    end
    function source.poll(s)
        drain()
        for _,data in ipairs(take(ON.explosion))do
            if events.wanted('explosion')then
                local kind,from,owner=b.u32(data,16),b.u32(data,20),b.u32(data,24)
                local source_type,owner_type=type_of(s,from),type_of(s,owner)
                local payload={name=names.name(kind),observed='queue',cause={source='native'},
                    position=handles.position({x=b.value(data,40,'f32'),y=b.value(data,44,'f32'),z=b.value(data,48,'f32')}),
                    source_id=from~=0 and from or nil,source_type=source_type,
                    source_name=source_type and world_module.source_name(source_type)or nil,
                    owner_id=owner~=0 and owner or nil,owner_type=owner_type,
                    owner_name=owner_type and world_module.source_name(owner_type)or nil,local_player=false}
                if not zero64(data,32)then
                    payload.creditor_peer=hex64(data,32)
                    for _,item in ipairs(world_module.players(s.world,false))do
                        if item.peer==payload.creditor_peer then
                            payload.player=handles.player(item);payload.local_player=item['local']==true
                        end
                    end
                end
                events.queue('explosion',payload)
            end
        end
    end
end

------------------------------------------------------------------------------------------------- bug holes --
local function bug_holes_source(source)
    function source.start(s)
        local ok,why=open(s,{ON.bughole})
        if not ok then return nil,why end
        return true
    end
    function source.stop(s)s.world=nil end
    function source.poll(s)
        drain()
        for _,data in ipairs(take(ON.bughole))do
            local type_hex=hex64(data,24)
            local hole=world_module.bug_hole_kind(type_hex)or'unknown'
            local at=b.u32(data,52)~=0 and{x=b.value(data,40,'f32'),y=b.value(data,44,'f32'),z=b.value(data,48,'f32')}or nil
            events.queue('bughole_destroyed',{hole=hole,name='bug_spawner_'..hole,bile_titan=hole=='bile_titan',
                entity_id=b.u32(data,16),type=type_hex,unit_id=b.u32(data,20),level=b.u32(data,32),
                position=at and handles.position(at)or nil,owned=b.u32(data,36)~=0})
        end
    end
end

-- Replaces the Runtime's own sources (runtime/event_sources.lua's) with HellForge's.
function M.install(sources)
    if not hellforge.active()then return false end
    if sources.game_state then game_state_source(sources.game_state)end
    if sources.players then players_source(sources.players)end
    if sources.health then health_source(sources.health)end
    if sources.stats then stats_source(sources.stats)end
    if sources.weapons then weapons_source(sources.weapons)end
    if sources.explosions then explosions_source(sources.explosions)end
    if sources.bug_holes then bug_holes_source(sources.bug_holes)end
    return true
end
function M.reset_for_tests()inbox,drained,said={},nil,{}end
return M
