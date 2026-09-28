-- Preserve the preceding update callback and all its return values.
local metrics=require('hd2runtime/runtime/metrics')
local M={}
local watches={}
local callback,original
local function tick(dt)
    metrics.count('scheduler.ticks')
    local started=metrics.now()
    for i=#watches,1,-1 do
        local watch=watches[i]
        local ok,why=pcall(watch.tick,dt)
        if not ok then
            watch.cancel()
            require('hd2runtime/runtime/log').emit('[HD2Runtime] scheduler rejected: '..tostring(why))
        end
        if watch.status=='cancelled' or watch.status=='rejected' or watch.status=='complete'
            or watch.status=='unavailable' then table.remove(watches,i)end
    end
    if #watches==0 and update==callback then update=original;callback=nil end
    metrics.elapsed('scheduler.tick',started)
end
function M.active()return #watches end
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
