-- Cross-catalogue native record identity, and which HD2Runtime operation applied which bytes.
-- (research/docs/support-sentry-conflict-F5FEE03DCFDB.md)
--
-- Each authoring catalogue (player, support and mounted weapons, stratagems, backpacks and vehicles, throwables,
-- enemies, boosters, attack outputs) lists the consumers of a shared settings row or component record only within
-- itself. The same native bytes can still be writable through targets of different catalogues: the ARC-3 Arc
-- Thrower's stun status row is the A/ARC-3 Tesla Tower's, and the FLAM-66 Torcher's DamageInfo row is the AX/FLAM-75
-- Hot Dog drone gun's. Two mods editing such bytes through different handles collide, and the guarded write fails
-- the later one closed (CONFLICT), by design.
--
-- This module answers, from the generated catalogues only (no memory access, no address), which other catalogued
-- targets write the same bytes, and remembers which patch, transaction, plan or ensure last applied which bytes, so
-- a CONFLICT can say what holds them. It never decides whether a write may happen: the guards are unchanged.
local M={}

-- Native record identity of a field backing: the settings table row, the entity component record, or the
-- StratagemInfo definition. nil when the catalogue gives no global identity (entity deltas, booster tables).
local SETTINGS={ArcSettings='arc',BeamSettings='beam',DamageInfo='damage',StatusEffectSettings='status',
    ProjectileSettings='projectile',ExplosionSettings='explosion'}
function M.key(backing)
    if type(backing)~='table'then return nil end
    local row=backing.row
    if backing.kind=='settings'and type(backing.settings)=='string'and row~=nil then
        local kind=backing.settings=='explosion_damage'and'damage'or backing.settings
        return 'settings/'..kind..'/'..tostring(row)
    end
    if SETTINGS[backing.kind]and row~=nil then return 'settings/'..SETTINGS[backing.kind]..'/'..tostring(row)end
    if backing.kind~='entity_delta'and type(backing.component)=='string'and backing.recordIndex~=nil then
        return 'component/'..backing.component..'/'..tostring(backing.recordIndex)
    end
    if backing.kind=='StratagemDefinition'and backing.nativeIdentity~=nil then
        return 'stratagem/'..tostring(backing.nativeIdentity)
    end
    return nil
end
local function span(backing)
    local offset,width=tonumber(backing.offset),tonumber(backing.width)or 4
    if not offset then return nil end
    return offset,width
end

-- Whether a field descriptor needs allow_shared under its own catalogue's rule.
local function marked_shared(field)
    return field.affectsMultipleWeapons==true or field.shared==true or field.allowSharedRequired==true
end
-- Catalogues and the public resource name of their targets. Fields are the tables with a backing and a field id
-- below each entry; a booster's status damage fields take their DamageInfo row from their target. An attack
-- output's slot and presentation fields belong to the weapon that fires the output (its owner): they are another
-- handle on that weapon's own row, not another consumer. Enemy fields are completed by their write domain's
-- descriptor (the shared schema and the class's health record).
local CATALOGUES={
    {module='hd2runtime/domains/player_weapon_authoring',root='weapons',resource='player_weapon'},
    {module='hd2runtime/domains/support_weapon_authoring',root='weapons',resource='support_weapon'},
    {module='hd2runtime/domains/vehicle_weapon_authoring',root='weapons',resource='vehicle_weapon'},
    {module='hd2runtime/domains/stratagem_authoring',root='stratagems',resource='stratagem'},
    {module='hd2runtime/domains/entity_authoring',root='backpacks',resource='backpack'},
    {module='hd2runtime/domains/entity_authoring',root='vehicles',resource='vehicle'},
    {module='hd2runtime/domains/throwable_authoring',root='throwables',resource='throwable'},
    {module='hd2runtime/domains/enemy_authoring',root='enemies',resource='enemy',enemy=true},
    {module='hd2runtime/domains/booster_authoring',root='boosters',resource='booster'},
    {module='hd2runtime/domains/attack_outputs',root='outputs',resource='attack_output',output=true},
}
local MAX_DEPTH=5
local index,by_descriptor

local function add(entry)
    local list=index[entry.key]
    if not list then list={};index[entry.key]=list end
    list[#list+1]=entry
end
local function record(resource,owner,id,field,backing,shared,via)
    if field.editable==false or field.writable==false or field.readOnly==true then return end
    local key=M.key(backing)
    local offset,width=span(backing)
    if key and offset then
        local entry={key=key,offset=offset,width=width,resource=resource,target=owner,field=id,
            descriptor=field,shared=shared,via=via}
        add(entry);by_descriptor[field]=entry
    end
end
local function walk(resource,owner,value,depth,row_context,via)
    if type(value)~='table'or depth>MAX_DEPTH then return end
    if type(value.damageRow)=='number'then row_context=value.damageRow end
    local id=value.semanticFieldId
    if type(id)=='string'and type(value.backing)=='table'then
        local backing=value.backing
        if backing.kind=='status_damage'and row_context and backing.row==nil then
            backing={kind='settings',settings='damage',row=row_context,offset=backing.offset,width=backing.width}
        end
        record(resource,owner,id,value,backing,marked_shared(value),via)
        return
    end
    for _,child in pairs(value)do walk(resource,owner,child,depth+1,row_context,via)end
end
local function sorted_names(root)
    local names={};for name in pairs(root)do names[#names+1]=name end
    table.sort(names,function(a,c)return tostring(a)<tostring(c)end)
    return names
end
local function build()
    if index then return index end
    index,by_descriptor={},setmetatable({},{__mode='k'})
    for _,catalogue in ipairs(CATALOGUES)do
        local ok,data=pcall(require,catalogue.module)
        local root=ok and type(data)=='table'and data[catalogue.root]
        if type(root)=='table'then
            for _,name in ipairs(sorted_names(root))do
                local entry=root[name]
                if type(entry)=='table'then
                    if catalogue.enemy then
                        local writes_ok,writes=pcall(require,'hd2runtime/domains/enemy_writes')
                        for _,field in ipairs(writes_ok and entry.fields or{})do
                            local made,descriptor=pcall(writes.descriptor,entry,field)
                            if made then
                                record('enemy',entry.name or tostring(name),field.id,descriptor,descriptor.backing,
                                    marked_shared(descriptor))
                                by_descriptor[field]=by_descriptor[descriptor]
                            end
                        end
                    elseif catalogue.output then
                        local owner=type(entry.owner)=='table'and entry.owner or{}
                        local resource=type(owner.kind)=='string'and owner.kind or'attack_output'
                        local target=type(owner.name)=='string'and owner.name or tostring(name)
                        for _,group in ipairs({entry.slotFields,entry.presentationFields})do
                            walk(resource,target,group,1,nil,'output '..tostring(entry.id or name))
                        end
                    else
                        local owner=type(entry.name)=='string'and entry.name or tostring(name)
                        walk(catalogue.resource,owner,entry,1,nil)
                    end
                end
            end
        end
    end
    return index
end
-- Test hook: rebuild from the catalogues on next use (the claims are kept).
function M.reset_index()index,by_descriptor=nil,nil end

local function overlaps(a,offset,width)return a.offset<offset+width and offset<a.offset+a.width end
local function label(entry)
    return entry.resource..' '..entry.target..' '..(entry.via and(entry.via..' ')or'')..entry.field
end
-- The (resource, target) a runtime descriptor belongs to when it is not a catalogue table itself (enemy writes
-- build their descriptor per request): from its target identity.
local NAME_KEYS={'weapon','stratagem','backpack','vehicle','throwable','enemy','booster','explosion','helldiver'}
local function own_identity(descriptor)
    local entry=by_descriptor[descriptor]
    if entry then return entry.resource,entry.target end
    local target=type(descriptor.target)=='table'and descriptor.target
    if not target then return nil end
    for _,name in ipairs(NAME_KEYS)do
        if type(target[name])=='string'then return target.resource,target[name]end
    end
    return nil
end
-- Native record identity and byte span of a field descriptor: its catalogue entry's (which completes a booster's
-- status damage row), else its own backing.
local function locate(descriptor)
    if type(descriptor)~='table'then return nil end
    build()
    local entry=by_descriptor[descriptor]
    if entry then return entry.key,entry.offset,entry.width end
    local backing=descriptor.backing
    local key=M.key(backing)
    if not key then return nil end
    local offset,width=span(backing)
    if not offset then return nil end
    return key,offset,width
end

-- The catalogue entry of a field descriptor (the field table a validated change carries), or nil.
function M.entry(descriptor)
    build()
    return type(descriptor)=='table'and by_descriptor[descriptor]or nil
end
-- The other targets that use the same native record as this field (a settings row or component record changes for
-- every entity that uses it, whichever field a catalogue exposes): distinct (resource, target) pairs other than the
-- field's own. `fields` lists the fields through which they write these exact bytes (empty: they use the record but
-- expose no field over these bytes). Sorted for stable messages.
function M.others(descriptor)
    local key,offset,width=locate(descriptor)
    if not key then return {}end
    local own_resource,own_target=own_identity(descriptor)
    local groups,order={},{}
    for _,entry in ipairs(index[key]or{})do
        if entry.descriptor~=descriptor and not(entry.resource==own_resource and entry.target==own_target)then
            local name=entry.resource..' '..entry.target
            local group=groups[name]
            if not group then
                group={resource=entry.resource,target=entry.target,fields={},shared=entry.shared}
                groups[name]=group;order[#order+1]=name
            end
            if overlaps(entry,offset,width)then
                local text=(entry.via and(entry.via..' ')or'')..entry.field
                local seen=false
                for _,field in ipairs(group.fields)do if field==text then seen=true end end
                if not seen then group.fields[#group.fields+1]=text end
            end
            group.shared=group.shared and entry.shared
        end
    end
    table.sort(order)
    local result={}
    for index_,name in ipairs(order)do result[index_]=groups[name]end
    return result
end
-- "resource target field" of a descriptor, from the index (nil when unknown).
function M.describe(descriptor)
    local entry=M.entry(descriptor)
    if entry then return label(entry)end
    if type(descriptor)~='table'then return nil end
    local resource,target=own_identity(descriptor)
    return resource and(resource..' '..target..' '..tostring(descriptor.semanticFieldId))or nil
end
-- One readable list of other targets, at most `limit` named.
function M.others_text(others,limit)
    limit=limit or 6
    local parts={}
    for index_,group in ipairs(others)do
        if index_>limit then parts[#parts+1]='and '..(#others-limit)..' more';break end
        parts[#parts+1]=group.resource..' '..group.target..' '..(#group.fields>0 and table.concat(group.fields,'/')
            or'(same native record)')
    end
    return table.concat(parts,', ')
end
-- Fields whose own catalogue marks them unshared although another catalogued target writes the same bytes.
function M.unlisted_sharing()
    build()
    local result={}
    for _,list in pairs(index)do
        for _,entry in ipairs(list)do
            if not entry.shared then
                local others=M.others(entry.descriptor)
                if #others>0 then result[#result+1]={entry=entry,others=others}end
            end
        end
    end
    table.sort(result,function(a,c)return label(a.entry)<label(c.entry)end)
    return result
end

-- The mod registering an operation now (hd2.events owner: the mod scope the SDK wrapper runs a mod's startup in, or
-- the mod whose callback is running), or 'unknown'.
-- Then, when that is 'unknown' (a mod built without the SDK wrapper's run_as scope, for example by the template's
-- build.ps1 or an older ModBuilder export): the registering operation's origin, which api/hd2.lua keeps current for
-- every validation (core/sdk_compatibility.lua; the same mod hd2.diagnostics.operations() names), and last the
-- nearest mods/... chunk on the call stack. Live 2026-10-07 (HD2Runtime Editor): every claim of 15 installed mods read 'unknown'.
local RUNTIME_CHUNK='mods/skyeshade/hd2runtime'
function M.current_mod()
    local ok,owner=pcall(function()return require('hd2runtime/runtime/events').owner()end)
    if ok and type(owner)=='string'and owner~='unknown'then return owner end
    local found,origin=pcall(function()return require('hd2runtime/core/sdk_compatibility').current()end)
    if found and type(origin)=='table'and type(origin.mod)=='string'and origin.mod~='unknown'then return origin.mod end
    if type(debug)=='table'and type(debug.getinfo)=='function'then
        for level=2,48 do
            local info=debug.getinfo(level,'S')
            if not info then break end
            local source=tostring(info.source or''):gsub('^[@=]',''):gsub('%.lua$','')
            if source:match('^mods/[%w_/]+$')and source~=RUNTIME_CHUNK and source:sub(1,#RUNTIME_CHUNK+1)~=RUNTIME_CHUNK..'/'then
                return source
            end
        end
    end
    return 'unknown'
end

---------------------------------------------------------------------------------------------------------- claims --
-- Which operation last applied which bytes, by native record identity and offset (never by address). Kept for the
-- session: an operation that is cancelled leaves its bytes written, so its claim stays true until the bytes change.
local claims={}
local function claim_key(key,offset)return key..'@'..tostring(offset)end
local function each_change(spec,fn)
    if type(spec)~='table'then return end
    if type(spec.operations)=='table'then
        for _,operation in ipairs(spec.operations)do
            for _,change in ipairs(operation.spec and operation.spec.changes or{})do
                fn(change,spec.id..'/'..tostring(operation.id))
            end
        end
        return
    end
    for _,change in ipairs(spec.changes or{})do fn(change,spec.id)end
end
local function value_text(value)
    if type(value)~='table'then return tostring(value)end
    if value.output then return tostring(value.output)end
    if value.weapon then return tostring(value.weapon)..(value.attack and':'..tostring(value.attack)or'')end
    local parts={}
    for index_,item in ipairs(value)do parts[index_]=tostring(item)end
    return '{'..table.concat(parts,', ')..'}'
end
-- Record that a validated spec (patch, transaction or plan) applied or found its values (APPLIED/ALREADY_DESIRED).
-- An ensure's operation is named as the ensure.
function M.claim(spec,kind,mod)
    if type(spec)=='table'and spec.ensured then kind='ensure'end
    each_change(spec,function(change,id)
        local descriptor=change.descriptor
        local key,offset=locate(descriptor)
        if key then
            local slot=claim_key(key,offset)
            local list=claims[slot]or{}
            local item={mod=mod or'unknown',kind=kind,id=id,field=change.field,value=change.value,
                target=M.describe(descriptor),desired=type(change.desired)=='string'and change.desired or nil}
            for index_=#list,1,-1 do
                if list[index_].mod==item.mod and list[index_].id==item.id then table.remove(list,index_)end
            end
            list[#list+1]=item
            while #list>8 do table.remove(list,1)end
            claims[slot]=list
        end
    end)
end
-- The operations that applied these bytes, newest first. `current` (the observed bytes) marks which still hold.
function M.holders(descriptor,current)
    local key,offset=locate(descriptor)
    if not key then return nil end
    local result={}
    local list=claims[claim_key(key,offset)]or{}
    for index_=#list,1,-1 do
        local item=list[index_]
        result[#result+1]={mod=item.mod,kind=item.kind,id=item.id,field=item.field,value=item.value,target=item.target,
            holds=item.desired~=nil and item.desired==current or nil}
    end
    return result
end
-- The conflict text: who holds the observed bytes, and which other targets write them.
function M.conflict_text(descriptor,current)
    local parts={}
    local holders=M.holders(descriptor,current)
    if holders then
        local holding,earlier={},{}
        for _,item in ipairs(holders)do
            local text=item.mod..' '..item.kind..' '..item.id..' ('..tostring(item.target or item.field)..' = '
                ..value_text(item.value)..')'
            if item.holds then holding[#holding+1]=text else earlier[#earlier+1]=text end
        end
        if #holding>0 then parts[#parts+1]='held by '..table.concat(holding,', ')
        elseif #earlier>0 then parts[#parts+1]='last applied by '..earlier[1]
            ..', changed since outside HD2Runtime patch/transaction/plan/ensure'
        else parts[#parts+1]='no HD2Runtime patch, transaction, plan or ensure applied these bytes this session '
            ..'(another program or a mod writing game memory directly)'end
    end
    local others=M.others(descriptor)
    if #others>0 then parts[#parts+1]='the same native record is also used by '..M.others_text(others)end
    return table.concat(parts,'; ')
end
-- Test hook: forget the claims.
function M.reset_claims()claims={}end

-- One warning per operation when a write's own catalogue marks a field unshared but another catalogued target uses
-- the same native record (each catalogue was reviewed per family). The write is not refused: the guard keeps the
-- published contract (a stricter rule for these fields needs the version-aware acknowledgement path); the author is
-- told what else changes. Returns the warnings, for tests.
local warned={}
function M.warn_unlisted(spec,kind,mod,emit)
    -- Every registration passes here: also its one-time field notices (deprecated ids, dormant writes).
    pcall(function()require('hd2runtime/core/field_notices').warn(spec,kind,mod,emit)end)
    local by_id,order={},{}
    each_change(spec,function(change,id)
        local descriptor=change.descriptor
        if type(descriptor)~='table'or marked_shared(descriptor)then return end
        local others=M.others(descriptor)
        if #others==0 then return end
        local item=by_id[id]
        if not item then item={id=id,fields={},targets={},order={}};by_id[id]=item;order[#order+1]=id end
        item.fields[#item.fields+1]=tostring(change.field)
        if not item.owner then
            local resource,target=own_identity(descriptor)
            item.owner=resource and(resource..' '..target)or nil
        end
        for _,group in ipairs(others)do
            local name=group.resource..' '..group.target
            if not item.targets[name]then item.targets[name]=true;item.order[#item.order+1]=name end
        end
    end)
    local lines={}
    for _,id in ipairs(order)do
        local item=by_id[id]
        local key=tostring(mod)..'|'..tostring(id)
        if not warned[key]then
            warned[key]=true
            require('hd2runtime/runtime/metrics').count('shared_records.unlisted_warnings')
            local owner=item.owner or'its target'
            table.sort(item.order)
            local line='[HD2Runtime] '..kind..' '..tostring(id)..' ('..tostring(mod)..'): '
                ..table.concat(item.fields,', ')..' of '..owner..' '..(#item.fields>1 and'are'or'is')
                ..' in a native record that '
                ..table.concat(item.order,', ')..' also '..(#item.order>1 and'use'or'uses')
                ..'; its catalogue lists no other user, so this edit changes '..(#item.order>1 and'them'or'it')
                ..' too, and another mod editing '..(#item.order>1 and'them'or'it')..' conflicts'
            lines[#lines+1]=line
            if emit then pcall(emit,line)end
        end
    end
    return lines
end
return M
