local M={}
local sink,attempted
-- The diagnostics switch (hd2.custom_stratagem.verbose): high-frequency development lines (per-shell conversions, the
-- Pelican cadence samples, peer-state internals) are written only while it is on; lifecycle lines always are.
M.debug=false
function M.verbose(on)M.debug=on==true end
-- Emits only with the diagnostics switch on.
function M.detail(message)if M.debug then M.emit(message)end end
-- A repeating line (r44: the logs had grown large): whether its occurrence under `key` is written: the first `first`,
-- then every `every`th if given, all of them with the diagnostics switch on. Counted for the session.
local samples={}
function M.sample(key,first,every)
    local n=(samples[key]or 0)+1
    samples[key]=n
    return M.debug or n<=first or(every~=nil and n%every==0)
end
function M.reset_samples()samples={}end
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
