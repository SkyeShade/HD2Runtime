-- The Runtime's initial setup progress (docs/getting-started.md, "Startup progress"). A small panel in the top-right
-- corner while the Runtime's initial work is actually pending, computed from that work, never from a timer:
--
--   HD2Runtime 0.30
--   Initializing...
--   [########----] 63%
--   Applying mod plans (5/8)
--
-- Stages and weights (the percentage is the weighted sum of each stage's done fraction):
--   catalogue  10  the Runtime's catalogue and domain data, loaded with the module (done by the first update; its
--                  time is measured from the module load to that update);
--   game       10  the game world and its state readable (the build's event pins proven): aboard the ship or in a
--                  mission;
--   assets     25  every asset package gate the mods and the Runtime opened (core/assets.lua gate): resident or failed;
--   plans      45  every registered mod operation (hd2.ensure, hd2.plan, hd2.patch, hd2.transaction) settled: its first
--                  verified cycle, or rejected, unavailable, disabled, cancelled;
--   custom     10  the custom stratagems' carriers allocated aboard the ship (or none selected).
-- A stage with no work is complete. The panel shows only once the game world exists and work is still pending
-- M.SHOW_AFTER s later (a quick start never shows it), and closes at READY: every stage complete for M.SETTLE s with no
-- new work. Work registered after READY (a mod registering late) shows it again; mission transitions alone do not.
-- A stage that makes no progress for M.STALL s (an operation waiting on something that is not Runtime work, e.g. a
-- weapon not yet built) ends the display: READY is logged with what is still pending.
-- Logging: an initializing line when the world appears, one line per stage completion and one READY line with every
-- stage's time; nothing per frame.
-- The display can never block the Runtime: every engine call is protected, and a GUI failure disables the display for
-- the session (logged once). Development: hd2.diagnostics / M.state() report the same numbers.
local M={}
M.SHOW_AFTER=0.5
M.SETTLE=1.0
M.STALL=45
M.REDRAW=0.25
M.STAGES={
    {key='catalogue',label='Loading catalogue data',weight=10},
    {key='game',label='Waiting for the game',weight=10},
    {key='assets',label='Loading asset packages',weight=25},
    {key='plans',label='Applying mod plans',weight=45},
    {key='custom',label='Preparing custom stratagems',weight=10},
}
local LAYER=925
local COLOURS={panel={210,10,12,14},edge={255,64,68,72},title={255,232,232,226},text={255,200,200,196},
    bar={255,40,43,47},fill={255,206,206,198},label={255,170,170,166}}

-- Times: the catalogue's load in CPU seconds (os.clock, from this module's load to the first update); every later
-- time in seconds of updates (the scheduler's dt), from the first update.
local function cpu()local ok,v=pcall(os.clock);return ok and v or 0 end
local function log(text)
    local ok,l=pcall(require,'hd2runtime/runtime/log')
    if ok then pcall(l.emit,'[HD2Runtime] startup: '..text)end
end

-- Tracked work: kind -> list of {done = fn() -> bool, label}.
local state
local function fresh()
    return {loaded_cpu=cpu(),catalogue_seconds=nil,elapsed=0,first_tick=nil,started=false,ready=false,ready_at=nil,
        shown=false,disabled=false,
        items={assets={},plans={}},stage_done={},stage_started={},stage_logged={},last_change=nil,last_key=nil,screen=nil,
        drawn_key=nil,drawn_at=-1,settle_since=nil,watch=nil,late=false,pending_text=nil}
end
state=fresh()

-- The hooks the module reads the game through (tests replace them): the game world and state, the custom
-- stratagems' readiness, and the screen opener.
M.hooks={}
function M.hooks.game()
    local wm=require('hd2runtime/runtime/event_world')
    local world=wm.open()
    if not world then return nil end
    local g=wm.game_state(world)
    if not(g and(g.mission or g.name=='Ship'or g.name=='Mission'))then return nil end
    return world
end
function M.hooks.custom()
    local custom=package.loaded['hd2runtime/runtime/custom_stratagems']
    if type(custom)~='table'or not custom.init_state then return true,0,0 end
    return custom.init_state()
end
function M.hooks.open_screen(world)
    return require('hd2runtime/runtime/stratagem_slot_overlay').open_gui(world)
end
function M.hooks.font()
    local D=require('hd2runtime/domains/stratagem_selector')
    local images=require('hd2runtime/runtime/image_resources')
    local world=require('hd2runtime/runtime/event_world').open()
    if not world then return nil end
    for _,kind in ipairs({D.font.type,D.font.materialType})do
        local ok,loaded=pcall(images.loaded,world.runtime,kind,D.font.name)
        if not(ok and loaded)then return nil end
    end
    return D.font.name
end
local function version_text()
    local ok,metadata=pcall(require,'hd2runtime/domains/metadata')
    local v=ok and tostring(metadata.version)or'?'
    return 'HD2Runtime '..(v:match('^(%d+%.%d+)')or v)
end

-- Custom stratagems registered: their carriers are work aboard the ship (starts the watch, nothing tracked here).
function M.custom_registered()M.start()end
-- Registers one piece of initial work. kind: 'plans' (a registered operation's handle; settled() decides) or
-- 'assets' (a core/assets gate). Work registered after READY shows the panel again. The caller starts the watch
-- (M.start) BEFORE attaching the work's own watch, so the progress watch ticks after it in each frame.
function M.track(kind,item,settled)
    if kind~='plans'and kind~='assets'then return end
    local done
    if kind=='assets'then done=function()return item.state~='waiting'end
    else done=function()return settled(item)end end
    local list=state.items[kind]
    list[#list+1]={done=done}
    if state.ready then
        state.ready=false;state.late=true;state.settle_since=nil;state.stage_done[kind]=nil;state.stage_logged[kind]=nil
    end
    if kind=='assets'then M.start()end
end

-- Each stage's {done, total, fraction} now.
local function counts(game_world)
    local out={}
    out.catalogue={done=state.first_tick and 1 or 0,total=1}
    out.game={done=game_world and 1 or 0,total=1}
    for _,kind in ipairs({'assets','plans'})do
        local d,t=0,0
        for _,item in ipairs(state.items[kind])do
            t=t+1
            local ok,yes=pcall(item.done)
            if ok and yes then d=d+1 end
        end
        out[kind]={done=d,total=t}
    end
    local ok,ready,d,t=pcall(M.hooks.custom)
    if not ok then ready,d,t=true,0,0 end
    out.custom={done=ready and(t or 0)or(d or 0),total=t or 0,ready=ready}
    for _,c in pairs(out)do
        if c.ready~=nil then c.fraction=c.ready and 1 or(c.total>0 and c.done/c.total or 0)
        else c.fraction=c.total==0 and 1 or c.done/c.total end
    end
    return out
end
-- The weighted percentage and the first incomplete stage: percent (0-100), stage (or nil when every stage is done),
-- label text.
function M.progress(c)
    local sum,total,first=0,0,nil
    for _,s in ipairs(M.STAGES)do
        local x=c[s.key]
        sum=sum+s.weight*x.fraction
        total=total+s.weight
        if x.fraction<1 and not first then first=s end
    end
    local percent=math.floor(100*sum/total+0.5)
    if first and percent>=100 then percent=99 end
    local label=first and first.label or'Ready'
    if first and c[first.key].total>1 then label=('%s (%d/%d)'):format(label,c[first.key].done,c[first.key].total)end
    return percent,first,label
end

local function close_screen()
    if state.screen then pcall(state.screen.close)end
    state.screen,state.drawn_key=nil,nil
end
local function fail(why)
    close_screen()
    if not state.disabled then
        state.disabled=true
        log('the progress display is unavailable ('..tostring(why)..'); the Runtime continues')
    end
end
-- Draws the panel (a fresh GUI: retained GUIs cannot change text). Returns true, or nil and why.
local function draw(world,percent,label)
    local font=M.hooks.font()
    if not font then return nil,'the engine font is not loaded'end
    close_screen()
    local screen,why=M.hooks.open_screen(world)
    if not screen then return nil,why end
    state.screen=screen
    local W,H=screen.width,screen.height
    local u=H/1080
    local w,h,m=250*u,72*u,24*u
    local x,y=W-w-m,H-h-m
    local pad=10*u
    local bar_w,bar_h=w-2*pad-42*u,7*u
    local function need(id,what)if id==nil then error(what,0)end return id end
    local ok,err=pcall(function()
        need(screen.rect(x,y,LAYER,w,h,COLOURS.panel),'the panel')
        need(screen.rect(x,y+h-2*u,LAYER+1,w,2*u,COLOURS.edge),'the edge')
        need(screen.text(version_text(),font,12*u,font,x+pad,y+h-17*u,LAYER+2,COLOURS.title),'the title')
        need(screen.text('Initializing...',font,10*u,font,x+pad,y+h-31*u,LAYER+2,COLOURS.text),'the status')
        local by=y+22*u
        need(screen.rect(x+pad,by,LAYER+1,bar_w,bar_h,COLOURS.bar),'the bar')
        if percent>0 then
            need(screen.rect(x+pad,by,LAYER+2,math.max(1,bar_w*percent/100),bar_h,COLOURS.fill),'the bar fill')
        end
        need(screen.text(percent..'%',font,10*u,font,x+pad+bar_w+6*u,by,LAYER+2,COLOURS.text),'the percentage')
        need(screen.text(label,font,9*u,font,x+pad,y+8*u,LAYER+2,COLOURS.label),'the stage')
    end)
    if not ok then return nil,err end
    return true
end

local function stage_line(c)
    local parts={}
    for _,s in ipairs(M.STAGES)do
        local x=c[s.key]
        local text
        if s.key=='catalogue'then text=('%.2f s CPU'):format(state.catalogue_seconds or 0)
        elseif state.stage_done[s.key]then
            text=('%.2f s'):format(state.stage_done[s.key]-(state.stage_started[s.key]or 0))
        else text='pending'end
        parts[#parts+1]=s.key..' '..text..(x.total>1 and(' ('..x.done..'/'..x.total..')')or'')
    end
    return table.concat(parts,', ')
end

local function seconds(a,b)return(b-a)end
local function tick(dt)
    state.elapsed=state.elapsed+(type(dt)=='number'and dt>=0 and dt<10 and dt or 0)
    local t=state.elapsed
    if not state.first_tick then
        state.first_tick=t
        state.catalogue_seconds=cpu()-state.loaded_cpu
        state.stage_done.catalogue=t
        state.stage_started.catalogue=t
    end
    local ok_game,world=pcall(M.hooks.game)
    world=ok_game and world or nil
    local c=counts(world)
    local percent,first,label=M.progress(c)
    -- Stage completion times, once each.
    for _,s in ipairs(M.STAGES)do
        local x=c[s.key]
        if x.fraction<1 then
            state.stage_done[s.key]=nil
            state.stage_started[s.key]=state.stage_started[s.key]or t
        elseif not state.stage_done[s.key]then
            state.stage_done[s.key]=t
            state.stage_started[s.key]=state.stage_started[s.key]or t
            -- Once per stage (a stage that drops back, e.g. the game while a mission loads, is not logged again).
            if s.key~='catalogue'and(x.total>0 or s.key=='game')and state.started and not state.stage_logged[s.key]then
                state.stage_logged[s.key]=true
                log(('stage %s done in %.2f s%s'):format(s.key,seconds(state.stage_started[s.key],t),
                    x.total>1 and(' ('..x.done..' of '..x.total..')')or''))
            end
        end
    end
    local key=percent..'|'..label
    if key~=state.last_key then state.last_key=key;state.last_change=t end
    if not state.started and world then
        state.started=true
        state.world_at=t
        log(('initializing: %d mod operation%s, %d asset gate%s; the Runtime and the mods loaded in %.2f s CPU'):format(
            #state.items.plans,#state.items.plans==1 and''or's',#state.items.assets,#state.items.assets==1 and''or's',
            state.catalogue_seconds or 0))
    end
    -- READY: everything done for M.SETTLE s; or no progress for M.STALL s (what is pending is not Runtime work).
    -- The Runtime's own work: every stage but the game's (waiting for the game is not work; with no world nothing is
    -- shown, and settled work needs no world to be READY).
    local work_done=true
    for _,s in ipairs(M.STAGES)do if s.key~='game'and c[s.key].fraction<1 then work_done=false end end
    if work_done then state.settle_since=state.settle_since or t else state.settle_since=nil end
    local stalled=state.started and state.last_change and(t-state.last_change)>M.STALL
    if(work_done and(not state.shown or(t-state.settle_since)>=M.SETTLE))or stalled then
        state.ready=true
        state.ready_at=t
        close_screen()
        -- Logged once a world appeared, or for work that settled before it (a start with no work stays silent).
        if state.started or#state.items.plans+#state.items.assets+c.custom.total>0 then
            log(('READY in %.2f s of updates (%s)%s%s%s'):format(t,stage_line(c),
                stalled and(': still pending, not Runtime work: '..label)or'',state.late and' (late work)'or'',
                state.started and''or' (before the game world)'))
        end
        state.late=false
        return 'complete'
    end
    -- The panel: aboard the ship or in a mission, once work is still pending M.SHOW_AFTER s after the world appeared.
    if world and not state.disabled and state.world_at and(t-state.world_at)>=M.SHOW_AFTER then
        if key~=state.drawn_key and(t-state.drawn_at)>=M.REDRAW then
            local ok,drawn,why=pcall(draw,world,percent,label)
            if not ok then fail(drawn)
            elseif not drawn then
                -- Not drawable now (no font yet, no Ui World): try again later, quietly.
                close_screen()
            else
                state.drawn_key,state.drawn_at=key,t
                if not state.shown then state.shown=true end
            end
        end
    end
    return 'waiting'
end
M.tick_for_tests=tick

-- Starts (or restarts, for late work) the watch. Safe to call any number of times.
function M.start()
    if state.watch and state.watch.status=='waiting'then return end
    local watch={status='waiting'}
    function watch.cancel()watch.status='cancelled';close_screen()end
    function watch.tick(dt)
        if watch.status~='waiting'then return end
        local okm,metrics=pcall(require,'hd2runtime/runtime/metrics')
        local started=okm and metrics.now()
        local ok,result=pcall(tick,dt)
        if okm then metrics.elapsed('init_progress.tick',started)end
        if not ok then
            fail(result)
            watch.status='complete'
            return
        end
        if result=='complete'then watch.status='complete'end
    end
    state.watch=watch
    local ok,scheduler=pcall(require,'hd2runtime/runtime/scheduler')
    if ok then scheduler.attach(watch)end
end

-- Development / tests: the numbers the display shows.
function M.state()
    local ok_game,world=pcall(M.hooks.game)
    local c=counts(ok_game and world or nil)
    local percent,first,label=M.progress(c)
    return {percent=percent,stage=first and first.key,label=label,ready=state.ready,shown=state.shown,
        disabled=state.disabled,counts=c,visible=state.screen~=nil}
end
function M.reset_for_tests()
    close_screen()
    if state.watch then state.watch.status='cancelled'end
    state=fresh()
end
return M
