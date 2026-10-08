"""Generate the builder-facing custom stratagem schema (docs/custom-stratagem-builder.md):

* sdk/CustomStratagemSchema.json: every field a tool (the future ModBuilder) may generate for hd2.custom_stratagem,
  per payload family, with its type, unit, range, default, whether it is supported and which catalogue its donors come
  from; the catalogues themselves (support weapons and backpacks with a reviewed pod rack, sentries, Eagles, orbital
  shells and patterns, explosion donors, carrier families, beacons, directions); and what is refused, with the reason.
* sdk/schemas/custom_stratagems.project.schema.json: the JSON Schema of a custom stratagem project file
  (custom_stratagems.json), which `hd2.py custom-stratagem compile` turns into the mod's src/addon.lua.

The limits and the catalogues are read from the Runtime itself (runtime/custom_stratagems.lua M.LIMITS and its
reviewed donor functions), offline, in HD2's standalone Lua VM (scripts/lua_offline.py): the schema can never claim a
range the Runtime does not enforce. No raw offset or address is written.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from reference_format import lua  # noqa: E402

SCHEMA = ROOT / 'sdk/CustomStratagemSchema.json'
PROJECT_SCHEMA = ROOT / 'sdk/schemas/custom_stratagems.project.schema.json'
FORMAT = 'hd2runtime-custom-stratagems/1'


def modules() -> bytes:
    out = []
    for folder in ['api', 'core', 'runtime', 'schemas', 'domains', 'primary_mapper']:
        for path in sorted((ROOT / folder).glob('*.lua')):
            name = 'hd2runtime/' + path.relative_to(ROOT).with_suffix('').as_posix()
            out.append(('package.preload[' + lua(name) + ']=function(...)\n').encode('utf-8') + path.read_bytes()
                + b'\nend\n')
    return b''.join(out)


PROGRAM = r'''
local json=require('hd2runtime/primary_mapper/json')
local custom=require('hd2runtime/runtime/custom_stratagems')
local weapons=require('hd2runtime/runtime/custom_weapons')
local executor=require('hd2runtime/runtime/bombardment_executor')
local eagles=require('hd2runtime/runtime/custom_eagles')
local donors=require('hd2runtime/runtime/explosion_donors')
local catalog=require('hd2runtime/domains/stratagem_authoring')
local core_assets=require('hd2runtime/core/assets')
local calldown=require('hd2runtime/runtime/calldown_codes')
local A=require('hd2runtime/runtime/carrier_allocator')
local function sorted_names(filter)
    local out={}
    for name,entry in pairs(catalog.stratagems)do if filter(name,entry)then out[#out+1]=name end end
    table.sort(out)
    return out
end
local function package_known(name)
    local e=catalog.stratagems[name]
    local id=e and e.root and e.root.id
    return id~=nil and core_assets.dependencies_for_stratagem(id,name)~=nil and core_assets.call_in_complete(name)==true
end
local out={limits=custom.LIMITS,weapon={rpm=weapons.RPM,spreadMax=weapons.SPREAD_MAX,ammoMax=weapons.AMMO_MAX,
    keys=json.array((function()local k={};for key in pairs(weapons.KEYS)do k[#k+1]=key end;table.sort(k);return k end)())},
    maxShells=executor.MAX_SHELLS,beacons=json.array({'offensive','support','any'}),directions=json.array({'up','down',
    'left','right'})}
-- Support weapons and backpacks whose pod rack is reviewed: the delivery donors.
local support={}
for _,name in ipairs(sorted_names(function(_,e)return e.family=='support'or e.family=='backpack'end))do
    local d,why=custom.support_delivery(name)
    local item={name=name,family=catalog.stratagems[name].family,deliverable=d~=nil,reason=d==nil and why or nil,
        packageKnown=package_known(name),rateSelector=weapons.binds_rate_selector(name)}
    if d then
        item.stableId=d.id
        item.count=d.count
        local items={}
        for kind,i in pairs(d.items)do items[#items+1]={entityType=kind,kind=i.kind,projectile=i.projectile}end
        table.sort(items,function(a,c)return a.entityType<c.entityType end)
        item.items=json.array(items)
        local modifiable=false
        for _,i in ipairs(items)do if i.kind=='weapon'then modifiable=true end end
        item.modifiable=modifiable
    end
    support[#support+1]=item
end
out.supportDonors=json.array(support)
-- The rounds a weapon modification's `projectile` may name: support weapons with one reviewed round and a known
-- call-in package (it becomes an asset).
local rounds={}
for _,name in ipairs(sorted_names(function(_,e)return e.family=='support'end))do
    local kind=custom.weapon_round(name)
    if kind and package_known(name)then rounds[#rounds+1]={name=name,projectile=kind}end
end
out.projectileDonors=json.array(rounds)
-- Clone donors (the expendable family): a support weapon with a reviewed expendable clone class, and its carrier weapon
-- pool in order (runtime/weapon_clone.lua; the first one no lobby member brings and no other custom stratagem holds).
local WC=require('hd2runtime/runtime/weapon_carriers')
-- The reviewed direct damage overrides of a round (domains/direct_damage.lua): its labels, ascending.
local function direct_damage_of(projectile)
    local r=require('hd2runtime/domains/direct_damage').rounds[tostring(projectile)]
    local out={}
    for label in pairs(r and r.overrides or{})do out[#out+1]=tonumber(label)end
    table.sort(out)
    return out
end
local clones={}
for _,name in ipairs(custom.clone_donors())do
    local pool={}
    for k,c in ipairs(WC.pool(name))do pool[k]={name=c.name,stableId=c.stable_id}end
    clones[#clones+1]={name=name,stableId=catalog.stratagems[name].root.id,
        projectile=require('hd2runtime/runtime/weapon_clone').donor(name).projectile,pool=json.array(pool),
        rounds=json.array(require('hd2runtime/runtime/weapon_clone').rounds(name)),packageKnown=package_known(name),
        directDamage=json.array(direct_damage_of(require('hd2runtime/runtime/weapon_clone').donor(name).projectile))}
end
out.cloneDonors=json.array(clones)
-- Sentries: the chassis a sentry payload deploys.
local sentries={}
for _,name in ipairs(sorted_names(function(_,e)return e.family=='sentry'end))do
    local e=catalog.stratagems[name]
    local ok=e.deployedEntity~=nil and e.deployedEntity.resource~=nil and e.root~=nil
    sentries[#sentries+1]={name=name,stableId=e.root and e.root.id,supported=ok,
        deployedEntity=ok and tostring(e.deployedEntity.resource):gsub('^0x',''):upper()or nil}
end
out.sentryDonors=json.array(sentries)
-- Eagles: reviewed jets, strikes and uses.
local eagle_list={}
for name,e in pairs(eagles.EAGLES)do
    local replaceable=e.strikeProjectile~=nil and e.rocket~=nil and e.rocket.impact>0 and e.rocket.expiry==0
    eagle_list[#eagle_list+1]={name=name,stableId=e.stableId,uses=e.uses,cooldown=e.cooldown,
        strikeProjectile=e.strikeProjectile,impactExplosionReplaceable=replaceable}
end
table.sort(eagle_list,function(a,c)return a.name<c.name end)
out.eagleDonors=json.array(eagle_list)
-- Orbitals: a reviewed bombardment record is both a shell donor and a pattern donor.
local orbitals={}
for _,name in ipairs(sorted_names(function(_,e)return e.family=='orbital'end))do
    local p=executor.pattern_of(name)
    if p then
        orbitals[#orbitals+1]={name=name,stableId=catalog.stratagems[name].root.id,packageKnown=package_known(name),
            pattern={salvos=p.salvos,shells_per_salvo=p.shells_per_salvo,shell_interval=p.shell_delay,
            shell_interval_random=p.shell_delay_random,salvo_interval=p.salvo_delay,salvo_interval_random=p.salvo_delay_random,
            scatter=p.scatter,salvo_scatter=p.salvo_scatter}}
    end
end
out.orbitals=json.array(orbitals)
-- Explosion donors.
local ex={}
for _,name in ipairs(donors.names())do
    local d=donors.DONORS[name]
    ex[#ex+1]={name=name,explosion=d.explosion,shell=d.shell,effect=d.effect}
end
out.explosionDonors=json.array(ex)
-- Carrier families (the catalogue's) and every catalogued stratagem name (exclusions, assets).
local fam={}
for _,e in pairs(catalog.stratagems)do if e.family then fam[e.family]=true end end
local families={}
for f in pairs(fam)do families[#families+1]=f end
table.sort(families)
out.carrierFamilies=json.array(families)
out.stratagems=json.array(sorted_names(function(_,e)return e.root~=nil end))
-- Carrier groups (runtime/carrier_groups.lua): the pools a definition's carrier is drawn from.
local G={}
for _,g in ipairs(require('hd2runtime/runtime/carrier_groups').catalogue())do
    G[#G+1]={name=g.name,beacon=g.beacon,families=g.families and json.array(g.families)or nil,pod=g.pod,
        weapon=g.weapon,eagle=g.eagle,doc=g.doc,payloads=json.array(g.payloads),defaults=json.array(g.defaults)}
end
out.carrierGroups=json.array(G)
-- Carrier pod items and carriers (domains/carrier_pod_items.lua): what a carrier's own pod may hold, and each exclusive
-- carrier rack's capacity and slot roles.
local P=require('hd2runtime/domains/carrier_pod_items')
local items={}
for key,e in pairs(P.items)do
    if e.supported then
        items[#items+1]={key=key,name=e.label,kind=e.kind,role=P.kinds[e.kind].role,status=e.status,
            acknowledgement=e.status=='unverified'and'allow_unverified_effect'or nil,
            rateSelector=e.kind=='support_weapon'and weapons.binds_rate_selector(e.label)or nil}
    end
end
table.sort(items,function(a,c)return a.key<c.key end)
out.podItems=json.array(items)
local carriers={}
for name,r in pairs(P.racks)do carriers[#carriers+1]={name=name,capacity=r.capacity,roles=json.array(r.roles)}end
table.sort(carriers,function(a,c)return a.name<c.name end)
out.podCarriers=json.array(carriers)
-- The Pelican family (pelican = {hover, orbit, gun, approach}; runtime/pelican_gunship.lua, api/pelican.lua): its limits
-- and its gun's dropdowns (rounds, sounds, the explosion donors a gun may take).
local PL=require('hd2runtime/runtime/pelicans')
local gunship=require('hd2runtime/runtime/pelican_gunship')
local pweapon=require('hd2runtime/runtime/pelican_weapon')
local papi=require('hd2runtime/api/pelican')
local function sorted_keys(t)local o={};for k in pairs(t)do o[#o+1]=k end;table.sort(o);return json.array(o)end
local orbit={}
for _,key in ipairs({'radius','altitude','duration','period','entry'})do
    orbit[key]={min=PL.ORBIT[key][1],max=PL.ORBIT[key][2],default=gunship.ORBIT_DEFAULTS[key]}
end
local gun_donors={}
for _,name in ipairs(donors.names({gun=true}))do
    local d=donors.DONORS[name]
    gun_donors[#gun_donors+1]={name=name,kind=d.automatic and'automatic'or'slow',maxRpm=d.max_rpm}
end
out.pelican={maxHover=papi.MAX_HOVER,orbit=orbit,approach={distance={min=0,max=papi.MAX_APPROACH_DISTANCE,
    default=papi.APPROACH_DISTANCE},height={min=0,max=papi.MAX_APPROACH_HEIGHT,default=papi.APPROACH_HEIGHT}},
    rounds=sorted_keys(gunship.ROUNDS),rateMultipliers=sorted_keys(pweapon.RATE_FACTORS),spreadMax=pweapon.SPREAD_MAX,
    aimHeightMax=gunship.AIM_HEIGHT_MAX}
out.pelicanSounds=json.array(require('hd2runtime/runtime/weapon_sounds').names())
out.pelicanExplosionDonors=json.array(gun_donors)
-- Every native stratagem code (domains/stratagem_calldown.lua nativeCodes, by stable id): a custom code equal to one is
-- refused at registration; one that starts or extends a catalogued (selectable) stratagem's is refused in every mission
-- where that stratagem can be picked.
local C=require('hd2runtime/domains/stratagem_calldown')
local by_id={}
for name,e in pairs(catalog.stratagems)do if e.root and e.root.id then by_id[e.root.id]=name end end
local natives={}
for id,code in pairs(C.nativeCodes)do
    local n=tonumber(id)
    natives[#natives+1]={stableId=n,name=by_id[n],catalogued=by_id[n]~=nil,code=json.array(calldown.names(code))}
end
table.sort(natives,function(a,c)return a.stableId<c.stableId end)
out.nativeCodes=json.array(natives)
-- Silos (runtime/custom_silos.lua): the donor silos whose rack items (the missile, the remote) are reviewed; the
-- explosions a silo's blast may name (the reviewed spawn set, hd2.explosions.reviewed(): those whose packages are known).
local silos=require('hd2runtime/runtime/custom_silos')
local silo_list={}
for _,name in ipairs(silos.names())do
    local s=silos.SILOS[name]
    silo_list[#silo_list+1]={name=name,stableId=s.id,packageKnown=package_known(name),detonation=s.missile.detonation}
end
out.siloDonors=json.array(silo_list)
local blasts={}
local A=require('hd2runtime/api/actions')
for _,e in ipairs(A.explosions.reviewed())do
    if e.assets_known then
        blasts[#blasts+1]={name=e.name,source=e.source,type=A.explosion_target(e.name).type,objective=e.objective}
    end
end
out.blastExplosions=json.array(blasts)
-- Weapon variants (delivery.family = 'weapon'; runtime/weapon_clone.lua variant, domains/weapon_variants.lua): each
-- host and the rounds it may fire: catalogued, live-tested projectile outputs of its own compatibility class whose
-- package is known (exactly what variant_spec accepts), by output id (hd2.attack_output takes it).
local WCL=require('hd2runtime/runtime/weapon_clone')
local AO=require('hd2runtime/domains/attack_outputs')
local variant_list={}
for _,name in ipairs(WCL.variants())do
    local host=WCL.variant(name)
    local own
    for _,o in pairs(AO.outputs)do
        if o.family=='projectile'and o.owner and o.owner.name==name and not o.unverifiedDonor
            and o.currentDefault==host.projectile then own=o end
    end
    local rounds={}
    if own then
        for id,o in pairs(AO.outputs)do
            if id~=own.id and o.family=='projectile'and o.editable and type(o.currentDefault)=='number'
                and not o.unverifiedDonor and o.compatibilityClass==own.compatibilityClass and o.dependencyKey
                and core_assets.dependency(o.dependencyKey)then
                rounds[#rounds+1]={output=id,label=o.owner and o.owner.name or id}
            end
        end
    end
    table.sort(rounds,function(a,c)return a.output<c.output end)
    -- shared: who else brings the type (world loot, another pod): then allow_shared; deliverable: its own pod is an
    -- authored support delivery (else registration refuses, with the reason); round: whether it has a ProjectileWeapon.
    local delivery,why=custom.support_delivery(name)
    variant_list[#variant_list+1]={name=name,stableId=catalog.stratagems[name].root.id,projectile=host.projectile,
        compatibilityClass=own and own.compatibilityClass or nil,rounds=json.array(rounds),packageKnown=package_known(name),
        round=host.round~=nil,shared=host.shared and json.array(host.shared)or nil,deliverable=delivery~=nil,
        refused=delivery==nil and tostring(why)or nil}
end
out.variantDonors=json.array(variant_list)
out.uses={min=1,max=custom.MAX_USES}
out.maxPerPlayer=custom.MAX_PER_PLAYER
out.traits={max=custom.MAX_TRAITS,length=custom.TRAIT_LENGTH}
return json.encode(out)
'''


def runtime_facts() -> dict:
    from lua_offline import execute
    raw = execute(modules() + PROGRAM.encode('utf-8'))
    return json.loads(raw.decode('utf-8'))


def rng(lo, hi, integer=False, unit=None, exclusive_min=False):
    out = {'type': 'integer' if integer else 'number', 'min': lo, 'max': hi}
    if exclusive_min:
        out['exclusiveMin'] = True
    if unit:
        out['unit'] = unit
    return out


def build(facts: dict | None = None) -> dict:
    facts = facts or runtime_facts()
    L = facts['limits']
    W = facts['weapon']
    version = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
    weapon_fields = {
        'projectile': {'type': 'projectile_donor', 'catalog': 'projectileDonors', 'reviewedDonor': True, 'optional': True,
            'doc': 'the round a support weapon fires (its name); its call-in package becomes an asset'},
        'rpm': dict(rng(W['rpm'][0], W['rpm'][1], unit='rounds per minute'), optional=True,
            doc='its own rate slot and current rate (times the mission factor the game applied); refused for a type '
                'that binds a rate-of-fire selector'),
        'spread': dict(rng(0, W['spreadMax'], unit='milliradians (full width)', exclusive_min=True), optional=True,
            doc='its own WeaponData instance spread, both axes'),
        'ammo': dict(rng(1, W['ammoMax'], integer=True, unit='rounds per magazine'), optional=True,
            doc='its own magazine copy (an 11-bit network field: at most 2047)'),
        'recoil': {'type': 'enum', 'values': ['zero'], 'optional': True, 'doc': 'zero aim recoil (its own instance)'},
    }
    sentry_weapon_fields = dict(weapon_fields)
    sentry_weapon_fields['sound'] = {'type': 'enum', 'values': facts['pelicanSounds'], 'catalog': 'pelicanSounds',
        'optional': True, 'doc': 'its firing sound: a name of the weapon sound catalogue (docs/weapon-sounds.md), on its '
        'own weapon copy; the stratagem that provides the sound\'s bank becomes an asset'}
    support_modify = dict(weapon_fields)
    support_modify['impact_explosion'] = {'type': 'explosion_donor', 'catalog': 'explosionDonors', 'reviewedDonor': True,
        'optional': True, 'doc': 'each converted projectile requests the donor explosion on impact (its own copy)'}
    support_modify['rounds'] = dict(rng(L['rounds'][0], L['rounds'][1], integer=True, unit='projectiles per weapon'),
        optional=True, default=1, doc='how many of each weapon\'s projectiles convert (with impact_explosion)')
    expendable_modify = {k: v for k, v in support_modify.items() if k != 'projectile'}
    damage_values = sorted({v for c in facts['cloneDonors'] for v in c.get('directDamage', [])})
    expendable_modify['direct_damage'] = {'type': 'enum', 'values': damage_values, 'optional': True,
        'doc': 'the damage of each round\'s direct hit: a reviewed override of the donor\'s own round '
        '(cloneDonors[].directDamage; the EAT-17\'s 500 = 500 / 500), written per round with impact_explosion (required '
        'with it); not with round. Not live-proven'}
    PL = L['pod']
    pod_item = {
        'item': {'type': 'pod_item', 'catalog': 'podItems', 'reviewedDonor': True, 'required': True,
            'doc': 'a podItems key (support_weapon/<name>, backpack/<name>, player_weapon/<name>); an expendable pod also '
                   'takes "clone" (its carrier weapon, the clone)'},
        'count': dict(rng(PL['count'][0], PL['count'][1], integer=True, unit='items'), optional=True, default=1),
        'modify': {'type': 'object', 'optional': True, 'fields': support_modify,
            'doc': 'a weapon item only (no backpack field is reviewed); impact_explosion and rounds for support '
                   'weapons with a reviewed round'},
        'allow_unverified_effect': {'type': 'boolean', 'optional': True,
            'doc': 'required for a podItems entry with status "unverified" (a primary: not live-tested), refused '
                   'otherwise'}}
    O = L['orbital']
    PE = facts['pelican']
    pelican_gun = {
        'round': {'type': 'enum', 'values': PE['rounds'], 'optional': True, 'default': 'standard',
            'doc': 'native: the chin turret\'s own autocannon round; standard: the Gatling Sentry\'s; ap4: the MG-206\'s '
                   'armor-piercing round; strafing_run / strafing_run_pattern: the Eagle Strafing Run\'s'},
        'behave_as': {'type': 'enum', 'values': ['gatling_sentry'], 'optional': True,
            'doc': 'the Gatling Sentry\'s AI (continuous fire, the Runtime target lock); without it the chin turret '
                   'keeps its own burst AI'},
        'rate_multiplier': {'type': 'enum', 'values': PE['rateMultipliers'], 'optional': True, 'default': 1,
            'doc': 'times the Gatling Sentry\'s rate (with behave_as)'},
        'rpm': dict(rng(30, 3000, unit='rounds per minute'), optional=True,
            doc='an explicit rate for the Gatling AI (with behave_as, without rate_multiplier); a slow explosion donor '
                'needs it at most the donor\'s maxRpm'),
        'casing': {'type': 'enum', 'values': ['gatling', 'own'], 'optional': True,
            'doc': 'the casings it ejects: the Gatling Sentry\'s (with behave_as, the default) or its own'},
        'spread': dict(rng(0, PE['spreadMax'], unit='milliradians (full width)', exclusive_min=True), optional=True),
        'recoil': {'type': 'enum', 'values': [False], 'optional': True, 'doc': 'false: no aim recoil'},
        'unlimited_ammo': {'type': 'enum', 'values': [True], 'optional': True},
        'face_target': {'type': 'enum', 'values': [True], 'optional': True,
            'doc': 'the Pelican turns its nose to the target (with behave_as)'},
        'sound': {'type': 'enum', 'values': facts['pelicanSounds'], 'catalog': 'pelicanSounds', 'optional': True,
            'doc': 'a firing sound of the catalogue (docs/weapon-sounds.md); without it the turret\'s own'},
        'impact_explosion': {'type': 'explosion_donor', 'catalog': 'pelicanExplosionDonors', 'reviewedDonor': True,
            'optional': True, 'doc': 'each round\'s own impact: an automatic donor, or a slow one with rpm at most its '
                                     'maxRpm'},
        'aim_height': dict(rng(0, PE['aimHeightMax'], unit='metres above the target\'s feet'), optional=True,
            doc='where it aims (with behave_as); 0: the game\'s own aim node'),
    }
    families = [
        {'family': 'script', 'apiField': 'delivery', 'builder': False,
         'doc': "delivery = 'runtime': the carrier delivers nothing and the mod delivers in Lua callbacks (on_activate, "
                'ctx:barrage, hd2.pelican.spawn, ...). The advanced escape hatch: not representable in a builder '
                'project.', 'carrier': {'beacon': ['offensive', 'support', 'any']}},
        {'family': 'support', 'apiField': 'delivery', 'builder': True,
         'doc': 'the donor\'s own vanilla support pod; exactly the items its rack holds are captured and modified on '
                'their own records',
         'carrier': {'beacon': ['support']},
         'fields': {
             'items': {'type': 'list', 'min': L['items'][0], 'max': 1, 'required': True, 'item': {
                 'donor': {'type': 'support_donor', 'catalog': 'supportDonors', 'reviewedDonor': True, 'required': True,
                     'doc': 'a support weapon or backpack with a reviewed pod rack (deliverable = true)'},
                 'count': {'type': 'integer', 'optional': True, 'doc': 'must equal the donor rack\'s own count '
                     '(supportDonors[].count); another count is refused'},
                 'modify': {'type': 'object', 'optional': True, 'fields': support_modify,
                     'doc': 'only donors with a weapon (modifiable = true); no backpack field is reviewed'}},
                 'doc': 'one donor per call (one native pod delivers one rack)'}}},
        {'family': 'expendable', 'apiField': 'delivery', 'builder': True,
         'doc': 'a mission-scoped CLONE of the donor weapon: an unused carrier weapon of the donor\'s expendable class '
                '(cloneDonors[].pool, the first free) becomes the donor for the mission (presentation, model, '
                'animations, round, sounds, handling) and is delivered by its own vanilla pod, whose row presents as '
                'the custom stratagem; restored aboard the ship. Unavailable (warned, not pickable, unpicked) while '
                'every pool weapon is a lobby member\'s native pick or another custom stratagem\'s carrier weapon',
         'fields': {
             'weapon': {'type': 'clone_donor', 'catalog': 'cloneDonors', 'reviewedDonor': True, 'required': True,
                 'doc': 'the donor weapon (a support weapon with a reviewed expendable clone class)'},
             'presentation': {'type': 'object', 'optional': True, 'fields': {
                 'name': {'type': 'string', 'minLength': 1, 'maxLength': L['text'], 'optional': True,
                     'default': 'the custom stratagem\'s name', 'doc': 'the name its pickup prompt, map label and '
                     'weapon panel show; \'donor\': the donor\'s own'},
                 'icon': {'type': 'string', 'optional': True, 'default': 'the custom stratagem\'s icon',
                     'doc': 'an image id (images/<id>.png) for its marker and prompt icon; \'donor\': the donor\'s '
                     'own'}},
                 'doc': 'what the carrier weapon shows; a Runtime text or icon the game cannot show is borrowed from '
                        'the donor (logged)'},
             'modify': {'type': 'object', 'optional': True, 'fields': expendable_modify,
                 'doc': 'per call, on the call\'s own launchers only (as a support delivery\'s)'},
             'round': {'type': 'support_donor', 'catalog': 'cloneDonors', 'reviewedDonor': True, 'optional': True,
                 'doc': 'another support weapon\'s round the clone fires (a cloneDonors[].rounds name, e.g. the RL-77 '
                        'Airburst\'s on an EAT-17 clone); not with modify.impact_explosion'},
             'level': {'type': 'enum', 'values': L['expendable']['levels'], 'optional': True, 'default': 'full',
                 'doc': 'development staging: presentation only; + model and animations; full (+ the donor\'s round, '
                        'sounds and handling)'}},
         'carrier': {'beacon': ['support']},
         'notes': ['CONDENSED: the carrier weapon\'s own stratagem carries the beacon too (one vanilla stratagem); a '
                   'separate support carrier only when that stratagem cannot (e.g. not owned)',
                   'its pod: familyOptions.expendable.pod']},
        {'family': 'sentry', 'apiField': 'sentry', 'builder': True,
         'doc': 'the donor sentry\'s own vanilla pod; exactly that pod\'s sentry is captured and its own weapon '
                'configured',
         'carrier': {'beacon': ['support'], 'allowFamilies': ['sentry']},
         'fields': {
             'donor': {'type': 'sentry_donor', 'catalog': 'sentryDonors', 'reviewedDonor': True, 'required': True},
             'weapon': {'type': 'object', 'optional': True, 'fields': sentry_weapon_fields}}},
        {'family': 'eagle', 'apiField': 'eagle', 'builder': True,
         'doc': 'the donor Eagle\'s own strike from an Eagle carrier; the slot is an Eagle fleet member with its own uses; '
                'the call\'s rockets are those of its jet\'s mounted pods (live-proven)',
         'carrier': {'beacon': ['offensive'], 'allowFamilies': ['eagle']},
         'fields': {
             'donor': {'type': 'eagle_donor', 'catalog': 'eagleDonors', 'reviewedDonor': True, 'required': True},
             'uses': dict(rng(L['eagle']['uses'][0], L['eagle']['uses'][1], integer=True, unit='uses per rearm'),
                 optional=True, default='the donor\'s uses'),
             'rearm_seconds': dict(rng(L['eagle']['rearm_seconds'][0], L['eagle']['rearm_seconds'][1],
                 unit='seconds'), optional=True, default='Eagle Rearm\'s own cooldown',
                 doc='the Runtime rearm when no native Eagle is in the loadout'),
             'payload': {'type': 'object', 'optional': True, 'fields': {
                 'impact_explosion': {'type': 'explosion_donor', 'catalog': 'explosionDonors', 'reviewedDonor': True,
                     'optional': True, 'doc': 'only donors with impactExplosionReplaceable = true'}}}},
         'notes': ['cooldown is refused: an Eagle keeps its native cooldown and rearm']},
        {'family': 'orbital', 'apiField': 'orbital', 'builder': True,
         'doc': 'a Runtime bombardment of a reviewed shell in a reviewed (or explicit) pattern at the activation; or, '
                'with native = true, the pattern donor\'s own native barrage (every player\'s machine fires it) with each '
                'of its shells exploding as impact_explosion\'s on every compatible machine\'s own copy',
         'carrier': {'beacon': ['offensive', 'support', 'any']},
         'fields': {
             'native': {'type': 'boolean', 'optional': True, 'default': False,
                 'doc': 'true: the pattern donor\'s own barrage (the beacon\'s delivery becomes the donor\'s); only pattern '
                        'and impact_explosion (required) apply. The form multiplayer mirrors on every machine'},
             'shell': {'type': 'orbital_donor', 'catalog': 'orbitals', 'reviewedDonor': True, 'optional': True,
                 'doc': 'required unless native: its first shell is fired; its package becomes an asset'},
             'pattern': {'type': 'orbital_donor', 'catalog': 'orbitals', 'reviewedDonor': True, 'optional': True,
                 'default': 'Orbital 120mm HE Barrage', 'doc': 'the vanilla pattern the fields below override'},
             'salvos': dict(rng(O['salvos'][0], O['salvos'][1], integer=True), optional=True),
             'shells_per_salvo': dict(rng(O['shells_per_salvo'][0], O['shells_per_salvo'][1], integer=True),
                 optional=True),
             'shell_interval': dict(rng(O['shell_interval'][0], O['shell_interval'][1], unit='seconds'),
                 optional=True, doc='exact (no random part)'),
             'salvo_interval': dict(rng(O['salvo_interval'][0], O['salvo_interval'][1], unit='seconds'),
                 optional=True, doc='exact (no random part)'),
             'scatter': dict(rng(O['scatter'][0], O['scatter'][1], unit='the pattern record\'s own units'),
                 optional=True, doc='per-shell scatter half-width (the 120mm\'s is 27)'),
             'salvo_scatter': dict(rng(O['salvo_scatter'][0], O['salvo_scatter'][1],
                 unit='the pattern record\'s own units'), optional=True),
             'impact_explosion': {'type': 'explosion_donor', 'catalog': 'explosionDonors', 'reviewedDonor': True,
                 'optional': True, 'doc': 'each shell\'s own impact copy (required with native)'}},
         'notes': ['salvos x shells_per_salvo is at most %d' % O['total'],
                   'native: the Runtime bombardment\'s shells exist on the caller\'s machine only; a native barrage is '
                   'every player\'s']},
        {'family': 'pelican', 'apiField': 'pelican', 'builder': True,
         'doc': 'the Runtime\'s Pelican CAS as data (hd2.pelican.spawn\'s hover, orbit, gun and approach): the carrier\'s '
                'own delivery is neutralized and, at the activation, a Pelican flies to the beacon, holds over it and '
                'fights with its own chin turret, configured on its own copies. With several players the session host '
                'spawns it for whoever called it and every compatible machine mirrors its chin gun',
         'carrier': {'beacon': ['offensive', 'support', 'any']},
         'fields': {
             'hover': dict(rng(0, PE['maxHover'], unit='seconds over the beacon', exclusive_min=True), required=True),
             'orbit': {'type': 'object', 'optional': True, 'fields': {key: dict(rng(v['min'], v['max'],
                 unit='metres' if key in ('radius', 'altitude') else 'seconds'), optional=True, default=v['default'])
                 for key, v in PE['orbit'].items()},
                 'doc': 'circles the beacon after arriving (radius, altitude above it, duration, period of one lap, '
                        'entry: the spiral-in seconds, shorter than duration); without it, it holds still'},
             'gun': {'type': 'object', 'optional': True, 'fields': pelican_gun,
                 'doc': 'its chin turret, on its own copies; without it (or with round = native and nothing else) the '
                        'Pelican\'s own autocannon and AI, its kills credited to the caller'},
             'approach': {'type': 'object', 'optional': True, 'fields': {
                 'distance': dict(rng(0, PE['approach']['distance']['max'], unit='metres'), optional=True,
                     default=PE['approach']['distance']['default']),
                 'height': dict(rng(0, PE['approach']['height']['max'], unit='metres'), optional=True,
                     default=PE['approach']['height']['default'])},
                 'doc': 'where it is created: back from the beacon along its heading and up'}},
         'notes': ['the Pelican Gatling, Gas and EMS examples use behave_as = gatling_sentry; the Pelican Cannon uses '
                   'round = native (the vanilla autocannon); round = native alone leaves the chin turret exactly as the '
                   'game spawned it, on every machine (only its kill credit is set)']},
        {'family': 'silo', 'apiField': 'silo', 'builder': True,
         'doc': 'the donor silo\'s own vanilla pod (the support redirect): its silo and laser remote, launched as the '
                'donor\'s; where exactly this call\'s missile detonates, the session host requests the blast explosion '
                '(the missile\'s own blast stays). With several players the caller publishes its missile and the host '
                'requests the blast for it',
         'carrier': {'beacon': ['support']},
         'fields': {
             'donor': {'type': 'silo_donor', 'catalog': 'siloDonors', 'reviewedDonor': True, 'required': True},
             'blast': {'type': 'explosion', 'catalog': 'blastExplosions', 'required': True,
                 'doc': 'the explosion requested at the detonation (a blastExplosions name); its packages load at '
                        'mission start, before the custom stratagem can be called'},
             'fallback': {'type': 'explosion', 'catalog': 'blastExplosions', 'optional': True,
                 'doc': 'requested instead when the blast\'s packages are not resident on the host'}},
         'notes': ['an objective explosion (blastExplosions[].objective) ships in objective packages: the Cyborg '
                   'Production Unit\'s are two packages of about 300 MB, loaded at mission start',
                   'the blast is credited to the session host\'s player (the request is the host\'s)']},
    ]
    # 0.30.0-dev additions, beside the families list (unchanged for tools that read it): the carrier pod payload family
    # and the expendable family's pod option.
    pod_family = (
        {'family': 'pod', 'apiField': 'delivery', 'builder': True,
         'doc': 'a CARRIER POD: the carrier\'s OWN pod (no beacon redirect), its exclusive rack holding these items for '
                'the mission (written at mission start, restored aboard the ship); the carrier is a support_pod group '
                'member whose rack holds them (podCarriers: capacity and slot roles). Solo host only in this build',
         'carrier': {'beacon': ['support'], 'groups': ['support_pod']},
         'fields': {
             'items': {'type': 'list', 'min': PL['items'][0], 'max': PL['items'][1], 'required': True, 'item': pod_item,
                 'doc': 'each item once (give it a count); at most 8 items in all; the carrier\'s capacity decides'}},
         'notes': ['compiles to delivery = {family = \'support\', items = {{item = ...}}}',
                   'a weapon item goes in a weapon slot, a backpack in a backpack slot (the rack\'s own roles)']})
    # 0.30.0-dev (r44): the weapon variant family, beside the families list like the pod family.
    VD = facts['variantDonors']
    variant_family = {
        'family': 'weapon', 'apiField': 'delivery', 'builder': True,
        'doc': 'a mission-scoped VARIANT of a support weapon on its OWN type (no clone carrier; any variantDonors[] '
               'host whose deliverable is true): its presentation, its round (another output of its own compatibility '
               'class; none for a host whose round is false) and optionally the mod\'s own model change for the mission '
               'and are restored aboard the ship. Its own vanilla pod delivers it with its own items (the Maxigun\'s '
               'backpack too). No fallback: while a lobby member brings it natively the variant is unavailable, and a '
               'selected variant blocks it in the native picker. A host with shared[] (world loot or another pod also '
               'brings the type: those copies convert too) needs allow_shared = true',
        'carrier': {'beacon': ['support'], 'groups': ['weapon']},
        'fields': {
            'weapon': {'type': 'variant_donor', 'catalog': 'variantDonors', 'reviewedDonor': True, 'required': True,
                'doc': 'a reviewed variant host (variantDonors[].name)'},
            'round': {'type': 'attack_output', 'catalog': 'variantDonors', 'optional': True,
                'doc': 'a variantDonors[].rounds[].output of that host (compiled to hd2.attack_output(output)); its '
                       'package loads first; without it the host\'s own round'},
            'presentation': {'type': 'object', 'optional': True, 'fields': {
                'name': {'type': 'string', 'minLength': 1, 'maxLength': L['text'], 'optional': True,
                    'default': 'the custom stratagem\'s name'},
                'icon': {'type': 'string', 'optional': True, 'default': 'the custom stratagem\'s icon',
                    'doc': 'an image id (images/<id>.png)'}},
                'doc': 'what the weapon shows for the mission (pickup prompt, map label, weapon panel)'},
            'model': {'type': 'model', 'optional': True,
                'doc': 'the id of one of the mod\'s models (models/<id>.json, a Runtime-owned unit beside the vanilla '
                       'one: docs/custom-models.md); a builder without a model pipeline leaves it out'},
            'allow_shared': {'type': 'boolean', 'optional': True,
                'doc': 'required true for a host with shared[] (variantDonors[].shared): the author\'s consent that '
                       'world loot and other pods\' copies of the type convert too; never added by a builder'},
            'model_use': {'type': 'enum', 'values': ['apply', 'check'], 'optional': True, 'default': 'apply',
                'doc': 'apply: the weapon shows the model; check: only checks at mission start that the model is '
                       'loaded and exact (the vanilla model stays). Needs model. (A Lua mod may pass a Mod Options '
                       'choice of these.)'}},
        'notes': ['compiles to delivery = {family = \'weapon\', ...}', 'live-proven solo on the M-1000 Maxigun (the '
                  'LAS-1000 Laser Maxigun: the LAS-58 Talon\'s round and a debug model); every other host is offline '
                  'only; not tried with several players']}
    # How far each payload family is live-tested (a builder's badges; docs/live-evidence.md and
    # docs/custom-stratagem-api.md hold the detail). live: used in real missions; partial: some of it; offline: built and
    # tested offline only.
    family_evidence = {
        'support': {'status': 'live', 'multiplayer': 'live', 'doc': 'the Gas EAT example (a support pod, its launchers '
            'converted), solo and with two players'},
        'expendable': {'status': 'live', 'multiplayer': 'live', 'evidence': ['custom_stratagem_expendable_clone',
            'custom_stratagem_expendable_payload', 'custom_stratagem_expendable_availability'],
            'doc': 'the EAT-40 Expendable Gas clone; two players r43'},
        'weapon': {'status': 'live', 'multiplayer': 'untested', 'evidence': ['custom_stratagem_weapon_variant'],
            'doc': 'the Laser Maxigun, solo'},
        'sentry': {'status': 'partial', 'multiplayer': 'pending', 'evidence': ['custom_stratagem_sentry_multiplayer'],
            'doc': 'the HMG sentry used live; its several-player mirror and firing sound not confirmed'},
        'eagle': {'status': 'live', 'multiplayer': 'host only', 'doc': 'the Eagle Stun Rocket Pods, solo; not yet tried '
            'with the carrier in the slot (the r44 default)'},
        'orbital': {'status': 'live', 'multiplayer': 'live', 'evidence': ['stratagem_carrier_bombardment_pattern',
            'stratagem_carrier_shell_redirect'], 'doc': 'native barrages (the Orbital Gas Barrage) solo and with two '
            'players; the Runtime bombardment (shell) solo, host only'},
        'pelican': {'status': 'live', 'multiplayer': 'live', 'evidence': ['custom_stratagem_pelican_native_gun'],
            'doc': 'the Gatling Pelican (round, rate, aim, kill credit) solo and with two players; explosive rounds and '
            'the slow payload guns (EMS, gas) offline only'},
        'silo': {'status': 'partial', 'multiplayer': 'live', 'evidence': ['custom_stratagem_silo'],
            'doc': 'the Shredder Silo with two players (r43); the blast near a Gatling Pelican crashed the host (fixed '
            'offline in r44)'},
        'pod': {'status': 'offline', 'multiplayer': 'unsupported', 'doc': 'a carrier pod: solo host only, not '
            'live-tested'},
        'script': {'status': 'live', 'multiplayer': 'per mod', 'doc': 'delivery = \'runtime\': the mod\'s own Lua'},
    }
    selection = {
        'field': None,
        'doc': 'what a pick writes into the loadout slot. Since r44 every custom stratagem\'s CARRIER itself (no option '
               'in a project): the slot shows the custom name and icon on the loading screen and in the mission, with '
               'the game\'s own cooldown and use counter, on every machine. The Runtime falls back to the Orbital '
               'Precision Strike token, converted at mission start, when several players are in the lobby without '
               'custom multiplayer, while custom multiplayer is still WAITING (a player joining: pick again once it is '
               'ENABLED), or when no carrier is known yet. A Lua mod may pass selection = \'token\' (development)',
        'evidence': ['custom_stratagem_carrier_in_slot'],
        'status': 'live (two players, r43); the r44 default not re-tested'}
    schema = {
        'schemaVersion': 1,
        'hd2RuntimeVersion': version,
        'format': FORMAT,
        'status': 'development (0.30.0-dev): every payload family runs on the host; with several players (custom '
                  'multiplayer: every player runs the same Runtime and mods) a client runs its support, expendable, '
                  'sentry and silo deliveries and native orbitals, and the host spawns its Pelican and requests its silo '
                  'blast; Eagles and the Runtime bombardment stay host-only (docs/custom-stratagem-api.md, "Several '
                  'players"). Per family: familyEvidence',
        'api': 'hd2.custom_stratagem.register',
        'metadata': {
            'id': {'type': 'string', 'pattern': L['id']['pattern'], 'maxLength': L['id']['max'], 'required': True,
                'doc': 'unique across every mod'},
            'name': {'type': 'string', 'minLength': 1, 'maxLength': L['text'], 'required': True, 'doc': 'the HUD name'},
            'name_cased': {'type': 'string', 'minLength': 1, 'maxLength': L['text'], 'optional': True,
                'default': 'name', 'doc': 'the panel\'s and loadout\'s name'},
            'description': {'type': 'string', 'minLength': 1, 'maxLength': L['description'], 'required': True},
            'icon': {'type': 'image', 'required': True,
                'doc': 'the id of the mod\'s images/<id>.png (256 x 256): the build compiles it into the mod\'s own '
                       'archive (docs/custom-images.md)'},
            'code': {'type': 'list', 'item': {'type': 'enum', 'values': facts['directions']}, 'min': L['code'][0],
                'max': L['code'][1], 'required': True,
                'doc': 'never equal to, the start of, or started by another custom stratagem\'s code or a native one'},
            'cooldown': dict(rng(L['cooldown'][0], L['cooldown'][1], unit='seconds from the call-in\'s arrival',
                exclusive_min=True), optional=True, default='the carrier\'s own'),
            'assets': {'type': 'list', 'item': {'type': 'stratagem', 'catalog': 'stratagems'}, 'optional': True,
                'doc': 'extra call-in packages the payload needs; a payload\'s own donors are added automatically'},
            'uses': dict(rng(facts['uses']['min'], facts['uses']['max'], integer=True, unit='calls per mission'),
                optional=True, default='unlimited',
                doc='each player\'s own calls: the game\'s own per-slot uses (its HUD counter, its depleted look, its '
                    'refusal at 0) on the slot that holds the carrier; refused for an Eagle, whose uses are per rearm'),
            'max_per_player': dict(rng(1, facts['maxPerPlayer'], integer=True, unit='loadout slots per player'),
                optional=True, default='no limit',
                doc='at most this many of each player\'s loadout slots hold it: a further pick is refused (its tile '
                    'unavailable); a loadout holding more aboard the ship loses the extra slots'),
            'traits': {'type': 'list', 'item': {'type': 'string', 'minLength': 1, 'maxLength': facts['traits']['length']},
                'max': facts['traits']['max'], 'optional': True, 'default': 'the payload family\'s',
                'doc': 'the ITEM TRAITS the custom panel shows after the automatic CUSTOM STRATAGEM (upper case)'},
        },
        'carrier': {
            'beacon': {'type': 'enum', 'values': facts['beacons'], 'required': 'unless group is given',
                'doc': 'the beam the player throws: offensive (red), support (blue), any'},
            'group': {'type': 'enum', 'values': L['groups'], 'optional': True, 'catalog': 'carrierGroups',
                'default': 'the payload family\'s default group',
                'doc': 'the carrier group the carrier is drawn from (carrierGroups: its beacon and families; refused '
                       'when it cannot carry the payload)'},
            'slots': dict(rng(L['slots'][0], L['slots'][1], integer=True, unit='pod items'), optional=True,
                doc='the pod capacity asked for (support_pod and expendable groups only); at least the pod\'s items'),
            'prefer_families': {'type': 'list', 'item': {'type': 'enum', 'values': facts['carrierFamilies']},
                'optional': True},
            'allow_families': {'type': 'list', 'item': {'type': 'enum', 'values': facts['carrierFamilies']},
                'optional': True, 'default': 'prefer_families (any family when neither is given)'},
            'exclude': {'type': 'list', 'item': {'type': 'stratagem', 'catalog': 'stratagems'}, 'optional': True},
        },
        'families': families,
        'podFamily': pod_family,
        'variantFamily': variant_family,
        'familyEvidence': family_evidence,
        'selection': selection,
        'familyOptions': {'expendable': {
            'pod': {'type': 'list', 'min': PL['items'][0], 'max': PL['items'][1], 'optional': True, 'item': pod_item,
                'default': 'the carrier weapon\'s vanilla rack',
                'doc': 'what the carrier weapon\'s own pod holds: {"item": "clone", "count": n} and other podItems; a '
                       'pool weapon whose rack cannot hold it is never the carrier weapon'},
            'carrier': {'groups': ['expendable']}}},
        'unsupported': [
            {'field': 'orbital.explosion_scale', 'reason': 'an explosion\'s size is a shared row: every shell of it would '
                'change'},
            {'field': 'eagle.pattern', 'reason': 'the strike pattern is the donor\'s EagleComponentData, a shared '
                'definition with no reviewed per-call field'},
            {'field': 'eagle.payload.projectile', 'reason': 'the strike projectile is the donor\'s (shared)'},
            {'field': 'eagle cooldown', 'reason': 'an Eagle keeps its native cooldown and rearm'},
            {'field': 'support.items[].modify on a backpack', 'reason': 'no instance-local backpack field is reviewed'},
            {'field': 'support.items[].count other than the rack\'s', 'reason': 'the rack lists are shared definitions'},
            {'field': 'two support donors in one call', 'reason': 'one native pod delivers one rack'},
            {'field': 'sentry.weapon.impact_explosion', 'reason': 'automatic weapons: the conversion is for launchers '
                'and rockets'},
            {'field': 'a raw projectile, explosion or entity number', 'reason': 'a donor\'s package must be known: '
                'donors are named'},
            {'field': 'expendable.modify.projectile', 'reason': 'the clone fires its donor\'s own round'},
            {'field': 'an expendable clone on a weapon outside the donor\'s component class (e.g. the AC-8 as an EAT)',
                'reason': 'components are fixed per type: a reloadable weapon never discards itself (research '
                'carrier-weapon-clone)'},
            {'field': 'an expendable carrier weapon a lobby member brings', 'reason': 'that player\'s own weapon would '
                'change: the custom stratagem is unavailable instead'},
            {'field': 'a pod item that is a secondary, a throwable or has no pickup zone', 'reason': 'not a reviewed '
                'rack item kind (research carrier-pod-items)'},
            {'field': 'more pod items than a carrier rack\'s usable slots', 'reason': 'a spawn-count write is not part '
                'of this pass: the capacity is the rack\'s usable slots (1 or 2)'},
            {'field': 'a carrier pod with several players', 'reason': 'solo host only in this build'},
        ],
        'limits': {'definitions': L['definitions'], 'orbitalShells': O['total']},
        'catalogs': {key: facts[key] for key in ('supportDonors', 'projectileDonors', 'cloneDonors', 'sentryDonors',
            'eagleDonors',
            'orbitals', 'explosionDonors', 'carrierFamilies', 'carrierGroups', 'podItems', 'podCarriers', 'beacons',
            'directions', 'stratagems', 'pelicanSounds', 'pelicanExplosionDonors', 'nativeCodes', 'siloDonors',
            'blastExplosions', 'variantDonors')},
    }
    return schema


def project_schema(schema: dict) -> dict:
    """The JSON Schema of custom_stratagems.json (structure and ranges; donors are checked against the catalogues by
    the compiler)."""
    M = schema['metadata']

    def number(field):
        out = {'type': field['type']}
        if 'min' in field:
            out['exclusiveMinimum' if field.get('exclusiveMin') else 'minimum'] = field['min']
        if 'max' in field:
            out['maximum'] = field['max']
        return out

    def fields_object(fields):
        props, required = {}, []
        for key, f in fields.items():
            if f['type'] in ('integer', 'number'):
                props[key] = number(f)
            elif f['type'] == 'enum':
                props[key] = {'enum': f['values']}
            elif f['type'] == 'boolean':
                props[key] = {'type': 'boolean'}
            elif f['type'] == 'object':
                props[key] = fields_object(f['fields'])
            elif f['type'] == 'list':
                props[key] = {'type': 'array', 'minItems': f.get('min', 0), 'maxItems': f.get('max', 64),
                    'items': fields_object(f['item']) if isinstance(f['item'], dict) and 'type' not in f['item']
                    else {'type': 'string'}}
            else:
                props[key] = {'type': 'string'}
            if f.get('required'):
                required.append(key)
        out = {'type': 'object', 'additionalProperties': False, 'properties': props}
        if required:
            out['required'] = required
        return out

    payloads = []
    for fam in schema['families'] + [schema['podFamily'], schema['variantFamily']]:
        if not fam['builder']:
            continue
        fields = dict(fam['fields'])
        for key, field in schema['familyOptions'].get(fam['family'], {}).items():
            if key != 'carrier':
                fields[key] = field
        body = fields_object(fields)
        body['properties']['family'] = {'const': fam['family']}
        body['required'] = ['family'] + body.get('required', [])
        payloads.append(body)
    stratagem = {'type': 'object', 'additionalProperties': False, 'required': ['id', 'name', 'description', 'icon',
        'code', 'carrier', 'payload'], 'properties': {
        'id': {'type': 'string', 'pattern': M['id']['pattern'], 'maxLength': M['id']['maxLength']},
        'name': {'type': 'string', 'minLength': 1, 'maxLength': M['name']['maxLength']},
        'name_cased': {'type': 'string', 'minLength': 1, 'maxLength': M['name_cased']['maxLength']},
        'description': {'type': 'string', 'minLength': 1, 'maxLength': M['description']['maxLength']},
        'icon': {'type': 'object', 'additionalProperties': False, 'required': ['image'], 'properties': {
            'image': {'type': 'string', 'pattern': '^[a-z0-9_]{1,64}$'},
            'source': {'type': 'string', 'pattern': r'^images/[a-z0-9_]{1,64}\.png$',
                'description': 'the editable PNG, images/<image>.png (the build compiles it into the mod)'}}},
        'code': {'type': 'array', 'minItems': M['code']['min'], 'maxItems': M['code']['max'],
            'items': {'enum': schema['catalogs']['directions']}},
        'cooldown': number(M['cooldown']),
        'uses': number(M['uses']),
        'max_per_player': number(M['max_per_player']),
        'traits': {'type': 'array', 'maxItems': M['traits']['max'], 'items': {'type': 'string', 'minLength': 1,
            'maxLength': M['traits']['item']['maxLength']}},
        'assets': {'type': 'array', 'items': {'type': 'string'}},
        'carrier': {'type': 'object', 'additionalProperties': False,
            'anyOf': [{'required': ['beacon']}, {'required': ['group']}], 'properties': {
            'beacon': {'enum': schema['catalogs']['beacons']},
            'group': {'enum': [g['name'] for g in schema['catalogs']['carrierGroups']]},
            'slots': {'type': 'integer', 'minimum': schema['carrier']['slots']['min'],
                'maximum': schema['carrier']['slots']['max']},
            'prefer_families': {'type': 'array', 'items': {'enum': schema['catalogs']['carrierFamilies']}},
            'allow_families': {'type': 'array', 'items': {'enum': schema['catalogs']['carrierFamilies']}},
            'exclude': {'type': 'array', 'items': {'type': 'string'}}}},
        'payload': {'oneOf': payloads}}}
    return {'$schema': 'https://json-schema.org/draft/2020-12/schema',
        '$id': 'https://hd2runtime/schemas/custom_stratagems.project.schema.json',
        'title': 'HD2Runtime custom stratagem project (custom_stratagems.json)',
        'description': 'Compiled by hd2.py custom-stratagem compile into the mod\'s src/addon.lua; donors are checked '
                       'against sdk/CustomStratagemSchema.json catalogs. Format ' + FORMAT + '.',
        'type': 'object', 'additionalProperties': False, 'required': ['format', 'stratagems'],
        'properties': {
            'format': {'const': FORMAT},
            'log': {'type': 'string', 'minLength': 1, 'maxLength': 160,
                'description': 'optional: one line the mod logs at load (e.g. a build banner)'},
            'stratagems': {'type': 'array', 'minItems': 1, 'maxItems': schema['limits']['definitions'],
                'items': stratagem}}}


def outputs() -> dict[str, str]:
    schema = build()
    return {'sdk/CustomStratagemSchema.json': json.dumps(schema, indent=1, sort_keys=True) + '\n',
        'sdk/schemas/custom_stratagems.project.schema.json': json.dumps(project_schema(schema), indent=1,
            sort_keys=True) + '\n'}


def generate(check=False):
    stale = []
    for name, body in outputs().items():
        path = ROOT / name
        if not path.exists() or path.read_text(encoding='utf-8') != body:
            stale.append(name)
            if not check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(body, encoding='utf-8', newline='\n')
    if check and stale:
        raise RuntimeError('Stale custom stratagem schema: ' + ', '.join(stale))
    return stale


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    print(', '.join(generate(parser.parse_args().check)) or 'up to date')
