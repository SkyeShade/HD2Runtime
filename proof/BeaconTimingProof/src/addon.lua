local hd2=require('mods/skyeshade/hd2runtime')
-- BeaconTimingProof 0.1.0: THE BEACON TIMING API (runtime/beacons.lua; docs/research/beacon-redirect-F5FEE03DCFDB.md,
-- "The beacon API"). Development only; solo host; no multiplayer change; not part of the Gas Barrage.
-- What the API sets, per beacon, semantically:
--     call_in_time              = countdown - activation threshold (the time to the activation, once landed)
--     lifetime_after_activation = the activation threshold (how long the beacon remains after its activation)
-- Default mode (AC-8 Autocannon, delivery left native; strongly differentiated values):
--     1. its first update:  call-in 6.0 s (natively about 0 to 2.4 s), lifetime kept;
--     2. 2 s later:         lifetime after activation 15.0 s (natively 8.7 s), the remaining call-in kept;
--     3. after activation:  one more change is attempted and must be REFUSED (ACTIVATED), nothing written.
--     Expect the AC-8 pod about 6 s after the beacon landed, and the beam about 15 s after that.
-- Option "120mm with the native 120mm's timing": in its first update the AC-8 beacon gets the delivery Orbital 120mm HE
-- Barrage AND call-in 4.0 s and lifetime 22.4 s (a native 120mm's), in one transaction; the 120mm barrage is observed.
-- Each change is one guarded transaction on that beacon's element only; nothing else is written.
local mod=hd2.mod()
local BUILD='0.1.0 BEACON TIMING API'
mod:log('BeaconTimingProof '..BUILD..' BUILD: put AC-8 Autocannon in your loadout, start a SOLO mission, wait for '
    ..'"BEACON TIMING READY", throw the AC-8 once and wait for its "TIMING RESULT" line. Default: call-in 6 s, then '
    ..'lifetime after activation 15 s (the pod about 6 s after landing; the beam about 15 s after that). Option (Mod '
    ..'Options > Beacon Timing Proof): 120mm delivery with a native 120mm\'s timing. Ctrl+F12: status.')

local beacons=require('hd2runtime/runtime/beacons')
local redirect=require('hd2runtime/runtime/beacon_redirect')
local world_module=require('hd2runtime/runtime/event_world')
local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
local CARRIER,TARGET='AC-8 Autocannon','Orbital 120mm HE Barrage'
local CALL_IN,LIFETIME,LATER=6.0,15.0,2.0
local CALL_IN_120,LIFETIME_120=4.0,22.4

local options=hd2.options({id='beacon_timing_proof',title='Beacon Timing Proof',fallback='default'})
local target_on=options:toggle({id='delivery_120mm',label='120mm delivery with a native 120mm\'s timing',default=false,
    description='The AC-8 beacon gets the Orbital 120mm HE Barrage delivery and a call-in of 4.0 s and a lifetime after '
        ..'activation of 22.4 s in one transaction. Read at mission start.'})
local function settled(t)return t:describe().state~='pending'end
local function wanted(t)return settled(t)and t:get()==true and not t:disables()end
local function n3(v)return v and('%.3f'):format(v)or'?'end

local M_={in_mission=false,armed=false,clock=0,beacons={},barrages={}}

------------------------------------------------------------------------------------------------- the barrage --
-- Read-only: barrage instances by entity (their own counters, logged as read at creation).
local function barrages(world)
    local list=redirect.prove(world)and redirect.bombardment(world)
    if not list then return end
    local seen={}
    for _,i in ipairs(list.list)do
        seen[i.entity]=true
        local s=M_.barrages[i.entity]
        if not s then
            s={created=M_.clock,fired0=i.fired,fired=i.fired,salvos0=i.salvos,left0=i.left,baseline=M_.first_read==nil}
            M_.barrages[i.entity]=s
            if not s.baseline then
                mod:log(('BARRAGE: instance %d (%s) created: start delay %s s, counters at creation: shells fired %s, '
                    ..'shells left %s, salvos left %s'):format(i.entity,i.payload,n3(i.salvoTimer),tostring(i.fired),
                    tostring(i.left),tostring(i.salvos)))
            end
        elseif not s.baseline and i.fired and s.fired and i.fired~=s.fired then
            s.first=s.first or M_.clock
            s.last=M_.clock
            s.fired=i.fired
        end
    end
    M_.first_read=true
    for entity,s in pairs(M_.barrages)do
        if not seen[entity]then
            M_.barrages[entity]=nil
            if not s.baseline then
                mod:log(('BARRAGE: instance %d removed %.1f s after it was created: shells fired %s (counter %s -> %s), '
                    ..'first shell %s s, last shell %s s'):format(entity,M_.clock-s.created,tostring((s.fired or 0)
                    -(s.fired0 or 0)),tostring(s.fired0),tostring(s.fired),s.first and('%.1f'):format(s.first-s.created)
                    or'?',s.last and('%.1f'):format(s.last-s.created)or'?'))
            end
        end
    end
end

------------------------------------------------------------------------------------------------------ events --
local function timing_text(t)
    return ('call-in %s s, lifetime after activation %s s (countdown %s, activation threshold %s)'):format(
        n3(t.call_in_time),n3(t.lifetime_after_activation),n3(t.countdown),n3(t.activation_threshold))
end
local function report(e)
    if e.kind=='ready'then
        mod:log('BEACON TIMING READY: throw '..CARRIER..' now (mode '..M_.mode..')')
    elseif e.kind=='created'then
        local bn=e.beacon
        if e.observed then
            mod:log(('BEACON TIMING OBSERVED (not changed): %s, entity %s: %s'):format(bn.carrier,tostring(bn.entity),
                timing_text(bn.timing)))
            return
        end
        M_.beacons[bn.entity]={first=M_.clock,created=bn.timing,landed=bn.landed}
        mod:log(('BEACON TIMING CREATED: %s, entity %s, %s; as created: %s'):format(bn.carrier,tostring(bn.entity),
            bn.landed and'landed'or'in flight',timing_text(bn.timing)))
    elseif e.kind=='applied'then
        local r=e.result
        local s=M_.beacons[e.entity]
        if s then s.applied=r end
        mod:log(('BEACON TIMING APPLIED (first update): entity %s%s; %s -> %s; verified %s (read back, other members '
            ..'unchanged %s, non-target bytes unchanged %s, protection restored %s), %d write%s'):format(tostring(e.entity),
            r.delivery and(', delivery '..r.delivery.from_name..' -> '..r.delivery.to_name)or'',timing_text(r.timing.from),
            timing_text(r.timing.to),tostring(r.verified),tostring(r.verify.others),tostring(r.verify.nonTarget),
            tostring(r.verify.protection),r.writes,r.writes==1 and''or's'))
    elseif e.kind=='refused'then
        mod:log(('BEACON TIMING REFUSED%s (nothing written): %s: %s'):format(e.entity and(' for entity '..tostring(e.entity))
            or'',tostring(e.code),tostring(e.reason)))
    elseif e.kind=='activated'then
        local s=M_.beacons[e.entity]
        if e.observed or not s then return end
        s.activated=M_.clock
        s.delay=e.seconds
        s.expected_after=s.later_life or(s.applied and s.applied.timing and s.applied.timing.to.lifetime_after_activation)
        mod:log(('BEACON TIMING ACTIVATED: entity %s, delivery %s, %s s after first seen (%s)'):format(tostring(e.entity),
            e.delivery,n3(e.seconds),s.landed and'it had landed when first seen'
            or'first seen in flight: the call-in runs only once it has landed'))
        -- The guard, live: a change after the activation must be refused and write nothing.
        local world=world_module.open()
        local list=world and redirect.beacons(world)
        local it=list and list[e.entity]
        if world and it then
            local ok,code,why=beacons.apply(world,e.entity,{type=it.type,timers=it.raw:sub(1,8)},{call_in_time=1})
            mod:log(('BEACON TIMING GUARD: a change after the activation: %s'):format(ok and'APPLIED (UNEXPECTED)'
                or('refused '..tostring(code)..': '..tostring(why))))
        end
    elseif e.kind=='gone'then
        local s=M_.beacons[e.entity]
        if e.observed or not s then return end
        M_.beacons[e.entity]=nil
        local wanted_call=s.applied and s.applied.timing and s.applied.timing.to.call_in_time
        mod:log(('TIMING RESULT: entity %s: activation %s s after first seen (set call-in %s s%s); the beacon remained %s s '
            ..'after its activation (set lifetime %s s)'):format(tostring(e.entity),n3(s.delay),n3(wanted_call),
            s.landed and''or', plus the flight before it landed',n3(e.after),n3(s.expected_after)))
    end
end

------------------------------------------------------------------------------------- the later timing write --
-- Mode A, step 2: 2 s after the first update, the lifetime after activation, keeping the remaining call-in.
local function later(world)
    if M_.mode~='TIMING'then return end
    local list
    for entity,s in pairs(M_.beacons)do
        if s.applied and not s.later_done and not s.activated and M_.clock-s.first>=LATER then
            s.later_done=true
            list=list or redirect.beacons(world)
            local it=list and list[entity]
            if not it then
                mod:log('BEACON TIMING LATER: entity '..tostring(entity)..' is gone')
            else
                local r,code,why=beacons.apply(world,entity,{type=it.type,timers=it.raw:sub(1,8)},
                    {lifetime_after_activation=LIFETIME})
                if r then
                    s.later_life=r.timing.to.lifetime_after_activation
                    mod:log(('BEACON TIMING APPLIED (%.1f s later, before its activation): entity %s; %s -> %s; verified %s, '
                        ..'%d write%s'):format(M_.clock-s.first,tostring(entity),timing_text(r.timing.from),
                        timing_text(r.timing.to),tostring(r.verified),r.writes,r.writes==1 and''or's'))
                else
                    mod:log(('BEACON TIMING LATER REFUSED for entity %s (nothing written): %s: %s'):format(tostring(entity),
                        tostring(code),tostring(why)))
                end
            end
        end
    end
end

local function arm(world)
    if not settled(target_on)then return end
    M_.armed=true
    M_.mode=wanted(target_on)and'120MM'or'TIMING'
    local spec={carrier=CARRIER}
    if M_.mode=='120MM'then
        spec.prepare={TARGET}
        spec.decide=function()return {delivery=TARGET,call_in_time=CALL_IN_120,lifetime_after_activation=LIFETIME_120}end
    else
        spec.decide=function()return {call_in_time=CALL_IN}end
    end
    local watch,why=beacons.watch(spec,report)
    local record=slots.local_record(world)
    mod:log(('MISSION START: %s; %s stratagem record(s) on this machine (solo: 1); mode %s (%s)'):format(watch
        and'the beacon timing watch is armed'or('the watch could not be armed: '..tostring(why)),
        tostring(record and record.records),M_.mode,M_.mode=='120MM'and('delivery '..TARGET..', call-in '..CALL_IN_120
        ..' s, lifetime '..LIFETIME_120..' s')or('call-in '..CALL_IN..' s, then lifetime '..LIFETIME..' s')))
end

hd2.every(0.1,function()
    M_.clock=M_.clock+0.1
    local world=world_module.open()
    if not world then return end
    local state=hd2.game_state()
    local mission=state and state.mission
    if mission and not M_.in_mission then
        M_.in_mission,M_.armed,M_.beacons,M_.barrages,M_.first_read=true,false,{},{},nil
    elseif not mission and M_.in_mission then
        M_.in_mission=false
        mod:log('MISSION END: nothing to restore (only consumed beacons were written)')
    end
    if mission then
        if not M_.armed then arm(world)end
        later(world)
        barrages(world)
    end
end,{id='beacon-timing-proof'})

hd2.input.bind('beacon_timing_proof.status',{key='Ctrl+F12',on_press=function()
    local world=world_module.open()
    local list=world and redirect.beacons(world)
    local parts={}
    for entity,it in pairs(list or{})do
        parts[#parts+1]=('entity %s type %d %s activated %s'):format(tostring(entity),it.type,
            timing_text(beacons.timing_of(it)),tostring(it.activated))
    end
    mod:log(('Ctrl+F12 [%s]: mode %s; beacons: %s'):format(BUILD,tostring(M_.mode),#parts>0 and table.concat(parts,'; ')
        or'none'))
end})
mod:log('loaded ('..BUILD..'): carrier '..CARRIER..'; Ctrl+F12 status')
