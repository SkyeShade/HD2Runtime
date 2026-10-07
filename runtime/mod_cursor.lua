-- Mouse cursor capture for mod windows (overlay:free_cursor; docs/ui-overlay.md "The cursor"). EXPERIMENTAL, r50.
--
-- While any holder holds it (an overlay that is shown with free_cursor on), the engine's own Lua Window API is asked to
-- show the cursor, not clip it to the window, and not keep the mouse focus (the camera's raw mouse input):
--   Window.set_show_cursor(true), Window.set_clip_cursor(false), Window.set_mouse_focus(false)
-- Each is asked only when its getter (Window.show_cursor / clip_cursor / mouse_focus, called with no argument as other
-- HD2 mods do) says otherwise, so a frame where nothing changed calls only the three getters. When the last holder lets
-- go, the values read before the first hold are restored (the game's defaults: hidden, clipped, focused, when a getter
-- did not answer). The functions are registered by the engine (their names are in the Window string table of the
-- retained snapshot) but no Runtime build has called them before r50; the bindings check nothing, so every value is a
-- boolean and the first error turns the feature off for the session (logged once).
-- Not done (no proven route): taking keys or clicks away from the game. See docs/events.md "Input blocking".
local log=require('hd2runtime/runtime/log')
local KEY='HD2RuntimeModCursorV1'
local existing=rawget(_G,KEY)
if existing then return existing end
local M={}
rawset(_G,KEY,M)

local holders,saved,applied,disabled,logged={},nil,false,nil,{}
M.STEPS={
    {get='show_cursor',set='set_show_cursor',want=true,default=false,required=true},
    {get='clip_cursor',set='set_clip_cursor',want=false,default=true},
    {get='mouse_focus',set='set_mouse_focus',want=false,default=true,camera=true},
}
local function emit(message)
    if logged[message]then return end
    logged[message]=true
    pcall(log.emit,'[HD2Runtime] cursor: '..message)
end
local function callable(f)
    if type(f)=='function'then return true end
    local mt=type(f)=='table'and getmetatable(f)
    return mt and type(mt.__call)=='function'or false
end
local function window()
    local S=rawget(_G,'stingray')
    local W=type(S)=='table'and S.Window
    return type(W)=='table'and W or nil
end
M.hooks={window=window}
local function read(name)
    local W=M.hooks.window()
    local f=W and W[name]
    if not callable(f)then return nil end
    local ok,value=pcall(f)
    if ok and type(value)=='boolean'then return value end
    return nil
end
local function write(name,value)
    assert(type(value)=='boolean','cursor values are booleans')
    local W=M.hooks.window()
    local f=W and W[name]
    if not callable(f)then return false,'stingray.Window.'..name..' is not callable'end
    local ok,why=pcall(f,value)
    if not ok then return false,'stingray.Window.'..name..' failed: '..tostring(why)end
    return true
end
local function disable(why)
    disabled=why
    emit('capture disabled for this session: '..why)
end

-- Holds the free cursor for `key` (call every frame while it should be free). opts = {camera = false} leaves the mouse
-- focus alone (the cursor is shown and unclipped, but the camera may still turn). True, or false and why.
function M.hold(key,opts)
    if disabled then return false,disabled end
    holders[key]=opts or{}
    if not saved then
        saved={}
        for _,step in ipairs(M.STEPS)do saved[step.get]=read(step.get)end
        emit('first hold; the game had show_cursor='..tostring(saved.show_cursor)..' clip_cursor='
            ..tostring(saved.clip_cursor)..' mouse_focus='..tostring(saved.mouse_focus))
    end
    local camera=true
    for _,o in pairs(holders)do if o.camera==false then camera=false end end
    for _,step in ipairs(M.STEPS)do
        if not step.camera or camera then
            local now=read(step.get)
            if now~=step.want then
                local ok,why=write(step.set,step.want)
                if not ok then
                    if step.required then disable(why);M.release(key,true);return false,why end
                    emit(why)
                end
            end
        end
    end
    applied=true
    return true
end
-- Lets go for `key`; the last holder restores what the game had.
function M.release(key,force)
    holders[key]=nil
    if next(holders)~=nil and not force then return end
    if not applied then saved=nil;return end
    for _,step in ipairs(M.STEPS)do
        local value=saved and saved[step.get]
        if value==nil then value=step.default end
        if read(step.get)~=value then
            local ok,why=write(step.set,value)
            if not ok then emit('restore: '..why)end
        end
    end
    applied,saved=false,nil
end
function M.status()
    local list={}
    for key in pairs(holders)do list[#list+1]=key end
    table.sort(list)
    return {held=#list>0,holders=list,disabled=disabled,saved=saved,
        show_cursor=read('show_cursor'),clip_cursor=read('clip_cursor'),mouse_focus=read('mouse_focus')}
end
function M.reset_for_tests()holders,saved,applied,disabled,logged={},nil,false,nil,{}end
return M
