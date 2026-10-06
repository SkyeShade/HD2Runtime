-- Incremental, read-only whole-process snapshot capture for research.
local format=require('hd2runtime/core/snapshot_format')
local metadata=require('hd2runtime/domains/metadata')
local M={}
local COMMIT,PRIVATE,MAPPED,IMAGE=0x1000,0x20000,0x40000,0x1000000
local readable=require('hd2runtime/core/page_protection').READABLE
local function safe(n)return type(n)=='number'and n>=0 and n%1==0 and n<=9007199254740991 end
local function now(runtime)return runtime.monotonic_time and runtime.monotonic_time()or os.clock()end
local function utc()return os.date('!%Y-%m-%dT%H:%M:%SZ')end
local function stamp(value)return value:gsub('[-:]',''):gsub('Z$','Z')end
-- A user annotation for the file name only (never part of the snapshot's proof data): letters, digits, '.', '_' and
-- '-'; every other run of characters becomes one '-'; leading/trailing '-' and '.' are dropped; at most 48 characters.
local LABEL_MAX=48
function M.sanitize_label(label)
    if label==nil then return nil end
    assert(type(label)=='string','snapshot label must be a string')
    local clean=label:gsub('[^%w%._%-]+','-'):gsub('%-%-+','-'):gsub('^[%-%.]+',''):gsub('[%-%.]+$','')
    clean=clean:sub(1,LABEL_MAX):gsub('[%-%.]+$','')
    assert(clean~='','snapshot label has no usable characters: '..label)
    return clean
end
-- Minimal JSON for the capture-context sidecar (strings, numbers, booleans; one flat object).
local function json_value(value)
    if type(value)=='number'then return value%1==0 and string.format('%d',value)or string.format('%.6f',value)end
    if type(value)=='boolean'then return tostring(value)end
    return '"'..tostring(value):gsub('[%c"\\]',function(c)return string.format('\\u%04x',c:byte())end)..'"'
end
local function json_object(fields)
    local keys={}
    for key in pairs(fields)do keys[#keys+1]=key end
    table.sort(keys)
    local parts={}
    for _,key in ipairs(keys)do parts[#parts+1]='  '..json_value(key)..': '..json_value(fields[key])end
    return '{\n'..table.concat(parts,',\n')..'\n}\n'
end
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
    if m.progress then m.progress.bytes_captured=m.bytes_captured;m.progress.eligible_bytes=eligible_total end
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
    local delay=request.capture_delay_seconds
    if delay==nil then delay=60 end
    assert(type(delay)=='number'and delay>=0 and delay<math.huge,'invalid snapshot capture delay')
    local label=M.sanitize_label(request.label)
    assert(request.expected==nil or type(request.expected)=='table','snapshot expected identity must be a table')
    assert(request.context==nil or type(request.context)=='table','snapshot context must be a table')
    local per_tick=request.bytes_per_tick or 8*1024*1024
    local chunk=request.chunk_bytes or 1024*1024
    assert(safe(per_tick)and per_tick>=65536 and per_tick<=64*1024*1024,'snapshot bytes_per_tick bounds')
    assert(safe(chunk)and chunk>=4096 and chunk<=per_tick and chunk<=4*1024*1024,'snapshot chunk bounds')
    local watch={status=delay>0 and'waiting'or'running',writes=0,protection_changes=0,
        scheduled_delay_seconds=delay,label=label,progress={bytes_captured=0,eligible_bytes=0}}
    local file,partial_path
    local delay_elapsed=0
    emit(string.format('[HD2Runtime] SNAPSHOT scheduled delay_seconds=%.3f',delay))
    local worker=coroutine.create(function()
        local started=now(runtime)
        local exe,dll=runtime.module(nil),runtime.module('game.dll')
        if not exe or not dll then error('TARGET_UNAVAILABLE: game modules not ready',0)end
        local exe_base,dll_base=runtime.address(exe),runtime.address(dll)
        local exe_sha,dll_sha=runtime.module_hash(exe),runtime.module_hash(dll)
        assert(type(exe_sha)=='string'and#exe_sha==64 and type(dll_sha)=='string'and#dll_sha==64,
            'module fingerprints unavailable')
        local process_id=runtime.process_id and runtime.process_id()or nil
        -- Armed captures: the process and build must be exactly the ones that were armed (re-read now, not cached),
        -- checked before any file is created.
        local expected=request.expected
        if expected then
            local function same(name,want,have)
                if want~=nil and want~=have then
                    error('TARGET_CHANGED: '..name..' is '..tostring(have)..', armed with '..tostring(want),0)
                end
            end
            same('process id',expected.process_id,process_id)
            same('helldivers2.exe fingerprint',expected.exe_sha,exe_sha)
            same('game.dll fingerprint',expected.dll_sha,dll_sha)
            same('helldivers2.exe base',expected.exe_base,exe_base)
            same('game.dll base',expected.dll_base,dll_base)
        end
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
        local filename=exe_sha:sub(1,12)..'-'..stamp(captured_at)..(label and('-'..label)or'')..'.hd2snap'
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
        local metrics={runtime=runtime,progress=watch.progress,regions_seen=#regions,regions_captured=0,bytes_captured=0,
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
        -- Capture context (armed captures): a sidecar beside the snapshot. The snapshot format is unchanged, and
        -- the sidecar is annotation only; the snapshot stays valid if writing it fails.
        local context_path
        if request.context then
            local fields={format='hd2runtime.snapshot_capture_context.v1',snapshot=final_path:match('[^\\/]+$'),
                captured_at=captured_at,capture_unix_time=meta.capture_unix_time,
                capture_started_at=watch.capture_started_at,executable_sha256=exe_sha,game_dll_sha256=dll_sha,
                executable_base=exe_base,game_dll_base=dll_base,hd2runtime_version=metadata.version,
                total_captured_bytes=metrics.bytes_captured,label=label}
            if process_id then fields.process_id=process_id end
            for key,value in pairs(request.context)do
                if fields[key]==nil and(type(value)=='string'or type(value)=='number'or type(value)=='boolean')then
                    fields[key]=value
                end
            end
            local sidecar=final_path..'.capture.json'
            local ok,why=pcall(function()
                local handle=assert(io.open(sidecar..'.partial','wb'))
                assert(handle:write(json_object(fields)));handle:close()
                os.remove(sidecar)
                assert(os.rename(sidecar..'.partial',sidecar),'cannot finalize capture context')
            end)
            if ok then context_path=sidecar else
                os.remove(sidecar..'.partial')
                emit('[HD2Runtime] SNAPSHOT context sidecar not written: '..tostring(why))
            end
        end
        emit('[HD2Runtime] SNAPSHOT complete path='..final_path..' writes=0 protection_changes=0')
        metrics.runtime=nil;metrics.elapsed_seconds=now(runtime)-started;metrics.path=final_path
        metrics.total_virtual_bytes=total_virtual;metrics.region_count=#regions;metrics.progress=nil
        return {path=final_path,context_path=context_path,label=label,process_id=process_id,metadata=meta,
            metrics=metrics,writes=0,protection_changes=0}
    end)
    -- A failed or cancelled capture leaves no partial container behind.
    local function discard()
        if file then file:close();file=nil end
        if partial_path then os.remove(partial_path);partial_path=nil end
    end
    function watch.cancel()
        if watch.status=='waiting'or watch.status=='running'then
            watch.status='cancelled';discard()
        end
    end
    function watch.tick(dt)
        if watch.status=='waiting'then
            dt=dt or 0
            assert(type(dt)=='number'and dt>=0 and dt<math.huge,'invalid snapshot elapsed time')
            delay_elapsed=delay_elapsed+dt
            if delay_elapsed<delay then return end
            watch.status='running';watch.capture_started_at=utc()
            emit(string.format('[HD2Runtime] SNAPSHOT capture_start=%s scheduled_delay_seconds=%.3f actual_delay_seconds=%.3f',
                watch.capture_started_at,delay,delay_elapsed))
        end
        if watch.status~='running'then return end
        if not watch.capture_started_at then
            watch.capture_started_at=utc()
            emit(string.format('[HD2Runtime] SNAPSHOT capture_start=%s scheduled_delay_seconds=%.3f actual_delay_seconds=%.3f',
                watch.capture_started_at,delay,delay_elapsed))
        end
        local ok,result=coroutine.resume(worker)
        if not ok then
            discard()
            watch.status='rejected';watch.error=tostring(result)
            emit('[HD2Runtime] SNAPSHOT rejected reason='..watch.error..' writes=0 protection_changes=0')
            if request.on_error then pcall(request.on_error,watch.error,{partial_removed=true})end
        elseif coroutine.status(worker)=='dead'then
            watch.status='complete';watch.result=result
            if request.on_result then pcall(request.on_result,result)end
        end
    end
    return watch
end
return M
