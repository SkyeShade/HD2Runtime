-- Bounded, failure-safe reads for event sources polled every update tick.
--
-- Reads go through the adapter's ReadProcessMemory path, so an address that is no longer mapped fails the read
-- (nil) instead of faulting. Nothing here writes. A block is a reusable slot: reading into it again replaces its
-- contents, so a hot poll allocates nothing per entity. Live adapters with read_into (windows_readonly) fill an FFI
-- buffer; other adapters (the packaged harness, offline tests) fall back to string reads.
local b=require('hd2runtime/core/bytes')
local M={}
local MAX_BLOCK=1048576

local Block={};Block.__index=Block
-- Accessors take an offset inside the block; the caller keeps offsets within block.size.
function Block:u8(o)return self.data and self.data[o]or self.bytes:byte(o+1)end
function Block:u32(o)
    if self.data then return self.cast(self.u32p,self.data+o)[0]end
    return b.u32(self.bytes,o)
end
function Block:i32(o)local v=self:u32(o);return v>=2147483648 and v-4294967296 or v end
function Block:f32(o)
    if self.data then return tonumber(self.cast(self.f32p,self.data+o)[0])end
    return b.value(self.bytes,o,'f32')
end
-- A 64-bit pointer as a number (userspace pointers are below 2^47 and exact in a double), else nil.
function Block:ptr(o)
    local lo,hi=self:u32(o),self:u32(o+4)
    if hi>0x7FFF then return nil end
    local value=lo+hi*4294967296
    return value>=65536 and value or nil
end
-- A 64-bit identity (type hash) as 16 upper-case hex digits. Allocates; use only when building payloads.
function Block:hex64(o)return string.format('%08X%08X',self:u32(o+4),self:u32(o))end
function Block:same64(o,lo,hi)return self:u32(o)==lo and self:u32(o+4)==hi end

function M.new(runtime)
    local view={runtime=runtime,reads=0,failures=0}
    local ffi_ok,ffi=pcall(require,'ffi')
    local fast=runtime.read_into and ffi_ok
    local u32p=fast and ffi.typeof('const uint32_t *')
    local f32p=fast and ffi.typeof('const float *')
    -- One string read. nil when the memory cannot be read.
    function view.read(address,size)
        if type(address)~='number'or address<65536 or size<=0 or size>MAX_BLOCK then return nil end
        view.reads=view.reads+1
        local bytes=runtime.read(address,size)
        if not bytes or#bytes~=size then view.failures=view.failures+1;return nil end
        return bytes
    end
    function view.u32(address)local s=view.read(address,4);return s and b.u32(s,0)end
    function view.pointer(address)
        local s=view.read(address,8)
        if not s then return nil end
        local lo,hi=b.u32(s,0),b.u32(s,4)
        if hi>0x7FFF then return nil end
        local value=lo+hi*4294967296
        return value>=65536 and value or nil
    end
    -- A reusable slot. Returns the block (filled) or nil when the read failed.
    function view.slot()
        local block=setmetatable({size=0,capacity=0},Block)
        if fast then block.u32p,block.f32p,block.cast=u32p,f32p,ffi.cast end
        return block
    end
    function view.fill(block,address,size)
        if type(address)~='number'or address<65536 or size<=0 or size>MAX_BLOCK then return nil end
        view.reads=view.reads+1
        if fast then
            if block.capacity<size then
                local capacity=math.max(size,256,block.capacity*2)
                block.buffer=ffi.new('uint8_t[?]',capacity);block.capacity=capacity
                block.data=ffi.cast('const uint8_t *',block.buffer)
            end
            if not runtime.read_into(address,size,block.buffer)then view.failures=view.failures+1;return nil end
        else
            local bytes=runtime.read(address,size)
            if not bytes or#bytes~=size then view.failures=view.failures+1;return nil end
            block.bytes=bytes
        end
        block.size=size;block.address=address
        return block
    end
    -- Exact code bytes at a module offset (pinned native proofs).
    function view.proves(address,hex)
        local expected=b.unhex(hex)
        return view.read(address,#expected)==expected
    end
    return view
end
return M
