-- A small build label in the bottom-left corner while the player is aboard the ship (docs/getting-started.md, "Version
-- label"):
--
--   HD2Runtime 0.30.0
--   Game F5FEE03DCFDB
--
-- Diagnostic text, not a watermark: a small dim font at the lowest layer of a Ui World screen GUI, so every native
-- interface drawn there covers it. Shown only in the game's Ship state; hidden while a mission loads (PrepareMission),
-- in a mission and while the ship loads again (PrepareShip); shown again aboard the ship.
--
-- The state is the events engine's game_state source (runtime/event_sources.lua: the state it polls every update, kept
-- in events.state.game_state), required while the label exists, as every hd2.mod() context requires it; nothing here
-- reads game memory. The game is the build the Runtime proved (core/fingerprint, the pinned executable's first 12 hex
-- digits): only a proven game has a state, so an unsupported build shows no label.
-- The GUI is created when the label appears and destroyed when it hides (one screen GUI, two texts; nothing is redrawn
-- while it shows); the state is checked every M.CHECK_EVERY s. The label is anchored in _G, so a reloaded Runtime
-- closes the previous one first. A GUI failure turns the label off for the session (logged once).
local M={}
M.CHECK_EVERY=0.25
M.LAYER=2
M.SIZE=18           -- font size at 1920 x 1080; every size scales with the window (M.scale)
M.MARGIN=14         -- the safe-area margin at 1920 x 1080, from the left and bottom edges
M.COLOUR={120,190,190,186}   -- a, r, g, b: dim grey
local KEY='HD2RuntimeVersionLabelV1'

local function log(text)
    local ok,l=pcall(require,'hd2runtime/runtime/log')
    if ok then pcall(l.emit,'[HD2Runtime] version label '..text)end
end

-- The hooks the label reads the game through (tests replace them).
M.hooks={}
function M.hooks.state()
    local events=require('hd2runtime/runtime/events')
    return events.state.game_state
end
function M.hooks.world()return require('hd2runtime/runtime/event_world').open()end
function M.hooks.font()
    local D=require('hd2runtime/domains/stratagem_selector')
    local images=require('hd2runtime/runtime/image_resources')
    local world=M.hooks.world()
    if not world then return nil end
    for _,kind in ipairs({D.font.type,D.font.materialType})do
        local ok,loaded=pcall(images.loaded,world.runtime,kind,D.font.name)
        if not(ok and loaded)then return nil end
    end
    return D.font.name
end
function M.hooks.open_screen(world)return require('hd2runtime/runtime/stratagem_slot_overlay').open_gui(world)end

-- The label's two lines.
function M.lines()
    local ok,metadata=pcall(require,'hd2runtime/domains/metadata')
    local okp,profile=pcall(require,'hd2runtime/schemas/current')
    return 'HD2Runtime '..tostring(ok and metadata.version or'?'),
        'Game '..tostring(okp and type(profile.exe_sha)=='string'and profile.exe_sha:sub(1,12)or'?')
end

-- The window scale: the GUI resolution against 1920 x 1080, by the tighter of width and height, so the label is the
-- same share of the screen at every resolution (twice the pixels at 4K, two thirds at 720p) and a narrow or tall
-- window never makes it wider than the same share of its width.
function M.scale(width,height)return math.min(width/1920,height/1080)end

local label=rawget(_G,KEY)
local function close()
    if label and label.screen then pcall(label.screen.close)end
    if label then label.screen,label.shown_text=nil,nil end
end
-- Opens the GUI and draws both lines. true, or nil and why (not drawable yet: retried at the next check).
local function show()
    local world=M.hooks.world()
    if not world then return nil,'no game world'end
    local font=M.hooks.font()
    if not font then return nil,'the engine font is not loaded'end
    local screen,why=M.hooks.open_screen(world)
    if not screen then return nil,why end
    label.screen=screen
    local u=M.scale(screen.width,screen.height)
    local size,x,y=M.SIZE*u,M.MARGIN*u,M.MARGIN*u
    local first,second=M.lines()
    local ok=screen.text(second,font,size,font,x,y,M.LAYER,M.COLOUR,{optional=true})~=nil
        and screen.text(first,font,size,font,x,y+size*1.35,M.LAYER,M.COLOUR,{optional=true})~=nil
    if not ok then close();return nil,'a text was refused'end
    label.shown_text=first..' / '..second
    return true
end

local function tick(dt)
    label.acc=label.acc+(dt or 0)
    if label.acc<M.CHECK_EVERY then return end
    label.acc=0
    local state=M.hooks.state()
    local aboard=state~=nil and state.name=='Ship'and not state.mission
    if aboard and not label.screen then
        local ok,shown,why=pcall(show)
        if not ok then
            close();label.disabled=true;label.watch.status='complete'
            log('is off for this session: '..tostring(shown))
        elseif not shown then
            label.why=why   -- not drawable yet (no Ui World or font): tried again at the next check, quietly
        end
    elseif not aboard and label.screen then
        close()
    end
end

-- Starts the label (once per session; again after a reload, which closes the previous one).
function M.start()
    if label and label.watch and label.watch.status=='waiting'and label.module==M then return end
    if label then M.stop()end
    label={module=M,acc=M.CHECK_EVERY,screen=nil,watch=nil,disabled=false}
    rawset(_G,KEY,label)
    local events=require('hd2runtime/runtime/events')
    require('hd2runtime/runtime/event_sources')   -- registers the game_state source (already loaded with hd2.events)
    events.require_source('game_state',1)
    label.required=true
    local watch={status='waiting',perf_label='the version label'}
    function watch.cancel()watch.status='cancelled'end
    function watch.tick(dt)if watch.status=='waiting'then tick(dt)end end
    label.watch=watch
    require('hd2runtime/runtime/scheduler').attach(watch)
end
-- Removes the label and its watch and releases the state source.
function M.stop()
    if not label then return end
    close()
    if label.watch then label.watch.status='cancelled'end
    if label.required then
        label.required=false
        pcall(function()require('hd2runtime/runtime/events').require_source('game_state',-1)end)
    end
end
-- What the label shows now: the text, or nil when hidden.
function M.status()return label and label.shown_text or nil end
function M.reset_for_tests()M.stop();label=nil;rawset(_G,KEY,nil)end
return M
