-- Incremental, read-only whole-process snapshot capture for research.
local format=require('hd2runtime/core/snapshot_format')
local metadata=require('hd2runtime/domains/metadata')
local M={}
local COMMIT,PRIVATE,MAPPED,IMAGE=0x1000,0x20000,0x40000,0x1000000
local readable={[2]=true,[4]=true,[8]=true,[0x20]=true,[0x40]=true,[0x80]=true}
local function safe(n)return type(n)=='number'and n>=0 and n%1==0 and n<=9007199254740991 end
local function now(runtime)return runtime.monotonic_time and runtime.monotonic_time()or os.clock()end
local function utc()return os.date('!%Y-%m-%dT%H:%M:%SZ')end
local function stamp(value)return value:gsub('[-:]',''):gsub('Z$','Z')end
local function status_for(r,d)
    if r.state~=COMMIT then d.skipped_uncommitted_bytes=d.skipped_uncommitted_bytes+r.size;return format.STATUS.SKIPPED_UNCOMMITTED end
    if r.protect%256==1 then d.skipped_noaccess_bytes=d.skipped_noaccess_bytes+r.size;return format.STATUS.SKIPPED_NOACCESS end
    if math.floor(r.protect/256)%2==1 then d.skipped_guard_bytes=d.skipped_guard_bytes+r.size;return format.STATUS.SKIPPED_GUARD end
    if not readable[r.protect%256]then d.skipped_unreadable_bytes=d.skipped_unreadable_bytes+r.size;return format.STATUS.SKIPPED_UNREADABLE end
    if r.type==PRIVATE then d.mem_private_bytes=d.mem_private_bytes+r.size
    elseif r.type==IMAGE then d.mem_image_bytes=d.mem_image_bytes+r.size
    elseif r.type==MAPPED then d.mem_mapped_bytes=d.mem_mapped_bytes+r.size end
    return nil
end
local function default_folder(runtime)
    local localdata=assert(os.getenv('LOCALAPPDATA'),'LOCALAPPDATA unavailable')
    return assert(runtime.ensure_directory,'snapshot directory capability unavailable')(
        localdata..'\\HD2Runtime\\local_research\\snapshots')
end
local function emit_progress(emit,m,start,eligible_done,eligible_total)
    local elapsed=math.max(now(m.runtime)-start,0.001)
    local rate=m.bytes_captured/elapsed/1048576
    local remaining=math.max(eligible_total-eligible_done,0)
    local estimate=rate>0 and remaining/1048576/rate or-1
    emit(string.format('[HD2Runtime] SNAPSHOT regions_seen=%d regions_captured=%d bytes_captured=%d bytes_skipped=%d read_failures=%d elapsed_seconds=%.1f MiB_per_second=%.1f estimated_remaining=%.1f',
        m.regions_seen,m.regions_captured,m.bytes_captured,m.bytes_skipped,m.read_failures,
        elapsed,rate,estimate))
end
function M.start(runtime,emit,request)
    request=request or{};emit=emit or print
    assert(runtime.mode=='live','snapshot capture requires LiveProcessReader')
    local per_tick=request.bytes_per_tick or 8*1024*1024
    local chunk=request.chunk_bytes or 1024*1024
    assert(safe(per_tick)and per_tick>=65536 and per_tick<=64*1024*1024,'snapshot bytes_per_tick bounds')
    assert(safe(chunk)and chunk>=4096 and chunk<=per_tick and chunk<=4*1024*1024,'snapshot chunk bounds')
    local watch={status='running',writes=0,protection_changes=0};local file,partial_path
    local worker=coroutine.create(function()
        local started=now(runtime)
        local exe,dll=runtime.module(nil),runtime.module('game.dll')
        if not exe or not dll then error('TARGET_UNAVAILABLE: game modules not ready',0)end
        local exe_base,dll_base=runtime.address(exe),runtime.address(dll)
        local exe_sha,dll_sha=runtime.module_hash(exe),runtime.module_hash(dll)
        assert(type(exe_sha)=='string'and#exe_sha==64 and type(dll_sha)=='string'and#dll_sha==64,
            'module fingerprints unavailable')
        local page,maximum=runtime.system_info()
        assert(page==4096 and safe(maximum)and maximum>65536,'unsupported process address space')
        local diagnostics={mem_private_bytes=0,mem_image_bytes=0,mem_mapped_bytes=0,
            skipped_noaccess_bytes=0,skipped_guard_bytes=0,failed_read_bytes=0,
            skipped_uncommitted_bytes=0,skipped_unreadable_bytes=0}
        local regions,cursor,total_virtual,eligible= {},65536,0,0
        while cursor<maximum do
            local r=assert(runtime.query(cursor),'VirtualQuery failed during snapshot enumeration')
            assert(safe(r.base)and safe(r.size)and r.size>0 and r.base<=cursor
                and r.base+r.size>cursor and r.base+r.size<=maximum,'invalid region enumeration')
            local item={base=r.base,allocation_base=r.allocation_base,size=r.size,state=r.state,
                type=r.type,protect=r.protect,captured_length=0,data_offset=0,error_code=0}
            item.status=status_for(item,diagnostics)
            if item.status==nil then eligible=eligible+item.size end
            regions[#regions+1]=item;total_virtual=total_virtual+item.size;cursor=r.base+r.size
            if #regions%256==0 then coroutine.yield()end
        end
        local captured_at=utc();local folder
        if request.output_path then
            folder=request.output_path:match('^(.*)[\\/][^\\/]+$')
        else
            folder=request.output_directory or default_folder(runtime)
            if request.output_directory then assert(runtime.ensure_directory,'snapshot directory capability unavailable')(folder)end
        end
        local filename=exe_sha:sub(1,12)..'-'..stamp(captured_at)..'.hd2snap'
        local final_path=request.output_path or(folder..'\\'..filename)
        if request.output_path then
            local parent=final_path:match('^(.*)[\\/][^\\/]+$');if parent then runtime.ensure_directory(parent)end
        end
        partial_path=final_path..'.partial'
        local exists=io.open(final_path,'rb');if exists then exists:close();error('snapshot path already exists: '..final_path)end
        file=assert(io.open(partial_path,'w+b'))
        assert(file:seek('set',format.HEADER_RESERVE-1),'cannot reserve snapshot header')
        assert(file:write('\0'),'cannot reserve snapshot header')
        assert(file:seek('set',format.HEADER_RESERVE),'cannot position snapshot payload')
        local metrics={runtime=runtime,regions_seen=#regions,regions_captured=0,bytes_captured=0,
            bytes_skipped=diagnostics.skipped_noaccess_bytes+diagnostics.skipped_guard_bytes
                +diagnostics.skipped_unreadable_bytes,read_failures=0}
        local eligible_done,tick_bytes,tick_regions,last_log=0,0,0,started
        for _,r in ipairs(regions)do
            if r.status==nil then
                r.status=format.STATUS.CAPTURED;r.data_offset=assert(file:seek())
                local remaining=r.size
                while remaining>0 do
                    if tick_bytes>=per_tick or tick_regions>=64 then
                        file:flush();emit_progress(emit,metrics,started,eligible_done,eligible)
                        coroutine.yield();tick_bytes,tick_regions=0,0
                    end
                    local amount=math.min(remaining,chunk,per_tick-tick_bytes)
                    local bytes,error_code=runtime.read(r.base+r.captured_length,amount)
                    if not bytes or#bytes~=amount then
                        r.status=format.STATUS.READ_FAILED
                        r.error_code=type(error_code)=='number'and error_code or 0
                        diagnostics.failed_read_bytes=diagnostics.failed_read_bytes+remaining
                        metrics.bytes_skipped=metrics.bytes_skipped+remaining
                        metrics.read_failures=metrics.read_failures+1
                        break
                    end
                    assert(file:write(bytes),'snapshot payload write failed')
                    r.captured_length=r.captured_length+amount;remaining=remaining-amount
                    metrics.bytes_captured=metrics.bytes_captured+amount;tick_bytes=tick_bytes+amount
                end
                eligible_done=eligible_done+r.size;tick_regions=tick_regions+1
                if r.status==format.STATUS.CAPTURED then metrics.regions_captured=metrics.regions_captured+1 end
                if r.captured_length==0 then r.data_offset=0 end
            end
        end
        file:flush()
        local function module_size(base)
            local ending=base
            for _,r in ipairs(regions)do if r.allocation_base==base and r.type==IMAGE then ending=math.max(ending,r.base+r.size)end end
            return ending-base
        end
        local modules={{name='helldivers2.exe',base=exe_base,size=module_size(exe_base),sha256=exe_sha},
            {name='game.dll',base=dll_base,size=module_size(dll_base),sha256=dll_sha}}
        local meta={architecture_code=0x8664,page_size=page,maximum_address=maximum,
            total_virtual_bytes=total_virtual,total_captured_bytes=metrics.bytes_captured,
            capture_unix_time=os.time(),captured_at=captured_at,hd2runtime_version=metadata.version,
            game_version=runtime.game_version and runtime.game_version()or'',
            executable_sha256=exe_sha,game_dll_sha256=dll_sha,diagnostics=diagnostics}
        local header=format.encode(meta,modules,regions)
        assert(file:seek('set',0));assert(file:write(header));file:flush();file:close();file=nil
        assert(os.rename(partial_path,final_path),'cannot finalize snapshot container');partial_path=nil
        emit_progress(emit,metrics,started,eligible_done,eligible)
        emit('[HD2Runtime] SNAPSHOT complete path='..final_path..' writes=0 protection_changes=0')
        metrics.runtime=nil;metrics.elapsed_seconds=now(runtime)-started;metrics.path=final_path
        metrics.total_virtual_bytes=total_virtual;metrics.region_count=#regions
        return {path=final_path,metadata=meta,metrics=metrics,writes=0,protection_changes=0}
    end)
    function watch.cancel()
        if watch.status=='running'then watch.status='cancelled';if file then file:close();file=nil end end
    end
    function watch.tick()
        if watch.status~='running'then return end
        local ok,result=coroutine.resume(worker)
        if not ok then
            if file then file:close();file=nil end
            watch.status='rejected';watch.error=tostring(result)
            emit('[HD2Runtime] SNAPSHOT rejected reason='..watch.error..' writes=0 protection_changes=0')
            if request.on_error then pcall(request.on_error,watch.error,{partial_path=partial_path})end
        elseif coroutine.status(worker)=='dead'then
            watch.status='complete';watch.result=result
            if request.on_result then pcall(request.on_result,result)end
        end
    end
    return watch
end
return M
