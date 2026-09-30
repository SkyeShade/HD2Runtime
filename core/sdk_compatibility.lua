-- Version-aware acknowledgements for mods built with an older SDK (docs/legacy-sdk-compatibility.md).
--
-- A later SDK can add an acknowledgement to a field that an earlier one let mods write without it: 0.28.0 added
-- allow_unverified_effect to 144 player weapon projectile, damage and explosion fields whose fired row it could no
-- longer establish (the PLAS-101 Purifier's charge levels, among others), and to the SH-51 Directional Shield body's
-- health and armor (domains/legacy_acknowledgements.lua, from schemas/legacy_acknowledgements.json). An operation
-- from a mod that declares an SDK older than the one that introduced the acknowledgement was valid when it was
-- written, so it is accepted without it as a legacy operation, and logged once with the advice to rebind and
-- re-export. A mod that declares that SDK or a later one keeps the rule, and so does every mod whose declaration
-- Runtime cannot read. No other acknowledgement or guard changes.
--
-- The declaration. Mods do not pass their SDK version to Runtime. Every published addon wrapper holds the version
-- its mod was built for in a local of its main chunk while it runs the mod's startup, and a generated mod registers
-- every operation inside that startup:
--   ModBuilder's ModExporter.Wrap and the ModTemplate's build.ps1: `local x,y,z=version('<sdk>')`;
--   the SDK's hd2.py wrap_addon: `local minimum='<sdk>'`;
-- both next to `local key='HD2RuntimeMod:<resource>'` and `local function start()`. At registration Runtime reads
-- those locals from the call stack (debug.getlocal on each main-chunk frame; nothing is called or written) and
-- remembers the declaration per mod resource, so an operation the same mod registers later from a callback, timer or
-- keybind (attributed to it by hd2.events) uses it too. Anything else is 'unknown'. Only the MAJOR.MINOR.PATCH core
-- is compared: an SDK prerelease of the introducing version already carried the acknowledgement.
local log=require('hd2runtime/runtime/log')
local table_=require('hd2runtime/domains/legacy_acknowledgements')
local M={}
local KEY='HD2RuntimeSdkCompatibilityV1'
local state=rawget(_G,KEY)
if not state then
    state={declared={},stack={}}
    rawset(_G,KEY,state)
end
local MAX_LEVELS,MAX_LOCALS=64,200

-- {major, minor, patch} of a SemVer string (prerelease and build metadata allowed), or nil.
function M.core(text)
    if type(text)~='string'then return nil end
    local major,minor,patch,rest=text:match('^(%d+)%.(%d+)%.(%d+)(.*)$')
    if not major or(rest~=''and not rest:match('^[%-+][0-9A-Za-z%-%.+]+$'))then return nil end
    return {tonumber(major),tonumber(minor),tonumber(patch)}
end
-- true when version a is older than b, comparing MAJOR.MINOR.PATCH only.
function M.older(a,b)
    local x,y=M.core(a),M.core(b)
    if not x or not y then return false end
    for index=1,3 do if x[index]~=y[index]then return x[index]<y[index]end end
    return false
end

-- The published wrapper shapes, recognised by their locals.
local function whole(value)return type(value)=='number'and value>=0 and value%1==0 and value<2^31 end
local function recognise(locals)
    local key,start=locals.key,locals.start
    if type(key)~='string'or type(start)~='function'then return nil end
    local mod=key:match('^HD2RuntimeMod:([^%c]+)$')
    if not mod then return nil end
    local sdk
    if type(locals.minimum)=='string'and type(locals.at_least)=='function'then
        sdk=locals.minimum
    elseif type(locals.version)=='function'and whole(locals.x)and whole(locals.y)and whole(locals.z)then
        sdk=string.format('%d.%d.%d',locals.x,locals.y,locals.z)
    end
    if not M.core(sdk)then return nil end
    return {mod=mod,sdk=sdk}
end
local function scan()
    -- Level 1 is scan itself; the first recognised main chunk towards the stack bottom is the registering wrapper.
    for level=2,MAX_LEVELS do
        local info=debug.getinfo(level,'S')
        if not info then return nil end
        if info.what=='main'then
            local locals={}
            for index=1,MAX_LOCALS do
                local name,value=debug.getlocal(level,index)
                if name==nil then break end
                locals[name]=value
            end
            local found=recognise(locals)
            if found then return found end
        end
    end
end
local function declared_by_wrapper()
    if type(debug)~='table'or type(debug.getinfo)~='function'or type(debug.getlocal)~='function'then return nil end
    local ok,found=pcall(scan)
    if not ok or not found then return nil end
    state.declared[found.mod]=found.sdk
    return found
end
-- Remember the declaration of the wrapper on the call stack, if any (hd2.events.run_as, which the SDK wrapper calls
-- before the startup runs). Never raises.
function M.remember()declared_by_wrapper()end
-- The registering mod and its declared SDK: {mod, sdk, source='wrapper'|'mod'|'unknown'}. Never raises.
function M.origin()
    local found=declared_by_wrapper()
    if found then
        return {mod=found.mod,sdk=found.sdk,source='wrapper',pending={},logged={}}
    end
    local ok,owner=pcall(function()return require('hd2runtime/runtime/events').owner()end)
    owner=ok and type(owner)=='string'and owner or'unknown'
    local sdk=state.declared[owner]
    return {mod=owner,sdk=sdk,source=sdk and'mod'or'unknown',pending={},logged={}}
end

-- The origin every validation inside fn(...) belongs to (nested calls stack). Errors propagate after it is left.
function M.with_origin(origin,fn,...)
    local stack=state.stack
    stack[#stack+1]=origin or false
    local depth=#stack
    local results={pcall(fn,...)}
    for index=#stack,depth,-1 do stack[index]=nil end
    if not results[1]then error(results[2],0)end
    return unpack(results,2,table.maxn(results))
end
function M.current()return state.stack[#state.stack]or nil end

-- A write domain asks this when a field that needs `acknowledgement` is written without it. true when the field
-- gained the acknowledgement in an SDK newer than the one the registering mod declares: the use is recorded on the
-- origin as a legacy operation. Otherwise false and, for a field that gained it, a clause for the refusal.
function M.legacy(acknowledgement,resource,target,field,reason)
    local since=(((table_[acknowledgement]or{})[resource]or{})[target]or{})[field]
    if not since then return false end
    local origin=M.current()
    if origin and origin.sdk and M.older(origin.sdk,since)then
        local key=resource..'\0'..target..'\0'..field
        if not origin.logged[key]then
            origin.logged[key]=true
            origin.pending[#origin.pending+1]={acknowledgement=acknowledgement,resource=resource,target=target,
                field=field,since=since,reason=reason}
        end
        require('hd2runtime/runtime/metrics').count('compatibility.legacy_checks')
        return true
    end
    if origin and origin.sdk then
        return false,'required since SDK '..since..'; '..origin.mod..' declares SDK '..origin.sdk
    end
    return false,'required since SDK '..since..'; Runtime could not read the SDK version of '
        ..(origin and origin.mod or'this mod')..', so the '..since..' rule applies'
end

-- Log the legacy uses a successful validation recorded on `origin`, once each, and move them to origin.legacy.
local function display(field)return(field:match('([^|]*)$'))end
function M.flush(origin,kind,id)
    if not origin or #origin.pending==0 then return end
    origin.legacy=origin.legacy or{}
    for _,use in ipairs(origin.pending)do
        origin.legacy[#origin.legacy+1]=use
        require('hd2runtime/runtime/metrics').count('compatibility.legacy_operations')
        log.emit('[HD2Runtime] '..kind..' '..tostring(id)..': legacy SDK '..origin.sdk..' operation from '..origin.mod
            ..': '..use.target..' '..display(use.field)..' needs '..use.acknowledgement..'=true since SDK '..use.since
            ..' and is applied without it, as SDK '..origin.sdk..' allowed. Rebind the project to SDK '..use.since
            ..' or later and re-export it, or add '..use.acknowledgement..'=true to the operation. Why it is needed: '
            ..tostring(use.reason))
    end
    origin.pending={}
end
-- Discard what a failed validation recorded, so a later successful one logs it.
function M.discard(origin)
    if not origin then return end
    for _,use in ipairs(origin.pending)do origin.logged[use.resource..'\0'..use.target..'\0'..use.field]=nil end
    origin.pending={}
end
-- Tests only.
function M._reset()state.declared,state.stack={}, {}end
return M
