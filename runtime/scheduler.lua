-- Preserve the preceding update callback and all its return values.
local M={}
local watches={}
local callback,original
local unpack=unpack
local function pack(...)return {n=select('#',...),...}end
local function tick(dt)
    for i=#watches,1,-1 do
        local watch=watches[i]
        local ok,why=pcall(watch.tick,dt)
        if not ok then
            watch.cancel()
            require('hd2runtime/runtime/log').emit('[HD2Runtime] scheduler rejected: '..tostring(why))
        end
        if watch.status=='cancelled' or watch.status=='rejected' or watch.status=='complete' then table.remove(watches,i)end
    end
    if #watches==0 and update==callback then update=original;callback=nil end
end
function M.attach(watch)
    watches[#watches+1]=watch
    if not callback then
        original=update
        callback=function(dt,...)
            local result=original and pack(original(dt,...)) or {n=0}
            tick(type(dt)=='number' and dt>=0 and dt<10 and dt or 0)
            return unpack(result,1,result.n)
        end
        update=callback
    end
    return watch
end
return M
