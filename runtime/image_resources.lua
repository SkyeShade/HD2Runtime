-- Runtime-owned custom icon resources (docs/custom-images.md): hd2.resources.image(id) and the guard that a custom icon
-- is ready before hd2.fields.stratagem.presentation_icon writes it (live-proven, CustomStratagemP0Proof 0.11.0).
--
-- A stratagem icon value N names a resource family (research/stratagem-icon-family-F5FEE03DCFDB.json): a GUI material
-- named N (required on the loadout grid's material path, which has no fallback) and the pixels, an atlas sprite N
-- (vanilla) or a texture N (custom). The SDK build ships a custom icon's texture and its GUI material (the vanilla icon
-- material with its slot naming N) in the mod's own archive, a patch of the boot package that loads at startup and
-- stays loaded (research/image-resources-F5FEE03DCFDB.json). Nothing here loads, creates, replaces or writes a resource.
--
-- M.handle(id, owner) names a mod's own image; its identity is kept privately and its name hash (MurmurHash64A, the
-- game's resource name hash) is never published. M.family reads, exactly as the game's lookups do and only after the
-- build and the lookup code (pins) are proven, whether the complete family is loaded: the texture, the material byte
-- for byte (with the loader's fix-ups and material object) and no atlas sprite of that name. A table that reads
-- inconsistently raises TARGET_UNAVAILABLE. Never guessed. M.icon_ready is the whole guard before a write.
local bit=require('bit')
local b=require('hd2runtime/core/bytes')
local profile=require('hd2runtime/schemas/current')
local D=require('hd2runtime/domains/image_resources')
local M={}
M.MAX_ID=64

------------------------------------------------------------------------------------------- the name hash --
-- MurmurHash64A (seed 0) on 32-bit halves, exactly as scripts/hd2_archive.py resource_hash (no 64-bit integers).
local TWO32,TWO16=4294967296,65536
local MH,ML=0xC6A4A793,0x5BD1E995
local function mul(ah,al,bh,bl)
    local a0,a1,a2,a3=al%TWO16,math.floor(al/TWO16),ah%TWO16,math.floor(ah/TWO16)
    local b0,b1,b2,b3=bl%TWO16,math.floor(bl/TWO16),bh%TWO16,math.floor(bh/TWO16)
    local r0=a0*b0
    local r1=a0*b1+a1*b0+math.floor(r0/TWO16)
    local r2=a0*b2+a1*b1+a2*b0+math.floor(r1/TWO16)
    local r3=a0*b3+a1*b2+a2*b1+a3*b0+math.floor(r2/TWO16)
    return(r3%TWO16)*TWO16+r2%TWO16,(r1%TWO16)*TWO16+r0%TWO16
end
local function xor(ah,al,bh,bl)return bit.bxor(ah,bh)%TWO32,bit.bxor(al,bl)%TWO32 end
local function mix(h,l)return xor(h,l,0,math.floor(h/32768))end   -- x ^ (x >> 47)
local function word(s,i,n)
    local value=0
    for k=n-1,0,-1 do value=value*256+(s:byte(i+k)or 0)end
    return value
end
-- (high, low) 32-bit halves of the resource name hash.
function M.hash(name)
    assert(type(name)=='string','resource name must be a string')
    local n=#name
    local hh,hl=mul(math.floor(n/TWO32),n%TWO32,MH,ML)
    local complete=n-n%8
    for i=1,complete,8 do
        local kh,kl=mul(word(name,i+4,4),word(name,i,4),MH,ML)
        kh,kl=mix(kh,kl)
        kh,kl=mul(kh,kl,MH,ML)
        hh,hl=xor(hh,hl,kh,kl)
        hh,hl=mul(hh,hl,MH,ML)
    end
    if complete<n then
        local tail=n-complete
        hh,hl=xor(hh,hl,tail>4 and word(name,complete+5,tail-4)or 0,word(name,complete+1,math.min(tail,4)))
        hh,hl=mul(hh,hl,MH,ML)
    end
    hh,hl=mix(hh,hl)
    hh,hl=mul(hh,hl,MH,ML)
    return mix(hh,hl)
end
local function hex(h,l)return string.format('0x%08X%08X',h,l)end
local function le(h,l)
    local out={}
    for k=0,3 do out[#out+1]=string.char(math.floor(l/256^k)%256)end
    for k=0,3 do out[#out+1]=string.char(math.floor(h/256^k)%256)end
    return table.concat(out)
end

---------------------------------------------------------------------------------------------- the handles --
local function valid_owner(owner)
    if type(owner)~='string'or#owner>128 or not owner:match('^mods/')then return false end
    local parts=0
    for part in(owner..'/'):gmatch('([^/]*)/')do
        if part==''or part:find('[^%w_]')then return false end
        parts=parts+1
    end
    return parts>=3
end
function M.valid_id(id)return type(id)=='string'and#id>=1 and#id<=M.MAX_ID and id:match('^[a-z0-9_]+$')~=nil end
-- The texture's resource name (scripts/hd2_image.py image_name).
function M.name(owner,id)return owner..'/images/'..id end

local identities=setmetatable({},{__mode='k'})   -- handle -> {owner, id, name, high, low}
local by_key={}
local Image={}
Image.__index=Image
function Image.__tostring(self)
    local identity=identities[self]
    return identity and("image '"..identity.id.."' of "..identity.owner)or'image'
end
function Image.describe(self)
    local identity=identities[self]
    return {kind='image',id=identity.id,mod=identity.owner}
end
-- Once per icon, when a mod first names it: the build record its archive carries (<mod>/hd2runtime_images, written by
-- the SDK build): the source PNG and its SHA-256, how the masks were prepared, whether the build compiled it, took it
-- from its cache or recompiled it because the source changed, and the resource it names (the texture and GUI material
-- the game loads from the mod's archive at startup; no file is read in game).
local records={}
local function log_source(owner,id,name)
    local record=records[owner]
    if record==nil then
        local ok,value=pcall(require,owner..'/hd2runtime_images')
        record=ok and type(value)=='table'and type(value.images)=='table'and value or false
        records[owner]=record
    end
    local text
    if not record then
        text=('custom image %s: no build record in this mod\'s archive (built before icon build records): the game draws '
            ..'the texture and GUI material of that name the archive holds'):format(name)
    elseif not record.images[id]then
        text=('custom image %s: NOT in this mod\'s build (no images/%s.png was compiled): the icon cannot load'):format(
            name,id)
    else
        local item=record.images[id]
        text=('custom image %s (texture and GUI material of that name, from this mod\'s archive): built from %s, sha256 '
            ..'%s, %s; build: %s'):format(tostring(item.resource or name),tostring(item.source),tostring(item.sha256),
            tostring(item.prepared),tostring(item.build))
    end
    pcall(function()require('hd2runtime/runtime/log').emit('[HD2Runtime] '..text)end)
end
-- The calling mod's image `id` (one handle per mod and id).
function M.handle(id,owner)
    assert(M.valid_id(id),'image id must be 1 to 64 lowercase letters, digits or underscores, the file name of '
        ..'images/<id>.png in the mod project: '..tostring(id))
    assert(valid_owner(owner),'hd2.resources.image must be called by a mod (from its startup or one of its '
        ..'callbacks): an image belongs to the mod that ships it')
    local key=owner..'\0'..id
    if by_key[key]then return by_key[key]end
    local name=M.name(owner,id)
    local high,low=M.hash(name)
    local handle=setmetatable({resource='image',image=id,mod=owner},Image)
    identities[handle]={owner=owner,id=id,name=name,high=high,low=low}
    by_key[key]=handle
    log_source(owner,id,name)
    return handle
end
function M.issued(value)return type(value)=='table'and identities[value]~=nil end
function M.label(handle)return tostring(handle)end
-- The 8 bytes a write stores for the image (the name hash, little-endian). Internal.
function M.bytes(handle)
    local identity=assert(identities[handle],'not an image from hd2.resources.image')
    return le(identity.high,identity.low)
end
-- The image's resource name: its texture and its GUI material both carry it. Internal (the development selector draws
-- the material by name through the engine GUI); never published.
function M.material_name(handle)return assert(identities[handle],'not an image from hd2.resources.image').name end
function M.texture_hex(handle)
    local identity=assert(identities[handle],'not an image from hd2.resources.image')
    return hex(identity.high,identity.low)
end

-------------------------------------------------------------------------------------------- the residency --
local proven={}
local function base_of(runtime,name)
    local handle=runtime.module and runtime.module(name)
    local address=handle and runtime.address and runtime.address(handle)
    if type(address)~='number'then error('TARGET_UNAVAILABLE: '..(name or'executable')..' not loaded',0)end
    return address
end
-- The resource lookup is proven once per loaded game: pins table, or nil and the reason.
function M.prove(runtime)
    if D.source.exeSha256~=profile.exe_sha then return nil,'the image research covers another game build'end
    require('hd2runtime/core/fingerprint').require(runtime)
    local exe,game=base_of(runtime,nil),base_of(runtime,'game.dll')
    local key=exe..'|'..game
    if proven[key]then return proven[key]end
    for _,pin in ipairs(D.pins)do
        local expected=b.unhex(pin.hex)
        if runtime.read((pin.module=='exe'and exe or game)+pin.rva,#expected)~=expected then
            return nil,'resource lookup changed ('..pin.label..' at '..pin.module..'+'..string.format('%X',pin.rva)..')'
        end
    end
    proven[key]={exe=exe,game=game}
    return proven[key]
end

-- Every consumer of a stratagem icon value and the material / texture paths it reaches
-- (research/stratagem-icon-consumers, research/stratagem-icon-family), proven once per loaded game before a development
-- custom icon write: true, or nil and the reason.
local consumers_proven={}
function M.prove_consumers(runtime)
    local pins,why=M.prove(runtime)
    if not pins then return nil,why end
    local key=pins.exe..'|'..pins.game
    if consumers_proven[key]then return true end
    for _,pin in ipairs(D.consumerPins)do
        local expected=b.unhex(pin.hex)
        if runtime.read((pin.module=='exe'and pins.exe or pins.game)+pin.rva,#expected)~=expected then
            return nil,'icon consumer changed ('..pin.label..' at '..pin.module..'+'..string.format('%X',pin.rva)..')'
        end
    end
    consumers_proven[key]=true
    return true
end

local function busy(what)error('TARGET_UNAVAILABLE: resource table '..what,0)end
local function reader(runtime)
    local function bytes(at,size)
        local s=type(at)=='number'and at>0 and runtime.read(at,size)
        if type(s)~='string'or#s~=size then busy('unreadable')end
        return s
    end
    local function u32(at)return b.u32(bytes(at,4),0)end
    local function ptr(at)
        local s=bytes(at,8)
        local high=b.u32(s,4)
        if high>2097151 then busy('holds an invalid pointer')end
        local value=b.u32(s,0)+high*TWO32
        if value==0 then busy('not initialised')end
        return value
    end
    return bytes,u32,ptr
end
-- In-array chained map (the game's layout): the address of the entry holding `key` (8 bytes), or nil.
local function find(read,u32,entries,buckets,capacity,stride,next_offset,high,key)
    local index=high%buckets
    if u32(entries+index*stride+next_offset)==D.markers.empty then return nil end
    for _=1,D.limits.chain do
        if index>=capacity then busy('changed while reading')end
        if read(entries+index*stride,8)==key then return entries+index*stride end
        index=u32(entries+index*stride+next_offset)
        if index==D.markers['end']then return nil end
    end
    busy('chain does not end')
end
local ZERO8=string.rep('\0',8)
local function type_key(hex)
    local high=tonumber(hex:sub(3,10),16)
    return high,le(high,tonumber(hex:sub(11,18),16))
end
local TEXTURE_HIGH,TEXTURE_KEY=type_key(D.texture.type)
local MATERIAL_HIGH,MATERIAL_KEY=type_key(D.material.type)
local function qword(s,o)
    local high=b.u32(s,o+4)
    if high>2097151 then busy('holds an invalid pointer')end
    return b.u32(s,o)+high*TWO32
end
-- The proven resource manager, or nil and why (another game build).
local function open(runtime)
    local pins,why=M.prove(runtime)
    if not pins then return nil,'custom images are unavailable on this game build: '..why end
    local read,u32,ptr=reader(runtime)
    local T,L=D.typeMap,D.limits
    local manager=ptr(ptr(pins.exe+D.manager.applicationGlobal)+D.manager.resourceManager)
    local buckets,capacity=u32(manager+T.buckets),u32(manager+T.capacity)
    if buckets==0 or buckets>L.typeBuckets or buckets>capacity or u32(manager+T.count)>capacity then
        busy('type map shape changed')
    end
    return {read=read,u32=u32,ptr=ptr,manager=manager,buckets=buckets,capacity=capacity}
end
-- A loaded resource of one type by name, read exactly as the game's lookup reads it: its address, or nil and why.
-- Raises TARGET_UNAVAILABLE when the table cannot be read consistently.
local function resource(m,type_high,type_key_bytes,label,high,low)
    local T,R,N,L=D.typeMap,D.record,D.names,D.limits
    local record=find(m.read,m.u32,m.ptr(m.manager+T.records),m.buckets,m.capacity,T.stride,T.next,type_high,
        type_key_bytes)
    if not record then busy('has no '..label..' type')end
    if m.u32(record+R.count)==0 then return nil,'no '..label..' is loaded'end
    local name_buckets,name_capacity=m.u32(record+R.buckets),m.u32(record+R.capacity)
    if name_buckets==0 or name_buckets>L.nameBuckets or name_buckets>name_capacity then busy('name map shape changed')end
    local entry=find(m.read,m.u32,m.ptr(record+R.entries),name_buckets,name_capacity,N.stride,N.next,high,le(high,low))
    if not entry then return nil,"not in the game's "..label..'s'end
    local slot=m.u32(entry+N.slot)
    if slot==D.markers.absent then return nil,'unloaded'end
    if slot>=L.slots then busy('holds an invalid slot')end
    local value=m.read(m.ptr(record+R.resources)+slot*R.resourceStride,8)
    if value==ZERO8 then return nil,'not loaded yet'end
    return qword(value,0)
end
-- true, or false and why (the texture is not loaded).
local function lookup(runtime,high,low)
    local m,why=open(runtime)
    if not m then return false,why end
    local at,reason=resource(m,TEXTURE_HIGH,TEXTURE_KEY,'texture',high,low)
    if not at then return false,reason end
    return true
end
-- A mod's image texture (a handle from M.handle).
function M.resident(runtime,handle)
    local identity=assert(identities[handle],'not an image from hd2.resources.image')
    return lookup(runtime,identity.high,identity.low)
end
-- Any texture by resource name: validation and diagnostics only.
function M.resident_name(runtime,name)return lookup(runtime,M.hash(name))end
-- A loaded texture's resource address by name hash halves, read exactly as the game's lookup reads it, or nil and why.
-- Read-only (the development native-slot texture probe reads its render handle, u32 [resource + 0]).
function M.texture_resource(runtime,high,low)
    local m,why=open(runtime)
    if not m then return nil,why end
    return resource(m,TEXTURE_HIGH,TEXTURE_KEY,'texture',high,low)
end
function M.texture_resource_of(runtime,handle)
    local identity=assert(identities[handle],'not an image from hd2.resources.image')
    return M.texture_resource(runtime,identity.high,identity.low)
end
-- Any loaded resource of a type ('0x' and 16 hex digits) by resource name, read as the game's lookup reads it: true, or
-- false and why. Read-only (the development selector checks the engine font before drawing text).
function M.loaded(runtime,type_hex,name)
    local m,why=open(runtime)
    if not m then return false,why end
    local type_high,type_bytes=type_key(type_hex)
    local high,low=M.hash(name)
    local at,reason=resource(m,type_high,type_bytes,'resource',high,low)
    if not at then return false,reason end
    return true
end

-- The GUI icon material named (high, low): loaded, and exactly the icon material for that name (D.material.template
-- with the name) as the loader leaves it: its three fix-ups point into itself and at its material object, whose magic,
-- body, shader and name match. true, or false and why.
local TEMPLATE=b.unhex(D.material.template)
local function masked(data)
    local F=D.material.fixups
    local cuts={F.object,F.slotIds,F.slotNames}
    table.sort(cuts)
    local out,at={},0
    for _,offset in ipairs(cuts)do
        out[#out+1]=data:sub(at+1,offset);out[#out+1]=ZERO8;at=offset+8
    end
    out[#out+1]=data:sub(at+1)
    return table.concat(out)
end
local function material(m,high,low)
    local MA,OB=D.material,D.material.object
    local at,why=resource(m,MATERIAL_HIGH,MATERIAL_KEY,'material',high,low)
    if not at then return false,why end
    local data=m.read(at,MA.size)
    local object=qword(data,MA.fixups.object)
    if object==0 or qword(data,MA.fixups.slotIds)~=at+MA.slotIds or qword(data,MA.fixups.slotNames)~=at+MA.slotNames then
        return false,'not a loaded icon material'
    end
    local name=le(high,low)
    local expected=TEMPLATE:sub(1,MA.nameOffset)..name..TEMPLATE:sub(MA.nameOffset+9)
    if masked(data)~=expected then return false,'not the icon material of this name'end
    local o=m.read(object,OB.size)
    if b.u32(o,0)~=OB.magic or qword(o,OB.body)~=at+MA.body or b.u32(o,OB.shader)~=MA.shader
        or o:sub(OB.name+1,OB.name+8)~=name then
        return false,'its material object differs'
    end
    return true
end
-- The atlas sprite map entry of (high, low) (the map GUI API +0x348 reads), or nil.
local function sprite_entry(m,high,low)
    local S=D.sprites
    if m.u32(m.manager+S.count)==0 then return nil end
    local buckets=m.u32(m.manager+S.buckets)
    if buckets==0 or buckets>D.limits.nameBuckets then busy('sprite map shape changed')end
    return find(m.read,m.u32,m.ptr(m.manager+S.entries),buckets,D.limits.nameBuckets,D.names.stride,D.names.next,high,
        le(high,low))
end
local function sprite(m,high,low)return sprite_entry(m,high,low)~=nil end
-- The icon family a value needs on every +0xB0 consumer path (research/stratagem-icon-family-F5FEE03DCFDB.json): a GUI
-- material of that name (required), and the pixels: an atlas sprite (vanilla) or a texture (custom). A custom icon is
-- complete when its texture is loaded, its material is exactly the icon material of its name and loaded, and no atlas
-- sprite has its name. Read-only.
local function family(runtime,high,low)
    local m,why=open(runtime)
    if not m then return {complete=false,reason=why}end
    local texture,texture_why=resource(m,TEXTURE_HIGH,TEXTURE_KEY,'texture',high,low)
    local material_ok,material_why=material(m,high,low)
    local has_sprite=sprite(m,high,low)
    local out={texture=texture and true or texture_why,material=material_ok or material_why,sprite=has_sprite}
    out.complete=texture~=nil and material_ok==true and not has_sprite
    if not out.complete then
        out.reason=material_ok~=true and('material: '..tostring(material_why))or not texture and('texture: '
            ..tostring(texture_why))or'an atlas sprite has this name'
    end
    return out
end
function M.family(runtime,handle)
    local identity=assert(identities[handle],'not an image from hd2.resources.image')
    return family(runtime,identity.high,identity.low)
end
-- Any icon value by resource name hash halves (validation: vanilla icons are material + sprite).
function M.family_of(runtime,high,low)return family(runtime,high,low)end

-- Read-only inspection of an icon value's resources, as the game resolves them (the development family probe and
-- validation; never a write): its texture, its GUI material (kind, shader, name from its material object, and its
-- slots read through the loader's own pointers), and where its image slot's texture name resolves: an atlas sprite (the
-- sprite record's atlas page texture) or a standalone texture. Names are '0x%016X' strings.
local function hex_at(s,o)return string.format('0x%08X%08X',b.u32(s,o+4),b.u32(s,o))end
local function slot_target(m,name_bytes)
    local high,low=b.u32(name_bytes,4),b.u32(name_bytes,0)
    local out={name=hex(high,low)}
    local entry=sprite_entry(m,high,low)
    out.sprite=entry~=nil
    if entry then
        local record=m.ptr(entry+D.names.slot)
        out.atlasTexture=hex_at(m.read(record+D.sprites.atlasTexture,8),0)
    end
    out.textureLoaded=resource(m,TEXTURE_HIGH,TEXTURE_KEY,'texture',high,low)~=nil
    out.resolvesTo=entry and('atlas sprite on '..out.atlasTexture)or out.textureLoaded and('standalone texture '..out.name)
        or'nothing loaded (the missing_texture fallback)'
    return out
end
function M.inspect(runtime,high,low)
    local m,why=open(runtime)
    if not m then return {available=false,reason=why}end
    local MA=D.material
    local out={available=true,name=hex(high,low)}
    local texture,texture_why=resource(m,TEXTURE_HIGH,TEXTURE_KEY,'texture',high,low)
    out.texture={loaded=texture~=nil,reason=texture_why}
    local at,material_why=resource(m,MATERIAL_HIGH,MATERIAL_KEY,'material',high,low)
    out.material={loaded=at~=nil,reason=material_why}
    out.sprite=sprite(m,high,low)
    if not at then return out end
    local data=m.read(at,MA.size)
    local exact,exact_why=material(m,high,low)
    out.material.exact=exact==true
    out.material.exactReason=exact_why
    out.material.kind=b.u32(data,MA.fields.kind)
    out.material.shader=string.format('0x%08X',b.u32(data,MA.fields.shaderId))
    local object=qword(data,MA.fixups.object)
    if object~=0 then
        local o=m.read(object,MA.object.size)
        out.material.objectName=hex_at(o,MA.object.name)
        out.material.objectShader=string.format('0x%08X',b.u32(o,MA.object.shader))
    end
    local count=b.u32(data,MA.fields.slotCount)
    if count>8 then busy('material slot count out of range')end
    local ids,names=qword(data,MA.fixups.slotIds),qword(data,MA.fixups.slotNames)
    out.material.slots={}
    for index=0,count-1 do
        local id=m.u32(ids+4*index)
        local slot=slot_target(m,m.read(names+8*index,8))
        slot.id=string.format('0x%08X',id)
        out.material.slots[#out.material.slots+1]=slot
        if id==MA.imageSlot then out.imageSlot=slot end
    end
    return out
end
function M.inspect_handle(runtime,handle)
    local identity=assert(identities[handle],'not an image from hd2.resources.image')
    return M.inspect(runtime,identity.high,identity.low)
end
-- Whether a mod's image is ready to be a stratagem's icon value: true, or nil, code and reason. Every +0xB0 consumer and
-- the material / texture paths they reach are proven (consumer pins, which include the lookup pins), and the complete
-- family is loaded as the game reads it: the texture, the GUI material exactly the icon material of its name, its image
-- slot resolving to the custom standalone texture, and no atlas sprite of that name. Codes: UNSUPPORTED_BUILD,
-- FAMILY_INCOMPLETE. Raises TARGET_UNAVAILABLE when a table reads inconsistently (a transient state).
function M.icon_ready(runtime,handle)
    assert(identities[handle],'not an image from hd2.resources.image')
    local consumers,why=M.prove_consumers(runtime)
    if not consumers then return nil,'UNSUPPORTED_BUILD',tostring(why)end
    local family=M.family(runtime,handle)
    if not family.complete then return nil,'FAMILY_INCOMPLETE',tostring(family.reason)end
    local inspected=M.inspect_handle(runtime,handle)
    local slot=inspected.imageSlot
    if not(inspected.material and inspected.material.exact and slot and slot.name==M.texture_hex(handle)
            and not slot.sprite and slot.textureLoaded)then
        return nil,'FAMILY_INCOMPLETE','the custom GUI material does not resolve to the custom texture'
    end
    return true
end
-- The atlas sprite record of an icon value, found exactly as the image setter finds it (the sprite map GUI API +0x348
-- reads): its address and its atlas page name ('0x%016X'), or nil and why. Read-only: the development slot-local loadout
-- icons read its rectangle (runtime/stratagem_slot_icons.lua).
function M.sprite_record(runtime,high,low)
    local m,why=open(runtime)
    if not m then return nil,why end
    local entry=sprite_entry(m,high,low)
    if not entry then return nil,'no atlas sprite has this name'end
    local record=m.ptr(entry+D.names.slot)
    if not record or record==0 then return nil,'the atlas sprite record is unreadable'end
    local page=m.read(record+D.sprites.atlasTexture,8)
    if not page or#page~=8 then return nil,'the atlas sprite record is unreadable'end
    return record,hex_at(page,0)
end
-- An atlas sprite in full (hd2.resources.game_icon; docs/game-icons.md): the record the sprite map entry points at, as
-- the game's image setter reads it (research slotIconAtlas, 0x343A66): +0 its name, +8 its atlas page texture, +0x10 its
-- size in pixels (u32 width, height), +0x18 its rectangle on the page (f32 u, v, width, height; 0..1). Validated: the
-- record names the sprite, the size is 1..4096 and the rectangle lies on the page and matches the size on a whole
-- number of page pixels. Returns {page = '%016X', page_high, page_low, w, h, u, v, du, dv}, or nil and why. Read-only.
local function f32(s,o)
    local ok,v=pcall(b.value,s,o,'f32')
    return ok and v or nil
end
function M.atlas_sprite(runtime,high,low)
    local m,why=open(runtime)
    if not m then return nil,why end
    local entry=sprite_entry(m,high,low)
    if not entry then return nil,'no atlas sprite has this name (not loaded)'end
    local record=m.ptr(entry+D.names.slot)
    local raw=m.read(record,40)
    if raw:sub(1,8)~=le(high,low)then return nil,'the atlas sprite record names another sprite'end
    local w,h=b.u32(raw,16),b.u32(raw,20)
    local u,v,du,dv=f32(raw,24),f32(raw,28),f32(raw,32),f32(raw,36)
    if not(w>=1 and w<=4096 and h>=1 and h<=4096)then return nil,'the atlas sprite size is out of range'end
    for _,x in ipairs({u,v,du,dv})do
        if not(x and x==x and x>=0 and x<=1)then return nil,'the atlas sprite rectangle is out of range'end
    end
    if du<=0 or dv<=0 or u+du>1+1e-6 or v+dv>1+1e-6 then return nil,'the atlas sprite rectangle is off its page'end
    -- the page in pixels from the size and the rectangle: a whole number (the sprite is a pixel rectangle of its page)
    local pw,ph=w/du,h/dv
    if math.abs(pw-math.floor(pw+0.5))>0.01 or math.abs(ph-math.floor(ph+0.5))>0.01 then
        return nil,'the atlas sprite is not a whole-pixel rectangle of its page'
    end
    local page_low,page_high=b.u32(raw,8),b.u32(raw,12)
    return {page=string.format('%08X%08X',page_high,page_low),page_high=page_high,page_low=page_low,w=w,h=h,u=u,v=v,
        du=du,dv=dv,page_w=math.floor(pw+0.5),page_h=math.floor(ph+0.5)}
end
-- Whether a texture is loaded, by name hash halves: true, or false and why. Read-only.
function M.texture_loaded(runtime,high,low)return lookup(runtime,high,low)end
-- Whether the GUI icon material named (high, low) is loaded and exactly the icon material of that name (the vanilla
-- stratagem icon materials are; research image-resources): true, or false and why. Read-only.
function M.icon_material(runtime,high,low)
    local m,why=open(runtime)
    if not m then return false,why end
    return material(m,high,low)
end
-- Whether any material named (high, low) is loaded: true, or false and why. Read-only.
function M.material_present(runtime,high,low)
    local m,why=open(runtime)
    if not m then return false,why end
    local at,reason=resource(m,MATERIAL_HIGH,MATERIAL_KEY,'material',high,low)
    if not at then return false,reason end
    return true
end
-- The game's UI image shader (template 0xBA25DE35, the most used GUI material shader: 664 materials aboard the ship,
-- 259 loaded in every retained snapshot): the diffuse_map slot and the UI variables, no mask layers. It draws a
-- texture's own colours with its alpha (GameIconProbe 0.2.0, live: the Vitality Enhancement booster's hexagon exactly,
-- where the stratagem icon shader drew its whole square). docs/game-icons.md.
M.UI_IMAGE_SHADER=0xBA25DE35
-- A loaded material's shape (the material layout the icon material check reads: +4 the kind, +0x20 its object, +0x30
-- its slot ids, body +0x28 the slot count; the object's shader at +0x30): kind, shader, slots, or nil.
local function material_shape(m,at)
    local MA=D.material
    local head=m.read(at,64)
    local object,ids=qword(head,MA.fixups.object),qword(head,MA.fixups.slotIds)
    if object==0 or ids==0 then return nil end
    local count=m.u32(at+MA.body+0x28)
    if count<1 or count>16 then return nil end
    local slots={}
    local raw=m.read(ids,4*count)
    for i=0,count-1 do slots[#slots+1]=b.u32(raw,i*4)end
    return {kind=b.u32(head,4),shader=m.u32(object+MA.object.shader),slots=slots}
end
local function is_ui_image(shape)
    return shape~=nil and shape.kind~=0 and shape.shader==M.UI_IMAGE_SHADER and#shape.slots==1
        and shape.slots[1]==D.material.imageSlot
end
-- Whether the material named (high, low) is loaded and a UI image material (one diffuse_map slot, not a material
-- set): true, or false and why. Read-only.
function M.ui_image_material(runtime,high,low)
    local m,why=open(runtime)
    if not m then return false,why end
    local at,reason=resource(m,MATERIAL_HIGH,MATERIAL_KEY,'material',high,low)
    if not at then return false,reason end
    if not is_ui_image(material_shape(m,at))then return false,'not a UI image material'end
    return true
end
-- Up to `limit` loaded UI image materials, by name ('%016X', sorted, so choices are stable), found by reading the
-- game's material table as its lookups do. Read-only; the game decides which are loaded, none is named here.
function M.ui_image_materials(runtime,limit)
    local m,why=open(runtime)
    if not m then return nil,why end
    local T,R,N,L,K=D.typeMap,D.record,D.names,D.limits,D.markers
    local record=find(m.read,m.u32,m.ptr(m.manager+T.records),m.buckets,m.capacity,T.stride,T.next,MATERIAL_HIGH,
        MATERIAL_KEY)
    if not record then return nil,'no material type'end
    local capacity=m.u32(record+R.capacity)
    if capacity==0 or capacity>L.nameBuckets then busy('material name map shape changed')end
    local entries,resources=m.ptr(record+R.entries),m.ptr(record+R.resources)
    local raw=m.read(entries,capacity*N.stride)
    local found={}
    for i=0,capacity-1 do
        local o=i*N.stride
        local slot,nxt=b.u32(raw,o+N.slot),b.u32(raw,o+N.next)
        if nxt~=K.empty and slot~=K.absent and slot<L.slots then
            local value=m.read(resources+slot*R.resourceStride,8)
            if value~=ZERO8 then
                local ok,shape=pcall(material_shape,m,qword(value,0))
                if ok and is_ui_image(shape)then
                    found[#found+1]=string.format('%08X%08X',b.u32(raw,o+4),b.u32(raw,o))
                end
            end
        end
    end
    table.sort(found)
    local out={}
    for i=1,math.min(#found,limit or 8)do out[i]=found[i]end
    return out
end
function M.reset_for_tests()proven={};consumers_proven={};records={}end
return M
