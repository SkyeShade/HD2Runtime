local hd2=require('mods/skyeshade/hd2runtime')
-- PelicanSpawnProof 0.2.0: THE HOVER ANCHOR, AND WHAT OTHER PLAYERS SEE (docs/event-scripting.md, "Pelicans";
-- docs/research/pelican-cas-F5FEE03DCFDB.md).
--
-- 0.1.0 is live-proven for the spawn (empty), the 60 s hold and the departure; its Pelican hovered ~250 m from the
-- requested point: the game's default spawn context is all zero, so the Pelican's drop-position record (its hover
-- anchor) was the world origin. hd2.pelican.spawn now hands the game a Runtime-owned copy of that context whose only set
-- member is the anchor (+0x610, as a beacon sets it for a vehicle drop): the Pelican is created 250 m back along your
-- heading and 80 m up, flies in and hovers over the requested point.
--
-- HOST: Ctrl+F8 asks for one empty Pelican hovering 25 m east of you, held 60 s after its release (public API only);
-- other players may be present (the API is host only). The proof logs every step and, every 5 s, where it is against
-- the requested point.
-- EVERY MACHINE (host and clients), read-only: every transport Pelican the game has here, by entity and network id (its
-- first sighting, stage changes, release, removal, and its anchor), so a client's log shows whether the host's Pelican
-- exists there, where, and whether it leaves when the host's does (INTERNAL observation: runtime/pelicans.lua readers,
-- never a write; not public API).
local mod=hd2.mod()
local BUILD='0.2.0 HOVER-ANCHOR + MULTIPLAYER BUILD'
local HOVER=60
local OFFSET=25
mod:log('PelicanSpawnProof '..BUILD..': HOST, in a mission, stand in the open and press Ctrl+F8. Expect "PELICAN SPAWN '
    ..'REQUESTED ... anchor", "PELICAN SPAWN CREATED ... anchor ... verified true", an empty Pelican flying in from behind '
    ..'you and "PELICAN HOVERING ... from the requested position" (a few metres, not ~250), "PELICAN HELD" about 60 s, '
    ..'then "PELICAN DEPARTING", "PELICAN GONE". CLIENTS (multiplayer, with this proof installed): "SEEN PELICAN" lines '
    ..'for the host\'s Pelican. Ctrl+F11: status.')

-- INTERNAL read-only observation (never written through here).
local pelicans=require('hd2runtime/runtime/pelicans')
local world_module=require('hd2runtime/runtime/event_world')

local function n1(v)return v and('%.1f'):format(v)or'?'end
local function at(v)return v and('(%.1f, %.1f, %.1f)'):format(v.x,v.y,v.z)or'(?)'end
local function flat(a,c)
    if not(a and c)then return nil end
    return math.sqrt((a.x-c.x)^2+(a.y-c.y)^2)
end

local current          -- the Pelican handle of this proof
local requested_at     -- the requested position (the anchor)
local function on_event(e)
    if e.kind=='spawned'then
        local r=e.result
        mod:log(('PELICAN EXISTS: entity %d (network id %s): a transport Pelican, empty (cargo none, no cargo entity, no '
            ..'associated entity), its flight running; created at %s (%s m from the requested position); its anchor %s '
            ..'read back (%s m from it)'):format(r.entity,tostring(r.network),at(r.pelican and r.pelican.position or
            r.position),n1(flat(r.pelican and r.pelican.position or r.position,requested_at)),at(r.anchor_read),
            n1(flat(r.anchor_read,requested_at))))
    elseif e.kind=='stage'then
        mod:log(('PELICAN STAGE: entity %d: %s -> %s at %s s; target %s (%s m from the requested position '
            ..'horizontally); at %s'):format(e.entity,tostring(e.from),tostring(e.to),n1(e.seconds),at(e.target),
            n1(flat(e.target,requested_at)),at(e.position)))
    elseif e.kind=='hovering'then
        mod:log(('PELICAN HOVERING: entity %d at %s s; hover point %s, %s m from the requested position horizontally, '
            ..'%s m above it'):format(e.entity,n1(e.seconds),at(e.target),n1(flat(e.target,requested_at)),
            n1(e.target and requested_at and e.target.z-requested_at.z)))
    elseif e.kind=='released'then
        mod:log(('PELICAN RELEASED: entity %d in stage %d at %s s (released nothing); at %s'):format(e.entity,e.stage,
            n1(e.seconds),at(e.position)))
    elseif e.kind=='held'then
        local r=e.result
        mod:log(('PELICAN HELD: entity %d: departs %s s after its release (native %s s); verified %s'):format(e.entity,
            n1(r.seconds),n1((r.native-r.release)/1e6),tostring(r.verified)))
    elseif e.kind=='departing'then
        mod:log(('PELICAN DEPARTING: entity %d: stage %d, %s s after its release'):format(e.entity,e.stage,
            n1(e.after_release)))
    elseif e.kind=='gone'then
        mod:log(('PELICAN GONE: entity %d: %s s after it was spawned, %s s after its release, %s s after departing'):format(
            e.entity,n1(e.seconds),n1(e.after_release),n1(e.after_departing)))
        mod:log(('PELICAN SUMMARY: entity %d: spawned empty, hovered %s s after its release (asked %d), left and was '
            ..'removed by the game %s s later'):format(e.entity,n1(e.after_release and e.after_departing and
            e.after_release-e.after_departing),HOVER,n1(e.after_departing)))
    elseif e.kind=='refused'or e.kind=='unverified'or e.kind=='hold_refused'or e.kind=='cargo'then
        mod:log(('PELICAN %s: %s: %s'):format(e.kind:upper(),tostring(e.code or(e.result and'SPAWN_UNVERIFIED')
            or e.spawned),tostring(e.reason or'')))
    end
end

local function spawn()
    if current and current:alive()then
        mod:log('Ctrl+F8: a Pelican of this proof is still alive (entity '..tostring(current.entity)..'); one at a time')
        return
    end
    local state=hd2.game_state()
    if not(state and state.mission)then mod:log('Ctrl+F8: not in a mission');return end
    if state.host~=true then
        mod:log('Ctrl+F8: this machine is a CLIENT: only the host spawns (watch for "SEEN PELICAN" lines instead)')
        return
    end
    local me=hd2.local_player()
    local p=me and me:position()
    if not p then mod:log('Ctrl+F8: your position is unreadable (no avatar?)');return end
    requested_at={x=p.x+OFFSET,y=p.y,z=p.z}
    current=hd2.pelican.spawn({position=requested_at,hover=HOVER,on_event=on_event})
    local h=current
    mod:log(('Ctrl+F8 [%s]: requested to hover at %s (%d m east of you), hover %d s, %d player%s in the mission: status '
        ..'%s%s; created at %s'):format(BUILD,at(requested_at),OFFSET,HOVER,#hd2.players(),#hd2.players()==1 and''or's',
        h.status,h.code and(' '..h.code..': '..tostring(h.reason))or'',at(h.spawn_point)))
end

-- Every transport Pelican here, read-only, every second: first sighting, stage changes, release, removal.
local seen={}
local tick_count=0
local function observe()
    local world=world_module.open()
    local state=hd2.game_state()
    if not(world and state and state.mission)then
        if next(seen)then seen={}end
        return
    end
    tick_count=tick_count+1
    local list=pelicans.list(world)
    if not list then return end
    local role=state.host and'HOST'or'CLIENT'
    local now=pelicans.clock(world)
    for entity,p in pairs(list)do
        local s=seen[entity]
        if not s then
            s={first=now,stage=p.stage,released=p.released}
            seen[entity]=s
            mod:log(('SEEN PELICAN (%s): entity %d network id %s at %s; stage %s, released %s, cargo %s, associated %s; '
                ..'its anchor %s; a Runtime Pelican of this machine %s'):format(role,entity,tostring(p.network),
                at(p.position),tostring(p.stage),tostring(p.released),tostring(p.cargo or'none'),tostring(p.associated
                or'none'),at(pelicans.anchor(world,entity)),tostring(pelicans.owned(entity))))
        else
            if p.stage~=s.stage then
                mod:log(('SEEN PELICAN (%s): entity %d network id %s: stage %s -> %s, %s s after first seen; at %s; target %s')
                    :format(role,entity,tostring(p.network),tostring(s.stage),tostring(p.stage),n1(now and s.first and
                    (now-s.first)/1e6),at(p.position),at(p.target)))
                s.stage=p.stage
            end
            if p.released and not s.released then
                mod:log(('SEEN PELICAN (%s): entity %d network id %s RELEASED, %s s after first seen; at %s'):format(role,
                    entity,tostring(p.network),n1(now and s.first and(now-s.first)/1e6),at(p.position)))
            end
            s.released=p.released
            if tick_count%5==0 then
                mod:log(('SEEN PELICAN (%s): entity %d network id %s stage %s at %s'):format(role,entity,tostring(p.network),
                    tostring(p.stage),at(p.position)))
            end
        end
    end
    for entity,s in pairs(seen)do
        if not list[entity]then
            seen[entity]=nil
            mod:log(('SEEN PELICAN (%s): entity %d GONE, %s s after first seen'):format(role,entity,n1(now and s.first and
                (now-s.first)/1e6)))
        end
    end
end
hd2.every(1,observe)

hd2.every(5,function()
    if current and current:alive()and current.entity then
        local s=current:state()
        if s then
            mod:log(('PELICAN STATE: entity %d stage %s released %s cargo %s at %s (%s m from the requested position '
                ..'horizontally); its anchor %s; status %s'):format(s.entity,tostring(s.stage),tostring(s.released),
                tostring(s.cargo),at(s.position),n1(flat(s.position,requested_at)),at(s.anchor),current.status))
        end
    end
end)

hd2.input.bind('pelican_spawn_proof.spawn',{key='Ctrl+F8',on_press=spawn})
hd2.input.bind('pelican_spawn_proof.status',{key='Ctrl+F11',on_press=function()
    local s=current and current:state()
    local state=hd2.game_state()or{}
    mod:log(('Ctrl+F11 [%s]: %s; %s; Runtime Pelicans alive %d; Pelicans seen here %d; capability: %s'):format(BUILD,
        state.mission and(state.host and'HOST'or'CLIENT')or'not in a mission',current and('handle status '
        ..current.status..', entity '..tostring(current.entity)..(s and(', stage '..tostring(s.stage)..' at '
        ..at(s.position))or''))or'no Pelican requested',#hd2.pelican.active(),(function()local k=0;for _ in pairs(seen)do
        k=k+1 end;return k end)(),hd2.pelican.status().live))
end})
mod:log('loaded ('..BUILD..'): Ctrl+F8 spawn (host), Ctrl+F11 status; every Pelican here observed read-only')
