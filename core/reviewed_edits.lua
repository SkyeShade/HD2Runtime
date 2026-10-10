-- Reviewed in-place edits of the entity file that HD2Runtime ITSELF made (the beam conversion, runtime/beam_conversion.lua;
-- the dev-only experiments runtime/experiment_*.lua, not shipped). Empty unless one applied an edit, so every capture
-- reads exactly as before.
--
-- An entry names one entity resource and the exact state the Runtime left it in: its whole membership list (bytes) and
-- the component index rows it owns. core/entity_catalog.lua consults it per candidate:
--   * the list bytes and every named row exactly as recorded: the diagnostics the edit causes by design
--     ('<component> membership absent' for the components in `absent`) are the Runtime's own and dropped, and the
--     components in `refuse` are refused with their reason (a dormant ProjectileWeapon record, the experiment's own
--     BeamWeapon record): every other component of that entity reads and writes as before;
--   * any third state (another list, another row): a diagnostic, so every write to that entity is refused (foreign).
local M={}
local edits={}      -- resource ('0x%016X') -> entry

local function copy(t)local out={}for k,v in pairs(t or{})do out[k]=v end return out end

-- entry = {owner, stage, membership (exact list bytes), rows = {[component] = {row, record}}, absent = {[component] =
-- true}, refuse = {[component] = reason}}.
function M.set(resource,entry)
    assert(type(resource)=='string'and resource:match('^0x%x+$')and#resource==18,'reviewed edit resource')
    assert(type(entry)=='table'and type(entry.owner)=='string'and type(entry.stage)=='string'
        and type(entry.membership)=='string'and#entry.membership>=2 and#entry.membership%2==0,'reviewed edit entry')
    for name,reason in pairs(entry.refuse or{})do
        assert(type(name)=='string'and type(reason)=='string','reviewed edit refusal')
    end
    edits[resource]={owner=entry.owner,stage=entry.stage,membership=entry.membership,rows=copy(entry.rows),
        absent=copy(entry.absent),refuse=copy(entry.refuse)}
end
function M.clear(resource)edits[resource]=nil end
function M.get(resource)
    local e=edits[resource]
    if not e then return nil end
    return {owner=e.owner,stage=e.stage,membership=e.membership,rows=copy(e.rows),absent=copy(e.absent),
        refuse=copy(e.refuse)}
end
function M.active()return next(edits)~=nil end
function M.reset()edits={}end

-- core/entity_catalog.lua: candidate (its resourceHash, ownership and diagnostics) and members (its exact membership
-- list bytes from the entity map). Adjusts the candidate in place; no effect without an entry.
function M.review(candidate,members)
    local e=edits[candidate.resourceHash]
    if not e then return end
    local function foreign(what)
        candidate.diagnostics[#candidate.diagnostics+1]=('the HD2Runtime experiment edit of this entity (%s, %s) is not '
            ..'in its recorded state (%s): another change; every write to it is refused'):format(e.owner,e.stage,what)
    end
    if members~=e.membership then return foreign('membership list')end
    for name,row in pairs(e.rows)do
        local identity=candidate.ownership[name]
        if identity and(identity.indexRow~=row.row or identity.recordIndex~=row.record)then
            return foreign(name..' index row')
        end
    end
    local kept={}
    for _,d in ipairs(candidate.diagnostics)do
        local name=type(d)=='string'and d:match('^(%S+) membership absent$')
        if not(name and e.absent[name])then kept[#kept+1]=d end
    end
    candidate.diagnostics=kept
    candidate.refused=copy(e.refuse)
    candidate.reviewed_edit=e.owner..' '..e.stage
end
return M
