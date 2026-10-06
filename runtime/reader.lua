-- Internal capability: reads only. Every read checks allocation ownership again.
local metrics=require('hd2runtime/runtime/metrics')
local protection=require('hd2runtime/core/page_protection')
local M={}
-- Read pacing bounds what one resolution costs a frame; it never changes what is checked: every read re-queries its
-- region and re-proves ownership and protection right before the read, however many reads share a tick.
-- A slice (the work between two yields) may always do the base quantum, 64 queries and 64 KiB (the only pacing before
-- 0.30). Inside an update tick with a precise clock (runtime/scheduler.lua) it continues while the Runtime's work in
-- that tick, everything ticked before it included, stays under SLICE_SECONDS, up to the hard ceilings. A slow machine
-- or an already heavy tick therefore falls back to the base quantum; without a clock nothing changes.
M.QUANTUM_OPERATIONS,M.QUANTUM_BYTES=64,65536
M.SLICE_SECONDS=0.001
M.MAX_OPERATIONS,M.MAX_BYTES=1024,1048576
-- The scheduler only when it is loaded: no update tick can run without it (and offline tools that bundle the reader
-- alone, such as the SDK snapshot scanner, never load it).
local function extend(operations,bytes)
    if operations>=M.MAX_OPERATIONS or bytes>M.MAX_BYTES then return false end
    local scheduler=package.loaded['hd2runtime/runtime/scheduler']
    local spent=type(scheduler)=='table'and scheduler.tick_seconds and scheduler.tick_seconds()
    return type(spent)=='number'and spent<M.SLICE_SECONDS
end
local function safe(n)return type(n)=='number' and n>=0 and n%1==0 and n<=9007199254740991 end
function M.new(runtime)
    local self={queries=0,bytes=0,snapshots={}}
    local operations,tick_bytes=0,0
    local function pace(n)
        if (operations>=M.QUANTUM_OPERATIONS or tick_bytes+n>M.QUANTUM_BYTES)
            and not extend(operations,tick_bytes+n)then
            coroutine.yield();operations,tick_bytes=0,0
        end
        operations=operations+1;tick_bytes=tick_bytes+n
    end
    local function query(at)
        assert(safe(at),'invalid query address')
        self.queries=self.queries+1
        metrics.count('reader.queries')
        assert(self.queries<=100000,'metadata query budget exceeded')
        local r=assert(runtime.query(at),'memory query failed')
        assert(safe(r.base) and safe(r.size) and safe(r.base+r.size) and r.size>0
            and r.base<=at and r.base+r.size>at and safe(r.allocation_base),'invalid region extent')
        return r
    end
    function self.query(at)pace(0);return query(at)end
    -- Start a bounded unit of work on a fresh update tick. This lets callers
    -- isolate candidate failures with pcall without ever yielding through it.
    function self.checkpoint()
        coroutine.yield();operations,tick_bytes=0,0
    end
    function self.read(owner,offset,length,capture)
        assert(safe(offset) and safe(length) and offset+length<=owner.size,'read outside owner')
        local start,remaining,parts=offset,length,{}
        while remaining>0 do
            local at=owner.base+offset
            pace(math.min(remaining,65536))
            -- No yield is allowed between this guard and ReadProcessMemory.
            local r=query(at)
            assert(r.state==0x1000 and r.type==(owner.type or 0x20000)
                and r.allocation_base==owner.base
                and protection.readable(r.protect),'read ownership/protection changed')
            local n=math.min(remaining,65536,r.base+r.size-at)
            self.bytes=self.bytes+n
            metrics.count('reader.bytes',n)
            assert(self.bytes<=16*1024*1024,'read byte budget exceeded')
            local bytes=assert(runtime.read(at,n),'memory read failed')
            assert(#bytes==n,'short memory read')
            parts[#parts+1]=bytes;offset=offset+n;remaining=remaining-n
        end
        local bytes=table.concat(parts)
        if capture then self.snapshots[#self.snapshots+1]={owner=owner,offset=start,bytes=bytes} end
        return bytes
    end
    function self.verify()
        for _,s in ipairs(self.snapshots)do
            assert(self.read(s.owner,s.offset,#s.bytes)==s.bytes,'unstable ownership/data snapshot')
        end
    end
    return self
end
return M
