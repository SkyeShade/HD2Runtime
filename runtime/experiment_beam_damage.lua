-- PER-WEAPON BEAM DAMAGE for the MULTI-WEAPON BEAM SWAP EXPERIMENT (EXPERIMENTAL, SOLO ONLY; branch exp/multi-beam,
-- never the 0.30.x line). The AR-23 Liberator, LAS-58 Talon and SMG-32 Reprimand that runtime/experiment_beam_swap.lua
-- swapped all fire ONE BeamWeapon record (23, the Trident's copy) and so one BeamType (6) and one DamageInfo row (508),
-- the real LAS-13 Trident's. This module gives each of them its own damage and armour penetration without touching any
-- row (research/docs/beam-damage-per-weapon-F5FEE03DCFDB.md, research/beam-damage-per-weapon-F5FEE03DCFDB.json;
-- domains/beam_swap.lua `damage`):
--   * every beam shot is one 0x168-byte entry of the beam system's 64-entry ring (S = [game+0x347CED0] = world +
--     0x2563C48; entry E = S + 0x170 + slot x 0x168). BeamFire (0x13B8410, in the entity component update) COPIES its
--     BeamInfo row into it: E+0x34 the DamageInfo id, E+0x24 / +0x28 the damage multipliers (near / far of the
--     falloff), E+0x2C / +0x30 the penetration multipliers; E+0x54 is the firing WEAPON entity.
--   * the hit processing (0x13BB240) reads only those copies: per hit event +0x98 (standard x (1 - D) + durable x D of
--     DamageInfo [E+0x34]) x the damage multiplier, the four penetration lanes x the penetration multiplier; the
--     Trident's pulse row applies it once (kind 3) and sets E+0x161. Nothing else writes or reads them (the census).
--   * a new entry's rays are submitted at the NEXT world update (0x13BAE20 at 0xAB55AF runs before the component
--     update), so the shot cannot hit before the next world update: a Lua update between two world updates sees it
--     unhit. Projectiles follow the same submit / fire / process order, and the live-proven per-shot projectile writes
--     saw every shot at 0.00 m travelled (STRONG for beams, not live-proven; each write logs the entry's ray state).
-- So, per configured weapon, each update reads the ring and writes each NEW entry of that weapon ONCE, in one guarded
-- transaction over the entry (private read-write memory, the exact entry bytes just read as context, a read-back):
-- E+0x24/+0x28 := the row's x the damage multiplier, E+0x2C/+0x30 := the row's x the penetration multiplier and, with a
-- damage row, E+0x34 := that row's id. Before-bytes: the entry's copies must equal the live BeamInfo row 6 (untouched
-- since BeamFire) and E+0x161 must be 0 (not yet applied); otherwise the shot stays as it is and is counted.
-- Independence: only entries whose weapon entity is of the configured type are written. The real Trident (another
-- entity type), every BeamInfo row, every DamageInfo row and the weapons' records are never written. There is nothing
-- to restore: an entry lives for one pulse and BeamFire zeroes and refills it for the next shot.
-- Gates: a weapon is configured only while its swap is applied (experiment_beam_swap.restore forgets it); in a mission;
-- solo (several players: the shot stays vanilla); every pin of the research proven once per game.dll; a damage row
-- other than the Trident's needs its weapon's package resident (its status effect). NOT LIVE-PROVEN.
if rawget(_G,'jit')then jit.off(true,true)end
local world_module=require('hd2runtime/runtime/event_world')
local transaction=require('hd2runtime/core/guarded_transaction')
local scheduler=require('hd2runtime/runtime/scheduler')
local metrics=require('hd2runtime/runtime/metrics')
local log_module=require('hd2runtime/runtime/log')
local b=require('hd2runtime/core/bytes')
local profile=require('hd2runtime/schemas/current')
local D=require('hd2runtime/domains/beam_swap')
local G=D.damage
local M={}
M.VERSION='0.1.0-experimental'
local E,RING,ROW=G.entry,G.ring,G.beamTable.members
local PRIVATE,COMMIT,READWRITE=0x20000,0x1000,0x4
local BY,BY_RESOURCE={},{}
for _,w in ipairs(D.weapons)do BY[w.id]=w;BY_RESOURCE[w.resource:sub(3):upper()]=w end
local DONOR={}
M.DONORS={}
for _,d in ipairs(G.donors)do DONOR[d.label]=d;M.DONORS[#M.DONORS+1]=d.label end
M.WEAPONS={}
for _,id in ipairs(D.order)do M.WEAPONS[#M.WEAPONS+1]=id end
M.LIMITS=G.limits
M.OFF_MISSION_EVERY=0.5

local configs={}            -- weapon id -> config
local by_type={}            -- entity type (16 hex digits) -> config
local proven={}             -- world key -> true | reason
local memo={}               -- ring slot -> {key, state}: each shot is handled once
local hooks={}
local watch
local clock,in_mission,off_mission_at=0,false,-math.huge
local unavailable_logged

local function log(text)log_module.emit('MULTI BEAM DAMAGE: '..text)end
local function detail(text)log_module.detail('MULTI BEAM DAMAGE: '..text)end
local function f32(bytes,offset)
    local n=b.u32(bytes,offset)
    if math.floor(n/8388608)%256==255 then return nil end
    return b.value(bytes,offset,'f32')
end
local function fmt(v)return v and('%g'):format(v)or'?'end

-- The research's pins (code bytes and the DamageValues jump table), once per loaded game.dll.
local function prove(world)
    local key=world.key
    if proven[key]==true then return true end
    if proven[key]then return nil,proven[key]end
    local why
    if G.source.gameDllSha256~=profile.dll_sha then why='the beam damage research covers another game.dll build'end
    for _,pin in ipairs(G.pins)do
        if not why and not world.view.proves(world.game+pin.rva,pin.hex)then
            why=('native code not as reviewed at game.dll+0x%X (%s)'):format(pin.rva,pin.label)
        end
    end
    proven[key]=why or true
    if why then return nil,why end
    return true
end

-- S, proven to be the world's own beam system (the hit processing's rcx and BeamFire's global agree).
local function beam_system(world)
    local system=world.view.pointer(world.game+G.system.global)
    local w=world.view.pointer(world.game+G.system.world)
    if not(system and w and system==w+G.system.inWorld)then return nil,'the beam system is not the world\'s'end
    return system
end

-- Read-only: the research's pins and the beam system on the running game (true, or nil and why).
function M.prove_pins()
    local world,why=world_module.open()
    if not world then return nil,why end
    local ok,reason=prove(world)
    if not ok then return nil,reason end
    local system,swhy=beam_system(world)
    if not system then return nil,swhy end
    return true
end

-- The live BeamInfo row of a BeamType and a DamageInfo row by id (the game's own pointer tables), or nil and why.
local function beam_row(world,beam_type)
    local row=world.view.pointer(world.game+G.beamTable.table+beam_type*8)
    local raw=row and world.view.read(row,G.beamTable.stride)
    if not(raw and b.u32(raw,0)==beam_type)then return nil,'BeamInfo row '..beam_type..' is unreadable'end
    return raw
end
local function damage_row(world,id)
    local row=world.view.pointer(world.game+G.damageTable.table+id*8)
    local raw=row and world.view.read(row,G.damageTable.stride)
    if not(raw and b.u32(raw,0)==id)then return nil,'DamageInfo row '..id..' is unreadable'end
    local out={id=id,standard=b.value(raw,4,'i32'),durable=b.value(raw,8,'i32'),lanes={}}
    for k=0,3 do out.lanes[k+1]=b.u32(raw,12+4*k)end
    return out
end

-- The multipliers a configuration gives on a damage row: m (damage), p (penetration), or nil and why.
local function multipliers(spec,row)
    local m=spec.damage_multiplier or 1
    if spec.damage then
        if not(row.standard and row.standard>0)then return nil,'the damage row has no standard damage'end
        m=spec.damage/row.standard
    end
    local p=spec.armor_penetration_multiplier or 1
    if spec.armor_penetration then
        local lane
        for _,v in ipairs(row.lanes)do
            if v~=0 then
                if lane and lane~=v then return nil,'the damage row\'s penetration lanes differ'end
                lane=v
            end
        end
        if not lane then return nil,'the damage row has no penetration'end
        p=spec.armor_penetration/lane
    end
    local lim=G.limits
    if m<lim.damageMultiplier[1]or m>lim.damageMultiplier[2]then
        return nil,('damage multiplier %g outside %g..%g'):format(m,lim.damageMultiplier[1],lim.damageMultiplier[2])
    end
    if p<lim.armorPenetrationMultiplier[1]or p>lim.armorPenetrationMultiplier[2]then
        return nil,('penetration multiplier %g outside %g..%g'):format(p,lim.armorPenetrationMultiplier[1],
            lim.armorPenetrationMultiplier[2])
    end
    return m,p
end

local function describe(row,m,p)
    local lanes={}
    for k=1,4 do lanes[k]=fmt(row.lanes[k]*p)end
    return ('DamageInfo %d: %s / %s damage (x%s), AP %s (x%s)'):format(row.id,fmt(row.standard*m),fmt(row.durable*m),
        fmt(m),table.concat(lanes,'/'),fmt(p))
end

-- A configuration, validated (independently of the game): the normalised spec, or nil and why.
local function validate(spec)
    if type(spec)~='table'then return nil,'the damage settings must be a table'end
    local allowed={damage=true,damage_multiplier=true,armor_penetration=true,armor_penetration_multiplier=true,
        damage_row=true}
    for k in pairs(spec)do if not allowed[k]then return nil,'unknown damage setting '..tostring(k)end end
    local function number(name)
        local v=spec[name]
        if v~=nil and(type(v)~='number'or v~=v or v<=0 or v>=1e9)then return nil,name..' must be a positive number'end
        return true
    end
    for _,k in ipairs({'damage','damage_multiplier','armor_penetration','armor_penetration_multiplier'})do
        local ok,why=number(k)
        if not ok then return nil,why end
    end
    if spec.damage and spec.damage_multiplier then return nil,'damage and damage_multiplier exclude each other'end
    if spec.armor_penetration and spec.armor_penetration_multiplier then
        return nil,'armor_penetration and armor_penetration_multiplier exclude each other'
    end
    local lim=G.limits
    if spec.armor_penetration and(spec.armor_penetration%1~=0 or spec.armor_penetration<lim.armorPenetration[1]
        or spec.armor_penetration>lim.armorPenetration[2])then
        return nil,('armor_penetration must be a whole number %d..%d'):format(lim.armorPenetration[1],
            lim.armorPenetration[2])
    end
    if spec.damage_row~=nil and not DONOR[spec.damage_row]then
        return nil,'damage_row must be one of '..table.concat(M.DONORS,', ')
    end
    local out={damage=spec.damage,damage_multiplier=spec.damage_multiplier,armor_penetration=spec.armor_penetration,
        armor_penetration_multiplier=spec.armor_penetration_multiplier,damage_row=spec.damage_row}
    local donor=DONOR[out.damage_row or G.donors[1].label]
    local row={id=donor.damageInfo,standard=donor.standard,durable=donor.durable,lanes=donor.armorPenetration}
    local m,p=multipliers(out,row)
    if not m then return nil,p end
    return out,{m=m,p=p,row=row,donor=donor}
end
M.validate=validate

local function owner_of(world,address,size)
    local r=hooks.query and hooks.query(address)or world.runtime.query(address)
    if not(r and r.state==COMMIT and r.type==PRIVATE and r.protect==READWRITE and r.allocation_base
        and address>=r.base and address+size<=r.base+r.size)then
        return nil
    end
    return {base=r.allocation_base,size=r.base+r.size-r.allocation_base,type=PRIVATE,protect=READWRITE}
end

local function count(config,code,reason,slot)
    config.refused[code]=(config.refused[code]or 0)+1
    if config.refused[code]==1 then
        log(('%s: a shot stays as fired (Trident damage): %s: %s (ring slot %d)'):format(config.weapon.name,code,
            reason,slot))
    end
end

-- One new entry of a configured weapon: written once.
local function consider(world,system,slot,e,config,player_count)
    config.shots=config.shots+1
    if player_count>1 then
        return count(config,'NOT_SOLO',player_count..' players: per-weapon beam damage is solo only',slot)
    end
    if e:byte(E.applied+1)~=0 then
        config.missed=config.missed+1
        return count(config,'MISSED','the pulse had already hit when the Runtime saw it',slot)
    end
    local beam,why=beam_row(world,G.trident.beamType)
    if not beam then return count(config,'UNEXPECTED_STATE',why,slot)end
    local function same(entry_at,row_at)return e:sub(entry_at+1,entry_at+4)==beam:sub(row_at+1,row_at+4)end
    local copies=same(E.damageInfo,ROW.damageInfo)and same(E.falloffStart,ROW.falloffStart)
        and same(E.falloffRange,ROW.falloffRange)
    local fields={{'damageNear',ROW.damageNear,'m'},{'damageFar',ROW.damageFar,'m'},
        {'penetrationNear',ROW.penetrationNear,'p'},{'penetrationFar',ROW.penetrationFar,'p'}}
    local spec=config.spec
    local donor=DONOR[spec.damage_row or G.donors[1].label]
    local row,rwhy=damage_row(world,donor.damageInfo)
    if not row then return count(config,'UNEXPECTED_STATE',rwhy,slot)end
    local m,p=multipliers(spec,row)
    if not m then return count(config,'UNEXPECTED_STATE',p,slot)end
    local desired={}
    for _,f in ipairs(fields)do
        local base=f32(beam,f[2])
        if not base then return count(config,'UNEXPECTED_STATE','BeamInfo row 6 holds a non-finite multiplier',slot)end
        desired[f[1]]=b.encode(base*(f[3]=='m'and m or p),'f32')
    end
    desired.damageInfo=b.encode(donor.damageInfo,'u32')
    local untouched,already=copies,true
    for _,f in ipairs(fields)do
        untouched=untouched and same(E[f[1]],f[2])
        already=already and e:sub(E[f[1]]+1,E[f[1]]+4)==desired[f[1]]
    end
    already=already and e:sub(E.damageInfo+1,E.damageInfo+4)==desired.damageInfo
    if already and not untouched then config.already=config.already+1;return end
    if not untouched then
        return count(config,'UNEXPECTED_STATE','its damage copies differ from BeamInfo row 6 (written by something '
            ..'else)',slot)
    end
    local address=system+RING.base+slot*RING.stride
    local owner=owner_of(world,address,RING.stride)
    if not owner then return count(config,'NOT_PRIVATE','the beam ring is not in private read-write memory',slot)end
    local changes={}
    local function change(name)
        local at=E[name]
        local now=e:sub(at+1,at+4)
        if now==desired[name]then return end
        changes[#changes+1]={label=('beam_damage.%s.slot%d.%s'):format(config.weapon.id,slot,name),owner=owner,
            offset=address+at-owner.base,expected=now,desired=desired[name],before=now,already_desired=false,
            identity={component='BeamSystem',component_type='native',record_type='beam shot entry',
                unique_owner=true,owner_count=1},chain={}}
    end
    for _,f in ipairs(fields)do change(f[1])end
    change('damageInfo')
    if#changes==0 then config.untouched=config.untouched+1;return end
    local plan={snapshots={{owner=owner,offset=address-owner.base,bytes=e}},changes=changes}
    local report=transaction.apply(world.runtime,plan)
    metrics.count('beam_damage.transactions')
    if report.status~='APPLIED'then return count(config,'GUARD_REJECTED',tostring(report.reason),slot)end
    local after=world.view.read(address,RING.stride)
    local verified=after~=nil
    for _,c in ipairs(changes)do verified=verified and after:sub(c.offset-(address-owner.base)+1,
        c.offset-(address-owner.base)+4)==c.desired end
    config.modified=config.modified+1
    config.writes=config.writes+report.writes
    if not verified then config.unverified=config.unverified+1 end
    local pending=b.u32(e,E.rayQuery)==0 and e:sub(E.rayQueries+1,E.rayQueries+8)==string.rep('\0',8)
    if pending then config.before_rays=config.before_rays+1 end
    if config.modified==1 then
        log(('%s: first shot written (ring slot %d, %s): %s; %d write%s, read back %s, non-target bytes unchanged %s')
            :format(config.weapon.name,slot,pending and'before its first ray query'or'after a ray query without a hit',
            describe(row,m,p),report.writes,report.writes==1 and''or's',tostring(verified),
            tostring(report.non_target_bytes_unchanged)))
    else
        detail(('%s: ring slot %d written (%d writes, read back %s)'):format(config.weapon.name,slot,report.writes,
            tostring(verified)))
    end
end

local function summary(config,why)
    if config.shots==0 then return end
    local parts={}
    for code,n in pairs(config.refused)do parts[#parts+1]=('%s x %d'):format(code,n)end
    table.sort(parts)
    log(('%s: %s: %d shot%s seen, %d written (%d before the first ray query, %d writes%s)%s'):format(config.weapon.name,
        why,config.shots,config.shots==1 and''or's',config.modified,config.before_rays,config.writes,
        config.unverified>0 and(', '..config.unverified..' NOT read back')or'',
        #parts>0 and('; as fired: '..table.concat(parts,', '))or''))
end
local function reset_counters(config)
    config.shots,config.modified,config.writes,config.missed,config.already,config.untouched=0,0,0,0,0,0
    config.before_rays,config.unverified=0,0
    config.refused={}
end
local function reset_mission(why)
    memo={}
    for _,config in pairs(configs)do summary(config,why);reset_counters(config)end
end

local function players(world)
    if hooks.players then return hooks.players(world)end
    return #(world_module.players(world)or{})
end
local function entity_type(world,entity)
    if hooks.entity_type then return hooks.entity_type(world,entity)end
    return world_module.entity_type(world,entity)
end

local function step(dt)
    clock=clock+(dt or 0)
    if not in_mission and clock-off_mission_at<M.OFF_MISSION_EVERY then return end
    local world=world_module.open()
    if not world then return end
    local game=hooks.game_state and hooks.game_state(world)or world_module.game_state(world)
    if not(game and game.mission)then
        if in_mission then reset_mission('the mission ended')end
        in_mission=false
        off_mission_at=clock
        return
    end
    in_mission=true
    local ok,why=prove(world)
    local system
    if ok then system,why=beam_system(world)end
    if not system then
        if unavailable_logged~=why then
            unavailable_logged=why
            log('UNAVAILABLE: every beam shot keeps the Trident\'s damage: '..tostring(why))
        end
        return
    end
    local ring=world.view.read(system+RING.base,RING.slots*RING.stride)
    if not ring then return end
    local player_count
    -- A shot is handled once: its slot is remembered with the shot's own bytes (+0x00..+0x17, the weapon entity and
    -- the +0x158 value BeamFire stores at 0x13B9BB4) until the slot is seen dead or holding another beam.
    for slot=0,RING.slots-1 do
        local at=slot*RING.stride
        if ring:byte(at+E.alive+1)==0 or b.u32(ring,at+E.beamType)~=G.trident.beamType then
            memo[slot]=nil
        else
            local entity=b.u32(ring,at+E.weaponEntity)
            local key=ring:sub(at+1,at+E.beamType)..b.encode(entity,'u32')..ring:sub(at+0x158+1,at+0x160)
            local seen=memo[slot]
            if not(seen and seen.key==key)then
                local kind=entity_type(world,entity)
                local w=kind and BY_RESOURCE[kind]
                local config=w and configs[w.id]
                memo[slot]={key=key,weapon=w and w.id}
                if config then
                    player_count=player_count or players(world)
                    consider(world,system,slot,ring:sub(at+1,at+RING.stride),config,player_count)
                end
            end
        end
    end
end
M.step=step

local function ensure_watch()
    if watch and watch.status=='active'then return end
    watch={status='active',perf_label='experiment beam damage'}
    function watch.tick(dt)
        if watch.status~='active'then return end
        local started=metrics.now()
        local ok,why=pcall(step,dt)
        if not ok then log('update failed: '..tostring(why))end
        metrics.elapsed('beam_damage.tick',started)
        if next(configs)==nil then watch.status='complete';reset_mission('stopped')end
    end
    function watch.cancel()watch.status='cancelled'end
    scheduler.attach(watch)
end

local function rebuild()
    by_type={}
    for _,config in pairs(configs)do by_type[config.weapon.resource:sub(3):upper()]=config end
end

local function swap_state(id)
    if hooks.swap_state then return hooks.swap_state(id)end
    local X=require('hd2runtime/runtime/experiment_beam_swap')
    local states,why=X.weapon_states()
    if not states then return nil,why end
    return states[id]
end
local function package_state(donor)
    if hooks.assets then return hooks.assets(donor)end
    local assets=require('hd2runtime/core/assets')
    local dep=assets.dependency(donor.dependency)
    if not(dep and tostring(dep.name):find(donor.package,1,true))then return'unknown'end
    local world=world_module.open()
    if not world then return'unknown'end
    local ok,state=pcall(assets.state,world.runtime,dep.package)
    return ok and state or'unknown'
end

-- Gives a swapped weapon its own beam damage (replacing its previous settings): spec = {damage (the standard damage
-- of the damage row, scaled with its durable damage) | damage_multiplier, armor_penetration (whole number: the row's
-- non-zero penetration lanes become it) | armor_penetration_multiplier, damage_row (a donor label, default the
-- Trident's)}. {} = the Trident's own damage (cleared). Returns {ok, detail} or {ok=false, reason}.
function M.set(id,spec)
    local w=BY[id]
    if not w then
        return {ok=false,reason='unknown weapon '..tostring(id)..' (one of '..table.concat(D.order,', ')..')'}
    end
    local normal,info=validate(spec)
    if not normal then
        log(w.name..': REFUSED: '..tostring(info))
        return {ok=false,reason=info}
    end
    local state,why=swap_state(id)
    if state~='applied'then
        local reason=('the %s is not swapped (%s): per-weapon beam damage applies only while its swap is applied')
            :format(w.name,tostring(state or why))
        log(w.name..': REFUSED: '..reason)
        return {ok=false,reason=reason}
    end
    if info.donor.damageInfo~=G.trident.damageInfo then
        local pstate=package_state(info.donor)
        if pstate~='resident'then
            local reason=('the %s\'s package (%s) is %s: its damage row carries a status effect; load it first')
                :format(info.donor.label,info.donor.package,tostring(pstate))
            log(w.name..': REFUSED: '..reason)
            return {ok=false,reason=reason}
        end
    end
    local text=describe(info.row,info.m,info.p)
    if info.m==1 and info.p==1 and info.donor.damageInfo==G.trident.damageInfo then
        M.clear(id,'set to the Trident\'s own damage')
        return {ok=true,detail='the Trident\'s own damage ('..text..')'}
    end
    local old=configs[id]
    if old then summary(old,'replaced')end
    local config={weapon=w,spec=normal,text=text}
    reset_counters(config)
    configs[id]=config
    rebuild()
    ensure_watch()
    log(('%s: its beam shots get %s (from the next shot; the Trident and the other weapons unchanged)'):format(w.name,
        text))
    return {ok=true,detail=text}
end

function M.clear(id,why)
    local config=configs[id]
    if not config then return false end
    summary(config,why or'cleared')
    configs[id]=nil
    rebuild()
    log(config.weapon.name..': its beam shots keep the Trident\'s damage again ('..(why or'cleared')..')')
    return true
end
-- The swap module forgets the weapons it restored.
function M.forget(ids,why)
    for _,id in ipairs(ids or D.order)do M.clear(id,why or'its swap was restored')end
end

function M.status()
    local out={ok=true,weapons={}}
    for _,id in ipairs(D.order)do
        local c=configs[id]
        local entry={id=id,name=BY[id].name,active=c~=nil}
        if c then
            entry.detail=c.text
            entry.shots,entry.written,entry.missed,entry.refused=c.shots,c.modified,c.missed,c.refused
            entry.before_rays,entry.writes=c.before_rays,c.writes
            local parts={}
            for code,n in pairs(c.refused)do parts[#parts+1]=code..' x '..n end
            table.sort(parts)
            log(('%s: %s; this mission %d shot%s seen, %d written (%d before the first ray query)%s'):format(
                BY[id].name,c.text,c.shots,c.shots==1 and''or's',c.modified,c.before_rays,
                #parts>0 and('; as fired: '..table.concat(parts,', '))or''))
        else
            log(BY[id].name..': Trident damage (no per-weapon setting)')
        end
        out.weapons[#out.weapons+1]=entry
    end
    if unavailable_logged then out.unavailable=unavailable_logged end
    return out
end

-- Tests only.
function M.set_hooks_for_tests(h)hooks=h or{}end
function M.reset_for_tests()
    configs,by_type,proven,memo,hooks={},{},{},{},{}
    clock,in_mission,off_mission_at,unavailable_logged=0,false,-math.huge,nil
    if watch then watch.status='cancelled'end
    watch=nil
end
return M
