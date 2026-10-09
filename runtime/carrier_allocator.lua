-- Carrier allocation for several custom stratagems (development; research/docs/pelican-cas-F5FEE03DCFDB.md, "Carrier
-- allocation"). Read-only: it chooses, it writes nothing.
--
-- Each custom stratagem borrows one vanilla carrier for its identity. Two custom stratagems must never share one:
-- a carrier has a single presentation and a single delivery per mission. M.allocate runs the Runtime's carrier
-- discovery (stratagem_slot_conversion.discover_carriers: owned, selectable, enabled, unlimited uses, not in the saved
-- loadout, never a mission type, vehicle or Eagle, a known call-in package, a reviewed presentation, a native code; the
-- definition's exclusions; with `payload`, payload-compatible with its donor) once per definition, IN THE GIVEN ORDER
-- (the most constrained first).
--
-- Two separate properties of a carrier (never one for the other):
--   * its delivery FAMILY (the catalogue: orbital, eagle, sentry, support, backpack, mine, emplacement, ...) and its
--     call-in class;
--   * its BEACON CATEGORY: the colour of the beam the game draws for its thrown beacon, the row's +0xD4 (research
--     "beaconPresentation": 1 red = offensive, 2 blue = support, 3 yellow = other). The ping colour (+0xB8) is a separate
--     member, reported alongside. An orbital is not necessarily red: the Orbital EMS Strike's beam is blue.
--
-- Choosing:
--   * a definition with `payload` takes the discovery's own choice, ranked exactly as its proof ranks it (so the
--     allocation names the carrier that proof uses);
--   * a definition with `beacon = 'offensive'` takes only a RED-beam carrier, by its `tiers` in order (the Pelican CAS:
--     an orbital, then an Eagle, then any other red carrier), within a tier the red ping first, then the call-in
--     class, then the STABLE ID (never by name or type number). With no red carrier left its `fallback` decides,
--     explicitly: 'refuse' (refused, every candidate's reason logged), or {beacon = 'any'} (the first other eligible
--     carrier, marked fallback);
--   * any other definition takes, among its eligible candidates of the allowed families, the first by class then
--     stable id;
--   * a carrier already allocated is never taken again, and a definition with `reserve` reserves its whole eligible
--     set: a later definition never takes any of it, so a proof that caches and revalidates its own carrier can never
--     collide with this allocation whichever member it holds.
-- Eagles are offensive (red beams) but the discovery refuses them (limited uses, Eagle Rearm, and the slot conversion
-- and cooldown need unlimited uses): their tier is reported, never relaxed here.
-- The result is deterministic for one account, loadout and build.
local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
local M={}

local function look(c)
    return ('%s beam, %s ping'):format(tostring(c.beamColour),tostring(c.pingColour))
end
M.look=look

-- definitions: {{id, label, token, exclude = {names}, payload = {donor}, families = {catalogue families}, beacon =
-- 'offensive', tiers = {{family = name} | {any = true}}, fallback = 'refuse' | {beacon = 'any'}, reserve}}.
-- present: a set of stable ids (the saved loadout). Returns {ready, reason, assignments = {[id] = {label, carrier,
-- stable_id, type, class, family, beacon, beam, ping, tier, fallback, eligible, skipped}}, refused = {[id] = reason},
-- verdicts = {[id] = {[stable id] = text}}, order = {ids}, candidates = {[id] = discovery candidates}, line}.
function M.allocate(world,definitions,present)
    local out={ready=true,assignments={},refused={},verdicts={},order={},candidates={}}
    local taken,reserved={},{}
    for _,d in ipairs(definitions)do
        out.order[#out.order+1]=d.id
        local found=slots.discover_carriers(world,d.token,{present=present or{},exclude=d.exclude,payload=d.payload})
        if not found.ready then
            out.ready=false;out.reason=d.label..': '..tostring(found.reason)
            return out
        end
        out.candidates[d.id]=found.candidates
        local verdicts={}
        out.verdicts[d.id]=verdicts
        local allowed
        if d.families then allowed={};for _,f in ipairs(d.families)do allowed[f]=true end end
        local function busy(c)
            if taken[c.id]then return 'taken by '..tostring(taken[c.id])end
            if reserved[c.id]then return 'RESERVED by '..tostring(reserved[c.id])..' (never shared)'end
        end
        local chosen,skipped,pool,fallback=nil,0,{},false
        if d.beacon=='offensive'then
            -- Red beams only, by tier; the tier a candidate falls in (nil: none of the tiers).
            local function tier_of(c)
                for k,t in ipairs(d.tiers or{{any=true}})do
                    if t.any or t.family==c.family then return k end
                end
            end
            local red,other={},{}
            for _,c in ipairs(found.candidates)do
                c.tier=tier_of(c)
                if not c.eligible then
                    verdicts[c.id]='rejected: '..table.concat(c.reasons,'; ')
                elseif c.beaconCategory~='offensive'then
                    verdicts[c.id]=('not offensive: a %s beacon (%s)'):format(c.beaconCategory,look(c))
                    other[#other+1]=c
                elseif not c.tier then
                    verdicts[c.id]='red, but in no tier of '..d.label
                else
                    red[#red+1]=c
                end
            end
            local function rank(a,c)
                if a.tier~=c.tier then return a.tier<c.tier end
                local pa,pc=a.pingColour=='red'and 0 or 1,c.pingColour=='red'and 0 or 1
                if pa~=pc then return pa<pc end
                local ra,rc=a.class or 9,c.class or 9
                if ra~=rc then return ra<rc end
                return a.id<c.id
            end
            table.sort(red,rank)
            pool=red
            for _,c in ipairs(red)do
                local why=busy(c)
                if why then skipped=skipped+1;verdicts[c.id]='red, but '..why
                elseif not chosen then chosen=c
                else verdicts[c.id]=('red (tier %d), ranked after the selected one'):format(c.tier)end
            end
            if not chosen and type(d.fallback)=='table'and d.fallback.beacon=='any'then
                table.sort(other,function(a,c)
                    local ra,rc=a.class or 9,c.class or 9
                    if ra~=rc then return ra<rc end
                    return a.id<c.id
                end)
                for _,c in ipairs(other)do
                    local why=busy(c)
                    if why then verdicts[c.id]=verdicts[c.id]..', '..why
                    elseif not chosen then chosen,fallback=c,true end
                end
            end
        else
            for _,c in ipairs(found.candidates)do
                if not c.eligible then verdicts[c.id]='rejected: '..table.concat(c.reasons,'; ')
                elseif allowed and not allowed[c.family]then verdicts[c.id]='not a '..table.concat(d.families,'/')
                else pool[#pool+1]=c end
            end
            if not d.payload then
                table.sort(pool,function(a,c)
                    local ra,rc=a.class or 9,c.class or 9
                    if ra~=rc then return ra<rc end
                    return a.id<c.id
                end)
            end
            for _,c in ipairs(pool)do
                local why=busy(c)
                if why then skipped=skipped+1;verdicts[c.id]=why
                elseif not chosen then chosen=c
                else verdicts[c.id]='eligible, ranked after the selected one'end
            end
        end
        if chosen then
            taken[chosen.id]=d.label
            verdicts[chosen.id]=fallback and'SELECTED (FALLBACK: not a red beacon)'or'SELECTED'
            out.assignments[d.id]={label=d.label,carrier=chosen.name,stable_id=chosen.id,type=chosen.type,
                class=chosen.class,family=chosen.family,beacon=chosen.beaconCategory,beam=chosen.beamColour,
                ping=chosen.pingColour,tier=chosen.tier,fallback=fallback,eligible=#pool,skipped=skipped}
        elseif d.beacon=='offensive'then
            out.refused[d.id]=('no unused red (offensive) carrier: %d red eligible%s, %d checked; fallback: %s'):format(
                #pool,skipped>0 and(', '..skipped..' taken or reserved by an earlier custom stratagem')or'',
                #found.candidates,type(d.fallback)=='table'and'no other eligible carrier either'or'refuse')
        else
            out.refused[d.id]=('no unused carrier: %d eligible%s, %d checked'):format(#pool,
                skipped>0 and(', '..skipped..' taken or reserved by an earlier custom stratagem')or'',#found.candidates)
        end
        if d.reserve then for _,c in ipairs(pool)do reserved[c.id]=reserved[c.id]or d.label end end
    end
    local parts={}
    for _,d in ipairs(definitions)do
        local a=out.assignments[d.id]
        parts[#parts+1]=d.label..' = '..(a and('%s (%s, %s beacon)'):format(a.carrier,tostring(a.family),tostring(a.beam))
            or('REFUSED ('..out.refused[d.id]..')'))
    end
    local distinct=true
    local seen={}
    for _,a in pairs(out.assignments)do
        if seen[a.stable_id]then distinct=false end
        seen[a.stable_id]=true
    end
    out.distinct=distinct
    out.line='CUSTOM CARRIER: '..table.concat(parts,', ')..'; distinct = '..tostring(distinct)
    return out
end

-- The two custom stratagems of this build, in allocation order: the Gas Barrage (payload-compatible with the 120mm,
-- exactly its proof's discovery; it reserves that set) and the Pelican CAS (an offensive custom stratagem: a RED beacon,
-- an orbital first, then an Eagle, then any other red carrier; never the 120mm or the Gas Strike, whose records the
-- Gas Barrage reads; no red carrier left: refused).
M.GAS_BARRAGE={id='orbital_gas_barrage',label='Gas Barrage',token='Orbital Precision Strike',
    exclude={'Orbital 120mm HE Barrage'},payload={donor='Orbital 120mm HE Barrage'},reserve=true}
M.PELICAN_CAS={id='pelican_close_air_support',label='Pelican CAS',token='Orbital Precision Strike',
    exclude={'Orbital 120mm HE Barrage','Orbital Gas Strike'},beacon='offensive',
    tiers={{family='orbital'},{family='eagle'},{any=true}},fallback='refuse'}
M.DEFINITIONS={M.GAS_BARRAGE,M.PELICAN_CAS}

------------------------------------------------------------------------------------------------- policies --
-- The carrier POLICY of a registered custom stratagem (runtime/custom_stratagems.lua): which carriers it may borrow.
--   beacon          'offensive' (a red beam, +0xD4 = 1), 'support' (blue, 2) or 'any': the beacon the player throws;
--   prefer_families catalogue families in order of preference (e.g. {'support', 'backpack'});
--   allow_families  the only families it may take (default: its preferred ones; any family when neither is given);
--   exclude         stratagem names never taken (with every custom stratagem's donors and deliveries: global_exclude).
-- The discovery's guards always hold (owned, selectable, enabled, unlimited uses, not in the loadout, never a mission
-- type, vehicle or Eagle, every call-in package known, a reviewed presentation, a native code). The one exception is a
-- custom EAGLE (definitions[k].eagle): its policy allows the 'eagle' family only, and its discovery takes Eagles only,
-- their limited uses accepted (the custom Eagle's slot gets its own uses per rearm: a fleet member of the record).
M.BEACONS={offensive=true,support=true,any=true}
-- A policy may also name a carrier GROUP (runtime/carrier_groups.lua: group, and slots for a pod group); its beacon is
-- then optional (the group's), and the group's fit with the payload is checked when the payload is known.
function M.check_policy(policy)
    if type(policy)~='table'then return nil,'carrier must be a table'end
    for key in pairs(policy)do
        if key~='beacon'and key~='prefer_families'and key~='allow_families'and key~='exclude'and key~='require_unlimited'
            and key~='group'and key~='slots'
        then return nil,'unsupported carrier option: '..tostring(key)end
    end
    if policy.group~=nil and not require('hd2runtime/runtime/carrier_groups').GROUPS[tostring(policy.group)]then
        return nil,'carrier.group must be one of '..table.concat(require('hd2runtime/runtime/carrier_groups').ORDER,', ')
    end
    if policy.slots~=nil and policy.group==nil then
        return nil,'carrier.slots needs carrier.group (a pod capacity: support_pod or expendable)'
    end
    if not(policy.group~=nil and policy.beacon==nil)and not M.BEACONS[policy.beacon or'']then
        return nil,"carrier.beacon must be 'offensive', 'support' or 'any'"
    end
    if policy.require_unlimited~=nil and policy.require_unlimited~=true then
        return nil,'carrier.require_unlimited can only be true (a carrier always has unlimited uses)'
    end
    for _,key in ipairs({'prefer_families','allow_families','exclude'})do
        local list=policy[key]
        if list~=nil then
            if type(list)~='table'or#list>32 then return nil,'carrier.'..key..' must be a list'end
            for _,v in ipairs(list)do if type(v)~='string'then return nil,'carrier.'..key..' lists names'end end
        end
    end
    return true
end
local function rank_index(list,value)
    for k,v in ipairs(list or{})do if v==value then return k end end
    return #(list or{})+1
end
-- Only the account's ownership stands between a candidate and eligibility (lobby mode ranks it anyway).
local function only_unowned(c)
    if c.eligible or not c.codes or#c.codes==0 then return false end
    for _,code in ipairs(c.codes)do if code~='not_owned'then return false end end
    return true
end
-- Allocates every definition's carrier: ONE carrier per custom stratagem ID (every slot and every player that selects
-- that id uses it; two ids never share one). definitions: {{id, label, token, policy}} (deduplicated by id; the input
-- order never matters); present: a set of stable ids natively selected (the loadout; in a lobby, every player's);
-- global_exclude: names no definition may take; opts.lobby: several players (see M.allocate_lobby). Deterministic for one
-- mod set, native selection and build: the most constrained definition (fewest eligible carriers) first, then by id;
-- within a definition by preferred family, then (offensive) the red ping, then the call-in class, then the stable id.
-- Returns {ready, reason, assignments = {[id] = {label, carrier, stable_id, type, class, family, beacon, beam, ping,
-- eligible, skipped, owned, local_refused}}, refused = {[id] = reason}, verdicts = {[id] = {[stable id] = text}},
-- candidates = {[id] = list}, order = {ids}, distinct, line}. opts.report: the ids the line names (default all).
-- d.pin (the carrier-in-slot probe, runtime/carrier_in_slot.lua: a stable id the definition's loadout slots already
-- hold): while that carrier is in its pool (eligible, never a native pick) the definition keeps it, ahead of every
-- unpinned definition; otherwise it is allocated as any other (its slot then moves to that carrier). Pinned
-- definitions are allocated first, by id.
-- d.selected == false (0.30.2): a custom stratagem nobody picked. It is allocated after every picked one and only
-- TENTATIVELY: it gets the first carrier no picked custom stratagem (and no native pick) holds, takes nothing from
-- another unpicked one, and reserves nothing (assignment.tentative; never in reservations). So a tile is unavailable
-- only when picking it now would leave it without a carrier, and picks never compete with registered-but-unpicked
-- definitions. nil counts as picked (the synced lobby table passes only picked ids).
function M.allocate_policies(world,definitions,present,global_exclude,opts)
    opts=opts or{}
    local out={ready=true,assignments={},refused={},verdicts={},candidates={},order={}}
    local pools,allowed_of={},{}
    local unique,seen_ids={},{}
    for _,d in ipairs(definitions)do
        if not seen_ids[d.id]then seen_ids[d.id]=true;unique[#unique+1]=d end
    end
    table.sort(unique,function(a,c)return a.id<c.id end)
    definitions=unique
    for _,d in ipairs(definitions)do
        local exclude={}
        for _,name in ipairs(global_exclude or{})do exclude[#exclude+1]=name end
        for _,name in ipairs(d.policy.exclude or{})do exclude[#exclude+1]=name end
        -- A custom Eagle (d.eagle) discovers in Eagle mode: only Eagles, their limited uses being its own.
        local found=slots.discover_carriers(world,d.token,{present=present or{},exclude=exclude,eagle=d.eagle==true})
        if not found.ready then
            out.ready=false;out.reason=d.label..': '..tostring(found.reason)
            return out
        end
        out.candidates[d.id]=found.candidates
        local verdicts={}
        out.verdicts[d.id]=verdicts
        local allowed=d.policy.allow_families or d.policy.prefer_families
        allowed_of[d.id]=allowed
        local allow={}
        for _,f in ipairs(allowed or{})do allow[f]=true end
        local pool={}
        for _,c in ipairs(found.candidates)do
            -- In a lobby every peer must rank alike whatever its account owns: ownership is checked after the choice.
            local eligible=c.eligible or(opts.lobby and only_unowned(c))
            -- A group's structural condition (d.filter: e.g. an exclusive pod rack of the capacity asked for): nil when
            -- the candidate fits, else why (definitions without a group have none).
            local unfit=eligible and d.filter and d.filter(c)
            if not eligible then verdicts[c.id]='rejected: '..table.concat(c.reasons,'; ')
            elseif d.policy.beacon~='any'and c.beaconCategory~=d.policy.beacon then
                verdicts[c.id]=('not %s: a%s %s beacon (%s)'):format(d.policy.beacon,
                    tostring(c.beaconCategory):match('^[aeiou]')and'n'or'',c.beaconCategory,look(c))
            elseif allowed and not allow[c.family]then
                verdicts[c.id]='not an allowed family ('..tostring(c.family)..')'
            elseif unfit then
                verdicts[c.id]='not in its group: '..tostring(unfit)
            else pool[#pool+1]=c end
        end
        local prefer=d.policy.prefer_families
        table.sort(pool,function(a,c)
            local fa,fc=rank_index(prefer,a.family),rank_index(prefer,c.family)
            if fa~=fc then return fa<fc end
            if d.policy.beacon=='offensive'then
                local pa,pc=a.pingColour=='red'and 0 or 1,c.pingColour=='red'and 0 or 1
                if pa~=pc then return pa<pc end
            end
            local ra,rc=a.class or 9,c.class or 9
            if ra~=rc then return ra<rc end
            return a.id<c.id
        end)
        pools[d.id]=pool
    end
    -- A pin counts only while its carrier is in the definition's pool.
    local pinned={}
    for _,d in ipairs(definitions)do
        if d.pin then
            for _,c in ipairs(pools[d.id])do if c.id==d.pin then pinned[d.id]=c end end
        end
    end
    local order={}
    for k,d in ipairs(definitions)do order[k]=d end
    table.sort(order,function(a,c)
        local pa,pc=pinned[a.id]and 0 or(a.selected==false and 2 or 1),pinned[c.id]and 0 or(c.selected==false and 2 or 1)
        if pa~=pc then return pa<pc end
        local na,nc=#pools[a.id],#pools[c.id]
        if na~=nc then return na<nc end
        return a.id<c.id
    end)
    local taken={}
    for _,d in ipairs(order)do
        out.order[#out.order+1]=d.id
        local verdicts,pool=out.verdicts[d.id],pools[d.id]
        local chosen,skipped=nil,0
        local pin=pinned[d.id]
        if pin and not taken[pin.id]then chosen=pin end
        for _,c in ipairs(pool)do
            if c==chosen then
            elseif taken[c.id]then skipped=skipped+1;verdicts[c.id]='taken by '..taken[c.id]..' (never shared)'
            elseif not chosen then chosen=c
            else verdicts[c.id]=chosen==pin and'eligible; its slot holds another carrier (kept)'
                or'eligible, ranked after the selected one'end
        end
        if chosen then
            local tentative=d.selected==false and not pin
            if not tentative then taken[chosen.id]=d.label end
            verdicts[chosen.id]=chosen==pin and'SELECTED (its loadout slot already holds it)'
                or tentative and'SELECTED (tentative: nobody picked it; reserves nothing)'or'SELECTED'
            local owned=chosen.eligible==true
            out.assignments[d.id]={label=d.label,carrier=chosen.name,stable_id=chosen.id,type=chosen.type,
                class=chosen.class,family=chosen.family,beacon=chosen.beaconCategory,beam=chosen.beamColour,
                ping=chosen.pingColour,eligible=#pool,skipped=skipped,owned=owned,pinned=chosen==pin or nil,
                tentative=tentative or nil,
                local_refused=not owned and('the lobby\'s carrier for it is '..chosen.name..', which this account does '
                    ..'not own: unavailable to this player (never remapped: every player must agree)')or nil}
        else
            local allowed=allowed_of[d.id]
            out.refused[d.id]=('no unused %scarrier%s: %d eligible%s, %d checked'):format(
                d.policy.beacon=='any'and''or(d.policy.beacon..' ('..(d.policy.beacon=='offensive'and'red'or'blue')
                ..' beacon) '),allowed and(' of the families '..table.concat(allowed,'/'))or'',#pool,
                skipped>0 and(', '..skipped..' taken by another custom stratagem')or'',#out.candidates[d.id])
        end
    end
    local parts,seen,distinct={},{},true
    for _,id in ipairs(out.order)do
        local a=out.assignments[id]
        if a and not a.tentative then
            if seen[a.stable_id]then distinct=false end
            seen[a.stable_id]=true
        end
    end
    for _,d in ipairs(definitions)do
        if not opts.report or opts.report[d.id]then
            local a=out.assignments[d.id]
            parts[#parts+1]=d.label..' = '..(a and('%s (%s, %s beacon)%s'):format(a.carrier,tostring(a.family),
                tostring(a.beam),a.local_refused and', NOT OWNED here'or'')or('REFUSED ('..out.refused[d.id]..')'))
        end
    end
    out.distinct=distinct
    out.line='CUSTOM CARRIERS: '..table.concat(parts,', ')..'; distinct = '..tostring(distinct)
    return out
end

-------------------------------------------------------------------------------------------------- the lobby --
-- Several players with the same mod set (EXPERIMENTAL multiplayer, runtime/multiplayer.lua: the host runs its own calls;
-- a client refuses its own). Carrier allocation is by custom stratagem IDENTITY across the lobby, never per player:
--   * every peer allocates every REGISTERED custom stratagem (the mod set, sorted by id), not only what it selected, so
--     the mapping id -> carrier never depends on who selected what (another player's custom selection is not visible);
--   * natively selected carriers are excluded for everybody: the union of every player's native selection this machine
--     can read (M.lobby_native);
--   * a carrier is reserved by ONE id; every slot and every player selecting that id reuses it; another id skips it;
--   * the order is explicit: definitions by (fewest eligible, id), candidates by (family preference, red ping, class,
--     stable id); never player order, join order, entity ids, timing or which peer evaluates first;
--   * ownership is per account: with several players the ranking ignores it (so every peer agrees); a carrier this
--     account does not own is refused locally (local_refused), never replaced by another.
-- M.lobby_native(world, saved): {present = set of stable ids, peers = {hex ids}, records, players, complete,
-- sources = text}. `saved` is the local saved loadout (a set). complete = every player's record was read.
function M.lobby_native(world,saved)
    local world_module=require('hd2runtime/runtime/event_world')
    local loadout=require('hd2runtime/runtime/stratagem_loadout')
    local present,peers={},{}
    for id in pairs(saved or{})do present[id]=true end
    local records=slots.records(world)or{}
    for _,r in ipairs(records)do
        peers[#peers+1]=r.peer
        for _,e in ipairs(r.entries)do
            local id=loadout.id_of(world,e.type)
            if id then present[id]=true end
        end
    end
    local players=world_module.players(world)or{}
    return {present=present,peers=peers,records=#records,players=#players,
        complete=#players>0 and#records>=#players,
        sources=('the local saved loadout and %d stratagem record%s of %d player%s'):format(#records,
            #records==1 and''or's',#players,#players==1 and''or's')}
end
-- M.allocate_lobby(world, definitions, lobby, global_exclude): definitions = every registered custom stratagem;
-- lobby = {present = set of natively selected stable ids (every player's), players = n, selections = {{player, ids =
-- {custom ids}}} (optional: for the mapping)}. Returns allocate_policies' result plus mapping = {{player, slots = {{id,
-- carrier, stable_id, reused}}}} (players sorted by their id) and reservations = {[stable id] = custom id}.
function M.allocate_lobby(world,definitions,lobby,global_exclude,opts)
    opts=opts or{}
    local a=M.allocate_policies(world,definitions,lobby.present or{},global_exclude,
        {lobby=(lobby.players or 1)>1,report=opts.report})
    a.reservations={}
    for id,assignment in pairs(a.assignments)do
        if not assignment.tentative then a.reservations[assignment.stable_id]=id end
    end
    a.mapping=M.lobby_mapping(a,lobby.selections)
    return a
end
-- The carrier each player's selections use: one reservation per id, reused by every later selection of that id, in
-- any slot. selections: {{player, ids = {custom ids}} or {player, slots = {{slot, id}}}}; players and slots are sorted,
-- so their order never matters. The walk: the id's reserved carrier (the same id: reused; another id never shares it).
function M.lobby_mapping(allocation,selections)
    local players={}
    for _,s in ipairs(selections or{})do players[#players+1]=s end
    table.sort(players,function(a,c)return tostring(a.player)<tostring(c.player)end)
    local used,out={},{}
    for _,s in ipairs(players)do
        local row={player=s.player,slots={}}
        local list={}
        if s.slots then
            for _,x in ipairs(s.slots)do list[#list+1]={slot=x.slot,id=x.id}end
            table.sort(list,function(a,c)return a.slot<c.slot end)
        else
            for k,id in ipairs(s.ids or{})do list[#list+1]={slot=k-1,id=id}end
        end
        for _,x in ipairs(list)do
            local a=allocation.assignments[x.id]
            row.slots[#row.slots+1]={slot=x.slot,id=x.id,carrier=a and a.carrier,stable_id=a and a.stable_id,
                reused=used[x.id]==true,refused=not a and(allocation.refused[x.id]or'not registered')or nil}
            if a then used[x.id]=true end
        end
        out[#out+1]=row
    end
    return out
end
return M
