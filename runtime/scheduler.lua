-- Preserve the preceding update callback and all its return values.
local metrics=require('hd2runtime/runtime/metrics')
local diagnostics=require('hd2runtime/runtime/diagnostics')
local perf=require('hd2runtime/runtime/perf_watch')
local telemetry=diagnostics.telemetry_state
local M={}
local watches={}
local callback,original
-- Non-zero while a tick runs: the engine calls update(dt) on the game thread, and every callback, timer and keybind
-- runs from inside it. Native game calls that must run on that thread check M.in_update().
local depth=0
-- The precise clock (runtime/metrics.lua) when the running tick started; nil outside a tick or without a clock.
local tick_started
-- The number of the running update (outer tick); M.serial() is nil outside one. Caches valid for one update key on it.
local serial=0
-- A watch's label for runtime/perf_watch.lua: its own (perf_label), else the module its tick function is defined in.
local function describe_watch(watch)
    if watch.perf_label then return watch.perf_label end
    local info=debug and debug.getinfo and type(watch.tick)=='function'and debug.getinfo(watch.tick,'S')
    local source=info and tostring(info.short_src):gsub('^.-(hd2runtime/)','%1'):gsub('%.lua$','')
    return 'update of '..(source or'a watch')
end
local function tick(dt)
    metrics.count('scheduler.ticks')
    local started=metrics.now()
    if depth==0 then tick_started=started;serial=serial+1 end
    depth=depth+1
    for i=#watches,1,-1 do
        local watch=watches[i]
        local timed=perf.begin()
        local ok,why=pcall(watch.tick,dt)
        perf.finish(timed,watch.perf_owner or'HD2Runtime',watch,describe_watch)
        if not ok then
            watch.cancel()
            require('hd2runtime/runtime/log').emit('[HD2Runtime] scheduler rejected: '..tostring(why))
        end
        if watch.status=='cancelled' or watch.status=='rejected' or watch.status=='complete'
            or watch.status=='unavailable' then table.remove(watches,i)end
    end
    depth=depth-1
    if depth==0 then tick_started=nil;perf.update(dt)end
    if #watches==0 and update==callback then update=original;callback=nil end
    metrics.elapsed('scheduler.tick',started)
    if telemetry.enabled then diagnostics.tick(dt,#watches)end
end
function M.active()return #watches end
function M.in_update()return depth>0 end
function M.serial()return depth>0 and serial or nil end
-- Seconds the Runtime has spent in the running tick so far (every watch ticked before the caller), or nil outside a
-- tick or without a precise clock. runtime/reader.lua sizes a read slice by it.
function M.tick_seconds()
    if depth==0 or not tick_started then return nil end
    local now=metrics.now()
    return now and now-tick_started or nil
end
-- Runs after the preceding callback and passes its results through unchanged
-- without allocating a table every frame.
local function after(dt,...)
    tick(type(dt)=='number' and dt>=0 and dt<10 and dt or 0)
    return ...
end
function M.attach(watch)
    watches[#watches+1]=watch
    if not callback then
        original=update
        callback=function(dt,...)
            if original then return after(dt,original(dt,...))end
            return after(dt)
        end
        update=callback
    end
    return watch
end
return M
