-- hd2.actions.resupply_from_pack(player): the Supply Pack's own self-use on the LOCAL player's avatar
-- (docs/player-equipment.md; research/player-equipment-F5FEE03DCFDB.json; runtime/player_equipment.lua).
--
-- Exactly what the game does when the wearer presses the pack's key: the self-use ability named by the pack's own
-- deposit definition starts on the avatar through the game's own try_start_action; the game's ability then consumes
-- one supply and resupplies the wearer, with its own animation and network replication. Each machine uses only the
-- pack its own avatar wears; no host needed. Like every action it belongs to the calling mod, records a cause, is
-- rate limited and fails closed with a code (docs/event-scripting.md#gameplay-actions).
local events=require('hd2runtime/runtime/events')
local handles=require('hd2runtime/runtime/handles')
local world_module=require('hd2runtime/runtime/event_world')
local equipment=require('hd2runtime/runtime/player_equipment')
local metrics=require('hd2runtime/runtime/metrics')
local M={}

-- One request at once per mod, refilled every 2 s: the game's own use takes about that long and refuses while busy.
M.BURST=1
M.REFILL=0.5

local Action={};Action.__index=Action
function Action:describe()
    return {kind=self.kind,owner=self.owner,status=self.status,code=self.code,reason=self.reason,mission=self.mission,
        backpack=self.backpack,supplies=self.supplies,capacity=self.capacity,ability=self.ability}
end
-- True once the game accepted the request (the self-use ability runs on the avatar).
function Action:requested()return self.status=='requested'end
local function refuse(action,code,reason)
    action.status,action.code,action.reason='refused',code,reason
    events.emit_log(action.kind..' ('..action.owner..') refused: '..code..': '..reason)
    metrics.count('actions.refused')
    return action
end
local buckets={}
local function take_token(owner)
    local now=events.state.now
    local bucket=buckets[owner]
    if not bucket then bucket={tokens=M.BURST,at=now};buckets[owner]=bucket end
    bucket.tokens=math.min(M.BURST,bucket.tokens+(now-bucket.at)*M.REFILL)
    bucket.at=now
    if bucket.tokens<1 then return false end
    bucket.tokens=bucket.tokens-1
    return true
end

-- hd2.actions.resupply_from_pack(player[, opts]): opts.owner (a mod id) only. Returns the action: 'requested' (with
-- backpack, supplies before the use, capacity, ability) or 'refused' with a code: INVALID_OPTION, INVALID_TARGET,
-- NOT_LOCAL_PLAYER, CAUSE_DEPTH, NOT_IN_MISSION, NO_LOCAL_AVATAR, AVATAR_DOWNED, RATE_LIMITED, NOT_GAME_THREAD,
-- NO_BACKPACK, NOT_A_SUPPLY_PACK, NO_SUPPLIES, BUSY, CANNOT_ACT, NO_AMMO_NEEDED, NOT_STARTED, RESUPPLY_UNAVAILABLE.
function M.resupply_from_pack(player,opts)
    opts=type(opts)=='table'and opts or{}
    local explicit=opts.owner
    local owner=events.owner(type(explicit)=='string'and#explicit>0 and#explicit<=128 and explicit or nil,2)
    local action=setmetatable({kind='resupply_from_pack',owner=owner,status='pending'},Action)
    local _,epoch=events.mission()
    action.mission=epoch
    if explicit~=nil and(type(explicit)~='string'or#explicit==0 or#explicit>128)then
        return refuse(action,'INVALID_OPTION','owner must be a mod id string')
    end
    for key in pairs(opts)do
        if key~='owner'then return refuse(action,'INVALID_OPTION','unsupported option: '..tostring(key))end
    end
    if getmetatable(player)~=handles.Player then
        return refuse(action,'INVALID_TARGET','the target must be a player handle (hd2.local_player())')
    end
    if not player.is_local then
        return refuse(action,'NOT_LOCAL_PLAYER','only the local player\'s own Supply Pack (each machine uses the pack '
            ..'its own avatar wears)')
    end
    action.cause=events.action_cause(owner,'resupply_from_pack')
    if action.cause.depth>events.MAX_CAUSE_DEPTH then
        return refuse(action,'CAUSE_DEPTH','refused to extend a chain of mod-caused actions')
    end
    local world,why=world_module.open()
    if not world then return refuse(action,'RESUPPLY_UNAVAILABLE',tostring(why))end
    local state=world_module.game_state(world)
    if not(state and state.mission)then return refuse(action,'NOT_IN_MISSION','the game is not in a mission')end
    local tracked,current=events.mission()
    if tracked and action.mission and current~=action.mission then
        return refuse(action,'NOT_IN_MISSION','the mission it was requested in has ended')
    end
    local avatar,reason=handles.local_avatar(world)
    if not avatar then return refuse(action,'NO_LOCAL_AVATAR',tostring(reason))end
    local health=world_module.entity_state(world,avatar.id)
    if health and health.life==1 then return refuse(action,'AVATAR_DOWNED','the avatar is downed')end
    if not take_token(owner)then
        return refuse(action,'RATE_LIMITED','at most '..M.BURST..' request at once and one every '..(1/M.REFILL)
            ..' s per mod')
    end
    local result,failure=equipment.resupply_self(world,avatar.id)
    if not result then
        local code=tostring(failure):match('^([A-Z_]+):')or'RESUPPLY_UNAVAILABLE'
        return refuse(action,code,(tostring(failure):gsub('^[A-Z_]+: ','')))
    end
    action.status,action.target='requested',avatar.id
    action.backpack,action.supplies,action.capacity,action.ability=result.backpack,result.supplies,result.capacity,
        result.ability
    metrics.count('actions.self_resupplies')
    events.emit_log('Supply Pack self-use requested on the local avatar '..avatar.id..' by '..owner..' ('
        ..result.supplies..'/'..result.capacity..' supplies before)')
    return action
end
function M.reset_for_tests()for key in pairs(buckets)do buckets[key]=nil end end
return M
