-- The mouse wheel for mod UI (hd2.input.wheel). EXPERIMENTAL, r51.
--
-- GetAsyncKeyState cannot see the wheel, and the engine's stingray.Mouse 'wheel' axis read nothing in a mod window in
-- the live test of 2026-10-08 (the overlay frees the mouse focus while it is open). Two sources, sampled once per
-- update tick while some mod asks for the wheel:
--   * the engine axis, read as the custom stratagem panel reads it;
--   * a thread message hook (SetWindowsHookExW WH_GETMESSAGE) on the game window's own thread, installed only when
--     that thread is the one running Lua (the hook then runs inside the engine's own message pump, never while Lua
--     runs). It counts WM_MOUSEWHEEL and the wheel of WM_INPUT raw mouse input (GetRawInputData on the message's own
--     handle: read-only, the game still reads it). Messages are only observed: CallNextHookEx is always called and
--     nothing is consumed.
-- The hook is removed one second after the last query, on any error (logged once; the hook is then off for the
-- session) and is never installed outside Windows. The first source that delivers a notch is logged, so a live test
-- tells which one works.
local events=require('hd2runtime/runtime/events')
local KEY='HD2RuntimeMouseWheelV1'
local existing=rawget(_G,KEY)
if existing then return existing end
local M={}
rawset(_G,KEY,M)

local IDLE_SECONDS=1
local WHEEL_DELTA=120
local state={hook=nil,callback=nil,pending=0,value=0,frame=-1,last_query=nil,clock=0,disabled=nil,logged={},
    source=nil,engine_ok=true}
M.state=state

local function log(message)
    if state.logged[message]then return end
    state.logged[message]=true
    pcall(events.emit_log,'wheel: '..message)
end

-------------------------------------------------------------------------------------------------- engine axis --
local function engine_axis()
    if not state.engine_ok then return 0 end
    local S=rawget(_G,'stingray')
    local mouse=type(S)=='table'and S.Mouse
    if type(mouse)~='table'then return 0 end
    local ok,v=pcall(function()return mouse.axis(mouse.axis_index('wheel'))end)
    if not ok or v==nil then
        state.engine_ok=false
        log('the engine wheel axis is unavailable ('..tostring(v)..')')
        return 0
    end
    if type(v)=='number'then return v end
    local oky,y=pcall(function()return v.y end)
    if oky and type(y)=='number'then return y end
    local oke,_,ey=pcall(function()return S.Vector3.to_elements(v)end)
    if oke and type(ey)=='number'then return ey end
    return 0
end

-------------------------------------------------------------------------------------------------- message hook --
M.hooks={}
function M.hooks.install(on_wheel)
    local win=require('hd2runtime/runtime/windows_ffi')
    local ffi,kernel=win.ffi,win.kernel
    local user32=kernel.GetModuleHandleA('user32.dll')
    assert(user32~=nil,'user32.dll is not loaded')
    local kernel32=kernel.GetModuleHandleA('kernel32.dll')
    local function proc(module,name,signature)
        local address=kernel.GetProcAddress(module,name)
        assert(address~=nil,name..' export unavailable')
        return ffi.cast(signature,address)
    end
    local foreground=proc(user32,'GetForegroundWindow','void *(*)(void)')
    local window_thread=proc(user32,'GetWindowThreadProcessId','uint32_t (*)(void *, uint32_t *)')
    local current_thread=proc(kernel32,'GetCurrentThreadId','uint32_t (*)(void)')
    local current_process=proc(kernel32,'GetCurrentProcessId','uint32_t (*)(void)')
    local set_hook=proc(user32,'SetWindowsHookExW','void *(*)(int, void *, void *, uint32_t)')
    local next_hook=proc(user32,'CallNextHookEx','intptr_t (*)(void *, int, uintptr_t, intptr_t)')
    local unhook=proc(user32,'UnhookWindowsHookEx','int (*)(void *)')
    local raw_data=proc(user32,'GetRawInputData','uint32_t (*)(void *, uint32_t, void *, uint32_t *, uint32_t)')
    local window=foreground()
    if window==nil then return nil,'the game window does not have the focus'end
    local pid=ffi.new('uint32_t[1]')
    local thread=window_thread(window,pid)
    if pid[0]~=current_process()then return nil,'the foreground window is not the game\'s'end
    if thread~=current_thread()then
        return nil,'the game window belongs to thread '..thread..', Lua runs on thread '..current_thread()
    end
    local buffer=ffi.new('uint8_t[64]')
    local size=ffi.new('uint32_t[1]')
    local handle
    local function on_message(code,wparam,lparam)
        if code>=0 and wparam==1 then   -- HC_ACTION, PM_REMOVE: the message is being taken off the queue (once)
            local ok,why=pcall(function()
                local msg=ffi.cast('uint8_t *',lparam)
                local message=ffi.cast('uint32_t *',msg+8)[0]
                if message==0x020A then                     -- WM_MOUSEWHEEL: HIWORD(wParam) is the signed delta
                    local w=tonumber(ffi.cast('uint64_t *',msg+16)[0]%4294967296)
                    local hi=math.floor(w/65536)%65536
                    if hi>=32768 then hi=hi-65536 end
                    on_wheel(hi/WHEEL_DELTA,'WM_MOUSEWHEEL')
                elseif message==0x00FF then                 -- WM_INPUT: read the raw mouse record (read-only)
                    local raw=ffi.cast('void **',msg+24)[0]
                    size[0]=64
                    local n=raw_data(raw,0x10000003,buffer,size,24)  -- RID_INPUT, sizeof(RAWINPUTHEADER)
                    if n~=0xFFFFFFFF and n>=32 and ffi.cast('uint32_t *',buffer)[0]==0 then   -- RIM_TYPEMOUSE
                        local flags=ffi.cast('uint16_t *',buffer+28)[0]
                        if bit.band(flags,0x0400)~=0 then         -- RI_MOUSE_WHEEL
                            local data=ffi.cast('int16_t *',buffer+30)[0]
                            on_wheel(data/WHEEL_DELTA,'WM_INPUT')
                        end
                    end
                end
            end)
            if not ok then on_wheel(nil,why)end
        end
        return next_hook(handle,code,wparam,lparam)
    end
    local callback=ffi.cast('intptr_t (*)(int, uintptr_t, intptr_t)',on_message)
    handle=set_hook(3,ffi.cast('void *',callback),nil,thread)   -- WH_GETMESSAGE on the window's own thread
    if handle==nil then callback:free();return nil,'SetWindowsHookExW failed'end
    return {remove=function()unhook(handle);callback:free()end,thread=thread}
end

local function remove()
    if state.hook then
        local hook=state.hook
        state.hook=nil
        pcall(hook.remove)
    end
end
local function disable(why)
    state.disabled=why
    remove()
    log('the message hook is off for this session: '..tostring(why))
end
local function on_wheel(notches,source)
    if notches==nil then return disable(source)end
    state.pending=state.pending+notches
    if not state.source then state.source=source;log('first wheel input from '..source)end
end
local function ensure_hook()
    if state.hook or state.disabled then return end
    if type(rawget(_G,'stingray'))~='table'then return end   -- only in the game
    local ok,hook,why=pcall(M.hooks.install,on_wheel)
    if not ok then return disable(hook)end
    if not hook then log('no message hook yet: '..tostring(why));return end
    state.hook=hook
    log('message hook installed on thread '..tostring(hook.thread))
end

-- Once per update tick while someone asks: the tick's wheel, and the hook's idle removal.
local function sample()
    local frame=events.state.frame
    if state.frame==frame then return end
    state.frame=frame
    local hooked=state.pending
    state.pending=0
    local engine=engine_axis()
    if hooked~=0 then state.value=hooked
    else
        state.value=engine
        if engine~=0 and not state.source then state.source='engine';log('first wheel input from the engine axis')end
    end
    if state.last_query and events.state.now and events.state.now-state.last_query>IDLE_SECONDS then
        remove()
        state.last_query=nil
        events.set_poller('wheel',nil)
    end
end

-- The wheel this update tick in notches (+ up, - down; fractions for smooth wheels), 0 when it did not move.
function M.read()
    state.last_query=events.state.now or 0
    if not state.hook then ensure_hook()end
    events.set_poller('wheel',sample)
    sample()
    return state.value
end
function M.status()
    return {hooked=state.hook~=nil,disabled=state.disabled,source=state.source,engine=state.engine_ok}
end
function M.reset_for_tests()
    remove()
    state.pending,state.value,state.frame,state.last_query,state.disabled,state.source,state.logged,state.engine_ok=
        0,0,-1,nil,nil,nil,{},true
    events.set_poller('wheel',nil)
end
return M
