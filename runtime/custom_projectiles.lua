-- Runtime-owned custom projectile definitions: the hybrid-row architecture (docs/custom-projectile-rows.md).
--
-- A definition is a semantic id, a vanilla base projectile (a catalogued attack output), explicitly permitted changes
-- and one stable Runtime-owned ProjectileInfo row. The row is built once: the live vanilla base row is cloned byte for
-- byte, only COPIED_AT_SPAWN members are changed (each value taken from another catalogued vanilla row, read-only),
-- the result must be a VALID hybrid of its base (core/projectile_rows.lua), and it is written into a block the Runtime
-- owns. No vanilla row is written, no ProjectileType is added and nothing is registered with the game: the game sees
-- the row only while SpawnProjectile runs (runtime/event_world.lua spawn_projectile_row), and the spawned projectile
-- keeps the vanilla base type. Definitions and their rows live as long as this Lua state.
--
-- Infrastructure only: there is no public API for definitions yet (a development proof defines one).
local projectile_rows=require('hd2runtime/core/projectile_rows')
local b=require('hd2runtime/core/bytes')
local core_assets=require('hd2runtime/core/assets')
local world_module=require('hd2runtime/runtime/event_world')
local metrics=require('hd2runtime/runtime/metrics')
local M={}
local definitions,order={},{}
local function catalog()return require('hd2runtime/domains/attack_outputs')end
local catalogued_explosion
local TYPE_COUNT=require('hd2runtime/domains/projectile_rows').table.typeCount

-- The live-verified development proof (docs/custom-projectile-rows.md): a LAS-58 Talon base with the PLAS-1 Scorcher's
-- visual and the RS-422 Railgun's direct damage. Both donors are unit-less like the Talon, so every late-lookup member
-- stays the Talon's own.
M.DEVELOPMENT_PROOF={id='dev/talon_hybrid_proof',base='LAS-58 Talon',
    components={visual='PLAS-1 Scorcher',damage='RS-422 Railgun'}}
-- The component proof variants (proof/CustomProjectileRowProof): each component alone on a Talon base, then all of
-- them together. The GL-21 Grenade Launcher's ballistics (100 m/s, gravity 1, drag 1.2) turn the Talon's straight
-- 1300 m/s bolt into a visible lob; the R-36 Eruptor's impact explosion is its shell's blast (with its shrapnel).
M.DEVELOPMENT_VARIANTS={
    {id='dev/talon_visual',base='LAS-58 Talon',components={visual='PLAS-1 Scorcher'}},
    {id='dev/talon_damage',base='LAS-58 Talon',components={damage='RS-422 Railgun'}},
    {id='dev/talon_ballistics',base='LAS-58 Talon',components={ballistics='GL-21 Grenade Launcher'}},
    {id='dev/talon_impact',base='LAS-58 Talon',components={impact_explosion='R-36 Eruptor'}},
    {id='dev/talon_combined',base='LAS-58 Talon',components={visual='PLAS-1 Scorcher',damage='RS-422 Railgun',
        ballistics='GL-21 Grenade Launcher',impact_explosion='R-36 Eruptor'}},
}

-- Copied members that are also catalogued slots of a projectile output: a donor's live value must equal its catalogue.
local CATALOGUED_SLOTS={direct_damage='projectile.direct_damage',impact_explosion='projectile.impact_explosion'}

local function valid_id(id)
    return type(id)=='string'and#id<=96 and id:match('^[%w_%-]+/[%w_%-/]+$')~=nil
end
-- A projectile output id from an id or the name of the weapon that owns it (its one established, non-spare output).
local function output_id(name)
    local outputs=catalog().outputs
    if type(name)~='string'or outputs[name]then return name end
    local found
    for id,output in pairs(outputs)do
        -- (The more projectile donors share their owners' names but are named by their own; never a weapon's output.)
        if output.family=='projectile'and output.owner and output.owner.name==name and output.currentDefault
                and not output.spare and not output.unverifiedDonor then
            if found then return nil,'AMBIGUOUS_PROJECTILE',name..' owns more than one projectile output; name one '
                ..'by its output id'end
            found=id
        end
    end
    return found or name
end
-- A catalogued vanilla projectile output: {output, weapon, type, dependency, catalog}, or nil, code, reason. The
-- package is required unless assets is false (a component made of plain numbers).
local function projectile_output(name,role,assets)
    local id,code,reason=output_id(name)
    if not id then return nil,code,reason end
    local output=type(id)=='string'and catalog().outputs[id]
    if not output or output.family~='projectile'then
        return nil,'UNKNOWN_PROJECTILE',role..' must be a catalogued projectile output (output/v1/projectile/...); '
            ..'raw ids are refused: '..tostring(id)
    end
    if output.spare then
        return nil,'BORROWED_ROW',role..' '..id..' is a spare twin (a borrowed vanilla row), not a vanilla projectile'
    end
    local kind=output.currentDefault
    if type(kind)~='number'or kind<=0 or kind>=TYPE_COUNT or kind%1~=0 then
        return nil,'UNKNOWN_PROJECTILE',role..' '..id..' has no vanilla ProjectileType'
    end
    local owner=output.owner or{}
    local dependency=output.dependencyKey and core_assets.dependency(output.dependencyKey)
    if not dependency and assets~=false then
        return nil,'ASSET_UNKNOWN','the package that holds the '..tostring(owner.name or id)..' projectile is not '
            ..'known, so its assets cannot be guaranteed loaded'
    end
    return {output=id,weapon=owner.name,type=kind,dependency=dependency,catalog=output}
end
-- A catalogued explosion as the impact explosion donor (hd2.explosion(name), or its catalogue name): entry, name; nil
-- otherwise. A weapon name or projectile output id is never a catalogue name (their namespaces differ).
function catalogued_explosion(donor)
    local name=donor
    if type(donor)=='table'and rawget(donor,'resource')=='explosion'then name=rawget(donor,'explosion')
    elseif type(donor)~='string'or catalog().outputs[donor]then return nil end
    local entry,id=require('hd2runtime/domains/explosion_writes').entry(name)
    if entry then return entry,id end
    return nil
end
-- The spec as a comparable string (a definition id is defined once; the same spec again returns it).
local function canonical(spec)
    local parts={tostring(spec.id),tostring(spec.base)}
    for _,id in ipairs(projectile_rows.COMPONENT_ORDER)do
        local donor=spec.components and spec.components[id]
        if donor then
            local _,explosion=catalogued_explosion(donor)
            parts[#parts+1]=id..'<'..(explosion and('explosion:'..explosion)or tostring(donor))
        end
    end
    for _,change in ipairs(spec.changes or{})do
        local members=change.members or{change.member}
        local names={}
        for _,member in ipairs(members)do names[#names+1]=tostring(member)end
        parts[#parts+1]=table.concat(names,'+')..'<'..tostring(change.from)
    end
    return table.concat(parts,'|')
end
local function validate_spec(spec)
    if type(spec)~='table'then return nil,'INVALID_DEFINITION','a definition must be a table'end
    for key in pairs(spec)do
        if key~='id'and key~='base'and key~='changes'and key~='components'then
            return nil,'INVALID_DEFINITION','unsupported definition option: '..tostring(key)
        end
    end
    if not valid_id(spec.id)then
        return nil,'INVALID_DEFINITION','the id must be a semantic id such as "dev/talon_hybrid" (letters, digits, '
            .."'_', '-', '/')"
    end
    if spec.changes~=nil and type(spec.changes)~='table'then
        return nil,'INVALID_DEFINITION','changes must be a list'
    end
    if spec.components~=nil and type(spec.components)~='table'then
        return nil,'INVALID_DEFINITION','components must be a table {component = donor}'
    end
    for id,donor in pairs(spec.components or{})do
        if id=='impact_explosion'and catalogued_explosion(donor)then donor=nil end
        if donor==nil then
            -- A catalogued explosion (hd2.explosion(name)): checked when the definition is built.
        elseif not projectile_rows.component(id)then
            return nil,'UNKNOWN_COMPONENT','no projectile component '..tostring(id)..' (components: '
                ..table.concat(projectile_rows.COMPONENT_ORDER,', ')..')'
        end
        if donor~=nil and type(donor)~='string'then
            return nil,'INVALID_DEFINITION','component '..id..' needs a donor projectile (a weapon name or output id)'
        end
    end
    for index,change in ipairs(spec.changes or{})do
        if type(change)~='table'or(change.member==nil)==(change.members==nil)or type(change.from)~='string'then
            return nil,'INVALID_DEFINITION','change '..index..' must be {member=... or members={...}, from=<output>}'
        end
        for key in pairs(change)do
            if key~='member'and key~='members'and key~='from'then
                return nil,'INVALID_DEFINITION','change '..index..' has an unsupported option: '..tostring(key)
            end
        end
    end
    return true
end

-- Creates (or returns the identical existing) definition. spec: {id, base=<weapon name or projectile output id>,
-- components={visual=<donor>, damage=<donor>, impact_explosion=<donor>, ballistics=<donor>}, changes={{member=
-- <COPIED_AT_SPAWN label or offset> or members={...}, from=<donor>}, ...}}. A component copies exactly the members its
-- descriptor owns from the donor's live vanilla row (and must satisfy its constraints); a change copies the named
-- members. Returns the definition, or nil, code, reason (and the validation report when the row was built but is not
-- a VALID hybrid).
function M.define(spec)
    local ok,code,reason=validate_spec(spec)
    if not ok then return nil,code,reason end
    local existing=definitions[spec.id]
    if existing then
        if existing.canonical==canonical(spec)then return existing end
        return nil,'DUPLICATE_DEFINITION','custom projectile '..spec.id..' is already defined differently'
    end
    local base
    base,code,reason=projectile_output(spec.base,'the base')
    if not base then return nil,code,reason end
    local world,why=world_module.open()
    if not world then return nil,'CUSTOM_PROJECTILE_UNAVAILABLE',tostring(why)end
    local runtime=world.runtime
    if not(runtime.owned_block and runtime.owned_write)then
        return nil,'CUSTOM_PROJECTILE_UNAVAILABLE','this Runtime adapter cannot allocate Runtime-owned rows'
    end
    local proven
    proven,why=world_module.prove_projectile_rows(world)
    if not proven then return nil,'CUSTOM_PROJECTILE_UNAVAILABLE',why end
    local base_row=world_module.projectile_row(world,base.type)
    if not base_row then
        return nil,'UNKNOWN_PROJECTILE','the vanilla row of '..tostring(base.weapon)..' (type '..base.type
            ..') does not resolve'
    end
    local row
    row,code,reason=projectile_rows.clone(base_row,base.type)
    if not row then return nil,code,reason end
    local changes,applied,dependencies,packages={},{},{base.dependency},{[base.dependency.package]=true}
    local summaries={}
    local function add_package(donor)
        if donor.dependency and not packages[donor.dependency.package]then
            packages[donor.dependency.package]=true
            dependencies[#dependencies+1]=donor.dependency
        end
    end
    local function donor_row_of(donor)
        local donor_row=world_module.projectile_row(world,donor.type)
        if not donor_row then
            return nil,'UNKNOWN_PROJECTILE','the vanilla row of '..tostring(donor.weapon)..' (type '..donor.type
                ..') does not resolve'
        end
        return donor_row
    end
    -- One donor member: re-proven against the donor's catalogue where it is a catalogued slot, then recorded.
    local function take(entry,value,donor,component)
        local slot_field=CATALOGUED_SLOTS[entry.label]
        if slot_field then
            -- The donor's catalogued slot value, re-proven live (the donor row is only referenced).
            local slot=donor.catalog.slotFields and donor.catalog.slotFields[slot_field]
            if slot and slot.currentDefault~=b.u32(value,0)then
                return nil,'DONOR_CHANGED','the live '..entry.label..' of '..donor.output..' is '
                    ..b.u32(value,0)..', not the catalogued '..tostring(slot.currentDefault)
            end
        end
        changes[#changes+1]={member=entry.offset,bytes=value}
        local current=row:sub(entry.offset+1,entry.offset+entry.width)
        -- Recorded only when it changes the base (a donor member equal to the base's is not a change).
        if value~=current then
            applied[#applied+1]={offset=entry.offset,width=entry.width,label=entry.label,from=donor.output,
                weapon=donor.weapon,type=donor.type,base=b.hex(current),value=b.hex(value),component=component}
        end
        return true
    end
    for _,id in ipairs(projectile_rows.COMPONENT_ORDER)do
        local name=spec.components and spec.components[id]
        local explosion,explosion_name
        if name and id=='impact_explosion'then explosion,explosion_name=catalogued_explosion(name)end
        if explosion then
            -- A catalogued explosion (domains/explosion_catalogue.lua): its type at +0x90, after its live settings
            -- record proves the reviewed type, damage link and radii; its package (unless it is the mission effects
            -- package, resident in every mission) is a dependency of the definition.
            if not explosion.payload then
                return nil,'ASSET_UNKNOWN','no package is known that ships the effect of the '..explosion_name
                    ..' explosion'
            end
            local record=world_module.explosion_settings(world,explosion.type)
            local raw=record and world.view.read(record,28)
            if not raw or b.u32(raw,4)~=(explosion.damage and explosion.damage.type or 0)
                or math.abs(b.value(raw,16,'f32')-explosion.values[1])>1e-4
                or math.abs(b.value(raw,20,'f32')-explosion.values[2])>1e-4
                or math.abs(b.value(raw,24,'f32')-explosion.values[3])>1e-4 then
                return nil,'DONOR_CHANGED','the live settings record of the '..explosion_name..' explosion is not '
                    ..'its reviewed row'
            end
            local entry=projectile_rows.copied('impact_explosion')
            local before=#applied
            ok,code,reason=take(entry,b.encode(explosion.type,'u32'),{output='explosion:'..explosion_name,
                type=explosion.type,catalog={}},id)
            if not ok then return nil,code,reason end
            summaries[#summaries+1]={id=id,name=projectile_rows.component(id).name,from='explosion:'..explosion_name,
                explosion=explosion_name,differs=#applied>before,assets='donor'}
            if not explosion.package.mission then
                local dependency=core_assets.dependency(explosion.package.key)
                if not dependency then
                    return nil,'ASSET_UNKNOWN','the package of the '..explosion_name..' explosion is not catalogued'
                end
                add_package({dependency=dependency})
            end
        elseif name then
            local component=projectile_rows.component(id)
            local donor
            donor,code,reason=projectile_output(name,component.name..' donor',component.assets=='donor')
            if not donor then return nil,code,reason end
            local donor_row
            donor_row,code,reason=donor_row_of(donor)
            if not donor_row then return nil,code,reason end
            local owned
            owned,code,reason=projectile_rows.component_changes(id,donor_row,base_row)
            if not owned then return nil,code,reason end
            local before=#applied
            for _,change in ipairs(owned)do
                ok,code,reason=take(projectile_rows.copied(change.member),change.bytes,donor,id)
                if not ok then return nil,code,reason end
            end
            summaries[#summaries+1]={id=id,name=component.name,from=donor.output,weapon=donor.weapon,type=donor.type,
                differs=#applied>before,assets=component.assets}
            if component.assets=='donor'then add_package(donor)end
        end
    end
    for index,change in ipairs(spec.changes or{})do
        local donor
        donor,code,reason=projectile_output(change.from,'change '..index..' donor')
        if not donor then return nil,code,reason end
        local donor_row
        donor_row,code,reason=donor_row_of(donor)
        if not donor_row then return nil,code,reason end
        for _,member in ipairs(change.members or{change.member})do
            local entry,restricted=projectile_rows.copied(member)
            if not entry then return nil,'RESTRICTED_MEMBER','change '..index..': '..restricted end
            local value=donor_row:sub(entry.offset+1,entry.offset+entry.width)
            ok,code,reason=take(entry,value,donor,nil)
            if not ok then return nil,code,reason end
        end
        add_package(donor)
    end
    row,code,reason=projectile_rows.apply(row,changes)
    if not row then return nil,code,reason end
    local report=projectile_rows.validate(row,base_row,base.type)
    if report.status~='VALID'then return nil,'HYBRID_INCOMPATIBLE',report.summary,report end
    local address=runtime.owned_block(projectile_rows.SIZE)
    runtime.owned_write(address,row)
    if world.view.read(address,projectile_rows.SIZE)~=row then
        return nil,'ROW_UNREADABLE','the Runtime-owned row did not read back as written'
    end
    local definition={id=spec.id,canonical=canonical(spec),status='defined',
        base={output=base.output,weapon=base.weapon,type=base.type},changes=applied,components=summaries,
        row={address=address,size=projectile_rows.SIZE},bytes=row,base_row=base_row,validation=report,
        dependencies=dependencies}
    definitions[spec.id]=definition
    order[#order+1]=spec.id
    metrics.count('custom_projectiles.defined')
    return definition
end
function M.get(id)return definitions[id]end
-- A catalogued vanilla projectile output by weapon name or output id (a weapon replacement's carrier): {output,
-- weapon, type, dependency, catalog}, or nil, code, reason. assets = false also accepts an output whose package is
-- not known.
function M.output(name,assets)return projectile_output(name,'the projectile',assets)end
function M.list()
    local out={}
    for _,id in ipairs(order)do out[#out+1]=M.describe(definitions[id])end
    return out
end
-- A copy for logs and diagnostics (no row bytes).
function M.describe(definition)
    local changes={}
    for _,item in ipairs(definition.changes)do
        changes[#changes+1]={offset=item.offset,width=item.width,label=item.label,from=item.from,weapon=item.weapon,
            type=item.type,base=item.base,value=item.value,component=item.component}
    end
    local components={}
    for _,summary in ipairs(definition.components or{})do
        components[#components+1]={id=summary.id,name=summary.name,from=summary.from,weapon=summary.weapon,
            type=summary.type,differs=summary.differs}
    end
    return {id=definition.id,status=definition.status,base_type=definition.base.type,base=definition.base.output,
        base_identity=definition.base.weapon,row=string.format('0x%X',definition.row.address),size=definition.row.size,
        compatibility=definition.validation.status,changes=changes,components=components,
        packages=#definition.dependencies}
end
-- A member value for logs: f32 members as numbers, u32 members in decimal, u64 members as 0x hex, others as bytes.
local function shown(hex,width,offset)
    local raw=b.unhex(hex)
    local entry=offset and projectile_rows.entries(offset)[1]
    if width==4 and entry and entry.storage=='FP32'then return string.format('%g',b.value(raw,0,'f32'))end
    if width==4 then return tostring(b.u32(raw,0))end
    if width==8 then return string.format('0x%08X%08X',b.u32(raw,4),b.u32(raw,0))end
    return hex
end
local function member_text(item,with_source)
    return string.format('+0x%X %s %s -> %s%s',item.offset,tostring(item.label),shown(item.base,item.width,item.offset),
        shown(item.value,item.width,item.offset),with_source and(' ('..tostring(item.weapon)..')')or'')
end
-- One log line: the identity, the base, the Runtime-owned row, the hybrid compatibility, then each component with its
-- source projectile and exactly the members that differ from the base, then any member-level changes.
function M.line(definition,report)
    local groups={}
    for _,summary in ipairs(definition.components or{})do
        local parts={}
        for _,item in ipairs(definition.changes)do
            if item.component==summary.id then parts[#parts+1]=member_text(item,false)end
        end
        groups[#groups+1]=string.format('%s from %s (%s)',summary.id,tostring(summary.weapon),
            #parts>0 and table.concat(parts,'; ')or'same as the base')
    end
    local loose={}
    for _,item in ipairs(definition.changes)do
        if not item.component then loose[#loose+1]=member_text(item,true)end
    end
    return string.format('custom projectile %s base type=%d base identity=%s custom row=0x%X hybrid compatibility=%s%s%s',
        definition.id,definition.base.type,tostring(definition.base.weapon),definition.row.address,
        (report or definition.validation).status,#groups>0 and(' components: '..table.concat(groups,', '))or'',
        #loose>0 and(' changes: '..table.concat(loose,'; '))or'')
end
function M.reset_for_tests()
    for key in pairs(definitions)do definitions[key]=nil end
    for index=#order,1,-1 do order[index]=nil end
end
return M
