"""Validate the built runtime ZIP itself, the way HD2 loads it.

Source-tree tests preload every module, which hides packaging and load-order faults.
This validator reads only the shipped archive:

1. Static: every internal module name referenced by shipped Lua, and every name in
   the generated package module list, resolves to a resource in the archive.
2. Dynamic: the archive runs on HD2's own lua51.dll behind an emulated Bingus
   loader. As in game, archived resources resolve through package.loaders only
   during startup; afterwards lookups fail with "module not found". Real addons
   then apply through the packaged API against the retained snapshot, using a
   copy-on-write memory overlay (no game process, no real writes), and each ensure
   must re-apply after a simulated reset.

Only runtime/windows_write is substituted, so writes land in the overlay.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import struct
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from hd2_archive import resource_hash

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_profile  # noqa: E402  central build identity (schemas/build_profile.json)
import parallel  # noqa: E402
SNAPSHOT = build_profile.SNAPSHOT
ENTRY = 'mods/skyeshade/hd2runtime'
PACKAGE_MODULES = 'hd2runtime/runtime/package_modules'
WRITE_ADAPTER = 'hd2runtime/runtime/windows_write'
REFERENCE = re.compile(rb"""['"](hd2runtime/[A-Za-z0-9_/]+)['"]""")

GUI_TRANSACTION = r'''local hd2=require('mods/skyeshade/hd2runtime')

local operations={}
operations[#operations+1]=hd2.ensure({
    transaction={
        id='gui-object-957b6b7e6b9132eff9fbc6fb',
        target=hd2.weapon('AR-23C Liberator Concussive'):attack('primary'):projectile(),
        allow_shared=true,
        changes={
            {field=hd2.fields.damage.ap_direct,expect=2,value=3},
            {field=hd2.fields.damage.ap_extreme,expect=2,value=3},
            {field=hd2.fields.damage.ap_large,expect=2,value=3},
            {field=hd2.fields.damage.ap_slight,expect=2,value=3},
            {field=hd2.fields.damage.push_force,expect=60,value=30},
        },
    }
})
operations[#operations+1]=hd2.ensure({
    patch={
        id='gui-object-b52a010dda6a8e42722ba35c',
        target=hd2.weapon('AR-23C Liberator Concussive'),
        field=hd2.fields.weapon.fire_rate,
        expect=400,
        value=1100,
    }
})
return operations
'''
SIMPLE_PATCH = r'''local hd2=require('mods/skyeshade/hd2runtime')
return hd2.patch({id='concussive-fire-rate',target=hd2.weapon('AR-23C Liberator Concussive'),
    field=hd2.fields.weapon.fire_rate,expect=400,value=1100})
'''


# Registration isolation: an independently authored operation that fails validation is logged and returned rejected;
# it never raises, so the operations declared before and after it still register and apply.
REGISTRATION_ISOLATION = r'''local hd2=require('mods/skyeshade/hd2runtime')
local operations={}
operations[#operations+1]=hd2.ensure({patch={id='isolation-before',target=hd2.weapon('AR-23C Liberator Concussive'),
    field=hd2.fields.weapon.fire_rate,expect=400,value=1100}})
operations[#operations+1]=hd2.ensure({patch={id='isolation-invalid',
    target=hd2.weapon('SG-20 Halt'):attack('feed_primary'):projectile(),field='damage.no_such_field',expect=1,value=2}})
operations[#operations+1]=hd2.ensure({patch={id='isolation-after',target=hd2.stratagem('Orbital Precision Strike'),
    field=hd2.fields.stratagem.definition_cooldown,expect=80,value=5}})
return operations
'''

# The AyakaMods user report (tests/fixtures/user-reports/ayakamods-weaponry-rebalance): the exact ModBuilder 1.3.1
# exports of the user's project and its variants, wrapped exactly as ModBuilder packages them.
USER_REPORT = ROOT / 'tests/fixtures/user-reports/ayakamods-weaponry-rebalance/generated'


def user_report(name, folder=USER_REPORT):
    return (folder / (name + '.wrapped.lua')).read_text(encoding='utf-8')


# ModBuilder issue 2 (tests/fixtures/user-reports/modbuilder-issue-2-halt): ModBuilder 1.3.1 exports editing every
# SG-20 Halt field next to unrelated weapons. With the published 0.27.0 the first Halt operation aborted the addon.
HALT_ISSUE = ROOT / 'tests/fixtures/user-reports/modbuilder-issue-2-halt/generated'


# Active projectile sources from the shipped archive: the Reprimand's own member is its fired projectile (the live
# PASS control); the Liberator's attack.projectile is refused as dormant (the live FAIL control) and the same donor
# goes to its active source, the default ammunition delta, after the donor package is loaded.
PROJECTILE_SOURCES = r'''local hd2=require('mods/skyeshade/hd2runtime')
local reprimand=hd2.weapon('SMG-32 Reprimand'):attack('primary'):projectile_source()
assert(reprimand.status=='ACTIVE_DIRECT'and reprimand.mechanism=='component'and reprimand.writable
    and reprimand.field=='attack.projectile','Reprimand is no longer a direct projectile source')
local attack=hd2.weapon('AR-23 Liberator'):attack('primary')
local talon=hd2.weapon('LAS-58 Talon'):attack('primary'):projectile()
-- Refused at registration: a logged, rejected handle (never a raised error that would abort this addon).
local dormant=hd2.ensure({patch={id='liberator-talon-dormant',target=attack,field=hd2.fields.attack.projectile,
    expect=attack:projectile(),value=talon}})
assert(dormant.status=='rejected'and dormant.result.code=='DORMANT_PROJECTILE_REFERENCE',
    'the dormant Liberator member was not refused: '..tostring(dormant.error))
local source=attack:projectile_source()
assert(source.status=='INDIRECT'and source.mechanism=='ammunition'and source.writable
    and source.field=='ammunition.projectile','Liberator is no longer an ammunition source')
return hd2.ensure({patch={id='liberator-talon-ammunition',target=source.target,field=hd2.fields.ammunition.projectile,
    expect=source.expect,value=talon,allow_shared=true,allow_unverified_effect=true}})
'''


SUPPORT_COVERAGE = r'''local hd2=require('mods/skyeshade/hd2runtime')
local mg43=hd2.support_weapon('MG-43 Machine Gun')
local operations={}
-- Delivery-resolved identity (call-in rack chain re-proven live) plus a reload duration.
operations[#operations+1]=hd2.ensure({plan={id='mg43-coverage',operations={
    {id='rate',target=mg43,field=hd2.fields.weapon.fire_rate,expect=760,value=900},
    {id='reload',target=mg43,allow_unverified_effect=true,
        field=hd2.fields.reload.duration,expect=4.5,value=3},
}}})
operations[#operations+1]=hd2.ensure({patch={id='maxigun-windup',target=hd2.support_weapon('M-1000 Maxigun'),
    field=hd2.fields.windup.wind_up_seconds,expect=0.5,value=0.2}})
operations[#operations+1]=hd2.ensure({patch={id='rl77-lifetime',allow_shared=true,
    target=hd2.support_weapon('RL-77 Airburst Rocket Launcher'):attack('primary'):projectile(),
    field=hd2.fields.projectile.lifetime,expect=1.5,value=3}})
return operations
'''


# Several magazine definitions of one weapon, edited independently (separate delta records).
MAGAZINE_OPTIONS = r'''local hd2=require('mods/skyeshade/hd2runtime')
local liberator=hd2.weapon('AR-23 Liberator')
local short=liberator:magazine_attachment('Short Magazine')
local drum=liberator:magazine_attachment('Drum Magazine')
local operations={}
operations[#operations+1]=hd2.ensure({patch={id='liberator-short-capacity',target=short,
    allow_shared=true,allow_unverified_effect=true,field=hd2.fields.attachment.magazine_capacity,expect=30,value=40}})
operations[#operations+1]=hd2.ensure({transaction={id='liberator-drum-handling',target=drum,
    allow_shared=true,allow_unverified_effect=true,changes={
        {field=hd2.fields.attachment.reload_duration,expect=3.5,value=3},
        {field=hd2.fields.attachment.ergonomics_modifier,expect=-15,value=-5}}}})
return operations
'''
# A player weapon's crosshair policy (the schema is shared with support weapons).
PLAYER_RETICLE = r'''local hd2=require('mods/skyeshade/hd2runtime')
return hd2.ensure({patch={id='diligence-reticle-off',target=hd2.weapon('R-63 Diligence'),
    field=hd2.fields.weapon.third_person_reticle,expect=true,value=false,allow_unverified_effect=true}})
'''

# Fire modes: a burst weapon's burst length and mode set, and an automatic weapon made single-shot.
FIRE_MODES = r'''local hd2=require('mods/skyeshade/hd2runtime')
local operations={}
operations[#operations+1]=hd2.ensure({transaction={id='liberator-burst',target=hd2.weapon('AR-23 Liberator'),
    allow_unverified_effect=true,changes={
        {field=hd2.fields.fire_mode.burst_rounds,expect=3,value=5},
        {field=hd2.fields.fire_mode.modes,expect={'automatic','single','burst'},value={'burst','single'}}}}})
operations[#operations+1]=hd2.ensure({patch={id='mg43-single',target=hd2.support_weapon('MG-43 Machine Gun'),
    field=hd2.fields.fire_mode.modes,expect={'automatic'},value={'single'},allow_unverified_effect=true}})
return operations
'''

# Tank mounted weapons: Bastion main cannon (shared round and own reserve), Bastion coaxial MG, Maelstrom gun.
TANK_WEAPONS = r'''local hd2=require('mods/skyeshade/hd2runtime')
local bastion,maelstrom=hd2.vehicle('TD-220 Bastion MK XVI'),hd2.vehicle('TD-110 Maelstrom')
local operations={}
operations[#operations+1]=hd2.ensure({patch={id='bastion-cannon-reserve',target=bastion:weapon('attach_tank_gun'),
    field=hd2.fields.magazine.spare_magazines,expect=30,value=45,allow_unverified_effect=true}})
operations[#operations+1]=hd2.ensure({patch={id='bastion-cannon-damage',target=bastion:weapon('attach_tank_gun'):projectile(),
    field=hd2.fields.damage.player_standard_damage,expect=3500,value=5000,allow_shared=true,allow_unverified_effect=true}})
operations[#operations+1]=hd2.ensure({patch={id='bastion-mg-capacity',target=bastion:weapon('attach_tank_gun_mg'),
    field=hd2.fields.weapon.capacity,expect=2000,value=3000,allow_unverified_effect=true}})
operations[#operations+1]=hd2.ensure({patch={id='maelstrom-gun-rate',target=maelstrom:weapon(0),
    field=hd2.fields.weapon.fire_rate,expect=1200,value=900,allow_unverified_effect=true}})
return operations
'''

# Mission uses: unlimited -> finite and finite -> different finite (not gameplay-proven: acknowledged).
STRATAGEM_USES = r'''local hd2=require('mods/skyeshade/hd2runtime')
local operations={}
operations[#operations+1]=hd2.ensure({patch={id='frv-two-uses',target=hd2.stratagem('M-102 Gunner FRV'),
    field=hd2.fields.stratagem.max_uses,expect='unlimited',value=2,allow_unverified_effect=true}})
operations[#operations+1]=hd2.ensure({patch={id='laser-five-uses',target=hd2.stratagem('Orbital Laser'),
    field=hd2.fields.stratagem.max_uses,expect=3,value=5,allow_unverified_effect=true}})
return operations
'''

# Backpack-owned ammunition for the other two backpack-fed support weapons.
BACKPACK_AMMO = r'''local hd2=require('mods/skyeshade/hd2runtime')
local operations={}
operations[#operations+1]=hd2.ensure({patch={id='cremator-backpack-capacity',
    target=hd2.support_weapon('B/FLAM-80 Cremator'):backpack(),allow_unverified_effect=true,
    field=hd2.fields.deposit.capacity,expect=500,value=750}})
operations[#operations+1]=hd2.ensure({patch={id='gl28-backpack-supply',
    target=hd2.support_weapon('GL-28 Belt-Fed Grenade Launcher'):backpack(),allow_unverified_effect=true,
    field=hd2.fields.deposit.refill_amount,expect=60,value=90}})
return operations
'''

# Drop-pod payloads: an ordinary support pod, a weapon+backpack pod, and the shared Resupply spawn count.
POD_PAYLOADS = r'''local hd2=require('mods/skyeshade/hd2runtime')
local operations={}
local rail=hd2.stratagem('RS-422 Railgun'):payload()
operations[#operations+1]=hd2.ensure({patch={id='railgun-pod-mg43',target=rail:slot(1),
    field=hd2.fields.payload.entity,expect=rail:slot(1):current(),value=hd2.pickup('MG-43 Machine Gun'),
    allow_unverified_reference=true}})
local maxigun=hd2.stratagem('M-1000 Maxigun'):payload()
operations[#operations+1]=hd2.ensure({patch={id='maxigun-pod-backpack',target=maxigun:slot(2),
    field=hd2.fields.payload.entity,expect=maxigun:slot(2):current(),value=hd2.pickup('B-1 Supply Pack'),
    allow_unverified_reference=true}})
local resupply=hd2.pod_rack('Resupply pod')
operations[#operations+1]=hd2.ensure({patch={id='resupply-three-boxes',target=resupply,
    field=hd2.fields.payload.spawn_count,expect=4,value=3,allow_unverified_effect=true,allow_shared=true}})
return operations
'''


BOOSTER_COVERAGE = r'''local hd2=require('mods/skyeshade/hd2runtime')
local operations={}
-- Remaining tuning scalars in one plan; every row is re-proven live from game.dll.
local tuning={
    {'Stamina Enhancement','stamina_scale',1.3,1.6},{'Muscle Enhancement','terrain_slowdown_scale',0.35,0.2},
    {'UAV Recon Booster','radar_range_scale',1.5,2},{'Increased Reinforcement Budget','reinforcements_per_player',1,2},
    {'Flexible Reinforcement Budget','reinforcement_cooldown_scale',0.75,0.5},
    {'Localization Confusion','encounter_rate_scale',0.9,0.8},{'Motivational Shocks','slow_scale',0.5,0.25},
    {'Dead Sprint','health_floor',0.05,0.1},{'Sample Extricator','sample_drop_cap',10,20},
    {'Integrated Extinguishers','burn_decay_bonus',0.5,0.75},
}
local plan={}
for index,item in ipairs(tuning)do
    plan[index]={id='tuning-'..index,target=hd2.booster(item[1]):tuning(),allow_unverified_effect=true,
        field=hd2.fields.booster[item[2]],expect=item[3],value=item[4]}
end
operations[#operations+1]=hd2.ensure({plan={id='booster-tuning-coverage',operations=plan}})
operations[#operations+1]=hd2.ensure({transaction={id='dead-sprint-drain',
    target=hd2.booster('Dead Sprint'):status_damage(),allow_shared=true,allow_unverified_effect=true,
    changes={{field=hd2.fields.damage.player_standard_damage,expect=5,value=2},
        {field=hd2.fields.damage.player_durable_damage,expect=5,value=2}}}})
operations[#operations+1]=hd2.ensure({patch={id='stun-pods-radius',target=hd2.booster('Stun Pods'):explosion(),
    allow_shared=true,allow_unverified_effect=true,field=hd2.fields.explosion.outer_radius,expect=4,value=7}})
operations[#operations+1]=hd2.ensure({patch={id='smoke-pods-radius',
    target=hd2.booster('Concealed Insertion'):explosion(),allow_shared=true,allow_unverified_effect=true,
    field=hd2.fields.explosion.inner_radius,expect=5,value=8}})
return operations
'''

# Stand-in for CowboyBingus Mod Options Menu api 1 (the release build cannot depend on a local
# checkout of the third-party addon). It follows the addon's contract: register_option validates
# and returns true or false, get returns the applied value (saved if valid, else the default),
# set replaces it without callbacks, and on_change callbacks run once per applied change.
# scripts/validate_options_binding_snapshot.py runs the real addon source instead.
MENU_STUB = r'''
local menu={api=1,version=1,max_mods=8,max_options=32,values={},callbacks={},saved={['liberator_damage.damage']='200'}}
function menu.register_option(id,spec)
 if type(id)~='string'or type(spec)~='table'or type(spec.label)~='string'then return false,'invalid option registration'end
 local value=menu.saved[id]and tonumber(menu.saved[id])
 if spec.type=='slider'then
  if not(value and value>=spec.min and value<=spec.max)then value=spec.default end
 elseif spec.type=='toggle'then value=spec.default==true
 else value=spec.default or 1 end
 menu.values[id]=value;return true
end
function menu.get(id)return menu.values[id]end
function menu.set(id,value)menu.values[id]=value;return true end
function menu.on_change(id,fn)menu.callbacks[id]=menu.callbacks[id]or{};table.insert(menu.callbacks[id],fn);return true end
function menu.ready()return true end
function menu.apply(id,value)menu.values[id]=value;for _,fn in ipairs(menu.callbacks[id]or{})do fn(value,id)end end
rawset(_G,'ModOptionsMenu',menu)
'''
OPTIONS_LIVE = r'''
return function(frame,watches,counts)
 local menu=rawget(_G,'ModOptionsMenu');local w=watches[1];local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function run(seconds)for _=1,math.floor(seconds/0.1+0.5)do frame()end end
 -- Wait out the debounce, then until the operation is idle again (resolution spans many ticks).
 local function settle()
  run(1)
  local spent=0
  while(w.status=='running'or w.status=='waiting'and w.runs==0)and spent<6000 do frame();spent=spent+1 end
 end
 step('saved value applied first',w.status=='waiting'and w.runs==1 and w.result.status=='APPLIED')
 local writes=counts.writes
 menu.apply('liberator_damage.damage',300);settle()
 step('live change applies through the same ensure',w.runs==2 and w.result.status=='APPLIED'
  and counts.writes==writes+1,w.error)
 writes=counts.writes
 menu.apply('liberator_damage.damage',300);settle()
 step('no-op change does no work',w.runs==2 and counts.writes==writes)
 menu.apply('liberator_damage.enabled',false);settle()
 step('disable restores the baseline',w.status=='disabled'and w.restores==1 and counts.writes==writes+1,w.error)
 menu.apply('liberator_damage.enabled',true);settle()
 step('re-enable applies the slider value',w.status=='waiting'and w.runs==3 and counts.writes==writes+2,w.error)
 return results
end
'''
OPTIONS_MISSING_ADDON = lambda name='LiberatorDamageOptions', folder='projects': wrap_example(name, folder, (example_source(name, folder)
    .replace('return hd2.ensure(', 'local operations={}\noperations[1]=hd2.ensure(')
    + '''-- Not bound to any option: runs normally whether or not Mod Options Menu is installed.
operations[2]=hd2.ensure({patch={id='plain-vitality',allow_unverified_effect=true,
    target=hd2.booster('Vitality Enhancement'):tuning(),field=hd2.fields.booster.damage_taken_scale,
    expect=0.9,value=0.8}})
return operations
'''))
# Default fallback: without Mod Options Menu the bound operation applies its declared defaults.
OPTIONS_MISSING = r'''
return function(frame,watches,counts,lines)
 local DEFAULT=150
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local warning='[HD2Runtime] options liberator_damage unavailable: Mod Options Menu is not installed; '
  ..'using configured defaults'
 local function count(text,plain)
  local n=0
  for _,line in ipairs(lines)do if line:find(text,1,plain)then n=n+1 end end
  return n
 end
 local bound,plain=watches[1],watches[2]
 step('bound operation applies its declared default',bound.status=='waiting'and bound.runs==1
  and bound.option_defaults==true and bound.result.status=='APPLIED'and count(' 90 -> '..DEFAULT,true)==1,
  bound.status)
 step('unrelated operation in the same mod applies',plain.status=='waiting'and plain.result.status=='APPLIED')
 step('one clear warning',count(warning,true)==1 and count('will not be applied',true)==0,
  table.concat(lines,' | '))
 local writes=counts.writes
 for _=1,3000 do frame()end
 step('no retries, repeated warnings or extra writes',count('Mod Options Menu',true)==1 and bound.runs==1
  and bound.status=='waiting'and counts.writes==writes)
 return results
end
'''
# Strict fallback (fallback='disable'): the bound operation stays inactive without the menu.
OPTIONS_MISSING_STRICT = r'''
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local warning='[HD2Runtime] options liberator_damage unavailable: Mod Options Menu is not installed; '
  ..'configurable operation will not be applied (liberator-damage)'
 local function count(text,plain)
  local n=0
  for _,line in ipairs(lines)do if line:find(text,1,plain)then n=n+1 end end
  return n
 end
 local bound,plain=watches[1],watches[2]
 step('bound operation stays inactive',bound.status=='unavailable'and bound.runs==0 and bound.result==nil,
  bound.status)
 step('unrelated operation in the same mod applies',plain.status=='waiting'and plain.result.status=='APPLIED')
 step('one clear warning',count(warning,true)==1,table.concat(lines,' | '))
 for _=1,3000 do frame()end
 step('no retries or repeated warnings',count('Mod Options Menu',true)==1 and bound.runs==0
  and bound.status=='unavailable')
 return results
end
'''
STRICT_PAGE = ("title='Liberator Damage'})", "title='Liberator Damage',fallback='disable'})")
# The live-validation mod (examples/live/HD2RuntimeOptionsTest) runs the same checks under its
# own page, option and operation ids, so the exact addon players test is proven from the ZIP.
TEST_MOD_IDS = (('liberator_damage.damage', 'hd2runtime_options_test.liberator_damage'),
    ('liberator_damage.enabled', 'hd2runtime_options_test.enabled'),
    ('options liberator_damage unavailable', 'options hd2runtime_options_test unavailable'),
    ('(liberator-damage)', '(options-test-liberator-damage)'),
    ('local DEFAULT=150', 'local DEFAULT=100'))


def test_mod_ids(text):
    for old, new in TEST_MOD_IDS:
        text = text.replace(old, new)
    assert 'liberator_damage.' not in text and '(liberator-damage)' not in text
    return text


# LiberatorAttackOutputTest: one Mod Options choice selects a complete output composition, written to the
# Liberator's active projectile source (its default ammunition delta). Every switch is one owned transition; each
# donor package is requested once, before its write; Vanilla restores the exact baseline; the run ends on a donor
# output so the reset check re-applies it.
ATTACK_OUTPUT_LIVE = r'''
return function(frame,watches,counts,lines)
 local menu=rawget(_G,'ModOptionsMenu');local w=watches[1];local results={}
 local ID='liberator_attack_output.output'
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function settle(runs)
  local spent=0
  while(w.runs<=runs or w.status=='running')and w.status~='blocked'and spent<20000 do frame();spent=spent+1 end
  for _=1,20 do frame()end
 end
 step('vanilla default leaves the ammunition baseline untouched',w.status=='waiting'and w.runs==1
  and counts.writes==0 and(counts.package_requests or 0)==0,tostring(w.status)..' writes='..counts.writes)
 local function choose(index,label,packages)
  local runs,writes=w.runs,counts.writes
  menu.apply(ID,index);settle(runs)
  step(label,w.status=='waiting'and w.result and w.result.status=='APPLIED'and counts.writes==writes+1
   and(counts.package_requests or 0)==packages,
   ('status=%s result=%s writes=%d packages=%d error=%s'):format(tostring(w.status),
    tostring(w.result and w.result.status),counts.writes-writes,counts.package_requests or 0,tostring(w.error)))
 end
 choose(2,'Talon control: donor package loaded, then one ammunition write',1)
 choose(3,'Talon -> EAT-700 napalm: owned transition, second donor package loaded',2)
 choose(4,'EAT-700 -> GL-52 arc: third donor package loaded',3)
 choose(1,'GL-52 -> Vanilla restores the exact ammunition baseline',3)
 choose(4,'Vanilla -> GL-52 again: package already held, no new request',3)
 choose(3,'GL-52 -> EAT-700: complete composition switch',3)
 return results
end
'''

# ResupplyTest: the Resupply stratagem as an hd2.stratagem target. Defaults (5 s cooldown, grenade boxes) apply
# first, the grenade box package loaded once before its slots are written; each option then switches alone, and
# Vanilla restores the exact supply boxes and the 180 s cooldown. A slot reference is two aligned dword writes.
RESUPPLY_LIVE = r'''
return function(frame,watches,counts,lines)
 local menu=rawget(_G,'ModOptionsMenu');local cooldown,payload=watches[1],watches[2];local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function settle(w,runs)
  local spent=0
  while(w.runs<=runs or w.status=='running')and w.status~='blocked'and spent<20000 do frame();spent=spent+1 end
  for _=1,20 do frame()end
 end
 local function count(text)
  local n=0
  for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end
  return n
 end
 step('defaults: 5 s cooldown and grenade boxes, donor package loaded once',cooldown.status=='waiting'
  and cooldown.result.status=='APPLIED'and payload.status=='waiting'and payload.result.status=='APPLIED'
  and counts.writes==9 and(counts.package_requests or 0)==1 and count('stratagem.cooldown 180 -> 5')==1,
  ('writes=%d packages=%d'):format(counts.writes,counts.package_requests or 0))
 local function choose(w,id,index,label,writes)
  local runs,before=w.runs,counts.writes
  menu.apply(id,index);settle(w,runs)
  step(label,w.status=='waiting'and w.result and w.result.status=='APPLIED'and counts.writes==before+writes
   and(counts.package_requests or 0)==1,('status=%s result=%s writes=%d packages=%d error=%s'):format(
   tostring(w.status),tostring(w.result and w.result.status),counts.writes-before,counts.package_requests or 0,
   tostring(w.error)))
 end
 choose(payload,'resupply_test.payload',1,'Vanilla payload restores the four supply boxes, cooldown untouched',8)
 choose(cooldown,'resupply_test.cooldown',1,'Vanilla cooldown restores 180 s',1)
 choose(payload,'resupply_test.payload',2,'grenade boxes again: package already held, no new request',8)
 choose(cooldown,'resupply_test.cooldown',2,'5 s again',1)
 return results
end
'''

# RuntimeEffectDiagnostics: seven independent toggle-bound tests, all off at start. Each toggle applies only its own
# operation; switching one off restores only that one; a later test never depends on an earlier one.
DIAGNOSTICS_LIVE = r'''
return function(frame,watches,counts,lines)
 local menu=rawget(_G,'ModOptionsMenu');local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function settle(w,runs)
  local spent=0
  while(w.runs<=runs or w.status=='running')and w.status~='blocked'and w.status~='rejected'and spent<60000 do
   frame();spent=spent+1
  end
  for _=1,20 do frame()end
 end
 step('every test starts off; nothing is written',counts.writes==0,'writes='..counts.writes)
 local ids={'ma5c_magazine','halt_damage','sickle_heat','maxigun_damage','maxigun_backpack','precision_cooldown',
  'cremator_start'}
 for index,id in ipairs(ids)do
  local w=watches[index];local runs,writes=w.runs,counts.writes
  menu.apply('runtime_effect_diagnostics.'..id,true);settle(w,runs)
  step(id..' on: its own operation applies',w.status=='waiting'and w.result and w.result.status=='APPLIED'
   and counts.writes>writes,('status=%s result=%s error=%s'):format(tostring(w.status),
    tostring(w.result and w.result.status),tostring(w.error)))
 end
 local w=watches[1];local restores=w.restores
 menu.apply('runtime_effect_diagnostics.ma5c_magazine',false)
 local spent=0
 while w.restores==restores and spent<60000 do frame();spent=spent+1 end
 step('switching one test off restores only that test',w.status=='disabled'and w.restores==restores+1
  and watches[2].status=='waiting'and watches[6].status=='waiting',tostring(w.status))
 menu.apply('runtime_effect_diagnostics.ma5c_magazine',true);settle(w,w.runs)
 step('and switching it on again reapplies it',w.status=='waiting'and w.result and w.result.status=='APPLIED',
  tostring(w.status))
 return results
end
'''

# Gameplay scripting from the built ZIP on real snapshot memory (aboard the ship). The native world must prove every
# pinned instruction against the snapshot's game.dll and executable; the sources then read the ship's real state.
EVENTS_WORLD = r"""
 local hd2=require('mods/skyeshade/hd2runtime')
 for _=1,10 do frame()end
 local unavailable=0
 for _,line in ipairs(lines)do if line:find('event source')and line:find('unavailable')then unavailable=unavailable+1 end end
 step('every event source proved its native structures on the snapshot',unavailable==0,table.concat(lines,' | '))
 local state=hd2.game_state()
 step('game state reads Ship',state and state.name=='Ship'and state.mission==false,tostring(state and state.name))
 local player=hd2.local_player()
 step('the local player and its avatar resolve',player~=nil and player:avatar()~=nil and player:health()==125,
  tostring(player and player:health()))
 local position=player and player:position()
 step('the avatar position is finite',position~=nil and position.z==position.z,tostring(position and position.z))
"""
EVENT_ISOLATION_LIVE = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
""" + EVENTS_WORLD + r"""
 local input=require('hd2runtime/runtime/input')
 local down=false
 input.set_backend({focused=function()return true end,down=function(code)return down and code==input.keys.F9 end})
 for press=1,3 do down=true;frame();frame();down=false;frame()end
 local failures,second=0,0
 for _,line in ipairs(lines)do
  if line:find('event key_down callback failed (mod mods/hd2runtime_examples/event_isolation_test',1,true)
   and line:find('intentional failure',1,true)then failures=failures+1 end
  if line:find('second subscriber ran after the failing one',1,true)then second=second+1 end
 end
 step('each press logs the failure with the mod and event',failures==3,'failures='..failures)
 step('the second subscriber ran on every press',second==3,'second='..second)
 for _=1,600 do frame()end
 local disabled,healthy=0,0
 for _,line in ipairs(lines)do
  if line:find('repeating timer callback disabled (mod mods/hd2runtime_examples/event_isolation_test',1,true)then disabled=disabled+1 end
  if line:find('healthy timer ran',1,true)then healthy=healthy+1 end
 end
 step('the failing timer is disabled once, the healthy one keeps running',disabled==1 and healthy>=3,
  'disabled='..disabled..' healthy='..healthy)
 return results
end
"""
EVENT_WORLD_LIVE = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
""" + EVENTS_WORLD + r"""
 local amount,why=hd2.local_player():heal(25)
 step('heal is refused without a native-call adapter (never a fallback write)',amount==nil
  and tostring(why):find('HEAL_UNAVAILABLE',1,true)~=nil,tostring(why))
 local boom=hd2.explosions.spawn('R-36 Eruptor',{position={x=1,y=2,z=3}})
 step('an explosion aboard the ship is refused (not in a mission)',boom.status=='refused'and boom.code=='NOT_IN_MISSION',
  tostring(boom.code)..' '..tostring(boom.reason))
 step('every catalogued explosion resolves from the packaged archive',#hd2.explosions.list()==15,
  tostring(#hd2.explosions.list()))
 step('the projectile and status catalogs resolve from the packaged archive',#hd2.projectiles.list()==67
  and #hd2.status.list()==11,tostring(#hd2.projectiles.list())..' '..tostring(#hd2.status.list()))
 local shot=hd2.projectiles.spawn('R-36 Eruptor',{position={x=1,y=2,z=3},direction={x=1,y=0,z=0}})
 step('a projectile aboard the ship is refused',shot.status=='refused'and(shot.code=='NOT_IN_MISSION'
  or shot.code=='PROJECTILE_UNAVAILABLE'),tostring(shot.code))
 local me=hd2.local_player()
 step('equipped_weapon resolves from the packaged archive',me==nil or type(me.equipped_weapon)=='function')
 step('no gameplay write happened',counts.writes==0,'writes='..counts.writes)
 return results
end
"""
KILL_STACK_LIVE = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
""" + EVENTS_WORLD + r"""
 local mod=hd2.mod('mods/hd2runtime_examples/kill_stack_damage_test')
 local damage=mod:value({id='liberator_damage',min=90,max=180,step=9,default=90})
 local w=watches[1]
 step('the bound ensure starts at the vanilla value',w.result and(w.result.status=='ALREADY_DESIRED'
  or w.result.status=='APPLIED'),tostring(w.result and w.result.status))
 local writes=counts.writes
 damage:set(117)                                  -- three kills
 local spent=0
 while counts.writes==writes and spent<6000 do frame();spent=spent+1 end
 for _=1,30 do frame()end
 step('a script value change re-applies the guarded write',counts.writes>writes and w.result
  and w.result.status=='APPLIED',('writes %d -> %d status %s'):format(writes,counts.writes,tostring(w.result and w.result.status)))
 writes=counts.writes
 damage:set(90)
 spent=0
 while counts.writes==writes and spent<6000 do frame();spent=spent+1 end
 step('back to vanilla on reset',counts.writes>writes,('writes %d -> %d'):format(writes,counts.writes))
 -- End boosted, so the harness's simulated game reset has a drift to re-apply.
 writes=counts.writes
 damage:set(108)
 spent=0
 while counts.writes==writes and spent<6000 do frame();spent=spent+1 end
 step('boosted again',counts.writes>writes,('writes %d -> %d'):format(writes,counts.writes))
 return results
end
"""

# HMGFireRateModesTest: the defaults (X / Y / Z = 300 / 550 / 1200, weapon-menu order) write all three MG-206 rate
# slots at startup; each slider then changes exactly its own slot (one write), and disable restores 450 / 600 / 750.
HMG_RATES_LIVE = r'''
return function(frame,watches,counts,lines)
 local menu=rawget(_G,'ModOptionsMenu');local w=watches[1];local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function settle(runs)
  local spent=0
  while(w.runs<=runs or w.status=='running')and w.status~='blocked'and w.status~='disabled'and spent<20000 do
   frame();spent=spent+1 end
  for _=1,20 do frame()end
 end
 step('defaults write the three native rate slots',w.status=='waiting'and w.result and w.result.status=='APPLIED'
  and counts.writes==3,('status=%s writes=%d'):format(tostring(w.status),counts.writes))
 local values={650,800,850}
 for index,id in ipairs({'hmg_fire_rate_modes.slot_x','hmg_fire_rate_modes.slot_y','hmg_fire_rate_modes.slot_z'})do
  local runs,writes=w.runs,counts.writes
  menu.apply(id,values[index]);settle(runs)
  step('slot '..('XYZ'):sub(index,index)..' alone writes one slot',w.result and w.result.status=='APPLIED'and counts.writes==writes+1,
   ('writes=%d error=%s'):format(counts.writes-writes,tostring(w.error)))
 end
 local writes=counts.writes
 menu.apply('hmg_fire_rate_modes.enabled',false);settle(w.runs)
 step('disable restores 450 / 600 / 750',w.status=='disabled'and w.restores==1 and counts.writes==writes+3,
  ('writes=%d'):format(counts.writes-writes))
 menu.apply('hmg_fire_rate_modes.enabled',true)
 local spent=0
 while w.status~='waiting'and w.status~='blocked'and spent<20000 do frame();spent=spent+1 end
 for _=1,20 do frame()end
 step('re-enable applies the options again',w.status=='waiting'and w.result and w.result.status=='APPLIED',
  tostring(w.status))
 return results
end
'''

# AddedFireRateModeTest: the defaults fill the two empty rate slots, change the default rate and bind the rate-of-fire
# selector (four writes, one transaction); a slider changes one slot; disable restores 640 rpm and no selector.
ADDED_RATES_LIVE = r'''
return function(frame,watches,counts,lines)
 local menu=rawget(_G,'ModOptionsMenu');local w=watches[1];local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function settle(runs)
  local spent=0
  while(w.runs<=runs or w.status=='running')and w.status~='blocked'and w.status~='disabled'and spent<20000 do
   frame();spent=spent+1 end
  for _=1,20 do frame()end
 end
 step('defaults write three rates and the selector binding',w.status=='waiting'and w.result
  and w.result.status=='APPLIED'and counts.writes==4,('status=%s writes=%d'):format(tostring(w.status),counts.writes))
 local runs,writes=w.runs,counts.writes
 menu.apply('added_fire_rate_mode.slot_z',800);settle(runs)
 step('slot Z alone writes one slot',w.result and w.result.status=='APPLIED'and counts.writes==writes+1,
  ('writes=%d'):format(counts.writes-writes))
 writes=counts.writes
 menu.apply('added_fire_rate_mode.enabled',false);settle(w.runs)
 step('disable restores 640 rpm and unbinds the selector',w.status=='disabled'and counts.writes==writes+4,
  ('writes=%d'):format(counts.writes-writes))
 menu.apply('added_fire_rate_mode.enabled',true)
 local spent=0
 while w.status~='waiting'and w.status~='blocked'and spent<20000 do frame();spent=spent+1 end
 for _=1,20 do frame()end
 step('re-enable applies the options again',w.status=='waiting'and w.result and w.result.status=='APPLIED',
  tostring(w.status))
 return results
end
'''

# SpeargunGasStunTest: the EMS Mortar shell (a stratagem-owned donor) binds ProgrammableAmmo and sets the function
# projectile (two writes) after the turret's package loads; the GAS label with its auto (generic) icon and the STUN
# label with the stun icon (three slots each) are separate operations on the two outputs; each toggle restores or
# re-applies exactly its own writes.
SPEARGUN_LIVE = r'''
return function(frame,watches,counts,lines)
 local menu=rawget(_G,'ModOptionsMenu');local mode,gas,stun=watches[1],watches[2],watches[3];local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function settle(w,runs,final)
  local spent=0
  while(w.runs<=runs or w.status=='running')and w.status~='blocked'and w.status~=final and spent<20000 do
   frame();spent=spent+1 end
  for _=1,20 do frame()end
 end
 local function applied(w)return w.status=='waiting'and w.result and w.result.status=='APPLIED'end
 step('EMS default: turret package loaded, selector and projectile written, both labels applied',applied(mode)
  and applied(gas)and applied(stun)and counts.writes==8 and(counts.package_requests or 0)==1,
  ('status=%s/%s/%s writes=%d packages=%d error=%s'):format(tostring(mode.status),tostring(gas.status),
   tostring(stun.status),counts.writes,counts.package_requests or 0,tostring(mode.error or gas.error or stun.error)))
 local writes,runs=counts.writes,gas.runs
 menu.apply('speargun_gas_stun.labels',false);settle(gas,runs,'disabled');settle(stun,stun.runs,'disabled')
 step('labels off restores the two outputs (six slots: vanilla labels and icons), the mode untouched',
  gas.status=='disabled'and stun.status=='disabled'and counts.writes==writes+6 and applied(mode),
  ('writes=%d'):format(counts.writes-writes))
 writes=counts.writes
 menu.apply('speargun_gas_stun.labels',true)
 local spent=0
 while(gas.status~='waiting'or stun.status~='waiting')and spent<20000 do frame();spent=spent+1 end
 for _=1,20 do frame()end
 step('labels on applies them again',applied(gas)and applied(stun)and counts.writes==writes+6,
  ('writes=%d'):format(counts.writes-writes))
 writes=counts.writes
 menu.apply('speargun_gas_stun.enabled',false);settle(mode,mode.runs,'disabled')
 step('disable removes the selector and the projectile, labels untouched',mode.status=='disabled'
  and counts.writes==writes+2 and applied(gas)and applied(stun),('writes=%d'):format(counts.writes-writes))
 menu.apply('speargun_gas_stun.enabled',true)
 spent=0
 while mode.status~='waiting'and mode.status~='blocked'and spent<20000 do frame();spent=spent+1 end
 for _=1,20 do frame()end
 step('re-enable applies the mode again, package already held',applied(mode)and(counts.package_requests or 0)==1,
  tostring(mode.status))
 return results
end
'''

# WeaponPresentationTest: gameplay AP (four DamageInfo lanes) and the displayed label (one trait slot) are separate
# operations; changing the label never writes a DamageInfo byte and changing the AP never writes a trait.
PRESENTATION_LIVE = r'''
return function(frame,watches,counts,lines)
 local menu=rawget(_G,'ModOptionsMenu');local ap,label=watches[1],watches[2];local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function settle(w,runs)
  local spent=0
  while(w.runs<=runs or w.status=='running')and w.status~='blocked'and spent<20000 do frame();spent=spent+1 end
  for _=1,20 do frame()end
 end
 step('defaults: AP 3 on four lanes and the HEAVY label',ap.result and ap.result.status=='APPLIED'and label.result
  and label.result.status=='APPLIED'and counts.writes==5,('writes=%d'):format(counts.writes))
 local runs,apruns,writes=label.runs,ap.runs,counts.writes
 menu.apply('weapon_presentation_test.displayed_label',3);settle(label,runs)
 step('label Medium: one trait write, AP untouched',label.result.status=='APPLIED'and counts.writes==writes+1
  and ap.runs==apruns,('writes=%d'):format(counts.writes-writes))
 runs,writes=ap.runs,counts.writes
 menu.apply('weapon_presentation_test.gameplay_ap',1);settle(ap,runs)
 step('gameplay Vanilla: four AP writes, label untouched',ap.result.status=='APPLIED'and counts.writes==writes+4,
  ('writes=%d'):format(counts.writes-writes))
 -- End on Medium again, so the harness's simulated game reset has a drift to re-apply on both operations.
 runs=ap.runs
 menu.apply('weapon_presentation_test.gameplay_ap',2);settle(ap,runs)
 return results
end
'''

def toggles_live(items, choices=(), notes=()):
    """A live program for an options-driven test mod: every option starts at its default (default-off operations are
    disabled and write nothing), then each default-on option is turned off (its operations restore exactly their
    writes) and every option is turned on (its operations apply exactly their writes). It ends with every operation
    applied, so the simulated reset re-applies all of them. items: (option id, [watch indexes], writes, default).
    choices, applied after the toggles: (choice option id, index, [watch indexes], writes, package requests so far).
    notes: log text that must have appeared by the end (for example a swapped-owner note)."""
    rows = ','.join("{option='%s',watches={%s},writes=%d,default=%s}" % (option, ','.join(map(str, indexes)), writes,
        'true' if default else 'false') for option, indexes, writes, default in items)
    picks = ','.join("{option='%s',index=%d,watches={%s},writes=%d,packages=%d}" % (option, index,
        ','.join(map(str, indexes)), writes, packages) for option, index, indexes, writes, packages in choices)
    return r'''
return function(frame,watches,counts,lines)
 local menu=rawget(_G,'ModOptionsMenu');local results={}
 local SPEC={''' + rows + r'''}
 local PICKS={''' + picks + r'''}
 local NOTES={''' + ','.join("'%s'" % note for note in notes) + r'''}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function applied(w)return w.status=='waiting'and w.result and w.result.status=='APPLIED'end
 local function state(w)return tostring(w.status)..'/'..tostring(w.result and w.result.status)..'/'..tostring(w.error)end
 local function wait(list,want)
  local function done()
   for _,w in ipairs(list)do
    if want=='applied'and not applied(w)then return false end
    if want=='disabled'and w.status~='disabled'then return false end
   end
   return true
  end
  local spent=0
  while not done()and spent<20000 do frame();spent=spent+1 end
  for _=1,20 do frame()end
 end
 local function of(item)local list={};for _,i in ipairs(item.watches)do list[#list+1]=watches[i]end;return list end
 for _,item in ipairs(SPEC)do
  local ok,detail=true,{}
  for _,w in ipairs(of(item))do
   ok=ok and(item.default and applied(w)or not item.default and w.status=='disabled')
   detail[#detail+1]=state(w)
  end
  step('default '..item.option..(item.default and' on: applied'or' off: nothing written'),ok,table.concat(detail,' '))
 end
 for _,item in ipairs(SPEC)do
  local list=of(item);local writes=counts.writes
  if item.default then
   menu.apply(item.option,false);wait(list,'disabled')
   local ok=counts.writes==writes+item.writes
   for _,w in ipairs(list)do ok=ok and w.status=='disabled'end
   step(item.option..' off restores exactly its writes',ok,('writes=%d'):format(counts.writes-writes))
   writes=counts.writes
  end
  menu.apply(item.option,true);wait(list,'applied')
  local ok,detail=counts.writes==writes+item.writes,{}
  for _,w in ipairs(list)do ok=ok and applied(w);detail[#detail+1]=state(w)end
  step(item.option..' on applies exactly its writes',ok,('writes=%d '):format(counts.writes-writes)
   ..table.concat(detail,' '))
 end
 for _,item in ipairs(PICKS)do
  local list=of(item);local writes=counts.writes;local runs={}
  for index,w in ipairs(list)do runs[index]=w.runs end
  menu.apply(item.option,item.index)
  local spent=0
  local function moved()for index,w in ipairs(list)do if w.runs<=runs[index]or w.status=='running'then return false end end
   return true end
  while not moved()and spent<20000 do frame();spent=spent+1 end
  for _=1,20 do frame()end
  local ok,detail=counts.writes==writes+item.writes and(counts.package_requests or 0)==item.packages,{}
  for _,w in ipairs(list)do ok=ok and applied(w);detail[#detail+1]=state(w)end
  step(item.option..' = '..item.index..' re-resolves exactly its writes',ok,('writes=%d packages=%d '):format(
   counts.writes-writes,counts.package_requests or 0)..table.concat(detail,' '))
 end
 for _,note in ipairs(NOTES)do
  local seen=0
  for _,line in ipairs(lines)do if line:find(note,1,true)then seen=seen+1 end end
  step('logged: '..note,seen>0,('lines=%d'):format(seen))
 end
 return results
end
'''


# Equipment coverage live tests (research/equipment-coverage-F5FEE03DCFDB.json).
EQUIPMENT_TOGGLES = {
    'example-double-edge-overheat-test': [('double_edge_overheat.later_levels', [1], 3, True),
        ('double_edge_overheat.no_ignition', [2], 1, True), ('double_edge_overheat.overheat_lock', [3], 1, False)],
    'example-warp-pack-test': [('warp_pack_test.long_warp', [1], 1, True), ('warp_pack_test.cool_pack', [2], 1, True),
        ('warp_pack_test.no_limb_damage', [3], 5, False)],
    'example-guard-dog-test': [('guard_dog_test.more_reloads', [1], 2, True), ('guard_dog_test.tough_dog', [2, 3], 2, True),
        ('guard_dog_test.drum', [4], 1, True), ('guard_dog_test.fast_gun', [5], 1, False),
        ('guard_dog_test.rover_beam', [6], 1, False), ('guard_dog_test.k9_arc', [7], 2, False)],
    'example-shield-generator-pack-test': [('shield_generator_pack_test.fast_recharge', [1], 1, True),
        ('shield_generator_pack_test.fast_restart', [2], 1, True), ('shield_generator_pack_test.slow_refill', [3], 1, False)],
    'example-directional-shield-test': [('directional_shield_test.big_barrier', [1], 1, True),
        ('directional_shield_test.long_outage', [2], 1, True), ('directional_shield_test.sturdy_emitter', [3], 1, False)],
    'example-hover-pack-test': [('hover_pack_test.long_hover', [1], 1, True), ('hover_pack_test.high_launch', [2], 1, False),
        ('hover_pack_test.quick_recharge', [3], 1, False)],
    'example-laser-cannon-test': [('laser_cannon_test.fast_beam', [1], 1, True)],
    'example-maxigun-coverage-test': [('maxigun_coverage_test.heavy_climb', [1], 1, True),
        ('maxigun_coverage_test.no_side_kick', [2], 1, True)],
}

# Projectile builder and unified donor pool live tests (research/projectile-builder-F5FEE03DCFDB.json). Speargun:
# the stun mode is the binding and function projectile (2 writes), the spare twin's expiry explosion (1) and its
# label and icon (3); the GAS label is the Speargun's own mode (3). HMG: the mode (2), then the three donor labels and
# the shared STANDARD label (3 each); switching the choice re-points only the function projectile (1 write) and loads
# that donor's package. Unified: one reference per host.
PROJECTILE_BUILDER_TOGGLES = {
    'example-speargun-projectile-builder-test': ([('speargun_projectile_builder.stun_mode', [1, 2, 3], 6, True),
        ('speargun_projectile_builder.gas_label', [4], 3, True)], (), 1),
    'example-hmgspecial-ammo-test': ([('hmg_special_ammo.enabled', [1], 2, True),
        ('hmg_special_ammo.labels', [2, 3, 4, 5], 12, True)],
        [('hmg_special_ammo.ammo', 2, [1], 1, 2), ('hmg_special_ammo.ammo', 3, [1], 1, 3),
         ('hmg_special_ammo.ammo', 1, [1], 1, 3)], 3),
    'example-unified-projectile-swap-test': ([('unified_projectile_swap.eat_scorcher', [1], 1, True),
        ('unified_projectile_swap.reprimand_napalm', [2], 1, True),
        ('unified_projectile_swap.liberator_talon', [3], 1, True),
        ('unified_projectile_swap.stalwart_amr', [4], 1, False)], (), 4),
    # ProjectileSlotTest: the Coyote's own row; each impact choice re-points one slot and loads that donor's package;
    # Vanilla restores the slot, and the grenade again needs no new package request.
    'example-projectile-slot-test': ([('projectile_slot_test.stun_rounds', [2], 1, False)],
        [('projectile_slot_test.impact', 2, [1], 1, 2), ('projectile_slot_test.impact', 3, [1], 1, 3),
         ('projectile_slot_test.impact', 4, [1], 1, 4), ('projectile_slot_test.impact', 5, [1], 1, 5),
         ('projectile_slot_test.impact', 1, [1], 1, 5), ('projectile_slot_test.impact', 2, [1], 1, 5)], 5),
    # OneTwoUnderbarrelTest: the One-Two launcher entity's own WeaponData (spread) and WeaponRounds (reserve) records.
    'example-one-two-underbarrel-test': ([('one_two_underbarrel_test.tight_grenades', [1], 2, True),
        ('one_two_underbarrel_test.grenade_pouch', [2], 3, True)], (), 0),
    # VehicleProjectileBuilderTest: the Talon bolt row's impact slot (the explicit donor-row composition: GL-21
    # package), the Patriot minigun's own ProjectileWeapon +0 (mount chain re-proven) through every donor, then the
    # shared minigun bullet row's impact slot through every effect; each switch is one write. The impact picks run
    # with the minigun swapped to EAT-17, so row 148 is edited for its other consumers and the log says the edit does
    # not reach the minigun.
    'example-vehicle-projectile-builder-test': ([('vehicle_projectile_builder.talon_impact', [3], 1, False)],
        [('vehicle_projectile_builder.projectile', index, [1], 1, packages) for index, packages in
            ((2, 2), (3, 3), (4, 4), (5, 5), (6, 6), (7, 7), (1, 7), (2, 7))]
        + [('vehicle_projectile_builder.impact', index, [2], 1, packages) for index, packages in
            ((2, 7), (3, 8), (4, 9), (5, 10), (1, 10), (2, 10))], 10,
        ('note: patriot-minigun-impact edits the EXO-45 Patriot Exosuit / right_gun projectile row',)),
}

EXTRAS = {'options-live': {'menu': MENU_STUB, 'after': OPTIONS_LIVE},
    # Event-only mods observe the game and write nothing (readOnly: exactly zero overlay writes).
    'example-event-isolation-test': {'after': EVENT_ISOLATION_LIVE, 'readOnly': True},
    'example-kill-heal-test': {'after': EVENT_WORLD_LIVE, 'readOnly': True},
    'example-death-hellbomb-test': {'after': EVENT_WORLD_LIVE, 'readOnly': True},
    'example-heavy-devastator-delayed-explosion-test': {'after': EVENT_WORLD_LIVE, 'readOnly': True},
    'example-player-kill-credited-example': {'after': EVENT_WORLD_LIVE, 'readOnly': True},
    'example-projectile-action-test': {'after': EVENT_WORLD_LIVE, 'readOnly': True},
    'example-status-action-test': {'after': EVENT_WORLD_LIVE, 'readOnly': True},
    'example-equipped-weapon-event-test': {'after': EVENT_WORLD_LIVE, 'readOnly': True},
    'example-vampiric-throwing-knives-test': {'after': EVENT_WORLD_LIVE, 'readOnly': True},
    'example-kill-stack-damage-test': {'after': KILL_STACK_LIVE},
    'example-liberator-attack-output-test': {'menu': MENU_STUB, 'after': ATTACK_OUTPUT_LIVE, 'packageRequests': 3},
    'example-runtime-effect-diagnostics': {'menu': MENU_STUB, 'after': DIAGNOSTICS_LIVE},
    'example-resupply-test': {'menu': MENU_STUB, 'after': RESUPPLY_LIVE, 'packageRequests': 1},
    'example-hmgfire-rate-modes-test': {'menu': MENU_STUB, 'after': HMG_RATES_LIVE},
    'example-added-fire-rate-mode-test': {'menu': MENU_STUB, 'after': ADDED_RATES_LIVE},
    'example-speargun-gas-stun-test': {'menu': MENU_STUB, 'after': SPEARGUN_LIVE, 'packageRequests': 1},
    'example-weapon-presentation-test': {'menu': MENU_STUB, 'after': PRESENTATION_LIVE},
    'options-missing': {'after': OPTIONS_MISSING},
    'options-missing-strict': {'after': OPTIONS_MISSING_STRICT, 'unavailable': ('liberator-damage',)},
    'options-test-mod-live': {'menu': test_mod_ids(MENU_STUB), 'after': test_mod_ids(OPTIONS_LIVE)},
    'options-test-mod-missing': {'after': test_mod_ids(OPTIONS_MISSING)},
    # Automatic asset loading: exactly one native package request per distinct catalog package, before the
    # reference is written, and none again after the simulated reset (Runtime retains its reference).
    'example-asset-test-stalwart-pod-eat700': {'packageRequests': 1},
    'example-asset-test-reprimand-talon-projectile': {'packageRequests': 1},
    'projectile-active-sources': {'packageRequests': 1},
    'registration-isolation': {'rejected': {'isolation-invalid': 'field is not exposed for SG-20 Halt'}},
    # The exact 133-operation user project: every operation registers; the one PLAS-101 Purifier row that its
    # charge levels only partly fire now needs allow_unverified_effect, so it alone is refused (logged), not all.
    'user-report-full-project': {'watches': 133, 'frames': 200000, 'resetSeconds': 20000,
        'rejected': {'gui-object-64f6c65514d7e06d97274943': 'allow_unverified_effect'}},
    # A Maxigun backpack of 1500 rounds exceeds the game's 1023 deposit limit: refused (logged), the Maxigun
    # weapon operations still apply.
    # Every operation of each ModBuilder 1.3.1 export registers and applies: the Halt edits never drop the others.
    'user-report-halt-issue-control': {'watches': 3},
    'user-report-halt-issue-all-fields': {'watches': 8, 'frames': 60000},
    'user-report-halt-issue-damage': {'watches': 5, 'frames': 60000},
    'user-report-halt-issue-sway': {'watches': 4},
    'user-report-maxigun-plus-backpack': {'rejected': {'entity-2f5a386db841be55d3be8e66':
        'outside the reviewed range for deposit.capacity (1 to 1023)'}},
    'example-explosive-projectile-swap': {'packageRequests': 1},
    'example-asset-test-frv-bastion-cannon': {'packageRequests': 1},
    'example-asset-test-mg43-pod-grenade-box': {'packageRequests': 1},
    **{name: {'menu': MENU_STUB, 'after': toggles_live(items)} for name, items in EQUIPMENT_TOGGLES.items()},
    **{name: {'menu': MENU_STUB, 'after': toggles_live(items, choices, *notes), 'packageRequests': packages}
        for name, (items, choices, packages, *notes) in PROJECTILE_BUILDER_TOGGLES.items()}}


def example_source(name, folder='projects'):
    return (ROOT / 'examples' / folder / name / 'src/addon.lua').read_text(encoding='utf-8-sig')


def wrap_example(name, folder, body):
    """An example addon body inside the SDK's addon wrapper, exactly as the built ZIP ships it: the dependency check
    runs, and the startup runs as the mod's own resource id (automatic ownership)."""
    spec_path = ROOT / 'examples' / folder / name / 'hd2runtime.json'
    if not spec_path.is_file():
        return body
    spec = json.loads(spec_path.read_text(encoding='utf-8'))
    import importlib.util
    loader = importlib.util.spec_from_file_location('hd2_sdk_cli', ROOT / 'sdk/hd2.py')
    sdk = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(sdk)
    return sdk.wrap_addon(spec['resource'], spec['requires']['hd2runtime']['min_version'], body)


def example(name, folder='projects'):
    return wrap_example(name, folder, example_source(name, folder))


# RuntimeVersionWarningTest (requires 0.29.0) and three more wrapped mods, loaded as the loader would: a prerelease
# requirement above it (0.29.1-rc.1), one equal to the installed runtime and one older. The two too-new mods fail
# closed and are reported; the dialog (presenter stubbed) appears once, only after the game state is Ship for five
# polls, naming the highest requirement; equal and older mods start and never warn.
VERSION_WARNING_LIVE = r'''
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local shown=rawget(_G,'HD2RuntimeVersionWarningShown');local started=rawget(_G,'HD2RuntimeVersionWarningResults')
 local compatibility=require('hd2runtime/api/compatibility')
 local function count(text)local n=0;for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end;return n end
 step('too-new mods fail closed, equal and older mods start',started[1][1]==false and started[2][1]==false
  and tostring(started[1][2]):find('dependency version mismatch',1,true)and started[3][1]==true and started[4][1]==true,
  tostring(started[1][2]))
 step('each too-new mod is logged once with its exact requirement',count('requires HD2Runtime 0.29.0 or newer')==1
  and count('requires HD2Runtime 0.29.1-rc.1 or newer')==1 and count('needs_equal')==0 and count('needs_older')==0,
  table.concat(lines,' | '):sub(1,400))
 step('no warning before the ship is stable',#shown==0,tostring(#shown))
 for _=1,120 do frame()end
 local installed=compatibility.installed()
 step('one aggregated warning with the highest requirement',#shown==1 and shown[1].title=='HD2Runtime update required'
  and shown[1].message=='One or more installed mods require a newer HD2Runtime version.\n\nRequired version: '
   ..'0.29.1-rc.1\nInstalled version: '..installed..'\n\nPlease update HD2Runtime.',
  shown[1]and shown[1].message or'none')
 compatibility.require_runtime('mods/test/needs_029','0.29.0','Repeat')
 for _=1,120 do frame()end
 step('once per session',#shown==1 and count('HD2Runtime update warning shown')==1 and compatibility.status().shown,
  tostring(#shown))
 step('SemVer precedence',compatibility.compare('0.29.0-rc.1','0.29.0')==-1 and compatibility.compare('0.29.0','0.28.9')==1
  and compatibility.compare('1.0.0-alpha.1','1.0.0-alpha.beta')==-1 and compatibility.compare('1.0.0+build.7','1.0.0')==0
  and compatibility.compare('1.0.0-2','1.0.0-10')==-1 and compatibility.compare('bad','1.0.0')==nil,'compare')
 return results
end
'''

# Informational only: the too-new mods fail closed and nothing is written (readOnly: exactly zero overlay writes).
EXTRAS['runtime-version-warning'] = {'after': VERSION_WARNING_LIVE, 'readOnly': True}


def version_warning_addon():
    import importlib.util
    loader = importlib.util.spec_from_file_location('hd2_sdk_cli', ROOT / 'sdk/hd2.py')
    sdk = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(sdk)
    installed = (ROOT / 'VERSION').read_text().strip()
    mods = [example('RuntimeVersionWarningTest'),
        sdk.wrap_addon('mods/test/needs_0291', '0.29.1-rc.1', 'return true', 'Needs0291'),
        sdk.wrap_addon('mods/test/needs_equal', installed, 'return true', 'NeedsEqual'),
        sdk.wrap_addon('mods/test/needs_older', '0.1.0', 'return true', 'NeedsOlder')]
    return ('''local compatibility=require('hd2runtime/api/compatibility')
local shown,polls={},0
compatibility.game_state=function()polls=polls+1;return {name=polls<=3 and'Mission'or'Ship'}end
compatibility.presenter=function(title,message)shown[#shown+1]={title=title,message=message};return true end
rawset(_G,'HD2RuntimeVersionWarningShown',shown)
local MODS={''' + ','.join(lua(m) for m in mods) + '''}
local results={}
for index,source in ipairs(MODS)do results[index]={pcall(assert(loadstring(source,'mod'..index)))}end
rawset(_G,'HD2RuntimeVersionWarningResults',results)
return true
''')


SCENARIOS = {
    'player-weapon-patch': lambda: SIMPLE_PATCH,
    'projectile-active-sources': lambda: PROJECTILE_SOURCES,
    'registration-isolation': lambda: REGISTRATION_ISOLATION,
    'user-report-full-project': lambda: user_report('A-original'),
    'user-report-ma5c-capacity-only': lambda: user_report('D2-ma5c-capacity-only'),
    'user-report-ma5c-plus-stratagem': lambda: user_report('D3-ma5c-plus-stratagem'),
    'user-report-maxigun-weapon': lambda: user_report('E-maxigun-only'),
    'user-report-maxigun-plus-backpack': lambda: user_report('E2-maxigun-plus-backpack'),
    'user-report-halt-dual-feed': lambda: user_report('F-SG-20-Halt'),
    'user-report-spray-and-pray-damage': lambda: user_report('F-SG-225SP-Breaker-Spray-Pray'),
    'user-report-sai-heat': lambda: user_report('F-LAS-12-Sai'),
    'user-report-sickle-heat': lambda: user_report('F-LAS-16-Sickle'),
    'user-report-orbital-cooldown': lambda: user_report('G-orbital-precision-strike-only'),
    'user-report-halt-issue-control': lambda: user_report('H0-control-no-halt', HALT_ISSUE),
    'user-report-halt-issue-all-fields': lambda: user_report('H1-halt-all', HALT_ISSUE),
    'user-report-halt-issue-damage': lambda: user_report('H2-halt-damage-only', HALT_ISSUE),
    'user-report-halt-issue-sway': lambda: user_report('H3-halt-sway-only', HALT_ISSUE),
    'player-weapon-transaction-gui': lambda: GUI_TRANSACTION,
    'support-weapon': lambda: example('SupportAMRProof'),
    'support-weapon-coverage': lambda: SUPPORT_COVERAGE,
    'stratagem': lambda: example('SupportStratagemCooldownProof'),
    'vehicle-armor': lambda: example('BastionReArmoredRecreation'),
    'vehicle-mount': lambda: example('FRVWeaponSwapRecreation'),
    'backpack': lambda: example('JumpPackRecreation'),
    'shield-relay': lambda: example('ShieldRelayRecreation'),
    'magazine-attachment': lambda: example('ConcussiveDrumMagazine'),
    'magazine-attachment-options': lambda: MAGAZINE_OPTIONS,
    'booster-deployed-entity': lambda: example('ArmedResupplyTurret'),
    'booster-status-effect': lambda: example('CombatStimBoost'),
    'booster-tuning': lambda: example('BoosterTuning'),
    'booster-explosion': lambda: example('IncendiaryHellpods'),
    'booster-coverage': lambda: BOOSTER_COVERAGE,
    'support-weapon-reticle': lambda: example('ReticleAmrRecreation'),
    'player-weapon-reticle': lambda: PLAYER_RETICLE,
    'fire-mode-jar5-full-auto': lambda: example('JAR5FullAuto'),
    'fire-mode-burst-and-automatic': lambda: FIRE_MODES,
    'vehicle-weapon-frv': lambda: example('M103TurretMagazine'),
    'vehicle-weapon-tank': lambda: TANK_WEAPONS,
    'vehicle-weapon-emancipator': lambda: example('EmancipatorAmmo'),
    'vehicle-weapon-lumberer': lambda: example('LumbererAmmo'),
    'vehicle-weapon-patriot': lambda: example('PatriotExosuitBuffs'),
    'stratagem-uses-unlimited': lambda: example('ExosuitUnlimitedUses'),
    'stratagem-uses-finite': lambda: STRATAGEM_USES,
    'backpack-ammo-maxigun': lambda: example('MaxigunBackpackAmmo'),
    'backpack-ammo-coverage': lambda: BACKPACK_AMMO,
    'pod-payload-surplus-eat': lambda: example('SurplusEatPodSwap'),
    'pod-payload-coverage': lambda: POD_PAYLOADS,
    'options-live': lambda: example('LiberatorDamageOptions'),
    'options-missing': OPTIONS_MISSING_ADDON,
    'options-missing-strict': lambda: OPTIONS_MISSING_ADDON().replace(*STRICT_PAGE),
    'options-test-mod-live': lambda: example('HD2RuntimeOptionsTest', 'live'),
    'options-test-mod-missing': lambda: OPTIONS_MISSING_ADDON('HD2RuntimeOptionsTest', 'live'),
    'runtime-version-warning': version_warning_addon,
}

# Every other shipped example project runs from the built ZIP too, so no example can rot unnoticed.
# Examples bound to Mod Options Menu keep their dedicated options-* scenarios.
_COVERED = set(re.findall(r"example\('(\w+)'", Path(__file__).read_text(encoding='utf-8')))
for _project in sorted((ROOT / 'examples/projects').iterdir()):
    if (_project / 'src/addon.lua').is_file() and _project.name not in _COVERED:
        SCENARIOS['example-' + re.sub(r'(?<=[a-z0-9])(?=[A-Z])', '-', _project.name).lower()] = (
            lambda name=_project.name: example(name))


def archive_resources(path):
    """Map resource-name hash to Lua source for the runtime archive inside a ZIP."""
    with zipfile.ZipFile(path) as package:
        data = package.read(next(name for name in package.namelist() if name.endswith('.patch_0')))
    count = struct.unpack_from('<I', data, 8)[0]
    found = {}
    for index in range(count):
        row = struct.unpack_from('<7Q6I', data, 104 + index * 80)
        length, version = struct.unpack_from('<II', data, row[2])
        assert version == 2, 'unexpected Lua resource version'
        found[row[0]] = data[row[2] + 8:row[2] + 8 + length]
    return found


def archive_version(resources):
    """(version, api) of the packaged runtime, read from its own metadata module (the packaged copy of VERSION)."""
    body = resources.get(resource_hash('hd2runtime/domains/metadata'))
    if body is None:
        raise AssertionError('packaged metadata module is missing')
    version = re.search(rb'\["version"\]="([^"]+)"', body)
    api = re.search(rb'\["api_version"\]=(\d+)', body)
    if not version or not api:
        raise AssertionError('packaged metadata has no version')
    return version.group(1).decode(), int(api.group(1))


def startup_line(version, api):
    return f'[HD2Runtime] HD2Runtime {version} initialized (API {api})'


def static_scan(resources):
    """Resolve every referenced internal module name against the archive by hash."""
    if resource_hash(ENTRY) not in resources:
        raise AssertionError('runtime entry resource is missing: ' + ENTRY)
    references = {}
    for body in resources.values():
        for match in REFERENCE.finditer(body):
            references.setdefault(match.group(1).decode(), 0)
            references[match.group(1).decode()] += 1
    listed = []
    modules = resources.get(resource_hash(PACKAGE_MODULES))
    if modules is not None:
        listed = [match.group(1).decode() for match in REFERENCE.finditer(modules)]
    names = sorted(set(references) | set(listed))
    unresolved = [name for name in names if resource_hash(name) not in resources]
    known = {resource_hash(name) for name in names} | {resource_hash(ENTRY)}
    return {'resources': len(resources), 'referencedModules': len(references),
        'packageModuleList': bool(modules), 'listedModules': len(listed),
        'unresolved': unresolved, 'unnamedResources': len(set(resources) - known),
        'names': names}


_ESCAPES = [chr(byte) if 32 <= byte < 127 and byte not in (34, 92) else '\\%03d' % byte for byte in range(256)]


def lua_bytes(data: bytes) -> str:
    """A Lua 5.1 string literal for arbitrary bytes."""
    return '"' + ''.join(map(_ESCAPES.__getitem__, data)) + '"'


def lua(value): return lua_bytes(str(value).encode())


def harness_sources():
    """Offline infrastructure loaded privately, never into the artifact's package tables."""
    names = ['hd2runtime/core/binary', 'hd2runtime/core/snapshot_format',
        'hd2runtime/runtime/snapshot_memory_reader', 'hd2runtime/primary_mapper/json']
    return {name: (ROOT / (name.split('/', 1)[1] + '.lua')).read_bytes() for name in names}


PROGRAM = r'''
-- Private harness modules: own cache and require, so they never populate package.loaded.
local private_loaded={}
local function private_require(name)
 if private_loaded[name]~=nil then return private_loaded[name]end
 if name=='ffi' or name=='bit' then return require(name)end
 local chunk=assert(loadstring(assert(HARNESS[name],'harness module missing: '..name),'@harness/'..name))
 setfenv(chunk,setmetatable({require=private_require},{__index=_G}))
 local value=chunk(name);if value==nil then value=true end
 private_loaded[name]=value;return value
end
local json=private_require('hd2runtime/primary_mapper/json')
local source=private_require('hd2runtime/runtime/snapshot_memory_reader').open(SNAPSHOT_PATH,{
 expected_exe_sha=EXE_SHA,expected_dll_sha=DLL_SHA})

-- Copy-on-write overlay adapter handed to the packaged API as windows_write.create().
local PAGE=4096
local overlay,protection,simulated={}, {},0
local counts={writes=0,protection_changes=0,module_hashes=0}
local runtime={mode='live-overlay'}
local function original_protect(at)return source.query(at).protect end
function runtime.module(name)return source.module(name)end
function runtime.address(handle)return source.address(handle)end
function runtime.system_info()return source.system_info()end
function runtime.module_hash(handle)counts.module_hashes=counts.module_hashes+1;return source.module_hash(handle)end
function runtime.monotonic_time()return simulated end
function runtime.query(at)
 local r,why=source.query(at)
 if not r or r.allocation_base==0 then return r,why end
 local low,high=r.base,r.base+r.size
 if next(protection)==nil then return r end
 local pages={}
 for page in pairs(protection)do if page>=low and page<high then pages[#pages+1]=page end end
 if #pages==0 then return r end
 table.sort(pages)
 for _,page in ipairs(pages)do
  if at>=page and at<page+PAGE then r.base=page;r.size=PAGE;r.protect=protection[page];return r end
  if page>at then high=math.min(high,page)else low=math.max(low,page+PAGE)end
 end
 r.base=low;r.size=high-low;return r
end
function runtime.read(at,n)
 local bytes,why=source.read(at,n)
 if not bytes then return nil,why end
 for address,value in pairs(overlay)do
  if address<at+n and address+#value>at then
   local first=math.max(address,at);local last=math.min(address+#value,at+n)
   bytes=bytes:sub(1,first-at)..value:sub(first-address+1,last-address)..bytes:sub(last-at+1)
  end
 end
 return bytes
end
function runtime.protect(page,size,value)
 assert(page%PAGE==0 and size==PAGE,'overlay protect extent')
 counts.protection_changes=counts.protection_changes+1
 local old=protection[page] or original_protect(page)
 if value==original_protect(page)then protection[page]=nil else protection[page]=value end
 return old
end
function runtime.write(at,bytes)
 assert((protection[at-at%PAGE] or original_protect(at-at%PAGE))==4,'overlay write without writable page')
 counts.writes=counts.writes+1;overlay[at]=bytes
 return true,nil,#bytes
end

-- Simulated engine package loader. The artifact's single native package call is observed here instead of
-- executed; a requested package resolves asynchronously (queued, then resident after LOAD_SECONDS), as the
-- engine's load queue does. Code proofs and the reference-map checks still run against snapshot memory.
local LOAD_SECONDS=0.35
local package_requests,package_log={},{}
counts.package_requests=0
local function hex_of(id)
 local out={};for index=8,1,-1 do out[#out+1]=string.format('%02X',id:byte(index))end
 return '0x'..table.concat(out)
end
function runtime.package_request(entry,instance,id)
 assert(type(entry)=='number' and type(instance)=='number' and type(id)=='string' and #id==8,'package request shape')
 local hex=hex_of(id)
 assert(not package_requests[hex],'duplicate native package request for '..hex)
 counts.package_requests=counts.package_requests+1
 package_requests[hex]=simulated;package_log[#package_log+1]=hex
 return true
end
function runtime.package_state(hex)
 local at=package_requests[hex]
 if not at then return 'absent' end
 return simulated-at>=LOAD_SECONDS and 'resident' or 'queued'
end

-- Emulated engine resource lookup: archive resources resolve only during startup.
local startup_open=true
local lookups={startup=0,late_found=0,late_missing={}}
local adapter_module='return {create=function()return rawget(_G,"HD2RuntimeArtifactOverlay")end}'
rawset(_G,'HD2RuntimeArtifactOverlay',runtime)
local function engine_searcher(name)
 local body=RESOURCES[name]
 if name==WRITE_ADAPTER and body then body=adapter_module end
 if not body then return '\n\tno resource '..name end
 if not startup_open then
  lookups.late_missing[#lookups.late_missing+1]=name
  return '\n\tno resource '..name..' (startup package unloaded)'
 end
 lookups.startup=lookups.startup+1
 return assert(loadstring(body,'@'..name..'.lua'))
end
-- LuaJIT's built-in libraries stay available, as in the game; every archive resource must come from the engine.
for name in pairs(package.preload)do if name~='ffi'and name~='bit'then package.preload[name]=nil end end
local preload_searcher=package.loaders[1]
for index=#package.loaders,1,-1 do package.loaders[index]=nil end
package.loaders[1]=preload_searcher;package.loaders[2]=engine_searcher

local lines={}
rawset(_G,'CowboyBingusModLoader',{api=1,version=16,modules={},
 open_log=function()return {write=function(_,text)lines[#lines+1]=text end,flush=function()end}end})
rawset(_G,'update',nil)

-- Startup: Bingus requires the runtime entry, then the gameplay addon.
local watches={}
local ok,why=pcall(require,ENTRY)
if not ok then return json.encode({startup_error=tostring(why),log=lines})end
local chunk=assert(loadstring(ADDON,'@'..SCENARIO..'/addon.lua'))
local ok_addon,returned=pcall(chunk)
if not ok_addon then return json.encode({startup_error=tostring(returned),log=lines})end
-- The SDK wrapper returns true for an addon that returns nothing; only operation handles are watches.
if type(returned)=='table' and returned.status==nil then
 for _,watch in ipairs(returned)do watches[#watches+1]=watch end
elseif type(returned)=='table' then watches[#watches+1]=returned end
startup_open=false
if MENU then assert(loadstring(MENU,'@mods/cowboybingus/mod_options_menu'))()end

local FRAME=FRAME_SECONDS
local function frame()simulated=simulated+FRAME;if update then update(FRAME)end end
local function done(watch)
 if watch.runs~=nil then return watch.status=='rejected' or watch.status=='unavailable' or watch.status=='disabled'
  or (watch.runs>=1 and watch.status=='waiting')end
 return watch.status=='complete' or watch.status=='rejected' or watch.status=='cancelled'
end
local function settled()for _,w in ipairs(watches)do if not done(w)then return false end end;return true end
local frames=0
while not settled()and frames<MAX_FRAMES do frame();frames=frames+1 end
local function describe()
 local out={}
 for _,w in ipairs(watches)do
  out[#out+1]={id=w.id,kind=w.runs~=nil and 'ensure' or 'once',status=w.status,runs=w.runs,
   error=w.error,result=w.result and w.result.status,code=w.result and w.result.code,
   writes=w.result and w.result.writes}
 end
 return out
end
if AFTER then AFTER_RESULTS=assert(loadstring(AFTER))()(frame,watches,counts,lines)end
local report={scenario=SCENARIO,settled=settled(),startup_seconds=simulated,watches=describe(),
 counts={writes=counts.writes,protection_changes=counts.protection_changes,module_hashes=counts.module_hashes,
  package_requests=counts.package_requests},packages=package_log}

-- Simulated game reset: ensures must detect drift and re-apply with lookups still closed.
local ensures={}
for index,w in ipairs(watches)do
 if w.runs~=nil and w.status~='rejected' and w.status~='unavailable' then ensures[index]=w.runs end
end
if next(ensures)then
 overlay={};protection={}
 local seconds=0
 local function reapplied()
  for index,runs in pairs(ensures)do
   local w=watches[index]
   if w.status=='rejected' or w.runs<=runs then return false end
  end
  return true
 end
 while not reapplied()and seconds<RESET_SECONDS do frame();seconds=seconds+FRAME end
 report.reset={reapplied=reapplied(),seconds=seconds,watches=describe()}
end
report.lookups={startup=lookups.startup,late_missing=lookups.late_missing}
report.after=AFTER_RESULTS
report.log=lines
source.close()
return json.encode(report)
'''


def prelude(resources, names, snapshot):
    """The scenario-independent head of every scenario program: archive resources, harness and fingerprints."""
    profile = resources[resource_hash('hd2runtime/schemas/current')].decode('latin-1')
    exe_sha = re.search(r'"exe_sha"\]="([0-9A-Fa-f]{64})"', profile).group(1)
    dll_sha = re.search(r'"dll_sha"\]="([0-9A-Fa-f]{64})"', profile).group(1)
    table = {name: resources[resource_hash(name)] for name in names + [ENTRY] if resource_hash(name) in resources}
    return ('local RESOURCES={' + ','.join('[' + lua(k) + ']=' + lua_bytes(v) for k, v in table.items()) + '}\n'
        + 'local HARNESS={' + ','.join('[' + lua(k) + ']=' + lua_bytes(v) for k, v in harness_sources().items()) + '}\n'
        + 'local SNAPSHOT_PATH=' + lua(Path(snapshot).resolve()) + '\nlocal EXE_SHA=' + lua(exe_sha)
        + '\nlocal DLL_SHA=' + lua(dll_sha) + '\nlocal ENTRY=' + lua(ENTRY) + '\nlocal WRITE_ADAPTER=' + lua(WRITE_ADAPTER))


def scenario_program(scenario, addon):
    """The scenario-specific tail that follows the prelude."""
    return ('\nlocal SCENARIO=' + lua(scenario) + '\nlocal ADDON=' + lua(addon)
        + '\nlocal MENU=' + (lua(EXTRAS.get(scenario, {}).get('menu')) if EXTRAS.get(scenario, {}).get('menu') else 'nil')
        + '\nlocal AFTER=' + (lua(EXTRAS.get(scenario, {}).get('after')) if EXTRAS.get(scenario, {}).get('after') else 'nil')
        # Guarded operations resolve one at a time; a large project needs a larger simulated window.
        + '\nlocal MAX_FRAMES=' + str(EXTRAS.get(scenario, {}).get('frames', 36000))
        + '\nlocal RESET_SECONDS=' + str(EXTRAS.get(scenario, {}).get('resetSeconds', 3600))
        + '\nlocal FRAME_SECONDS=' + repr(EXTRAS.get(scenario, {}).get('frameSeconds', 0.1))
        + '\nlocal AFTER_RESULTS\n' + PROGRAM)


def run_scenario(resources, names, scenario, addon, snapshot, head=None):
    sys.path.insert(0, str(ROOT / 'sdk'))
    from tools.lua_runner import execute
    program = (head or prelude(resources, names, snapshot)) + scenario_program(scenario, addon)
    return json.loads(execute(program.encode()))


def check(report):
    """Return the failures for one scenario report."""
    failures = []
    if 'startup_error' in report:
        return ['startup: ' + report['startup_error']]
    if report.get('lookups', {}).get('late_missing'):
        failures.append('modules required after startup: ' + ', '.join(sorted(set(report['lookups']['late_missing']))))
    if not report.get('settled'):
        failures.append('did not settle')
    expected_rejections = EXTRAS.get(report.get('scenario'), {}).get('rejected', {})
    for watch_id, reason in expected_rejections.items():
        line = f'[HD2Runtime] ensure {watch_id} rejected: '
        if not any(entry.startswith(line) and reason in entry for entry in report.get('log') or []):
            failures.append(f'{watch_id}: expected a logged registration rejection containing {reason!r}')
    expected_watches = EXTRAS.get(report.get('scenario'), {}).get('watches')
    if expected_watches is not None and len(report.get('watches', [])) != expected_watches:
        failures.append(f"expected {expected_watches} registered operations, got {len(report.get('watches', []))}")
    for watch in report.get('watches', []):
        if watch.get('id') in expected_rejections:
            if watch.get('status') != 'rejected' or watch.get('writes'):
                failures.append('%s: expected a rejected registration, got status=%s' % (watch.get('id'),
                    watch.get('status')))
            continue
        if watch.get('id') in EXTRAS.get(report.get('scenario'), {}).get('unavailable', ()):
            if watch.get('status') != 'unavailable' or watch.get('writes'):
                failures.append('%s: expected an inactive operation, got status=%s' % (watch.get('id'),
                    watch.get('status')))
            continue
        if watch.get('result') not in ('APPLIED', 'RESIDENT') or watch.get('status') == 'rejected':
            failures.append('%s: status=%s result=%s error=%s' % (watch.get('id'), watch.get('status'),
                watch.get('result'), watch.get('error')))
    if not str(report.get('scenario', '')).startswith('options-'):
        if any('Mod Options Menu' in line for line in report.get('log', [])):
            failures.append('a mod without options logged about Mod Options Menu')
    for step in report.get('after') or []:
        if not step.get('passed'):
            failures.append('live option step failed: %s %s' % (step.get('name'), step.get('detail') or ''))
    reset = report.get('reset')
    if reset is not None and not reset['reapplied']:
        failures.append('ensure did not re-apply after reset')
    if any('not found' in line for line in report.get('log', [])):
        failures.append('log reports a missing module')
    return failures


def validate(zip_path, snapshot=SNAPSHOT, scenarios=None, jobs=None):
    """Validate a built runtime ZIP; raise AssertionError with details on any failure.

    Scenarios are independent Lua states, so they run in up to `jobs` worker processes. Reports are checked in
    scenario order, so the result and any failure text do not depend on scheduling."""
    resources = archive_resources(zip_path)
    scan = static_scan(resources)
    version, api = archive_version(resources)
    line = startup_line(version, api)
    result = {'artifact': Path(zip_path).name, 'static': {k: v for k, v in scan.items() if k != 'names'},
        'version': version, 'startupLine': line, 'scenarios': {}, 'gameProcessAccess': False, 'realWrites': 0}
    failures = ['unresolved module: ' + name for name in scan['unresolved']]
    named = re.search(r'HD2Runtime-(\d+\.\d+\.\d+)-runtime', Path(zip_path).name)
    if named and named.group(1) != version:
        failures.append(f'artifact name says {named.group(1)} but the packaged runtime reports {version}')
    if not scan['packageModuleList']:
        failures.append('package module list is missing: ' + PACKAGE_MODULES)
    names = list(scenarios or SCENARIOS)
    head = prelude(resources, scan['names'], snapshot).encode()
    reports = [json.loads(raw) for raw in parallel.lua_programs(
        [['head', scenario_program(name, SCENARIOS[name]()).encode()] for name in names], {'head': head}, jobs)]
    for name, report in zip(names, reports):
        problems = check(report)
        # Every session names the packaged runtime version exactly once, as its first log line.
        log = [entry.rstrip(chr(13) + chr(10)) for entry in report.get('log') or []]
        if log.count(line) != 1 or not log or log[0] != line:
            problems.append(f'startup version line {line!r} expected once as the first log line '
                f'(found {log.count(line)}, first {log[0] if log else None!r})')
        result['scenarios'][name] = {'passed': not problems, 'problems': problems,
            'watches': report.get('watches'), 'reset': report.get('reset', {}).get('reapplied'),
            'overlayWrites': report.get('counts', {}).get('writes'),
            'moduleHashes': report.get('counts', {}).get('module_hashes'),
            'lateLookupsMissing': sorted(set(report.get('lookups', {}).get('late_missing', []))),
            'packageRequests': report.get('counts', {}).get('package_requests', 0)}
        expected = EXTRAS.get(name, {}).get('packageRequests')
        if expected is not None and report.get('counts', {}).get('package_requests') != expected:
            problems.append('expected %s native package requests, got %s' % (expected,
                report.get('counts', {}).get('package_requests')))
        failures += [name + ': ' + problem for problem in problems]
    result['passed'] = not failures
    if failures:
        raise AssertionError('packaged runtime validation failed:\n' + '\n'.join(failures)
            + '\n' + json.dumps(result, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('zip', type=Path, help='built HD2Runtime-<version>-runtime.zip')
    parser.add_argument('--snapshot', type=Path, default=SNAPSHOT)
    parser.add_argument('--scenario', action='append', choices=sorted(SCENARIOS))
    parser.add_argument('--output', type=Path, help='write the JSON report here')
    parallel.add_argument(parser)
    args = parser.parse_args()
    parallel.configure(args.jobs)
    try:
        result = validate(args.zip, args.snapshot, args.scenario, args.jobs)
    except AssertionError as error:
        print(error)
        raise SystemExit(1)
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + '\n')
    for name, item in result['scenarios'].items():
        print(name, 'PASS' if item['passed'] else 'FAIL', 'writes=%s' % item['overlayWrites'],
            'reset_reapplied=%s' % item['reset'])


if __name__ == '__main__':
    main()
