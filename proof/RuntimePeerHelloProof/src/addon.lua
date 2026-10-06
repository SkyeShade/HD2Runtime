local hd2=require('mods/skyeshade/hd2runtime')
-- RuntimePeerHelloProof 0.1.0: the smallest Runtime-to-Runtime proof (DEVELOPMENT; docs/research/runtime-peer-
-- messaging-F5FEE03DCFDB.md, section 4). Nothing of gameplay changes.
--
-- Each machine publishes ONE lobby member property, hd2rt, through the Runtime's peer channel (runtime/peer_channel.lua:
-- the game's own PlayFab lobby member data, the two engine functions game.dll calls for its own keys), and reads every
-- other member's. The value is an hd2rt/1 state (runtime/peer_protocol.lua) with no custom stratagem in it:
--   HELLO          seq 1, as soon as the channel allows (10 s after this machine joined the lobby);
--   SIZE PROBE     seq 2, four 48-character slot ids (the longest legal value), 20 s after another member's value was
--                  first read here;
--   MISSION        20 s into a mission (the lobby and the channel in a mission);
--   BACK ON SHIP   after that mission, aboard the ship again.
-- A value is set only after the previous one was posted, so the channel's rate limit never folds two of them together.
-- Every member's value is read every 2 s aboard the ship and every 5 s in a mission, and logged when it changes, with
-- this machine's UTC time (compare two players' logs for the latency).
-- This proof itself reads and writes no game memory and makes no game call; the Runtime's peer channel does both.
local mod=hd2.mod()
local BUILD='0.1.0 PEER HELLO BUILD'
local ok,channel=pcall(require,'hd2runtime/runtime/peer_channel')
if not ok then
    mod:log('RuntimePeerHelloProof '..BUILD..': this HD2Runtime has no peer channel. Install '
        ..'HD2Runtime-0.30.0-dev-peer-channel.zip (its log says "EXPERIMENTAL MULTIPLAYER PEER-CHANNEL BUILD"). '
        ..'Nothing runs.')
    return
end
local P=require('hd2runtime/runtime/peer_protocol')
local world_module=require('hd2runtime/runtime/event_world')
local scheduler=require('hd2runtime/runtime/scheduler')

local VERSION=hd2.version_label or hd2.version
local REGISTRY=P.registry_hash({})          -- the proof registers no custom stratagem: the empty registry's hash
local POLL_SHIP,POLL_MISSION=2,5
local SIZE_PROBE_AFTER,MISSION_POST_AFTER=20,20
local SIZE_SLOTS={}
for k=1,4 do
    local head=('size_probe_slot%d_'):format(k-1)
    SIZE_SLOTS[k]=head..string.rep('x',48-#head)
end

mod:log(('RuntimePeerHelloProof %s: publishes ONE lobby member property (hd2rt) through the Runtime\'s peer channel and '
    ..'reads every other member\'s. Play with at least one other player who runs this proof and the same HD2Runtime '
    ..'build: stay aboard the ship about a minute, play one mission (stay in it at least 30 s), return to the ship and '
    ..'wait a minute. Search for "PEER HELLO RECEIVED", "SIZE PROBE RECEIVED", "OWN VALUE VISIBLE", "PEER IDS", '
    ..'"STATE" and "PEER CHANNEL". Ctrl+F10: the status. Nothing of gameplay changes.'):format(BUILD))

local function utc()
    local done,text=pcall(os.date,'!%H:%M:%S')
    return done and text or'?'
end
local said={}
local function once(key,text)
    if said[key]==text then return end
    said[key]=text
    mod:log(text)
end

local seq=0
local current                -- {seq, value, kind, set_at (the channel's clock), utc}
local kinds={}               -- the kinds already set
local visible={}             -- [seq] = true once this machine read its own value back
local peers={}               -- [peer] = {value, seq, said_none}
local first_remote_at        -- the channel clock when another member's value was first read
local where,where_since

local function publish(kind,slots)
    seq=seq+1
    local value=assert(P.encode({version=VERSION,registry=REGISTRY,seq=seq,slots=slots}))
    current={seq=seq,value=value,kind=kind,set_at=channel.clock(),utc=utc()}
    kinds[kind]=true
    local r=channel.publish(value)
    mod:log(('%s SET (seq %d, %d bytes, %s UTC): "%s"; the channel: %s%s'):format(kind,seq,#value,current.utc,value,
        r.status,r.code and(' ('..r.code..')')or''))
end
-- The last value set has been posted (the next may be set without folding into it).
local function idle()return current~=nil and channel.status().posted==current.value end

local function slots_text(s)
    local out={}
    for k=1,4 do out[k]=s.slots[k]or'-'end
    return table.concat(out,',')
end

local function peer_ids(world,lobby)
    local players=world_module.players(world)
    local session={}
    for _,p in ipairs(players)do session[p.peer]=true end
    local members,all={},true
    for _,m in ipairs(lobby.members)do
        members[#members+1]=m.peer..(m['local']and' (you)'or'')
        all=all and session[m.peer]==true
    end
    local listed={}
    for _,p in ipairs(players)do listed[#listed+1]=p.peer..(p['local']and' (you)'or'')end
    once('ids',('PEER IDS: lobby members %s; session players %s; every lobby member is a session player: %s'):format(
        table.concat(members,', '),#listed>0 and table.concat(listed,', ')or'none listed',all and'yes'or'NO'))
end

local function received(peer,value,now)
    local st=peers[peer]
    local s,code,why=P.decode(value)
    if not s then
        mod:log(('PEER VALUE REFUSED from %s (%s UTC): %s: %s ("%s")'):format(peer,utc(),code,why,value))
        return
    end
    if st.seq and s.seq<=st.seq then
        mod:log(('PEER SEQ REGRESSION from %s: %d after %d'):format(peer,s.seq,st.seq))
    elseif st.seq and s.seq>st.seq+1 then
        mod:log(('PEER SEQ GAP from %s: %d after %d (a value in between was replaced before this machine read it)')
            :format(peer,s.seq,st.seq))
    end
    st.seq=s.seq
    first_remote_at=first_remote_at or now
    local compatible,field=P.compatible({version=VERSION,registry=REGISTRY},s)
    mod:log(('PEER HELLO RECEIVED from %s (%s UTC, %s): seq %d, Runtime %s, registry %s, slots %s, %d bytes; '
        ..'compatible with this machine: %s'):format(peer,utc(),where or'?',s.seq,s.version,s.registry,slots_text(s),
        #value,compatible and'yes'or('NO ('..field..' differs: mine '..VERSION..' / '..REGISTRY..')')))
    if s.slots[1]and s.slots[1]:find('^size_probe_')then
        local whole=true
        for k=1,4 do whole=whole and s.slots[k]==SIZE_SLOTS[k]end
        mod:log(('SIZE PROBE RECEIVED %s from %s: %d bytes'):format(whole and'WHOLE'or'DAMAGED',peer,#value))
    end
end

local next_poll=0
local watch={status='active'}
function watch.cancel()watch.status='cancelled'end
function watch.tick()
    local now=channel.clock()
    if now<next_poll then return end
    local world=world_module.open()
    if not world then next_poll=now+POLL_SHIP;return end
    local game=world_module.game_state(world)
    local here=game and game.mission and'mission'or'ship'
    next_poll=now+(here=='mission'and POLL_MISSION or POLL_SHIP)
    if here~=where then
        where,where_since=here,now
        local lobby,code,why=channel.lobby(world)
        mod:log(('STATE: %s (%s UTC)%s; lobby %s'):format(here,utc(),game and game.mission and(', this machine is the '
            ..(game.host and'host'or'client'))or'',lobby and(lobby.id..', '..#lobby.members..' members')
            or(tostring(code)..': '..tostring(why))))
    end
    if not current then publish('HELLO',{})
    elseif idle()then
        if current.kind=='HELLO'and first_remote_at and now-first_remote_at>=SIZE_PROBE_AFTER then
            publish('SIZE PROBE',SIZE_SLOTS)
        elseif here=='mission'and not kinds.MISSION and now-where_since>=MISSION_POST_AFTER then
            publish('MISSION',{})
        elseif here=='ship'and kinds.MISSION and not kinds['BACK ON SHIP']then
            publish('BACK ON SHIP',{})
        end
    end
    local p,code,why=channel.poll(world,{include_local=true})
    if not p then
        once('poll',('POLL WAITING (%s): %s: %s'):format(here,tostring(code),tostring(why)))
        return
    end
    said.poll=nil
    peer_ids(world,p.lobby)
    for _,v in ipairs(p.values)do
        if v['local']then
            if current and v.value==current.value and not visible[current.seq]then
                visible[current.seq]=true
                mod:log(('OWN VALUE VISIBLE: %s (seq %d) reads back from the lobby %.1f s after it was set (%s UTC)')
                    :format(current.kind,current.seq,now-current.set_at,utc()))
            end
        else
            local st=peers[v.peer]or{}
            peers[v.peer]=st
            if v.error then
                once('error:'..v.peer,('PEER VALUE REFUSED from %s: %s'):format(v.peer,v.error))
            elseif not v.value then
                if not st.said_none then
                    st.said_none=true
                    mod:log(('PEER %s: no hd2rt value yet (no peer channel on that machine, or its first post still '
                        ..'waits)'):format(v.peer))
                end
            elseif v.value~=st.value then
                st.value=v.value
                received(v.peer,v.value,now)
            end
        end
    end
end
scheduler.attach(watch)

hd2.input.bind('peer_hello.status',{key='Ctrl+F10',on_press=function()
    local s=channel.status()
    local parts={}
    for peer,st in pairs(peers)do parts[#parts+1]=peer..' seq '..tostring(st.seq)end
    mod:log(('STATUS (%s UTC): this machine set %s, posted %s in lobby %s (%d failed posts); peers read: %s'):format(
        utc(),current and(current.kind..' seq '..current.seq)or'nothing',tostring(s.posted~=nil and s.posted==s.wanted),
        tostring(s.lobby),s.failures,#parts>0 and table.concat(parts,'; ')or'none'))
end})
