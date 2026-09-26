-- HD2SNAP v1 header/index codec. Payload bytes remain uncompressed for direct seeks.
local bin=require('hd2runtime/core/binary')
local M={MAGIC='HD2SNAP\0',VERSION=1,HEADER_RESERVE=16*1024*1024,
    STATUS={SKIPPED_UNCOMMITTED=0,CAPTURED=1,SKIPPED_NOACCESS=2,SKIPPED_GUARD=3,
        READ_FAILED=4,SKIPPED_UNREADABLE=5}}
local function valid_hash(value)return type(value)=='string'and#value==64 and not value:find('[^0-9A-F]')end
local function string_field(value)
    value=value or'';assert(type(value)=='string','snapshot string metadata required')
    return bin.u32(#value)..value
end
local function counters(meta)
    local d=meta.diagnostics or{}
    return {'mem_private_bytes','mem_image_bytes','mem_mapped_bytes','skipped_noaccess_bytes',
        'skipped_guard_bytes','failed_read_bytes','skipped_uncommitted_bytes','skipped_unreadable_bytes'} ,d
end
function M.encode(meta,modules,regions)
    assert(valid_hash(meta.executable_sha256)and valid_hash(meta.game_dll_sha256),
        'snapshot fingerprints must be uppercase SHA-256')
    assert(#modules==2,'snapshot requires executable and game.dll metadata')
    local parts={M.MAGIC,bin.u32(M.VERSION),bin.u32(0),bin.u32(M.HEADER_RESERVE),
        bin.u32(#regions),bin.u32(#modules),bin.u32(meta.architecture_code),bin.u32(meta.page_size),
        bin.u32(0),bin.u64(meta.maximum_address),bin.u64(meta.total_virtual_bytes),
        bin.u64(meta.total_captured_bytes),bin.u64(meta.capture_unix_time),
        meta.executable_sha256,meta.game_dll_sha256,
        string_field(meta.hd2runtime_version),string_field(meta.game_version),
        string_field(meta.captured_at)}
    local names,d=counters(meta)
    for _,name in ipairs(names)do parts[#parts+1]=bin.u64(d[name]or 0)end
    for _,module in ipairs(modules)do
        assert(valid_hash(module.sha256),'invalid module fingerprint')
        parts[#parts+1]=string_field(module.name)
        parts[#parts+1]=bin.u64(module.base)
        parts[#parts+1]=bin.u64(module.size)
        parts[#parts+1]=module.sha256
    end
    for _,region in ipairs(regions)do
        parts[#parts+1]=bin.u64(region.base)
        parts[#parts+1]=bin.u64(region.allocation_base)
        parts[#parts+1]=bin.u64(region.size)
        parts[#parts+1]=bin.u32(region.state)
        parts[#parts+1]=bin.u32(region.type)
        parts[#parts+1]=bin.u32(region.protect)
        parts[#parts+1]=bin.u32(region.status)
        parts[#parts+1]=bin.u64(region.captured_length or 0)
        parts[#parts+1]=bin.u64(region.data_offset or 0)
        parts[#parts+1]=bin.u32(region.error_code or 0)
        parts[#parts+1]=bin.u32(0)
    end
    local header=table.concat(parts)
    assert(#header<=M.HEADER_RESERVE,'snapshot region index exceeds reserved header')
    header=header:sub(1,12)..bin.u32(#header)..header:sub(17)
    return header
end
function M.decode(header,file_size)
    local c=bin.cursor(header)
    assert(c.bytes(8)==M.MAGIC,'invalid snapshot magic')
    local version=c.u32();assert(version==M.VERSION,'unsupported snapshot format version: '..version)
    local header_length=c.u32();assert(header_length==#header,'snapshot header length mismatch')
    local reserve=c.u32();assert(reserve==M.HEADER_RESERVE and header_length<=reserve,'snapshot header reserve mismatch')
    local region_count,module_count=c.u32(),c.u32()
    assert(region_count<=1000000 and module_count==2,'snapshot index count bounds')
    local meta={format_version=version,header_length=header_length,header_reserve=reserve,
        region_count=region_count,module_count=module_count,architecture_code=c.u32(),page_size=c.u32()}
    assert(c.u32()==0,'snapshot header flags unsupported')
    meta.maximum_address=c.u64();meta.total_virtual_bytes=c.u64()
    meta.total_captured_bytes=c.u64();meta.capture_unix_time=c.u64()
    meta.executable_sha256=c.bytes(64);meta.game_dll_sha256=c.bytes(64)
    assert(valid_hash(meta.executable_sha256)and valid_hash(meta.game_dll_sha256),'invalid snapshot fingerprint')
    local function text()
        local length=c.u32();assert(length<=1048576,'snapshot string length bounds');return c.bytes(length)
    end
    meta.hd2runtime_version=text();meta.game_version=text();meta.captured_at=text()
    meta.diagnostics={}
    local names=counters(meta)
    for _,name in ipairs(names)do meta.diagnostics[name]=c.u64()end
    local modules={}
    for _=1,module_count do
        local module={name=text(),base=c.u64(),size=c.u64(),sha256=c.bytes(64)}
        assert(module.name~=''and valid_hash(module.sha256),'invalid snapshot module metadata')
        assert(not modules[module.name:lower()],'duplicate snapshot module')
        modules[module.name:lower()]=module
    end
    local regions={};local previous_end=0;local payload_at=reserve;local total_virtual,total_captured=0,0
    for index=1,region_count do
        local r={base=c.u64(),allocation_base=c.u64(),size=c.u64(),state=c.u32(),type=c.u32(),
            protect=c.u32(),status=c.u32(),captured_length=c.u64(),data_offset=c.u64(),
            error_code=c.u32()}
        assert(c.u32()==0,'snapshot region reserved field changed')
        assert(r.size>0 and r.base>=previous_end and r.base+r.size<=meta.maximum_address,
            'duplicate/overlapping or invalid snapshot region')
        assert(r.allocation_base<=r.base,'invalid snapshot allocation base')
        assert(r.status>=0 and r.status<=M.STATUS.SKIPPED_UNREADABLE,'invalid snapshot region status')
        assert(r.captured_length<=r.size,'snapshot captured length exceeds region')
        if r.captured_length>0 then
            assert(r.data_offset==payload_at,'non-deterministic snapshot payload index')
            assert(r.data_offset+r.captured_length<=file_size,'truncated snapshot payload')
            payload_at=payload_at+r.captured_length
        else assert(r.data_offset==0,'empty snapshot region has payload offset')end
        if r.status==M.STATUS.CAPTURED then
            assert(r.captured_length==r.size and r.error_code==0,'captured region is incomplete')
        elseif r.status==M.STATUS.READ_FAILED then
            assert(r.captured_length<r.size,'failed region recorded as complete')
        else assert(r.captured_length==0,'skipped region contains payload')end
        regions[index]=r;previous_end=r.base+r.size
        total_virtual=total_virtual+r.size;total_captured=total_captured+r.captured_length
    end
    assert(c.at==#header,'snapshot header trailing bytes')
    assert(total_virtual==meta.total_virtual_bytes and total_captured==meta.total_captured_bytes,
        'snapshot aggregate byte counts differ')
    assert(payload_at==file_size,'snapshot trailing or missing payload bytes')
    local exe=assert(modules['helldivers2.exe'],'snapshot executable module absent')
    local dll=assert(modules['game.dll'],'snapshot game.dll module absent')
    assert(exe.sha256==meta.executable_sha256 and dll.sha256==meta.game_dll_sha256,
        'snapshot module/header fingerprints differ')
    meta.executable_base=exe.base;meta.game_dll_base=dll.base
    meta.process_architecture=meta.architecture_code==0x8664 and'x86_64'or string.format('0x%X',meta.architecture_code)
    return {metadata=meta,modules=modules,regions=regions}
end
return M
