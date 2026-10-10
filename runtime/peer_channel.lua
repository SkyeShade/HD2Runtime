-- The Runtime-to-Runtime peer channel (DEVELOPMENT; research/docs/runtime-peer-messaging-F5FEE03DCFDB.md, section 2;
-- research/peer-messaging-F5FEE03DCFDB.json). Not exported to mods; the user approved it for RuntimePeerHelloProof only:
-- no custom stratagem uses it yet.
--
-- The channel is the game's own PlayFab lobby member data: each member's key/value properties, kept by the PlayFab
-- service and readable by every member of the lobby. game.dll publishes and reads its own two keys ("platform_lobby",
-- "crossplay_mode") through two slots of the engine's API table T = [[game+0x3326308]+0xF8]; the Runtime calls the same
-- two slots for its own keys (M.KEYS): `hd2rt` (the custom stratagem multiplayer state, runtime/custom_mp_sync.lua),
-- `hd2as` (the synced asset set, runtime/asset_sync.lua) and `hd2bc` (the beam conversion set, runtime/beam_conversion_
-- sync.lua):
--   * T+0x120 set_member_data(engine lobby, 1, &key, &value): one PFLobbyPostUpdate of this machine's own property;
--   * T+0x118 member_data(engine lobby, peer, key): a member's property as the SDK holds it (NULL: none).
-- Two native calls (runtime/windows_write.lua), each only:
--   * inside the Runtime's own update (the game thread, where the game itself uses the lobby);
--   * after every pin re-proved and the registry, T and both slots resolved to the pinned engine functions;
--   * with the game's lobby joined: the wrapper's flag (the game's own condition), its engine lobby, the PlayfabLobby
--     state 3 and handle, the local peer among its members.
-- Publishing is rate-limited because the PlayFab service's request limit is shared with the game's own posts (its one
-- "platform_lobby" post per join is never retried): nothing in the first FIRST_POST_DELAY seconds of a lobby, nor
-- before the game made that post (the wrapper's byte it sets right after it) unless PLATFORM_WAIT seconds passed; then
-- at most one post per MIN_POST_INTERVAL, never an unchanged value, and after MAX_FAILURES failed posts in a lobby
-- nothing more there. The value is posted again in every new lobby this machine joins.
-- More keys never raise the post rate: MIN_POST_INTERVAL holds between ANY two posts of this machine (whichever key),
-- the join and "platform_lobby" delays count from when the channel first saw the lobby, and when several keys have a
-- value due the one posted least recently goes first (none can starve another). Each key keeps its own value, its
-- last post and its failure count; the OWNED rule (below) is the hd2rt key's only.
-- Reading is polling: the engine raises no event when another member's property changes.
-- Received values are text only. This module copies them (bounded, printable ASCII); what they mean is
-- runtime/peer_protocol.lua's business, and nothing received is ever an address or a value to write.
local world_module=require('hd2runtime/runtime/event_world')
local scheduler=require('hd2runtime/runtime/scheduler')
local log_module=require('hd2runtime/runtime/log')
local metrics=require('hd2runtime/runtime/metrics')
local b=require('hd2runtime/core/bytes')
local D=require('hd2runtime/domains/peer_messaging')
local M={}
M.KEY='hd2rt'
-- The only keys this machine ever publishes or reads (never one of the game's own, domains/peer_messaging gameKeys).
M.KEYS={hd2rt=true,hd2as=true,hd2bc=true}
M.MAX_VALUE=512
M.MAX_MEMBERS=16
M.FIRST_POST_DELAY=10
M.PLATFORM_WAIT=20          -- the longest a first post waits for the game's own "platform_lobby" post
M.MIN_POST_INTERVAL=5
M.MAX_FAILURES=3
M.RETRY=0.5                 -- seconds between the watch's attempts while a value is set

local proven                -- {key, ok, why}: the pins, once per proven world
local clock=0               -- seconds of Runtime updates since the channel started
local lobby_seen            -- {id, since}: the joined lobby this machine is in, and when it first saw it
local last_post             -- {at, lobby}: this machine's last post attempt (any key), for MIN_POST_INTERVAL
local next_try=0
local owner                 -- M.OWNER once the custom stratagem state published
local watch
-- Per key: {key, wanted (the value this machine publishes), posted ({value, at, lobby}: the last post of this key
-- there; value nil: it failed), failures (failed posts of this key in this lobby), lobby (the lobby posted and
-- failures belong to), said}.
local keys={}
local order={}              -- the keys in the order they were first used
local function state(key)
    local k=keys[key]
    if not k then
        k={key=key,failures=0,said={}}
        keys[key]=k;order[#order+1]=k
    end
    return k
end
-- The hd2rt key's lines are unchanged; another key is named in them.
local function tag(k)return k.key==M.KEY and''or(k.key..' ')end

local function log(text)log_module.emit('[HD2Runtime] '..text)end
local function say(k,slot,text)
    if k.said[slot]==text then return end
    k.said[slot]=text
    log(text)
end
function M.reset_for_tests()
    if watch then watch.cancel()end
    proven,lobby_seen,last_post,watch,owner=nil,nil,nil,nil,nil
    clock,next_try,keys,order=0,0,{},{}
end
function M.clock()return clock end

-- Every pin, once per world (the build is fixed by the fingerprint; the pins name the code the layout comes from).
function M.prove(world)
    if proven and proven.key==world.key then return proven.ok,proven.why end
    local ok,why=true,nil
    for _,pin in ipairs(D.pins)do
        local base=pin.module=='exe'and world.exe or world.game
        if not world.view.proves(base+pin.rva,pin.hex)then
            ok,why=false,('%s+%X changed (%s)'):format(pin.module,pin.rva,pin.label)
            break
        end
    end
    proven={key=world.key,ok=ok,why=why}
    metrics.count('peer_channel.proofs')
    return ok,why
end

-- The two engine functions, re-read every time: the registry, T and both slots must be exactly the pinned ones.
local function slots(world)
    local A=D.api
    local registry=world.view.pointer(world.game+A.registryGlobal)
    if registry~=world.exe+A.registry then return nil,'the engine API registry is not the pinned one'end
    local T=world.view.pointer(registry+A.table)
    if T~=world.exe+A.tableRva then return nil,'the PlayFab API table is not the pinned one'end
    local get,set=world.view.pointer(T+A.memberData),world.view.pointer(T+A.setMemberData)
    if get~=world.exe+A.memberDataRva or set~=world.exe+A.setMemberDataRva then
        return nil,'a member-data slot is not the pinned function'
    end
    return {get=get,set=set}
end

-- The game's joined lobby, re-read every time: {engine (the engine lobby), playfab, id (diagnostic text), members =
-- {{peer, lo, hi, local}}, local_peer, platform_posted (the game made its own "platform_lobby" post here)}, or nil,
-- code, reason. Nothing is called.
function M.lobby(world)
    local C,WR,PL=D.context,D.wrapper,D.playfab
    local ctx=world.view.pointer(world.game+C.global)
    if not ctx then return nil,'NO_SESSION','no network context'end
    local wrapper=ctx+C.wrapper
    local flag=world.view.read(wrapper+WR.active,1)
    if not flag then return nil,'UNREADABLE','the lobby wrapper'end
    if flag:byte()==0 then return nil,'NOT_JOINED','the game is in no lobby'end
    local platform=world.view.read(wrapper+WR.platformPosted,1)
    if not platform then return nil,'UNREADABLE','the lobby wrapper'end
    local engine=world.view.pointer(wrapper+WR.engineLobby)
    if not engine then return nil,'NOT_JOINED','the wrapper holds no engine lobby'end
    local pl=world.view.pointer(engine+PL.lobby)
    if not pl then return nil,'NOT_JOINED','the engine lobby holds no PlayFab lobby'end
    local state=world.view.u32(pl+PL.state)
    if state~=PL.joined then return nil,'NOT_JOINED','PlayFab lobby state '..tostring(state)end
    local handle=world.view.read(pl+PL.handle,8)
    if not handle or handle==string.rep('\0',8)then return nil,'NOT_JOINED','no PlayFab lobby handle'end
    local count=world.view.u32(pl+PL.memberCount)
    if not count or count<1 or count>M.MAX_MEMBERS then return nil,'UNREADABLE','member count '..tostring(count)end
    local array=world.view.pointer(pl+PL.members)
    local raw=array and world.view.read(array,count*8)
    if not raw then return nil,'UNREADABLE','the member list'end
    local lo,hi=world_module.local_peer(world)
    if not lo then return nil,'UNREADABLE','the local peer'end
    local members,found={},false
    for i=0,count-1 do
        local plo,phi=b.u32(raw,i*8),b.u32(raw,i*8+4)
        local mine=plo==lo and phi==hi
        found=found or mine
        members[#members+1]={peer=world_module.peer_hex(plo,phi),lo=plo,hi=phi,['local']=mine}
    end
    if not found then return nil,'NOT_MEMBER','the local peer is not a member of the lobby'end
    local text=world.view.pointer(pl)
    local id=text and(world.view.read(text,64)or''):match('^[%w%-:]+')
    -- The session host (network context +0xB3A8, the peer game_session_disconnect checks a sender against).
    local host=world.view.read(ctx+C.hostPeer,8)
    local host_peer=host and world_module.peer_hex(b.u32(host,0),b.u32(host,4))
    return {engine=engine,playfab=pl,id=id or('lobby@'..string.format('%X',pl)),members=members,
        local_peer=world_module.peer_hex(lo,hi),platform_posted=platform:byte()~=0,host_peer=host_peer,
        is_host=host_peer==world_module.peer_hex(lo,hi)}
end

-- A string the SDK owns: printable ASCII up to its NUL, read page by page (never past an unreadable page). nil, why.
local function read_text(world,address)
    local parts,total,at=nil,0,address
    parts={}
    while total<=M.MAX_VALUE do
        local n=math.min(M.MAX_VALUE+1-total,4096-at%4096)
        local chunk=world.view.read(at,n)
        if not chunk then return nil,'unreadable'end
        local nul=chunk:find('\0',1,true)
        if nul then
            parts[#parts+1]=chunk:sub(1,nul-1)
            local text=table.concat(parts)
            if text:find('[^\32-\126]')then return nil,'not printable ASCII'end
            return text
        end
        parts[#parts+1]=chunk
        total=total+n
        at=at+n
    end
    return nil,'longer than '..M.MAX_VALUE..' bytes'
end

-- Why a native call may not run now (nil when it may): adapter, thread, pins, table and slots.
local function ready(world,what)
    if not(world.runtime and world.runtime[what])then
        return 'UNAVAILABLE','this Runtime adapter cannot call game functions'
    end
    if not scheduler.in_update()then return 'NOT_GAME_THREAD','only inside the Runtime\'s own update'end
    local ok,why=M.prove(world)
    if not ok then return 'UNSUPPORTED_BUILD',why end
    local s,swhy=slots(world)
    if not s then return 'UNSUPPORTED_BUILD',swhy end
    return nil,nil,s
end

-- Posts `wanted` when it is due: not yet posted in this lobby, the lobby joined for FIRST_POST_DELAY s, the game's
-- own "platform_lobby" post made (or PLATFORM_WAIT s passed), the last post MIN_POST_INTERVAL s ago, fewer than
-- MAX_FAILURES failures here. Returns the outcome, or nil (nothing set).
local function flush(world,k)
    local wanted=k.wanted
    if not wanted then return nil end
    local code,why,s=ready(world,'native_lobby_publish')
    if code then
        say(k,'publish','PEER CHANNEL: '..tag(k)..'post waiting ('..code..': '..why..')')
        return {status='deferred',code=code,reason=why}
    end
    local lobby,lcode,lwhy=M.lobby(world)
    if not lobby then
        say(k,'publish','PEER CHANNEL: '..tag(k)..'post waiting ('..lcode..': '..lwhy..')')
        return {status='deferred',code=lcode,reason=lwhy}
    end
    if not lobby_seen or lobby_seen.id~=lobby.id then
        lobby_seen={id=lobby.id,since=clock}
        log(('PEER CHANNEL LOBBY: %s, %d members; this machine is %s'):format(lobby.id,#lobby.members,
            lobby.local_peer))
    end
    if k.lobby~=lobby.id then
        k.lobby=lobby.id
        k.posted,k.failures=nil,0           -- a new lobby holds no value of this machine's
    end
    local posted,failures=k.posted,k.failures
    if posted and posted.value==wanted then return {status='unchanged'}end
    if failures>=M.MAX_FAILURES then
        return {status='refused',code='POST_FAILED',reason=failures..' failed posts in this lobby'}
    end
    if clock-lobby_seen.since<M.FIRST_POST_DELAY then
        return {status='deferred',code='JOIN_DELAY',reason=('the first post waits %d s after joining a lobby'):format(
            M.FIRST_POST_DELAY)}
    end
    if not lobby.platform_posted and clock-lobby_seen.since<M.PLATFORM_WAIT then
        return {status='deferred',code='GAME_POST',reason=('the first post waits for the game\'s own "platform_lobby" '
            ..'post (at most %d s)'):format(M.PLATFORM_WAIT)}
    end
    -- Between ANY two posts of this machine (whichever key): the keys share the PlayFab post rate.
    if last_post and last_post.lobby==lobby.id and clock-last_post.at<M.MIN_POST_INTERVAL then
        return {status='deferred',code='RATE',reason=('at most one post per %d s'):format(M.MIN_POST_INTERVAL)}
    end
    local value=wanted
    metrics.count('peer_channel.posts')
    local result=world.runtime.native_lobby_publish(s.set,lobby.engine,k.key,value)
    last_post={at=clock,lobby=lobby.id}
    if result==0 then
        k.posted,k.failures={value=value,at=clock,lobby=lobby.id},0
        -- Every change is posted; CUSTOM MP PUBLISH names each (r44: the first few here, then every 25th).
        if log_module.sample('peer_channel.posted'..(k.key==M.KEY and''or('.'..k.key)),3,25)then
            log(('PEER CHANNEL POSTED: %s = "%s" (%d bytes; lobby %s, %d members; the game\'s set_member_data, '
                ..'exe+%X)'):format(k.key,value,#value,lobby.id,#lobby.members,D.api.setMemberDataRva))
        end
        return {status='posted',value=value,lobby=lobby.id}
    end
    failures=failures+1
    k.failures=failures
    k.posted={value=nil,at=clock,lobby=lobby.id}
    local hresult=string.format('0x%08X',(tonumber(result)or 0)%4294967296)
    if failures>=M.MAX_FAILURES then
        log(('PEER CHANNEL %sPOST FAILED %d times (last %s): nothing more is posted in this lobby'):format(tag(k),
            failures,hresult))
    else
        log(('PEER CHANNEL %sPOST FAILED (%s); retried after %d s'):format(tag(k),hresult,M.MIN_POST_INTERVAL))
    end
    return {status='failed',code='POST_FAILED',reason=hresult}
end

-- The keys with a value set, the one posted least recently first (never posted: first; ties: first used first).
local function due()
    local list={}
    for i,k in ipairs(order)do if k.wanted then list[#list+1]={k=k,at=k.posted and k.posted.at or-1,i=i}end end
    table.sort(list,function(a,c)if a.at~=c.at then return a.at<c.at end return a.i<c.i end)
    return list
end

-- The channel's own watch: its clock, and every RETRY s the due post (a new lobby, the delays, a changed value).
-- Attached once, on the first publish or poll.
local function start()
    if watch then return end
    watch={status='active'}
    function watch.cancel()watch.status='cancelled'end
    function watch.tick(dt)
        clock=clock+(dt or 0)
        if clock>=next_try then
            local list=due()
            if#list>0 then
                next_try=clock+M.RETRY
                local world=world_module.open()
                if world then for _,item in ipairs(list)do flush(world,item.k)end end
            end
        end
    end
    scheduler.attach(watch)
end

-- Sets this machine's own value (printable ASCII, 1..MAX_VALUE bytes). It is posted as soon as the rate limits and the
-- lobby allow (now, when they already do), and again in every lobby this machine joins later. owner: who publishes.
-- The custom stratagem multiplayer state (M.OWNER) owns the one key once it publishes: any other publisher (the
-- standalone RuntimePeerHelloProof) is then refused, OWNED. Returns {status = 'posted' | 'deferred' | 'unchanged' |
-- 'failed' | 'refused', code, reason}. key: one of M.KEYS (default M.KEY); the OWNED rule is M.KEY's only.
M.OWNER='custom stratagems'
local function key_of(key)
    if key==nil then return M.KEY end
    return M.KEYS[key]and key or nil
end
function M.publish(value,by,key)
    if not(type(value)=='string'and#value>=1 and#value<=M.MAX_VALUE and not value:find('[^\32-\126]'))then
        return {status='refused',code='INVALID',reason='the value must be 1-'..M.MAX_VALUE..' printable ASCII bytes'}
    end
    local name=key_of(key)
    if not name then return {status='refused',code='INVALID_KEY',reason='not a Runtime member-data key: '..tostring(key)}end
    if name==M.KEY then
        if by==M.OWNER then owner=M.OWNER
        elseif owner==M.OWNER then
            return {status='refused',code='OWNED',reason='the custom stratagem multiplayer state publishes this '
                ..'machine\'s '..M.KEY..' value'}
        end
    end
    start()
    local k=state(name)
    k.wanted=value
    local world,why=world_module.open()
    if not world then return {status='deferred',code='UNAVAILABLE',reason=why}end
    return flush(world,k)
end

-- Every lobby member's value. Returns {lobby, values = {{peer, local, value (nil: none), error}}} or nil, code, reason.
-- opts.include_local: also this machine's own (as the SDK holds it); opts.key: which of M.KEYS (default M.KEY).
function M.poll(world,opts)
    local key=key_of(opts and opts.key)
    if not key then return nil,'INVALID_KEY','not a Runtime member-data key: '..tostring(opts.key)end
    start()
    local code,why,s=ready(world,'native_lobby_read')
    if code then return nil,code,why end
    local lobby,lcode,lwhy=M.lobby(world)
    if not lobby then return nil,lcode,lwhy end
    local values={}
    for _,m in ipairs(lobby.members)do
        if not m['local']or(opts and opts.include_local)then
            metrics.count('peer_channel.reads')
            local address=world.runtime.native_lobby_read(s.get,lobby.engine,m.lo,m.hi,key)
            local entry={peer=m.peer,['local']=m['local']}
            if address then entry.value,entry.error=read_text(world,address)end
            values[#values+1]=entry
        end
    end
    return {lobby=lobby,values=values}
end

-- What this machine publishes under a key (default M.KEY), what it last posted in this lobby (nil: nothing yet) and
-- where.
function M.status(key)
    local k=keys[key_of(key)or M.KEY]or{failures=0}
    return {wanted=k.wanted,posted=k.posted and k.posted.value,lobby=lobby_seen and lobby_seen.id,failures=k.failures,
        clock=clock,last_post=last_post and last_post.at}
end
return M
