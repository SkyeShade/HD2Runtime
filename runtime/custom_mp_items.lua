-- Custom item PROVENANCE across machines (EXPERIMENTAL; docs/research/runtime-peer-messaging-F5FEE03DCFDB.md section
-- 14). A launcher a custom stratagem call delivered (the Gas EAT's two EAT-17s) is that custom stratagem's whoever
-- picks it up: its rocket's payload follows the exact launcher, never the player who fires it.
--
-- Live (2026-10-04): the projectile's impact explosion copy (+0x7C) is each machine's own. The caller converted its own
-- copy (376 -> 82); every other machine exploded its copy as 376 (research gas-eat section 6: the impact message
-- carries the override flag, not the type). And another player's shot from the caller's launcher was refused on the
-- caller's machine (NOT_LOCAL: its creditor is the wielder). So every compatible Runtime converts ITS OWN copy of a
-- tracked launcher's rocket, whoever fired it, as every machine's copy of a vanilla Orbital Gas Strike shell explodes
-- as 82 by its row:
--   * the caller publishes each call's delivered launchers by their NETWORK ids (the same on every machine; entity ids
--     are not) in its hd2rt value (runtime/custom_mp_sync.lua, items: custom id, the call's beacon network id, the
--     launchers' network ids). Nothing else: no address, no type to write, no value;
--   * every other machine accepts an entry only when: its sender is a compatible lobby member whose synced picks (the
--     mission's frozen snapshot) select that id; the id is registered here with a mirrored payload (a support delivery
--     whose weapons take an impact explosion); this machine saw that call's carrier beacon (its network id, the carrier
--     mapping to that id) and, when the thrown ball named its thrower, that thrower is the sender; the definition's
--     assets are resident here; each network id resolves through THIS machine's network id map to an entity of the
--     definition's own launcher type. The change it then makes is derived from its own registered definition (the
--     donor explosion, the rounds), never from the value;
--   * each accepted launcher is bound here like the caller's own (runtime/projectile_impact.lua, provenance: no
--     creditor gate): one guarded 4-byte write of this machine's own projectile copy, 376 -> 82, every other guard
--     unchanged. Nothing of another machine is ever written.
-- A launcher whose network id does not resolve yet (replication) is retried until M.WAIT; a launcher of another type is
-- refused. A member leaving forgets its launchers here; the mission's end forgets everything.
if rawget(_G,'jit')then jit.off(true,true)end
local world_module=require('hd2runtime/runtime/event_world')
local log_module=require('hd2runtime/runtime/log')
local P=require('hd2runtime/runtime/peer_protocol')
local provenance=require('hd2runtime/runtime/custom_provenance')
local M={}
M.WAIT=30            -- seconds an entry may wait for its beacon, its assets and its launchers' replication
M.FAST_SECONDS=45    -- seconds after a remote mirrored call's beacon during which the lobby is read fast
local function log(text)log_module.emit('[HD2Runtime] '..text)end

local own={}         -- this machine's own calls: {{id, call_id, beacon, items = {network ids}, entities = {entity ids}}}
local beacons={}     -- [beacon network id] = {id, entity, thrower (peer, from the ball) or nil, at}
local entries={}     -- [peer..'|'..beacon] = {peer, id, beacon, first, state, items = {[network] = item state}}
local tracked={}     -- [entity here] = {peer, id, beacon, network, binding}
local fast_until=-math.huge
local said={}
local function say(key,text)if said[key]~=text then said[key]=text;log(text)end end

function M.reset()
    for _,t in pairs(tracked)do
        if t.binding and t.binding.status=='active'then pcall(t.binding.cancel)end
    end
    own,beacons,entries,tracked,fast_until,said={},{},{},{},-math.huge,{}
    provenance.reset()
end
M.reset_for_tests=M.reset

-------------------------------------------------------------------------------------- this machine's own calls --
-- One of this machine's own calls delivered launchers with a mirrored payload: listed in its published state from now
-- on (the newest P.MAX_ITEM_CALLS calls). spec = {id, call_id, beacon (network id), items = {network ids}, entities =
-- {entity ids here}}. Returns true, or nil and why.
function M.own(spec)
    if type(spec)~='table'or not P.id_ok(spec.id)or type(spec.beacon)~='number'or type(spec.items)~='table'
        or#spec.items==0 then
        return nil,'a call needs its id, its beacon network id and its items\' network ids'
    end
    for _,n in ipairs(spec.items)do
        if type(n)~='number'or n<1 or n>P.MAX_NETWORK then return nil,'an item has no network id'end
    end
    local items,entities={},{}
    for k,n in ipairs(spec.items)do items[k]=n;entities[k]=spec.entities and spec.entities[k]end
    own[#own+1]={id=spec.id,call_id=spec.call_id,beacon=spec.beacon,items=items,entities=entities}
    while#own>P.MAX_ITEM_CALLS do table.remove(own,1)end
    -- Their provenance (runtime/custom_provenance.lua): this machine's own copies, realized by its own call.
    for k,n in ipairs(items)do
        local role=spec.roles and spec.roles[k]or'launcher'
        provenance.entity({network_id=n,custom_id=spec.id,call=spec.call_id,role=role,
            parent_network_id=spec.parents and spec.parents[k]or nil,entity=entities[k],realized=true})
    end
    return true
end
-- What this machine publishes now: its own calls whose launchers are not all gone here (newest last).
function M.published(world)
    for k=#own,1,-1 do
        local e=own[k]
        local alive=false
        for _,entity in ipairs(e.entities)do
            if entity==nil or world_module.entity_exists(world,entity)~=false then alive=true;break end
        end
        if not alive then table.remove(own,k)end
    end
    local out={}
    for k,e in ipairs(own)do
        local items={}
        for j,n in ipairs(e.items)do items[j]=n end
        out[k]={id=e.id,beacon=e.beacon,items=items}
    end
    return out
end

----------------------------------------------------------------------------------------- other machines' calls --
-- Another machine's custom call seen here: its carrier beacon (network id) and the custom id its carrier maps to.
-- mirrored: the id has a mirrored payload (the lobby is then read fast for a while, for its items).
function M.remote_beacon(network,spec,now,mirrored)
    if type(network)~='number'then return end
    local b=beacons[network]or{}
    b.id,b.entity,b.at,b.position=spec.id,spec.entity,b.at or now,spec.position or b.position
    beacons[network]=b
    if mirrored then fast_until=math.max(fast_until,(now or 0)+M.FAST_SECONDS)end
end
-- The thrown ball named that call's thrower (runtime/call_ins.lua).
function M.thrower(network,peer)
    local b=type(network)=='number'and beacons[network]
    if b then b.thrower=peer end
end
-- Every other machine's call seen here: {{network, id, entity, thrower, position}} (copies).
function M.remote_beacons()
    local out={}
    for network,b in pairs(beacons)do
        out[#out+1]={network=network,id=b.id,entity=b.entity,thrower=b.thrower,position=b.position}
    end
    table.sort(out,function(a,c)return a.network<c.network end)
    return out
end
-- An entity this machine bound for another machine's call by itself (a native barrage it derived): tracked like a
-- published one (a member leaving, the mission's end forget it; a published network id naming it confirms it).
function M.track(entity,t)
    tracked[entity]=t
    if t and t.network then
        provenance.entity({network_id=t.network,custom_id=t.id,call=t.beacon,role=t.kind=='barrage'and'barrage'or'payload',
            entity=entity,realized=true})
    end
end
-- Another machine's call seen here by its beacon's network id: {id, entity, thrower} (copies), or nil.
function M.beacon_info(network)
    local b=type(network)=='number'and beacons[network]
    return b and{id=b.id,entity=b.entity,thrower=b.thrower}or nil
end
-- Whether the lobby should be read fast now (a remote mirrored call whose items may be arriving).
function M.fast(now)return now<fast_until end

local function fail(e,text)
    e.state='refused'
    local h=e.handler or{title='REMOTE CUSTOM ITEM',vanilla='its rockets explode as the vanilla rocket on this machine'}
    log(('%s REFUSED: peer %s, custom %s, call beacon network id %d: %s (nothing of it is mirrored here: %s)'):format(
        h.title,e.peer,e.id,e.beacon,text,h.vanilla))
end

-- One entry of a member's items: wait, refuse or bind each item. env: see M.step. The handler (env.handler(d), by the
-- definition's payload family) says what its network ids name and how this machine mirrors them:
--   {kind, title (log), noun(index), vanilla (what stays vanilla when refused), caller(e, beacon, view) -> the calling
--    peer or nil, why (a caller's own items: the sender; a host-executed call's: the thrower, sent by the host),
--    check(world, d, entity, entity type, index) -> info or nil, why, wait (true: not yet, retried),
--    bind(spec, t) -> binding or nil, code, reason, describe(d, binding) -> the success line's tail}.
local function try(world,e,env,now,v)
    local d=env.definition(e.id)
    local h=d and env.handler(d)
    if not h then return fail(e,'it is not a custom stratagem with a mirrored payload here')end
    e.handler=h
    local late=now-e.first>M.WAIT
    local b=beacons[e.beacon]
    if not b then
        if late then return fail(e,'no carrier beacon with that network id was seen here within '..M.WAIT..' s')end
        e.waiting='its beacon';return
    end
    if b.id~=e.id then return fail(e,('the beacon with that network id is a call of %s here'):format(tostring(b.id)))end
    local caller,cwhy=h.caller(e,b,v)
    if not caller then
        if cwhy=='wait'then
            if late then return fail(e,'the thrown ball never named that call\'s thrower within '..M.WAIT..' s')end
            e.waiting='its thrower';return
        end
        return fail(e,tostring(cwhy))
    end
    e.caller=caller
    local picks=env.table and env.table[caller]
    local selected=false
    for slot=0,P.SLOTS-1 do if picks and picks[slot]==e.id then selected=true end end
    if not selected then
        return fail(e,(caller==e.peer and'that player\'s'or('its caller '..caller..'\'s'))..' synced picks (frozen at the '
            ..'mission start) do not select it')
    end
    local ready,why=env.assets(e.id)
    if ready==false then return fail(e,'its assets are not resident here: '..tostring(why))end
    if ready~=true then
        if late then return fail(e,'its assets were not resident within '..M.WAIT..' s')end
        e.waiting='its assets';return
    end
    local pending=false
    for index,n in ipairs(e.order)do
        local it=e.items[n]
        if it.state=='pending'then
            local noun=h.noun(index)
            local entity=world_module.network_entity(world,n)
            local kind=entity and world_module.entity_type(world,entity)
            local info,iwhy,wait
            if entity then info,iwhy,wait=h.check(world,d,entity,kind,index)end
            if not entity or(not info and wait)then
                if late then
                    it.state='refused'
                    log(('%s REFUSED: peer %s, custom %s, %s network id %d: %s within %d s'):format(h.title,e.peer,e.id,noun,
                        n,not entity and'it never resolved through this machine\'s network id map'or tostring(iwhy),M.WAIT))
                else pending=true end
            elseif not info then
                it.state='refused'
                log(('%s REFUSED: peer %s, custom %s, %s network id %d: it names entity %d of type %s here, %s (nothing '
                    ..'bound)'):format(h.title,e.peer,e.id,noun,n,entity,tostring(kind),tostring(iwhy)))
            elseif tracked[entity]and tracked[entity].peer==e.peer and tracked[entity].id==e.id then
                it.state='confirmed'
                log(('%s CONFIRMED: peer %s, custom %s, %s network id %d (entity %d on this machine), call beacon network id '
                    ..'%d: the caller\'s published network id names the one this machine derived itself'):format(h.title,
                    e.peer,e.id,noun,n,entity,e.beacon))
            elseif tracked[entity]then
                it.state='refused'
                log(('%s REFUSED: peer %s, custom %s, %s network id %d: entity %d is tracked already (%s\'s)'):format(
                    h.title,e.peer,e.id,noun,n,entity,tracked[entity].peer))
            else
                local t={peer=e.peer,caller=caller,id=e.id,beacon=e.beacon,network=n,entity=entity,kind=h.kind}
                local binding,code,reason=h.bind({entity=entity,entity_type=kind,info=info,index=index,network=n,
                    peer=e.peer,caller=caller,id=e.id,beacon=e.beacon,definition=d,networks=e.order},t)
                if binding then
                    it.state,it.entity='bound',entity
                    t.binding=binding
                    tracked[entity]=t
                    local role=h.kind=='pelican'and(index==1 and'vehicle'or'turret')or h.kind
                    provenance.entity({network_id=n,custom_id=e.id,call=e.beacon,role=provenance.ROLES[role]and role
                        or'payload',parent_network_id=h.kind=='pelican'and index>1 and e.order[1]or nil,entity=entity,
                        realized=true})
                    log(('%s: peer %s, custom %s, %s network id %d (entity %d on this machine), call beacon network id %d%s: '
                        ..'%s'):format(h.title,e.peer,e.id,noun,n,entity,e.beacon,caller~=e.peer and(' (the call of '..caller
                        ..')')or'',h.describe(d,binding,index)))
                else
                    it.state='refused'
                    log(('%s REFUSED: peer %s, custom %s, %s network id %d (entity %d here): %s: %s'):format(h.title,e.peer,
                        e.id,noun,n,entity,tostring(code),tostring(reason)))
                end
            end
        end
    end
    if pending then e.waiting='its '..h.noun(1)..'s\' replication';return end
    e.state='done'
end

-- Every Runtime step of a mission with custom multiplayer running. v: the current synced view (custom_mp_sync); env =
-- {table (the frozen synced table: peer -> slot -> id), definition(id) -> d, handler(d) -> the payload family's
-- handler (see try) or nil (not mirrored), assets(id) -> true | false, why | nil (loading)}.
function M.step(world,v,env,now)
    if not(v and v.members)then return end
    local present={}
    for _,peer in ipairs(v.members)do present[peer]=true end
    -- A member that left: its launchers are forgotten here.
    local gone={}
    for key,e in pairs(entries)do if not present[e.peer]then gone[e.peer]=true;entries[key]=nil end end
    for peer in pairs(gone)do
        local n,noun=0,'launcher'
        for entity,t in pairs(tracked)do
            if t.peer==peer then
                n=n+1
                if t.kind~='launcher'then noun='item'end
                if t.binding and t.binding.status=='active'then pcall(t.binding.cancel)end
                tracked[entity]=nil
            end
        end
        log(('REMOTE CUSTOM ITEM: peer %s left the lobby: its %d tracked %s%s forgotten on this machine'):format(peer,n,
            noun,n==1 and''or's'))
    end
    for peer,q in pairs(v.peers or{})do
        if present[peer]and q.state=='compatible'then
            for _,item in ipairs(q.items or{})do
                local key=peer..'|'..item.beacon
                if not entries[key]then
                    local e={peer=peer,id=item.id,beacon=item.beacon,first=now,state='pending',items={},order={}}
                    for _,n in ipairs(item.items)do
                        if not e.items[n]then e.items[n]={state='pending'};e.order[#e.order+1]=n end
                    end
                    entries[key]=e
                end
            end
        end
    end
    for _,e in pairs(entries)do
        if e.state=='pending'then
            local ok,why=pcall(try,world,e,env,now,v)
            if not ok then fail(e,'its correlation failed: '..tostring(why))end
            if e.state=='pending'then
                say('wait '..e.peer..'|'..e.beacon,('%s: peer %s, custom %s, call beacon network id %d: waiting for %s')
                    :format(e.handler and e.handler.title or'REMOTE CUSTOM ITEM',e.peer,e.id,e.beacon,tostring(e.waiting)))
            end
        end
    end
end
-- A tracked launcher's binding ended (fired, gone): it stays known (a tracked entity is never bound twice).
function M.tracked(entity)return tracked[entity]end
-- {entries = {{peer, id, beacon, state}}, tracked = {{entity, peer, id, network}}} (diagnostics and tests).
function M.status()
    local out={entries={},tracked={},own=#own}
    for _,e in pairs(entries)do out.entries[#out.entries+1]={peer=e.peer,id=e.id,beacon=e.beacon,state=e.state}end
    for entity,t in pairs(tracked)do
        out.tracked[#out.tracked+1]={entity=entity,peer=t.peer,id=t.id,network=t.network,beacon=t.beacon}
    end
    table.sort(out.tracked,function(a,c)return a.network<c.network end)
    return out
end
return M
