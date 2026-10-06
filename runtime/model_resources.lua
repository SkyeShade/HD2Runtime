-- Runtime-owned custom MODELS (docs/custom-models.md): hd2.resources.model(id) and the guard that a mod's model is
-- loaded and is exactly what the build derived before runtime/weapon_clone.lua names its unit anywhere.
--
-- The SDK build derives a model from its base weapon's unit in the installed game (sdk/tools/hd2_model.py): three
-- resources under the mod's own names, <mod>/models/<id> (the unit), <mod>/models/<id>/m_weapon (its body material)
-- and <mod>/models/<id>/lut (its material LUT), shipped as a patch of the base weapon's own package archive, so they
-- load with that package beside every vanilla resource they reference. Its build record (<mod>/hd2runtime_models, a Lua
-- resource of the mod) names the base, the game build it was derived on, the base unit and its SHA-256, the names and
-- the digests. Nothing here loads, creates, replaces or writes a resource.
--
-- M.ready is the whole guard before a write: the record exists and names this model; it was derived from the base the
-- caller converts, on this game build, from the reviewed base unit (domains/weapon_variants.lua); and the unit, the
-- material and the LUT are all loaded in the game's resource table (read exactly as the game's lookup reads it,
-- runtime/image_resources.lua). Never guessed: any doubt refuses.
local images=require('hd2runtime/runtime/image_resources')
local V=require('hd2runtime/domains/weapon_variants')
local M={}
M.MAX_ID=64
M.RECORD='hd2runtime_models'

local function valid_owner(owner)
    return type(owner)=='string'and owner:match('^mods/[%w_]+/[%w_/]+$')~=nil and owner~='mods/skyeshade/hd2runtime'
end
function M.valid_id(id)return type(id)=='string'and#id>=1 and#id<=M.MAX_ID and id:match('^[a-z0-9_]+$')~=nil end
function M.names(owner,id)
    local base=owner..'/models/'..id
    return {unit=base,material=base..'/m_weapon',lut=base..'/lut'}
end

local identities=setmetatable({},{__mode='k'})   -- handle -> {owner, id, names, high, low}
local by_key={}
local records={}
local Model={}
Model.__index=Model
function Model.__tostring(self)
    local identity=identities[self]
    return identity and("model '"..identity.id.."' of "..identity.owner)or'model'
end
function Model.describe(self)
    local identity=identities[self]
    return {kind='model',id=identity.id,mod=identity.owner}
end

-- The mod's build record (its archive's <mod>/hd2runtime_models), or false.
local function record_of(owner)
    local r=records[owner]
    if r==nil then
        local ok,value=pcall(require,owner..'/'..M.RECORD)
        r=ok and type(value)=='table'and value.format==1 and type(value.models)=='table'and value or false
        records[owner]=r
    end
    return r
end
local function log(text)pcall(function()require('hd2runtime/runtime/log').emit('[HD2Runtime] '..text)end)end

-- The calling mod's model `id` (one handle per mod and id).
function M.handle(id,owner)
    assert(M.valid_id(id),'model id must be 1 to 64 lowercase letters, digits or underscores, the file name of '
        ..'models/<id>.json in the mod project: '..tostring(id))
    assert(valid_owner(owner),'hd2.resources.model must be called by a mod (from its startup or one of its callbacks): '
        ..'a model belongs to the mod that ships it')
    local key=owner..'\0'..id
    if by_key[key]then return by_key[key]end
    local names=M.names(owner,id)
    local high,low=images.hash(names.unit)
    local handle=setmetatable({resource='model',model=id,mod=owner},Model)
    identities[handle]={owner=owner,id=id,names=names,high=high,low=low}
    by_key[key]=handle
    local r=record_of(owner)
    local entry=r and r.models[id]
    if not r then
        log(('custom model %s: NO build record in this mod\'s archive (no models/%s.json was derived): it cannot load')
            :format(names.unit,id))
    elseif not entry then
        log(('custom model %s: NOT in this mod\'s build (no models/%s.json was derived): it cannot load'):format(names.unit,
            id))
    else
        log(('custom model %s (unit, body material and LUT of that name, a patch of the %s package archive %s): derived '
            ..'from the %s unit %s on game build %s, palette %s; sha256 unit %s'):format(names.unit,tostring(entry.base),
            tostring(entry.archive),tostring(entry.base),tostring(entry.baseUnit),tostring(entry.build),
            tostring(entry.palette),tostring(entry.sha256 and entry.sha256.unit)))
    end
    return handle
end
function M.issued(value)return type(value)=='table'and identities[value]~=nil end
function M.label(handle)return tostring(handle)end
function M.identity(handle)return identities[handle]end
-- The build record entry of a model, or nil and why.
function M.record(handle)
    local identity=assert(identities[handle],'not a model from hd2.resources.model')
    local r=record_of(identity.owner)
    if not r then return nil,'NO_BUILD_RECORD','the mod\'s archive has no model build record'end
    local entry=r.models[identity.id]
    if not entry then return nil,'NOT_BUILT','models/'..identity.id..'.json was not derived by the build'end
    return entry
end
-- The unit's name hash as UnitPath bytes (8, little-endian).
function M.unit_bytes(handle)
    local identity=assert(identities[handle],'not a model from hd2.resources.model')
    local function le32(v)
        return string.char(v%256,math.floor(v/256)%256,math.floor(v/65536)%256,math.floor(v/16777216)%256)
    end
    return le32(identity.low)..le32(identity.high)
end
function M.unit_hex(handle)
    local identity=assert(identities[handle],'not a model from hd2.resources.model')
    return string.format('0x%08X%08X',identity.high,identity.low)
end

-- Whether the model can be named now as `base`'s unit (a variant host's catalogue name): true, or nil, code, reason.
-- Read-only, within this call.
function M.ready(runtime,handle,base)
    local identity=identities[handle]
    if not identity then return nil,'INVALID','not a model from hd2.resources.model'end
    local entry,code,reason=M.record(handle)
    if not entry then return nil,code,reason end
    local host,facts=V.hosts[base],V.models[base]
    if not(host and facts)then return nil,'UNREVIEWED',tostring(base)..' is not a reviewed model base'end
    if entry.base~=base then
        return nil,'WRONG_BASE',('the model was derived from the %s, not the %s'):format(tostring(entry.base),base)
    end
    if entry.build~=V.source.build then
        return nil,'OTHER_BUILD',('the model was derived on game build %s; this Runtime reviewed %s'):format(
            tostring(entry.build),V.source.build)
    end
    if entry.baseUnit~=host.model.unit or entry.baseUnitSha256~=facts.unit.mainSha256 then
        return nil,'BASE_CHANGED','the model was derived from another '..base..' unit than the reviewed one'
    end
    for _,role in ipairs({'unit','material','lut'})do
        if entry[role]~=identity.names[role]then
            return nil,'NAME_MISMATCH','the build record names another '..role..' ('..tostring(entry[role])..')'
        end
    end
    local kinds={unit=V.types.unit,material=V.types.material,lut=V.types.texture}
    for _,role in ipairs({'unit','material','lut'})do
        local ok,loaded,why=pcall(images.loaded,runtime,kinds[role],identity.names[role])
        if not ok then return nil,'UNAVAILABLE','the resource table is unreadable: '..tostring(loaded)end
        if not loaded then
            return nil,'NOT_RESIDENT',('its %s %s is not loaded (%s): the %s package must be resident and the mod\'s '
                ..'%s.patch installed'):format(role,identity.names[role],tostring(why),base,tostring(entry.archive))
        end
    end
    return true
end
function M.reset_for_tests()records={}end
return M
