local hd2=require('mods/skyeshade/hd2runtime')
-- BeaconRedirectProof 0.3.0: THE BEACON'S TIMING AND THE BARRAGE'S LIFECYCLE (research/docs/beacon-redirect-
-- F5FEE03DCFDB.md). Development only; solo host; no multiplayer change.
-- 0.2.0 (AC-8 Autocannon -> 120mm) is live-proven at the dispatcher level: the dispatcher was given 136 and the 120mm's
-- payload and requested its spawn. The redirected beacon keeps the AC-8's timers. 0.2.0's 30 s summary was wrong: a
-- 120mm barrage instance existed from the activation and ended 24.3 s later, as the native control's (24.2 s).
-- 0.3.0 measures what the barrage does, for every beacon (redirected or native):
--     the beacon: countdown, threshold, activation, life after the activation;
--     its barrage instance: created, start delay, first shell, last shell, shells fired, removal.
-- Two modes (Mod Options):
--   * default: the AC-8 beacon's type 25 -> 136 only (0.2.0's live-proven write). Nothing else is written.
--   * "Normalize the AC-8 beacon's timing" (the timing proof): the same transaction also sets that beacon's countdown
--     and threshold to a NATIVE 120mm control beacon's, observed earlier in this mission (throw the 120mm first). No
--     control yet: the AC-8 beacon is refused whole (it delivers natively).
-- Never written: any StratagemInfo (AC-8, 120mm), any component, projectile or bombardment record, the mission record,
-- the save, the account; only that one beacon's element.
local mod=hd2.mod()
local BUILD='0.3.0 BEACON TIMING'
mod:log('BeaconRedirectProof '..BUILD..' BUILD: put AC-8 Autocannon AND Orbital 120mm HE Barrage in your loadout, '
    ..'start a SOLO mission, wait for "BEACON REDIRECT READY". Then, one at a time and each to its end ("LIFECYCLE" '
    ..'lines): throw the 120mm (the control), then the AC-8. Watch for 120mm shells at the AC-8 beacon. Expect '
    ..'"BOMBARDMENT ... first shell" and "LIFECYCLE" lines for both. Timing mode: Mod Options > Beacon Redirect Proof. '
    ..'Ctrl+F12: status.')

local redirect=require('hd2runtime/runtime/beacon_redirect')
local world_module=require('hd2runtime/runtime/event_world')
local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
local loadout=require('hd2runtime/runtime/stratagem_loadout')
local catalog=require('hd2runtime/domains/stratagem_authoring')
local payload_module=require('hd2runtime/runtime/bombardment_payload')
local CARRIER,TARGET='AC-8 Autocannon','Orbital 120mm HE Barrage'
local ENTITY_WINDOW=30      -- seconds of new-entity observation after an activation
local LIFECYCLE_WAIT=60     -- seconds after an activation a lifecycle is reported at the latest

-- Names for stratagem types and payload hashes (every catalogued stratagem's payload list, in name order: a payload
-- such as a hellpod is shared by several stratagems).
local names_by_id,payload_users,sorted={},{},{}
for name in pairs(catalog.stratagems)do sorted[#sorted+1]=name end
table.sort(sorted)
for _,name in ipairs(sorted)do
    local root=catalog.stratagems[name].root
    if root then
        names_by_id[root.id]=name
        for k,hash in ipairs(root.payloads or{})do
            local key=(hash:upper():gsub('^0X','0x'))
            payload_users[key]=payload_users[key]or{}
            table.insert(payload_users[key],{name=name,k=k})
        end
    end
end
local CARRIER_PAYLOADS={}
for _,hash in ipairs(catalog.stratagems[CARRIER].root.payloads)do CARRIER_PAYLOADS[hash]=true end
local function type_name(world,kind)
    if kind==0 then return'type 0 (the empty default row)'end
    local id=world and loadout.id_of(world,kind)
    return ('%s (%d)'):format(id and names_by_id[id]or'uncatalogued',kind)
end
local function payload_name(hash)
    local users=payload_users[hash]
    if not users then return hash end
    local pick=users[1]
    for _,u in ipairs(users)do if u.name==CARRIER or u.name==TARGET then pick=u;break end end
    return ('%s (%s payload %d%s)'):format(hash,pick.name,pick.k,#users>1 and(', shared by '..#users..' stratagems')
        or'')
end
local function n3(v)return v and('%.3f'):format(v)or'?'end
local function n2(v)return v and('%.2f'):format(v)or'?'end

local options=hd2.options({id='beacon_redirect_proof',title='Beacon Redirect Proof',fallback='default'})
local timing_on=options:toggle({id='timing',label='Normalize the AC-8 beacon\'s timing to the native 120mm control',
    default=false,description='The timing proof: the AC-8 beacon\'s countdown and threshold are set, with its type, to '
        ..'those of a native 120mm beacon thrown earlier in this mission (throw the 120mm first). Read at mission start.'})
local neutral_on=options:toggle({id='neutral',label='Neutral redirect (type 0) instead of the 120mm',default=false,
    description='Only after a 120mm barrage was seen from the AC-8: the AC-8 beacon\'s type becomes 0 (nothing is '
        ..'spawned). Not with the timing option. Read at mission start.'})
local function settled(t)return t:describe().state~='pending'end
local function wanted(t)return settled(t)and t:get()==true and not t:disables()end

local M_={in_mission=false,armed=false,clock=0,windows={},beacons={}}

-------------------------------------------------------------------------------------------- the control timing --
-- The target timing: the latest native 120mm beacon's countdown and threshold as first seen in this mission.
local function control_timing()
    local c=M_.control
    if not c then
        return nil,'no native '..TARGET..' beacon was observed in this mission yet: throw one first (the control)'
    end
    return {countdown=c.countdown,threshold=c.threshold,source=('the native %s beacon %s (countdown %s, threshold %s)')
        :format(TARGET,tostring(c.entity),n3(c.countdown),n3(c.threshold))}
end

-------------------------------------------------------------------------------------------------- lifecycles --
-- Per beacon: {role, countdown, threshold, delay (first seen -> activation), at (the activation's clock), life (after
-- the activation), instances = {[entity] = {created, first, last, shells, ended}}}; reported once complete.
local function lifecycle(entity,role,first_countdown,first_threshold)
    local l=M_.beacons[entity]or{entity=entity,instances={}}
    l.role=l.role or role
    l.countdown,l.threshold=l.countdown or first_countdown,l.threshold or first_threshold
    M_.beacons[entity]=l
    return l
end
local function report_lifecycle(l,why)
    if l.reported then return end
    l.reported=true
    local parts={}
    for entity,i in pairs(l.instances)do
        local base=l.at or i.created
        local function rel(t)return t and base and n2((t-base)/1e6)..' s'or'?'end
        parts[#parts+1]=('barrage instance %d (%s): created %s, start delay %s s, first shell %s, last shell %s, %s '
            ..'shells fired, removed %s'):format(entity,payload_name(i.payload),rel(i.created),n2(i.delay),rel(i.first),
            rel(i.last),tostring(i.shells or i.fired or 0),i.ended and rel(i.ended)or'not yet')
    end
    table.sort(parts)
    mod:log(('LIFECYCLE: %s, beacon %s: countdown %s s, threshold %s s as first seen; activation %s s after first seen; '
        ..'beacon life after the activation %s; %s (times after the activation%s)'):format(l.role or'?',
        tostring(l.entity),n3(l.countdown),n3(l.threshold),n3(l.delay),l.life and(n3(l.life)..' s')or'still alive',
        #parts>0 and table.concat(parts,'; ')or'NO barrage instance attributed to it',why and('; '..why)or''))
end
local function maybe_report(l)
    if l.reported or not l.at then return end
    local open=false
    for _,i in pairs(l.instances)do if not i.ended then open=true end end
    if l.life and not open then report_lifecycle(l)end
end

-- After an activation: new entities with health (the AC-8's pod or weapon would show here), for 30 s.
local function observe(world)
    for k=#M_.windows,1,-1 do
        local w=M_.windows[k]
        local t=M_.clock-w.at
        local header=world_module.health_header(world,world.view.slot())
        if header then
            if header.live>w.live then
                for index=w.live,header.live-1 do
                    local d=world_module.descriptor(world,header,index)
                    local hash=d and('0x'..d.type)
                    if hash and not w.seen[hash]then
                        w.seen[hash]=true
                        mod:log(('OBSERVED: a new entity %d of type %s, %.1f s after beacon %s activated%s'):format(d.entity,
                            payload_name(hash),t,tostring(w.entity),CARRIER_PAYLOADS[hash]and(': the '..CARRIER
                            ..' delivery still ran')or''))
                    end
                end
            end
            w.live=header.live
        end
        if t>=ENTITY_WINDOW then table.remove(M_.windows,k)end
    end
    for _,l in pairs(M_.beacons)do
        if l.at_proof and not l.reported and M_.clock-l.at_proof>=LIFECYCLE_WAIT then
            report_lifecycle(l,('reported %d s after the activation'):format(LIFECYCLE_WAIT))
        end
    end
end
local function window_from(world,entity)
    local header=world_module.health_header(world,world.view.slot())
    M_.windows[#M_.windows+1]={entity=entity,at=M_.clock,live=header and header.live or 0,seen={}}
end

------------------------------------------------------------------------------------------------------ reports --
local function timing_line(world,e,role,thrower)
    local t=redirect.row_timing(world,thrower)
    local call_in=e.first_countdown and e.first_threshold and e.first_countdown-e.first_threshold
    mod:log(('CALL-IN TIMING: %s, beacon %s: countdown %s s, threshold %s s as first seen (the thrower\'s row: call-in '
        ..'+0x54 = %s s, linger +0x60 = %s s); call-in as applied (countdown - threshold) %s s; activation %s s / %d updates '
        ..'after first seen (%s); activation type %s'):format(role,tostring(e.entity),n3(e.first_countdown),
        n3(e.first_threshold),n3(t and t.callIn),n3(t and t.linger),n3(call_in),n3(e.seconds),e.updates,
        e.stateful and'first seen with state'or'first seen in flight',type_name(world,e.type)))
end
local function dispatch_line(world,e,prefix)
    local d,b0=e.dispatch,e.before
    if not d then
        mod:log(prefix..('DISPATCH: entity = %s: the dispatcher\'s record is unreadable'):format(tostring(e.entity)))
        return
    end
    local fresh=not b0 or b0.waves~=d.waves or b0.spawn~=d.spawn or b0.payload~=d.payload or b0.type~=d.type
    mod:log(prefix..('DISPATCH: entity = %s, the dispatcher\'s own record: type %s, payload %s, called %s, spawn requested = '
        ..'%s (state +0x8D8 = %d), waves spawned %s -> %d; %s'):format(tostring(e.entity),type_name(world,d.type),
        payload_name(d.payload),d.called==1 and'yes'or'no',d.requested and'yes'or'no',d.spawn,b0 and tostring(b0.waves)
        or'?',d.waves,not b0 and'(no baseline: no update saw its state before the activation)'or fresh
        and'written at this activation'or'UNCHANGED at this activation (an Eagle records nothing; type 0 spawns nothing)'))
end

local function report(e)
    local world=world_module.open()
    if e.kind=='armed'then
        local c,t=e.carrierTiming,e.targetTiming
        mod:log(('BEACON REDIRECT ARMED: carrier %s (type %d), target %s%s; mode %s. Rows (read-only): %s call-in %s s, '
            ..'linger %s s; %s'):format(e.carrier,e.carrierType,e.targetType==0
            and'type 0 (neutral: the empty default row)'or(e.target..' (type '..e.targetType..')'),e.package
            and('; requesting its call-in package '..e.package)or'',M_.mode,CARRIER,n3(c and c.callIn),n3(c and c.linger),
            t and(TARGET..' call-in '..n3(t.callIn)..' s, linger '..n3(t.linger)..' s')or'no target row'))
    elseif e.kind=='ready'then
        mod:log('BEACON REDIRECT READY: the target\'s call-in package is resident ('..tostring(e.package)..')'
            ..(M_.mode=='TIMING'and': throw the native 120mm first (the control), then the AC-8'or': throw now'))
    elseif e.kind=='created'then
        lifecycle(e.entity,CARRIER..' -> '..(M_.neutral and'type 0'or TARGET),e.countdown,e.threshold).thrower=e.type
        mod:log(('BEACON REDIRECT CREATED: %s, entity = %s, original type = %d, target type = %d; index %d, countdown %s, '
            ..'threshold %s, %s, first seen at update %d'):format(CARRIER,tostring(e.entity),e.type,M_.target_type or-1,
            e.index,n3(e.countdown),n3(e.threshold),e.mode==nil and'in flight (no state yet)'or('state mode '
            ..tostring(e.mode)..(e.counting and', counting'or'')),e.frame))
    elseif e.kind=='applied'then
        local v=e.verify
        local ok=v.type and v.others and v.nonTarget and v.protection and(not e.timing or(v.countdown and v.threshold))
        mod:log(('BEACON REDIRECT APPLIED: entity = %s, type %d -> %d, verified = %s (the type reads back %s; its other '
            ..'members unchanged %s; non-target bytes unchanged %s; protection restored %s; %d write%s), in update %d, the '
            ..'same update it was first seen'):format(tostring(e.entity),e.from,e.to,tostring(ok==true),tostring(v.type),
            tostring(v.others),tostring(v.nonTarget),tostring(v.protection),e.writes,e.writes==1 and''or's',e.frame))
        if e.timing then
            mod:log(('BEACON REDIRECT TIMING: entity = %s, countdown %s -> %s, threshold %s -> %s (call-in %s -> %s s), read '
                ..'back %s; the target: %s'):format(tostring(e.entity),n3(e.timing.from.countdown),n3(e.timing.to.countdown),
                n3(e.timing.from.threshold),n3(e.timing.to.threshold),n3(e.timing.from.countdown-e.timing.from.threshold),
                n3(e.timing.to.countdown-e.timing.to.threshold),tostring(v.countdown and v.threshold),
                tostring(e.timing.source)))
        end
    elseif e.kind=='refused'then
        mod:log(('BEACON REDIRECT REFUSED%s (nothing written; the beacon goes on natively): %s: %s'):format(
            e.entity and(' for entity '..tostring(e.entity))or'',tostring(e.code),tostring(e.reason)))
    elseif e.kind=='missed'then
        mod:log(('BEACON REDIRECT MISSED WINDOW: entity %s: %s (nothing written)'):format(tostring(e.entity),e.reason))
    elseif e.kind=='reverted'then
        mod:log(('BEACON REDIRECT REVERTED: entity %s: its type is %d again before activation (update %d)'):format(
            tostring(e.entity),e.value,e.frame))
    elseif e.kind=='activated'then
        local l=lifecycle(e.entity,nil,e.first_countdown,e.first_threshold)
        if e.n==1 then l.at,l.at_proof,l.delay=e.clock,M_.clock,e.seconds end
        mod:log(('BEACON REDIRECT ACTIVATED: entity = %s, activation type = %s, original type = %s, redirected = %s, '
            ..'%d updates after first seen%s%s'):format(tostring(e.entity),type_name(world,e.type),CARRIER,
            tostring(e.redirected),e.updates,e.applied and''or' (not redirected: it activated natively)',
            e.n>1 and(', activation '..e.n)or''))
        if world then
            timing_line(world,e,CARRIER..(e.redirected and(' redirected to '..type_name(world,e.type))or''),l.thrower)
            dispatch_line(world,e,'BEACON REDIRECT ')
            if e.n==1 then window_from(world,e.entity)end
        end
    elseif e.kind=='gone'then
        local l=lifecycle(e.entity)
        l.life=e.after
        mod:log(('BEACON REDIRECT: beacon %s gone (%s, %s): %s s after first seen, %s s after its activation'):format(
            tostring(e.entity),e.activated and'activated'or'NOT seen activated',e.applied and'redirected'or'not redirected',
            n3(e.seconds),n3(e.after)))
        maybe_report(l)
    elseif e.kind=='observed'and world then
        -- Any other beacon: read-only. A native 120mm's timers become the timing mode's target.
        if e.phase=='created'then
            lifecycle(e.entity,'native '..type_name(world,e.type),e.countdown,e.threshold).thrower=e.type
            mod:log(('BEACON OBSERVED (read-only, not redirected): %s, entity %s: countdown %s, threshold %s, %s'):format(
                type_name(world,e.type),tostring(e.entity),n3(e.countdown),n3(e.threshold),e.mode==nil and'in flight'
                or'with state'))
            if e.type==M_.target_type and not e.activated and e.countdown and e.threshold then
                M_.control={entity=e.entity,countdown=e.countdown,threshold=e.threshold}
                mod:log(('BEACON TIMING CONTROL: native %s beacon %s: countdown %s s, threshold %s s (call-in %s s)%s')
                    :format(TARGET,tostring(e.entity),n3(e.countdown),n3(e.threshold),n3(e.countdown-e.threshold),
                    M_.mode=='TIMING'and': the target timing for the next AC-8 beacon'or''))
            end
        elseif e.phase=='activated'then
            local l=lifecycle(e.entity,nil,e.first_countdown,e.first_threshold)
            if e.n==1 then l.at,l.at_proof,l.delay=e.clock,M_.clock,e.seconds end
            timing_line(world,e,'native '..type_name(world,e.type)..' (not redirected)',l.thrower)
            dispatch_line(world,e,'BEACON OBSERVED ')
            if e.n==1 then window_from(world,e.entity)end
        elseif e.phase=='gone'then
            local l=lifecycle(e.entity)
            l.life=e.after
            mod:log(('BEACON OBSERVED: %s, entity %s gone %s s after first seen, %s s after its activation'):format(
                type_name(world,e.type),tostring(e.entity),n3(e.seconds),n3(e.after)))
            maybe_report(l)
        end
    elseif e.kind=='bombardment'then
        -- A barrage instance, attributed to the beacon(s) that activated in its update.
        local owners={}
        for _,entity in ipairs(e.beacons or{})do owners[#owners+1]=tostring(entity)end
        local owner_text=#owners>0 and('beacon '..table.concat(owners,', '))or'no beacon activated in its update'
        if e.phase=='created'then
            for _,entity in ipairs(e.beacons or{})do
                lifecycle(entity).instances[e.entity]={payload=e.payload,created=e.clock,delay=e.startDelay}
            end
            mod:log(('BOMBARDMENT: instance %d (%s) created in the update %s activated: start delay %s s, %s salvos, aim '
                ..'(%s, %s, %s)'):format(e.entity,payload_name(e.payload),owner_text,n2(e.startDelay),tostring(e.salvos),
                n2(e.aim and e.aim[1]),n2(e.aim and e.aim[2]),n2(e.aim and e.aim[3])))
        elseif e.phase=='fired'then
            for _,entity in ipairs(e.beacons or{})do
                local i=lifecycle(entity).instances[e.entity]
                if i then i.first=e.clock end
            end
            mod:log(('BOMBARDMENT: instance %d (%s): FIRST SHELL %s s after it was created (%s)'):format(e.entity,
                payload_name(e.payload),n2(e.after),owner_text))
        elseif e.phase=='ended'then
            for _,entity in ipairs(e.beacons or{})do
                local l=lifecycle(entity)
                local i=l.instances[e.entity]
                if i then
                    i.ended,i.shells=e.clock,e.shells
                    i.last=e.last and i.created and i.created+e.last*1e6
                end
                maybe_report(l)
            end
            mod:log(('BOMBARDMENT: instance %d (%s) removed %s s after it was created: %s shells fired, first %s s, last %s s '
                ..'(%s)'):format(e.entity,payload_name(e.payload),n2(e.life),tostring(e.shells),n2(e.first),n2(e.last),
                owner_text))
        end
    elseif e.kind=='ended'then
        mod:log('BEACON REDIRECT: watch ended: '..tostring(e.reason))
    end
end

local function arm(world)
    if not(settled(neutral_on)and settled(timing_on))then return end
    M_.armed=true
    M_.neutral=wanted(neutral_on)and not wanted(timing_on)
    M_.mode=wanted(timing_on)and'TIMING'or M_.neutral and'NEUTRAL (type 0)'or'TYPE ONLY'
    M_.carrier_type=redirect.type_of(world,CARRIER)
    M_.target_type=redirect.type_of(world,TARGET)
    local record=slots.local_record(world)
    local spec={carrier=CARRIER,observe=true}
    if M_.neutral then spec.neutral=true else spec.target=TARGET end
    if M_.mode=='TIMING'then spec.timing=control_timing end
    local watch,why=redirect.arm(spec,report)
    mod:log(('MISSION START: %s; %s stratagem record(s) on this machine (solo: 1); mode %s%s'):format(watch and
        'the redirect is armed'or('the redirect could not be armed: '..tostring(why)),tostring(record and record.records),
        M_.mode,wanted(neutral_on)and wanted(timing_on)and' (neutral ignored: the timing option needs the 120mm)'or''))
end

hd2.every(0.1,function()
    M_.clock=M_.clock+0.1
    local world=world_module.open()
    if not world then return end
    local state=hd2.game_state()
    local mission=state and state.mission
    if mission and not M_.in_mission then
        M_.in_mission,M_.armed,M_.windows,M_.beacons,M_.control=true,false,{},{},nil
    elseif not mission and M_.in_mission then
        M_.in_mission=false
        if redirect.armed()then redirect.disarm()end
        for _,l in pairs(M_.beacons)do if l.at then report_lifecycle(l,'the mission ended')end end
        mod:log('MISSION END: the redirect is disarmed; nothing to restore (only consumed beacons were written)')
    end
    if mission then
        if not M_.armed then arm(world)end
        observe(world)
    end
end,{id='beacon-redirect-proof'})

hd2.input.bind('beacon_redirect_proof.status',{key='Ctrl+F12',on_press=function()
    local world=world_module.open()
    local list=world and redirect.beacons(world)
    local parts={}
    for entity,it in pairs(list or{})do
        parts[#parts+1]=('entity %s type %d countdown %s threshold %s counting %s activated %s mode %s'):format(
            tostring(entity),it.type,n3(it.countdown),n3(it.threshold),tostring(it.counting),tostring(it.activated),
            tostring(it.mode))
    end
    local bombs=world and payload_module.prove(world)and redirect.bombardment(world)
    local barrages={}
    for _,i in ipairs(bombs and bombs.list or{})do
        barrages[#barrages+1]=('%d %s fired %s left %s salvos %s'):format(i.entity,i.payload,tostring(i.fired),
            tostring(i.left),tostring(i.salvos))
    end
    mod:log(('Ctrl+F12 [%s]: armed %s, mode %s, control %s; beacons: %s; barrages: %s'):format(BUILD,
        tostring(redirect.armed()),tostring(M_.mode),M_.control and tostring(M_.control.entity)or'none',
        #parts>0 and table.concat(parts,'; ')or'none',#barrages>0 and table.concat(barrages,'; ')or'none'))
end})
mod:log('loaded ('..BUILD..'): carrier '..CARRIER..' -> '..TARGET..'; type-only by default, timing by option; every '
    ..'beacon and barrage observed read-only; Ctrl+F12 status')
