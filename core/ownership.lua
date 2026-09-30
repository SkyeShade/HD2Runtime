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
-- sharing scope, so a log shows which writer and which value collided. The rule itself is unchanged.
function M.describe(change,current,context)
    local descriptor=change.descriptor or{}
    local storage=(descriptor.backing or{}).storage
    local parts={}
    if context and context.target then parts[#parts+1]='target '..context.target end
    parts[#parts+1]='expected '..text(change.expect)..' ('..decoded(change.expected,storage)..')'
    parts[#parts+1]='desired '..text(change.value)..' ('..decoded(change.desired,storage)..')'
    parts[#parts+1]='observed '..decoded(current,storage)
    if type(change.owned)=='string'then parts[#parts+1]='owned '..decoded(change.owned,storage)end
    if descriptor.writeScope or descriptor.affectsMultipleWeapons~=nil then
        parts[#parts+1]='scope '..tostring(descriptor.writeScope or'unknown')
            ..(descriptor.affectsMultipleWeapons and(', shared with '..#(descriptor.sharedWithWeapons or{})
                ..' other weapons')or'')
    end
    return table.concat(parts,'; ')
end
-- Returns the bytes the guarded transaction must find before writing.
function M.expected(change,current,label,context)
    if current==change.expected or current==change.desired then return change.expected end
    if type(change.owned)=='string'and current==change.owned then
        metrics.count('options.owned_transitions')
        return current
    end
    local ok,detail=pcall(M.describe,change,current,context)
    error('CONFLICT: '..tostring(label or change.field)..' is neither expected nor desired'
        ..(ok and' ('..detail..')'or''),0)
end
return M
