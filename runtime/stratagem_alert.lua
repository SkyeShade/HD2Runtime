-- The custom stratagem alert card (0.30.2, docs/custom-stratagem-api.md "Readiness"): a Runtime-owned card at the top
-- right of the screen that says what will make custom stratagems fail and how to fix it. One card per subject
-- (readiness, disabled, ...); the most severe shows, the newest of equal severity first. It is drawn the way every
-- other Runtime panel is: a screen GUI in the Ui World (runtime/stratagem_slot_overlay.lua open_gui, through
-- init_progress's hooks) in the native loadout typeface (runtime/ui_fonts.lua: FS Sinclair, monaco when it is not
-- loaded), the colours of the native details panel and a severity accent. Read-only: nothing of the game is written.
-- When the card cannot be drawn (a GUI error), its subject goes to the small safety notice panel instead
-- (runtime/matchmaking_safety.lua notice), the path used before; the log keeps every line either way.
--
-- post({key, severity, title, tag, items = {{line, fix}}, footer, seconds}); clear(key); status().
local scheduler=require('hd2runtime/runtime/scheduler')
local log_module=require('hd2runtime/runtime/log')
local fonts=require('hd2runtime/runtime/ui_fonts')
local M={}

M.SCALE=1.6              -- the card's size, times its base layout (520 x n units at 1080p)
M.SECONDS=14             -- how long a card stays on screen
M.WAIT=120               -- how long a card waits for a drawable screen before it is dropped (the log keeps it)
M.REPEAT=20              -- seconds before the same card (key and text) is shown again
M.MAX_ITEMS=3            -- problems listed on the card; the rest are counted ("+2 more in the HD2Runtime log")
M.RETRY=0.5              -- seconds between two tries to draw a card that is not drawable yet (no font, no Ui World)
M.LAYER=935              -- above the safety notice (930), below the slot overlay (940)
M.SEVERITY={fail=3,warn=2,ok=1}
-- The native details panel's colours (runtime/custom_stratagem_panel.lua NATIVE_COLOURS) and one accent per severity.
M.COLOURS={plate={232,10,11,12},edge={255,54,56,58},rule={255,40,42,44},title={255,244,244,236},
    text={255,222,222,214},fix={255,178,178,170},dim={255,132,132,126},
    accent={fail={255,226,72,56},warn={255,240,190,90},ok={255,110,196,120}}}

local function fresh()return {clock=0,alerts={},order=0,shown={},current=nil,screen=nil,timer=nil,gui_disabled=false,
    watch=nil}end
local state=fresh()
-- Whether an on-screen item is on in the HD2Runtime settings (F10; on when the settings cannot be read).
local function shown(key)
    local ok,settings=pcall(require,'hd2runtime/runtime/runtime_settings')
    if not(ok and type(settings)=='table'and settings.enabled)then return true end
    local okv,on=pcall(settings.enabled,key)
    return not okv or on~=false
end
local function log(text)log_module.emit('[HD2Runtime] '..text)end

-- The hooks the card is drawn through (tests replace them): the screen, and the title and body fonts (nil and why while
-- no font is loaded).
M.hooks={}
function M.hooks.open_screen(world)return require('hd2runtime/runtime/init_progress').hooks.open_screen(world)end
function M.hooks.world()return require('hd2runtime/runtime/event_world').open()end
function M.hooks.fonts(world)
    local title,body=fonts.font(world.runtime,'title'),fonts.font(world.runtime,'body')
    -- A fallback is monaco: drawable only once the engine font itself is loaded.
    if(title.fallback or body.fallback)and not require('hd2runtime/runtime/init_progress').hooks.font()then
        return nil,'the engine font is not loaded'
    end
    return title,body
end
-- The safety notice panel: where a subject goes when the card cannot be drawn.
function M.hooks.fallback(alert)
    local ok,safety=pcall(require,'hd2runtime/runtime/matchmaking_safety')
    if not(ok and type(safety)=='table'and safety.notice)then return false end
    local first=alert.items[1]or{}
    local more=#alert.items>1 and(' (+'..(#alert.items-1)..' more in the log)')or''
    local title=string.upper(alert.title)..(alert.tag and(' - '..string.upper(alert.tag))or'')
    return pcall(safety.notice,title,(first.line or'')..more,first.fix,alert.footer)
end

local function close_screen()
    if state.screen then pcall(state.screen.close)end
    state.screen,state.timer=nil,nil
end
-- The alert on screen: the most severe, the newest of equal severity.
local function pick()
    local best
    for _,a in pairs(state.alerts)do
        if not best or M.SEVERITY[a.severity]>M.SEVERITY[best.severity]
            or(M.SEVERITY[a.severity]==M.SEVERITY[best.severity]and a.order>best.order)then best=a end
    end
    return best
end

local function clean(s)
    s=tostring(s or''):gsub('[%z\1-\31\127]',' '):gsub('%s+',' '):gsub('^ ',''):gsub(' $','')
    return s
end
-- The card's layout for a width x height screen: {x, y, w, h, u} and the drawing list (each {kind, ...}), from the
-- alert and the fonts (their metrics wrap the lines). Pure: no engine call.
function M.layout(alert,W,H,title_font,body_font)
    local u=H/1080
    local margin=24*u
    local k=math.min(M.SCALE,(W*0.9-margin)/(520*u))
    u=u*k
    local w=520*u
    local pad,accent_w=16*u,4*u
    local inner=w-pad*2-accent_w
    local accent=M.COLOURS.accent[alert.severity]or M.COLOURS.accent.warn
    local ops={}
    local function text(s,font,cap,x,top,colour)
        local size=fonts.size_for_cap(font,cap*u)
        ops[#ops+1]={kind='text',s=s,font=font.name,size=size,x=x,y=top-cap*u,colour=colour}
        return size
    end
    -- Laid out top-down from y = 0 (the card's top); moved to the screen at the end.
    local y=-pad
    local left=accent_w+pad
    -- The header: the title (upper case, the title font) and the tag right-aligned in the accent colour.
    local tag=alert.tag and string.upper(alert.tag)
    if tag then
        local size=fonts.size_for_cap(title_font,8*u)
        local tw=fonts.width(title_font,tag,size)
        text(tag,title_font,8,w-pad-tw,y-3*u,accent)     -- on the title's baseline
    end
    text(string.upper(alert.title),title_font,11,left,y,M.COLOURS.title)
    y=y-11*u-10*u
    ops[#ops+1]={kind='rect',x=left,y=y,w=inner,h=math.max(1,u),colour=M.COLOURS.rule}
    y=y-12*u
    -- The problems: a square bullet in the accent, the problem (2 lines at most) and its fix (2 lines at most).
    local body_cap,fix_cap=8.5,7.5
    local bsize=fonts.size_for_cap(body_font,body_cap*u)
    local fsize=fonts.size_for_cap(body_font,fix_cap*u)
    local label_size=fonts.size_for_cap(title_font,fix_cap*u)
    local label_w=fonts.width(title_font,'FIX',label_size)+5*u
    local tx=left+14*u
    for i=1,math.min(#alert.items,M.MAX_ITEMS)do
        local item=alert.items[i]
        if i>1 then y=y-10*u end
        ops[#ops+1]={kind='rect',x=left+1*u,y=y-body_cap*u+0.5*u,w=6*u,h=6*u,colour=accent}
        for n,line in ipairs(fonts.wrap(body_font,clean(item.line),bsize,w-pad-tx,2))do
            if n>1 then y=y-body_cap*u*1.75 end
            text(line,body_font,body_cap,tx,y,M.COLOURS.text)
        end
        y=y-body_cap*u
        local fix=clean(item.fix):gsub('^[Ff]ix:%s*','')
        if fix~=''then
            y=y-7*u
            text('FIX',title_font,fix_cap,tx,y,accent)
            for n,line in ipairs(fonts.wrap(body_font,fix,fsize,w-pad-tx-label_w,2))do
                if n>1 then y=y-fix_cap*u*1.75 end
                text(line,body_font,fix_cap,tx+label_w,y,M.COLOURS.fix)
            end
            y=y-fix_cap*u
        end
    end
    local rest=#alert.items-M.MAX_ITEMS
    if rest>0 then
        y=y-10*u
        text(('+%d more in the HD2Runtime log'):format(rest),body_font,7,tx,y,M.COLOURS.dim)
        y=y-7*u
    end
    if alert.footer and alert.footer~=''then
        y=y-12*u
        for n,line in ipairs(fonts.wrap(body_font,clean(alert.footer),fonts.size_for_cap(body_font,7*u),inner,1))do
            if n==1 then text(line,body_font,7,left,y,M.COLOURS.dim)end
        end
        y=y-7*u
    end
    y=y-pad
    local h=-y
    -- The screen place: the top right, below the startup progress panel's place (bottom-left origin).
    local x0,y0=W-w-margin,H-margin-(72+12)*(H/1080)-h
    for _,op in ipairs(ops)do op.x,op.y=x0+op.x,y0+h+op.y end
    -- The plate, its edge, the accent bar and the timer bar (along the bottom edge; it shrinks while the card shows).
    table.insert(ops,1,{kind='rect',x=x0,y=y0,w=w,h=h,colour=M.COLOURS.plate,layer=0})
    table.insert(ops,2,{kind='rect',x=x0,y=y0+h-math.max(1,u),w=w,h=math.max(1,u),colour=M.COLOURS.edge,layer=1})
    table.insert(ops,3,{kind='rect',x=x0,y=y0,w=accent_w,h=h,colour=accent,layer=1})
    local timer={kind='rect',x=x0+accent_w,y=y0,w=w-accent_w,h=2*u,colour={170,accent[2],accent[3],accent[4]},layer=1,
        timer=true}
    ops[#ops+1]=timer
    return {x=x0,y=y0,w=w,h=h,u=u,ops=ops,timer=timer}
end

local function draw(world,alert)
    local title_font,body_font=M.hooks.fonts(world)
    if not title_font then return nil,body_font end
    local screen,why=M.hooks.open_screen(world)
    if not screen then return nil,why end
    state.screen=screen
    local L=M.layout(alert,screen.width,screen.height,title_font,body_font)
    local ok,err=pcall(function()
        for _,op in ipairs(L.ops)do
            local layer=M.LAYER+(op.layer or 2)
            local id
            if op.kind=='rect'then id=screen.rect(op.x,op.y,layer,op.w,op.h,op.colour)
            else id=screen.text(op.s,op.font,op.size,op.font,op.x,op.y,layer,op.colour)end
            if id==nil then error(('the card %s was refused (%s)'):format(op.kind,tostring(op.s or'')),0)end
            if op.timer then state.timer={id=id,op=op,layer=layer,frac=1}end
        end
    end)
    if not ok then return nil,err,true end
    return true
end

-- The shrinking timer bar: moved at most every 1 % of its length (update_rect; a failure leaves it as it is).
local function step_timer(a)
    local t=state.timer
    if not(t and state.screen and state.screen.update_rect)then return end
    local frac=math.max(0,1-(state.clock-a.shown_at)/a.seconds)
    if t.frac-frac<0.01 then return end
    t.frac=frac
    local op=t.op
    local ok=pcall(state.screen.update_rect,t.id,op.x,op.y,t.layer,op.w*frac,op.h,op.colour)
    if not ok then state.timer=nil end
end

local function tick(dt)
    state.clock=state.clock+(type(dt)=='number'and dt>=0 and dt<10 and dt or 0)
    -- Turned off while a card shows: it goes at once, and every queued card with it.
    if not shown('alert_cards')then state.alerts={};close_screen();state.current=nil;return 'idle'end
    local a=pick()
    if not a then close_screen();state.current=nil;return 'idle'end
    if state.current~=a or a.dirty then
        close_screen()
        state.current=a
        a.dirty=false
        a.shown_at=nil
    end
    if a.shown_at then
        if state.clock-a.shown_at>=a.seconds then
            close_screen();state.alerts[a.key]=nil;state.current=nil
        else step_timer(a)end
        return 'shown'
    end
    if state.clock-a.queued>=M.WAIT then state.alerts[a.key]=nil;state.current=nil;return 'dropped'end
    if state.gui_disabled then
        M.hooks.fallback(a);state.alerts[a.key]=nil;state.current=nil
        return 'fallback'
    end
    if state.clock<(a.next_try or 0)then return 'waiting'end
    a.next_try=state.clock+M.RETRY
    local world=M.hooks.world()
    if not world then return 'waiting'end
    local ok,drawn,why,fatal=pcall(draw,world,a)
    if ok and drawn then a.shown_at=state.clock;return 'shown'end
    close_screen()
    a.why=why
    if not ok or fatal then
        -- A GUI error: the card is off for the session; this and every later subject go to the safety notice panel.
        state.gui_disabled=true
        log('CUSTOM STRATAGEM ALERT: the card is unavailable ('..tostring(ok and why or drawn)..'); the safety notice '
            ..'panel shows the alerts instead and the log keeps every line')
        M.hooks.fallback(a);state.alerts[a.key]=nil;state.current=nil
        return 'fallback'
    end
    return 'waiting'
end
M.tick_for_tests=tick

local function start()
    if state.watch and state.watch.status=='active'then return end
    local watch={status='active'}
    function watch.cancel()watch.status='cancelled';close_screen()end
    function watch.tick(dt)
        if watch.status~='active'then return end
        local ok,result=pcall(tick,dt)
        if not ok then log('CUSTOM STRATAGEM ALERT STEP FAILED: '..tostring(result))
        elseif result=='idle'then watch.status='complete'end   -- nothing to show: the update hook may detach
    end
    state.watch=watch
    pcall(scheduler.attach,watch)
end

-- Shows an alert card: {key (its subject; a newer card of the same key replaces it), severity ('fail', 'warn' or 'ok'),
-- title, tag (a short word at the right of the title), items ({line (what fails), fix (how to fix it)} each), footer,
-- seconds}. The same key and text is not shown again within M.REPEAT s unless force. Returns whether it was queued.
function M.post(alert,force)
    if type(alert)~='table'or type(alert.key)~='string'or type(alert.title)~='string'then return false end
    -- Turned off in the HD2Runtime settings (F10): nothing is shown (the callers log every problem anyway).
    if not shown('alert_cards')then return false end
    local items={}
    for _,i in ipairs(alert.items or{})do items[#items+1]={line=clean(i.line),fix=i.fix and clean(i.fix)or nil}end
    local a={key=alert.key,severity=M.SEVERITY[alert.severity]and alert.severity or'warn',title=clean(alert.title),
        tag=alert.tag and clean(alert.tag)or nil,items=items,footer=alert.footer and clean(alert.footer)or nil,
        seconds=type(alert.seconds)=='number'and alert.seconds>0 and alert.seconds or M.SECONDS}
    local parts={a.key,a.severity,a.title,a.tag or'',a.footer or''}
    for _,i in ipairs(items)do parts[#parts+1]=i.line..'/'..(i.fix or'')end
    local text=table.concat(parts,'|')
    local last=state.shown[text]
    if not force and last and state.clock-last<M.REPEAT then return false end
    state.shown[text]=state.clock
    state.order=state.order+1
    a.order,a.queued,a.dirty=state.order,state.clock,true
    state.alerts[a.key]=a
    start()
    return true
end
-- Removes the card of a subject (on screen or queued): its problem is gone.
function M.clear(key)
    if state.alerts[key]then state.alerts[key]=nil;return true end
    return false
end
-- Development / tests: what the card shows.
function M.status()
    local a=state.current
    return {clock=state.clock,visible=state.screen~=nil,key=a and a.key,severity=a and a.severity,
        queued=(function()local n=0;for _ in pairs(state.alerts)do n=n+1 end;return n end)(),
        gui_disabled=state.gui_disabled,timer=state.timer and state.timer.frac}
end
function M.reset_for_tests()
    close_screen()
    if state.watch then state.watch.status='cancelled'end
    state=fresh()
end
return M
