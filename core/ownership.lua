-- Conflict rule shared by every typed write domain.
--
-- A guarded write may replace only the reviewed baseline (`expected`) or bytes that are
-- already desired. An option-bound ensure additionally owns the exact bytes it verified
-- live on its previous successful run (`change.owned`), so moving a setting from one
-- value to another is a transition, not a conflict. Anything else is a third-party value.
local metrics=require('hd2runtime/runtime/metrics')
local b=require('hd2runtime/core/bytes')
local M={}
-- A readable value for the conflict message: the declared value when it is plain, else the bytes decoded by the
-- field's storage, else hex. Never an address.
local function text(value)
    if type(value)=='number'or type(value)=='string'or type(value)=='boolean'then return tostring(value)end
    if type(value)=='table'then
        if value.output then return tostring(value.output)end
        if value.weapon then return tostring(value.weapon)..(value.attack and':'..tostring(value.attack)or'')end
    end
    return type(value)
end
local function decoded(bytes,storage)
    if type(bytes)~='string'then return'?'end
    if(storage=='u32'or storage=='i32'or storage=='f32')and#bytes==4 or storage=='u8'and#bytes==1 then
        local ok,value=pcall(b.value,bytes,0,storage)
        if ok then return('%.9g'):format(value)end
    end
    return'0x'..b.hex(bytes)
end
-- The conflict names the target, the reviewed expect, the desired value and what was observed, and the field's
-- sharing scope, so a log shows which writer and which value collided. It also names the HD2Runtime operation (mod
-- and operation id) holding the observed bytes, or says none applied them, and every other catalogued target that
-- uses the same native record (core/shared_records.lua). The rule itself is unchanged.
local function shared_records()
    local ok,module=pcall(require,'hd2runtime/core/shared_records')
    return ok and module or nil
end
function M.describe(change,current,context)
    local descriptor=change.descriptor or{}
    local storage=(descriptor.backing or{}).storage
    local records=shared_records()
    local parts={}
    if context and context.target then parts[#parts+1]='target '..context.target
    elseif records then
        local ok,name=pcall(records.describe,descriptor)
        if ok and name then parts[#parts+1]='target '..name end
    end
    parts[#parts+1]='expected '..text(change.expect)..' ('..decoded(change.expected,storage)..')'
    parts[#parts+1]='desired '..text(change.value)..' ('..decoded(change.desired,storage)..')'
    parts[#parts+1]='observed '..decoded(current,storage)
    if type(change.owned)=='string'then parts[#parts+1]='owned '..decoded(change.owned,storage)end
    if descriptor.writeScope or descriptor.affectsMultipleWeapons~=nil then
        parts[#parts+1]='scope '..tostring(descriptor.writeScope or'unknown')
            ..(descriptor.affectsMultipleWeapons and(', shared with '..#(descriptor.sharedWithWeapons or{})
                ..' other weapons')or'')
    end
    if records then
        local ok,text=pcall(records.conflict_text,descriptor,current)
        if ok and text~=''then parts[#parts+1]=text end
    end
    return table.concat(parts,'; ')
end
-- The HD2Runtime operation whose applied bytes are `current` ({mod, kind, id, ...}), or nil: no patch, transaction,
-- plan or ensure applied them this session (or they changed since), so a mod outside HD2Runtime owns them.
function M.holder(change,current)
    local records=shared_records()
    if not records then return nil end
    local ok,holders=pcall(records.holders,change.descriptor or{},current)
    if not ok or type(holders)~='table'then return nil end
    for _,item in ipairs(holders)do if item.holds then return item end end
    return nil
end
-- Who owns `current`: 'vanilla' (the reviewed baseline), 'runtime' (bytes an HD2Runtime operation applied: owner is
-- its mod, operation its id) or 'foreign' (owner 'unknown': a mod outside HD2Runtime).
function M.state(change,current)
    if current==change.expected then return 'vanilla'end
    local holder=M.holder(change,current)
    if holder then return 'runtime',holder.mod,holder.id end
    return 'foreign','unknown'
end
-- The marker every refusal of a value owned by an unknown mod carries (results and logs: owner=unknown).
M.FOREIGN_MARKER='owner: unknown mod'
function M.foreign(reason)return type(reason)=='string'and reason:find(M.FOREIGN_MARKER,1,true)~=nil end
-- A rejected operation's result: owner='unknown' when the refusal was a value owned by an unknown mod.
function M.annotate(result,reason)
    if type(result)=='table'and M.foreign(reason)then result.owner='unknown';result.foreign=true end
    return result
end
-- Returns the bytes the guarded transaction must find before writing.
function M.expected(change,current,label,context)
    -- hd2.inspect (api/inspect.lua): a read-only pass records what it found and never writes.
    if type(change.inspect)=='table'then
        local found=change.inspect
        found[#found+1]={current=current,expected=change.expected,label=label,context=context}
        return change.expected
    end
    if current==change.expected or current==change.desired then return change.expected end
    if type(change.owned)=='string'and current==change.owned then
        metrics.count('options.owned_transitions')
        return current
    end
    local ok,detail=pcall(M.describe,change,current,context)
    -- Nobody in HD2Runtime holds these bytes: a mod outside HD2Runtime changed this value. Only this value is
    -- refused; it is remembered and logged once (core/foreign_values.lua).
    local foreign=M.holder(change,current)==nil
    if foreign then
        pcall(function()
            local storage=((change.descriptor or{}).backing or{}).storage
            local records=shared_records()
            local target=context and context.target
            if not target and records then
                local found,name=pcall(records.describe,change.descriptor or{})
                target=found and name or nil
            end
            local field=tostring(label or change.field)
            -- records.describe ends with the catalogue's field id (an attack's own alias of the field, too)
            if target and not(context and context.target)then target=target:match('^(.*) %S+$')or target end
            require('hd2runtime/core/foreign_values').note({target=target,field=field,
                observed=decoded(current,storage),expected=text(change.expect)})
        end)
    end
    error('CONFLICT: '..tostring(label or change.field)..' is neither expected nor desired'
        ..(ok and' ('..detail..(foreign and'; '..M.FOREIGN_MARKER..', not HD2Runtime'or'')..')'
            or(foreign and' ('..M.FOREIGN_MARKER..', not HD2Runtime)'or'')),0)
end
return M
