-- ARMOR STATS (docs/armor-stats.md; research/armor-stats-F5FEE03DCFDB.json, generated into domains/armor_stats.lua).
-- Not exported directly: hd2.armor_stats (api/armor_stats.lua) and the guarded kit write domain
-- (domains/armor_stats_writes.lua) use it.
--
-- No armor stores its own numbers. Each armor piece of a kit carries a weight (piece +0x10: 0 light, 1 medium,
-- 2 heavy) that indexes three per-weight f32[3] tables in game.dll (armor 0x21CB160, speed 0x2160678, stamina
-- 0x21C6F78):
--   * the armor value A = PassiveValue(kit passive, AFAE3B47, mean of armor[weight] over the type-0 pieces in slots
--     2..9 except the hips), read on EVERY HIT (0x12A15E0 -> hit +0x50; the avatar damage curve 0x129C940 is keyed on
--     A alone); the armory shows RATING = 100 + (A - 1) x 50;
--   * the speed and stamina factors S and F = the mean over every type-0 piece (any slot), written into the avatar
--     when a kit change is APPLIED (0x877AB0: F to avatar +0x53E900, S to locomotion speed slot 3); the armory shows
--     SPEED = 500 x S and STAMINA REGEN = 100 x (2 - F) from the first averager.
-- This module is the read side and the per-player write: the live tables, a kit's live pieces and the stats they give,
-- and the local player's two avatar members (the armor modifier +0x546AC4 + i x 0x1B8, read on every hit, and the
-- stamina factor +0x53E900 + i x 0x1238, read every frame until the next apply). The avatar slot i is the game's own
-- entity -> slot map (avatar manager +0xF8), the map its writer and readers use (pins added by this feature).
--
-- Every read re-proves the research's 166 instruction pins, the slot-map pins and the constant data the consumers
-- read, once per loaded game.dll; nothing is cached across calls but the proof. Per-player writes: DEVELOPMENT, solo
-- (NOT_SOLO otherwise), the local player's own avatar, one guarded 4-byte write per member in one transaction whose
-- contexts are the manager pointer, the slot map header and bucket, and each member; each member must hold the game's
-- own value (the armor modifier 0 or -1, the stamina factor the kit's derived F) or the value this Runtime last wrote
-- there. NOT LIVE-TESTED.
if rawget(_G,'jit')then jit.off(true,true)end
local world_module=require('hd2runtime/runtime/event_world')
local transaction=require('hd2runtime/core/guarded_transaction')
local metrics=require('hd2runtime/runtime/metrics')
local log_module=require('hd2runtime/runtime/log')
local b=require('hd2runtime/core/bytes')
local natives=require('hd2runtime/domains/event_natives')
local D=require('hd2runtime/domains/armor_stats')
local M={}
local K,BODY,PIECE,AV,CM=D.kit,D.body,D.piece,D.avatar,D.customization
M.MAX_KITS=2048
M.MAX_BODIES=8
M.MAX_PIECES=64
M.UI_ROWS,M.GAMEPLAY_ROWS=30,20     -- the averagers' own row caps (0x11D91B0, 0x8774D0 / 0x8777C0)
M.WEIGHTS=D.classes
M.SLOTS=D.slots
M.EXECUTABLE_DATA='the per-weight tables and the damage curve sit in game.dll pages that are PAGE_EXECUTE_READWRITE '
    ..'(0x40) at run time; they are written as REVIEWED EXECUTABLE DATA (the decision of the user, 2026-10-08): only '
    ..'their exact 4-byte entries, after the build, every pin and constant are proved (core/page_protection.lua)'

local function round(v)return v and math.floor(v*1e6+0.5)/1e6 end
M.round=round
local function log(text)log_module.emit('[HD2Runtime] armor stats '..text)end
local function hex32(n)return string.format('%08X',n)end
-- A row's f32, or nil when it is not finite.
local function f32(raw,o)
    if math.floor(b.u32(raw,o)/8388608)%256==255 then return nil end
    return b.value(raw,o,'f32')
end
M.f32=f32
local function same(a,c)return type(a)=='number'and type(c)=='number'and math.abs(a-c)<=math.max(1e-6,math.abs(c)*1e-6)end
M.same=same

------------------------------------------------------------------------------------------------- identities --
local kit_by_id,kit_by_name={},{}
for _,kit in ipairs(D.kits)do
    kit_by_id[kit.id]=kit
    if kit.name then
        local key=kit.name:lower()
        kit_by_name[key]=kit_by_name[key]or{}
        table.insert(kit_by_name[key],kit)
    end
end
-- An armor kit of the research by id (a number, '1F9BFA78' or '0x1F9BFA78') or by its game name (any case), or nil,
-- code, reason. A name several kits share is refused with their ids.
function M.find_kit(identity)
    if type(identity)=='number'then
        if identity%1~=0 or identity<0 or identity>=4294967296 then
            return nil,'UNKNOWN_ARMOR_KIT','armor kit ids are 32-bit: '..tostring(identity)
        end
        identity=hex32(identity)
    end
    if type(identity)~='string'then return nil,'UNKNOWN_ARMOR_KIT','name an armor kit by id or name'end
    local id=identity:upper():gsub('^0X','')
    if id:match('^%x%x%x%x%x%x%x%x$')and kit_by_id[id]then return kit_by_id[id]end
    local named=kit_by_name[identity:lower()]
    if named and#named==1 then return named[1]end
    if named then
        local ids={}
        for _,kit in ipairs(named)do ids[#ids+1]=kit.id end
        return nil,'AMBIGUOUS_ARMOR_KIT',('%d armor kits are named %s: name one by id (%s)'):format(#named,identity,
            table.concat(ids,', '))
    end
    return nil,'UNKNOWN_ARMOR_KIT',tostring(identity)..' is not an armor kit of this build (hd2.armor_stats.kits())'
end
M.kit_by_id=kit_by_id
-- A weight class index (0 light, 1 medium, 2 heavy) from its name (any case) or index, or nil.
function M.weight(value)
    if type(value)=='number'then return value%1==0 and value>=0 and value<=2 and value or nil end
    if type(value)~='string'then return nil end
    for index,name in ipairs(D.classes)do if name==value:lower()then return index-1 end end
    return nil
end
function M.weight_name(index)return D.classes[(index or-1)+1]or('weight '..tostring(index))end
-- The armor-rating rows of a passive {{type, value}} ({} when it has none).
function M.passive_armor(id)
    local p=D.passives[id]
    return p and p.armor or{},p and p.name or('passive '..tostring(id))
end

----------------------------------------------------------------------------------------------- the formulas --
-- PassiveValue (0x11DA090) for the armor key: (Set or base) + sum Add, x prod Multiply.
function M.passive_value(rows,base)
    local value,add,mul=base,0,1
    for _,row in ipairs(rows or{})do
        if row.type=='Set'then value=row.value elseif row.type=='Add'then add=add+row.value
        elseif row.type=='Multiply'then mul=mul*row.value end
    end
    return (value+add)*mul
end
-- The avatar damage curve (0x129C940): keys descending, linear between neighbours, the top value above the top key,
-- 1.0 below the lowest key.
function M.curve(points,x)
    for i,point in ipairs(points)do
        if x>=point[1]then
            if i==1 then return point[2]end
            local prior=points[i-1]
            return (math.min(prior[1],x)-point[1])/(prior[1]-point[1])*(prior[2]-point[2])+point[2]
        end
    end
    return 1.0
end
-- Replicas of the two averagers over a kit's pieces {{body, slot, type, weight}} (research/armor-stats: the census
-- equals the game's armory numbers for every kit):
--   armory 0x11D91B0: bodies of the body type or 3, the first 30 rows, type 0, slot 2..9 except 3, weight < 3; 0 when none;
--   gameplay 0x8774D0 / 0x8777C0: bodies of the body type or 3, the first 20 rows, type 0, weight ~= 3; 1.0 when none.
local function rows_of(pieces,body_type,cap)
    local rows={}
    for _,p in ipairs(pieces)do
        if(p.body==body_type or p.body==3)and#rows<cap then rows[#rows+1]=p end
    end
    return rows
end
local function average(rows,values,ui)
    local sum,n=0,0
    for _,p in ipairs(rows)do
        local counted
        if ui then counted=p.type==0 and p.slot>=2 and p.slot<=9 and p.slot~=3 and p.weight<3
        else counted=p.type==0 and p.weight~=3 end
        if counted then
            local v=values[p.weight+1]
            if v==nil then return nil end
            sum,n=sum+v,n+1
        end
    end
    if n==0 then return ui and 0 or 1.0 end
    return sum/n
end
-- The stats a kit's pieces give with the tables {armor, speed, stamina} and points (the curve): the display numbers
-- the armory shows, the factors the gameplay applies, the armor value and its damage multiplier.
function M.stats(pieces,tables,points,passive,body_type)
    local ui_rows,play_rows=rows_of(pieces,body_type,M.UI_ROWS),rows_of(pieces,body_type,M.GAMEPLAY_ROWS)
    local base=average(ui_rows,tables.armor,true)
    local speed_ui,stamina_ui=average(ui_rows,tables.speed,true),average(ui_rows,tables.stamina,true)
    local speed,stamina=average(play_rows,tables.speed,false),average(play_rows,tables.stamina,false)
    if not(base and speed_ui and stamina_ui and speed and stamina)then return nil end
    local a=M.passive_value(M.passive_armor(passive),base)
    local torso
    for _,p in ipairs(ui_rows)do if p.type==0 and p.slot==2 and p.weight<3 then torso=torso or M.weight_name(p.weight)end end
    return {rating=round(100+(a-1)*50),speed=round(500*speed_ui),stamina_regen=round(100*(2-stamina_ui)),
        armor_value=round(a),armor_base=round(base),damage_multiplier=round(M.curve(points,a)),
        speed_factor=round(speed),stamina_factor=round(stamina),display_speed_factor=round(speed_ui),
        display_stamina_factor=round(stamina_ui),class=torso}
end
-- The vanilla tables and curve (the research's).
function M.vanilla_tables()
    return {armor=D.tables.armor.values,speed=D.tables.speed.values,stamina=D.tables.stamina.values},D.curve.points
end
-- A research kit's vanilla pieces as one body-3 piece per armor slot (the census: every body agrees per slot).
function M.research_pieces(kit,weights)
    local pieces={}
    for index,slot in ipairs(D.slots)do
        local w=(weights and weights[slot])or kit.weights[slot]
        if w then pieces[#pieces+1]={body=3,slot=index-1,type=0,weight=w}end
    end
    return pieces
end

--------------------------------------------------------------------------------------------- live reading --
-- The research's pins, the slot-map pins and the consumers' constants, proven once per loaded game.dll. true, or nil
-- and the first mismatch.
function M.prove(world)
    if world.armor_stats_proven then return true end
    if D.source.gameDllSha256~=natives.source.gameDllSha256 then
        return nil,'the armor stats research covers another game.dll build'
    end
    for _,list in ipairs({D.pins,D.constants})do
        for _,pin in ipairs(list)do
            if not world.view.proves(world.game+pin.rva,pin.hex)then
                return nil,('native armor code changed (%s at game+%X)'):format(pin.label,pin.rva)
            end
        end
    end
    world.armor_stats_proven=true
    return true
end
-- The world, proven, or nil, code, reason.
function M.open()
    local world,why=world_module.open()
    if not world then return nil,'UNAVAILABLE','the game is not readable: '..tostring(why)end
    local ok,reason=M.prove(world)
    if not ok then return nil,'UNSUPPORTED_BUILD',reason end
    return world
end
-- The three live tables and the curve, read now: {armor = {..3}, speed, stamina}, points, vanilla (all four are the
-- research's bytes), or nil, reason.
function M.read_tables(world)
    local tables,vanilla={},true
    for _,name in ipairs({'armor','speed','stamina'})do
        local t=D.tables[name]
        local raw=world.view.read(world.game+t.rva,12)
        if not raw then return nil,'the '..name..' table is unreadable'end
        local values={}
        for i=0,2 do
            values[i+1]=f32(raw,i*4)
            if values[i+1]==nil then return nil,'the '..name..' table holds a non-finite value'end
            values[i+1]=round(values[i+1])
        end
        tables[name]=values
        vanilla=vanilla and b.hex(raw)==t.hex
    end
    local raw=world.view.read(world.game+D.curve.rva,40)
    if not raw then return nil,'the damage curve is unreadable'end
    local points={}
    for i=0,4 do
        local key,value=f32(raw,i*8),f32(raw,i*8+4)
        if not(key and value)then return nil,'the damage curve holds a non-finite value'end
        points[i+1]={round(key),round(value)}
    end
    return tables,points,vanilla and b.hex(raw)==D.curve.hex
end
-- The customization manager's kit table: {address, kits, count}, or nil, why.
local function kit_table(world)
    local manager=world.view.pointer(world.game+CM.globalRva)
    local head=manager and world.view.read(manager+CM.kits,16)
    if not head then return nil,'the customization manager is not created yet'end
    local kits=b.u32(head,4)<=0x7FFF and b.pointer(head,0)or 0
    local count=b.u32(head,CM.kitCount)
    if kits<65536 or count==0 or count>M.MAX_KITS then return nil,'the kit table is not the reviewed one'end
    return {address=manager,kits=kits,count=count}
end
-- One kit as the game holds it now: {id, address, passive, type, bodies = {{type, address, count}}, pieces = {{body,
-- slot, type, weight, address}}}, or nil, why. The kit is found at its research index (re-checked by id), else by a
-- scan of the table.
function M.read_kit(world,kit)
    local t,why=kit_table(world)
    if not t then return nil,why end
    local want=tonumber(kit.id,16)
    local function row_at(index)
        if index<0 or index>=t.count then return nil end
        local address=world.view.pointer(t.kits+index*8)
        local raw=address and world.view.read(address,K.read)
        if raw and b.u32(raw,K.id)==want then return address,raw end
    end
    local address,raw=row_at(kit.index)
    if not address then
        for index=0,t.count-1 do
            address,raw=row_at(index)
            if address then break end
        end
    end
    if not address then return nil,'armor kit '..kit.id..' is not in the kit table'end
    if b.u32(raw,K.type)~=0 then return nil,'kit '..kit.id..' is not an armor kit'end
    local bodies,count=b.u32(raw,K.bodies+4)<=0x7FFF and b.pointer(raw,K.bodies)or 0,b.u32(raw,K.bodyCount)
    if bodies<65536 or count==0 or count>M.MAX_BODIES or b.u32(raw,K.bodyCount+4)~=0 then
        return nil,'kit '..kit.id..' bodies are not the reviewed layout'
    end
    local body_rows=world.view.read(bodies,count*BODY.stride)
    if not body_rows then return nil,'kit '..kit.id..' bodies are unreadable'end
    local out={id=kit.id,address=address,passive=b.u32(raw,K.passive),type=0,bodies={},pieces={}}
    for i=0,count-1 do
        local o=i*BODY.stride
        local pieces,n=b.u32(body_rows,o+BODY.pieces+4)<=0x7FFF and b.pointer(body_rows,o+BODY.pieces)or 0,
            b.u32(body_rows,o+BODY.count)
        if pieces<65536 or n>M.MAX_PIECES or b.u32(body_rows,o+BODY.count+4)~=0 then
            return nil,'kit '..kit.id..' body '..i..' pieces are not the reviewed layout'
        end
        local body={type=b.u32(body_rows,o+BODY.type),address=bodies+o,pieces=pieces,count=n}
        out.bodies[#out.bodies+1]=body
        local rows=n>0 and world.view.read(pieces,n*PIECE.stride)or''
        if not rows then return nil,'kit '..kit.id..' pieces are unreadable'end
        for k=0,n-1 do
            local p=k*PIECE.stride
            out.pieces[#out.pieces+1]={body=body.type,slot=b.u32(rows,p+PIECE.slot),type=b.u32(rows,p+PIECE.type),
                weight=b.u32(rows,p+PIECE.weight),address=pieces+p}
        end
    end
    return out
end
-- The armor pieces of a kit per slot: {[slot name] = {weight (when every body agrees, else nil), weights = {...},
-- count}}.
function M.slots_of(pieces)
    local out={}
    for _,p in ipairs(pieces)do
        if p.type==0 then
            local name=D.slots[p.slot+1]or('slot_'..p.slot)
            local s=out[name]
            if not s then s={weight=p.weight,weights={},count=0};out[name]=s end
            s.count=s.count+1
            s.weights[#s.weights+1]=p.weight
            if s.weight~=p.weight then s.weight=nil end
        end
    end
    return out
end

------------------------------------------------------------------------------------------------- describe --
local function stats_pair(pieces,tables,points,passive)
    local stocky,slim=M.stats(pieces,tables,points,passive,0),M.stats(pieces,tables,points,passive,1)
    local agree=true
    for key,v in pairs(stocky or{})do if slim[key]~=v then agree=false end end
    return stocky,agree and nil or slim
end
-- A kit's derived stats: live (its pieces and the tables now) when the game is readable, else the research's vanilla
-- ones. {id, name, passive = {id, name, armor = {{type, value}}}, source = 'live' | 'research', reason (research
-- only), pieces = {[slot] = {weight, weights, count}}, stats = {rating, speed, stamina_regen, armor_value,
-- damage_multiplier, speed_factor, stamina_factor, class, ...}, slim_stats (only when body type 1 differs), vanilla
-- (the research's), tables_vanilla}.
function M.describe_kit(kit)
    local rows,pname=M.passive_armor(kit.passive)
    local out={id=kit.id,name=kit.name,passive={id=kit.passive,name=pname,armor=rows},vanilla=kit.vanilla,
        class_vanilla=kit.class}
    local world,code,why=M.open()
    local live,tables,points,vanilla
    if world then
        tables,points,vanilla=M.read_tables(world)
        if tables then live,why=M.read_kit(world,kit)else why=points end
    end
    if live then
        if live.passive~=kit.passive then
            out.passive.live=live.passive
            out.passive.armor_live,out.passive.live_name=M.passive_armor(live.passive)
        end
        out.source='live';out.tables_vanilla=vanilla
        out.pieces=M.slots_of(live.pieces)
        out.stats,out.slim_stats=stats_pair(live.pieces,tables,points,live.passive)
        return out
    end
    tables,points=M.vanilla_tables()
    out.source='research';out.reason=(code and(code..': ')or'')..tostring(why)
    out.pieces={}
    for slot,w in pairs(kit.weights)do out.pieces[slot]={weight=w,weights={w},count=1}end
    out.stats=M.stats(M.research_pieces(kit),tables,points,kit.passive,0)
    return out
end
-- What a kit's stats would be with some slots' weights changed ({[slot] = weight index}), with the tables now (or
-- the research's).
function M.preview_kit(kit,weights)
    local world=M.open()
    local tables,points
    if world then tables,points=M.read_tables(world)end
    if not tables then tables,points=M.vanilla_tables()end
    return M.stats(M.research_pieces(kit,weights),tables,points,kit.passive,0)
end
-- A weight class: {name, index, rating = {value (A), display, vanilla}, speed = {value, display, vanilla}, stamina =
-- {value, display, vanilla}, damage_multiplier (the curve at its armor value now), source, editable = true, executable_data}.
function M.describe_class(index)
    local world,code,why=M.open()
    local tables,points,vanilla
    if world then tables,points,vanilla=M.read_tables(world)if not tables then why=points end end
    local source='live'
    if not tables then tables,points=M.vanilla_tables();source='research'end
    local w=index+1
    local a,s,f=tables.armor[w],tables.speed[w],tables.stamina[w]
    return {name=D.classes[w],index=index,source=source,reason=source=='research'and((code and(code..': ')or'')
        ..tostring(why))or nil,tables_vanilla=vanilla,
        rating={value=a,display=round(50+50*a),vanilla=D.tables.armor.values[w]},
        speed={value=s,display=round(500*s),vanilla=D.tables.speed.values[w]},
        stamina={value=f,display=round(100*(2-f)),vanilla=D.tables.stamina.values[w]},
        damage_multiplier=round(M.curve(points,a)),editable=true,executable_data=M.EXECUTABLE_DATA}
end
-- The damage curve now: {points = {{armor_value, damage}}, vanilla = {...}, source, editable = true}.
function M.describe_curve()
    local world,code,why=M.open()
    local points,vanilla
    if world then
        local tables
        tables,points,vanilla=M.read_tables(world)
        if not tables then points,why=nil,points end
    end
    local source='live'
    if not points then points=D.curve.points;source='research'end
    local out={points={},vanilla={},source=source,points_vanilla=vanilla,editable=true,
        reason=source=='research'and((code and(code..': ')or'')..tostring(why))or nil,executable_data=M.EXECUTABLE_DATA}
    for i=#points,1,-1 do
        out.points[#out.points+1]={armor_value=points[i][1],damage=points[i][2]}
        out.vanilla[#out.vanilla+1]={armor_value=D.curve.points[i][1],damage=D.curve.points[i][2]}
    end
    return out
end

------------------------------------------------------------------------------------------- the local player --
local written={}         -- [avatar entity] = {slot, armor_bonus = bytes, stamina_factor = bytes}: this Runtime's last
-- A memory region's owner for a guarded transaction; writable: the target must be committed private read-write.
local function owner_of(world,address,size,writable)
    local r=world.runtime.query and world.runtime.query(address)
    if not(r and r.state==0x1000 and address>=r.base and address+size<=r.base+r.size)then return nil end
    if writable and not(r.type==0x20000 and r.protect==4)then return nil end
    return {base=r.allocation_base,size=r.base+r.size-r.allocation_base,type=r.type,protect=r.protect}
end
-- The local player's avatar members, read now: {world, entity, avatar, players, manager, slot, map_entry, armor =
-- {address, value, bytes}, stamina = {address, value, bytes}, kit (research entry), kit_live, body_type, derived =
-- {stamina_factor, armor_value, ...}}, or nil, code, reason.
function M.read_player(world)
    local players=world_module.players(world,true)
    local me
    for _,p in ipairs(players)do if p['local']then me=p end end
    if not(me and me.entity)then return nil,'NO_PLAYER','the local player is not in the player list'end
    if not me.avatar then return nil,'NO_LOCAL_AVATAR','the local player has no avatar now'end
    local manager=world.view.pointer(world.game+AV.globalRva)
    if not manager then return nil,'UNAVAILABLE','the avatar manager is not created yet'end
    local header=world.view.read(manager+AV.map,20)
    if not header then return nil,'UNAVAILABLE','the avatar slot map is unreadable'end
    local buckets,capacity,multiplier=b.u32(header,4)<=0x7FFF and b.pointer(header,0)or 0,b.u32(header,8),b.u32(header,16)
    if buckets<65536 or capacity==0 or capacity>1024 then return nil,'UNAVAILABLE','the avatar slot map is not the reviewed one'end
    local slot=world_module.hash_value(world,manager+AV.map,me.avatar)
    if slot==nil then return nil,'NO_AVATAR_SLOT','the avatar (entity '..me.avatar..') has no avatar manager slot'end
    if slot>=AV.maxSlots then return nil,'UNEXPECTED_STATE','the avatar slot map names slot '..slot end
    -- The bucket the game's own lookup reads (the same probe sequence): a transaction context.
    local start,entry=world_module.mul32(me.avatar,multiplier),nil
    for probe=0,math.min(capacity,4096)-1 do
        local at=buckets+((start+probe)%capacity)*8
        local bytes=world.view.read(at,8)
        if bytes and b.u32(bytes,0)==me.avatar then entry={address=at,bytes=bytes};break end
    end
    if not entry then return nil,'UNAVAILABLE','the avatar slot bucket is unreadable'end
    local function member(offset,stride)
        local address=manager+offset+slot*stride
        local bytes=world.view.read(address,4)
        if not bytes then return nil end
        return {address=address,bytes=bytes,value=f32(bytes,0)and round(f32(bytes,0))}
    end
    local armor,stamina=member(AV.armorModifier,AV.armorStride),member(AV.staminaFactor,AV.staminaStride)
    if not(armor and stamina)then return nil,'UNAVAILABLE','the avatar members are unreadable'end
    local out={world=world,entity=me.entity,avatar=me.avatar,players=#players,manager=manager,slot=slot,
        header=header,map_entry=entry,armor=armor,stamina=stamina}
    -- The armor kit the local player's applied record names (runtime/player_passives.lua reads that record, read-only)
    -- and the factors it derives now.
    local ok,s=pcall(function()
        local passives=require('hd2runtime/runtime/player_passives')
        if not passives.prove(world)then return nil end
        return (passives.read_local(world))
    end)
    if ok and s then
        out.body_type=b.u32(s.bytes,0)
        out.kit=kit_by_id[hex32(s.kits.armor_id)]
        local tables,points=M.read_tables(world)
        local live=out.kit and tables and M.read_kit(world,out.kit)
        if live then
            out.kit_live=live
            out.derived=M.stats(live.pieces,tables,points,live.passive,out.body_type)
            -- The F the kit's VANILLA pieces give: what the avatar holds when a kit write (hd2.armor_stats.kit) came
            -- after the last armor apply.
            local vanilla={}
            for i,p in ipairs(live.pieces)do
                local w=p.type==0 and out.kit.weights[D.slots[p.slot+1]or'']
                vanilla[i]={body=p.body,slot=p.slot,type=p.type,weight=w or p.weight}
            end
            out.vanilla_derived=M.stats(vanilla,tables,points,live.passive,out.body_type)
        end
    end
    return out
end
local function player_view(s)
    local held=written[s.avatar]
    return {entity=s.entity,avatar=s.avatar,slot=s.slot,players=s.players,armor_bonus=s.armor.value,
        stamina_factor=s.stamina.value,body_type=s.body_type,
        armor_kit=s.kit and{id=s.kit.id,name=s.kit.name,passive=s.kit.passive}or nil,
        derived=s.derived,
        effective_armor_value=s.derived and s.armor.value and round(s.armor.value~=0 and
            math.max(-1,math.min(3,s.derived.armor_value+s.armor.value))or s.derived.armor_value)or nil,
        overridden=held~=nil and(held.armor_bonus==s.armor.bytes or held.stamina_factor==s.stamina.bytes)or false}
end
-- The local player's armor members now: {entity, avatar, slot, armor_bonus, stamina_factor, armor_kit, derived =
-- {rating, speed, stamina_regen, armor_value, damage_multiplier, speed_factor, stamina_factor, ...}, effective_armor_value
-- (what a hit uses: clamp(A + bonus, -1, 3) when the bonus is not 0), overridden}, or nil, code, reason.
function M.observe_player()
    local world,code,why=M.open()
    if not world then return nil,code,why end
    local s,scode,swhy=M.read_player(world)
    if not s then return nil,scode,swhy end
    return player_view(s)
end

-- Writes want = {armor_bonus = number|nil, stamina_factor = number|nil} (nil: left as it is) on the local player's
-- avatar; restore = true puts the game's own values back (armor bonus 0, the derived stamina factor) where a member
-- still holds this Runtime's value. Returns {status = 'APPLIED' | 'UNCHANGED', writes, armor_bonus, stamina_factor,
-- verified, skipped} or nil, code, reason.
function M.write_player(want,restore)
    local world,code,why=M.open()
    if not world then return nil,code,why end
    local s,scode,swhy=M.read_player(world)
    if not s then return nil,scode,swhy end
    if s.players>1 and not restore then
        return nil,'NOT_SOLO',s.players..' players: per-player armor stats are solo only (which machine evaluates a hit '
            ..'on a remote player is not proven)'
    end
    local held=written[s.avatar]
    if held and held.slot~=s.slot then held=nil;written[s.avatar]=nil end
    local derived_f=s.derived and s.derived.stamina_factor
    local vanilla_f=s.vanilla_derived and s.vanilla_derived.stamina_factor
    local members={{name='armor_bonus',m=s.armor,label='avatar.armor_modifier',
            game=function(v)return v==0 or v==-1 end,restore_to=0},
        {name='stamina_factor',m=s.stamina,label='avatar.stamina_factor',
            game=function(v)return derived_f~=nil and same(v,derived_f)or vanilla_f~=nil and same(v,vanilla_f)end,
            restore_to=derived_f}}
    local changes,values,skipped={},{},{}
    for _,item in ipairs(members)do
        local now,bytes=item.m.value,item.m.bytes
        local ours=held and held[item.name]==bytes
        local target
        if restore then
            if ours then target=item.restore_to else skipped[#skipped+1]=item.name end
            if ours and target==nil then
                return nil,'NOT_READY','the kit\'s derived stamina factor is not readable now: nothing restored'
            end
        else
            target=want[item.name]
            if target~=nil and not ours and not(now and item.game(now))then
                return nil,'UNEXPECTED_STATE',('the %s holds %s, neither the game\'s own value (%s) nor this Runtime\'s '
                    ..'(a status effect may be active; try again later)'):format(item.name,tostring(now),
                    item.name=='armor_bonus'and'0 or -1'or('the kit\'s '..tostring(derived_f)
                        ..(vanilla_f~=derived_f and(' or its vanilla pieces\' '..tostring(vanilla_f))or'')))
            end
        end
        values[item.name]=target~=nil and target or now
        if target~=nil then
            local desired=b.encode(target,'f32')
            if desired~=bytes then
                local owner=owner_of(world,item.m.address,4,true)
                if not owner then return nil,'NOT_PRIVATE','the avatar manager is not private read-write memory'end
                changes[#changes+1]={label=item.label,owner=owner,offset=item.m.address-owner.base,expected=bytes,
                    desired=desired,before=bytes,already_desired=false,name=item.name,
                    identity={component='AvatarManager',component_type='native',record_type='avatar slot '..s.slot,
                        unique_owner=true,owner_count=1},chain={}}
            end
        end
    end
    local result={status='UNCHANGED',writes=0,armor_bonus=values.armor_bonus,stamina_factor=values.stamina_factor,
        skipped=skipped,state=s}
    if #changes==0 then return result end
    local snapshots={}
    local function context(address,size,bytes)
        local o=owner_of(world,address,size,false)
        if not o then return false end
        snapshots[#snapshots+1]={owner=o,offset=address-o.base,bytes=bytes or world.view.read(address,size)}
        return snapshots[#snapshots].bytes~=nil
    end
    local function u64(n)return b.encode(n%4294967296,'u32')..b.encode(math.floor(n/4294967296),'u32')end
    if not(context(world.game+AV.globalRva,8,u64(s.manager))and context(s.manager+AV.map,20,s.header)
            and context(s.map_entry.address,8,s.map_entry.bytes)and context(s.armor.address,4,s.armor.bytes)
            and context(s.stamina.address,4,s.stamina.bytes))then
        return nil,'UNAVAILABLE','the identity chain is not readable memory'
    end
    local report=transaction.apply(world.runtime,{snapshots=snapshots,changes=changes})
    metrics.count('armor_stats.player_transactions')
    if report.status~='APPLIED'then return nil,'GUARD_REJECTED',tostring(report.reason)end
    local mine=written[s.avatar]or{slot=s.slot}
    written[s.avatar]=mine
    local verified=true
    for _,change in ipairs(changes)do
        local after=world.view.read(change.owner.base+change.offset,4)
        verified=verified and after==change.desired
        mine[change.name]=not restore and change.desired or nil
    end
    if restore then written[s.avatar]=nil end
    result.status,result.writes,result.verified='APPLIED',report.writes,verified
    return result
end
-- What this Runtime last wrote, per avatar (tests and diagnostics).
function M.held()return written end
function M.reset_for_tests()written={}end
M.log=log
return M
