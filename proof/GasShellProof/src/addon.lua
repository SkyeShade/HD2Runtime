local hd2=require('mods/skyeshade/hd2runtime')
-- GasShellProof 0.1.0: RUNTIME GAS SHELLS (runtime/bombardment_executor.lua, runtime/beacons.lua;
-- research/docs/beacon-redirect-F5FEE03DCFDB.md, "The Runtime bombardment executor"). Development only; solo host; no
-- multiplayer change; not part of the Gas Barrage (the existing Gas Barrage stays the fallback).
--     throw an AC-8 Autocannon beacon
--         -> its delivery becomes 'none' in its first update (the empty default row: no pod, nothing spawned)
--         -> when it activates, the Runtime fires the Orbital 120mm HE Barrage's pattern (5 salvos of 3, 0.75 s between
--            shells, 2.0 s between salvos, a +-27 m square scatter) as the Orbital Gas Strike's shell 197, at the
--            beacon's position, through the game's own projectile wrapper from your avatar
--         -> shell 197's own chain: explosion 82, the gas cloud, gas and confusion.
-- Written: only that beacon's type (one guarded write). Nothing else: no 120mm or Gas Strike record, no shell,
-- explosion or status row. Read-only: the game's projectile pool (each shell 197 it really spawned).
-- Known differences from a native 120mm barrage (logged at start): see runtime/bombardment_executor.lua DIFFERENCES.
local mod=hd2.mod()
local BUILD='0.1.0 RUNTIME GAS SHELLS'
mod:log('GasShellProof '..BUILD..' BUILD: put AC-8 Autocannon in your loadout, start a SOLO mission, wait for '
    ..'"GAS SHELLS READY", throw the AC-8 once, then STAND STILL until "GAS SHELLS RESULT". Expect no AC-8 pod and 15 '
    ..'gas shells around the beacon: gas clouds, enemies coughing and confused. Ctrl+F12: status.')

local beacons=require('hd2runtime/runtime/beacons')
local executor=require('hd2runtime/runtime/bombardment_executor')
local world_module=require('hd2runtime/runtime/event_world')
local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
local CARRIER,SHELL_DONOR,PATTERN='AC-8 Autocannon','Orbital Gas Strike','Orbital 120mm HE Barrage'
local SHELL=197

local M_={in_mission=false,armed=false,clock=0,barrages={}}
local function n1(v)return v and('%.1f'):format(v)or'?'end
local function vec(v)return v and('(%.1f, %.1f, %.1f)'):format(v.x,v.y,v.z)or'?'end

------------------------------------------------------------------------------------------- the projectile pool --
-- Read-only: the shells 197 the game really spawned since the barrage started.
local function pool(world,b)
    if not b.counter then return end
    local now,system=world_module.projectile_counter(world)
    if not now or now==b.counter then return end
    local count=math.min((now-b.counter)%4294967296,2048)
    local list=world_module.projectile_types(world,system,b.counter,count)
    b.counter=now
    for _,item in ipairs(list or{})do
        if item.type==SHELL then
            b.pooled=b.pooled+1
            if b.pooled==1 then
                local slot=world_module.projectile_slot(world,system,item.slot)
                mod:log(('GAS SHELLS POOL: the first shell %d in the game\'s projectile pool (slot %d): position %s, velocity '
                    ..'%s, speed %s, lifetime %s, source %s, owner %s'):format(SHELL,item.slot,vec(slot and slot.position),
                    vec(slot and slot.velocity),n1(slot and slot.speed),n1(slot and slot.lifetime),
                    tostring(slot and slot.source),tostring(slot and slot.owner)))
            end
        end
    end
end

---------------------------------------------------------------------------------------------- the barrage --
local function start(world,entity,position)
    local b={entity=entity,pooled=0,fired=0,at=M_.clock}
    b.counter=world_module.projectile_counter(world)
    local h,code,why=executor.start({shell=SHELL,shell_donor=SHELL_DONOR,pattern=PATTERN,target=position,
        label='gas shells for beacon '..tostring(entity)},function(e)
        if e.kind=='started'then
            local p=e.pattern
            mod:log(('GAS SHELLS STARTED for beacon %s at %s: shell %d, %d salvos of %d, %.2f s between shells, %.2f s '
                ..'between salvos, scatter +-%.1f m, origin %.0f m above each aim'):format(tostring(entity),vec(position),
                e.shell,p.salvos,p.shells_per_salvo,p.shell_delay,p.salvo_delay,p.scatter,p.distance or 3000))
            for k,d in ipairs(executor.DIFFERENCES)do mod:log(('GAS SHELLS DIFFERENCE %d: %s'):format(k,d))end
        elseif e.kind=='shell'then
            b.fired=e.n
            mod:log(('GAS SHELL %d (salvo %d) at %.2f s: aim %s'):format(e.n,e.salvo,e.seconds,vec(e.aim)))
        elseif e.kind=='ended'or e.kind=='refused'then
            b.done=M_.clock
            b.outcome=e.kind=='ended'and('ended: '..e.shells..' shells in '..e.salvos..' salvos over '..n1(e.seconds)..' s')
                or('REFUSED '..tostring(e.code)..': '..tostring(e.reason)..' after '..tostring(e.shells)..' shells')
        end
    end)
    if not h then
        mod:log(('GAS SHELLS REFUSED for beacon %s (nothing fired): %s: %s'):format(tostring(entity),tostring(code),
            tostring(why)))
        return
    end
    M_.barrages[#M_.barrages+1]=b
end

local function report(e)
    local world=world_module.open()
    if e.kind=='ready'then
        mod:log('GAS SHELLS READY: the '..SHELL_DONOR..' call-in package is resident: throw '..CARRIER..' now')
    elseif e.kind=='created'and not e.observed then
        mod:log(('GAS SHELLS BEACON CREATED: %s, entity %s'):format(e.beacon.carrier,tostring(e.beacon.entity)))
    elseif e.kind=='applied'then
        local r=e.result
        mod:log(('GAS SHELLS BEACON NEUTRALIZED: entity %s, delivery %s -> %s, verified %s, %d write'):format(
            tostring(e.entity),r.delivery.from_name,r.delivery.to_name,tostring(r.verified),r.writes))
    elseif e.kind=='refused'then
        mod:log(('GAS SHELLS BEACON REFUSED%s (nothing written; it delivers natively): %s: %s'):format(e.entity
            and(' for entity '..tostring(e.entity))or'',tostring(e.code),tostring(e.reason)))
    elseif e.kind=='activated'and not e.observed then
        local d=e.dispatch
        mod:log(('GAS SHELLS BEACON ACTIVATED: entity %s, delivery %s, %.2f s after first seen; the dispatcher: spawn '
            ..'requested %s'):format(tostring(e.entity),e.delivery,e.seconds or-1,d and(d.requested and'YES'or'no')
            or'unreadable'))
        if e.delivery~='none'then
            mod:log('GAS SHELLS: the beacon was not neutralized: no gas shells')
            return
        end
        local position=world and beacons.position(world,e.entity)
        if not position then
            mod:log('GAS SHELLS REFUSED: the beacon position is unreadable (nothing fired)')
            return
        end
        start(world,e.entity,position)
    end
end

local function arm(world)
    M_.armed=true
    local watch,why=beacons.watch({carrier=CARRIER,prepare={SHELL_DONOR},decide=function()return {delivery='none'}end},
        report)
    local record=slots.local_record(world)
    mod:log(('MISSION START: %s; %s stratagem record(s) on this machine (solo: 1)'):format(watch and
        'the gas shell watch is armed'or('the watch could not be armed: '..tostring(why)),
        tostring(record and record.records)))
end

hd2.every(0.1,function()
    M_.clock=M_.clock+0.1
    local world=world_module.open()
    if not world then return end
    local state=hd2.game_state()
    local mission=state and state.mission
    if mission and not M_.in_mission then
        M_.in_mission,M_.armed,M_.barrages=true,false,{}
    elseif not mission and M_.in_mission then
        M_.in_mission=false
        mod:log('MISSION END: nothing to restore (only a consumed beacon was written)')
    end
    if mission then
        if not M_.armed then arm(world)end
        for k=#M_.barrages,1,-1 do
            local b=M_.barrages[k]
            pool(world,b)
            if b.done and M_.clock-b.done>=8 then   -- the last shells' flight (3000 m at 400 m/s) observed too
                mod:log(('GAS SHELLS RESULT for beacon %s: %s; the game\'s projectile pool shows %d shell(s) %d'):format(
                    tostring(b.entity),b.outcome,b.pooled,SHELL))
                table.remove(M_.barrages,k)
            end
        end
    end
end,{id='gas-shell-proof'})

hd2.input.bind('gas_shell_proof.status',{key='Ctrl+F12',on_press=function()
    local parts={}
    for _,b in ipairs(M_.barrages)do
        parts[#parts+1]=('beacon %s: fired %d, pooled %d'):format(tostring(b.entity),b.fired,b.pooled)
    end
    mod:log(('Ctrl+F12 [%s]: barrages: %s'):format(BUILD,#parts>0 and table.concat(parts,'; ')or'none'))
end})
mod:log('loaded ('..BUILD..'): carrier '..CARRIER..' neutralized; shell '..SHELL..' in the '..PATTERN..' pattern; '
    ..'Ctrl+F12 status')
