-- Process-wide gate for guarded operations (patch, transaction, plan).
--
-- A guarded operation captures shared native tables over many frames and later
-- re-verifies them before writing. If another mod's operation wrote into one of
-- those tables in between, the first one correctly failed closed, so independent
-- mods could reject each other at startup. Only one operation may therefore be
-- between its first read and its final write/verify at a time; others queue.
-- Steady-state verification is read-only and synchronous and needs no gate.
local metrics=require('hd2runtime/runtime/metrics')
local M={}
local holder
function M.acquire(owner)
    if holder==nil then holder=owner;metrics.count('exclusive.acquisitions');return true end
    if holder==owner then return true end
    metrics.count('exclusive.queued_ticks')
    return false
end
function M.release(owner)if holder==owner then holder=nil end end
function M.busy()return holder~=nil end
return M
