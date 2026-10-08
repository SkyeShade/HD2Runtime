-- Custom stratagems (development; docs/custom-stratagem-api.md). hd2.custom_stratagem (api/custom_stratagem.lua) is
-- its public face. One orchestrator for every custom stratagem of every mod, built from the live-proven parts:
--   * identity: a Runtime-owned definition (runtime/virtual_stratagems.lua) selected in the Runtime's custom panel
--     (runtime/custom_stratagem_panel.lua, ONE panel for every mod); the save holds only the vanilla token (Orbital
--     Precision Strike); no account, save or catalogue data changes;
--   * the carrier: allocated per definition by its POLICY (runtime/carrier_allocator.lua allocate_policies: owned,
--     selectable, enabled, unlimited, not in the loadout, every call-in package known, the beacon colour and families
--     asked for, never another custom stratagem's carrier, donor or delivery); cached aboard the ship and allocated
--     again at every mission start against the current loadout;
--   * aboard the ship the carrier is NATIVE; at mission start (the host; with several players EXPERIMENTAL, see
--     runtime/multiplayer.lua: a client refuses its own and observes the others') each custom stratagem in turn: its assets
--     resident, its carrier's mission presentation (name, cased name, description, icon, code) applied and verified
--     (runtime/carrier_presentation.lua), its cooldown armed (runtime/slot_cooldown.lua), only its own virtual slots
--     converted to its carrier (runtime/stratagem_slot_conversion.lua). It is never callable before all of that holds;
--   * ONE beacon watch (runtime/beacons.lua) for every custom stratagem: a beacon of a converted carrier's type is a call
--     of that custom stratagem (the carrier is in no loadout); in its FIRST update its delivery becomes 'none' (the
--     Runtime delivers) or the definition's vanilla delivery (a support pod), in one guarded write of that beacon. Every
--     other beacon is left alone;
--   * each call gets a CONTEXT (ctx): the definition, a mission-unique call id, the caller (the local player), the slot,
--     the carrier, the beacon, its landing position; mods get on_called, on_beacon_created, on_beacon_landed,
--     on_activate and (support deliveries) on_delivered with ctx.weapons, the exact delivered weapon entities
--     (runtime/support_pods.lua capture);
--   * spawned instances are associated with their call (runtime/spawned_instances.lua), and kills whose last hit came
--     from an associated entity are reported against that call;
--   * back aboard the ship every carrier's presentation is restored exactly (the loadout screen opening is the hard
--     boundary).
-- The payload families (data a mod or a ModBuilder states; Lua callbacks stay available as an escape hatch):
--   * delivery = 'runtime': the carrier's own delivery is neutralized and the mod delivers (on_activate);
--   * delivery = {family = 'support', items = {{donor, count, modify}}} (or the older {stratagem = name}): the vanilla
--     support pod of ONE donor stratagem; the exact items its rack holds are captured (runtime/support_pods.lua), each
--     associated with the call, and each weapon's modifications applied to that entity only (runtime/custom_weapons.lua,
--     runtime/projectile_impact.lua);
--   * sentry = {donor, weapon}: the donor sentry's vanilla pod (a sentry-family carrier, blue); the exact sentry its pod
--     deploys is captured and its weapon configured on its own records;
--   * eagle = {donor, uses, payload = {impact_explosion}}: the donor Eagle's own strike from an Eagle carrier (red; the
--     slot a fleet member with its own uses per rearm); the exact jet of the call is captured and its rockets request
--     the donor explosion on impact (runtime/custom_eagles.lua);
--   * orbital = {shell, pattern, salvos, shells_per_salvo, shell_interval, salvo_interval, scatter, salvo_scatter,
--     impact_explosion}: a Runtime bombardment (runtime/bombardment_executor.lua) of a reviewed shell in a reviewed or
--     explicit pattern; each shell's own impact explosion optionally the donor's.
-- Solo host only: every write path refuses otherwise (the conversion, the beacon write, the cooldown, the presentation).
if rawget(_G,'jit')then jit.off(true,true)end
local world_module=require('hd2runtime/runtime/event_world')
local scheduler=require('hd2runtime/runtime/scheduler')
local events=require('hd2runtime/runtime/events')
local handles=require('hd2runtime/runtime/handles')
local log_module=require('hd2runtime/runtime/log')
local metrics=require('hd2runtime/runtime/metrics')
local core_assets=require('hd2runtime/core/assets')
local texts=require('hd2runtime/runtime/text_resources')
local images=require('hd2runtime/runtime/image_resources')
local calldown=require('hd2runtime/runtime/calldown_codes')
local virtual=require('hd2runtime/runtime/virtual_stratagems')
local selector=require('hd2runtime/runtime/stratagem_selector')
local panel_module=require('hd2runtime/runtime/custom_stratagem_panel')
local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
local loadout=require('hd2runtime/runtime/stratagem_loadout')
local stratagem_hud=require('hd2runtime/runtime/stratagem_hud')
local allocator=require('hd2runtime/runtime/carrier_allocator')
local carrier_presentation=require('hd2runtime/runtime/carrier_presentation')
local beacons=require('hd2runtime/runtime/beacons')
local beacon_reader=require('hd2runtime/runtime/beacon_redirect')
local cooldowns=require('hd2runtime/runtime/slot_cooldown')
local support_pods=require('hd2runtime/runtime/support_pods')
local impacts=require('hd2runtime/runtime/projectile_impact')
local executor=require('hd2runtime/runtime/bombardment_executor')
local instances=require('hd2runtime/runtime/spawned_instances')
local weapons=require('hd2runtime/runtime/custom_weapons')
local eagles=require('hd2runtime/runtime/custom_eagles')
local donors=require('hd2runtime/runtime/explosion_donors')
local catalog=require('hd2runtime/domains/stratagem_authoring')
local mp=require('hd2runtime/runtime/multiplayer')
local cmp=require('hd2runtime/runtime/custom_multiplayer')
local sync=require('hd2runtime/runtime/custom_mp_sync')
local observer=require('hd2runtime/runtime/custom_mp_observer')
local barrages=require('hd2runtime/runtime/custom_barrages')
local mp_items=require('hd2runtime/runtime/custom_mp_items')
local mp_calls=require('hd2runtime/runtime/custom_mp_calls')
local evidence=require('hd2runtime/runtime/custom_mp_evidence')
local provenance=require('hd2runtime/runtime/custom_provenance')
local protocol=require('hd2runtime/runtime/peer_protocol')
local call_ins=require('hd2runtime/runtime/call_ins')
local weapon_clone=require('hd2runtime/runtime/weapon_clone')
local weapon_carriers=require('hd2runtime/runtime/weapon_carriers')
local carrier_pod=require('hd2runtime/runtime/carrier_pod')
local groups=require('hd2runtime/runtime/carrier_groups')
-- The native picker's blocked-card state (r6; optional in a build: loaded at startup, never on first use).
local blocking
do local ok,m=pcall(require,'hd2runtime/runtime/stratagem_blocking');blocking=ok and type(m)=='table'and m or nil end
local PP=require('hd2runtime/domains/pod_payload_authoring')
local SWC=require('hd2runtime/domains/support_weapon_catalog')
local C=require('hd2runtime/domains/stratagem_calldown')
local SLOTS=require('hd2runtime/domains/stratagem_slots')
local SD=require('hd2runtime/domains/support_delivery')
local M={}
M.TOKEN='Orbital Precision Strike'
M.MAX=16
M.STEP=0.5               -- the ship and mission step
M.LANDING_STEP=0.1       -- the landing watch while a call is pending
M.REVALIDATE_EVERY=5     -- aboard the ship: the cached carriers checked again at least this often
M.MP_EVERY=2             -- aboard the ship with several players: the lobby view read this often (read-only)
M.SETTLE=5               -- in a mission: seconds after the HUD is populated before the custom stratagems start
M.RESTORE_DEADLINE=5     -- back aboard the ship: the presentations restored at the latest this long after the mission
M.ASSET_TIMEOUT=30
M.OBJECTIVE_ASSET_TIMEOUT=90 -- a definition whose payload loads objective packages (a silo's objective blast: ~300 MB)
M.AGREEMENT_TIMEOUT=60   -- in a mission (a client): seconds to wait for the host's matching table and carrier hashes
M.RECORDS_TIMEOUT=30     -- in a mission: seconds to wait for every lobby member's stratagem record
M.MP_WAIT=20             -- in a mission with several players: seconds custom multiplayer may take to be enabled
M.BALL_WAIT=5            -- seconds a remote call's thrown ball may take to name its beacon
M.MAX_COOLDOWN=600
M.MAX_USES=100           -- calls per mission (spec.uses; runtime/slot_cooldown.lua M.MAX_USES)
-- The panel's ITEM TRAITS (spec.traits): up to MAX_TRAITS labels of 1 to TRAIT_LENGTH characters after the automatic
-- CUSTOM STRATAGEM. Returns the list (CUSTOM STRATAGEM first, no repeats, upper case) or nil without any.
M.MAX_TRAITS,M.TRAIT_LENGTH=4,32
function M.traits_of(list)
    if list==nil then return nil end
    assert(type(list)=='table','traits must be a list of short labels')
    local out,seen={'CUSTOM STRATAGEM'},{['CUSTOM STRATAGEM']=true}
    for k,t in ipairs(list)do
        assert(type(t)=='string'and#t>=1 and#t<=M.TRAIT_LENGTH and t:find('^[%w%p ]+$'),
            ('traits[%d] must be 1 to %d printable characters'):format(k,M.TRAIT_LENGTH))
        local u=string.upper(t)
        if not seen[u]then seen[u]=true;out[#out+1]=u end
    end
    assert(#out-1<=M.MAX_TRAITS,('traits: at most %d after CUSTOM STRATAGEM'):format(M.MAX_TRAITS))
    for k in pairs(list)do assert(type(k)=='number'and k%1==0 and k>=1 and k<=#list,'traits must be a list')end
    return out
end
-- Every limit a custom stratagem's data is checked against (the builder schema, sdk/CustomStratagemSchema.json, is
-- generated from this table: scripts/generate_custom_stratagem_schema.py).
M.LIMITS={
    definitions=M.MAX,
    id={pattern='^[a-z][a-z0-9_]*$',max=48},
    text=64,
    description=400,
    code={1,8},
    cooldown={0,M.MAX_COOLDOWN},                 -- seconds, above the minimum
    items={1,8},                                 -- support delivery items listed (one donor)
    rounds={1,64},
    eagle={uses={1,20},rearm_seconds={1,600}},
    orbital={salvos={1,16},shells_per_salvo={1,16},shell_interval={0,10},salvo_interval={0,30},scatter={0,100},
        salvo_scatter={0,100},total=64},
    expendable={levels={'presentation','model','full'}},   -- the carrier weapon clone's levels (staged live tests)
    pod={items={1,8},count={1,8}},               -- a carrier pod's item entries and each one's count (capacity: its rack)
    slots={1,8},                                 -- carrier.slots: the pod capacity a definition asks its group for
    groups=groups.ORDER,                          -- carrier.group (runtime/carrier_groups.lua)
}
M.KILL_LOGS=3            -- kill lines per call (then counted)
-- The vanilla support deliveries whose delivered items the Runtime can capture: every catalogued support weapon or
-- backpack whose pod rack is reviewed (domains/pod_payload_authoring.lua racks: the rack's active slots and their
-- entity types; the support weapon catalogue: the round a weapon fires). M.support_delivery(name) -> {stratagem, id,
-- rack, count (the rack's native items), items = {[entity type] = {kind = 'weapon' | 'backpack', projectile}}}, or nil
-- and why.
local function hex_of(resource)return(tostring(resource):gsub('^0x',''):upper())end
-- A beacon's position on this machine (research peer-messaging section 18): this machine's own beacon's state +0x30,
-- another machine's copy's creation position (runtime/beacons.lua position reads owned beacons only: nil for a copy).
local function beacon_at(world,entity)
    if not entity then return nil end
    local ok,at=pcall(barrages.beacon_position,world,entity)
    if ok and at then return at end
    return beacons.position(world,entity)
end
-- The round a support weapon fires: the attack of its entity `resource` (hex) when given; else its one round; else the
-- round of the entity its pod's rack delivers (a weapon with variants, e.g. the MG-43's 148 and 49).
local function weapon_projectile(name,resource)
    local w=SWC.weapons[name]
    local kind,mine
    for _,attack in ipairs(w and w.runtimeAttacks or{})do
        if attack.projectileType then
            if resource and attack.resourceHash and hex_of(attack.resourceHash)==resource then
                mine=mine or attack.projectileType
            end
            if kind==nil then kind=attack.projectileType elseif kind~=attack.projectileType then kind=false end
        end
    end
    if mine then return mine end
    if kind then return kind end
    if not resource then
        local pod=PP.byStratagem[name]
        local rack=pod and PP.racks[pod]
        local first=rack and rack.slots['1']and rack.slots['1'].resource
        if first then return weapon_projectile(name,hex_of(first))end
    end
    return nil
end
function M.support_delivery(name)
    local entry=catalog.stratagems[name]
    if not(entry and entry.root and entry.root.id)then return nil,tostring(name)..' is not a catalogued stratagem'end
    if entry.family~='support'and entry.family~='backpack'then
        return nil,name..' is not a support weapon or backpack (its family is '..tostring(entry.family)..')'
    end
    local pod=PP.byStratagem[name]
    local rack=pod and PP.racks[pod]
    if not rack then return nil,name..' has no reviewed pod rack'end
    local items,count={},0
    local weapon_types={}
    local w=SWC.weapons[name]
    for _,h in ipairs(w and w.resourceHashes or{})do weapon_types[hex_of(h)]=true end
    for k=1,8 do
        local slot=rack.slots[tostring(k)]
        if slot and slot.active and slot.resource and slot.resource~='0x0000000000000000'then
            count=count+1
            local t=hex_of(slot.resource)
            if not items[t]then
                local is_weapon=weapon_types[t]==true
                items[t]={kind=is_weapon and'weapon'or'backpack',projectile=is_weapon and weapon_projectile(name,t)or nil}
            end
        end
    end
    if count==0 then
        return nil,name..'\'s rack has no authored active slot (its pod is not a reviewed pickup rack: an item with no '
            ..'resolvable pickup name, or a deployable; domains/pod_payload_authoring.lua)'
    end
    return {stratagem=name,id=entry.root.id,rack=rack.resource,count=count,items=items,family=entry.family}
end
M.DELIVERIES=setmetatable({},{__index=function(_,name)
    local d=M.support_delivery(name)
    if not d then return nil end
    for t,item in pairs(d.items)do
        if item.kind=='weapon'then return {item=t,projectile=item.projectile,stableId=d.id}end
    end
end})

local defs,order={},{}
local verbose=false
local function log(text)log_module.emit('[HD2Runtime] custom stratagem '..text)end
local function vlog(text)if verbose then log(text)end end
-- More log lines: every carrier candidate and its verdict, each custom Eagle call's per-rocket trace with its read-only
-- probes (runtime/custom_eagles.lua) and every repeated Pelican gun target line (runtime/pelican_weapon.lua). Off by
-- default.
function M.verbose(on)
    verbose=on==true;eagles.verbose=verbose
    log_module.verbose(verbose)
    local ok,pw=pcall(require,'hd2runtime/runtime/pelican_weapon')
    if ok and type(pw)=='table'then pw.verbose=verbose end
end
local function n1(v)return v and('%.1f'):format(v)or'?'end
local function at(v)return v and('(%.1f, %.1f, %.1f)'):format(v.x,v.y,v.z)or'(?)'end

local names_by_id={}
for name,entry in pairs(catalog.stratagems)do if entry.root then names_by_id[entry.root.id]=name end end
local function stratagem_id(name)
    local entry=type(name)=='string'and catalog.stratagems[name]
    return entry and entry.root and entry.root.id
end

-------------------------------------------------------------------------------------------- registration --
-- The icon colour set a custom stratagem shows aboard the ship (the custom panel's tile, the native slot overlay):
-- its beacon category's. A support custom stratagem takes a support stratagem's (blue, as its support carrier's HUD
-- slot and beacon are in the mission): its delivery's when that is a blue support stratagem, else the first such
-- catalogued stratagem by name. Every other one keeps its token's (unchanged). Returns a stratagem name or nil.
local function colour_donor(policy,delivery)
    if delivery~='runtime'and delivery.kind=='sentry'then return delivery.stratagem end
    if policy.beacon~='support'then return nil end
    local observed=SLOTS.beacon.observed
    local function blue_support(name)
        local entry=catalog.stratagems[name]
        local look=observed[name]
        return entry~=nil and entry.family=='support'and look~=nil and look.ping==2
    end
    if delivery~='runtime'and blue_support(delivery.stratagem)then return delivery.stratagem end
    local names={}
    for name in pairs(observed)do if blue_support(name)then names[#names+1]=name end end
    table.sort(names)
    return names[1]
end
local CALLBACKS={'on_called','on_beacon_created','on_beacon_landed','on_activate','on_delivered'}
local SPEC_KEYS={id=true,name=true,name_cased=true,description=true,icon=true,code=true,cooldown=true,carrier=true,
    assets=true,delivery=true,sentry=true,eagle=true,orbital=true,pelican=true,silo=true,uses=true,traits=true,
    selection=true,max_per_player=true}

----------------------------------------------------------------------------------- the payload families (data) --
-- A donor reference: a catalogued name, or a typed handle (hd2.support_weapon(name), hd2.backpack(name), or a table
-- naming a stratagem). Returns the name or nil.
local function donor_name(ref)
    if type(ref)=='string'then return ref end
    if type(ref)=='table'then
        return rawget(ref,'stratagem')or rawget(ref,'weapon')or rawget(ref,'backpack')or rawget(ref,'name')
    end
end
M.donor_name=donor_name
-- The reviewed round a support weapon fires (a weapon modification's `projectile`), or nil.
function M.weapon_round(name)return weapon_projectile(name)end
local function family_of(name)local e=catalog.stratagems[name];return e and e.family end
local WEAPON_KEYS={projectile=true,rpm=true,spread=true,ammo=true,recoil=true,impact_explosion=true,rounds=true,
    direct_damage=true,
    sound=true}
-- A weapon modification table (a mod's data) -> {weapon = custom_weapons spec, impact = donor, rounds, assets}; errors.
-- projectile: the round a support weapon fires (its name or hd2.support_weapon(name)); its call-in package becomes an
-- asset. impact_explosion: a reviewed explosion donor (runtime/explosion_donors.lua); its package becomes an asset.
-- sound (allow_sound: a sentry's weapon): a firing sound of the catalogue (runtime/weapon_sounds.lua); the stratagem
-- that provides its bank becomes an asset.
-- direct_damage (allow_damage: an expendable delivery's modify): the damage of each fired round's direct hit, a reviewed
-- override of the weapon's round (runtime/projectile_impact.lua DIRECT DAMAGE; domains/direct_damage.lua: the EAT-17's
-- 500), written per round with its impact_explosion (required with it).
local function weapon_modify(value,where,allow_impact,weapon_name,allow_sound,allow_damage)
    assert(type(value)=='table',where..' must be a table')
    -- (The delivery would refuse it: the selector rebuilds the rate from the type's three slots.)
    assert(value.rpm==nil or not weapons.binds_rate_selector(weapon_name),('%s.rpm: the %s binds the rate-of-fire '
        ..'selector, which rebuilds its rate from its type\'s three slots: a per-call rpm is refused (its modes are '
        ..'hd2.fields.fire_rate.modes)'):format(where,tostring(weapon_name)))
    local out={weapon={},assets={}}
    for key,v in pairs(value)do
        assert(WEAPON_KEYS[key],where..': unsupported weapon modification '..tostring(key)..' (supported: projectile, '
            ..'rpm, spread, ammo, recoil'..(allow_impact and', impact_explosion, rounds'or'')..(allow_damage and
            ', direct_damage'or'')..(allow_sound and', sound'or'')..')')
        if key=='projectile'then
            local name=donor_name(v)
            local kind=name and weapon_projectile(name)
            assert(kind,where..'.projectile must name a support weapon whose round is reviewed (its name or '
                ..'hd2.support_weapon(name)); a raw projectile type is not accepted (its package must be known)')
            out.weapon.projectile=kind
            out.projectile_donor=name
            out.assets[#out.assets+1]=name
        elseif key=='impact_explosion'then
            assert(allow_impact,where..'.impact_explosion is not supported here (an automatic weapon fires hundreds of '
                ..'rounds; the per-projectile conversion is for launchers and rockets)')
            local name=donors.resolve(v)
            assert(name,where..'.impact_explosion must be a reviewed explosion donor: '..table.concat(donors.names(),', '))
            out.impact=name
            out.assets[#out.assets+1]=name
        elseif key=='sound'then
            assert(allow_sound,where..'.sound is supported on a sentry\'s weapon only')
            local WSN=require('hd2runtime/runtime/weapon_sounds')
            local canonical,entry=WSN.resolve(v)
            assert(entry and not entry.own,where..'.sound must be a firing sound of the catalogue (hd2.sounds.list(), '
                ..'docs/weapon-sounds.md): '..WSN.hint())
            out.weapon.sound=canonical
            if entry.stratagem then out.assets[#out.assets+1]=entry.stratagem end
        elseif key=='direct_damage'then
            assert(allow_damage,where..'.direct_damage is supported on an expendable delivery\'s modify only')
            local kind=weapon_name and weapon_projectile(weapon_name)
            local o,_,why=impacts.damage_override(kind or 0,v)
            assert(type(v)=='number'and o,where..'.direct_damage: '..tostring(why))
            out.damage=v
        elseif key=='rounds'then
            local R=M.LIMITS.rounds
            assert(type(v)=='number'and v>=R[1]and v<=R[2]and v%1==0,('%s.rounds must be %d..%d'):format(where,R[1],R[2]))
            out.rounds=v
        else
            out.weapon[key]=v
        end
    end
    local invalid=weapons.check(out.weapon)
    assert(not invalid,where..': '..tostring(invalid))
    assert(out.damage==nil or out.impact,where..'.direct_damage needs '..where..'.impact_explosion (it is written with each '
        ..'round\'s impact explosion)')
    return out
end
-- A CARRIER POD's item entries (docs/custom-stratagem-api.md "pod"): the support carrier pod's delivery.items, an
-- expendable definition's delivery.pod. Each {item, count, modify, allow_unverified_effect}: item a typed handle
-- (hd2.support_weapon(name), hd2.backpack(name), hd2.weapon(name) for a primary) or, in an expendable pod, 'clone' (its
-- carrier weapon, the clone). Kinds (domains/carrier_pod_items.lua): support weapons and backpacks (vanilla rack items,
-- CONFIRMED), primaries only with allow_unverified_effect = true (not live-tested), secondaries and throwables refused.
-- Returns {entries = {{key, label, kind, role, resource, count, modify, projectile, clone}}, units = {{role, resource,
-- label, key, clone}} (one per spawned item, in order), total, deps = {package dependencies}, assets = {stratagem
-- names}}; errors.
local POD_ITEM_KEYS={item=true,count=true,modify=true,allow_unverified_effect=true}
local function pod_spec(list,where,clone_ok)
    local PL=M.LIMITS.pod
    assert(type(list)=='table'and#list>=PL.items[1]and#list<=PL.items[2],('%s must list %d to %d items'):format(where,
        PL.items[1],PL.items[2]))
    local out={entries={},units={},total=0,deps={},assets={}}
    local seen={}
    for k,e in ipairs(list)do
        local at=where..'['..k..']'
        assert(type(e)=='table',at..' must be a table')
        for key in pairs(e)do
            assert(POD_ITEM_KEYS[key],at..': unsupported pod item field '..tostring(key)..' (supported: item, count, '
                ..'modify, allow_unverified_effect)')
        end
        local count=e.count==nil and 1 or e.count
        assert(type(count)=='number'and count%1==0 and count>=PL.count[1]and count<=PL.count[2],
            ('%s.count must be a whole number %d..%d'):format(at,PL.count[1],PL.count[2]))
        local entry
        if e.item=='clone'then
            assert(clone_ok,at..".item 'clone' is an expendable definition's carrier weapon (delivery.pod only)")
            assert(e.modify==nil,at..'.modify: the clone takes delivery.modify')
            assert(e.allow_unverified_effect==nil,at..'.allow_unverified_effect: the clone is a reviewed kind')
            entry={clone=true,key='clone',label='the clone',kind='clone',role='weapon',count=count}
        else
            local item,why=carrier_pod.item(e.item)
            assert(item,at..'.item: '..tostring(why))
            if item.status=='unverified'then
                assert(e.allow_unverified_effect==true,('%s: %s is a %s in a pod rack: not live-tested (research '
                    ..'carrier-pod-items, stage A); it needs allow_unverified_effect = true'):format(at,item.label,
                    item.kind))
            else
                assert(e.allow_unverified_effect==nil,at..'.allow_unverified_effect: '..item.label..' is a reviewed kind ('
                    ..item.kind..'): no acknowledgement')
            end
            local dep=core_assets.dependency(item.key)
            assert(dep,at..'.item: no package is known for '..item.label..' (its assets could not be loaded)')
            out.deps[#out.deps+1]=dep
            entry={key=item.key,label=item.label,kind=item.kind,role=item.role,resource=item.resource,count=count,
                status=item.status}
            if item.kind=='support_weapon'then entry.projectile=weapon_projectile(item.label,hex_of(item.resource))end
            if e.modify~=nil then
                assert(item.kind~='backpack',at..'.modify: '..item.label..' is a backpack; no instance-local backpack '
                    ..'field is reviewed')
                entry.modify=weapon_modify(e.modify,at..'.modify',item.kind=='support_weapon',item.label)
                assert(not entry.modify.impact or entry.projectile,at..'.modify.impact_explosion: '..item.label
                    ..'\'s round is not reviewed')
                for _,a in ipairs(entry.modify.assets)do out.assets[#out.assets+1]=a end
            end
        end
        assert(not seen[entry.key],at..': '..entry.label..' is listed twice (give it a count)')
        seen[entry.key]=true
        out.entries[#out.entries+1]=entry
        out.total=out.total+count
        for _=1,count do
            out.units[#out.units+1]={role=entry.role,resource=entry.resource,label=entry.label,
                key=not entry.clone and entry.key or nil,clone=entry.clone}
        end
    end
    assert(out.total<=PL.count[2],('%s: %d items in all; at most %d (a rack has 8 slots)'):format(where,out.total,
        PL.count[2]))
    return out
end
M.pod_spec=pod_spec
-- A pod's items as text (logs and the registry hash): '<key> x<count>[ {modify}]', in order.
local function pod_text(p)
    local parts={}
    for _,e in ipairs(p.entries)do
        local mod={}
        for k,v in pairs(e.modify and e.modify.weapon or{})do mod[#mod+1]=k..'='..tostring(v)end
        if e.modify and e.modify.impact then mod[#mod+1]='impact='..e.modify.impact end
        if e.modify and e.modify.rounds then mod[#mod+1]='rounds='..e.modify.rounds end
        table.sort(mod)
        parts[#parts+1]=e.key..' x'..e.count..(#mod>0 and(' {'..table.concat(mod,',')..'}')or'')
    end
    return table.concat(parts,'; ')
end
M.pod_text=pod_text
-- The units of a pod on one carrier (the clone's resource: that carrier weapon's own entity).
local function pod_units(p,carrier_entity)
    local out={}
    for k,u in ipairs(p.units)do
        out[k]={role=u.role,resource=u.clone and carrier_entity or u.resource,label=u.clone and'the clone'or u.label,
            key=u.key,clone=u.clone}
    end
    return out
end
-- A pod delivery's items by entity type ({[type] = {kind, projectile, modify, impact, rounds, label}}), its types and
-- its slot layout ({[slot] = type}) on one carrier. clone: {resource, projectile, modify, impact, rounds}.
local function pod_items(p,carrier,carrier_entity,clone)
    local items,types={},{}
    for _,e in ipairs(p.entries)do
        local t
        if e.clone then
            t=hex_of(carrier_entity)
            items[t]={kind='weapon',projectile=clone.projectile,modify=clone.modify,impact=clone.impact,
                rounds=clone.rounds,damage=clone.damage,label='the clone'}
        else
            t=hex_of(e.resource)
            items[t]={kind=e.role=='backpack'and'backpack'or'weapon',projectile=e.projectile,
                modify=e.modify and e.modify.weapon,impact=e.modify and e.modify.impact,rounds=e.modify and e.modify.rounds,
                label=e.label,item_kind=e.kind}
        end
        types[t]=true
    end
    local plan=carrier_pod.plan(carrier,pod_units(p,carrier_entity))
    local layout
    if plan then
        layout={}
        for _,l in ipairs(plan.layout)do layout[l.slot]=hex_of(l.resource)end
    end
    return items,types,layout,plan
end

-- The carrier families a policy allows (allow_families, else prefer_families); errors unless they are exactly `only`.
local function require_families(policy,only,what)
    local allowed=policy.allow_families or policy.prefer_families
    assert(allowed and#allowed>=1,('%s needs carrier = {..., allow_families = {%s}}: its carrier must be %s only'):format(
        what,"'"..only.."'",only))
    for _,f in ipairs(allowed)do
        assert(f==only,('%s allows the %s family only (carrier family %s given)'):format(what,only,tostring(f)))
    end
end
-- delivery: 'runtime', {stratagem = name} (the older form) or {family = 'support', items = {{donor, count, modify}}}.
local function support_delivery_spec(value,policy)
    assert(type(value)=='table',"delivery must be 'runtime', {stratagem = name} or {family = 'support', items = {...}}")
    local items
    if value.family~=nil or value.items~=nil then
        for key in pairs(value)do
            assert(key=='family'or key=='items','unsupported delivery field: '..tostring(key))
        end
        assert(value.family=='support',"delivery.family must be 'support'")
        local I=M.LIMITS.items
        assert(type(value.items)=='table'and#value.items>=I[1]and#value.items<=I[2],
            ('delivery.items must list %d to %d items'):format(I[1],I[2]))
        items=value.items
    else
        for key in pairs(value)do assert(key=='stratagem','unsupported delivery field: '..tostring(key))end
        assert(type(value.stratagem)=='string',"delivery must be 'runtime' or {stratagem = name}")
        items={{donor=value.stratagem}}
    end
    local stratagem
    local out={modify={},assets={}}
    for k,item in ipairs(items)do
        local where='delivery.items['..k..']'
        assert(type(item)=='table',where..' must be a table')
        for key in pairs(item)do
            assert(key=='donor'or key=='count'or key=='modify',where..': unsupported item field '..tostring(key))
        end
        local name=donor_name(item.donor)
        assert(name,where..'.donor must name a support weapon or backpack (its name, hd2.support_weapon(name) or '
            ..'hd2.backpack(name))')
        assert(stratagem==nil or name==stratagem,('delivery.items: one native pod delivers ONE stratagem\'s rack; %s and '
            ..'%s cannot be delivered by one call (list one donor)'):format(tostring(stratagem),name))
        assert(stratagem==nil,'delivery.items: list each donor once')
        stratagem=name
        local d,why=M.support_delivery(name)
        assert(d,where..'.donor: '..tostring(why))
        if item.count~=nil then
            assert(item.count==d.count,('%s.count: the %s pod holds %d (its rack\'s own count); another count is not '
                ..'supported (the rack lists are shared definitions)'):format(where,name,d.count))
        end
        out.base=d
        if item.modify~=nil then
            local has_weapon=false
            for _,i in pairs(d.items)do if i.kind=='weapon'then has_weapon=true end end
            assert(has_weapon,where..'.modify: '..name..' delivers no weapon; no instance-local backpack field is reviewed')
            out.modify=weapon_modify(item.modify,where..'.modify',true,name)
            for _,a in ipairs(out.modify.assets)do out.assets[#out.assets+1]=a end
        end
    end
    assert(policy.beacon=='support','a support delivery needs a support (blue beacon) carrier')
    local d=out.base
    local types={}
    for t in pairs(d.items)do types[t]=true end
    local legacy
    for t,i in pairs(d.items)do if i.kind=='weapon'then legacy=legacy or{item=t,projectile=i.projectile}end end
    return {kind='support',stratagem=d.stratagem,id=d.id,items=d.items,item_types=types,count=d.count,
        item=legacy and legacy.item,projectile=legacy and legacy.projectile,modify=out.modify.weapon,
        impact=out.modify.impact,rounds=out.modify.rounds,family=d.family},out.assets
end
-- delivery = {family = 'support', items = {{item, count, modify, allow_unverified_effect}, ...}}: a CARRIER POD (the
-- support_pod group): the carrier's OWN pod (no beacon redirect) whose exclusive rack holds these items for the
-- mission (runtime/carrier_pod.lua); every spawned item captured from that rack and each weapon's modify applied to it.
-- Several players: refused in this pass (solo host). Mixing `item` and `donor` entries is refused.
local function carrier_pod_delivery_spec(value,policy)
    for key in pairs(value)do
        assert(key=='family'or key=='items','unsupported delivery field: '..tostring(key))
    end
    for k,item in ipairs(value.items)do
        assert(item.donor==nil,('delivery.items[%d]: a delivery lists items (the carrier\'s own pod) or donors (a donor\'s '
            ..'vanilla pod), never both'):format(k))
    end
    local p=pod_spec(value.items,'delivery.items',false)
    assert(policy.beacon=='support','a carrier pod needs a support (blue beacon) carrier')
    local items,types={},{}
    for _,e in ipairs(p.entries)do
        local t=hex_of(e.resource)
        items[t]={kind=e.role=='backpack'and'backpack'or'weapon',projectile=e.projectile,
            modify=e.modify and e.modify.weapon,impact=e.modify and e.modify.impact,rounds=e.modify and e.modify.rounds,
            label=e.label,item_kind=e.kind}
        types[t]=true
    end
    return {kind='pod',family='support',pod=p,items=items,item_types=types,count=p.total},p.assets
end

-- delivery = {family = 'expendable', weapon = the donor (hd2.support_weapon(name)), presentation = {name, icon},
-- modify = {impact_explosion, rounds, rpm, spread, ammo, recoil}, level = 'presentation' | 'model' | 'full' (or a Mod
-- Options choice of those)}: a mission-scoped clone of the donor on an unused carrier WEAPON of its expendable component
-- class (runtime/weapon_carriers.lua: for the EAT-17 the EAT-700, then the EAT-411; never one a lobby member brings or
-- another custom stratagem holds), delivered by that carrier weapon's own vanilla pod (its rack's launchers captured, as
-- a support delivery's). The carrier weapon's type records become the donor's for the mission (runtime/weapon_clone.lua),
-- its pod row presents as the custom stratagem; both are restored aboard the ship. modify stays instance-local.
local EXPENDABLE_KEYS={family=true,weapon=true,presentation=true,modify=true,level=true,pod=true,round=true}
local function clone_donors()
    local out={}
    for _,name in ipairs(weapon_clone.donors())do out[#out+1]=name end
    return out
end
M.clone_donors=clone_donors
-- A level given as a Mod Options choice is read when used (each mission start freezes it); an unusable value is the
-- most conservative level.
local function level_value(level)
    if level==nil then return'full'end
    if type(level)=='string'then return level end
    local ok,value=pcall(function()return level:get()end)
    return(ok and weapon_clone.LEVELS[value])and value or'presentation'
end
function M.level_of(d)return d.kind=='expendable'and level_value(d.delivery.level)or nil end
local function expendable_spec(value,policy)
    for key in pairs(value)do
        assert(EXPENDABLE_KEYS[key],'unsupported expendable delivery field: '..tostring(key)..' (supported: family, weapon, '
            ..'presentation, modify, level, pod, round)')
    end
    local donor=donor_name(value.weapon)
    assert(donor and weapon_clone.donor(donor),'delivery.weapon must name a support weapon with a reviewed expendable '
        ..'clone class (hd2.support_weapon(name)): '..table.concat(clone_donors(),', '))
    assert(policy.beacon=='support','an expendable delivery needs a support (blue beacon) carrier')
    local level=value.level
    if level==nil then level='full'
    elseif type(level)=='string'then
        assert(weapon_clone.LEVELS[level],"delivery.level must be 'presentation', 'model' or 'full'")
    else
        local options=require('hd2runtime/api/options')
        assert(options.is_handle(level)and level.kind=='choice','delivery.level must be \'presentation\', \'model\' or '
            ..'\'full\', or a Mod Options choice whose values are those')
        for _,v in ipairs(level.values)do
            assert(weapon_clone.LEVELS[v],'delivery.level: a choice value must be presentation, model or full ('..tostring(v)..')')
        end
    end
    local presentation={}
    if value.presentation~=nil then
        assert(type(value.presentation)=='table','delivery.presentation must be {name, icon}')
        for key in pairs(value.presentation)do
            assert(key=='name'or key=='icon','unsupported delivery.presentation field: '..tostring(key)..' (supported: '
                ..'name, icon)')
        end
        presentation.name=value.presentation.name
        presentation.icon=value.presentation.icon
    end
    local mod={weapon={},assets={}}
    if value.modify~=nil then
        assert(type(value.modify)=='table','delivery.modify must be a table')
        assert(value.modify.projectile==nil,'delivery.modify.projectile is not supported: the clone fires its donor\'s '
            ..'own round (that is the clone)')
        mod=weapon_modify(value.modify,'delivery.modify',true,donor,nil,true)
    end
    local deliveries,assets,pool={},{},weapon_clone.pool(donor)
    for _,name in ipairs(pool)do
        local d,why=M.support_delivery(name)
        assert(d,'the carrier weapon '..name..': '..tostring(why))
        deliveries[name]=d
        assets[#assets+1]=name
    end
    for _,a in ipairs(mod.assets)do assets[#assets+1]=a end
    -- round: another support weapon's reviewed round the clone fires at every level (runtime/weapon_clone.lua M.round;
    -- the carrier type's ProjectileWeapon +0, converted on every machine at its mission start like the clone itself):
    -- the RL-77 Airburst's round 312 on an EAT-17 clone. Its weapon's call-in package (the round's unit) is an asset.
    local round
    if value.round~=nil then
        local rname=donor_name(value.round)
        local r=type(rname)=='string'and weapon_clone.round(donor,rname)
        local reviewed=weapon_clone.rounds(donor)
        assert(r,'delivery.round must name a support weapon whose round is reviewed for the '..donor..'\'s clone '
            ..'(hd2.support_weapon(name)): '..(#reviewed>0 and table.concat(reviewed,', ')or'none'))
        assert(mod.impact==nil,'delivery.round with delivery.modify.impact_explosion: the '..rname..'\'s round has its '
            ..'own explosions (an expiry burst), which a per-projectile impact conversion refuses')
        assert(mod.damage==nil,'delivery.round with delivery.modify.direct_damage: the override is reviewed for the '
            ..donor..'\'s own round only')
        round={name=rname,type=r.type}
        assets[#assets+1]=rname
    end
    -- pod: what the carrier weapon's own pod holds (the clone and other items); its capacity is the pool weapon's
    -- usable rack slots, and a pool weapon whose rack cannot hold them is never its carrier weapon.
    local pod,fits
    if value.pod~=nil then
        pod=pod_spec(value.pod,'delivery.pod',true)
        local clones=0
        for _,e in ipairs(pod.entries)do if e.clone then clones=e.count end end
        assert(clones>=1,"delivery.pod must hold the clone ({item = 'clone', count = n})")
        fits={}
        local why={}
        for _,name in ipairs(pool)do
            local c=weapon_clone.carrier(name)
            local plan,_,reason=carrier_pod.plan(name,pod_units(pod,c and c.entity))
            if plan then fits[name]=true else why[#why+1]=reason end
        end
        assert(next(fits),'delivery.pod: no carrier weapon of the '..donor..'\'s class can hold it: '..table.concat(why,'; '))
        for _,a in ipairs(pod.assets)do assets[#assets+1]=a end
    end
    -- The DONOR ITSELF, the pool's last member (runtime/weapon_carriers.lua; the user's rules of 2026-10-06): when every
    -- clone carrier weapon of the class is taken, the regular donor from its OWN native pod, reserved like any carrier
    -- (a native pick of it takes it; as the last viable carrier it is blocked in the native picker). No clone and no type write (the donor's type is
    -- shared: the EAT-17 is in the world loot table), no rack write (its rack is shared too): only this call's
    -- launchers change, per projectile (runtime/projectile_impact.lua; mirrored by runtime/custom_mp_items.lua), and they
    -- keep the donor's own name and icon. Possible when its pod holds only the clone, at most as many as the donor's own
    -- rack delivers; a round's definition then explodes as that round's weapon's reviewed launcher donor on impact (the
    -- RL-77's cluster: no proximity airburst, the user's choice).
    local fallback
    do
        local native=M.support_delivery(donor)
        local clones,others=0,0
        for _,e in ipairs(pod and pod.entries or{})do if e.clone then clones=clones+e.count else others=others+1 end end
        if not pod then clones=native and native.count or 0 end
        local impact=mod.impact
        if round then impact=donors.resolve(round.name,{internal=true})end
        if native and others==0 and clones<=native.count and(not round or impact)then
            fallback={stratagem=donor,id=native.id,delivery=native,impact=impact,rounds=mod.rounds,
                damage=not round and mod.damage or nil}
        end
    end
    local entry=catalog.stratagems[donor]
    return {kind='expendable',stratagem=donor,id=entry.root.id,donor=donor,pool=pool,deliveries=deliveries,level=level,
        presentation=presentation,modify=mod.weapon,impact=mod.impact,rounds=mod.rounds,damage=mod.damage,
        family='support',projectile=weapon_clone.donor(donor).projectile,round=round,pod=pod,fits=fits,
        fallback=fallback},assets
end

-- delivery = {family = 'weapon', weapon = a variant host (hd2.support_weapon(name)), round = hd2.attack_output(name),
-- model = hd2.resources.model(id) or an id of the mod's models, model_use = 'apply' | 'check' (or a Mod Options choice
-- of those), presentation = {name, icon}, allow_shared}: a mission-scoped VARIANT of a support weapon on its OWN type
-- (runtime/weapon_clone.lua variant; domains/weapon_variants.lua: every support weapon with exclusively owned records
-- and a stratagem of its own, 26 of 27 since 2026-10-08; first the M-1000 Maxigun). Its pool is itself: a lobby member
-- bringing it makes the variant unavailable, and the selected variant blocks it in the native picker (the user's rule
-- of 2026-10-06: no fallback). A SHARED host (world loot or another hellpod rack also brings the type: the MG-43, the
-- EAT-17, ...) converts those copies too, so it needs allow_shared = true (the author's consent; never added here). A
-- host without a ProjectileWeapon (beam, arc, spray: the LAS-98, the ARC-3, the flamethrowers, the Meltagun) has no
-- round.
-- Its own vanilla pod delivers it with its own items (the Maxigun's backpack too). The type's presentation, round
-- (ProjectileWeapon +0: a catalogued attack output of the weapon's own compatibility class, never an unverified donor;
-- its package loaded first) and model (UnitPath: the mod's Runtime-owned unit, runtime/model_resources.lua) change for
-- the mission, restored aboard the ship. model_use = 'check' only reads, at mission start, whether the model is
-- loaded and exact (MODEL READY / MODEL NOT READY) and keeps the vanilla model.
local variant_spec
do
    local models=require('hd2runtime/runtime/model_resources')
    local VARIANT_KEYS={family=true,weapon=true,presentation=true,round=true,model=true,model_use=true,allow_shared=true}
    M.MODEL_USES={apply=true,check=true}
    local function model_use_value(use)
        if use==nil then return'apply'end
        if type(use)=='string'then return use end
        local ok,value=pcall(function()return use:get()end)
        return(ok and M.MODEL_USES[value])and value or'check'
    end
    M.model_use_value=model_use_value
    function variant_spec(value,policy,owner)
        for key in pairs(value)do
            assert(VARIANT_KEYS[key],'unsupported weapon delivery field: '..tostring(key)..' (supported: family, weapon, '
                ..'round, model, model_use, presentation, allow_shared)')
        end
        local weapon=donor_name(value.weapon)
        local host=weapon and weapon_clone.variant(weapon)
        local excluded=weapon and weapon_clone.variant_excluded(weapon)
        assert(not excluded,'delivery.weapon: the '..tostring(weapon)..' cannot have a variant: '..tostring(excluded))
        assert(host,'delivery.weapon must name a reviewed variant weapon (hd2.support_weapon(name)): '
            ..table.concat(weapon_clone.variants(),', '))
        assert(value.allow_shared==nil or type(value.allow_shared)=='boolean','delivery.allow_shared must be a boolean')
        if host.shared then
            assert(value.allow_shared==true,('delivery.allow_shared = true is required: the %s variant converts its '
                ..'type, which is shared: %s'):format(weapon,table.concat(host.shared,'; ')))
        end
        assert(policy.beacon=='support','a weapon delivery needs a support (blue beacon) carrier')
        local presentation={}
        if value.presentation~=nil then
            assert(type(value.presentation)=='table','delivery.presentation must be {name, icon}')
            for key in pairs(value.presentation)do
                assert(key=='name'or key=='icon','unsupported delivery.presentation field: '..tostring(key)..' (supported: '
                    ..'name, icon)')
            end
            presentation.name=value.presentation.name
            presentation.icon=value.presentation.icon
        end
        local d,why=M.support_delivery(weapon)
        assert(d,'the weapon '..weapon..': '..tostring(why))
        local assets={weapon}
        -- round: a catalogued attack output of the weapon's own compatibility class (the Maxigun's: conventional_plain), a
        -- reviewed, live-catalogued one (an unverified donor is refused here: no acknowledgement path).
        local round,deps
        if value.round~=nil then
            assert(host.round,'delivery.round: the '..weapon..' fires no projectile (no ProjectileWeapon): it has no round '
                ..'to change')
            local A=require('hd2runtime/domains/attack_outputs')
            local r=value.round
            assert(type(r)=='table'and rawget(r,'resource')=='attack_output','delivery.round must be hd2.attack_output(name)')
            local out=A.outputs[rawget(r,'output')]
            assert(out and out.family=='projectile'and out.editable and type(out.currentDefault)=='number',
                'delivery.round must be a catalogued projectile output')
            assert(not out.unverifiedDonor,'delivery.round: '..out.id..' is not live-tested yet (an unverified donor)')
            local own
            for _,o in pairs(A.outputs)do
                if o.family=='projectile'and o.owner and o.owner.name==weapon and not o.unverifiedDonor
                    and o.currentDefault==host.projectile then own=o end
            end
            assert(own,'the '..weapon..'\'s own projectile output is not catalogued')
            assert(out.compatibilityClass==own.compatibilityClass,('delivery.round: %s is %s; the %s fires %s rounds (the '
                ..'compatibility class must be its own)'):format(out.id,tostring(out.compatibilityClass),weapon,
                tostring(own.compatibilityClass)))
            local dep=out.dependencyKey and core_assets.dependency(out.dependencyKey)
            assert(dep,'delivery.round: no package is catalogued for '..out.id)
            round={name=out.owner and out.owner.name or out.id,type=out.currentDefault,package=dep.package,
                label=out.owner and out.owner.name or out.id,output=out.id,class=out.compatibilityClass}
            deps={dep}
        end
        local model,use
        if value.model~=nil then
            local h=value.model
            if type(h)=='string'then h=models.handle(h,owner)end
            assert(models.issued(h),'delivery.model must be hd2.resources.model(id) or the id of one of the mod\'s models')
            model=h
            use=value.model_use
            if use==nil then use='apply'
            elseif type(use)=='string'then
                assert(M.MODEL_USES[use],"delivery.model_use must be 'apply' or 'check'")
            else
                local options=require('hd2runtime/api/options')
                assert(options.is_handle(use)and use.kind=='choice','delivery.model_use must be \'apply\' or \'check\', or a '
                    ..'Mod Options choice whose values are those')
                for _,v in ipairs(use.values)do
                    assert(M.MODEL_USES[v],'delivery.model_use: a choice value must be apply or check ('..tostring(v)..')')
                end
            end
        else
            assert(value.model_use==nil,'delivery.model_use needs delivery.model')
        end
        local entry=catalog.stratagems[weapon]
        return {kind='expendable',variant=true,stratagem=weapon,id=entry.root.id,donor=weapon,pool={weapon},
            deliveries={[weapon]=d},level='variant',presentation=presentation,modify={},family='support',
            projectile=host.projectile,round=round,model=model,model_use=use,variant_deps=deps},assets
    end
end

-- sentry = {donor = a sentry stratagem, weapon = {projectile, rpm, spread, ammo, recoil}}.
local function sentry_spec(value,policy)
    assert(type(value)=='table','sentry must be {donor = name, weapon = {...}}')
    for key in pairs(value)do assert(key=='donor'or key=='weapon','unsupported sentry field: '..tostring(key))end
    local name=donor_name(value.donor)
    local entry=name and catalog.stratagems[name]
    assert(entry and entry.family=='sentry'and entry.deployedEntity and entry.deployedEntity.resource and entry.root,
        'sentry.donor must be a catalogued sentry (e.g. A/G-16 Gatling Sentry)')
    assert(policy.beacon=='support','a sentry needs a support (blue beacon) carrier')
    require_families(policy,'sentry','a sentry')
    local mod={weapon={},assets={}}
    if value.weapon~=nil then mod=weapon_modify(value.weapon,'sentry.weapon',false,nil,true)end
    return {kind='sentry',stratagem=name,id=entry.root.id,content_type=hex_of(entry.deployedEntity.resource),
        weapon=mod.weapon},mod.assets
end
-- eagle = {donor = an Eagle, uses = per rearm, rearm_seconds, payload = {impact_explosion = donor}}.
local function eagle_spec(value,policy,cooldown)
    assert(type(value)=='table','eagle must be {donor = name, uses = n, payload = {...}}')
    assert(value.pattern==nil,'eagle.pattern is not supported: the strike pattern is the donor Eagle\'s own '
        ..'(EagleComponentData, a shared definition with no reviewed per-call field); choose the donor whose run you want')
    for key in pairs(value)do
        assert(key=='donor'or key=='uses'or key=='payload'or key=='rearm_seconds','unsupported eagle field: '..tostring(key))
    end
    local name=donor_name(value.donor)
    local reviewed=name and eagles.EAGLES[name]
    local entry=name and catalog.stratagems[name]
    assert(reviewed and entry and entry.family=='eagle'and entry.root,'eagle.donor must be a catalogued Eagle: '
        ..'its jet and strike are reviewed (research/custom-payloads)')
    assert(policy.beacon=='offensive','an Eagle needs an offensive (red beacon) carrier')
    require_families(policy,'eagle','an Eagle')
    local EL=M.LIMITS.eagle
    local uses=value.uses or reviewed.uses
    assert(type(uses)=='number'and uses>=EL.uses[1]and uses<=EL.uses[2]and uses%1==0,
        ('eagle.uses must be %d..%d (uses per rearm)'):format(EL.uses[1],EL.uses[2]))
    local rearm=value.rearm_seconds
    assert(rearm==nil or(type(rearm)=='number'and rearm>=EL.rearm_seconds[1]and rearm<=EL.rearm_seconds[2]),
        ('eagle.rearm_seconds must be %d..%d'):format(EL.rearm_seconds[1],EL.rearm_seconds[2]))
    local out={kind='eagle',stratagem=name,id=entry.root.id,jet=hex_of(reviewed.jet),projectile=reviewed.strikeProjectile,
        uses=uses,rearm_seconds=rearm}
    local assets={}
    if value.payload~=nil then
        assert(type(value.payload)=='table','eagle.payload must be a table')
        assert(value.payload.projectile==nil,'eagle.payload.projectile is not supported: the strike projectile is the '
            ..'donor Eagle\'s own (a shared definition); the call\'s own rockets take impact_explosion')
        for key in pairs(value.payload)do
            assert(key=='impact_explosion','unsupported eagle.payload field: '..tostring(key)..' (supported: impact_explosion)')
        end
        if value.payload.impact_explosion~=nil then
            local d=donors.resolve(value.payload.impact_explosion)
            assert(d,'eagle.payload.impact_explosion must be a reviewed explosion donor: '..table.concat(donors.names(),', '))
            assert(reviewed.strikeProjectile and reviewed.rocket and reviewed.rocket.impact>0 and reviewed.rocket.expiry==0,
                name..'\'s strike projectile has no impact explosion only: its impact cannot be replaced')
            out.impact=d
            assets[#assets+1]=d
        end
    end
    assert(cooldown==nil,'an Eagle keeps its native cooldown and rearm: no cooldown')
    return out,assets
end
-- orbital = {shell, pattern, salvos, shells_per_salvo, shell_interval, salvo_interval, scatter, salvo_scatter,
-- impact_explosion}: a Runtime bombardment (runtime/bombardment_executor.lua; its shells exist on the caller's machine
-- only). Or orbital = {pattern, impact_explosion, native = true}: the pattern donor's OWN native barrage (the beacon's
-- delivery becomes the donor's; the game creates the barrage, replicated to every player, and every machine fires its
-- shells locally), each of its shells exploding as impact_explosion's on every compatible machine's own copy
-- (runtime/custom_barrages.lua, runtime/custom_mp_items.lua). Native: the donor's record is used exactly as the game
-- reads it (no pattern override, no other shell).
local ORBITAL_KEYS={shell=true,pattern=true,salvos=true,shells_per_salvo=true,shell_interval=true,salvo_interval=true,
    scatter=true,salvo_scatter=true,impact_explosion=true,explosion_scale=true,native=true}
local function orbital_spec(value)
    assert(type(value)=='table','orbital must be a table')
    for key in pairs(value)do assert(ORBITAL_KEYS[key],'unsupported orbital field: '..tostring(key))end
    assert(value.explosion_scale==nil,'orbital.explosion_scale is not supported: explosion sizes are shared rows (every '
        ..'shell of that explosion would change); choose another impact_explosion donor')
    assert(value.native==nil or value.native==true,'orbital.native must be true (or absent)')
    if value.native then
        for key in pairs(value)do
            assert(key=='pattern'or key=='impact_explosion'or key=='native',('orbital.%s is not supported with native = '
                ..'true: the donor\'s own barrage is used exactly as the game reads it'):format(tostring(key)))
        end
        local pattern=donor_name(value.pattern)
        local payload,shells=barrages.payload_of(pattern)
        assert(payload and shells and#shells>0,'orbital.pattern must be a reviewed orbital bombardment (its own barrage '
            ..'is called): e.g. Orbital 120mm HE Barrage')
        local d=donors.resolve(value.impact_explosion)
        assert(d,'orbital.impact_explosion is required with native = true (else it is just the donor): a reviewed '
            ..'explosion donor: '..table.concat(donors.names(),', '))
        local types,seen={},{}
        for _,t in ipairs(shells)do if not seen[t]then seen[t]=true;types[#types+1]=t end end
        local entry=catalog.stratagems[pattern]
        return {kind='orbital',native=true,pattern=pattern,payload=payload,shells=types,impact=d,stratagem=pattern,
            id=entry.root.id},{pattern,d}
    end
    local shell=donor_name(value.shell)
    assert(shell and executor.pattern_of(shell),'orbital.shell must be a reviewed orbital (its first shell is fired): '
        ..'e.g. Orbital Gas Strike, Orbital EMS Strike, Orbital Napalm Barrage')
    local pattern=donor_name(value.pattern)or'Orbital 120mm HE Barrage'
    assert(executor.pattern_of(pattern),'orbital.pattern must be a reviewed orbital bombardment')
    local OL=M.LIMITS.orbital
    local function range(key,int)
        local v,lo,hi=value[key],OL[key][1],OL[key][2]
        assert(v==nil or(type(v)=='number'and v==v and v>=lo and v<=hi and(not int or v%1==0)),
            ('orbital.%s must be %s%g..%g'):format(key,int and'a whole number 'or'',lo,hi))
        return v
    end
    local o={salvos=range('salvos',true),shells_per_salvo=range('shells_per_salvo',true),
        shell_delay=range('shell_interval'),salvo_delay=range('salvo_interval'),scatter=range('scatter'),
        salvo_scatter=range('salvo_scatter')}
    local base=executor.pattern_of(pattern)
    local total=(o.salvos or base.salvos)*(o.shells_per_salvo or base.shells_per_salvo)
    local most=math.min(OL.total,executor.MAX_SHELLS)
    assert(total>=1 and total<=most,('orbital: %d shells in all; at most %d'):format(total,most))
    local overrides={}
    for k,v in pairs(o)do overrides[k]=v end
    -- Explicit delays are exact: no random part unless the pattern's own is kept.
    if o.shell_delay then overrides.shell_delay_random=0 end
    if o.salvo_delay then overrides.salvo_delay_random=0 end
    local out={kind='orbital',shell=shell,pattern=pattern,overrides=overrides,total=total}
    local assets={shell}
    if value.impact_explosion~=nil then
        local d=donors.resolve(value.impact_explosion)
        assert(d,'orbital.impact_explosion must be a reviewed explosion donor: '..table.concat(donors.names(),', '))
        out.impact=d
        assets[#assets+1]=d
    end
    return out,assets
end
-- pelican = {hover, orbit, gun, approach}: the Runtime's Pelican CAS (hd2.pelican.spawn's options as data): the
-- carrier's own delivery is neutralized and, at the activation, a Pelican flies to the beacon and holds over it, its
-- chin gun configured on its own copies (runtime/pelican_gunship.lua). With several players the SESSION HOST spawns it
-- for whoever called it (a client requests it: runtime/custom_mp_calls.lua), and every compatible Runtime mirrors the
-- chin gun's private presentation on its own copy of the turret.
local PELICAN_KEYS={hover=true,orbit=true,gun=true,approach=true}
local function pelican_spec(value)
    assert(type(value)=='table','pelican must be a table')
    for key in pairs(value)do assert(PELICAN_KEYS[key],'unsupported pelican field: '..tostring(key))end
    local gunship=require('hd2runtime/runtime/pelican_gunship')
    local api=require('hd2runtime/api/pelican')
    local hover=value.hover
    assert(type(hover)=='number'and hover==hover and hover>0 and hover<=api.MAX_HOVER,
        'pelican.hover must be seconds above 0 and at most '..api.MAX_HOVER)
    local gun
    if value.gun~=nil then
        local ok,why=gunship.check_gun(value.gun)
        assert(ok,'pelican.gun: '..tostring(why))
        gun={}
        for k,v in pairs(value.gun)do gun[k]=v end
        -- Explosive rounds by the donor's name (a typed handle too): the registry hash compares that name. A Mod Options
        -- choice stays the handle: read when the gun is armed and by the registry hash (its value now).
        if ok.impact and value.gun.impact_explosion~=nil
                and not require('hd2runtime/api/options').is_handle(value.gun.impact_explosion)then
            gun.impact_explosion=ok.impact
        end
    end
    local orbit
    if value.orbit~=nil then
        local ok,why=gunship.check_orbit(value.orbit)
        assert(ok,'pelican.orbit: '..tostring(why))
        orbit={}
        for k,v in pairs(value.orbit)do orbit[k]=v end
    end
    local approach
    if value.approach~=nil then
        assert(type(value.approach)=='table','pelican.approach must be {distance, height}')
        approach={distance=value.approach.distance,height=value.approach.height}
    end
    -- What the chin gun's configuration loads: the Gatling Sentry's package (its round and casing), the MG-206's (AP4).
    local assets={}
    if gun and gun.behave_as=='gatling_sentry'then assets[#assets+1]='A/G-16 Gatling Sentry'end
    -- Its round's package: the MG-206's (AP4), the Eagle Strafing Run's (its rounds); for a Mod Options choice, each value's.
    for _,name in ipairs(gun and gunship.round_assets(gun.round)or{})do assets[#assets+1]=name end
    -- A firing sound (research/docs/pelican-maelstrom-sound-F5FEE03DCFDB.md): its bank's package on every machine before
    -- the first shot, so the sound goes into the gun's own copy in the same transaction.
    if gun and gun.sound~=nil then assets[#assets+1]=require('hd2runtime/runtime/weapon_sounds').stratagem(gun.sound)end
    -- Explosive rounds: the package that ships a blast's effect, for every blast it can name (a faction's: none).
    for _,name in ipairs(gun and gunship.impact_assets(gun.impact_explosion,gun.rpm)or{})do assets[#assets+1]=name end
    return {kind='pelican',hover=hover,gun=gun,orbit=orbit,approach=approach},assets
end
for _,name in ipairs(CALLBACKS)do SPEC_KEYS[name]=true end

local function text_of(value,what)
    local most=what=='description'and M.LIMITS.description or M.LIMITS.text
    if type(value)~='string'or#value<1 or#value>most or value:find('[%c]')then
        error(what..' must be a string of 1 to '..most..' characters',0)
    end
    return value
end

-- Registers a custom stratagem for `owner` (the mod id). Returns the definition; errors on an invalid spec (a mod's
-- mistake is reported at load time, never guessed around).
function M.register(spec,owner)
    assert(type(spec)=='table','a custom stratagem must be a table')
    assert(type(owner)=='string'and#owner>0,'a custom stratagem needs its mod')
    for key in pairs(spec)do assert(SPEC_KEYS[key],'unsupported custom stratagem field: '..tostring(key))end
    local id=spec.id
    assert(type(id)=='string'and#id>=1 and#id<=M.LIMITS.id.max and id:match(M.LIMITS.id.pattern),
        'id must be 1-'..M.LIMITS.id.max..' characters of a-z, 0-9 and _, starting with a letter')
    assert(not defs[id],'custom stratagem '..id..' is already registered')
    assert(#order<M.MAX,'at most '..M.MAX..' custom stratagems')
    local name=text_of(spec.name,'name')
    local name_cased=text_of(spec.name_cased or spec.name,'name_cased')
    local description=text_of(spec.description,'description')
    -- The icon: a Runtime image of the mod (its images/<id>.png).
    local icon=spec.icon
    if type(icon)=='string'then icon=images.handle(icon,owner)end
    assert(images.issued(icon),'icon must be the id of one of the mod\'s images (images/<id>.png) or hd2.resources.image(id)')
    -- The code: 1-8 directions, never equal to or a start of another custom stratagem's.
    assert(type(spec.code)=='table','code must be a list of directions (\'up\', \'down\', \'left\', \'right\')')
    local values=calldown.values(spec.code)
    assert(values and#values>=M.LIMITS.code[1]and#values<=M.LIMITS.code[2],
        ('code must be %d to %d directions (\'up\', \'down\', \'left\', \'right\')'):format(M.LIMITS.code[1],
        M.LIMITS.code[2]))
    for _,other in ipairs(order)do
        local relation=calldown.relation(values,other.code_values)
        assert(not relation,('the code %s collides with the custom stratagem %s (%s): the game would select one of them')
            :format(calldown.text(values),other.id,calldown.text(other.code_values)))
    end
    local cooldown=spec.cooldown
    assert(cooldown==nil or(type(cooldown)=='number'and cooldown>0 and cooldown<=M.MAX_COOLDOWN),
        'cooldown must be seconds above 0 and at most '..M.MAX_COOLDOWN)
    -- Calls per mission, each player's own (runtime/slot_cooldown.lua: the call that uses the last of them ends with a
    -- cooldown longer than any mission).
    assert(spec.uses==nil or(type(spec.uses)=='number'and spec.uses%1==0 and spec.uses>=1 and spec.uses<=M.MAX_USES),
        'uses must be a whole number of calls per mission from 1 to '..M.MAX_USES)
    -- The loadout slot holds the carrier itself (runtime/carrier_in_slot.lua; the default since r44); 'token' is a
    -- development option (the Orbital Precision Strike token, the Runtime's own fallback path).
    assert(spec.selection==nil or spec.selection=='token'or spec.selection=='carrier',
        "selection must be 'carrier' (the default: the slot holds the carrier itself) or 'token' (development)")
    assert(spec.uses==nil or spec.eagle==nil,'uses counts calls per mission; an Eagle\'s uses are per rearm (eagle.uses)')
    -- r45: at most this many of a player's loadout slots hold it (each player's own; picks beyond it are refused).
    local mpp=spec.max_per_player
    assert(mpp==nil or(type(mpp)=='number'and mpp%1==0 and mpp>=1 and mpp<=M.MAX_PER_PLAYER),
        'max_per_player must be a whole number of loadout slots from 1 to '..M.MAX_PER_PLAYER)
    local ok,why=allocator.check_policy(spec.carrier)
    assert(ok,tostring(why))
    -- The policy the payload and the allocation read: the carrier spec, with a requested GROUP's beacon and families
    -- where it gives none (runtime/carrier_groups.lua). Without a group it is exactly the spec (unchanged allocation).
    local policy=spec.carrier
    if spec.carrier.group~=nil then
        local g=groups.GROUPS[spec.carrier.group]
        policy={beacon=spec.carrier.beacon or g.beacon,prefer_families=spec.carrier.prefer_families or g.families,
            allow_families=spec.carrier.allow_families or g.families,exclude=spec.carrier.exclude,
            require_unlimited=spec.carrier.require_unlimited}
    end
    local assets={}
    for k,asset in ipairs(spec.assets or{})do
        local sid=stratagem_id(asset)
        assert(sid,'assets['..k..'] must name a catalogued stratagem')
        assert(core_assets.dependencies_for_stratagem(sid,asset)and core_assets.call_in_complete(asset),
            'assets['..k..']: no call-in package is known for '..asset)
        assets[#assets+1]=asset
    end
    -- The payload family: one of a support delivery, a sentry, an Eagle and an orbital (else 'runtime': the mod's).
    local families={}
    if spec.delivery~=nil and spec.delivery~='runtime'then families[#families+1]='delivery'end
    for _,k in ipairs({'sentry','eagle','orbital','pelican','silo'})do if spec[k]~=nil then families[#families+1]=k end end
    assert(#families<=1,'one payload family per custom stratagem: '..table.concat(families,', ')..' given together')
    local delivery,sentry,eagle,orbital,pelican,extra='runtime',nil,nil,nil,nil,{}
    local function pod_form(v)
        if type(v)~='table'or type(v.items)~='table'then return false end
        for _,item in ipairs(v.items)do if type(item)=='table'and item.item~=nil then return true end end
        return false
    end
    if families[1]=='delivery'and type(spec.delivery)=='table'and spec.delivery.family=='expendable'then
        delivery,extra=expendable_spec(spec.delivery,policy)
    elseif families[1]=='delivery'and type(spec.delivery)=='table'and spec.delivery.family=='weapon'then
        delivery,extra=variant_spec(spec.delivery,policy,owner)
    elseif families[1]=='delivery'and pod_form(spec.delivery)then
        delivery,extra=carrier_pod_delivery_spec(spec.delivery,policy)
    elseif families[1]=='delivery'then delivery,extra=support_delivery_spec(spec.delivery,policy)
    elseif families[1]=='sentry'then sentry,extra=sentry_spec(spec.sentry,policy);delivery=sentry
    elseif families[1]=='eagle'then eagle,extra=eagle_spec(spec.eagle,policy,cooldown);delivery=eagle
    elseif families[1]=='orbital'then
        orbital,extra=orbital_spec(spec.orbital)
        -- Native: the beacon's delivery becomes the pattern donor's (its own barrage).
        if orbital.native then delivery=orbital end
    elseif families[1]=='pelican'then pelican,extra=pelican_spec(spec.pelican)
    elseif families[1]=='silo'then
        -- The donor silo's own pod; its call-in packages are the delivery's (definition_deps), the blasts' its pod_deps.
        delivery=require('hd2runtime/runtime/custom_silos').spec(spec.silo,policy,donor_name)
        assert(core_assets.dependencies_for_stratagem(delivery.id,delivery.stratagem)
            and core_assets.call_in_complete(delivery.stratagem),'no call-in package is known for '..delivery.stratagem)
    end
    local kind=delivery~='runtime'and delivery.kind or(orbital and'orbital'or pelican and'pelican'or'runtime')
    -- A code EQUAL to a vanilla stratagem's own code can never work (live r25: the Laser Maxigun's DOWN LEFT DOWN UP
    -- RIGHT is the MG-43's, so every mission refused it and its slot stayed the token): refused here, with the name.
    -- A weapon variant's own row is its carrier and takes the custom code, so its own vanilla code is no collision.
    do
        local own=delivery~='runtime'and delivery.variant and delivery.id or nil
        for _,r in ipairs(calldown.native_relations(values,{}))do
            if r.relation=='equal'and r.id~=own then
                error(('the code %s is the vanilla %s\'s own code: the game would call that stratagem instead; choose '
                    ..'another code'):format(calldown.text(values),names_by_id[r.id]or('stratagem '..tostring(r.id))),0)
            end
        end
    end
    -- Its carrier GROUP: the one it requested (checked against its payload), else its payload's default (a legacy policy
    -- keeps deciding its allocation exactly as before; the group then only names it).
    local payload_key=delivery~='runtime'and delivery.variant and'weapon'or groups.payload_key(kind,orbital and orbital.native)
    local pod=delivery~='runtime'and delivery.pod or nil
    local group,group_source
    if spec.carrier.group~=nil then
        group,group_source=groups.resolve(spec.carrier,payload_key,pod and pod.total)
        assert(group,tostring(group_source))
    else
        group,group_source=groups.label(policy,payload_key),'default'
    end
    -- The payload's own donors are assets (their packages loaded at mission start, never carriers).
    local listed={}
    for _,a in ipairs(assets)do listed[a]=true end
    for _,a in ipairs(extra or{})do
        if not listed[a]and not(delivery~='runtime'and a==delivery.stratagem)then
            local sid=stratagem_id(a)
            assert(sid and core_assets.dependencies_for_stratagem(sid,a)and core_assets.call_in_complete(a),
                'no call-in package is known for the donor '..tostring(a))
            listed[a]=true
            assets[#assets+1]=a
        end
    end
    for _,cb in ipairs(CALLBACKS)do
        assert(spec[cb]==nil or type(spec[cb])=='function',cb..' must be a function')
    end
    assert(delivery~='runtime'or spec.on_delivered==nil,'on_delivered needs a delivery (support, sentry or eagle)')
    -- The Runtime's own text resources for its presentation (the mod's resource).
    local key=id:sub(1,40)
    local t={name=texts.handle(key..'_name',name,owner),nameCased=texts.handle(key..'_name_cased',name_cased,owner),
        description=texts.handle(key..'_description',description,owner)}
    local exclude={}
    for _,asset in ipairs(assets)do exclude[#exclude+1]=asset end
    if delivery~='runtime'then exclude[#exclude+1]=delivery.stratagem end
    local definition={id=id,owner=owner,label=name_cased,texts=t,icon=icon,code=spec.code,code_values=values,
        code_text=calldown.text(values),cooldown=cooldown,uses=spec.uses,traits=M.traits_of(spec.traits),
        -- The loadout slot holds the carrier itself (the default since r44); 'token' (development, Lua only): the
        -- Orbital Precision Strike token, converted at mission start.
        selection=(spec.selection or M.default_selection)=='carrier'and'carrier'or nil,
        max_per_player=spec.max_per_player,
        policy=spec.carrier,assets=assets,delivery=delivery,
        exclude=exclude,callbacks={},kind=kind,sentry=sentry,eagle=eagle,orbital=orbital,pelican=pelican,
        group=group,group_source=group_source,alloc_policy=policy,
        pod_deps=(pod and pod.deps)or(delivery~='runtime'and(delivery.variant_deps or kind=='silo'and delivery.deps))
            or nil,asset_timeout=kind=='silo'and delivery.objective and M.OBJECTIVE_ASSET_TIMEOUT or nil}
    -- The pod capacity it needs from its carrier: its items, or more when carrier.slots asks for it.
    if pod then definition.slots=math.max(pod.total,spec.carrier.slots or 0)end
    if kind=='pod'then
        -- The support_pod group's structural condition on each candidate: an exclusive rack of that capacity whose slot
        -- roles take the items (runtime/carrier_pod.lua).
        local need=definition.slots
        definition.filter=function(c)
            local rack=carrier_pod.rack(c.name)
            if not rack then return'no exclusive pod rack (its rack is shared, or it delivers no pod)'end
            if rack.capacity<need then
                return('its pod holds at most %d item%s, %d needed'):format(rack.capacity,rack.capacity==1 and''or's',need)
            end
            local plan,_,reason=carrier_pod.plan(c.name,pod_units(pod))
            if not plan then return reason end
            return nil
        end
    end
    for _,cb in ipairs(CALLBACKS)do definition.callbacks[cb]=spec[cb]end
    if kind=='expendable'then
        -- What the carrier weapon shows (prompt, map, weapon panel): the definition's name and icon unless the delivery
        -- names others ('donor': the donor's own). A Runtime text or icon the game cannot show is borrowed at the write.
        local p=delivery.presentation
        local wname=p.name==nil and name or(p.name~='donor'and text_of(p.name,'delivery.presentation.name')or nil)
        definition.weapon_text=wname and texts.handle(key..'_weapon_name',wname,owner)or nil
        if p.icon==nil then definition.weapon_icon=icon
        elseif p.icon~='donor'then
            local h=p.icon
            if type(h)=='string'then h=images.handle(h,owner)end
            assert(images.issued(h),'delivery.presentation.icon must be \'donor\', the id of one of the mod\'s images or '
                ..'hd2.resources.image(id)')
            definition.weapon_icon=h
        end
    end
    definition.colours=colour_donor(policy,delivery)
    definition.virtual=virtual.define({id=id,display={name=t.nameCased,description=t.description,icon=icon,
        colours=definition.colours},selection={token=M.TOKEN},mission={discover=true}},owner)
    defs[id]=definition
    order[#order+1]=definition
    local payload_text
    if kind=='support'then
        local parts={}
        for k,v in pairs(delivery.modify or{})do parts[#parts+1]=k..' '..tostring(v)end
        table.sort(parts)
        payload_text=('the vanilla %s pod (%d item%s)%s%s'):format(delivery.stratagem,delivery.count,
            delivery.count==1 and''or's',#parts>0 and('; each weapon of it: '..table.concat(parts,', '))or'',
            delivery.impact and('; its projectiles explode as '..delivery.impact..'\'s')or'')
    elseif kind=='expendable'and delivery.variant then
        payload_text=('a mission-scoped VARIANT of the %s on its own type (its only carrier: picked natively by anyone, '
            ..'it is unavailable), delivered by its own pod%s%s; it shows %s with %s'):format(delivery.donor,
            delivery.round and(('; it fires the %s\'s round %d (%s)'):format(delivery.round.label,delivery.round.type,
            delivery.round.class))or'',delivery.model and(('; its model %s (%s)'):format(tostring(delivery.model),
            type(delivery.model_use)=='string'and delivery.model_use or('a Mod Options choice (now '
            ..M.model_use_value(delivery.model_use)..')')))or'',definition.weapon_text and'its own name'
            or('the '..delivery.donor..'\'s name'),definition.weapon_icon and'its own icon'or('the '..delivery.donor
            ..'\'s icon'))
    elseif kind=='expendable'then
        local parts={}
        for k,v in pairs(delivery.modify or{})do parts[#parts+1]=k..' '..tostring(v)end
        table.sort(parts)
        payload_text=('a mission-scoped %s clone on an unused carrier weapon of its expendable class (%s, first free), '
            ..'delivered by that weapon\'s own pod; level %s%s%s; it shows %s with %s'):format(delivery.donor,
            table.concat(delivery.pool,', '),type(delivery.level)=='string'and delivery.level
            or('a Mod Options choice (now '..level_value(delivery.level)..')'),#parts>0 and('; each launcher: '
            ..table.concat(parts,', '))or'',(delivery.impact and('; its rockets explode as '..delivery.impact..'\'s')or'')
            ..(delivery.round and(('; it fires the %s\'s round %d'):format(delivery.round.name,delivery.round.type))or''),
            definition.weapon_text and'its own name'or('the '..delivery.donor..'\'s name'),definition.weapon_icon
            and'its own icon'or('the '..delivery.donor..'\'s icon'))
        if delivery.pod then
            local fit={}
            for _,name in ipairs(delivery.pool)do if delivery.fits[name]then fit[#fit+1]=name end end
            payload_text=payload_text..('; its pod holds %s (%d item%s; carrier weapons that can hold them: %s)'):format(
                pod_text(delivery.pod),delivery.pod.total,delivery.pod.total==1 and''or's',table.concat(fit,', '))
        end
    elseif kind=='pod'then
        payload_text=('the carrier\'s OWN pod (no redirect), its exclusive rack holding %s for the mission (%d item%s)')
            :format(pod_text(delivery.pod),delivery.pod.total,delivery.pod.total==1 and''or's')
    elseif kind=='sentry'then
        local parts={}
        for k,v in pairs(sentry.weapon)do parts[#parts+1]=k..' '..tostring(v)end
        table.sort(parts)
        payload_text=('the vanilla %s pod; its sentry\'s own weapon: %s'):format(sentry.stratagem,
            #parts>0 and table.concat(parts,', ')or'vanilla')
    elseif kind=='silo'then
        payload_text=require('hd2runtime/runtime/custom_silos').text(delivery)
    elseif kind=='eagle'then
        payload_text=('the %s strike from an Eagle carrier, %d uses per rearm%s'):format(eagle.stratagem,eagle.uses,
            eagle.impact and('; its rockets explode as '..eagle.impact..'\'s')or'')
    elseif kind=='pelican'then
        local parts={}
        local now=require('hd2runtime/runtime/pelican_gunship').gun_now(pelican.gun or{})
        for k,v in pairs(pelican.gun or{})do
            if type(v)=='table'then v='a Mod Options choice (now '..tostring(now[k])..')'end
            parts[#parts+1]=k..' '..tostring(v)
        end
        table.sort(parts)
        payload_text=('a Pelican that holds over the beacon %g s%s; its chin gun: %s (with several players the session '
            ..'host spawns it for its caller)'):format(pelican.hover,pelican.orbit and', orbiting it'or'',
            #parts>0 and table.concat(parts,', ')or'vanilla')
    elseif kind=='orbital'and orbital.native then
        payload_text=('the %s\'s own native barrage (every player\'s machine fires it), each of its shells (%s) exploding as '
            ..'%s\'s'):format(orbital.pattern,table.concat(orbital.shells,', '),orbital.impact)
    elseif kind=='orbital'then
        payload_text=('a Runtime bombardment: %s\'s shell in %s\'s pattern (%d shells)%s'):format(orbital.shell,
            orbital.pattern,orbital.total,orbital.impact and('; each explodes as '..orbital.impact..'\'s')or'')
    else
        payload_text='by the mod (the carrier\'s own is neutralized)'
    end
    if definition.max_per_player then
        payload_text=payload_text..('; at most %d per player'):format(definition.max_per_player)
    end
    if definition.selection~='carrier'then
        payload_text=payload_text..'; SELECTION token (development): its loadout slot holds the Orbital Precision '
            ..'Strike token, converted to its carrier at mission start'
    end
    pcall(function()require('hd2runtime/runtime/init_progress').custom_registered()end)
    log(('REGISTERED %s (%s) by %s: code %s, cooldown %s, carrier policy: %s beacon%s%s; delivery %s; assets %s%s; '
        ..'carrier group %s (%s%s)')
        :format(id,name_cased,owner,definition.code_text,cooldown and(cooldown..' s')or'the carrier\'s own',
        policy.beacon,policy.prefer_families and(', prefer '..table.concat(policy.prefer_families,'/'))
        or'',policy.allow_families and(', allow '..table.concat(policy.allow_families,'/'))or'',
        payload_text,#assets>0 and table.concat(assets,', ')or'none',definition.colours and('; ship icon colours: '
        ..definition.colours..(kind=='sentry'and'\'s (its sentry\'s own)'or'\'s (support, blue)'))or'',group,
        group_source,definition.slots and(', capacity '..definition.slots)or''))
    M.start()
    return definition
end
function M.get(id)return defs[id]end
function M.list()local out={};for k,d in ipairs(order)do out[k]=d end;return out end
-- Tuning after registration (r51, for in-game editors): a definition's cooldown (seconds) and uses (calls per mission)
-- only. Both are each player's own (armed on this machine when a call lands; not in the lobby registry hash), so a
-- tuned value changes this player's next call and never what other machines agree on. The same checks as register;
-- values = {cooldown, uses} (nil leaves a field as it is). The registered values are kept: untune restores them.
-- Returns true, or nil and why.
function M.tune(id,values,by)
    local d=defs[id]
    if not d then return nil,'no custom stratagem '..tostring(id)end
    if type(values)~='table'then return nil,'tune needs {cooldown, uses}'end
    for key in pairs(values)do
        if key~='cooldown'and key~='uses'then return nil,'only cooldown and uses can be tuned, not '..tostring(key)end
    end
    local cooldown,uses=values.cooldown,values.uses
    if cooldown~=nil and not(type(cooldown)=='number'and cooldown>0 and cooldown<=M.MAX_COOLDOWN)then
        return nil,'cooldown must be seconds above 0 and at most '..M.MAX_COOLDOWN
    end
    if uses~=nil then
        if d.eagle then return nil,'an Eagle\'s uses are per rearm (eagle.uses) and cannot be tuned'end
        if not(type(uses)=='number'and uses%1==0 and uses>=1 and uses<=M.MAX_USES)then
            return nil,'uses must be a whole number of calls per mission from 1 to '..M.MAX_USES
        end
    end
    d.registered_values=d.registered_values or{cooldown=d.cooldown,uses=d.uses}
    if cooldown~=nil then d.cooldown=cooldown end
    if uses~=nil then d.uses=uses end
    d.tuned_by=by
    log(('TUNED %s by %s: cooldown %s, uses %s (registered: %s, %s); from its next call')
        :format(id,tostring(by or'unknown'),tostring(d.cooldown),tostring(d.uses or'unlimited'),
        tostring(d.registered_values.cooldown),tostring(d.registered_values.uses or'unlimited')))
    return true
end
function M.untune(id)
    local d=defs[id]
    if not d then return nil,'no custom stratagem '..tostring(id)end
    if d.registered_values then
        d.cooldown,d.uses=d.registered_values.cooldown,d.registered_values.uses
        d.registered_values,d.tuned_by=nil,nil
        log('UNTUNED '..id..': back to its registered cooldown and uses')
    end
    return true
end

------------------------------------------------------------------------------------------------ helpers --
-- Every global exclusion: no custom stratagem's carrier is another's asset or delivery.
local function global_exclude()
    local out={}
    for _,d in ipairs(order)do for _,name in ipairs(d.exclude)do out[#out+1]=name end end
    return out
end
-- The definitions with virtual slots in the current identity: {definition, ...} and {[id] = {slots}}.
local function selected()
    local set=selector.virtual_slots()
    local out,by={},{}
    for slot=0,3 do
        local e=set and set.slots[slot]
        if e and defs[e.definition]then
            local list=by[e.definition]
            if not list then list={};by[e.definition]=list;out[#out+1]=defs[e.definition]end
            list[#list+1]=slot
        end
    end
    table.sort(out,function(a,c)return a.id<c.id end)
    return out,by
end
local function saved_ids(world)
    local saved=loadout.saved(world)
    if not saved then return nil end
    local ids,set={},{}
    for k,pair in ipairs(saved.pairs or{})do ids[k]=pair.id;set[pair.id]=true end
    return ids,set
end
-- This player's loadout as it is NOW (stable ids in order, and as a set): the loadout screen's live record while the
-- screen is open (the save is written only when it is left, so it lags every pick made there), else the save. The
-- ship allocation, the availability and the carrier reservations read it, so they follow a pick at once.
local function loadout_ids(world)
    local ok,view=pcall(selector.screen,world)
    if ok and view and view.open and view.record and view.record.entries then
        local ids,set={},{}
        for k,e in ipairs(view.record.entries)do
            local id=loadout.id_of(world,e.type)
            if not id then ids=nil;break end
            ids[k]=id;set[id]=true
        end
        if ids then return ids,set end
    end
    return saved_ids(world)
end
local function row_of(world,kind)return kind and world.view.pointer(world.game+require('hd2runtime/schemas/current')
    .stratagem.table_rva+kind*8)end
local function row_code(world,row)
    local count=row and world.view.u32(row+C.row.count)
    local array=row and world.view.pointer(row+C.row.sequence)
    if not(count and array and count>0 and count<=16)then return nil end
    local values={}
    for k=0,count-1 do values[k+1]=world.view.u32(array+k*4)end
    return values
end
local function selectable(world,id)
    local kind=loadout.type_of(world,id)
    local row=row_of(world,kind)
    local flags=row and world.view.u32(row+SLOTS.row.selectable)
    if not flags then return nil end
    return math.floor(flags/SLOTS.row.selectableBit)%2==1
end
-- The definition's code against every reviewed native code: the relations that refuse it (a selectable stratagem, or
-- an equal code), as text; empty when safe. skip: the carrier's stable id.
local function native_conflicts(world,d,carrier_id)
    local out={}
    for _,r in ipairs(calldown.native_relations(d.code_values,{[carrier_id]=true}))do
        local pick=selectable(world,r.id)
        if r.relation=='equal'or pick~=false then
            out[#out+1]=('%s (%s) %s'):format(names_by_id[r.id]or('stable id '..r.id),calldown.text(r.values),r.relation)
        end
    end
    return out
end
-- The definition's code against the codes of the current mission record (other than its own carrier's entries).
local function record_conflicts(world,d,carrier_type)
    local record=slots.local_record(world)
    if not record then return nil end
    local out={}
    for _,entry in ipairs(record.entries)do
        if entry.type~=carrier_type then
            local values=row_code(world,row_of(world,entry.type))
            local relation=values and calldown.relation(d.code_values,values)
            if relation then
                local id=loadout.id_of(world,entry.type)
                out[#out+1]={key=entry.index..':'..entry.type,text=('record entry %d %s (%s) %s'):format(entry.index,
                    names_by_id[id]or('type '..entry.type),calldown.text(values),relation)}
            end
        end
    end
    return out
end

------------------------------------------------------------------------------------------- the ship side --
local cache={}            -- by definition id: the carrier allocated aboard the ship (assignment)
local ship={key=nil,at=-1,line=nil,status={}}
local clock=0

-- The carriers, by custom stratagem IDENTITY (runtime/carrier_allocator.lua, "the lobby"): every REGISTERED custom
-- stratagem is allocated (the mod set, by id), so the carrier of an id never depends on what this player, or another,
-- selected; `present` is every native selection this machine can read; `list` (this player's selections) is what the
-- line reports and what the mission uses. With several players the ranking ignores the account's ownership and a
-- carrier this account does not own is refused locally (never remapped).
-- The carrier WEAPONS of the expendable custom stratagems (runtime/weapon_carriers.lua): claimed by the definitions in
-- scope (the synced lobby table's ids, else this player's selections) that have a carrier, in id order, from the native
-- picks `present`; a definition left without one is refused (UNAVAILABLE, with who took each candidate) and gets no
-- carrier this mission. Every machine computes the same claims from the same synced data.
-- The CONDENSED carrier of an expendable custom stratagem (the expendable group): its carrier weapon's OWN stratagem
-- carries the beacon too (its row presents as the custom stratagem and answers to its code, its weapon type is the
-- clone, its own pod delivers it), so the definition uses up ONE vanilla stratagem. It must be a carrier under the
-- carrier rules: the discovery's guards on that one row (owned, selectable, enabled, unlimited, not in any lobby pick,
-- its call-in package known, a reviewed presentation and a native code, never another custom stratagem's asset or
-- delivery other than its own pool) and a blue (support) beam. In a lobby an only-unowned row is the carrier for every
-- machine alike and refused locally (local_refused), never replaced. Returns the candidate (and local_refused), or nil
-- and why (then a separate support carrier carries the beacon: the fallback).
local function only_unowned(c)
    if not c or c.eligible or not c.codes or#c.codes==0 then return false end
    for _,code in ipairs(c.codes)do if code~='not_owned'then return false end end
    return true
end
local function condensed_exclude()
    local pools={}
    for _,d in ipairs(order)do
        if d.kind=='expendable'then for _,name in ipairs(d.delivery.pool)do pools[name]=true end end
    end
    local out={}
    for _,name in ipairs(global_exclude())do if not pools[name]then out[#out+1]=name end end
    return out
end
local function condensed_carrier(world,weapon,present,lobby)
    local ok,v=pcall(slots.validate_carrier,world,M.TOKEN,weapon,{present=present or{},exclude=condensed_exclude()})
    if not ok then return nil,'its row cannot be read now ('..tostring(v)..')'end
    if not(v and v.ready)then return nil,'the carrier discovery is not ready ('..tostring(v and v.reason)..')'end
    local c=v.candidate
    if c and c.beaconCategory~='support'then
        return nil,('its beacon is not a blue support beacon (%s)'):format(allocator.look(c))
    end
    if v.valid then return c end
    if lobby and only_unowned(c)then return c,true end
    return nil,table.concat(v.reasons or{},'; ')
end
M.condensed_carrier=condensed_carrier
-- The expendable custom stratagems in scope (the synced lobby table's ids, else this player's selections): their carrier
-- weapons claimed in id order (runtime/weapon_carriers.lua; a pool weapon whose pod cannot hold the pod items is not a
-- candidate), then each one's carrier: condensed when its weapon's own stratagem can carry the beacon, else marked for a
-- separate support carrier (the fallback, allocated with the policies). {assignments, refused, fallback = {[id] = why},
-- weapons, weapon_line, line}.
local function expendable_pass(world,present,list,ids,who,lobby)
    local scope={}
    if ids then for _,id in ipairs(ids)do scope[id]=true end else for _,d in ipairs(list)do scope[d.id]=true end end
    local claims={}
    for _,d in ipairs(order)do
        if d.kind=='expendable'and scope[d.id]then
            claims[#claims+1]={id=d.id,donor=d.delivery.donor,slots=d.slots,fits=d.delivery.fits,
                fallback=d.delivery.fallback~=nil,variant=d.delivery.variant==true}
        end
    end
    local out={assignments={},refused={},fallback={}}
    if#claims==0 then return out end
    local w=weapon_carriers.allocate(claims,present,{who=who})
    out.weapons=w
    for id,why in pairs(w.refused)do out.refused[id]=why end
    local parts,modes={},{}
    for _,id in ipairs(w.order)do
        local x=w.assignments[id]
        parts[#parts+1]=id..' = '..(x and(x.donor_self and('the regular '..x.weapon..' (the donor itself)')or x.weapon)
            or('REFUSED ('..tostring(w.refused[id])..')'))
        if x and x.donor_self then
            -- The donor itself (the pool's last member, reserved like the others): its own pod, no clone; a separate
            -- support carrier throws the beacon (its own row is never presented: its type stays the vanilla donor).
            out.fallback[id]=('its carrier weapon is the regular %s'):format(x.weapon)
            out.assignments[id]={weapon=x}
            modes[#modes+1]=('%s = the regular %s (THE DONOR ITSELF: every clone carrier weapon of its class is taken: %s; '
                ..'its own pod, no clone; a separate support carrier throws the beacon)'):format(id,x.weapon,tostring(x.taken))
        elseif x then
            local d=defs[id]
            local c,second=condensed_carrier(world,x.weapon,present,lobby)
            if c then
                out.assignments[id]={label=d.label,carrier=c.name,stable_id=c.id,type=c.type,class=c.class,
                    family=c.family,beacon=c.beaconCategory,beam=c.beamColour,ping=c.pingColour,eligible=1,skipped=0,
                    owned=c.eligible==true,weapon=x,condensed=true,group='expendable',local_refused=second==true
                    and('the lobby\'s carrier for it is '..c.name..', which this account does not own: unavailable to '
                    ..'this player (never remapped: every player must agree)')or nil}
                modes[#modes+1]=('%s = %s (CONDENSED: its own beacon, clone and pod; one vanilla stratagem)'):format(id,
                    c.name)
            else
                out.fallback[id]=tostring(second)
                out.assignments[id]={weapon=x}
                modes[#modes+1]=('%s = %s (FALLBACK: a separate support carrier throws the beacon, because %s cannot '
                    ..'carry it: %s)'):format(id,x.weapon,x.weapon,tostring(second))
            end
        end
    end
    out.weapon_line='CUSTOM CARRIER WEAPONS: '..table.concat(parts,', ')
    out.line=#modes>0 and('EXPENDABLE CARRIERS: '..table.concat(modes,', '))or nil
    return out
end
-- quiet: a feasibility probe (nothing logged, nothing of the ship's log state changed).
-- The selection a definition takes when it names none (r44: the carrier itself). Tests of the token path (the
-- Runtime's own fallback) set 'token' through M.set_default_selection_for_tests; reset_for_tests restores it.
M.default_selection='carrier'
function M.set_default_selection_for_tests(s)M.default_selection=s end
-- max_per_player (r45): at most that many of this player's loadout slots hold a definition.
M.MAX_PER_PLAYER=4
do
    -- This player's virtual slots holding `id`, the slot being edited excluded (picking it again there is no new slot).
    local function holders(id,except)
        local out={}
        local V=selector.virtual_slots()
        for slot,e in pairs(V and V.slots or{})do
            if e.definition==id and slot~=except then out[#out+1]=slot end
        end
        table.sort(out)
        return out
    end
    -- Why a pick of `id` into the slot being edited is refused by its limit, or nil.
    function M.limit_reason(id)
        local d=defs[id]
        local max=d and d.max_per_player
        if not max then return nil end
        local edited
        local world=world_module.open()
        if world then
            local ok,view=pcall(selector.screen,world)
            if ok and view and view.open then edited=view.editedSlot end
        end
        local held=holders(id,edited)
        if#held<max then return nil end
        return('LIMIT: at most %d per player: loadout slot%s %s already hold%s it'):format(max,#held==1 and''or's',
            table.concat(held,', '),#held==1 and's'or'')
    end
    -- Aboard the ship: a loadout holding more than the limit (picked before it applied) loses its extra slots, the
    -- highest first; each is then a plain native entry of the loadout (nothing written).
    function M.limit_step()
        for _,d in ipairs(order)do
            local max=d.max_per_player
            if max then
                local held=holders(d.id)
                if#held>max then
                    for k=#held,max+1,-1 do
                        local dropped=selector.drop_virtual_slot(held[k],('at most %d per player'):format(max))
                        if dropped then
                            ship.key=nil
                            log(('SHIP (%s): loadout slot %d UNPICKED: at most %d per player (slots %s held it); pick '
                                ..'another stratagem there'):format(d.id,held[k],max,table.concat(held,', ')))
                        end
                    end
                end
            end
        end
    end
end
-- The carrier-in-slot probe's pins: {[definition id] = the stable id all its carrier slots hold} (none when they differ).
function M.probe_pins()
    local out={}
    for id,x in pairs(require('hd2runtime/runtime/carrier_in_slot').slots_by_definition(selector.virtual_slots()))do
        if not x.mixed and defs[id]and defs[id].selection=='carrier'then out[id]=x.id end
    end
    return out
end
local function allocate(world,present,list,where,ids,who,quiet,pins_given)
    local definitions,report={},{}
    -- ids (custom multiplayer): only the custom stratagems the synced lobby table selects, one carrier each.
    local only
    if ids then only={};for _,id in ipairs(ids)do only[id]=true end end
    local players=world_module.players(world)or{}
    -- The expendable custom stratagems first: a condensed one takes no policy carrier (its carrier is its weapon's own
    -- stratagem); only a fallback one is allocated a separate support carrier with the policies.
    local ex=expendable_pass(world,present,list,ids,who,#players>1)
    -- The carrier-in-slot probe: a definition whose loadout slots hold its carrier keeps it while nobody else holds it
    -- (the allocator's pin); never with the synced lobby table (every peer must allocate alike).
    -- With several players the caller gives them (M.ship_pins aboard the ship; the first-seen records at mission start).
    local pins=pins_given or(not ids and M.probe_pins()or{})
    for _,d in ipairs(order)do
        if(not only or only[d.id])and(d.kind~='expendable'or ex.fallback[d.id])then
            definitions[#definitions+1]={id=d.id,label=d.label,token=M.TOKEN,policy=d.alloc_policy or d.policy,
                eagle=d.eagle~=nil,filter=d.filter,pin=pins[d.id]}
        end
    end
    for _,d in ipairs(list)do report[d.id]=true end
    local a=allocator.allocate_lobby(world,definitions,{present=present,players=#players},global_exclude(),
        {report=report})
    if not a.ready then return nil,a.reason end
    -- The expendable results (in id order): a condensed carrier, a fallback carrier with its weapon, or refused.
    local ex_ids={}
    for id in pairs(ex.assignments)do ex_ids[#ex_ids+1]=id end
    table.sort(ex_ids)
    for _,id in ipairs(ex_ids)do
        local x=ex.assignments[id]
        if ex.fallback[id]then
            if a.assignments[id]then
                a.assignments[id].weapon=x.weapon
                a.assignments[id].group='expendable'
                a.assignments[id].fallback=ex.fallback[id]
            elseif a.refused[id]and x.weapon.donor_self then
                a.refused[id]=('UNAVAILABLE: its carrier weapon is the regular %s (every clone carrier weapon of its class is taken) '
                    ..'and no separate support carrier is free: %s'):format(x.weapon.weapon,tostring(a.refused[id]))
            elseif a.refused[id]then
                a.refused[id]=('UNAVAILABLE: its carrier weapon %s cannot carry its beacon (%s) and no separate support '
                    ..'carrier is free: %s'):format(x.weapon.weapon,ex.fallback[id],tostring(a.refused[id]))
            end
        else
            a.assignments[id]=x
            a.order[#a.order+1]=id
        end
    end
    local in_order={}
    for _,id in ipairs(a.order)do in_order[id]=true end
    local refused_ids={}
    for id in pairs(ex.refused)do refused_ids[#refused_ids+1]=id end
    table.sort(refused_ids)
    for _,id in ipairs(refused_ids)do
        a.refused[id]=ex.refused[id];a.assignments[id]=nil
        if not in_order[id]then a.order[#a.order+1]=id;in_order[id]=true end
    end
    a.weapons=ex.weapons
    a.weapon_line=ex.weapon_line
    if quiet then
        for _,d in ipairs(list)do
            local mine=a.assignments[d.id]
            if mine and mine.local_refused then a.refused[d.id]=mine.local_refused;a.assignments[d.id]=nil end
        end
        return a
    end
    if a.weapon_line and a.weapon_line~=ship.weapon_line then
        ship.weapon_line=a.weapon_line
        log(a.weapon_line..' ('..where..')')
    end
    if ex.line and ex.line~=ship.expendable_line then
        ship.expendable_line=ex.line
        log(ex.line..' ('..where..')')
    end
    for _,d in ipairs(list)do
        local mine=a.assignments[d.id]
        if mine and mine.local_refused then
            a.refused[d.id]=mine.local_refused
            a.assignments[d.id]=nil
            -- Its carrier weapon stays claimed lobby-wide: another player's launchers of it are the clone here too.
            if mine.weapon then a.weapons_kept=a.weapons_kept or{};a.weapons_kept[d.id]=mine.weapon end
        end
    end
    if verbose then
        for _,d in ipairs(list)do
            for _,c in ipairs(a.candidates[d.id]or{})do
                vlog(('CARRIER CANDIDATE (%s): %s (stable id %d): family %s, %s beacon -> %s'):format(d.id,c.name,c.id,
                    tostring(c.family),tostring(c.beamColour),tostring(a.verdicts[d.id][c.id])))
            end
        end
    end
    if a.line~=ship.line then
        ship.line=a.line
        log(a.line..' ('..where..')')
    end
    return a
end

---------------------------------------------------------------------------- several players: the synced state --
-- runtime/custom_mp_sync.lua: this machine publishes its current custom picks (hd2rt/1) and reads every lobby member's;
-- custom multiplayer is enabled while every member runs a compatible Runtime. Then the carriers are allocated from the
-- synced table (one per custom id the lobby selects) and the host publishes the table and carrier hashes.
local mpstate={}          -- registry (hash, n), host (the hashes this machine publishes as the session host), preview
local VERSION=require('hd2runtime/domains/metadata').version
-- The registry hash: every registered custom stratagem with what the carrier allocation reads of it.
-- What every machine derives from a definition to mirror its payload (the impact donor, the native barrage, the Pelican's
-- gun): two Runtimes whose definitions differ there are not compatible.
-- (the registry hash: one do-block keeps the main chunk under LuaJIT's 200 locals; only registry_hash outside.)
local registry_hash
do
    local function payload_signature(d)
        local function sorted(t)
            local parts={}
            for k,v in pairs(t or{})do
                parts[#parts+1]=tostring(k)..'='..(type(v)=='table'and('{'..sorted(v)..'}')or tostring(v))
            end
            table.sort(parts)
            return table.concat(parts,',')
        end
        if d.kind=='support'and d.delivery~='runtime'then
            return 'impact='..tostring(d.delivery.impact)..',rounds='..tostring(d.delivery.rounds)
        elseif d.kind=='orbital'and d.orbital and d.orbital.native then
            return 'native='..d.orbital.pattern..',impact='..tostring(d.orbital.impact)
        elseif d.kind=='pelican'then
            -- A Mod Options choice of explosive rounds counts by its value now (dynamic_stamp re-hashes on a change).
            local gun=d.pelican.gun
            if require('hd2runtime/runtime/pelican_gunship').has_choice(gun)then
                local copy={}
                for k,v in pairs(d.pelican)do copy[k]=v end
                copy.gun=require('hd2runtime/runtime/pelican_gunship').gun_now(gun)
                return sorted(copy)
            end
            return sorted(d.pelican)
        elseif d.kind=='expendable'then
            -- The clone every machine applies (its level read now: a Mod Options level must agree across the lobby); a pod
            -- (its rack's items) only when the definition gives one (a definition without keeps its hash).
            if d.delivery.variant then
                local m=d.delivery.model
                local entry=m and require('hd2runtime/runtime/model_resources').record(m)
                return 'variant='..d.delivery.donor..(d.delivery.round and(',round='..d.delivery.round.type)or'')
                    ..(m and(',model='..tostring(entry and entry.sha256 and entry.sha256.unit or'none')..',model_use='
                    ..M.model_use_value(d.delivery.model_use))or'')
            end
            return 'expendable='..d.delivery.donor..',level='..level_value(d.delivery.level)..',impact='
                ..tostring(d.delivery.impact)..',rounds='..tostring(d.delivery.rounds)
                ..(d.delivery.pod and(',pod='..pod_text(d.delivery.pod))or'')
                ..(d.delivery.round and(',round='..d.delivery.round.type)or'')
                ..(d.delivery.damage and(',damage='..d.delivery.damage)or'')
        elseif d.kind=='pod'then
            return 'pod='..pod_text(d.delivery.pod)
        elseif d.kind=='sentry'and d.sentry then
            return 'sentry='..tostring(d.sentry.donor)..',weapon={'..sorted(d.sentry.weapon)..'}'
        elseif d.kind=='silo'then
            return require('hd2runtime/runtime/custom_silos').signature(d.delivery)
        end
        return''
    end
    -- What can change the registry hash after registration: the Mod Options level of an expendable definition (none for
    -- every other definition, so their hash is computed exactly as before).
    local function dynamic_stamp()
        local parts={#order}
        for _,d in ipairs(order)do
            if d.kind=='expendable'and type(d.delivery.level)~='string'then parts[#parts+1]=d.id..'='..level_value(d.delivery.level)end
            if d.kind=='expendable'and d.delivery.model and type(d.delivery.model_use)~='string'then
                parts[#parts+1]=d.id..'.model='..M.model_use_value(d.delivery.model_use)
            end
            local gun=d.kind=='pelican'and d.pelican.gun
            if gun and require('hd2runtime/runtime/pelican_gunship').has_choice(gun)then
                local now=require('hd2runtime/runtime/pelican_gunship').gun_now(gun)
                parts[#parts+1]=d.id..'='..tostring(now.round)..'/'..tostring(now.impact_explosion)..'/'
                    ..tostring(now.spread)..'/'..tostring(now.aim_height)
            end
        end
        return table.concat(parts,'|')
    end
    function registry_hash()
        local stamp=dynamic_stamp()
        if mpstate.registry and mpstate.registry_stamp==stamp then return mpstate.registry end
        local list={}
        for _,d in ipairs(order)do
            local policy=d.policy or{}
            local exclude={}
            for _,name in ipairs(d.exclude or{})do exclude[#exclude+1]=name end
            table.sort(exclude)
            -- A requested carrier group (and its slots) only when given: a definition without one keeps its line.
            -- Its selection always (r44: the carrier by default; an older build's token default is told apart).
            local group=policy.group~=nil and('|group='..tostring(policy.group)..(policy.slots and(',slots='
                ..tostring(policy.slots))or''))or''
            list[#list+1]={id=d.id,policy=table.concat({tostring(policy.beacon),table.concat(policy.prefer_families or{},'/'),
                table.concat(policy.allow_families or{},'/'),table.concat(policy.exclude or{},'/'),d.eagle and'eagle'or''},'|')
                ..group,
                family=table.concat({d.kind,d.delivery~='runtime'and d.delivery.stratagem or'',table.concat(exclude,'/'),
                    payload_signature(d),'selection='..(d.selection or'token')},'|')}
        end
        mpstate.registry,mpstate.registry_stamp=protocol.registry_hash(list),stamp
        return mpstate.registry
    end
    M.registry_hash=registry_hash
end
local function known_ids()local out={};for _,d in ipairs(order)do out[d.id]=true end;return out end
-- This player's SEMANTIC custom picks ({[slot] = id}; empty when none). The authority is the Runtime's own virtual-slot
-- table (runtime/stratagem_selector.lua virtual_slots), never a native record rebuilt now: while the loadout screen is
-- open the selector follows every virtual slot (one the player replaced or the game removed is dropped there, M.track),
-- and an unavailable definition unpicks itself (drop_virtual). Native data only VALIDATES it. The game's saved loadout is
-- written when the loadout screen is left, so it lags every pick made while the screen is open: live r4, a custom LAST
-- pick (the selector closing, the panel record repainting) published -,-,-,- until the save caught up. So a virtual slot
-- counts as vanilla only when the saved loadout POSITIVELY contradicts it: readable, the loadout screen closed (the save
-- settled), its order not the recorded one (selector.reconstruct), for M.PICK_CONTRADICTION s in a row. An unreadable
-- save, an open screen (a selector opening or closing, a repaint, the token briefly gone), a changed panel record: never.
M.PICK_CONTRADICTION=3
-- (the published picks: one do-block keeps the main chunk under LuaJIT's 200 locals; only virtual_picks outside.)
local virtual_picks
do
    local picks_check={since=nil,said=nil}
    function virtual_picks(world)
        local set=selector.virtual_slots()
        if not set then picks_check.since,picks_check.said=nil,nil;return {}end
        local out={}
        for slot,entry in pairs(set.slots)do
            if slot>=0 and slot<sync.SLOTS and defs[entry.definition]then out[slot]=entry.definition end
        end
        local ids=saved_ids(world)
        local ok,view=pcall(selector.screen,world)
        local settled=ids~=nil and ok and view~=nil and view.open==false
        if settled and not selector.reconstruct(ids)then
            picks_check.since=picks_check.since or clock
            if clock-picks_check.since>=M.PICK_CONTRADICTION then
                if not picks_check.said then
                    picks_check.said=true
                    log(('PICKS: the saved loadout (%s) has not matched the virtual slots (%s) for %.0f s with the loadout '
                        ..'screen closed: they count as vanilla until it does (the virtual slots are kept)'):format(
                        table.concat(ids,', '),selector.slots_text(set),clock-picks_check.since))
                end
                return {}
            end
        else
            if picks_check.said then log('PICKS: the saved loadout matches the virtual slots again')end
            picks_check.since,picks_check.said=nil,nil
        end
        return out
    end
    M.virtual_picks=virtual_picks
end
-- This player's custom picks by loadout slot ({[0..3] = id or false}), as published.
local function local_picks(world)
    local set=virtual_picks(world)
    local out={}
    for slot=0,sync.SLOTS-1 do out[slot]=set[slot]or false end
    return out
end
-- THE SHIP LOADOUT STATE (0.30 lifecycle; the user's choice: intentional, never a cache side effect). The custom slots the
-- player launched with are frozen at the mission entry: ship-scoped, separate from the selector's transient virtual
-- slots, the mission's frozen state and the peer channel. At the mission end every mission-scoped cache is cleared and
-- so are the selector's virtual slots; once the ship's saved loadout is readable again (M.RECONCILE_SETTLE s after the
-- return) they are rebuilt from this state only when the save still holds exactly the order they were launched with
-- (their tokens where they were); else they stay cleared, logged: a token alone never names a custom id. Until then this
-- machine publishes nothing new; afterwards it publishes its reconciled state once, as a new seq even when unchanged, so
-- every peer reads fresh ship state (runtime/custom_mp_sync.lua mission_ended).
M.RECONCILE_SETTLE=2
M.RECONCILE_TIMEOUT=30
local loadout_state={}
do
    local st={launched=nil,pending=false,since=nil,republish=false}
    function loadout_state.enter()
        st.launched=selector.snapshot_virtual()
        st.pending,st.republish=false,false
        log(('SHIP LOADOUT (mission entry): %s'):format(st.launched and('custom slots '..selector.slots_text(st.launched)
            ..' frozen with the loadout order '..table.concat(st.launched.pairs,', '))or'no custom slot'))
    end
    function loadout_state.leave()
        selector.restore_virtual(nil,'the mission ended (rebuilt from the ship loadout state once the saved loadout is '
            ..'readable)')
        st.pending,st.since=true,clock
    end
    function loadout_state.pending()return st.pending end
    function loadout_state.take_republish()
        local r=st.republish
        st.republish=false
        return r
    end
    local function same(a,c)
        if#a~=#c then return false end
        for k=1,#a do if a[k]~=c[k]then return false end end
        return true
    end
    -- Aboard the ship, every step while a reconciliation is pending.
    function loadout_state.step(world)
        if not st.pending or clock-st.since<M.RECONCILE_SETTLE then return end
        local ids=saved_ids(world)
        local l=st.launched
        if not ids and clock-st.since<M.RECONCILE_TIMEOUT then return end
        if not l then
            log('SHIP LOADOUT RECONCILED (back aboard the ship): no custom slot was launched; nothing to rebuild')
        elseif ids and same(ids,l.pairs)then
            selector.restore_virtual(l,'the saved loadout still holds their tokens in the launched order')
            log(('SHIP LOADOUT RECONCILED (back aboard the ship): custom slots %s restored (the saved loadout is the one '
                ..'they were launched with)'):format(selector.slots_text(l)))
        else
            log(('SHIP LOADOUT RECONCILED (back aboard the ship): custom slots %s NOT restored: the saved loadout is %s, '
                ..'they were launched with %s; pick them again'):format(selector.slots_text(l),ids and table.concat(ids,
                ', ')or'unreadable',table.concat(l.pairs,', ')))
        end
        st.pending,st.republish=false,true
    end
    function loadout_state.reset_for_tests()st={launched=nil,pending=false,since=nil,republish=false}end
end
M.loadout_state=loadout_state
-- Every Runtime step: publish this machine's state, read the lobby's. Returns the view.
local mp_sync_body
local function mp_sync_step(world,in_mission)
    if#order==0 then return nil end
    return mp_sync_body(world,in_mission)
end
function mp_sync_body(world,in_mission)
    local v=sync.view()
    -- In a mission, the items this machine's own custom calls delivered (runtime/custom_mp_items.lua). Back aboard the
    -- ship, nothing new until the ship loadout state is reconciled; then once, even unchanged (a fresh seq for peers).
    if in_mission or not loadout_state.pending()then
        sync.publish({version=VERSION,registry=registry_hash(),slots=local_picks(world),
            host=v and v.status=='enabled'and v.is_host and mpstate.host or nil,
            items=in_mission and mp_items.published(world)or nil,calls=in_mission and mp_calls.published(clock)or nil,
            force=not in_mission and loadout_state.take_republish()})
    end
    return sync.poll(world,clock,{mission=in_mission,known=known_ids(),version=VERSION,registry=registry_hash(),
        fast=in_mission and(mp_items.fast(clock)or#mp_calls.published(clock)>0 or mp_calls.waiting()>0
            or evidence.unresolved(clock)>0)})
end
M.mp_view=function()return sync.view()end
-- The carrier map of an allocation ({[id] = stable id}), its hash and its line.
local function carrier_map(a,ids)
    local map,parts={},{}
    for _,id in ipairs(ids)do
        local x=a and a.assignments[id]
        -- An expendable custom stratagem's entry also names its carrier weapon (a value of the hash input, never new
        -- protocol grammar); every other entry is exactly as before.
        if x then map[id]=x.weapon and(tostring(x.stable_id)..'+'..tostring(x.weapon.stable_id))or x.stable_id end
        parts[#parts+1]=id..' = '..(x and(('%s (stable id %d)'):format(x.carrier,x.stable_id)..(x.weapon and(', carrier '
            ..'weapon '..x.weapon.weapon)or'')..(x.local_refused and' NOT OWNED here'or''))or('REFUSED: '
            ..tostring(a and a.refused[id])))
    end
    return map,protocol.carrier_hash(map),#parts>0 and table.concat(parts,', ')or'none selected'
end

-- The startup progress (runtime/init_progress.lua): ready, done, total. Ready once the ship allocation ran for this
-- player's selection, or when nothing is registered or selected (no carrier work).
function M.init_state()
    if#order==0 then return true,0,0 end
    local ok,list=pcall(selected)
    if not ok or not list or#list==0 then return true,#order,#order end
    return ship.key~=nil,ship.key~=nil and#order or 0,#order
end
local function ship_step(world,v)
    -- Disabled lobby-wide (an incompatible registry): no carrier is allocated, nothing is reserved or blocked.
    local block=M.disabled_reason(v)
    if block then
        ship.alloc,ship.inputs,ship.key=nil,nil,nil
        if ship.disabled~=block then
            ship.disabled=block
            log('SHIP: '..block..'. No custom stratagem can be picked or run until then; your custom slots stay selected '
                ..'and are LOCKED in a mission (their token is never called); vanilla gameplay is untouched')
            M.disabled_notice()
        end
        return
    elseif ship.disabled then
        ship.disabled=nil
        log('SHIP: custom stratagems ENABLED again: every lobby Runtime has the same custom stratagem registry')
    end
    local list=selected()
    local mp_on=v and v.status=='enabled'
    if#list==0 and not mp_on then return end
    local ids,saved=loadout_ids(world)
    if not ids then return end
    if#list>0 and not selector.reconstruct(ids)then return end
    if carrier_presentation.applied()or weapon_clone.applied()or carrier_pod.applied()then return end   -- the restore comes first
    -- Every native selection this machine can read: its saved loadout and every stratagem record (aboard the ship
    -- other players' records are not proven to be there; in a mission each player's is).
    local lobby=allocator.lobby_native(world,saved)
    local present=lobby.present
    -- The carrier-in-slot probe: a carrier this player holds only in its own custom slots is not its native pick.
    do
        local probe=require('hd2runtime/runtime/carrier_in_slot')
        local own=probe.own_carriers(ids,selector.virtual_slots(),M.peer_ids(world))
        if next(own)then present=probe.discount(present,own)end
    end
    local table_ids=mp_on and sync.table_ids(v.table)or nil
    local screen_key='-'
    local mp_pins
    if mp_on then
        local carrier_mode=false
        for _,id in ipairs(table_ids or{})do if defs[id]and defs[id].selection=='carrier'then carrier_mode=true end end
        if carrier_mode then
            -- ONLY real native picks, so every machine computes the same carrier for an id (r40): this player's own
            -- loadout (its own carrier slots discounted) and each other player's (M.other_natives: the loadout screen's
            -- record of that player when it holds one, else its stratagem record), every slot the synced table names as
            -- custom excluded. r41: the own-carrier discount reads that same set (r40 read the stratagem records for it
            -- while the preview read the screen: a stale native pick there moved the slot back and forth). And the pins
            -- (M.ship_pins): a carrier-mode id keeps the carrier its slots hold, the lowest peer's holder's.
            local extra,okey,sources=M.other_natives(world,v)
            local merged={}
            for k in pairs(saved or{})do merged[k]=true end
            for k in pairs(extra)do merged[k]=true end
            local probe=require('hd2runtime/runtime/carrier_in_slot')
            present=probe.discount(merged,probe.own_carriers(ids,selector.virtual_slots(),extra))
            mp_pins=M.ship_pins(world,v)
            local parts,pin_text={},{}
            for k in pairs(extra)do parts[#parts+1]=tostring(k)end
            table.sort(parts)
            for id,stable in pairs(mp_pins)do pin_text[#pin_text+1]=id..'='..stable end
            table.sort(pin_text)
            screen_key=okey..'|'..table.concat(pin_text,',')
            if ship.screen_said~=screen_key then
                ship.screen_said=screen_key
                log(('CUSTOM MP NATIVE PICKS (aboard the ship, read-only; the carrier-in-slot probe): the other players\' '
                    ..'native picks (%s): %s; every custom slot excluded; pins %s'):format(sources~=''and sources or'none',
                    #parts>0 and table.concat(parts,', ')or'none',#pin_text>0 and table.concat(pin_text,', ')or'none'))
            end
        end
    end
    local pin_parts={}
    for id,stable in pairs(M.probe_pins())do pin_parts[#pin_parts+1]=id..'='..stable end
    table.sort(pin_parts)
    local key=table.concat(ids,',')..'|'..table.concat(lobby.peers,',')..'|'..(mp_on and v.table_hash or'-')..'|'
        ..table.concat(pin_parts,',')..'|'..screen_key
    if key==ship.key and clock<ship.at+M.REVALIDATE_EVERY then return end
    ship.key,ship.at=key,clock
    local a,why=allocate(world,present,list,mp_on and'aboard the ship, a PREVIEW from the synced lobby table (every '
        ..'player\'s native picks are final only at mission start)'or'aboard the ship, against the saved loadout',
        table_ids,nil,nil,mp_pins)
    if not a then
        if ship.waiting~=why then ship.waiting=why;log('carriers: waiting: '..tostring(why))end
        return
    end
    ship.waiting=nil
    ship.alloc=a
    ship.inputs={present=present,list=list,ids=table_ids,pins=mp_pins}
    -- Several players (EXPERIMENTAL): what this machine sees of the lobby, and the id -> carrier map every peer with
    -- the same mod set computes (runtime/custom_multiplayer.lua; read-only).
    local n=#(world_module.players(world)or{})
    if mp_on then
        local _,hash,text=carrier_map(a,table_ids)
        cmp.say('mp carriers',('CUSTOM MP CARRIERS (aboard the ship, preview; table hash %s): %s; carrier hash %s')
            :format(v.table_hash,text,hash))
        if v.is_host then mpstate.host={table=v.table_hash,carrier=hash}end
        local ag=sync.agreement(v,v.table_hash)
        if ag.status=='agree'then
            cmp.say('mp agreement','CUSTOM MP AGREEMENT (aboard the ship): table hash '..v.table_hash..' agrees with the '
                ..'session host\'s (carrier preview: '..hash..', the host\'s '..tostring(v.host_hashes.carrier)..')')
        elseif ag.status=='differ'then
            cmp.say('mp agreement',('CUSTOM MP AGREEMENT (aboard the ship): the %s hash DIFFERS from the session host\'s '
                ..'(mine %s, the host\'s %s)'):format(ag.field,tostring(ag.mine),tostring(ag.host)))
        end
    elseif n>1 then cmp.carriers(a,n,'aboard the ship')end
    for _,d in ipairs(list)do
        local mine=a.assignments[d.id]
        cache[d.id]=mine
        local reasons={}
        if not mine then
            -- Refused by the allocation, or not in it at all: with custom multiplayer the allocation covers the synced
            -- table's ids only (a pick this machine has not published yet is not in it).
            reasons[#reasons+1]=a.refused[d.id]or(mp_on and'not in the synchronized lobby table yet (it is published in '
                ..'the next Runtime step)'or'no carrier was allocated for it')
        else
            local conflicts=native_conflicts(world,d,mine.stable_id)
            if#conflicts>0 then reasons[#reasons+1]='its code '..d.code_text..' collides with '..table.concat(conflicts,'; ')end
            for _,id in ipairs(ids)do
                if id~=mine.stable_id then
                    local values=row_code(world,row_of(world,loadout.type_of(world,id)))
                    local relation=values and calldown.relation(d.code_values,values)
                    if relation then
                        reasons[#reasons+1]=('its code %s collides with %s in your loadout (%s)'):format(d.code_text,
                            names_by_id[id]or tostring(id),relation)
                    end
                end
            end
        end
        local text=#reasons==0 and('READY: carrier %s (%s, %s beacon), code %s'):format(mine.carrier,tostring(mine.family),
            tostring(mine.beam),d.code_text)or('NOT READY: '..table.concat(reasons,'; '))
        if ship.status[d.id]~=text then
            ship.status[d.id]=text
            log(('PRE-MISSION (%s): %s'):format(d.id,text))
        end
    end
end

-- The carrier-in-slot probe aboard the ship (0.2.1; the user's rule of 2026-10-07: never a lockout of the carrier):
-- a carrier slot whose carrier is no longer its definition's (anyone else picked it natively, or it went to another
-- custom stratagem: its pin no longer holds) is MOVED to the carrier the allocation gives it now, before the mission
-- (stratagem_selector.move_carrier: the pick's own guarded loadout write). One slot at a time; the difference must hold
-- for M.PROBE_MOVE_SETTLE s first (the loadout settles), then it is retried every M.PROBE_MOVE_RETRY s while the loadout
-- screen cannot take it (each reason logged once). A slot that has not moved by the launch is refused at mission start
-- (its slot locked, never called).
M.PROBE_MOVE_SETTLE=1
M.PROBE_MOVE_RETRY=2
do
    local probe_move={busy=false,seen={},said={},at=-math.huge}
    local function probe_move_why(world,set,e)
        local present=ship.inputs and ship.inputs.present or{}
        if present[e.token]then
            for k,id in ipairs(loadout_ids(world)or{})do
                local other=set.slots[k-1]
                if id==e.token and not(other and other.carrier and other.token==id)then
                    return('you picked it natively into loadout slot %d'):format(k-1)
                end
            end
            return 'another player picked it natively'
        end
        for id,x in pairs(ship.alloc and ship.alloc.assignments or{})do
            if id~=e.definition and x.stable_id==e.token then return 'it is now the carrier of '..id end
        end
        return 'it is no longer eligible for it'
    end
    local function probe_move_step(world)
        if probe_move.busy then return end
        local game=world_module.game_state(world)
        local set=selector.virtual_slots()
        local a=ship.alloc
        if not(game and game.name=='Ship'and set and a)then probe_move.seen={};return end
        local list={}
        for slot,e in pairs(set.slots)do if e.carrier then list[#list+1]=slot end end
        table.sort(list)
        for _,slot in ipairs(list)do
            local e=set.slots[slot]
            local mine=a.assignments[e.definition]
            local key=mine and mine.stable_id and mine.stable_id~=e.token and not mine.local_refused
                and(e.token..'>'..mine.stable_id)or nil
            local seen=probe_move.seen[slot]
            if not key then probe_move.seen[slot]=nil;probe_move.said[slot]=nil
            elseif not(seen and seen.key==key)then probe_move.seen[slot]={key=key,at=clock}
            elseif clock>=seen.at+M.PROBE_MOVE_SETTLE and clock>=probe_move.at+M.PROBE_MOVE_RETRY then
                probe_move.at=clock
                local from=names_by_id[e.token]or('stable id '..tostring(e.token))
                local why=probe_move_why(world,set,e)
                local function waiting(text)
                    if probe_move.said[slot]~=text then
                        probe_move.said[slot]=text
                        log(('SHIP (%s): its loadout slot %d holds %s, but %s: it moves to %s once %s (a slot that has not moved '
                            ..'by the launch is refused in the mission, locked)'):format(e.definition,slot,from,why,mine.carrier,
                            text))
                    end
                end
                local view=selector.screen(world)
                if not(view and view.open and view.record)then waiting('the loadout screen is open')
                elseif view.launched then waiting('the loadout is not launched yet (too late now)')
                elseif view.ready then waiting('you are not ready (unready to let it move)')
                elseif view.bound~=view.record.address then waiting('the loadout panel is bound again')
                else
                    probe_move.busy=true
                    selector.move_carrier(slot,e.definition,{id=mine.stable_id,name=mine.carrier},function(h)
                        probe_move.busy=false
                        if h.status=='moved'then
                            probe_move.seen[slot],probe_move.said[slot]=nil,nil
                            log(('SHIP (%s): loadout slot %d MOVED from %s to %s (%s), before the mission; nothing else in the '
                                ..'loadout changed'):format(e.definition,slot,from,mine.carrier,why))
                        else
                            waiting(('the write is accepted (%s: %s)'):format(tostring(h.code),tostring(h.reason)))
                        end
                    end)
                    return
                end
            end
        end
    end
    M.probe_move_step=probe_move_step
end

-- THE CARRIER-IN-SLOT PROBE WITH SEVERAL PLAYERS (r38, EXPERIMENTAL; the user's request of 2026-10-07): every other
-- player's carrier slot is presented as its custom stratagem on THIS machine too: the custom name and icon on that
-- carrier's row (no code: this machine never calls it), as an expendable's clone already is on every machine
-- (add_clone). From the first mission update (before the HUD), so this machine's teammate panel shows that slot as the
-- custom stratagem natively, and the teammate HUD overlay stands down for it (M.presented_here). r40: from the loading
-- screen (PrepareMission: every player's record is built at the launch), so what reads the names while the mission
-- loads (the TAB menu showed the carrier's own name at r38) already reads the custom stratagem's. The authority is the
-- synced lobby table (that player's slot names a carrier-mode custom id) and that player's record entry (the type it
-- holds); never presented when that type is also a native pick anywhere (this machine's own included) or two custom
-- ids claim it. This machine's own carrier slots are presented by their own steps. Restored with every presentation
-- at the mission's end (restore_all).
M.REMOTE_EVERY=0.25
do
    local remote={done={},names={},ids={}}
    function M.probe_remote_step(world)
        local game=world_module.game_state(world)
        if not(game and(game.mission or game.name=='PrepareMission'))then
            if next(remote.done)or next(remote.ids)then remote={done={},names={},ids={}}end
            return
        end
        local v=sync.view()
        if not(v and v.status=='enabled'and v.table)then return end
        local records=game.mission and cmp.first_records()or nil
        if not(records and#records>1)then records=slots.records(world)end
        if not(records and#records>1)then return end
        local present,custom=sync.native_present(records,v.table,function(kind)return loadout.id_of(world,kind)end)
        local token=loadout.type_of(world,stratagem_id(M.TOKEN))
        -- r43: this machine's own slots of an id, in either mode (a token slot's own steps present it with its code).
        local mine={}
        local V=selector.virtual_slots()
        for _,e in pairs(V and V.slots or{})do if e.definition then mine[e.definition]=true end end
        local claims={}
        for _,c in ipairs(custom)do
            local d=defs[c.id]
            if c.type~=token and d and d.selection=='carrier'then
                local cl=claims[c.type]or{id=c.id,where={},own=false}
                claims[c.type]=cl
                if cl.id~=c.id then cl.conflict=true end
                if c.peer==v.local_peer or mine[c.id]then cl.own=true end
                if c.peer~=v.local_peer then cl.where[#cl.where+1]=('peer %s slot %d'):format(c.peer,c.slot)end
            end
        end
        for kind,cl in pairs(claims)do
            local stable=loadout.id_of(world,kind)
            local name=stable and names_by_id[stable]
            local key=kind..'='..cl.id
            -- Found restored (it is never restored before the ship, r41; but if so): applied again, at most 3 times.
            if remote.done[key]=='applied'and name and not carrier_presentation.applied(name)then
                remote.again=(remote.again or 0)+1
                if remote.again<=3 then
                    remote.done[key]=nil
                    log(('MISSION: REMOTE CARRIER found restored (%s for %s): applied again'):format(name,cl.id))
                end
            end
            if not remote.done[key]then
                local why
                if cl.conflict then why='two custom stratagems claim it'
                elseif not name then why='not a catalogued stratagem'
                elseif present[stable]then why='it is also a native pick here (never presented as a custom stratagem)'end
                if why then
                    remote.done[key]='refused'
                    log(('MISSION: REMOTE CARRIER NOT PRESENTED (the carrier-in-slot probe): %s holds %s for %s: %s'):format(
                        #cl.where>0 and table.concat(cl.where,', ')or'your slot',tostring(name or kind),cl.id,why))
                elseif cl.own or carrier_presentation.applied(name)then
                    -- This machine's own slot of it (its own steps present it), or already presented here.
                    remote.done[key]='own'
                    remote.names[kind],remote.ids[kind]=name,cl.id
                    if#cl.where>0 then
                        log(('MISSION: REMOTE CARRIER (the carrier-in-slot probe): %s holds %s for %s: presented here by '
                            ..'this machine\'s own slot of it'):format(table.concat(cl.where,', '),name,cl.id))
                    end
                else
                    remote.done[key]='pending'
                    local d=defs[cl.id]
                    carrier_presentation.apply({carrier=name,text=d.texts,icon=d.icon},function(h)
                        local applied=h.status=='applied'
                        remote.done[key]=applied and'applied'or'refused'
                        if applied then remote.names[kind],remote.ids[kind]=name,cl.id end
                        log(('MISSION: REMOTE CARRIER %s (the carrier-in-slot probe): %s holds %s for %s: %s'):format(
                            applied and'PRESENTED'or'NOT PRESENTED',table.concat(cl.where,', '),name,cl.id,applied
                            and('presented here as '..d.label..' (its name and icon; no code: never called here)')
                            or(tostring(h.code)..': '..tostring(h.reason))))
                    end)
                end
            end
        end
    end
    -- Whether this machine presents carrier type `kind` as custom id `id` now: the native card shows it.
    function M.presented_here(kind,id)
        local name=remote.names[kind]
        return name~=nil and remote.ids[kind]==id and carrier_presentation.applied(name)==true
    end
end

------------------------------------------------------------------ expendable: availability (aboard the ship) --
-- An expendable custom stratagem is AVAILABLE while a carrier weapon of its donor's class remains for it: not picked
-- natively by any lobby member (this player's saved loadout, every stratagem record this machine reads) and not the
-- carrier weapon of another expendable custom stratagem the lobby selects (the synced picks; solo: this player's own).
-- Unavailable: its panel tile warns (who took the candidates), it cannot be picked, and when it is picked it UNPICKS
-- ITSELF (runtime/stratagem_selector.lua drop_virtual: the slot is plainly the token again; nothing written), unless
-- its slot holds its carrier itself (the carrier-in-slot probe): that slot stays selected (moved or locked). Its
-- carrier stratagem refused by the ship allocation makes it unavailable too. Re-evaluated every M.AVAILABILITY_EVERY s
-- aboard the ship; each transition logged once; never in a mission (the mission start freezes it: an unavailable
-- definition is simply not converted).
M.AVAILABILITY_EVERY=1
local avail={state={},text={},at=-math.huge,carrier={},kept={}}
-- The native picks this machine reads, and who made each: present {[stable id] = true}, who {[stable id] = {tags}},
-- and this player's virtual slots ({[slot] = id}).
local function lobby_picks(world,ids)
    local present,who={},{}
    local function add(id,tag)
        if not id then return end
        present[id]=true
        local l=who[id]or{}
        who[id]=l
        for _,x in ipairs(l)do if x==tag then return end end
        l[#l+1]=tag
    end
    -- The semantic picks (a custom slot's lagging saved entry is never a native pick of this player).
    local set=virtual_picks(world)
    for k,id in ipairs(ids)do if set[k-1]==nil then add(id,'your loadout')end end
    local v=sync.view()
    if v and v.status=='enabled'and v.table then
        -- With custom multiplayer, another player's slot the synced table names as custom is its custom slot (its token,
        -- or with the carrier-in-slot probe its carrier), never a native pick: the ship allocation's own set
        -- (M.other_natives). (The 2026-10-07 report: the host's Pelican carriers counted as its native picks here, so
        -- this view took the client's own carrier for another tile and unpicked the client's Pelican.)
        M.other_natives(world,v,function(peer,id)add(id,'peer '..peer)end)
    else
        for _,r in ipairs(slots.records(world)or{})do
            if not r['local']then
                for _,e in ipairs(r.entries or{})do add(loadout.id_of(world,e.type),'peer '..tostring(r.peer))end
            end
        end
    end
    return present,who,set
end
M.lobby_picks=lobby_picks
-- The stable ids other players' stratagem records hold now (a set; read-only). With custom multiplayer, an entry at a
-- loadout slot the synced lobby table names as that player's custom stratagem is that player's custom slot (its token,
-- or with the carrier-in-slot probe its carrier), never a native pick.
function M.peer_ids(world)
    local out={}
    local v=sync.view()
    local t=v and v.status=='enabled'and v.table or nil
    for _,r in ipairs(slots.records(world)or{})do
        if not r['local']then
            local picks=t and t[r.peer]
            local entries={}
            for _,e in ipairs(r.entries or{})do entries[#entries+1]=e end
            table.sort(entries,function(a,c)return a.index<c.index end)
            local slot=0
            for _,e in ipairs(entries)do
                local custom=false
                if e.granted==0 then
                    custom=picks~=nil and picks[slot]and true or false
                    slot=slot+1
                end
                local id=not custom and loadout.id_of(world,e.type)
                if id then out[id]=true end
            end
        end
    end
    return out
end
-- The other players' NATIVE picks the loadout screen shows (stratagem_selector.lobby_records, read-only), aboard the
-- ship with custom multiplayer (r38, the carrier-in-slot probe: a carrier slot whose carrier another player picks
-- moves before the launch): each other player's slots the synced lobby table does not name as custom. Only when every
-- other loadout record's owner is a peer of the table. Returns a set of stable ids and its key, or nil and why.
function M.screen_natives(world,v)
    if not(v and v.status=='enabled'and v.table)then return nil,'custom multiplayer is not enabled'end
    local ok,list=pcall(selector.lobby_records,world)
    if not(ok and list)then return nil,'the loadout screen is not open'end
    local out,parts=({}),{}
    for _,r in ipairs(list)do
        if not r['local']then
            local picks=v.table[r.owner]
            if picks==nil then
                return nil,('the loadout screen\'s player %s is not a peer of the lobby table'):format(tostring(r.owner))
            end
            for k,kind in ipairs(r.types)do
                local id=not picks[k-1]and loadout.id_of(world,kind)or nil
                if id then out[id]=true;parts[#parts+1]=r.owner..':'..id end
            end
        end
    end
    table.sort(parts)
    return out,table.concat(parts,',')
end
do
    -- r41: each other player's loadout as this machine sees it aboard the ship: {[peer] = {types in slot order},
    -- source}: the loadout screen's record of that player when it holds one (owner = peer), else its stratagem record here.
    local function other_loadouts(world,v)
        local screen,out={},{}
        local ok,list=pcall(selector.lobby_records,world)
        for _,r in ipairs(ok and list or{})do
            if not r['local']and#(r.types or{})>0 then screen[r.owner]=r.types end
        end
        for _,r in ipairs(slots.records(world)or{})do
            if not r['local']then
                local entries={}
                for _,e in ipairs(r.entries or{})do if e.granted==0 then entries[#entries+1]=e end end
                table.sort(entries,function(a,c)return a.index<c.index end)
                local types={}
                for k,e in ipairs(entries)do types[k]=e.type end
                out[r.peer]={types=types,source='its stratagem record'}
            end
        end
        for peer,types in pairs(screen)do out[peer]={types=types,source='the loadout screen'}end
        local peers={}
        for peer in pairs(v.table or{})do if peer~=v.local_peer then peers[#peers+1]=peer end end
        table.sort(peers)
        return out,peers
    end
    -- The other players' NATIVE picks aboard the ship with custom multiplayer (r41): per player (other_loadouts), every slot
    -- the synced lobby table names as that player's custom slot excluded. Returns the set of stable ids, a key, the sources.
    -- on_pick(peer, stable id), optional: called for each native pick (who made it).
    function M.other_natives(world,v,on_pick)
        local out,parts,sources={},{},{}
        if not(v and v.status=='enabled'and v.table)then return out,'',''end
        local seen,peers=other_loadouts(world,v)
        for _,peer in ipairs(peers)do
            local picks,l=v.table[peer]or{},seen[peer]
            sources[#sources+1]=peer..' from '..(l and l.source or'nowhere (nothing seen yet)')
            for k,kind in ipairs(l and l.types or{})do
                local id=not picks[k-1]and loadout.id_of(world,kind)or nil
                if id then
                    out[id]=true;parts[#parts+1]=peer..':'..id
                    if on_pick then on_pick(peer,id)end
                end
            end
        end
        table.sort(parts)
        return out,table.concat(parts,','),table.concat(sources,'; ')
    end
    -- The pins with several players (r41): every carrier-mode custom id the synced table selects keeps the carrier its
    -- slots hold: of every player holding it (this player's own carrier slots, the others' slots as other_loadouts sees
    -- them), the holder with the lowest peer id gives it. Deterministic for the same observations, so two players holding
    -- one id converge on one carrier; the allocator honours a pin only while that carrier is eligible (no native pick).
    -- Returns {[definition id] = stable id}.
    function M.ship_pins(world,v)
        local holders={}
        local token=stratagem_id(M.TOKEN)
        local function add(peer,id,stable)
            local d=id and defs[id]
            if not(d and d.selection=='carrier'and stable and stable~=token)then return end
            local h=holders[id]
            if not h or peer<h.peer then holders[id]={peer=peer,stable=stable}end
        end
        if not(v and v.status=='enabled'and v.table)then return {}end
        local set=selector.virtual_slots()
        for _,e in pairs(set and set.slots or{})do if e.carrier then add(v.local_peer,e.definition,e.token)end end
        local seen,peers=other_loadouts(world,v)
        for _,peer in ipairs(peers)do
            local picks,l=v.table[peer]or{},seen[peer]
            for k,kind in ipairs(l and l.types or{})do
                if picks[k-1]then add(peer,picks[k-1],loadout.id_of(world,kind))end
            end
        end
        local pins={}
        for id,h in pairs(holders)do pins[id]=h.stable end
        return pins
    end
    -- The pins at mission start with several players (r41): the same rule from every player's first-seen record (`custom`:
    -- sync.native_present's custom slots), identical on every machine. Returns {[definition id] = stable id}.
    function M.mission_pins(world,custom,token_type)
        local holders={}
        for _,c in ipairs(custom or{})do
            local d=defs[c.id]
            local stable=c.type~=token_type and loadout.id_of(world,c.type)or nil
            if d and d.selection=='carrier'and stable then
                local h=holders[c.id]
                if not h or c.peer<h.peer then holders[c.id]={peer=c.peer,stable=stable}end
            end
        end
        local pins={}
        for id,h in pairs(holders)do pins[id]=h.stable end
        return pins
    end
end
-- Definitions that follow the availability rule: every expendable one, every carrier pod, and every definition that
-- requested a carrier GROUP. (A legacy policy-only definition keeps its PRE-MISSION refusal, unchanged.)
-- r6: every definition with a carrier group, requested or default (the user's rule: both directions for every custom
-- stratagem; a large group is unavailable only when every member is taken).
local function availability_ruled(d)
    return d.kind=='expendable'or d.kind=='pod'or d.group~=nil or(type(d.policy)=='table'and d.policy.group~=nil)
end
-- The lobby picks that took a definition's group members: its candidates refused only for being in a lobby pick.
local function taken_by(a,id,who)
    local out={}
    for _,c in ipairs(a and a.candidates and a.candidates[id]or{})do
        if c.codes and#c.codes==1 and c.codes[1]=='in_loadout'then
            local tags=who and who[c.id]
            out[#out+1]=('%s (picked natively: %s)'):format(c.name,tags and#tags>0 and table.concat(tags,', ')
                or'a lobby member\'s loadout')
        end
    end
    return out
end
-- A quiet policy allocation of every registered definition that takes a policy carrier (the ship's group view; no
-- line logged), cached for M.REVALIDATE_EVERY s per native-pick set and pins. pins: {[definition id] = stable id}, the
-- carriers the carrier-in-slot probe's slots hold (as the ship allocation's: a held carrier is never given to a tile
-- nobody picked).
local group_view={key=nil,at=-math.huge}
local function group_allocation(world,present,players,pins)
    pins=pins or{}
    local keys,pin_keys={},{}
    for id in pairs(present)do keys[#keys+1]=tostring(id)end
    table.sort(keys)
    for id,stable in pairs(pins)do pin_keys[#pin_keys+1]=id..'='..tostring(stable)end
    table.sort(pin_keys)
    local key=table.concat(keys,',')..'|'..players..'|'..table.concat(pin_keys,',')
    if group_view.key==key and clock<group_view.at+M.REVALIDATE_EVERY then return group_view.a end
    local definitions={}
    for _,d in ipairs(order)do
        if d.kind~='expendable'then
            definitions[#definitions+1]={id=d.id,label=d.label,token=M.TOKEN,policy=d.alloc_policy or d.policy,
                eagle=d.eagle~=nil,filter=d.filter,pin=pins[d.id]}
        end
    end
    local ok,a=pcall(allocator.allocate_lobby,world,definitions,{present=present,players=players},global_exclude())
    group_view.key,group_view.at,group_view.a=key,clock,ok and a and a.ready and a or nil
    return group_view.a
end
-- The carrier-in-slot probe at mission start: why a definition whose slots hold its carrier cannot run now (text and
-- that carrier's name), or nil (it runs; or its slots hold the token).
function M.probe_refusal(d,a,players)
    local set=selector.virtual_slots()
    local x=require('hd2runtime/runtime/carrier_in_slot').slots_by_definition(set)[d.id]
    if not x then return nil end
    local name=names_by_id[x.id]or('stable id '..tostring(x.id))
    if players>1 then
        return('the probe runs solo only; its slot%s hold%s the carrier %s itself and %s locked for this mission'):format(
            #x.slots==1 and''or's',#x.slots==1 and's'or'',name,#x.slots==1 and'is'or'are'),name
    end
    if x.mixed then return 'its slots hold different carriers',name end
    for _,e in pairs(set.slots)do
        if e.definition==d.id and not e.carrier then return 'its slots mix the token and the carrier',name end
    end
    if x.id~=a.stable_id then
        return('its slot%s hold%s the carrier %s, but its carrier now is %s (anyone else picked it, and the slot could not '
            ..'move aboard the ship before the launch)'):format(#x.slots==1 and''or's',#x.slots==1 and's'or'',name,
            tostring(a.carrier)),name,'moved'
    end
    return nil
end
-- Whether the probe refuses a definition at mission start (every probe_refusal but the moved carrier, which the launch
-- fallback swaps: M.probe_reconvert).
function M.probe_blocks(d,a,players)
    local text,_,kind=M.probe_refusal(d,a,players)
    return text~=nil and kind~='moved'
end
-- The launch fallback (0.3.0): a definition whose carrier slots hold a carrier that is no longer its carrier (the slot
-- could not move aboard the ship before the launch) is swapped in this mission's record, old carrier -> its carrier,
-- by the proven slot conversion (its own entries only, by loadout position; the slots locked until ready). Returns
-- {from (stable id), from_name} or nil.
function M.probe_reconvert(d,a,players)
    local text,name,kind=M.probe_refusal(d,a,players)
    if not(text and kind=='moved')then return nil end
    local x=require('hd2runtime/runtime/carrier_in_slot').slots_by_definition(selector.virtual_slots())[d.id]
    return {from=x.id,from_name=name,text=text}
end
-- The carrier-in-slot probe (runtime/carrier_in_slot.lua): the carrier a definition's pick writes into the slot now,
-- {id (stable id), name}, or nil (its pick writes the token: another selection mode, several players, or no carrier
-- known yet).
function M.probe_carrier(id)
    local d=defs[id]
    if not(d and d.selection=='carrier')then return nil end
    local world=world_module.open()
    local players=world and world_module.players(world)
    if players and#players>1 then
        local v=sync.view()
        if not(v and v.status=='enabled')then
            require('hd2runtime/runtime/carrier_in_slot').log(id..': several players without custom multiplayer: its pick '
                ..'writes the token')
            return nil
        end
        require('hd2runtime/runtime/carrier_in_slot').log(id..': several players (custom multiplayer, EXPERIMENTAL r38): '
            ..'its pick writes the carrier the lobby gives it')
    end
    -- The ship preview's own assignment first (r41: with several players it holds the pins, so a pick of an id another
    -- player already holds takes that player's carrier), then the selection's cache, then the availability view.
    local a=(ship.alloc and ship.alloc.assignments[id])or cache[id]or(group_view.a and group_view.a.assignments[id])
        -- r43: an expendable's condensed carrier (its carrier weapon's own stratagem), from the availability step.
        or(d.kind=='expendable'and avail.carrier[id])or nil
    if not(a and a.stable_id and a.carrier)then
        require('hd2runtime/runtime/carrier_in_slot').log(id..': no carrier is allocated yet: its pick writes the token')
        return nil
    end
    return {id=a.stable_id,name=a.carrier}
end
local function availability_step(world,v)
    if clock<avail.at+M.AVAILABILITY_EVERY then return end
    avail.at=clock
    local block=M.disabled_reason(v)
    if block then
        -- Every custom stratagem unavailable with that reason (its tile warns; a pick is refused). Selected slots are NOT
        -- unpicked: that would leave a plain token; they are locked in the mission instead.
        for _,d in ipairs(order)do
            avail.state[d.id]=block
            if avail.text[d.id]~=block then avail.text[d.id]=block;log(('AVAILABILITY (%s): UNAVAILABLE: %s'):format(d.id,block))end
        end
        avail.disabled=true
        return
    elseif avail.disabled then
        avail.disabled=nil
        avail.state,avail.text={},{}
    end
    local list={}
    for _,d in ipairs(order)do if availability_ruled(d)then list[#list+1]=d end end
    if#list==0 then return end
    local ids=loadout_ids(world)
    if not ids then return end
    local present,who,set=lobby_picks(world,ids)
    local selected={}
    for _,id in pairs(set)do selected[id]=true end
    -- The carriers held in carrier slots (the ship allocation's pins: with custom multiplayer every player's).
    local pins=(v and v.status=='enabled'and v.table)and M.ship_pins(world,v)or M.probe_pins()
    local source={}
    if v and v.status=='enabled'then source=sync.table_ids(v.table)
    else for id in pairs(selected)do source[#source+1]=id end;table.sort(source)end
    local claims={}
    for _,id in ipairs(source)do
        local d=defs[id]
        if d and d.kind=='expendable'then
            claims[#claims+1]={id=id,donor=d.delivery.donor,slots=d.slots,fits=d.delivery.fits,
                fallback=d.delivery.fallback~=nil,variant=d.delivery.variant==true}
        end
    end
    local alloc=weapon_carriers.allocate(claims,present,{who=who})
    local okp,plist=pcall(world_module.players,world)
    local players=okp and plist and#plist or 1
    for _,d in ipairs(list)do
        local reason,text
        if d.kind=='expendable'then
            local weapon
            if alloc.assignments[d.id]then weapon=alloc.assignments[d.id]
            elseif alloc.refused[d.id]then reason=alloc.refused[d.id]
            else reason,weapon=weapon_carriers.unavailable(d.id,d.delivery.donor,present,claims,{who=who,slots=d.slots,
                fallback=d.delivery.fallback~=nil,variant=d.delivery.variant==true})end
            local mode
            avail.carrier[d.id]=nil
            if not reason and weapon.donor_self then
                -- The donor itself: its beacon always a separate support carrier.
                local mine=ship.alloc and ship.alloc.assignments[d.id]
                local carrier_why=ship.alloc and not mine and ship.alloc.refused[d.id]
                if carrier_why then
                    reason=('UNAVAILABLE: its carrier weapon is the regular %s and no separate support carrier is free: %s')
                        :format(weapon.weapon,tostring(carrier_why))
                else
                    mode=('the donor itself: every clone carrier weapon of its class is taken (%s): the regular %s from its own '
                        ..'pod, no clone (its launchers keep its name and icon); %s'):format(tostring(weapon.taken),
                        weapon.weapon,mine and('its beacon carrier is '..mine.carrier)or'a separate support carrier throws '
                        ..'its beacon')
                end
            elseif not reason then
                -- Its beacon: the carrier weapon's own stratagem (condensed), else a separate support carrier.
                local c,second=condensed_carrier(world,weapon.weapon,present,players>1)
                if c then
                    mode=('condensed: %s is also its beacon carrier and its pod'):format(weapon.weapon)
                    avail.carrier[d.id]={stable_id=c.id,carrier=c.name}
                else
                    local mine=ship.alloc and ship.alloc.assignments[d.id]
                    local carrier_why=ship.alloc and not mine and ship.alloc.refused[d.id]
                    if mine then
                        mode=('fallback: its beacon carrier is %s, because %s cannot carry it: %s'):format(mine.carrier,
                            weapon.weapon,tostring(second))
                    elseif carrier_why and not tostring(carrier_why):find('^UNAVAILABLE: every carrier weapon')then
                        reason=('UNAVAILABLE: its carrier weapon %s cannot carry its beacon (%s) and no separate support '
                            ..'carrier is free: %s'):format(weapon.weapon,tostring(second),tostring(carrier_why))
                    else
                        mode=('fallback: a separate support carrier throws its beacon, because %s cannot carry it: %s')
                            :format(weapon.weapon,tostring(second))
                    end
                end
            end
            text=reason or(('AVAILABLE: its carrier weapon is %s%s (%s)'):format(weapon.weapon,alloc.assignments[d.id]
                and''or' when it is picked',mode))
        else
            -- A selected definition: the ship allocation's own verdict when it has one (the allocation its slot follows:
            -- the synced table's ids with every player's pins); a tile nobody picked: the view of every registered one.
            local a=ship.alloc
            if not(selected[d.id]and a and(a.assignments[d.id]or a.refused[d.id]))then
                a=group_allocation(world,present,players,pins)
            end
            local x=a and a.assignments[d.id]
            if x then
                text=('AVAILABLE: its carrier is %s (group %s%s)'):format(x.carrier,tostring(d.group),d.slots and
                    (', capacity '..d.slots)or'')
            elseif a and a.refused[d.id]then
                local took=taken_by(a,d.id,who)
                reason=('UNAVAILABLE: no free member of its carrier group %s: %s%s'):format(tostring(d.group),
                    tostring(a.refused[d.id]),#took>0 and('; taken by lobby picks: '..table.concat(took,'; '))or'')
                text=reason
            end
        end
        avail.state[d.id]=reason
        if not reason then avail.kept[d.id]=nil end
        if text and avail.text[d.id]~=text then
            avail.text[d.id]=text
            log(('AVAILABILITY (%s): %s'):format(d.id,text))
        end
        -- A carrier slot is never unpicked: unpicking leaves the carrier itself in the slot, a plain native pick that
        -- calls as the carrier's own (the 2026-10-07 report: a client's Gas Pelican called as its Orbital Smoke Strike).
        -- It stays selected: it moves once its allocation gives it a carrier again (probe_move_step), else the mission
        -- locks it (carrier_in_slot: never ready, never called).
        local held={}
        if reason and selected[d.id]then
            local V=selector.virtual_slots()
            for slot,e in pairs(V and V.slots or{})do if e.definition==d.id and e.carrier then held[#held+1]=slot end end
            table.sort(held)
        end
        if#held>0 then
            if avail.kept[d.id]~=reason then
                avail.kept[d.id]=reason
                log(('SHIP (%s): KEPT loadout slot%s %s (not unpicked): %s. The slot%s its carrier itself: unpicked it '
                    ..'would be that carrier\'s own call; it moves once a carrier is free for it, else it is LOCKED in the '
                    ..'mission (never called)'):format(d.id,#held==1 and''or's',table.concat(held,', '),reason,
                    #held==1 and' holds'or's hold'))
            end
        elseif reason and selected[d.id]then
            local dropped=selector.drop_virtual(d.id,reason)
            if#dropped>0 then
                ship.key=nil
                log(('SHIP (%s): UNPICKED loadout slot%s %s: %s. The slot%s plainly the %s token again: no conversion, '
                    ..'no presentation, no payload'):format(d.id,#dropped==1 and''or's',table.concat(dropped,', '),reason,
                    #dropped==1 and' is'or's are',M.TOKEN))
            end
        end
    end
end
-- Why a custom stratagem cannot be picked now (nil: it can): an expendable one, a carrier pod or a group definition
-- whose group has no free member.
function M.unavailable(id)return avail.state[id]end

-------------------------------------------------------------- carrier reservations: the native blocked set --
-- r6 (the user's decision, 2026-10-05): a carrier a selected custom stratagem depends on is BLOCKED in the native
-- stratagem picker while it is reserved (the game's own disabled-card state where it can be used safely:
-- runtime/stratagem_blocking.lua), and a custom stratagem whose carriers are all taken by native picks is unavailable in
-- the custom panel (the availability rule above). Generic, never per custom stratagem:
--   custom selections (this player's virtual slots; with custom multiplayer every lobby member's synced picks)
--   -> the ship allocation (one carrier per custom id; an expendable one's carrier weapon's own stratagem)
--   -> reserved carriers {[stable id] = {name, holders = {'you slot 2 (eat17g_clone)', 'peer X slot 3 (...)'}}}
-- Ref-counted by its holders: a carrier stays reserved until its last holder is gone (a cleared or replaced custom slot,
-- a teammate's synced picks changing). Recomputed every Runtime step aboard the ship; each change logged once.
-- (the carrier reservations: one do-block keeps the main chunk under LuaJIT's 200 locals; only reservations_step outside.)
local reservations_step,blocked_apply
do
    local reservations={key=nil,set={},blocked={}}
    -- Who selects each custom id now: {[id] = {'you slot 2', 'peer X slot 3'}} (this player's virtual slots; with custom
    -- multiplayer every lobby member's synced picks).
    local function holders_of(v)
        local holders={}
        local rows={}
        if v and v.status=='enabled'and v.table then
            local peers={}
            for peer in pairs(v.table)do peers[#peers+1]=peer end
            table.sort(peers)
            for _,peer in ipairs(peers)do rows[#rows+1]={label=peer==v.local_peer and'you'or('peer '..peer),slots=v.table[peer]}end
        else
            local s=selector.virtual_slots()
            local by={}
            for slot,e in pairs(s and s.slots or{})do by[slot]=e.definition end
            rows[1]={label='you',slots=by}
        end
        for _,r in ipairs(rows)do
            for slot=0,sync.SLOTS-1 do
                local id=r.slots[slot]
                if id then holders[id]=holders[id]or{};table.insert(holders[id],('%s slot %d'):format(r.label,slot))end
            end
        end
        return holders
    end
    -- The carrier stable ids an allocation's entry for id holds (its carrier stratagem, its carrier weapon's).
    local function held(x)
        local out={}
        if x and x.stable_id then out[#out+1]={id=x.stable_id,name=x.carrier}end
        -- (the donor itself too: reserved like every carrier weapon since the user's rule of 2026-10-06)
        if x and x.weapon and x.weapon.stable_id and x.weapon.stable_id~=x.stable_id then
            out[#out+1]={id=x.weapon.stable_id,name=x.weapon.weapon}
        end
        return out
    end
    local function satisfied(a,id)
        local x=a and a.assignments[id]
        return x~=nil and not(a.refused and a.refused[id])and(x.stable_id~=nil or x.weapon~=nil)
    end
    -- r7 (the user's rule): a native card X is BLOCKED iff picking X natively would leave a currently satisfiable selected
    -- custom stratagem without a carrier: present + X re-allocated with the same deterministic allocator, every id that
    -- had a carrier must keep one. Only carriers the current allocation ASSIGNS need testing: the allocator is greedy and
    -- deterministic, so removing a candidate nobody was given changes no choice. So EAT-17G with the EAT-700 and the
    -- EAT-411 both free blocks neither (its allocation moves); with one of them picked natively the other is its last
    -- carrier and is blocked. inputs = {present, list, ids} (the allocation's own inputs); scope = the selected ids.
    -- Returns {[stable id] = {name, ids = {lost custom ids}}}.
    local function carrier_blocks(world,inputs,a,scope)
        local blocks={}
        if not(inputs and a)then return blocks end
        local base,tested={},{}
        for _,id in ipairs(scope)do if satisfied(a,id)then base[#base+1]=id end end
        for _,id in ipairs(base)do
            for _,c in ipairs(held(a.assignments[id]))do
                if not tested[c.id]and not inputs.present[c.id]then
                    tested[c.id]=true
                    local present={}
                    for k in pairs(inputs.present)do present[k]=true end
                    present[c.id]=true
                    local ok,b=pcall(allocate,world,present,inputs.list,'feasibility',inputs.ids,nil,true,inputs.pins)
                    local lost={}
                    for _,other in ipairs(base)do
                        if not(ok and b and satisfied(b,other))then lost[#lost+1]=other end
                    end
                    if#lost>0 then blocks[c.id]={name=c.name,ids=lost}end
                end
            end
        end
        return blocks
    end
    M.carrier_blocks=function(world,inputs,a,scope)return carrier_blocks(world,inputs,a,scope)end
    -- Every update aboard the ship (the game rebuilds the grid's cards at every open): the blocked set on the open native
    -- grid; restored by the module when a carrier leaves the set or the grid closes.
    function blocked_apply(world,dt)
        if not(blocking and blocking.apply)then return end
        local ok,r=pcall(blocking.apply,world,reservations.blocked or{},dt)
        local why=not ok and tostring(r)or(r and r.status=='refused'and(tostring(r.code)..': '..tostring(r.reason)))or nil
        if why and reservations.failed~=why then
            reservations.failed=why
            log('CARRIER BLOCKING NOT APPLIED (the native picker keeps every card as it is): '..why)
        elseif not why then reservations.failed=nil end
        -- The carrier-in-slot probe's doubles (0.3.0): the carriers this player's carrier slots hold stay pickable.
        if blocking.enable then
            local eok,er=pcall(blocking.enable,world,reservations.enable or{},dt,
                {helper=require('hd2runtime/runtime/stratagem_card_enable')})
            local ewhy=not eok and tostring(er)or nil
            if ewhy and reservations.enable_failed~=ewhy then
                reservations.enable_failed=ewhy
                log('CARRIER DOUBLES NOT APPLIED (the game\'s grey stays): '..ewhy)
            elseif not ewhy then reservations.enable_failed=nil end
        end
    end
    -- Every ship step: the blocks recomputed when the allocation or its inputs changed (each change logged once).
    function reservations_step(world,v)
        local a,inputs=ship.alloc,ship.inputs
        local holders=holders_of(v)
        local scope={}
        for id in pairs(holders)do if defs[id]then scope[#scope+1]=id end end
        table.sort(scope)
        local key=tostring(a)..'|'..table.concat(scope,',')
        if key~=reservations.key then
            reservations.key=key
            reservations.set=(a and inputs and#scope>0)and carrier_blocks(world,inputs,a,scope)or{}
        end
        local set=reservations.set
        local stables={}
        for stable in pairs(set)do stables[#stables+1]=stable end
        table.sort(stables)
        local parts,blocked={},{}
        for _,stable in ipairs(stables)do
            local r=set[stable]
            local who={}
            for _,id in ipairs(r.ids)do
                who[#who+1]=('%s (%s)'):format(id,table.concat(holders[id]or{'not selected'},', '))
            end
            parts[#parts+1]=('%s (stable id %d): picking it would leave no carrier for %s'):format(tostring(r.name),stable,
                table.concat(who,'; '))
            blocked[stable]={reason=('the last viable carrier of %s'):format(table.concat(who,'; ')),holders=who}
        end
        local text=table.concat(parts,'; ')
        if text~=reservations.text then
            for stable,r in pairs(reservations.last or{})do
                if not set[stable]then
                    log(('CARRIER BLOCK RELEASED: %s (stable id %d): another carrier remains for every selected custom '
                        ..'stratagem'):format(tostring(r.name),stable))
                end
            end
            if#parts>0 then log('CARRIER BLOCKS (aboard the ship): '..text)end
            reservations.text,reservations.last=text,set
        end
        -- The carrier-in-slot probe adds no block of its own (the user's rule, 2026-10-07): a carrier slot's carrier is
        -- blocked only as above (the last viable carrier); when anyone else picks it, the slot moves to its next carrier
        -- aboard the ship (probe_move_step). 0.3.0: it stays pickable natively in this player's other slots (the
        -- doubles: the game's own "already in this loadout" grey lifted), unless the rule above blocks it.
        local enable={}
        local vs=selector.virtual_slots()
        for slot,e in pairs(vs and vs.slots or{})do
            if e.carrier and not blocked[e.token]then
                enable[e.token]=enable[e.token]or{definition=e.definition,slots={}}
                table.insert(enable[e.token].slots,slot)
            end
        end
        for _,spec in pairs(enable)do table.sort(spec.slots)end
        reservations.enable=enable
        reservations.blocked=blocked
    end
end

-- Aboard the ship with several players (EXPERIMENTAL; read-only, every M.MP_EVERY s, whatever this player selected): the
-- peers and every lobby player's slots as the loadout screen shows them (runtime/custom_multiplayer.lua).
local mp_ship={at=-math.huge}
local function mp_ship_step(world)
    if#order==0 or clock<mp_ship.at+M.MP_EVERY then return end
    mp_ship.at=clock
    local n=cmp.peers(world,'aboard the ship')
    if n>1 then
        mp.announce(n,'aboard the ship')
        cmp.lobby(world,loadout.type_of(world,stratagem_id(M.TOKEN)))
    end
end

-- Back aboard the ship: every carrier's presentation restored once the mission HUD is torn down (at the latest
-- RESTORE_DEADLINE s after the mission), and at once when the loadout screen opens.
local life={busy={},due=nil,refused={},retry_at=0}
local function restore_all(why,now)
    for _,carrier in ipairs(carrier_presentation.applied_carriers())do
        if now then
            local r,code,reason=carrier_presentation.restore_now(carrier)
            life.busy[carrier]=nil
            if r then
                life.refused[carrier]=nil
                log(('%s: %s presentation RESTORED in this frame: %d writes; exact %s; native %s'):format(why,carrier,
                    r.writes,tostring(r.verify.exact),tostring(r.verify.native)))
            else
                log(('%s: %s presentation could NOT be restored (nothing overwritten): %s: %s'):format(why,carrier,
                    tostring(code),tostring(reason)))
            end
        elseif not life.busy[carrier]and not life.refused[carrier]then
            life.busy[carrier]=true
            carrier_presentation.restore(function(h)
                life.busy[carrier]=nil
                if h.status=='restored'then
                    log(('%s: %s presentation RESTORED: %d writes; exact %s; native %s'):format(why,carrier,h.writes or 0,
                        tostring(h.verify.exact),tostring(h.verify.native)))
                elseif h.code=='UNAVAILABLE'or h.code=='TARGET_UNAVAILABLE'then
                    life.retry_at=clock+1
                else
                    life.refused[carrier]=h.code
                    log(('%s: %s presentation restore REFUSED (retried when the loadout screen opens): %s: %s'):format(why,
                        carrier,tostring(h.code),tostring(h.reason)))
                end
            end,carrier)
        end
    end
    -- The carrier PODS (a carrier's own rack items): back to the captured vanilla bytes.
    for _,carrier in ipairs(carrier_pod.applied_carriers())do
        local key='pod:'..carrier
        if now then
            local r,code,reason=carrier_pod.restore_now(carrier)
            life.busy[key]=nil
            if r then
                life.refused[key]=nil
                log(('%s: carrier pod %s RESTORED in this frame: %d writes; vanilla bytes %s'):format(why,carrier,r.writes,
                    tostring(r.verify.exact)))
            else
                log(('%s: carrier pod %s could NOT be restored (nothing overwritten): %s: %s'):format(why,carrier,
                    tostring(code),tostring(reason)))
            end
        elseif not life.busy[key]and not life.refused[key]then
            life.busy[key]=true
            carrier_pod.restore(function(h)
                life.busy[key]=nil
                if h.status=='restored'then
                    log(('%s: carrier pod %s RESTORED: %d writes; vanilla bytes %s'):format(why,carrier,h.writes or 0,
                        tostring(h.verify.exact)))
                elseif h.code=='UNAVAILABLE'or h.code=='TARGET_UNAVAILABLE'then
                    life.retry_at=clock+1
                else
                    life.refused[key]=h.code
                    log(('%s: carrier pod %s restore REFUSED (retried when the loadout screen opens): %s: %s'):format(
                        why,carrier,tostring(h.code),tostring(h.reason)))
                end
            end,carrier)
        end
    end
    -- The carrier WEAPONS (expendable custom stratagems): their type records back to the captured native bytes.
    for _,carrier in ipairs(weapon_clone.applied_carriers())do
        local key='weapon:'..carrier
        if now then
            local r,code,reason=weapon_clone.restore_now(carrier)
            life.busy[key]=nil
            if r then
                life.refused[key]=nil
                log(('%s: carrier weapon %s RESTORED in this frame: %d writes; every record native %s'):format(why,
                    carrier,r.writes,tostring(r.verify.exact)))
            else
                log(('%s: carrier weapon %s could NOT be restored (nothing overwritten): %s: %s'):format(why,carrier,
                    tostring(code),tostring(reason)))
            end
        elseif not life.busy[key]and not life.refused[key]then
            life.busy[key]=true
            weapon_clone.restore(function(h)
                life.busy[key]=nil
                if h.status=='restored'then
                    log(('%s: carrier weapon %s RESTORED: %d writes; every record native %s'):format(why,carrier,
                        h.writes or 0,tostring(h.verify.exact)))
                elseif h.code=='UNAVAILABLE'or h.code=='TARGET_UNAVAILABLE'then
                    life.retry_at=clock+1
                else
                    life.refused[key]=h.code
                    log(('%s: carrier weapon %s restore REFUSED (retried when the loadout screen opens): %s: %s'):format(
                        why,carrier,tostring(h.code),tostring(h.reason)))
                end
            end,carrier)
        end
    end
end
local function lifecycle_step(world,mission)
    if mission or not(carrier_presentation.applied()or weapon_clone.applied()or carrier_pod.applied())
        or clock<life.retry_at then return end
    life.due=life.due or clock+M.RESTORE_DEADLINE
    if stratagem_hud.populated(world)==true and clock<life.due then return end
    restore_all('RETURN TO SHIP',false)
end

------------------------------------------------------------------------------------------ the mission side --
local mission={}          -- the state of this mission
local Call={};Call.__index=Call
-- Writes a line tagged with the call.
function Call:log(text)log_module.emit('['..tostring(self.owner)..'] '..self.call_id..': '..tostring(text))end
-- Associates an entity this call spawned (role: 'pelican', 'weapon', ...). true, or nil and why.
function Call:associate(entity,role)
    local entry,why=instances.associate(entity,self,role or'spawned')
    return entry~=nil or nil,why
end
-- The live entities associated with this call (optionally of one role).
function Call:spawned(role)return instances.of_call(self.call_id,role)end
-- A Runtime bombardment for this call (runtime/bombardment_executor.lua: the vanilla shell of `shell`'s reviewed
-- record fired through the game's own projectile wrapper in `pattern`'s salvo pattern; nothing written).
-- spec = {shell = stratagem name (its reviewed first shell; its call-in package must be resident: list it in assets),
-- pattern = stratagem name (its reviewed bombardment record, exactly vanilla), target = {x, y, z} (default the call's
-- position)}. Returns the barrage handle, or nil, code, reason.
function Call:barrage(spec)
    spec=spec or{}
    local target=spec.target or self.position
    local d=defs[self.definition]
    local listed=false
    for _,name in ipairs(d and d.assets or{})do if name==spec.shell then listed=true end end
    if not listed then
        self:log('BARRAGE REFUSED: the shell donor '..tostring(spec.shell)..' is not one of this custom stratagem\'s assets')
        return nil,'NOT_AN_ASSET','list '..tostring(spec.shell)..' in assets'
    end
    if spec.impact_explosion~=nil then
        local listed_donor=false
        for _,name in ipairs(d and d.assets or{})do if name==spec.impact_explosion then listed_donor=true end end
        if not listed_donor then
            self:log('BARRAGE REFUSED: the explosion donor '..tostring(spec.impact_explosion)..' is not one of this custom '
                ..'stratagem\'s assets')
            return nil,'NOT_AN_ASSET','list '..tostring(spec.impact_explosion)..' in assets'
        end
    end
    local h,code,reason=executor.start({shell_donor=spec.shell,pattern=spec.pattern,overrides=spec.overrides,
        impact_explosion=spec.impact_explosion,target=target,label=self.call_id,multiplayer=self.multiplayer==true},
        function(e)
            if e.kind=='ended'then
                self:log(('BARRAGE ended: %d shells in %d salvos over %.1f s%s'):format(e.shells,e.salvos or 0,e.seconds or 0,
                    spec.impact_explosion and(('; %d exploded as %s\'s'):format(e.converted or 0,spec.impact_explosion))or''))
            elseif e.kind=='refused'then
                self:log(('BARRAGE stopped after %d shells: %s: %s'):format(e.shells or 0,tostring(e.code),tostring(e.reason)))
            end
        end)
    if not h then self:log(('BARRAGE REFUSED: %s: %s'):format(tostring(code),tostring(reason)))end
    return h,code,reason
end
-- A plain table of what the call is (for logs).
function Call:describe()
    return {id=self.definition,call_id=self.call_id,n=self.n,slot=self.slot,carrier=self.carrier and self.carrier.name,
        beacon=self.beacon and self.beacon.entity,position=self.position,state=self.state}
end

local Weapon={};Weapon.__index=Weapon
-- This weapon's projectiles explode as `donor`'s on impact (runtime/projectile_impact.lua: each projectile's own copy;
-- the weapon, its type, its row and every other weapon stay vanilla). The payload follows this exact weapon whoever
-- wields it (provenance: another player who picked it up fires the same payload; the kill credit stays the game's own,
-- the wielder). donor: 'Orbital Gas Strike'. Returns true, or nil, code, reason.
function Weapon:set_impact_explosion(donor,opts)
    opts=opts or{}
    -- An internal donor is the Runtime's own (its definition data): never a mod's call.
    local d=impacts.DONORS[donor]
    if d and d.internal and opts.data~=true then
        self.call:log(('weapon %d: set_impact_explosion(%s) REFUSED: UNREVIEWED_DONOR: an internal donor (the Runtime\'s '
            ..'own fallback)'):format(self.entity,tostring(donor)))
        return nil,'UNREVIEWED_DONOR','no reviewed impact explosion donor '..tostring(donor)
    end
    local binding,code,reason=impacts.bind({sources={self.entity},projectile=self.projectile,donor=donor,
        direct_damage=opts.damage,
        rounds=opts.rounds or 1,entity_type=self.entity_type,label=self.call.call_id..' weapon '..self.entity,
        multiplayer=self.call.multiplayer==true,client=self.call.client==true,provenance=true},
        function(e)
            if e.kind=='converted'then
                self.call.converted=(self.call.converted or 0)+1
                if(mission.players or 1)>1 and log_module.sample('call.projectile_converted',3)then
                    self.call:log(('PROJECTILE CONVERTED: launcher %d (network id %s): its projectile in pool slot %d, '
                        ..'impact explosion copy %d -> %d on this machine (%s; fired by %s; creditor %s, the game\'s own)')
                        :format(self.entity,tostring(self.network),e.slot,e.from,e.to,self.call.client and'a client'
                        or'the host',e.local_creditor and'this machine\'s player'or('another player who picked it up, '
                        ..tostring(e.creditor)),tostring(e.creditor)))
                end
            elseif e.kind=='impact'then
                self.call:log(('weapon %d: its projectile (pool slot %d) requested %s\'s explosion %d on impact'):format(
                    self.entity,e.slot,donor,e.explosion))
            elseif e.kind=='refused'and e.first then
                self.call:log(('weapon %d: a projectile stays vanilla: %s: %s'):format(self.entity,tostring(e.code),
                    tostring(e.reason)))
            end
        end)
    if not binding then
        self.call:log(('weapon %d: set_impact_explosion(%s) REFUSED: %s: %s'):format(self.entity,tostring(donor),
            tostring(code),tostring(reason)))
        return nil,code,reason
    end
    self.binding=binding
    -- A payload a mod's callback attached (not its definition's data): no other machine can derive it.
    if not opts.data and(mission.players or 1)>1 and not self.call.callback_noted then
        self.call.callback_noted=true
        self.call:log(('weapon %d: this payload was attached by the mod\'s callback, not declared as data: only this '
            ..'machine converts its rockets (declare delivery.items[].modify.impact_explosion to have every compatible '
            ..'Runtime convert its own copy)'):format(self.entity))
    end
    local dd=binding.damage and binding.damage[self.projectile]
    self.call:log(('weapon %d: its projectiles (type %d) explode as %s\'s on impact (explosion %d instead of %d)%s, %d '
        ..'round%s; every other weapon stays vanilla'):format(self.entity,self.projectile,donor,binding.to,binding.from,
        dd and(', their direct hit %d / %d (DamageInfo %d instead of %d, each round\'s own copy; not live-proven)')
        :format(dd.standard,dd.durable,dd.to,dd.from)or'',opts.rounds or 1,(opts.rounds or 1)==1 and''or's'))
    return true
end

-- This entity's own weapon, configured from data (runtime/custom_weapons.lua: projectile, rpm, spread, ammo, recoil; its
-- own copies and records only; its type and every other entity stay vanilla). Returns the result, or nil, code, reason.
function Weapon:configure(spec)
    local world=world_module.open()
    if not world then return nil,'UNAVAILABLE','no game world'end
    local result,code,reason=weapons.configure(world,self.entity,spec,self.call.call_id..' '..(self.kind or'weapon')..' '
        ..self.entity,{role=self.call.client and'client'or nil})
    if result then
        if spec.projectile then self.projectile=spec.projectile end
        self.configured=result
        self.call:log(('%s %d: its own weapon configured (%d writes; verified %s)'):format(self.kind or'weapon',self.entity,
            result.writes,tostring(result.verified)))
    else
        self.call:log(('%s %d: configure REFUSED: %s: %s (it stays vanilla)'):format(self.kind or'weapon',self.entity,
            tostring(code),tostring(reason)))
    end
    return result,code,reason
end
-- Its kill credit as the game computes it (read-only): the wielder, the no-credit tag, the faction, the network id.
function Weapon:credit()
    local world=world_module.open()
    local c=world and require('hd2runtime/runtime/pelican_weapon').credit_state(world,self.entity)
    return c
end

local function run_callback(d,name,ctx)
    local fn=d.callbacks[name]
    if not fn then return end
    local ok,why=pcall(events.run_as,d.owner,fn,ctx)
    if not ok then log(('%s %s failed: %s'):format(ctx.call_id,name,tostring(why)))end
end

local ensure_kill_watch   -- (defined with the kill report below)
local function reset_mission()
    mission={on=false,clock=0,populated=nil,started=false,queue={},by_type={},calls={},calls_by_beacon={},count={},
        n=0,watch=nil,seen={},conflicts={},kills={},remote={},pending={},remote_assets={},clones={},clone_order={},
        pods={}}
    instances.clear()
    cmp.reset_mission()
    -- Every launcher tracked for another machine's call, and this machine's published items, end with the mission.
    mp_items.reset()
    mp_calls.reset()
    evidence.reset()
    observer.reset_mission()
end
reset_mission()
-- The mission's FROZEN carrier map (custom id -> carrier, from the allocation at the mission start) and its inverse:
-- carrier type -> custom id and carrier stable id -> custom id. One carrier per unique custom id, distinct ids distinct
-- carriers, the same id across players one shared carrier, every native lobby pick excluded: so in the mission a
-- carrier beacon or thrown ball NAMES its custom id (the mission-time discriminator); no message has to claim it.
local function freeze_carriers(a,label)
    mission.carrier_types=cmp.carrier_types(a)
    local by_id,parts={},{}
    for id,x in pairs(a and a.assignments or{})do
        if x.stable_id then by_id[x.stable_id]=id;parts[#parts+1]=('%s (stable id %d) -> %s'):format(x.carrier,x.stable_id,id)end
    end
    table.sort(parts)
    mission.carrier_ids=by_id
    if label and#parts>0 then
        log(('FROZEN CARRIER MAP (%s): %s; a beacon or ball of one of these carriers is that custom id\'s call'):format(label,
            table.concat(parts,', ')))
    end
end

-- The call of a beacon (created in its first update); an on_called seen first from the record is joined to it.
local function new_call(d,a,slot)
    mission.n=mission.n+1
    mission.count[d.id]=(mission.count[d.id]or 0)+1
    local me=handles.local_player()
    local ctx=setmetatable({definition=d.id,id=d.id,owner=d.owner,n=mission.count[d.id],
        call_id=d.id..'#'..mission.count[d.id],player=me,slot=slot,carrier={name=a.carrier,stable_id=a.stable_id,
        type=a.type,group=d.group,condensed=a.condensed==true},delivery=d.delivery=='runtime'and'runtime'
        or(d.kind=='pod'and a.carrier)or(d.kind=='expendable'and M.delivery_of(d)and M.delivery_of(d).stratagem)
        or d.delivery.stratagem,state='called'},Call)
    ctx.player_peer=me and me.peer
    -- A client's own call inside the client-write proof (runtime/multiplayer.lua): its writes carry the mark.
    ctx.client=mission.client==true
    -- The call's own writes (and the entities associated with it) accept the experimental multiplayer scope
    -- (runtime/multiplayer.lua): only the solo guard is lifted, and only for them.
    ctx.multiplayer=true
    mp.mark_call(ctx)
    -- Its common shape (runtime/custom_provenance.lua CustomCall): the Pelican CAS is the session host's to run.
    ctx.custom_call=provenance.call({custom_id=d.id,call_id=ctx.call_id,seq=mission.count[d.id],caller_peer=ctx.player_peer,
        slot=slot,carrier_stable_id=a.stable_id,authority=d.kind=='pelican'and'host'or'caller'})
    mission.calls[#mission.calls+1]=ctx
    return ctx
end

--------------------------------------------------------- expendable: the carrier weapon clone (each mission) --
-- An expendable definition's delivery this mission: its carrier weapon's own pod and rack, its launchers firing the
-- donor's round at the full level (else the carrier weapon's own round, which the clone did not change).
local function expendable_delivery(d,weapon,level)
    -- The donor itself (the pool's last member): its own native pod; only the call's own launchers change, per projectile.
    if weapon and weapon.donor_self then
        local f=d.delivery.fallback
        if not f then return nil end
        local items,types,legacy={},{},nil
        for t,i in pairs(f.delivery.items)do
            items[t]={kind=i.kind,projectile=i.kind=='weapon'and i.projectile or nil}
            types[t]=true
            if i.kind=='weapon'and not legacy then legacy={item=t,projectile=i.projectile}end
        end
        return {kind='expendable',stratagem=f.stratagem,id=f.id,items=items,item_types=types,count=f.delivery.count,
            item=legacy and legacy.item,projectile=legacy and legacy.projectile,modify=d.delivery.modify,impact=f.impact,
            rounds=f.rounds,damage=f.damage,family='support',donor=d.delivery.donor,donor_self=true}
    end
    local base=weapon and d.delivery.deliveries[weapon.weapon]
    if not base then return nil end
    if d.delivery.pod then
        -- Its own pod items (the clone and the others) on this carrier weapon's rack, in the planned slots.
        local c=weapon_clone.carrier(weapon.weapon)
        local own
        for t,i in pairs(base.items)do if i.kind=='weapon'then own=own or i.projectile end end
        local projectile=d.delivery.round and d.delivery.round.type or(level=='full'and d.delivery.projectile or own)
        local items,types,layout,plan=pod_items(d.delivery.pod,weapon.weapon,c.entity,{projectile=projectile,
            modify=d.delivery.modify,impact=d.delivery.impact,rounds=d.delivery.rounds,damage=d.delivery.damage})
        if not plan then return nil end
        local legacy=hex_of(c.entity)
        return {kind='expendable',stratagem=base.stratagem,id=base.id,items=items,item_types=types,
            count=d.delivery.pod.total,item=legacy,projectile=projectile,modify=d.delivery.modify,impact=d.delivery.impact,
            rounds=d.delivery.rounds,damage=d.delivery.damage,family='support',donor=d.delivery.donor,layout=layout,
            units=pod_units(d.delivery.pod,c.entity),plan=plan}
    end
    local items,types,legacy={},{},nil
    for t,i in pairs(base.items)do
        local projectile=i.kind=='weapon'and(d.delivery.round and d.delivery.round.type
            or(level=='full'and d.delivery.projectile or i.projectile))or nil
        items[t]={kind=i.kind,projectile=projectile}
        types[t]=true
        if i.kind=='weapon'and not legacy then legacy={item=t,projectile=projectile}end
    end
    return {kind='expendable',stratagem=base.stratagem,id=base.id,items=items,item_types=types,count=base.count,
        item=legacy and legacy.item,projectile=legacy and legacy.projectile,modify=d.delivery.modify,
        impact=d.delivery.impact,rounds=d.delivery.rounds,damage=d.delivery.damage,family='support',
        donor=d.delivery.donor}
end
M.expendable_delivery=expendable_delivery
-- This mission's delivery of a definition: its own (support, sentry, Eagle, native orbital), or an expendable one's
-- carrier weapon delivery (frozen when its clone was set up; nil before or when it has none).
local function delivery_of(d)
    if d.kind=='pod'then
        -- A carrier pod: its carrier's own delivery this mission (frozen when its rack was written).
        local q=mission.pods and mission.pods[d.id]
        return q and q.delivery or nil
    end
    if d.delivery=='runtime'or d.kind~='expendable'then return d.delivery end
    local c=mission.clones and mission.clones[d.id]
    return c and c.delivery or nil
end
M.delivery_of=function(d)return delivery_of(d)end
-- One clone per expendable id the mission runs (this machine's own picks; with custom multiplayer every id the synced
-- lobby selects, whoever picked it: another player's launchers must be the clone here too).
local function add_clone(d,assignment)
    if mission.clones[d.id]or not(assignment and assignment.weapon)then return end
    local level=level_value(d.delivery.level)
    local donor_self=assignment.weapon.donor_self==true
    mission.clones[d.id]={definition=d,weapon=assignment.weapon,level=level,state='assets',waited=0,
        delivery=expendable_delivery(d,assignment.weapon,level),condensed=assignment.condensed==true,donor_self=donor_self}
    mission.clone_order[#mission.clone_order+1]=d.id
    if donor_self then
        local f=d.delivery.fallback
        log(('MISSION (%s): THE DONOR ITSELF: every clone carrier weapon of %s is taken (%s): the regular %s from its own pod, no '
            ..'clone (its launchers keep the %s\'s name and icon)%s; its beacon carrier is %s'):format(d.id,
            table.concat(d.delivery.pool,', '),tostring(assignment.weapon.taken),d.delivery.donor,d.delivery.donor,
            f and f.impact and('; each launcher\'s rocket explodes as '..f.impact..'\'s on impact')or'',
            tostring(assignment.carrier)))
        return
    end
    log(('MISSION (%s): carrier weapon %s (the first free of %s), level %s (frozen for this mission)%s%s'):format(d.id,
        assignment.weapon.weapon,table.concat(d.delivery.pool,', '),level,assignment.condensed and('; CONDENSED: '
        ..assignment.weapon.weapon..' is also its beacon carrier and its pod (one vanilla stratagem)')or
        (assignment.carrier and('; its beacon carrier is '..assignment.carrier..' (fallback: '..tostring(
        assignment.fallback)..')')or''),d.delivery.pod and('; its pod: '..pod_text(d.delivery.pod))or''))
end
local function clone_refused(c,text)
    c.state,c.why='refused',text
    log(('MISSION (%s): the carrier weapon %s stays its own weapon: %s'):format(c.definition.id,c.weapon.weapon,text))
end
-- One clone at a time: its assets (the donor's package, every pool candidate's, the payload donors'), the conversion of
-- the carrier weapon's type records, then its pod row's presentation (the custom stratagem's name and icon).
local function clone_step(world)
    for _,id in ipairs(mission.clone_order)do
        local c=mission.clones[id]
        local d=c.definition
        if c.state=='assets'then
            if not c.gate then
                local deps={}
                for _,name in ipairs(d.assets)do
                    for _,dep in ipairs(core_assets.dependencies_for_stratagem(stratagem_id(name),name)or{})do deps[#deps+1]=dep end
                end
                for _,dep in ipairs(core_assets.dependencies_for_stratagem(d.delivery.id,d.delivery.stratagem)or{})do
                    deps[#deps+1]=dep
                end
                for _,dep in ipairs(d.pod_deps or{})do deps[#deps+1]=dep end
                c.gate=core_assets.gate(world.runtime,{id='custom-clone-'..id,asset_dependencies=deps},log_module.emit)
            end
            local result,why=c.gate.tick(M.STEP)
            c.waited=c.waited+M.STEP
            if result=='failed'or(result~='ready'and c.waited>M.ASSET_TIMEOUT)then
                clone_refused(c,'the '..d.delivery.donor..'\'s package and its assets did not load: '..tostring(why or'timeout'))
                return
            end
            if result~='ready'then return end
            if c.donor_self then
                -- The donor itself: nothing to convert, rack or present (all shared); its own pod delivers.
                c.state='ready'
                log(('MISSION (%s): the regular %s READY (the donor itself: no clone; its own pod)'):format(id,
                    d.delivery.donor))
                return
            end
            c.state='applying'
            local spec={carrier=c.weapon.weapon,donor=d.delivery.donor,level=c.level,name=d.weapon_text,
                icon=d.weapon_icon,multiplayer=true,label=id,round=d.delivery.round and d.delivery.round.name}
            if d.delivery.variant then
                -- A variant: its own type; its round and (model_use 'apply') its model. 'check' reads only.
                local r=d.delivery.round
                spec={carrier=c.weapon.weapon,variant=true,name=d.weapon_text,icon=d.weapon_icon,multiplayer=true,label=id,
                    round=r and{type=r.type,package=r.package,label=r.label}or nil}
                local m=d.delivery.model
                if m then
                    local use=M.model_use_value(d.delivery.model_use)
                    local ok,ready,code,reason=pcall(require('hd2runtime/runtime/model_resources').ready,world.runtime,m,
                        c.weapon.weapon)
                    local text=ok and ready and'MODEL READY'or('MODEL NOT READY ('..tostring(ok and code or'FAILED')..': '
                        ..tostring(ok and reason or ready)..')')
                    local good=ok and ready==true
                    log(('MISSION (%s): %s: %s %s for the %s (model_use %s)%s'):format(id,text,tostring(m),
                        require('hd2runtime/runtime/model_resources').unit_hex(m),c.weapon.weapon,use,use=='check'
                        and': nothing written to its UnitPath (check only)'or(good and''
                        or': its UnitPath is not written (the vanilla model is kept); its round and name still apply')))
                    if use=='apply'and good then spec.model=m end
                end
            end
            weapon_clone.apply(spec,function(h)
                    if h.status=='applied'then c.applied=h;c.state=d.delivery.pod and'rack'or'pod'
                    else clone_refused(c,tostring(h.code)..': '..tostring(h.reason))end
                end)
            return
        elseif c.state=='applying'or c.state=='presenting'or c.state=='racking'then
            return
        elseif c.state=='rack'then
            -- Its own pod's rack holds the pod items for this mission (runtime/carrier_pod.lua), before any call.
            c.state='racking'
            if not c.delivery then
                clone_refused(c,'its pod items do not fit '..c.weapon.weapon..'\'s rack')
                return
            end
            carrier_pod.apply({carrier=c.weapon.weapon,items=c.delivery.units,multiplayer=true,label=id},function(h)
                if h.status=='applied'then
                    c.rack=h
                    c.state='pod'
                    log(('MISSION (%s): %s\'s own pod holds %s (%d slot%s written)'):format(id,c.weapon.weapon,
                        pod_text(d.delivery.pod),h.slots or 0,(h.slots or 0)==1 and''or's'))
                else
                    clone_refused(c,'its pod rack: '..tostring(h.code)..': '..tostring(h.reason))
                end
            end)
            return
        elseif c.state=='pod'then
            -- Condensed and this machine's own call: the definition's own presentation step presents that row (with the
            -- code) once; here nothing more is needed.
            local mine=false
            for _,item in ipairs(mission.queue)do if item.definition==d then mine=true end end
            if c.condensed and mine then
                c.state='ready'
                log(('MISSION (%s): carrier weapon %s READY as the %s (level %s); CONDENSED: its own row presents as %s '
                    ..'and answers to its code (the definition\'s presentation)'):format(id,c.weapon.weapon,
                    d.delivery.donor,c.level,d.label))
                return
            end
            c.state='presenting'
            carrier_presentation.apply({carrier=c.weapon.weapon,text=d.texts,icon=d.icon},function(h)
                c.pod=h.status=='applied'
                c.state='ready'
                log(('MISSION (%s): carrier weapon %s READY as the %s (level %s)%s'):format(id,c.weapon.weapon,
                    d.delivery.donor,c.level,c.pod and('; its pod and its marker present as '..d.label)
                    or('; its pod row keeps its own look ('..tostring(h.code)..': '..tostring(h.reason)..')')))
            end)
            return
        end
    end
end

-- In a beacon's FIRST update: a beacon of a converted carrier's type is a call of that custom stratagem.
local function decide(beacon)
    local entry=mission.by_type[beacon.type]
    if not entry then return nil end
    local d=entry.definition
    if d.delivery=='runtime'then return {delivery='none',client=entry.client==true}end
    -- An expendable custom stratagem: its carrier weapon's own pod (the clone); condensed, the beacon IS that weapon's
    -- own stratagem: nothing to change.
    if d.kind=='expendable'then
        local dl=delivery_of(d)
        if not dl then return nil end
        if entry.assignment and entry.assignment.condensed then return nil end
        return {delivery=dl.stratagem,client=entry.client==true}
    end
    -- A carrier pod: the carrier delivers its own pod (its rack written for the mission): nothing to change.
    if d.kind=='pod'then return nil end
    -- A support pod, a sentry pod or an Eagle strike: the donor's own delivery.
    return {delivery=d.delivery.stratagem,client=entry.client==true}
end

local function start_capture(ctx,d)
    local world=world_module.open()
    local dl=delivery_of(d)
    local delivery_type=world and dl and loadout.type_of(world,dl.id)
    if not(ctx.beacon and ctx.beacon.network and delivery_type)then
        ctx:log('NO CAPTURE: the beacon\'s network id or the delivery type is unknown; the pod is vanilla')
        return
    end
    local spec={beacon_network=ctx.beacon.network,type=delivery_type,label=ctx.call_id}
    if d.kind=='sentry'then spec.content_type=d.delivery.content_type else spec.item_types=dl.item_types end
    local w,why=support_pods.capture(spec,function(e)
        if e.kind=='pod'then
            ctx.pod=e.pod
            ctx:associate(e.pod,'pod')
        elseif e.kind=='captured'and d.kind=='silo'then
            -- A silo: the pod's content is the silo itself (its rack); its items are the missile and the laser remote.
            local s=d.delivery
            ctx.items={}
            ctx:associate(e.rack,'silo')
            for k,entity in ipairs(e.items)do
                local role=e.types[k]==s.missile and'missile'or'remote'
                local ok,awhy=ctx:associate(entity,role)
                if ok then
                    ctx.items[#ctx.items+1]={entity=entity,kind=role,entity_type=e.types[k],network=e.networks and e.networks[k]}
                    if role=='missile'then ctx.missile,ctx.missile_network=entity,e.networks and e.networks[k]end
                else
                    ctx:log(('%s %d not associated: %s'):format(role,entity,tostring(awhy)))
                end
            end
            ctx:log(('DELIVERED: pod %d, silo %d: missile %s, remote %s (exactly this pod\'s; every other %s stays vanilla)')
                :format(e.pod,e.rack,tostring(ctx.missile),tostring((function()
                    for _,i in ipairs(ctx.items)do if i.kind=='remote'then return i.entity end end end)()),s.stratagem))
            if ctx.missile then
                -- Several players: the missile's network id to every compatible Runtime (the host watches its own copy
                -- and requests the blast for a client's call).
                if mission.mp and mission.mp.state=='running'then
                    local ok,pwhy=false,'its network id is unreadable'
                    if ctx.missile_network then
                        ok,pwhy=mp_items.own({id=d.id,call_id=ctx.call_id,beacon=ctx.beacon and ctx.beacon.network,
                            items={ctx.missile_network},entities={ctx.missile},roles={'payload'}})
                    end
                    ctx:log(ok and(('CUSTOM MP ITEMS: missile network id %d (call beacon network id %s) published to every '
                        ..'compatible Runtime: every machine requests its blast from its own copy'):format(ctx.missile_network,
                        tostring(ctx.beacon and ctx.beacon.network)))or('CUSTOM MP ITEMS NOT published (the other '
                        ..'machines cannot watch this missile: only this machine draws its blast): '..tostring(pwhy)))
                end
                local silos=require('hd2runtime/runtime/custom_silos')
                ctx.silo_watch=silos.watch({missile=ctx.missile,detonation=s.detonation,label=ctx.call_id},function(ev)
                    if ev.kind=='launched'then
                        ctx:log(('missile %d LAUNCHED (it left the silo at %s)'):format(ctx.missile,at(ev.position)))
                    elseif ev.kind=='gone'then
                        ctx:log(('missile %d ended before it left the silo: no blast'):format(ctx.missile))
                    elseif ev.kind=='detonated'then
                        local action,name=silos.blast(d,ev.position,ctx.call_id,ev.origin)
                        ctx:log(('missile %d DETONATED at %s (%s, %.1f s after its capture): %s'):format(ctx.missile,
                            at(ev.position),ev.via=='queue'and'its own detonation in the explosion queue'
                            or'inferred: the missile is gone',ev.seconds,action and(name..' explosion requested there on this machine ('
                            ..tostring(action.status)..')')or('no blast from this machine: '..tostring(name))))
                    end
                end)
            end
            ctx.state='delivered'
            run_callback(d,'on_delivered',ctx)
        elseif e.kind=='captured'and d.kind=='sentry'then
            local entity=e.content
            local ok,awhy=ctx:associate(entity,'sentry')
            if not ok then
                ctx:log(('sentry %d not associated: %s (it stays vanilla)'):format(entity,tostring(awhy)))
                return
            end
            ctx.sentry=setmetatable({entity=entity,call=ctx,entity_type=e.types and e.types[1],kind='sentry'},Weapon)
            ctx:log(('DELIVERED: pod %d: sentry %d (%s; exactly this pod\'s sentry; every other %s stays vanilla)')
                :format(e.pod,entity,tostring(e.types and e.types[1]),d.delivery.stratagem))
            if next(d.sentry.weapon)then ctx.sentry:configure(d.sentry.weapon)end
            -- Custom multiplayer: every other compatible Runtime gives its OWN copy of this sentry the same round and
            -- spread (each machine fires a turret's rounds from its own data); the machine that created it configures
            -- it whole (runtime/custom_weapons.lua roles).
            if next(d.sentry.weapon)and mission.mp and mission.mp.state=='running'then
                local net=world and world_module.entity_network(world,entity)
                local ok,pwhy=false,'its network id is unreadable'
                if net then
                    ok,pwhy=mp_items.own({id=d.id,call_id=ctx.call_id,beacon=ctx.beacon and ctx.beacon.network,items={net},
                        entities={entity},roles={'sentry'}})
                end
                ctx:log(ok and(('CUSTOM MP ITEMS: sentry network id %d (call beacon network id %s) published to every '
                    ..'compatible Runtime: each mirrors its weapon on its own copy'):format(net,tostring(ctx.beacon
                    and ctx.beacon.network)))or('CUSTOM MP ITEMS NOT published (the other machines see the sentry\'s '
                    ..'stock weapon): '..tostring(pwhy)))
            end
            local c=ctx.sentry:credit()
            ctx:log(('sentry %d credit: %s'):format(entity,c and require('hd2runtime/runtime/pelican_weapon').credit_text(c)
                or'(unreadable)'))
            ctx.state='delivered'
            run_callback(d,'on_delivered',ctx)
        elseif e.kind=='captured'then
            ctx.weapons,ctx.items={},{}
            for k,entity in ipairs(e.items)do
                local t=e.types and e.types[k]or dl.item
                local item=dl.items and dl.items[t]or{kind='weapon',projectile=dl.projectile}
                local ok,awhy=ctx:associate(entity,item.kind)
                if ok then
                    local obj=setmetatable({entity=entity,call=ctx,projectile=item.projectile,entity_type=t,kind=item.kind,
                        network=e.networks and e.networks[k]},Weapon)
                    ctx.items[#ctx.items+1]=obj
                    if item.kind=='weapon'then ctx.weapons[#ctx.weapons+1]=obj end
                else
                    ctx:log(('%s %d not associated: %s'):format(item.kind,entity,tostring(awhy)))
                end
            end
            ctx:log(('DELIVERED: pod %d, rack %d: weapons %s%s (exactly the rack\'s items; every other %s stays vanilla)')
                :format(e.pod,e.rack,table.concat((function()local o={};for _,x in ipairs(ctx.weapons)do o[#o+1]=x.entity end
                return o end)(),', '),(#ctx.items>#ctx.weapons)and(', other items '..table.concat((function()local o={}
                for _,x in ipairs(ctx.items)do if x.kind~='weapon'then o[#o+1]=x.kind..' '..x.entity end end
                return o end)(),', '))or'',dl.stratagem))
            if(mission.players or 1)>1 then
                local parts={}
                for _,obj in ipairs(ctx.items)do parts[#parts+1]=('%s %d (network id %s)'):format(obj.kind,obj.entity,
                    tostring(obj.network))end
                ctx:log(('%sCALL CAPTURED: pod %d (network id %s), rack %d (network id %s): %s; the other machines log '
                    ..'these network ids as REMOTE OBSERVED'):format(ctx.client and'CLIENT 'or'',e.pod,tostring(e.pod_network),
                    e.rack,tostring(e.rack_network),table.concat(parts,', ')))
            end
            -- A pod with a planned layout: each slot holds the item planned for it (the capture is the call's own rack).
            if dl.layout then
                local wrong={}
                for k,slot in ipairs(e.slots or{})do
                    if dl.layout[slot]~=(e.types and e.types[k])then
                        wrong[#wrong+1]=('slot %d holds %s, %s planned'):format(slot,tostring(e.types and e.types[k]),
                            tostring(dl.layout[slot]))
                    end
                end
                ctx.pod_layout=dl.layout
                ctx:log(#wrong==0 and(('POD: %d item%s, each in its planned slot (%d planned)'):format(#ctx.items,
                    #ctx.items==1 and''or's',dl.count or 0))or('POD LAYOUT differs: '..table.concat(wrong,'; ')))
            end
            -- The data-driven modifications, on each delivered weapon's own records (a pod item's own modify, else the
            -- delivery's).
            local mirrored={nets={},entities={}}
            for _,obj in ipairs(ctx.weapons)do
                local it=dl.items and dl.items[obj.entity_type]
                local modify=it and it.modify or dl.modify
                local impact=it and it.impact or dl.impact
                local rounds=it and it.rounds or dl.rounds
                local damage=it and it.damage or dl.damage
                if modify and next(modify)then obj:configure(modify)end
                if impact and obj:set_impact_explosion(impact,{rounds=rounds,data=true,damage=damage})
                    and obj.network then
                    mirrored.nets[#mirrored.nets+1]=obj.network
                    mirrored.entities[#mirrored.entities+1]=obj.entity
                end
            end
            -- Custom multiplayer: every other compatible Runtime converts its OWN copy of these launchers' rockets
            -- (runtime/custom_mp_items.lua): their network ids go into this machine's published state.
            if#mirrored.nets>0 and mission.mp and mission.mp.state=='running'then
                local ok,why=mp_items.own({id=d.id,call_id=ctx.call_id,beacon=ctx.beacon and ctx.beacon.network,
                    items=mirrored.nets,entities=mirrored.entities})
                if ok then
                    ctx:log(('CUSTOM MP ITEMS: launcher network ids %s (call beacon network id %s) published to every '
                        ..'compatible Runtime: each converts its own copy of their rockets, whoever fires them'):format(
                        table.concat(mirrored.nets,', '),tostring(ctx.beacon and ctx.beacon.network)))
                else
                    ctx:log('CUSTOM MP ITEMS NOT published (the other machines keep the vanilla rocket): '..tostring(why))
                end
            end
            ctx.state='delivered'
            run_callback(d,'on_delivered',ctx)
        elseif e.kind=='refused'then
            ctx:log(('CAPTURE REFUSED: %s: %s (the delivered weapons stay vanilla)'):format(tostring(e.code),
                tostring(e.reason)))
        end
    end)
    if not w then ctx:log('CAPTURE REFUSED: '..tostring(why))end
end

-- A custom Eagle call: its exact jet (the one first seen at this activation), then its rockets bound.
local function start_eagle(ctx,d,e)
    local eg=d.eagle
    local w,why=eagles.capture({activation=e.clock,beacon=e.entity,donor_type=e.type,resource=eg.jet,label=ctx.call_id},
        function(ev)
            if ev.kind=='captured'then
                local ok,awhy=ctx:associate(ev.jet,'eagle_jet')
                if not ok then ctx:log('jet '..ev.jet..' not associated: '..tostring(awhy));return end
                ctx.jet=ev.jet
                ctx:log(('DELIVERED: the %s jet %d (network id %d), first seen %.2f s after the activation; every other '
                    ..'%s stays vanilla'):format(eg.stratagem,ev.jet,ev.network,ev.seconds or 0,eg.stratagem))
                if eg.impact then
                    local binding,code,reason=eagles.bind_rockets({jet=ev.jet,network=ev.network,resource=ev.resource,
                        projectile=eg.projectile,donor=eg.impact,activation=e.clock,donor_type=e.type,beacon=e.entity,
                        label=ctx.call_id..' rockets',multiplayer=ctx.multiplayer==true},function(r)
                            if r.kind=='converted'then
                                ctx.converted=(ctx.converted or 0)+1
                            elseif r.kind=='refused'and r.first then
                                ctx:log(('a rocket stays vanilla: %s: %s'):format(tostring(r.code),tostring(r.reason)))
                            elseif r.kind=='pod'then
                                -- A pod mounted on the call's jet (its rockets' source): this call's, by the hierarchy.
                                local ok,awhy=ctx:associate(r.pod,'eagle_pod')
                                if not ok then ctx:log('pod '..r.pod..' not associated: '..tostring(awhy))end
                            elseif r.kind=='ended'then
                                ctx.payload_result=r
                                ctx:log(('PAYLOAD RESULT: %d rocket%s converted to %s\'s explosion, %d impact%s requested '
                                    ..'it%s'):format(r.converted,r.converted==1 and''or's',eg.impact,r.impacts_to,
                                    r.impacts_to==1 and''or's',r.proven and''or' (NOT PROVEN: the run was vanilla)'))
                            end
                        end)
                    if binding then
                        ctx.rockets=binding
                        ctx:log(('ROCKETS: projectiles %d of jet %d\'s mounted pods (owner this jet) explode as %s\'s on '
                            ..'impact (explosion %d instead of %d); their type, their row and every other projectile stay '
                            ..'vanilla'):format(eg.projectile,ev.jet,eg.impact,binding.to,binding.from))
                    else
                        ctx:log(('ROCKETS REFUSED: %s: %s (they stay vanilla)'):format(tostring(code),tostring(reason)))
                    end
                end
                ctx.state='delivered'
                run_callback(d,'on_delivered',ctx)
            elseif ev.kind=='refused'then
                ctx:log(('NO JET: %s: %s (the strike is the vanilla %s)'):format(tostring(ev.code),tostring(ev.reason),
                    eg.stratagem))
            end
        end)
    if not w then ctx:log('NO JET: '..tostring(why))end
end

-- A native custom orbital's call: its beacon's delivery became the donor's own barrage; the game creates that barrage
-- at the activation. The barrage watch (below) recognises it at its first shell and converts its shells on this
-- machine's own copies; this call only waits for it.
local function start_barrage(ctx,d)
    if ctx.barrage_entity then return end      -- already bound (its first shell was judged in the activation update)
    ctx.awaiting_barrage,ctx.awaiting_since=true,clock
    ctx:log(('BARRAGE: the native %s barrage of this call is recognised at its first shell (its carrier type, this '
        ..'machine\'s peer, its target at the beacon); its shells explode as %s\'s on every compatible machine\'s own '
        ..'copies'):format(d.orbital.pattern,d.orbital.impact))
end

-- THE BARRAGE WATCH (native custom orbitals, on every machine): one shell binding per donor barrage and impact donor
-- (runtime/projectile_impact.lua with an accept rule). The first shell of an unbound source asks the rule whether that
-- source is a custom call's barrage (runtime/custom_barrages.lua instance: the donor's payload; its carrier type maps to
-- this custom stratagem; then exactly one call matches):
--   * created here: this machine's own call of that id whose beacon is at the barrage's target, waiting for it;
--   * another machine's copy: a beacon of that id seen here whose thrown ball names the barrage's creator, at its
--     target, the creator's synced picks (frozen) selecting the id.
-- The source is then bound, and that shell (and every later one of it) converts on this machine's own copy, in the
-- same pass. A vanilla barrage (its own type, no custom carrier) or a barrage nothing matches stays vanilla.
local barrage_counts={}
local function barrage_line(source,text)
    local c=barrage_counts[source]
    if not c then return end
    if c.ctx then c.ctx:log('BARRAGE SHELLS: '..text)
    else
        log(('REMOTE CUSTOM BARRAGE: peer %s\'s custom %s barrage network id %s (entity %d here): %s'):format(c.peer,c.id,
            tostring(c.network),source,text))
    end
end
local function barrage_event(e)
    local c=e.source and barrage_counts[e.source]
    if e.kind=='converted'and c then
        c.n=c.n+1
        if c.n==1 then
            barrage_line(e.source,('CONVERTED its first shell (projectile %d, pool slot %d): impact explosion copy %d -> %d '
                ..'on this machine (creditor %s, the game\'s own); the next ones are counted'):format(e.type or 0,e.slot,
                e.from,e.to,tostring(e.creditor)))
        end
    elseif e.kind=='refused'and e.first and c then
        barrage_line(e.source,('a shell stays vanilla here: %s: %s'):format(tostring(e.code),tostring(e.reason)))
    elseif e.kind=='source_gone'and c then
        barrage_line(e.source,('ended: %d shell%s converted on this machine'):format(c.n,c.n==1 and''or's'))
        barrage_counts[e.source]=nil
    end
end
-- (the barrage association: one do-block keeps the main chunk under LuaJIT's 200 locals; only barrage_accept outside.)
local barrage_accept
do
    local function local_peer_hex_of(world)
        local lo,hi=world_module.local_peer(world)
        return lo and world_module.peer_hex(lo,hi)or nil
    end
    -- The barrage's CALL (r6). Live r5: the custom identity was right on both machines (the barrage's carrier type, the frozen
    -- carrier map), but the association to the call failed: BARRAGE NOT TAKEN ... matches 0 of its own calls at its target,
    -- and REMOTE CUSTOM BARRAGE NOT TAKEN ... matches 0 of its beacons seen here. Position (3 m) was the only discriminator.
    -- Now: the candidates are the calls of THAT custom id by THAT creator (this machine's own call, or another player's
    -- observed beacon whose caller is the barrage's creator: its thrown ball, else derived from the frozen table) that have no
    -- barrage yet and are recent (M.BARRAGE_WINDOW s); a structural field of the barrage naming its beacon (when the
    -- research proves one: inst.beacon_network) narrows them first. Exactly one candidate: bound (its distance only logged).
    -- Several: the one within barrages.TOLERANCE of the target, only if exactly one is; else refused (real ambiguity, never a
    -- guess). Each binding is one-to-one (a call or beacon takes one barrage). Nothing matching: retried on later shells for
    -- M.BARRAGE_RETRY s (the evidence may still be arriving), with one BARRAGE MATCH DEBUG block naming every candidate and
    -- why it was rejected. A vanilla barrage (its own type) is never a candidate's: its carrier type maps to no custom id.
    M.BARRAGE_WINDOW=60
    M.BARRAGE_RETRY=6
    local function barrage_candidates(world,inst,id,me)
        local out={}
        local target=inst.target
        local function add(c)
            c.distance=barrages.distance(target,c.at)
            out[#out+1]=c
        end
        if inst.created_here then
            for _,c in ipairs(mission.calls)do
                if c.definition==id then
                    local since=c.awaiting_since or c.beacon_clock
                    local x={kind='own',ctx=c,peer=me,network=c.beacon and c.beacon.network,at=c.landing or c.activation
                        or c.position or(c.beacon and beacon_at(world,c.beacon.entity)),age=since and(clock-since)or nil,id=id,
                        entity=c.beacon and c.beacon.entity}
                    if c.barrage_entity then x.reject=('already bound to barrage %d'):format(c.barrage_entity)
                    elseif inst.beacon_entity and x.entity~=inst.beacon_entity then
                        x.reject=('the barrage was dispatched by beacon %d (its exact beacon)'):format(inst.beacon_entity)
                    elseif not inst.beacon_entity and not(c.awaiting_barrage or(c.neutralized and c.beacon))then
                        x.reject='its beacon was never redirected to a native barrage'
                    elseif x.age and x.age>M.BARRAGE_WINDOW then x.reject=('its beacon is %.0f s old'):format(x.age)end
                    add(x)
                end
            end
        else
            for _,r in ipairs(mp_items.remote_beacons())do
                local ev=M.call_evidence and M.call_evidence(r.network)
                local caller=r.thrower or(ev and ev.thrower)
                local at=r.entity and(beacon_reader.beacons(world)or{})[r.entity]and beacon_at(world,r.entity)
                    or(ev and ev.position)or r.position
                local x={kind='remote',beacon=r,peer=caller,network=r.network,at=at,age=ev and ev.age or nil,id=r.id,
                    how=ev and ev.how}
                if r.id~=id then x.reject='a call of '..tostring(r.id)
                elseif caller==nil then x.reject='its caller is unknown (no thrown ball, not derivable)'
                elseif caller~=inst.creator then x.reject='its caller is '..caller..', not the barrage\'s creator'
                elseif(mission.barrage_bound or{})[r.network]then
                    x.reject=('already bound to barrage %d'):format(mission.barrage_bound[r.network])
                elseif x.age and x.age>M.BARRAGE_WINDOW then x.reject=('observed %.0f s ago'):format(x.age)end
                add(x)
            end
        end
        local eligible={}
        for _,x in ipairs(out)do if not x.reject then eligible[#eligible+1]=x end end
        if#eligible==1 then return eligible[1],out,inst.beacon_entity and'its exact beacon'or'the only one'end
        if#eligible>1 then
            local near={}
            for _,x in ipairs(eligible)do if x.distance<=barrages.TOLERANCE then near[#near+1]=x end end
            if#near==1 then return near[1],out,'the only one at its target'end
            for _,x in ipairs(eligible)do x.reject=('ambiguous: %d calls fit, %d at its target'):format(#eligible,#near)end
        end
        return nil,out,#eligible==0 and'no call fits'or'ambiguous'
    end
    local function barrage_debug(source,inst,id,me,list,why)
        log(('BARRAGE MATCH DEBUG: barrage %d (network id %s), creator %s (created here %s; this machine %s), carrier type %s '
            ..'-> %s, target %s, its beacon %s; %d candidate call%s; %s'):format(source,tostring(inst.network),
            tostring(inst.creator),tostring(inst.created_here),tostring(me),tostring(inst.carrier_type),tostring(id),
            at(inst.target),inst.beacon_entity and('entity '..inst.beacon_entity)or('not linked ('..tostring(inst.beacon_why
            or inst.association_why or'a copy: none')..')'),#list,#list==1 and''or's',why))
        for k,x in ipairs(list)do
            if k>8 then log('BARRAGE MATCH DEBUG:   ... '..(#list-8)..' more');break end
            log(('BARRAGE MATCH DEBUG:   %s call: peer %s, beacon network id %s, position %s, distance %s m, age %s s, custom '
                ..'%s%s: %s'):format(x.kind,tostring(x.peer),tostring(x.network),at(x.at),x.distance==math.huge and'?'
                or('%.1f'):format(x.distance),x.age and('%.1f'):format(x.age)or'?',tostring(x.id),x.how and(' (caller '..x.how
                ..')')or'',x.reject and('REJECTED: '..x.reject)or'eligible'))
        end
    end
    function barrage_accept(world,source,binding,group)
        mission.barrage_seen=mission.barrage_seen or{}
        local seen=mission.barrage_seen[source]
        if seen and(seen.done or clock<seen.next)then return end
        if not seen then seen={first=clock};mission.barrage_seen[source]=seen end
        seen.next=clock+0.5
        local inst=barrages.instance(world,source)
        if not(inst and inst.payload==group.payload)then seen.done=true;return end
        local id=mission.carrier_types and mission.carrier_types[inst.carrier_type]
        local d=id and defs[id]
        -- A vanilla barrage (its own type) or another custom stratagem's: never this group's.
        if not(d and group.ids[id])then seen.done=true;return end
        local me=local_peer_hex_of(world)
        if inst.created_here and inst.creator~=me then
            seen.done=true
            log(('BARRAGE NOT TAKEN: barrage %d was created here but names creator %s, not this machine (%s)'):format(source,
                tostring(inst.creator),tostring(me)))
            return
        end
        if not inst.created_here then
            if not(mission.mp and mission.mp.state=='running')then seen.done=true;return end
            local picks=mission.mp.view.table[inst.creator or'']
            local selected=false
            for slot=0,sync.SLOTS-1 do if picks and picks[slot]==id then selected=true end end
            if not selected then
                seen.done=true
                log(('REMOTE CUSTOM BARRAGE NOT TAKEN: barrage %d (network id %s) names creator %s, whose synced picks do not '
                    ..'select %s'):format(source,tostring(inst.network),tostring(inst.creator),id))
                return
            end
        end
        local pick,list,why=barrage_candidates(world,inst,id,me)
        if not pick then
            if not seen.debugged then seen.debugged=true;barrage_debug(source,inst,id,me,list,why)end
            if clock-seen.first>=M.BARRAGE_RETRY then
                seen.done=true
                local fit=0
                for _,x in ipairs(list)do if not x.reject or x.reject:find('^ambiguous')then fit=fit+1 end end
                if inst.created_here then
                    log(('BARRAGE NOT TAKEN: this machine\'s %s barrage %d matches %d of its own calls (%s; one is needed: '
                        ..'never a guess); its shells stay vanilla here'):format(id,source,fit,why))
                else
                    log(('REMOTE CUSTOM BARRAGE NOT TAKEN: barrage %d (network id %s) of %s matches %d of its beacons seen here '
                        ..'(%s; one is needed: never a guess)'):format(source,tostring(inst.network),tostring(inst.creator),fit,
                        why))
                end
            end
            return
        end
        local how,ctx,peer,beacon_network
        if pick.kind=='own'then
            ctx=pick.ctx
            peer,beacon_network,how=me,pick.network,'its own call '..ctx.call_id..' ('..why..')'
        else
            peer,beacon_network,how=inst.creator,pick.network,'derived from its beacon ('..why..')'
        end
        local ok,code,reason=binding.add_source(source,{how=how})
        if not ok then
            log(('BARRAGE NOT TAKEN: barrage %d: %s: %s'):format(source,tostring(code),tostring(reason)))
            return
        end
        seen.done=true
        if beacon_network then
            mission.barrage_bound=mission.barrage_bound or{}
            mission.barrage_bound[beacon_network]=source
        end
        barrage_counts[source]={n=0,ctx=ctx,peer=peer,id=id,network=inst.network}
        if ctx then
            ctx.barrage_entity,ctx.barrage_network,ctx.awaiting_barrage=source,inst.network,nil
            local okc,awhy=ctx:associate(source,'barrage')
            if not okc then ctx:log('barrage '..source..' not associated: '..tostring(awhy))end
            ctx:log(('DELIVERED: the native %s barrage, entity %d (network id %s), %s, its target %s m from the beacon; its '
                ..'shells (%s) explode as %s\'s on this machine\'s own copies; every other barrage stays vanilla'):format(
                d.orbital.pattern,source,tostring(inst.network),why,pick.distance==math.huge and'?'or('%.1f'):format(
                pick.distance),table.concat(d.orbital.shells,', '),d.orbital.impact))
            if mission.mp and mission.mp.state=='running'and inst.network then
                local pok,pwhy=mp_items.own({id=id,call_id=ctx.call_id,beacon=beacon_network,items={inst.network},
                    entities={source},roles={'barrage'}})
                ctx:log(pok and(('CUSTOM MP ITEMS: barrage network id %d (call beacon network id %s) published to every '
                    ..'compatible Runtime as a confirmation (each derives it itself)'):format(inst.network,tostring(beacon_network)))
                    or('CUSTOM MP ITEMS NOT published: '..tostring(pwhy)))
            end
            ctx.state='delivered'
            run_callback(d,'on_delivered',ctx)
        else
            mp_items.track(source,{peer=peer,caller=peer,id=id,beacon=beacon_network,network=inst.network,kind='barrage',
                binding=binding})
            log(('REMOTE CUSTOM BARRAGE: peer %s, custom %s, barrage network id %s (entity %d on this machine), call beacon '
                ..'network id %s: derived from its carrier type (%d), its creator and its call (%s; target %s m from that '
                ..'beacon); its shells (%s) explode as %s\'s on this machine\'s own copies'):format(peer,id,tostring(inst.network),
                source,tostring(beacon_network),inst.carrier_type,why,pick.distance==math.huge and'?'or('%.1f'):format(
                pick.distance),table.concat(d.orbital.shells,', '),d.orbital.impact))
        end
    end
end
-- The barrage watch, armed once the mission's carriers are known (and, with custom multiplayer, its setup ran): one per
-- donor group, ASSET-GATED. Live r4: the watch was refused at once (DONOR_NOT_RESIDENT: Orbital Gas Strike's call-in
-- package is not resident) and only afterwards was the synced id's package resident (CUSTOM MP ASSETS); the refusal was
-- final, so every shell of that mission exploded vanilla on that machine. Now a group whose donor is still loading
-- WAITS and is retried every step until it binds (WAITING, then ARMED, each logged once); only any other refusal is
-- final. A definition of a group is READY TO CALL only once its group's watch is armed (advance: 'barrage_watch'), so
-- the first shell after readiness converts.
-- (the barrage watch: one do-block keeps the main chunk under LuaJIT's 200 locals; only barrage_watch_step, barrage_watch_state outside.)
local barrage_watch_step,barrage_watch_state
do
    local function barrage_key(d)return d.orbital.payload..'|'..d.orbital.impact end
    function barrage_watch_step()
        if mission.barrage_watch_done or not mission.carrier_types then return end
        if mission.mp and mission.mp.state~='running'then return end
        if not mission.barrage_groups then
            local groups={}
            for _,d in ipairs(order)do
                if d.kind=='orbital'and d.orbital.native then
                    local key=barrage_key(d)
                    local g=groups[key]
                    if not g then
                        g={key=key,payload=d.orbital.payload,donor=d.orbital.impact,shells={},ids={},seen={},state='new'}
                        groups[key]=g
                    end
                    g.ids[d.id]=true
                    for _,t in ipairs(d.orbital.shells)do if not g.seen[t]then g.seen[t]=true;g.shells[#g.shells+1]=t end end
                end
            end
            mission.barrage_groups=groups
            mission.barrage_watch={}
            barrage_counts={}
        end
        local open=0
        for _,g in pairs(mission.barrage_groups)do
            if g.state=='new'or g.state=='waiting'then
                local binding
                local b_,code,reason=impacts.bind({sources={},projectiles=g.shells,donor=g.donor,rounds=64,max_sources=64,
                    label='custom native barrages ('..g.payload..')',multiplayer=true,client=mission.client==true,
                    provenance=true,accept=function(world,system,slot,source,owner)return barrage_accept(world,source,binding,g)
                    end},barrage_event)
                binding=b_
                if binding then
                    mission.barrage_watch[#mission.barrage_watch+1]=binding
                    log(('BARRAGE WATCH ARMED (%s barrages, shells exploding as %s\'s): %s%s'):format(g.payload,g.donor,
                        g.state=='waiting'and('its donor became resident after '..n1(mission.clock-g.since)..' s; ')or'',
                        'every later shell of a custom call of it converts on this machine'))
                    g.state='armed'
                elseif code=='DONOR_NOT_RESIDENT'or code=='UNAVAILABLE'then
                    -- Still loading (the definition's or the synced ids' packages were requested): retried next step.
                    if g.state~='waiting'then
                        g.state,g.since='waiting',mission.clock
                        log(('BARRAGE WATCH WAITING (%s barrages): %s: %s; retried every step until resident (its custom '
                            ..'stratagems are not READY TO CALL until it is armed)'):format(g.payload,tostring(code),
                            tostring(reason)))
                    end
                    open=open+1
                else
                    g.state,g.why='refused',tostring(code)..': '..tostring(reason)
                    log(('BARRAGE WATCH REFUSED (native custom barrages stay vanilla on this machine): %s'):format(g.why))
                end
            end
        end
        if open==0 then mission.barrage_watch_done=true end
    end
    -- The barrage watch of a definition's group: 'armed', 'waiting', 'refused' (and why), or nil (not started yet).
    function barrage_watch_state(d)
        local g=mission.barrage_groups and mission.barrage_groups[barrage_key(d)]
        if not g then return nil end
        return g.state=='new'and'waiting'or g.state,g.why
    end
end

-- A Pelican CAS call (the pelican family). This machine's own call: the host (or a solo player) spawns it here; a client
-- requests it from the session host (runtime/custom_mp_calls.lua: semantic call state only). host_pelican spawns it for
-- a call context whose caller may be another player (ctx.remote): its Pelican and chin turret are associated with that
-- call, its kills are meant for that caller, and with custom multiplayer their network ids are published so every
-- compatible Runtime mirrors the chin gun's private presentation on its own copy (runtime/custom_mp_items.lua).
local function host_pelican(ctx,d)
    local P=d.pelican
    local api=require('hd2runtime/api/pelican')
    local world=world_module.open()
    -- Its heading: from its caller's avatar toward the beacon (as the game faces a vehicle's Pelican from its thrower).
    local facing
    for _,pl in ipairs(world and world_module.players(world,true)or{})do
        if pl.peer==ctx.player_peer and pl.avatar then
            local unit=world_module.entity_unit(world,pl.avatar)
            local from=unit and world_module.unit_position(world,unit)
            if from and ctx.position then
                local dx,dy=ctx.position.x-from.x,ctx.position.y-from.y
                if math.sqrt(dx*dx+dy*dy)>=1 then facing={x=dx,y=dy}end
            end
        end
    end
    ctx.pelican_state={}
    local handle=api.spawn({owner=d.owner,position=ctx.position,hover=P.hover,orbit=P.orbit,gun=P.gun,
        approach=P.approach,credit_to=P.gun and ctx.player or nil,call=ctx,facing=facing,on_event=function(e)
            if e.kind=='spawned'then
                ctx.pelican_state.entity=e.result and e.result.entity
                ctx:log(('PELICAN: %d spawned on the host for %s; on its way to the beacon'):format(
                    tostring(ctx.pelican_state.entity),ctx.remote and('the requesting player '..tostring(ctx.player_peer))
                    or'this player'))
            elseif e.kind=='gun_armed'then
                ctx.pelican_state.turret=e.turret
                ctx:log(('PELICAN chin gun armed: turret %s, projectile %s (%s), %s RPM, credit %s'):format(tostring(e.turret),
                    tostring(e.projectile),tostring(e.round),e.rpm and('%.0f'):format(e.rpm)or'?',tostring(e.credit)))
                -- Every other compatible Runtime mirrors the gun's private presentation on its own copy.
                local w=world_module.open()
                local pnet=w and ctx.pelican_state.entity and world_module.entity_network(w,ctx.pelican_state.entity)
                local tnet=w and e.turret and world_module.entity_network(w,e.turret)
                if mission.mp and mission.mp.state=='running'then
                    if pnet and tnet and ctx.beacon and ctx.beacon.network then
                        local ok,why=mp_items.own({id=d.id,call_id=ctx.call_id,beacon=ctx.beacon.network,items={pnet,tnet},
                            entities={ctx.pelican_state.entity,e.turret},roles={'vehicle','turret'},parents={nil,pnet}})
                        ctx:log(ok and(('CUSTOM MP ITEMS: Pelican network id %d, chin turret network id %d (call beacon '
                            ..'network id %d) published: every compatible Runtime mirrors the chin gun on its own copy')
                            :format(pnet,tnet,ctx.beacon.network))or('CUSTOM MP ITEMS NOT published: '..tostring(why)))
                    else
                        ctx:log(('CUSTOM MP ITEMS NOT published (the other machines keep the stock chin gun): Pelican '
                            ..'network id %s, chin turret network id %s, beacon network id %s'):format(tostring(pnet),
                            tostring(tnet),tostring(ctx.beacon and ctx.beacon.network)))
                    end
                end
            elseif e.kind=='gun_refused'or e.kind=='refused'or e.kind=='unverified'then
                ctx:log(('PELICAN %s %s: %s: %s'):format(tostring(e.stage or''),e.kind,tostring(e.code),tostring(e.reason)))
            elseif e.kind=='gone'then
                ctx:log('PELICAN gone')
            end
        end})
    if handle.status=='refused'then
        ctx:log(('NO PELICAN: %s: %s'):format(tostring(handle.code),tostring(handle.reason)))
        return nil,tostring(handle.code)..': '..tostring(handle.reason)
    end
    ctx.pelican=handle
    return true
end
M.host_pelican=host_pelican
local function pelican_call(ctx,d)
    if not mission.client then return host_pelican(ctx,d)end
    -- A client: the session host spawns it (its synced slot, carrier map, sequence and beacon thrower checked there).
    local slot=ctx.slot or(ctx.ball and ctx.ball.slot)
    if slot==nil then
        for _,item in ipairs(mission.queue)do if item.definition==d and item.slots then slot=item.slots[1]end end
    end
    local r,why=mp_calls.request({id=d.id,beacon=ctx.beacon and ctx.beacon.network,slot=slot,
        carrier=mission.mp and mission.mp.carrier_hash},clock)
    if r then
        ctx.request=r
        -- The host publishes the Pelican it spawns for this call by this beacon: this machine knows the call (its own
        -- thrower) so it mirrors the chin gun on its own copy too.
        local world=world_module.open()
        local lo,hi
        if world then lo,hi=world_module.local_peer(world)end
        mp_items.remote_beacon(r.beacon,{id=d.id,entity=ctx.beacon and ctx.beacon.entity,position=ctx.position},clock,true)
        if lo then mp_items.thrower(r.beacon,world_module.peer_hex(lo,hi))end
        ctx:log(('CUSTOM MP CALL REQUESTED: the session host spawns the Pelican for this call (call seq %d, loadout slot %d, '
            ..'beacon network id %d, carrier map hash %s); this client owns its slot, cooldown and beacon'):format(r.seq,
            r.slot,r.beacon,r.carrier))
    else
        ctx:log('CUSTOM MP CALL NOT REQUESTED (nothing comes): '..tostring(why))
    end
end

local function beacon_event(e)
    if e.kind=='activated'then eagles.note_activation(e.type,e.entity,e.clock)end
    if e.kind=='created'then
        -- A carrier beacon with no state here is another machine's call (its thrower's Runtime runs it): reported, with
        -- several players, whatever this player selected (runtime/custom_multiplayer.lua).
        if e.beacon.landed==false and mission.carrier_types and mission.carrier_types[e.beacon.type]
                and(mission.players or 1)>1 then
            local world_r=world_module.open()
            if world_r then
                if mission.mp then M.mp_remote_beacon(world_r,e.beacon)
                else cmp.remote_beacon(world_r,e.beacon,mission.carrier_types)end
            end
        end
        local entry=mission.by_type[e.beacon.type]
        if not entry then return end
        local d,a=entry.definition,entry.assignment
        -- Only the thrower's machine holds a beacon's state (research beacon-redirect; the first-update change refuses
        -- another machine's copy, NOT_OWNED). A carrier is shared by custom stratagem id across a lobby, so a copy
        -- without state here is another player's call: never this player's, no context, no callback.
        local world0=world_module.open()
        local it0=world0 and(beacon_reader.beacons(world0)or{})[e.beacon.entity]
        if(it0 and it0.mode==nil)or e.beacon.landed==false then
            if log_module.sample('mp.remote_beacon',3)then log(('BEACON %d of the carrier %s is another machine\'s (no state here): another player\'s call, not this '
                ..'player\'s; ignored'):format(e.beacon.entity,a.carrier))end
            return
        end
        -- The call this beacon is: one already seen from the record (on_called), else a new one.
        local ctx
        for _,c in ipairs(mission.calls)do
            if c.definition==d.id and not c.beacon and c.state=='called'then ctx=c;break end
        end
        local fresh=not ctx
        ctx=ctx or new_call(d,a,nil)
        local world=world_module.open()
        local it=world and(beacon_reader.beacons(world)or{})[e.beacon.entity]
        local network=world and it and support_pods.beacon_network(world,it)
        ctx.beacon={entity=e.beacon.entity,network=network,type=e.beacon.type,timing=e.beacon.timing}
        ctx.beacon_clock=clock
        if ctx.custom_call then ctx.custom_call.beacon_network=network end
        ctx.state='beacon'
        mission.calls_by_beacon[e.beacon.entity]=ctx
        -- Its own delivery (a carrier pod, a condensed expendable): the carrier's own pod comes; no beacon write.
        if d.kind=='pod'or(d.kind=='expendable'and a.condensed)then
            ctx.neutralized=true
            ctx.own_delivery=true
            log(('%s: beacon %d delivers its carrier %s\'s OWN pod (no redirect, no beacon write)'):format(ctx.call_id,
                e.beacon.entity,a.carrier))
        end
        log(('%s: BEACON %d (the carrier %s\'s own beam; call-in %s s)%s'):format(ctx.call_id,e.beacon.entity,a.carrier,
            n1(e.beacon.timing and e.beacon.timing.call_in_time),ctx.slot and(' from loadout slot '..ctx.slot)or''))
        if(mission.players or 1)>1 and world then
            cmp.local_call(world,ctx)
            if ctx.client then
                ctx:log(('CLIENT CALL: beacon %d (network id %s) of the carrier %s is OWNED here (it has state: this '
                    ..'client runs its activation)'):format(e.beacon.entity,tostring(network),a.carrier))
            end
            if mission.mp then M.own_ball_line(world,ctx)end
        end
        if fresh then run_callback(d,'on_called',ctx)end
        run_callback(d,'on_beacon_created',ctx)
    elseif e.kind=='applied'then
        local ctx=mission.calls_by_beacon[e.entity]
        if not ctx then return end
        local r=e.result
        ctx.neutralized=true
        log(('%s: beacon %d delivery %s -> %s in its first update (%d write, verified %s)'):format(ctx.call_id,e.entity,
            tostring(r.delivery and r.delivery.from_name),tostring(r.delivery and r.delivery.to_name),r.writes or 0,
            tostring(r.verified)))
        if ctx.client then
            ctx:log(('CLIENT WRITE PROOF: beacon %d (network id %s): delivery %s -> %s, one guarded write on this client'
                ..'\'s own beacon'):format(e.entity,tostring(ctx.beacon and ctx.beacon.network),
                tostring(r.delivery and r.delivery.from_name),tostring(r.delivery and r.delivery.to_name)))
            if r.verified then
                ctx:log(('CLIENT WRITE VERIFIED: beacon %d reads back %s; the host logs what it sees of this call as '
                    ..'CUSTOM MP CALL and REMOTE OBSERVED'):format(e.entity,tostring(r.delivery and r.delivery.to_name)))
            end
        end
    elseif e.kind=='refused'then
        local ctx=e.entity and mission.calls_by_beacon[e.entity]
        if not ctx then return end
        ctx.refused=true
        log(('%s: beacon %d NOT CHANGED: %s: %s; the carrier\'s own delivery may execute; nothing custom is delivered')
            :format(ctx.call_id,e.entity,tostring(e.code),tostring(e.reason)))
    elseif e.kind=='activated'then
        local ctx=mission.calls_by_beacon[e.entity]
        if not ctx then return end
        local d=defs[ctx.definition]
        local world=world_module.open()
        ctx.activation=world and beacons.position(world,e.entity)
        ctx.position=ctx.landing or ctx.activation
        ctx.state='activated'
        if not ctx.neutralized then
            log(('%s: ACTIVATED without its delivery change: nothing custom'):format(ctx.call_id))
            return
        end
        log(('%s: ACTIVATED %s s after the beacon was first seen, at %s'):format(ctx.call_id,n1(e.seconds),at(ctx.position)))
        ensure_kill_watch()
        if d.kind=='eagle'then start_eagle(ctx,d,e)
        elseif d.kind=='orbital'and d.orbital.native then start_barrage(ctx,d)
        elseif d.kind=='pelican'then pelican_call(ctx,d)
        elseif d.delivery~='runtime'then start_capture(ctx,d)end
        if d.kind=='orbital'and not d.orbital.native then
            local o=d.orbital
            ctx:barrage({shell=o.shell,pattern=o.pattern,overrides=o.overrides,impact_explosion=o.impact})
        end
        run_callback(d,'on_activate',ctx)
    elseif e.kind=='gone'then
        local ctx=mission.calls_by_beacon[e.entity]
        if ctx then ctx.beacon_gone=true;mission.calls_by_beacon[e.entity]=nil end
    elseif e.kind=='ended'then
        vlog('beacon watch ended: '..tostring(e.reason))
    end
end

-- Every 0.1 s while a call is pending: the landing (its countdown started) and its position then.
local function landing_step()
    if not mission.on or not next(mission.calls_by_beacon)then return end
    local world=world_module.open()
    local list=world and beacon_reader.beacons(world)
    if not list then return end
    for entity,ctx in pairs(mission.calls_by_beacon)do
        local it=list[entity]
        if it and not ctx.landing and it.counting then
            ctx.landing=beacons.position(world,entity)
            if ctx.landing then
                ctx.position=ctx.landing
                log(('%s: LANDED at %s'):format(ctx.call_id,at(ctx.landing)))
                run_callback(defs[ctx.definition],'on_beacon_landed',ctx)
            end
        end
    end
end

-- Each custom stratagem of the mission, one at a time: checks, assets, presentation, cooldown, conversion.
local function refuse_definition(item,text)
    item.state='refused'
    log(('MISSION (%s): REFUSED: %s (nothing of it written; the mission goes on)'):format(item.definition.id,text))
    if carrier_presentation.applied(item.assignment and item.assignment.carrier)then
        carrier_presentation.restore(function(h)
            if h.status~='restored'then
                log(('MISSION (%s): presentation restore: %s: %s'):format(item.definition.id,tostring(h.code),
                    tostring(h.reason)))
            end
        end,item.assignment.carrier)
    end
    if mission.by_type[item.assignment and item.assignment.type or-1]==item then mission.by_type[item.assignment.type]=nil end
    cooldowns.disarm(item.definition.id)
end

local function cooldown_event(item)
    return function(e)
        local d=item.definition
        -- A definition with uses: this call's count, and the slot spent when it was the last.
        local uses=e.uses and(e.depleted and(' USES: %d of %d: SPENT for this mission (its cooldown outlasts the mission)')
            :format(e.calls,e.uses)or(' USES: %d of %d'):format(e.calls,e.uses))or''
        if e.kind=='overridden'then
            log(('%s: COOLDOWN %s s from the call-in\'s arrival (record entry %d; the carrier\'s own was %s s); verified %s%s')
                :format(d.id,n1(e.seconds),e.index,n1(e.gameEnd and e.arrival
                and(e.gameEnd-e.arrival)/1e6),tostring(e.verify and e.verify.finish and e.verify.others),uses))
        elseif e.kind=='call'then
            log(('%s: COOLDOWN the carrier\'s own (record entry %d);%s'):format(d.id,e.index,uses))
        elseif e.kind=='refused'and e.depleted then
            log(('%s: USES: %d of %d, but the slot could NOT be spent (the carrier\'s own cooldown applies, so it can be '
                ..'called again): %s: %s'):format(d.id,e.calls,e.uses,tostring(e.code),tostring(e.reason)))
        elseif e.kind=='refused'then
            log(('%s: COOLDOWN REFUSED for this call (the carrier\'s own applies): %s: %s'):format(item.definition.id,
                tostring(e.code),tostring(e.reason)))
        elseif e.kind=='ready'then
            vlog(item.definition.id..': cooldown over')
        end
    end
end

-- A definition's packages: every declared stratagem's and its delivery's call-in packages.
local function definition_deps(d)
    local deps={}
    for _,name in ipairs(d.assets)do
        for _,dep in ipairs(core_assets.dependencies_for_stratagem(stratagem_id(name),name)or{})do deps[#deps+1]=dep end
    end
    if d.delivery~='runtime'and d.delivery.id then
        for _,dep in ipairs(core_assets.dependencies_for_stratagem(d.delivery.id,d.delivery.stratagem)or{})do
            deps[#deps+1]=dep
        end
    end
    -- A pod's own items (their loadout packages: research carrier-pod-items section 3).
    for _,dep in ipairs(d.pod_deps or{})do deps[#deps+1]=dep end
    return deps
end
-- Whether a definition's payload is mirrored on every compatible Runtime (runtime/custom_mp_items.lua): a support
-- delivery whose delivered weapons take an impact explosion (the Gas EAT); a silo (the host watches every caller's
-- missile for its blast).
function M.mirrored(d)
    return type(d)=='table'and(((d.kind=='support'or d.kind=='expendable')and d.delivery~='runtime'
        and d.delivery.impact~=nil)or(d.kind=='orbital'and d.orbital~=nil and d.orbital.native==true)or d.kind=='pelican'
        or d.kind=='sentry'and d.sentry~=nil and next(d.sentry.weapon)~=nil or d.kind=='silo')
end

-- The carrier-in-slot probe, once its slots are adopted (h: the adoption's handle): its early lock released, then its
-- cooldown armed (the game counts its native uses itself, so no last-call cooldown), then READY.
function M.probe_ready(item,h)
    local d=item.definition
    require('hd2runtime/runtime/carrier_in_slot').release(world_module.open(),d.id)
    if d.cooldown or(d.uses and not h.native_uses)then
        local armed,why=cooldowns.arm({definition=d.id,seconds=d.cooldown,uses=not h.native_uses and d.uses or nil,
            from='arrival',carrier=item.assignment.carrier,multiplayer=true,client=item.client==true},cooldown_event(item))
        if not armed then log(('MISSION (%s): cooldown not armed (the carrier\'s own applies): %s'):format(d.id,
            tostring(why)))end
    end
    if h.native_uses then
        log(('MISSION (%s): NATIVE USES: %d per slot, counted down by the game (its HUD counter, its depleted look, its '
            ..'refusal at 0)'):format(d.id,h.native_uses))
    end
end
local function advance(world,item)
    local d,a=item.definition,item.assignment
    if item.state=='checks'then
        local conflicts=record_conflicts(world,d,a.type)
        if conflicts==nil then return refuse_definition(item,'the mission record is unreadable for the code check')end
        if#conflicts>0 then
            local out={}
            for _,c in ipairs(conflicts)do out[#out+1]=c.text end
            return refuse_definition(item,'its code '..d.code_text..' collides with '..table.concat(out,'; '))
        end
        local native=native_conflicts(world,d,a.stable_id)
        if#native>0 then return refuse_definition(item,'its code collides with '..table.concat(native,'; '))end
        -- The assets: every declared stratagem's and the delivery's call-in packages.
        local deps=definition_deps(d)
        -- A carrier pod: its carrier's own call-in packages too (its rack is written before the slot conversion loads
        -- them; every package a pod item references must be resident first).
        if d.kind=='pod'then
            for _,dep in ipairs(core_assets.dependencies_for_stratagem(a.stable_id,a.carrier)or{})do deps[#deps+1]=dep end
        end
        item.gate=core_assets.gate(world.runtime,{id='custom-stratagem-'..d.id,asset_dependencies=deps},
            log_module.emit)
        item.state='assets'
        item.waited=0
        return
    end
    if item.state=='assets'then
        local result,why=item.gate.tick(M.STEP)
        item.waited=item.waited+M.STEP
        if result=='failed'or(result~='ready'and item.waited>(d.asset_timeout or M.ASSET_TIMEOUT))then
            return refuse_definition(item,'its assets did not load: '..tostring(why or'timeout'))
        end
        if result~='ready'then return end
        -- An expendable custom stratagem: its carrier weapon is the donor (and its pod row presents as it) first.
        if d.kind=='expendable'then item.state='clone';return end
        -- A carrier pod: its carrier's own rack holds the pod items first.
        if d.kind=='pod'then item.state='pod_rack';return end
        -- A native custom orbital: its group's barrage watch armed first (its shells' donor resident here).
        if d.kind=='orbital'and d.orbital and d.orbital.native then item.state='barrage_watch';item.waited=0;return end
        item.state='presenting'
    end
    if item.state=='barrage_watch'then
        local state,why=barrage_watch_state(d)
        if state=='refused'then
            return refuse_definition(item,'its barrage watch was refused (its shells would explode vanilla): '..tostring(why))
        end
        if state~='armed'then
            item.waited=item.waited+M.STEP
            if item.waited>M.ASSET_TIMEOUT then
                return refuse_definition(item,('its barrage watch was not armed within %d s (its shells\' donor %s is not '
                    ..'resident here)'):format(M.ASSET_TIMEOUT,d.orbital.impact))
            end
            if not item.said_watch then
                item.said_watch=true
                log(('MISSION (%s): NOT READY: waiting for its barrage watch (%s\'s package resident here) before its slot '
                    ..'converts'):format(d.id,d.orbital.impact))
            end
            return
        end
        item.state='presenting'
    end
    if item.state=='pod_rack'then
        item.state='pod_writing'
        carrier_pod.apply({carrier=a.carrier,items=pod_units(d.delivery.pod),label=d.id},function(h)
            if h.status~='applied'then
                return refuse_definition(item,'its carrier pod was refused: '..tostring(h.code)..': '..tostring(h.reason))
            end
            local layout={}
            for _,l in ipairs(h.layout or{})do layout[l.slot]=hex_of(l.resource)end
            mission.pods[d.id]={rack=h,delivery={kind='pod',stratagem=a.carrier,id=a.stable_id,items=d.delivery.items,
                item_types=d.delivery.item_types,count=d.delivery.count,layout=layout,family='support'}}
            log(('MISSION (%s): its carrier %s\'s OWN pod holds %s for this mission (%d slot%s written)'):format(d.id,
                a.carrier,pod_text(d.delivery.pod),h.slots or 0,(h.slots or 0)==1 and''or's'))
            item.state='pod_done'
        end)
        return
    end
    if item.state=='pod_done'then item.state='presenting'end
    if item.state=='clone'then
        local c=mission.clones[d.id]
        if not c then return refuse_definition(item,'its carrier weapon was not allocated')end
        if c.state=='refused'then
            return refuse_definition(item,('its carrier weapon %s could not become the %s: %s'):format(c.weapon.weapon,
                d.delivery.donor,tostring(c.why)))
        end
        if c.state~='ready'then return end
        item.state='presenting'
    end
    if item.state=='presenting'then
        -- (The job runs from here; the tick never advances an item in 'presenting'.)
        mission.by_type[a.type]=item
        -- The carrier-in-slot probe: the presentation applied early (the loading screen, or before the HUD) is kept.
        if d.selection=='carrier'then
            local probe=require('hd2runtime/runtime/carrier_in_slot')
            if probe.waiting(d.id)then return end
            if probe.early(d.id,a.carrier)then
                log(('MISSION (%s): its presentation on %s was applied early (the carrier-in-slot probe): kept'):format(
                    d.id,a.carrier))
                item.state='arming'
                return
            end
        end
        carrier_presentation.apply({carrier=a.carrier,text=d.texts,icon=d.icon,code=d.code,
            uses=d.eagle and d.eagle.uses or nil},function(h)
            if h.status=='applied'then
                item.state='arming'
            else
                refuse_definition(item,'its carrier presentation was refused: '..tostring(h.code)..': '..tostring(h.reason))
            end
        end)
        return
    end
    if item.state=='arming'then
        -- The carrier-in-slot probe: its slots already hold the carrier: verified and adopted, nothing written but its
        -- native uses; its cooldown is armed after the adoption and the release of its early lock (M.probe_ready).
        local reconvert=item.reconvert
        local adopt=d.selection=='carrier'and not reconvert
            and require('hd2runtime/runtime/carrier_in_slot').slots_by_definition(selector.virtual_slots())[d.id]~=nil
        if(d.cooldown or d.uses)and not adopt and not reconvert then
            local armed,why=cooldowns.arm({definition=d.id,seconds=d.cooldown,uses=d.uses,from='arrival',carrier=a.carrier,
                multiplayer=true,client=item.client==true},cooldown_event(item))
            if not armed then log(('MISSION (%s): cooldown not armed (the carrier\'s own applies): %s'):format(d.id,
                tostring(why)))end
        end
        item.state='converting'
        local convert=adopt and selector.adopt_virtual or reconvert and selector.reconvert_virtual
            or selector.convert_virtual
        convert(d.id,function(h)
            if h.status=='converted'then
                -- The fallback's lock follows the swapped type (its end is untouched by the conversion).
                if reconvert then require('hd2runtime/runtime/carrier_in_slot').retype(d.id,h.carrier)end
                if adopt or reconvert then M.probe_ready(item,h)end
                item.state='ready'
                item.indices=h.indices
                if item.client then
                    log(('MISSION (%s): CLIENT WRITE VERIFIED: this client\'s own record entr%s %s now hold%s the carrier '
                        ..'%s (loadout slot%s %s)'):format(d.id,#(h.indices or{})==1 and'y'or'ies',
                        table.concat(h.indices or{},', '),#(h.indices or{})==1 and's'or'',a.carrier,
                        #h.slots==1 and''or's',table.concat(h.slots,', ')))
                end
                if d.eagle then
                    -- The jet tracker, before any call; the slot's uses (the game's rearm with a real Eagle, else the
                    -- Runtime's).
                    eagles.arm()
                    item.eagle_armed=true
                    item.uses_watch=eagles.uses_watch({definition=d.id,carrier_type=a.type,uses=d.eagle.uses,
                        seconds=d.eagle.rearm_seconds,label=d.id})
                end
                log(('MISSION (%s): READY TO CALL: loadout slot%s %s = %s, presenting as %s; code %s; delivery %s'):format(
                    d.id,#h.slots==1 and''or's',table.concat(h.slots,', '),a.carrier,d.label,d.code_text,
                    d.kind=='eagle'and(('the %s strike, %d uses per rearm'):format(d.eagle.stratagem,d.eagle.uses))
                    or d.kind=='orbital'and'a Runtime bombardment'
                    or d.delivery=='runtime'and'by the mod'or d.kind=='expendable'and(('the %s pod: the %s clone%s%s')
                    :format(tostring(delivery_of(d)and delivery_of(d).stratagem),d.delivery.donor,d.delivery.pod and
                    (' ('..pod_text(d.delivery.pod)..')')or'',a.condensed and'; CONDENSED: its own beacon, no redirect'
                    or''))
                    or d.kind=='pod'and(('its carrier %s\'s own pod: %s'):format(a.carrier,pod_text(d.delivery.pod)))
                    or('the vanilla '..d.delivery.stratagem..' pod')))
            else
                refuse_definition(item,'the slot conversion was refused: '..tostring(h.code)..': '..tostring(h.reason))
            end
        end,a.carrier,adopt and{uses=d.uses,client=item.client==true}or reconvert and{multiplayer=true,
            client=item.client==true}
            or{uses=d.eagle and d.eagle.uses or nil,multiplayer=true,client=item.client==true})
        return
    end
end

---------------------------------------------------------------- several players: the synced mission start --
-- With custom multiplayer enabled (runtime/custom_mp_sync.lua) the mission starts in three steps, each re-checked every
-- Runtime step:
--   1. 'records': every lobby member's stratagem record (as first seen) is here; the native picks are computed from them
--      and the synced table (custom_mp_sync.native_present: the same on every machine), and ONE carrier is allocated per
--      custom id the table selects (same id: one carrier; another id: another carrier; a native pick anywhere: never a
--      carrier). Every custom slot's record entry is checked: the token or its id's carrier, else CUSTOM MP DESYNC;
--   2. the session host publishes the table and carrier hashes and runs its own custom stratagems as before; a client
--      waits for the host's hashes ('agreement'): equal, it runs the client-write proof; different, nothing runs;
--   3. 'running': this machine's own custom stratagems go through their steps (a client: the families in
--      runtime/multiplayer.lua CLIENT_FAMILIES only, the Gas EAT proof).
-- FAIL CLOSED (0.30 release rule, the user's): with any lobby member running another custom stratagem registry or
-- Runtime version (or naming ids not registered here), custom stratagems are DISABLED lobby-wide: no carrier is
-- allocated or frozen, no token converted, no custom call run, no provenance published; vanilla gameplay is untouched.
-- The full registry hash stays the compatibility contract (no partial or intersection compatibility). The reason (or
-- nil): the view's incompatible members (runtime/custom_mp_sync.lua).
function M.disabled_reason(v)
    local list=v and v.incompatible
    if not(list and#list>0)then return nil end
    local parts={}
    for _,x in ipairs(list)do parts[#parts+1]=x.peer..': '..x.reason end
    return 'CUSTOM STRATAGEMS DISABLED: incompatible custom-stratagem mods detected ('..table.concat(parts,'; ')
        ..'). All players must use the same custom stratagems and versions'
end
-- The on-screen warning (the safety notice panel; its own repeat rule).
function M.disabled_notice(advice)
    local ok,safety=pcall(require,'hd2runtime/runtime/matchmaking_safety')
    if ok and type(safety)=='table'and safety.notice then
        pcall(safety.notice,'CUSTOM STRATAGEMS DISABLED','Incompatible custom-stratagem mods detected.',
            'All players must use the same custom stratagems and versions.',advice or
            'Custom stratagems are unavailable; vanilla gameplay is unaffected.')
    end
end
-- Every custom slot of this machine that will NOT run in this mission is LOCKED: its token (Orbital Precision Strike)
-- is never called (runtime/slot_cooldown.lua lock: its own entry unavailable all mission; the client's write carries the
-- lockout mark, runtime/multiplayer.lua). A carrier slot (the carrier-in-slot probe) is locked the same way on its own
-- entry holding its own carrier (the entry by loadout position, its type checked: never another slot holding the same
-- stratagem). only: {[custom id] = true} or nil (every virtual slot). Returns the slots locked now.
local fail_closed
do
    function fail_closed(world,reason,only)
        local set=selector.virtual_slots()
        if not(world and set)then return 0 end
        local record=slots.local_record(world)
        if not record then
            log(('CUSTOM STRATAGEM LOCK FAILED: the stratagem record is unreadable: DO NOT CALL your custom stratagem '
                ..'slots in this mission (each would call the native %s). Why they do not run: %s'):format(M.TOKEN,
                tostring(reason)))
            M.disabled_notice('DO NOT call your custom slots: they would call '..M.TOKEN..'.')
            return 0
        end
        -- Loadout slot -> record entry (the granted mission defaults hold no slot).
        local list={}
        for _,e in ipairs(record.entries)do list[#list+1]=e end
        table.sort(list,function(a,c)return a.index<c.index end)
        local entry_of,n={},0
        for _,e in ipairs(list)do if e.granted==0 then entry_of[n]=e.index;n=n+1 end end
        local token=mission.token_type or loadout.type_of(world,stratagem_id(M.TOKEN))
        mission.locked=mission.locked or{}
        mp.enable_lockout(true)
        local count=0
        for slot,v in pairs(set.slots)do
            if(not only or only[v.definition])and not mission.locked[slot]then
                local index=entry_of[slot]
                local said=false
                local native=v.carrier and(names_by_id[v.token]or('stable id '..tostring(v.token)))or M.TOKEN
                local what=v.carrier and('its carrier '..native..' itself (the carrier-in-slot probe)')
                    or('its token '..M.TOKEN)
                mission.locked[slot]=cooldowns.lock({index=index or-1,token=v.carrier and v.type or token,
                    client='lockout',label=v.definition},function(e)
                        if(e.kind=='locked'or e.kind=='held')and not said then
                            said=true
                            log(('CUSTOM STRATAGEM LOCKED: loadout slot %d (%s): %s (record entry %d) is unavailable '
                                ..'for this mission and is never called (its own cooldown end %s far ahead, re-applied; '
                                ..'verified %s). Why it does not run: %s'):format(slot,v.definition,what,e.index,
                                e.kind=='held'and'already held'or'set',tostring(e.verified),tostring(reason)))
                        elseif e.kind=='refused'and said~='refused'then
                            said='refused'
                            log(('CUSTOM STRATAGEM LOCK FAILED: loadout slot %d (%s): %s: %s. DO NOT CALL loadout slot %d in '
                                ..'this mission: it would call the native %s'):format(slot,v.definition,tostring(e.code),
                                tostring(e.reason),slot,native))
                            M.disabled_notice(('DO NOT call loadout slot %d: it would call %s.'):format(slot+1,native))
                        end
                    end)
                count=count+1
            end
        end
        return count
    end
end
-- Every custom slot of this machine that will NOT run in this mission, loudly, and LOCKED (fail closed): its token is
-- never called.
local function setup_refused(text,by)
    local only={}
    for id,list_slots in pairs(by or{})do
        only[id]=true
        for _,slot in ipairs(list_slots)do
            local v=(selector.virtual_slots()or{slots={}}).slots[slot]
            log(('CUSTOM MP SETUP REFUSED: loadout slot %d (%s) is UNAVAILABLE in this mission: %s. It was not converted: '
                ..'%s is LOCKED for this mission (never called)'):format(slot,id,text,v and v.carrier
                and('its carrier '..(names_by_id[v.token]or tostring(v.token))..' itself')or('its token '..M.TOKEN)))
        end
    end
    if next(only)then fail_closed(world_module.open(),text,only)end
end
M.setup_refused=setup_refused
local function mp_refuse(text)
    mission.mp.state='refused'
    mp.enable_client_proof(false)
    log('MISSION: custom multiplayer REFUSED on this machine: '..text..' (nothing of it written; vanilla gameplay '
        ..'continues)')
    setup_refused(text,mission.mp.by)
end
local function mp_queue(world,role)
    local m=mission.mp
    local a=mission.allocation
    mission.client=role=='client'
    if role=='client'then mp.enable_client_proof(true)end
    for _,id in ipairs(a.order)do
        local d=defs[id]
        local assignment=a.assignments[id]
        if not m.by[id]then
            -- Another player's custom stratagem (its carrier is reserved for it lobby-wide).
        elseif not assignment then
            log(('MISSION (%s): REFUSED: %s'):format(id,tostring(a.refused[id])))
        elseif d.kind=='pod'then
            log(('MISSION (%s): REFUSED: a carrier pod (the support_pod group) runs solo host only in this build; your '
                ..'slot stays the token %s'):format(id,M.TOKEN))
            setup_refused('a carrier pod runs solo host only',{[id]=m.by[id]})
        elseif role=='client'and not mp.client_family(d)then
            log(('MISSION (%s): REFUSED on this client: client execution of the %s family is not enabled in this proof '
                ..'build (support, expendable and sentry deliveries, native orbitals and host-spawned Pelicans only); your '
                ..'slot stays the token %s')
                :format(id,mp.family_name(d),M.TOKEN))
            setup_refused('client execution of the '..mp.family_name(d)..' family is not enabled in this proof build',
                {[id]=m.by[id]})
        elseif m.desynced[id]then
            log(('MISSION (%s): REFUSED: %s'):format(id,m.desynced[id]))
            setup_refused(m.desynced[id],{[id]=m.by[id]})
        else
            mission.queue[#mission.queue+1]={definition=d,assignment=assignment,state='checks',slots=m.by[id],
                client=role=='client'}
        end
    end
    m.state='running'
    -- Every expendable custom stratagem the synced lobby selects (any player's): its carrier weapon is the clone on this
    -- machine too, converted from the same definition and the same allocation (after the agreement on a client).
    for _,id in ipairs(sync.table_ids(m.view.table))do
        local d=defs[id]
        if d and d.kind=='expendable'then
            add_clone(d,a.assignments[id]or(a.weapons_kept and a.weapons_kept[id]and{weapon=a.weapons_kept[id]}))
        end
    end
    -- Every custom id the synced lobby selects (any player's): its declared assets on this machine too.
    for _,id in ipairs(sync.table_ids(m.view.table))do
        local d=defs[id]
        if d and not mission.remote_assets[id]then
            mission.remote_assets[id]={state='loading',waited=0,deps=definition_deps(d),
                gate=core_assets.gate(world.runtime,{id='custom-mp-'..id,asset_dependencies=definition_deps(d)},
                log_module.emit)}
        end
    end
end
-- Custom multiplayer: each custom id the synced lobby selects is resident on this machine whoever selected it: another
-- player's call of it shows here (its delivered items, its payload's explosion and cloud), and a mirrored payload is
-- converted here on this machine's own copies (runtime/custom_mp_items.lua). Only the synced selection is requested,
-- never every registered id; like every Runtime package reference it is kept for the session (core/assets.lua).
local function remote_assets_step()
    for id,r in pairs(mission.remote_assets)do
        if r.state=='loading'then
            local result,why=r.gate.tick(M.STEP)
            r.waited=r.waited+M.STEP
            if result=='ready'then
                r.state='ready'
                local names={}
                for k,dep in ipairs(r.deps)do names[k]=tostring(dep.name)end
                log(('CUSTOM MP ASSETS: %s resident for remote presentation/payload (%d package%s: %s)'):format(id,#names,
                    #names==1 and''or's',#names>0 and table.concat(names,'; ')or'none'))
            elseif result=='failed'or r.waited>((defs[id]or{}).asset_timeout or M.ASSET_TIMEOUT)then
                r.state,r.why='failed',tostring(why or'timeout')
                log(('CUSTOM MP ASSETS: %s NOT resident (%s): another player\'s call of it may look vanilla here, and its '
                    ..'payload is not mirrored on this machine'):format(id,r.why))
            end
        end
    end
end
local function mp_step(world)
    local m=mission.mp
    if m.state=='records'then
        local v=m.view
        local records=cmp.first_records()
        local have={}
        for _,r in ipairs(records)do have[r.peer]=true end
        local missing={}
        for peer in pairs(v.table)do if not have[peer]then missing[#missing+1]=peer end end
        table.sort(missing)
        if#missing>0 then
            if mission.clock-m.since>M.RECORDS_TIMEOUT then
                return mp_refuse('no stratagem record of '..table.concat(missing,', ')..' after '..M.RECORDS_TIMEOUT..' s')
            end
            return
        end
        local present,custom=sync.native_present(records,v.table,function(kind)return loadout.id_of(world,kind)end)
        local ids=sync.table_ids(v.table)
        local who={}
        for _,r in ipairs(records)do
            for _,e in ipairs(r.entries or{})do
                local sid=loadout.id_of(world,e.type)
                if sid then
                    who[sid]=who[sid]or{}
                    local tag=r.peer==v.local_peer and'your loadout'or('peer '..tostring(r.peer))
                    local l,seen=who[sid],false
                    for _,x in ipairs(l)do seen=seen or x==tag end
                    if not seen then l[#l+1]=tag end
                end
            end
        end
        -- r41: a carrier-mode id keeps the carrier its slots hold (the lowest peer's holder's): every machine reads the
        -- same first-seen records, so the map follows the slots, and only a real conflict (that carrier a native pick)
        -- maps it elsewhere.
        local mpins=M.mission_pins(world,custom,mission.token_type)
        local a,why=allocate(world,present,m.list,'at mission start, custom multiplayer: the synced lobby table and every '
            ..'player\'s record as first seen',ids,who,nil,mpins)
        if not a then return mp_refuse('the carriers cannot be allocated: '..tostring(why))end
        mission.allocation=a
        freeze_carriers(a,'custom multiplayer, mission start')
        local map,hash,text=carrier_map(a,ids)
        m.table_hash,m.carrier_hash,m.map=v.table_hash,hash,map
        log(('CUSTOM MP CARRIERS (mission start; table hash %s): %s; carrier hash %s; one carrier per custom id, shared by '
            ..'every slot and player selecting it'):format(v.table_hash,text,hash))
        -- Every custom slot's record entry: the token, or its own id's carrier (a faster peer converted it).
        m.desynced={}
        for _,c in ipairs(custom)do
            local x=a.assignments[c.id]
            if c.type~=mission.token_type and not(x and c.type==x.type)then
                local you=c.peer==v.local_peer
                log(('CUSTOM MP DESYNC: %s%s loadout slot %d: the synced picks say %s, but its record entry %d holds %s '
                    ..'(neither the token %s nor %s\'s carrier)%s'):format(c.peer,you and' (you)'or'',c.slot,c.id,c.index,
                    cmp.name_of(world,c.type),M.TOKEN,c.id,you and': that custom stratagem does not run here until '
                    ..'consistent'or': this machine runs nothing of that player\'s calls in any case'))
                if you then m.desynced[c.id]=('loadout slot %d is DESYNCED (record entry %d holds %s)'):format(c.slot,
                    c.index,cmp.name_of(world,c.type))end
            end
        end
        if m.game.host==true then
            mpstate.host={table=v.table_hash,carrier=hash}
            log(('CUSTOM MP AGREEMENT (mission start): this machine is the session host: it publishes table hash %s and '
                ..'carrier hash %s; every client compares its own'):format(v.table_hash,hash))
            return mp_queue(world,'host')
        end
        m.state,m.since='agreement',mission.clock
    end
    if m.state=='agreement'then
        local ag=sync.agreement(sync.view(),m.table_hash,m.carrier_hash)
        if ag.status=='agree'then
            log(('CUSTOM MP AGREEMENT (mission start): table hash %s, carrier hash %s: this client agrees with the '
                ..'session host %s; the client-write proof runs (support deliveries, native orbitals and host-spawned '
                ..'Pelican requests)'):format(m.table_hash,
                m.carrier_hash,tostring(m.view.host_peer)))
            return mp_queue(world,'client')
        elseif ag.status=='differ'then
            return mp_refuse(('the %s hash differs from the session host\'s (mine %s, the host\'s %s): the lobby\'s '
                ..'states or mod sets differ'):format(ag.field,tostring(ag.mine),tostring(ag.host)))
        elseif ag.status=='unavailable'then
            return mp_refuse('custom multiplayer is no longer enabled: '..tostring(sync.view()and sync.view().reason))
        elseif mission.clock-m.since>M.AGREEMENT_TIMEOUT then
            return mp_refuse('the session host published no matching hashes within '..M.AGREEMENT_TIMEOUT..' s')
        end
    end
end
-- (other machines' calls: one do-block keeps the main chunk under LuaJIT's 200 locals; only ball_thrower, ball_scan, call_evidence, pending_step outside.)
local ball_thrower,ball_scan,call_evidence,pending_step
do
    -- A carrier beacon's thrower, from its thrown ball (runtime/call_ins.lua): a custom slot's record entry here may still
    -- hold the token while its owner's converted entry threw the carrier. The synced table: the mission's frozen one (else
    -- the current view's).
    local function ball_accept(peer,slot,entry_type,ball_type)
        local t=mission.mp and mission.mp.view and mission.mp.view.table
        if not t then local v=sync.view();t=v and v.table end
        local picks=t and t[peer]
        return slot~=nil and entry_type==mission.token_type and picks~=nil and picks[slot]~=nil and picks[slot]~=false
            and mission.carrier_types~=nil and mission.carrier_types[ball_type]==picks[slot]
    end
    function ball_thrower(world,network)
        return call_ins.thrower(world,network,slots.records(world),ball_accept)
    end
    local function local_peer_hex(world)
        local lo,hi=world_module.local_peer(world)
        return lo and world_module.peer_hex(lo,hi)or nil
    end
    -- One thrown ball of another machine's call, cached as this machine's own evidence of it (runtime/custom_mp_evidence.lua).
    local function ball_evidence(world,network,id,t)
        local known=evidence.get(network,clock)
        local e=evidence.observe(network,{id=id,type=t.type,carrier=loadout.id_of(world,t.type),peer=t.peer,entry=t.entry,
            slot=t.slot,source='ball'},clock)
        mp_items.thrower(network,t.peer)
        if e and not(known and known.peer==t.peer)then
            if log_module.sample('mp.evidence',3)then log(('CUSTOM MP EVIDENCE: beacon network id %d: peer %s\'s thrown ball (record entry %d, loadout slot %s), carrier '
                ..'%s -> custom %s by the frozen carrier map; kept %d s as this machine\'s own evidence of that call'):format(
                network,t.peer,t.entry,tostring(t.slot),cmp.name_of(world,t.type),tostring(id),evidence.KEEP))end
        end
        return e
    end
    -- Every M.BALL_SCAN s of a mission with custom multiplayer running: every other player's thrown ball that names the
    -- beacon of a frozen carrier (its type maps to one custom id) is cached as evidence of that call. A ball lives only
    -- around its landing; its evidence outlives it for the slower lobby messages about that call (a host-call request).
    M.BALL_SCAN=0.1
    function ball_scan(world)
        if not mission.carrier_types then return end
        local balls=call_ins.balls(world)
        if not balls then return end
        local me=local_peer_hex(world)
        local records
        for _,ball in ipairs(balls)do
            local network,id=ball.beacon_network,mission.carrier_types[ball.type]
            if id and ball.owner~=me and network and network>0 and network~=call_ins.NO_NETWORK then
                local known=evidence.get(network,clock)
                if not(known and known.peer==ball.owner and known.entry==ball.entry)then
                    records=records or slots.records(world)
                    local t=call_ins.resolve(ball,records,ball_accept)
                    if t then ball_evidence(world,network,id,t)end
                end
            end
        end
    end
    -- The native evidence of another machine's call by its beacon's network id, merged with what custom_mp_items holds:
    -- {id, entity, position, thrower, how ('ball' | 'derived'), slot, age}, or nil and why. The caller is derived from the
    -- frozen carrier map when no ball named it (runtime/custom_mp_evidence.lua caller).
    function call_evidence(network)
        local e=evidence.get(network,clock)
        local b=mp_items.beacon_info(network)
        if not(e or b)then return nil,'that network id was never observed here as a carrier beacon or thrown ball'end
        local out={id=e and e.id or b.id,entity=e and e.entity or b and b.entity,position=e and e.position,
            age=e and(clock-e.first)or nil}
        local t=mission.mp and mission.mp.view and mission.mp.view.table
        local me=mission.mp and mission.mp.view and mission.mp.view.local_peer
        local peer,how,slot,why
        if e then peer,how,slot=evidence.caller(e,t,me)end
        if not peer and b and b.thrower then peer,how=b.thrower,'ball'
        elseif not peer and e then
            local _,cwhy=evidence.caller(e,t,me)
            why=cwhy
        end
        out.thrower,out.how,out.slot=peer,how,slot
        return out,why
    end
    M.call_evidence=function(network)return call_evidence(network)end
    -- Another machine's call, seen here as a carrier beacon with no state: which custom stratagem (the carrier maps to
    -- exactly one id) and which player: the thrown ball's owner (retried M.BALL_WAIT s); never a guess (only after that, and
    -- labelled, the frozen table's one other player selecting that id: the evidence's derived caller).
    local function remote_call_line(world,r,final)
        local t,why
        if r.network then t,why=ball_thrower(world,r.network)else why='its beacon\'s network id is not resolved yet'end
        if t then
            ball_evidence(world,r.network,r.id,t)
            if log_module.sample('mp.remote_call',3)then log(('CUSTOM MP CALL: peer %s (the thrown ball\'s owner), custom %s, slot %s (its record entry %d), beacon %d '
                ..'(network id %s), carrier %s: another machine\'s call; its thrower\'s Runtime runs it; this machine only '
                ..'observes'):format(t.peer,r.id,tostring(t.slot),t.entry,r.entity,tostring(r.network),r.carrier))end
            return true
        end
        -- The ball scan may have cached it already.
        local e=r.network and evidence.get(r.network,clock)
        if e and e.peer then
            log(('CUSTOM MP CALL: peer %s (its thrown ball, observed), custom %s, slot %s (its record entry %s), beacon %d '
                ..'(network id %d), carrier %s: another machine\'s call; its thrower\'s Runtime runs it; this machine only '
                ..'observes'):format(e.peer,r.id,tostring(e.slot),tostring(e.entry),r.entity,r.network,r.carrier))
            return true
        end
        if not final then r.why=why;return false end
        local v=mission.mp and mission.mp.view or sync.view()
        local peer,how,slot=evidence.caller({id=r.id},v and v.table,v and v.local_peer)
        local who
        if peer then
            who=('peer %s (NOT from the ball: %s; derived from the frozen carrier map: the only other player selecting it), '
                ..'slot %s'):format(peer,tostring(r.why),tostring(slot or'?'))
        else
            who=('peer unknown (no thrown ball names the beacon: %s; %s), slot ?'):format(tostring(r.why),tostring(how))
        end
        log(('CUSTOM MP CALL: %s, custom %s, beacon %d (network id %s), carrier %s: another machine\'s call; its thrower\'s '
            ..'Runtime runs it; this machine only observes'):format(who,r.id,r.entity,tostring(r.network),r.carrier))
        return true
    end
    -- A remote beacon's network id (read lazily: a copy may not have it in the update it is first seen). Once known, the
    -- call is cached as evidence and handed to custom_mp_items (its later items arrive by that network id). Returns true.
    M.NETWORK_WAIT=10
    local function remote_beacon_network(world,r)
        if r.network then return true end
        local it=(beacon_reader.beacons(world)or{})[r.entity]
        local network=it and support_pods.beacon_network(world,it)
        r.position=beacon_at(world,r.entity)or r.position
        if not network or network==call_ins.NO_NETWORK then return false end
        r.network=network
        local d=defs[r.id]
        evidence.observe(network,{id=r.id,type=r.type,carrier=loadout.id_of(world,r.type),entity=r.entity,position=r.position,
            source='beacon'},clock)
        -- The call this machine may later get launcher items of (runtime/custom_mp_items.lua): by its beacon's network id.
        mp_items.remote_beacon(network,{id=r.id,entity=r.entity,position=r.position},clock,d~=nil and M.mirrored(d))
        local dl=d and(d.kind=='support'or d.kind=='expendable')and delivery_of(d)
        if dl then
            observer.remote_support({network=network,call=r.id..' beacon '..r.entity,type=loadout.type_of(world,dl.id),
                item_types=dl.item_types})
        end
        return true
    end
    function M.mp_remote_beacon(world,beacon)
        local id=mission.carrier_types and mission.carrier_types[beacon.type]
        if not id or mission.remote[beacon.entity]then return end
        mission.remote[beacon.entity]=true
        local r={id=id,entity=beacon.entity,type=beacon.type,carrier=cmp.name_of(world,beacon.type),
            until_clock=mission.clock+M.BALL_WAIT,network_until=mission.clock+M.NETWORK_WAIT}
        remote_beacon_network(world,r)
        if not remote_call_line(world,r,false)then mission.pending[#mission.pending+1]=r end
    end
    -- Every Runtime step: the remote calls whose beacon network id or ball is not known yet.
    function pending_step(world)
        for k=#mission.pending,1,-1 do
            local r=mission.pending[k]
            local resolved=remote_beacon_network(world,r)
            local final=mission.clock>=r.until_clock and(resolved or mission.clock>=r.network_until)
            if remote_call_line(world,r,final)then table.remove(mission.pending,k)end
        end
    end
end
-- Every Runtime step with custom multiplayer running: other machines' published call items, correlated here by their
-- network ids and mirrored on this machine's own copies (runtime/custom_mp_items.lua). One handler per payload family:
-- what the network ids name, whose call it is, and how this machine mirrors it, all derived from its own registered
-- definition.
local remote_handlers={}
-- The caller's own items (a launcher, a barrage): the sender is the thrower (the ball, when it named one, must agree).
-- (the remote handlers: one do-block keeps the main chunk under LuaJIT's 200 locals; nothing but the handlers
-- table outside.)
do
    local function own_caller(e,b)
        if b.thrower and b.thrower~=e.peer then return nil,'the thrown ball names another thrower ('..b.thrower..')'end
        return e.peer
    end
    local function remote_item(d,kind)
        -- (An expendable definition: this mission's carrier weapon delivery, the same on every machine.)
        local dl=delivery_of(d)
        if not dl or dl=='runtime'or not(dl.item_types and dl.item_types[kind])then return nil end
        local it=dl.items and dl.items[kind]or{kind='weapon',projectile=dl.projectile}
        if not(it.kind=='weapon'and it.projectile)then return nil end
        -- Its payload this mission (a donor-self fallback's is the mission delivery's, not the definition's).
        return {kind=it.kind,projectile=it.projectile,impact=it.impact or dl.impact,rounds=it.rounds or dl.rounds,
            damage=it.damage or dl.damage}
    end
    -- A Gas EAT launcher: its rocket's own copy (live-proven r3).
    remote_handlers.launcher={kind='launcher',title='REMOTE CUSTOM ITEM',
        vanilla='its rockets explode as the vanilla rocket on this machine',caller=own_caller,
        noun=function()return'launcher'end,
        check=function(world,d,entity,kind)
            local item=kind and remote_item(d,kind)
            if not item then return nil,'not the delivery\'s launcher'end
            if not item.impact then return nil,'its rockets are the clone\'s own this mission (nothing per projectile)'end
            return item
        end,
        describe=function(d,binding)
            return('its rockets explode as %s\'s (explosion %d instead of %d) on this machine\'s own copy, whoever fires it')
                :format(tostring(binding.donor or d.delivery.impact),binding.to or 0,binding.from or 0)
        end,
        bind=function(spec)
            local d=spec.definition
            local function line(text)
                log(('REMOTE CUSTOM ITEM: peer %s\'s custom %s launcher network id %d (entity %d here): %s'):format(spec.peer,
                    spec.id,spec.network,spec.entity,text))
            end
            return impacts.bind({sources={spec.entity},projectile=spec.info.projectile,
                donor=spec.info.impact or d.delivery.impact,direct_damage=spec.info.damage,
                rounds=spec.info.rounds or d.delivery.rounds or 1,entity_type=spec.entity_type,label=('remote %s %s launcher %d'):format(spec.peer,
                spec.id,spec.network),multiplayer=true,client=mission.client==true,provenance=true},function(e)
                    if e.kind=='converted'then
                        if log_module.sample('mp.remote_item.converted',3)then line(('CONVERTED its projectile in pool slot %d: impact explosion copy %d -> %d on this machine (fired '
                            ..'by %s; creditor %s, the game\'s own)'):format(e.slot,e.from,e.to,e.local_creditor and
                            ('this machine\'s player, who picked it up')or tostring(e.creditor),tostring(e.creditor)))end
                    elseif e.kind=='impact'then
                        line(('its projectile (pool slot %d) requested explosion %d on impact here'):format(e.slot,e.explosion))
                    elseif e.kind=='refused'and e.first then
                        line(('a projectile stays vanilla here: %s: %s'):format(tostring(e.code),tostring(e.reason)))
                    end
                end)
        end}
    -- A native barrage (orbital native): its shells, each machine's own copies (source = this machine's barrage entity).
    local function barrage_events(label,on)
        local n,first=0,false
        return function(e)
            if e.kind=='converted'then
                n=n+1
                if not first then
                    first=true
                    on(('CONVERTED its first shell (projectile %d, pool slot %d): impact explosion copy %d -> %d on this machine '
                        ..'(creditor %s, the game\'s own); the next ones are counted'):format(e.type or 0,e.slot,e.from,e.to,
                        tostring(e.creditor)))
                end
            elseif e.kind=='refused'and e.first then
                on(('a shell stays vanilla here: %s: %s'):format(tostring(e.code),tostring(e.reason)))
            elseif e.kind=='ended'then
                on(('ended (%s): %d shell%s converted, %d impact%s requested here, %d refused'):format(tostring(e.reason),n,
                    n==1 and''or's',e.impacts or 0,(e.impacts or 0)==1 and''or's',e.refused or 0))
            end
        end
    end
    M.barrage_events=barrage_events
    remote_handlers.barrage={kind='barrage',title='REMOTE CUSTOM BARRAGE',
        vanilla='its shells explode as the donor\'s own on this machine',caller=own_caller,
        noun=function()return'barrage'end,
        check=function(world,d,entity)
            local inst,why=barrages.instance(world,entity)
            if not inst then return nil,tostring(why),true end
            if inst.payload~=d.orbital.payload then return nil,'a barrage of '..inst.payload..', not '..d.orbital.payload end
            return {instance=inst}
        end,
        describe=function(d,binding)
            return('its shells (%s) explode as %s\'s (explosion %d) on this machine\'s own copies, whoever\'s call it is')
                :format(table.concat(d.orbital.shells,', '),d.orbital.impact,binding.to or 0)
        end,
        bind=function(spec)
            local d=spec.definition
            return impacts.bind({sources={spec.entity},projectiles=d.orbital.shells,donor=d.orbital.impact,rounds=64,
                entity_type=spec.entity_type,label=('remote %s %s barrage %d'):format(spec.peer,spec.id,spec.network),
                multiplayer=true,client=mission.client==true,provenance=true},barrage_events(spec.id,function(text)
                    log(('REMOTE CUSTOM BARRAGE: peer %s\'s custom %s barrage network id %d (entity %d here): %s'):format(
                        spec.peer,spec.id,spec.network,spec.entity,text))
                end))
        end}
    -- A custom sentry (the sentry family): published by its caller. Here: this machine's own copy of that sentry, its
    -- type the definition's sentry; the creator configures it whole, any other machine mirrors its round, spread and
    -- recoil (runtime/custom_weapons.lua role 'published').
    remote_handlers.sentry={kind='sentry',title='REMOTE CUSTOM SENTRY',
        vanilla='its weapon stays the sentry\'s stock one on this machine',caller=own_caller,
        noun=function()return'sentry'end,
        check=function(world,d,entity,kind)
            if kind~=d.delivery.content_type then
                return nil,('not the %s\'s sentry (entity type %s, not %s)'):format(d.delivery.stratagem,tostring(kind),
                    tostring(d.delivery.content_type))
            end
            if world_module.entity_exists(world,entity)~=true then return nil,'the sentry is gone',true end
            return {sentry=entity}
        end,
        describe=function(d,binding)
            local r=binding.result
            return r.mirror and(('its round, spread and recoil mirrored on this machine\'s own copy (%d writes; verified %s); '
                ..'its rate and magazine are its creator\'s (replicated)'):format(r.writes,tostring(r.verified)))
                or(('configured whole here: this machine created it (%d writes; verified %s)'):format(r.writes,
                tostring(r.verified)))
        end,
        bind=function(spec)
            local world=world_module.open()
            if not world then return nil,'UNAVAILABLE','no game world'end
            local r,code,reason=weapons.configure(world,spec.entity,spec.definition.sentry.weapon,('remote %s %s sentry %d')
                :format(spec.caller,spec.id,spec.network),{role='published',published=true})
            if not r then return nil,code,reason end
            return {status='active',cancel=function()end,kind='sentry',result=r}
        end}
    -- A custom silo's missile (the silo family): published by its caller. Here: this machine's own copy of that missile,
    -- watched until it detonates; the session host requests the blast there (runtime/custom_silos.lua), every other
    -- machine logs it.
    remote_handlers.silo={kind='silo',title='REMOTE CUSTOM SILO',
        vanilla='its missile\'s own blast only (no custom blast for it from this machine)',caller=own_caller,
        noun=function()return'missile'end,
        check=function(world,d,entity,kind)
            if kind~=d.delivery.missile then
                return nil,('not the %s\'s missile (entity type %s, not %s)'):format(d.delivery.stratagem,tostring(kind),
                    tostring(d.delivery.missile))
            end
            if world_module.entity_exists(world,entity)~=true then return nil,'the missile is gone',true end
            return {missile=entity}
        end,
        describe=function(d)
            return 'watched here: where it detonates this machine requests the '..d.delivery.blast..' explosion from its '
                ..'own copy'
        end,
        bind=function(spec)
            local d=spec.definition
            local silos=require('hd2runtime/runtime/custom_silos')
            local label=('remote %s %s missile %d'):format(spec.caller,spec.id,spec.network)
            local function line(text)
                log(('REMOTE CUSTOM SILO: peer %s\'s custom %s missile network id %d (entity %d here): %s'):format(
                    spec.caller,spec.id,spec.network,spec.entity,text))
            end
            local w=silos.watch({missile=spec.entity,detonation=d.delivery.detonation,label=label},function(ev)
                if ev.kind=='launched'then line('LAUNCHED at '..at(ev.position))
                elseif ev.kind=='gone'then line('ended before it left the silo: no blast')
                elseif ev.kind=='detonated'then
                    local action,name=silos.blast(d,ev.position,label,ev.origin)
                    line(('DETONATED at %s (%s): %s'):format(at(ev.position),ev.via=='queue'and'its own detonation in the '
                        ..'explosion queue'or'inferred: the missile is gone',action and(name..' explosion requested there on this machine ('
                        ..tostring(action.status)..')')or('no blast from this machine: '..tostring(name))))
                end
            end)
            return {status='active',cancel=function()w.cancel()end,kind='silo'}
        end}
    -- A host-spawned Pelican (the pelican family): published by the SESSION HOST (it spawns every Pelican), the call's
    -- caller being its beacon's thrower (the ball). Network ids: the Pelican, then its chin turret. Here: the turret's own
    -- copy (runtime/custom_mp_pelican.lua mirrors the chin gun's private presentation; nothing of the Pelican's flight,
    -- AI, target or lifetime, which the host keeps).
    local pelican_mirror=require('hd2runtime/runtime/custom_mp_pelican')
    remote_handlers.pelican={kind='pelican',title='REMOTE CUSTOM PELICAN',
        vanilla='its chin gun stays the stock one on this machine',
        caller=function(e,b,v)
            if not(v and e.peer==v.host_peer)then
                return nil,'only the session host spawns a Pelican; '..e.peer..' is not the host'
            end
            -- The call's caller: its thrown ball's thrower, else derived from the frozen carrier map (the evidence).
            local thrower=b.thrower
            if not thrower then local ev=call_evidence(e.beacon);thrower=ev and ev.thrower end
            if not thrower then return nil,'wait'end
            return thrower
        end,
        noun=function(index)return index==1 and'Pelican'or'chin turret'end,
        check=function(world,d,entity,kind,index)return pelican_mirror.check(world,entity,index)end,
        describe=function(d,binding,index)
            if index==1 then return'the host-spawned Pelican of that call (its flight, AI, target and lifetime stay the host\'s)'end
            return binding.describe and binding.describe()or'its chin gun mirrored on this machine\'s own copy'
        end,
        bind=function(spec)
            if spec.index==1 then return {status='active',cancel=function()end,kind='pelican'}end
            -- Its Pelican here: the entry's first network id (correlated first).
            local world=world_module.open()
            local pelican=world and spec.networks and world_module.network_entity(world,spec.networks[1])
            if not pelican then return nil,'NO_PELICAN','its Pelican does not resolve here'end
            return pelican_mirror.mirror({turret=spec.entity,pelican=pelican,network=spec.network,
                gun=spec.definition.pelican.gun or{},label=('remote %s %s chin turret %d'):format(spec.caller,spec.id,
                spec.network),client=mission.client==true})
        end}
end
-- The handler of a definition (nil: its payload is not mirrored on other machines).
local function remote_handler(d)
    if(d.kind=='support'or d.kind=='expendable')and d.delivery~='runtime'and(d.delivery.impact
            or d.kind=='expendable'and d.delivery.fallback and d.delivery.fallback.impact)then
        return remote_handlers.launcher
    end
    if d.kind=='orbital'and d.orbital and d.orbital.native then return remote_handlers.barrage end
    if d.kind=='pelican'then return remote_handlers.pelican end
    if d.kind=='sentry'and d.sentry and next(d.sentry.weapon)then return remote_handlers.sentry end
    if d.kind=='silo'then return remote_handlers.silo end
    return nil
end
M.remote_handler=remote_handler
local function items_step(world)
    mp_items.step(world,sync.view(),{table=mission.mp.view.table,
        definition=function(id)return defs[id]end,handler=remote_handler,
        assets=function(id)
            local r=mission.remote_assets[id]
            if not r then return false,'not requested (not in the synced picks)'end
            if r.state=='ready'then return true end
            if r.state=='failed'then return false,r.why end
            return nil
        end},clock)
end
-- The session host runs a call another player requested (runtime/custom_mp_calls.lua, every check passed): a call
-- context whose caller is that player (ctx.remote), positioned at that player's beacon (its copy here). No mod callback
-- runs for it: it is that player's call, run here only because only the host can create its payload for everyone.
local function host_call(r,peer,b)
    local d=defs[r.id]
    local world=world_module.open()
    if not(d and world)then return nil,'no definition or no game world'end
    local caller
    for _,pl in ipairs(handles.players())do if pl.peer==peer then caller=pl end end
    if not caller then return nil,'the caller is not a player of this game'end
    -- Its beacon copy's position while that entity is still a beacon here, else the one observed with it (the copy may
    -- be gone by the time the request comes, and its entity id reused).
    local live=b.entity and(beacon_reader.beacons(world)or{})[b.entity]
    local position=live and beacon_at(world,b.entity)or b.position
    if not position then return nil,'its beacon copy has no position here (none was observed)'end
    mission.n=mission.n+1
    mission.count[d.id]=(mission.count[d.id]or 0)+1
    local a=mission.allocation and mission.allocation.assignments[d.id]
    local ctx=setmetatable({definition=d.id,id=d.id,owner=d.owner,n=mission.count[d.id],
        call_id=d.id..'#'..mission.count[d.id]..'@'..peer,player=caller,player_peer=peer,slot=r.slot,remote=true,
        multiplayer=true,client=false,carrier=a and{name=a.carrier,stable_id=a.stable_id,type=a.type},delivery='runtime',
        state='activated',position=position,beacon={entity=b.entity,network=r.beacon},request=r},Call)
    mp.mark_call(ctx)
    ctx.custom_call=provenance.call({custom_id=d.id,call_id=ctx.call_id,seq=r.seq,caller_peer=peer,slot=r.slot,
        carrier_stable_id=a and a.stable_id,beacon_network=r.beacon,position=position,authority='host'})
    mission.calls[#mission.calls+1]=ctx
    ensure_kill_watch()
    ctx:log(('HOST CALL: peer %s\'s %s (call seq %d, loadout slot %d), its beacon %s (network id %d) at %s: the host runs '
        ..'it for that player'):format(peer,d.id,r.seq,r.slot,tostring(b.entity),r.beacon,at(position)))
    return host_pelican(ctx,d)
end
local function calls_step(world)
    mp_calls.host_step(world,sync.view(),{table=mission.mp.view.table,carrier=mission.mp.carrier_hash,
        definition=function(id)return defs[id]end,host_runs=function(d)return d.kind=='pelican'end,
        beacon=call_evidence,run=host_call},clock)
end
-- This machine's own call, with several players: what its thrown ball says (the owner must be this machine's peer).
function M.own_ball_line(world,ctx)
    local t,why=ball_thrower(world,ctx.beacon and ctx.beacon.network)
    local lo,hi=world_module.local_peer(world)
    local me=lo and world_module.peer_hex(lo,hi)
    ctx.ball=t
    if t then
        ctx:log(('CALL BALL: the thrown ball names peer %s (this machine: %s), record entry %d (loadout slot %s), type %d'):
            format(t.peer,tostring(t.peer==me),t.entry,tostring(t.slot),t.type))
    else
        ctx:log('CALL BALL: no thrown ball names this beacon yet ('..tostring(why)..')')
    end
end

local function start_mission(world)
    local list,by=selected()
    local players=world_module.players(world)
    local game=world_module.game_state(world)
    -- Several players: custom multiplayer may still be settling (a member's value, the lobby read after the loading).
    -- Also: this machine's current state not posted yet (its peers would allocate from an older row of it).
    local v0=sync.view()
    if#players>1 and#order>0 and v0~=nil and(v0.status=='waiting'or(v0.status=='enabled'and not v0.local_posted))
            and mission.clock<(mission.populated or 0)+M.SETTLE+M.MP_WAIT then
        return
    end
    mission.started=true
    mission.players=#players
    if#players>1 then
        mp.announce(#players,'a mission')
        cmp.peers(world,'mission start')
    end
    local block=mission.disabled or M.disabled_reason(sync.view())
    if block then
        mission.disabled=block
        log('MISSION: '..block..'. Nothing custom runs in this mission: no carrier allocated or frozen, no slot converted, '
            ..'no custom call, no provenance; vanilla gameplay is untouched')
        if#list>0 then fail_closed(world,block)end
        return
    end
    if#list==0 and#players<=1 then return end
    local v=sync.view()
    if#players>1 and v and v.status=='enabled'then
        -- ONE coherent snapshot for the whole setup: the members, each one's last accepted state (seq), this machine's
        -- own row, the table and its hash, all copies (runtime/custom_mp_sync.lua composes a fresh view every step);
        -- nothing of the channel's polling state is held while converting.
        local seqs={}
        for _,peer in ipairs(v.members)do
            seqs[#seqs+1]=peer..(peer==v.local_peer and(' seq '..tostring(v.local_seq)..(v.local_posted and' posted'
                or' NOT posted'))or(' seq '..tostring((v.peers or{})[peer]and v.peers[peer].seq)))
        end
        log(('CUSTOM MP SNAPSHOT (mission start, frozen for the setup): %s; table hash %s'):format(table.concat(seqs,', '),
            tostring(v.table_hash)))
        mission.token_type=loadout.type_of(world,stratagem_id(M.TOKEN))
        mission.mp={state='records',since=mission.clock,view=v,list=list,by=by,game=game,desynced={}}
        -- One beacon watch for this machine's own calls and every other machine's (observed).
        local watch,wwhy=beacons.watch({label='custom stratagems (multiplayer)',decide=decide,multiplayer=true},
            beacon_event)
        if not watch then return mp_refuse('the beacon watch cannot run: '..tostring(wwhy))end
        mission.watch=watch
        return mp_step(world)
    end
    if#players>1 then
        log(('MISSION: custom multiplayer is %s (%s): this build keeps its earlier behaviour (the host runs its own '
            ..'custom calls; a client none)'):format(v and v.status or'unknown',tostring(v and v.reason)))
    end
    local _,saved=saved_ids(world)
    -- The saved loadout and every stratagem record of this mission AS FIRST SEEN (each player's record, the mission's
    -- defaults): a carrier a faster peer's Runtime converted and the game synced since is never a native pick.
    local token_type=loadout.type_of(world,stratagem_id(M.TOKEN))
    local native=cmp.native(world,saved or{},token_type)
    -- The carrier-in-slot probe: a carrier this player holds only in its own custom slots is not its native pick.
    do
        local probe=require('hd2runtime/runtime/carrier_in_slot')
        local own=probe.own_carriers(saved_ids(world),selector.virtual_slots(),M.peer_ids(world))
        if next(own)then
            local removed
            native.present,removed=probe.discount(native.present,own)
            local names={}
            for k,id in ipairs(removed)do names[k]=names_by_id[id]or tostring(id)end
            probe.log(('MISSION: %s, held only in this player\'s custom slots, %s not a native pick'):format(
                table.concat(names,', '),#names==1 and'is'or'are'))
        end
    end
    if#native.converted>0 then
        log('MISSION: converted custom slots seen in the records before this allocation (not native picks): '
            ..table.concat(native.converted,'; '))
    end
    if#native.changed>0 then
        log('MISSION: record entries changed since first seen (both types count as native picks): '
            ..table.concat(native.changed,'; '))
    end
    local _,who=lobby_picks(world,saved_ids(world)or{})
    local a,why=allocate(world,native.present,list,'at mission start, against the saved loadout and this mission\'s '
        ..'records as first seen',nil,who)
    if not a then
        log('MISSION: custom stratagems REFUSED: the carriers cannot be allocated now: '..tostring(why))
        return
    end
    mission.allocation=a
    freeze_carriers(a,#players>1 and'mission start'or nil)
    mission.token_type=token_type
    if#players>1 then
        cmp.carriers(a,#players,'mission start')
        local ids_by_slot={}
        for id,list_slots in pairs(by)do for _,slot in ipairs(list_slots)do ids_by_slot[slot]=id end end
        cmp.picks(world,nil,mission.token_type,mission.carrier_types,ids_by_slot)
    end
    if not(game and game.host==true)then
        if#list>0 then
            setup_refused(('this machine is a client and custom multiplayer is %s'):format(v and v.status or'unknown'),by)
            log(('MISSION: custom stratagems REFUSED on this machine: it is a client (%d players). Each player\'s own '
                ..'Runtime runs that player\'s calls (a beacon belongs to its thrower\'s machine), and every custom '
                ..'stratagem write is host-only in this build (a client\'s were never proven safe). Your custom slot%s '
                ..'stay%s the token %s'):format(#players,#list==1 and''or's',#list==1 and's'or'',M.TOKEN))
        end
        -- Read-only: other machines' custom calls are reported (no decision, nothing written).
        if#players>1 then
            mission.watch=beacons.watch({label='custom stratagems (observing)',multiplayer=true},beacon_event)
        end
        return
    end
    for _,id in ipairs(a.order)do
        local d=defs[id]
        local assignment=a.assignments[id]
        if not by[id]then
            -- Registered, allocated (its carrier is reserved for it lobby-wide), not selected by this player.
        elseif assignment and d.kind=='pod'and#players>1 then
            log(('MISSION (%s): REFUSED: a carrier pod (the support_pod group) runs solo host only in this build (a rack '
                ..'written on one machine; the other machines\' racks are vanilla)'):format(id))
            setup_refused('a carrier pod runs solo host only',{[id]=by[id]})
        elseif assignment and d.kind=='expendable'and#players>1 then
            log(('MISSION (%s): REFUSED: an expendable custom stratagem with several players needs custom multiplayer '
                ..'(every lobby member a compatible Runtime converting the same carrier weapon); it is %s'):format(id,
                v and v.status or'unknown'))
            setup_refused('custom multiplayer is not enabled',{[id]=by[id]})
        elseif assignment and M.probe_blocks(d,assignment,#players)then
            local text,carrier=M.probe_refusal(d,assignment,#players)
            log(('MISSION (%s): REFUSED (the carrier-in-slot probe): %s'):format(id,text))
            if carrier and carrier_presentation.applied(carrier)then
                carrier_presentation.restore(function()end,carrier)
            end
            setup_refused(text,{[id]=by[id]})
        elseif assignment then
            local reconvert=M.probe_reconvert(d,assignment,#players)
            if reconvert then
                log(('MISSION (%s): LAUNCH FALLBACK (the carrier-in-slot probe): %s: its slot is swapped to %s in this '
                    ..'mission\'s record (its own entry by loadout position; locked until it is ready)'):format(id,
                    reconvert.text,assignment.carrier))
            end
            mission.queue[#mission.queue+1]={definition=d,assignment=assignment,state='checks',slots=by[id],
                reconvert=reconvert}
            -- No carrier weapon conversion for a definition whose code the slot checks will refuse anyway (its type
            -- would stay converted for nothing).
            local clash=d.kind=='expendable'and native_conflicts(world,d,assignment.stable_id)or{}
            if d.kind=='expendable'and#clash>0 then
                log(('MISSION (%s): its carrier weapon is not converted: its code %s collides with %s'):format(id,
                    d.code_text,table.concat(clash,'; ')))
            elseif d.kind=='expendable'then add_clone(d,assignment)end
        else
            log(('MISSION (%s): REFUSED: %s'):format(id,tostring(a.refused[id])))
        end
    end
    -- One beacon watch for every custom stratagem, armed before any carrier can be called (with several players also
    -- reporting other machines' custom calls).
    if#mission.queue==0 and#players<=1 then return end
    local watch,wwhy=beacons.watch({label='custom stratagems',decide=decide,multiplayer=true},beacon_event)
    if not watch then
        log('MISSION: custom stratagems REFUSED: the beacon watch cannot run: '..tostring(wwhy))
        mission.queue={}
        return
    end
    mission.watch=watch
end

-- On_called from the record: a converted entry's call-in starting (read-only).
local function record_step(world)
    if(mission.players or 1)>1 and mission.carrier_types then
        cmp.records_step(world,mission.token_type,mission.carrier_types)
    end
    for _,item in ipairs(mission.queue)do
        if item.state=='ready'then
            local seen=slots.observe(world,item.definition.id)
            for _,obs in ipairs(seen or{})do
                local last=mission.seen[obs.index]
                if obs.flying and not(last and last.flying)then
                    local slot
                    for k,index in ipairs(item.indices or{})do if index==obs.index then slot=(item.slots or{})[k]end end
                    -- A beacon seen first already made the call: give it its slot; else a call now.
                    local ctx
                    for _,c in ipairs(mission.calls)do
                        if c.definition==item.definition.id and c.slot==nil and c.state~='called'and not c.slot_seen then
                            ctx=c;break
                        end
                    end
                    if ctx then ctx.slot,ctx.slot_seen=slot,true
                    else
                        ctx=new_call(item.definition,item.assignment,slot)
                        ctx.slot_seen=true
                        log(('%s: CALLED from loadout slot %s'):format(ctx.call_id,tostring(slot)))
                        run_callback(item.definition,'on_called',ctx)
                    end
                end
                mission.seen[obs.index]=obs
            end
            -- A record entry related to its code appearing later: the slot returns to its token.
            local conflicts=record_conflicts(world,item.definition,item.assignment.type)
            for _,c in ipairs(conflicts or{})do
                if not mission.conflicts[c.key]then
                    mission.conflicts[c.key]=true
                    log(('MISSION (%s): CODE CONFLICT: the record now holds %s: its slot returns to its token'):format(
                        item.definition.id,c.text))
                    item.state='returning'
                    slots.restore(function(h)
                        item.state='returned'
                        log(('MISSION (%s): returned to its token: %s'):format(item.definition.id,tostring(h.status)))
                    end,item.definition.id)
                end
            end
        end
    end
end

-- Kills whose last hit came from an associated entity (a Pelican's chin turret) are reported against its call.
local function on_death(event)
    if not mission.on then return end
    local world=world_module.open()
    if not world then return end
    local hit=require('hd2runtime/runtime/ownership').last_hit(world,event.entity_id)
    local owner=hit and hit.owner
    local entry=owner and instances.lookup(owner)
    if not entry then return end
    local k=mission.kills[entry.call_id]or{n=0,mine=0}
    mission.kills[entry.call_id]=k
    k.n=k.n+1
    if event.local_killer then k.mine=k.mine+1 end
    if k.n<=M.KILL_LOGS then
        log(('%s: KILL: victim %d (%s) by its %s %d -> credited to %s'):format(entry.call_id,event.entity_id,
            tostring(event.semantic_id),entry.role,owner,event.killer_peer and(event.killer_peer..(event.local_killer
            and' (you)'or''))or'nobody'))
    end
end

-- The kill report's death events: only once a call has activated in this mission (the health source then runs), and
-- only for this mission (scope 'mission': dropped at its end).
function ensure_kill_watch()
    if mission.kill_watch then return end
    mission.kill_watch=events.subscribe('entity_died',on_death,{owner='hd2runtime',id='custom-stratagem-kills',
        scope='mission'})
end

local function mission_end(world)
    mp.enable_client_proof(false)
    mp.enable_lockout(false)
    mpstate.host=nil
    for _,binding in ipairs(mission.barrage_watch or{})do if binding.status=='active'then binding.cancel()end end
    for _,item in ipairs(mission.queue)do
        cooldowns.disarm(item.definition.id)
        if item.eagle_armed then eagles.disarm();item.eagle_armed=nil end
        if item.uses_watch then item.uses_watch.cancel();item.uses_watch=nil end
    end
    if mission.watch then mission.watch.cancel()end
    local parts={}
    for _,item in ipairs(mission.queue)do
        local k=0
        for _,c in ipairs(mission.calls)do if c.definition==item.definition.id then k=k+1 end end
        local credit={}
        for call_id,kc in pairs(mission.kills)do
            if call_id:sub(1,#item.definition.id+1)==item.definition.id..'#'then
                credit[#credit+1]=('%s %d kills (%d yours)'):format(call_id,kc.n,kc.mine)
            end
        end
        parts[#parts+1]=('%s: %s, %d call%s%s'):format(item.definition.id,item.state,k,k==1 and''or's',
            #credit>0 and('; '..table.concat(credit,', '))or'')
    end
    if#parts>0 then log('MISSION END: '..table.concat(parts,'; '))end
    if(mission.players or 1)>1 then log('PROVENANCE (mission end): '..provenance.summary())end
    reset_mission()
end

------------------------------------------------------------------------------------------------- the loop --
local loop,landing,panel,remote_overlays
-- A step that raised: logged once per reason (the next step runs again).
local failed={}
local function step_failed(what,why)
    local text=('STEP FAILED (%s): %s; the custom stratagem loop continues and retries'):format(what,tostring(why))
    if failed[text]then return end
    failed[text]=true
    log(text)
end
local function tick(dt)
    clock=clock+(dt or 0)
    -- Aboard the ship: the carriers the custom selections reserve, blocked on the open native grid every update.
    if not mission.on and blocking then
        local wg=world_module.open()
        if wg then blocked_apply(wg,dt)end
    end
    -- The carrier-in-slot probe (development, runtime/carrier_in_slot.lua): its timing log and its early presentation,
    -- every update while a carrier slot is picked (nothing otherwise).
    do
        local set=selector.virtual_slots()
        local has=false
        for _,e in pairs(set and set.slots or{})do if e.carrier then has=true end end
        local wp=has and world_module.open()
        local game=wp and world_module.game_state(wp)
        if game then
            local players=world_module.players(wp)
            local probe=require('hd2runtime/runtime/carrier_in_slot')
            local sv=sync.view()
            probe.step({game=game,clock=clock,definitions=defs,set=set,world=wp,mp=sv~=nil and sv.status=='enabled',
                carrier_name=function(id)return names_by_id[id]end,players=players and#players or nil,
                hud=function()return stratagem_hud.populated(wp)end,
                -- Whether the slots' carrier is the definition's carrier now and held by nobody else.
                consistent=function(id,x)
                    local mine=cache[id]
                    if not(mine and mine.stable_id==x.id)then
                        return false,'its carrier now is '..tostring(mine and mine.carrier or'none')
                    end
                    if not probe.own_carriers(loadout_ids(wp),set,M.peer_ids(wp))[x.id]then
                        return false,'it is also a native pick'
                    end
                    return true
                end})
        end
    end
    -- r38: every other player's carrier slot presented on this machine too (custom multiplayer), from the first mission
    -- update (before the HUD), every M.REMOTE_EVERY s.
    if clock>=(M.remote_at or 0)then
        M.remote_at=clock+M.REMOTE_EVERY
        local wr=world_module.open()
        if wr then
            local ok,err=pcall(M.probe_remote_step,wr)
            if not ok then step_failed('the remote carrier presentation',err)end
        end
    end
    -- Other players' thrown balls, faster than the step (a ball lives only around its landing): cached as evidence.
    if mission.mp and mission.mp.state=='running'and clock>=(mission.ball_next or 0)then
        mission.ball_next=clock+M.BALL_SCAN
        local wb=world_module.open()
        if wb then
            local ok,why=pcall(ball_scan,wb)
            if not ok then step_failed('the thrown-ball scan',why)end
        end
    end
    if clock<(loop.next or 0)then return end
    loop.next=clock+M.STEP
    local world=world_module.open()
    if not world then return end
    local game=world_module.game_state(world)
    local in_mission=game and game.mission
    if in_mission and not mission.on then
        loadout_state.enter()
        reset_mission()
        mission.on=true
        life.due,life.refused,life.retry_at=nil,{},0
    elseif not in_mission and mission.on then
        mission_end(world)
        -- Every ship-side cache derived before the mission: recomputed from the reconciled ship loadout state.
        ship.key,ship.status,ship.alloc,ship.inputs=nil,{},nil,nil
        cache={}
        avail.at=-math.huge
        sync.mission_ended(clock)
        loadout_state.leave()
    end
    -- The ship-side restore runs back aboard the ship only: never on the loading screen or in the mission's first frames
    -- (its mode not set yet), where the carrier-in-slot probe's early and remote presentations stand (r41: r40 restored
    -- them there, and the HUD then showed the carrier).
    if game then
        lifecycle_step(world,in_mission or game.name=='PrepareMission'or game.name=='Mission')
    end
    -- Back aboard the ship: the ship loadout state reconciled before anything is published.
    if game and not in_mission then loadout_state.step(world)end
    local v
    if game then
        local ok,result=pcall(mp_sync_step,world,in_mission)
        if ok then v=result
        else
            -- The synced state is unusable for this step: no multiplayer view (WAITING), read afresh next time.
            step_failed('the multiplayer sync',result)
            sync.reset_reads()
        end
    end
    if not in_mission then
        if game then
            M.limit_step();ship_step(world,v);M.probe_move_step(world);availability_step(world,v)
            reservations_step(world,v)
            mp_ship_step(world)
        end
        return
    end
    mission.clock=mission.clock+M.STEP
    if not mission.started then cmp.first_seen(world)end
    if not mission.populated then
        if stratagem_hud.populated(world)then mission.populated=mission.clock end
        return
    end
    -- Disabled lobby-wide: this machine's custom slots are locked at once (never callable, not even before the setup).
    if not mission.disable_checked then
        mission.disable_checked=true
        local block=M.disabled_reason(v)
        if block then
            mission.disabled=block
            if fail_closed(world,block)>0 then
                M.disabled_notice('Your custom stratagem slots are locked for this mission.')
            end
        end
    end
    -- The Ongoing probe (runtime/ongoing_probe.lua, read-only): what drives the HUD's "Ongoing" countdown of a call. A
    -- development diagnostic (a line a second per call): only with hd2.custom_stratagem.verbose(true) since 0.30.0.
    if verbose then
        local okp,why=pcall(function()require('hd2runtime/runtime/ongoing_probe').step(world,M.STEP)end)
        if not okp and not mission.ongoing_failed then mission.ongoing_failed=true;log('ONGOING PROBE failed: '..tostring(why))end
    end
    if mission.clock<mission.populated+M.SETTLE then return end
    if not mission.started then start_mission(world)end
    if mission.mp and(mission.mp.state=='records'or mission.mp.state=='agreement')then mp_step(world)end
    if mission.mp and#mission.pending>0 then pending_step(world)end
    if mission.started then barrage_watch_step()end
    if mission.mp and mission.mp.state=='running'then
        remote_assets_step()
        items_step(world)
        if mission.mp.game and mission.mp.game.host==true then calls_step(world)end
    end
    -- The carrier weapons (expendable custom stratagems), one at a time, before their definitions can present.
    if#mission.clone_order>0 then clone_step(world)end
    -- One custom stratagem at a time through its steps (the jobs complete in later ticks).
    for _,item in ipairs(mission.queue)do
        if item.state~='ready'and item.state~='refused'and item.state~='returned'and item.state~='returning'then
            if item.state=='checks'or item.state=='assets'or item.state=='clone'or item.state=='arming'
                or item.state=='pod_rack'or item.state=='pod_done'or item.state=='barrage_watch'then
                advance(world,item)
            end
            break
        end
    end
    record_step(world)
end

-- Starts the shared panel, the loop and the watches (once, at the first registration).
function M.start()
    if loop then return end
    -- Which build this is, in every log that registers a custom stratagem (the version alone does not tell it).
    log(('EXPERIMENTAL CUSTOM MP FAIL-CLOSED BUILD r9 (%s; hd2rt/1 picks, call items and host calls; carrier groups): '
        ..'r8 unchanged (the weapon sound catalogue); an incompatible custom stratagem registry in the lobby disables '
        ..'custom stratagems on every machine (CUSTOM STRATAGEMS DISABLED) and locks the token of every custom slot in a '
        ..'mission'):format(cmp.PROTOCOL))
    loop={status='active'}
    function loop.tick(dt)
        if loop.status~='active'then return end
        local started=metrics.now()
        -- Never let one failing step end the loop (the scheduler cancels a watch that raises): the custom stratagems
        -- would stop for the rest of the session and every custom slot would silently stay its token.
        local ok,why=pcall(tick,dt)
        if not ok then
            step_failed('a custom stratagem step',why)
            ship.key=nil
            if mission.mp and(mission.mp.state=='records'or mission.mp.state=='agreement')then
                pcall(mp_refuse,'its setup failed: '..tostring(why))
            end
        end
        metrics.elapsed('custom_stratagems.tick',started)
    end
    function loop.cancel()loop.status='cancelled'end
    scheduler.attach(loop)
    landing={status='active',acc=0}
    function landing.tick(dt)
        if landing.status~='active'then return end
        landing.acc=landing.acc+(dt or 0)
        if landing.acc<M.LANDING_STEP then return end
        landing.acc=0
        landing_step()
    end
    function landing.cancel()landing.status='cancelled'end
    scheduler.attach(landing)
    -- Other players' synced custom picks on their loadout panels (display only; the synced view of
    -- runtime/custom_mp_sync.lua is the authority: a compatible player's slots only, whatever the native slot shows).
    remote_overlays=require('hd2runtime/runtime/stratagem_slot_overlay').remote_slots(function()
        local v=sync.view()
        local out
        for peer,q in pairs(v and v.peers or{})do
            if q.state=='compatible'and q.slots and peer~=v.local_peer then
                out=out or{}
                out[peer]=q.slots
            end
        end
        return out
    end)
    -- In a mission, the same players' custom slots on the teammate stratagem HUD (display only; the mission's frozen
    -- synced table and carrier map are the authority; nothing while custom multiplayer is not running).
    do
        local teammates=require('hd2runtime/runtime/stratagem_slot_overlay').mission_remote_slots(function()
            local m=mission.mp
            if not(m and m.state=='running'and m.view and m.view.table and mission.carrier_types)then return nil end
            -- A player whose Runtime this lobby now reports incompatible (a rejoin with another mod set) is left out.
            local live=sync.view()
            local out
            for peer,slots in pairs(m.view.table)do
                local q=live and live.peers and live.peers[peer]
                if peer~=m.view.local_peer and not(q and(q.state=='incompatible'or q.state=='invalid'))then
                    out=out or{};out[peer]=slots
                end
            end
            return out,mission.carrier_types,M.presented_here
        end)
        local stop=remote_overlays.stop
        remote_overlays.teammates=teammates
        function remote_overlays.stop()stop();teammates.stop()end
    end
    panel=panel_module.panel({renderer='native',placeholders=0,focus=true,selection=true,mouse=true,
        -- An expendable custom stratagem without a free carrier weapon: its tile warns and it cannot be picked.
        availability=function(id)return avail.state[id]or M.limit_reason(id)end,
        -- A focused card's details, drawn over the native details panel.
        details=function(id)return M.panel_details(id)end,
        -- The carrier-in-slot probe: the carrier a definition's pick writes (nil: the token).
        carrier_for=function(id)return M.probe_carrier(id)end,
        on_selected=function(h)
            if h.status=='selected'then
                local vs=selector.virtual_slots()
                local e=vs and vs.slots[h.index]
                log(('SHIP: selected into loadout slot %s (%s); virtual slots: %s'):format(tostring(h.index),
                    e and e.carrier and'the saved loadout holds its carrier itself: the carrier-in-slot probe'
                    or('the saved loadout holds the '..M.TOKEN..' token'),selector.slots_text(vs)))
            elseif h.status~='restored'then
                log(('SHIP: selection REFUSED (nothing written): %s: %s'):format(tostring(h.code),tostring(h.reason)))
            end
        end})
    -- The panel's keys (the live-proven proof keys; a click selects too): F6 focus, F7 select, Ctrl+F7 undo.
    local input=require('hd2runtime/runtime/input')
    input.bind('hd2runtime.custom_stratagem_focus',{key='F6',on_press=function()log('F6: '..tostring(panel.focus_next()))end},
        'hd2runtime')
    input.bind('hd2runtime.custom_stratagem_select',{key='F7',on_press=function()log('F7: '..tostring(panel.press()))end},
        'hd2runtime')
    input.bind('hd2runtime.custom_stratagem_undo',{key='Ctrl+F7',on_press=function()log('Ctrl+F7: '
        ..tostring(panel.cancel()))end},'hd2runtime')
    -- The loadout screen opening is the hard boundary: a stale carrier presentation is restored in that frame.
    selector.watch(function(event)
        if event~='opened'and event~='grid_opened'then return end
        if(carrier_presentation.applied()or weapon_clone.applied()or carrier_pod.applied())and not mission.on then
            restore_all('LOADOUT OPEN',true)
        end
    end)
end
-- The panel's own actions for key bindings: focus the next entry, select the focused one, undo the last selection.
function M.panel()return panel end
-- What every custom stratagem is doing: {{id, owner, carrier, state, calls}}.
function M.status()
    local out={}
    for _,d in ipairs(order)do
        local state='ship'
        for _,item in ipairs(mission.queue or{})do if item.definition==d then state=item.state end end
        local calls=0
        for _,c in ipairs(mission.calls or{})do if c.definition==d.id then calls=calls+1 end end
        out[#out+1]={id=d.id,owner=d.owner,carrier=cache[d.id]and cache[d.id].carrier,state=state,calls=calls,
            ship=ship.status[d.id]}
    end
    return out
end
-- What a custom stratagem uses (hd2.custom_stratagem.describe): plain data, read-only. {id, owner, kind, group (its carrier
-- group), group_source ('requested' | 'default'), carrier = {name, stable_id, type, family, beacon, beam, condensed,
-- fallback, local_refused} (the mission's allocation, else the ship's; nil before), carrier_weapon = {name, stable_id,
-- entity, level} (expendable), pod = {carrier (whose rack), rack, path, exclusive, capacity, written (this mission),
-- items = {{item, kind, count}}, slots = {{slot, item, label}}}, available, reason, state, calls, allocated ('mission' |
-- 'ship' | nil)}. nil for an unknown id.
local function rack_of(carrier)
    local r=carrier_pod.rack(carrier)
    if r then return {carrier=carrier,rack=r.resource,path=r.path,exclusive=true,capacity=r.capacity}end
    local name=PP.byStratagem[carrier]
    local pr=name and PP.racks[name]
    if pr then return {carrier=carrier,rack=pr.resource,exclusive=pr.shared~=true and pr.ownerCount==1,
        capacity=pr.spawnCount,shared=pr.shared==true}end
    return {carrier=carrier}
end
function M.describe(id)
    local d=defs[id]
    if not d then return nil end
    local a,where
    if mission.allocation and mission.allocation.assignments[id]then a,where=mission.allocation.assignments[id],'mission'
    elseif ship.alloc and ship.alloc.assignments[id]then a,where=ship.alloc.assignments[id],'ship'end
    local refused=(mission.allocation and mission.allocation.refused[id])or(ship.alloc and ship.alloc.refused[id])
    local out={id=id,owner=d.owner,kind=d.kind,group=d.group,group_source=d.group_source,allocated=where,
        slots=d.slots,label=d.label,code=d.code_text,code_values=d.code_values and{unpack(d.code_values)}or nil,
        cooldown=d.cooldown,uses=d.uses,eagle_uses=d.eagle and d.eagle.uses or nil,icon=d.icon,
        tuned=d.registered_values~=nil,registered=d.registered_values and{cooldown=d.registered_values.cooldown,
            uses=d.registered_values.uses}or{cooldown=d.cooldown,uses=d.uses},
        limits={cooldown={0,M.MAX_COOLDOWN},uses={1,M.MAX_USES}}}
    if a then
        out.carrier={name=a.carrier,stable_id=a.stable_id,type=a.type,family=a.family,beacon=a.beacon,beam=a.beam,
            condensed=a.condensed==true,fallback=a.fallback,local_refused=a.local_refused}
        if a.weapon then
            out.carrier_weapon={name=a.weapon.weapon,stable_id=a.weapon.stable_id,entity=a.weapon.entity,
                level=level_value(d.delivery.level),donor_self=a.weapon.donor_self==true}
        end
    end
    -- The pod: an expendable's carrier weapon's own pod, a carrier pod's carrier's own, a donor's vanilla pod.
    local pod_carrier
    if d.kind=='expendable'then pod_carrier=out.carrier_weapon and out.carrier_weapon.name
    elseif d.kind=='pod'then pod_carrier=out.carrier and out.carrier.name
    elseif d.kind=='support'or d.kind=='sentry'or d.kind=='silo'then pod_carrier=d.delivery.stratagem end
    local spec=d.delivery~='runtime'and d.delivery.pod or nil
    if pod_carrier then
        out.pod=rack_of(pod_carrier)
        out.pod.written=carrier_pod.applied(pod_carrier)
        local items={}
        if spec then
            for _,e in ipairs(spec.entries)do items[#items+1]={item=e.clone and'clone'or e.label,kind=e.kind,count=e.count}end
            local entity=d.kind=='expendable'and out.carrier_weapon and out.carrier_weapon.entity or nil
            local plan=carrier_pod.plan(pod_carrier,pod_units(spec,entity))
            if plan then
                out.pod.slots={}
                for _,l in ipairs(plan.layout)do out.pod.slots[#out.pod.slots+1]={slot=l.slot,item=l.resource,label=l.label}end
            end
        else
            -- The vanilla rack (no pod given): its own items.
            local base=d.kind=='expendable'and d.delivery.deliveries[pod_carrier]or(d.kind~='sentry'and d.delivery)or nil
            for t,i in pairs(base and base.items or{})do items[#items+1]={item=t,kind=i.kind,count=nil}end
            table.sort(items,function(x,y)return tostring(x.item)<tostring(y.item)end)
            out.pod.vanilla=true
            out.pod.count=base and base.count
        end
        out.pod.items=items
    elseif spec then
        out.pod={items={},capacity=d.slots}
        for _,e in ipairs(spec.entries)do out.pod.items[#out.pod.items+1]={item=e.clone and'clone'or e.label,kind=e.kind,
            count=e.count}end
    end
    local reason=avail.state[id]or(not a and refused)or nil
    out.available=reason==nil and(a~=nil or not refused)
    out.reason=reason or(a and a.local_refused)or nil
    for _,st in ipairs(M.status())do if st.id==id then out.state,out.calls=st.state,st.calls end end
    return out
end
-- What the custom panel draws over the native details panel while a card is focused (runtime/custom_stratagem_panel.lua
-- draw_native_focus), in the native details layout: the category line (the native '<SECTION> STRATAGEM PERMIT'), the
-- name and description, a STATS box (call-in time, uses, cooldown and the call-in code, its directions in `code` for the
-- panel's arrows) and ITEM TRAITS. Read-only.
M.KIND_TRAITS={expendable='EXPENDABLE WEAPON',support='SUPPORT WEAPON',pod='SUPPLY POD',sentry='SENTRY',silo='MISSILE SILO',
    eagle='EAGLE',orbital='ORBITAL',orbital_native='ORBITAL',pelican='PELICAN GUNSHIP',runtime='SCRIPTED DELIVERY'}
-- The native CALL-IN TIME is the row's call-in time with the account's upgrades (0x879900), plus a hellpod's travel for a
-- hellpod delivery (0x6ADB40). Every hellpod delivery is the pod 0x73F8498BFFDCF415 (hellpod/hellpod/hellpod_payload),
-- whose HellpodComponentData gives 4.75 s. The upgrades are the account's and not read here: this is the base time.
M.POD_TRAVEL=4.75
M.POD_KINDS={expendable=true,support=true,pod=true,sentry=true,silo=true}
function M.panel_details(id)
    local d=defs[id]
    if not d then return nil end
    local policy=d.alloc_policy or d.policy or{}
    local section=d.kind=='sentry'and'DEFENSIVE'or policy.beacon=='offensive'and'OFFENSIVE'or'SUPPLY'
    local name,description=virtual.strings(d.virtual,'us')
    local words,code={},{}
    for _,v in ipairs(d.code_values or{})do words[#words+1]=calldown.text({v});code[#code+1]=calldown.names({v})[1]end
    local uses='UNLIMITED'
    if d.kind=='eagle'and d.eagle and d.eagle.uses then uses=('%d PER REARM'):format(d.eagle.uses)end
    if d.uses then uses=('%d PER MISSION'):format(d.uses)end
    -- Its carrier: the one allocated for its pick, else the one the availability view would allocate; an expendable
    -- not picked yet, its carrier weapons' own stratagems (each its own beacon carrier) when they agree.
    local a=cache[id]or(group_view.a and group_view.a.assignments[id])
    local entries={a and a.carrier and catalog.stratagems[a.carrier]or nil}
    if not entries[1]and d.kind=='expendable'and type(d.delivery)=='table'then
        for _,n in ipairs(d.delivery.pool or{})do entries[#entries+1]=catalog.stratagems[n]end
    end
    local function carrier_value(semantic)
        local value
        for _,e in ipairs(entries)do
            local mine
            for _,f in ipairs(e.fields or{})do
                if f.semanticFieldId==semantic and type(f.currentDefault)=='number'then mine=f.currentDefault end
            end
            if mine==nil or(value~=nil and value~=mine)then return nil end
            value=mine
        end
        return value
    end
    local cooldown=d.cooldown or carrier_value('stratagem.cooldown')
    cooldown=cooldown and('%d SEC'):format(math.floor(cooldown+0.5))or'AS ITS CARRIER'
    local call_in=carrier_value('stratagem.call_in_time')
    if call_in then
        call_in=call_in+(M.POD_KINDS[d.kind]and M.POD_TRAVEL or 0)
        call_in=('%.2f SEC'):format(math.floor(call_in*20+0.5)/20)
    end
    -- The definition's own traits (spec.traits: CUSTOM STRATAGEM first, up to five rows), else its family's.
    local traits={'CUSTOM STRATAGEM'}
    if d.traits then
        for k,t in ipairs(d.traits)do traits[k]=t end
    else
        local kind=d.kind=='expendable'and d.delivery~='runtime'and d.delivery.variant and'support'or d.kind
        if d.kind=='orbital'and d.orbital and d.orbital.native then kind='orbital_native'end
        traits[#traits+1]=M.KIND_TRAITS[kind]or string.upper(tostring(d.kind))
        if d.delivery~='runtime'and type(d.delivery)=='table'then
            if d.delivery.model then traits[#traits+1]='CUSTOM MODEL'end
            if d.delivery.round then traits[#traits+1]=string.upper(tostring(d.delivery.round.label
                or d.delivery.round.name))..' ROUNDS'end
            if d.delivery.impact then traits[#traits+1]=string.upper(tostring(d.delivery.impact))end
        end
        while#traits>4 do table.remove(traits)end
    end
    return {category=('CUSTOM %s STRATAGEM'):format(section),name=name,description=description,
        stats={{'CALL-IN TIME',call_in or'AS ITS CARRIER'},{'USES',uses},{'COOLDOWN TIME',cooldown},
            {'CALL-IN CODE',table.concat(words,' '),code=code}},traits=traits}
end
-- The carrier groups (runtime/carrier_groups.lua catalogue).
function M.groups()return groups.catalogue()end
function M.instance_of(entity)
    local e=instances.lookup(entity)
    if not e then return nil end
    return {id=e.definition,call_id=e.call_id,n=e.n,role=e.role,player=e.player,parent=e.parent}
end
-- Test seam (offline tests only): the call glue of the payload families.
function M.internals_for_tests()
    return {new_call=new_call,start_capture=start_capture,start_eagle=start_eagle,beacon_event=beacon_event,
        start_mission=start_mission,record_step=record_step,mp_step=mp_step,decide=decide,pending_step=pending_step,
        items_step=items_step,remote_assets_step=remote_assets_step,mp_sync_body=mp_sync_body,mission_end=mission_end,
        calls_step=calls_step,host_call=host_call,ball_scan=ball_scan,call_evidence=call_evidence,reservations_step=reservations_step,blocked_apply=blocked_apply,start_barrage=start_barrage,pelican_call=pelican_call,
        barrage_watch_step=barrage_watch_step,barrage_watch_state=barrage_watch_state,clone_step=clone_step,add_clone=add_clone,
        availability_step=availability_step,allocate=allocate,carrier_map=carrier_map,advance=advance,
        mission=function()return mission end,mpstate=function()return mpstate end,ship=function()return ship end,
        teammates=function()return remote_overlays and remote_overlays.teammates end}
end
function M.reset_for_tests()
    M.default_selection='carrier'
    defs,order,cache,ship,life,clock={},{},{},{key=nil,at=-1,line=nil,status={}},{busy={},due=nil,refused={},retry_at=0},0
    verbose=false;eagles.verbose=false
    mp_ship.at=-math.huge
    avail={state={},text={},at=-math.huge,carrier={},kept={}}
    group_view={key=nil,at=-math.huge}
    if loop then loop.cancel();loop=nil end
    if landing then landing.cancel();landing=nil end
    if remote_overlays then remote_overlays.stop();remote_overlays=nil end
    panel=nil
    mpstate={}
    sync.reset_for_tests()
    observer.reset_for_tests()
    reset_mission()
end
return M
