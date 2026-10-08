-- hd2.passives and hd2.player_passives (docs/armor-passives.md; runtime/player_passives.lua). The write is DEVELOPMENT,
-- the local player's own record, solo only, not live-tested.
--
--   for _, p in ipairs(hd2.passives.list()) do print(p.id, p.name) end
--   local mine = hd2.player_passives()           -- {armor_kit, armor_passive, helmet_passive, effective, ...} or nil, code, reason
--   local h = hd2.player_passives.set({armor = 'SERVO-ASSISTED', second = 'SCOUT', allow_unverified_effect = true})
--   h:stop()                                      -- the kit's own passives again
--
-- A passive is named by its game name (any case) or its id. armor replaces the armor passive (record +0x3C); second
-- puts a passive in the helmet slot (+0x38, empty for every vanilla helmet): its keys the armor passive lacks are added
-- for every reader that consults both slots (flags 3); an overlapping key keeps the armor's row (no stacking). Omitted
-- or false: the kit's own value. The handle keeps the values in place: after a kit change the game re-derives the slots
-- and the Runtime writes them again; stop() puts the kit's values back. A mod's second set() replaces its first;
-- another mod's is refused (ALREADY_SET). A refusal never raises: status 'refused' with code and reason.
local events=require('hd2runtime/runtime/events')
local passives=require('hd2runtime/runtime/player_passives')
local D=require('hd2runtime/domains/player_passives')
local M={}
local OPTIONS={armor=true,second=true,owner=true,allow_unverified_effect=true}
local UNUSED={}
for _,id in ipairs(D.unused)do UNUSED[id]=true end

local function copy_passive(p)
    local modifiers={}
    for i,m in ipairs(p.modifiers)do modifiers[i]={key=m.key,key_name=m.key_name,type=m.type,value=m.value,text=m.text}end
    return {id=p.id,name=p.name,modifiers=modifiers,effect_package=p.package~=nil,package=p.package,armor_kits=p.armorKits}
end
-- Every passive of the game (the research's table, offline): {id, name, modifiers = {{key, key_name, type, value,
-- text}}, effect_package, package, armor_kits}, by id.
function M.list()
    local out={}
    for i,p in ipairs(D.passives)do out[i]=copy_passive(p)end
    return out
end
-- One passive by name (any case) or id, or nil, code, reason.
function M.find(value)
    local p
    if type(value)=='number'then
        if value%1~=0 or value<0 or value>=D.manager.passiveIds then
            return nil,'UNKNOWN_PASSIVE','passive ids are 0 to '..(D.manager.passiveIds-1)
        end
        if UNUSED[value]then return nil,'UNKNOWN_PASSIVE','passive id '..value..' is unused by the game'end
        p=passives.by_id[value]
    elseif type(value)=='string'then
        for _,item in ipairs(D.passives)do if item.name:lower()==value:lower()then p=item end end
    end
    if not p then return nil,'UNKNOWN_PASSIVE',tostring(value)..' is not a passive (see hd2.passives.list())'end
    return copy_passive(p)
end
-- The local player's passives (read now): {entity, record, armor_kit = {id, name, passive}, helmet_kit, cape_kit,
-- armor_passive = {id, name}, helmet_passive = {id, name}, derived = {armor, second}, overridden, runtime (the mod
-- holding an override), effective = {{key, key_name, type, value, source, passive, name}}}, or nil, code, reason.
function M.current()return passives.observe()end

-- A handle's status, code and reason follow the held override (active, waiting, suspended, lost, replaced) until
-- stop(); a refused handle keeps its own.
local Handle={}
local LIVE={status=true,code=true,reason=true}
local Meta={__index=function(handle,key)
    local s=rawget(handle,'state')
    if s and LIVE[key]then return s[key]end
    return Handle[key]
end}
function Handle:describe()
    local s=rawget(self,'state')or rawget(self,'last')
    return {kind='player_passives',owner=self.owner,status=self.status,code=self.code,reason=self.reason,
        armor=self.armor,second=self.second,applications=s and s.applications or 0}
end
-- Stop holding: the kit's own passives go back where the slots still hold this override's values.
function Handle:stop()
    local s=rawget(self,'state')
    if not s then return self end
    rawset(self,'state',nil)
    rawset(self,'last',s)
    if s.status~='replaced'then passives.release(s)end
    rawset(self,'status','stopped')
    return self
end
local function refuse(handle,code,reason)
    handle.status,handle.code,handle.reason='refused',code,reason
    events.emit_log('passives ('..handle.owner..') refused: '..code..': '..reason)
    return handle
end
local function slot_value(handle,spec,key)
    local v=spec[key]
    if v==nil or v==false then return true,nil end
    local p,code,reason=M.find(v)
    if not p then return false,code,('%s: %s'):format(key,reason)end
    handle[key]={id=p.id,name=p.name}
    return true,p.id
end

-- Override the local player's armor passive and/or add a second passive. Returns a handle {status = 'active' |
-- 'waiting' (no record yet: applied when it appears) | 'refused', code, reason, armor, second, stop(), describe()}.
function M.set(spec)
    local explicit=type(spec)=='table'and spec.owner
    local owner=events.owner(type(explicit)=='string'and explicit or nil,2)
    local handle=setmetatable({kind='player_passives',owner=owner,status='pending'},Meta)
    if type(spec)~='table'then return refuse(handle,'INVALID_OPTION','spec must be a table {armor, second}')end
    for key in pairs(spec)do
        if not OPTIONS[key]then return refuse(handle,'INVALID_OPTION','unsupported option: '..tostring(key))end
    end
    if spec.allow_unverified_effect~=true then
        return refuse(handle,'ACKNOWLEDGEMENT_REQUIRED','a passive override is not yet shown in game: pass '
            ..'allow_unverified_effect = true')
    end
    local ok,armor,reason=slot_value(handle,spec,'armor')
    if not ok then return refuse(handle,armor,reason)end
    local ok2,second,reason2=slot_value(handle,spec,'second')
    if not ok2 then return refuse(handle,second,reason2)end
    if armor==nil and second==nil then
        return refuse(handle,'INVALID_OPTION','give armor and/or second (a passive name or id)')
    end
    if second==0 then return refuse(handle,'INVALID_OPTION','second = STANDARD ISSUE adds nothing: use false')end
    if second~=nil and second==armor then
        return refuse(handle,'SAME_PASSIVE','the second passive is the armor passive: its keys are already read')
    end
    if second~=nil and armor==nil then
        -- The second passive against the armor kit's own passive, as the record reads now (a later armor change is
        -- the player's: the second passive then simply adds nothing the armor has).
        local now=passives.observe()
        if now and now.derived.armor==second then
            return refuse(handle,'SAME_PASSIVE','the second passive is the armor kit\'s own passive: its keys are '
                ..'already read')
        end
    end
    local state=passives.hold({owner=owner,want={armor=armor,second=second}})
    if state.status=='refused'then return refuse(handle,state.code,state.reason)end
    handle.status=nil
    handle.state=state
    return handle
end
-- The held override, or nil: {owner, status, code, reason, armor = {id, name}|nil, second = {id, name}|nil,
-- applications}.
function M.status()
    local s=passives.held()
    if not s then return nil end
    local function view(id)return id and{id=id,name=passives.name_of(id)}or nil end
    return {owner=s.owner,status=s.status,code=s.code,reason=s.reason,armor=view(s.want.armor),
        second=view(s.want.second),applications=s.applications}
end
return M
