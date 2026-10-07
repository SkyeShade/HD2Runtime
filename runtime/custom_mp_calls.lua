-- Calls a client asks the SESSION HOST to run (EXPERIMENTAL; research/docs/runtime-peer-messaging-F5FEE03DCFDB.md
-- section 15). For payloads only the host can create for everyone (the Pelican CAS: a Runtime-spawned Pelican is
-- created through the host's spawn request; a client's would exist on that client only).
--
-- The CALLER keeps everything that is its own: its slot (converted to the agreed carrier), its cooldown, its beacon
-- (thrown by it, neutralized by it: delivery 'none'). At its beacon's activation it PUBLISHES a request, semantic state
-- only (runtime/peer_protocol.lua calls: custom id, the beacon's network id, the call's sequence number, the loadout
-- slot, the carrier map hash); never a gun configuration, a projectile, a rate, an address or a write.
--
-- The HOST runs a request once, only when every check holds:
--   * the sender is a compatible lobby member and the definition (registered here) is a host-executed family;
--   * the sender's synced picks (the mission's frozen snapshot) hold that id in that slot;
--   * its carrier map hash is the host's;
--   * its sequence is new for that sender (a repeated or older one is ignored), and no call ran for that beacon yet;
--   * this machine OBSERVED that call natively (runtime/custom_mp_evidence.lua, cached by the beacon's network id for
--     45 s: the beacon or the thrown ball need not still exist when the slower request arrives): its carrier maps to that
--     id in the frozen carrier map, its caller is the SENDER (the thrown ball's thrower, else derived from the frozen
--     table: the only other player selecting that id) and, when the ball named it, its loadout slot is the request's
--     (waited for up to M.WAIT).
-- Then the orchestrator runs the call on the host for that caller (runtime/custom_stratagems.lua host_call): its
-- context names the remote player as the caller.
local log_module=require('hd2runtime/runtime/log')
local P=require('hd2runtime/runtime/peer_protocol')
local M={}
M.WAIT=20             -- seconds the host waits for a request's beacon and thrower
M.KEEP=45             -- seconds a caller keeps a request published (the host has run it or refused it by then)
local function log(text)log_module.emit('[HD2Runtime] '..text)end

local own={}          -- this machine's requests: {id, beacon, seq, slot, carrier, at}
local next_seq=0
local handled={}      -- host: [peer] = the highest seq run or refused
local waiting={}      -- host: [peer..'#'..seq] = {first}
local ran={}          -- host: [beacon network id] = {peer, seq} (one host call per beacon)
local said={}
local function say(key,text)if said[key]~=text then said[key]=text;log(text)end end
function M.reset()own,handled,waiting,ran,said={},{},{},{},{};if M.reset_decided then M.reset_decided()end end
M.reset_for_tests=function()M.reset();next_seq=0 end

-------------------------------------------------------------------------------------------------- the caller --
-- This machine asks the host to run one of its calls. spec = {id, beacon (network id), slot, carrier (hash)}. Returns
-- the request ({id, beacon, seq, slot, carrier}), or nil and why.
function M.request(spec,now)
    if type(spec)~='table'or not P.id_ok(spec.id)or type(spec.beacon)~='number'or spec.beacon<1
        or spec.beacon>P.MAX_NETWORK or type(spec.slot)~='number'or spec.slot<0 or spec.slot>=P.SLOTS
        or type(spec.carrier)~='string'then
        return nil,'a request needs its id, its beacon\'s network id, its loadout slot and the carrier map hash'
    end
    next_seq=next_seq+1
    local r={id=spec.id,beacon=spec.beacon,seq=next_seq,slot=spec.slot,carrier=spec.carrier,at=now}
    own[#own+1]=r
    while#own>P.MAX_CALLS do table.remove(own,1)end
    return r
end
-- What this machine publishes now: its requests younger than M.KEEP s (newest last).
function M.published(now)
    for k=#own,1,-1 do if now-own[k].at>M.KEEP then table.remove(own,k)end end
    local out={}
    for k,r in ipairs(own)do out[k]={id=r.id,beacon=r.beacon,seq=r.seq,slot=r.slot,carrier=r.carrier}end
    return out
end

------------------------------------------------------------------------------------------------------ the host --
-- Every Runtime step on the session host with custom multiplayer running. v: the current synced view; env = {table (the
-- frozen synced table), carrier (this host's carrier map hash), definition(id) -> d, host_runs(d) -> bool, beacon(network)
-- -> the call's native evidence {id, entity, position, thrower, how ('ball' | 'derived'), slot, age} or nil, why
-- (runtime/custom_stratagems.lua call_evidence), run(request, peer, evidence) -> true or nil, why}.
--
-- Each request is a small state machine, every step logged (live r5: a client's request was published and nothing on
-- the host said why no Pelican came): RECEIVED (once), then SEQUENCE, PICK, CARRIER, EVIDENCE and BEACON CHECK (each
-- pass or fail logged once; EVIDENCE may wait up to M.WAIT), then ACCEPTED or one precise REFUSED. A request already
-- decided stays published by its sender for a while: it is not logged again. A request never decided whose sequence is
-- not newer than one already handled is refused once (stale or replayed). The custom identity is the OBSERVED beacon's
-- carrier through the frozen carrier map (the evidence), never only the request's id string.
local decided={}      -- host: [peer..'#'..seq] = 'accepted' | 'refused'
local function title(d)return(d and d.kind=='pelican')and'PELICAN REQUEST'or'HOST CALL REQUEST'end
local function evidence_step(r,peer,key,tag,head,w,env,now,picks,step,refuse)
    local b,bwhy=env.beacon(r.beacon)
    if not(b and b.thrower)then
        if now-w.first>M.WAIT then
            return refuse('EVIDENCE',b and('no caller was established for that beacon: '..tostring(bwhy))
                or('no carrier beacon or thrown ball with that network id was observed here in the last 45 s'
                ..(bwhy and(' ('..tostring(bwhy)..')')or'')))
        end
        say('wait '..key,head..': waiting for '..(b and'its caller'or'its beacon or thrown ball')
            ..' (this machine\'s own observation)')
        say(key..' EVIDENCE wait',('%s: EVIDENCE CHECK waiting (%s; up to %d s)'):format(tag,
            b and'its beacon was observed, its caller not yet'or tostring(bwhy),M.WAIT))
        return
    end
    if b.id~=r.id then
        return refuse('EVIDENCE',('its observed beacon\'s carrier maps to %s here (the frozen carrier map), not %s')
            :format(tostring(b.id),r.id))
    end
    if b.thrower~=peer then
        return refuse('EVIDENCE',('its observed caller is %s (%s), not the sender'):format(b.thrower,tostring(b.how)))
    end
    step('EVIDENCE',true,('observed %.1f s ago: its carrier maps to %s, its caller is the sender (%s)'):format(b.age or 0,
        r.id,b.how=='derived'and'derived from the frozen table'or'the thrown ball'))
    if ran[r.beacon]then
        return refuse('BEACON',('a call already ran for that beacon (peer %s, call seq %d): one host call per beacon')
            :format(ran[r.beacon].peer,ran[r.beacon].seq))
    end
    if b.slot~=nil and b.slot~=r.slot and not(picks and picks[b.slot]==r.id)then
        -- (Another slot of the same custom id is the same call's: a request may name its first slot.)
        return refuse('BEACON',('the thrown ball says loadout slot %d (%s there), not %d'):format(b.slot,
            tostring(picks and picks[b.slot]),r.slot))
    end
    step('BEACON',true,('no call ran for beacon network id %d yet%s'):format(r.beacon,
        b.slot~=nil and(', the thrown ball\'s slot '..b.slot)or''))
    handled[peer]=math.max(handled[peer]or 0,r.seq)
    waiting[key]=nil
    decided[key]='accepted'
    ran[r.beacon]={peer=peer,seq=r.seq}
    log(head..(': ACCEPTED (its synced slot, the carrier map hash, a new sequence and this machine\'s own observation '
        ..'agree: the beacon\'s carrier maps to %s, its caller is the sender (%s)%s, observed %.1f s ago); the host runs it '
        ..'for that player'):format(r.id,b.how=='derived'and'derived from the frozen table: the only other player '
        ..'selecting it'or'the thrown ball',b.slot~=nil and(', loadout slot '..b.slot)or'',b.age or 0))
    local ok,why=env.run(r,peer,b)
    if not ok then log(head..': the host could not run it: '..tostring(why))end
end
function M.host_step(world,v,env,now)
    if not(v and v.is_host and v.peers)then return end
    for peer,q in pairs(v.peers)do
        if q.state=='compatible'then
            for _,r in ipairs(q.calls or{})do
                local key=peer..'#'..r.seq
                if not decided[key]then
                    local d=env.definition(r.id)
                    local name=title(d)
                    local tag=('%s %s#%d'):format(name,peer,r.seq)
                    local head=('CUSTOM MP CALL REQUEST: peer %s asks the host to run custom %s (call seq %d, loadout slot '
                        ..'%d, beacon network id %d)'):format(peer,r.id,r.seq,r.slot,r.beacon)
                    local w=waiting[key]
                    if not w then
                        w={first=now}
                        waiting[key]=w
                        log(('%s RECEIVED: sender peer %s, seq %d, slot %d, beacon network id %d, carrier hash %s, custom %s '
                            ..'(as named: its identity is checked against its beacon\'s carrier)'):format(name,peer,r.seq,
                            r.slot,r.beacon,tostring(r.carrier),r.id))
                    end
                    local function step(check,ok,text)
                        say(key..' '..check,('%s: %s CHECK %s (%s)'):format(tag,check,ok and'pass'or'FAIL',text))
                    end
                    local function refuse(check,why)
                        if check then step(check,false,why)end
                        if r.seq>(handled[peer]or 0)then handled[peer]=r.seq end
                        waiting[key]=nil
                        decided[key]='refused'
                        log(head..': REFUSED: '..why..' (nothing runs for it)')
                    end
                    local picks=env.table and env.table[peer]
                    if r.seq<=(handled[peer]or 0)then
                        refuse('SEQUENCE',('seq %d is not newer than seq %d already handled for that player: a stale or '
                            ..'replayed request'):format(r.seq,handled[peer]))
                    elseif not(d and env.host_runs(d))then
                        refuse(nil,'it is not a host-executed custom stratagem here')
                    else
                        step('SEQUENCE',true,('seq %d is new; last handled %d'):format(r.seq,handled[peer]or 0))
                        if not(picks and picks[r.slot]==r.id)then
                            refuse('PICK',('that player\'s synced loadout slot %d (frozen at the mission start) is not %s')
                                :format(r.slot,r.id))
                        else
                            step('PICK',true,('its frozen loadout slot %d holds %s'):format(r.slot,r.id))
                            if r.carrier~=env.carrier then
                                refuse('CARRIER',('its carrier map hash %s is not the host\'s %s'):format(r.carrier,
                                    tostring(env.carrier)))
                            else
                                step('CARRIER',true,'its carrier map hash is the host\'s '..tostring(env.carrier))
                                evidence_step(r,peer,key,tag,head,w,env,now,picks,step,refuse)
                            end
                        end
                    end
                end
            end
        end
    end
end
-- Host: the requests waiting for their evidence now (the lobby is then read fast).
function M.waiting()local n=0;for _ in pairs(waiting)do n=n+1 end;return n end
function M.reset_decided()decided={}end
function M.status()return {own=#own,handled=handled,ran=ran,decided=decided}end
return M
