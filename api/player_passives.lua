-- hd2.passives and hd2.player_passives (docs/armor-passives.md; runtime/player_passives.lua). The write is DEVELOPMENT,
-- the local player's own record, solo only, not live-tested.
--
--   for _, p in ipairs(hd2.passives.list()) do print(p.id, p.name) end
--   local mine = hd2.player_passives()           -- {armor_kit, armor_passive, helmet_passive, effective, ...} or nil, code, reason
--   local h = hd2.player_passives.set({armor = 'SERVO-ASSISTED', second = 'SCOUT', allow_unverified_effect = true})
--   h:stop()                                      -- the kit's own passives again
--
-- A passive is named by its game name (any case) or its id. armor replaces the armor passive (record +0x3C); second
-- puts a passive in the helmet slot (+0x38, empty for every vanilla helmet): its keys the armor passive lacks are added
-- for every reader that consults both slots (flags 3); an overlapping key keeps the armor's row (no stacking). Omitted
-- or false: the kit's own value. The handle keeps the values in place: after a kit change the game re-derives the slots
-- and the Runtime writes them again; stop() puts the kit's values back. A mod's second set() replaces its first;
-- another mod's is refused (ALREADY_SET). A refusal never raises: status 'refused' with code and reason.
--
-- A passive with an effect package (17 INTEGRATED EXPLOSIVES, 19 ADRENO-DEFIBRILLATOR) is loaded first through
-- core/assets (shared with compatible peers): the handle is 'waiting_for_assets' until it is resident, then written;
-- a failed load refuses it (ASSET_UNAVAILABLE). INTEGRATED EXPLOSIVES as the SECOND passive is refused
-- (ARMOR_SLOT_ONLY): the death explosion reads the armor slot only. Every override but an armor-slot swap alone to a
-- live-proven passive (SCOUT, ENGINEERING KIT, MED-KIT, SERVO-ASSISTED) needs allow_unverified_effect = true.
--
-- The kits (research/armor-names-F5FEE03DCFDB.json; read-only, offline):
--   for _, k in ipairs(hd2.armor_kits({slot = 'armor', weight = 'heavy', passive = 'FORTIFIED'})) do print(k.name) end
--   local k = hd2.armor_kit('FS-37 Ravager')             -- or its index (0-410) or id ('0x1F9BFA78')
--   print(k.wiki and k.wiki.armor_rating)                -- the community wiki's stats (k.wiki.source == 'wiki')
local events=require('hd2runtime/runtime/events')
local passives=require('hd2runtime/runtime/player_passives')
local D=require('hd2runtime/domains/player_passives')
local M={}
local OPTIONS={armor=true,second=true,owner=true,allow_unverified_effect=true}
local UNUSED={}
for _,id in ipairs(D.unused)do UNUSED[id]=true end
-- The live-proven armor-slot swaps by name, for the refusal text ('SCOUT, ENGINEERING KIT, MED-KIT or SERVO-ASSISTED').
local function proven_names()
    local names={}
    for _,id in ipairs(D.live and D.live.armorSwap or{})do names[#names+1]=passives.name_of(id)end
    if #names<2 then return names[1]or'none'end
    return table.concat(names,', ',1,#names-1)..' or '..names[#names]
end

local function copy_list(list)
    local out={}
    for i,v in ipairs(list or{})do out[i]=v end
    return out
end
local function copy_passive(p)
    local modifiers={}
    for i,m in ipairs(p.modifiers)do
        modifiers[i]={key=m.key,key_name=m.key_name,type=m.type,value=m.value,text=m.text,reader=m.reader,
            follows=m.follows,observable=m.observable,note=m.note,armor_slot_only=m.armorSlotOnly==true}
    end
    local stats={}
    for i,s in ipairs(p.stats or{})do
        stats[i]={stat=s.stat,name=s.name,add=s.add,mul=s.mul,described_by=s.describedBy}
    end
    local info=p.packageInfo
    return {id=p.id,name=p.name,description=p.description,modifiers=modifiers,effect_package=p.package~=nil,
        package=p.package,armor_kits=p.armorKits,follows_swap=p.followsSwap,note=p.note,stats=stats,
        package_info=info and{key=info.key,catalogue=info.dependency,package=info.package,contents=info.contents,
            armor_slot_only=copy_list(info.armorSlotOnly),loads='core/assets before the write; shared with '
            ..'compatible peers (runtime/asset_sync)'}or nil}
end
-- Every passive of the game (the research's table, offline): {id, name, description, modifiers = {{key, key_name,
-- type, value, text, reader, follows, observable, note, armor_slot_only}}, effect_package, package, package_info,
-- armor_kits, follows_swap, note, stats}, by id.
function M.list()
    local out={}
    for i,p in ipairs(D.passives)do out[i]=copy_passive(p)end
    return out
end
-- One passive by name (any case) or id, or nil, code, reason.
function M.find(value)
    local p
    if type(value)=='number'then
        if value%1~=0 or value<0 or value>=D.manager.passiveIds then
            return nil,'UNKNOWN_PASSIVE','passive ids are 0 to '..(D.manager.passiveIds-1)
        end
        if UNUSED[value]then return nil,'UNKNOWN_PASSIVE','passive id '..value..' is unused by the game'end
        p=passives.by_id[value]
    elseif type(value)=='string'then
        for _,item in ipairs(D.passives)do if item.name:lower()==value:lower()then p=item end end
    end
    if not p then return nil,'UNKNOWN_PASSIVE',tostring(value)..' is not a passive (see hd2.passives.list())'end
    return copy_passive(p)
end

-- THE KITS (read-only; the research's table: no game read). A kit: {index, id, slot, weight (armor only: 'light' |
-- 'medium' | 'heavy'), passive, passive_name, set, dlc, rarity, name (nil for the 33 the game's text does not name),
-- description, wiki = {source = 'wiki', name, match, class, armor_rating, speed, stamina_regen, passive,
-- passive_agrees} | nil (the community wiki's page values where one matched: NOT read from the game)}.
local SLOT_NAMES,WEIGHT_NAMES={},{}
for _,s in ipairs(D.slots)do SLOT_NAMES[s]=true end
for _,w in ipairs(D.weights)do WEIGHT_NAMES[w]=true end
local KIT_FILTERS={slot=true,weight=true,passive=true,name=true}
local same_name={}
for _,k in ipairs(D.kits)do
    if k.name then same_name[k.name:lower()]=(same_name[k.name:lower()]or 0)+1 end
end
local function copy_kit(k)
    local w=k.wiki
    return {index=k.index,id=k.id,slot=k.slot,weight=k.weight,passive=k.passive,passive_name=passives.name_of(k.passive),
        set=k.set,dlc=k.dlc,rarity=k.rarity,name=k.name,description=k.description,
        same_name=k.name and same_name[k.name:lower()]or 0,
        wiki=w and{source='wiki',name=w.name,match=w.match,class=w.class,armor_rating=w.armorRating,speed=w.speed,
            stamina_regen=w.staminaRegen,passive=w.passive,passive_agrees=w.passiveAgrees}or nil}
end
-- Every kit matching filter {slot, weight, passive (name or id), name (the game name, any case)}, by index. A bad
-- filter raises (a programming error).
function M.armor_kits(filter)
    assert(filter==nil or type(filter)=='table','hd2.armor_kits(filter): filter must be a table or nil')
    filter=filter or{}
    for key in pairs(filter)do assert(KIT_FILTERS[key],'unsupported armor kit filter: '..tostring(key))end
    assert(filter.slot==nil or SLOT_NAMES[filter.slot],"hd2.armor_kits: slot is 'armor', 'helmet' or 'cape'")
    assert(filter.weight==nil or WEIGHT_NAMES[filter.weight],"hd2.armor_kits: weight is 'light', 'medium' or 'heavy'")
    assert(filter.name==nil or type(filter.name)=='string','hd2.armor_kits: name is a string')
    local passive
    if filter.passive~=nil then
        local p,_,reason=M.find(filter.passive)
        assert(p,'hd2.armor_kits: '..tostring(reason))
        passive=p.id
    end
    local name=filter.name and filter.name:lower()
    local out={}
    for _,k in ipairs(D.kits)do
        if(filter.slot==nil or k.slot==filter.slot)and(filter.weight==nil or k.weight==filter.weight)
                and(passive==nil or k.passive==passive)and(name==nil or(k.name and k.name:lower()==name))then
            out[#out+1]=copy_kit(k)
        end
    end
    return out
end
-- One kit by its index (0-410), its id ('0x1F9BFA78', any case, 0x optional) or its game name (any case; several kits
-- share a name, e.g. an armor and its helmet: slot picks one, else the armor first, then the lowest index; same_name
-- counts them), or nil, 'UNKNOWN_KIT', reason.
function M.armor_kit(value,slot)
    if slot~=nil and not SLOT_NAMES[slot]then return nil,'INVALID_OPTION',"slot is 'armor', 'helmet' or 'cape'"end
    local found
    if type(value)=='number'then
        found=value%1==0 and D.kits[value+1]or nil
    elseif type(value)=='string'then
        local hex=value:upper():match('^0X(%x%x%x%x%x%x%x%x)$')or value:upper():match('^(%x%x%x%x%x%x%x%x)$')
        found=hex and passives.kit_by_id['0x'..hex]
        if not found then
            local name,rank=value:lower(),{armor=1,helmet=2,cape=3}
            for _,k in ipairs(D.kits)do
                if k.name and k.name:lower()==name and(slot==nil or k.slot==slot)
                        and(not found or rank[k.slot]<rank[found.slot])then found=k end
            end
        end
    end
    if found and slot~=nil and found.slot~=slot then found=nil end
    if not found then
        return nil,'UNKNOWN_KIT',tostring(value)..' is not a kit'..(slot and(' in the '..slot..' slot')or'')
            ..' (see hd2.armor_kits())'
    end
    return copy_kit(found)
end
-- The local player's passives (read now): {entity, record, armor_kit = {id, index, name, slot, weight, passive},
-- helmet_kit, cape_kit,
-- armor_passive = {id, name}, helmet_passive = {id, name}, derived = {armor, second}, overridden, runtime (the mod
-- holding an override), effective = {{key, key_name, type, value, source, passive, name}}}, or nil, code, reason.
function M.current()return passives.observe()end

-- A handle's status, code and reason follow the held override (active, waiting, waiting_for_assets, suspended, lost,
-- replaced, refused after a failed effect package load) until stop(); a refused handle keeps its own.
local Handle={}
local LIVE={status=true,code=true,reason=true}
local Meta={__index=function(handle,key)
    local s=rawget(handle,'state')
    if s and LIVE[key]then return s[key]end
    return Handle[key]
end}
function Handle:describe()
    local s=rawget(self,'state')or rawget(self,'last')
    return {kind='player_passives',owner=self.owner,status=self.status,code=self.code,reason=self.reason,
        armor=self.armor,second=self.second,applications=s and s.applications or 0}
end
-- Stop holding: the kit's own passives go back where the slots still hold this override's values.
function Handle:stop()
    local s=rawget(self,'state')
    if not s then return self end
    rawset(self,'state',nil)
    rawset(self,'last',s)
    if s.status~='replaced'then passives.release(s)end
    rawset(self,'status','stopped')
    return self
end
local function refuse(handle,code,reason)
    handle.status,handle.code,handle.reason='refused',code,reason
    events.emit_log('passives ('..handle.owner..') refused: '..code..': '..reason)
    return handle
end
local function slot_value(handle,spec,key)
    local v=spec[key]
    if v==nil or v==false then return true,nil end
    local p,code,reason=M.find(v)
    if not p then return false,code,('%s: %s'):format(key,reason)end
    handle[key]={id=p.id,name=p.name}
    return true,p.id
end

-- Override the local player's armor passive and/or add a second passive. Returns a handle {status = 'active' |
-- 'waiting' (no record yet: applied when it appears) | 'waiting_for_assets' (an effect package loads first) |
-- 'refused', code, reason, armor, second, notes (what the swap does not carry), stop(), describe()}.
function M.set(spec)
    local explicit=type(spec)=='table'and spec.owner
    local owner=events.owner(type(explicit)=='string'and explicit or nil,2)
    local handle=setmetatable({kind='player_passives',owner=owner,status='pending'},Meta)
    if type(spec)~='table'then return refuse(handle,'INVALID_OPTION','spec must be a table {armor, second}')end
    for key in pairs(spec)do
        if not OPTIONS[key]then return refuse(handle,'INVALID_OPTION','unsupported option: '..tostring(key))end
    end
    local ok,armor,reason=slot_value(handle,spec,'armor')
    if not ok then return refuse(handle,armor,reason)end
    -- The acknowledgement: an override is not live-tested, except an armor-slot swap alone to a passive the live
    -- evidence proved (schemas/live_evidence.json, player_armor_passive_swap, D.live.armorSwap: SCOUT, ENGINEERING KIT,
    -- MED-KIT, SERVO-ASSISTED).
    local proven=false
    for _,id in ipairs(D.live and D.live.armorSwap or{})do if id==armor then proven=true end end
    if proven and spec.second~=nil and spec.second~=false then proven=false end
    if spec.allow_unverified_effect~=true and not proven then
        return refuse(handle,'ACKNOWLEDGEMENT_REQUIRED','this passive override is not yet shown in game: pass '
            ..'allow_unverified_effect = true (live-proven without it: an armor-slot swap alone to '
            ..proven_names()..')')
    end
    local ok2,second,reason2=slot_value(handle,spec,'second')
    if not ok2 then return refuse(handle,second,reason2)end
    if armor==nil and second==nil then
        return refuse(handle,'INVALID_OPTION','give armor and/or second (a passive name or id)')
    end
    if second==0 then return refuse(handle,'INVALID_OPTION','second = STANDARD ISSUE adds nothing: use false')end
    -- A passive whose effect package serves an armor-slot-only reader (17: the death explosion, 0x822140 reads flags 1)
    -- does nothing of that kind in the helmet slot: refused rather than loading a package no reader can use.
    local info=second and passives.by_id[second]and passives.by_id[second].packageInfo
    if info and#(info.armorSlotOnly or{})>0 then
        return refuse(handle,'ARMOR_SLOT_ONLY',('%s works only in the armor slot: its %s is read from the armor slot '
            ..'alone (flags 1), so a second-slot copy never triggers it; put it in the armor slot instead')
            :format(passives.name_of(second),table.concat(info.armorSlotOnly,', ')))
    end
    if second~=nil and second==armor then
        return refuse(handle,'SAME_PASSIVE','the second passive is the armor passive: its keys are already read')
    end
    if second~=nil and armor==nil then
        -- The second passive against the armor kit's own passive, as the record reads now (a later armor change is
        -- the player's: the second passive then simply adds nothing the armor has).
        local now=passives.observe()
        if now and now.derived.armor==second then
            return refuse(handle,'SAME_PASSIVE','the second passive is the armor kit\'s own passive: its keys are '
                ..'already read')
        end
    end
    local state=passives.hold({owner=owner,want={armor=armor,second=second}})
    if state.status=='refused'then return refuse(handle,state.code,state.reason)end
    handle.status=nil
    handle.state=state
    -- What a swap does not carry (research/passive-effects-F5FEE03DCFDB.json): logged once, kept on the handle.
    local notes={}
    for _,id in ipairs({armor or false,second or false})do
        local p=id and passives.by_id[id]
        if p and p.note then
            notes[#notes+1]=p.name..' ('..p.followsSwap..'): '..p.note
            events.emit_log('passives ('..owner..') note: '..notes[#notes])
        end
    end
    handle.notes=notes
    return handle
end
-- The held override, or nil: {owner, status, code, reason, armor = {id, name}|nil, second = {id, name}|nil,
-- applications}.
function M.status()
    local s=passives.held()
    if not s then return nil end
    local function view(id)return id and{id=id,name=passives.name_of(id)}or nil end
    return {owner=s.owner,status=s.status,code=s.code,reason=s.reason,armor=view(s.want.armor),
        second=view(s.want.second),applications=s.applications}
end
return M
