-- The public API on HellForge (runtime/hellforge.lua, docs/hellforge.md). The API keeps every name. The actions (heal,
-- injure, statuses, velocity, the Supply Pack, explosions, projectiles, homing, per-shot changes, the Pelican, kill
-- credit, the mission timer freeze) are HellForge's engine actions (runtime/hellforge_actions.lua). What HellForge
-- does not take answers HELLFORGE_UNAVAILABLE instead (a rejected handle, or nil, code, reason), logged once per area,
-- so a mod that uses it keeps running:
--   custom stratagems (HellForge registers stratagems as game data: its code mods)
--   enemy spawn weights and the director (HellForge has not mapped enemies yet)
-- The local player's armor passives go through HellForge's own override (set_passives).
local hellforge=require('hd2runtime/runtime/hellforge')
local log=require('hd2runtime/runtime/log')
local M={}
local CODE='HELLFORGE_UNAVAILABLE'
-- Every area and why, for hd2.hellforge.unavailable and docs/hellforge.md.
M.AREAS={
    custom_stratagem='custom stratagems are HellForge stratagem mods (its stratagem registry)',
    enemies='HellForge has not mapped enemies yet',
}
local said={}
local function say(area)
    if said[area]then return end
    said[area]=true
    log.emit('[HD2Runtime] on HellForge: '..area..' is unavailable ('..M.AREAS[area]..')')
end
-- A rejected handle, as a refused registration gives.
local function rejected(area,what)
    say(area)
    local message=CODE..': '..what..' is not available on HellForge: '..M.AREAS[area]
    local handle={kind=area,status='rejected',error=message,result={status='REJECTED',code=CODE,message=message}}
    function handle.tick()end
    function handle.cancel()end
    function handle.stop()return handle end
    function handle.describe()return {kind=area,status='rejected',code=CODE,reason=message}end
    return handle
end
local function handle_returning(area,name)return function()return rejected(area,name)end end
local function nil_returning(area,name)
    return function()say(area);return nil,CODE,name..' is not available on HellForge: '..M.AREAS[area]end
end
-- A table's functions made unavailable: `names` (every function when nil); registrations (`handles`) return a
-- handle, the rest nil, code, reason. Catalogue reads (lists, descriptions) stay.
local function table_unavailable(t,area,label,handles,names)
    if type(t)~='table'then return end
    local only
    if names then only={};for _,name in ipairs(names)do only[name]=true end end
    for key,value in pairs(t)do
        if type(value)=='function'and(not only or only[key])then
            t[key]=(handles and handles[key])and handle_returning(area,label..'.'..key)or nil_returning(area,label..'.'..key)
        end
    end
end

-- The local player's armor passives through HellForge (hd2.player_passives.set).
local function passives_set(api,mod_name)
    local KIT=0xFFFFFFFF
    local base=require('hd2runtime/api/player_passives')
    return function(spec)
        local backend=hellforge.backend()
        local mod=hellforge.mod(mod_name())
        local handle={kind='player_passives',status='pending'}
        local function refuse(code,reason)
            handle.status,handle.code,handle.reason='refused',code,reason
            function handle.stop()return handle end
            return handle
        end
        if type(spec)~='table'then return refuse('INVALID_OPTION','spec must be a table {armor, second}')end
        local ids={}
        for _,slot in ipairs({'armor','second'})do
            local v=spec[slot]
            if v==nil or v==false then ids[slot]=KIT
            else
                local found,code,reason=base.find(v)
                if not found then return refuse(code,reason)end
                ids[slot]=found.id
            end
        end
        if ids.armor==KIT and ids.second==KIT then return refuse('INVALID_OPTION','give armor and/or second (a passive name or id)')end
        if not mod or not backend.set_passives(mod,ids.armor,ids.second)then
            return refuse('HELLFORGE_REFUSED',mod and backend.last(mod)or'HellForge has no room for another Lua mod')
        end
        handle.status,handle.armor,handle.second='active',ids.armor~=KIT and ids.armor or nil,ids.second~=KIT and ids.second or nil
        function handle.stop()
            backend.set_passives(mod,KIT,KIT)
            handle.status='stopped'
            return handle
        end
        function handle.describe()return {kind='player_passives',status=handle.status,armor=handle.armor,second=handle.second}end
        return handle
    end
end

-- Adapts the API table on HellForge; returns hd2.hellforge: {active, reason, bridge, build, unavailable}.
function M.adapt(api)
    if not hellforge.active()then return {active=false,reason=hellforge.reason}end
    table_unavailable(api.custom_stratagem,'custom_stratagem','hd2.custom_stratagem',{register=true})
    require('hd2runtime/runtime/hellforge_actions').install()
    if type(api.enemies)=='table'then
        for _,name in ipairs({'spawn_weight','spawn_list','spawn_status','spawn_compatibility','spawn_control_reason',
            'open_spawn_picker'})do
            if type(api.enemies[name])=='function'then api.enemies[name]=nil_returning('enemies','hd2.enemies.'..name)end
        end
    end
    if type(api.player_passives)=='table'then
        api.player_passives.set=passives_set(api,function()
            local ok,owner=pcall(function()return require('hd2runtime/runtime/events').owner()end)
            return ok and owner or nil
        end)
    end
    local backend=hellforge.backend()
    local info=backend.info()
    local unavailable={}
    for area in pairs(M.AREAS)do unavailable[#unavailable+1]=area end
    table.sort(unavailable)
    return {active=true,bridge=info.bridge,sdk=info.sdk,build=info.build,unavailable=unavailable,
        events_unavailable=require('hd2runtime/runtime/hellforge_events').UNAVAILABLE}
end
return M
