-- Mod keybinds (hd2.input.bind). See docs/events.md.
--
-- * Only bound keys are polled, once per update tick, and only while the game window has the keyboard focus
--   (GetForegroundWindow belongs to this process). Losing focus releases every held binding.
-- * Binding ids are namespaced ('author.mod.action'). An id belongs to the mod that registered it first; another
--   mod reusing it is refused (logged). The same mod registering it again (a repeated startup) updates it in place.
-- * One key chord belongs to one binding. A second binding asking for a chord already in use is registered in the
--   'conflict' state with no key and logged; it never takes the key over silently. rebind() resolves it.
-- * A chord matches only its exact modifiers: 'F6' does not fire while Ctrl is held, 'Ctrl+F6' does.
-- * Runtime cannot see the game's own bindings or whether the chat box has focus; prefer keys the game leaves
--   unbound (F5-F12, Insert, Home, End, Page Up/Down).
local events=require('hd2runtime/runtime/events')
local metrics=require('hd2runtime/runtime/metrics')
local KEY='HD2RuntimeInputV1'
local existing=rawget(_G,KEY)
if existing then return existing end
local M={}
rawset(_G,KEY,M)

local VK={BACKSPACE=0x08,TAB=0x09,ENTER=0x0D,PAUSE=0x13,CAPSLOCK=0x14,ESCAPE=0x1B,SPACE=0x20,PAGEUP=0x21,
    PAGEDOWN=0x22,END=0x23,HOME=0x24,LEFT=0x25,UP=0x26,RIGHT=0x27,DOWN=0x28,INSERT=0x2D,DELETE=0x2E,
    MOUSE4=0x05,MOUSE5=0x06,MOUSE3=0x04,MULTIPLY=0x6A,ADD=0x6B,SUBTRACT=0x6D,DECIMAL=0x6E,DIVIDE=0x6F,
    SEMICOLON=0xBA,EQUALS=0xBB,COMMA=0xBC,MINUS=0xBD,PERIOD=0xBE,SLASH=0xBF,GRAVE=0xC0,LBRACKET=0xDB,
    BACKSLASH=0xDC,RBRACKET=0xDD,QUOTE=0xDE}
for i=0,9 do VK[tostring(i)]=0x30+i;VK['NUMPAD'..i]=0x60+i end
for i=0,25 do VK[string.char(65+i)]=0x41+i end
for i=1,24 do VK['F'..i]=0x6F+i end
local MODIFIERS={CTRL=0x11,SHIFT=0x10,ALT=0x12}
local NAMES={}
for name,code in pairs(VK)do NAMES[code]=name end
M.keys=VK

-- Win32 backend through GetProcAddress-typed pointers (no global ffi.cdef names another mod could also declare).
local function win32_backend()
    local win=require('hd2runtime/runtime/windows_ffi')
    local ffi,kernel=win.ffi,win.kernel
    local user32=kernel.GetModuleHandleA('user32.dll')
    assert(user32~=nil,'user32.dll is not loaded')
    local function proc(module,name,signature)
        local address=kernel.GetProcAddress(module,name)
        assert(address~=nil,name..' export unavailable')
        return ffi.cast(signature,address)
    end
    local key_state=proc(user32,'GetAsyncKeyState','int16_t (*)(int)')
    local foreground=proc(user32,'GetForegroundWindow','void *(*)(void)')
    local window_process=proc(user32,'GetWindowThreadProcessId','uint32_t (*)(void *, uint32_t *)')
    local process_id=proc(kernel.GetModuleHandleA('kernel32.dll'),'GetCurrentProcessId','uint32_t (*)(void)')()
    local owner=ffi.new('uint32_t[1]')
    return {
        focused=function()
            local window=foreground()
            if window==nil then return false end
            owner[0]=0
            window_process(window,owner)
            return owner[0]==process_id
        end,
        down=function(code)return key_state(code)<0 end}
end
local backend
function M.set_backend(value)backend=value end   -- tests
local function get_backend()
    if backend==nil then
        local ok,value=pcall(win32_backend)
        if ok then backend=value else
            backend=false
            events.emit_log('input unavailable: '..tostring(value))
        end
    end
    return backend or nil
end

-- 'Ctrl+Shift+F6' -> {code=0x75, ctrl=true, shift=true, alt=false, text='Ctrl+Shift+F6'}
local function parse(text)
    assert(type(text)=='string'and#text>0 and#text<=40,'key must be a key name such as "F6" or "Ctrl+F6"')
    local chord={ctrl=false,shift=false,alt=false}
    local parts={}
    for part in text:gmatch('[^+]+')do parts[#parts+1]=part:upper():gsub('%s','')end
    assert(#parts>=1,'key must name a key')
    for i=1,#parts-1 do
        local modifier=parts[i]=='CONTROL'and'CTRL'or parts[i]
        assert(MODIFIERS[modifier],'unknown modifier '..parts[i]..' (Ctrl, Shift, Alt)')
        chord[modifier:lower()]=true
    end
    local main=parts[#parts]
    main=({ESC='ESCAPE',RETURN='ENTER',PGUP='PAGEUP',PGDN='PAGEDOWN',INS='INSERT',DEL='DELETE'})[main]or main
    chord.code=assert(VK[main],'unknown key '..parts[#parts])
    local names={}
    if chord.ctrl then names[#names+1]='Ctrl'end
    if chord.shift then names[#names+1]='Shift'end
    if chord.alt then names[#names+1]='Alt'end
    names[#names+1]=NAMES[chord.code]
    chord.text=table.concat(names,'+')
    return chord
end
M.parse=parse

local bindings,order,chords={}, {},{}
local Binding={};Binding.__index=Binding
local function chord_key(chord)return chord and(chord.code..(chord.ctrl and'c'or'')..(chord.shift and's'or'')
    ..(chord.alt and'a'or''))end
local function release(binding)
    if binding.held then
        binding.held=false
        if binding.on_release then events.invoke(binding,'input '..binding.id,binding.on_release,binding:describe())end
        events.queue('key_up',{binding=binding.id,key=binding.key,owner=binding.owner})
    end
end
local function claim(binding,chord)
    local key=chord_key(chord)
    local holder=chords[key]
    if holder and holder~=binding then
        binding.chord=nil;binding.key=nil;binding.state='conflict'
        binding.conflict={key=chord.text,binding=holder.id,owner=holder.owner}
        events.emit_log('input binding '..binding.id..' ('..binding.owner..') wants '..chord.text..', already bound to '
            ..holder.id..' ('..holder.owner..'); left unbound until rebound')
        metrics.count('input.conflicts')
        return false
    end
    chords[key]=binding
    binding.chord=chord;binding.key=chord.text;binding.conflict=nil
    if binding.state~='disabled'then binding.state='active'end
    return true
end
local function unclaim(binding)
    local key=chord_key(binding.chord)
    if key and chords[key]==binding then chords[key]=nil end
    release(binding)
    binding.chord=nil
end
function Binding:describe()
    return {id=self.id,owner=self.owner,key=self.key,default=self.default,state=self.state,
        conflict=self.conflict,presses=self.presses,failures=self.failures}
end
function Binding:rebind(text)
    if self.state=='rejected'or self.state=='removed'then return false,self.state end
    local ok,chord=pcall(parse,text)
    if not ok then events.emit_log('input binding '..self.id..' rebind rejected: '..tostring(chord));return false,chord end
    unclaim(self)
    if self.state=='conflict'then self.state='active'end
    local claimed=claim(self,chord)
    return claimed,claimed and nil or'conflict'
end
function Binding:disable()if self.state=='active'then release(self);self.state='disabled'end;return self end
function Binding:enable()if self.state=='disabled'then self.state=self.chord and'active'or'conflict'end;return self end
function Binding:unbind()
    if bindings[self.id]~=self then return self end
    unclaim(self)
    bindings[self.id]=nil
    for i,b in ipairs(order)do if b==self then table.remove(order,i)break end end
    self.state='removed'
    if#order==0 then events.set_poller('input',nil)end
    return self
end
function Binding:active()return self.state=='active'end

local function rejected(id,owner,why)
    local message=tostring(why):gsub('^[^%s:]+:%d+: ','')
    events.emit_log('input binding '..tostring(id)..' ('..tostring(owner)..') rejected: '..message)
    metrics.count('input.rejected')
    return setmetatable({id=id,owner=owner,state='rejected',reason=message,presses=0,failures=0},Binding)
end
M.rejected=rejected

local modifiers_down={}
local function poll()
    local b=get_backend()
    if not b then return end
    if not b.focused()then
        for _,binding in ipairs(order)do release(binding)end
        return
    end
    for name,code in pairs(MODIFIERS)do modifiers_down[name]=b.down(code)end
    for _,binding in ipairs(order)do
        local chord=binding.chord
        if binding.state=='active'and chord then
            local main=b.down(chord.code)
            if binding.held then
                if not main then release(binding)end
            elseif main and modifiers_down.CTRL==chord.ctrl and modifiers_down.SHIFT==chord.shift
                and modifiers_down.ALT==chord.alt then
                binding.held=true
                binding.presses=binding.presses+1
                metrics.count('input.presses')
                if binding.on_press then events.invoke(binding,'input '..binding.id,binding.on_press,binding:describe())end
                events.queue('key_down',{binding=binding.id,key=binding.key,owner=binding.owner})
            end
        elseif binding.held then
            release(binding)
        end
    end
end

-- spec: {key='F6', on_press=function(binding) end, on_release=function(binding) end, enabled=true}
function M.bind(id,spec,owner)
    local valid,why=pcall(function()
        assert(type(id)=='string'and#id<=80 and id:match('^[%a][%w_]*%.[%w_%.]*[%w_]$'),
            'binding id must be namespaced, e.g. "author_mod.action" (letters, digits, _ and dots)')
        assert(type(spec)=='table','binding spec must be a table')
        assert(spec.on_press==nil or type(spec.on_press)=='function','on_press must be a function')
        assert(spec.on_release==nil or type(spec.on_release)=='function','on_release must be a function')
        assert(spec.on_press or spec.on_release,'a binding needs on_press or on_release')
    end)
    if not valid then return rejected(id,owner,why)end
    local ok,chord=pcall(parse,spec.key or spec.default)
    if not ok then return rejected(id,owner,chord)end
    local binding=bindings[id]
    if binding then
        if binding.owner~=owner then
            return rejected(id,owner,'id already registered by '..binding.owner)
        end
        binding.on_press,binding.on_release=spec.on_press,spec.on_release
        if binding.default~=chord.text then binding.default=chord.text;binding:rebind(chord.text)end
        return binding
    end
    binding=setmetatable({id=id,owner=owner,on_press=spec.on_press,on_release=spec.on_release,default=chord.text,
        state=spec.enabled==false and'disabled'or'active',presses=0,calls=0,failures=0,consecutive=0,
        max_failures=0,label='binding '..id,held=false},Binding)
    bindings[id]=binding
    order[#order+1]=binding
    claim(binding,chord)
    events.set_poller('input',poll)
    return binding
end
function M.bindings()
    local result={}
    for _,binding in ipairs(order)do result[#result+1]=binding:describe()end
    return result
end
function M.get(id)return bindings[id]end
function M.reset_for_tests()
    for _,binding in ipairs({unpack(order)})do binding:unbind()end
    backend=nil
end
return M
