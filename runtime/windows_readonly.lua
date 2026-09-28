-- Read-only adapter. It intentionally declares no write or protection-changing API.
local win32 = require('hd2runtime/runtime/windows_ffi')
local ffi, kernel, bcrypt = win32.ffi, win32.kernel, win32.bcrypt

local function create_runtime()
    local process = kernel.GetCurrentProcess()
    local runtime = {mode="live"}
    function runtime.address(handle) return tonumber(ffi.cast("uintptr_t",handle)) end

    function runtime.module(name)
        local handle = kernel.GetModuleHandleA(name)
        if handle == nil then return nil end
        return handle
    end

    local function finish_hash(feed)
        local algorithm, hash = ffi.new('void *[1]'), ffi.new('void *[1]')
        local ok, result = pcall(function()
            local sha256 = ffi.new('uint16_t[7]', {83,72,65,50,53,54,0})
            assert(bcrypt.BCryptOpenAlgorithmProvider(algorithm,sha256,nil,0)==0,
                'SHA-256 provider unavailable')
            assert(bcrypt.BCryptCreateHash(algorithm[0],hash,nil,0,nil,0,0)==0,
                'SHA-256 initialization failed')
            feed(hash[0])
            local digest = ffi.new('uint8_t[32]')
            assert(bcrypt.BCryptFinishHash(hash[0],digest,32,0)==0,
                'SHA-256 finalization failed')
            return (ffi.string(digest,32):gsub('.',function(char)
                return string.format('%02X',char:byte())
            end))
        end)
        if hash[0] ~= nil then bcrypt.BCryptDestroyHash(hash[0]) end
        if algorithm[0] ~= nil then bcrypt.BCryptCloseAlgorithmProvider(algorithm[0],0) end
        if not ok then error(result) end
        return result
    end

    function runtime.sha256(bytes)
        return finish_hash(function(hash)
            assert(bcrypt.BCryptHashData(hash,bytes,#bytes,0)==0,'SHA-256 update failed')
        end)
    end

    function runtime.module_hash(module)
        local path = ffi.new('uint16_t[32768]')
        local length = kernel.GetModuleFileNameW(module,path,32768)
        assert(length>0 and length<32768,'cannot resolve module filename')
        local file = kernel.CreateFileW(path,0x80000000,7,nil,3,0,nil)
        assert(file ~= ffi.cast('void *',-1),'cannot open module file')
        local ok, result = pcall(function()
            return finish_hash(function(hash)
                local buffer,count=ffi.new('uint8_t[1048576]'),ffi.new('uint32_t[1]')
                repeat
                    assert(kernel.ReadFile(file,buffer,1048576,count,nil)~=0,'module read failed')
                    if count[0]~=0 then
                        assert(bcrypt.BCryptHashData(hash,buffer,count[0],0)==0,'SHA-256 update failed')
                    end
                until count[0]==0
            end)
        end)
        kernel.CloseHandle(file)
        if not ok then error(result) end
        return result
    end

    local region = ffi.new('HD2RuntimeMemoryRegion[1]')
    function runtime.query(address)
        if kernel.VirtualQuery(ffi.cast('const void *',address),region,
            ffi.sizeof(region[0])) ~= ffi.sizeof(region[0]) then
            return nil,tonumber(kernel.GetLastError())
        end
        return {base=tonumber(ffi.cast('uintptr_t',region[0].base)),
            allocation_base=tonumber(ffi.cast('uintptr_t',region[0].allocation_base)),
            size=tonumber(region[0].size),state=tonumber(region[0].state),
            protect=tonumber(region[0].protection),type=tonumber(region[0].type)}
    end

    function runtime.read(address,size)
        local buffer,count=ffi.new('uint8_t[?]',size),ffi.new('size_t[1]')
        if kernel.ReadProcessMemory(process,ffi.cast('const void *',address),
            buffer,size,count)==0 then
            return nil,tonumber(kernel.GetLastError()),tonumber(count[0])
        end
        if count[0]~=size then return nil,'short read',tonumber(count[0]) end
        return ffi.string(buffer,size)
    end

    function runtime.system_info()
        local info=ffi.new('HD2RuntimeSystemInfo[1]')
        win32.get_system_info(info)
        return tonumber(info[0].page_size),
            tonumber(ffi.cast('uintptr_t',info[0].maximum_address))+1
    end
    function runtime.monotonic_time() return tonumber(kernel.GetTickCount64())/1000 end
    local counter,frequency=ffi.new('int64_t[1]'),ffi.new('int64_t[1]')
    kernel.QueryPerformanceFrequency(frequency)
    local ticks_per_second=tonumber(frequency[0])
    function runtime.precise_time()
        kernel.QueryPerformanceCounter(counter)
        return tonumber(counter[0])/ticks_per_second
    end
    require('hd2runtime/runtime/metrics').set_clock(runtime.precise_time)
    function runtime.ensure_directory(path)
        assert(type(path)=='string'and#path>0,'directory path required')
        local normalized=path:gsub('/','\\'):gsub('\\+$','')
        local prefix=normalized:match('^%a:\\')and normalized:sub(1,3)or''
        local cursor=prefix
        for part in normalized:sub(#prefix+1):gmatch('[^\\]+')do
            cursor=cursor==''and part or cursor..(cursor:sub(-1)=='\\'and''or'\\')..part
            if kernel.CreateDirectoryA(cursor,nil)==0 then
                local error_code=tonumber(kernel.GetLastError())
                assert(error_code==183,'cannot create snapshot directory; error='..error_code)
            end
        end
        return normalized
    end
    return runtime
end
return create_runtime
