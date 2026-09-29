-- Loaded only by a patch-capable package when patch() is requested.
local M={}
function M.create()
    local runtime=require('hd2runtime/runtime/windows_readonly')()
    local win=require('hd2runtime/runtime/windows_ffi')
    local ffi,kernel=win.ffi,win.kernel
    if not rawget(_G,'HD2RuntimeWriteFfiV1') then
        ffi.cdef [[
            int WriteProcessMemory(void *,void *,const void *,size_t,size_t *);
            int VirtualProtect(void *,size_t,uint32_t,uint32_t *);
        ]]
        rawset(_G,'HD2RuntimeWriteFfiV1',true)
    end
    -- packed=true is only passed for byte-packed entity-delta data; it must still stay in one page.
    function runtime.write(address,bytes,packed)
        assert(type(address)=='number' and address>0 and address<=9007199254740991
            and type(bytes)=='string' and (#bytes==1 or #bytes==4 or #bytes==8 or #bytes==12)
            and (#bytes==1 or address%4==0 or (packed==true and #bytes==4 and address%4096+4<=4096)),
            'unsupported native write extent')
        local count=ffi.new('size_t[1]')
        local ok=kernel.WriteProcessMemory(kernel.GetCurrentProcess(),ffi.cast('void *',address),bytes,#bytes,count)
        return ok~=0,ok==0 and tonumber(kernel.GetLastError()) or nil,tonumber(count[0])
    end
    function runtime.protect(page,size,protection)
        assert(type(page)=='number' and page>0 and page<=9007199254740991
            and page%4096==0 and size==4096 and (protection==2 or protection==4),
            'unsupported native protection extent')
        local old=ffi.new('uint32_t[1]')
        local ok=kernel.VirtualProtect(ffi.cast('void *',page),size,protection,old)
        return ok~=0 and tonumber(old[0]) or nil,ok==0 and tonumber(kernel.GetLastError()) or nil
    end
    -- One native call, used only by core/assets after it re-proved the build, the exact code bytes of
    -- game.dll's RefcountedPackageSystem request function and the instance it passes: take one reference on
    -- one catalog package (the same call gameplay makes when a player carries the item).
    function runtime.package_request(entry,instance,id)
        assert(type(entry)=='number'and entry>0 and entry<=9007199254740991
            and type(instance)=='number'and instance>0 and instance<=9007199254740991
            and type(id)=='string'and#id==8 and id~=string.rep('\0',8),'unsupported package request')
        local ids=ffi.new('uint64_t[1]');ffi.copy(ids,id,8)
        local request=ffi.cast('void (*)(void *, const uint64_t *, uint32_t)',entry)
        request(ffi.cast('void *',instance),ids,1)
        return true
    end
    -- One native call, used only by runtime/event_world.lua after it re-proved the heal function's exact prologue
    -- bytes and that the entity is the local player's living avatar: the game's own
    -- AddHealthFraction(health manager, entity, fraction), which clamps to maximum health.
    function runtime.native_heal(entry,manager,entity,fraction)
        assert(type(entry)=='number'and entry>0 and entry<=9007199254740991
            and type(manager)=='number'and manager>0 and manager<=9007199254740991
            and type(entity)=='number'and entity>0 and entity<4294967296 and entity%1==0
            and type(fraction)=='number'and fraction>0 and fraction<=1,'unsupported heal call')
        local heal=ffi.cast('void (*)(void *, uint32_t, float)',entry)
        heal(ffi.cast('void *',manager),entity,fraction)
        return true
    end
    -- One native call, used only by runtime/event_world.lua after it re-proved the request function's exact prologue
    -- bytes, the queue headroom and that the type's settings record carries that type: the game's own
    -- RequestExplosion(queue, position, type, source, owner, creditor, ...) with the argument template the game's own
    -- callers pass (research/event-actions-F5FEE03DCFDB.json): 0, null, 1, 0, null, null, null, 0, 0.
    function runtime.native_explosion(entry,queue,x,y,z,kind,source,owner,peer_lo,peer_hi)
        local function coordinate(v)return type(v)=='number'and v==v and math.abs(v)<=100000 end
        assert(type(entry)=='number'and entry>0 and entry<=9007199254740991
            and type(queue)=='number'and queue>0 and queue<=9007199254740991
            and coordinate(x)and coordinate(y)and coordinate(z)
            and type(kind)=='number'and kind>0 and kind<0x1A7 and kind%1==0
            and type(source)=='number'and source>0 and source<4294967296 and source%1==0
            and type(owner)=='number'and owner>0 and owner<4294967296 and owner%1==0
            and type(peer_lo)=='number'and peer_lo>=0 and peer_lo<4294967296 and peer_lo%1==0
            and type(peer_hi)=='number'and peer_hi>=0 and peer_hi<4294967296 and peer_hi%1==0,'unsupported explosion call')
        local position=ffi.new('float[3]',x,y,z)
        local peer=ffi.new('uint64_t',peer_hi)*4294967296+peer_lo
        local request=ffi.cast('void (*)(void *, const float *, uint32_t, uint32_t, uint32_t, uint64_t, uint32_t, '
            ..'const float *, uint8_t, uint32_t, const uint32_t *, const float *, const float *, uint8_t, uint32_t)',entry)
        request(ffi.cast('void *',queue),position,kind,source,owner,peer,0,nil,1,0,nil,nil,nil,0,0)
        return true
    end
    return runtime
end
return M
