-- The weapon firing-sound catalogue (docs/weapon-sounds.md; docs/research/weapon-sounds-F5FEE03DCFDB.md), read-only.
--
-- domains/weapon_sounds.lua (scripts/generate_weapon_sounds.py) names every firing sound of build F5FEE03DCFDB that a
-- ProjectileWeapon type posts and a Wwise bank defines: `<family>/<weapon>[/<part>]`, for example
-- 'vehicle/maelstrom/main_gun', 'sentry/gatling', 'support/mg206', 'pelican/chin_autocannon'. Each entry keeps its
-- events, its bank, the packages listing the bank and the stratagem whose call-in package provides it, for the Runtime
-- only: mods name a sound, never an id (hd2.sounds lists and describes them without ids; api/sounds.lua).
--
-- A Runtime Pelican's chin gun takes a 'shot' or 'loop' entry on its own weapon copy (runtime/pelican_weapon.lua).
local D=require('hd2runtime/domains/weapon_sounds')
local M={}
M.SOUNDS=D.sounds
M.ALIASES=D.aliases
M.PINS=D.pins
M.CHIN=D.chin

-- The canonical name and entry of a name or alias, or nil.
function M.resolve(name)
    if type(name)~='string'then return nil end
    local canonical=D.aliases[name]or name
    local entry=D.sounds[canonical]
    if not entry then return nil end
    return canonical,entry
end
function M.entry(name)return select(2,M.resolve(name))end
-- Every canonical name, sorted.
local sorted
function M.names()
    if not sorted then
        sorted={}
        for name in pairs(D.sounds)do sorted[#sorted+1]=name end
        table.sort(sorted)
    end
    local out={}
    for k,name in ipairs(sorted)do out[k]=name end
    return out
end
-- True for the chin turret's own sound (taking it changes nothing).
function M.own(name)
    local _,e=M.resolve(name)
    return e~=nil and e.own==true
end
-- The stratagem whose call-in package provides the entry's bank (what a custom stratagem lists as an asset), or nil
-- (unknown, the chin turret's own, or resident-only).
function M.stratagem(name)
    local _,e=M.resolve(name)
    return e and not e.own and e.stratagem or nil
end
-- The text a refusal lists: a few names and where to find all of them.
function M.hint()
    return "a name of hd2.sounds.list() (for example 'vehicle/maelstrom/main_gun', 'sentry/gatling', "
        .."'support/mg206', 'pelican/chin_autocannon')"
end

-- What mods see of an entry: no event, bank or package id.
function M.public(name,e)
    return {name=name,label=e.label,kind=e.kind,family=e.family,stratagem=not e.own and e.stratagem or nil,
        resident_only=e.residentOnly==true,designed_rpm=e.rpm,range_m=e.range and e.range.maxDistance or nil,
        midi=e.midi==1,pelican_default=e.own==true}
end
function M.describe(name)
    local canonical,e=M.resolve(name)
    return e and M.public(canonical,e)or nil
end
-- filter: nil (all), a family ('sentry'), or {family, kind ('shot' | 'loop'), stratagem (true: has one; or a name),
-- resident_only (boolean), text (in the name or label, case-insensitive)}. Sorted by name.
local FILTER_KEYS={family=true,kind=true,stratagem=true,resident_only=true,text=true}
function M.check_filter(filter)
    if filter==nil then return {}end
    if type(filter)=='string'then return {family=filter}end
    if type(filter)~='table'then return nil,'the filter must be nil, a family name or a table'end
    for key in pairs(filter)do
        if not FILTER_KEYS[key]then return nil,'unsupported filter key: '..tostring(key)end
    end
    if filter.kind~=nil and filter.kind~='shot'and filter.kind~='loop'then return nil,"filter.kind must be 'shot' or 'loop'"end
    if filter.resident_only~=nil and type(filter.resident_only)~='boolean'then
        return nil,'filter.resident_only must be a boolean'
    end
    if filter.stratagem~=nil and filter.stratagem~=true and type(filter.stratagem)~='string'then
        return nil,'filter.stratagem must be true or a stratagem name'
    end
    for _,key in ipairs({'family','text'})do
        if filter[key]~=nil and type(filter[key])~='string'then return nil,'filter.'..key..' must be a string'end
    end
    return filter
end
function M.list(filter)
    local f,why=M.check_filter(filter)
    if not f then return nil,why end
    local text=f.text and f.text:lower()
    local out={}
    for _,name in ipairs(M.names())do
        local p=M.public(name,D.sounds[name])
        if(f.family==nil or p.family==f.family)and(f.kind==nil or p.kind==f.kind)
            and(f.resident_only==nil or p.resident_only==f.resident_only)
            and(f.stratagem==nil or(f.stratagem==true and p.stratagem~=nil)or p.stratagem==f.stratagem)
            and(text==nil or name:lower():find(text,1,true)or p.label:lower():find(text,1,true))then
            out[#out+1]=p
        end
    end
    return out
end
return M
