-- HD2Runtime's own settings and their in-game panel (0.30.2; docs/getting-started.md "Settings (F10)"). F10 opens a
-- small window in the HD2R Editor's look (its theme: dark panel, gold rail and accents, FS Sinclair) where each thing
-- the Runtime shows on screen can be turned off:
--   * startup_notice    the notice about public lobbies when you first board the ship;
--   * alert_cards       the custom stratagem alert cards (problems before a launch, DISABLED, vanilla names);
--   * version_label     the HD2Runtime / game build label in the bottom-left corner aboard the ship;
--   * startup_progress  the asset loading panel in the top-right corner while mods load.
-- Every setting is on by default and saved between sessions in the Runtime's own store (hd2.store's file for the owner
-- "hd2runtime"). Turning one off hides it at once; the log keeps every line either way. The panel is drawn through the
-- Runtime's mod overlay (runtime/mod_overlay.lua: a screen GUI in the Ui World) and frees the cursor while it is open.
-- Nothing of the game is written.
local log_module=require('hd2runtime/runtime/log')
local M={}
M.KEY='F10'
M.OWNER='hd2runtime'
M.BINDING='hd2runtime.settings'
M.ITEMS={
    {key='startup_notice',label='Startup notice',
        description='The public lobby notice when you first board the ship.'},
    {key='alert_cards',label='Custom stratagem alerts',
        description='Problems before a launch, and how to fix them.'},
    {key='version_label',label='Version label',
        description='The HD2Runtime build, bottom left aboard the ship.'},
    {key='startup_progress',label='Startup progress',
        description='The asset loading panel, top right, while mods load.'},
}
local KNOWN={}
for _,item in ipairs(M.ITEMS)do KNOWN[item.key]=item end
-- The HD2R Editor's theme (HD2RuntimeEditor src/editor/ui/theme.lua), the colours a, r, g, b as {r, g, b, a}.
M.COLOUR={panel={11,14,18,240},header={7,9,12,250},footer={7,9,12,250},rail={255,199,44,255},
    line={255,255,255,14},line_strong={255,255,255,30},text={234,234,228,255},dim={160,164,170,255},
    faint={104,110,118,255},inverse={14,16,20,255},gold={255,199,44,255},gold_dim={150,113,10,255},
    hover={255,255,255,10},shadow={0,0,0,110},error={255,96,84,255},error_soft={255,96,84,44}}
M.SIZE={title=22,heading=13,body=16,small=13,tiny=12}
M.CAP_OFFSET=(49.25-34.75/2)/56   -- FS Sinclair: from a line's vertical centre to its top
M.W,M.HEADER,M.FOOTER,M.ROW,M.PAD=560,58,46,52,18

local function log(text)pcall(log_module.emit,'[HD2Runtime] settings '..text)end

-------------------------------------------------------------------------------------------------- the values --
-- The Runtime's store (only inside the game: offline, and in tests unless replaced, the values live in memory).
M.hooks={}
function M.hooks.store()
    if type(rawget(_G,'stingray'))~='table'then return nil end
    return require('hd2runtime/runtime/mod_store').open(M.OWNER)
end
local memory={}
local listeners={}
local function store()
    local ok,s=pcall(M.hooks.store)
    return ok and s or nil
end
-- Whether a thing is shown (true unless turned off). Unknown keys are on.
function M.enabled(key)
    local s=store()
    if s then
        local ok,value=pcall(s.get,s,'show.'..key)
        if ok and value~=nil then return value~=false end
        return true
    end
    return memory[key]~=false
end
-- Turns a thing on or off (saved); listeners hear the change at once.
function M.set(key,on)
    assert(KNOWN[key],'unknown HD2Runtime setting: '..tostring(key))
    on=on~=false
    local s=store()
    if s then
        local ok,why=pcall(s.set,s,'show.'..key,on)
        if not ok then log('could not save '..key..': '..tostring(why))end
    else memory[key]=on end
    log(('%s %s'):format(KNOWN[key].label,on and'ON'or'OFF'))
    for _,fn in ipairs(listeners)do pcall(fn,key,on)end
    return on
end
-- fn(key, on) whenever a setting changes.
function M.on_change(fn)listeners[#listeners+1]=fn end

-------------------------------------------------------------------------------------------------- the panel --
local panel={overlay=nil,binding=nil,was_left=false,hover=nil}
local function clicked_in(m,box)
    return m and m.x>=box.x and m.x<=box.x+box.w and m.y>=box.y and m.y<=box.y+box.h
end
-- Lays the panel out for a w x h overlay at scale s: {x, y, w, h, k, rows = {{item, box, toggle}}, close}. Pure.
function M.layout(width,height,scale)
    local h=M.HEADER+M.PAD+22+#M.ITEMS*M.ROW+M.PAD+22+3*22+M.PAD+M.FOOTER
    local k=math.max(0.5,math.min(scale,width/(M.W+24),height/(h+24)))
    local w=M.W*k
    local x,y=math.floor((width-w)/2),math.floor((height-h*k)/2)
    local L={x=x,y=y,w=w,h=h*k,k=k,rows={}}
    local cy=y+(M.HEADER+M.PAD)*k
    L.messages_y=cy
    cy=cy+22*k
    for _,item in ipairs(M.ITEMS)do
        L.rows[#L.rows+1]={item=item,box={x=x+M.PAD*k,y=cy,w=w-2*M.PAD*k,h=(M.ROW-6)*k},y=cy}
        cy=cy+M.ROW*k
    end
    L.about_y=cy+M.PAD*k
    L.close={x=x+w-50*k,y=y+12*k,w=36*k,h=34*k}
    return L
end
local function text(d,s,x,cy,size,colour,font,align,z)
    d:text(s,x,cy-size*M.CAP_OFFSET,{size=size,colour=colour,font=font or'body',align=align,z=z or 5})
end
local function about_lines()
    local ok,label=pcall(require,'hd2runtime/runtime/version_label')
    local first,second='HD2Runtime','Game'
    if ok and label.lines then first,second=label.lines()end
    local wheel='Mouse wheel hook: unknown'
    local okw,mw=pcall(require,'hd2runtime/runtime/mouse_wheel')
    if okw and mw.native_allowed then
        local okn,allowed=pcall(mw.native_allowed)
        if okn then wheel='Mouse wheel hook: '..(allowed and'on'or'off (the install choice)')end
    end
    return {first..'  |  '..second,wheel,'Settings are saved for every game session.'}
end
-- One frame of the panel (the overlay's draw function).
function M.draw(d,mouse,input)
    local C,S=M.COLOUR,M.SIZE
    local L=M.layout(d.width,d.height,d.scale)
    local k,x,y,w=L.k,L.x,L.y,L.w
    local press=mouse and mouse.left and not panel.was_left
    panel.was_left=mouse and mouse.left or false
    -- The window: shadow, panel, the gold rail; the header; the footer.
    d:rect(x-4*k,y-4*k,w+8*k,L.h+8*k,C.shadow,0)
    d:rect(x,y,w,L.h,C.panel,0)
    d:rect(x,y,w,M.HEADER*k,C.header,1)
    d:rect(x,y+M.HEADER*k-1,w,math.max(1,k),C.line_strong,2)
    d:rect(x,y,3*k,L.h,C.rail,7)
    local hy=y+M.HEADER*k/2
    text(d,'HD2R',x+20*k,hy,S.title*k,C.text,'title')
    text(d,'RUNTIME',x+20*k+d:text_width('HD2R ',S.title*k,'title'),hy,S.title*k,C.gold,'title')
    text(d,'SETTINGS',x+w-62*k,hy,S.heading*k,C.faint,'title','right')
    local close_hover=clicked_in(mouse,L.close)
    d:rect(L.close.x,L.close.y,L.close.w,L.close.h,close_hover and C.error_soft or C.panel,3)
    d:rect(L.close.x,L.close.y,L.close.w,math.max(1,k),close_hover and C.error or C.line_strong,4)
    d:rect(L.close.x,L.close.y+L.close.h-math.max(1,k),L.close.w,math.max(1,k),close_hover and C.error or C.line_strong,4)
    text(d,'x',L.close.x+L.close.w/2,L.close.y+L.close.h/2,20*k,close_hover and C.error or C.dim,'title','center')
    -- MESSAGES: one toggle row per setting.
    local function section(label,sy)
        text(d,label,x+M.PAD*k,sy,S.tiny*k,C.gold_dim,'title')
        local lw=d:text_width(label,S.tiny*k,'title')
        d:rect(x+M.PAD*k+lw+10*k,sy,w-2*M.PAD*k-lw-10*k,math.max(1,k),C.line,2)
    end
    section('MESSAGES ON SCREEN',L.messages_y)
    local hit
    for _,row in ipairs(L.rows)do
        local on=M.enabled(row.item.key)
        local hovered=clicked_in(mouse,row.box)
        if hovered then hit=row;d:rect(row.box.x-6*k,row.box.y,row.box.w+12*k,row.box.h,C.hover,2)end
        local tx,ty=row.box.x,row.box.y+row.box.h/2
        d:rect(tx,ty-9*k,34*k,18*k,on and C.gold or C.line_strong,3)
        d:rect(on and tx+18*k or tx+2*k,ty-7*k,14*k,14*k,on and C.inverse or C.dim,4)
        text(d,row.item.label,tx+48*k,ty-8*k,S.body*k,C.text,'body')
        text(d,row.item.description,tx+48*k,ty+10*k,S.small*k,C.dim,'body')
        text(d,on and'ON'or'OFF',row.box.x+row.box.w,ty,S.tiny*k,on and C.gold or C.faint,'title','right')
    end
    section('ABOUT',L.about_y)
    for n,line in ipairs(about_lines())do
        text(d,line,x+M.PAD*k,L.about_y+(14+(n-1)*22)*k,S.small*k,n==3 and C.faint or C.dim,'body')
    end
    -- The footer.
    local fy=y+L.h-M.FOOTER*k
    d:rect(x,fy,w,M.FOOTER*k,C.footer,1)
    d:rect(x,fy,w,math.max(1,k),C.line_strong,2)
    text(d,'F10 or Esc closes  |  click a row to turn it on or off',x+M.PAD*k,fy+M.FOOTER*k/2,S.small*k,C.faint,'body')
    -- Input: a click on a row toggles it; the x or Esc closes.
    if press and hit then M.set(hit.item.key,not M.enabled(hit.item.key))end
    if(press and close_hover)or(input and input.pressed('ESCAPE'))then M.close()end
    return L
end

function M.open()
    if not panel.overlay then
        local overlay=require('hd2runtime/runtime/mod_overlay')
        panel.overlay=overlay.open(M.OWNER,{id='settings',visible=false,layer=980})
        panel.overlay:free_cursor(true)
        local input=require('hd2runtime/runtime/input')
        panel.overlay:draw(function(d)
            local m=panel.overlay:mouse()
            local ok,err=pcall(M.draw,d,m,input)
            if not ok then
                d:rect(0,0,d.width,4,{255,96,84,230})
                if not panel.failed then panel.failed=true;log('panel draw failed: '..tostring(err))end
            end
        end)
    end
    panel.was_left=true   -- a held button is not a click
    panel.overlay:show(true)
    log('panel opened')
end
function M.close()
    if panel.overlay then panel.overlay:hide()end
end
function M.toggle()
    if panel.overlay and panel.overlay:status().visible then M.close()else M.open()end
end
function M.visible()return panel.overlay~=nil and panel.overlay:status().visible==true end
-- Binds F10 (once). The Runtime binds at load, before any mod, so F10 is its own.
function M.start()
    if panel.binding then return panel.binding end
    local input=require('hd2runtime/runtime/input')
    panel.binding=input.bind(M.BINDING,{key=M.KEY,on_press=function()M.toggle()end},M.OWNER)
    return panel.binding
end
function M.reset_for_tests()
    if panel.overlay then pcall(panel.overlay.close,panel.overlay)end
    panel={overlay=nil,binding=nil,was_left=false}
    memory,listeners={},{}
end
return M
