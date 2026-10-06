-- Multiplayer diagnostics of custom stratagems (EXPERIMENTAL; read-only; docs/custom-stratagem-api.md, "Several
-- players"). Nothing here writes the game. Every line is logged when its text changes, never per frame.
--
-- What a machine can know of another player's custom stratagem, from the game's own replicated state only (no Runtime
-- networking; no message path is supported):
--   * aboard the ship, each lobby player's loadout as the loadout screen holds it (M.lobby): a custom slot holds the
--     TOKEN there, the same type a native pick of it has, so the custom id is not visible;
--   * in a mission, every peer's stratagem record (rpc_sync_stratagems: raw types). Its custom slots hold the token until
--     that player's own Runtime converts its slot to the carrier; the converted type reaches this machine only if the
--     game sends that record again afterwards (M.records_step reports it when it does);
--   * a converted carrier maps back to exactly one custom id through the deterministic lobby allocation (every peer
--     with the same mod set computes the same id -> carrier map), because no player natively selects a carrier;
--   * a beacon of a carrier type with no state here is another machine's call (its thrower's machine runs it): its
--     thrower is the one peer whose record holds that carrier, when the record has been synced (M.remote_beacon).
local world_module=require('hd2runtime/runtime/event_world')
local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
local loadout=require('hd2runtime/runtime/stratagem_loadout')
local log_module=require('hd2runtime/runtime/log')
local catalog=require('hd2runtime/domains/stratagem_authoring')
local M={}
M.PROTOCOL='custom-mp/1'          -- the diagnostic vocabulary and allocation rule this build reports

local said={}                     -- key -> the last text logged
local state                       -- this mission: first-seen record entries, reported changes
local function log(text)log_module.emit('[HD2Runtime] '..text)end
local function say(key,text)
    if said[key]==text then return false end
    said[key]=text
    log(text)
    return true
end
M.say=say

local names
local function name_of(world,kind)
    if not names then
        names={}
        for name,e in pairs(catalog.stratagems)do if e.root and e.root.id then names[e.root.id]=name end end
    end
    local id=kind and loadout.id_of(world,kind)
    return id and names[id]or('type '..tostring(kind))
end
M.name_of=name_of

function M.reset_mission()state={first={},reported={},beacons={}}end
M.reset_mission()
function M.reset_for_tests()said={};M.reset_mission()end

-- The peers this machine sees: players (the game's list) and stratagem records. Logged with several players only.
function M.peers(world,where)
    local players=world_module.players(world)or{}
    local records=slots.records(world)or{}
    if#players<=1 and#records<=1 then return #players end
    local game=world_module.game_state(world)
    local parts={}
    table.sort(players,function(a,c)return a.peer<c.peer end)
    local has_record={}
    for _,r in ipairs(records)do has_record[r.peer]=true end
    for _,p in ipairs(players)do
        parts[#parts+1]=p.peer..(p['local']and(' (you'..(game and game.host and', host'or', client')..')')or'')
            ..(has_record[p.peer]and''or' (no stratagem record here)')
    end
    say('peers',('CUSTOM MP PEERS (%s): %d players, %d stratagem records: %s'):format(where,#players,#records,
        table.concat(parts,', ')))
    return #players
end

-- Aboard the ship: every lobby player's slots as the loadout screen holds them (stratagem_selector.lobby_records).
function M.lobby(world,token_type)
    local list=require('hd2runtime/runtime/stratagem_selector').lobby_records(world)
    if not list or#list<=1 then return end
    local parts={}
    for _,r in ipairs(list)do
        local slots_text={}
        for k,kind in ipairs(r.types)do
            slots_text[#slots_text+1]=('slot %d = %s%s'):format(k-1,name_of(world,kind),kind==token_type and' (the token)'
                or'')
        end
        parts[#parts+1]=('player %d (%s%s): %s'):format(r.index,r.owner,r['local']and', you'or'',
            #slots_text>0 and table.concat(slots_text,', ')or'no slots')
    end
    say('lobby','CUSTOM MP LOBBY (the loadout screen, read-only): '..table.concat(parts,'; ')..'. A custom slot holds '
        ..'the token here: its custom id is not visible to other players')
end

-- The id -> carrier map of an allocation (every registered id), with several players.
function M.carriers(a,players,where)
    if not(a and players and players>1)then return end
    local parts={}
    for _,id in ipairs(a.order or{})do
        local x=a.assignments[id]
        parts[#parts+1]=id..' = '..(x and(x.carrier..(x.local_refused and' (NOT OWNED here)'or''))
            or('REFUSED: '..tostring(a.refused[id])))
    end
    say('carriers',('CUSTOM MP CARRIERS (%s; rule %s: every registered id by (fewest eligible, id), candidates by '
        ..'(family preference, red ping, class, stable id), lobby-wide native picks skipped, one carrier per id): %s')
        :format(where,M.PROTOCOL,#parts>0 and table.concat(parts,', ')or'none'))
end
-- {[carrier type] = custom id} of an allocation.
function M.carrier_types(a)
    local out={}
    for id,x in pairs(a and a.assignments or{})do if x.type then out[x.type]=id end end
    return out
end

-- In a mission, from its first update: every peer record entry as FIRST seen (before any player's Runtime converts
-- its slot). A token found later as another type is a conversion (that player's Runtime wrote it, the game synced it):
-- never a native pick.
function M.first_seen(world)
    local records=slots.records(world)
    if not records then return end
    for _,r in ipairs(records)do
        local f=state.first[r.peer]
        if not f then f={entries={},['local']=r['local']};state.first[r.peer]=f end
        for _,e in ipairs(r.entries)do
            if f.entries[e.index]==nil then f.entries[e.index]={type=e.type,granted=e.granted}end
        end
    end
end
-- Every peer record as first seen in this mission: {{peer, local, entries = {{index, type, granted}}}} (the input of
-- runtime/custom_mp_sync.lua native_present: the same on every machine once every record arrived).
function M.first_records()
    local out={}
    for peer,f in pairs(state.first)do
        local entries={}
        for index,e in pairs(f.entries)do entries[#entries+1]={index=index,type=e.type,granted=e.granted}end
        out[#out+1]={peer=peer,['local']=f['local'],entries=entries}
    end
    table.sort(out,function(a,c)return a.peer<c.peer end)
    return out
end
-- The lobby-wide native selections: this machine's saved loadout, every peer record entry as first seen, and every
-- live entry except a token turned into another type since (a converted custom slot). A record the game rebuilt
-- (another type at an index first seen with a default) counts both. {present = set of stable ids, peers = {hex},
-- changed = {text}, converted = {text}}.
function M.native(world,saved,token_type)
    M.first_seen(world)
    local present,peers,changed,converted={},{},{},{}
    local function add(kind)
        local id=loadout.id_of(world,kind)
        if id then present[id]=true end
    end
    for id in pairs(saved or{})do present[id]=true end
    local live={}
    for _,r in ipairs(slots.records(world)or{})do
        live[r.peer]={}
        for _,e in ipairs(r.entries)do live[r.peer][e.index]=e.type end
    end
    local keys={}
    for peer in pairs(state.first)do keys[#keys+1]=peer end
    table.sort(keys)
    for _,peer in ipairs(keys)do
        peers[#peers+1]=peer
        local indices={}
        for index in pairs(state.first[peer].entries)do indices[#indices+1]=index end
        table.sort(indices)
        for _,index in ipairs(indices)do
            local first=state.first[peer].entries[index].type
            add(first)
            local now=live[peer]and live[peer][index]
            if now and now~=first then
                local text=('peer %s entry %d: %s first, %s now'):format(peer,index,name_of(world,first),name_of(world,now))
                -- Another machine's converted custom slot (this machine converts its own only after the allocation:
                -- a change in its own record before it is a rebuild).
                if token_type and first==token_type and not state.first[peer]['local']then
                    converted[#converted+1]=text      -- a converted custom slot: not a native pick
                else
                    changed[#changed+1]=text
                    add(now)
                end
            end
        end
        for index,now in pairs(live[peer]or{})do
            if state.first[peer].entries[index]==nil then add(now)end
        end
    end
    return {present=present,peers=peers,changed=changed,converted=converted}
end

-- The loadout slots of a record (its non-granted entries, in order): {{slot, index, type}}.
local function picks_of(entries)
    local out={}
    local list={}
    for index,e in pairs(entries)do list[#list+1]={index=index,type=e.type,granted=e.granted}end
    table.sort(list,function(a,c)return a.index<c.index end)
    for _,e in ipairs(list)do if e.granted==0 then out[#out+1]={slot=#out,index=e.index,type=e.type}end end
    return out
end

-- Every player's custom picks this machine knows: its own (the virtual slots) and, for the others, what their records
-- show (the token: custom or native, not distinguishable; a carrier: reconstructed).
function M.picks(world,local_slots,token_type,carrier_types,ids_by_slot)
    local lo,hi=world_module.local_peer(world)
    local me=lo and world_module.peer_hex(lo,hi)
    local parts={}
    local keys={}
    for peer in pairs(state.first)do keys[#keys+1]=peer end
    table.sort(keys)
    for _,peer in ipairs(keys)do
        if peer==me then
            local own={}
            for slot,id in pairs(ids_by_slot or{})do own[#own+1]={slot=slot,id=id}end
            table.sort(own,function(a,c)return a.slot<c.slot end)
            for _,o in ipairs(own)do parts[#parts+1]=('%s (you) slot %d = %s'):format(peer,o.slot,o.id)end
        else
            local live={}
            for _,r in ipairs(slots.records(world)or{})do
                if r.peer==peer then for _,e in ipairs(r.entries)do live[e.index]=e end end
            end
            for _,p in ipairs(picks_of(state.first[peer].entries))do
                local now=live[p.index]and live[p.index].type or p.type
                if carrier_types[now]then
                    parts[#parts+1]=('%s slot %d = %s (reconstructed: its record holds the carrier %s)'):format(peer,p.slot,
                        carrier_types[now],name_of(world,now))
                elseif now==token_type then
                    parts[#parts+1]=('%s slot %d = %s (the token: a custom stratagem or a native pick, not '
                        ..'distinguishable from replicated state)'):format(peer,p.slot,name_of(world,now))
                end
            end
        end
    end
    say('picks','CUSTOM MP PICKS: '..(#parts>0 and table.concat(parts,'; ')or'none'))
end

-- Every update of a multiplayer mission: each peer record entry whose type changed since first seen. A token turned
-- into a carrier this machine maps to a custom id is that player's pick, reconstructed; into any other type, a DESYNC
-- (the peers' maps or mod sets differ). Returns the reconstructed {[peer] = {[entry index] = id}}.
function M.records_step(world,token_type,carrier_types)
    M.first_seen(world)
    local out={}
    for _,r in ipairs(slots.records(world)or{})do
        local f=state.first[r.peer]
        if f and not r['local']then
            for _,e in ipairs(r.entries)do
                local first=f.entries[e.index]
                if first and first.type~=e.type then
                    local key=r.peer..':'..e.index..':'..e.type
                    local id=carrier_types[e.type]
                    if id and first.type==token_type then
                        out[r.peer]=out[r.peer]or{}
                        out[r.peer][e.index]=id
                        if not state.reported[key]then
                            state.reported[key]=true
                            log(('CUSTOM MP PICKS: peer %s record entry %d %s -> %s: that player\'s %s (reconstructed from '
                                ..'its synced record: its Runtime converted the slot and the game sent the record again)')
                                :format(r.peer,e.index,name_of(world,first.type),name_of(world,e.type),id))
                        end
                    elseif first.type==token_type then
                        if not state.reported[key]then
                            state.reported[key]=true
                            local mine={}
                            for t,cid in pairs(carrier_types)do mine[#mine+1]=cid..' = '..name_of(world,t)end
                            table.sort(mine)
                            log(('CUSTOM MP DESYNC: peer %s converted record entry %d %s -> %s, which this machine maps to '
                                ..'no custom stratagem (this machine: %s). Its mod set, Runtime build or lobby view differs '
                                ..'from this machine\'s'):format(r.peer,e.index,name_of(world,first.type),
                                name_of(world,e.type),#mine>0 and table.concat(mine,', ')or'no carriers'))
                        end
                    elseif carrier_types[first.type]and e.type==token_type then
                        if not state.reported[key]then
                            state.reported[key]=true
                            log(('CUSTOM MP PICKS: peer %s record entry %d returned to the token (%s -> %s)'):format(r.peer,
                                e.index,name_of(world,first.type),name_of(world,e.type)))
                        end
                    elseif not state.reported[key]then
                        state.reported[key]=true
                        log(('CUSTOM MP RECORD: peer %s record entry %d %s -> %s (not a custom slot conversion)'):format(
                            r.peer,e.index,name_of(world,first.type),name_of(world,e.type)))
                    end
                end
            end
        end
    end
    return out
end

-- A beacon of a carrier type with no state here: another machine's call. Its thrower is the one remote peer whose
-- record holds that carrier now (when its converted record was synced). Logged once per beacon.
function M.remote_beacon(world,beacon,carrier_types)
    local id=carrier_types[beacon.type]
    if not id or state.beacons[beacon.entity]then return nil end
    state.beacons[beacon.entity]=true
    local holders={}
    for _,r in ipairs(slots.records(world)or{})do
        if not r['local']then
            for _,e in ipairs(r.entries)do if e.type==beacon.type then holders[#holders+1]=r.peer;break end end
        end
    end
    local thrower=#holders==1 and holders[1]
        or(#holders==0 and'unknown (no remote record holds the carrier: its conversion was not synced)'
        or('unknown (%d remote records hold the carrier: %s)'):format(#holders,table.concat(holders,', ')))
    log(('CUSTOM MP CALL: peer %s, custom %s (carrier %s), beacon %d: another machine\'s call (no state here): its '
        ..'thrower\'s Runtime runs it; nothing of it runs here'):format(thrower,id,name_of(world,beacon.type),beacon.entity))
    return {id=id,thrower=#holders==1 and holders[1]or nil}
end

-- This machine's own call.
function M.local_call(world,ctx)
    local game=world_module.game_state(world)
    log(('CUSTOM MP CALL: peer %s (you, %s), custom %s, call %s%s, beacon %s'):format(tostring(ctx.player_peer),
        game and game.host and'host'or'client',ctx.definition,ctx.call_id,ctx.slot and(', slot '..ctx.slot)or'',
        tostring(ctx.beacon and ctx.beacon.entity)))
end
return M
