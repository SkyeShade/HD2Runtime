-- Explosion type -> name for event payloads (the `explosion` event, runtime/event_sources.lua). Internal: mods see the
-- name, never the raw ExplosionType.
--
-- The default lookup names the explosion types domains/event_natives.lua catalogues: each weapon's own explosion
-- (explosion.weapons: the type the weapon's shell requests, named by its weapon) and the named explosions
-- (explosion.named: the Hellbombs, the Cyborg Production Unit). A name names the explosion TYPE: another requester of
-- the same type (a mission objective requesting 242, a Runtime custom projectile using a donor's explosion) gets the
-- same name; who requested it is the event's source, owner and creditor.
--
-- A fuller catalogue can extend the lookup: M.set_resolver(fn) with fn(type) returning a name (string), a table
-- {name = ...}, or nil (the catalogue does not name it: the default answers). set_resolver(nil) restores the default.
-- A resolver that raises or returns anything else is logged once and the default answers instead.
local natives=require('hd2runtime/domains/event_natives')
local M={}

local defaults
local function default_names()
    if defaults then return defaults end
    defaults={}
    local X=natives.explosion
    for _,item in ipairs(X.weapons or{})do
        if defaults[item.type]==nil then defaults[item.type]=item.weapon end
    end
    for _,item in ipairs(X.named or{})do defaults[item.type]=item.name end
    return defaults
end
function M.default(kind)return default_names()[kind]end

local resolver,failed
function M.set_resolver(fn)
    assert(fn==nil or type(fn)=='function','an explosion name resolver is a function or nil')
    resolver,failed=fn,nil
end
function M.resolver()return resolver end

-- The name of an explosion type, or nil when no catalogue names it.
function M.name(kind)
    if type(kind)~='number'then return nil end
    if resolver then
        local ok,value=pcall(resolver,kind)
        if ok and type(value)=='string'then return value end
        if ok and type(value)=='table'and type(value.name)=='string'then return value.name end
        if not(ok and(value==nil or type(value)=='table'and value.name==nil))and not failed then
            failed=true
            pcall(require('hd2runtime/runtime/log').emit,'[HD2Runtime] explosion name resolver failed ('
                ..(ok and('returned '..type(value))or tostring(value))..'): the default names answer instead')
        end
    end
    return default_names()[kind]
end
return M
