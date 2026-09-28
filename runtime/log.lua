local M={}
local sink,attempted
function M.emit(message)
    require('hd2runtime/runtime/metrics').count('log.lines')
    pcall(print,message)
    if not attempted then
        attempted=true
        local ok,result=pcall(function()
            assert(CowboyBingusModLoader and CowboyBingusModLoader.open_log,'Bingus logging unavailable')
            return CowboyBingusModLoader.open_log('HD2Runtime.log')
        end)
        if ok then sink=result else pcall(print,'[HD2Runtime] log unavailable: '..tostring(result))end
    end
    if sink then
        local ok,why=pcall(function()sink:write(message..'\n');if sink.flush then sink:flush()end end)
        if not ok then pcall(print,'[HD2Runtime] log write failed: '..tostring(why));sink=nil end
    end
end
return M
