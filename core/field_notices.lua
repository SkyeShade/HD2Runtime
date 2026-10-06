-- One-time registration diagnostics for fields whose catalogue publishes notices: a deprecated id (charge.minimum_seconds
-- is the projectile speed multiplier, not a time) or a write the target's native code never reads (the legacy charge
-- speed ids on arc and beam weapons, the jump launch thrust on the Hover Pack). Diagnostics only: a notice never
-- changes whether or what a registration writes. Called from core/shared_records.warn_unlisted, which every patch,
-- transaction, plan and ensure registration runs.
local M={}

local warned={}
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
-- The notices of one validated change: those of the id the author named (a deprecated alias carries its own), else
-- those of the field it resolved to, plus any the validation attached to this change for this operation (the charge
-- time order).
local function notices_of(change)
    local list,owner={},change.descriptor
    local requested=change.requested_descriptor
    local descriptor=change.descriptor
    if type(requested)=='table'and type(requested.notices)=='table'then
        owner=requested
        for _,notice in ipairs(requested.notices)do list[#list+1]=notice end
    elseif type(descriptor)=='table'and type(descriptor.notices)=='table'then
        for _,notice in ipairs(descriptor.notices)do list[#list+1]=notice end
    end
    if type(change.notices)=='table'then
        for _,notice in ipairs(change.notices)do list[#list+1]=notice end
    end
    if #list==0 or type(owner)~='table'then return nil end
    return list,owner
end
-- The field instance a notice belongs to (its weapon or backpack target), so one operation id reused on two targets
-- still warns for each.
local function owner_of(descriptor)
    local target=type(descriptor.target)=='table'and descriptor.target or{}
    return tostring(descriptor.instanceKey or target.weapon or target.backpack or'')
end
-- Emits each notice once per mod, operation, field and notice kind. Returns the lines (for tests).
function M.warn(spec,kind,mod,emit)
    local lines={}
    each_change(spec,function(change,id)
        local list,descriptor=notices_of(change)
        for _,notice in ipairs(list or{})do
            local key=tostring(mod)..'|'..tostring(id)..'|'..owner_of(descriptor)..'|'..tostring(change.field)..'|'
                ..tostring(notice.kind)
            if not warned[key]then
                warned[key]=true
                local line='[HD2Runtime] '..tostring(kind)..' '..tostring(id)..' ('..tostring(mod)..'): '
                    ..string.upper(tostring(notice.kind))..': '..tostring(notice.text)
                lines[#lines+1]=line
                pcall(function()require('hd2runtime/runtime/metrics').count('field_notices.'..tostring(notice.kind))end)
                if emit then pcall(emit,line)end
            end
        end
    end)
    return lines
end
-- Test hook: forget which notices were emitted.
function M.reset()warned={}end
return M
