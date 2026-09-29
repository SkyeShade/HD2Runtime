-- Armed snapshot capture (docs/snapshots.md#armed-in-mission-capture). Research tooling; no gameplay effect.
--
-- The in-game side of `py hd2.py snapshot arm`: it never captures on its own. While the game runs it writes a status
-- file (heartbeat, process id, module fingerprints and bases, state) into a control folder, and it checks once per
-- second for a request file the SDK command writes when its countdown ends or ENTER is pressed. A request is taken
-- once (by id) and must:
--   * not be expired (the command stops waiting after its acknowledgement timeout);
--   * name this process id and this game session (a restarted game is a new session);
--   * name the module fingerprints and bases that were armed.
-- The capture itself is the one capture engine (api/snapshot_capture.lua) with capture_delay_seconds=0, the
-- request's label and the armed identity as `expected`, so the engine re-reads and re-checks the process and build
-- when capture begins, before any file exists.
local capture=require('hd2runtime/api/snapshot_capture')
local metadata=require('hd2runtime/domains/metadata')
local M={}
local POLL,HEARTBEAT=1.0,2.0   -- game seconds between request checks / status writes

function M.default_directory()
    local localdata=assert(os.getenv('LOCALAPPDATA'),'LOCALAPPDATA unavailable')
    return localdata..'\\HD2Runtime\\local_research\\snapshots\\control'
end
-- key=value lines; nil unless the file is complete (it ends with end=1).
function M.parse(text)
    if type(text)~='string'then return nil end
    local fields={}
    for line in text:gmatch('[^\r\n]+')do
        local key,value=line:match('^([%w_]+)=(.*)$')
        if key then fields[key]=value end
    end
    if fields['end']~='1'then return nil end
    return fields
end
local ORDER={'state','session','heartbeat','process_id','exe_sha','dll_sha','exe_base','dll_base','runtime_version',
    'request','label','path','context_path','reason','bytes_captured','eligible_bytes','captures'}
function M.serialize(fields)
    local lines={}
    for _,key in ipairs(ORDER)do
        local value=fields[key]
        if value~=nil then lines[#lines+1]=key..'='..tostring(value):gsub('[%c]',' ')end
    end
    lines[#lines+1]='end=1'
    return table.concat(lines,'\n')..'\n'
end
local function read_file(path)
    local handle=io.open(path,'rb')
    if not handle then return nil end
    local text=handle:read('*a');handle:close()
    return text
end
local function write_file(path,text)
    local handle=io.open(path..'.tmp','wb')
    if not handle then return false end
    local ok=handle:write(text);handle:close()
    if not ok then os.remove(path..'.tmp');return false end
    os.remove(path)
    if not os.rename(path..'.tmp',path)then os.remove(path..'.tmp');return false end
    return true
end

function M.start(runtime,emit,request)
    request=request or{};emit=emit or print
    assert(runtime.mode=='live','armed snapshot capture requires LiveProcessReader')
    local folder=request.control_directory or M.default_directory()
    assert(runtime.ensure_directory,'snapshot directory capability unavailable')(folder)
    local status_path,request_path=folder..'\\status.txt',folder..'\\request.txt'
    local now=request.clock or os.time
    -- This game session: the process id plus the time the controller started (a restarted game differs).
    local process_id=runtime.process_id and runtime.process_id()or 0
    local session=tostring(process_id)..'-'..tostring(now())
    -- The armed identity, read once the game modules are loaded (hashing the module files is not repeated every
    -- heartbeat; the capture engine re-hashes them when a capture begins).
    local identity={process_id=process_id}
    local function identify()
        if identity.exe_sha then return end
        local exe,dll=runtime.module(nil),runtime.module('game.dll')
        if not exe or not dll then return end
        local exe_sha,dll_sha=runtime.module_hash(exe),runtime.module_hash(dll)
        if type(exe_sha)=='string'and#exe_sha==64 and type(dll_sha)=='string'and#dll_sha==64 then
            identity.exe_base,identity.dll_base=runtime.address(exe),runtime.address(dll)
            identity.exe_sha,identity.dll_sha=exe_sha,dll_sha
        end
    end
    identify()
    local watch={status='armed',captures=0,writes=0,protection_changes=0,session=session,directory=folder}
    local handled,current={},nil
    local status={state='idle'}
    local since_poll,since_beat=POLL,HEARTBEAT
    local function publish(fields)
        identify()
        if fields then status=fields end
        status.session=session;status.heartbeat=now();status.process_id=process_id
        status.exe_sha=identity.exe_sha;status.dll_sha=identity.dll_sha
        status.exe_base=identity.exe_base;status.dll_base=identity.dll_base
        status.runtime_version=metadata.version;status.captures=watch.captures
        if current then
            status.bytes_captured=current.watch.progress.bytes_captured
            status.eligible_bytes=current.watch.progress.eligible_bytes
        end
        write_file(status_path,M.serialize(status))
        since_beat=0
    end
    local function reject(id,reason)
        emit('[HD2Runtime] SNAPSHOT request '..tostring(id)..' rejected: '..reason)
        publish({state='rejected',request=id,reason=reason})
    end
    local function take()
        local fields=M.parse(read_file(request_path))
        if not fields or not fields.id or handled[fields.id]then return end
        handled[fields.id]=true
        os.remove(request_path)
        local id=fields.id
        if current then return reject(id,'a capture is already running')end
        if not tonumber(fields.expires)or tonumber(fields.expires)<now()then return reject(id,'request expired')end
        if fields.session~=session then return reject(id,'request was armed for another game session')end
        if tonumber(fields.process_id)~=process_id then return reject(id,'request targets another process')end
        if not identity.exe_sha then return reject(id,'game modules were not loaded when this session started')end
        for _,key in ipairs({'exe_sha','dll_sha','exe_base','dll_base'})do
            if tostring(identity[key])~=fields[key]then return reject(id,'armed '..key..' differs from this process')end
        end
        local ok,label=pcall(capture.sanitize_label,fields.label~=''and fields.label or nil)
        if not ok then return reject(id,tostring(label))end
        local started,snapshot=pcall(capture.start,runtime,emit,{capture_delay_seconds=0,label=label,
            output_directory=request.output_directory,bytes_per_tick=request.bytes_per_tick,
            chunk_bytes=request.chunk_bytes,
            expected={process_id=process_id,exe_sha=identity.exe_sha,dll_sha=identity.dll_sha,
                exe_base=identity.exe_base,dll_base=identity.dll_base},
            context={request_id=id,mode=fields.mode,configured_delay_seconds=tonumber(fields.delay),
                armed_at_unix=tonumber(fields.armed_at),triggered_at_unix=tonumber(fields.triggered_at),
                game_session=session,trigger='hd2.py snapshot arm'}})
        if not started then return reject(id,tostring(snapshot))end
        current={id=id,watch=snapshot,label=label}
        emit('[HD2Runtime] SNAPSHOT request '..id..' accepted'..(label and(' label='..label)or''))
        publish({state='capturing',request=id,label=label})
    end
    function watch.cancel()
        if current then current.watch.cancel();current=nil end
        watch.status='cancelled'
        publish({state='stopped'})
    end
    function watch.tick(dt)
        if watch.status~='armed'then return end
        dt=type(dt)=='number'and dt>=0 and dt<10 and dt or 0
        since_poll,since_beat=since_poll+dt,since_beat+dt
        if current then
            current.watch.tick(dt)
            local state=current.watch.status
            if state=='complete'then
                watch.captures=watch.captures+1
                local result=current.watch.result
                local id,label=current.id,current.label
                current=nil
                publish({state='complete',request=id,label=label,path=result.path,context_path=result.context_path,
                    bytes_captured=result.metrics.bytes_captured})
            elseif state=='rejected'or state=='cancelled'then
                local id,reason=current.id,current.watch.error or state
                current=nil
                publish({state='rejected',request=id,reason=reason})
            end
        end
        if since_poll>=POLL then since_poll=0;take()end
        if since_beat>=HEARTBEAT then publish()end
    end
    publish({state='idle'})
    emit('[HD2Runtime] SNAPSHOT armed controller ready directory='..folder..' session='..session)
    return watch
end
return M
