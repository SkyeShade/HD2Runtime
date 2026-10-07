-- Runtime public-matchmaking safety (research/docs/matchmaking-safety-F5FEE03DCFDB.md;
-- research/matchmaking-safety-F5FEE03DCFDB.json; domains/matchmaking_safety.lua). The conservative rule: while
-- HD2Runtime is active, Public matchmaking is off. A Runtime user must not end up with strangers by accident:
--
--   * the lobby privacy SETTING Public (Open) becomes Friends Only through the game's own privacy setter
--     set_setting(settings, 0, &1) (game.dll 0x11ED0B0, the call the options menu makes): settings +0x174 and the
--     lobby's advertised PrivacyMode key, nothing else. A host whose lobby advertises Open while no SOS Beacon is active
--     (the options menu's working copy set it) gets its own non-public setting advertised again the same way (Friends
--     Only when the setting itself is Public);
--   * QUICKPLAY (the only public-matchmaking search: it finds Open lobbies only) is cancelled through the game's own
--     stop set_quickplay(matchmaker, 0, -1, 0x7FFFFFFF, 0, 0, 0, 0) (game.dll 0x133E6E0, what the galactic war map's
--     cancel and its closing call);
--   * an SOS BEACON makes the host's lobby Open whatever the setting (the game's own rule); the Runtime cannot block it
--     without changing the game's behaviour, so it WARNS (log and screen) for as long as it is active.
-- Friends Only, Invite Only and Friends and Clan are never touched; nor is anything while the game is offline (no Game
-- object or network context) or in its singleplayer mode (the host refuses every join there).
--
-- Every change is logged and shown on screen (a Runtime-owned panel, top right, drawn as runtime/init_progress.lua
-- draws). Nothing is written directly: the two native calls are the game's own functions, each only
--   * inside the Runtime's own update (the game thread), on a live game process;
--   * after every pin re-proved (the setter's case 0 and its jump-table entry, the descriptor lookup, the stop and its
--     callers, every layout read here);
--   * for the setter: the Game object, the settings descriptor of id 0 (the setter reads it unchecked), the network
--     context, and either no engine lobby or a joined one (wrapper flag, PlayfabLobby, state 3, handle);
--   * for the stop: the matchmaker, its Quickplay flag set, the game aboard the ship.
-- Each call is verified afterwards (the setting reads the value it was called with and the host's lobby no longer
-- advertises Open / the Quickplay flag reads 0); MAX_FAILURES unverified calls in a row end that enforcement for the
-- session (warnings only).
-- FAIL-SAFE: a pin that does not prove, an unreadable layout or no live process means NO call and NO write; the module
-- then warns loudly (log and screen) that Public matchmaking is NOT blocked and what to do instead.
local world_module=require('hd2runtime/runtime/event_world')
local scheduler=require('hd2runtime/runtime/scheduler')
local log_module=require('hd2runtime/runtime/log')
local metrics=require('hd2runtime/runtime/metrics')
local b=require('hd2runtime/core/bytes')
local D=require('hd2runtime/domains/matchmaking_safety')
local M={}

M.CHECK=0.25               -- seconds between two privacy checks (Quickplay is checked every update)
M.MIN_CALL_INTERVAL={privacy=1.0,quickplay=0.25}   -- seconds between two calls of the same native function
M.UNREADABLE_GRACE=5       -- seconds an unreadable layout may last (a transition) before it is reported
M.MAX_FAILURES=3           -- unverified calls in a row before that enforcement stops (warnings only)
M.NOTICE_SECONDS=12        -- how long a notice stays on screen
M.NOTICE_WAIT=120          -- how long a notice waits for a drawable screen before it is dropped (the log keeps it)
-- The notice's size against the original 430 x 80 panel (r6 tried 3: too large; the user's choice for 0.30 is 2). Every
-- dimension is in units of the screen height / 1080 (as the startup progress panel), so the notice covers the same share
-- of the screen's height at any resolution and UI scale; it is never wider than 90 % of the screen (narrow ratios).
M.NOTICE_SCALE=2
M.NOTICE_REPEAT=20         -- seconds before the same notice text is shown again
M.READVERTISE=10           -- seconds between two re-sets while only the lobby's advertisement still says Public
M.REPEAT_LOG=30            -- seconds between two lines counting those re-sets
M.ENFORCED=D.privacy.friendsOnly
-- The names the player sees in the options menu, by the game's privacy value.
M.NAMES={[0]='Public',[1]='Friends Only',[2]='Invite Only',[3]='Friends and Clan'}
M.TEXT={
    title='HD2Runtime multiplayer safety',
    rule='Public matchmaking disabled while Runtime is active.',
    advice='Use Friends Only / Invite Only with compatible Runtime users.',
    privacy='Lobby privacy changed: Public -> %s.',
    quickplay='Quickplay cancelled: it joins public games with strangers.',
    sos='SOS Beacon active: this lobby is PUBLIC and strangers can join.',
    public_setting='Lobby privacy is Public: set Friends Only / Invite Only.',
    public_quickplay='Quickplay joins public games: cancel it.',
    unavailable='Safety UNAVAILABLE: Public matchmaking is NOT blocked.',
    unavailable_advice='Set Friends Only / Invite Only and do not use Quickplay.',
}

local state
local adapter_override,native
local function fresh()
    return {clock=0,next_check=0,proven=nil,announced=false,said={},notices={},enforced=0,readvertised=0,
        readvertise_logged=-math.huge,
        failures={privacy=0,quickplay=0},stopped={},last_call={privacy=-math.huge,quickplay=-math.huge},
        sos=false,watch=nil,notice=nil,screen=nil,gui_disabled=false,events={}}
end
state=fresh()

local function log(text)log_module.emit('[HD2Runtime] '..text)end
-- One line per distinct text under a key (a state that persists is not logged every check).
local function say(key,text)
    if state.said[key]==text then return end
    state.said[key]=text
    log(text)
end
local function event(kind,detail)
    if #state.events>=64 then table.remove(state.events,1)end
    state.events[#state.events+1]={kind=kind,detail=detail,clock=state.clock}
end

---------------------------------------------------------------------------------------------- native calls --
-- The two game functions as typed calls (windows_write.lua style; tests replace them with M.set_adapter). Only the
-- privacy id 0 with a non-public value, and only the stop (on = 0) with the arguments the game's own callers pass.
function M.native_adapter()
    local win=require('hd2runtime/runtime/windows_ffi')
    local ffi=win.ffi
    local A={}
    local function address(v)return type(v)=='number'and v>0 and v<=9007199254740991 and v%1==0 end
    -- set_setting(settings, 0, &value): settings +0x174 := value and the lobby's PrivacyMode key (game.dll 0x11ED0B0).
    -- Never Open: Friends Only, or the player's own non-public setting (Invite Only, Friends and Clan) re-advertised.
    function A.set_privacy(entry,settings,value)
        assert(address(entry)and address(settings)and(value==D.privacy.friendsOnly or value==D.privacy.inviteOnly
            or value==D.privacy.friendsAndClan),'unsupported privacy call')
        local v=ffi.new('uint32_t[1]',value)
        local set=ffi.cast('void (*)(void *, uint32_t, const void *)',entry)
        set(ffi.cast('void *',settings),D.setter.privacyId,v)
        assert(v~=nil)
        return true
    end
    -- set_quickplay(matchmaker, 0, -1, 0x7FFFFFFF, 0, 0, 0, 0): the game's own Quickplay stop (game.dll 0x133E6E0).
    function A.stop_quickplay(entry,matchmaker)
        assert(address(entry)and address(matchmaker),'unsupported Quickplay stop call')
        local a=D.stopQuickplay.arguments
        local stop=ffi.cast('void (*)(void *, uint8_t, int32_t, int32_t, uint8_t, uint8_t, uint8_t, uint8_t)',entry)
        stop(ffi.cast('void *',matchmaker),a[1],a[2],a[3],a[4],a[5],a[6],a[7])
        return true
    end
    return A
end
function M.set_adapter(a)adapter_override=a end
-- The caller for this world, or nil, code, reason: tests' adapter, else the native one on a live process only (never
-- on a snapshot or an offline harness).
local function caller(world)
    if adapter_override then return adapter_override end
    if not(world.runtime and world.runtime.mode=='live')then
        return nil,'UNAVAILABLE','not a live game process'
    end
    if not native then
        local ok,a=pcall(M.native_adapter)
        if not ok then return nil,'UNAVAILABLE','the native call adapter: '..tostring(a)end
        native=a
    end
    return native
end

--------------------------------------------------------------------------------------------------- reading --
-- Every pin, once per world (the build is fixed by the fingerprint event_world proved; the pins name the code every
-- layout and both functions come from).
function M.prove(world)
    if state.proven and state.proven.key==world.key then return state.proven.ok,state.proven.why end
    local ok,why=true,nil
    for _,pin in ipairs(D.pins)do
        if not world.view.proves(world.game+pin.rva,pin.hex)then
            ok,why=false,('game.dll+%X changed (%s)'):format(pin.rva,pin.label)
            break
        end
    end
    state.proven={key=world.key,ok=ok,why=why}
    metrics.count('matchmaking_safety.proofs')
    return ok,why
end

local function text_at(world,address,limit)
    local raw=world.view.read(address,limit)
    if not raw then return nil end
    local nul=raw:find('\0',1,true)
    local text=nul and raw:sub(1,nul-1)or raw
    if text:find('[^\32-\126]')then return nil end
    return text
end
local function peer_hex(world,address)
    local raw=world.view.read(address,8)
    return raw and world_module.peer_hex(b.u32(raw,0),b.u32(raw,4))
end
-- The game's own descriptor lookup (game.dll 0x11ECD60) replayed: true when id exists (the setter reads its
-- descriptor without a NULL check).
local function descriptor_exists(world,id)
    local L=D.setter.lookup
    for k=0,L.groups-1 do
        local count=world.view.u32(world.game+L.counts+L.countStride*k)
        local array=world.view.pointer(world.game+L.table+8*k)
        if count and array and count>0 and count<=4096 then
            for i=0,count-1 do
                local value=world.view.u32(array+i*L.stride)
                if value==nil then return false end
                if value==id then return true end
            end
        end
    end
    return false
end

-- Everything the rule looks at, read now: {game, settings, privacy, game_state, ctx, singleplayer, local_peer,
-- host_peer, is_host, wrapper, engine, platform, active, playfab, pl_state, handle, joined, advertised (lobby key 19
-- text), sos_key (key 8 text), matchmaker, quickplay, joining}; or nil, code, reason. Nothing is called or written.
function M.observe(world)
    local G,C,W,P,K,MM=D.game,D.context,D.wrapper,D.playfab,D.lobbyKeys,D.matchmaker
    local o={}
    o.game=world.view.pointer(world.game+G.global)
    o.ctx=world.view.pointer(world.game+C.global)
    if not o.game or not o.ctx then return nil,'OFFLINE','no Game object or network context yet'end
    o.settings=o.game+G.settings
    o.privacy=world.view.u32(o.settings+D.settings.privacy)
    o.game_state=world.view.u32(o.game+G.state)
    if o.privacy==nil or o.game_state==nil then return nil,'UNREADABLE','the settings'end
    local sp=world.view.read(o.ctx+C.singleplayer,1)
    if not sp then return nil,'UNREADABLE','the network context'end
    o.singleplayer=sp:byte()~=0
    o.local_peer,o.host_peer=peer_hex(world,o.ctx+C.localPeer),peer_hex(world,o.ctx+C.hostPeer)
    if not o.local_peer or not o.host_peer then return nil,'UNREADABLE','the session peers'end
    o.is_host=o.host_peer=='0000000000000000'or o.host_peer==o.local_peer
    o.wrapper=o.ctx+C.wrapper
    local flag=world.view.read(o.wrapper+W.active,1)
    if not flag then return nil,'UNREADABLE','the lobby wrapper'end
    o.active=flag:byte()~=0
    o.engine=world.view.pointer(o.wrapper+W.engineLobby)
    o.platform=world.view.pointer(o.wrapper+W.platformLobby)
    if o.engine then
        o.playfab=world.view.pointer(o.engine+P.lobby)
        o.pl_state=o.playfab and world.view.u32(o.playfab+P.state)
        local handle=o.playfab and world.view.read(o.playfab+P.handle,8)
        o.handle=handle~=nil and handle~=string.rep('\0',8)
    end
    o.joined=o.active and o.engine~=nil and o.playfab~=nil and o.pl_state==P.joined and o.handle==true
    if o.joined then
        o.advertised=text_at(world,o.wrapper+W.keys+K.privacyMode*W.keyStride,W.keyLength)
        o.sos_key=text_at(world,o.wrapper+W.keys+K.sosBeacons*W.keyStride,W.keyLength)
    end
    o.matchmaker=world.view.pointer(world.game+MM.global)
    if o.matchmaker then
        local flags=world.view.read(o.matchmaker+MM.quickplay,2)
        if not flags then return nil,'UNREADABLE','the matchmaker'end
        o.quickplay,o.joining=flags:byte(1)~=0,flags:byte(2)~=0
    end
    return o
end
local function privacy_name(v)return M.NAMES[v]or('privacy '..tostring(v))end
-- The value the setter is called with: the player's own setting when it is not public, else Friends Only.
local function target_of(o)
    local p=o.privacy
    if p==D.privacy.friendsOnly or p==D.privacy.inviteOnly or p==D.privacy.friendsAndClan then return p end
    return M.ENFORCED
end
local function sos_active(o)return o.sos_key~=nil and o.sos_key~=''and o.sos_key~='0'end
-- The host's lobby advertises Open while no SOS Beacon forces it (the options menu's working copy did).
local function advertises_open(o)return o.is_host and o.joined and o.advertised=='0'and not sos_active(o)end

---------------------------------------------------------------------------------------------------- notice --
-- The screen notice: the hooks the panel is drawn through (init_progress's live-proven screen and font; tests
-- replace them).
M.hooks={}
function M.hooks.open_screen(world)return require('hd2runtime/runtime/init_progress').hooks.open_screen(world)end
function M.hooks.font()return require('hd2runtime/runtime/init_progress').hooks.font()end
local LAYER=930
local COLOURS={panel={220,10,12,14},edge={255,230,160,40},title={255,232,232,226},event={255,240,190,90},
    text={255,200,200,196}}
local function close_screen()
    if state.screen then pcall(state.screen.close)end
    state.screen=nil
end
-- Queues a notice: {line (what happened), rule, advice}; a newer notice replaces the one on screen. The same text is not
-- shown again within M.NOTICE_REPEAT s (the log keeps every line). Returns whether it was queued.
local function notify(line,rule,advice,title)
    local key=table.concat({title or'',line,rule or'',advice or''},'|')
    local last=state.notices[key]
    if last and state.clock-last<M.NOTICE_REPEAT then return false end
    state.notices[key]=state.clock
    state.notice={lines={title or M.TEXT.title,line,rule or M.TEXT.rule,advice or M.TEXT.advice},queued=state.clock,
        shown=nil}
    close_screen()
    metrics.count('matchmaking_safety.notices_queued')
    return true
end
local function draw(world,lines)
    local font=M.hooks.font()
    if not font then return nil,'the engine font is not loaded'end
    local screen,why=M.hooks.open_screen(world)
    if not screen then return nil,why end
    state.screen=screen
    local W,H=screen.width,screen.height
    local u=H/1080
    local m=24*u
    -- M.NOTICE_SCALE times the original panel, never wider than 90 % of the screen (narrow aspect ratios scale less).
    local k=math.min(M.NOTICE_SCALE,(W*0.9-m)/(430*u))
    u=u*k
    local w,h=430*u,80*u
    local x,y=W-w-m,H-h-m-(72+12)*(H/1080)      -- below the startup progress panel's place
    local pad=10*u
    local function need(id,what)if id==nil then error(what,0)end return id end
    local ok,err=pcall(function()
        need(screen.rect(x,y,LAYER,w,h,COLOURS.panel),'the panel')
        need(screen.rect(x,y+h-2*u,LAYER+1,w,2*u,COLOURS.edge),'the edge')
        need(screen.text(lines[1],font,12*u,font,x+pad,y+h-18*u,LAYER+2,COLOURS.title),'the title')
        need(screen.text(lines[2],font,10*u,font,x+pad,y+h-35*u,LAYER+2,COLOURS.event),'the event')
        need(screen.text(lines[3],font,9*u,font,x+pad,y+22*u,LAYER+2,COLOURS.text),'the rule')
        need(screen.text(lines[4],font,9*u,font,x+pad,y+8*u,LAYER+2,COLOURS.text),'the advice')
    end)
    if not ok then return nil,err,true end      -- a refused primitive: the GUI path does not work here
    return true
end
local function show(world)
    local n=state.notice
    if not n or state.gui_disabled then return end
    if n.shown then
        if state.clock-n.shown>=M.NOTICE_SECONDS then close_screen();state.notice=nil end
        return
    end
    if state.clock-n.queued>=M.NOTICE_WAIT then state.notice=nil;return end
    local ok,drawn,why,fatal=pcall(draw,world,n.lines)
    if ok and drawn then
        n.shown=state.clock
        metrics.count('matchmaking_safety.notices')
    else
        -- Not drawable yet (no font, no Ui World: why): tried again on the next check, quietly. A GUI error (a refused
        -- primitive, or an error) disables the notice for the session; the log keeps every safety line.
        close_screen()
        n.why=why
        if not ok or fatal then
            state.gui_disabled=true
            state.notice=nil
            log('MATCHMAKING SAFETY: the on-screen notice is unavailable ('..tostring(ok and why or drawn)..'); the '
                ..'log keeps every safety line')
        end
    end
end

---------------------------------------------------------------------------------------------- enforcement --
local function unavailable(code,why)
    say('unavailable',('MATCHMAKING SAFETY UNAVAILABLE (%s: %s): Public matchmaking is NOT blocked. Set Privacy to '
        ..'Friends Only / Invite Only and do not use Quickplay.'):format(code,why))
    if not state.said.unavailable_notice then
        state.said.unavailable_notice=true
        notify(M.TEXT.unavailable,M.TEXT.unavailable_advice,M.TEXT.advice)
    end
end
-- Why a call of `what` may not run now (nil when it may), plus the caller.
local function ready(world,what)
    if state.stopped[what]then return 'STOPPED',state.stopped[what]end
    if not scheduler.in_update()then return 'NOT_GAME_THREAD','only inside the Runtime\'s own update'end
    if state.clock-state.last_call[what]<M.MIN_CALL_INTERVAL[what]then
        return 'RATE',('at most one call per %g s'):format(M.MIN_CALL_INTERVAL[what])
    end
    local a,code,why=caller(world)
    if not a then return code,why end
    return nil,nil,a
end
local function failed(what,detail)
    state.failures[what]=state.failures[what]+1
    log(('MATCHMAKING SAFETY CALL NOT VERIFIED (%s, %d of %d): %s'):format(what,state.failures[what],M.MAX_FAILURES,
        detail))
    if state.failures[what]>=M.MAX_FAILURES then
        state.stopped[what]=detail
        log(('MATCHMAKING SAFETY FAILED (%s): %d unverified calls; this enforcement stops for the session, warnings '
            ..'only'):format(what,state.failures[what]))
        notify(M.TEXT.unavailable,M.TEXT.unavailable_advice,M.TEXT.advice)
    end
end

-- Privacy: the setting Public, or the host's lobby advertising Open with no SOS Beacon. Returns the outcome.
local function enforce_privacy(world,o)
    local target=target_of(o)
    -- The setting itself already non-public and only the lobby's advertisement still Open (the game re-advertises it
    -- after the setter; live r5: the host re-set it again and again): re-set at most every M.READVERTISE s, no notice,
    -- one line counting them every M.REPEAT_LOG s. The setting Public (the first time, or the player chose it again):
    -- enforced at once, logged and noticed.
    local lagging=o.privacy~=D.privacy.open and state.enforced>0
    if lagging and state.clock-state.last_call.privacy<M.READVERTISE then
        return {status='deferred',code='READVERTISE',reason='the lobby\'s advertisement still says Public'}
    end
    local why_text=('setting %s, advertised %s, %s, lobby %s'):format(privacy_name(o.privacy),
        o.advertised and('"'..o.advertised..'"')or'-',o.is_host and'host'or'client',o.joined and'joined'or
        (o.engine and'not joined'or'none'))
    local code,why,a=ready(world,'privacy')
    if not code then
        if not descriptor_exists(world,D.setter.privacyId)then code,why='NOT_READY','the settings descriptors are not '
            ..'loaded yet'
        elseif o.engine and not o.joined then code,why='LOBBY_BUSY','the lobby is not joined yet'end
    end
    if code then
        if code=='RATE'then return {status='deferred',code=code,reason=why}end
        if code=='NOT_READY'or code=='LOBBY_BUSY'or code=='NOT_GAME_THREAD'then
            say('privacy_wait',('MATCHMAKING SAFETY WAITING (%s: %s): lobby privacy is Public (%s)'):format(code,why,
                why_text))
            return {status='deferred',code=code,reason=why}
        end
        say('privacy_warn',('MATCHMAKING SAFETY WARNING: lobby privacy is Public (%s) and cannot be changed (%s: %s). '
            ..'Set Privacy to Friends Only / Invite Only yourself.'):format(why_text,code,why))
        if state.said.privacy_warn_notice~=code then
            state.said.privacy_warn_notice=code
            notify(M.TEXT.public_setting)
        end
        return {status='refused',code=code,reason=why}
    end
    state.last_call.privacy=state.clock
    metrics.count('matchmaking_safety.privacy_calls')
    a.set_privacy(world.game+D.setter.rva,o.settings,target)
    local after=M.observe(world)
    local ok=after and after.privacy==target and not advertises_open(after)
    if not ok then
        failed('privacy',('after the call: setting %s, advertised %s'):format(privacy_name(after and after.privacy),
            tostring(after and after.advertised)))
        return {status='failed',code='NOT_VERIFIED'}
    end
    state.failures.privacy=0
    state.said.privacy_wait,state.said.privacy_warn,state.said.privacy_warn_notice=nil,nil,nil
    if lagging then
        state.readvertised=state.readvertised+1
        if state.clock-state.readvertise_logged>=M.REPEAT_LOG then
            state.readvertise_logged=state.clock
            log(('MATCHMAKING SAFETY: the lobby still advertised Public with the setting %s: privacy set again (%d time%s '
                ..'since the last enforcement; at most every %d s; no notice)'):format(privacy_name(o.privacy),
                state.readvertised,state.readvertised==1 and''or's',M.READVERTISE))
        end
        event('readvertise',why_text)
        return {status='enforced',before=why_text,value=target,readvertised=true}
    end
    state.enforced=state.enforced+1
    state.readvertised=0
    log(('MATCHMAKING SAFETY: lobby privacy Public -> %s (%s; the game\'s own privacy setter, game.dll+%X, as the '
        ..'options menu changes it)%s. Public matchmaking is disabled while HD2Runtime is active; use Friends Only / Invite '
        ..'Only with compatible Runtime users.'):format(privacy_name(target),why_text,D.setter.rva,state.enforced>1
        and(' (Public chosen again: enforcement '..state.enforced..')')or''))
    event('privacy',why_text)
    notify(M.TEXT.privacy:format(privacy_name(target)))
    return {status='enforced',before=why_text,value=target}
end

-- Quickplay running: the game's own stop. Returns the outcome.
local function enforce_quickplay(world,o)
    local phase=o.joining and'joining a found lobby'or'searching'
    local code,why,a=ready(world,'quickplay')
    if not code and o.game_state~=D.game.ship then code,why='NOT_ON_SHIP','the game is not aboard the ship'end
    if code then
        if code=='RATE'then return {status='deferred',code=code,reason=why}end
        say('quickplay_warn',('MATCHMAKING SAFETY WARNING: Quickplay is running (%s) and cannot be cancelled (%s: %s); '
            ..'it joins public games with strangers. Cancel it.'):format(phase,code,why))
        if not state.said.quickplay_warn_notice then
            state.said.quickplay_warn_notice=true
            notify(M.TEXT.public_quickplay)
        end
        return {status='refused',code=code,reason=why}
    end
    state.last_call.quickplay=state.clock
    metrics.count('matchmaking_safety.quickplay_calls')
    a.stop_quickplay(world.game+D.stopQuickplay.rva,o.matchmaker)
    local after=M.observe(world)
    if not after or after.quickplay then
        failed('quickplay','the Quickplay flag is still set after the stop')
        return {status='failed',code='NOT_VERIFIED'}
    end
    state.failures.quickplay=0
    state.said.quickplay_warn,state.said.quickplay_warn_notice=nil,nil
    log(('MATCHMAKING SAFETY: Quickplay cancelled (%s; the game\'s own Quickplay stop, game.dll+%X, as the galactic '
        ..'war map\'s cancel does). Quickplay is public matchmaking and is disabled while HD2Runtime is active.'):format(
        phase,D.stopQuickplay.rva))
    event('quickplay',phase)
    notify(M.TEXT.quickplay)
    return {status='enforced',phase=phase}
end

-- One check: reads, decides, acts. Returns {status, ...} (tests and diagnostics).
function M.check(world,quickplay_only)
    local ok,why=M.prove(world)
    if not ok then unavailable('UNSUPPORTED_BUILD',why);return {status='unavailable',code='UNSUPPORTED_BUILD',reason=why}end
    if quickplay_only then
        -- Between full checks only the Quickplay flag is read (two reads per update); a set flag takes the full path.
        local mm=world.view.pointer(world.game+D.matchmaker.global)
        local flag=mm and world.view.read(mm+D.matchmaker.quickplay,1)
        if not(flag and flag:byte()~=0)then return {status='idle'}end
    end
    local o,code,reason=M.observe(world)
    if not o then
        if code=='OFFLINE'then return {status='offline',code=code,reason=reason}end
        -- An unreadable layout must persist UNREADABLE_GRACE s before it is reported (never a call meanwhile).
        state.unreadable_since=state.unreadable_since or state.clock
        if state.clock-state.unreadable_since<M.UNREADABLE_GRACE then
            return {status='waiting',code=code,reason=reason}
        end
        unavailable(code,reason)
        return {status='unavailable',code=code,reason=reason}
    end
    state.unreadable_since=nil
    state.said.unavailable,state.said.unavailable_notice=nil,nil
    if not state.announced then
        state.announced=true
        log(('MATCHMAKING SAFETY ACTIVE: Public matchmaking is disabled while HD2Runtime is active (privacy Public -> '
            ..'Friends Only, Quickplay cancelled, SOS Beacon warned; Friends Only / Invite Only untouched). Build %s, %d '
            ..'pins.'):format(D.source.build,#D.pins))
    end
    local out={status='safe',privacy=o.privacy,observed=o}
    if o.singleplayer then out.status='singleplayer';return out end
    if o.quickplay then out.quickplay=enforce_quickplay(world,o);out.status='quickplay'end
    if quickplay_only then return out end
    if o.privacy==D.privacy.open or advertises_open(o)then
        out.privacy_action=enforce_privacy(world,o)
        out.status=out.status=='quickplay'and out.status or'public'
    end
    -- The SOS Beacon: the game advertises Open while it is active, whatever the setting. Warned, never overridden.
    local sos=o.is_host and o.joined and sos_active(o)
    if sos and not state.sos then
        log('MATCHMAKING SAFETY WARNING: an SOS Beacon is active and the game made this lobby PUBLIC (advertised '
            ..'privacy "'..tostring(o.advertised)..'", SOSBeacons "'..tostring(o.sos_key)..'"): strangers can join through '
            ..'Quickplay until it ends. HD2Runtime cannot block the SOS Beacon; do not use it while Runtime is active.')
        event('sos',o.sos_key)
        notify(M.TEXT.sos,M.TEXT.rule,'Do not use the SOS Beacon while Runtime is active.')
    elseif not sos and state.sos then
        log('MATCHMAKING SAFETY: the SOS Beacon ended; the lobby advertises the privacy setting again')
    end
    state.sos=sos
    if sos and out.status=='safe'then out.status='sos'end
    return out
end

-- Another Runtime safety notice in the same panel (the same size, place and repeat rule): {title, line, rule, advice}.
-- Returns whether it was queued (false: the same text within M.NOTICE_REPEAT s).
function M.notice(title,line,rule,advice)return notify(line,rule,advice,title)end

------------------------------------------------------------------------------------------------------ watch --
local function tick(dt)
    state.clock=state.clock+(type(dt)=='number'and dt>=0 and dt<10 and dt or 0)
    local world=world_module.open()
    if not world then return end
    -- Only the live game process is guarded: a snapshot or offline harness (no tests' adapter) ends the watch, so the
    -- Runtime's update hook still detaches when nothing else needs it.
    if not adapter_override and not(world.runtime and world.runtime.mode=='live')then
        if state.watch then state.watch.status='complete'end
        return
    end
    local full=state.clock>=state.next_check
    if full then state.next_check=state.clock+M.CHECK end
    M.check(world,not full)
    if full then show(world)end
end
M.tick_for_tests=tick
-- Starts the watch (once; safe to call any number of times). The wiring: api/hd2.lua at load.
function M.start()
    if state.watch and state.watch.status=='active'then return state.watch end
    local watch={status='active'}
    function watch.cancel()watch.status='cancelled';close_screen()end
    function watch.tick(dt)
        if watch.status~='active'then return end
        local started=metrics.now()
        local ok,why=pcall(tick,dt)
        metrics.elapsed('matchmaking_safety.tick',started)
        if not ok then
            log('MATCHMAKING SAFETY STEP FAILED: '..tostring(why)..'; Public matchmaking is NOT blocked until the next '
                ..'check succeeds')
        end
    end
    state.watch=watch
    scheduler.attach(watch)
    return watch
end
-- Development / tests: what the module did and sees.
function M.status()
    return {clock=state.clock,announced=state.announced,failures={privacy=state.failures.privacy,
        quickplay=state.failures.quickplay},stopped={privacy=state.stopped.privacy,quickplay=state.stopped.quickplay},
        sos=state.sos,events=state.events,notice=state.notice and state.notice.lines,
        visible=state.screen~=nil,gui_disabled=state.gui_disabled}
end
function M.reset_for_tests()
    close_screen()
    if state.watch then state.watch.status='cancelled'end
    state=fresh()
    adapter_override,native=nil,nil
end
return M
