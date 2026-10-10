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
-- MEMBERSHIP LISTS HD2Runtime itself relocated (kind 'membership_list'; runtime/beam_conversion.lua, the add layout:
-- research/docs/beam-conversion-add-layout-F5FEE03DCFDB.md). An entity map row of a converted root names a list in a
-- Runtime-owned, never-freed, read-only block instead of the entity file's packed list: the row's pointer (+8) and
-- count (+16) are the only bytes written in the entity allocation. core/entity_catalog.lua validates every row's
-- pointer against the map body and refuses (stray) a row whose list lies elsewhere; an entry here is the one exception:
-- exactly this resource's row, exactly the pointer and count HD2Runtime stored, over exactly the bytes it built (the
-- catalogue reads them back from the block and compares). Any other pointer is still another program's and refused.
-- entry = {owner, row, list (address the row holds), count, bytes (the exact list bytes), allocation, size (the block),
-- original (the file list's address), original_count}.
local LISTS_KEY='HD2RuntimeOwnedListsV1'
local function lists()
    local s=rawget(_G,LISTS_KEY)
    if not s then s={};rawset(_G,LISTS_KEY,s)end
    return s
end
function M.set_list(resource,entry)
    assert(type(resource)=='string'and resource:match('^0x%x+$'),'owned list resource')
    assert(type(entry)=='table'and type(entry.owner)=='string'and type(entry.row)=='number'and entry.row>=0
        and entry.row%1==0 and address(entry.list)and address(entry.allocation)and address(entry.original)
        and type(entry.count)=='number'and entry.count>0 and entry.count<=1024 and entry.count%1==0
        and type(entry.bytes)=='string'and#entry.bytes==2*entry.count
        and type(entry.size)=='number'and entry.size>0 and entry.size%4096==0
        and entry.list>=entry.allocation and entry.list+2*entry.count<=entry.allocation+entry.size,
        'owned list entry')
    lists()[resource]=copy(entry)
end
function M.clear_list(resource)lists()[resource]=nil end
function M.get_list(resource)
    local e=lists()[resource]
    return e and copy(e)or nil
end
function M.lists_active()return next(lists())~=nil end
-- The entry when entity map row `row` of `resource` names exactly HD2Runtime's own list (pointer and count).
function M.list_accepts(resource,row,pointer,count)
    local e=lists()[resource]
    if e and e.row==row and e.list==pointer and e.count==count then return copy(e)end
    return nil
end

-- Tests only.
function M.reset()rawset(_G,KEY,nil);rawset(_G,LISTS_KEY,nil)end
return M
