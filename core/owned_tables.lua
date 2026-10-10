-- Component tables HD2Runtime ITSELF moved (EXPERIMENTAL; branch exp/multi-beam only: runtime/experiment_beam_table.lua).
-- Empty unless an experiment made one live, so every capture reads exactly as before.
--
-- core/component_tables.lua refuses a component whose slot ([manager + 0xF12478 + 8 x index]) is not the entity
-- allocation's own table: another program moved it, and HD2Runtime never writes to a table the game no longer reads.
-- An entry here is the one exception: the exact pointer HD2Runtime stored itself, to a private, never-freed copy it
-- built from the file's own table. An entry names the component, the copy's table address (the value the slot holds),
-- the copy's allocation (base and size: one committed private page), the ORIGINAL table (the entity allocation's own,
-- which the slot held before) and the copy's record count (the file's records plus the Runtime-owned ones appended).
-- The guard accepts a moved slot only when it equals `table` AND the capture's own in-place table equals `original`;
-- any other value of any slot is still foreign and refused. core/entity_catalog.lua then reads that component's rows
-- and records from the copy, so typed writes land where the game reads.
--
-- Kept in _G: a reloaded module must still know the pointer it stored (the copy outlives every Lua module).
local KEY='HD2RuntimeOwnedTablesV1'
local M={}
local function store()
    local s=rawget(_G,KEY)
    if not s then s={};rawset(_G,KEY,s)end
    return s
end
local function copy(t)local out={}for k,v in pairs(t)do out[k]=v end return out end
local function address(v)return type(v)=='number'and v>0 and v<=9007199254740991 and v%1==0 end

-- entry = {owner, index, table, allocation, size, original, records}.
function M.set(component,entry)
    assert(type(component)=='string'and component:match('ComponentData$'),'owned table component')
    assert(type(entry)=='table'and type(entry.owner)=='string'and type(entry.index)=='number'
        and address(entry.table)and address(entry.allocation)and address(entry.original)
        and type(entry.size)=='number'and entry.size>0 and entry.size<=65536 and entry.size%4096==0
        and entry.table>entry.allocation and entry.table<entry.allocation+entry.size
        and type(entry.records)=='number'and entry.records>0 and entry.records%1==0,'owned table entry')
    store()[component]=copy(entry)
end
function M.clear(component)store()[component]=nil end
function M.get(component)
    local e=store()[component]
    return e and copy(e)or nil
end
function M.active()return next(store())~=nil end
-- The entry when `pointer` is exactly HD2Runtime's own copy of a table whose in-place original is `original`.
function M.accepts(component,pointer,original)
    local e=store()[component]
    if e and e.table==pointer and e.original==original then return copy(e)end
    return nil
end
-- Tests only.
function M.reset()rawset(_G,KEY,nil)end
return M
