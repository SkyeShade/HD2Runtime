-- Process-wide runtime work counters. Cheap increments only; no allocation or
-- formatting happens on the counting path. hd2.metrics() returns a copy.
local M={}
local counters,worst,total_time={},{},{}
local clock
function M.set_clock(fn)if type(fn)=='function'then clock=fn end end
function M.count(name,n)counters[name]=(counters[name]or 0)+(n or 1)end
function M.now()return clock and clock()or nil end
-- Record a duration measured by the caller between two M.now() samples.
function M.elapsed(name,started)
    if not started or not clock then return end
    local duration=clock()-started
    total_time[name]=(total_time[name]or 0)+duration
    if duration>(worst[name]or 0)then worst[name]=duration end
end
function M.snapshot()
    local result={counters={},worst_seconds={},total_seconds={},timed=clock~=nil}
    for key,value in pairs(counters)do result.counters[key]=value end
    for key,value in pairs(worst)do result.worst_seconds[key]=value end
    for key,value in pairs(total_time)do result.total_seconds[key]=value end
    return result
end
function M.reset()counters,worst,total_time={},{},{}end
return M
