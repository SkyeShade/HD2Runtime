-- The explosion catalogue (docs/explosions.md): every explosion type research/explosion-identities-F5FEE03DCFDB.json
-- names from its owners (domains/explosion_catalogue.lua), as hd2.explosions.list(filter), hd2.explosions.describe(name)
-- and the typed target hd2.explosion(name). Offline: no game reads. Raw type, row, resource and package ids never leave
-- this module; an explosion is its semantic id ('weapon/r36_eruptor/impact').
local catalogue=require('hd2runtime/domains/explosion_catalogue')
local writes=require('hd2runtime/domains/explosion_writes')
local M={}

local function copy(value)
    if type(value)~='table'then return value end
    local out={}
    for key,item in pairs(value)do out[key]=copy(item)end
    return out
end
-- An entry by semantic id or label (case-insensitive): entry, id; or nil and the reason.
function M.entry(name)
    if type(name)=='table'and rawget(name,'resource')=='explosion'then name=rawget(name,'explosion')end
    local entry,id=writes.entry(name)
    if not entry then
        return nil,'UNKNOWN_EXPLOSION: '..tostring(name)..' is not a catalogued explosion (hd2.explosions.list())'
    end
    return entry,id
end
local function owners(entry)
    local out={}
    for index,owner in ipairs(entry.owners)do
        out[index]={category=owner.category,name=owner.name,role=owner.role,reference=owner.reference}
    end
    return out
end
local function package_view(entry)
    local package=entry.package
    if not package then return {known=false}end
    return {known=true,name=package.name,via=package.via,mission=package.mission==true,
        loaded_by_runtime=package.mission~=true}
end
local NAMES={'inner_radius','outer_radius','shockwave_radius','shrapnel_count','standard_damage','durable_damage',
    'ap_direct','ap_slight','ap_large','ap_extreme','demolition','stagger','push_force'}
local function stats(entry)
    local out={}
    for index,name in ipairs(NAMES)do out[name]=entry.values[index]end
    out.shrapnel=entry.shrapnel==true;out.arc=entry.arc==true;out.damage_row=entry.damage~=nil
    return out
end
local function summary(id,entry)
    local legacy=entry.legacy
    return {name=id,label=entry.label,family=entry.family,evidence=entry.evidence,shared=entry.shared==true,
        owners=entry.ownerCount,package_known=entry.package~=nil,mission_package=entry.package~=nil
            and entry.package.mission==true or false,payload=entry.payload==true,spawn=entry.spawn==true,
        reviewed_spawn=legacy~=nil,legacy_name=legacy and legacy.name or nil,stats=stats(entry)}
end
M.summary=summary

-- Filter keys: family ('weapon', 'support_weapon', 'throwable', 'stratagem', 'backpack', 'vehicle', 'enemy',
-- 'entity'), owner (a substring of an owner's name, case-insensitive), search (a substring of the name or label),
-- shared, payload, spawn, package_known, reviewed_spawn (booleans).
local FILTERS={family=true,owner=true,search=true,shared=true,payload=true,spawn=true,package_known=true,
    reviewed_spawn=true}
function M.list(filter)
    assert(filter==nil or type(filter)=='table','hd2.explosions.list(filter): filter must be a table or nil')
    filter=filter or{}
    for key in pairs(filter)do assert(FILTERS[key],'unsupported explosion filter: '..tostring(key))end
    local out={}
    for _,id in ipairs(catalogue.order)do
        local entry=catalogue.explosions[id]
        local item=summary(id,entry)
        local keep=(filter.family==nil or entry.family==filter.family)
        for _,key in ipairs({'shared','payload','spawn','package_known','reviewed_spawn'})do
            if filter[key]~=nil and item[key]~=(filter[key]==true)then keep=false end
        end
        if keep and filter.search then
            local text=tostring(filter.search):lower()
            keep=id:find(text,1,true)~=nil or entry.label:lower():find(text,1,true)~=nil
        end
        if keep and filter.owner then
            local text=tostring(filter.owner):lower()
            local found=false
            for _,owner in ipairs(entry.owners)do
                if owner.name and owner.name:lower():find(text,1,true)then found=true;break end
            end
            keep=found
        end
        if keep then out[#out+1]=item end
    end
    return out
end

-- Everything the catalogue knows about one explosion: the summary plus its owners, package and editable fields.
function M.describe(name)
    local entry,id=M.entry(name)
    if not entry then return nil,id end
    local out=summary(id,entry)
    out.owners=owners(entry)
    out.owner_count=entry.ownerCount
    out.package=package_view(entry)
    out.damage_shared=entry.damage~=nil and entry.damage.shared==true
    out.fields=M.fields(id)
    return out
end
-- The editable fields of one explosion: {semanticFieldId, currentDefault, editable, reason, shared, range,
-- acknowledgements} in catalogue order (hd2.fields.explosion.* ids).
function M.fields(name)
    local entry,id=assert(M.entry(name))
    local out={}
    for index,field in ipairs(catalogue.fields)do
        local descriptor=writes.descriptor(entry,id,field.id)
        out[index]={semanticFieldId=field.id,unit=field.unit,type=field.type,currentDefault=descriptor.currentDefault,
            editable=descriptor.editable,reason=descriptor.reason,shared=descriptor.shared,range=copy(descriptor.range),
            acknowledgements=descriptor.editable and(descriptor.shared and{'allow_shared','allow_unverified_effect'}
                or{'allow_unverified_effect'})or{}}
    end
    return out
end

-- The typed target and payload handle: hd2.explosion(name). A target for hd2.patch / transaction / plan / ensure
-- (the explosion.* fields), a value for terminal.explosion, projectile.impact_explosion / expiry_explosion and custom
-- projectile rows, and an argument of hd2.explosions.spawn / prepare.
local Handle={}
Handle.__index=Handle
function Handle:describe()return M.describe(rawget(self,'explosion'))end
function Handle:fields()return M.fields(rawget(self,'explosion'))end
function M.handle(name)
    local entry,id=M.entry(name)
    assert(entry,id)
    return setmetatable({resource='explosion',explosion=id},Handle)
end
function M.is_handle(value)
    return type(value)=='table'and rawget(value,'resource')=='explosion'and type(rawget(value,'explosion'))=='string'
end
return M
