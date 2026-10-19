-- Process-wide control for the 0.40.0 application optimizations: shared discovery walks, decoded entity/index caches,
-- the 2 MiB read slice, sleeping ensures (the scheduler skips their ticks; the editor may pause their verification),
-- the per-update write-gate budget and the enemy capture's resource filter.
-- OFF by default since 0.40.1 (the user's decision of 2026-10-19): off is the 0.31 behaviour. F10 > Settings
-- "Faster application (0.40.0)" saves the choice (runtime/runtime_settings.lua). Both modes keep native ownership
-- checks and transaction snapshots.
local M={}
local enabled=false
local clearers={}
function M.enabled()return enabled end
function M.on_change(key,clear)clearers[key]=clear end
function M.configure(value)
    if value==nil then return enabled end
    assert(type(value)=='boolean','application optimizations must be a boolean')
    if value~=enabled then
        enabled=value
        for _,clear in pairs(clearers)do clear()end
    end
    return enabled
end
return M
