-- File-backed address-space source implementing the live runtime read contract.
local bin=require('hd2runtime/core/binary')
local format=require('hd2runtime/core/snapshot_format')
local M={}
local function safe(value)return type(value)=='number'and value>=0 and value%1==0 and value<=9007199254740991 end
local function lower(value)return tostring(value):lower()end

function M.open(path,options)
    options=options or{}
    local file,why=io.open(path,'rb');assert(file,'cannot open snapshot: '..tostring(why))
    local ok,result=pcall(function()
        local size=assert(file:seek('end'));assert(size>=16,'truncated snapshot preamble')
        assert(file:seek('set',0));local preamble=assert(file:read(16))
        assert(#preamble==16,'truncated snapshot preamble')
        local c=bin.cursor(preamble);assert(c.bytes(8)==format.MAGIC,'invalid snapshot magic')
        assert(c.u32()==format.VERSION,'unsupported snapshot format version')
        local header_length=c.u32()
        assert(header_length>=16 and header_length<=format.HEADER_RESERVE and header_length<=size,
            'invalid snapshot header length')
        assert(file:seek('set',0));local header=assert(file:read(header_length))
        assert(#header==header_length,'truncated snapshot header')
        return format.decode(header,size)
    end)
    if not ok then file:close();error(result,0)end
    local parsed=result;local meta,regions,modules=parsed.metadata,parsed.regions,parsed.modules
    if not options.historical_analysis then
        if options.expected_exe_sha then assert(meta.executable_sha256==options.expected_exe_sha,
            'snapshot executable fingerprint differs from requested profile')end
        if options.expected_dll_sha then assert(meta.game_dll_sha256==options.expected_dll_sha,
            'snapshot game.dll fingerprint differs from requested profile')end
    end
    local source={mode='snapshot',path=path,metadata=meta,historical_analysis=options.historical_analysis==true}
    local function containing(address)
        local low,high=1,#regions
        while low<=high do
            local mid=math.floor((low+high)/2);local r=regions[mid]
            if address<r.base then high=mid-1
            elseif address>=r.base+r.size then low=mid+1
            else return r end
        end
        return nil,low
    end
    function source.query(address)
        if not safe(address)or address>=meta.maximum_address then return nil,'address outside snapshot' end
        local region,next_index=containing(address)
        if region then return {base=region.base,allocation_base=region.allocation_base,size=region.size,
            state=region.state,type=region.type,protect=region.protect,capture_status=region.status,
            captured_length=region.captured_length,error_code=region.error_code}end
        local next_base=regions[next_index]and regions[next_index].base or meta.maximum_address
        return {base=address,size=next_base-address,allocation_base=0,state=0x10000,type=0,protect=0,
            capture_status=format.STATUS.SKIPPED_UNCOMMITTED,captured_length=0,error_code=0}
    end
    function source.read(address,length)
        if not safe(address)or not safe(length)or address+length>meta.maximum_address then
            return nil,'snapshot read range invalid'
        end
        local region=containing(address)
        if not region then return nil,'snapshot address was not indexed' end
        if region.status~=format.STATUS.CAPTURED then
            return nil,'snapshot region was not fully captured; status='..region.status..' error='..region.error_code
        end
        if address+length>region.base+region.size then return nil,'snapshot read crosses region boundary'end
        local offset=region.data_offset+(address-region.base)
        assert(file:seek('set',offset),'snapshot seek failed')
        local bytes=file:read(length)
        if not bytes or#bytes~=length then return nil,'truncated snapshot read'end
        return bytes
    end
    function source.system_info()return meta.page_size,meta.maximum_address end
    function source.module(name)
        local module=modules[lower(name or'helldivers2.exe')]
        return module and module.base or nil
    end
    function source.address(handle)return handle end
    function source.module_hash(handle)
        for _,module in pairs(modules)do if module.base==handle then return module.sha256 end end
        return nil
    end
    function source.module_metadata(name)
        local module=modules[lower(name or'helldivers2.exe')]
        if not module then return nil end
        return {name=module.name,base=module.base,size=module.size,sha256=module.sha256}
    end
    function source.close()if file then file:close();file=nil end end
    return source
end
return M
