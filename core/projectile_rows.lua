-- Runtime-owned custom projectile rows: the hybrid-row policy (docs/custom-projectile-rows.md).
--
-- A custom row is a byte-for-byte clone of a vanilla ProjectileInfo row. It keeps the vanilla base ProjectileType at
-- +0 and may differ from its base only in members SpawnProjectile copies into the spawned projectile
-- (COPIED_AT_SPAWN). The game reads every other member again later through the stored vanilla type (LATE_LOOKUP), on
-- the weapon's fire path through the weapon's configured type (FIRE_PATH_LOOKUP), or its use is not proven either way
-- (UNKNOWN), so each of those must stay equal to the base row. domains/projectile_rows.lua is the generated member
-- policy with its evidence. This module is pure: rows are Lua strings, nothing reads or writes memory.
local b=require('hd2runtime/core/bytes')
local domain=require('hd2runtime/domains/projectile_rows')
local M={}
M.SIZE=domain.row.size
M.CLASSES=domain.classes
local TYPE_COUNT=domain.table.typeCount

local members=domain.members
local copied_by_label,copied_by_offset={},{}
local permitted={}   -- byte offset -> true for bytes of COPIED_AT_SPAWN members
for _,entry in ipairs(members)do
    if entry.class=='COPIED_AT_SPAWN'then
        assert(entry.mask==nil,'a copied member is a whole member')
        copied_by_offset[entry.offset]=entry
        if entry.label then copied_by_label[entry.label]=entry end
        for offset=entry.offset,entry.offset+entry.width-1 do permitted[offset]=true end
    end
end

local function hex_offset(offset)return string.format('+0x%X',offset)end
local function name(entry)
    local text=hex_offset(entry.offset)
    if entry.mask then text=text..string.format(' mask 0x%X',entry.mask)end
    if entry.label then text=text..' '..entry.label end
    return text
end
M.name=name

-- The policy entries covering a byte offset (a bitfield word has one entry per named bit).
function M.entries(offset)
    local found={}
    for _,entry in ipairs(members)do
        if offset>=entry.offset and offset<entry.offset+entry.width then found[#found+1]=entry end
    end
    return found
end
-- A COPIED_AT_SPAWN member by label or offset, or nil and why that member cannot differ from its base.
function M.copied(member)
    local entry=type(member)=='string'and copied_by_label[member]or type(member)=='number'and copied_by_offset[member]
    if entry then return entry end
    if type(member)=='number'then
        local covering=M.entries(member)
        local first=covering[1]
        if first then
            return nil,name(first)..' is '..first.class..' ('..first.reason..')'
        end
    end
    return nil,tostring(member)..' is not a member SpawnProjectile copies (COPIED_AT_SPAWN)'
end

-- Semantic component descriptors (domains/projectile_rows.lua components: ProjectileVisual, ProjectileDamage,
-- ProjectileImpactExplosion, ProjectileBallistics). A component owns only whole, labelled COPIED_AT_SPAWN members;
-- composing it copies exactly those members from its donor's row and nothing else.
local components,UNIT={},nil
M.COMPONENT_ORDER={}
for _,entry in ipairs(members)do if entry.label=='unit'then UNIT=entry end end
for _,component in ipairs(domain.components or{})do
    for _,member in ipairs(component.members)do
        local entry=copied_by_offset[member.offset]
        assert(entry and entry.label==member.label and entry.width==member.width,
            'component '..component.id..' owns '..tostring(member.label)..', which is not a COPIED_AT_SPAWN member')
    end
    components[component.id]=component
    M.COMPONENT_ORDER[#M.COMPONENT_ORDER+1]=component.id
end
function M.component(id)return components[id]end

local function row_string(value,label)
    return type(value)=='string'and#value==M.SIZE,label..' must be a '..M.SIZE..'-byte ProjectileInfo row'
end
local function valid_type(kind)return type(kind)=='number'and kind>0 and kind<TYPE_COUNT and kind%1==0 end

-- The complete vanilla row, unchanged: the only way a custom row starts. Returns the clone, or nil, code, reason.
function M.clone(base_row,base_type)
    local ok,why=row_string(base_row,'the base row')
    if not ok then return nil,'INVALID_BASE_ROW',why end
    if not valid_type(base_type)then return nil,'INVALID_BASE_TYPE','the base must be a vanilla ProjectileType'end
    if b.u32(base_row,0)~=base_type then
        return nil,'INVALID_BASE_ROW','the base row carries type '..b.u32(base_row,0)..', not '..base_type
    end
    -- Lua strings are values: the clone is a copy of every byte, and later changes never touch base_row.
    return base_row:sub(1,M.SIZE)
end

-- The changes one component makes: exactly its owned members, each taken from the donor row, after the component's
-- constraints hold against the base row. Returns {{member, bytes, label, component}, ...}, or nil, code, reason. An
-- unrecognised constraint refuses (fail closed).
function M.component_changes(id,donor_row,base_row)
    local component=components[id]
    if not component then return nil,'UNKNOWN_COMPONENT','no projectile component '..tostring(id)end
    local ok,why=row_string(donor_row,'the donor row')
    if not ok then return nil,'INVALID_ROW',why end
    ok,why=row_string(base_row,'the base row')
    if not ok then return nil,'INVALID_ROW',why end
    for _,constraint in ipairs(component.constraints or{})do
        if constraint=='donor_unit_matches_base'then
            local at,width=UNIT.offset,UNIT.width
            if donor_row:sub(at+1,at+width)~=base_row:sub(at+1,at+width)then
                return nil,'COMPONENT_CONSTRAINT',component.name..': the donor has another unit (+0x80, LATE_LOOKUP) '
                    ..'than the base; the visible part of a unit projectile is its unit, which stays the base\'s'
            end
        else
            return nil,'COMPONENT_CONSTRAINT',component.name..': unrecognised constraint '..tostring(constraint)
        end
    end
    local changes={}
    for _,member in ipairs(component.members)do
        changes[#changes+1]={member=member.offset,label=member.label,component=id,
            bytes=donor_row:sub(member.offset+1,member.offset+member.width)}
    end
    return changes
end

-- Applies explicitly permitted changes: {{member=<label or offset>, bytes=<member-width string>}, ...}. Every member
-- must be COPIED_AT_SPAWN; anything else refuses the whole list. Returns the new row, or nil, code, reason.
function M.apply(row,changes)
    local ok,why=row_string(row,'the row')
    if not ok then return nil,'INVALID_ROW',why end
    if type(changes)~='table'then return nil,'INVALID_CHANGE','changes must be a list'end
    local out=row
    for index,change in ipairs(changes)do
        local entry,reason=M.copied(type(change)=='table'and change.member)
        if not entry then return nil,'RESTRICTED_MEMBER','change '..index..': '..tostring(reason)end
        if type(change.bytes)~='string'or#change.bytes~=entry.width then
            return nil,'INVALID_CHANGE','change '..index..' ('..name(entry)..') needs exactly '..entry.width..' bytes'
        end
        out=out:sub(1,entry.offset)..change.bytes..out:sub(entry.offset+entry.width+1)
    end
    return out
end

local function bits_differ(a,c,mask,width)
    local x,y=0,0
    for index=width,1,-1 do x=x*256+a:byte(index);y=y*256+c:byte(index)end
    local differing=0
    for bit=0,width*8-1 do
        local weight=2^bit
        if math.floor(mask/weight)%2==1 and math.floor(x/weight)%2~=math.floor(y/weight)%2 then
            differing=differing+weight
        end
    end
    return differing
end

-- Hybrid compatibility of a custom row with its live vanilla base row. Returns a report:
-- {status='VALID'|'INVALID', base_type, changes={{offset,width,label,base,value}}, violations={{offset,width,mask,
-- class,label,reason,base,value}}, summary}. VALID only when row+0 is the base type, the base row carries it, and
-- every byte outside COPIED_AT_SPAWN members equals the base row.
function M.validate(custom,base,base_type)
    local report={status='INVALID',base_type=base_type,changes={},violations={}}
    local function fail(code,reason)
        report.violations[#report.violations+1]={class=code,reason=reason}
        report.summary='INVALID: '..reason
        return report
    end
    local ok,why=row_string(custom,'the custom row')
    if not ok then return fail('INVALID_ROW',why)end
    ok,why=row_string(base,'the base row')
    if not ok then return fail('INVALID_ROW',why)end
    if not valid_type(base_type)then return fail('BASE_TYPE','the base must be a vanilla ProjectileType')end
    if b.u32(base,0)~=base_type then
        return fail('BASE_TYPE','the vanilla row of type '..base_type..' carries type '..b.u32(base,0))
    end
    if b.u32(custom,0)~=base_type then
        return fail('BASE_TYPE','row +0x0 is '..b.u32(custom,0)..', not the base type '..base_type
            ..' (every late lookup indexes the vanilla table with it)')
    end
    -- Byte comparison first: nothing outside COPIED_AT_SPAWN may differ, whatever the policy entries say.
    local stray={}
    for offset=0,M.SIZE-1 do
        if not permitted[offset]and custom:byte(offset+1)~=base:byte(offset+1)then stray[offset]=true end
    end
    for _,entry in ipairs(members)do
        local a=base:sub(entry.offset+1,entry.offset+entry.width)
        local c=custom:sub(entry.offset+1,entry.offset+entry.width)
        if a~=c then
            if entry.class=='COPIED_AT_SPAWN'then
                report.changes[#report.changes+1]={offset=entry.offset,width=entry.width,label=entry.label,
                    base=b.hex(a),value=b.hex(c)}
            elseif not entry.mask or bits_differ(a,c,entry.mask,entry.width)>0 then
                report.violations[#report.violations+1]={offset=entry.offset,width=entry.width,mask=entry.mask,
                    class=entry.class,label=entry.label,reason=entry.reason,base=b.hex(a),value=b.hex(c)}
                for offset=entry.offset,entry.offset+entry.width-1 do stray[offset]=nil end
            end
        end
    end
    for offset in pairs(stray)do
        report.violations[#report.violations+1]={offset=offset,width=1,class='UNKNOWN',
            reason='a byte no policy member explains'}
    end
    table.sort(report.violations,function(x,y)
        if(x.offset or-1)~=(y.offset or-1)then return(x.offset or-1)<(y.offset or-1)end
        return(x.mask or 0)<(y.mask or 0)
    end)
    if #report.violations>0 then
        local parts={}
        for index,item in ipairs(report.violations)do
            if index>4 then parts[#parts+1]='and '..(#report.violations-4)..' more';break end
            parts[#parts+1]=name(item)..' ('..item.class..')'
        end
        report.summary='INVALID: differs from the base in '..table.concat(parts,', ')
        return report
    end
    report.status='VALID'
    local parts={}
    for _,item in ipairs(report.changes)do parts[#parts+1]=name(item)end
    report.summary='VALID ('..#report.changes..' copied-at-spawn change'..(#report.changes==1 and''or's')
        ..(#parts>0 and(': '..table.concat(parts,', '))or'')..')'
    return report
end

-- Why a member can or cannot differ from its base: {{offset, width, mask, class, label, reason}} for every policy
-- entry covering the offset.
function M.describe(offset)
    local out={}
    for _,entry in ipairs(M.entries(offset))do
        out[#out+1]={offset=entry.offset,width=entry.width,mask=entry.mask,class=entry.class,label=entry.label,
            reason=entry.reason,class_meaning=M.CLASSES[entry.class]}
    end
    return out
end
return M
