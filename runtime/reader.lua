-- Internal capability: reads only. Every read checks allocation ownership again.
local M={}
local function safe(n)return type(n)=='number' and n>=0 and n%1==0 and n<=9007199254740991 end
function M.new(runtime)
    local self={queries=0,bytes=0,snapshots={}}
    local operations,tick_bytes=0,0
    local function pace(n)
        if operations>=64 or tick_bytes+n>65536 then
            coroutine.yield();operations,tick_bytes=0,0
        end
        operations=operations+1;tick_bytes=tick_bytes+n
    end
    local function query(at)
        assert(safe(at),'invalid query address')
        self.queries=self.queries+1
        assert(self.queries<=100000,'metadata query budget exceeded')
        local r=assert(runtime.query(at),'memory query failed')
        assert(safe(r.base) and safe(r.size) and safe(r.base+r.size) and r.size>0
            and r.base<=at and r.base+r.size>at and safe(r.allocation_base),'invalid region extent')
        return r
    end
    function self.query(at)pace(0);return query(at)end
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
                and (r.protect==2 or r.protect==4 or r.protect==8 or r.protect==0x20
                    or r.protect==0x40 or r.protect==0x80),'read ownership/protection changed')
            local n=math.min(remaining,65536,r.base+r.size-at)
            self.bytes=self.bytes+n
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
