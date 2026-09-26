local b=require('hd2runtime/core/bytes')
local p=require('hd2runtime/schemas/current')
local regions={
    {base=0x100000,size=p.entity_region_size},
    {base=0x4000000,size=0x18000},
    {base=0x5000000,size=0xD000},
    {base=0x6000000,size=0x14000},
    {base=0x10000000,size=0x3800000,type=0x1000000},
}
local runtime={mode='fixture',reads=0}
function runtime.module(name)return name or 'exe'end
function runtime.module_hash(name)return name=='exe' and p.exe_sha or p.dll_sha end
function runtime.address()return 0x10000000 end
function runtime.system_info()return 4096,0x13800000 end
function runtime.query(at)
    local previous=65536
    for _,r in ipairs(regions)do
        if at<r.base then return {base=previous,size=r.base-previous,allocation_base=0,state=0x10000,type=0,protect=0}end
        if at<r.base+r.size then return {base=r.base,size=r.size,allocation_base=r.base,state=0x1000,type=r.type or 0x20000,protect=2}end
        previous=r.base+r.size
    end
    error('query outside fixture')
end
function runtime.read(at,n)
    runtime.reads=runtime.reads+1
    for _,s in ipairs(spans)do
        if at>=s.at and at+n<=s.at+#s.bytes then return s.bytes:sub(at-s.at+1,at-s.at+n)end
    end
    error('read outside sparse fixture '..at..'/'..n)
end
local function replace(at,bytes)
    for _,s in ipairs(spans)do
        if at>=s.at and at+#bytes<=s.at+#s.bytes then
            local off=at-s.at
            s.bytes=s.bytes:sub(1,off)..bytes..s.bytes:sub(off+#bytes+1)
            return
        end
    end
    error('mutation outside fixture')
end
local function u32(n)return string.char(n%256,math.floor(n/256)%256,math.floor(n/65536)%256,math.floor(n/16777216)%256)end
local function u64(n)return u32(n%4294967296)..u32(math.floor(n/4294967296))end
local hd2=require('hd2runtime/api/session').new(runtime,function()end)
local targets=require('hd2runtime/examples/known_values')
local function finish(job)
    for _=1,10000 do if job.step()then return job end end
    error('fixture scheduler did not terminate')
end
local function read(t)return finish(hd2.read{targets=t or targets})end
