-- hd2.armor_stats: armor rating, speed and stamina (docs/armor-stats.md; runtime/armor_stats.lua,
-- domains/armor_stats_writes.lua). DEVELOPMENT line, not live-tested.
--
--   local kit = hd2.armor_stats.kit('FS-37 Ravager')          -- or an id: 0x1F9BFA78, '1F9BFA78'
--   kit:describe()                                            -- its pieces and the stats they give now
--   hd2.transaction({id = 'ravager-heavy', target = kit, allow_shared = true, allow_unverified_effect = true,
--       changes = kit:changes('heavy')})                      -- every armor piece heavy (or hd2.ensure it)
--   hd2.armor_stats.class('heavy'):describe()                 -- the per-weight tables (writable: reviewed executable data)
--   local me = hd2.armor_stats.player()
--   me:set({stamina_factor = 0.5, allow_unverified_effect = true})   -- the local player's avatar (solo)
--   me:restore()
--
-- A kit's pieces are shared by every player wearing that kit (allow_shared). The class tables and the damage curve
-- are shared by every Helldiver (allow_shared): reviewed executable data (their game.dll pages are executable; only
-- their exact entries are written, the user's decision of 2026-10-08; docs/armor-stats.md). The per-player members are the local
-- player's own avatar, solo only; a refusal never raises: {status = 'refused', code, reason}.
local A=require('hd2runtime/runtime/armor_stats')
local W=require('hd2runtime/domains/armor_stats_writes')
local D=require('hd2runtime/domains/armor_stats')
local events=require('hd2runtime/runtime/events')
local M={}

local function public(fields)
    local out={}
    for _,f in ipairs(fields)do
        out[#out+1]={semanticFieldId=f.semanticFieldId,type=f.type,unit=f.unit,currentDefault=f.currentDefault,
            editable=f.editable,readOnlyReason=f.readOnlyReason,executableData=f.executableData,min=f.min,max=f.max,allowedValues=f.allowedValues,
            slot=f.slot,armorValue=f.armorValue,lifecycle=f.lifecycle,shared=true,sharedReason=f.sharedReason,
            acknowledgements=f.editable and{'allow_shared','allow_unverified_effect'}or nil}
    end
    return out
end

----------------------------------------------------------------------------------------------------- kits --
local Kit={}
local KitMeta={__index=Kit}
-- The kit: {id, name, passive, pieces (live per slot), stats (rating, speed, stamina_regen, armor_value,
-- damage_multiplier, speed_factor, stamina_factor, class; live when the game is readable), vanilla, source, fields}.
function Kit:describe()
    local kit=A.kit_by_id[self.armor_kit]
    local out=A.describe_kit(kit)
    out.scope=W.SHARED_KIT
    out.liveTested=false
    out.acknowledgements={'allow_shared','allow_unverified_effect'}
    out.lifecycle='armor rating: the next hit (live); speed and stamina: the next armor apply (a respawn or a kit change)'
    out.fields=public(W.kit_fields(kit))
    return out
end
function Kit:fields()return public(W.kit_fields(A.kit_by_id[self.armor_kit]))end
-- The change list that puts every armor piece (or the given slots) at a weight: {{field, expect, value}} for
-- hd2.transaction / hd2.ensure. It adds no acknowledgement. weight: 'light' | 'medium' | 'heavy' | 0..2; slots: a
-- list of slot names (default: every slot the kit has).
function Kit:changes(weight,slots)
    local w=A.weight(weight)
    if w==nil then error('UNKNOWN_WEIGHT: '..tostring(weight)..' is not light, medium, heavy or 0..2',0)end
    local kit=A.kit_by_id[self.armor_kit]
    local wanted
    if slots~=nil then
        assert(type(slots)=='table','slots must be a list of slot names')
        wanted={}
        for _,slot in ipairs(slots)do
            if kit.weights[slot]==nil then
                error('UNKNOWN_SLOT: armor kit '..kit.id..' has no armor piece in slot '..tostring(slot),0)
            end
            wanted[slot]=true
        end
    end
    local out={}
    for _,f in ipairs(W.kit_fields(kit))do
        if not wanted or wanted[f.slot]then
            out[#out+1]={field=f.semanticFieldId,expect=f.currentDefault,value=A.weight_name(w)}
        end
    end
    return out
end
-- The stats the kit would give with these weights ({[slot] = weight}; the tables now, the stocky body).
function Kit:preview(weights)
    local kit=A.kit_by_id[self.armor_kit]
    local resolved={}
    for slot,value in pairs(weights or{})do
        if kit.weights[slot]==nil then error('UNKNOWN_SLOT: armor kit '..kit.id..' has no armor piece in '..tostring(slot),0)end
        local w=A.weight(value)
        if w==nil then error('UNKNOWN_WEIGHT: '..tostring(value),0)end
        resolved[slot]=w
    end
    return A.preview_kit(kit,resolved)
end
function M.kit(identity)
    local kit,code,why=A.find_kit(identity)
    if not kit then error(code..': '..why,0)end
    return setmetatable({resource='armor_kit',armor_kit=kit.id},KitMeta)
end
-- Every armor kit of the build: {id, name, passive, class, vanilla = {rating, speed, stamina, ...}}.
function M.kits()
    local out={}
    for i,kit in ipairs(D.kits)do
        local v=kit.vanilla
        out[i]={id=kit.id,name=kit.name,passive=kit.passive,passive_name=(D.passives[kit.passive]or{}).name,
            class=kit.class,vanilla={rating=v.rating,speed=v.speed,stamina=v.stamina,armor_value=v.armorValue,
                speed_factor=v.speedFactor,stamina_factor=v.staminaFactor,damage_multiplier=v.damageMultiplier}}
    end
    return out
end

------------------------------------------------------------------------------------- classes and the curve --
local Class={}
local ClassMeta={__index=Class}
function Class:describe()
    local out=A.describe_class(A.weight(self.armor_class))
    out.scope=W.SHARED_CLASS
    out.fields=public(W.class_fields(out.index))
    return out
end
function Class:fields()return public(W.class_fields(A.weight(self.armor_class)))end
function M.class(name)
    local index=type(name)=='string'and A.weight(name)
    if not index then error('UNKNOWN_ARMOR_CLASS: '..tostring(name)..' is not an armor class (light, medium, heavy)',0)end
    return setmetatable({resource='armor_class',armor_class=D.classes[index+1]},ClassMeta)
end
local Curve={}
local CurveMeta={__index=Curve}
function Curve:describe()
    local out=A.describe_curve()
    out.fields=public(W.curve_fields())
    return out
end
function Curve:fields()return public(W.curve_fields())end
function M.damage_curve()return setmetatable({resource='armor_damage_curve'},CurveMeta)end

------------------------------------------------------------------------------------------- the local player --
local Player={}
local PlayerMeta={__index=Player}
local OPTIONS={armor_bonus=true,stamina_factor=true,allow_unverified_effect=true,owner=true}
local function refuse(owner,code,reason)
    events.emit_log('armor stats ('..owner..') refused: '..code..': '..reason)
    return {status='refused',code=code,reason=reason}
end
-- The local player's members now (or nil, code, reason): {entity, avatar, slot, armor_bonus, stamina_factor,
-- armor_kit, derived, effective_armor_value, overridden}.
function Player:describe()return A.observe_player()end
-- Write the local player's armor_bonus (-1..3: added to the armor value of every hit on this avatar, the sum clamped to
-- -1..3; live) and / or stamina_factor (0.1..3: scales stamina drain and regen and the jump / dive / climb / slide
-- costs; live until the game next applies the armor). Returns {status = 'APPLIED' | 'UNCHANGED' | 'refused', code,
-- reason, armor_bonus, stamina_factor, writes, verified}.
function Player:set(spec)
    local explicit=type(spec)=='table'and spec.owner
    local owner=events.owner(type(explicit)=='string'and explicit or nil,2)
    if type(spec)~='table'then return refuse(owner,'INVALID_OPTION','spec must be a table {armor_bonus, stamina_factor}')end
    for key in pairs(spec)do
        if not OPTIONS[key]then return refuse(owner,'INVALID_OPTION','unsupported option: '..tostring(key))end
    end
    if spec.allow_unverified_effect~=true then
        return refuse(owner,'ACKNOWLEDGEMENT_REQUIRED','per-player armor stats are not live-tested: pass '
            ..'allow_unverified_effect = true')
    end
    local want={}
    for _,key in ipairs({'armor_bonus','stamina_factor'})do
        local v=spec[key]
        if v~=nil then
            local range=D.ranges[key=='armor_bonus'and'armorBonus'or'staminaFactor']
            if type(v)~='number'or v~=v or v<range[1]or v>range[2]then
                return refuse(owner,'OUT_OF_RANGE',('%s must be a number in [%g, %g]'):format(key,range[1],range[2]))
            end
            want[key]=v
        end
    end
    if want.armor_bonus==nil and want.stamina_factor==nil then
        return refuse(owner,'INVALID_OPTION','give armor_bonus and/or stamina_factor')
    end
    local result,code,why=A.write_player(want,false)
    if not result then return refuse(owner,code,why)end
    A.log(('(%s): %s: armor_bonus %s, stamina_factor %s; %d write%s%s; solo only, not live-tested'):format(owner,
        result.status,tostring(result.armor_bonus),tostring(result.stamina_factor),result.writes,
        result.writes==1 and''or's',result.status=='APPLIED'and(', read back '..tostring(result.verified))or''))
    result.state=nil
    return result
end
-- Put the game's own values back (armor bonus 0, the kit's derived stamina factor) where a member still holds this
-- Runtime's value. Returns {status = 'APPLIED' | 'UNCHANGED' | 'refused', skipped, ...}.
function Player:restore()
    local owner=events.owner(nil,2)
    local result,code,why=A.write_player({},true)
    if not result then return refuse(owner,code,why)end
    A.log(('(%s): restore %s: armor_bonus %s, stamina_factor %s; %d write%s'):format(owner,result.status,
        tostring(result.armor_bonus),tostring(result.stamina_factor),result.writes,result.writes==1 and''or's'))
    result.state=nil
    return result
end
function M.player()return setmetatable({resource='armor_player'},PlayerMeta)end
return M
