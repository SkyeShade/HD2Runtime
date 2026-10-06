-- The reviewed explosion donors of the custom stratagem payloads (development; docs/custom-stratagem-api.md,
-- "Explosion donors"). Not exported by api/hd2.lua: the custom stratagem payload families reach it (a weapon's, a
-- shell's or an Eagle's impact explosion).
--
-- A donor is a stratagem whose own projectile requests an explosion on impact; a projectile of the custom stratagem may
-- request that explosion instead of its own (runtime/projectile_impact.lua: one write of that projectile's own copy).
-- Only a donor whose WHOLE chain is exactly as reviewed is used: its explosion row, the explosion's damage row, its
-- volume template and every status they name (relocated words masked), read now, and its call-in package resident
-- (the explosion's effects come from it). Nothing here writes.
--   * Orbital Gas Strike: shell 197 -> explosion 82 (no damage; gas and gas confusion; a 15 s, 15 m gas cloud);
--     research/bombardment-payload gasChain (runtime/bombardment_payload.lua chain_intact);
--   * Orbital EMS Strike: shell 74 -> explosion 188 (no damage; stun; a 15 s StaticField); research/custom-payloads.
--   * RL-77 Airburst Rocket Launcher: its round 312's explosion 325, the cluster (25 bomblets, projectile 78, each
--     exploding as 7); research/carrier-weapon-clone roundOverrides (domains/weapon_clone.lua rounds). Requested on
--     impact by another rocket it is the cluster without the RL-77's proximity airburst (that lives in its round's row).
--     Its effect and the bomblet's unit ship only in the mission package (`requires`, resident in a mission); its
--     call-in package is its dependency. INTERNAL: only the EAT-17C's donor fallback takes it (custom_stratagems: the
--     regular EAT-17's rocket; M.resolve(ref, {internal = true})); never a mod's impact_explosion, never in M.names().
-- An AUTOMATIC donor (`automatic`) is reviewed for a weapon that fires many rounds a second: one plain blast a round
-- (no volume, status, submunition or arc), as the round that requests it natively. Only the Pelican gunship's chin gun
-- takes one (M.resolve(ref, {automatic = true})); the other families never see them, and an automatic weapon never takes
-- the others (a 15 s cloud a round). research/custom-payloads automaticDonors (radii inner / outer / shockwave):
--   * Pelican chin autocannon: the chin turret's own round 120 -> 234 (150 damage, AP 3; 2 / 6 / 8 m);
--   * 66mm Missile Mk2: round 272 -> 170 (150, AP 5; 1 / 2 / 4 m); `asset` the MLS-4X Commando, whose call-in package
--     ships its effect;
--   * Automaton explosion 27: round 302 -> 27 (70, AP 4; 1 / 2 / 3.5 m): Automaton faction content only;
--   * Illuminate explosion 392: round 166 -> 392 (150, AP 4; 1.2 / 2.7 / 4 m): Illuminate faction content only;
--   * Strafing run cannon: the Eagle Strafing Run's 23mm HE round 16 -> 50 (350, AP 3; 2.5 / 5 / 6.5 m); `asset` the
--     Eagle Strafing Run;
--   * Exploding crossbow: the CB-9 Exploding Crossbow's bolt 249 -> 59 (350, AP 3/3/3; 3 / 6 / 7 m); `asset_key` its
--     package's catalogue key (a primary weapon is no stratagem).
-- A SLOW donor (`slow`) is reviewed for a gun firing at most its max_rpm rounds a minute: a damage-over-time volume a
-- round (the game holds 4096 status volumes and checks no count before adding one; runtime/projectile_impact.lua refuses
-- a round faster than that). Only a gun takes one (M.resolve(ref, {gun = true, rpm = its rate})). research/custom-payloads
-- slowDonors (radii inner / outer / shockwave):
--   * EMS mortar field: the A/M-23 EMS Mortar Sentry shell 154's expiry explosion 180 (no damage; stun; a 7 s
--     StaticField; 1 / 10 / 12 m), at most 60 a minute; `asset` the A/M-23 EMS Mortar Sentry;
--   * Gas grenade cloud: the G-4 Gas grenade's 177 (3 damage; gas and gas confusion; a 15 s cloud; 2 / 7 / 7 m), at most
--     60 a minute; `asset_key` throwable/G-4 Gas;
--   * Gas mortar cloud: the A/GM-17 Gas Mortar Sentry shell 342's impact explosion 185 (the same cloud, no damage), at
--     most 60 a minute; `asset` the A/GM-17 Gas Mortar Sentry.
-- M.assets(world, name, dt) requests the package a donor's effect needs through the asset loader (core/assets gate),
-- for the Pelican gunship on the host and every other machine's mirror alike.
-- An automatic donor is ready while ANY package that ships its explosion's particle effect (the game data's archives)
-- is resident: a faction's blast only in that faction's missions (the Runtime never loads faction content).
local core_assets=require('hd2runtime/core/assets')
local log_module=require('hd2runtime/runtime/log')
local b=require('hd2runtime/core/bytes')
local catalog=require('hd2runtime/domains/stratagem_authoring')
local D=require('hd2runtime/domains/custom_payloads')
local M={}

local function masked_equal(bytes,reviewed,masked)
    if not bytes or#bytes~=#reviewed then return false end
    local skip={}
    for _,offset in ipairs(masked or{})do skip[offset]=true end
    for offset=0,#reviewed-4,4 do
        if not skip[offset]and bytes:sub(offset+1,offset+4)~=reviewed:sub(offset+1,offset+4)then return false end
    end
    return true
end
-- Every row of a reviewed chain exactly as reviewed: true, or false and which.
local function rows_intact(world,rows)
    for _,item in ipairs(rows)do
        local table_rva=type(item.table)=='string'and tonumber(item.table:sub(3),16)or item.table
        local at=world.view.pointer(world.game+table_rva+item.id*8)
        if not masked_equal(at and world.view.read(at,item.stride),b.unhex(item.reviewed),item.masked)then
            return false,item.kind..' '..item.id..' is not its reviewed row'
        end
    end
    return true
end
M.rows_intact=rows_intact

M.DONORS={
    ['Orbital Gas Strike']={shell=197,explosion=82,effect='gas (a 15 s, 15 m cloud; no damage)',
        chain=function(world)return require('hd2runtime/runtime/bombardment_payload').chain_intact(world)end},
    ['Orbital EMS Strike']={shell=D.explosionDonors['Orbital EMS Strike'].shell,
        explosion=D.explosionDonors['Orbital EMS Strike'].explosion,effect='stun (a 15 s StaticField; no damage)',
        chain=function(world)return rows_intact(world,D.explosionDonors['Orbital EMS Strike'].rows)end},
}
-- The RL-77's cluster: its chain without the round's own row.
do
    local R=require('hd2runtime/domains/weapon_clone').rounds
    local r=R and R['EAT-17 Expendable Anti-Tank']and R['EAT-17 Expendable Anti-Tank']['RL-77 Airburst Rocket Launcher']
    if r then
        local rows={}
        for _,item in ipairs(r.rows)do if not(item.kind=='projectile'and item.id==r.type)then rows[#rows+1]=item end end
        local sub=r.submunition or{}
        M.DONORS['RL-77 Airburst Rocket Launcher']={explosion=r.impact,requires={r.packages.mission.id},internal=true,
            effect=('the cluster (explosion %d: %s bomblets, projectile %s exploding as %s; no proximity airburst)'):format(
                r.impact,tostring(sub.count or 25),tostring(sub.projectile or 78),tostring(sub.explosion or 7)),
            chain=function(world)return rows_intact(world,rows)end}
    end
end
-- An automatic or slow donor's semantic key (its name in lower case, words joined by '_': a Mod Options choice value).
local by_key={}
for name,e in pairs(D.explosionDonors)do
    if e.slow==true then
        local packages={}
        for k,p in ipairs(e.packages)do packages[k]={id=p.id,name=p.name}end
        local key=name:lower():gsub('[^%w]+','_')
        by_key[key]=name
        local v=e.volume
        M.DONORS[name]={round=e.round,explosion=e.explosion,slow=true,max_rpm=e.maxRpm,volume=v,packages=packages,
            asset=e.asset,asset_key=e.assetKey,radii=e.radii,damage=e.damage,key=key,
            effect=('explosion %d (a %g s volume, radius %g m; %d damage; at most %d a minute)'):format(e.explosion,
                v.seconds,e.radii[2],e.damage.standard,e.maxRpm),
            chain=function(world)return rows_intact(world,e.rows)end}
    end
    if e.automatic==true then
        local packages={}
        for k,p in ipairs(e.packages)do packages[k]={id=p.id,name=p.name}end
        local key=name:lower():gsub('[^%w]+','_')
        by_key[key]=name
        M.DONORS[name]={round=e.round,explosion=e.explosion,automatic=true,packages=packages,asset=e.asset,
            asset_key=e.assetKey,
            radii=e.radii,damage=e.damage,key=key,
            effect=('explosion %d (%d damage, AP %d; radii %g / %g / %g m)'):format(e.explosion,e.damage.standard,
                e.damage.armorPenetration[1],e.radii[1],e.radii[2],e.radii[3]),
            chain=function(world)return rows_intact(world,e.rows)end}
    end
end
-- Whether a donor fits the use: opts.automatic asks for one reviewed for an automatic weapon; opts.gun for one a gun may
-- take (an automatic one, or a slow one when opts.rpm is at most its max_rpm; any slow one without opts.rpm); else the
-- others (a launcher's, a shell's: neither automatic nor slow).
local function fits(donor,opts)
    opts=type(opts)=='table'and opts or{}
    -- An internal donor (the Runtime's own fallback) only when asked for by name with opts.internal.
    if donor.internal then return opts.internal==true end
    if opts.gun then
        return donor.automatic==true or donor.slow==true and(opts.rpm==nil or opts.rpm<=donor.max_rpm)
    end
    if opts.automatic then return donor.automatic==true end
    return not donor.automatic and not donor.slow
end
-- The donor names that fit (opts as M.resolve), sorted (for messages).
function M.names(opts)
    local out={}
    for name,donor in pairs(M.DONORS)do if fits(donor,opts)then out[#out+1]=name end end
    table.sort(out)
    return out
end
-- A donor reference: a stratagem name or a typed handle naming one ({stratagem = name} or {name = name}); an automatic
-- or slow donor also by its key ('pelican_chin_autocannon', 'ems_mortar_field'). opts = {automatic = true}: only a donor
-- reviewed for an automatic weapon; {gun = true, rpm = n}: one a gun firing n rounds a minute may take; without them,
-- only the others. Returns the name and its donor, or nil.
function M.resolve(ref,opts)
    local name=type(ref)=='string'and ref or type(ref)=='table'and(ref.stratagem or ref.name)or nil
    if type(name)=='string'and not M.DONORS[name]then name=by_key[name]end
    local donor=name and M.DONORS[name]
    if not(donor and fits(donor,opts))then return nil end
    return name,donor
end
-- The donor's package dependency, or nil: a stratagem donor's call-in package; an automatic or slow donor's `asset`
-- (the stratagem whose call-in package ships its effect: what a definition loads for it) or `asset_key`, none for a
-- faction's blast.
function M.dependency(name)
    local donor=M.DONORS[name]
    if donor and(donor.automatic or donor.slow)then
        if donor.asset_key then return core_assets.dependency(donor.asset_key)end
        -- A support weapon's call-in package is its weapon's (the loader's +0xF8; core/assets dependencies).
        local entry=donor.asset and catalog.stratagems[donor.asset]
        local id=entry and entry.root and entry.root.id
        local list=id and core_assets.dependencies_for_stratagem(id,donor.asset)
        return list and list[1]or nil
    end
    local entry=catalog.stratagems[name]
    local id=entry and entry.root and entry.root.id
    return id and core_assets.dependency_for_stratagem(id,name)
end
-- An automatic or slow donor's residency is re-read every M.READY_CALLS checks (each converted round asks; one read walks the
-- engine's whole package list for each package): the package found resident is remembered until then.
M.READY_CALLS=32
local ready_cache={}
local function package_list(donor)
    local named={}
    for _,p in ipairs(donor.packages)do named[#named+1]=p.name or p.id end
    if#named>3 then return table.concat(named,', ',1,3)..(' (%d more)'):format(#named-3)end
    return table.concat(named,', ')
end
-- Whether the donor can be used now: its chain exactly as reviewed and its call-in package resident (an automatic or
-- slow donor: any package that ships its effect). true, or nil, code, reason.
function M.ready(world,name)
    local donor=M.DONORS[name]
    if not donor then return nil,'UNREVIEWED_DONOR','no reviewed explosion donor '..tostring(name)end
    local intact,why=donor.chain(world)
    if not intact then return nil,'DONOR_CHANGED',tostring(why)end
    -- Packages its effect needs beside its call-in package (the RL-77's cluster: the mission package).
    for _,id in ipairs(donor.requires or{})do
        local ok,state=pcall(core_assets.state,world.runtime,id)
        if not(ok and state=='resident')then
            return nil,'DONOR_NOT_RESIDENT',('%s\'s effect package %s is not resident'):format(name,id)
        end
    end
    if donor.automatic or donor.slow then
        local c=ready_cache[name]
        if c and c.left>0 then
            c.left=c.left-1
            if c.package then return true end
            return nil,'DONOR_NOT_RESIDENT',c.reason
        end
        for _,p in ipairs(donor.packages)do
            local ok,state=pcall(core_assets.state,world.runtime,p.id)
            if ok and state=='resident'then
                ready_cache[name]={left=M.READY_CALLS,package=p}
                return true
            end
        end
        local reason=('%s\'s effect ships only in %s; none is resident'):format(name,package_list(donor))
        ready_cache[name]={left=M.READY_CALLS,reason=reason}
        return nil,'DONOR_NOT_RESIDENT',reason
    end
    local dependency=M.dependency(name)
    if not dependency then return nil,'ASSET_UNAVAILABLE','no call-in package is known for '..name end
    local ok,state=pcall(core_assets.state,world.runtime,dependency.package)
    if not(ok and state=='resident')then return nil,'DONOR_NOT_RESIDENT',name..'\'s call-in package is not resident'end
    return true
end
-- The package an automatic or slow donor was last found resident in ({id, name}), or nil.
function M.resident_package(name)local c=ready_cache[name];return c and c.package end
-- The package an automatic or slow donor's effect needs, requested through the asset loader (one gate per donor, shared by
-- every caller): 'ready', 'waiting' or 'failed' (and why). A donor with nothing to load (a faction's blast: the game
-- loads its content) is 'ready' at once; M.ready still decides whether its effect is resident.
local gates={}
function M.assets(world,name,dt)
    local donor=M.DONORS[name]
    if not donor then return'failed','UNREVIEWED_DONOR: '..tostring(name)end
    local dependency=M.dependency(name)
    if not((donor.automatic or donor.slow)and dependency)then return'ready'end
    local gate=gates[name]
    if not gate then
        gate=core_assets.gate(world.runtime,{id='explosion-donor-'..donor.key,asset_dependencies={dependency}},
            log_module.emit)
        gates[name]=gate
    end
    return gate.tick(dt or 0)
end
function M.reset_for_tests()ready_cache={};gates={}end
return M
