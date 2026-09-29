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

--------------------------------------------------------------------------------------------------- positions --
-- A position snapshot {x, y, z} that nobody can change: every subscriber of an event (and every delayed callback
-- that kept it) reads the same values. p.x / p.y / p.z read it; p:copy() returns a plain, writable table;
-- p:unpack() returns x, y, z. tostring(p) formats it.
local Position={}
local position_data=setmetatable({},{__mode='k'})
local position_meta={__metatable='HD2Position'}
function position_meta.__index(p,key)
    local data=position_data[p]
    local value=data and data[key]
    if value~=nil then return value end
    return Position[key]
end
function position_meta.__newindex()error('positions are read-only snapshots; use p:copy() for a table you can change',2)end
function position_meta.__tostring(p)
    local data=position_data[p]
    return('(%.2f, %.2f, %.2f)'):format(data.x,data.y,data.z)
end
function position_meta.__eq(a,b)
    local da,db=position_data[a],position_data[b]
    return da~=nil and db~=nil and da.x==db.x and da.y==db.y and da.z==db.z
end
function Position.copy(p)local data=position_data[p];return{x=data.x,y=data.y,z=data.z}end
function Position.unpack(p)local data=position_data[p];return data.x,data.y,data.z end
-- Distance in metres to another position (read-only or a plain {x, y, z}).
function Position.distance(p,other)
    local data=position_data[p]
    local dx,dy,dz=data.x-other.x,data.y-other.y,data.z-other.z
    return math.sqrt(dx*dx+dy*dy+dz*dz)
end
-- A read-only position from {x, y, z} (nil stays nil; a position is returned as it is).
function M.position(value)
    if value==nil then return nil end
    if position_data[value]then return value end
    local proxy=setmetatable({},position_meta)
    position_data[proxy]={x=value.x,y=value.y,z=value.z}
    return proxy
end
function M.is_position(value)return position_data[value]~=nil end

------------------------------------------------------------------------------------------------------ entities --
local Entity={};Entity.__index=Entity
-- The identity snapshot of an entity type: its catalog entry, or the stable unresolved id for an unknown type.
local function identity_of(type_hex)
    local info=world_module.type_info(type_hex)
    if info then return info end
    return {id='entity/v1/unresolved/'..tostring(type_hex),kill=false}
end
M.identity_of=identity_of
-- snapshot: {id, type, descriptor_pointer, unit, network_id} (type = 16 hex digits)
function M.entity(snapshot)
    local info=identity_of(snapshot.type)
    return setmetatable({id=snapshot.id,type=snapshot.type,semantic_id=info.id,name=info.name,
        display_name=info.display,faction=info.faction,kind=info.kind,enemy=info.kill==true,avatar=info.avatar==true,
        unit=snapshot.unit,network_id=snapshot.network_id,epoch=events.state.epoch,
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
-- True when this entity is one of the given semantic ids ('enemy/v1/automatons/soldier_mg', ...): one id, several
-- ids, or a set {[id]=true}. Static: it answers from the snapshot, also after the entity is gone.
function Entity:is(first,...)
    if type(first)=='table'then return first[self.semantic_id]==true end
    if first==self.semantic_id then return true end
    for index=1,select('#',...)do if select(index,...)==self.semantic_id then return true end end
    return false
end
-- The identity snapshot as a plain table (never reads the game).
function Entity:identity()
    return {id=self.id,type=self.type,semantic_id=self.semantic_id,name=self.name,display_name=self.display_name,
        faction=self.faction,kind=self.kind,enemy=self.enemy,avatar=self.avatar,unit=self.unit,
        network_id=self.network_id,mission=self.epoch}
end
function Entity:is_player_avatar()return self.avatar end
function Entity:health()local state=live(self);return state and state.health or nil end
function Entity:max_health()local state=live(self);return state and state.max_health or nil end
-- Root position now (a read-only position); nil once the entity or its unit is gone.
function Entity:position()
    local state,world=live(self)
    if not state then return nil end
    return M.position(world_module.unit_position(world,state.descriptor.unit))
end
function Entity:describe()
    local state,why=live(self)
    return {id=self.id,type=self.type,semantic_id=self.semantic_id,name=self.name,display_name=self.display_name,
        faction=self.faction,kind=self.kind,enemy=self.enemy,avatar=self.avatar,
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
            return M.entity({id=player.avatar,type=state.descriptor.type,descriptor_pointer=state.descriptor.pointer,
                unit=state.descriptor.unit,network_id=player.avatar_network_id})
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
    local explicit=opts and opts.owner
    if explicit~=nil and(type(explicit)~='string'or#explicit==0 or#explicit>128)then
        return nil,'owner must be a mod id string'
    end
    local owner=events.owner(explicit,2)
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
