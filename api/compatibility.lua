-- Mods that need a newer HD2Runtime, reported by their own shipped wrapper (SDK 0.28.0 and later) just before the
-- wrapper's version check fails closed: the mod still does not start. Runtime logs every such mod with its exact
-- requirement and, once per session when the player is on the ship (the native game state Ship, held for a few
-- seconds), shows one aggregated, informational warning naming the highest required version. The warning is a
-- non-blocking Windows message box (WTSSendMessageW, no wait): the game keeps running, and any failure only logs.
-- Mods built with older SDKs never report and behave exactly as before.
local log=require('hd2runtime/runtime/log')
local M={}
local KEY='HD2RuntimeCompatibilityV1'
local state=rawget(_G,KEY)
if not state then
    state={mods={},order={},shown=false,attached=false,dialog=nil}
    rawset(_G,KEY,state)
end
M.SETTLE_SECONDS=5
M.TITLE='HD2Runtime update required'

-- SemVer 2.0: MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD]. Build metadata never affects precedence.
function M.parse(text)
    if type(text)~='string'then return nil end
    local core,pre=text:match('^([^%-+]+)%-?([^+]*)')
    local major,minor,patch=(core or''):match('^(%d+)%.(%d+)%.(%d+)$')
    if not major then return nil end
    if text:find('-',1,true)and pre==''then return nil end
    local ids={}
    if pre~=''then
        for id in (pre..'.'):gmatch('([^%.]*)%.')do
            if id==''or id:find('[^0-9A-Za-z%-]')then return nil end
            ids[#ids+1]=id
        end
    end
    return {major=tonumber(major),minor=tonumber(minor),patch=tonumber(patch),pre=ids}
end
local function compare_ids(a,c)
    local an,cn=a:match('^%d+$'),c:match('^%d+$')
    if an and cn then
        local x,y=tonumber(a),tonumber(c)
        return x<y and -1 or x>y and 1 or 0
    end
    if an then return -1 end
    if cn then return 1 end
    return a<c and -1 or a>c and 1 or 0
end
-- -1, 0 or 1; nil for a malformed version.
function M.compare(a,c)
    local x,y=M.parse(a),M.parse(c)
    if not x or not y then return nil end
    for _,key in ipairs({'major','minor','patch'})do
        if x[key]~=y[key]then return x[key]<y[key]and -1 or 1 end
    end
    -- A version with a prerelease has lower precedence than the same version without one.
    if #x.pre==0 or #y.pre==0 then
        return #x.pre==#y.pre and 0 or(#x.pre==0 and 1 or -1)
    end
    for index=1,math.max(#x.pre,#y.pre)do
        local p,q=x.pre[index],y.pre[index]
        if p==nil then return -1 end
        if q==nil then return 1 end
        local order=compare_ids(p,q)
        if order~=0 then return order end
    end
    return 0
end
-- The compatibility version (hd2.version: MAJOR.MINOR.PATCH of the installed build), the one every wrapper compares.
function M.installed()
    local v=require('hd2runtime/domains/metadata').version
    return tostring(v):match('^(%d+%.%d+%.%d+)')or v
end

-- Called by a mod's wrapper. Returns true when the installed Runtime satisfies `minimum`; otherwise records the mod
-- (once) and returns false with the reason. Equal and older requirements never warn.
function M.require_runtime(mod,minimum,display)
    assert(type(mod)=='string'and#mod>0 and#mod<=200,'mod identity required')
    local installed=M.installed()
    local order=M.compare(installed,minimum)
    if order==nil then
        log.emit('[HD2Runtime] mod '..mod..' declares an invalid HD2Runtime requirement: '..tostring(minimum))
        return false,'invalid requirement'
    end
    if order>=0 then return true end
    if not state.mods[mod]then
        state.mods[mod]={mod=mod,display=type(display)=='string'and display or nil,required=minimum}
        state.order[#state.order+1]=mod
        log.emit('[HD2Runtime] mod '..mod..(display and(' ('..display..')')or'')..' requires HD2Runtime '
            ..minimum..' or newer; installed '..installed..'. The mod was not started. Please update HD2Runtime.')
        M.arm()
    end
    return false,'requires HD2Runtime '..minimum..' (installed '..installed..')'
end
-- Every recorded mod, in report order, and the highest requirement among them.
function M.incompatible()
    local result={}
    for index,mod in ipairs(state.order)do local item=state.mods[mod];result[index]={mod=item.mod,
        display=item.display,required=item.required}end
    return result
end
function M.highest()
    local best
    for _,mod in ipairs(state.order)do
        local required=state.mods[mod].required
        if not best or M.compare(required,best)==1 then best=required end
    end
    return best
end
function M.message()
    local highest=M.highest()
    if not highest then return nil end
    return 'One or more installed mods require a newer HD2Runtime version.\n\nRequired version: '..highest
        ..'\nInstalled version: '..M.installed()..'\n\nPlease update HD2Runtime.'
end

-- The informational dialog: WTSSendMessageW with bWait = FALSE returns at once; the session shows the box on its
-- own. Only ASCII text is passed (versions and a fixed message).
local function wide(ffi,text)
    local buffer=ffi.new('uint16_t[?]',#text+1)
    for index=1,#text do buffer[index-1]=text:byte(index)end
    return buffer,#text*2
end
function M.windows_dialog(title,message)
    local ffi=require('ffi')
    pcall(ffi.cdef,[[int WTSSendMessageW(void *server, uint32_t session, uint16_t *title, uint32_t title_length,
        uint16_t *message, uint32_t message_length, uint32_t style, uint32_t timeout, uint32_t *response,
        int wait);]])
    local wts=ffi.load('wtsapi32')
    local t,tl=wide(ffi,title)
    local m,ml=wide(ffi,message)
    local response=ffi.new('uint32_t[1]')
    -- MB_OK | MB_ICONINFORMATION | MB_SETFOREGROUND | MB_TOPMOST; no timeout; WTS_CURRENT_SESSION; no wait.
    local ok=wts.WTSSendMessageW(nil,0xFFFFFFFF,t,tl,m,ml,0x00000040+0x00010000+0x00040000,0,response,0)
    if ok==0 then error('WTSSendMessageW failed',0)end
    return true
end
-- Tests replace the presenter and the game-state source; production uses the dialog and the native game state.
M.presenter=function(title,message)return M.windows_dialog(title,message)end
M.game_state=function()return require('hd2runtime/api/events').game_state()end

local function present()
    if state.shown then return end
    state.shown=true
    local message=M.message()
    for _,item in ipairs(M.incompatible())do
        log.emit('[HD2Runtime] update required: '..item.mod..' needs HD2Runtime '..item.required)
    end
    local ok,why=pcall(M.presenter,M.TITLE,message)
    state.dialog=ok and'shown'or'unavailable'
    log.emit('[HD2Runtime] HD2Runtime update warning '..(ok and'shown'or('could not be shown ('..tostring(why)
        ..'); see the lines above')))
end
-- Waits (cheaply, once a second) for a stable ship, then presents once per session.
function M.arm()
    if state.attached or state.shown then return end
    state.attached=true
    local watch={status='waiting'}
    local elapsed,next_poll,ship_polls=0,0,0
    function watch.tick(dt)
        if state.shown then watch.status='complete';return end
        elapsed=elapsed+dt
        if elapsed<next_poll then return end
        next_poll=elapsed+1
        -- Consecutive once-a-second polls that read the Ship state; anything else (loading, mission, unreadable)
        -- starts the count again.
        local ok,game=pcall(M.game_state)
        ship_polls=(ok and type(game)=='table'and game.name=='Ship')and ship_polls+1 or 0
        if ship_polls>=M.SETTLE_SECONDS then present();watch.status='complete'end
    end
    function watch.cancel()watch.status='cancelled'end
    local ok,why=pcall(function()require('hd2runtime/runtime/scheduler').attach(watch)end)
    if not ok then log.emit('[HD2Runtime] update warning scheduling failed: '..tostring(why))end
    state.watch=watch
    return watch
end
function M.status()
    return {incompatible=#state.order,highest=M.highest(),shown=state.shown,dialog=state.dialog}
end
-- Tests only: forget this session's reports.
function M._reset()
    state.mods,state.order,state.shown,state.attached,state.dialog,state.watch={},{},false,false,nil,nil
end
return M
