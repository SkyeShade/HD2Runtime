-- Entity and player handles (docs/events.md#handles).
--
-- A handle never holds a live address. Every method that needs the game re-resolves the object through the game's
-- own tables and checks it is still the same object: the same mission (epoch), the entity still in the health
-- manager's hash, the same type and the same descriptor. Anything else is invalid, and live queries return nil.
-- Static facts captured when the handle was made (id, type, name, faction, enemy) stay readable after destruction.
local events=require('hd2runtime/runtime/events')
local world_module=require('hd2runtime/runtime/event_world')
local metrics=require('hd2runtime/runtime/metrics')
local M={}

local Entity={};Entity.__index=Entity
-- snapshot: {id, type, descriptor_pointer} (type = 16 hex digits)
function M.entity(snapshot)
    local info=world_module.type_info(snapshot.type)or{}
    return setmetatable({id=snapshot.id,type=snapshot.type,name=info.name,faction=info.faction,
        enemy=info.kill==true,avatar=info.avatar==true,epoch=events.state.epoch,
        descriptor_pointer=snapshot.descriptor_pointer},Entity)
end
local function live(self)
    if self.epoch~=events.state.epoch then return nil,'the mission this handle belongs to has ended' end
    local world,why=world_module.open()
    if not world then return nil,why end
    -- The engine advances an entity's generation when it destroys it: a stale id never reads as live.
    if world_module.entity_exists(world,self.id)==false then return nil,'the engine destroyed the entity' end
    local state=world_module.entity_state(world,self.id)
    if not state then return nil,'the entity no longer exists' end
    if state.descriptor.type~=self.type or(self.descriptor_pointer and state.descriptor.pointer~=self.descriptor_pointer)then
        return nil,'the entity id now belongs to another object'
    end
    metrics.count('events.handle_lookups')
    return state,world
end
function Entity:is_valid()return live(self)~=nil end
-- Not dead (a downed enemy or Helldiver still counts as alive until it dies).
function Entity:is_alive()local state=live(self);return state~=nil and state.life<2 end
function Entity:is_downed()local state=live(self);return state~=nil and state.life==1 end
-- The game's own rule: its death counts as an enemy kill (settings KillScore > 0).
function Entity:is_enemy()return self.enemy end
function Entity:is_player_avatar()return self.avatar end
function Entity:health()local state=live(self);return state and state.health or nil end
function Entity:max_health()local state=live(self);return state and state.max_health or nil end
-- Root position now ({x,y,z}); nil once the entity or its unit is gone.
function Entity:position()
    local state,world=live(self)
    if not state then return nil end
    return world_module.unit_position(world,state.descriptor.unit)
end
function Entity:describe()
    local state,why=live(self)
    return {id=self.id,type=self.type,name=self.name,faction=self.faction,enemy=self.enemy,avatar=self.avatar,
        valid=state~=nil,reason=state==nil and why or nil,health=state and state.health,
        max_health=state and state.max_health,life=state and state.life}
end
M.Entity=Entity

local Player={};Player.__index=Player
-- snapshot: {peer (16 hex digits), slot, local}
function M.player(snapshot)
    return setmetatable({peer=snapshot.peer,slot=snapshot.slot,is_local=snapshot['local']==true,
        avatar_hint=snapshot.avatar},Player)
end
function Player:is_local_player()return self.is_local end
function Player:is_valid()
    local world=world_module.open()
    if not world then return false end
    for _,player in ipairs(world_module.players(world))do if player.peer==self.peer then return true end end
    return false
end
-- The player's current avatar, resolved through the player list (avatar network id -> entity). nil while the player
-- has none (dead and waiting to respawn, or not in a mission).
function Player:avatar()
    local world,why=world_module.open()
    if not world then return nil,why end
    for _,player in ipairs(world_module.players(world,true))do
        if player.peer==self.peer then
            if not player.avatar then return nil,'the player has no avatar now' end
            local state=world_module.entity_state(world,player.avatar)
            if not state then return nil,'the avatar has no health record' end
            return M.entity({id=player.avatar,type=state.descriptor.type,descriptor_pointer=state.descriptor.pointer})
        end
    end
    return nil,'the player is no longer in the player list'
end
function Player:is_alive()local avatar=self:avatar();return avatar~=nil and avatar:is_alive()end
function Player:health()local avatar=self:avatar();return avatar and avatar:health()end
function Player:max_health()local avatar=self:avatar();return avatar and avatar:max_health()end
function Player:position()local avatar=self:avatar();return avatar and avatar:position()end
-- Heal the local player through the game's own heal function (clamped to maximum health). Returns the amount
-- requested after Runtime's clamp, or nil and the reason. The resulting player_healed event carries this mod's cause.
function Player:heal(amount,opts)
    local owner=(opts and opts.owner)or events.current_owner()or'unknown'
    local cause=events.action_cause(owner,'heal')
    if cause.depth>events.MAX_CAUSE_DEPTH then
        events.emit_log('heal refused for '..owner..': cause chain deeper than '..events.MAX_CAUSE_DEPTH)
        return nil,'CAUSE_DEPTH: refused to extend a chain of mod-caused actions'
    end
    if not self.is_local then return nil,'only the local player can be healed' end
    local avatar,why=self:avatar()
    if avatar and not avatar.avatar then return nil,'the avatar is not a Helldiver' end
    if not avatar then return nil,why end
    local world=world_module.open()
    local applied,reason=world_module.heal(world,avatar.id,amount)
    if applied and applied>0 then M.expect_heal(avatar.id,applied,cause)end
    return applied,reason
end
function Player:describe()
    return {peer=self.peer,slot=self.slot,is_local=self.is_local,valid=self:is_valid()}
end
M.Player=Player

-- Every player in the session now, and the local player.
function M.players()
    local world=world_module.open()
    local result={}
    if not world then return result end
    for _,player in ipairs(world_module.players(world,false))do result[#result+1]=M.player(player)end
    return result
end
function M.local_player()
    for _,player in ipairs(M.players())do if player.is_local then return player end end
    return nil
end

-- The locally owned Helldiver avatar: {id, type, descriptor_pointer} or nil. Owned records are the first
-- `owned` indices of the health manager (its owned partition).
function M.local_avatar(world)
    local header=world_module.health_header(world,world.view.slot())
    if not header then return nil end
    for index=0,math.min(header.live,64)-1 do
        local descriptor=world_module.descriptor(world,header,index)
        if descriptor and descriptor.owned then
            local info=world_module.type_info(descriptor.type)
            if info and info.avatar then
                return {id=descriptor.entity,type=descriptor.type,descriptor_pointer=descriptor.pointer}
            end
        end
    end
    return nil
end

-- Causes: a heal Runtime performed is matched to the health increase the next polls observe.
local pending={}
function M.expect_heal(entity,amount,cause)
    pending[#pending+1]={entity=entity,amount=amount,cause=cause,until_time=events.state.now+2}
end
-- The cause of an observed heal of `entity`: the matching pending action, or nil (native gameplay).
function M.claim_heal(entity)
    local now=events.state.now
    for index=#pending,1,-1 do
        local item=pending[index]
        if item.until_time<now then table.remove(pending,index)
        elseif item.entity==entity then table.remove(pending,index);return item.cause end
    end
    return nil
end
function M.reset_for_tests()for index=#pending,1,-1 do pending[index]=nil end end
return M
