-- A patch, transaction or plan on HellForge (runtime/hellforge.lua, docs/hellforge.md): the same validated spec, made
-- HellForge live edits of the same native fields instead of guarded writes. Nothing is captured, compared or written
-- here: HellForge resolves each field through the game's tables (a mod entity's own records, moved tables) and keeps
-- the edit for later data loads, and its F8 editor names the mod that made it (lua.<mod>). A Lua mod's edit sits over
-- code mods' and under the editors' changes.
--
-- A change is routed when its field names one native value: a component record (by the record's entity), a settings row
-- (projectile, damage, explosion, status, arc, beam: by its id), a stratagem's definition (by its stable id, as its
-- type), a booster's row, or a row its target names (a booster's explosion, damage, status or granted stratagem; a
-- stratagem's payload entity), stored as one u8, u16, u32, i32, f32 or u64, with the bytes the validation made; and,
-- through HellForge's set_stat, an entity delta (an attachment's stats, a mission's timer) or a status multiplier, and
-- through its copy_row, a row copied from a reviewed donor (the G-109 Urchin's pulse), and through its set_code, a
-- stratagem's calldown code. Anything else is refused with HELLFORGE_UNSUPPORTED, and the whole operation with it (what
-- it changed in this run is undone).
-- Setting a field back to its reviewed value removes the mod's edit (HellForge puts back what is under it).
local hellforge=require('hd2runtime/runtime/hellforge')
local b=require('hd2runtime/core/bytes')
local M={}

local SETTINGS={projectile='ProjectileSettings',damage='DamageInfo',explosion_damage='DamageInfo',
    explosion='ExplosionSettings',status='StatusEffectSettings',arc='ArcSettings',beam='BeamSettings'}
local TABLE_KINDS={ProjectileSettings=true,DamageInfo=true,ExplosionSettings=true,StatusEffectSettings=true,
    ArcSettings=true,BeamSettings=true}
local SIZE={u8=1,u16=2,u32=4,i32=4,f32=4,u64=8}

-- Every validated change of a spec: a patch's or transaction's changes, a plan's phases (or operations); and the spec
-- each came from (its booster or stratagem and target path name the rows a change's field leaves unnamed).
function M.changes(spec)
    local list,from={},{}
    local function add(s)
        for _,change in ipairs(type(s)=='table'and s.changes or{})do list[#list+1]=change;from[#list]=s end
    end
    if type(spec.phases)=='table'then
        for _,phase in ipairs(spec.phases)do for _,s in ipairs(phase.capture_specs or{})do add(s)end end
    elseif type(spec.operations)=='table'then
        for _,operation in ipairs(spec.operations)do add(operation.spec)end
    else add(spec)end
    return list,from
end

-- Native slot lists (domains/player_weapon_writes.lua SLOT_SETS): the domain writes them slot by slot, aligned 4-byte
-- values from the field's offset; so does HellForge, one live edit per slot. weapon_sound also has its MIDI byte.
local SLOT_SETS={fire_mode_set={4,'u32'},fire_rate_set={3,'f32'},trait_set={5,'u32'},armor_penetration_label={5,'u32'},
    weapon_sound={3,'u32'}}
function M.pieces(change)
    local descriptor=change.descriptor
    local set=type(descriptor)=='table'and SLOT_SETS[descriptor.type]
    local backing=set and descriptor.backing
    if not set or type(backing)~='table'or type(change.desired)~='string'or not tonumber(backing.offset)then return {change}end
    local list={}
    local function piece(label,offset,storage,from,to)
        local copy={}
        for key,value in pairs(backing)do copy[key]=value end
        copy.offset,copy.storage,copy.width=offset,storage,to-from+1
        list[#list+1]={field=tostring(change.field or change.canonical_field)..label,descriptor={backing=copy},
            desired=change.desired:sub(from,to),
            expected=type(change.expected)=='string'and change.expected:sub(from,to)or nil,
            expect=change.expect,value=change.value}
    end
    for slot=0,set[1]-1 do piece('['..(slot+1)..']',tonumber(backing.offset)+slot*4,set[2],slot*4+1,slot*4+4)end
    if descriptor.type=='weapon_sound'and tonumber(descriptor.midiOffset)then
        piece('.midi',tonumber(descriptor.midiOffset),'u8',13,13)
    end
    return list
end

-- A u64 from its two u32 halves (a cdata on the game's LuaJIT, a number in tests).
local function u64(lo,hi)
    local backend=hellforge.backend()
    if backend and backend.ffi then return backend.ffi.new('uint64_t',hi)*4294967296+lo end
    return hi*4294967296+lo
end
-- A catalogue resource ('0x3575AABC5F1F9326') as a u64.
function M.resource(text)
    if type(text)~='string'then return text end
    local hex=text:gsub('^0[xX]','')
    if not hex:match('^%x+$')or #hex>16 then return nil end
    hex=string.rep('0',16-#hex)..hex
    return u64(tonumber(hex:sub(9,16),16),tonumber(hex:sub(1,8),16))
end

-- The reviewed entry a spec names: a booster's (booster_authoring) or a stratagem's (stratagem_authoring).
local function catalogued(module,root,name)
    local ok,data=pcall(require,module)
    return ok and type(data)=='table'and type(data[root])=='table'and data[root][name]or nil
end
-- A booster target's rows by the field's kind: its ids (explosionType, damageType, statusType), as HellForge names
-- rows; the target's `row` is the row's position again (domains/booster_writes.lua checks both).
local BOOSTER_ROWS={explosion={'ExplosionSettings','explosionType'},explosion_damage={'DamageInfo','damageType'},
    status_damage={'DamageInfo','damageType'},status_row={'StatusEffectSettings','statusType'}}
local function stratagem_row(stable,offset,kind,storage)
    local stratagem=hellforge.backend().stratagem_type(stable)
    if not stratagem or stratagem==0 then
        return nil,'TARGET_UNAVAILABLE: the stratagems have not loaded yet (stable id '..stable..')',true
    end
    return {component='StratagemDefinition',target=stratagem,offset=offset,kind=kind,flags=0,storage=storage,
        label='StratagemDefinition '..stratagem..' +'..offset}
end
local function from_target(backing,source,offset,kind,storage)
    if type(source)~='table'then return nil end
    if type(source.booster)=='string'then
        local entry=catalogued('hd2runtime/domains/booster_authoring','boosters',source.booster)
        local owned=entry and type(entry.targets)=='table'and entry.targets[source.target_path]
        if type(owned)~='table'then return nil end
        local rows=BOOSTER_ROWS[backing.kind]
        if rows then
            local row=owned[rows[2]]
            if type(row)~='number'or row==0 then return nil,'the booster names no '..rows[1]..' row'end
            return {component=rows[1],target=row,offset=offset,kind=kind,flags=0,storage=storage,
                label=rows[1]..' row '..row..' +'..offset}
        end
        -- the stratagem a booster grants (Surplus EAT Allocation's), by its stable id
        if backing.kind=='stratagem_row'and type(owned.record)=='table'and type(owned.record.id)=='number'then
            return stratagem_row(owned.record.id,offset,kind,storage)
        end
        return nil
    end
    -- a component of the stratagem's own payload entity (an Orbital Laser's OrbitalAbilityComponentData)
    if type(source.stratagem)=='string'then
        local entry=catalogued('hd2runtime/domains/stratagem_authoring','stratagems',source.stratagem)
        local link=entry and entry.rootLink
        if type(link)=='table'and link.component==backing.kind and type(link.payload)=='string'then
            local resource=M.resource(link.payload)
            if not resource then return nil end
            return {component=link.component,target=resource,offset=offset,kind=kind,flags=0,storage=storage,
                label=link.component..' of '..link.payload..' +'..offset}
        end
    end
    return nil
end

-- An entity delta, as HellForge's set_stat names it (the stats schema's EntityDelta fields): "<component>:<member>",
-- the delta's resource, its settings index and the value's place in the delta data.
local function delta(component,member,resource,settings,data,storage,label)
    local kind=hellforge.TYPE[storage]
    if not kind or not tonumber(component)or not tonumber(member)or not tonumber(settings)or not tonumber(data)then
        return nil,'its entity delta is not named'
    end
    local id=M.resource(resource)
    if not id then return nil,'its entity delta names no resource'end
    return {stat='EntityDelta',component=component..':'..member,resource=id,record=settings,offset=data,kind=kind,
        storage=storage,label=label}
end
-- Fields set_stat reaches: an attachment's (by the spec's attachment), a mission's timer; nil when it is not one.
function M.stat(descriptor,backing,source)
    if backing.kind=='entity_delta'then
        local entry=type(source)=='table'and type(source.attachment)=='string'
            and catalogued('hd2runtime/domains/attachment_authoring','attachments',source.attachment)
        if not entry then return nil,'its entity delta belongs to no attachment the bridge knows'end
        return delta(descriptor.component,descriptor.componentOffset,entry.resource,entry.settingsIndex,
            descriptor.dataOffset,descriptor.storage or backing.storage,
            tostring(entry.name or source.attachment)..' '..tostring(backing.component))
    end
    if backing.kind=='mission_timer'then
        local ok,missions=pcall(require,'hd2runtime/domains/missions')
        local s=ok and type(missions.sources)=='table'and missions.sources[backing.source]
        if type(s)~='table'then return nil,'its mission timer source is not catalogued'end
        if s.kind=='delta'then
            return delta(s.component,s.componentOffset,s.resource,s.settingsIndex,s.dataOffset,'f32',
                'mission timer '..backing.source)
        end
        -- a mission director's own record (HiveMindComponentData, its entity's), set before launch
        local id=M.resource(s.resource)
        local component=type(s.identity)=='table'and s.identity.component
        if not id or type(component)~='string'or not tonumber(s.offset)then return nil,'its mission timer is not named'end
        return {component=component,target=id,offset=tonumber(s.offset),kind=hellforge.TYPE.f32,flags=0,storage='f32',
            label='mission timer '..backing.source}
    end
    -- a booster status's multiplier (Experimental Infusion's incoming damage): an element of the (stat, value) list its
    -- status row points to, by the stat it names
    if backing.kind=='status_multiplier'then
        local entry=type(source)=='table'and type(source.booster)=='string'
            and catalogued('hd2runtime/domains/booster_authoring','boosters',source.booster)
        local owned=entry and type(entry.targets)=='table'and entry.targets[source.target_path]
        local kind=hellforge.TYPE[backing.storage]
        if type(owned)~='table'or type(owned.statusType)~='number'or not kind or type(backing.stat)~='number'
            or type(backing.index)~='number'then
            return nil,'its status multiplier is not named'
        end
        return {stat='StatusMultiplier',component=tostring(backing.stat),resource=0,record=owned.statusType,
            offset=4+backing.index*8,kind=kind,storage=backing.storage,
            label='StatusEffectSettings '..owned.statusType..' multiplier of stat '..backing.stat}
    end
    return nil
end
-- A row copied from a donor of the same table, as HellForge's copy_row does (mappings/references.json "rowCopies"):
-- the G-109 Urchin's pulse explosion. The value names the donor (payloadOptions, by its row id). HellForge copies into
-- the rows that go with the named one itself (the Urchin's final discharge, HD2Runtime's second payloadRecipients row).
function M.copy(change,descriptor,backing)
    if backing.storage~='bytes'or type(descriptor.payloadOptions)~='table'then return nil end
    local table_name=backing.kind=='settings'and SETTINGS[backing.settings]
    local row=backing.recordType or backing.nativeIdentity
    if not table_name or type(row)~='number'then return nil,'its row is not named'end
    local from=0
    if change.value~=descriptor.currentDefault then
        local option=descriptor.payloadOptions[change.value]
        from=type(option)=='table'and tonumber(option.recordType)
        if not from then return nil,'its donor is not a reviewed one'end
        if from==row then from=0 end
    end
    return {copy=true,table=table_name,row=row,from=from,offset=tonumber(backing.offset)or 0,
        size=tonumber(backing.width)or 0,label=table_name..' row '..row..(from~=0 and(' from row '..from)or' (its own)')}
end

-- Where a change goes in HellForge: {component, target, offset, kind, flags, storage}, or nil, why and whether it is
-- worth another try later (the entity data is not loaded yet). source: the spec the change came from (M.changes).
function M.locate(change,source)
    local descriptor=change.descriptor
    local backing=type(descriptor)=='table'and descriptor.backing
    if type(backing)~='table'then return nil,'the field names no native record'end
    local stat,why=M.stat(descriptor,backing,source)
    if stat or why then return stat,why end
    local copy
    copy,why=M.copy(change,descriptor,backing)
    if copy or why then return copy,why end
    -- a stratagem's calldown code (domains/stratagem_writes.lua validate_calldown: its directions, 1 up .. 4 left)
    if backing.storage=='calldown'then
        local code=type(change.calldown)=='table'and change.calldown.value
        if type(backing.nativeIdentity)~='number'or type(code)~='table'then return nil,'its calldown code is not named'end
        return {code=true,stable=backing.nativeIdentity,values=code,label='calldown code of '..backing.nativeIdentity}
    end
    local storage=backing.storage
    -- a stratagem's presentation member is one value: a text id (u32) or an icon's image hash (u64)
    if backing.kind=='StratagemDefinition'and storage=='presentation'then
        storage=tonumber(backing.width)==4 and'u32'or tonumber(backing.width)==8 and'u64'or storage
    end
    local kind=hellforge.TYPE[storage]
    if not kind then return nil,'its value is not one number (storage '..tostring(storage)..')'end
    local offset=tonumber(backing.offset)
    if not offset or offset<0 or offset%1~=0 then return nil,'it has no offset'end
    if tonumber(backing.width)and tonumber(backing.width)~=SIZE[storage]then
        return nil,'it spans '..tostring(backing.width)..' bytes, not one '..storage
    end
    -- An armor perk's value (domains/armor_perks.lua): a row of HellForge's PassiveModifier (16 bytes) or PassiveStat
    -- (12 bytes) tables, id passive * 16 + index; the catalogue's offset counts from the passive's first entry.
    if backing.kind=='armor_perk'then
        local stride=backing.part=='modifier'and 16 or backing.part=='stat'and 12
        if not stride or type(backing.passive)~='number'or type(backing.index)~='number'then
            return nil,'its armor perk row is not named'
        end
        local table_name=stride==16 and'PassiveModifier'or'PassiveStat'
        local id,at=backing.passive*16+backing.index,offset-backing.index*stride
        return {component=table_name,target=id,offset=at,kind=kind,flags=0,storage=storage,
            label=table_name..' row '..id..' +'..at}
    end
    -- A settings row by its id, as HellForge names rows: recordType (weapon catalogues) or nativeIdentity (stratagem
    -- catalogues); every catalogued row has one. `row` is its position in the game's table, which is another row's id
    -- (the RS-422 Railgun's damage is id 64 at position 69; Eagle Smoke Strike's projectile 130 at 9).
    local row=backing.recordType or backing.nativeIdentity
    local table_name=backing.kind=='settings'and SETTINGS[backing.settings]or TABLE_KINDS[backing.kind]and backing.kind
    if table_name then
        if type(row)~='number'then return nil,'its '..table_name..' row is not named'end
        return {component=table_name,target=row,offset=offset,kind=kind,flags=0,storage=storage,
            label=table_name..' row '..row..' +'..offset}
    end
    if backing.kind=='settings'then return nil,tostring(backing.settings)..' settings rows are not on HellForge yet'end
    -- a row the field leaves to its target (a booster's explosion, a stratagem's payload entity)
    if backing.row==nil and backing.recordIndex==nil then
        local at,why,later=from_target(backing,source,offset,kind,storage)
        if at or why then return at,why,later end
    end
    -- a booster's own row (BoosterSettings), by the row the catalogue names (as HellForge's editor does)
    if backing.kind=='booster_table'and type(backing.row)=='number'then
        return {component='BoosterSettings',target=backing.row,offset=offset,kind=kind,flags=0,storage=storage,
            label='BoosterSettings row '..backing.row..' +'..offset}
    end
    -- a stratagem's definition: its StratagemDefinition row, the type HellForge finds for its stable id
    if backing.kind=='StratagemDefinition'and type(backing.nativeIdentity)=='number'then
        return stratagem_row(backing.nativeIdentity,offset,kind,storage)
    end
    -- a component record: its component named, or the kind itself a component (OrbitalAbilityComponentData)
    local component=backing.component or(type(backing.kind)=='string'and backing.kind:match('ComponentData$')and backing.kind)
    if type(component)=='string'and type(backing.recordIndex)=='number'and backing.kind~='entity_delta'then
        local backend=hellforge.backend()
        local resource,owners=backend.owner(component,backing.recordIndex)
        if not resource then
            return nil,'TARGET_UNAVAILABLE: no entity names '..component..' record '..backing.recordIndex..' yet',true
        end
        local shared=(owners or 1)>1 or(tonumber(backing.ownerCount)or 1)>1 or backing.uniqueOwner==false
        return {component=component,target=resource,offset=offset,kind=kind,
            flags=shared and hellforge.LIVE_SHARED or 0,storage=storage,
            label=component..' record '..backing.recordIndex..' +'..offset}
    end
    return nil,tostring(backing.kind or'these')..' fields are not on HellForge yet'
end

-- A change's value as the bridge takes it: number (every type but u64) and u64.
function M.value(bytes,storage)
    if type(bytes)~='string'or #bytes~=SIZE[storage]then return nil end
    if storage=='u64'then return 0,u64(b.u32(bytes,0),b.u32(bytes,4))end
    if storage=='u16'then return b.u16(bytes,0),0 end
    return b.value(bytes,0,storage),0
end

local function text(value)
    if type(value)=='table'then
        if value.weapon and value.attack then return value.weapon..':'..value.attack end
        if value.output then return tostring(value.output)end
        return '{...}'
    end
    return tostring(value)
end

-- A watch with the guarded operations' interface (status, result, tick, cancel). kind: 'patch', 'transaction', 'plan'.
function M.start_spec(kind,runtime,emit,spec,startup_delay)
    startup_delay=startup_delay==nil and 3 or startup_delay
    local backend=hellforge.backend()
    local watch={status='waiting',backend='hellforge',attempts=0}
    local elapsed=0
    local function log(message)pcall(emit,'[HD2Runtime] '..message)end
    local name=spec.mod
    if type(name)~='string'or name=='unknown'then
        local ok,mod=pcall(function()return require('hd2runtime/core/shared_records').current_mod()end)
        name=ok and mod or nil
    end
    local mod=backend and hellforge.mod(name)
    local function reject(code,reason)
        watch.status='rejected';watch.error=code..': '..tostring(reason)
        watch.result={status='REJECTED',code=code,reason=watch.error,writes=0,bytes_written=0,protection_changes=0,
            protection_restored=true,rollback='not_needed',backend='hellforge'}
        log(kind..' '..tostring(spec.id)..' REJECTED code='..code..' reason='..watch.error)
    end
    -- Enemies wait until HellForge maps them (runtime/hellforge_api.lua).
    local enemy=spec.kind=='enemy'or spec.kind=='enemy_director'
    for _,phase in ipairs(type(spec.phases)=='table'and spec.phases or{})do
        for _,s in ipairs(phase.capture_specs or{})do enemy=enemy or s.kind=='enemy'or s.kind=='enemy_director'end
    end
    if enemy or not mod then
        reject('HELLFORGE_UNAVAILABLE',not backend and('HellForge\'s Lua bridge cannot be used: '..tostring(hellforge.reason))
            or enemy and'enemy fields: HellForge has not mapped enemies yet'or'HellForge has no room for another Lua mod')
        function watch.tick()end
        function watch.cancel()end
        return watch
    end
    local dependencies
    local ok_assets,collected=pcall(function()return require('hd2runtime/core/assets').collect(spec)end)
    dependencies=ok_assets and collected or{}
    function watch.cancel()
        if watch.status~='complete'and watch.status~='rejected'then watch.status='cancelled'end
    end
    function watch.tick(dt)
        if watch.status=='complete'or watch.status=='rejected'or watch.status=='cancelled'then return end
        elapsed=elapsed+(dt or 0)
        if elapsed<startup_delay then return end
        -- The packages a reference needs (a donor projectile, an explosion's effect), through HellForge's loader.
        for _,dependency in ipairs(dependencies)do
            local package=M.resource(dependency.package)
            local state=package and backend.load_package(mod,package)or 0
            if state==0 then
                return reject('ASSET_UNAVAILABLE','HellForge could not load '..tostring(dependency.name or dependency.package)
                    ..': '..backend.last(mod))
            end
            if state~=2 then watch.status='waiting_for_assets';return end
        end
        watch.attempts=watch.attempts+1
        local applied,report={},{}
        -- a change taken away: the value under the mod's shows again
        local function take_back(a)
            if a.stat then return backend.clear_stat(mod,a.stat,a.component,a.resource,a.record,a.offset,a.kind)end
            if a.copy then return backend.copy_row(mod,a.table,a.row,0,a.offset,a.size)end
            if a.code then return backend.set_code(mod,a.stable,nil)end
            return backend.clear(mod,a.component,a.target,a.offset,a.kind)
        end
        local function undo()for i=#applied,1,-1 do take_back(applied[i])end end
        local writes,cleared=0,0
        local pieces,sources={},{}
        local changes,from=M.changes(spec)
        for i,change in ipairs(changes)do
            for _,piece in ipairs(M.pieces(change))do pieces[#pieces+1]=piece;sources[#pieces]=from[i]end
        end
        for index,change in ipairs(pieces)do
            local at,why,later=M.locate(change,sources[index])
            if not at and later then
                undo()
                watch.status='waiting';watch.waiting=why
                return
            end
            if not at then
                undo()
                return reject('HELLFORGE_UNSUPPORTED',tostring(change.field or change.canonical_field or('change '..index))..': '..why)
            end
            local result
            if change.image~=nil then
                -- a mod's own icon must be loaded before the game draws it, which HellForge does not do for Lua mods yet
                undo()
                return reject('HELLFORGE_UNSUPPORTED',tostring(change.field)..': a mod\'s own icon image is not on HellForge yet')
            end
            if at.copy then
                result=backend.copy_row(mod,at.table,at.row,at.from,at.offset,at.size)
                if at.from==0 then cleared=cleared+1
                elseif result~=0 then
                    applied[#applied+1]=at
                    writes=writes+1
                    report[#report+1]=tostring(change.field)..' '..text(change.expect)..' -> '..text(change.value)..' ('
                        ..at.label..', '..tostring(hellforge.APPLIES[result]or result)..')'
                end
            elseif change.desired~=nil and change.desired==change.expected then
                result=take_back(at)
                cleared=cleared+1
            elseif at.code then
                result=backend.set_code(mod,at.stable,at.values)
                if result~=0 then
                    applied[#applied+1]=at
                    writes=writes+1
                    report[#report+1]=tostring(change.field)..' -> '..table.concat(at.values,',')..' ('..at.label..')'
                end
            else
                local number,u64_value=M.value(change.desired,at.storage)
                if number==nil then
                    undo()
                    return reject('HELLFORGE_UNSUPPORTED',tostring(change.field or('change '..index))
                        ..': its value is worked out while it applies, which HellForge does not do yet')
                end
                if at.stat then
                    result=backend.set_stat(mod,at.stat,at.component,at.resource,at.record,at.offset,at.kind,number)
                else
                    result=backend.set(mod,at.component,at.target,at.offset,at.kind,number,u64_value,at.flags)
                end
                if result~=0 then
                    applied[#applied+1]=at
                    writes=writes+1
                    report[#report+1]=tostring(change.field or change.canonical_field)..' '..text(change.expect)..' -> '
                        ..text(change.value)..' ('..at.label..', '..tostring(hellforge.APPLIES[result]or result)..')'
                end
            end
            if result==0 then
                local reason=backend.last(mod)
                undo()
                return reject('HELLFORGE_REFUSED',tostring(change.field or('change '..index))..': '..reason)
            end
        end
        watch.status='complete';watch.waiting=nil
        watch.result={status=writes>0 and'APPLIED'or'ALREADY_DESIRED',writes=writes,cleared=cleared,bytes_written=0,
            protection_changes=0,protection_restored=true,rollback='not_needed',backend='hellforge',id=spec.id}
        for _,line in ipairs(report)do log(line)end
        log(kind..' '..tostring(spec.id)..' '..watch.result.status..' through HellForge ('..writes..' set, '..cleared
            ..' back to their base)')
        pcall(function()require('hd2runtime/core/shared_records').claim(spec,kind,name)end)
    end
    return watch
end
return M
