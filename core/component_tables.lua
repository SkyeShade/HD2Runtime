-- Where the game reads each entity component table from (research/docs/entity-component-table-pointers.md).
--
-- The entity manager ([game.dll + global], stored only by its constructor) keeps ONE pointer per component type:
-- manager + slotBase + 8 x component index, stored only by the entity file loader, = the table the game's lookups read
-- that component's records from. In place it is the entity allocation + the profile component offset + 28, the very
-- table core/entity_catalog.lua reads and every typed write writes. Another program can repoint it to a private copy
-- (True Lasgun Beam Overhaul does so for BeamWeapon, WeaponHeat and WeaponMagazine: the LAS-12 Sai report, "editing
-- Heat Per Shot and Cool Per Sec has no effect"); a write to the original table then lands where the game no longer
-- reads, with no effect and no error.
--
-- M.check re-proves, read-only, per entity capture, that the live pointer of every captured component equals the
-- table HD2Runtime is about to use. A component whose pointer differs is refused ALONE (CONFLICT, owner: unknown mod):
-- every other component, resource and value goes ahead. Pins (the global's constructor store, the loader's slot store
-- and layout, each component's lookup reading its slot through the global) are re-proven as exact bytes once per
-- loaded game.dll, after the build fingerprint. An unreadable pointer is TARGET_UNAVAILABLE (transient) for every
-- component of that capture. Nothing is written; no address leaves this module.
local b=require('hd2runtime/core/bytes')
local metrics=require('hd2runtime/runtime/metrics')
local D=require('hd2runtime/domains/component_tables')
local M={}
local IMAGE,PRIVATE=0x1000000,0x20000
local proven={}        -- game.dll base -> true | false, reason
local logged={}        -- component -> true (one log line per component and session)

local function emit(message)
    local ok,log=pcall(require,'hd2runtime/runtime/log')
    if ok and log and log.emit then pcall(log.emit,message)end
end
local function short(name)return(tostring(name):gsub('ComponentData$',''))end

-- The refusal of one component whose table the game reads elsewhere. Carries the unknown-owner marker
-- (core/ownership.lua FOREIGN_MARKER): results get owner='unknown', hd2.inspect reports the field 'foreign'.
function M.moved_reason(name)
    return('CONFLICT: the game reads its %s table from another place (another mod moved it); HD2Runtime leaves it '
        ..'alone, writes to %s records are refused and every other component goes ahead (owner: unknown mod, not '
        ..'HD2Runtime)'):format(name,short(name))
end
function M.is_moved(reason)
    return type(reason)=='string'and reason:find('table from another place (another mod moved it)',1,true)~=nil
end

local function note_moved(name)
    if logged[name]then return end
    logged[name]=true
    metrics.count('component_tables.moved')
    emit(('[HD2Runtime] COMPONENT TABLE MOVED: the game reads its %s table from another place, not the entity file\'s '
        ..'own table (another mod moved it, e.g. one that rebuilds laser weapons): HD2Runtime leaves it alone and '
        ..'refuses writes to %s records only; every other component and value goes ahead. owner: unknown mod')
        :format(name,short(name)))
    pcall(function()
        require('hd2runtime/core/foreign_values').note({target=name..' table',field='every field',
            observed='read from another place',expected='the entity file\'s own table',silent=true})
    end)
end

-- Exact bytes of every pin, once per loaded game.dll: true, or false and why.
local function prove(reader,image,profile)
    local key=tostring(image.base)
    if proven[key]~=nil then return proven[key],proven[key..'|why']end
    local function fail(why)proven[key]=false;proven[key..'|why']=why;return false,why end
    if D.source.gameDllSha256~=profile.dll_sha then return fail('the component table research covers another build')end
    for _,pin in ipairs(D.pins)do
        local expected=b.unhex(pin.hex)
        if reader.read(image,pin.rva,#expected)~=expected then
            return fail('the entity manager code is not as reviewed ('..pin.label..')')
        end
    end
    proven[key]=true
    return true
end
local lookup_proven={}  -- game.dll base | component -> true | reason
local function prove_lookup(reader,image,name)
    local key=tostring(image.base)..'|'..name
    if lookup_proven[key]~=nil then return lookup_proven[key]end
    local pins=D.lookups[name]
    local result=true
    if pins then
        for _,pin in ipairs(pins)do
            local expected=b.unhex(pin.hex)
            if reader.read(image,pin.rva,#expected)~=expected then
                result=('CONFLICT: the game\'s %s lookup code is not as reviewed (%s; another mod changed it); '
                    ..'HD2Runtime leaves %s records alone (owner: unknown mod, not HD2Runtime)')
                    :format(name,pin.label,short(name))
                break
            end
        end
    end
    -- A component without a reviewed lookup pin (a development profile's extra component) keeps the pointer check.
    lookup_proven[key]=result
    return result
end

-- owner: the located entity allocation; components: {[name] = profile component}. Returns {[name] = refusal reason}
-- for every component a write must not use (absent = the game reads exactly that table). Read-only; may yield.
function M.check(reader,owner,profile,components)
    metrics.count('component_tables.checks')
    local refused={}
    local function all(reason)
        for name in pairs(components)do refused[name]=reason end
        return refused
    end
    if type(reader.module)~='function'then
        return all('TARGET_UNAVAILABLE: the component table pointers cannot be read (no module access)')
    end
    local dll=reader.module('game.dll')
    if not dll then return all('TARGET_UNAVAILABLE: game.dll not loaded (component table pointers unreadable)')end
    if reader.fingerprint then
        local ok,why=pcall(reader.fingerprint)
        if not ok then return all((tostring(why):gsub('^[^%s:]+:%d+: ','')))end
    end
    reader.stage='core/component_tables:pins'
    local image={base=dll,size=D.imageExtent,type=IMAGE}
    local ok,proved,why=pcall(prove,reader,image,profile)
    if not ok then return all('TARGET_UNAVAILABLE: the entity manager code is unreadable ('..tostring(proved)..')')end
    if not proved then return all('component table pointers unproven: '..tostring(why))end
    reader.stage='core/component_tables:pointers'
    local slots,reason=nil,nil
    ok,reason=pcall(function()
        local manager=b.pointer(reader.read(image,D.global,8),0)
        assert(manager and manager~=0,'the entity manager is not initialised')
        local at=manager+D.slotBase
        local region=reader.query(at)
        assert(region.state==0x1000 and region.type==PRIVATE and region.allocation_base>0
            and region.allocation_base<=at,'the entity manager is not in private memory')
        local base=region.allocation_base
        local span={base=base,size=at-base+D.slots*8,type=PRIVATE}
        slots=reader.read(span,at-base,D.slots*8)
    end)
    if not ok or not slots then
        return all('TARGET_UNAVAILABLE: the game\'s component table pointers are unreadable ('
            ..tostring(reason):gsub('^[^%s:]+:%d+: ','')..')')
    end
    for name,c in pairs(components)do
        assert(type(c.index)=='number'and c.index>=0 and c.index<D.slots,name..' component index outside the slots')
        local pointer=b.pointer(slots,c.index*8)
        if pointer~=owner.base+c.offset+D.tableFromProfileOffset then
            refused[name]=M.moved_reason(name)
            note_moved(name)
        else
            local lookup=prove_lookup(reader,image,name)
            if lookup~=true then refused[name]=lookup end
        end
    end
    return refused
end

-- Test hook: forget proofs and logged components.
function M.reset()proven,lookup_proven,logged={},{},{}end
return M
