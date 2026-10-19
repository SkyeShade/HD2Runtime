-- HD2Runtime's own settings and their in-game panel (0.30.2; docs/getting-started.md "Settings (F10)"). F10 opens a
-- small window in the HD2R Editor's look (its theme: dark panel, gold rail and accents, FS Sinclair) where each thing
-- the Runtime shows on screen can be turned off:
--   * startup_notice    the notice about public lobbies when you first board the ship;
--   * alert_cards       the custom stratagem alert cards (problems before a launch, DISABLED, vanilla names);
--   * version_label     the HD2Runtime / game build label in the bottom-left corner aboard the ship;
--   * startup_progress  the asset loading panel in the top-right corner while mods load.
-- 0.31.1: a Language setting (a list: Automatic follows the game's language, or one of the game languages), the language
-- every text the Runtime shows is in (runtime/i18n.lua); and hd2.ui.open_settings() opens the panel from a mod.
-- 0.31.1: an Interface size (the HD2R Editor's choices, 90 to 150 %, kept to what fits the screen), and two tabs:
-- SETTINGS and PERFORMANCE (runtime/performance_panel.lua: a live graph of the time the Runtime and each mod take,
-- measured only while that tab is shown).
-- Every setting is on by default and saved between sessions in the Runtime's own store (hd2.store's file for the owner
-- "hd2runtime"). Turning one off hides it at once; the log keeps every line either way. The panel is drawn through the
-- Runtime's mod overlay (runtime/mod_overlay.lua: a screen GUI in the Ui World) and frees the cursor while it is open.
-- Nothing of the game is written.
local log_module=require('hd2runtime/runtime/log')
local i18n=require('hd2runtime/runtime/i18n')
local T=i18n.t
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
    {key='ui_sounds',label='Menu sounds',
        description='Play interface sounds when opening, closing or changing this menu.'},
    -- runtime/application_mode.lua: off by default (0.40.1); off is the 0.31 behaviour.
    {key='optimized_application',label='Faster application (0.40.0)',default=false,
        description='Caches and fewer checks while mods apply. Turn off if the game fails to start.'},
    {key='startup_progress',label='Startup progress',
        description='The asset loading panel, top right, while mods load.'},
}
local KNOWN={}
for _,item in ipairs(M.ITEMS)do KNOWN[item.key]=item end
-- The interface sizes (the HD2R Editor's, theme.UI_SCALES).
M.UI_SCALES={0.9,1,1.1,1.25,1.4,1.5}
-- Settings that hold a value rather than on / off: their default, and the values they accept.
M.VALUES={language={default=i18n.AUTO,valid=function(v)
    if v==i18n.AUTO then return true end
    for _,item in ipairs(i18n.languages())do if item.code==v then return true end end
    return false
end},ui_scale={default=1,valid=function(v)
    for _,s in ipairs(M.UI_SCALES)do if s==v then return true end end
    return false
end}}
-- The HD2R Editor's theme (HD2RuntimeEditor src/editor/ui/theme.lua), the colours a, r, g, b as {r, g, b, a}.
M.COLOUR={panel={11,14,18,240},header={7,9,12,250},footer={7,9,12,250},rail={255,199,44,255},
    line={255,255,255,14},line_strong={255,255,255,30},text={234,234,228,255},dim={160,164,170,255},
    faint={104,110,118,255},inverse={14,16,20,255},gold={255,199,44,255},gold_dim={150,113,10,255},
    hover={255,255,255,10},shadow={0,0,0,110},error={255,96,84,255},error_soft={255,96,84,44}}
M.SIZE={title=22,heading=13,body=16,small=13,tiny=12}
M.CAP_OFFSET=(49.25-34.75/2)/56   -- FS Sinclair: from a line's vertical centre to its top
M.W,M.HEADER,M.FOOTER,M.ROW,M.PAD=700,58,46,43,18
M.OPTION=30   -- a row of the language list

local function log(text)pcall(log_module.emit,'[HD2Runtime] settings '..text)end
local function performance()return require('hd2runtime/runtime/performance_panel')end

-------------------------------------------------------------------------------------------------- the values --
-- The Runtime's store (only inside the game: offline, and in tests unless replaced, the values live in memory).
M.hooks={}
function M.hooks.block(on)
    return require('hd2runtime/runtime/mouse_wheel').block(on and{keyboard=true,mouse=true}or false,'hd2runtime.settings')
end
function M.hooks.sound(event)return require('hd2runtime/runtime/sound_events').play(M.OWNER,event)end
local sound_last=-math.huge
local sound_failed={}
local SOUND={open='ui/slot_select',back='ui/picker_close',click='ui/generic_select'}
function M.sound(kind)
    if not M.enabled('ui_sounds')then return end
    local event=SOUND[kind];if not event then return end
    local t=require('hd2runtime/runtime/events').state.now or 0
    if t-sound_last<0.04 or(sound_failed[event]and t-sound_failed[event]<30)then return end
    sound_last=t
    local ok,handle=pcall(M.hooks.sound,event)
    sound_failed[event]=not(ok and handle)and t or nil
end

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
-- Whether a thing is on: its saved choice, else its default (on unless the item says default = false). Unknown keys
-- are on.
function M.enabled(key)
    local default=not(KNOWN[key]and KNOWN[key].default==false)
    local s=store()
    if s then
        local ok,value=pcall(s.get,s,'show.'..key)
        if ok and value~=nil then return value~=false end
        return default
    end
    if memory[key]==nil then return default end
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
    if key=='optimized_application'then require('hd2runtime/runtime/application_mode').configure(on)end
    for _,fn in ipairs(listeners)do pcall(fn,key,on)end
    return on
end
-- A value setting (M.VALUES): its saved value, or its default.
function M.value(key)
    local spec=assert(M.VALUES[key],'unknown HD2Runtime value setting: '..tostring(key))
    local s=store()
    local value
    if s then
        local ok,v=pcall(s.get,s,'setting.'..key)
        if ok then value=v end
    else value=memory['value.'..key]end
    if value==nil or not spec.valid(value)then return spec.default end
    return value
end
-- Sets a value setting (saved); listeners hear it as fn(key, value).
function M.set_value(key,value)
    local spec=assert(M.VALUES[key],'unknown HD2Runtime value setting: '..tostring(key))
    assert(spec.valid(value),'not a value of '..key..': '..tostring(value))
    local s=store()
    if s then
        local ok,why=pcall(s.set,s,'setting.'..key,value)
        if not ok then log('could not save '..key..': '..tostring(why))end
    else memory['value.'..key]=value end
    log(('%s = %s'):format(key,tostring(value)))
    for _,fn in ipairs(listeners)do pcall(fn,key,value)end
    return value
end
-- fn(key, value) whenever a setting changes (true / false for a toggle).
function M.on_change(fn)listeners[#listeners+1]=fn end

-------------------------------------------------------------------------------------------------- the panel --
local panel={overlay=nil,binding=nil,was_left=false,hover=nil,tab='settings'}
M.TABS={{id='settings',label='SETTINGS'},{id='performance',label='PERFORMANCE'}}
local function clicked_in(m,box)
    return m and m.x>=box.x and m.x<=box.x+box.w and m.y>=box.y and m.y<=box.y+box.h
end
-- Steps the interface size one choice up (+1) or down (-1); returns the new size.
function M.step_ui_scale(direction)
    local list,now,index=M.UI_SCALES,M.value('ui_scale'),1
    for i,v in ipairs(list)do if v==now then index=i end end
    local target=list[math.max(1,math.min(#list,index+direction))]
    if target~=now then M.set_value('ui_scale',target)end
    return target
end
-- Lays the panel out for a w x h overlay at scale s: {x, y, w, h, k, rows = {{item, box, toggle}}, close, tabs,
-- content}. The interface size multiplies the screen's scale, kept to what fits (L.fits: the size shown). Pure.
function M.layout(width,height,scale)
    local settings_h=22+M.ROW+M.PAD+22+M.ROW+M.PAD+22+#M.ITEMS*M.ROW+M.PAD+22+3*22
    local h=M.HEADER+M.PAD+math.max(settings_h,performance().HEIGHT)+M.PAD+M.FOOTER
    local chosen=M.value('ui_scale')
    local k=math.max(0.5,math.min(scale*chosen,width/(M.W+24),height/(h+24)))
    local w=M.W*k
    local x,y=math.floor((width-w)/2),math.floor((height-h*k)/2)
    local L={x=x,y=y,w=w,h=h*k,k=k,rows={},fits=scale>0 and k/scale or chosen,chosen=chosen}
    L.content={x=x+M.PAD*k,y=y+(M.HEADER+M.PAD)*k,w=w-2*M.PAD*k,h=(h-M.HEADER-M.FOOTER-2*M.PAD)*k}
    -- the tabs, right of the title
    local tx=x+w-62*k
    L.tabs={}
    for n=#M.TABS,1,-1 do
        local tw=(M.TABS[n].id=='performance'and 150 or 112)*k
        tx=tx-tw
        L.tabs[n]={tab=M.TABS[n],box={x=tx,y=y+10*k,w=tw,h=M.HEADER*k-20*k}}
        tx=tx-6*k
    end
    local cy=y+(M.HEADER+M.PAD)*k
    -- LANGUAGE: one list row
    L.language_y=cy
    cy=cy+22*k
    L.language={x=x+M.PAD*k,y=cy,w=w-2*M.PAD*k,h=(M.ROW-6)*k}
    cy=cy+(M.ROW+M.PAD)*k
    -- INTERFACE: the size row, its - and + buttons
    L.interface_y=cy
    cy=cy+22*k
    L.size={x=x+M.PAD*k,y=cy,w=w-2*M.PAD*k,h=(M.ROW-6)*k}
    local by=L.size.y+L.size.h/2-14*k
    L.size_up={x=L.size.x+L.size.w-30*k,y=by,w=30*k,h=28*k}
    L.size_down={x=L.size_up.x-110*k,y=by,w=30*k,h=28*k}
    cy=cy+M.ROW*k
    local function add_row(item)
        L.rows[#L.rows+1]={item=item,box={x=x+M.PAD*k,y=cy,w=w-2*M.PAD*k,h=(M.ROW-6)*k},y=cy}
        cy=cy+M.ROW*k
    end
    add_row(KNOWN.ui_sounds)
    add_row(KNOWN.optimized_application)
    cy=cy+M.PAD*k
    L.messages_y=cy
    cy=cy+22*k
    for _,item in ipairs(M.ITEMS)do
        if item.key~='ui_sounds'and item.key~='optimized_application'then add_row(item)end
    end
    L.about_y=cy+M.PAD*k
    L.close={x=x+w-50*k,y=y+12*k,w=36*k,h=34*k}
    -- the open language list: below its row, every option (Automatic first), kept on screen
    local options={{code=i18n.AUTO}}
    for _,item in ipairs(i18n.languages())do options[#options+1]={code=item.code,name=item.name}end
    local lh=#options*M.OPTION*k
    local ly=math.min(L.language.y+L.language.h,math.max(0,height-lh))
    L.options={}
    for n,option in ipairs(options)do
        L.options[n]={option=option,box={x=L.language.x,y=ly+(n-1)*M.OPTION*k,w=L.language.w,h=M.OPTION*k}}
    end
    return L
end
local function text(d,s,x,cy,size,colour,font,align,z)
    d:text(s,x,cy-size*M.CAP_OFFSET,{size=size,colour=colour,font=font or'body',align=align,z=z or 5})
end
local function about_lines()
    local ok,label=pcall(require,'hd2runtime/runtime/version_label')
    local first,second='HD2Runtime','Game'
    if ok and label.lines then first,second=label.lines()end
    local wheel=T('Mouse wheel hook: unknown')
    local okw,mw=pcall(require,'hd2runtime/runtime/mouse_wheel')
    if okw and mw.native_allowed then
        local okn,allowed=pcall(mw.native_allowed)
        if okn then wheel=allowed and T('Mouse wheel hook: on')or T('Mouse wheel hook: off (the install choice)')end
    end
    return {first..'  |  '..second,wheel,T('Settings are saved for every game session.')}
end
-- The language list's text for a value: a language's own name, or Automatic with the game's language.
function M.language_text(code)
    if code==i18n.AUTO then
        local game=i18n.game_language()
        return game and T('Automatic (the game: %s)',i18n.name(game)or game)or T("Automatic (the game's language)")
    end
    return i18n.name(code)or code
end
-- One frame of the panel (the overlay's draw function).
function M.draw(d,mouse,input)
    -- One breadcrumb on entering a view, not a frame-by-frame trace. A native GUI crash cannot be caught by pcall.
    local view=panel.tab..(panel.tab=='performance'and('/'..performance().mode())or(panel.menu and'/languages'or''))
    d._diagnostic_view='F10 '..view
    if panel.draw_view~=view then
        panel.draw_view=view
        log(('layout begin: %s (%sx%s)'):format(view,tostring(d.width),tostring(d.height)))
    end
    pcall(M.hooks.block,true)
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
    -- The tabs: the open one gold and underlined.
    local tab_hit
    for _,t in ipairs(L.tabs)do
        local open=panel.tab==t.tab.id
        local hovered=not panel.menu and clicked_in(mouse,t.box)
        if hovered and not open then tab_hit=t;d:rect(t.box.x,t.box.y,t.box.w,t.box.h,C.hover,2)end
        if open then d:rect(t.box.x,t.box.y+t.box.h-2*k,t.box.w,2*k,C.gold,4)end
        text(d,i18n.upper(T(t.tab.label)),t.box.x+t.box.w/2,t.box.y+t.box.h/2,S.heading*k,
            open and C.gold or(hovered and C.text or C.faint),'title','center')
    end
    local close_hover=clicked_in(mouse,L.close)
    d:rect(L.close.x,L.close.y,L.close.w,L.close.h,close_hover and C.error_soft or C.panel,3)
    d:rect(L.close.x,L.close.y,L.close.w,math.max(1,k),close_hover and C.error or C.line_strong,4)
    d:rect(L.close.x,L.close.y+L.close.h-math.max(1,k),L.close.w,math.max(1,k),close_hover and C.error or C.line_strong,4)
    text(d,'x',L.close.x+L.close.w/2,L.close.y+L.close.h/2,20*k,close_hover and C.error or C.dim,'title','center')
    -- The footer (before the tab's own items, so a tab's changing rows never move it).
    local fy=y+L.h-M.FOOTER*k
    d:rect(x,fy,w,M.FOOTER*k,C.footer,1)
    d:rect(x,fy,w,math.max(1,k),C.line_strong,2)
    local footer_text=panel.tab=='performance'
        and T('Measured Lua callbacks only; native hooks and asset costs are not individually measurable | F10 or Esc closes')
        or T('F10 or Esc closes  |  click a row to turn it on or off')
    local footer=d:wrap(footer_text,w-2*M.PAD*k,{size=S.small*k,lines=1})
    text(d,footer[1]or'',x+M.PAD*k,fy+M.FOOTER*k/2,S.small*k,C.faint,'body')
    local escape=input and input.pressed('ESCAPE')
    if panel.tab=='performance'then
        performance().draw({d=d,text=text,C=C,S=S,sound=M.sound},L.content,k,mouse,press)
        if press and tab_hit then M.select_tab(tab_hit.tab.id)
        elseif(press and close_hover)or escape then M.close()end
        return L
    end
    -- MESSAGES: one toggle row per setting.
    local function section(label,sy)
        text(d,label,x+M.PAD*k,sy,S.tiny*k,C.gold_dim,'title')
        local lw=d:text_width(label,S.tiny*k,'title')
        d:rect(x+M.PAD*k+lw+10*k,sy,w-2*M.PAD*k-lw-10*k,math.max(1,k),C.line,2)
    end
    -- LANGUAGE: the current choice; a click opens the list
    section(i18n.upper(T('LANGUAGE')),L.language_y)
    local current=M.value('language')
    local lbox=L.language
    local menu=panel.menu
    local language_hover=not menu and clicked_in(mouse,lbox)
    if language_hover then d:rect(lbox.x-6*k,lbox.y,lbox.w+12*k,lbox.h,C.hover,2)end
    local ly=lbox.y+lbox.h/2
    text(d,T('Language'),lbox.x,ly-8*k,S.body*k,C.text,'body')
    local lines=d:wrap(T('The language of everything HD2Runtime shows on screen.'),lbox.w*0.55,{size=S.small*k,lines=1})
    text(d,lines[1]or'',lbox.x,ly+10*k,S.small*k,C.dim,'body')
    local bw=lbox.w*0.42
    d:rect(lbox.x+lbox.w-bw,ly-14*k,bw,28*k,C.header,3)
    d:rect(lbox.x+lbox.w-bw,ly+14*k-math.max(1,k),bw,math.max(1,k),menu and C.gold or C.line_strong,4)
    local shown=d:wrap(M.language_text(current),bw-34*k,{size=S.small*k,lines=1})
    text(d,shown[1]or'',lbox.x+lbox.w-bw+10*k,ly,S.small*k,C.text,'body')
    text(d,menu and'^'or'v',lbox.x+lbox.w-12*k,ly,S.small*k,C.gold,'title','right')
    -- INTERFACE: the size, - and + (the HD2R Editor's sizes); the size that fits when the chosen one does not.
    section(i18n.upper(T('INTERFACE')),L.interface_y)
    local sbox=L.size
    local sy=sbox.y+sbox.h/2
    text(d,T('Interface size'),sbox.x,sy-8*k,S.body*k,C.text,'body')
    local size_lines=d:wrap(T('The size of this panel and its text.'),sbox.w*0.5,{size=S.small*k,lines=1})
    text(d,size_lines[1]or'',sbox.x,sy+10*k,S.small*k,C.dim,'body')
    local size_hit
    for _,b in ipairs({{box=L.size_down,sign='-',step=-1,on=L.chosen>M.UI_SCALES[1]},
            {box=L.size_up,sign='+',step=1,on=L.chosen<M.UI_SCALES[#M.UI_SCALES]}})do
        local hovered=not menu and b.on and clicked_in(mouse,b.box)
        if hovered then size_hit=b end
        d:rect(b.box.x,b.box.y,b.box.w,b.box.h,hovered and C.hover or C.header,3)
        d:rect(b.box.x,b.box.y+b.box.h-math.max(1,k),b.box.w,math.max(1,k),b.on and C.line_strong or C.line,4)
        text(d,b.sign,b.box.x+b.box.w/2,b.box.y+b.box.h/2,S.body*k,b.on and C.gold or C.faint,'title','center')
    end
    text(d,('%d%%'):format(math.floor(L.chosen*100+0.5)),(L.size_down.x+L.size_down.w+L.size_up.x)/2,sy,S.body*k,C.text,
        'title','center')
    if math.floor(L.fits*100+0.5)<math.floor(L.chosen*100+0.5)then
        text(d,T('(%d%% fits this screen)',math.floor(L.fits*100+0.5)),L.size_down.x-10*k,sy,S.tiny*k,C.faint,'body',
            'right')
    end
    section(i18n.upper(T('MESSAGES ON SCREEN')),L.messages_y)
    local hit
    for _,row in ipairs(L.rows)do
        local on=M.enabled(row.item.key)
        local hovered=not menu and clicked_in(mouse,row.box)
        if hovered then hit=row;d:rect(row.box.x-6*k,row.box.y,row.box.w+12*k,row.box.h,C.hover,2)end
        local tx,ty=row.box.x,row.box.y+row.box.h/2
        d:rect(tx,ty-9*k,34*k,18*k,on and C.gold or C.line_strong,3)
        d:rect(on and tx+18*k or tx+2*k,ty-7*k,14*k,14*k,on and C.inverse or C.dim,4)
        text(d,T(row.item.label),tx+48*k,ty-8*k,S.body*k,C.text,'body')
        local desc=d:wrap(T(row.item.description),row.box.w-48*k-60*k,{size=S.small*k,lines=1})
        text(d,desc[1]or'',tx+48*k,ty+10*k,S.small*k,C.dim,'body')
        text(d,i18n.upper(on and T('ON')or T('OFF')),row.box.x+row.box.w,ty,S.tiny*k,on and C.gold or C.faint,'title',
            'right')
    end
    section(i18n.upper(T('ABOUT')),L.about_y)
    for n,line in ipairs(about_lines())do
        text(d,line,x+M.PAD*k,L.about_y+(14+(n-1)*22)*k,S.small*k,n==3 and C.faint or C.dim,'body')
    end
    -- The open language list, over everything: a click picks a language; a click elsewhere or Esc closes the list.
    local picked
    if menu then
        local top,last=L.options[1].box,L.options[#L.options].box
        local lh=last.y+last.h-top.y
        d:rect(top.x-2*k,top.y-2*k,top.w+4*k,lh+4*k,C.shadow,20)
        d:rect(top.x,top.y,top.w,lh,C.header,21)
        d:rect(top.x,top.y,3*k,lh,C.rail,23)
        for _,o in ipairs(L.options)do
            local hovered=clicked_in(mouse,o.box)
            local chosen=o.option.code==current
            if hovered then picked=o;d:rect(o.box.x,o.box.y,o.box.w,o.box.h,C.hover,22)end
            local label=o.option.code==i18n.AUTO and M.language_text(i18n.AUTO)or o.option.name
            text(d,label,o.box.x+16*k,o.box.y+o.box.h/2,S.small*k,chosen and C.gold or C.text,'body',nil,24)
            if chosen then text(d,'*',o.box.x+o.box.w-12*k,o.box.y+o.box.h/2,S.small*k,C.gold,'title','right',24)end
        end
    end
    -- Input: the list first; a click on a row toggles it; a tab or a size button; the x or Esc closes.
    if menu then
        if press then
            if picked then M.set_value('language',picked.option.code);M.sound('click')else M.sound('back')end
            panel.menu=nil
        elseif escape then panel.menu=nil;M.sound('back')end
        return L
    end
    if press and language_hover then log('language list requested');panel.menu=true;M.sound('click');return L end
    if press and hit then log('toggle requested: '..hit.item.key);M.sound('click');M.set(hit.item.key,not M.enabled(hit.item.key))end
    if press and size_hit then M.step_ui_scale(size_hit.step);M.sound('click')end
    if press and tab_hit then M.select_tab(tab_hit.tab.id)end
    if(press and close_hover)or escape then M.close()end
    return L
end

-- Shows a tab ('settings' or 'performance'). The Performance tab's measurements run only while it is shown.
function M.select_tab(id)
    assert(id=='settings'or id=='performance','unknown HD2Runtime settings tab: '..tostring(id))
    if id~=panel.tab then
        log('tab requested: '..panel.tab..' -> '..id)
        if M.visible()then M.sound('click')end;panel.tab=id;panel.menu=nil
        if id~='performance'then require('hd2runtime/runtime/perf_watch').record(false);performance().reset()end
    end
    return id
end
function M.tab()return panel.tab end
function M.open(tab)
    if tab then M.select_tab(tab)end
    log('panel opening: '..panel.tab)
    panel.draw_view=nil
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
    pcall(M.hooks.block,true)
    if not M.visible()then M.sound('open')end
    panel.was_left=true   -- a held button is not a click
    panel.overlay:show(true)
    log('panel opened')
end
function M.close()
    if M.visible()then log('panel closing: '..panel.tab)end
    if M.visible()then M.sound('back')end
    pcall(M.hooks.block,false)
    panel.menu=nil
    require('hd2runtime/runtime/perf_watch').record(false)
    performance().reset()
    if panel.overlay then panel.overlay:hide()end
end
function M.toggle()
    if panel.overlay and panel.overlay:status().visible then M.close()else M.open()end
end
function M.visible()return panel.overlay~=nil and panel.overlay:status().visible==true end
-- Binds F10 (once). The Runtime binds at load, before any mod, so F10 is its own.
function M.start()
    if panel.binding then return panel.binding end
    -- The saved application mode (off unless turned on), before any mod applies anything.
    local mode=require('hd2runtime/runtime/application_mode')
    mode.configure(M.enabled('optimized_application'))
    log('Faster application (0.40.0) '..(mode.enabled()and'ON'or'OFF (the 0.31 behaviour)'))
    local input=require('hd2runtime/runtime/input')
    -- (also on the game's own keybind page with Mod Bindings Menu installed: runtime/mod_bindings_bridge.lua)
    panel.binding=input.bind(M.BINDING,{key=M.KEY,on_press=function()M.toggle()end,
        native={label='Open / close HD2Runtime settings',category='HD2Runtime'}},M.OWNER)
    return panel.binding
end
function M.reset_for_tests()
    pcall(M.hooks.block,false)
    sound_last=-math.huge;sound_failed={}
    if panel.overlay then pcall(panel.overlay.close,panel.overlay)end
    panel={overlay=nil,binding=nil,was_left=false,tab='settings'}
    require('hd2runtime/runtime/perf_watch').record(false)
    performance().reset()
    memory,listeners={},{}
    i18n.reset_for_tests()
end
return M
