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
    function runtime.write(address,bytes)
        assert(type(address)=='number' and address>0 and address<=9007199254740991
            and type(bytes)=='string' and (#bytes==1 or #bytes==4 or #bytes==8 or #bytes==12)
            and (#bytes==1 or address%4==0),
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
    return runtime
end
return M
