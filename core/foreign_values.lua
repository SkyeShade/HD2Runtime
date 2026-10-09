-- Values owned by an unknown mod: game data that is neither HD2Runtime's reviewed (vanilla) value nor bytes any
-- HD2Runtime patch, transaction, plan or ensure applied this session. A mod outside HD2Runtime changed them: a
-- data-file mod (patched game archives) or another program writing game memory. HD2Runtime never overwrites such a
-- value (core/ownership.lua refuses the write as a CONFLICT naming "owner: unknown mod"); it only refuses writes to
-- that value, and every other value, record and target is unaffected.
--
-- This module remembers which values were found so, for hd2.diagnostics.foreign_values() and hd2.inspect, and logs
-- each value once. No memory access, no address: the entries carry the catalogue's target and field names only.
local M={}
M.MAX=256
local entries,order={},{}
local function emit(message)
    local ok,log=pcall(require,'hd2runtime/runtime/log')
    if ok and log and log.emit then pcall(log.emit,message)end
end
-- info = {target = readable target, field = field id, observed = text, expected = text}. Returns the entry.
function M.note(info)
    if type(info)~='table'then return nil end
    local target,field=tostring(info.target or'unknown target'),tostring(info.field or'?')
    local key=target..'\0'..field
    local entry=entries[key]
    if entry then
        entry.seen=entry.seen+1;entry.observed=info.observed or entry.observed
        return entry
    end
    if #order>=M.MAX then return nil end
    entry={target=target,field=field,observed=info.observed,expected=info.expected,owner='unknown',seen=1}
    entries[key]=entry;order[#order+1]=key
    emit('[HD2Runtime] FOREIGN VALUE: '..target..' '..field..' is '..tostring(info.observed)
        ..', not HD2Runtime\'s reviewed '..tostring(info.expected)..': owner unknown mod (a mod outside HD2Runtime: '
        ..'a data-file mod or another program writing game memory). HD2Runtime leaves it as it is and refuses writes '
        ..'to this value only; every other value is unaffected')
    return entry
end
-- Every value found so, in the order found: {target, field, observed, expected, owner = 'unknown', seen}.
function M.list()
    local out={}
    for index,key in ipairs(order)do
        local e=entries[key]
        out[index]={target=e.target,field=e.field,observed=e.observed,expected=e.expected,owner=e.owner,seen=e.seen}
    end
    return out
end
-- Test hook.
function M.reset()entries,order={},{}end
return M
