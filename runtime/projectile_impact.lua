-- A projectile's own impact explosion, per projectile (development; research/docs/gas-eat-F5FEE03DCFDB.md). Not
-- exported by api/hd2.lua: hd2.custom_stratagem weapons reach it (weapon:set_impact_explosion).
--
-- SpawnProjectile copies the row's impact explosion (+0x90) into the projectile's own hit record (+0x7C), and the
-- impact reads that copy, never the row (research/projectile-pool-F5FEE03DCFDB.json, proof 4 and its census: the only
-- store is SpawnProjectile's). So a projectile fired by one exact weapon entity can request another reviewed explosion on
-- impact: ONE guarded 4-byte write of that projectile's +0x7C while it flies, from the row's explosion to the donor's.
-- The projectile stays the vanilla type in flight and on a direct hit; its row, the weapon, every other projectile and
-- every shared definition are never written. The explosion is requested by the game itself with the projectile's own
-- creditor (the wielder's peer), owner and source, as for its native explosion.
--
-- M.bind(spec) follows exact weapon entities (the sources; binding.add_source(entity, {entity_type, owner}) adds one more
-- exact entity the caller has established as its own, e.g. a pod mounted on a custom Eagle call's jet; with `owner`,
-- that source's projectiles must also name that owner; spec.accept(world, system, slot, source, owner) may establish
-- an unbound source at its first projectile). Each update it reads the projectiles spawned since its last look (the
-- pool counter, read-only) and, for one of a bound source's, writes +0x7C only when every guard holds (else the
-- projectile stays vanilla and the reason is reported):
--   * the pool pins (with the impact pins) proven; a mission, as host, solo; the binding's donor chain intact (every
--     row of the donor's explosion exactly as reviewed) and the donor's call-in package resident;
--   * the projectile: the bound type, the bound source entity (still alive, still the bound entity type), in flight
--     (flags bit 1), its impact not requested (+0xB9 = 0), its impact explosion copy exactly the row's (+0x7C) and no
--     pending expiry explosion (+0x80 = 0), the local peer as its creditor (NOT_LOCAL) unless the binding follows the
--     PAYLOAD PROVENANCE of exact launchers (spec.provenance: a custom stratagem's delivered launcher is that custom
--     stratagem's whoever wields it, so its rocket converts whoever fired it; the creditor is the game's own (the
--     wielder's peer), reported and never written);
--   * the source has rounds left (an EAT-17 fires one).
-- The transaction's contexts are the projectile's whole hit record, its source record, its type entry and its flags;
-- afterwards +0x7C is read back. Later updates report the impact (+0xB9 set: the donor explosion requested) or the slot
-- reused. A Lua update runs before the game update that steps projectiles, so a projectile is read before its first
-- step (projectile replacement measured 0.00 m travelled on every carrier read).
--
-- Scope: this machine's own pool. A peer explodes its OWN copy of the projectile (research: the impact message carries
-- the override flag, not the type), so another machine's copy keeps the native explosion unless that machine's Runtime
-- converts its own copy too: with several players every compatible Runtime binds the same launchers by their network
-- ids (runtime/custom_mp_items.lua) and writes only its own copy (as every machine's copy of a vanilla Orbital Gas
-- Strike shell explodes as 82 by its row).
--
-- M.observe(fn): a read-only observer of every new slot the watch reads (diagnostics, e.g. a custom Eagle call's rocket
-- trace): fn(world, system, item, outcome) with item = {slot, type, source} and outcome the binding's event for that slot
-- (converted / refused) or nil when no binding claimed it. Nothing is written for an observer.
--
-- CONTINUOUS bindings (spec.continuous: an automatic weapon, the Pelican gunship's chin gun) convert every round of
-- their sources while those exist, and take only a donor reviewed for a gun (explosion_donors): an `automatic` one (one
-- plain blast a round), or a `slow` one (a damage-over-time volume: an EMS field, a gas cloud), whose binding converts
-- at most its max_rpm rounds a minute: a round less than M.SLOW_GAP of its interval after the binding's last conversion
-- is refused (RATE_EXCEEDED: it stays vanilla), whatever rate the gun was given (the game holds 4096 status volumes and
-- checks no count before adding one: research/custom-payloads slowDonors). Their rounds may be EXPLOSION-LESS CARRIERS (research/custom-payloads
-- impactCarriers: the Pelican CAS rounds 148 and 275): no impact or expiry explosion and, read now, exactly the reviewed
-- flags +0xF0 of the LAS-58 Talon base whose Runtime-owned row with +0x90 = 158 exploded live (docs/custom-projectile-
-- rows.md, F10). SpawnProjectile is the only store of +0x7C and hit processing reads only that copy, so the write
-- from 0 is the state that row's spawn made. Any other row without an impact explosion is refused as before.
-- A source may have one impact binding and one credit binding (M.bind_credit) at once: they write different members of
-- the same round (+0x7C, +0x00), each in its own transaction over the hit record read then.
--
-- Logging: every write (CONVERTED); a refusal once per binding and reason (the event carries first = true), the rest
-- counted in one line when the binding ends. A binding ends once every source has fired its rounds and nothing it
-- converted still flies (unless a rule may still add a source), once every source with rounds left is gone, at the
-- mission's end, or when cancelled; the watch stops with the last binding and observer.
if rawget(_G,'jit')then jit.off(true,true)end
local world_module=require('hd2runtime/runtime/event_world')
local transaction=require('hd2runtime/core/guarded_transaction')
local scheduler=require('hd2runtime/runtime/scheduler')
local metrics=require('hd2runtime/runtime/metrics')
local log_module=require('hd2runtime/runtime/log')
local b=require('hd2runtime/core/bytes')
local PO=require('hd2runtime/domains/projectile_rows').pool
local M={}
M.MAX_BINDINGS=32
M.MAX_SOURCES=8
M.MAX_READS=64            -- new slots examined per update at most (the newest are kept)
M.FOLLOW_SECONDS=30       -- a written projectile is followed this long for its impact
local H,S,F=PO.hit,PO.source,PO.flags
local COUNTER_RANGE=4294967296

-- The reviewed donor explosions (runtime/explosion_donors.lua): a donor stratagem, the explosion its own shell requests
-- and the check that its whole chain is exactly as reviewed (the Orbital Gas Strike's 82, the Orbital EMS Strike's 188).
local donors=require('hd2runtime/runtime/explosion_donors')
M.DONORS=donors.DONORS
M.SLOW_GAP=0.8            -- a slow donor's binding: the shortest gap between two conversions, in its interval
local CARRIERS=require('hd2runtime/domains/custom_payloads').impactCarriers

-- An explosion-less carrier's row, read now (see the header): its type, no impact or expiry explosion, and exactly the
-- reviewed flags of the live-verified base. true, or nil, reason.
local function carrier_intact(world,row,kind)
    local c=CARRIERS.types[tostring(kind)]
    if not c then
        return nil,'projectile '..kind..' has no impact explosion and is not a reviewed explosion-less carrier'
    end
    local flags=world.view.read(row+CARRIERS.flagsOffset,2)
    local f=flags and#flags==2 and flags:byte(1)+flags:byte(2)*256
    if world.view.u32(row)~=kind or world.view.u32(row+PO.explosions.impact)~=0
            or world.view.u32(row+PO.explosions.expiry)~=0 or f~=c.flags or f~=CARRIERS.baseFlags then
        return nil,('projectile %d\'s row is not the reviewed explosion-less carrier (flags +0x%X: %s, reviewed %d)')
            :format(kind,CARRIERS.flagsOffset,tostring(f),c.flags)
    end
    return true
end

local function log(text)log_module.emit('[HD2Runtime] projectile impact '..text)end
local function u32(n)return b.encode(n%4294967296,'u32')end

local bindings={}         -- by id
local order={}
local by_source={}        -- source entity -> its impact binding
local by_credit={}        -- source entity -> its credit binding
local observers={}        -- read-only slot observers (M.observe)
local watch
local pool={}             -- {system, counter}
local clock=0
local next_id=0

local function owner_of(world,address,size)
    local r=world.runtime.query and world.runtime.query(address)
    if not(r and r.state==0x1000 and r.type==0x20000 and r.protect==4 and address>=r.base and address+size<=r.base+r.size)
    then return nil end
    return {base=r.allocation_base,size=r.base+r.size-r.allocation_base,type=0x20000,protect=4}
end

local function emit(binding,event)
    if binding.callback then
        local ok,why=pcall(binding.callback,event)
        if not ok then log('callback failed: '..tostring(why))end
    end
end

-- The binding-wide guards, read now: true, or nil, code, reason.
local function binding_guards(world,binding)
    local game=world_module.game_state(world)
    if not(game and game.mission)then return nil,'NOT_IN_MISSION','a projectile impact is changed in a mission only'end
    -- This machine's own player's projectile (NOT_LOCAL below): the host, or a client inside the client-write proof.
    local hcode,hwhy=require('hd2runtime/runtime/multiplayer').host_guard(game,binding.client==true,
        'development: host only')
    if hcode then return nil,hcode,hwhy end
    local players=world_module.players(world)
    -- A peer explodes its own copy (the impact message carries the override flag, not the type): with several players
    -- (binding.multiplayer: a custom stratagem call) the donor explosion happens on this machine only.
    local scode,swhy=require('hd2runtime/runtime/multiplayer').solo_guard(#players,binding.multiplayer==true,
        'a peer explodes its own copy')
    if scode then return nil,scode,swhy end
    return donors.ready(world,binding.donor)
end

-- One projectile of a bound source: every guard, then the write. Returns the event.
local function convert(world,system,binding,source,slot,kind)
    local event={kind='refused',slot=slot,source=source,type=kind,binding=binding.id}
    local function refuse(code,reason)
        event.code,event.reason=code,reason
        binding.refused=binding.refused+1
        return event
    end
    local s=binding.sources[source]
    if s.owner~=nil then
        local owner=world.view.u32(system+H.base+slot*H.stride+H.owner)
        if owner~=s.owner then
            return refuse('OWNER_MISMATCH',('its owner is %s, not %d'):format(tostring(owner),s.owner))
        end
    end
    if s.rounds<=0 then
        event.kind='untouched';event.reason='no rounds left for source '..source
        return event
    end
    if world_module.entity_exists(world,source)~=true then return refuse('SOURCE_GONE','the source entity is gone')end
    if world_module.entity_type(world,source)~=s.entity_type then
        return refuse('SOURCE_CHANGED','the source is no longer the bound entity type')
    end
    local ok,code,reason=binding_guards(world,binding)
    if not ok then return refuse(code,reason)end
    local hit_address=system+H.base+slot*H.stride
    local source_address=system+S.base+slot*S.stride
    local type_address=system+PO.types.base+slot*PO.types.stride
    local flags_address=system+F.base+slot*F.stride
    local hit=world.view.read(hit_address,H.stride)
    local source_record=world.view.read(source_address,S.stride)
    local type_bytes=world.view.read(type_address,PO.types.stride)
    local flags=world.view.read(flags_address,F.stride)
    if not(hit and source_record and type_bytes and flags)then return refuse('UNREADABLE','the projectile is unreadable')end
    local from=binding.types[kind]
    if not from or b.u32(type_bytes,0)~=kind then return refuse('SLOT_MISMATCH','the slot holds another type now')end
    if b.u32(source_record,S.entity)~=source then return refuse('SLOT_MISMATCH','the slot names another source now')end
    local flag_word=flags:byte(1)+flags:byte(2)*256
    if math.floor(flag_word/F.inFlight)%2~=1 then return refuse('MISSED','the projectile is no longer in flight')end
    if hit:byte(H.impactRequested+1)~=0 then return refuse('MISSED','its impact was already requested')end
    local impact,expiry=b.u32(hit,H.impactExplosion),b.u32(hit,H.expiryExplosion)
    if impact~=from then
        return refuse('UNEXPECTED_EXPLOSION',('its impact explosion is %d, not %d'):format(impact,from))
    end
    if expiry~=0 then return refuse('UNEXPECTED_EXPLOSION','an expiry explosion is pending')end
    -- An explosion-less carrier's row is re-read for every round (another mod may have changed it since the bind).
    if from==0 then
        local intact,why=carrier_intact(world,binding.carrier_rows and binding.carrier_rows[kind]or 0,kind)
        if not intact then return refuse('CARRIER_CHANGED',why)end
    end
    -- A slow donor's volume at most max_rpm times a minute.
    if binding.min_gap and binding.last_at and clock-binding.last_at<binding.min_gap then
        return refuse('RATE_EXCEEDED',('%.2f s after the last converted round: %s makes at most %d volumes a minute')
            :format(clock-binding.last_at,binding.donor,binding.max_rpm))
    end
    local lo,hi=world_module.local_peer(world)
    local clo,chi=b.u32(hit,H.creditor),b.u32(hit,H.creditor+4)
    local local_creditor=lo~=nil and clo==lo and chi==hi
    -- Payload provenance (binding.provenance): the exact launcher decides the payload, never who fired it.
    if not local_creditor and not binding.provenance then
        return refuse('NOT_LOCAL',('the projectile is credited to peer %s, not the local player (in multiplayer: '
            ..'another player fired it; only the caller\'s own shots convert)'):format(world_module.peer_hex(clo,chi)))
    end
    local owner=owner_of(world,hit_address,H.stride)
    if not(owner and owner_of(world,source_address,S.stride)and owner_of(world,type_address,4)
            and owner_of(world,flags_address,F.stride))then
        return refuse('NOT_PRIVATE','the projectile pool is not in private read-write memory')
    end
    local function context(address,bytes)return {owner=owner,offset=address-owner.base,bytes=bytes}end
    local plan={snapshots={context(hit_address,hit),context(source_address,source_record),context(type_address,type_bytes),
            context(flags_address,flags)},
        changes={{label='projectile.pool.slot'..slot..'.impactExplosion',owner=owner,
            offset=hit_address+H.impactExplosion-owner.base,expected=u32(from),desired=u32(binding.to),
            before=u32(from),already_desired=false,
            identity={component='ProjectileSystem',component_type='native',record_type='projectile hit record',
                unique_owner=true,owner_count=1},chain={}}}}
    local report=transaction.apply(world.runtime,plan)
    metrics.count('projectile_impact.transactions')
    if report.status~='APPLIED'then return refuse('GUARD_REJECTED',tostring(report.reason))end
    local after=world.view.u32(hit_address+H.impactExplosion)
    s.rounds=s.rounds-1
    binding.converted=binding.converted+1
    binding.last_at=clock
    binding.flying[slot]={source=source,at=clock,type=kind}
    event.kind='converted'
    event.from,event.to=from,binding.to
    event.writes=report.writes
    event.verify={readBack=after==binding.to,nonTarget=report.non_target_bytes_unchanged==true,
        protection=report.protection_restored==true}
    event.creditor=world_module.peer_hex(clo,chi)
    event.local_creditor=local_creditor
    event.owner=b.u32(hit,H.owner)
    return event
end

-- CREDIT MODE (M.bind_credit): one round of a bound source, its own pool creditor (hit record +0x00, u64 peer) from the
-- game's own (this machine's player, the turret's network owner; or none) to binding.credit_to, in one guarded 8-byte
-- write before its first step (research peer-messaging "pelicanMirror": a round spawned in an update is first stepped in
-- the next; its creditor flows unchanged into the hit, the damage event, the victim's health +0x38 and the kill, for
-- any player of the game). The round's type, source, flight and impact state are checked as for an impact conversion.
local function peer_bytes(hex)
    return u32(tonumber(hex:sub(9,16),16))..u32(tonumber(hex:sub(1,8),16))
end
local function convert_credit(world,system,binding,source,slot,kind)
    local event={kind='refused',slot=slot,source=source,type=kind,binding=binding.id}
    local function refuse(code,reason)
        event.code,event.reason=code,reason
        binding.refused=binding.refused+1
        return event
    end
    if world_module.entity_exists(world,source)~=true then return refuse('SOURCE_GONE','the source entity is gone')end
    local game=world_module.game_state(world)
    if not(game and game.mission)then return refuse('NOT_IN_MISSION','in a mission only')end
    if game.host~=true then return refuse('NOT_HOST','the credit of a host-spawned turret is written on the host')end
    local hit_address=system+H.base+slot*H.stride
    local source_address=system+S.base+slot*S.stride
    local type_address=system+PO.types.base+slot*PO.types.stride
    local flags_address=system+F.base+slot*F.stride
    local hit=world.view.read(hit_address,H.stride)
    local source_record=world.view.read(source_address,S.stride)
    local type_bytes=world.view.read(type_address,PO.types.stride)
    local flags=world.view.read(flags_address,F.stride)
    if not(hit and source_record and type_bytes and flags)then return refuse('UNREADABLE','the projectile is unreadable')end
    if not binding.types[kind]or b.u32(type_bytes,0)~=kind then return refuse('SLOT_MISMATCH','another type')end
    if b.u32(source_record,S.entity)~=source then return refuse('SLOT_MISMATCH','the slot names another source now')end
    local flag_word=flags:byte(1)+flags:byte(2)*256
    if math.floor(flag_word/F.inFlight)%2~=1 then return refuse('MISSED','the projectile is no longer in flight')end
    if hit:byte(H.impactRequested+1)~=0 then return refuse('MISSED','its impact was already requested')end
    local lo,hi=world_module.local_peer(world)
    local clo,chi=b.u32(hit,H.creditor),b.u32(hit,H.creditor+4)
    local current=world_module.peer_hex(clo,chi)
    if current==binding.credit_to then event.kind='untouched';event.reason='already credited';return event end
    if not((clo==lo and chi==hi)or(clo==0 and chi==0))then
        return refuse('UNEXPECTED_CREDITOR','it is credited to '..current..', not this machine\'s player or nobody')
    end
    local owner=owner_of(world,hit_address,H.stride)
    if not(owner and owner_of(world,source_address,S.stride)and owner_of(world,type_address,4)
            and owner_of(world,flags_address,F.stride))then
        return refuse('NOT_PRIVATE','the projectile pool is not in private read-write memory')
    end
    local function context(address,bytes)return {owner=owner,offset=address-owner.base,bytes=bytes}end
    local want=peer_bytes(binding.credit_to)
    local plan={snapshots={context(hit_address,hit),context(source_address,source_record),context(type_address,type_bytes),
            context(flags_address,flags)},
        changes={{label='projectile.pool.slot'..slot..'.creditor',owner=owner,offset=hit_address+H.creditor-owner.base,
            expected=hit:sub(H.creditor+1,H.creditor+8),desired=want,before=hit:sub(H.creditor+1,H.creditor+8),
            already_desired=false,identity={component='ProjectileSystem',component_type='native',
            record_type='projectile hit record',unique_owner=true,owner_count=1},chain={}}}}
    local report=transaction.apply(world.runtime,plan)
    metrics.count('projectile_impact.credit_transactions')
    if report.status~='APPLIED'then return refuse('GUARD_REJECTED',tostring(report.reason))end
    binding.converted=binding.converted+1
    event.kind='converted'
    event.from,event.to=current,binding.credit_to
    event.writes=report.writes
    event.verify={readBack=world.view.read(hit_address+H.creditor,8)==want}
    return event
end

-- The written projectiles: their impact (the donor explosion requested) or their end.
local function follow(world,system,binding)
    for slot,f in pairs(binding.flying)do
        local hit=world.view.read(system+H.base+slot*H.stride,H.stride)
        local kind=world.view.u32(system+PO.types.base+slot*PO.types.stride)
        local source=world.view.u32(system+S.base+slot*S.stride+S.entity)
        local same=hit and kind==f.type and source==f.source
        if same and hit:byte(H.impactRequested+1)==1 then
            binding.flying[slot]=nil
            binding.impacts=binding.impacts+1
            emit(binding,{kind='impact',slot=slot,source=f.source,explosion=b.u32(hit,H.impactExplosion),
                seconds=clock-f.at,binding=binding.id})
        elseif not same or clock-f.at>M.FOLLOW_SECONDS then
            binding.flying[slot]=nil
            emit(binding,{kind='lost',slot=slot,source=f.source,seconds=clock-f.at,binding=binding.id,
                reason=not same and'the slot was reused'or'no impact within '..M.FOLLOW_SECONDS..' s'})
        end
    end
end

local function finish(binding,reason)
    if binding.status~='active'then return end
    binding.status='complete'
    if binding.mode=='credit'then
        log(('CREDIT (%s): ended (%s): %d round%s credited to %s'):format(binding.label,tostring(reason),binding.converted,
            binding.converted==1 and''or's',binding.credit_to))
    end
    if(binding.suppressed or 0)>0 then
        local parts={}
        for code,n in pairs(binding.refusals)do if n>1 then parts[#parts+1]=('%s x %d'):format(code,n-1)end end
        table.sort(parts)
        log(('REFUSED (%s): %d more projectile%s stayed vanilla (%s)'):format(binding.label,binding.suppressed,
            binding.suppressed==1 and''or's',table.concat(parts,', ')))
    end
    local map=binding.mode=='credit'and by_credit or by_source
    for source in pairs(binding.sources)do if map[source]==binding then map[source]=nil end end
    bindings[binding.id]=nil
    for k,item in ipairs(order)do if item==binding then table.remove(order,k)break end end
    emit(binding,{kind='ended',reason=reason,converted=binding.converted,impacts=binding.impacts,refused=binding.refused,
        binding=binding.id})
end

local function step(dt)
    clock=clock+(dt or 0)
    if#order==0 and not next(observers)then return end
    local world=world_module.open()
    if not world then return end
    local game=world_module.game_state(world)
    if not(game and game.mission)then
        for k=#order,1,-1 do finish(order[k],'the mission ended')end
        pool={}
        return
    end
    local counter,system=world_module.projectile_counter(world)
    if not counter then pool={};return end
    if pool.system~=system or not pool.counter then pool.system,pool.counter=system,counter;return end
    local count=(counter-pool.counter)%COUNTER_RANGE
    local from=pool.counter
    pool.counter=counter
    if count>0 and count<=PO.slots then
        if count>M.MAX_READS then from=(from+count-M.MAX_READS)%COUNTER_RANGE;count=M.MAX_READS end
        local slots=world_module.projectile_types(world,system,from,count)
        metrics.count('projectile_impact.slots_read',slots and#slots or 0)
        for _,item in ipairs(slots or{})do
            local outcome
            for _,binding in ipairs(order)do
                if binding.status=='active'and binding.types[item.type]then
                    local source=world.view.u32(system+S.base+item.slot*S.stride+S.entity)
                    -- An unbound source the binding's own rule establishes (exactly, from this projectile's records).
                    if source and not binding.sources[source]and binding.accept and not by_source[source]then
                        local owner=world.view.u32(system+H.base+item.slot*H.stride+H.owner)
                        local ok,why=pcall(binding.accept,world,system,item.slot,source,owner)
                        if not ok then log('accept failed: '..tostring(why))end
                    end
                    if source and binding.sources[source]and binding.mode=='credit'then
                        local event=convert_credit(world,system,binding,source,item.slot,item.type)
                        outcome=event
                        if event.kind=='converted'and binding.converted==1 then
                            log(('CREDIT (%s): projectile %d in pool slot %d from source %d: its own creditor %s -> %s (1 write; '
                                ..'read back %s); the next rounds are counted'):format(binding.label,item.type,item.slot,source,
                                event.from,event.to,tostring(event.verify.readBack)))
                        elseif event.kind=='refused'then
                            local code=tostring(event.code)
                            binding.refusals[code]=(binding.refusals[code]or 0)+1
                            event.first=binding.refusals[code]==1
                            if event.first then
                                log(('CREDIT REFUSED (%s): projectile %d in pool slot %d keeps its creditor: %s: %s'):format(
                                    binding.label,item.type,item.slot,code,tostring(event.reason)))
                            else binding.suppressed=binding.suppressed+1 end
                        end
                        emit(binding,event)
                    elseif source and binding.sources[source]then
                        local event=convert(world,system,binding,source,item.slot,item.type)
                        outcome=event
                        if event.kind=='converted'then
                            -- The first of a binding always; the next ones with the diagnostics switch (each binding's
                            -- owner logs its own count at its end).
                            local emit=binding.converted<=1 and log or function(text)
                                log_module.detail('[HD2Runtime] projectile impact '..text)end
                            emit(('CONVERTED (%s): projectile %d in pool slot %d from source %d: impact explosion %d -> %d '
                                ..'(%d write; read back %s; non-target bytes unchanged %s; protection restored %s); '
                                ..'creditor %s, owner %d%s'):format(binding.label,item.type,item.slot,source,event.from,
                                event.to,event.writes,tostring(event.verify.readBack),tostring(event.verify.nonTarget),
                                tostring(event.verify.protection),event.creditor,event.owner,event.local_creditor and''
                                or' (another player fired it: the payload follows its exact source; the credit is the '
                                ..'game\'s own)'))
                        elseif event.kind=='refused'then
                            -- Once per reason: the rest are counted (finish).
                            local code=tostring(event.code)
                            binding.refusals[code]=(binding.refusals[code]or 0)+1
                            event.first=binding.refusals[code]==1
                            if event.first then
                                log(('REFUSED (%s): projectile %d in pool slot %d from source %d stays vanilla: %s: %s'):format(
                                    binding.label,item.type,item.slot,source,code,tostring(event.reason)))
                            else
                                binding.suppressed=binding.suppressed+1
                            end
                        end
                        emit(binding,event)
                    end
                end
            end
            if next(observers)then
                item.source=world.view.u32(system+S.base+item.slot*S.stride+S.entity)
                for observer in pairs(observers)do
                    local ok,why=pcall(observer.fn,world,system,item,outcome)
                    if not ok then log('observer failed: '..tostring(why))end
                end
            end
        end
    end
    for _,binding in ipairs(order)do if next(binding.flying)then follow(world,system,binding)end end
    -- A binding whose every source fired its rounds, with nothing of it in flight, has nothing left to do (a binding
    -- with an accept rule may still gain a source: its owner ends it).
    -- An accept rule's sources that are gone (a barrage over) leave it, with nothing of them in flight.
    for _,binding in ipairs(order)do
        if binding.accept then
            for source in pairs(binding.sources)do
                local flying=false
                for _,f in pairs(binding.flying)do if f.source==source then flying=true end end
                if not flying and world_module.entity_exists(world,source)==false then
                    binding.sources[source]=nil
                    if by_source[source]==binding then by_source[source]=nil end
                    emit(binding,{kind='source_gone',source=source,binding=binding.id})
                end
            end
        end
    end
    -- A binding whose every source with rounds left is gone (a launcher despawned unfired) has nothing left either.
    for k=#order,1,-1 do
        local binding=order[k]
        if not binding.accept and not next(binding.flying)then
            local left,alive=false,false
            for source,s in pairs(binding.sources)do
                if s.rounds>0 or binding.mode=='credit'then
                    left=true
                    if world_module.entity_exists(world,source)~=false then alive=true;break end
                end
            end
            if not left then finish(binding,'every source fired its rounds')
            elseif not alive then finish(binding,'every source with rounds left is gone')end
        end
    end
end

-- One update, timed for hd2.diagnostics.telemetry ('projectile_impact.tick').
local function tick(dt)
    local started=metrics.now()
    step(dt)
    metrics.elapsed('projectile_impact.tick',started)
end

local function ensure_watch()
    if watch and watch.status=='active'then return end
    watch={status='active'}
    function watch.tick(dt)
        if watch.status~='active'then return end
        tick(dt)
        -- Nothing bound or observed: the watch stops (the next binding or observer starts it again, re-reading the
        -- pool counter first).
        if#order==0 and not next(observers)then watch.status='complete';pool={}end
    end
    function watch.cancel()watch.status='cancelled'end
    scheduler.attach(watch)
end

-- Binds exact weapon entities. spec = {sources = {entity ids}, projectile = the vanilla ProjectileInfo type they fire,
-- donor = a stratagem of M.DONORS whose explosion replaces the impact explosion, rounds = per source (default 1),
-- label, provenance (true: the payload follows the exact source whoever fired it; no NOT_LOCAL), continuous (true: every
-- round while the sources exist, no `rounds`; the donor must be an automatic or a slow one)}. Every source must exist now, be one
-- entity type, and the projectile's row must hold an impact explosion and no expiry explosion (read now: the `from` every
-- write expects), or, for a continuous binding, be a reviewed explosion-less carrier (from 0). callback(event): 'converted' (slot, source, from, to,
-- writes, verify, creditor, owner), 'refused' (code, reason: the projectile stays vanilla), 'untouched' (a source with
-- no rounds left), 'impact' (slot, source, explosion), 'lost', 'ended'. Returns the binding {id, status, cancel()}, or
-- nil, code, reason.
function M.bind(spec,callback)
    if type(spec)~='table'then return nil,'INVALID','spec must be a table'end
    if#order>=M.MAX_BINDINGS then return nil,'LIMIT','at most '..M.MAX_BINDINGS..' impact bindings'end
    local donor=M.DONORS[spec.donor]
    if not donor then return nil,'UNREVIEWED_DONOR','no reviewed impact explosion donor '..tostring(spec.donor)end
    -- One type (projectile) or several (projectiles: a barrage firing two shell types), each its own row's impact.
    local list=spec.projectiles or{spec.projectile}
    if type(list)~='table'or#list<1 or#list>4 then return nil,'INVALID','projectiles lists 1..4 types'end
    for _,t in ipairs(list)do
        if type(t)~='number'or t%1~=0 or t<=0 then return nil,'INVALID','projectile must be a ProjectileInfo type'end
    end
    local continuous=spec.continuous==true
    -- A gun's donor (automatic: one plain blast a round; slow: a volume at most max_rpm a minute) belongs to a
    -- continuous binding, and only there.
    local gun_donor=donor.automatic==true or donor.slow==true
    if continuous~=gun_donor then
        return nil,'UNSUITABLE_DONOR',continuous and(tostring(spec.donor)..' is not reviewed for a gun '
            ..'(gun donors: '..table.concat(donors.names({gun=true}),', ')..')')
            or(tostring(spec.donor)..' is reviewed for a gun only (a continuous binding)')
    end
    if continuous and spec.rounds~=nil then return nil,'INVALID','a continuous binding converts every round: no rounds'end
    local rounds=continuous and math.huge or spec.rounds or 1
    if not continuous and(type(rounds)~='number'or rounds%1~=0 or rounds<1 or rounds>64)then
        return nil,'INVALID','rounds is 1..64'
    end
    -- An accept rule may start with no source and take up to spec.max_sources (64 at most) of its own.
    local max_sources=spec.accept and math.min(64,spec.max_sources or M.MAX_SOURCES)or M.MAX_SOURCES
    if type(spec.sources)~='table'or(#spec.sources<1 and not spec.accept)or#spec.sources>max_sources then
        return nil,'INVALID','sources is a list of 1..'..max_sources..' entity ids'
    end
    local world,why=world_module.open()
    if not world then return nil,'UNAVAILABLE',tostring(why)end
    local proven,pwhy=world_module.prove_projectile_pool(world)
    if not proven then return nil,'UNSUPPORTED_BUILD',tostring(pwhy)end
    local types,from,carrier_rows={},nil,{}
    for _,t in ipairs(list)do
        local _,row=world_module.projectile_row(world,t)
        if not row then return nil,'UNKNOWN_PROJECTILE','no row for projectile '..t end
        local f=world.view.u32(row+PO.explosions.impact)
        local expiry=world.view.u32(row+PO.explosions.expiry)
        if f==0 and continuous then
            local intact,why=carrier_intact(world,row,t)
            if not intact then return nil,'NO_IMPACT_EXPLOSION',why end
            carrier_rows[t]=row
        elseif not(f and f>0)then return nil,'NO_IMPACT_EXPLOSION','projectile '..t..' has no impact explosion'end
        if expiry~=0 then return nil,'EXPIRY_EXPLOSION','projectile '..t..' has an expiry explosion'end
        if f==donor.explosion then return nil,'NOTHING_TO_CHANGE','projectile '..t..' already explodes as the donor'end
        types[t]=f
        from=from or f
    end
    local sources,entity_type={},nil
    for k,source in ipairs(spec.sources)do
        if world_module.entity_exists(world,source)~=true then return nil,'SOURCE_GONE','source '..k..' does not exist'end
        if by_source[source]then return nil,'ALREADY_BOUND','source '..source..' is bound already'end
        local kind=world_module.entity_type(world,source)
        if not kind then return nil,'SOURCE_UNREADABLE','source '..source..' has no entity type'end
        if spec.entity_type and kind~=spec.entity_type then
            return nil,'SOURCE_CHANGED','source '..source..' is not entity type '..tostring(spec.entity_type)
        end
        sources[source]={rounds=rounds,entity_type=kind}
        entity_type=entity_type or kind
    end
    local ok,code,reason=binding_guards(world,{donor=spec.donor,multiplayer=spec.multiplayer==true,client=spec.client==true})
    if not ok then return nil,code,reason end
    next_id=next_id+1
    local binding={id=next_id,status='active',label=tostring(spec.label or('binding '..next_id)),donor=spec.donor,
        projectile=list[1],projectiles=list,types=types,from=from,to=donor.explosion,sources=sources,callback=callback,
        flying={},
        converted=0,impacts=0,refused=0,entity_type=spec.entity_type,rounds=rounds,accept=spec.accept,refusals={},
        suppressed=0,multiplayer=spec.multiplayer==true,client=spec.client==true,provenance=spec.provenance==true,
        max_sources=max_sources,continuous=continuous,carrier_rows=carrier_rows,
        max_rpm=donor.slow and donor.max_rpm or nil,min_gap=donor.slow and M.SLOW_GAP*60/donor.max_rpm or nil}
    function binding.cancel()finish(binding,'cancelled')end
    -- One more exact source the caller established as its own: it must exist now, be the binding's entity type (or
    -- opts.entity_type) and not be bound by another binding; with opts.owner, every projectile of it must name that owner.
    -- Returns true, or nil, code, reason.
    function binding.add_source(source,opts)
        opts=opts or{}
        if binding.status~='active'then return nil,'ENDED','the binding has ended'end
        if binding.sources[source]then return true end
        local n=0;for _ in pairs(binding.sources)do n=n+1 end
        if n>=(binding.max_sources or M.MAX_SOURCES)then
            return nil,'LIMIT','at most '..(binding.max_sources or M.MAX_SOURCES)..' sources'
        end
        local w=world_module.open()
        if not w then return nil,'UNAVAILABLE','no game world'end
        if world_module.entity_exists(w,source)~=true then return nil,'SOURCE_GONE','source '..tostring(source)..' does not exist'end
        if by_source[source]then return nil,'ALREADY_BOUND','source '..source..' is bound already'end
        local kind=world_module.entity_type(w,source)
        if not kind then return nil,'SOURCE_UNREADABLE','source '..source..' has no entity type'end
        local want=opts.entity_type or binding.entity_type
        if want and kind~=want then
            return nil,'SOURCE_CHANGED','source '..source..' is not entity type '..tostring(want)
        end
        binding.sources[source]={rounds=binding.rounds,entity_type=kind,owner=opts.owner,how=opts.how}
        by_source[source]=binding
        return true
    end
    bindings[binding.id]=binding
    order[#order+1]=binding
    for source in pairs(sources)do by_source[source]=binding end
    ensure_watch()
    return binding
end
-- ONE exact projectile, now: the pool slot a caller has just spawned into (the bombardment executor's shell, read
-- right after its own FireProjectile and before the game steps it). spec = {slot, source (the entity it names),
-- projectile (the type it must hold), donor, label}. The projectile guards are a bound projectile's (the type and
-- source, in flight, its impact not requested, its impact explosion copy exactly the row's and no expiry explosion
-- pending, the local peer as its creditor) and the binding guards (a mission, host, solo, the donor ready). Returns the
-- event: 'converted' {slot, from, to, writes, verify, creditor, owner} or 'refused' {code, reason}; nothing else is
-- followed.
function M.convert_slot(spec)
    local event={kind='refused',slot=spec and spec.slot}
    if type(spec)~='table'or type(spec.slot)~='number'or type(spec.source)~='number'or type(spec.projectile)~='number'
            or not M.DONORS[spec.donor]then
        event.code,event.reason='INVALID','spec must be {slot, source, projectile, donor}'
        return event
    end
    local world,why=world_module.open()
    if not world then event.code,event.reason='UNAVAILABLE',tostring(why);return event end
    local proven,pwhy=world_module.prove_projectile_pool(world)
    if not proven then event.code,event.reason='UNSUPPORTED_BUILD',tostring(pwhy);return event end
    local counter,system=world_module.projectile_counter(world)
    if not counter then event.code,event.reason='UNAVAILABLE','the projectile pool is unreadable';return event end
    local _,row=world_module.projectile_row(world,spec.projectile)
    local from=row and world.view.u32(row+PO.explosions.impact)
    local expiry=row and world.view.u32(row+PO.explosions.expiry)
    if not(from and from>0 and expiry==0)then
        event.code,event.reason='NO_IMPACT_EXPLOSION','projectile '..spec.projectile..' has no impact explosion only'
        return event
    end
    local donor=M.DONORS[spec.donor]
    if from==donor.explosion then
        event.code,event.reason='NOTHING_TO_CHANGE','the projectile already explodes as the donor'
        return event
    end
    local kind=world_module.entity_type(world,spec.source)
    local binding={id=0,label=tostring(spec.label or'slot'),donor=spec.donor,projectile=spec.projectile,from=from,
        types={[spec.projectile]=from},
        to=donor.explosion,sources={[spec.source]={rounds=1,entity_type=kind}},flying={},converted=0,impacts=0,refused=0,
        multiplayer=spec.multiplayer==true,client=spec.client==true}
    local result=convert(world,system,binding,spec.source,spec.slot,spec.projectile)
    if result.kind=='converted'and log_module.sample('impact.item.converted',3)then
        log(('CONVERTED (%s): projectile %d in pool slot %d from source %d: impact explosion %d -> %d (%d write; read '
            ..'back %s); creditor %s'):format(binding.label,spec.projectile,spec.slot,spec.source,result.from,result.to,
            result.writes,tostring(result.verify.readBack),result.creditor))
    else
        log(('REFUSED (%s): projectile %d in pool slot %d stays vanilla: %s: %s'):format(binding.label,spec.projectile,
            spec.slot,tostring(result.code),tostring(result.reason)))
    end
    return result
end
-- CREDIT: binds exact weapon entities whose rounds credit another player of the game (the host-spawned Pelican CAS
-- of a client's call: its chin turret's rounds, the requesting player's). spec = {sources = {entity ids}, projectiles =
-- {types}, credit_to (a peer hex: a player of this game, not this machine's), label, multiplayer}. Each round's own pool
-- creditor (this machine's player or none) becomes credit_to before its first step; nothing else of it changes. On the
-- host only. Ends when its sources are gone, at the mission's end, or when cancelled. Returns the binding or nil, code,
-- reason.
function M.bind_credit(spec,callback)
    if type(spec)~='table'then return nil,'INVALID','spec must be a table'end
    if#order>=M.MAX_BINDINGS then return nil,'LIMIT','at most '..M.MAX_BINDINGS..' impact bindings'end
    if type(spec.credit_to)~='string'or not spec.credit_to:match('^%x%x%x%x%x%x%x%x%x%x%x%x%x%x%x%x$')then
        return nil,'INVALID','credit_to must be a peer id (16 hex digits)'
    end
    if type(spec.projectiles)~='table'or#spec.projectiles<1 then return nil,'INVALID','projectiles must list types'end
    if type(spec.sources)~='table'or#spec.sources<1 or#spec.sources>M.MAX_SOURCES then
        return nil,'INVALID','sources is a list of 1..'..M.MAX_SOURCES..' entity ids'
    end
    local world,why=world_module.open()
    if not world then return nil,'UNAVAILABLE',tostring(why)end
    local proven,pwhy=world_module.prove_projectile_pool(world)
    if not proven then return nil,'UNSUPPORTED_BUILD',tostring(pwhy)end
    local game=world_module.game_state(world)
    if not(game and game.mission and game.host==true)then return nil,'NOT_HOST','on the host, in a mission only'end
    local lo,hi=world_module.local_peer(world)
    if lo and world_module.peer_hex(lo,hi)==spec.credit_to then
        return nil,'INVALID','credit_to is this machine\'s player: the game credits it already'
    end
    local member=false
    for _,pl in ipairs(world_module.players(world))do member=member or pl.peer==spec.credit_to end
    if not member then return nil,'NOT_A_PLAYER','credit_to is not a player of this game'end
    local scode,swhy=require('hd2runtime/runtime/multiplayer').solo_guard(#world_module.players(world),
        spec.multiplayer==true,'a credit for another player')
    if scode then return nil,scode,swhy end
    local types={}
    for _,t in ipairs(spec.projectiles)do types[t]=true end
    local sources={}
    for k,source in ipairs(spec.sources)do
        if world_module.entity_exists(world,source)~=true then return nil,'SOURCE_GONE','source '..k..' does not exist'end
        if by_credit[source]then return nil,'ALREADY_BOUND','source '..source..' has a credit binding already'end
        sources[source]={rounds=0,entity_type=world_module.entity_type(world,source)}
    end
    next_id=next_id+1
    local binding={id=next_id,status='active',mode='credit',label=tostring(spec.label or('credit '..next_id)),
        projectile=spec.projectiles[1],projectiles=spec.projectiles,types=types,credit_to=spec.credit_to,sources=sources,
        callback=callback,flying={},converted=0,impacts=0,refused=0,refusals={},suppressed=0,multiplayer=true}
    function binding.cancel()finish(binding,'cancelled')end
    bindings[binding.id]=binding
    order[#order+1]=binding
    for source in pairs(sources)do by_credit[source]=binding end
    ensure_watch()
    return binding
end
-- The impact binding following a source entity, or nil (a credit binding is not returned).
function M.binding_of(source)return by_source[source]end
-- A read-only observer of every new slot (see the header). Returns {cancel()}.
function M.observe(fn)
    local observer={fn=fn}
    observers[observer]=true
    function observer.cancel()observers[observer]=nil end
    ensure_watch()
    return observer
end
-- One slot's members a trace reports, read-only: {type, source, impact (its own +0x7C copy), expiry, impact_requested,
-- in_flight, creditor (hex), local_creditor, owner}, or nil.
function M.slot_state(world,system,slot)
    local hit=world.view.read(system+H.base+slot*H.stride,H.stride)
    local source=world.view.read(system+S.base+slot*S.stride,S.stride)
    local kind=world.view.u32(system+PO.types.base+slot*PO.types.stride)
    local flags=world.view.read(system+F.base+slot*F.stride,F.stride)
    if not(hit and source and kind and flags)then return nil end
    local lo,hi=world_module.local_peer(world)
    local clo,chi=b.u32(hit,H.creditor),b.u32(hit,H.creditor+4)
    local flag_word=flags:byte(1)+flags:byte(2)*256
    return {type=kind,source=b.u32(source,S.entity),impact=b.u32(hit,H.impactExplosion),
        expiry=b.u32(hit,H.expiryExplosion),impact_requested=hit:byte(H.impactRequested+1)~=0,
        in_flight=math.floor(flag_word/F.inFlight)%2==1,creditor=world_module.peer_hex(clo,chi),
        local_creditor=lo~=nil and clo==lo and chi==hi,owner=b.u32(hit,H.owner)}
end
function M.active()local out={};for k,item in ipairs(order)do out[k]=item end;return out end
function M.reset_for_tests()
    for k=#order,1,-1 do order[k].status='cancelled';order[k]=nil end
    bindings,by_source,by_credit,pool,clock,next_id,observers={},{},{},{},0,0,{}
    if watch then watch.cancel();watch=nil end
end
return M
