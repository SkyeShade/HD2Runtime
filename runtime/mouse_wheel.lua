-- The mouse wheel for mod UI (hd2.input.wheel). EXPERIMENTAL, r51.
--
-- GetAsyncKeyState cannot see the wheel, and the engine's stingray.Mouse 'wheel' axis read nothing in a mod window in
-- the live test of 2026-10-08 (the overlay frees the mouse focus while it is open). Two sources, sampled once per
-- update tick while some mod asks for the wheel:
--   * the engine axis, read as the custom stratagem panel reads it;
--   * a thread message hook (SetWindowsHookExW WH_GETMESSAGE) on the game window's thread. The game pumps its window
--     messages on another thread than the one running Lua (live r51 log: window thread 65780, Lua thread 51232), so
--     the hook procedure is NATIVE code, not a Lua callback: about 200 bytes of x64 built by M.hook_code below, in
--     pages the Runtime's write adapter allocates once and never frees (windows_write.lua native_procedure). It only adds: WM_MOUSEWHEEL deltas to one counter, the wheel
--     of WM_INPUT raw mouse records to another (GetRawInputData on the message's own handle, read-only: the game
--     still reads it), and always returns CallNextHookEx. Lua reads the counters once per tick; nothing is consumed
--     and no Lua ever runs on the window thread.
-- The hook is removed one second after the last query (the code and counter pages stay, so a message already inside
-- the procedure finishes safely). Any error turns the hook off for the session (logged once). It is never installed
-- outside the game on Windows x64. The first source that delivers a notch is logged, so a live test tells which works.
--
-- 0.30.2: the player can turn the native hook off at install: the runtime ZIP's second mod manager option (Arsenal,
-- Echelon) "mouse wheel hook off" also deploys a one-resource archive, hd2runtime/settings/wheel_hook_off, whose
-- presence turns it off (M.native_allowed). GameGuard error 1015 was reported with 0.30.x, and a window hook running
-- generated code is what anti-cheat looks for, so the option says it may fix that. Off, nothing native is built or
-- installed (no executable page, no hook): hd2.input.wheel() reads the engine axis only (over a game menu the mouse
-- focus is kept, runtime/mod_cursor.lua) and hd2.input.block() returns false with the reason, which every caller
-- already handles. The API is unchanged, so no mod needs an update.
local events=require('hd2runtime/runtime/events')
local KEY='HD2RuntimeMouseWheelV2'
local existing=rawget(_G,KEY)
if existing then return existing end
local M={}
rawset(_G,KEY,M)

local IDLE_SECONDS=1
local RETRY_SECONDS=2
local WHEEL_DELTA=120
local state={hook=nil,value=0,frame=-1,last_query=nil,disabled=nil,logged={},source=nil,engine_ok=true,
    next_try=0,seen={legacy=0,raw=0}}
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

-------------------------------------------------------------------------------------------------- hook code --
local function u32(n)return string.char(n%256,math.floor(n/256)%256,math.floor(n/65536)%256,math.floor(n/16777216)%256)end
local function u64(n)
    assert(type(n)=='number'and n>=0 and n<2^53 and n%1==0,'address out of range')
    return u32(n%4294967296)..u32(math.floor(n/4294967296))
end
-- The x64 hook procedure LRESULT CALLBACK proc(int code, WPARAM wParam, LPARAM lParam /* MSG * */). counters is the
-- address of the shared block:
--   +0  int32  WM_MOUSEWHEEL delta sum            +4  int32  raw-input wheel delta sum
--   +8  int32  wheel messages seen                +12 int32  block flags (1 keyboard, 2 mouse), written by Lua
--   +16 uint64 block lease: GetTickCount64 ms until which the flags hold, written by Lua every update
--   +24 int32  messages blocked
-- raw_data, next_hook and tick_count are GetRawInputData, CallNextHookEx and GetTickCount64. Blocking turns a message
-- into WM_NULL before the game's window procedure sees it: key presses and characters (legacy and raw; key releases
-- always pass, so nothing stays held), mouse button presses and the wheel (after it is counted). Only while the lease
-- holds: if Lua stops renewing it, nothing is blocked half a second later. Win64 ABI: 16-byte aligned calls, 32 bytes
-- of shadow space, rbx/rsi/rdi callee-saved. Every branch ends in CallNextHookEx(NULL, code, wParam, lParam).
function M.hook_code(counters,raw_data,next_hook,tick_count)
    local parts={}
    local function emit(s)parts[#parts+1]=s end
    local function hex(s)emit((s:gsub(' ',''):gsub('%x%x',function(b)return string.char(tonumber(b,16))end)))end
    local labels,fixups={},{}
    local function size()local n=0 for _,p in ipairs(parts)do n=n+#p end return n end
    -- near branches (rel32): Jcc is 0F 8x, JMP is E9
    local NEAR={js='0F 88',jne='0F 85',je='0F 84',jb='0F 82',ja='0F 87',jz='0F 84',jnz='0F 85',jmp='E9'}
    local function jump(op,label)hex(NEAR[op]);fixups[#fixups+1]={at=size(),label=label};emit('\0\0\0\0')end
    local function label(name)labels[name]=size()end
    local function imm32(n)return string.format('%02X %02X %02X %02X',n%256,math.floor(n/256)%256,
        math.floor(n/65536)%256,math.floor(n/16777216)%256)end
    hex('53 56 57')                      -- push rbx; push rsi; push rdi
    hex('48 83 EC 70')                   -- sub rsp, 0x70
    hex('89 CB')                         -- mov ebx, ecx         (code)
    hex('48 89 D6')                      -- mov rsi, rdx         (wParam: PM_REMOVE?)
    hex('4C 89 C7')                      -- mov rdi, r8          (MSG *)
    hex('85 DB');jump('js','next')       -- test ebx, ebx; js next          (code < 0: pass on)
    hex('48 83 FE 01');jump('jne','next')-- cmp rsi, 1; jne next            (only messages being removed: once)
    hex('8B 47 08')                      -- mov eax, [rdi+8]     (MSG.message)
    hex('3D 0A 02 00 00');jump('jne','input') -- cmp eax, WM_MOUSEWHEEL; jne input
    hex('48 8B 47 10')                   -- mov rax, [rdi+16]    (MSG.wParam)
    hex('C1 F8 10')                      -- sar eax, 16          (signed HIWORD: the delta)
    hex('48 B9');emit(u64(counters))     -- mov rcx, counters
    hex('F0 01 01')                      -- lock add [rcx], eax
    hex('F0 FF 41 08')                   -- lock inc dword [rcx+8]
    jump('jmp','block_mouse')
    label('input')
    hex('3D FF 00 00 00');jump('je','raw')    -- cmp eax, WM_INPUT; je raw
    for _,m in ipairs({0x100,0x104,0x102,0x106})do       -- WM_KEYDOWN, WM_SYSKEYDOWN, WM_CHAR, WM_SYSCHAR
        hex('3D '..imm32(m));jump('je','block_keyboard')
    end
    for _,m in ipairs({0x201,0x203,0x204,0x206,0x207,0x209,0x20B,0x20D})do  -- button downs and double clicks
        hex('3D '..imm32(m));jump('je','block_mouse')
    end
    jump('jmp','next')
    label('raw')
    hex('C7 44 24 28 40 00 00 00')       -- mov dword [rsp+0x28], 64     (pcbSize)
    hex('48 8B 4F 18')                   -- mov rcx, [rdi+24]    (MSG.lParam: HRAWINPUT)
    hex('BA 03 00 00 10')                -- mov edx, RID_INPUT
    hex('4C 8D 44 24 30')                -- lea r8, [rsp+0x30]   (64-byte buffer)
    hex('4C 8D 4C 24 28')                -- lea r9, [rsp+0x28]
    hex('C7 44 24 20 18 00 00 00')       -- mov dword [rsp+0x20], 24     (sizeof(RAWINPUTHEADER))
    hex('48 B8');emit(u64(raw_data))     -- mov rax, GetRawInputData
    hex('FF D0')                         -- call rax
    hex('83 F8 20');jump('jb','next')    -- cmp eax, 32; jb next          (too short)
    hex('83 F8 40');jump('ja','next')    -- cmp eax, 64; ja next          (error: (UINT)-1)
    hex('8B 44 24 30')                   -- mov eax, [rsp+0x30]  (RAWINPUTHEADER.dwType)
    hex('83 F8 01');jump('je','raw_keyboard') -- cmp eax, RIM_TYPEKEYBOARD; je raw_keyboard
    hex('85 C0');jump('jne','next')      -- test eax, eax; jne next       (not RIM_TYPEMOUSE)
    hex('0F B7 44 24 4C')                -- movzx eax, word [rsp+0x4C]   (RAWMOUSE.usButtonFlags)
    hex('A9 00 04 00 00');jump('jz','raw_buttons')  -- test eax, RI_MOUSE_WHEEL; jz raw_buttons
    hex('0F BF 4C 24 4E')                -- movsx ecx, word [rsp+0x4E]   (usButtonData: the delta)
    hex('48 BA');emit(u64(counters))     -- mov rdx, counters
    hex('F0 01 4A 04')                   -- lock add [rdx+4], ecx
    hex('F0 FF 42 08')                   -- lock inc dword [rdx+8]
    jump('jmp','block_mouse')
    label('raw_buttons')
    hex('A9 55 01 00 00');jump('jz','next')    -- test eax, any button DOWN flag; jz next
    jump('jmp','block_mouse')
    label('raw_keyboard')
    hex('0F B7 44 24 4A')                -- movzx eax, word [rsp+0x4A]   (RAWKEYBOARD.Flags)
    hex('A8 01');jump('jnz','next')      -- test al, RI_KEY_BREAK; jnz next   (a release always passes)
    label('block_keyboard')
    hex('BA 01 00 00 00')                -- mov edx, 1
    jump('jmp','block')
    label('block_mouse')
    hex('BA 02 00 00 00')                -- mov edx, 2
    label('block')
    hex('48 B9');emit(u64(counters))     -- mov rcx, counters
    hex('85 51 0C');jump('jz','next')    -- test [rcx+12], edx; jz next   (not asked to block this kind)
    hex('48 B8');emit(u64(tick_count))   -- mov rax, GetTickCount64
    hex('FF D0')                         -- call rax
    hex('48 B9');emit(u64(counters))     -- mov rcx, counters
    hex('48 3B 41 10');jump('ja','next') -- cmp rax, [rcx+16]; ja next    (the lease ran out)
    hex('C7 47 08 00 00 00 00')          -- mov dword [rdi+8], WM_NULL   (the game's window never sees it)
    hex('F0 FF 41 18')                   -- lock inc dword [rcx+24]
    label('next')
    hex('31 C9')                         -- xor ecx, ecx         (hhk: ignored)
    hex('89 DA')                         -- mov edx, ebx
    hex('49 89 F0')                      -- mov r8, rsi
    hex('49 89 F9')                      -- mov r9, rdi
    hex('48 B8');emit(u64(next_hook))    -- mov rax, CallNextHookEx
    hex('FF D0')                         -- call rax
    hex('48 83 C4 70')                   -- add rsp, 0x70
    hex('5F 5E 5B C3')                   -- pop rdi; pop rsi; pop rbx; ret
    local code=table.concat(parts)
    local bytes={code:byte(1,-1)}
    for _,f in ipairs(fixups)do
        local delta=(labels[f.label]-(f.at+4))%4294967296
        for i=1,4 do bytes[f.at+i]=delta%256;delta=math.floor(delta/256)end
    end
    local out={}
    for i,b in ipairs(bytes)do out[i]=string.char(b)end
    return table.concat(out)
end

-------------------------------------------------------------------------------------------------- the hook --
-- Every FFI type and export is made ONCE: a per-call ffi.cast of a function type string creates a new ctype each time,
-- and retrying that every frame filled LuaJIT's ctype table ('table overflow', live r51).
local win32
local function bindings()
    if win32 then return win32 end
    local win=require('hd2runtime/runtime/windows_ffi')
    local ffi,kernel=win.ffi,win.kernel
    local user32=kernel.GetModuleHandleA('user32.dll')
    assert(user32~=nil,'user32.dll is not loaded')
    local kernel32=kernel.GetModuleHandleA('kernel32.dll')
    local function export(module,name)
        local address=kernel.GetProcAddress(module,name)
        assert(address~=nil,name..' export unavailable')
        return address
    end
    local function typed(module,name,signature)return ffi.cast(signature,export(module,name))end
    win32={ffi=ffi,kernel=kernel,
        foreground=typed(user32,'GetForegroundWindow','void *(*)(void)'),
        window_thread=typed(user32,'GetWindowThreadProcessId','uint32_t (*)(void *, uint32_t *)'),
        current_process=typed(kernel32,'GetCurrentProcessId','uint32_t (*)(void)'),
        set_hook=typed(user32,'SetWindowsHookExW','void *(*)(int, void *, void *, uint32_t)'),
        unhook=typed(user32,'UnhookWindowsHookEx','int (*)(void *)'),
        raw_data=tonumber(ffi.cast('uintptr_t',export(user32,'GetRawInputData'))),
        next_hook=tonumber(ffi.cast('uintptr_t',export(user32,'CallNextHookEx'))),
        tick_count=tonumber(ffi.cast('uintptr_t',export(kernel32,'GetTickCount64'))),
        pid=ffi.new('uint32_t[1]')}
    return win32
end

-- The procedure and its counters: built once per process by the write-capable adapter
-- (runtime/windows_write.lua native_procedure: pages never freed, the code execute-read). Kept in _G so a reloaded
-- module reuses them.
local PAGES_KEY='HD2RuntimeMouseWheelPagesV1'
function M.pages(w)
    w=w or bindings()
    local pages=rawget(_G,PAGES_KEY)
    if pages then return pages end
    local adapter=require('hd2runtime/runtime/windows_write').create()
    assert(adapter.native_procedure,'this Runtime adapter cannot build a native procedure')
    local code,counters=adapter.native_procedure(function(counters)
        return M.hook_code(counters,w.raw_data,w.next_hook,w.tick_count)
    end)
    pages={code=w.ffi.cast('void *',code),counters=w.ffi.cast('volatile int32_t *',counters),
        lease=w.ffi.cast('volatile uint64_t *',counters+16)}
    rawset(_G,PAGES_KEY,pages)
    return pages
end

M.hooks={}
-- Installs the native hook on the game window's thread: a handle {remove, thread, read} or nil and why.
function M.hooks.install()
    local w=bindings()
    local window=w.foreground()
    if window==nil then return nil,'the game window does not have the focus'end
    local thread=w.window_thread(window,w.pid)
    if w.pid[0]~=w.current_process()then return nil,'the foreground window is not the game\'s'end
    local pages=M.pages(w)
    local handle=w.set_hook(3,pages.code,nil,thread)             -- WH_GETMESSAGE on the window's own thread
    if handle==nil then return nil,'SetWindowsHookExW failed ('..tostring(w.kernel.GetLastError())..')'end
    local c,lease=pages.counters,pages.lease
    return {thread=thread,remove=function()c[3]=0;w.unhook(handle)end,
        read=function()return c[0],c[1],c[2]end,
        -- block flags and their lease (GetTickCount64 ms), and how many messages were blocked
        block=function(flags,until_ms)c[3]=flags;lease[0]=until_ms end,
        blocked=function()return c[6]end,
        now=function()return tonumber(w.kernel.GetTickCount64())end}
end

local function remove()
    if state.hook then
        local hook=state.hook
        state.hook=nil
        pcall(hook.remove)
    end
end
local function disable(why)
    state.disabled=tostring(why)
    remove()
    log('the message hook is off for this session: '..tostring(why))
end
local function now()return events.state.now or 0 end
-- Off only when the mod manager's "mouse wheel hook off" option deployed hd2runtime/settings/wheel_hook_off (looked up
-- once per session; the archive is either deployed or not).
M.SETTING='hd2runtime/settings/wheel_hook_off'
M.NATIVE_OFF='the native mouse wheel hook is off (the "mouse wheel hook off" install option); the wheel is the engine '
    ..'axis'
local off_setting
function M.native_allowed()
    if off_setting==nil then
        local ok,value=pcall(require,M.SETTING)
        off_setting=ok and value==true
        if off_setting then log('the "mouse wheel hook off" install option is present: no native hook this session')end
    end
    return not off_setting
end
local function ensure_hook()
    if state.hook or state.disabled or now()<state.next_try then return end
    if type(rawget(_G,'stingray'))~='table'then return end   -- only in the game
    if not M.native_allowed()then
        log(M.NATIVE_OFF)
        return
    end
    state.next_try=now()+RETRY_SECONDS                        -- at most one attempt per RETRY_SECONDS
    local ok,hook,why=pcall(M.hooks.install)
    if not ok then return disable(hook)end
    if not hook then log('no message hook yet: '..tostring(why));return end
    state.hook=hook
    local ok_read,legacy,raw=pcall(hook.read)
    state.seen={legacy=ok_read and legacy or 0,raw=ok_read and raw or 0}
    log('native message hook installed on the window thread '..tostring(hook.thread))
end

-- The hook's notches since the last read: raw input when it moved, else the legacy messages (both report the same
-- turn when the game receives both).
local function hooked()
    if not state.hook then return 0 end
    local ok,legacy,raw=pcall(state.hook.read)
    if not ok then disable(legacy);return 0 end
    local dl,dr=legacy-state.seen.legacy,raw-state.seen.raw
    state.seen.legacy,state.seen.raw=legacy,raw
    if dr~=0 then
        if not state.source then state.source='WM_INPUT';log('first wheel input from WM_INPUT (raw input)')end
        return dr/WHEEL_DELTA
    end
    if dl~=0 then
        if not state.source then state.source='WM_MOUSEWHEEL';log('first wheel input from WM_MOUSEWHEEL')end
        return dl/WHEEL_DELTA
    end
    return 0
end

-- Once per update tick while someone asks: the tick's wheel, and the hook's idle removal.
local function sample()
    local frame=events.state.frame
    if state.frame==frame then return end
    state.frame=frame
    if state.hook and not M.native_allowed()then
        remove()
        log('the native message hook was removed: the player turned it off')
    end
    local h=hooked()
    local engine=engine_axis()
    if h~=0 then state.value=h
    else
        state.value=engine
        if engine~=0 and not state.source then state.source='engine';log('first wheel input from the engine axis')end
    end
    if state.block_flags and state.block_flags~=0 and now()-(state.block_query or 0)>IDLE_SECONDS then
        M.block(false)
    end
    if state.last_query and now()-state.last_query>IDLE_SECONDS and not(state.block_flags and state.block_flags~=0)then
        remove()
        state.last_query=nil
        events.set_poller('wheel',nil)
    end
end

-- The wheel this update tick in notches (+ up, - down; fractions for smooth wheels), 0 when it did not move.
function M.read()
    state.last_query=now()
    if not state.hook then ensure_hook()end
    events.set_poller('wheel',sample)
    sample()
    return state.value
end
-- Keep the game from acting on key presses (keyboard) and mouse button presses and the wheel (mouse) while a mod's
-- window is open (r52, EXPERIMENTAL). spec = {keyboard = true, mouse = true}, or false to stop. A lease: call it every
-- update while it should hold; the native procedure stops blocking 0.5 s after the last call, so a stopped Lua never
-- leaves the game deaf. Key releases always reach the game. Mods read keys and the cursor with GetAsyncKeyState and
-- GetCursorPos, which blocking does not touch. Returns true, or false and why (no hook yet: the game window must have
-- the focus and the hook installs on the first call).
local LEASE_MS=500
function M.block(spec)
    local flags=0
    if type(spec)=='table'then
        if spec.keyboard then flags=flags+1 end
        if spec.mouse then flags=flags+2 end
    end
    state.block_flags,state.block_query=flags,now()
    if flags~=0 then
        state.last_query=now()
        if not state.hook then ensure_hook()end
        events.set_poller('wheel',sample)
    end
    local hook=state.hook
    if not hook and flags~=0 and not M.native_allowed()then return false,M.NATIVE_OFF end
    if not hook or not hook.block then return flags==0,'no message hook (yet)'end
    local ok,why=pcall(function()hook.block(flags,flags~=0 and hook.now()+LEASE_MS or 0)end)
    if not ok then disable(why);return false,tostring(why)end
    return true
end
function M.status()
    local blocked
    if state.hook and state.hook.blocked then local ok,n=pcall(state.hook.blocked);blocked=ok and n or nil end
    return {hooked=state.hook~=nil,native=M.native_allowed(),disabled=state.disabled,source=state.source,
        engine=state.engine_ok,
        thread=state.hook and state.hook.thread or nil,blocking=state.block_flags or 0,blocked=blocked}
end
function M.reset_for_tests()
    off_setting=nil
    state.block_flags,state.block_query=nil,nil
    remove()
    state.value,state.frame,state.last_query,state.disabled,state.source,state.logged,state.engine_ok,state.next_try=
        0,-1,nil,nil,nil,{},true,0
    state.seen={legacy=0,raw=0}
    events.set_poller('wheel',nil)
end
return M
