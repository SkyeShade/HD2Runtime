-- Process-wide gate for guarded operations (patch, transaction, plan).
--
-- A guarded operation captures shared native tables over many frames and later
-- re-verifies them before writing. If another mod's operation wrote into one of
-- those tables in between, the first one correctly failed closed, so independent
-- mods could reject each other at startup. Only one operation may therefore be
-- between its first read and its final write/verify at a time; others queue.
-- Steady-state verification is read-only and synchronous and needs no gate.
local metrics=require('hd2runtime/runtime/metrics')
local application_mode=require('hd2runtime/runtime/application_mode')
local M={}
local holder,last_acquired_serial
function M.acquire(owner)
    if holder==nil then
        local scheduler=package.loaded['hd2runtime/runtime/scheduler']
        local serial=scheduler and scheduler.serial()
        -- Budget a burst as a whole, not 600 independent minimum read slices. Always admit one operation per
        -- update so unrelated recurring work cannot starve pending edits. Existing holders must keep progressing.
        -- Only with the application optimizations on (runtime/application_mode.lua); off, as in 0.31.
        if serial and last_acquired_serial==serial and application_mode.enabled()then
            local spent=scheduler.tick_seconds()
            if spent and spent>=0.001 then return false end
        end
        last_acquired_serial=serial
        holder=owner;metrics.count('exclusive.acquisitions');return true
    end
    if holder==owner then return true end
    metrics.count('exclusive.queued_ticks')
    return false
end
function M.release(owner)if holder==owner then holder=nil end end
function M.busy()return holder~=nil end
return M
