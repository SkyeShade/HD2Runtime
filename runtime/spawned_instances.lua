-- The spawned-instance registry (development; docs/custom-stratagem-api.md, "Spawned instances"). Not exported by
-- api/hd2.lua directly: hd2.custom_stratagem call contexts associate, and hd2.custom_stratagem.instance_of reads.
--
-- "This exact entity belongs to custom stratagem call X of player Y": a Pelican a call summoned, the chin turret of that
-- Pelican, the two launchers a call's pod delivered. An association names one live entity by its full id (index and
-- generation), so a reused index is never mistaken for it: every lookup re-checks that the entity still exists. Nothing
-- here writes the game, and nothing identifies an instance by a type or a shared definition: a vanilla entity of the
-- same type is never associated.
--
-- Scope: the mission. Every association is dropped when the mission ends (and on M.clear). At most M.MAX entries.
local world_module=require('hd2runtime/runtime/event_world')
local M={}
M.MAX=256
M.ROLE_PATTERN='^[a-z][a-z0-9_]*$'

local entries={}          -- entity -> {entity, role, definition, call_id, n, player (peer hex), parent, at}
local count=0
local epoch=0

-- Associates `entity` with a call. call: {definition, call_id, n, player} (the call context's identity). role: a short
-- name ('pelican', 'weapon', 'launcher'). parent: the entity it belongs to (optional). Returns the entry, or nil and why.
function M.associate(entity,call,role,parent)
    if type(entity)~='number'or entity<=0 or entity%1~=0 or entity>=4294967296 then return nil,'not an entity id'end
    if type(role)~='string'or not role:match(M.ROLE_PATTERN)or#role>32 then return nil,'role must be a short name'end
    if type(call)~='table'or type(call.definition)~='string'or type(call.call_id)~='string'then
        return nil,'call must be a call context'
    end
    local world=world_module.open()
    if not world then return nil,'no game world'end
    if world_module.entity_exists(world,entity)~=true then return nil,'entity '..entity..' does not exist'end
    local existing=entries[entity]
    if existing then
        if existing.call_id==call.call_id then return existing end
        return nil,('entity %d already belongs to %s'):format(entity,existing.call_id)
    end
    if count>=M.MAX then return nil,'at most '..M.MAX..' associated entities'end
    -- The experimental multiplayer scope: only a call the orchestrator marked (runtime/multiplayer.lua), or the parent's.
    local scope=require('hd2runtime/runtime/multiplayer').call_allowed(call)
    if parent~=nil then local p=entries[parent];scope=p~=nil and p.multiplayer==true end
    local entry={entity=entity,role=role,definition=call.definition,call_id=call.call_id,n=call.n,player=call.player,
        parent=parent,epoch=epoch,multiplayer=scope}
    entries[entity]=entry
    count=count+1
    return entry
end
-- A child of an associated entity (the turret of an associated Pelican) inherits its call. Returns the entry or nil.
function M.associate_child(parent,child,role)
    local p=M.lookup(parent)
    if not p then return nil,'the parent is not associated'end
    return M.associate(child,{definition=p.definition,call_id=p.call_id,n=p.n,player=p.player},role,parent)
end
-- The association of a live entity, or nil (also when it no longer exists: the entry is then dropped).
function M.lookup(entity)
    local e=entries[entity]
    if not e then return nil end
    local world=world_module.open()
    local exists=world and world_module.entity_exists(world,entity)
    if exists==false then
        entries[entity]=nil
        count=count-1
        return nil
    end
    return e
end
-- Every live entity of a call (optionally of one role), sorted by entity id.
function M.of_call(call_id,role)
    local out={}
    for entity,e in pairs(entries)do
        if e.call_id==call_id and(role==nil or e.role==role)then out[#out+1]=entity end
    end
    table.sort(out)
    local live={}
    for _,entity in ipairs(out)do if M.lookup(entity)then live[#live+1]=entity end end
    return live
end
function M.count()return count end
-- Drops every association (the mission ended).
function M.clear()
    entries,count={},0
    epoch=epoch+1
end
function M.reset_for_tests()entries,count,epoch={},0,0 end
return M
