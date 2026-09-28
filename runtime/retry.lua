-- Bounded retry policy shared by guarded operations and observation.
--
-- An attempt is one full guarded resolution/application run that has actually
-- started (after the startup delay and after acquiring the operation gate).
-- Only failures that mean "HD2 is not ready yet" retry, and only if no bytes
-- remain changed. Everything else is deterministic for this operation and build
-- and fails on the first attempt.
local M={}
M.MAX_ATTEMPTS=6
M.DELAY_SECONDS=5
local TRANSIENT={
    -- Modules, entity region, settings table, or stratagem table not loaded yet.
    {prefix='TARGET_UNAVAILABLE:',code='TARGET_UNAVAILABLE'},
    -- Captured native data changed while the resolution was in progress; raised by
    -- the stability reread before any write.
    {text='unstable ownership/data snapshot',code='TARGET_UNSTABLE'},
}
-- Returns a transient code, or nil when the failure must be terminal.
-- `result` is the operation report when one exists; a failure that left rollback
-- incomplete or unverified is never retried.
function M.transient(reason,result)
    reason=tostring(reason)
    if result and result.rollback and result.rollback~='not_needed' and result.rollback~='verified' then
        return nil
    end
    if result and result.protection_restored==false then return nil end
    for _,item in ipairs(TRANSIENT)do
        if item.prefix and reason:find(item.prefix,1,true)then return item.code end
        if item.text and reason:find(item.text,1,true)then return item.code end
    end
    return nil
end
return M
