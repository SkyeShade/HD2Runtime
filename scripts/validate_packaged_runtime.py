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
3. Outcomes: every operation a scenario registers (from hd2.diagnostics.operations(), so an operation the addon
   kept no handle for counts too) is classified as applied, intentionally not applicable (an option-bound
   operation switched off or without its menu, declared by the scenario), rejected, or skipped (never applied).
   Every operation is part of the scenario's expected mutation unless the scenario declares it a negative control
   (`rejected`, with the reason) or not applicable (`unavailable`); a refused or skipped operation fails the
   scenario even when the resulting state looks right. An operation applied only through the legacy SDK path
   (docs/legacy-sdk-compatibility.md) must be declared (`legacy`, with its fields). A mutation scenario must write;
   a read-only one must not.

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
MODBUILDER_EXPORT = USER_REPORT / 'F-SG-20-Halt.wrapped.lua'


def modbuilder_wrap(resource, sdk_version, body):
    """ModBuilder's addon wrapper (ModExporter.Wrap), cut from a real ModBuilder 1.3.1 export, around another body,
    resource and bound SDK version. `body` is what ModBuilder's generator writes inside start()."""
    text = MODBUILDER_EXPORT.read_text(encoding='utf-8')
    marker = 'local function start()\n'
    head = text[:text.index(marker) + len(marker)]
    tail = text[text.index('\nend\nlocal state=start() or true'):]
    head = head.replace("version('0.27.0')", "version('" + sdk_version + "')")
    head = head.replace('mods/nephelym/nephelym_s_weaponry_rebalance', resource)
    assert "version('" + sdk_version + "')" in head and resource in head, 'ModBuilder wrapper shape changed'
    return head + "local hd2=require('mods/skyeshade/hd2runtime')\n" + body + tail


# Legacy SDK compatibility (docs/legacy-sdk-compatibility.md): the user report's PLAS-101 Purifier drag edit, exactly
# as ModBuilder 1.3.1 exported it for SDK 0.27.0 (no allow_unverified_effect). A project bound to SDK 0.27.0 applies
# it as a legacy operation; one bound to 0.28.0 must carry the acknowledgement. Each mod also registers controls: a
# field that already needed the acknowledgement in 0.27.0 (refused for every mod) and an unprotected field (applied).
PURIFIER_DRAG = r"""operations[#operations+1]=hd2.ensure({patch={id='%s',
    target=hd2.weapon('PLAS-101 Purifier'):attack('primary'):projectile(),allow_shared=true,%s
    field=hd2.fields.projectile.drag,expect=1.5,value=0.8}})
"""
LEGACY_CONTROLS = r"""operations[#operations+1]=hd2.ensure({patch={id='control-purifier-ergonomics',
    target=hd2.weapon('PLAS-101 Purifier'),field=hd2.fields.weapon.ergonomics,expect=65,value=70}})
operations[#operations+1]=hd2.ensure({patch={id='control-coyote-burst',target=hd2.weapon('AR-2 Coyote'),
    field=hd2.fields.fire_mode.burst_rounds,expect=3,value=4}})
"""


def legacy_scenario(sdk_version, operation_id, acknowledged=False):
    body = ('local operations={}\n' + PURIFIER_DRAG % (operation_id, 'allow_unverified_effect=true,'
        if acknowledged else '') + LEGACY_CONTROLS + 'return operations\n')
    return modbuilder_wrap('mods/hd2runtime_validation/sdk_' + sdk_version.replace('.', '_'), sdk_version, body)


def user_report(name, folder=USER_REPORT):
    return (folder / (name + '.wrapped.lua')).read_text(encoding='utf-8')


# ModBuilder issue 2 (tests/fixtures/user-reports/modbuilder-issue-2-halt): ModBuilder 1.3.1 exports editing every
# SG-20 Halt field next to unrelated weapons. With the published 0.27.0 the first Halt operation aborted the addon.
HALT_ISSUE = ROOT / 'tests/fixtures/user-reports/modbuilder-issue-2-halt/generated'
# The HMG read-budget report (tests/fixtures/user-reports/hmg-read-budget): the user's exact ModBuilder 1.3.1 / SDK
# 0.27.0 package, as its ZIP ships it. Its MG-206 plan (six operations, 19 fields) exhausted the guarded read budget.
HMG_READ_BUDGET = ROOT / 'tests/fixtures/user-reports/hmg-read-budget'


# Active projectile sources from the shipped archive: the Reprimand's own member is its fired projectile (the live
# PASS control); the Liberator's attack.projectile is refused as dormant (the live FAIL control) and the same donor
# goes to its active source, the default ammunition delta, after the donor package is loaded.
# More projectile donors (research/projectile-donors-F5FEE03DCFDB.json, docs/attack-outputs.md "More donors"): a
# stratagem's Eagle payload, an orbital shell and a support weapon's second projectile each become a host's projectile
# from the shipped archive (the donor's own component re-proven live, its package loaded first); an unacknowledged
# donor is refused at registration.
PROJECTILE_DONORS = r'''local hd2=require('mods/skyeshade/hd2runtime')
local ack={allow_unverified_reference=true,allow_unverified_effect=true}
local function swap(id,target,donor,acknowledged)
    local spec={id=id,target=target,field=hd2.fields.attack.projectile,expect=target:projectile(),
        value=hd2.attack_output(donor)}
    if acknowledged then for k,v in pairs(ack)do spec[k]=v end end
    return hd2.ensure({patch=spec})
end
return {
    swap('reprimand-500kg',hd2.weapon('SMG-32 Reprimand'):attack('primary'),'Eagle 500kg Bomb',true),
    swap('stalwart-precision',hd2.support_weapon('M-105 Stalwart'):attack('primary'),'Orbital Precision Strike',true),
    swap('apw-ac8-flak',hd2.support_weapon('APW-1 Anti-Materiel Rifle'):attack('primary'),
        'AC-8 Autocannon (projectile 284)',true),
    -- The same class (conventional_plain) on a player host: only the donor's own rule refuses it.
    swap('arbitrator-hmg-no-ack',hd2.weapon('AR-11 Arbitrator'):attack('primary'),'E/MG-101 HMG Emplacement',false),
}
'''
# Every donor of research/projectile-donors-F5FEE03DCFDB.json, each on its own component host (acknowledged): each
# one's component re-proven live, its package loaded, its reference written.
DONOR_HOSTS = [('weapon', n) for n in ('AR-11 Arbitrator', 'AR-23A Liberator Carbine', 'AR-23C Liberator Concussive',
    'AR-23P Liberator Penetrator', 'AR-59 Suppressor', 'AR-61 Tenderizer', 'AR/GL-21 One-Two', 'BR-14 Adjudicator',
    'CB-9 Exploding Crossbow', 'GP-20 Ultimatum', 'M6C/SOCOM Pistol', 'M7S SMG', 'MA5C Assault Rifle', 'P-113 Verdict',
    'P/40-K Bolt Pistol', 'PLAS-1 Scorcher', 'R-2 Amendment', 'R-36 Eruptor', 'R-63CS Diligence Counter Sniper',
    'R-72 Censor', 'R/40-K Hot-Shot Marksman Rifle', 'SG-225SP Breaker Spray&Pray', 'SG-8P Punisher Plasma',
    'SMG-203 Gallant', 'SMG-32 Reprimand', 'SMG/FLAM-34 Stoker', 'StA-11 SMG', 'StA-52 Assault Rifle',
    'VG-70 Variable')] + [('support_weapon', n) for n in ('APW-1 Anti-Materiel Rifle', 'EAT-17 Expendable Anti-Tank',
    'EAT-411 Leveller', 'EAT-700 Expendable Napalm', 'GL-21 Grenade Launcher', 'M-105 Stalwart',
    'MG-206 Heavy Machine Gun', 'S-11 Speargun')]


def projectile_donors_all():
    donors = json.loads((ROOT / 'research/projectile-donors-F5FEE03DCFDB.json').read_text(encoding='utf-8'))['donors']
    if len(donors) > len(DONOR_HOSTS):
        raise ValueError('more donors than component hosts')
    lines = ["local hd2=require('mods/skyeshade/hd2runtime')", 'local out={}']
    for index, donor in enumerate(donors):
        kind, host = DONOR_HOSTS[index]
        lines.append("do local t=hd2.%s(%s):attack('primary');out[#out+1]=hd2.ensure({patch={id=%s,target=t,"
            "field=hd2.fields.attack.projectile,expect=t:projectile(),value=hd2.attack_output(%s),"
            "allow_unverified_reference=true,allow_unverified_effect=true}})end"
            % (kind, lua(host), lua('donor-%d' % donor['projectileType']), lua(donor['name'])))
    lines.append('return out')
    return '\n'.join(lines) + '\n'


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

# Calldown codes (hd2.fields.stratagem.calldown_code, docs/stratagem-calldown-code.md): a code patch and a transaction
# that changes a code and the definition cooldown together, through hd2.ensure. Inline rather than an example project:
# the field is unreleased, so an example would need a min_version above this runtime.
STRATAGEM_CALLDOWN = r'''local hd2=require('mods/skyeshade/hd2runtime')
local operations={}
operations[#operations+1]=hd2.ensure({patch={id='calldown-120mm',target=hd2.stratagem('Orbital 120mm HE Barrage'),
    field=hd2.fields.stratagem.calldown_code,expect={'right','right','down','left','right','down'},
    value={'up','up','down','down'}}})
operations[#operations+1]=hd2.ensure({transaction={id='precision-code-and-cooldown',
    target=hd2.stratagem('Orbital Precision Strike'),changes={
        {field=hd2.fields.stratagem.definition_cooldown,expect=80,value=60},
        {field=hd2.fields.stratagem.calldown_code,expect={'right','right','up'},value={'right','up','right','up'}}}}})
return operations
'''
STRATAGEM_CALLDOWN_LIVE = r'''
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local hd2=require('mods/skyeshade/hd2runtime')
 local loaded=package.loaded['hd2runtime/runtime/calldown_codes']and package.loaded['hd2runtime/runtime/stratagem_hud']
 step('the calldown code subsystem and its HUD sync were loaded at startup from the packaged archive',loaded~=nil)
 local calldown=require('hd2runtime/runtime/calldown_codes')
 local hud=require('hd2runtime/runtime/stratagem_hud')
 local world=require('hd2runtime/runtime/event_world').open()
 local proven,why=calldown.prove(world.runtime)
 local hud_proven,hud_why=hud.prove(world)
 step('the calldown reader pins and the HUD pins prove on the snapshot game.dll',proven==true and hud_proven==true,
  tostring(why)..' '..tostring(hud_why))
 -- The HUD check runs every 0.25 s; the last write may have landed just now.
 for _=1,5 do frame()end
 local rows=calldown.list()
 local function find(name)for _,row in ipairs(rows)do if row.name==name then return row end end end
 local barrage,precision=find('Orbital 120mm HE Barrage'),find('Orbital Precision Strike')
 step('both rows hold their new codes in Runtime-owned arrays: 2 + 3 writes (count, pointer; and the cooldown), '
  ..'2 owned arrays',#rows==2 and barrage and calldown.text(barrage.values)=='up up down down'
  and calldown.text(barrage.native)=='right right down left right down'
  and precision and calldown.text(precision.values)=='right up right up' and counts.writes==5
  and counts.owned_blocks==2,('rows=%d writes=%d owned=%d'):format(#rows,counts.writes,counts.owned_blocks))
 step('aboard the ship the HUD sync waits for a mission: nothing drawn, the watch runs',barrage and barrage.pending
  and barrage.hud==nil and precision.pending and calldown.watching(),('pending=%s hud=%s watching=%s'):format(
  tostring(barrage and barrage.pending),tostring(barrage and barrage.hud and barrage.hud.state),
  tostring(calldown.watching())))
 local too_long=hd2.ensure({patch={id='calldown-too-long',target=hd2.stratagem('Orbital 120mm HE Barrage'),
  field=hd2.fields.stratagem.calldown_code,expect={'right','right','down','left','right','down'},
  value={'up','up','up','up','up','up','up','up','up','up'}}})
 local equal=hd2.ensure({patch={id='calldown-equal',target=hd2.stratagem('Orbital 120mm HE Barrage'),
  field=hd2.fields.stratagem.calldown_code,expect={'right','right','down','left','right','down'},
  value={'right','right','up'}}})
 local bad=hd2.ensure({patch={id='calldown-bad-direction',target=hd2.stratagem('Orbital 120mm HE Barrage'),
  field=hd2.fields.stratagem.calldown_code,expect={'right','right','down','left','right','down'},value={'up','north'}}})
 for _=1,20 do frame()end
 step('a code longer than 9, a code equal to another stratagem\'s and an unknown direction are rejected at '
  ..'registration and write nothing',too_long.status=='rejected'
  and tostring(too_long.error):find('1 to 9 directions',1,true)~=nil and equal.status=='rejected'
  and tostring(equal.error):find('allow_unverified_effect',1,true)~=nil and bad.status=='rejected'
  and tostring(bad.error):find('north',1,true)~=nil and counts.writes==5,
  tostring(too_long.error)..' | '..tostring(equal.error)..' | '..tostring(bad.error))
 -- Before the Lua state goes away: both rows get their native pointer and count back (the HUD waits: no mission).
 calldown.finalize_for_tests()
 rows=calldown.list()
 barrage,precision=find('Orbital 120mm HE Barrage'),find('Orbital Precision Strike')
 step('finalize restores both rows to their native arrays (count and pointer each): 4 writes',barrage
  and calldown.text(barrage.values)=='right right down left right down' and precision
  and calldown.text(precision.values)=='right right up' and counts.writes==9,'writes='..counts.writes)
 return results
end
'''

# Presentation (hd2.fields.stratagem.presentation_*, docs/stratagem-presentation.md): the 120mm presents as the
# Orbital Gas Strike (all four members, one transaction) and the Precision Strike takes the Railcannon's icon, each
# value an existing vanilla resource named by its stratagem. Inline: the fields are unreleased.
STRATAGEM_PRESENTATION = r'''local hd2=require('mods/skyeshade/hd2runtime')
local S=hd2.fields.stratagem
local operations={}
operations[#operations+1]=hd2.ensure({transaction={id='presentation-120mm',target=hd2.stratagem('Orbital 120mm HE Barrage'),
    changes={
        {field=S.presentation_name,expect='Orbital 120mm HE Barrage',value='Orbital Gas Strike'},
        {field=S.presentation_name_cased,expect='Orbital 120mm HE Barrage',value='Orbital Gas Strike'},
        {field=S.presentation_description,expect='Orbital 120mm HE Barrage',value='Orbital Gas Strike'},
        {field=S.presentation_icon,expect='Orbital 120mm HE Barrage',value=hd2.stratagem('Orbital Gas Strike')}}}})
operations[#operations+1]=hd2.ensure({patch={id='presentation-precision-icon',
    target=hd2.stratagem('Orbital Precision Strike'),field=S.presentation_icon,expect='Orbital Precision Strike',
    value='Orbital Railcannon Strike'}})
return operations
'''
STRATAGEM_PRESENTATION_LIVE = r'''
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function count(text)local n=0;for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end;return n end
 step('the presentation fields resolve from the packaged archive: 4 + 1 guarded writes, logged semantically',
  counts.writes==5 and count('stratagem.presentation.icon Orbital 120mm HE Barrage -> Orbital Gas Strike')==1
  and count('stratagem.presentation.icon Orbital Precision Strike -> Orbital Railcannon Strike')==1,
  'writes='..counts.writes)
 local hd2=require('mods/skyeshade/hd2runtime')
 local S=hd2.fields.stratagem
 local bad=hd2.ensure({patch={id='presentation-raw',target=hd2.stratagem('Orbital 120mm HE Barrage'),
  field=S.presentation_name,expect='Orbital 120mm HE Barrage',value=0x34DEFEED}})
 local unknown=hd2.ensure({patch={id='presentation-unknown',target=hd2.stratagem('Orbital 120mm HE Barrage'),
  field=S.presentation_icon,expect='Orbital 120mm HE Barrage',value='No Such Stratagem'}})
 for _=1,20 do frame()end
 step('a raw localization id and an unknown stratagem are rejected at registration and write nothing',
  bad.status=='rejected'and tostring(bad.error):find('raw localization ids',1,true)~=nil
  and unknown.status=='rejected'and tostring(unknown.error):find('not a catalogued stratagem',1,true)~=nil
  and counts.writes==5,tostring(bad.error)..' | '..tostring(unknown.error))
 return results
end
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
 local injury=hd2.actions.injure(hd2.local_player(),'r_hand',5)
 step('an injury aboard the ship is refused (not in a mission)',injury.status=='refused'and injury.code=='NOT_IN_MISSION',
  tostring(injury.code)..' '..tostring(injury.reason))
 step('the injury limbs resolve from the packaged archive',#hd2.actions.limbs()==6,tostring(#hd2.actions.limbs()))
 local healed=hd2.actions.heal_limb(hd2.local_player(),'r_hand')
 local all=hd2.actions.heal_limbs(hd2.local_player())
 local kick=hd2.actions.add_velocity(hd2.local_player(),{x=0,y=0,z=5})
 step('a limb heal and a velocity kick aboard the ship are refused (not in a mission)',healed.code=='NOT_IN_MISSION'
  and all.code=='NOT_IN_MISSION'and kick.code=='NOT_IN_MISSION',tostring(healed.code)..' '..tostring(all.code)..' '
  ..tostring(kick.code))
 local boom=hd2.explosions.spawn('R-36 Eruptor',{position={x=1,y=2,z=3}})
 step('an explosion aboard the ship is refused (not in a mission)',boom.status=='refused'and boom.code=='NOT_IN_MISSION',
  tostring(boom.code)..' '..tostring(boom.reason))
 step('every catalogued explosion resolves from the packaged archive',#hd2.explosions.list()==16,
  tostring(#hd2.explosions.list()))
 step('the projectile and status catalogs resolve from the packaged archive',#hd2.projectiles.list()==67
  and #hd2.status.list()==11,tostring(#hd2.projectiles.list())..' '..tostring(#hd2.status.list()))
 local shot=hd2.projectiles.spawn('R-36 Eruptor',{position={x=1,y=2,z=3},direction={x=1,y=0,z=0}})
 step('a projectile aboard the ship is refused',shot.status=='refused'and(shot.code=='NOT_IN_MISSION'
  or shot.code=='PROJECTILE_UNAVAILABLE'),tostring(shot.code))
 local me=hd2.local_player()
 step('equipped_weapon resolves from the packaged archive',me==nil or type(me.equipped_weapon)=='function')
 -- Runtime-owned custom projectile rows (docs/custom-projectile-rows.md), required after startup like the proof does.
 local custom_ok,custom=pcall(require,'hd2runtime/runtime/custom_projectiles')
 step('the custom projectile modules resolve from the packaged archive after startup',custom_ok
  and type(custom)=='table' and type(custom.define)=='function',tostring(custom))
 if custom_ok then
  local world_module=require('hd2runtime/runtime/event_world')
  local world=world_module.open()
  local vanilla=world and world_module.projectile_row(world,144)
  local def,code,reason=custom.define(custom.DEVELOPMENT_PROOF)
  step('the development proof row is a VALID Runtime-owned hybrid of the snapshot LAS-58 Talon row',def~=nil
   and def.validation.status=='VALID' and def.base.type==144 and counts.owned_blocks==1,tostring(code)..' '..tostring(reason))
  if def and vanilla then
   local outside=0
   for offset=0,271 do
    local allowed=(offset>=0x3C and offset<0x40)or(offset>=0x48 and offset<0x50)or(offset>=0x58 and offset<0x5C)
    if not allowed and def.bytes:byte(offset+1)~=vanilla:byte(offset+1)then outside=outside+1 end
   end
   step('only +0x3C, +0x48 and +0x58 differ from row 144, which is unchanged',outside==0
    and world_module.projectile_row(world,144)==vanilla and def.bytes:byte(0x3D)==64,'outside='..outside)
   local custom_shot=require('hd2runtime/api/actions').spawn_custom_projectile(def.id,{position={x=1,y=2,z=3},
    direction={x=1,y=0,z=0}})
   step('a custom projectile aboard the ship is refused',custom_shot.status=='refused'
    and(custom_shot.code=='NOT_IN_MISSION' or custom_shot.code=='CUSTOM_PROJECTILE_UNAVAILABLE'),tostring(custom_shot.code))
   -- The component proof variants: each VALID and different from row 144 only inside its components' members.
   local rows=require('hd2runtime/core/projectile_rows')
   local bad={}
   for _,spec in ipairs(custom.DEVELOPMENT_VARIANTS)do
    local vdef,vcode,vreason=custom.define(spec)
    local owned={}
    for id in pairs(spec.components)do
     for _,member in ipairs(rows.component(id).members)do
      for o=member.offset,member.offset+member.width-1 do owned[o]=true end
     end
    end
    local outside=0
    for offset=0,271 do
     if vdef and not owned[offset]and vdef.bytes:byte(offset+1)~=vanilla:byte(offset+1)then outside=outside+1 end
    end
    if not vdef or vdef.validation.status~='VALID'or outside>0 then
     bad[#bad+1]=spec.id..' '..tostring(vcode)..' '..tostring(vreason)..' outside='..outside
    end
   end
   step('every component proof variant is a VALID hybrid differing only in its components',#bad==0
    and#custom.DEVELOPMENT_VARIANTS==5 and world_module.projectile_row(world,144)==vanilla,table.concat(bad,'; '))
  end
  -- Weapon projectile replacement (docs/custom-projectile-rows.md#weapon-projectile-replacement), required after
  -- startup like ReprimandCustomProjectileProof does: the pool pins prove on this game.dll, the pool reads as inactive
  -- aboard the ship, and the proof's carrier passes every check up to the host one (there is no hosted session aboard
  -- the ship), so nothing is bound. Binding and replacing are covered by tests/test_custom_projectiles.py.
  local replacement_ok,replacement=pcall(require,'hd2runtime/runtime/projectile_replacement')
  step('the projectile replacement module resolves from the packaged archive after startup',replacement_ok
   and type(replacement)=='table' and type(replacement.bind)=='function',tostring(replacement))
  if replacement_ok and def then
   local proven,why=world_module.prove_projectile_pool(world)
   local counter,reason=world_module.projectile_counter(world)
   step('the projectile pool pins prove on the snapshot game.dll and the pool is inactive aboard the ship',proven==true
    and counter==nil and tostring(reason):find('^NOT_IN_MISSION')~=nil,tostring(why)..' '..tostring(reason))
   local actions=require('hd2runtime/api/actions')
   local carrier='output/v1/projectile/td-110-maelstrom-slot-2'
   local exploding=actions.replace_projectiles(def,{carrier='output/v1/projectile/r-36-eruptor'})
   step('a carrier with an explosion is refused',exploding.code=='CARRIER_HAS_EXPLOSION',tostring(exploding.code))
   local native='output/v1/projectile/smg-32-reprimand'
   local same=actions.replace_projectiles(def,{carrier=carrier,unreplaced=carrier})
   local bound=actions.replace_projectiles(def,{carrier=carrier,weapon='SMG-32 Reprimand',unreplaced=native,
    detail_logs=math.huge})
   for _=1,40 do if bound.status~='waiting_for_assets' then break end;frame()end
   step('the TD-110 Maelstrom slot 2 carrier (type 324), with the Reprimand bullet unreplaced, passes the carrier '
    ..'checks and loads the packages, then is refused HOST_ONLY aboard the ship',same.code=='INVALID_UNREPLACED'
    and bound.status=='refused' and bound.code=='HOST_ONLY' and bound.type==324
    and replacement.list()[1]==nil and actions.stop_replacing_projectiles(carrier)==false,
    tostring(bound.status)..' '..tostring(bound.code)..' '..tostring(bound.reason)..' '..tostring(same.code))
   -- The Patriot proof's binding: the minigun output as the source identity and the suppressed native projectile.
   local patriot='output/v1/projectile/exo-45-patriot-exosuit-right-gun'
   local bad_credit=actions.replace_projectiles(def,{carrier=carrier,credit='anyone'})
   local mounted=actions.replace_projectiles(def,{carrier=carrier,source=patriot,suppressed=patriot,
    credit='local_or_none',attribute=true,detail_logs=100})
   for _=1,40 do if mounted.status~='waiting_for_assets' then break end;frame()end
   step('the Patriot minigun binding (source identity, suppressed native bullet, local_or_none credit) resolves from '
    ..'the packaged archive, then is refused HOST_ONLY aboard the ship',bad_credit.code=='INVALID_CREDIT'
    and mounted.status=='refused' and mounted.code=='HOST_ONLY' and replacement.list()[1]==nil,
    tostring(mounted.status)..' '..tostring(mounted.code)..' '..tostring(mounted.reason)..' '..tostring(bad_credit.code))
  end
  -- Custom stratagem P0 (docs/custom-stratagems.md), required after startup like CustomStratagemP0Proof does: the
  -- calldown readers prove, the real 120mm row resolves from its catalogue id, and P0 is refused aboard the ship.
  local stratagem_ok,stratagem=pcall(require,'hd2runtime/runtime/custom_stratagem')
  step('the custom stratagem module resolves from the packaged archive after startup',stratagem_ok
   and type(stratagem)=='table' and type(stratagem.apply)=='function',tostring(stratagem))
  if stratagem_ok then
   local proven,why=stratagem.prove(world)
   local read=stratagem.read()
   for _=1,40 do if read.status~='pending' then break end;frame()end
   step('the calldown readers prove and the Orbital 120mm HE Barrage row reads its native code',proven==true
    and read.status=='read' and read.type==136 and read.id==1063322614
    and stratagem.names(read.sequence)=='Right Right Down Left Right Down' and not read.runtime_owned,
    tostring(why)..' '..tostring(read.status)..' '..tostring(read.code)..' '..tostring(read.reason))
   local p0=stratagem.apply()
   for _=1,40 do if p0.status~='pending' then break end;frame()end
   step('P0 is refused aboard the ship and writes nothing',p0.status=='refused' and p0.code=='NOT_IN_MISSION'
    and not stratagem.state().applied,tostring(p0.status)..' '..tostring(p0.code))
   -- The development HUD refresh (runtime/stratagem_hud.lua): its pins prove on the game.dll, the stratagem list is
   -- refused aboard the ship, and the refresh is refused without P0.
   local hud_ok,hud=pcall(require,'hd2runtime/runtime/stratagem_hud')
   local hud_proven,hud_why=hud_ok and hud.prove(world)
   local located,located_code=nil,nil
   if hud_ok then located,located_code=hud.locate(world,136)end
   local refresh=stratagem.refresh_hud()
   for _=1,40 do if refresh.status~='pending' then break end;frame()end
   step('the HUD refresh resolves from the packaged archive, its pins prove, and aboard the ship it is refused',hud_ok
    and hud_proven==true and located==nil and located_code=='NOT_IN_MISSION' and refresh.status=='refused'
    and refresh.code=='NOT_APPLIED',tostring(hud_why)..' '..tostring(located_code)..' '..tostring(refresh.code))
  end
 end
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

# Eagle attack fields live test (research/eagle-components-F5FEE03DCFDB.json): each option is exactly one 4-byte write
# to the EagleComponentData record of that Eagle's own jet; turning it off restores exactly that write.
STRATAGEM_FIELD_TOGGLES = {
    'example-eagle-fields-test': [('eagle_fields_test.airstrike_pattern', [1], 1, True),
        ('eagle_fields_test.napalm_interval', [2], 1, True), ('eagle_fields_test.strafe_duration', [3], 1, True),
        ('eagle_fields_test.rocket_radius', [4], 1, True)],
    # Orbital pattern and call-in time live test (research/bombardment-payload-F5FEE03DCFDB.json, research/beacon-
    # redirect-F5FEE03DCFDB.json): each option writes exactly its members in the orbital's own bombardment record (EMS
    # barrage 5, precise napalm 3, Gatling pauses 1) or the stratagem's own row (each call-in 1); off restores them.
    'example-orbital-strike-fields-test': [('orbital_strike_fields_test.ems_barrage', [1], 5, True),
        ('orbital_strike_fields_test.precise_napalm', [2], 3, True), ('orbital_strike_fields_test.fast_120mm', [3], 1, True),
        ('orbital_strike_fields_test.slow_380mm', [4], 1, True),
        ('orbital_strike_fields_test.gatling_pauses', [5], 1, False),
        ('orbital_strike_fields_test.eagle_delay', [6], 1, False)],
    # Sentry component fields (research/sentry-components-F5FEE03DCFDB.json): each option writes exactly its members in
    # the sentry's own component records (spread and recoil 2, coupling 1, wind-up 1, blind spots 2, yaw limits 2, range
    # 1); turning it off restores exactly those writes.
    'example-sentry-tuning-test': [('sentry_tuning_test.mg43_spread', [1], 2, True),
        ('sentry_tuning_test.ac8_recoil', [2], 2, True), ('sentry_tuning_test.ac8_coupling', [3], 1, True),
        ('sentry_tuning_test.m12_coupling', [4], 1, True), ('sentry_tuning_test.g16_windup', [5], 1, True),
        ('sentry_tuning_test.mg43_blind_spots', [6], 2, False), ('sentry_tuning_test.mg43_yaw_limits', [7], 2, False),
        ('sentry_tuning_test.mg43_range_control', [8], 1, False)],
}

# Charge and jump / hover live tests (scripts/charge_fields.py, scripts/jump_hover_fields.py): each option writes exactly
# its fields in the weapon's or pack's own record; turning it off restores exactly those writes. The Epoch overcharge
# explosion on the Railgun loads the Epoch package (one native package request).
CHARGE_HOVER_TOGGLES = {
    'example-railgun-charge-test': ([('railgun_charge_test.slow_charge', [1], 3, True),
        ('railgun_charge_test.no_explode', [2], 1, False), ('railgun_charge_test.hold_limit', [3], 1, False),
        ('railgun_charge_test.auto_fire', [4], 1, False), ('railgun_charge_test.crawl_shot', [5], 1, False),
        ('railgun_charge_test.weak_ap', [6], 1, False), ('railgun_charge_test.huge_damage', [7], 1, False),
        ('railgun_charge_test.epoch_blast', [8], 1, False), ('railgun_charge_test.arc_burst', [9], 2, False)], 1),
    'example-jump-hover-test': ([('jump_hover_test.flat_dash', [1], 1, True),
        ('jump_hover_test.long_launch', [2], 1, False), ('jump_hover_test.second_boost', [3], 2, False),
        ('jump_hover_test.air_steer', [4], 1, False), ('jump_hover_test.big_hop', [5], 1, False),
        ('jump_hover_test.hover_drift', [6], 2, True), ('jump_hover_test.hover_fuel', [7], 2, False),
        ('jump_hover_test.hover_climb', [8], 1, False)], 0),
    # EpochExplosionsTest (research/charge-explosions-F5FEE03DCFDB.json): each option writes exactly its fields in the
    # Epoch's / Railgun's charge-level rows; the harmless overcharge explosions are on by default.
    'example-epoch-explosions-test': ([('epoch_explosions_test.harmless_overcharge', [1], 3, True),
        ('epoch_explosions_test.wide_overcharge', [2], 3, False),
        ('epoch_explosions_test.big_partial_blast', [3], 3, False),
        ('epoch_explosions_test.big_full_charge_blast', [4], 3, False),
        ('epoch_explosions_test.slow_full_charge', [5], 1, False),
        ('epoch_explosions_test.railgun_gentle_overcharge', [6], 3, True)], 0),
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
    # ProjectileDonorTest: one reference per host; each donor's own package (docs/attack-outputs.md "More donors").
    'example-projectile-donor-test': ([('projectile_donor_test.reprimand_500kg', [1], 1, True),
        ('projectile_donor_test.stalwart_precision', [2], 1, True),
        ('projectile_donor_test.arbitrator_hmg', [3], 1, True),
        ('projectile_donor_test.apw_flak', [4], 1, False),
        ('projectile_donor_test.hmg_gatling', [5], 1, False),
        ('projectile_donor_test.amendment_railcannon', [6], 1, False)], (), 6),
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

# ProjectileHomingTest 0.1.0 (docs/projectile-homing.md): the example configures homing from the packaged archive
# for its four weapons that are on by default. No shot flies on a snapshot, so nothing is written (readOnly); the
# steering write itself is validated on the mission snapshot by scripts/validate_projectile_homing_snapshot.py.
PROJECTILE_HOMING_LIVE = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function count(text)local n=0;for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end;return n end
 local hd2=require('mods/skyeshade/hd2runtime')
 for _=1,120 do frame()end
 step('the example loads once from the archive',count('PROJECTILE HOMING 0.1.0 BUILD')==1,'')
 local weapons={}
 for _,item in ipairs(hd2.projectiles.homing_status())do weapons[item.weapon]=(weapons[item.weapon]or 0)+1 end
 step('its four default weapons home (one configuration per projectile type)',weapons['EAT-17 Expendable Anti-Tank']==1
  and weapons['R-36 Eruptor']==1 and weapons['GL-21 Grenade Launcher']~=nil and weapons['P-11 Stim Pistol']==1
  and weapons['AR-23 Liberator']==nil and weapons['A/MG-43 Machine Gun Sentry']==nil,'')
 step('the homing catalogue resolves from the archive',#hd2.projectiles.homing_list()>=170,
  tostring(#hd2.projectiles.homing_list()))
 local refused=0
 for _,line in ipairs(lines)do
  if line:find('homing refused',1,true)or(line:find('projectile homing (',1,true)and line:find(') refused: ',1,true))then
   refused=refused+1
  end
 end
 step('nothing refused, nothing written',refused==0 and count('callback failed')==0 and counts.writes==0,
  tostring(counts.writes))
 return results
end
"""

# EnemySpawnMixTest 0.1.0 (docs/enemy-spawns.md): its four default mixes, applied from the packaged archive, scale
# exactly those enemy types' roster weights (Bile Titan x 0, Hive Guard x 5, Berserker x 5, Watcher x 0); every other
# roster row stays vanilla.
ENEMY_SPAWN_MIX_LIVE = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function count(text)local n=0;for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end;return n end
 local hd2=require('mods/skyeshade/hd2runtime')
 for _=1,120 do frame()end
 step('the example loads once from the archive',count('ENEMY SPAWN MIX 0.1.0 BUILD')==1,'')
 local status={}
 for _,item in ipairs(hd2.enemies.spawn_status())do status[item.enemy]=item.status end
 step('its four default mixes are applied',status['Bile Titan']=='applied'and status['Hive Guard']=='applied'
  and status['berserker']=='applied'and status['Watcher']=='applied',
  table.concat({tostring(status['Bile Titan']),tostring(status['Hive Guard']),tostring(status['berserker']),
  tostring(status['Watcher'])},' '))
 local D=require('hd2runtime/domains/enemy_spawn_weights')
 local b=require('hd2runtime/core/bytes')
 local world=assert(require('hd2runtime/runtime/event_world').open())
 local multiplier={['Bile Titan']=0,['Hive Guard']=5,['berserker']=5,['Watcher']=0}
 local exact,detail,scaled=true,'',0
 for _,faction in ipairs(D.factions)do
  for _,entry in ipairs(faction.entries)do
   local now=world.runtime.read(world.game+faction.rows+entry.index*D.row.stride+D.row.weights,40)
   local vanilla=b.unhex(entry.weights)
   local k=multiplier[entry.name]or 1
   if multiplier[entry.name]then scaled=scaled+1 end
   for d=1,10 do
    if math.abs(b.value(now,(d-1)*4,'f32')-b.value(vanilla,(d-1)*4,'f32')*k)>1e-6 then
     exact=false;detail=faction.name..' row '..entry.index..' difficulty '..d
    end
   end
  end
 end
 step('exactly those types\' weights are scaled; every other roster row is vanilla',exact and scaled==8,
  detail..' ('..scaled..' rows scaled)')
 step('nothing refused, no failed callback',count(') refused: ')==0 and count('REFUSED')==0
  and count('callback failed')==0 and counts.writes>0,tostring(counts.writes))
 return results
end
"""

EXTRAS = {'options-live': {'menu': MENU_STUB, 'after': OPTIONS_LIVE},
    'example-projectile-homing-test': {'menu': MENU_STUB, 'after': PROJECTILE_HOMING_LIVE, 'readOnly': True},
    'example-enemy-spawn-mix-test': {'menu': MENU_STUB, 'after': ENEMY_SPAWN_MIX_LIVE},
    # Event-only mods observe the game and write nothing (readOnly: exactly zero overlay writes).
    'example-event-isolation-test': {'after': EVENT_ISOLATION_LIVE, 'readOnly': True},
    'example-kill-heal-test': {'after': EVENT_WORLD_LIVE, 'readOnly': True},
    'example-death-hellbomb-test': {'after': EVENT_WORLD_LIVE, 'readOnly': True},
    'example-heavy-devastator-delayed-explosion-test': {'after': EVENT_WORLD_LIVE, 'readOnly': True},
    'example-player-kill-credited-example': {'after': EVENT_WORLD_LIVE, 'readOnly': True},
    'example-projectile-action-test': {'after': EVENT_WORLD_LIVE, 'readOnly': True},
    'example-status-action-test': {'after': EVENT_WORLD_LIVE, 'readOnly': True},
    'example-limb-injury-test': {'after': EVENT_WORLD_LIVE, 'readOnly': True},
    'example-avatar-actions-test': {'after': EVENT_WORLD_LIVE, 'readOnly': True},
    'example-equipped-weapon-event-test': {'after': EVENT_WORLD_LIVE, 'readOnly': True},
    'example-vampiric-throwing-knives-test': {'after': EVENT_WORLD_LIVE, 'readOnly': True},
    'example-kill-stack-damage-test': {'after': KILL_STACK_LIVE},
    'example-liberator-attack-output-test': {'menu': MENU_STUB, 'after': ATTACK_OUTPUT_LIVE, 'packageRequests': 3},
    'example-runtime-effect-diagnostics': {'menu': MENU_STUB, 'after': DIAGNOSTICS_LIVE},
    'example-resupply-test': {'menu': MENU_STUB, 'after': RESUPPLY_LIVE, 'packageRequests': 1},
    # Their live steps register negative controls that must be refused at registration (and write nothing).
    'stratagem-calldown-code': {'after': STRATAGEM_CALLDOWN_LIVE, 'watches': 2, 'rejected': {
        'calldown-too-long': 'value must be a list of 1 to 9 directions',
        'calldown-equal': 'equals the native code of Orbital Precision Strike',
        'calldown-bad-direction': 'must be "up", "right", "down" or "left", not north'}},
    'stratagem-presentation': {'after': STRATAGEM_PRESENTATION_LIVE, 'watches': 2, 'rejected': {
        'presentation-raw': 'raw localization ids and image hashes are not accepted',
        'presentation-unknown': 'No Such Stratagem is not a catalogued stratagem'}},
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
    # The Liberator's dormant base member is the live FAIL control: refused at registration by design.
    'projectile-donors': {'rejected': {'arbitrator-hmg-no-ack': 'this donor is not live-tested yet and requires '
        'allow_unverified_reference=true'}},
    'projectile-active-sources': {'packageRequests': 1,
        'rejected': {'liberator-talon-dormant': 'DORMANT_PROJECTILE_REFERENCE'}},
    'registration-isolation': {'rejected': {'isolation-invalid': 'field is not exposed for SG-20 Halt'}},
    # SDK 0.27.0 project: the Purifier drag applies as a legacy operation (logged); the control that already needed
    # the acknowledgement in 0.27.0 is still refused. SDK 0.28.0 project: refused without the acknowledgement, applied
    # with it. The unprotected control applies in all three.
    'legacy-sdk-027-purifier': {'legacy': {'legacy-purifier-drag': ['projectile.drag']},
        'rejected': {'control-coyote-burst': 'field requires allow_unverified_effect=true: fire_mode.burst_rounds'}},
    'sdk-028-purifier-without-ack': {'rejected': {
        'current-purifier-drag': 'required since SDK 0.28.0; mods/hd2runtime_validation/sdk_0_28_0 declares SDK 0.28.0',
        'control-coyote-burst': 'field requires allow_unverified_effect=true: fire_mode.burst_rounds'}},
    'sdk-028-purifier-with-ack': {'rejected': {
        'control-coyote-burst': 'field requires allow_unverified_effect=true: fire_mode.burst_rounds'}},
    # The exact 133-operation user project (ModBuilder 1.3.1, SDK 0.27.0): every operation registers and applies. The
    # PLAS-101 Purifier row its charge levels only partly fire needs allow_unverified_effect since SDK 0.28.0; the
    # project declares 0.27.0, so it applies as a legacy operation (0.28.0 refused it).
    'user-report-full-project': {'watches': 133, 'frames': 200000, 'resetSeconds': 20000,
        # Its PLAS-45 Epoch plan writes the partial-charge shot's rows, which need allow_unverified_effect since 0.30.0
        # (research/charge-explosions-F5FEE03DCFDB.json): also a legacy operation of the SDK 0.27.0 export.
        'legacy': {'gui-object-64f6c65514d7e06d97274943': ['projectile.drag'],
            'support-plan-12bd9a610e6a4fe58e6abaa5': ['explosion.primary_impact.damage.durable_damage',
                'explosion.primary_impact.damage.standard_damage', 'explosion.primary_impact.inner_radius',
                'explosion.primary_impact.outer_radius', 'projectile.primary.velocity']}},
    # A Maxigun backpack of 1500 rounds exceeds the game's 1023 deposit limit: refused (logged), the Maxigun
    # weapon operations still apply.
    # Every operation of each ModBuilder 1.3.1 export registers and applies: the Halt edits never drop the others.
    'user-report-halt-issue-control': {'watches': 3},
    'user-report-halt-issue-all-fields': {'watches': 8, 'frames': 60000},
    'user-report-halt-issue-damage': {'watches': 5, 'frames': 60000},
    'user-report-halt-issue-sway': {'watches': 4},
    # Both plans of the user's HMG package apply; neither exhausts the guarded read budget.
    'user-report-hmg-read-budget': {'watches': 2, 'frames': 60000},
    'user-report-maxigun-plus-backpack': {'rejected': {'entity-2f5a386db841be55d3be8e66':
        'outside the reviewed range for deposit.capacity (1 to 1023)'}},
    'example-explosive-projectile-swap': {'packageRequests': 1},
    'example-asset-test-frv-bastion-cannon': {'packageRequests': 1},
    'example-asset-test-mg43-pod-grenade-box': {'packageRequests': 1},
    # GibThresholdTest: one choice drives the whole-body gib threshold of the seven Warrior classes (one write per
    # class per switch): 750 restores the vanilla value through the same guards, -1 disables bursting, and it ends
    # back on the default (400) so the simulated reset re-applies every class.
    'example-gib-threshold-test': {'menu': MENU_STUB, 'watches': 23, 'after': toggles_live(
        [('gib_threshold_test.extreme_active', list(range(1, 24)), 23, True)],
        [('gib_threshold_test.terminid_burst_damage', index, list(range(1, 24)), 23, 0) for index in (2, 1)])},
    'example-vehicle-tuning-test': {'menu': MENU_STUB, 'watches': 5, 'after': toggles_live((), [
        ('vehicle_tuning_test.patriot_turn_acceleration', 2, [4], 1, 0),
        ('vehicle_tuning_test.m103_traverse', 1, [1], 1, 0), ('vehicle_tuning_test.bastion_left_limit', 1, [3], 1, 0),
        ('vehicle_tuning_test.bastion_elevation', 1, [3], 1, 0), ('vehicle_tuning_test.frv_steering', 1, [5], 1, 0),
        ('vehicle_tuning_test.frv_steering', 2, [5], 1, 0), ('vehicle_tuning_test.m103_traverse', 2, [1], 1, 0),
        ('vehicle_tuning_test.bastion_left_limit', 2, [3], 1, 0), ('vehicle_tuning_test.bastion_elevation', 2, [3], 1, 0)])},
    **{name: {'menu': MENU_STUB, 'after': toggles_live(items)} for name, items in EQUIPMENT_TOGGLES.items()},
    **{name: {'menu': MENU_STUB, 'after': toggles_live(items)} for name, items in STRATAGEM_FIELD_TOGGLES.items()},
    **{name: {'menu': MENU_STUB, 'after': toggles_live(items), 'packageRequests': packages}
        for name, (items, packages) in CHARGE_HOVER_TOGGLES.items()},
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


def proof(name):
    """A development proof's addon (proof/<name>) inside the SDK's addon wrapper, exactly as its built ZIP ships it."""
    project = ROOT / 'proof' / name
    spec = json.loads((project / 'hd2runtime.json').read_text(encoding='utf-8'))
    import importlib.util
    loader = importlib.util.spec_from_file_location('hd2_sdk_cli', ROOT / 'sdk/hd2.py')
    sdk = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(sdk)
    return sdk.wrap_addon(spec['resource'], spec['requires']['hd2runtime']['min_version'],
        (project / 'src/addon.lua').read_text(encoding='utf-8-sig'))


PROOF_IMAGE = ('mods/skyeshade/hd2runtime_custom_stratagem_p0_proof', 'orbital_gas_barrage_icon')


def _seeded_u32(mem, prior, address):
    """A u32 as the snapshot reads with the earlier seeds of the same scenario laid over it."""
    for at, data in (prior or {}).items():
        if at <= address and address + 4 <= at + len(data):
            return struct.unpack_from('<I', data, address - at)[0]
    return mem.u32(address)


def _seeded(prior, address, size):
    """True when [address, address + size) meets an earlier seed."""
    return any(at < address + size and address < at + len(data) for at, data in (prior or {}).items())


def _name_entry(mem, entries, buckets, capacity, name, slot, prior=None):
    """{address: bytes} linking `name` (with resource slot `slot`) into an in-array chained name map, as the game links
    a resource of a loaded archive: its bucket's head when free, else a free entry at the end of the chain. prior: the
    scenario's earlier seeds, read through (several images in one scenario)."""
    import research_image_resources as research
    if research.resolve(mem, entries, buckets, 24, 0x10, 0, name) is not None:
        raise ValueError('the name is already in the snapshot')
    u32 = lambda address: _seeded_u32(mem, prior, address)  # noqa: E731
    head = (name >> 32) % buckets
    entry = struct.pack('<QIIii', name, slot, 0, 0x7FFFFFFF, 0)
    if u32(entries + head * 24 + 0x10) == 0xFFFFFFFE:
        return {entries + head * 24: entry}
    last = head
    while u32(entries + last * 24 + 0x10) != 0x7FFFFFFF:
        last = u32(entries + last * 24 + 0x10)
    free = next(i for i in range(buckets, capacity) if u32(entries + i * 24 + 0x10) == 0xFFFFFFFE)
    return {entries + last * 24 + 0x10: struct.pack('<I', free), entries + free * 24: entry}


def _snapshot_mem(snapshot):
    import research_event_state as base
    if Path(snapshot).parent != build_profile.snapshot_directory():
        raise ValueError('image seeding needs a retained snapshot')
    return base.Mem(Path(snapshot).name)


def seed_image(snapshot, resource, image_id, prior=None):
    """Validation only: {address: bytes} that enter a mod's texture into the snapshot's texture name map, as the game
    enters every texture of an archive it loads (the snapshots predate the proof); its slot is that of the loaded
    fallback texture, so the lookup reads exactly the game's layout (research/image-resources-F5FEE03DCFDB.json). This
    layer sits under the write overlay and is never counted as a write."""
    import research_image_resources as research
    sys.path.insert(0, str(ROOT / 'scripts'))
    import hd2_image
    mem = _snapshot_mem(snapshot)
    try:
        record = research.Manager(mem).record(hd2_image.TEXTURE_TYPE)
        entries, buckets, capacity = mem.ptr(record + 0x28), mem.u32(record + 0x3C), mem.u32(record + 0x20)
        fallback = research.resolve(mem, entries, buckets, 24, 0x10, 0, research.MISSING_TEXTURE)
        name = resource_hash(hd2_image.image_name(resource, image_id))
        return _name_entry(mem, entries, buckets, capacity, name, mem.u32(entries + fallback * 24 + 8), prior)
    finally:
        mem.close()


def seed_family(snapshot, resource, image_id, prior=None):
    """Validation only: the complete custom icon family (research/stratagem-icon-family-F5FEE03DCFDB.json) entered into
    the snapshot, as the game holds it once the mod's archive is loaded (the 0.10.0 live probe read exactly this in
    game): the texture (seed_image) and the GUI icon material: its name-map entry, its resource record pointing at the
    160 material bytes (hd2_image.icon_material) with the loader's three fix-ups, and its material object {magic, body,
    shader, name}, placed in zeroed memory of the material records' own region. Never counted as a write."""
    import research_image_resources as research
    sys.path.insert(0, str(ROOT / 'scripts'))
    import hd2_image
    prior = dict(prior or {})
    seed = seed_image(snapshot, resource, image_id, prior)
    prior.update(seed)
    name = resource_hash(hd2_image.image_name(resource, image_id))
    mem = _snapshot_mem(snapshot)
    try:
        record = research.Manager(mem).record(hd2_image.MATERIAL_TYPE)
        entries, buckets, capacity = mem.ptr(record + 0x28), mem.u32(record + 0x3C), mem.u32(record + 0x20)
        used = [_seeded_u32(mem, prior, entries + 24 * i + 8) for i in range(capacity)
            if _seeded_u32(mem, prior, entries + 24 * i + 0x10) != 0xFFFFFFFE]
        slot = max(v for v in used if v != 0xFAFEF0F1) + 1
        records = mem.ptr(record + 0x10)
        if mem.read(records + slot * 0xA0, 8) is None:
            raise ValueError('no free material resource record is mapped')
        region = mem.s.region(records)
        zero, start = bytes(0x200), None
        for at in range(region['base'], region['base'] + region['size'], 0x10000):
            chunk = mem.read(at, min(0x10000, region['base'] + region['size'] - at)) or b''
            index = chunk.find(zero)
            while index >= 0 and ((at + index) % 16 or _seeded(prior, at + index, len(zero))):
                index = chunk.find(zero, index + 1)
            if index >= 0:
                start = at + index
                break
        if start is None:
            raise ValueError('no zeroed memory for the seeded material')
        material, obj = start, start + 0x100
        body = bytearray(hd2_image.icon_material(name))
        struct.pack_into('<Q', body, 0x20, obj)
        struct.pack_into('<QQ', body, 0x30, material + 0x88, material + 0x8C)
        o = bytearray(0x48)
        struct.pack_into('<II', o, 0, 0xD92A8333, 0xFFFFFF)
        struct.pack_into('<Q', o, 0x10, material + 0x18)
        struct.pack_into('<I', o, 0x30, hd2_image.ICON_SHADER)
        struct.pack_into('<Q', o, 0x38, name)
        seed.update(_name_entry(mem, entries, buckets, capacity, name, slot, prior))
        seed.update({records + slot * 0xA0: struct.pack('<Q', material), material: bytes(body), obj: bytes(o)})
        return seed
    finally:
        mem.close()


def seed_registry_full(snapshot):
    """Validation only: the snapshot's game text registry with no spare capacity (capacity = count), so the Runtime text
    must be refused (research/stratagem-text-F5FEE03DCFDB.json). Never counted as a write."""
    import research_event_state as base
    mem = _snapshot_mem(snapshot)
    try:
        exe = mem.s.modules[[k for k in mem.s.modules if k.endswith('.exe')][0]]['base']
        registry = mem.ptr(exe + 0x1A101E0)
        return {registry + 4: struct.pack('<I', mem.u32(registry))}
    finally:
        mem.close()


def seed_payload_mission(snapshot):
    """Validation only, mission snapshots only: the local record's first unlimited loadout entry made an Orbital
    Precision Strike token (its type only), the state a virtual Gas Barrage slot is in at mission start. Its cooldown end
    stays the snapshot's own: an absolute game time, NOT 0 on a fresh entry (0.1.0's live refusal). Never counted as a
    write; aboard the ship nothing is seeded."""
    mem = _snapshot_mem(snapshot)
    try:
        g = mem.game
        state = mem.u32(mem.ptr(g + 0x3326340) + 0xAC21C) if mem.ptr(g + 0x3326340) else None
        records = mem.ptr(g + 0x347CE50)
        if not records or mem.u32(records + 0x2D200) != 1:
            return {}
        token = None
        for t in range(1, 150):
            row = mem.ptr(g + 0x37CB600 + 8 * t)
            if row and mem.u32(row + 4) == 3523620028:
                token = t
        base = records + 0x38
        for k in range(min(mem.u32(base + 0x788) or 0, 16)):
            at = base + 0x188 + k * 0x30
            if mem.read(at + 9, 1)[0] == 0 and mem.u32(at + 4) == 0xFFFFFFFF and token is not None and state == 4:
                return {at: struct.pack('<I', token)}
        return {}
    finally:
        mem.close()


def seed_client(snapshot):
    """Validation only, mission snapshots only: the game mode descriptor's authority bit (+0x14 bit 0, the Runtime's
    "host") cleared, so the packaged runtime sees this machine as a CLIENT on real snapshot memory (the client-write
    proof's snapshot validation: the host condition overlaid as absent). Never counted as a write."""
    mem = _snapshot_mem(snapshot)
    try:
        mode = mem.ptr(mem.game + 0x33266A0)
        descriptor = mode and mem.ptr(mode + 0x38)
        flags = descriptor and mem.u32(descriptor + 0x14)
        if flags is None or mem.u32(mode + 0x8) != 1:
            return {}
        return {descriptor + 0x14: struct.pack('<I', flags & ~1)}
    finally:
        mem.close()


# CustomStratagemP0Proof 0.12.0, the custom text write proof (docs/custom-text.md), on the shipped artifact, the
# snapshot's real StratagemSettings and the snapshot's real game text registry (17 tables of 18):
# * proof-text-write: the complete custom icon family entered as the game holds it once the mod's archive is loaded
#   (seed_family). The public ensure writes the 120mm's icon and calldown code; then, aboard the ship, the development
#   path registers the Runtime text table (the slot after the game's 17 tables, then the count: 2 guarded writes) and
#   writes the 120mm's name, cased name and description (3), verified (ids, each text resolving exactly, identity, icon,
#   non-target bytes, protection). The text toggle restores the three members and takes the table out of the registry;
#   the look toggle restores the icon and the code: the row and the registry are as they were.
# * proof-text-write-refused: the registry with no spare capacity (seed_registry_full): the text probe fails and the
#   text is refused with nothing written; only the public ensure's icon and code writes happen.
PROOF_TEXT = r"""
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function count(text)local n=0;for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end;return n end
 local texts=require('hd2runtime/runtime/text_resources')
 local D=require('hd2runtime/domains/text_resources')
 local world=assert(require('hd2runtime/runtime/event_world').open())
 local kind=require('hd2runtime/runtime/stratagem_loadout').type_of(world,1063322614)
 local row=kind and world.view.pointer(world.game+require('hd2runtime/schemas/current').stratagem.table_rva+kind*8)
 local NATIVE=row and world.runtime.read(row,400)
 local exe=world.runtime.address(world.runtime.module(nil))
 local function u32(s,o)return s:byte(o+1)+s:byte(o+2)*256+s:byte(o+3)*65536+s:byte(o+4)*16777216 end
 local function u64(s,o)return u32(s,o)+u32(s,o+4)*4294967296 end
 local function registry()
  local list=u64(world.runtime.read(exe+D.registry.global,8),0)
  local head=world.runtime.read(list,16)
  local n,capacity,array=u32(head,0),u32(head,4),u64(head,8)
  return {count=n,capacity=capacity,array=array,slots=world.runtime.read(array,capacity*8)}
 end
 local BEFORE=registry()
 local RESOURCE='mods/skyeshade/hd2runtime_custom_stratagem_p0_proof'
 local function only(allowed)
  local now=world.runtime.read(row,400)
  for i=1,400 do
   local at,inside=i-1,false
   for _,range in ipairs(allowed)do if at>=range[1]and at<range[2]then inside=true end end
   if now:byte(i)~=NATIVE:byte(i)and not inside then return false end
  end
  return true
 end
"""
PROOF_TEXT_WRITE = r"""
return function(frame,watches,counts,lines)
""" + PROOF_TEXT + r"""
 for _=1,200 do frame()end
 step('the proof loads; its read-only text probe passes on the real registry',count('CustomStratagemP0Proof 0.12.0 '
  ..'CUSTOM-TEXT-WRITE BUILD')==1 and count('  game text registry: 17 of 18 tables, 1 spare; current language us')==1
  and count('  TEXT PROBE RESULT: PASS: room for the Runtime text table, no id clash, a known language')==1,
  table.concat(lines,' | '):match('text probe[^|]*'))
 step('the public ensure writes the icon and the calldown code',count('custom icon and code (public ensure): waiting '
  ..'APPLIED')==1 and counts.owned_blocks==1,'owned='..counts.owned_blocks)
 step('the development path writes the text, verified on the real row and registry',count('stratagem presentation '
  ..'custom text APPLIED: Orbital 120mm HE Barrage (type 136, stable id 1063322614): name 0x4FAAD695 -> 0xC9131101 '
  ..'"ORBITAL GAS BARRAGE"; nameCased 0x628B5A83 -> 0x06DFCD45 "Orbital Gas Barrage"; description 0x35FEBFE6 -> '
  ..'0xA50908A0 "Calls down a barrage of gas shells."; 3 write; Runtime text table appended (table 18 of 18, language '
  ..'us); read back true; each resolves to exactly its text: true; identity unchanged: true; icon unchanged: true; '
  ..'other text members native: true; non-target bytes unchanged true; protection restored true')==1
  and count('custom text APPLIED aboard the ship: the 120mm row holds the Runtime text and the custom icon')==1
  and counts.writes==8 and counts.permanent_blocks==1 and only({{0x28,0x34},{0x40,0x4C},{0xB0,0xB8}}),
  'writes='..counts.writes..' '..tostring(table.concat(lines,' | '):match('custom text [A-Z]+[^|]*')))
 local after=registry()
 local table_ok=after.count==18 and after.slots:sub(1,17*8)==BEFORE.slots:sub(1,17*8)
 local placed=u64(after.slots,17*8)
 local magic=world.runtime.read(placed,4)
 local resolves=true
 for id,text in pairs({orbital_gas_barrage_name='ORBITAL GAS BARRAGE',orbital_gas_barrage_name_cased='Orbital Gas Barrage',
   orbital_gas_barrage_description='Calls down a barrage of gas shells.'})do
  if not texts.resolves(world.runtime,texts.handle(id,text,RESOURCE))then resolves=false end
 end
 step('the game\'s 17 tables are untouched and the Runtime table is the 18th; every text resolves',table_ok
  and magic==string.char(0xAE,0xF3,0x85,0x3E)and resolves,('count %d'):format(after.count))
 local menu=rawget(_G,'ModOptionsMenu')
 local writes=counts.writes
 menu.apply('custom_stratagem_proof.text',false)
 for _=1,80 do frame()end
 local restored=registry()
 step('the text toggle off restores the native text and takes the table out of the registry',count('RESTORED: Orbital '
  ..'120mm HE Barrage presents as itself again: 3 writes; restored values read back exactly: true; name, cased name and '
  ..'description native: true; identity unchanged (type 136, stable id 1063322614): true; non-target bytes unchanged '
  ..'true; protection restored true; Runtime text table unregistered')==1 and counts.writes==writes+4
  and restored.count==17 and only({{0x40,0x4C},{0xB0,0xB8}}),'writes='..counts.writes..' count='..restored.count)
 menu.apply('custom_stratagem_proof.look',false)
 for _=1,120 do frame()end
 step('the look toggle off restores the icon and the code: the row is native again',
  world.runtime.read(row,400)==NATIVE and count('ensure gas-barrage-look restored the reviewed baseline and is '
  ..'disabled')==1,'writes='..counts.writes)
 step('no failed callback, no lost text',count('callback failed')==0 and count('custom text LOST')==0)
 return results
end
"""
PROOF_TEXT_WRITE_REFUSED = r"""
return function(frame,watches,counts,lines)
""" + PROOF_TEXT + r"""
 for _=1,200 do frame()end
 step('no spare registry capacity: the probe fails and the text is refused with nothing written',
  count('  game text registry: 17 of 17 tables, 0 spare; current language us')==1
  and count('  TEXT PROBE RESULT: FAIL: the custom text would be refused')==1
  and count("custom text REFUSED (nothing written): REGISTRY_FULL: the game's text registry has no spare capacity "
  ..'(17 of 17)')==1 and counts.permanent_blocks==0 and registry().count==17,
  table.concat(lines,' | '):match('custom text [A-Z]+[^|]*'))
 step('only the public icon and code are written',count('custom icon and code (public ensure): waiting APPLIED')==1
  and counts.writes==3 and only({{0x40,0x4C},{0xB0,0xB8}}),'writes='..counts.writes)
 step('no failed callback',count('callback failed')==0)
 return results
end
"""
# VirtualSlotProof 0.1.0 (mission-time slot conversion, docs/custom-stratagems.md) on the shipped artifact aboard the
# ship: it loads, reports the saved loadout, and converts nothing (the conversion runs in a solo mission only; the
# mission snapshots validate it in scripts/validate_stratagem_calldown_snapshot.py). readOnly: zero overlay writes.
PROOF_VIRTUAL_SLOT = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function count(text)local n=0;for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end;return n end
 for _=1,200 do frame()end
 step('the proof loads and reports the saved loadout aboard the ship',count('VirtualSlotProof 0.1.0 '
  ..'VIRTUAL-SLOT-CONVERSION BUILD')==1 and count('saved ship loadout: ')==1
  and count('Orbital Precision Strike saved: select two (Stratagem MultiSelect) for this proof')==1,
  table.concat(lines,' | '):match('saved ship loadout[^|]*'))
 step('nothing is converted or written aboard the ship',count('stratagem slot CONVERTED')==0 and counts.writes==0
  and count('callback failed')==0,'writes='..counts.writes)
 return results
end
"""
EXTRAS['proof-virtual-slot'] = {'menu': MENU_STUB, 'after': PROOF_VIRTUAL_SLOT, 'readOnly': True}
# The build label (runtime/version_label.lua) from the archive on the snapshot's real game state and engine font, with
# a stand-in for the engine GUI API over the snapshot's own world list (the Ui World by its position): aboard the ship
# it is one Ui World GUI with "HD2Runtime <version>" over "Game <build>" in the bottom-left corner at the lowest layer,
# drawn once; a mission loading hides it (its GUI destroyed); back aboard the ship it is drawn again; in a mission (the
# mission snapshot) nothing is drawn; stop releases everything. readOnly: zero overlay writes.
RUNTIME_VERSION_LABEL = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local b=require('hd2runtime/core/bytes')
 local function u64(s)return s and b.u32(s,0)+b.u32(s,4)*4294967296 end
 local wm=require('hd2runtime/runtime/event_world')
 local world=assert(wm.open())
 local O=require('hd2runtime/domains/stratagem_selector').slotOverlay
 local app=world.view.pointer(world.exe+O.application)
 local n=app and world.view.u32(app+O.worldCount)
 local array=app and world.view.pointer(app+O.worldArray)
 local context=world.view.pointer(world.game+O.gameContext)
 local ui_pointer=context and u64(world.view.read(context+O.uiWorld,8))
 local worlds,ui_index={},nil
 for k=0,(n or 0)-1 do
  worlds[#worlds+1]=newproxy()
  if u64(world.view.read(array+8*k,8))==ui_pointer then ui_index=k+1 end
 end
 local UW=ui_index and worlds[ui_index]
 local calls={}
 local function rec(name)return function(...)calls[#calls+1]={name=name,args={...}};return #calls end end
 local function nothing(name)return function(...)calls[#calls+1]={name=name,args={...}}end end
 local function constructor(kind)return setmetatable({},{__call=function(_,...)return {kind=kind,...}end})end
 rawset(_G,'stingray',{Application={main_world=function()return worlds[1]end,worlds=function()return worlds end},
  World={create_screen_gui=rec('create_screen_gui'),destroy_gui=nothing('destroy_gui')},
  Gui={resolution=function()return 1920,1080 end,rect=rec('rect'),update_rect=nothing('update_rect'),text=rec('text'),
   bitmap=rec('bitmap')},
  Vector2=constructor('Vector2'),Vector3=constructor('Vector3'),Color=function(a,r,g,b)return {kind='Color',a,r,g,b}end})
 local function of(name)local out={};for _,c in ipairs(calls)do if c.name==name then out[#out+1]=c end end;return out end
 local L=require('hd2runtime/runtime/version_label')
 local real_state=L.hooks.state
 L.start()
 for _=1,10 do frame()end
 local state=wm.game_state(world)
 local metadata=require('hd2runtime/domains/metadata')
 local profile=require('hd2runtime/schemas/current')
 local first,second='HD2Runtime '..metadata.version,'Game '..profile.exe_sha:sub(1,12)
 local guis,texts=of('create_screen_gui'),of('text')
 if state and state.name=='Ship'then
  step('aboard the ship: one Ui World GUI, "'..first..'" over "'..second..'" in the bottom-left corner, small, dim, at '
   ..'the lowest layer, drawn once',UW~=nil and#guis==1 and guis[1].args[1]==UW and#texts==2
   and texts[1].args[2]==second and texts[2].args[2]==first and texts[1].args[6][1]==14 and texts[1].args[6][2]==14
   and texts[1].args[6][3]==2 and texts[2].args[6][2]>14 and texts[1].args[4]==18 and texts[1].args[7][1]<=128
   and L.status()==first..' / '..second,tostring(L.status())..' guis='..#guis..' texts='..#texts)
  for _=1,30 do frame()end
  step('nothing is redrawn while it shows',#of('create_screen_gui')==1 and#of('text')==2,tostring(#of('text')))
  L.hooks.state=function()return {name='PrepareMission',mission=false}end
  for _=1,5 do frame()end
  step('a mission loading hides it (its GUI destroyed)',#of('destroy_gui')==1 and L.status()==nil,'')
  L.hooks.state=real_state
  for _=1,5 do frame()end
  step('back aboard the ship it is drawn again',#of('create_screen_gui')==2 and#of('text')==4,tostring(#of('text')))
 else
  step('outside the ship (game state '..tostring(state and state.name)..'): nothing drawn',#guis==0 and#texts==0
   and L.status()==nil,tostring(#guis))
 end
 L.stop()
 local failed=0
 for _,line in ipairs(lines)do if line:find('callback failed',1,true)or line:find('version label is off',1,true)then
  failed=failed+1 end end
 step('stop removes it; nothing written; no failed callback, the label never turned off',L.status()==nil
  and counts.writes==0 and failed==0,'writes='..counts.writes..' failed='..failed)
 rawset(_G,'stingray',nil)
 return results
end
"""
EXTRAS['runtime-version-label'] = {'after': RUNTIME_VERSION_LABEL, 'readOnly': True}
# VirtualSelectorProof 0.6.0 (coordinate diagnostics for the Runtime card in the native stratagem list; selection off,
# docs/custom-stratagems.md) on the shipped artifact aboard the ship with no loadout screen open (no snapshot holds one):
# every module it needs resolves from the archive, it reports the saved loadout (no virtual slot recognised) and draws
# and selects nothing. Then, from the archive, against a stand-in for the engine GUI API with the engine's own types and
# returns (Vector2/Vector3 callable tables, Color a function; rect/bitmap/text return an id, update_rect and destroy_gui
# return nothing), with the real snapshot's engine font and the seeded custom icon loaded: its drawing proof issues a
# rectangle, the image and the text; the card renderer draws the native-sized tile (edge, inner frame, centred icon) in a
# grid cell with its text area, name and description; the tile alone at layers 900-902 (the 0.6.0 card); the
# calibration markers (screen corners and centre, the frame, a native card, the virtual cell, the low-layer probes) and
# the calibration lines from a calibration record; every GUI is destroyed. readOnly: zero overlay writes.
PROOF_SELECTOR_IMAGE = ('mods/skyeshade/hd2runtime_virtual_selector_proof', 'orbital_gas_barrage_icon')
PROOF_VIRTUAL_SELECTOR = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function count(text)local n=0;for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end;return n end
 for _=1,200 do frame()end
 step('the proof loads from the archive and defines its virtual stratagem',count('VirtualSelectorProof 0.6.0 '
  ..'COORDINATE-DIAGNOSTICS BUILD')==1 and count('loaded (0.6.0 COORDINATE-DIAGNOSTICS): virtual stratagem '
  ..'orbital_gas_barrage (token Orbital Precision Strike). F8 diagnostics on/off')==1,table.concat(lines,' | '):match('VirtualSelectorProof[^|]*'))
 step('aboard the ship it reports the saved loadout, with no virtual slot recognised',count('saved ship loadout: ')==1
  and count('no virtual slot recognised in this order')==1,table.concat(lines,' | '):match('saved ship loadout[^|]*'))
 step('no loadout screen: no card, no selection',count('stratagem selector shown')==0
  and count('stratagem selector SELECTED')==0 and count('loadout screen opened')==0,'')
 -- From the archive, against the stand-in engine GUI.
 local calls={}
 local MAIN=newproxy(true)
 local function rec(name)return function(...)calls[#calls+1]={name=name,args={...}};return #calls end end
 local function nothing(name)return function(...)calls[#calls+1]={name=name,args={...}}end end
 local function constructor(kind)return setmetatable({},{__call=function(_,...)return {kind=kind,...}end})end
 rawset(_G,'stingray',{Application={main_world=function()return MAIN end,worlds=function()return {MAIN}end},
  World={create_screen_gui=rec('create_screen_gui'),destroy_gui=nothing('destroy_gui')},
  Gui={resolution=function()return 2560,1440 end,rect=rec('rect'),update_rect=nothing('update_rect'),text=rec('text'),
   bitmap=rec('bitmap')},
  Vector2=constructor('Vector2'),Vector3=constructor('Vector3'),Color=function(a,r,g,b)return {kind='Color',a,r,g,b}end})
 local selector=require('hd2runtime/runtime/stratagem_selector')
 local texts=require('hd2runtime/runtime/text_resources')
 local images=require('hd2runtime/runtime/image_resources')
 local RESOURCE='mods/skyeshade/hd2runtime_virtual_selector_proof'
 local world=assert(require('hd2runtime/runtime/event_world').open())
 local icon=images.handle('orbital_gas_barrage_icon',RESOURCE)
 local function sequence(from)
  local names={}
  for k=from,#calls do names[#names+1]=calls[k].name end
  return table.concat(names,',')
 end
 local overlay,why=selector.overlay(world.runtime,{text=texts.handle('orbital_gas_barrage_name','Orbital Gas Barrage',
  RESOURCE),icon=icon})
 local text=calls[4]
 step('the drawing proof issues a screen GUI, a rectangle, the custom icon and the custom text',overlay~=nil
  and sequence(1)=='create_screen_gui,rect,bitmap,text'and calls[1].args[1]==MAIN and calls[1].args[2]=='scale'
  and calls[3].args[2]==images.material_name(icon)and text.args[2]=='Orbital Gas Barrage'
  and text.args[3]=='core/performance_hud/monaco'and text.args[6].kind=='Vector3'and text.args[7].kind=='Color',
  tostring(why)..' '..sequence(1))
 if overlay then overlay.close()end
 local first=#calls+1
 local renderer=selector.engine_renderer(world.runtime)
 local cell={x=1100,y=600,w=120,h=120}
 local shown,show_why=renderer.show({{name='Orbital Gas Barrage',description='Calls down a barrage of gas shells.',
  icon=icon}},1,{card=cell,text={x=1100,y=460,w=530,h=120},column=2,newRow=false})
 local inner,tile_icon=calls[first+2],calls[first+3]
 step('the card renderer draws a native-sized tile in the grid cell, then its text area, name and description',
  shown==true and renderer.state=='shown'and renderer.focusFrame=='off'
  and sequence(first)=='create_screen_gui,rect,rect,bitmap,rect,text,text'and calls[first+1].args[2][1]==1100
  and math.abs(inner.args[3][1]-102)<1e-6 and math.abs(tile_icon.args[4][1]-76.5)<1e-6
  and calls[first+5].args[2]=='Orbital Gas Barrage'and calls[first+6].args[2]=='Calls down a barrage of gas shells.',
  tostring(show_why)..' '..sequence(first))
 renderer.close()
 -- The 0.6.0 card: the tile alone, on its own layers.
 first=#calls+1
 local tile=selector.engine_renderer(world.runtime,{layer=900})
 local tile_shown=tile.show({{name='Orbital Gas Barrage',description='Calls down a barrage of gas shells.',icon=icon}},1,
  {card=cell,column=2,newRow=false})
 step('the tile alone is drawn at layers 900 to 902',tile_shown==true and sequence(first)=='create_screen_gui,rect,rect,bitmap'
  and calls[first+1].args[2][3]==900 and calls[first+2].args[2][3]==901 and calls[first+3].args[3][3]==902,
  sequence(first))
 tile.close()
 -- The calibration markers and lines from a calibration record (a 2 px/unit list).
 first=#calls+1
 local native={x=224,y=900,w=160,h=160}
 local cal={scale=2,frameScale=2,frame={x=200,y=150,w=790,h=1056},scroll=100,limit=1000,content=1500,leftUnits=12,
  samples={{label='N0',row=3,column=0,content={x=12,y=403},scrolled={x=12,y=303},model={x=224,y=600,w=160,h=160},
   native=native,runtime=native,delta={x=0,y=-300},depth=0}},
  virtual={label='V',row=9,column=1,content={x=97,y=935},scrolled={x=97,y=835},model={x=394,y=300,w=160,h=160},
   runtime={x=394,y=300,w=160,h=160},visible=true}}
 local markers,markers_why=selector.draw_calibration(world.runtime,cal)
 local labels={}
 for k=first,#calls do if calls[k].name=='text'then labels[calls[k].args[2]]=true end end
 local layers={}
 for k=first,#calls do if calls[k].name=='rect'then layers[calls[k].args[2][3]]=(layers[calls[k].args[2][3]]or 0)+1 end end
 step('the calibration markers are drawn in their own GUI',markers~=nil and calls[first].name=='create_screen_gui'
  and labels['N0 r3 c0']and labels['V r9 c1']and labels['F']and labels['BL 0,0']and labels['TR 2560,1440']
  and labels['C']and labels['L']and layers[21]==2 and(layers[990]or 0)>=7 and(layers[991]or 0)==8,
  tostring(markers_why)..' '..sequence(first))
 if markers then markers.close()end
 local cal_lines=selector.calibration_lines(cal,{resolution={2560,1440},worlds=1,mainIndex=1},0)
 step('the calibration lines name every stage',#cal_lines==3 and cal_lines[1]:find('GUI resolution 2560 x 1440',1,true)
  and cal_lines[2]:find('content (12.00, 403.00) -> after scroll (12.00, 303.00) -> model (224.0, 600.0) -> native '
   ..'transform (224.0, 900.0, 160.0 x 160.0; depth 0.000) -> Runtime GUI (224.0, 900.0, 160.0 x 160.0); model - native '
   ..'(0.00, -300.00)',1,true)~=nil and cal_lines[3]:find('calibration V row 9 column 1',1,true)~=nil,
  table.concat(cal_lines,' | '))
 step('every GUI is destroyed and nothing was written',calls[#calls].name=='destroy_gui'and counts.writes==0
  and count('callback failed')==0 and count('drawing disabled')==0,'writes='..counts.writes)
 rawset(_G,'stingray',nil)
 return results
end
"""
EXTRAS['proof-virtual-selector'] = {'menu': MENU_STUB, 'after': PROOF_VIRTUAL_SELECTOR, 'readOnly': True,
    'seed': PROOF_SELECTOR_IMAGE, 'seedFamily': True}
# RenderOrderProof 0.1.0 (the render-order probe: can a Runtime GUI appear above the native Noesis UI; docs/
# custom-stratagems.md, "Render order") on the shipped artifact aboard the ship with no loadout screen open: every module
# it needs resolves from the archive and it draws nothing. Then, from the archive, against a stand-in for the engine GUI
# and world API with the engine's own types and returns, with the real snapshot's engine font, camera unit and shading
# environment residency: the probe draws its eight GUIs in order (labels, test, layers, A, B, C, D, immediate; the last
# as the performance HUD script makes one), the five layers, the TEST RECTANGLE and two immediate rectangles a frame;
# the overlay world is built (new_world, the 'overlay' viewport, the shading environment, the camera unit), queued from
# the engine's render callback after the original, and released with the callback restored. readOnly: zero writes.
PROOF_RENDER_ORDER = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function count(text)local n=0;for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end;return n end
 for _=1,200 do frame()end
 step('the proof loads from the archive',count('RenderOrderProof 0.1.0 RENDER-ORDER BUILD')==1
  and count('loaded (0.1.0 RENDER-ORDER). F6 overlay world; F8 layers 2000/10000; F9 status.')==1,
  table.concat(lines,' | '):match('RenderOrderProof[^|]*'))
 step('no loadout screen: nothing drawn',count('render probe drawn')==0 and count('overlay world created')==0,'')
 local calls={}
 local MAIN,NEW=newproxy(true),newproxy(true)
 local alive={MAIN}
 local function rec(name)return function(...)calls[#calls+1]={name=name,args={...}};return #calls end end
 local function nothing(name)return function(...)calls[#calls+1]={name=name,args={...}}end end
 local function constructor(kind)return setmetatable({},{__call=function(_,...)return {kind=kind,...}end})end
 rawset(_G,'stingray',{Application={main_world=function()return MAIN end,worlds=function()return alive end,
   new_world=function(...)calls[#calls+1]={name='new_world',args={...}};alive[#alive+1]=NEW;return NEW end,
   create_viewport=rec('create_viewport'),destroy_viewport=nothing('destroy_viewport'),
   render_world=nothing('render_world'),
   release_world=function(w)calls[#calls+1]={name='release_world',args={w}};for i=#alive,1,-1 do if alive[i]==w then
    table.remove(alive,i)end end end},
  World={create_screen_gui=rec('create_screen_gui'),destroy_gui=nothing('destroy_gui'),
   create_shading_environment=rec('create_shading_environment'),
   destroy_shading_environment=nothing('destroy_shading_environment'),spawn_unit=rec('spawn_unit')},
  Unit={camera=rec('camera')},
  Gui={resolution=function()return 2560,1440 end,rect=rec('rect'),update_rect=nothing('update_rect'),text=rec('text'),
   bitmap=rec('bitmap')},
  Vector2=constructor('Vector2'),Vector3=constructor('Vector3'),Color=function(a,r,g,b)return {kind='Color',a,r,g,b}end})
 local probe=require('hd2runtime/runtime/render_probe')
 local world=assert(require('hd2runtime/runtime/event_world').open())
 local cards={}
 for k=0,3 do cards[k+1]={rect={x=300+k*170,y=900,w=160,h=160},row=4,column=k}end
 local P,why=probe.draw(world.runtime,{cards=cards})
 local guis,layers,immediate={},{},nil
 for k,c in ipairs(calls)do
  if c.name=='create_screen_gui'then guis[#guis+1]=k;if c.args[4]=='immediate'then immediate=k end end
 end
 for _,c in ipairs(calls)do if c.name=='rect'and c.args[1]==guis[3]then layers[#layers+1]=c.args[2][3]end end
 step('the probe draws its eight GUIs in order, the layers and the test rectangle',P~=nil
  and table.concat(P.order,',')=='labels,test,layers,A,B,C,D,immediate'and #guis==8 and immediate==guis[8]
  and calls[guis[8]].args[2]==0 and calls[guis[8]].args[3]==0
  and table.concat(layers,',')=='0,21,100,900,990,0,21,100,900,990',tostring(why)..' '..table.concat(layers,','))
 local before=#calls
 P.tick()
 step('the immediate rectangles are drawn again each frame',#calls==before+2 and calls[#calls].args[1]==immediate,
  tostring(#calls-before))
 local original=function(...)return 'original',...end
 rawset(_G,'render',original)
 before=#calls
 local O,overlay_why=probe.overlay_world(world.runtime,P,cards)
 local names={}
 for k=before+1,#calls do names[#names+1]=calls[k].name end
 local a,b=render(5)
 local queued=calls[#calls]
 step('the overlay world is built and queued from the render callback after the original',O~=nil
  and table.concat(names,','):find('new_world,create_viewport,create_shading_environment,spawn_unit,camera,'
   ..'create_screen_gui',1,true)~=nil and a=='original'and b==5 and queued.name=='render_world'and queued.args[1]==NEW,
  tostring(overlay_why)..' '..table.concat(names,','))
 if O then O.close()end
 P.close()
 step('everything is released, the render callback restored, nothing written',rawget(_G,'render')==original
  and #alive==1 and counts.writes==0 and count('callback failed')==0,'writes='..counts.writes)
 rawset(_G,'stingray',nil)
 return results
end
"""
EXTRAS['proof-render-order'] = {'menu': MENU_STUB, 'after': PROOF_RENDER_ORDER, 'readOnly': True}
# CustomStratagemPanelProof 0.7.0 (the custom stratagem system with the slot overlays; docs/custom-stratagems.md, "Slot
# icon overlays in the custom stratagem system") on the shipped artifact aboard the ship with no loadout screen open:
# every module resolves from the archive, the proof defines its virtual stratagem with the masked icon, nothing is drawn
# (no panel, no overlay) or written. Then, from the archive, against the real snapshot: the selector's pinned code
# proven (the slot background research included); the icon colours read from game.dll as the native loadout slot reads
# them (Orbital Precision Strike's colour set 0); the borrowed-icon fallback's atlas lookup still finding both icons on
# one page. Against a stand-in engine GUI whose Application.worlds follows the snapshot's engine world array, and the
# snapshot's residency with the proof's two images seeded as complete families: the anchored layout at 1080p and 4K; the
# panel as a GUI of the Ui World with an opaque tile, the masked icon by its GUI material name on the native grey plate
# (exactly its quad, one layer below) and the native colours on its instance; an overlay drawn with the same shared
# technique getting exactly the same colours; the tooltip; the icon diagnostics; the mouse; the legacy renderer; every
# GUI destroyed. Selection is on in this build, but with no loadout screen open nothing can be selected: readOnly, zero
# writes.
PANEL_IMAGES = [('mods/skyeshade/hd2runtime_custom_stratagem_panel_proof', 'orbital_gas_barrage_masks'),
    ('mods/skyeshade/hd2runtime_custom_stratagem_panel_proof', 'icon_test_pattern')]
PROOF_CUSTOM_PANEL = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function count(text)local n=0;for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end;return n end
 local function u64(q)return q and(q:byte(1)+q:byte(2)*256+q:byte(3)*65536+q:byte(4)*16777216
  +(q:byte(5)+q:byte(6)*256+q:byte(7)*65536+q:byte(8)*16777216)*4294967296)end
 for _=1,200 do frame()end
 step('the proof loads from the archive and defines its virtual stratagem with the masked icon',count('CustomStratagem'
  ..'PanelProof 0.7.0 SLOT OVERLAYS BUILD')==1 and count('loaded (0.7.0 SLOT OVERLAYS): virtual stratagem '
  ..'orbital_gas_barrage (token Orbital Precision Strike, carrier Orbital 120mm HE Barrage, icon '
  ..'orbital_gas_barrage_masks drawn over virtual slots) and 5 visual placeholders')==1 and count('saved ship loadout: ')==1,
  table.concat(lines,' | '):match('CustomStrat[^|]*'))
 step('no loadout screen: no panel, no slot overlay, no borrowed slot icon, nothing written',
  count('custom stratagem panel shown')==0 and count('OVERLAY:')==0 and count('SLOT ICON')==0 and counts.writes==0,'')
 local selector=require('hd2runtime/runtime/stratagem_selector')
 local slot_icons=require('hd2runtime/runtime/stratagem_slot_icons')
 local overlay=require('hd2runtime/runtime/stratagem_slot_overlay')
 local loadout=require('hd2runtime/runtime/stratagem_loadout')
 local D=require('hd2runtime/domains/stratagem_selector')
 local O=D.slotOverlay
 local world=assert(require('hd2runtime/runtime/event_world').open())
 local proven,proof_why=selector.prove(world)
 step('the selector code (every pin: the advance, the slot icon element, the icon colours, the slot focus, the UI sound, '
  ..'the slot overlay chain, the slot background) is proven on the snapshot',
  proven==true,#D.pins..' pins '..tostring(proof_why))
 -- The game's own selection close (what Back calls): its exact first bytes are the snapshot's; this copy-on-write
 -- adapter calls no game function, so a close is refused and nothing is called.
 local C=D.selectorClose
 local refused_close=selector.close_native(world,{ui=0},{index=0,edited=0,token=0})
 step('the game\'s own selection close (game+146F3B0, the call Back makes): its exact first bytes are the snapshot\'s; '
  ..'with no adapter call a close is refused and nothing is called',world.view.proves(world.game+C.rva,C.prologue)
  and C.rva==0x146F3B0 and refused_close.status=='refused'and refused_close.code=='UNAVAILABLE'
  and counts.writes==0,tostring(refused_close.code))
 local precision=loadout.type_of(world,3523620028)
 local vars,set=selector.icon_colours(world,precision)
 local function near(a,b)return math.abs(a-b)<1e-6 end
 step('the icon colours read from game.dll as the native loadout slot reads them',vars~=nil and set==0
  and vars[1][1]=='c0'and near(vars[1][2],0.8)and near(vars[1][3],1)and near(vars[1][4],0.43137255)
  and near(vars[1][5],0.35686275)and near(vars[2][5],0.93333334)and near(vars[3][2],0.2)and vars[4][2]==0,
  tostring(set)..' '..tostring(vars and vars[1][2]))
 local token,token_why=slot_icons.icon(world,3523620028)
 local borrowed,borrowed_why=slot_icons.icon(world,3193297673)
 step('the borrowed-icon fallback still finds both icons on one atlas page (the Runtime\'s own atlas lookup)',token~=nil
  and borrowed~=nil and token.page=='0x5207684C3952B0CC'and borrowed.page==token.page and token.colourSet==0
  and borrowed.colourSet==0 and near(token.rect[1],0.42578125)and near(token.rect[2],0.47265625)
  and near(borrowed.rect[1],0.49609375)and near(borrowed.rect[2],0.4921875)and near(borrowed.rect[3],0.0625),
  tostring(token_why)..' '..tostring(borrowed_why))
 step('the plate is the native icon background\'s grey (slot widget + 0x110, 36/255)',O.background==0x110
  and O.backgroundGrey==36 and overlay.PLATE[1]==36 and overlay.PLATE[2]==36 and overlay.PLATE[3]==36,'')
 -- The engine's world array from the snapshot; Application.worlds lists it in order (full userdata).
 local app=world.view.pointer(world.exe+O.application)
 local n=app and world.view.u32(app+O.worldCount)
 local array=app and world.view.pointer(app+O.worldArray)
 local context=world.view.pointer(world.game+O.gameContext)
 local ui_pointer=context and u64(world.view.read(context+O.uiWorld,8))
 local worlds,ui_index={},nil
 for k=0,(n or 0)-1 do
  worlds[#worlds+1]=newproxy()
  if u64(world.view.read(array+8*k,8))==ui_pointer then ui_index=k+1 end
 end
 local UW=ui_index and worlds[ui_index]
 local calls={}
 local function rec(name)return function(...)calls[#calls+1]={name=name,args={...}};return #calls end end
 local function nothing(name)return function(...)calls[#calls+1]={name=name,args={...}}end end
 local function constructor(kind)return setmetatable({},{__call=function(_,...)return {kind=kind,...}end})end
 rawset(_G,'stingray',{Application={main_world=function()return worlds[1]end,worlds=function()return worlds end},
  World={create_screen_gui=rec('create_screen_gui'),destroy_gui=nothing('destroy_gui')},
  Gui={resolution=function()return 1920,1080 end,rect=rec('rect'),update_rect=nothing('update_rect'),text=rec('text'),
   bitmap=rec('bitmap'),update_bitmap=nothing('update_bitmap'),
   material=function(gui,m)calls[#calls+1]={name='gui_material',args={gui,m}};return {gui=gui,m=m}end},
  Material={set_vector4=nothing('set_vector4')},
  Quaternion={from_elements=function(x,y,z,w)return {kind='Quaternion',x,y,z,w}end},
  IdString64={from_hex=function(h)return {kind='IdString64',hex=h}end},
  Vector2=constructor('Vector2'),Vector3=constructor('Vector3'),Color=function(a,r,g,b)return {kind='Color',a,r,g,b}end})
 local panel=require('hd2runtime/runtime/custom_stratagem_panel')
 local images=require('hd2runtime/runtime/image_resources')
 local RESOURCE='mods/skyeshade/hd2runtime_custom_stratagem_panel_proof'
 local icon=images.handle('orbital_gas_barrage_masks',RESOURCE)
 local pattern=images.handle('icon_test_pattern',RESOURCE)
 local D1,D4={x=500,y=232,w=1024,h=400},{x=1002,y=600,w=2048,h=800}
 local L,K=panel.anchored_layout(1920,1080,{details=D1,count=6}),panel.anchored_layout(3840,2160,{details=D4,count=6,unit=2})
 local function meets(a,b)return a.x<b.x+b.w and b.x<a.x+a.w and a.y<b.y+b.h and b.y<a.y+a.h end
 step('the panel sits right of the details panel at 1080p and 4K: 75 and 150 px tiles, 3 columns, 2 rows',L~=nil
  and K~=nil and math.abs(L.tile-75)<1e-6 and math.abs(K.tile-150)<1e-6 and L.grid.columns==3 and K.grid.rows==2
  and not meets(L.panel,D1)and not meets(K.panel,D4)and L.panel.x>=D1.x+D1.w+15-1e-6 and K.panel.x>=D4.x+D4.w+30-1e-6,'')
 local entries=panel.entries()
 entries[1].colours,entries[1].colourSet=vars,set
 for _,e in ipairs(panel.placeholders(5))do entries[#entries+1]=e end
 local reported={}
 local screen,why=panel.draw_compact(world.runtime,L,entries,function(l)reported[#reported+1]=l end)
 local gui,bitmap,plate,opaque
 for k,c in ipairs(calls)do if c.name=='create_screen_gui'then gui=k end end
 for _,c in ipairs(calls)do if c.name=='bitmap'and c.args[1]==gui then bitmap=c end end
 for _,c in ipairs(calls)do
  if c.name=='rect'and c.args[1]==gui and bitmap and c.args[2][3]==bitmap.args[3][3]-1 then plate=c end
  if c.name=='rect'and c.args[1]==gui and c.args[2][3]==panel.LAYER_BASE+12 then opaque=(opaque~=false)and c.args[4][1]==255 end
 end
 local function vectors(g)
  local out={}
  for _,c in ipairs(calls)do
   if c.name=='set_vector4'and c.args[1].gui==g then
    out[#out+1]=c.args[2]..'='..table.concat({c.args[3][1],c.args[3][2],c.args[3][3],c.args[3][4]},',')
   end
  end
  return table.concat(out,' ')
 end
 step('the panel is a Ui World GUI: an opaque tile, the masked icon by its GUI material name on the native grey plate '
  ..'(its quad, one layer below) and the native colours on its instance',screen~=nil and UW~=nil
  and calls[gui].args[1]==UW and opaque==true and bitmap~=nil and bitmap.args[2]==images.material_name(icon)
  and plate~=nil and plate.args[2][1]==bitmap.args[3][1]and plate.args[2][2]==bitmap.args[3][2]
  and plate.args[3][1]==bitmap.args[4][1]and plate.args[3][2]==bitmap.args[4][2]and plate.args[4][1]==255
  and plate.args[4][2]==36 and plate.args[4][3]==36 and plate.args[4][4]==36
  and(reported[3]or''):find('custom icon colours set for orbital_gas_barrage',1,true)~=nil
  and select(2,vectors(gui):gsub('=',''))==4,tostring(why)..' '..table.concat(reported,' | '))
 -- The slot overlay's own path, the same shared functions, the same colours: one colour treatment everywhere.
 local over,over_why=overlay.open_gui(world)
 local ids=over and overlay.draw_icon(over,{material=images.material_name(icon),x=100,y=900,w=70,h=70,
  layer=O.overlayLayer,alpha=1,plate=overlay.PLATE})
 local coloured=over and ids and overlay.colour(over,images.material_name(icon),vars)
 local og
 for k,c in ipairs(calls)do if c.name=='create_screen_gui'then og=k end end
 step('an overlay drawn with the same shared technique gets exactly the panel tile\'s colours, in the Ui World',
  over~=nil and ids~=nil and ids.plate~=nil and coloured==true and calls[og].args[1]==UW and vectors(og)==vectors(gui),
  tostring(over_why)..' '..vectors(og)..' | '..vectors(gui))
 local focus,tip=panel.draw_focus(world.runtime,L,entries[1],1)
 step('the tooltip is drawn below the panel, inside its column',focus~=nil and tip~=nil and L.tooltipMode=='below'
  and tip.y+tip.h<=L.panel.y+1e-6 and not meets(tip,D1),'')
 local diag_lines={}
 local diag,res=panel.draw_icon_diagnostics(world.runtime,L,icon,function(l)diag_lines[#diag_lines+1]=l end,
  {colours=vars,pattern=pattern})
 local labels={}
 for _,r in ipairs(res or{})do
  labels[#labels+1]=r.label..(r.id~=nil and'+'or'-')..((r.colours or''):find('^set')and'c'or'')
 end
 step('the icon diagnostics: row 1 coloured (font, vanilla and custom by IdString64 and name, the test pattern), row 2 '
  ..'plain, the custom material at four sizes, the texture not drawable',diag~=nil and #labels==13
  and table.concat(labels,',',1,9)=='A font+,A vanilla+c,B name+c,B hash+c,E pattern+c,C texture-,A vanilla plain+,'
  ..'B name plain+,E pattern plain+',table.concat(labels,',')..' | '..table.concat(diag_lines,' | '))
 local gx,gy=panel.to_gui({x=960,y=540,w=1920,h=1080},3840,2160)
 local t=L.tiles[1].rect
 local hit=panel.hit(L,t.x+1,t.y+1)
 step('the mouse converts to GUI pixels and hits the tiles',math.abs(gx-1920)<1e-6 and math.abs(gy-1080)<1e-6 and hit==1
  and panel.hit(L,1,1)==nil,'')
 local legacy=panel.draw(world.runtime,panel.layout(1920,1080,{count=6}),entries,{})
 step('the legacy renderer still draws',legacy~=nil,'')
 for _,g in ipairs({screen,over,focus,diag,legacy})do if g then g.close()end end
 local made,gone=0,0
 for _,c in ipairs(calls)do if c.name=='create_screen_gui'then made=made+1 elseif c.name=='destroy_gui'then gone=gone+1 end end
 step('every GUI is destroyed and nothing was written',made==6 and gone==6 and counts.writes==0
  and count('callback failed')==0,'writes='..counts.writes..' made '..made..' gone '..gone)
 rawset(_G,'stingray',nil)
 return results
end
"""
EXTRAS['proof-custom-stratagem-panel'] = {'menu': MENU_STUB, 'after': PROOF_CUSTOM_PANEL, 'readOnly': True,
    'seeds': PANEL_IMAGES, 'seedFamily': True}
# SlotHighlightProof 0.1.0 (the native loadout slot highlight moved by guarded data writes; docs/custom-stratagems.md,
# "Moving the native slot highlight") on the shipped artifact aboard the ship with no loadout screen open: every module
# resolves from the archive, the selector's pinned code (with the highlight path: the focus setter, the widget visual
# update and the panel update's frame-flash end) is proven on the real snapshot, the highlight state is not readable
# without a loadout screen, and a move is refused with nothing written.
PROOF_SLOT_HIGHLIGHT = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function count(text)local n=0;for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end;return n end
 for _=1,200 do frame()end
 step('the proof loads from the archive',count('SlotHighlightProof 0.1.0 NATIVE HIGHLIGHT BUILD')==1
  and count('loaded (0.1.0 NATIVE HIGHLIGHT): F7 next')==1,table.concat(lines,' | '):match('SlotHigh[^|]*'))
 local selector=require('hd2runtime/runtime/stratagem_selector')
 local focus=require('hd2runtime/runtime/stratagem_slot_focus')
 local world=assert(require('hd2runtime/runtime/event_world').open())
 local proven,why=selector.prove(world)
 step('the selector code with the highlight path is proven on the snapshot',proven==true,tostring(why))
 local view=selector.screen(world)
 step('no loadout screen in the snapshot: the highlight state is not read',view~=nil and view.open==false
  and focus.read(world,view)==nil,'')
 local handle=focus.move(1)
 for _=1,10 do frame()end
 step('a move without a loadout screen is refused, nothing written',handle.status=='refused'
  and handle.code=='SCREEN_CLOSED'and counts.writes==0 and count('callback failed')==0,
  tostring(handle.status)..' '..tostring(handle.code)..' writes='..counts.writes)
 return results
end
"""
EXTRAS['proof-slot-highlight'] = {'menu': MENU_STUB, 'after': PROOF_SLOT_HIGHLIGHT, 'readOnly': True}
# PanelIconProof 0.1.0 (the custom panel's icon as the game's icon masks; visual only; docs/custom-stratagems.md, "The
# panel icon: the game's mask convention") on the shipped artifact aboard the ship with no loadout screen open: every
# module resolves from the archive, the proof defines its virtual stratagem with the masked icon, nothing is drawn or
# written. Then, against the stand-in engine GUI (its Application.worlds following the snapshot's engine world array:
# the panel's GUIs are opened in the Ui World since the 0.7.0 runtime) and the real snapshot (the icon colours read from
# game.dll), with both images seeded as complete families: the panel draws the masked icon's GUI material with the
# native colours set, and the diagnostics compare it with the original picture ('E original'). Selection is off: zero
# overlay writes.
PANEL_ICON_IMAGES = [('mods/skyeshade/hd2runtime_panel_icon_proof', 'orbital_gas_barrage_masks'),
    ('mods/skyeshade/hd2runtime_panel_icon_proof', 'orbital_gas_barrage')]
PROOF_PANEL_ICON = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function count(text)local n=0;for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end;return n end
 for _=1,200 do frame()end
 step('the proof loads from the archive with the masked icon',count('PanelIconProof 0.1.0 MASKED ICON BUILD')==1
  and count('loaded (0.1.0 MASKED ICON): the masked icon orbital_gas_barrage_masks on the tile')==1
  and count('custom stratagem panel shown')==0 and counts.writes==0,table.concat(lines,' | '):match('PanelIcon[^|]*'))
 local selector=require('hd2runtime/runtime/stratagem_selector')
 local loadout=require('hd2runtime/runtime/stratagem_loadout')
 local world=assert(require('hd2runtime/runtime/event_world').open())
 local proven,why=selector.prove(world)
 local vars,set=selector.icon_colours(world,loadout.type_of(world,3523620028))
 step('the native icon colours are read from game.dll',proven==true and vars~=nil and set==0,tostring(why))
 local calls={}
 -- The engine's world array from the snapshot (Application.worlds lists it in order): the panel's GUIs are opened in the
 -- Ui World (0.7.0 runtime: the slot overlay technique).
 local O=require('hd2runtime/domains/stratagem_selector').slotOverlay
 local app=world.view.pointer(world.exe+O.application)
 local listed=app and world.view.u32(app+O.worldCount)or 0
 local worlds={}
 for k=1,listed do worlds[k]=newproxy()end
 local function rec(name)return function(...)calls[#calls+1]={name=name,args={...}};return #calls end end
 local function nothing(name)return function(...)calls[#calls+1]={name=name,args={...}}end end
 local function constructor(kind)return setmetatable({},{__call=function(_,...)return {kind=kind,...}end})end
 rawset(_G,'stingray',{Application={main_world=function()return worlds[1]end,worlds=function()return worlds end},
  World={create_screen_gui=rec('create_screen_gui'),destroy_gui=nothing('destroy_gui')},
  Gui={resolution=function()return 1920,1080 end,rect=rec('rect'),update_rect=nothing('update_rect'),text=rec('text'),
   bitmap=rec('bitmap'),material=function(gui,m)calls[#calls+1]={name='gui_material',args={gui,m}};return {gui=gui,m=m}end},
  Material={set_vector4=nothing('set_vector4')},
  Quaternion={from_elements=function(x,y,z,w)return {kind='Quaternion',x,y,z,w}end},
  IdString64={from_hex=function(h)return {kind='IdString64',hex=h}end},
  Vector2=constructor('Vector2'),Vector3=constructor('Vector3'),Color=function(a,r,g,b)return {kind='Color',a,r,g,b}end})
 local panel=require('hd2runtime/runtime/custom_stratagem_panel')
 local images=require('hd2runtime/runtime/image_resources')
 local RESOURCE='mods/skyeshade/hd2runtime_panel_icon_proof'
 local masks=images.handle('orbital_gas_barrage_masks',RESOURCE)
 local original=images.handle('orbital_gas_barrage',RESOURCE)
 local L=panel.anchored_layout(1920,1080,{details={x=500,y=232,w=1024,h=400},count=6})
 local entries=panel.entries()
 entries[1].colours,entries[1].colourSet=vars,set
 for _,e in ipairs(panel.placeholders(5))do entries[#entries+1]=e end
 local reported={}
 local screen,draw_why=panel.draw_compact(world.runtime,L,entries,function(l)reported[#reported+1]=l end)
 local bitmap,sets=nil,0
 for _,c in ipairs(calls)do if c.name=='bitmap'then bitmap=c elseif c.name=='set_vector4'then sets=sets+1 end end
 step('the tile draws the masked icon with the native colours set',screen~=nil and bitmap~=nil
  and bitmap.args[2]==images.material_name(masks)and sets==4,tostring(draw_why)..' '..table.concat(reported,' | '))
 local diag,res=panel.draw_icon_diagnostics(world.runtime,L,masks,function()end,{colours=vars,pattern=original,
  patternLabel='E original'})
 local labels={}
 for _,r in ipairs(type(res)=='table'and res or{})do labels[#labels+1]=r.label..(r.id~=nil and'+'or'-')end
 step('the diagnostics compare the masked icon with the original picture',diag~=nil
  and table.concat(labels,','):find('B name+,B hash+,E original+,C texture-,A vanilla plain+,B name plain+,E original '
  ..'plain+',1,true)~=nil,table.concat(labels,',')..' '..tostring(type(res)=='string'and res or''))
 for _,g in ipairs({screen,diag})do if g then g.close()end end
 step('nothing was written',counts.writes==0 and count('callback failed')==0,'writes='..counts.writes)
 rawset(_G,'stingray',nil)
 return results
end
"""
EXTRAS['proof-panel-icon'] = {'menu': MENU_STUB, 'after': PROOF_PANEL_ICON, 'readOnly': True,
    'seeds': PANEL_ICON_IMAGES, 'seedFamily': True}
# SelectionSoundProof 0.1.0 (the loadout screen's own UI sound events through the Wwise Lua API; docs/custom-stratagems.md,
# "The selection sound") on the shipped artifact aboard the ship: the proof loads from the archive and plays nothing on
# its own. Then, from the archive, against the real snapshot: the selector's pinned code (with the UI sound path) is
# proven and the game's own Game World and its WwiseWorld are read from game.dll memory; against a stand-in Wwise API
# whose world list follows the snapshot's engine world array, an event is posted only on the world value at the Game
# World's position, by the name hashing to the game's event id, and refused (nothing posted) when the lists differ.
# Zero writes.
PROOF_SELECTION_SOUND = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function count(text)local n=0;for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end;return n end
 for _=1,200 do frame()end
 step('the proof loads from the archive and plays nothing on its own',count('SelectionSoundProof 0.1.0 UI SOUND '
  ..'IDENTIFICATION BUILD')==1 and count('ui sound PLAYED')==0 and counts.writes==0,
  table.concat(lines,' | '):match('SelectionSound[^|]*'))
 local selector=require('hd2runtime/runtime/stratagem_selector')
 local sound=require('hd2runtime/runtime/ui_sound')
 local D=require('hd2runtime/domains/stratagem_selector')
 local world=assert(require('hd2runtime/runtime/event_world').open())
 local proven,why=selector.prove(world)
 local context=world.view.pointer(world.game+D.uiSound.context)
 local s=context and world.view.read(context+D.uiSound.world,8)
 local game_world=s and(s:byte(1)+s:byte(2)*256+s:byte(3)*65536+s:byte(4)*16777216
  +(s:byte(5)+s:byte(6)*256+s:byte(7)*65536+s:byte(8)*16777216)*4294967296)
 local ww=context and world.view.read(context+D.uiSound.wwiseWorld,8)
 step('the UI sound path is proven and the Game World with its WwiseWorld is read from game.dll',proven==true
  and game_world and game_world~=0 and ww and ww~=string.rep(string.char(0),8),tostring(why))
 -- The engine's world array from the snapshot: Application.worlds lists it in order (full userdata, matched by position).
 local O=D.slotOverlay
 local app=world.view.pointer(world.exe+O.application)
 local listed=app and world.view.u32(app+O.worldCount)
 local array=app and world.view.pointer(app+O.worldArray)
 local worlds,GW={},nil
 for k=0,(listed or 0)-1 do
  local v=newproxy();worlds[#worlds+1]=v
  local q=world.view.read(array+8*k,8)
  local ptr=q and(q:byte(1)+q:byte(2)*256+q:byte(3)*65536+q:byte(4)*16777216
   +(q:byte(5)+q:byte(6)*256+q:byte(7)*65536+q:byte(8)*16777216)*4294967296)
  if ptr==game_world then GW=v end
 end
 local OTHER=worlds[#worlds]~=GW and worlds[#worlds]or worlds[1]
 step('the Game World is in the engine world list read from the snapshot',GW~=nil and listed~=nil and listed>=2,
  tostring(listed))
 local posts={}
 rawset(_G,'stingray',{Application={worlds=function()return worlds end,main_world=function()return OTHER end},
  Wwise={wwise_world=function(w)return {of=w}end,has_event=function()return true end},
  WwiseWorld={trigger_event=function(w,name)posts[#posts+1]={world=w.of,name=name};return 77,1 end}})
 local played=sound.play('picker_close')
 step('an event is posted only on the Game World, by the name hashing to the game\'s event id',played~=nil
  and #posts==1 and posts[1].world==GW and posts[1].name=='hd2runtime_bci6lee'
  and sound.fnv1(posts[1].name)==0x0DBB2A14,'')
 local full=worlds
 worlds={OTHER}
 local refused,code=sound.play('picker_close')
 step('Application.worlds not matching the engine list: refused, nothing posted',refused==nil and code=='NO_WORLD'
  and #posts==1,tostring(code))
 worlds=full
 step('nothing was written',counts.writes==0 and count('callback failed')==0,'writes='..counts.writes)
 rawset(_G,'stingray',nil)
 return results
end
"""
EXTRAS['proof-selection-sound'] = {'menu': MENU_STUB, 'after': PROOF_SELECTION_SOUND, 'readOnly': True}
# SlotTextureProbe 0.1.0 (the native slot icon's render-side texture chain, read only; docs/custom-stratagems.md, "A
# custom texture in a native slot") on the shipped artifact aboard the ship with no loadout screen open: the proof loads
# from the archive, the probe reports that the loadout screen is not open, nothing is written.
PROOF_SLOT_TEXTURE = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function count(text)local n=0;for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end;return n end
 for _=1,200 do frame()end
 step('the probe loads from the archive',count('SlotTextureProbe 0.1.0 READ ONLY BUILD')==1,
  table.concat(lines,' | '):match('SlotTexture[^|]*'))
 local probe=require('hd2runtime/runtime/stratagem_slot_texture_probe')
 local out=probe.run(nil)
 step('no loadout screen: nothing read further, nothing written',out[1]=='the loadout screen is not open'
  and counts.writes==0 and count('callback failed')==0,tostring(out[1]))
 return results
end
"""
EXTRAS['proof-slot-texture-probe'] = {'menu': MENU_STUB, 'after': PROOF_SLOT_TEXTURE, 'readOnly': True,
    'seeds': [('mods/skyeshade/hd2runtime_slot_texture_probe', 'orbital_gas_barrage_masks')], 'seedFamily': True}
# SlotOverlayProof 0.1.0 (the custom icon drawn by a Runtime GUI over native slot icons for fake virtual slot identities;
# visual only; docs/custom-stratagems.md, "Slot icon overlays") on the shipped artifact aboard the ship with no loadout
# screen open: the proof loads from the archive and draws nothing on its own. Against the real snapshot and a stand-in
# engine GUI whose Application.worlds follows the snapshot's engine world array: the Ui World named by the game context
# is found at its position in that array; the Orbital Precision Strike's icon colours are read from game.dll; the mission
# HUD is refused aboard the ship. Then the proof's own keys (through the input backend): F9 sets virtual / native /
# virtual / native, nothing is drawn because no loadout screen is open (logged per slot), Home and End answer, F9 clears.
# Zero writes.
PROOF_SLOT_OVERLAY = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function count(text)local n=0;for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end;return n end
 local function u64(q)return q and(q:byte(1)+q:byte(2)*256+q:byte(3)*65536+q:byte(4)*16777216
  +(q:byte(5)+q:byte(6)*256+q:byte(7)*65536+q:byte(8)*16777216)*4294967296)end
 for _=1,200 do frame()end
 step('the proof loads from the archive and draws nothing on its own',count('SlotOverlayProof 0.1.0 SLOT ICON OVERLAY '
  ..'BUILD')==1 and count('loaded (0.1.0 SLOT ICON OVERLAY)')==1 and count('OVERLAY:')==0 and counts.writes==0,
  table.concat(lines,' | '):match('SlotOverlay[^|]*'))
 local selector=require('hd2runtime/runtime/stratagem_selector')
 local overlay=require('hd2runtime/runtime/stratagem_slot_overlay')
 local loadout=require('hd2runtime/runtime/stratagem_loadout')
 local D=require('hd2runtime/domains/stratagem_selector')
 local O=D.slotOverlay
 local world=assert(require('hd2runtime/runtime/event_world').open())
 local proven,why=selector.prove(world)
 step('the selector code with the overlay chain is proven on the snapshot',proven==true,tostring(why))
 -- The engine's world array from the snapshot; Application.worlds lists it in order (full userdata).
 local app=world.view.pointer(world.exe+O.application)
 local n=app and world.view.u32(app+O.worldCount)
 local array=app and world.view.pointer(app+O.worldArray)
 local context=world.view.pointer(world.game+O.gameContext)
 local ui_pointer=context and u64(world.view.read(context+O.uiWorld,8))
 local worlds,expected={},nil
 for k=0,(n or 0)-1 do
  worlds[#worlds+1]=newproxy()
  if u64(world.view.read(array+8*k,8))==ui_pointer then expected=k+1 end
 end
 local calls={}
 local function rec(name)return function(...)calls[#calls+1]={name=name,args={...}};return #calls end end
 local function nothing(name)return function(...)calls[#calls+1]={name=name,args={...}}end end
 local function constructor(kind)return setmetatable({},{__call=function(_,...)return {kind=kind,...}end})end
 rawset(_G,'stingray',{Application={main_world=function()return worlds[1]end,worlds=function()return worlds end},
  World={create_screen_gui=rec('create_screen_gui'),destroy_gui=nothing('destroy_gui')},
  Gui={resolution=function()return 1920,1080 end,rect=rec('rect'),update_rect=nothing('update_rect'),
   bitmap=rec('bitmap'),update_bitmap=nothing('update_bitmap'),
   material=function(gui,m)calls[#calls+1]={name='gui_material',args={gui,m}};return {gui=gui,m=m}end},
  Material={set_vector4=nothing('set_vector4')},
  Quaternion={from_elements=function(x,y,z,w)return {kind='Quaternion',x,y,z,w}end},
  Vector2=constructor('Vector2'),Vector3=constructor('Vector3'),Color=function(a,r,g,b)return {kind='Color',a,r,g,b}end})
 local uw,index=overlay.ui_world(world)
 step('the Ui World is found at its position in the snapshot\'s engine world list',expected~=nil and n>=2
  and uw==worlds[expected]and index==expected,('expected %s, got %s of %s'):format(tostring(expected),tostring(index),
  tostring(n)))
 local vars,set=selector.icon_colours(world,loadout.type_of(world,3523620028))
 step('the Orbital Precision Strike\'s icon colours are read from game.dll',vars~=nil and set==0,tostring(set))
 local hud,hud_why=overlay.hud_entries(world)
 step('the mission HUD is refused aboard the ship',hud==nil and tostring(hud_why):find('the mission HUD is not shown',1,
  true)~=nil,tostring(hud_why))
 local input=require('hd2runtime/runtime/input')
 local held
 input.set_backend({focused=function()return true end,down=function(code)return code==held end})
 local function press(key)held=assert(input.keys[key:upper()],key);frame();frame();held=nil;frame()end
 press('F9')
 for _=1,5 do frame()end
 step('F9: virtual / native / virtual / native, nothing drawn with no loadout screen open',
  count('F9: virtual / native / virtual / native: fake virtual slots V n V n')==1
  and count('ship slot 0: no icon element: the loadout screen is not open')==1
  and count('ship slot 2: no icon element: the loadout screen is not open')==1
  and count('ship slot 1: no icon element')==0 and#calls==0,table.concat(lines,' | '):match('F9[^|]*'))
 press('Home')
 press('End')
 step('Home toggles the backing plate; End reports the Ui World and the colours',count('Home: backing plate ON')==1
  and count('End [0.1.0 SLOT ICON OVERLAY]: fake virtual slots V n V n; backing on; Ui World worlds()['..tostring(expected)
  ..']; colours Orbital Precision Strike\'s; shown: no overlay shown')==1,table.concat(lines,' | '):match('End %[[^|]*'))
 press('F9')
 for _=1,3 do frame()end
 step('F9 again: all native, nothing drawn',count('F9: all native: fake virtual slots n n n n')==1 and#calls==0,'')
 step('nothing was written',counts.writes==0 and count('callback failed')==0,'writes='..counts.writes)
 rawset(_G,'stingray',nil)
 return results
end
"""
EXTRAS['proof-slot-overlay'] = {'menu': MENU_STUB, 'after': PROOF_SLOT_OVERLAY, 'readOnly': True,
    'seeds': [('mods/skyeshade/hd2runtime_slot_overlay_proof', 'orbital_gas_barrage_masks')], 'seedFamily': True}
# GasBarrageMissionProof 0.5.0 (carrier discovery, live-proven in 0.4.0, and the custom Gas Barrage code on the carrier:
# payload stage A; docs/custom-stratagems.md, "The custom stratagem in a mission") on the shipped artifact aboard the
# ship, the snapshot's real StratagemSettings, account catalogue and text registry, with the proof's masked icon entered
# as a complete family: it loads from the archive with the custom panel and its text probe passes; with no virtual slot
# on this snapshot it discovers nothing, applies nothing and writes nothing (the pre-mission check: not ready). Then,
# from the archive against the real snapshot, the proof's own discovery: ready (the token shows as owned), the donor
# excluded, the token never a candidate, the first eligible carrier an orbital bombardment not in the saved loadout; the
# Runtime text applied to THAT carrier only (5 writes: the table and its three members) and restored (4); the code check
# on the real rows (no native code equal to UP UP DOWN DOWN, only the three mission objectives' codes start with it, no
# saved stratagem related); the public calldown_code ensure on THAT carrier (its native code read from its row first as
# the expect): 2 writes (the count, then the pointer), only the carrier's +0x40..+0x4C changed, then restored exactly
# (2 writes); the token's and the donor's rows byte-identical throughout.
PROOF_GAS_BARRAGE_MISSION = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function count(text)local n=0;for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end;return n end
 local world=assert(require('hd2runtime/runtime/event_world').open())
 local loadout=require('hd2runtime/runtime/stratagem_loadout')
 local TABLE=require('hd2runtime/schemas/current').stratagem.table_rva
 local function row_of(id)local kind=loadout.type_of(world,id);return kind and world.view.pointer(world.game+TABLE+kind*8)end
 local token_row,donor_row=row_of(3523620028),row_of(1063322614)
 local TOKEN_ROW=token_row and world.runtime.read(token_row,400)
 local DONOR_ROW=donor_row and world.runtime.read(donor_row,400)
 local function others_native()
  return world.runtime.read(token_row,400)==TOKEN_ROW and world.runtime.read(donor_row,400)==DONOR_ROW
 end
 for _=1,240 do frame()end
 step('the proof loads from the archive with the custom panel; its text probe passes on the real registry',
  count('GasBarrageMissionProof 0.5.0 CUSTOM CALLDOWN BUILD')==1 and count('loaded (0.5.0 CUSTOM CALLDOWN): '
  ..'virtual stratagem orbital_gas_barrage (token Orbital Precision Strike; carrier: discovered from what you own, '
  ..'never the donor Orbital 120mm HE Barrage; icon orbital_gas_barrage_masks; code up up down down on the carrier)')==1
  and count('text probe: game text registry 17 of 18 tables, 1 spare; language us; id clashes: none -> PASS')==1,
  table.concat(lines,' | '):match('text probe[^|]*'))
 step('no virtual slot: nothing discovered, applied or written; the pre-mission check is not ready',
  count('CARRIER CANDIDATE: ')==0 and count('SELECTED: the first of')==0 and count('CODE CHECK: ')==0
  and counts.writes==0
  and count('PRE-MISSION CHECK: virtual Gas Barrage slots = 0; saved tokens = ')>=1
  and count('carrier = nil (stable id nil); carrier present in saved loadout = false; 120mm present in saved '
  ..'loadout = false')>=1
  and count('NOT READY: no virtual Gas Barrage slot')>=1,table.concat(lines,' | '):match('PRE%-MISSION CHECK[^|]*'))
 local selector=require('hd2runtime/runtime/stratagem_selector')
 local saved=loadout.saved(world)
 local present={}
 for _,pair in ipairs(saved and saved.pairs or{})do present[pair.id]=true end
 local found=selector.discover_carrier('orbital_gas_barrage',present)
 local donor,token_listed,eligible=nil,false,0
 for _,c in ipairs(found.candidates or{})do
  if c.name=='Orbital 120mm HE Barrage'then donor=c end
  if c.name=='Orbital Precision Strike'then token_listed=true end
  if c.eligible then eligible=eligible+1 end
 end
 local chosen=found.chosen
 step('the proof\'s discovery on the real account catalogue: ready, the donor excluded, the token never a candidate, '
  ..'an orbital bombardment chosen that is not in the saved loadout',found.ready==true and donor~=nil and not donor.eligible
  and not token_listed and chosen~=nil and chosen.class==1 and chosen.component=='BombardmentComponentData'
  and not chosen.inLoadout and chosen.owned and eligible>=1,('%s; chosen %s; %d eligible'):format(tostring(found.reason),
  tostring(chosen and chosen.name),eligible))
 local presentation=require('hd2runtime/runtime/stratagem_presentation')
 local texts=require('hd2runtime/runtime/text_resources')
 local RESOURCE='mods/skyeshade/hd2runtime_gas_barrage_mission_proof'
 local function settle(handle)for _=1,200 do if handle.status~='pending'then break end;frame()end;return handle end
 local carrier_row=chosen and row_of(chosen.id)
 local CARRIER_ROW=carrier_row and world.runtime.read(carrier_row,400)
 local applied=chosen and settle(presentation.apply_text({carrier=chosen.name,
  name=texts.handle('orbital_gas_barrage_name','ORBITAL GAS BARRAGE',RESOURCE),
  nameCased=texts.handle('orbital_gas_barrage_name_cased','Orbital Gas Barrage',RESOURCE),
  description=texts.handle('orbital_gas_barrage_description','Calls down a barrage of gas shells.',RESOURCE)}))
 local after_apply=counts.writes
 local only=carrier_row~=nil
 if carrier_row then
  local now=world.runtime.read(carrier_row,400)
  for i=1,400 do
   local at=i-1
   if now:byte(i)~=CARRIER_ROW:byte(i)and not(at>=0x28 and at<0x34)then only=false end
  end
 end
 step('the Runtime text on the discovered carrier only: 5 writes (the table and its three members); the token\'s and '
  ..'the donor\'s rows byte-identical',applied~=nil and applied.status=='applied'and after_apply==5 and only
  and others_native(),tostring(applied and applied.code)..' writes='..after_apply)
 local restored=chosen and settle(presentation.restore())
 step('restored: the carrier row is native again (4 writes); the token and the donor untouched',restored~=nil
  and restored.status=='restored'and counts.writes==after_apply+4 and carrier_row~=nil
  and world.runtime.read(carrier_row,400)==CARRIER_ROW and others_native(),'writes='..counts.writes)
 -- Stage A: the custom code on the discovered carrier, through the public field, from its native code read first.
 local calldown=require('hd2runtime/runtime/calldown_codes')
 local domain=require('hd2runtime/domains/stratagem_calldown')
 local function code_at(row)
  local n=row and world.runtime.read(row+0x48,4)
  local raw=row and world.runtime.read(row+0x40,8)
  if not(n and raw)then return nil end
  n=n:byte(1)+n:byte(2)*256
  local array=0
  for i=8,1,-1 do array=array*256+raw:byte(i)end
  local out={}
  for k=0,n-1 do local v=world.runtime.read(array+k*4,4);out[k+1]=v and v:byte(1)end
  return out
 end
 local native_code=code_at(carrier_row)
 local reviewed=chosen and domain.nativeCodes[tostring(chosen.id)]
 local related,equal,selectable_related={},0,0
 local ROWM=require('hd2runtime/domains/stratagem_slots').row
 for _,r in ipairs(calldown.native_relations({1,1,3,3},chosen and{[chosen.id]=true}))do
  related[#related+1]=calldown.key(r.values);if r.relation=='equal'then equal=equal+1 end
  local row=row_of(r.id)
  local flags=row and world.runtime.read(row+ROWM.selectable,4)
  if not flags or math.floor(flags:byte(1)/ROWM.selectableBit)%2==1 then selectable_related=selectable_related+1 end
 end
 table.sort(related)
 local saved_related=0
 for _,pair in ipairs(saved and saved.pairs or{})do
  local values=code_at(row_of(pair.id))
  if values and calldown.relation({1,1,3,3},values)then saved_related=saved_related+1 end
 end
 step('the code check on the real rows: the carrier\'s native code read from its row equals the reviewed one; no '
  ..'native code equals UP UP DOWN DOWN; only the three mission objectives\' codes start with it, none of them '
  ..'selectable; no saved stratagem relates to it',native_code~=nil and reviewed~=nil
  and calldown.same(native_code,reviewed) and equal==0 and selectable_related==0
  and table.concat(related,' ')=='1,1,3,3,2,2,3 1,1,3,3,2,3 1,1,3,3,4,2,4,2'and saved_related==0,
  ('native %s; related %s (%d selectable); saved related %d'):format(native_code and calldown.text(native_code)
  or'nil',table.concat(related,' '),selectable_related,saved_related))
 local hd2=require('mods/skyeshade/hd2runtime')
 local before_code=counts.writes
 local code_op=chosen and native_code and hd2.ensure({patch={id='gas-barrage-carrier-code-check',
  target=hd2.stratagem(chosen.name),field=hd2.fields.stratagem.calldown_code,expect=calldown.names(native_code),
  value={'up','up','down','down'}}})
 for _=1,40 do if code_op and code_op.result then break end;frame()end
 local now=carrier_row and world.runtime.read(carrier_row,400)
 local outside=now~=nil
 if now then
  for i=1,400 do
   local at=i-1
   if now:byte(i)~=CARRIER_ROW:byte(i)and not(at>=0x40 and at<0x4C)then outside=false end
  end
 end
 local applied_code=code_at(carrier_row)
 step('the public calldown_code ensure on the discovered carrier only: 2 writes (the count, then the pointer); the row '
  ..'holds UP UP DOWN DOWN; nothing else of the carrier row changed; the token and the donor untouched',code_op~=nil
  and code_op.result~=nil and counts.writes==before_code+2 and applied_code~=nil
  and calldown.key(applied_code)=='1,1,3,3'and outside and others_native(),('status %s %s writes=%d'):format(
  tostring(code_op and code_op.status),tostring(code_op and code_op.result and code_op.result.status),
  counts.writes-before_code))
 -- The restore before the Lua state goes away (the ensure stopped first so it does not apply again).
 if code_op then code_op.cancel()end
 calldown.finalize_for_tests()
 step('the carrier\'s native code restored exactly (2 writes): the carrier row byte-identical to before; the token and '
  ..'the donor untouched',carrier_row~=nil and world.runtime.read(carrier_row,400)==CARRIER_ROW
  and counts.writes==before_code+4 and others_native(),'writes='..(counts.writes-before_code))
 step('no failed callback, no conversion',count('callback failed')==0 and count('stratagem slot CONVERTED')==0,'')
 return results
end
"""
EXTRAS['proof-gas-barrage-mission'] = {'menu': MENU_STUB, 'after': PROOF_GAS_BARRAGE_MISSION,
    'seeds': [('mods/skyeshade/hd2runtime_gas_barrage_mission_proof', 'orbital_gas_barrage_masks')], 'seedFamily': True}
# GasBarragePayloadProof 0.2.2 (carrier revalidation, docs/custom-stratagems.md "Carrier revalidation": the discovered
# carrier validated with the discovery's guards against the current loadout; in the loadout it is invalid and the
# discovery chooses another payload-compatible carrier or none, never it). 0.2.1 (the carrier lifecycle,
# docs/custom-stratagems.md "The carrier presentation lifecycle":
# aboard the ship the carrier is native; its Gas Barrage look and code are applied at mission start through
# runtime/carrier_presentation.lua and restored exactly on the return to the ship; on every snapshot the module, loaded
# at startup from the archive, applies them to the real carrier row (verified native first) and restore_now writes back
# exactly the captured bytes: the whole carrier row and the token row byte-identical, a second restore writes nothing.
# Payload stage C: the 120mm's pattern with the Orbital Gas Strike's shell 197 on the
# carrier's OWN BombardmentComponentData; stage B, 0.1.1, live-proven: the 120mm's pattern and shells on the carrier's OWN
# BombardmentComponentData; docs/custom-stratagems.md, "Payload stage B") on the shipped artifact, the snapshot's real
# StratagemSettings, bombardment component, account catalogue and text registry; late resource lookups disabled, so
# runtime/bombardment_payload.lua must have been loaded at startup from the archive. On every snapshot: the proof loads;
# the record lookup's pins prove; the 380mm's record is found by the game's own lookup, owned by one index slot and its
# row only, exactly vanilla and payload-compatible; the strike (Airburst) is not; the payload-filtered discovery chooses
# a compatible orbital bombardment. Aboard the ship: the proof writes nothing; the payload write is refused
# (NOT_IN_MISSION). On a mission snapshot (seed_payload_mission: a token entry with the snapshot's own non-zero
# cooldown end): before the conversion the write is refused (NOT_CONVERTED); the proof's own path,
# stratagem_selector.convert_with_payload with the proof's definition and the virtual-slot record a selection leaves,
# converts the token entry to the discovered carrier and writes the 120mm's pattern words (3 for the 380mm) then the
# shell list 197, 197, 197 (3) onto its record in ONE tick (7 writes), through the read-only entity pages (opened and
# restored), the carrier never in the record without its payload; the 120mm's and the Gas Strike's records and the Gas
# Strike's chain exactly as reviewed; the restore writes them back and the whole record equals its vanilla bytes; the
# conversion is undone.
PROOF_GAS_BARRAGE_PAYLOAD = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function count(text)local n=0;for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end;return n end
 local world=assert(require('hd2runtime/runtime/event_world').open())
 for _=1,240 do frame()end
 step('the proof loads from the archive with the custom panel; the payload module was loaded at startup',
  count('GasBarragePayloadProof 0.2.2 CARRIER REVALIDATION BUILD')==1
  and package.loaded['hd2runtime/runtime/bombardment_payload']~=nil
  and package.loaded['hd2runtime/runtime/carrier_presentation']~=nil
  and count('text probe: game text registry 17 of 18 tables, 1 spare; language us; id clashes: none -> PASS')==1,'')
 local payload=require('hd2runtime/runtime/bombardment_payload')
 local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
 local loadout=require('hd2runtime/runtime/stratagem_loadout')
 local state=require('hd2runtime/runtime/event_world').game_state(world)
 local mission=state and state.mission
 local r=payload.inspect(world,'Orbital 380mm HE Barrage')
 local donor=payload.inspect(world,'Orbital 120mm HE Barrage')
 local gas=payload.inspect(world,'Orbital Gas Strike')
 step('the 380mm\'s BombardmentComponentData by the game\'s own lookup: one owner, its row only, exactly vanilla, '
  ..'payload-compatible (6 words); the strike is not; the donors vanilla',r~=nil and r.owners==1 and#r.rowsListing==1
  and r.ownRow and r.vanilla and r.compatible and#r.differences==6 and r.size==192 and r.instances and r.instances.of==0
  and r.variant==false and donor and donor.vanilla and gas and gas.vanilla
  and payload.compatible('Orbital Airburst Strike')==false,r and('record %d slot %d'):format(r.record,r.indexRow)or'nil')
 local present={}
 local record=slots.local_record(world)
 for _,entry in ipairs(record and record.entries or{})do
  local id=loadout.id_of(world,entry.type);if id then present[id]=true end
 end
 local saved=loadout.saved(world)
 for _,pair in ipairs(saved and saved.pairs or{})do present[pair.id]=true end
 local found=slots.discover_carriers(world,'Orbital Precision Strike',{present=present,
  exclude={'Orbital 120mm HE Barrage'},payload={donor='Orbital 120mm HE Barrage'}})
 local chosen=found.chosen
 local eligible=0
 for _,c in ipairs(found.candidates)do if c.eligible then eligible=eligible+1 end end
 step('the payload-filtered discovery: a compatible orbital bombardment chosen, every eligible one payload-compatible',
  found.ready and chosen~=nil and chosen.class==1 and chosen.payloadCompatible==true and eligible>=1,
  tostring(chosen and chosen.name))
 -- Revalidation (0.2.2): the cached carrier against the current loadout with the discovery's own guards; put in the
 -- loadout it is invalid (in_loadout) and the discovery never chooses it again.
 local OPTS={exclude={'Orbital 120mm HE Barrage'},payload={donor='Orbital 120mm HE Barrage'}}
 local valid=slots.validate_carrier(world,'Orbital Precision Strike',chosen.name,{present=present,exclude=OPTS.exclude,
  payload=OPTS.payload})
 local with={}
 for id in pairs(present)do with[id]=true end
 with[chosen.id]=true
 local stale=slots.validate_carrier(world,'Orbital Precision Strike',chosen.name,{present=with,exclude=OPTS.exclude,
  payload=OPTS.payload})
 local again=slots.discover_carriers(world,'Orbital Precision Strike',{present=with,exclude=OPTS.exclude,
  payload=OPTS.payload})
 step('revalidation: the chosen carrier is valid against the current loadout; put in the loadout it is invalid '
  ..'(in_loadout) and the discovery chooses another payload-compatible carrier or none, never it',valid.ready and valid.valid
  and stale.ready and not stale.valid and table.concat(stale.codes,',')=='in_loadout'and again.ready
  and(again.chosen==nil or(again.chosen.id~=chosen.id and again.chosen.payloadCompatible==true)),
  chosen.name..' -> '..tostring(again.chosen and again.chosen.name))
 local function settle(handle)for _=1,600 do if handle.status~='pending'then break end;frame()end;return handle end
 -- The carrier lifecycle module on the real rows (the proof's own text and icon handles).
 local CP=require('hd2runtime/runtime/carrier_presentation')
 local texts=require('hd2runtime/runtime/text_resources')
 local images=require('hd2runtime/runtime/image_resources')
 local profile=require('hd2runtime/schemas/current')
 local RES='mods/skyeshade/hd2runtime_gas_barrage_payload_proof'
 local SPEC={carrier=chosen.name,text={name=texts.handle('orbital_gas_barrage_name','ORBITAL GAS BARRAGE',RES),
  nameCased=texts.handle('orbital_gas_barrage_name_cased','Orbital Gas Barrage',RES),
  description=texts.handle('orbital_gas_barrage_description','Calls down a barrage of gas shells.',RES)},
  icon=images.handle('orbital_gas_barrage_masks',RES),code={'up','up','down','down'}}
 local token_type=loadout.type_of(world,3523620028)
 local function row_bytes(kind)
  local row=world.view.pointer(world.game+profile.stratagem.table_rva+kind*8)
  return row and world.runtime.read(row,profile.stratagem.stride)
 end
 local function lifecycle_apply(label)
  local carrier_row,token_row=row_bytes(chosen.type),row_bytes(token_type)
  local w0=counts.writes
  local applied=settle(CP.apply(SPEC))
  local v=applied.verify or{}
  step(label..': the lifecycle module (runtime/carrier_presentation.lua, loaded at startup) on the real carrier row: '
   ..'native first, then the Gas Barrage text, icon and code applied and verified (8 writes with the text table\'s '
   ..'registration); the token row byte-identical',applied.status=='applied'and v.identity and v.text and v.icon
   and v.code and v.others and row_bytes(chosen.type)~=carrier_row and row_bytes(token_type)==token_row
   and counts.writes==w0+8,tostring(applied.code)..' '..tostring(applied.reason)..' writes='..(counts.writes-w0))
  return carrier_row,token_row
 end
 local function lifecycle_restore(label,carrier_row,token_row)
  local w1=counts.writes
  local restored,code,why=CP.restore_now()
  local w2=counts.writes
  local again,again_code=CP.restore_now()
  step(label..': restored in one tick from the captured bytes (7 writes with the text table\'s removal): the whole '
   ..'carrier row and the token row byte-identical; a second restore finds nothing and writes nothing',
   restored~=nil and restored.verify.exact and restored.verify.native and restored.verify.identity
   and row_bytes(chosen.type)==carrier_row and row_bytes(token_type)==token_row and w2==w1+7 and again==nil
   and again_code=='NOT_APPLIED'and counts.writes==w2 and not CP.applied(),tostring(code)..' '..tostring(why)
   ..' writes='..(w2-w1))
 end
 if not mission then
  local writes=counts.writes
  local refused=settle(payload.apply({carrier='Orbital 380mm HE Barrage'}))
  step('aboard the ship: nothing written by the proof (the carrier stays native: no look or code aboard the ship); '
   ..'the payload write refused (NOT_IN_MISSION)',refused.code=='NOT_IN_MISSION'and counts.writes==0 and writes==0
   and count('PAYLOAD: APPLIED: ')==0 and count('[HD2Runtime] carrier presentation APPLIED')==0 and CP.state()==nil,
   tostring(refused.code))
  local carrier_row,token_row=lifecycle_apply('the lifecycle module aboard the ship')
  lifecycle_restore('the lifecycle module aboard the ship',carrier_row,token_row)
  return results
 end
 local writes=counts.writes
 local early=settle(payload.apply({carrier=chosen.name}))
 step('in the mission, before the conversion: refused (NOT_CONVERTED), nothing written',early.code=='NOT_CONVERTED'
  and counts.writes==writes,tostring(early.code))
 -- MISSION START: the carrier's look and code first, then the conversion and the payload.
 local carrier_row,token_row=lifecycle_apply('mission start, before the conversion')
 writes=counts.writes
 local order,slot,entry_address={},nil,nil
 local picks={}
 for _,entry in ipairs(record.entries)do if entry.granted==0 then picks[#picks+1]=entry end end
 for k,entry in ipairs(picks)do
  order[k]=loadout.id_of(world,entry.type)
  if entry.type==token_type and not slot then slot,entry_address=k-1,entry.address end
 end
 local selector=require('hd2runtime/runtime/stratagem_selector')
 selector.set_virtual_slots_for_tests({slots={[slot]={definition='orbital_gas_barrage',token=3523620028,
  type=token_type}},pairs=order})
 local before=world.runtime.read(r.address,192)
 local protections=counts.protection_changes
 -- Every frame: the carrier in the record means its record holds the 120mm pattern.
 local seen,bad=0,0
 local function frame_and_watch()
  frame()
  local now=world.runtime.read(entry_address,4)
  if now and now:byte(1)+now:byte(2)*256==chosen.type then
   seen=seen+1
   if not payload.inspect(world,chosen.name,nil,'Orbital Gas Strike').desired then bad=bad+1 end
  end
 end
 local combined=selector.convert_with_payload('orbital_gas_barrage',nil,chosen.name)
 for _=1,600 do if combined.status~='pending'then break end;frame_and_watch()end
 for _=1,5 do frame_and_watch()end
 local now=payload.inspect(world,chosen.name,nil,'Orbital Gas Strike')
 local donors=payload.donors(world,'Orbital Gas Strike')
 step('the proof\'s path (stage C): the conversion, the 120mm pattern and the Gas Strike shell in ONE tick (1 + 3 + 3 '
  ..'writes) through the read-only entity pages (opened and restored); the carrier never in the record without its '
  ..'payload; shells 197, 197, 197 on the 120mm pattern; the 120mm, the Gas Strike and its chain unchanged',
  combined.status=='applied'and combined.payload and combined.payload.writes==6 and combined.payload.patternWrites==3
  and combined.payload.shellWrites==3 and counts.writes==writes+7 and counts.protection_changes>protections and seen>=1
  and bad==0 and combined.payload.verify.record and combined.payload.verify.shellCount==3 and combined.payload.verify.shells
  and now.desired and table.concat(now.shells,',')=='197,197,197'and now.perSalvo==3 and now.salvos==5
  and donors.pattern and donors.shells and donors.chain,tostring(combined.code)..' '..tostring(combined.reason)
  ..' writes='..(counts.writes-writes)..' seen='..seen..' bad='..bad)
 local mid=counts.writes
 local restored=settle(payload.restore())
 step('the restore: the vanilla words back; the whole record equals its vanilla bytes',restored.status=='restored'
  and restored.exact and world.runtime.read(r.address,192)==before and counts.writes==mid+6,tostring(restored.code))
 local back=settle(slots.restore())
 step('the conversion undone; no failed callback',back.status=='restored'and count('callback failed')==0,'')
 lifecycle_restore('the return to the ship',carrier_row,token_row)
 return results
end
"""
# On the default (ship) snapshot the proof writes nothing and the payload is refused; the lifecycle module's round trip
# writes 15 (8 + 7). Run with --snapshot on a mission snapshot: the look and code (8), the conversion and payload (7),
# the payload restore (6), the conversion undone (1) and the look and code restored (7): 29 overlay writes.
EXTRAS['proof-gas-barrage-payload'] = {'menu': MENU_STUB, 'after': PROOF_GAS_BARRAGE_PAYLOAD,
    'seeds': [('mods/skyeshade/hd2runtime_gas_barrage_payload_proof', 'orbital_gas_barrage_masks')], 'seedFamily': True,
    'seedPayload': True}
# GasBarrageCooldownProof 0.1.0, the fixed 60 s cooldown (runtime/slot_cooldown.lua; docs/custom-stratagems.md, "The
# fixed cooldown"), a companion of GasBarragePayloadProof, on the shipped artifact and the snapshot's real game.dll,
# StratagemSettings, mission record, HUD and clock; late resource lookups disabled, so runtime/slot_cooldown.lua must
# have been loaded at startup from the archive. On every snapshot: the proof loads, the module's pins prove on the real
# code, the clock reads; aboard the ship the proof logs the payload-compatible carriers' own cooldowns from their real
# rows (240 s each, cooldown type 0) and writes nothing. On a mission snapshot (seed_payload_mission): the HUD draws
# every record entry in its own slot; the proof is armed; the payload proof's own path (the definition, the
# virtual-slot record a selection leaves, stratagem_selector.convert_with_payload) converts the token entry; then the
# game's call is SIMULATED in the overlay (validation scaffolding: the entry's activation, arrival 6 s later and its end
# the row's cooldown x 0.855 after the arrival, 3 writes) and the next frame the module writes the end 60 s after the
# arrival (1 guarded write), nothing else of the record changing; the carrier's row is byte-identical; the payload and
# the conversion are undone.
PROOF_GAS_BARRAGE_COOLDOWN = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function count(text)local n=0;for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end;return n end
 local world=assert(require('hd2runtime/runtime/event_world').open())
 for _=1,240 do frame()end
 local cool=require('hd2runtime/runtime/slot_cooldown')
 local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
 local loadout=require('hd2runtime/runtime/stratagem_loadout')
 local profile=require('hd2runtime/schemas/current')
 local proven,why=cool.prove(world)
 local clock=cool.clock(world)
 step('the proof loads from the archive; runtime/slot_cooldown.lua was loaded at startup; its pins prove on the real '
  ..'game.dll; the clock reads',count('GasBarrageCooldownProof 0.1.0 FIXED COOLDOWN BUILD')==1
  and package.loaded['hd2runtime/runtime/slot_cooldown']~=nil and proven==true and type(clock)=='number'and clock>0,
  tostring(why)..' clock='..tostring(clock))
 local state=require('hd2runtime/runtime/event_world').game_state(world)
 if not(state and state.mission)then
  step('aboard the ship: the compatible carriers\' own cooldowns from their real rows (240 s, cooldown type 0); '
   ..'nothing written; not armed',count('COOLDOWN: carrier native cooldowns before any conversion (the payload-compatible '
   ..'carriers\' own rows, read-only): Orbital 380mm HE Barrage 240.00 s (cooldown type 0); Orbital Napalm Barrage '
   ..'240.00 s (cooldown type 0); Orbital Walking Barrage 240.00 s (cooldown type 0)')==1 and counts.writes==0
   and not cool.armed(),'')
  return results
 end
 local record=slots.local_record(world)
 local drawn=record~=nil
 local seeded=loadout.type_of(world,3523620028)
 for _,entry in ipairs(record and record.entries or{})do
  -- The seed made one entry the token (its type only): the snapshot's HUD still draws that slot's own type.
  local h=cool.hud(world,entry.index)
  if not(h and(h.type==entry.type or entry.type==seeded))then drawn=false end
 end
 step('in the mission: the HUD draws every record entry in its own slot (slot and bar index; the type, but for the '
  ..'seeded token entry); the proof is armed',drawn
  and cool.armed()and count('MISSION START: the fixed cooldown is armed: 60.0 s from the call-in\'s arrival')==1,'')
 -- The payload proof's definition and path (validation: that proof is not loaded in this scenario).
 local virtual=require('hd2runtime/runtime/virtual_stratagems')
 local texts=require('hd2runtime/runtime/text_resources')
 local images=require('hd2runtime/runtime/image_resources')
 local RES='mods/skyeshade/hd2runtime_gas_barrage_payload_proof'
 local CASED=texts.handle('orbital_gas_barrage_name_cased','Orbital Gas Barrage',RES)
 virtual.define({id='orbital_gas_barrage',display={name=CASED,description=CASED,icon=images.handle(
  'orbital_gas_barrage_masks',RES)},selection={token='Orbital Precision Strike'},mission={discover=true,
  exclude={'Orbital 120mm HE Barrage'}},payload={donor='Orbital 120mm HE Barrage',shells='Orbital Gas Strike'}},RES)
 local token_type=loadout.type_of(world,3523620028)
 local order,slot,entry={},nil,nil
 local picks={}
 for _,e in ipairs(record.entries)do if e.granted==0 then picks[#picks+1]=e end end
 for k,e in ipairs(picks)do
  order[k]=loadout.id_of(world,e.type)
  if e.type==token_type and not slot then slot,entry=k-1,e end
 end
 local selector=require('hd2runtime/runtime/stratagem_selector')
 selector.set_virtual_slots_for_tests({slots={[slot]={definition='orbital_gas_barrage',token=3523620028,type=token_type}},
  pairs=order})
 local present={}
 for _,e in ipairs(record.entries)do local id=loadout.id_of(world,e.type);if id then present[id]=true end end
 local found=slots.discover_carriers(world,'Orbital Precision Strike',{present=present,
  exclude={'Orbital 120mm HE Barrage'},payload={donor='Orbital 120mm HE Barrage'}})
 local carrier=found.chosen
 local function row_bytes(kind)
  local row=world.view.pointer(world.game+profile.stratagem.table_rva+kind*8)
  return row and world.runtime.read(row,profile.stratagem.stride)
 end
 local carrier_row=row_bytes(carrier.type)
 local combined=selector.convert_with_payload('orbital_gas_barrage',nil,carrier.name)
 for _=1,600 do if combined.status~='pending'then break end;frame()end
 for _=1,5 do frame()end
 step('the conversion and the payload (the payload proof\'s path); the cooldown watch sees the conversion',
  combined.status=='applied'and count('COOLDOWN: the Gas Barrage conversion is seen: loadout slot '..slot..' = record '
  ..'entry '..entry.index..' -> the carrier '..carrier.name)==1 and count('COOLDOWN: carrier native = 240.00 s (its row, '
  ..'never written; cooldown type 0')==1,tostring(combined.code)..' '..tostring(combined.reason))
 -- The game's call, simulated in the overlay (validation scaffolding, 3 writes): activated 0.3 s ago, arriving 6 s
 -- later, its end the row's 240 s x 0.855 after the arrival.
 local function u64(n)return string.char(n%256,math.floor(n/256)%256,math.floor(n/65536)%256,math.floor(n/16777216)%256,
  math.floor(n/4294967296)%256,math.floor(n/1099511627776)%256,0,0)end
 local now=cool.clock(world)
 local activation=now-300000
 local arrival=activation+6000000
 local before=slots.local_record(world)
 local w0=counts.writes
 world.runtime.write(entry.address+0x10,u64(activation))
 world.runtime.write(entry.address+0x20,u64(arrival))
 world.runtime.write(entry.address+0x18,u64(arrival+205200000))
 frame();frame()
 local after=slots.local_record(world)
 local raw=after.entries[entry.index+1].bytes
 local finish=0
 for i=8,1,-1 do finish=finish*256+raw:byte(0x18+i)end
 local others=after.count==before.count
 for k,e in ipairs(before.entries)do
  local b2=after.entries[k].bytes
  if k-1==entry.index then
   others=others and b2:sub(1,0x10)==e.bytes:sub(1,0x10)and b2:sub(0x29)==e.bytes:sub(0x29)
  else others=others and b2==e.bytes end
 end
 step('the simulated call: the module writes the end 60 s after the arrival in the next frame (1 guarded write), '
  ..'nothing else of the record changed, the carrier\'s row byte-identical (its own cooldown never written)',finish==arrival+60000000 and counts.writes==w0+4 and others and row_bytes(carrier.type)==carrier_row
  and count('COOLDOWN: Gas Barrage override = 60.0 s from the call-in\'s arrival')==1
  and count('COOLDOWN: verified end = current_game_time + ')==1 and count('callback failed')==0,
  'end='..finish..' expected='..(arrival+60000000)..' writes='..(counts.writes-w0))
 local restored=require('hd2runtime/runtime/bombardment_payload').restore
 local function settle(handle)for _=1,600 do if handle.status~='pending'then break end;frame()end;return handle end
 local back=settle(restored())
 local undone=settle(slots.restore())
 step('the payload and the conversion undone',back.status=='restored'and back.exact and undone.status=='restored','')
 return results
end
"""
# On the default (ship) snapshot nothing is written (readOnly: the proof only reads aboard the ship). Run with
# --snapshot on a mission snapshot: the conversion and payload (7), the simulated call (3), the override (1), the payload
# restore (6) and the conversion undone (1).
EXTRAS['proof-gas-barrage-cooldown'] = {'menu': MENU_STUB, 'after': PROOF_GAS_BARRAGE_COOLDOWN, 'seedPayload': True,
    'readOnly': True}
# BeaconProbe 0.1.0 (read-only; docs/research/beacon-redirect-F5FEE03DCFDB.md) on the shipped artifact and the snapshot's
# real game.dll and memory: the probe loads, its 27 pins prove on the real code, the beacon manager path
# ([game+0x346BF98] + 0x40 + 0x1380) reads a plausible manager (the snapshots hold no beacon: none is reported created),
# and in a mission it reports every player's record. Read-only: no overlay write.
PROOF_BEACON_PROBE = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function count(text)local n=0;for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end;return n end
 for _=1,60 do frame()end
 local world=assert(require('hd2runtime/runtime/event_world').open())
 local state=require('hd2runtime/runtime/event_world').game_state(world)
 step('the probe loads from the archive, its pins prove on the real game.dll, the beacon manager reads plausibly '
  ..'(no beacon in the snapshot), nothing is written',count('BeaconProbe 0.1.0 READ-ONLY BEACON PROBE')==1
  and count('pins: the beacon manager path and its readers are the researched code (27 pins)')==1
  and count('REFUSED')==0 and count('beacon manager: ')==0 and count('BEACON CREATED:')==0 and counts.writes==0,
  table.concat(lines,' | '):sub(-400))
 if state and state.mission then
  step('in a mission: every player\'s record is reported',count('MISSION START (frame')==1 and count(' record(s) (* granted): ')
   ==1,'')
 end
 return results
end
"""
EXTRAS['proof-beacon-probe'] = {'after': PROOF_BEACON_PROBE, 'readOnly': True}
# BeaconRedirectProof 0.3.0, the per-beacon redirect (runtime/beacon_redirect.lua; docs/research/beacon-redirect-
# F5FEE03DCFDB.md) on the shipped artifact and the snapshot's real game.dll and memory; late resource lookups disabled,
# so runtime/beacon_redirect.lua must have been loaded at startup from the archive. On every snapshot: the proof loads,
# the module's pins prove on the real code, the beacon manager reads. Aboard the ship nothing is armed or written. On a
# mission snapshot: the proof arms (AC-8 Autocannon type 25 -> the 120mm's 136; the 120mm's package requested through
# the simulated loader); then an AC-8 beacon is SIMULATED in the real manager's own heap arrays (validation scaffolding:
# its element with the AC-8's timers, its countdown already started (+0x3C), its entity handle, state and the counts,
# written in the overlay) and in the next update the module writes that beacon's type 25 -> 136 (ONE guarded write, on
# the real heap pages, protection restored), nothing else of the element changing; the simulated activation (the
# dispatcher's record in the real state block) is reported with the 120mm's type, the call-in timing and the dispatch;
# no StratagemInfo row changes. Then the timing proof's transaction on the real heap: a second simulated AC-8 beacon
# (countdown = threshold = 8.715, as live) gets its type 25 -> 136 AND its countdown and threshold (26.196 / 22.196) in
# ONE guarded transaction, called directly (the proof's default mode writes the type only); read back, the other
# members unchanged, protection restored; a beacon whose timers changed since they were observed is refused.
PROOF_BEACON_REDIRECT = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function count(text)local n=0;for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end;return n end
 for _=1,240 do frame()end
 local world=assert(require('hd2runtime/runtime/event_world').open())
 local BR=require('hd2runtime/runtime/beacon_redirect')
 local proven,why=BR.prove(world)
 local m,mwhy=BR.manager(world)
 step('the proof loads from the archive; runtime/beacon_redirect.lua was loaded at startup; its pins prove on the real '
  ..'game.dll; the beacon manager reads',count('BeaconRedirectProof 0.3.0 BEACON TIMING BUILD')==1
  and package.loaded['hd2runtime/runtime/beacon_redirect']~=nil and proven==true and m~=nil,
  tostring(why)..' '..tostring(mwhy))
 local state=require('hd2runtime/runtime/event_world').game_state(world)
 if not(state and state.mission)then
  step('aboard the ship: nothing armed, nothing written',not BR.armed()and counts.writes==0
   and count('BEACON REDIRECT ARMED')==0,'')
  return results
 end
 for _=1,600 do if count('BEACON REDIRECT READY:')>0 then break end;frame()end
 step('in the mission: armed (AC-8 Autocannon type 25 -> Orbital 120mm HE Barrage type 136; the rows\' call-in members '
  ..'read) and the 120mm\'s call-in package resident',BR.armed()and count('BEACON REDIRECT ARMED: carrier AC-8 Autocannon '
  ..'(type 25), target Orbital 120mm HE Barrage (type 136)')==1 and count('mode TYPE ONLY. Rows (read-only): AC-8 '
  ..'Autocannon call-in 3.000 s, linger 4.000 s; Orbital 120mm HE Barrage call-in 5.000 s, linger 0.000 s')==1
  and count('BEACON REDIRECT READY:')==1,'')
 local profile=require('hd2runtime/schemas/current')
 local function row(kind)return world.runtime.read(world.view.pointer(world.game+profile.stratagem.table_rva+kind*8),400)end
 local row25,row136=row(25),row(136)
 -- The simulated beacon (scaffolding), in the real manager's own heap arrays.
 local function u32(n)return string.char(n%256,math.floor(n/256)%256,math.floor(n/65536)%256,math.floor(n/16777216)%256)end
 local function u64(n)return u32(n%4294967296)..u32(math.floor(n/4294967296))end
 local b=require('hd2runtime/core/bytes')
 local DR=require('hd2runtime/domains/beacon_redirect').dispatch
 local w0=counts.writes
 local element,stateblock=m.elements,m.state
 local fake_handle=stateblock+0x100
 -- The overlay keys writes by their start address and composes overlapping ones in no fixed order: the scaffold writes
 -- each element member at exactly the address the Runtime writes it (+0x0, +0x4, +0x8, +0xC).
 local function head(countdown,threshold,kind)
  world.runtime.write(element,b.encode(countdown,'f32'))
  world.runtime.write(element+4,b.encode(threshold,'f32'))
  world.runtime.write(element+8,u32(0))
  world.runtime.write(element+0xC,u32(kind))
 end
 world.runtime.write(fake_handle+8,u32(424242))
 world.runtime.write(m.entities,u64(fake_handle))
 head(11.717,8.717,25)
 world.runtime.write(element+0x2C,u32(0))                               -- the init's waves (0x6AEB7A)
 world.runtime.write(element+0x3C,string.char(1))                       -- its countdown has started
 world.runtime.write(stateblock+0x8E0,u32(1))   -- mode 1: a normal owned beacon (live)
 world.runtime.write(stateblock+0x8E4,string.char(0))  -- separate: the overlay composes overlapping writes in no order
 world.runtime.write(m.address+0x34,u32(1)..u32(1))
 local scaffold=counts.writes-w0
 local before=world.runtime.read(element,0x40)
 frame();frame()
 local after=world.runtime.read(element,0x40)
 local only_type=true
 for i=1,0x40 do if after:byte(i)~=before:byte(i)and not(i>0xC and i<=0x10)then only_type=false end end
 step('the simulated AC-8 beacon (its countdown started, not crossed): type 25 -> 136 in the update it was first seen (1 '
  ..'guarded write on the real heap page, protection restored), nothing else of the element changed',b.u32(after,0xC)==136
  and only_type and counts.writes==w0+scaffold+1 and count('BEACON REDIRECT CREATED: AC-8 Autocannon, entity = 424242, '
  ..'original type = 25, target type = 136')==1 and count('BEACON REDIRECT APPLIED: entity = 424242, type 25 -> 136, '
  ..'verified = true')==1,'type='..b.u32(after,0xC)..' writes='..(counts.writes-w0-scaffold))
 -- The game's activation as the dispatcher leaves it (scaffolding): its record in the real state block.
 world.runtime.write(element,b.encode(8.70,'f32'))
 world.runtime.write(stateblock+DR.payload,u32(0x1ED411B1)..u32(0x2D3BD00B)..string.char(1))
 world.runtime.write(stateblock+DR.type,u32(136))
 world.runtime.write(stateblock+DR.spawn,u32(DR.spawnRequested))
 world.runtime.write(element+DR.elementWaves,u32(1))
 world.runtime.write(stateblock+0x8E4,string.char(1))
 frame();frame()
 step('the simulated activation is reported with the 120mm\'s type, the AC-8\'s call-in timing and the dispatcher\'s '
  ..'record; no StratagemInfo row changed',count('BEACON REDIRECT ACTIVATED: entity = 424242, activation type = Orbital '
  ..'120mm HE Barrage (136), original type = AC-8 Autocannon, redirected = true')==1 and count('CALL-IN TIMING: AC-8 '
  ..'Autocannon redirected to Orbital 120mm HE Barrage (136), beacon 424242: countdown 11.717 s, threshold 8.717 s as '
  ..'first seen')==1 and count('BEACON REDIRECT DISPATCH: entity = 424242, the dispatcher\'s own record: type '
  ..'Orbital 120mm HE Barrage (136), payload 0x2D3BD00B1ED411B1')==1 and count('spawn requested = yes (state +0x8D8 = 10)')==1
  and row(25)==row25 and row(136)==row136 and count('callback failed')==0,'')
 -- The timing proof's transaction on the real heap: the first beacon gone, a second AC-8 beacon in the same slot.
 world.runtime.write(m.address+0x34,u32(0)..u32(0))
 frame();frame()
 world.runtime.write(fake_handle+8,u32(424243))
 head(8.715,8.715,25)
 world.runtime.write(element+0x2C,u32(0))
 world.runtime.write(stateblock+0x8E4,string.char(0))
 world.runtime.write(m.address+0x34,u32(1)..u32(1))
 local seen=world.runtime.read(element,0x40)
 local w1=counts.writes
 local wrong=BR.redirect_now(world,{carrierType=25,targetType=136,resident=true,timing={countdown=26.196,threshold=22.196}},
  424243,b.encode(8.0,'f32')..b.encode(8.715,'f32'))
 local refused_ok=wrong==nil and counts.writes==w1 and world.runtime.read(element,0x40)==seen
 BR.reset_for_tests()
 local result,code,why=BR.redirect_now(world,{carrierType=25,targetType=136,resident=true,timing={countdown=26.196,threshold=22.196}},
  424243,seen:sub(1,8))
 local timed=world.runtime.read(element,0x40)
 local rest=true
 for i=1,0x40 do if timed:byte(i)~=seen:byte(i)and not(i<=8 or(i>0xC and i<=0x10))then rest=false end end
 local v=result and result.verify or{}
 step('the timing proof\'s transaction on the real heap: type 25 -> 136 with countdown 8.715 -> 26.196 and threshold 8.715 '
  ..'-> 22.196 in one guarded transaction (read back, the other members unchanged, protection restored); timers that '
  ..'changed since they were observed are refused with nothing written',refused_ok and result~=nil and v.type and v.countdown
  and v.threshold and v.others and v.nonTarget and v.protection and rest and b.u32(timed,0xC)==136
  and math.abs(b.value(timed,0,'f32')-26.196)<1e-4 and math.abs(b.value(timed,4,'f32')-22.196)<1e-4
  and row(25)==row25 and row(136)==row136,'writes='..(counts.writes-w1)..' refused first '..tostring(refused_ok)..' '..tostring(code)..' '..tostring(why)..' seen type '..b.u32(seen,0xC)..' count '..tostring(world.runtime.read(m.address+0x34,8)and b.u32(world.runtime.read(m.address+0x34,8),0)))
 return results
end
"""
# On the default (ship) snapshot nothing is armed or written. Run with --snapshot on a mission snapshot: the simulated
# beacon (10 overlay writes) and the redirect (1 guarded write), the simulated activation (6), the second beacon (9) and
# the timing transaction.
EXTRAS['proof-beacon-redirect'] = {'menu': MENU_STUB, 'after': PROOF_BEACON_REDIRECT, 'readOnly': True}
# BeaconTimingProof 0.1.0, the development beacon API (runtime/beacons.lua; docs/research/beacon-redirect-F5FEE03DCFDB.md,
# "The beacon API") on the shipped artifact and the snapshot's real game.dll and memory; late resource lookups
# disabled, so runtime/beacons.lua must have been loaded at startup from the archive. Aboard the ship nothing is armed
# or written. On a mission snapshot (default mode): an AC-8 beacon is SIMULATED in the real manager's own heap arrays
# (scaffolding, each member at the address the Runtime writes it); in the next update the API sets its call-in to 6 s
# (1 guarded write: its countdown, on the real heap page); 2 s later its lifetime after activation to 15 s keeping the
# remaining call-in (2 writes: countdown and threshold); after a simulated activation one more change is refused
# (ACTIVATED) with nothing written; no StratagemInfo row changes.
PROOF_BEACON_TIMING = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function count(text)local n=0;for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end;return n end
 for _=1,240 do frame()end
 local world=assert(require('hd2runtime/runtime/event_world').open())
 local BR=require('hd2runtime/runtime/beacon_redirect')
 local m=BR.manager(world)
 step('the proof loads from the archive; runtime/beacons.lua was loaded at startup; the beacon manager reads',
  count('BeaconTimingProof 0.1.0 BEACON TIMING API BUILD')==1 and package.loaded['hd2runtime/runtime/beacons']~=nil
  and m~=nil,'')
 local state=require('hd2runtime/runtime/event_world').game_state(world)
 if not(state and state.mission)then
  step('aboard the ship: nothing armed, nothing written',counts.writes==0 and count('MISSION START')==0,'')
  return results
 end
 for _=1,600 do if count('BEACON TIMING READY:')>0 then break end;frame()end
 step('in the mission: armed (default mode: call-in 6 s, then lifetime 15 s)',count('mode TIMING (call-in 6')==1
  and count('BEACON TIMING READY:')==1,'')
 local profile=require('hd2runtime/schemas/current')
 local function row(kind)return world.runtime.read(world.view.pointer(world.game+profile.stratagem.table_rva+kind*8),400)end
 local row25=row(25)
 local function u32(n)return string.char(n%256,math.floor(n/256)%256,math.floor(n/65536)%256,math.floor(n/16777216)%256)end
 local function u64(n)return u32(n%4294967296)..u32(math.floor(n/4294967296))end
 local b=require('hd2runtime/core/bytes')
 local element,stateblock=m.elements,m.state
 local fake_handle=stateblock+0x100
 world.runtime.write(fake_handle+8,u32(434343))
 world.runtime.write(m.entities,u64(fake_handle))
 world.runtime.write(element,b.encode(11.717,'f32'))
 world.runtime.write(element+4,b.encode(8.717,'f32'))
 world.runtime.write(element+8,u32(0))
 world.runtime.write(element+0xC,u32(25))
 world.runtime.write(element+0x2C,u32(0))
 world.runtime.write(element+0x3C,string.char(1))
 world.runtime.write(stateblock+0x8E0,u32(1))   -- mode 1: a normal owned beacon (live)
 world.runtime.write(stateblock+0x8E4,string.char(0))  -- separate: the overlay composes overlapping writes in no order
 world.runtime.write(m.address+0x34,u32(1)..u32(1))
 local w0=counts.writes
 local before=world.runtime.read(element,0x40)
 frame();frame()
 local after=world.runtime.read(element,0x40)
 local rest=true
 for i=5,0x40 do if after:byte(i)~=before:byte(i)then rest=false end end
 step('the simulated AC-8 beacon: call-in 3 -> 6 s in its first update (1 guarded write on the real heap page: the '
  ..'countdown 11.717 -> 14.717), nothing else of the element changed',math.abs(b.value(after,0,'f32')-14.717)<1e-3
  and rest and counts.writes==w0+1 and count('BEACON TIMING APPLIED (first update): entity 434343')==1
  and count('verified true')>=1,'writes='..(counts.writes-w0))
 for _=1,2000 do if count('BEACON TIMING APPLIED (2.')+count('BEACON TIMING LATER')>0 then break end;frame()end
 local later=world.runtime.read(element,0x40)
 step('2 s later, before its activation: the lifetime after activation 8.717 -> 15 s, the remaining call-in kept (2 '
  ..'guarded writes: countdown and threshold)',count('BEACON TIMING APPLIED (2.')==1 and math.abs(b.value(later,4,'f32')-15)<1e-3
  and b.value(later,0,'f32')-b.value(later,4,'f32')>5 and counts.writes==w0+3,'writes='..(counts.writes-w0))
 world.runtime.write(stateblock+0x8E4,string.char(1))
 local w1=counts.writes
 frame();frame()
 step('after the simulated activation one more change is refused (ACTIVATED), nothing written; no StratagemInfo row '
  ..'changed',count('BEACON TIMING GUARD: a change after the activation: refused ACTIVATED')==1 and counts.writes==w1
  and row(25)==row25 and count('callback failed')==0,'')
 return results
end
"""
EXTRAS['proof-beacon-timing'] = {'menu': MENU_STUB, 'after': PROOF_BEACON_TIMING, 'readOnly': True}
# GasShellProof 0.1.0, the Runtime bombardment executor (runtime/bombardment_executor.lua, runtime/beacons.lua) on the
# shipped artifact and the snapshot's real game.dll and memory; late resource lookups disabled, so both modules must
# have been loaded at startup from the archive. Aboard the ship nothing is armed, fired or written. On a mission
# snapshot: the Gas Strike's call-in package is requested through the simulated loader ("READY"); an AC-8 beacon is
# SIMULATED in the real manager's own heap arrays (scaffolding) and its delivery becomes 'none' in the next update (1
# guarded write on the real heap page); its simulated activation (position scaffolding in the real state block) starts
# the executor, which proves FireProjectile's real prologue, shell 197's real row against its reviewed row, the real
# 120mm record against its vanilla bytes and the real local avatar, then fires 15 shells 197 through the game's
# projectile wrapper (a recording stub installed as scaffolding: the overlay adapter cannot call game functions) in the
# 120mm's pattern, 3000 m above aims within +-27 m of the beacon, straight down, from the real avatar.
PROOF_GAS_SHELLS = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function count(text)local n=0;for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end;return n end
 for _=1,240 do frame()end
 local world=assert(require('hd2runtime/runtime/event_world').open())
 local BR=require('hd2runtime/runtime/beacon_redirect')
 local m=BR.manager(world)
 step('the proof loads from the archive; runtime/bombardment_executor.lua and runtime/beacons.lua were loaded at '
  ..'startup; the beacon manager reads',count('GasShellProof 0.1.0 RUNTIME GAS SHELLS BUILD')==1
  and package.loaded['hd2runtime/runtime/bombardment_executor']~=nil and package.loaded['hd2runtime/runtime/beacons']~=nil
  and m~=nil,'')
 local state=require('hd2runtime/runtime/event_world').game_state(world)
 if not(state and state.mission)then
  step('aboard the ship: nothing armed, fired or written',counts.writes==0 and count('MISSION START')==0,'')
  return results
 end
 for _=1,600 do if count('GAS SHELLS READY:')>0 then break end;frame()end
 step('in the mission: armed, the Gas Strike\'s call-in package resident',count('GAS SHELLS READY:')==1,'')
 -- The projectile wrapper, recorded (scaffolding: the overlay adapter cannot call game functions).
 local fired={}
 world.runtime.native_projectile=function(entry,system,kind,x,y,z,dx,dy,dz,entity)
  fired[#fired+1]={entry=entry,type=kind,x=x,y=y,z=z,dx=dx,dy=dy,dz=dz,entity=entity}
  return true
 end
 local function u32(n)return string.char(n%256,math.floor(n/256)%256,math.floor(n/65536)%256,math.floor(n/16777216)%256)end
 local function u64(n)return u32(n%4294967296)..u32(math.floor(n/4294967296))end
 local b=require('hd2runtime/core/bytes')
 local element,stateblock=m.elements,m.state
 local fake_handle=stateblock+0x100
 world.runtime.write(fake_handle+8,u32(454545))
 world.runtime.write(m.entities,u64(fake_handle))
 world.runtime.write(element,b.encode(11.717,'f32'))
 world.runtime.write(element+4,b.encode(8.717,'f32'))
 world.runtime.write(element+8,u32(0))
 world.runtime.write(element+0xC,u32(25))
 world.runtime.write(element+0x2C,u32(0))
 world.runtime.write(element+0x3C,string.char(1))
 world.runtime.write(stateblock+0x8E0,u32(1))   -- mode 1: a normal owned beacon (live)
 world.runtime.write(stateblock+0x8E4,string.char(0))  -- separate: the overlay composes overlapping writes in no order
 world.runtime.write(m.address+0x34,u32(1)..u32(1))
 local w0=counts.writes
 frame();frame()
 step('the simulated AC-8 beacon: delivery 25 -> none in its first update (1 guarded write on the real heap page)',
  count('GAS SHELLS BEACON NEUTRALIZED: entity 454545, delivery AC-8 Autocannon -> none, verified true, 1 write')==1
  and counts.writes==w0+1 and b.u32(world.runtime.read(element+0xC,4),0)==0,'writes='..(counts.writes-w0))
 -- Its activation (scaffolding): the position in the real state block, the countdown crossed, "activated".
 world.runtime.write(stateblock+0x30,b.encode(100,'f32')..b.encode(-50,'f32')..b.encode(12,'f32'))
 world.runtime.write(element,b.encode(8.7,'f32'))
 world.runtime.write(stateblock+0x8E4,string.char(1))
 for _=1,4000 do if count('GAS SHELLS RESULT for beacon')>0 then break end;frame()end
 local avatar=require('hd2runtime/runtime/handles').local_avatar(world)
 local ok=#fired==15
 for _,f in ipairs(fired)do
  if not(f.type==197 and f.entry==world.game+require('hd2runtime/domains/event_natives').projectile.rva
    and math.abs(f.x-100)<=27 and math.abs(f.y+50)<=27 and math.abs(f.z-3012)<1e-3 and f.dz==-1
    and avatar and f.entity==avatar.id)then ok=false end
 end
 step('the activation starts the executor on the real game data (FireProjectile\'s prologue, shell 197\'s reviewed row, '
  ..'the 120mm\'s vanilla record, the real avatar): 15 shells 197 through the projectile wrapper, 3000 m above aims '
  ..'within +-27 m of the beacon, straight down, in 5 salvos',ok and count('GAS SHELLS STARTED for beacon 454545')==1
  and count('GAS SHELL 15 (salvo 5)')==1 and count('ended: 15 shells in 5 salvos')==1 and count('callback failed')==0,
  'fired='..#fired)
 return results
end
"""
EXTRAS['proof-gas-shells'] = {'menu': MENU_STUB, 'after': PROOF_GAS_SHELLS, 'readOnly': True}
# PodProbe 0.1.0 (read-only) on the shipped artifact and the snapshot's real game.dll and memory: the probe loads, its 15
# pins (the TransportComponent manager, its layout, the content written at creation and read at the spawn, the landing
# timer, a beacon handle's network id) prove on the real code, and in a mission it reads the real Transport manager.
# Nothing is written.
PROOF_POD_PROBE = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function count(text)local n=0;for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end;return n end
 for _=1,120 do frame()end
 step('the probe loads from the archive; nothing is written',count('PodProbe 0.1.0 READ-ONLY HELLPOD PROBE')==1
  and counts.writes==0 and count('REFUSED')==0,'')
 local world=assert(require('hd2runtime/runtime/event_world').open())
 local state=require('hd2runtime/runtime/event_world').game_state(world)
 if state and state.mission then
  local mgr=world.view.pointer(world.game+0x3326518)
  step('in a mission: its 15 pins prove on the real game.dll and the real Transport manager reads (no pod in the '
   ..'snapshot)',count('pins: the Transport component and its readers are the researched code (15 pins)')==1
   and mgr~=nil and world.view.u32(mgr+0x10)~=nil and count('POD CREATED:')==0,'')
 end
 return results
end
"""
EXTRAS['proof-pod-probe'] = {'after': PROOF_POD_PROBE, 'readOnly': True}
# PelicanProbe 0.1.0 (runtime/pelicans.lua, runtime/carrier_allocator.lua; docs/research/pelican-cas-F5FEE03DCFDB.md) on
# the shipped artifact and the snapshot's real game.dll and memory, late resource lookups disabled (both modules must
# have been loaded at startup from the archive). Aboard the ship: the read-only carrier allocation is logged (or waits
# for the account catalogue). In a mission: the Pelican pins prove on the real code, the hold watch runs, the real
# Transport component reads (no Pelican in a snapshot), and the real transform component finds the local avatar's
# position through its entity map (the readers a Pelican uses). Nothing is written.
PROOF_PELICAN_PROBE = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function count(text)local n=0;for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end;return n end
 for _=1,200 do frame()end
 step('the probe loads from the archive; runtime/pelicans.lua and runtime/carrier_allocator.lua were loaded at startup; '
  ..'nothing is written',count('PelicanProbe 0.1.0 PELICAN PROBE + HOLD')==1
  and package.loaded['hd2runtime/runtime/pelicans']~=nil and package.loaded['hd2runtime/runtime/carrier_allocator']~=nil
  and counts.writes==0 and count('REFUSED:')==0 and count('callback failed')==0,'')
 local world=assert(require('hd2runtime/runtime/event_world').open())
 local state=require('hd2runtime/runtime/event_world').game_state(world)
 local pelicans=require('hd2runtime/runtime/pelicans')
 if not(state and state.mission)then
  step('aboard the ship: the read-only carrier allocation is logged, or waits for the account catalogue',
   count('CUSTOM CARRIER: Gas Barrage = ')+count('CUSTOM CARRIER: waiting: ')>=1 and counts.writes==0,'')
  return results
 end
 local list=pelicans.list(world)
 local n=0;for _ in pairs(list or{})do n=n+1 end
 local avatar=require('hd2runtime/runtime/handles').local_avatar(world)
 local at=avatar and pelicans.position(world,avatar.id)
 step('in a mission: the Pelican pins prove on the real game.dll, the hold watch runs, the real Transport component '
  ..'reads (no Pelican in the snapshot) and the real transform component finds the local avatar\'s position',
  count('pins: the Transport, Behavior and transform components and the flight\'s stage machine are the researched code')==1
  and count('PELICAN WATCH: running; hold 60 s after each release')==1 and list~=nil and n==0
  and at~=nil and pelicans.clock(world)~=nil and count('PELICAN SEEN:')==0 and counts.writes==0,
  'pelicans='..n..' avatar='..tostring(avatar and avatar.id)..' at='..tostring(at and(at.x..','..at.y..','..at.z)))
 return results
end
"""
EXTRAS['proof-pelican-probe'] = {'after': PROOF_PELICAN_PROBE, 'readOnly': True}
# PelicanSpawnProof 0.2.0 (hd2.pelican: api/pelican.lua -> runtime/pelicans.lua M.spawn, anchored: a Runtime-owned copy
# of the default spawn context with the hover anchor at +0x610) on the shipped artifact and the snapshot's real game.dll
# and memory. Aboard the ship a request is refused NOT_IN_MISSION and nothing is called. On a
# mission snapshot every guard runs against the real game: the spawn pins and the request's exact bytes, the world's
# real default spawn context (all zero), the Pelican's entity in the real settings table, base_faction resident, the
# real local avatar (the default facing); base_faction's residency is scaffolded (the simulated loader knows only the
# packages the Runtime requested; the research reads it resident in this snapshot's real package list). The game's
# spawn request is replaced by a recording stub (scaffolding: the
# overlay adapter cannot call game functions): it is called exactly once, with the request's real entry and the
# position; no Pelican appears in the real Transport component, so the Runtime reports the spawn UNVERIFIED (exists
# false) and writes nothing.
PROOF_PELICAN_SPAWN = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function count(text)local n=0;for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end;return n end
 for _=1,120 do frame()end
 step('the proof loads from the archive; api/pelican.lua and runtime/pelicans.lua were loaded at startup; nothing is '
  ..'written',count('PelicanSpawnProof 0.2.0 HOVER-ANCHOR + MULTIPLAYER BUILD')==1
  and package.loaded['hd2runtime/api/pelican']~=nil and package.loaded['hd2runtime/runtime/pelicans']~=nil
  and counts.writes==0,'')
 local world=assert(require('hd2runtime/runtime/event_world').open())
 -- Scaffolding: the simulated package loader answers only for packages the Runtime requested; base_faction (which
 -- holds the Pelican) is resident in this snapshot's real package list (research/pelican-F5FEE03DCFDB.json).
 local PE=require('hd2runtime/domains/pelican')
 local simulated_state=world.runtime.package_state
 world.runtime.package_state=function(hex)
  if hex==PE.packageId then return 'resident' end
  return simulated_state(hex)
 end
 local calls={}
 world.runtime.native_spawn_pelican=function(entry,x,y,z,fx,fy,ax,ay,az)
  calls[#calls+1]={entry=entry,x=x,y=y,z=z,fx=fx,fy=fy,ax=ax,ay=ay,az=az}
  return 909090
 end
 local hd2=require('hd2runtime/api/hd2')
 local state=require('hd2runtime/runtime/event_world').game_state(world)
 local avatar=require('hd2runtime/runtime/handles').local_avatar(world)
 local at=avatar and require('hd2runtime/runtime/event_world').unit_position(world,avatar.unit)
 local target=at and{x=at.x+25,y=at.y,z=at.z}or{x=0,y=0,z=0}
 local events={}
 local handle=hd2.pelican.spawn({position=target,hover=60,owner='mods/validation/pelican',
  on_event=function(e)events[#events+1]=e.kind end})
 for _=1,8 do frame()end
 if not(state and state.mission)then
  step('aboard the ship: refused NOT_IN_MISSION; the game is not called; nothing written',handle.status=='refused'
   and handle.code=='NOT_IN_MISSION'and #calls==0 and counts.writes==0,tostring(handle.code))
  return results
 end
 local SP=require('hd2runtime/domains/pelican').spawn
 local c=calls[1]
 step('in a mission, every guard on the real game: REQUESTED with the real default context (all zero), the Pelican '
  ..'registered, base_faction resident',count('PELICAN SPAWN REQUESTED (mods/validation/pelican): anchor ')==1
  and count('context: the game\'s default (2208 zero bytes: no cargo, no associated entity) with the anchor at '
  ..'+0x610')==1
  and count('PELICAN SPAWN REFUSED')==0,tostring(handle.status)..' '..tostring(handle.code)..' '..tostring(handle.reason))
 step('the game\'s spawn request (a recording stub: scaffolding) is called once, with its real entry, the position and '
  ..'a unit facing from the real local avatar: the anchor is the position, the spawn point 250 m back and 80 m up',
  #calls==1 and c.entry==world.game+SP.rva and math.abs(c.ax-target.x)<1e-3 and math.abs(c.ay-target.y)<1e-3
  and math.abs(c.x-(target.x-250*c.fx))<1e-3 and math.abs(c.z-(target.z+80))<1e-3
  and math.abs(c.fx*c.fx+c.fy*c.fy-1)<1e-3 and at~=nil,'calls='..#calls)
 step('no Pelican appears in the real Transport component: UNVERIFIED (exists false), nothing written',
  count('PELICAN SPAWN UNVERIFIED (mods/validation/pelican): entity 909090: exists false')==1
  and handle.status=='unverified'and events[1]=='unverified'and counts.writes==0,table.concat(events,','))
 return results
end
"""
EXTRAS['proof-pelican-spawn'] = {'after': PROOF_PELICAN_SPAWN, 'readOnly': True}
# PelicanCasProof 0.1.1 (Pelican Close Air Support with a RED-beacon carrier: docs/research/pelican-cas-F5FEE03DCFDB.md,
# "Carrier allocation"; 0.1.0 live-proven with the blue Orbital EMS Strike) on the shipped artifact and
# the snapshot's real StratagemSettings, account catalogue, text registry, mission record and clock; late resource
# lookups disabled, so the allocator, the beacon API, the slot cooldown, the Pelican modules and the carrier lifecycle
# must have been loaded at startup from the archive. On every snapshot: the proof loads (its text probe passes); the
# allocation on the real catalogue (runtime/carrier_allocator.lua): the Gas Barrage first, the Pelican CAS an unused
# carrier whose real row's beam (+0xD4) is red, never the 120mm, the Gas Strike, the blue Orbital EMS Strike or a carrier
# the Gas Barrage reserves, distinct and deterministic; every candidate's family and beacon category reported apart;
# its code relates to no reviewed native code; the lifecycle module applies the Pelican CAS text, icon and code to the
# real carrier row (native first) and restores exactly the captured bytes. Aboard the ship the proof itself writes
# nothing. On a mission snapshot (seed_payload_mission: a token entry): the proof refuses itself (no virtual slot: the
# snapshot has no selection); then its path: the look and code, a beacon watch for the carrier (observing only), the
# 60 s cooldown armed, the virtual slot converted to the allocated carrier (1 write) and seen by the cooldown watch,
# the conversion undone, the look and code restored.
PROOF_PELICAN_CAS = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function count(text)local n=0;for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end;return n end
 local world=assert(require('hd2runtime/runtime/event_world').open())
 for _=1,240 do frame()end
 step('the proof loads from the archive with the custom panel; the allocator, beacon, cooldown, Pelican and lifecycle '
  ..'modules were loaded at startup',count('PelicanCasProof 0.1.1 RED-BEACON CARRIER BUILD')==1
  and package.loaded['hd2runtime/runtime/carrier_allocator']~=nil and package.loaded['hd2runtime/runtime/beacons']~=nil
  and package.loaded['hd2runtime/runtime/slot_cooldown']~=nil and package.loaded['hd2runtime/runtime/pelicans']~=nil
  and package.loaded['hd2runtime/api/pelican']~=nil and package.loaded['hd2runtime/runtime/carrier_presentation']~=nil
  and count('text probe: game text registry 17 of 18 tables, 1 spare; language us; id clashes: none -> PASS')==1,'')
 local allocator=require('hd2runtime/runtime/carrier_allocator')
 local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
 local loadout=require('hd2runtime/runtime/stratagem_loadout')
 local catalog=require('hd2runtime/domains/stratagem_authoring')
 local calldown=require('hd2runtime/runtime/calldown_codes')
 local state=require('hd2runtime/runtime/event_world').game_state(world)
 local mission=state and state.mission
 local present={}
 local record=slots.local_record(world)
 for _,entry in ipairs(record and record.entries or{})do
  local id=loadout.id_of(world,entry.type);if id then present[id]=true end
 end
 local saved=loadout.saved(world)
 for _,pair in ipairs(saved and saved.pairs or{})do present[pair.id]=true end
 local a=allocator.allocate(world,allocator.DEFINITIONS,present)
 local again=allocator.allocate(world,allocator.DEFINITIONS,present)
 local mine=a.assignments and a.assignments['pelican_close_air_support']
 local gas=a.assignments and a.assignments['orbital_gas_barrage']
 local reserved={}
 for _,c in ipairs(a.candidates and a.candidates['orbital_gas_barrage']or{})do if c.eligible then reserved[c.id]=true end end
 local entry=mine and catalog.stratagems[mine.carrier]
 -- The beacon category from the REAL rows: the EMS Strike's beam is blue, every other orbital's red.
 local ems,airburst
 for _,c in ipairs(a.candidates and a.candidates['pelican_close_air_support']or{})do
  if c.name=='Orbital EMS Strike'then ems=c end
  if c.name=='Orbital Airburst Strike'then airburst=c end
 end
 local SR=require('hd2runtime/domains/stratagem_slots').row
 local row=mine and world.view.pointer(world.game+require('hd2runtime/schemas/current').stratagem.table_rva+mine.type*8)
 step('the beacon category from the real rows (+0xD4): the Orbital EMS Strike an orbital with a BLUE beam (support), '
  ..'the Airburst Strike red (offensive); family and beacon category reported apart',ems~=nil and ems.family=='orbital'
  and ems.beam==2 and ems.beaconCategory=='support'and ems.pingColour=='red'and airburst~=nil and airburst.beam==1
  and airburst.beaconCategory=='offensive','')
 step('the allocation on the real catalogue: the Gas Barrage first; the Pelican CAS an unused RED-beacon carrier (its '
  ..'real row\'s +0xD4 = 1), never the 120mm, the Gas Strike, the EMS Strike or a carrier the Gas Barrage reserves; '
  ..'distinct; deterministic',a.ready and mine~=nil and entry~=nil and mine.beacon=='offensive'and not mine.fallback
  and row and world.view.u32(row+SR.beam)==1 and mine.carrier~='Orbital 120mm HE Barrage'
  and mine.carrier~='Orbital Gas Strike'and mine.carrier~='Orbital EMS Strike'and not reserved[mine.stable_id]
  and(gas==nil or gas.stable_id~=mine.stable_id)and a.distinct and again.line==a.line,tostring(a.line))
 if not mine then return results end
 local values=assert(calldown.values({'left','down','left','up','left','up'}))
 step('the code left down left up left up relates to no reviewed native code',
  #calldown.native_relations(values,{[mine.stable_id]=true})==0,'')
 local function settle(handle)for _=1,600 do if handle.status~='pending'then break end;frame()end;return handle end
 local CP=require('hd2runtime/runtime/carrier_presentation')
 local texts=require('hd2runtime/runtime/text_resources')
 local images=require('hd2runtime/runtime/image_resources')
 local profile=require('hd2runtime/schemas/current')
 local RES='mods/skyeshade/hd2runtime_pelican_cas_proof'
 local SPEC={carrier=mine.carrier,text={name=texts.handle('pelican_close_air_support_name','PELICAN CLOSE AIR SUPPORT',RES),
  nameCased=texts.handle('pelican_close_air_support_name_cased','Pelican Close Air Support',RES),
  description=texts.handle('pelican_close_air_support_description','Calls in a Pelican that flies to the beacon and '
  ..'holds over it for 60 seconds.',RES)},icon=images.handle('pelican_close_air_support',RES),
  code={'left','down','left','up','left','up'}}
 local token_type=loadout.type_of(world,3523620028)
 local function row_bytes(kind)
  local row=world.view.pointer(world.game+profile.stratagem.table_rva+kind*8)
  return row and world.runtime.read(row,profile.stratagem.stride)
 end
 local function lifecycle_apply(label)
  local carrier_row,token_row=row_bytes(mine.type),row_bytes(token_type)
  local w0=counts.writes
  local applied=settle(CP.apply(SPEC))
  local v=applied.verify or{}
  step(label..': the lifecycle module on the real carrier row ('..mine.carrier..'): native first, then the Pelican CAS '
   ..'text, icon and code applied and verified (8 writes with the text table\'s registration); the token row '
   ..'byte-identical',applied.status=='applied'and v.identity and v.text and v.icon and v.code and v.others
   and row_bytes(mine.type)~=carrier_row and row_bytes(token_type)==token_row and counts.writes==w0+8,
   tostring(applied.code)..' '..tostring(applied.reason)..' writes='..(counts.writes-w0))
  return carrier_row,token_row
 end
 local function lifecycle_restore(label,carrier_row,token_row)
  local w1=counts.writes
  local restored,code,why=CP.restore_now()
  step(label..': restored in one tick from the captured bytes (7 writes): the whole carrier row and the token row '
   ..'byte-identical',restored~=nil and restored.verify.exact and restored.verify.native
   and row_bytes(mine.type)==carrier_row and row_bytes(token_type)==token_row and counts.writes==w1+7
   and not CP.applied(),tostring(code)..' '..tostring(why)..' writes='..(counts.writes-w1))
 end
 if not mission then
  step('aboard the ship: the proof wrote nothing (the carrier stays native aboard the ship)',counts.writes==0
   and count('[HD2Runtime] carrier presentation APPLIED')==0 and CP.state()==nil,'')
  local carrier_row,token_row=lifecycle_apply('the lifecycle module aboard the ship')
  lifecycle_restore('the lifecycle module aboard the ship',carrier_row,token_row)
  return results
 end
 step('in the mission the proof refuses itself (the snapshot has no virtual Pelican CAS slot) and writes nothing',
  count('MISSION START: TEST REFUSED (nothing converted, nothing written): no virtual Pelican CAS slot')==1
  and counts.writes==0,'')
 local carrier_row,token_row=lifecycle_apply('mission start, before the conversion')
 local order,slot={},nil
 local picks={}
 for _,e in ipairs(record.entries)do if e.granted==0 then picks[#picks+1]=e end end
 for k,e in ipairs(picks)do
  order[k]=loadout.id_of(world,e.type)
  if e.type==token_type and not slot then slot=k-1 end
 end
 local selector=require('hd2runtime/runtime/stratagem_selector')
 selector.set_virtual_slots_for_tests({slots={[slot]={definition='pelican_close_air_support',token=3523620028,
  type=token_type}},pairs=order})
 local beacons=require('hd2runtime/runtime/beacons')
 local seen={}
 local watch=beacons.watch({carrier=mine.carrier,label='validation: observe'},function(e)seen[#seen+1]=e.kind end)
 local cool=require('hd2runtime/runtime/slot_cooldown')
 local cooled={}
 local armed=cool.arm({definition='pelican_close_air_support',seconds=60,from='arrival',carrier=mine.carrier},
  function(e)cooled[#cooled+1]=e.kind end)
 local writes=counts.writes
 local converted=settle(selector.convert_virtual('pelican_close_air_support',nil,mine.carrier))
 for _=1,8 do frame()end
 step('the proof\'s path: the virtual slot converted to the allocated carrier (1 write); the beacon watch resolved the '
  ..'carrier; the 60 s cooldown watch sees the conversion',converted.status=='converted'and counts.writes==writes+1
  and watch~=nil and watch.status=='active'and watch.carrier_type==mine.type and armed~=nil and cooled[1]=='armed',
  tostring(converted.code)..' '..tostring(converted.reason)..' cooldown='..table.concat(cooled,','))
 local back=settle(slots.restore())
 watch.cancel();cool.disarm()
 step('the conversion undone; no failed callback',back.status=='restored'and count('callback failed')==0,'')
 lifecycle_restore('the return to the ship',carrier_row,token_row)
 return results
end
"""
# PelicanOrbitProof 0.2.0 (runtime/pelicans.lua retarget, now aligned 4-byte members, and the orbit with its entry:
# docs/research/pelican-cas-F5FEE03DCFDB.md, "The orbit") on the shipped artifact and the snapshot's real game.dll and memory: the proof loads; the Pelican pins (the
# retarget evidence: the flight update reading its target every frame, the release's one push, the only other writer)
# prove on the real code; nothing is written by the proof. The orbit driver and the retarget refuse anything but a
# held Runtime Pelican, writing nothing: aboard the ship (NOT_IN_MISSION), and in a mission for a Pelican the Runtime
# did not spawn (NOT_RUNTIME_PELICAN); an orbit of an entity that is not a Pelican stops at once ("the Pelican is gone").
PROOF_PELICAN_ORBIT = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function count(text)local n=0;for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end;return n end
 for _=1,120 do frame()end
 local pelicans=require('hd2runtime/runtime/pelicans')
 local world=assert(require('hd2runtime/runtime/event_world').open())
 local ok,why=pelicans.prove(world)
 step('the proof loads from the archive; runtime/pelicans.lua (loaded at startup) proves every Pelican pin, the retarget '
  ..'evidence included, on the real game.dll; nothing written',count('PelicanOrbitProof 0.3.0 ORBIT ORIENTATION BUILD')==1
  and ok==true and counts.writes==0,tostring(why))
 local state=require('hd2runtime/runtime/event_world').game_state(world)
 local raw=string.rep('\0',12)
 local r,code=pelicans.retarget(world,4242,{behaviour=raw,flight=raw},{x=0,y=0,z=0})
 if not(state and state.mission)then
  step('aboard the ship: a retarget is refused (NOT_IN_MISSION), nothing written',r==nil and code=='NOT_IN_MISSION'
   and counts.writes==0,tostring(code))
 else
  step('in a mission: a Pelican the Runtime did not spawn is never retargeted (NOT_RUNTIME_PELICAN), nothing written',
   r==nil and code=='NOT_RUNTIME_PELICAN'and counts.writes==0,tostring(code))
 end
 local events={}
 local o=pelicans.orbit(4242,{center={x=0,y=0,z=0},radius=40,altitude=60,duration=60,interval=0.25},
  function(e)events[#events+1]=e end)
 for _=1,8 do frame()end
 local stopped=events[#events]
 step('an orbit of an entity that is not a Runtime Pelican stops at once and writes nothing',o~=nil and stopped~=nil
  and stopped.kind=='stopped'and stopped.writes==0 and counts.writes==0 and count('callback failed')==0,
  tostring(stopped and stopped.reason))
 return results
end
"""
EXTRAS['proof-pelican-orbit'] = {'after': PROOF_PELICAN_ORBIT, 'readOnly': True}
# ExtractionPelicanProbe 0.1.0 and PelicanTurretProbe 0.3.0 (read-only; docs/research/pelican-cas-F5FEE03DCFDB.md, "Pelican
# variants" and "The Pelican's turret") on the shipped artifact and the snapshot's real memory: each probe loads and writes
# nothing; runtime/pelicans.lua's read-only readers, loaded at startup, read the REAL behaviour settings: the transport
# Pelican 667, the extraction Pelican (shuttle_gunship) 202, its chin turret 645, the Gatling Sentry 213; the live
# entity scan and the weapon-component maps read (on a mission snapshot the turret component holds its live turrets);
# and (0.3.0) the turret-weapon reader reads every real projectile weapon: its shot interval is 60 / its RPM, and none has
# a per-instance resolved copy (research section 15).
PROOF_PELICAN_PROBES = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function count(text)local n=0;for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end;return n end
 for _=1,120 do frame()end
 local pelicans=require('hd2runtime/runtime/pelicans')
 local PE=require('hd2runtime/domains/pelican')
 local world=assert(require('hd2runtime/runtime/event_world').open())
 local ok,why=pelicans.prove(world)
 step('the probe loads from the archive; the Pelican pins (the variants, the extraction flight and the turret components '
  ..'included) prove on the real game.dll; nothing written',(count('EXTRACTION PELICAN PROBE')>=1
  or count('TURRET WEAPON CONFIG PROBE')>=1)and ok==true and counts.writes==0,tostring(why))
 local T=PE.variants.byType
 local got={}
 for _,name in ipairs({'shuttle_transport','shuttle_gunship','shuttle_gunship_turret_hmg','gatling_turret'})do
  got[name]=pelicans.type_behaviour(world,T[name].resource)
 end
 step('the real behaviour settings: the transport Pelican 667, the extraction Pelican (shuttle_gunship) 202, the chin '
  ..'turret 645, the Gatling Sentry 213',got.shuttle_transport==667 and got.shuttle_gunship==202
  and got.shuttle_gunship_turret_hmg==645 and got.gatling_turret==213,('%s %s %s %s'):format(tostring(got.shuttle_transport),
  tostring(got.shuttle_gunship),tostring(got.shuttle_gunship_turret_hmg),tostring(got.gatling_turret)))
 local all={}
 for id=1,1000 do all[id]=true end
 local live=pelicans.behaviours(world,all)
 local n,held=0,0
 for entity,p in pairs(live or{})do
  n=n+1
  local c=pelicans.weapon_components(world,entity)
  if c.turret then held=held+1 end
 end
 local state=require('hd2runtime/runtime/event_world').game_state(world)
 step('the live entity scan reads the real Behavior component, and the turret component\'s real map finds its turrets in '
  ..'a mission; nothing written',live~=nil and n>0 and(not(state and state.mission)or held>0)and counts.writes==0,
  ('%d entities, %d in the turret component'):format(n,held))
 if state and state.mission then
  -- The snapshot's mounted pair (the shuttle escape hatch 386 carrying a personnel shuttle 387): the child's attachable
  -- record names its parent's handle link, at node 35; the poses read.
  local child,parent=pelicans.attachable(world,387),pelicans.handle(world,386)
  local pose=pelicans.pose(world,386)
  step('a real mounted pair: the child attachable record names the parent handle link (node 35); the parent '
   ..'pose reads a unit rotation',child~=nil and parent~=nil and child.link==parent.link and child.node==35
   and pose~=nil and math.abs(pose.rotation.x^2+pose.rotation.y^2+pose.rotation.z^2+pose.rotation.w^2-1)<1e-3,
   ('%s %s'):format(tostring(child and child.link),tostring(parent and parent.link)))
  -- Every real projectile weapon (the players' weapons in the snapshot): the reader's interval against its RPM slot, no
  -- per-instance copies, and a magazine record for the magazine weapons.
  local weapons,consistent,copies,magazines=0,0,0,0
  for entity=1,4000 do
   local w=pelicans.weapon_config(world,entity)
   if w then
    weapons=weapons+1
    if w.interval and w.rofSlots and math.abs(w.interval*w.rofSlots.y-60)<0.01 then consistent=consistent+1 end
    if w.copy or(w.magazine and w.magazine.copy)then copies=copies+1 end
    if w.path=='magazine'and w.magazine then magazines=magazines+1 end
   end
  end
  step('the turret-weapon reader on the real projectile weapons: every shot interval is 60 / its RPM, no per-instance '
   ..'copy, the magazine weapons read their records; nothing written',weapons>0 and consistent==weapons and copies==0
   and magazines>0 and counts.writes==0,('%d weapons, %d consistent, %d copies, %d magazine'):format(weapons,consistent,
   copies,magazines))
 end
 return results
end
"""
# PelicanGatlingProof 0.5.0 (runtime/pelican_weapon.lua, runtime/pelican_heading.lua; docs/research/pelican-cas-
# F5FEE03DCFDB.md sections 19-22) on the
# shipped artifact and the snapshot's real game.dll and memory: the proof loads and runtime/pelican_weapon.lua was loaded
# at startup; every Pelican pin (the casing path, the first shot, the rate seed, the Gatling AI's stage 12 and the
# pending stage, the magazine) and the exact entry bytes of the weapon and magazine copy routines and SetBehaviour prove
# on the real game.dll; the Gatling is read from the real type tables (148, 1600 RPM, its casing, a 500-round magazine)
# with the chin turret's (120, 300 RPM, its casing) and the same fire-effects layout; in a mission the Gatling package is
# requested at once through the asset loader; the development modules run interpreted (the JIT stays on for the rest);
# in a mission the target controller's candidate reader reads every real AI's perception record (0.4.2). There is no
# Runtime Pelican in a snapshot, so nothing is configured; direct requests outside the Runtime update are refused
# (NOT_GAME_THREAD; the target setter: NOT_SWITCHED) and no routine is called (recording stubs: scaffolding) and nothing
# is written.
PROOF_PELICAN_GATLING = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function count(text)local n=0;for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end;return n end
 for _=1,120 do frame()end
 step('the proof loads from the archive; runtime/pelican_weapon.lua was loaded at startup; nothing is written',
  count('PelicanGatlingProof 0.5.0 GATLING ATTRIBUTION BUILD (solo host)')==1
  and package.loaded['hd2runtime/runtime/pelican_weapon']~=nil and package.loaded['hd2runtime/runtime/pelican_heading']~=nil
  and counts.writes==0,'')
 local world=assert(require('hd2runtime/runtime/event_world').open())
 local weapon=require('hd2runtime/runtime/pelican_weapon')
 local PE=require('hd2runtime/domains/pelican')
 local AI=PE.gatling.ai
 local ok,why=weapon.prove(world)
 local sb=world.view.proves(world.game+PE.gatling.setBehaviour.rva,PE.gatling.setBehaviour.prologue)
 local t213=world.view.proves(world.game+AI.table+4*212,AI.entry213)
 local setter=world.view.proves(world.game+PE.targetSet.setter.rva,PE.targetSet.setter.prologue)
 step('every Pelican pin (the casing path, the first shot, the rate seed, the Gatling AI stage 12 and the pending '
  ..'stage, the magazine, the target setter and the perception lists) and the exact entry bytes of the weapon and '
  ..'magazine copy routines, SetBehaviour and the target setter prove on the real game.dll',ok==true and sb and t213
  and setter,tostring(why))
 local ref,code,reason=weapon.reference(world)
 local CS=PE.casing.observed
 step('the Gatling read from the real type tables: projectile 148, 1600 RPM, casing '..CS.gatlingSentry.particles
  ..', a 500-round magazine; the chin turret 120, 300 RPM, casing '..CS.chinTurret.particles..'; the same '
  ..'fire-effects layout (only the casing differs)',ref~=nil and ref.projectile==148 and ref.rpm==1600
  and ref.chin.projectile==120 and ref.chin.rpm==300 and weapon.hex(ref.casing.particles)==CS.gatlingSentry.particles
  and weapon.hex(ref.chin.casing.particles)==CS.chinTurret.particles and ref.casing.layout==ref.chin.casing.layout
  and ref.magazine.capacity==500 and ref.magazine.spares==0 and ref.chin.magazine.capacity==500,
  tostring(code)..' '..tostring(reason))
 local gt=require('hd2runtime/runtime/pelican_gatling')
 local TY=PE.aim.weaponData.types
 local function recoil(hex)
  local raw=gt.type_record(world,TY,hex)
  return raw and require('hd2runtime/core/bytes').value(raw,TY.recoilB,'f32'),raw and
   require('hd2runtime/core/bytes').value(raw,TY.recoilB+4,'f32')
 end
 local cx,cy=recoil(weapon.RESOURCES.chin)
 local gx,gy=recoil(weapon.RESOURCES.gatling)
 step('the aim recoil read from the real WeaponData type tables: the chin turret 2.5 sideways and 10 up a shot, the '
  ..'Gatling Sentry 0 and 3; the safe-maximum magazine is the maximum of the rounds network field, 2047',cx==2.5
  and cy==10 and gx==0
  and gy==3 and weapon.AMMO_MAX==2047,('%s %s %s %s %s'):format(tostring(cx),tostring(cy),tostring(gx),tostring(gy),
  tostring(weapon.AMMO_MAX)))
 local cs,gs=weapon.type_spread(world,weapon.RESOURCES.chin),weapon.type_spread(world,weapon.RESOURCES.gatling)
 step('the spread read from the real WeaponData type tables: the chin turret 1 and 1 mrad, the Gatling Sentry 10 and '
  ..'10, distribution word 0 (Mild would be 5.5)',cs~=nil and gs~=nil and cs.x==1 and cs.y==1 and cs.word==0 and gs.x==10
  and gs.y==10 and gs.word==0,('%s %s %s %s'):format(tostring(cs and cs.x),tostring(cs and cs.y),tostring(gs and gs.x),
  tostring(gs and gs.y)))
 local d4,s4=weapon.projectile_identity(world,275),weapon.projectile_identity(world,148)
 local dep=weapon.ap_dependency()
 step('the AP4 donor read from the real projectile table: 275 (the MG-206 round) type 275, damage 205, 980 m/s, mass 52; '
  ..'the standard 148 damage 125, 820 m/s, mass 11; its package is catalogued',d4~=nil and d4.type==275 and d4.damage==205
  and d4.velocity==980 and d4.mass==52 and s4~=nil and s4.type==148 and s4.damage==125 and s4.velocity==820
  and s4.mass==11 and dep~=nil and dep.key=='support_weapon/MG-206 Heavy Machine Gun',('%s %s %s'):format(
  tostring(d4 and d4.damage),tostring(s4 and s4.damage),tostring(dep and dep.package)))
 local jit_=rawget(_G,'jit')
 step('the development modules run interpreted; the JIT stays on for everything else',jit_~=nil and jit_.status()==true,
  tostring(jit_ and jit_.version))
 local game=require('hd2runtime/runtime/event_world').game_state(world)
 local in_mission=game and game.mission
 step('the Gatling package and the AP4 donor package (the MG-206 one) go through the Runtime asset loader: requested '
  ..'at once in a mission, not aboard the ship',
  count('assets for pelican-weapon requested: 1 package(s)')==(in_mission and 1 or 0)
  and count('assets for pelican-weapon-ap4 requested: 1 package(s)')==(in_mission and 1 or 0),
  'requested='..count('assets for pelican-weapon requested'))
 if in_mission then
  -- The target controller's candidate reader on the real perception records: every AI with a perceiver.
  local perceivers,unreadable,listed,known,perceived,candidates=0,0,0,0,0,0
  local wm=require('hd2runtime/runtime/event_world')
  for entity=1,4000 do
   local a=weapon.ai_state(world,entity)
   if a and require('hd2runtime/core/bytes').u32(a.raw,PE.targetSet.record.perceiver)~=0 then
    perceivers=perceivers+1
    local p=weapon.perception(world,entity,a)
    if not p then unreadable=unreadable+1 else
     for _,e in ipairs(p.entries)do
      listed=listed+1
      if wm.entity_state(world,e.entity)then known=known+1 end
      if e.perceived then perceived=perceived+1 end
     end
     local list=weapon.candidates(world,entity,a)
     candidates=candidates+(list and #list or 0)
    end
   end
  end
  step('the candidate reader on the real perception records: every AI with a perceiver reads its record (lists A, B and '
   ..'C within 16 entries, its sensors); every listed entity has a health record; the candidates are perceived ones; '
   ..'nothing written',perceivers>0 and unreadable==0 and known==listed and candidates<=perceived and counts.writes==0,
   ('%d perceivers, %d unreadable, %d listed, %d with health, %d perceived now, %d candidates'):format(perceivers,
   unreadable,listed,known,perceived,candidates))
  -- The attribution readers on real records: a weapon wielded by a player's avatar is creditable (the avatar has
  -- faction bit 0, a network id and no no-credit tag); the last hit of real health records reads.
  local wielded,creditable,hits=0,0,0
  for entity=1,4000 do
   local c=weapon.credit_state(world,entity)
   if c and c.wielder~=0 and c.wielder~=entity then
    wielded=wielded+1
    if c.raw and not c.no_credit and c.faction%2==1 and c.network then creditable=creditable+1 end
   end
   if wm.entity_state(world,entity)and weapon.last_hit(world,entity)then hits=hits+1 end
  end
  step('the attribution readers on the real records: every weapon wielded by an avatar reads creditable (faction bit 0, '
   ..'a network id, no no-credit tag); real health records give their last hit; nothing written',wielded>0
   and creditable==wielded and hits>0 and counts.writes==0,('%d wielded, %d creditable, %d last hits'):format(wielded,
   creditable,hits))
  -- The spread reader on the real WeaponData instance records (research "spread": their type's times their own
  -- multipliers, 1 for every weapon in the snapshots).
  local weapons,plain=0,0
  for entity=1,4000 do
   local sp=weapon.spread_state(world,entity)
   if sp then
    weapons=weapons+1
    if sp.x>=0 and sp.x<1000 and sp.y>=0 and sp.y<1000 and sp.multipliers.x==1 and sp.multipliers.y==1 then
     plain=plain+1
    end
   end
  end
  step('the spread reader on the real WeaponData instance records: widths in range, own multipliers 1; nothing written',
   weapons>0 and plain==weapons and counts.writes==0,('%d weapons, %d plain'):format(weapons,plain))
 end
 local calls={}
 for _,name in ipairs({'native_weapon_copy','native_magazine_copy','native_set_behaviour','native_set_target'})do
  world.runtime[name]=function(...)calls[#calls+1]=name;return true end
 end
 local r,c1=weapon.configure(world,386,{projectile=148,rpm='gatling',casing=true,ammo=true,recoil=true},'validation')
 local s,c2=weapon.switch_ai(world,386,'validation')
 local e=weapon.target_step(world,386,'validation')
 local f=weapon.refill_step(world,386,'validation')
 local h=require('hd2runtime/runtime/pelican_heading').face_step(world,386,{x=0,y=0,z=0},'validation')
 local st,c3=weapon.set_target(world,387,386,'validation')
 local sp=weapon.configure_spread(world,387,'validation','gatling')
 local cr=weapon.configure_credit(world,387,'validation')
 step('direct requests outside the Runtime update are refused (configure, the AI change, the target controller, the '
  ..'target setter, the spread, the kill credit, the refill, the body facing); no routine is called; nothing written',r==nil and c1=='NOT_GAME_THREAD'
  and s==nil and c2=='NOT_GAME_THREAD'and #e==0 and st==nil and c3=='NOT_SWITCHED'and not sp.applied
  and tostring(sp.reason):find('NOT_GAME_THREAD',1,true)~=nil and not cr.applied
  and tostring(cr.reason):find('NOT_GAME_THREAD',1,true)~=nil and f==nil and h~=nil
  and h.code=='NOT_GAME_THREAD'and #calls==0 and counts.writes==0,tostring(c1)..' '..tostring(c2)..' '..tostring(c3)
  ..' '..tostring(h and h.code))
 return results
end
"""
EXTRAS['proof-pelican-gatling'] = {'after': PROOF_PELICAN_GATLING, 'readOnly': True}
# PelicanWeaponBehaviorProof 0.1.0 (runtime/pelican_weapon.lua; docs/research/pelican-cas-F5FEE03DCFDB.md section 17) on
# the shipped artifact and the snapshot's real game.dll and memory: the proof loads and runtime/pelican_weapon.lua was
# loaded at startup; every Pelican pin (the chin turret AI's 0.5 s fire window and 1.5 s re-aim, the trigger, the
# magazine copy routine and the record the game derives from it, included) and the exact entry bytes of the ProjectileWeapon
# and magazine copy routines prove on the real game.dll; in a mission the projectile's package is requested at once
# through the asset loader. There is no Runtime Pelican in a snapshot, so nothing is configured; direct requests outside the
# Runtime update are refused (NOT_GAME_THREAD) and no routine is called (recording stubs: scaffolding) and nothing written.
PROOF_PELICAN_WEAPON = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function count(text)local n=0;for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end;return n end
 for _=1,120 do frame()end
 step('the proof loads from the archive; runtime/pelican_weapon.lua was loaded at startup; nothing is written',
  count('PelicanWeaponBehaviorProof 0.1.0 CHIN TURRET CONTINUOUS-FIRE BUILD (solo host)')==1
  and package.loaded['hd2runtime/runtime/pelican_weapon']~=nil and counts.writes==0,'')
 local world=assert(require('hd2runtime/runtime/event_world').open())
 local weapon=require('hd2runtime/runtime/pelican_weapon')
 local ok,why=weapon.prove(world)
 step('every Pelican pin (the chin turret AI fire window and re-aim, the trigger, the magazine copy routine) and the '
  ..'exact entry bytes of the weapon and magazine copy routines prove on the real game.dll',ok==true,tostring(why))
 local game=require('hd2runtime/runtime/event_world').game_state(world)
 local in_mission=game and game.mission
 step('the projectile package goes through the Runtime asset loader: requested at once in a mission, not aboard the ship',
  count('assets for pelican-weapon requested: 1 package(s)')==(in_mission and 1 or 0),
  'requested='..count('assets for pelican-weapon requested'))
 local calls={}
 for _,name in ipairs({'native_weapon_copy','native_magazine_copy'})do
  world.runtime[name]=function(...)calls[#calls+1]=name;return true end
 end
 local r,code=weapon.configure(world,386,{rpm=600},'validation')
 local h,hcode=weapon.hold_fire(world,386,'validation')
 step('direct requests outside the Runtime update are refused; no routine is called; nothing written',
  r==nil and code=='NOT_GAME_THREAD'and h==nil and hcode=='NOT_CONFIGURED'and #calls==0 and counts.writes==0,
  tostring(code)..' '..tostring(hcode))
 return results
end
"""
EXTRAS['proof-pelican-weapon-behavior'] = {'after': PROOF_PELICAN_WEAPON, 'readOnly': True}
# PelicanGatlingAIProof 0.2.0 (runtime/pelican_weapon.lua switch_ai through the game SetBehaviour; docs/research/pelican-cas-F5FEE03DCFDB.md section 18)
# on the shipped artifact and the snapshot's real game.dll and memory: the proof loads; every Pelican pin (the Behavior
# update choosing code by the record's behaviour id, the jump table, the Gatling AI's stage machine included) proves and
# the jump table's 645 and 213 entries are the researched ones; on a mission snapshot the real Behavior records read
# through the AI reader (id, stage, nothing pending, no transition); a direct switch outside the Runtime update is refused
# and nothing is written.
PROOF_PELICAN_GATLING_AI = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function count(text)local n=0;for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end;return n end
 for _=1,120 do frame()end
 step('the proof loads from the archive; nothing is written',
  count('PelicanGatlingAIProof 0.2.0 GATLING-AI SET-BEHAVIOUR BUILD (solo host)')==1 and counts.writes==0,'')
 local world=assert(require('hd2runtime/runtime/event_world').open())
 local weapon=require('hd2runtime/runtime/pelican_weapon')
 local PE=require('hd2runtime/domains/pelican')
 local AI=PE.gatling.ai
 local ok,why=weapon.prove(world)
 local t645=world.view.proves(world.game+AI.table+4*644,AI.entry645)
 local t213=world.view.proves(world.game+AI.table+4*212,AI.entry213)
 local sb=world.view.proves(world.game+PE.gatling.setBehaviour.rva,PE.gatling.setBehaviour.prologue)
 step('every Pelican pin (the Behavior update choosing code by the behaviour id, the Gatling AI stages) proves; the jump '
  ..'table entries of 645 and 213 and the game SetBehaviour entry bytes are the researched ones',ok==true and t645
  and t213 and sb,tostring(why))
 local game=require('hd2runtime/runtime/event_world').game_state(world)
 if game and game.mission then
  local pelicans=require('hd2runtime/runtime/pelicans')
  local all={};for id=1,1000 do all[id]=true end
  local n,rest=0,0
  for entity in pairs(pelicans.behaviours(world,all)or{})do
   local a=weapon.ai_state(world,entity)
   if a then n=n+1;if a.pending==-1 and a.transitioning==-1 and a.id>0 then rest=rest+1 end end
  end
  step('the AI reader on the real Behavior records: every one reads an id, nothing pending, no transition running',
   n>0 and rest==n,('%d records, %d at rest'):format(n,rest))
 end
 local r,code=weapon.switch_ai(world,386,'validation')
 step('a direct switch outside the Runtime update is refused; nothing written',r==nil and code=='NOT_GAME_THREAD'
  and counts.writes==0,tostring(code))
 return results
end
"""
EXTRAS['proof-pelican-gatling-ai'] = {'after': PROOF_PELICAN_GATLING_AI, 'readOnly': True}
# The custom stratagem API examples (proof/PelicanCasExample, GasBarrageExample, GasEatExample, HmgSentryExample,
# EagleStunRocketPodsExample; runtime/custom_stratagems.lua; docs/custom-stratagem-api.md) on the shipped artifact and the
# snapshot's real game.dll and memory: the example loads from the archive and registers through hd2.custom_stratagem
# (the orchestrator, the gunship, the pod capture, the impact, weapon, Eagle and explosion-donor modules loaded at
# startup); every new pin proves on the real game.dll (the projectile pool's impact pins and its census, the support
# delivery's pod and rack pins, the mission loader's call-in package rule, the payload families' Eagle and weapon-record
# pins, the EMS and Gas Strike donor chains); the EAT-17's call-in
# package is its weapon's (lat_oneshot) and complete; the carrier allocation runs on the real catalogue with the
# example's policy (an Eagle example in the allocator's Eagle mode; when the account catalogue is filled: its carrier
# has the policy's beacon and family, never the token, never an asset); the ship icon colour set (the sentry's own: 3);
# the pod and rack readers read the real components; direct requests are refused; nothing is written.
EXAMPLE_CUSTOM_STRATAGEM = r'''
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function count(text)local n=0;for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end;return n end
 for _=1,120 do frame()end
 local ID,BANNER,BEACON,FAMILIES,COLOUR_SET=%(id)r,%(banner)r,%(beacon)r,%(families)s,%(colour_set)d
 step('the example loads from the archive and registers through hd2.custom_stratagem; the orchestrator, the Pelican '
  ..'gunship, the pod capture and the impact modules were loaded at startup; nothing is written',
  count(BANNER)==1 and count('custom stratagem REGISTERED '..ID..' ')==1
  and package.loaded['hd2runtime/runtime/custom_stratagems']~=nil
  and package.loaded['hd2runtime/runtime/pelican_gunship']~=nil and package.loaded['hd2runtime/runtime/support_pods']~=nil
  and package.loaded['hd2runtime/runtime/projectile_impact']~=nil
  and package.loaded['hd2runtime/runtime/custom_weapons']~=nil and package.loaded['hd2runtime/runtime/custom_eagles']~=nil
  and package.loaded['hd2runtime/runtime/explosion_donors']~=nil and counts.writes==0,
  'banner='..count(BANNER)..' registered='..count('custom stratagem REGISTERED '..ID))
 local wm=require('hd2runtime/runtime/event_world')
 local world=assert(wm.open())
 local pool_ok,pool_why=wm.prove_projectile_pool(world)
 local pods=require('hd2runtime/runtime/support_pods')
 local pods_ok,pods_why=pods.prove(world)
 local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
 local slots_ok,slots_why=slots.prove(world)
 local PO=require('hd2runtime/domains/projectile_rows').pool
 -- The impact group's twelve pins (research/projectile-pool proof 4), all among the pool's re-proven pins.
 local IMPACT={[0x13AED1D]=1,[0x13AED9B]=1,[0x13AEDA7]=1,[0x13AEDB4]=1,[0x13AEDC6]=1,[0x13B070F]=1,[0x13B0736]=1,
  [0x13B073D]=1,[0x13B09DC]=1,[0x13B09E9]=1,[0x13B09F8]=1,[0x13B0A00]=1}
 local impact_pins=0
 for _,pin in ipairs(PO.pins)do if IMPACT[pin.rva]then impact_pins=impact_pins+1 end end
 step('every new pin proves on the real game.dll: the projectile pool with the impact explosion copy, the support '
  ..'delivery (pod, content, rack), the mission loader\'s call-in package rule',pool_ok==true and pods_ok==true
  and slots_ok==true and impact_pins==12,tostring(pool_why)..' '..tostring(pods_why)..' '..tostring(slots_why)..' '
  ..impact_pins)
 -- The payload families: the Eagle jet and rockets, the weapon handle, the EMS donor (research/custom-payloads).
 local eagles=require('hd2runtime/runtime/custom_eagles')
 local eagles_ok,eagles_why=eagles.prove(world)
 local jets,jwhy=eagles.jets(world)
 local donors=require('hd2runtime/runtime/explosion_donors')
 local ems_ok,ems_why=donors.DONORS['Orbital EMS Strike'].chain(world)
 local gas_ok,gas_why=donors.DONORS['Orbital Gas Strike'].chain(world)
 step('the payload families on the real game.dll: the Eagle manager, strike and dispatch pins, the ProjectileWeapon '
  ..'world record (+0x68), the jets read (read-only), the EMS and Gas Strike donor chains exactly as reviewed',
  eagles_ok==true and jets~=nil and ems_ok==true and gas_ok==true and counts.writes==0,tostring(eagles_why)..' '
  ..tostring(jwhy)..' '..tostring(ems_why)..' '..tostring(gas_why))
 -- The Pelican's frozen Gatling values are the game's own type records on this build; the MG-43 Sentry's own types as
 -- the research found them (no rate-of-fire input, its Y slot 630). Read-only.
 local b=require('hd2runtime/core/bytes')
 local PWM=require('hd2runtime/runtime/pelican_weapon')
 local PGT=require('hd2runtime/runtime/pelican_gatling')
 local PD=require('hd2runtime/domains/pelican')
 local F,ref=PWM.FROZEN,PWM.reference(world)
 local frozen_ok=ref~=nil and ref.projectile==F.projectile and ref.rpm==F.rpm and ref.chin.rpm==F.chin.rpm
  and ref.casing.particles==F.casing.particles and ref.casing.parameters==F.casing.parameters
  and ref.magazine.capacity==F.magazine.capacity and ref.chin.casing.particles==F.chin.casing.particles
 local mgwd=PGT.type_record(world,PD.aim.weaponData.types,'37CDE43876BA26BB')
 local mgpw=PGT.type_record(world,PD.gatling.pwTypes,'37CDE43876BA26BB')
 local mg_ok=mgwd~=nil and mgpw~=nil and b.u32(mgwd,184)==0 and b.u32(mgwd,188)==0 and b.u32(mgpw,0)==148
  and b.value(mgpw,8,'f32')==630
 step('the Pelican\'s frozen Gatling values equal the type records on the real game.dll; the MG-43 Machine Gun Sentry\'s '
  ..'own types as researched (round 148, Y slot 630, no rate-of-fire input); nothing written',frozen_ok and mg_ok
  and counts.writes==0,'frozen='..tostring(frozen_ok)..' mg43='..tostring(mg_ok))
 -- The lobby's native selections (runtime/carrier_allocator.lua "the lobby"): every stratagem record, one per peer,
 -- read on the real game; the same local record the per-player paths use; read-only.
 local SC=require('hd2runtime/runtime/stratagem_slot_conversion')
 local recs,rwhy=SC.records(world)
 local lr=SC.local_record(world)
 local locals=0
 for _,r in ipairs(recs or{})do if r['local']then locals=locals+1 end end
 local lob=require('hd2runtime/runtime/carrier_allocator').lobby_native(world,{})
 step('the lobby\'s native selections on the real game: every stratagem record read (one per peer; this snapshot: '
  ..tostring(recs and#recs)..'), exactly one of them the local player\'s and the same record the per-player paths '
  ..'use, unioned into the native set; nothing written',((lr==nil and recs==nil)or(lr~=nil and recs~=nil
  and locals==1 and#recs==lr.records and lob.records==#recs))and counts.writes==0,tostring(rwhy)..' '..lob.sources)
 local assets=require('hd2runtime/core/assets')
 local catalog=require('hd2runtime/domains/stratagem_authoring')
 local eat=assets.dependencies_for_stratagem(catalog.stratagems['EAT-17 Expendable Anti-Tank'].root.id,'EAT-17')
 local ac8=assets.dependencies_for_stratagem(catalog.stratagems['AC-8 Autocannon'].root.id,'AC-8')
 step('the call-in packages: the EAT-17\'s is its weapon\'s (lat_oneshot, 0xDE96CD7CC69628BC); the AC-8 has two (its '
  ..'own and its weapon\'s); both complete',eat~=nil and#eat==1 and eat[1].package=='0xDE96CD7CC69628BC'
  and ac8~=nil and#ac8==2 and assets.call_in_complete('EAT-17 Expendable Anti-Tank'),tostring(eat and eat[1].package))
 local custom=require('hd2runtime/runtime/custom_stratagems')
 local d=custom.get(ID)
 local A=require('hd2runtime/runtime/carrier_allocator')
 local excl={}
 for _,def in ipairs(custom.list())do for _,n in ipairs(def.exclude)do excl[#excl+1]=n end end
 local a=A.allocate_policies(world,{{id=ID,label=ID,token='Orbital Precision Strike',policy=d.policy,
  eagle=d.eagle~=nil}},{},excl)
 local mine=a.ready and a.assignments[ID]
 local fine=true
 if mine then
  local allowed=false
  for _,f in ipairs(FAMILIES)do if f==mine.family then allowed=true end end
  fine=mine.beacon==BEACON and allowed and mine.carrier~='Orbital Precision Strike'
  for _,n in ipairs(excl)do if n==mine.carrier then fine=false end end
 end
 step('the carrier allocation on the real catalogue: '..(a.ready and(mine and(mine.carrier..' ('..tostring(mine.family)
  ..', '..tostring(mine.beam)..' beacon)')or('refused: '..tostring(a.refused[ID])))or('not ready: '..tostring(a.reason)))
  ..' (read-only)',fine and counts.writes==0,a.line or a.reason)
 -- The ship icon colours (the custom panel's tile, the native slot overlay) on the real colour table: a support custom
 -- stratagem takes a support stratagem's set (2, blue), the others keep the token's (Orbital Precision Strike: 0).
 local OV=require('hd2runtime/runtime/stratagem_slot_overlay')
 local SELM=require('hd2runtime/runtime/stratagem_selector')
 local token_kind=require('hd2runtime/runtime/stratagem_loadout').type_of(world,d.virtual.selection.tokenId)
 local ckind=OV.colour_type(world,d.virtual,token_kind)
 local cvals,cset=SELM.icon_colours(world,ckind)
 step('the ship icon colours: '..tostring(d.virtual.display.colours or 'the token')..'\'s, colour set '..tostring(cset)
  ..' (read from the real table)',cvals~=nil and cset==COLOUR_SET,tostring(cset))
 local list,lwhy=pods.pods(world)
 step('the pod reader reads the real Transport component (read-only)',list~=nil,tostring(lwhy))
 local impacts=require('hd2runtime/runtime/projectile_impact')
 local b,code=impacts.bind({sources={4242},projectile=132,donor='Orbital Gas Strike'})
 local credit=require('hd2runtime/api/ownership').credit_to_player(4242,{is_local=true,peer='0'})
 step('direct requests are refused: an impact binding without a mission and a live launcher, a credit outside the '
  ..'Runtime update; nothing written',b==nil and code~=nil and credit.applied==false
  and tostring(credit.reason):find('NOT_GAME_THREAD',1,true)~=nil and counts.writes==0,tostring(code)..' '
  ..tostring(credit.reason))
 return results
end
'''
for _name, _id, _banner, _beacon, _families, _colour_set in (
        ('example-pelican-cas', 'pelican_close_air_support', 'PelicanCasExample 0.1.8 HOST PELICAN BUILD',
            'offensive', "{'orbital','eagle','sentry','emplacement','mine','support','backpack'}", 0),
        ('example-gas-barrage', 'orbital_gas_barrage', 'OrbitalGasBarrage 0.2.0 BUILD',
            'offensive', "{'orbital','eagle','sentry','emplacement','mine','support','backpack'}", 0),
        ('example-orbital-ems-barrage', 'orbital_ems_barrage', 'OrbitalEmsBarrage 0.1.0 BUILD',
            'offensive', "{'orbital','eagle','sentry','emplacement','mine','support','backpack'}", 0),
        ('example-gas-eat', 'eat17_gas', 'GasEatExample 0.1.7 MULTIPLAYER PROVENANCE BUILD', 'support',
            "{'support','backpack'}", 2),
        ('example-hmg-sentry', 'hmg_sentry', 'HeavyMgSentry 0.3.0 BUILD', 'support', "{'sentry'}", 3),
        ('example-eagle-stun-rocket-pods', 'eagle_stun_rocket_pods',
            'EagleStunRocketPodsExample 0.3.1 DEV LINE BUILD', 'offensive', "{'eagle'}", 0)):
    EXTRAS[_name] = {'after': EXAMPLE_CUSTOM_STRATAGEM % {'id': _id, 'banner': _banner,
        'beacon': _beacon, 'families': _families, 'colour_set': _colour_set}, 'readOnly': True}
# The expendable custom stratagem example (proof/EAT17GExample 0.2.1; runtime/weapon_clone.lua, runtime/weapon_carriers.lua,
# runtime/carrier_pod.lua, runtime/carrier_groups.lua; docs/research/carrier-weapon-clone-F5FEE03DCFDB.md,
# docs/research/carrier-pod-items-F5FEE03DCFDB.md section 11) on the shipped artifact, the snapshot's real game.dll and
# its real entity region: the example loads from the archive, binds its Mod Options level and registers through
# hd2.custom_stratagem in the expendable carrier group with a two-launcher pod; the clone and carrier pod modules were
# loaded at startup; every clone pin proves on the real game.dll; each clone host's records are where the research found
# them (one owner each, the game's own type tables pointing at them) and hold exactly their native bytes; each pool
# weapon's own rack record is exclusively its own and exactly its vanilla bytes (read-only); the pool, the deliveries
# (two launchers in the planned slots, the EAT-411's slot 1 at attach_1) and the call-in packages on the real catalogue;
# the condensed carrier check of the free pool weapon's own row and the availability against the real loadout
# (read-only); describe(); a conversion and a rack write aboard the ship are refused with nothing written.
EXAMPLE_EAT17G = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function count(text)local n=0;for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end;return n end
 for _=1,120 do frame()end
 local custom=require('hd2runtime/runtime/custom_stratagems')
 local d=custom.get('eat17g_clone')
 step('the example loads from the archive and registers through hd2.custom_stratagem (the expendable family); the '
  ..'clone and carrier pod modules were loaded at startup; nothing is written',
  count('EAT40ExpendableGas 0.3.0 BUILD')==1
  and count('custom stratagem REGISTERED eat17g_clone ')==1 and d~=nil and d.kind=='expendable'
  and package.loaded['hd2runtime/runtime/weapon_clone']~=nil and package.loaded['hd2runtime/runtime/weapon_carriers']~=nil
  and package.loaded['hd2runtime/runtime/carrier_pod']~=nil and package.loaded['hd2runtime/runtime/carrier_groups']~=nil
  and counts.writes==0,'registered='..count('custom stratagem REGISTERED eat17g_clone '))
 step('its carrier group is expendable (requested) and its pod holds two clone launchers (capacity 2)',d~=nil
  and d.group=='expendable'and d.group_source=='requested'and d.slots==2 and d.delivery.pod.total==2
  and count('carrier group expendable (requested, capacity 2)')==1,tostring(d and d.group))
 step('its clone level is full (the default)',d~=nil and custom.level_of(d)=='full',
  tostring(d and custom.level_of(d)))
 local wm=require('hd2runtime/runtime/event_world')
 local world=assert(wm.open())
 local clone=require('hd2runtime/runtime/weapon_clone')
 local ok,why=clone.prove(world)
 step('every clone pin proves on the real game.dll (the type-table readers, the pickup prompt\'s icon path, the Spottable '
  ..'instance manager)',ok==true,tostring(why))
 local all=true
 local details={}
 for _,carrier in ipairs(clone.pool('EAT-17 Expendable Anti-Tank'))do
  local r,code,reason=clone.inspect(world,carrier)
  details[#details+1]=carrier..': '..(r and(('native %s, %d records'):format(tostring(r.native),r.records))
   or(tostring(code)..' '..tostring(reason)))
  all=all and r~=nil and r.native==true and r.records==8
  local n=clone.instances(world,clone.carrier(carrier).entity)
  all=all and type(n)=='number'
 end
 step('each clone host on the real entity region: one owner per record, the game\'s type tables pointing at them, the '
  ..'exact native bytes (read-only)',all and counts.writes==0,table.concat(details,'; '))
 local assets=require('hd2runtime/core/assets')
 local complete=true
 for _,name in ipairs({'EAT-17 Expendable Anti-Tank','EAT-700 Expendable Napalm','EAT-411 Leveller'})do
  complete=complete and assets.call_in_complete(name)==true
 end
 local dl=d and custom.expendable_delivery(d,{weapon='EAT-700 Expendable Napalm'},'full')
 step('the deliveries and call-in packages on the real catalogue: the EAT-700\'s rack delivers its launchers, which fire '
  ..'the EAT-17\'s round at the full level; the donor\'s and every pool weapon\'s packages are known and complete',
  complete and dl~=nil and dl.item_types['B2B5E0D185605F9E']==true and dl.items['B2B5E0D185605F9E'].projectile==132,
  tostring(dl and dl.stratagem))
 local pod=require('hd2runtime/runtime/carrier_pod')
 local racks,rdetail=true,{}
 for _,carrier in ipairs(clone.pool('EAT-17 Expendable Anti-Tank'))do
  local r,code,reason=pod.inspect(world,carrier)
  rdetail[#rdetail+1]=carrier..': '..(r and('native, capacity '..r.capacity)or(tostring(code)..' '..tostring(reason)))
  racks=racks and r~=nil and r.native==true and r.capacity==2
 end
 step('each pool weapon\'s own rack record on the real entity region: one owner, one consumer row, exactly its vanilla '
  ..'slots, capacity 2 (read-only)',racks and counts.writes==0,table.concat(rdetail,'; '))
 local l411=d and custom.expendable_delivery(d,{weapon='EAT-411 Leveller'},'full')
 local l700=d and custom.expendable_delivery(d,{weapon='EAT-700 Expendable Napalm'},'full')
 step('the pod plans: the EAT-411\'s two launchers in slots 0 and 1 (slot 1 at attach_1: one slot item written), the '
  ..'EAT-700\'s already its own two (nothing written)',l411~=nil and l411.count==2 and l411.layout[0]=='7617642765AC38C7'
  and l411.layout[1]=='7617642765AC38C7'and l411.plan.writes==1 and l700~=nil and l700.plan.writes==0,
  tostring(l411 and l411.plan and l411.plan.writes))
 local job=pod.apply({carrier='EAT-411 Leveller',items=l411 and l411.units or{}})
 for _=1,100 do if job.status~='pending'then break end;frame()end
 step('a rack write aboard the ship is refused (NOT_IN_MISSION); nothing written',job.status=='refused'
  and job.code=='NOT_IN_MISSION'and counts.writes==0,tostring(job.code))
 local loadout=require('hd2runtime/runtime/stratagem_loadout')
 local saved=loadout.saved(world)
 local ids={}
 for k,pair in ipairs(saved and saved.pairs or{})do ids[k]=pair.id end
 local present,who=custom.lobby_picks(world,ids)
 local WC=require('hd2runtime/runtime/weapon_carriers')
 local reason,weapon=WC.unavailable('eat17g_clone','EAT-17 Expendable Anti-Tank',present,{},{who=who})
 local both=present[WC.stable_id('EAT-700 Expendable Napalm')]and present[WC.stable_id('EAT-411 Leveller')]
 step('the availability against the real loadout and records (read-only): '..tostring(reason or('available, carrier '
  ..'weapon '..tostring(weapon and weapon.weapon))),(both and reason~=nil)or(not both and reason==nil and weapon~=nil),
  tostring(reason))
 if weapon then
  local c,why=custom.condensed_carrier(world,weapon.weapon,present,false)
  step('the condensed carrier check of '..weapon.weapon..'\'s own row against the real loadout (read-only): '
   ..(c and('it carries the beacon too ('..tostring(c.beamColour)..' beam)')or('fallback: '..tostring(why))),
   counts.writes==0 and(c==nil or c.beaconCategory=='support'),tostring(why))
 end
 local desc=custom.describe('eat17g_clone')
 step('describe: group expendable, its pod items (clone x2), capacity',desc~=nil and desc.group=='expendable'
  and desc.slots==2 and(desc.pod==nil or desc.pod.items[1].item=='clone'),tostring(desc and desc.group))
 local h=clone.apply({carrier='EAT-700 Expendable Napalm',donor='EAT-17 Expendable Anti-Tank',level='full'})
 for _=1,100 do if h.status~='pending'then break end;frame()end
 step('a conversion aboard the ship is refused (NOT_IN_MISSION); nothing written',h.status=='refused'
  and h.code=='NOT_IN_MISSION'and counts.writes==0,tostring(h.code))
 return results
end
"""
EXTRAS['example-eat17g'] = {'after': EXAMPLE_EAT17G, 'readOnly': True}
# The weapon VARIANT example (proof/LaserMaxigunExample 0.1.0; runtime/weapon_clone.lua variant_body,
# runtime/model_resources.lua, domains/weapon_variants.lua; docs/custom-models.md, docs/research/weapon-variants-
# F5FEE03DCFDB.md) on the shipped artifact, the snapshot's real game.dll and entity region: it registers in the weapon
# carrier group with the Talon round and its model (Mod Options: check only by default); the clone pins and the UnitPath
# consumer pins prove on the real game.dll; the Maxigun's four records are where the research found them, native; its
# own pod delivers the gun (firing the Talon's 144) and its backpack; the availability against the real loadout (no
# fallback); a conversion aboard the ship is refused with nothing written.
EXAMPLE_LASER_MAXIGUN = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function count(text)local n=0;for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end;return n end
 for _=1,120 do frame()end
 local custom=require('hd2runtime/runtime/custom_stratagems')
 local d=custom.get('laser_maxigun')
 step('the example loads from the archive and registers through hd2.custom_stratagem (the weapon family, a variant of '
  ..'the M-1000 Maxigun on its own type); nothing is written',count('LaserMaxigunExample 0.1.1 LASER MAXIGUN CODE FIX BUILD')==1
  and count('custom stratagem REGISTERED laser_maxigun ')==1 and d~=nil and d.kind=='expendable'and d.delivery.variant==true
  and counts.writes==0,'registered='..count('custom stratagem REGISTERED laser_maxigun '))
 step('its carrier group is weapon (requested); its pool is the Maxigun alone; it fires the LAS-58 Talon\'s round 144 '
  ..'(conventional_plain, its package a dependency); its model is the mod\'s own, model_use the Mod Options choice '
  ..'(default: check)',d~=nil and d.group=='weapon'and d.group_source=='requested'
  and table.concat(d.delivery.pool,',')=='M-1000 Maxigun'and d.delivery.round.type==144
  and d.delivery.round.class=='conventional_plain'and d.pod_deps~=nil
  and require('hd2runtime/runtime/model_resources').issued(d.delivery.model)
  and custom.model_use_value(d.delivery.model_use)=='check',tostring(d and d.group))
 local wm=require('hd2runtime/runtime/event_world')
 local world=assert(wm.open())
 local clone=require('hd2runtime/runtime/weapon_clone')
 local ok,why=clone.prove(world)
 local uok,uwhy=clone.prove_model_consumers(world)
 step('the clone pins and every UnitPath consumer pin prove on the real game.dll',ok==true and uok==true,
  tostring(why)..' / '..tostring(uwhy))
 local r,code,reason=clone.inspect(world,'M-1000 Maxigun')
 step('the Maxigun\'s records on the real entity region: one owner each, the game\'s type tables pointing at them, the '
  ..'exact native bytes (read-only)',r~=nil and r.native==true and r.records==4 and counts.writes==0,
  r and('native '..tostring(r.native)..', '..r.records..' records')or(tostring(code)..' '..tostring(reason)))
 local assets=require('hd2runtime/core/assets')
 local dl=d and custom.expendable_delivery(d,{weapon='M-1000 Maxigun'},'variant')
 step('its own pod on the real catalogue: the Maxigun firing the Talon\'s 144 and its backpack; its call-in packages '
  ..'known and complete',assets.call_in_complete('M-1000 Maxigun')==true and dl~=nil
  and dl.items['43A58CB89CFA197C'].projectile==144 and dl.items['056DE1C5E21E723E'].kind=='backpack',
  tostring(dl and dl.stratagem))
 local loadout=require('hd2runtime/runtime/stratagem_loadout')
 local saved=loadout.saved(world)
 local ids={}
 for k,pair in ipairs(saved and saved.pairs or{})do ids[k]=pair.id end
 local present,who=custom.lobby_picks(world,ids)
 local WC=require('hd2runtime/runtime/weapon_carriers')
 local reason2,weapon=WC.unavailable('laser_maxigun','M-1000 Maxigun',present,{},{who=who})
 local mine=present[WC.stable_id('M-1000 Maxigun')]
 step('the availability against the real loadout and records (read-only; no fallback): '..tostring(reason2 or
  ('available, carrier weapon '..tostring(weapon and weapon.weapon))),(mine and reason2~=nil)
  or(not mine and reason2==nil and weapon~=nil and weapon.weapon=='M-1000 Maxigun'),tostring(reason2))
 local desc=custom.describe('laser_maxigun')
 step('describe: group weapon',desc~=nil and desc.group=='weapon',tostring(desc and desc.group))
 local h=clone.apply({carrier='M-1000 Maxigun',variant=true,round={type=144,package=d.delivery.round.package,
  label='LAS-58 Talon'}})
 for _=1,100 do if h.status~='pending'then break end;frame()end
 step('a variant conversion aboard the ship is refused (NOT_IN_MISSION); nothing written',h.status=='refused'
  and h.code=='NOT_IN_MISSION'and counts.writes==0,tostring(h.code))
 return results
end
"""
EXTRAS['example-laser-maxigun'] = {'after': EXAMPLE_LASER_MAXIGUN, 'readOnly': True, 'menu': MENU_STUB, 'options': True}
# The EAT-17C Cluster Expendable (proof/EAT17CExample 0.2.0, split out of ExtraStratagems 0.1.1): the same expendable
# group checks as the EAT-17G, for its own id, banner and round (the RL-77 Airburst's rocket, type 312).
def _eat17c_scenario():
    text = EXAMPLE_EAT17G
    for old, new in (("count('EAT40ExpendableGas 0.3.0 BUILD')==1", "count('EAT77ExpendableCluster 0.3.0 BUILD')==1"),
            ("'eat17g_clone'", "'eat_cluster'"), ("REGISTERED eat17g_clone ", "REGISTERED eat_cluster "),
            ("which fire '\n  ..'the EAT-17\\'s round at the full level", "which fire '\n  ..'the RL-77\\'s round at the "
            "full level"), ("dl.items['B2B5E0D185605F9E'].projectile==132", "dl.items['B2B5E0D185605F9E'].projectile==312")):
        if old not in text:
            raise AssertionError('the EAT-17G scenario changed: ' + old)
        text = text.replace(old, new)
    return text
EXTRAS['example-eat17c'] = {'after': _eat17c_scenario(), 'readOnly': True}


# The EAT-23 Expendable EMS (proof/EAT23Example 0.1.0): the EAT-40's checks, its rockets bursting into the Orbital EMS
# Strike's field instead of the gas cloud.
def _eat23_scenario():
    text = EXAMPLE_EAT17G
    for old, new in (("count('EAT40ExpendableGas 0.3.0 BUILD')==1", "count('EAT23ExpendableEMS 0.1.0 BUILD')==1"),
            ("'eat17g_clone'", "'eat23_ems'"), ("REGISTERED eat17g_clone ", "REGISTERED eat23_ems ")):
        if old not in text:
            raise AssertionError('the EAT-40 scenario changed: ' + old)
        text = text.replace(old, new)
    return text


EXTRAS['example-eat23'] = {'after': _eat23_scenario(), 'readOnly': True}


# The MS-N223 Shredder Silo (proof/ShredderSiloExample 0.1.0; runtime/custom_silos.lua; research/silo-payload,
# research/event-actions "Cyborg Production Unit"): the custom stratagem checks of the other examples (its group's resolved
# policy: a blue support carrier, the Solo Silo's blue colour set), then on the real game.dll and memory: the silo
# delivery as reviewed (the rack's missile and remote, the missile's own detonation type), the explosion queue reader
# on the real queue, the Cyborg Production Unit's settings record and its two objective packages (effect and sound) by
# identity, the blast refused aboard the ship, a detonation watch that ends without a blast; nothing is written.
SILO_STEPS = r'''
 local silos=require('hd2runtime/runtime/custom_silos')
 local s=d.delivery
 step('the silo delivery as reviewed: the MS-11 Solo Silo\'s own pod, its rack\'s missile (its own detonation 135) and '
  ..'laser remote; the blast the Cyborg Production Unit\'s, the NUX-223 Hellbomb\'s the fallback',d.kind=='silo'
  and s.stratagem=='MS-11 Solo Silo'and s.missile=='DDDB2910FF2B24E9'and s.remote=='FC13460592CA79AA'
  and s.detonation==135 and s.blast=='Cyborg Production Unit'and s.fallback=='NUX-223 Hellbomb'
  and package.loaded['hd2runtime/runtime/custom_silos']~=nil,tostring(s.missile)..' '..tostring(s.blast))
 local q=wm.explosion_queue(world,silos.QUEUE_SLOTS)
 step('the explosion queue reader reads the real queue (read-only): '..tostring(q and#q)..' entries',q~=nil
  and#q==silos.QUEUE_SLOTS and counts.writes==0,tostring(q and#q))
 local actions=require('hd2runtime/api/actions')
 local t=actions.explosion_target('Cyborg Production Unit')
 step('the Cyborg Production Unit explosion: its settings record on the real game (type 293) and its two objective '
  ..'packages, the effect\'s and the sound\'s, by identity',t~=nil and t.type==293 and wm.explosion_settings(world,293)~=nil
  and#t.dependencies==2 and t.dependencies[1].package=='0x9BFA7EB1324C29A5'
  and t.dependencies[2].package=='0xCF1B36D0765B57A5',tostring(t and t.type))
 local resident=actions.explosion_resident(world.runtime,t)
 local action,why=silos.blast(d,{x=1,y=2,z=3},'packaged')
 step('the blast aboard the ship is refused (its packages '..(resident and'resident'or'not resident')..'); nothing '
  ..'written',action==nil and why~=nil and counts.writes==0,tostring(why))
 local events={}
 local w=silos.watch({missile=4242,detonation=135,label='packaged'},function(e)events[#events+1]=e.kind end)
 for _=1,5 do frame()end
 local text=table.concat(events,' ')
 step('a detonation watch aboard the ship ends without a blast: '..text,w.status=='complete'
  and not text:find('detonated',1,true)and counts.writes==0,text)
 local desc=custom.describe(ID)
 step('describe: the silo\'s own vanilla rack (two items)',desc~=nil and desc.pod~=nil
  and desc.pod.rack=='0xDE18775FA447A9BF'and desc.pod.count==2,tostring(desc and desc.pod and desc.pod.rack))
 return results
end
'''


def _silo_scenario():
    text = EXAMPLE_CUSTOM_STRATAGEM % {'id': 'shredder_silo', 'banner': 'ShredderSilo 0.1.0 BUILD', 'beacon': 'support',
        'families': "{'support','backpack'}", 'colour_set': 2}
    for old, new in (("policy=d.policy,", "policy=d.alloc_policy or d.policy,"),
            (" return results\nend\n", SILO_STEPS)):
        if old not in text:
            raise AssertionError('the custom stratagem scenario changed: ' + old)
        text = text.replace(old, new)
    return text


EXTRAS['example-shredder-silo'] = {'after': _silo_scenario(), 'readOnly': True}
# Pelican CAS 0.7.1 (proof/PelicanCasExplosive: the aim point, the 15 mrad spread and the explosive rounds in Mod Options;
# the same resource as proof/PelicanCasExample) and the two Pelican support stratagems split out of ExtraStratagems 0.1.1
# (proof/PelicanEmsExample, proof/PelicanGasExample): the same custom stratagem checks as the other examples.
for _name, _id, _banner, _extra in (
        ('example-pelican-cas-explosive', 'pelican_close_air_support', 'PelicanGatlingSupport 0.8.0 BUILD', {}),
        ('example-pelican-cannon', 'pelican_cannon_support', 'PelicanCannonSupport 0.1.0 BUILD', {}),
        ('example-pelican-ems', 'pelican_ems_support', 'PelicanEmsSupport 0.3.0 BUILD', {}),
        ('example-pelican-gas', 'pelican_gas_support', 'PelicanGasSupport 0.3.0 BUILD', {})):
    EXTRAS[_name] = dict({'after': EXAMPLE_CUSTOM_STRATAGEM % {'id': _id, 'banner': _banner, 'beacon': 'offensive',
        'families': "{'orbital','eagle','sentry','emplacement','mine','support','backpack'}", 'colour_set': 0},
        'readOnly': True}, **_extra)
# The experimental multiplayer scope of custom stratagems in the PACKAGED runtime (0.30.0-dev; runtime/multiplayer.lua,
# runtime/custom_multiplayer.lua), with the HMG Sentry example registered. Read-only: the scope's semantics; the native
# set from the real stratagem records as first seen; the lobby reader on real memory; and, with a second player's
# record shown in Lua only (nothing in memory), the executor's solo guard refusing a caller without the scope and
# passing a custom stratagem call's (the next guard decides: nothing is fired or written).
CUSTOM_MULTIPLAYER = r'''
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local world_module=require('hd2runtime/runtime/event_world')
 local world=world_module.open()
 local mp=require('hd2runtime/runtime/multiplayer')
 local cmp=require('hd2runtime/runtime/custom_multiplayer')
 local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
 local handles=require('hd2runtime/runtime/handles')
 local real={definition='hmg_sentry',call_id='hmg_sentry#1'}
 mp.mark_call(real)
 local code=mp.solo_guard(2,false)
 step('the scope: a marked custom stratagem call only; a forged call table is not one',mp.call_allowed(real)
  and not mp.call_allowed({definition='x',call_id='x#1',multiplayer=true})and mp.solo_guard(1,false)==nil
  and mp.solo_guard(2,true)==nil and code=='NOT_SOLO','scope')
 cmp.reset_for_tests()
 local records=slots.records(world)
 local native=cmp.native(world,{},nil)
 local ids=0
 for _ in pairs(native.present)do ids=ids+1 end
 step(('the native set from the real stratagem records as first seen: %d record(s), %d stable ids (read-only)')
  :format(#native.peers,ids),records~=nil and#records>=1 and#native.peers==#records and ids>0 and counts.writes==0,
  tostring(records and#records))
 local okl,list,lwhy=pcall(require('hd2runtime/runtime/stratagem_selector').lobby_records,world)
 step('the lobby reader on real memory (read-only; '..(okl and list and(#list..' lobby record(s)')or tostring(lwhy or list))
  ..')',okl and counts.writes==0,tostring(list))
 local state0,record0,avatar0=world_module.game_state,slots.local_record,handles.local_avatar
 world_module.game_state=function()return {mission=true,host=true}end
 slots.local_record=function()return {records=2,entries={},address=0,state=0}end
 handles.local_avatar=function()return nil,'no avatar (the scenario stops here)'end
 local executor=require('hd2runtime/runtime/bombardment_executor')
 local h1,c1,r1=executor.start({target={x=0,y=0,z=0}})
 local h2,c2=executor.start({target={x=0,y=0,z=0},multiplayer=true})
 world_module.game_state,slots.local_record,handles.local_avatar=state0,record0,avatar0
 step('two stratagem records: a caller without the scope is refused NOT_SOLO; a custom stratagem call passes the solo '
  ..'guard (the next guard decides); nothing fired or written',h1==nil and c1=='NOT_SOLO'
  and tostring(r1):find('only a custom stratagem call',1,true)~=nil and h2==nil and c2=='NO_LOCAL_AVATAR'
  and counts.writes==0,tostring(c1)..' / '..tostring(c2))
 local builds=0
 for _,line in ipairs(lines)do if line:find('EXPERIMENTAL CUSTOM MP FAIL-CLOSED BUILD r9 (custom-mp/1;',1,true)then builds=builds+1 end end
 step('the packaged runtime names its build once: EXPERIMENTAL CUSTOM MP FAIL-CLOSED BUILD r9 (custom-mp/1;',builds==1,tostring(builds))
 -- The teammate stratagem HUD (runtime/stratagem_slot_overlay.lua mission_remote_slots) on real memory, read-only: its
 -- pins prove on this build; a solo snapshot has no teammate card drawn (aboard the ship the mission HUD is not shown).
 local overlay=require('hd2runtime/runtime/stratagem_slot_overlay')
 local game=world_module.game_state(world)
 local okc,cards,cwhy=pcall(overlay.teammate_cards,world)
 local mission_hud=game and game.mission
 step('the teammate HUD on real memory: its pins proven; '..(mission_hud and'no teammate card drawn in a solo mission'
  or'the mission HUD not shown aboard the ship')..' (read-only; '..tostring(okc and cards and(#cards..' panel(s) drawn')
  or cwhy or cards)..')',okc and counts.writes==0 and(mission_hud and cards~=nil and#cards==0
  or not mission_hud and cards==nil and tostring(cwhy):find('is not shown',1,true)~=nil),tostring(cwhy or cards))
 local asked=0
 local follower=overlay.mission_remote_slots(function()asked=asked+1;return {['5555666677778888']={[0]='hmg_sentry'}},{}end)
 for _=1,5 do frame()end
 follower.stop()
 local teammate_lines=0
 for _,line in ipairs(lines)do if line:find('TEAMMATE HUD OVERLAY',1,true)then teammate_lines=teammate_lines+1 end end
 step('its follower, given a synced teammate, draws and logs nothing on a solo snapshot; nothing written',asked>0
  and teammate_lines==0 and counts.writes==0,tostring(asked)..' / '..tostring(teammate_lines))
 return results
end
'''
EXTRAS['custom-stratagem-multiplayer'] = {'after': CUSTOM_MULTIPLAYER, 'readOnly': True}
# RuntimePeerHelloProof 0.1.0 (the Runtime-to-Runtime peer channel: runtime/peer_channel.lua and
# runtime/peer_protocol.lua; research/peer-messaging-F5FEE03DCFDB.json) on the shipped artifact and the snapshot's real
# game.dll, executable and memory, late resource lookups disabled. The proof loads and the channel and protocol were
# loaded at startup; every pin proves on the real images; the real engine registry, PlayFab table and both member-data
# slots are the pinned functions; the real lobby is joined with this machine's own session peer as its one member. The
# overlay adapter cannot call game functions, so the post waits (UNAVAILABLE) and nothing is called. Then the two engine
# calls are replaced by recording stubs (scaffolding): after the 10 s join delay the hello is posted exactly once
# through the real set_member_data entry with the real engine lobby, and every read goes through the real member_data
# entry for the snapshot's one member (this machine). Nothing is written.
PROOF_PEER_HELLO = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function count(text)local n=0;for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end;return n end
 for _=1,30 do frame()end
 local channel=package.loaded['hd2runtime/runtime/peer_channel']
 step('the proof loads from the archive; the peer channel and protocol were loaded at startup; nothing is written',
  count('RuntimePeerHelloProof 0.1.0 PEER HELLO BUILD')==1 and channel~=nil
  and package.loaded['hd2runtime/runtime/peer_protocol']~=nil and counts.writes==0,'')
 local W=require('hd2runtime/runtime/event_world')
 local world=assert(W.open())
 local ok,why=channel.prove(world)
 step('every pin proves on the real game.dll and executable',ok==true,tostring(why))
 local PM=require('hd2runtime/domains/peer_messaging')
 local registry=world.view.pointer(world.game+PM.api.registryGlobal)
 local T=registry and world.view.pointer(registry+PM.api.table)
 step('the real engine registry, PlayFab table and both member-data slots are the pinned functions',
  registry==world.exe+PM.api.registry and T==world.exe+PM.api.tableRva
  and world.view.pointer(T+PM.api.memberData)==world.exe+PM.api.memberDataRva
  and world.view.pointer(T+PM.api.setMemberData)==world.exe+PM.api.setMemberDataRva,'')
 local lobby,code,lwhy=channel.lobby(world)
 local lo,hi=W.local_peer(world)
 local me=lo and W.peer_hex(lo,hi)
 step('the real lobby is joined (the wrapper flag, the engine lobby, PlayfabLobby state 3 and handle) with this '
  ..'machine\'s own session peer as its one member',lobby~=nil and #lobby.members==1 and lobby.members[1].peer==me
  and lobby.members[1]['local']==true and lobby.local_peer==me and lobby.id:find('^cv2:')~=nil,
  tostring(code)..' '..tostring(lwhy))
 step('without native calls the post waits (UNAVAILABLE): nothing is called or written',
  count('PEER CHANNEL: post waiting (UNAVAILABLE')==1 and count('PEER CHANNEL POSTED')==0 and counts.writes==0,'')
 local posts,reads={},{}
 world.runtime.native_lobby_publish=function(entry,engine,key,value)
  posts[#posts+1]={entry=entry,engine=engine,key=key,value=value}
  return 0
 end
 world.runtime.native_lobby_read=function(entry,engine,plo,phi,key)
  reads[#reads+1]={entry=entry,engine=engine,peer=W.peer_hex(plo,phi),key=key}
  return nil
 end
 for _=1,150 do frame()end
 local p=posts[1]
 step('the hello is posted exactly once, after the join delay, through the real set_member_data entry with the real '
  ..'engine lobby',#posts==1 and p.entry==world.exe+PM.api.setMemberDataRva and p.engine==lobby.engine
  and p.key=='hd2rt'and p.value:find('^hd2rt/1;[^;]+;811C9DC5;1;%-,%-,%-,%-$')~=nil
  and count('PEER CHANNEL POSTED: hd2rt = "hd2rt/1;')==1,'posts='..#posts..' '..tostring(p and p.value))
 local only=#reads>0
 for _,r in ipairs(reads)do
  only=only and r.entry==world.exe+PM.api.memberDataRva and r.engine==lobby.engine and r.peer==me and r.key=='hd2rt'
 end
 step('every read goes through the real member_data entry, for the snapshot\'s one member (this machine) only',only,
  'reads='..#reads)
 step('the proof reports the lobby member as a session player',count('every lobby member is a session player: yes')==1,'')
 step('nothing is written',counts.writes==0,tostring(counts.writes))
 return results
end
"""
EXTRAS['proof-peer-hello'] = {'after': PROOF_PEER_HELLO, 'readOnly': True}
# The client-write proof (runtime/multiplayer.lua host_guard; docs/research/runtime-peer-messaging-F5FEE03DCFDB.md
# section 10), with the Gas EAT example, on the shipped artifact and a real MISSION snapshot whose host condition is
# overlaid as absent (seed_client: the game mode's authority bit cleared) and whose first unlimited loadout entry is the
# token (seed_payload_mission). The Gas EAT's carrier allocated on the real catalogue; this machine's OWN record entry
# converted to it: an unmarked conversion and a marked one with the proof off are refused NOT_HOST with nothing
# written; inside the proof the same conversion the host makes (1 write on the real record, every other entry and the
# count unchanged), then restored exactly. Aboard the ship nothing is converted.
CLIENT_WRITE_PROOF = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
 local function count(text)local n=0;for _,line in ipairs(lines)do if line:find(text,1,true)then n=n+1 end end;return n end
 local function settle(handle)for _=1,600 do if handle.status~='pending'then break end;frame()end;return handle end
 for _=1,60 do frame()end
 local wm=require('hd2runtime/runtime/event_world')
 local world=assert(wm.open())
 local state=wm.game_state(world)
 if not(state and state.mission)then
  step('aboard the ship: nothing to convert; nothing written',counts.writes==0,'')
  return results
 end
 step('the host condition is absent on the real mission snapshot (the overlay): this machine is a client',
  state.host==false,tostring(state.host))
 local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
 local selector=require('hd2runtime/runtime/stratagem_selector')
 local loadout=require('hd2runtime/runtime/stratagem_loadout')
 local mp=require('hd2runtime/runtime/multiplayer')
 local custom=require('hd2runtime/runtime/custom_stratagems')
 local A=require('hd2runtime/runtime/carrier_allocator')
 local record=assert(slots.local_record(world))
 local token_type=loadout.type_of(world,3523620028)
 local order,slot,picks={},nil,{}
 for _,e in ipairs(record.entries)do if e.granted==0 then picks[#picks+1]=e end end
 for k,e in ipairs(picks)do
  order[k]=loadout.id_of(world,e.type)
  if e.type==token_type and not slot then slot=k-1 end
 end
 step('the seeded token is one of this machine\'s own loadout entries',slot~=nil,'')
 if not slot then return results end
 selector.set_virtual_slots_for_tests({slots={[slot]={definition='eat17_gas',token=3523620028,type=token_type}},
  pairs=order})
 local d=custom.get('eat17_gas')
 local excl={}
 for _,def in ipairs(custom.list())do for _,n in ipairs(def.exclude)do excl[#excl+1]=n end end
 local a=A.allocate_policies(world,{{id='eat17_gas',label='Gas EAT',token='Orbital Precision Strike',policy=d.policy}},
  {},excl)
 local mine=a.ready and a.assignments.eat17_gas
 step('the Gas EAT\'s support carrier on the real catalogue: '..tostring(mine and mine.carrier),mine~=nil
  and mine.beacon=='support','')
 if not mine then return results end
 local before=record.entries
 local writes=counts.writes
 local plain=settle(selector.convert_virtual('eat17_gas',nil,mine.carrier,{multiplayer=true}))
 local marked=settle(selector.convert_virtual('eat17_gas',nil,mine.carrier,{multiplayer=true,client=true}))
 step('a client\'s conversion unmarked, or marked with the proof off: NOT_HOST, nothing written',plain.code=='NOT_HOST'
  and marked.code=='NOT_HOST'and counts.writes==writes,tostring(plain.code)..' '..tostring(marked.code))
 mp.enable_client_proof(true)
 local converted=settle(selector.convert_virtual('eat17_gas',nil,mine.carrier,{multiplayer=true,client=true}))
 local after=slots.local_record(world)
 local same=after~=nil and#after.entries==#before
 for k,e in ipairs(before)do
  local now=after and after.entries[k]
  if now and k-1~=(converted.indices and converted.indices[1])and now.type~=e.type then same=false end
 end
 local index=converted.indices and converted.indices[1]
 step('inside the proof: this client\'s own record entry converted to '..mine.carrier..' on the real record (1 write; '
  ..'every other entry unchanged), as the host\'s conversion',converted.status=='converted'and counts.writes==writes+1
  and after~=nil and index~=nil and after.entries[index+1].type==mine.type and same,tostring(converted.code)..' '
  ..tostring(converted.reason))
 local back=settle(slots.restore())
 mp.enable_client_proof(false)
 local restored=slots.local_record(world)
 step('restored exactly: the entry holds the token again',back.status=='restored'and back.exact==true and restored~=nil
  and restored.entries[index+1].type==token_type,tostring(back.code))
 return results
end
"""
# missionOnly: its writes apply on a mission snapshot only (aboard the ship it writes nothing, by design);
# tests/test_packaged_runtime.py runs it on a retained mission snapshot and requires its writes there.
EXTRAS['client-write-proof'] = {'after': CLIENT_WRITE_PROOF, 'seedPayload': True, 'seedClient': True, 'missionOnly': True}
EXTRAS['proof-extraction-pelican-probe'] = {'after': PROOF_PELICAN_PROBES, 'readOnly': True}
EXTRAS['proof-pelican-turret-probe'] = {'after': PROOF_PELICAN_PROBES, 'readOnly': True}
EXTRAS['proof-pelican-cas'] = {'menu': MENU_STUB, 'after': PROOF_PELICAN_CAS,
    'seeds': [('mods/skyeshade/hd2runtime_pelican_cas_proof', 'pelican_close_air_support')], 'seedFamily': True,
    'seedPayload': True}
EXTRAS['proof-text-write'] = {'menu': MENU_STUB, 'after': PROOF_TEXT_WRITE, 'seed': PROOF_IMAGE, 'seedFamily': True}
EXTRAS['proof-text-write-refused'] = {'menu': MENU_STUB, 'after': PROOF_TEXT_WRITE_REFUSED, 'seed': PROOF_IMAGE,
    'seedFamily': True, 'seedRegistryFull': True}


# RuntimeVersionWarningTest (requires 0.31.0) and three more wrapped mods, loaded as the loader would: a prerelease
# requirement above it (0.31.1-rc.1), one equal to the installed runtime and one older. The two too-new mods fail
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
 step('each too-new mod is logged once with its exact requirement',count('requires HD2Runtime 0.31.0 or newer')==1
  and count('requires HD2Runtime 0.31.1-rc.1 or newer')==1 and count('needs_equal')==0 and count('needs_older')==0,
  table.concat(lines,' | '):sub(1,400))
 step('no warning before the ship is stable',#shown==0,tostring(#shown))
 for _=1,120 do frame()end
 local installed=compatibility.installed()
 step('one aggregated warning with the highest requirement',#shown==1 and shown[1].title=='HD2Runtime update required'
  and shown[1].message=='One or more installed mods require a newer HD2Runtime version.\n\nRequired version: '
   ..'0.31.1-rc.1\nInstalled version: '..installed..'\n\nPlease update HD2Runtime.',
  shown[1]and shown[1].message or'none')
 compatibility.require_runtime('mods/test/needs_031','0.31.0','Repeat')
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
        sdk.wrap_addon('mods/test/needs_0311', '0.31.1-rc.1', 'return true', 'Needs0311'),
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


# What the local player holds and wears (docs/player-equipment.md), from the built ZIP on the reference ship snapshot:
# every equipment pin proves on the snapshot's game.dll, the loadout is the snapshot's own (JAR-5 Dominator, P-113
# Verdict, G-4 Gas x3, no support weapon, no backpack), and the Supply Pack self-use is refused aboard the ship
# without any native call (readOnly: exactly zero overlay writes).
PLAYER_EQUIPMENT_LIVE = r"""
return function(frame,watches,counts,lines)
 local results={}
 local function step(name,ok,detail)results[#results+1]={name=name,passed=ok==true,detail=detail}end
""" + EVENTS_WORLD + r"""
 local equipment=require('hd2runtime/runtime/player_equipment')
 local world=require('hd2runtime/runtime/event_world').open()
 local proven,why=equipment.prove(world)
 step('every player equipment pin proves on the snapshot game.dll',proven==true,tostring(why))
 local loadout,reason=player:loadout()
 step('the loadout is the snapshot\'s own',loadout~=nil and loadout.primary and loadout.primary.name=='JAR-5 Dominator'
  and loadout.secondary and loadout.secondary.name=='P-113 Verdict'and loadout.support==nil and loadout.backpack==nil
  and loadout.throwable and loadout.throwable.name=='G-4 Gas'and loadout.throwable.count==3,
  tostring(reason)..' '..tostring(loadout and loadout.primary and loadout.primary.name))
 local pack,none=player:backpack()
 step('no backpack is worn aboard the ship',pack==nil and tostring(none):find('NO_BACKPACK',1,true)~=nil,tostring(none))
 local ammo=player:ammo('primary')
 step('the primary magazine reads within the catalog',ammo~=nil and ammo.feed=='magazine'and ammo.capacity==15
  and ammo.rounds<=15 and ammo.spare_magazines<=ammo.max_spare_magazines,tostring(ammo and ammo.rounds))
 local action=hd2.actions.resupply_from_pack(player)
 step('the Supply Pack self-use is refused aboard the ship',action.status=='refused'and action.code=='NOT_IN_MISSION',
  tostring(action.code)..' '..tostring(action.reason))
 local loaded=0
 for _,line in ipairs(lines)do if line:find('AUTO SUPPLY PACK 0.1.0 BUILD: loaded',1,true)then loaded=loaded+1 end end
 step('the example mod loaded once',loaded==1,'loaded='..loaded)
 return results
end
"""
EXTRAS['example-auto-supply-pack-test'] = {'after': PLAYER_EQUIPMENT_LIVE, 'readOnly': True}


SCENARIOS = {
    'player-weapon-patch': lambda: SIMPLE_PATCH,
    'runtime-version-label': lambda: 'return true',
    'projectile-active-sources': lambda: PROJECTILE_SOURCES,
    'projectile-donors': lambda: PROJECTILE_DONORS,
    'projectile-donors-all': projectile_donors_all,
    'registration-isolation': lambda: REGISTRATION_ISOLATION,
    'legacy-sdk-027-purifier': lambda: legacy_scenario('0.27.0', 'legacy-purifier-drag'),
    'sdk-028-purifier-without-ack': lambda: legacy_scenario('0.28.0', 'current-purifier-drag'),
    'sdk-028-purifier-with-ack': lambda: legacy_scenario('0.28.0', 'current-purifier-drag-ack', acknowledged=True),
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
    'user-report-hmg-read-budget': lambda: user_report('HMG', HMG_READ_BUDGET),
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
    'stratagem-calldown-code': lambda: STRATAGEM_CALLDOWN,
    'stratagem-presentation': lambda: STRATAGEM_PRESENTATION,
    'proof-text-write': lambda: proof('CustomStratagemP0Proof'),
    'proof-virtual-slot': lambda: proof('VirtualSlotProof'),
    'proof-virtual-selector': lambda: proof('VirtualSelectorProof'),
    'proof-render-order': lambda: proof('RenderOrderProof'),
    'proof-custom-stratagem-panel': lambda: proof('CustomStratagemPanelProof'),
    'proof-slot-highlight': lambda: proof('SlotHighlightProof'),
    'proof-panel-icon': lambda: proof('PanelIconProof'),
    'proof-selection-sound': lambda: proof('SelectionSoundProof'),
    'proof-slot-texture-probe': lambda: proof('SlotTextureProbe'),
    'proof-slot-overlay': lambda: proof('SlotOverlayProof'),
    'proof-gas-barrage-mission': lambda: proof('GasBarrageMissionProof'),
    'proof-gas-barrage-payload': lambda: proof('GasBarragePayloadProof'),
    'proof-gas-barrage-cooldown': lambda: proof('GasBarrageCooldownProof'),
    'proof-beacon-probe': lambda: proof('BeaconProbe'),
    'proof-beacon-redirect': lambda: proof('BeaconRedirectProof'),
    'proof-beacon-timing': lambda: proof('BeaconTimingProof'),
    'proof-gas-shells': lambda: proof('GasShellProof'),
    'proof-pod-probe': lambda: proof('PodProbe'),
    'proof-pelican-probe': lambda: proof('PelicanProbe'),
    'proof-pelican-spawn': lambda: proof('PelicanSpawnProof'),
    'proof-pelican-cas': lambda: proof('PelicanCasProof'),
    'proof-pelican-orbit': lambda: proof('PelicanOrbitProof'),
    'proof-extraction-pelican-probe': lambda: proof('ExtractionPelicanProbe'),
    'proof-pelican-turret-probe': lambda: proof('PelicanTurretProbe'),
    'proof-pelican-gatling': lambda: proof('PelicanGatlingProof'),
    'proof-pelican-weapon-behavior': lambda: proof('PelicanWeaponBehaviorProof'),
    'proof-pelican-gatling-ai': lambda: proof('PelicanGatlingAIProof'),
    'example-pelican-cas': lambda: proof('PelicanCasExample'),
    'example-gas-barrage': lambda: proof('GasBarrageExample'),
    'example-gas-eat': lambda: proof('GasEatExample'),
    'example-eat17g': lambda: proof('EAT17GExample'),
    'example-eat17c': lambda: proof('EAT17CExample'),
    'example-laser-maxigun': lambda: proof('LaserMaxigunExample'),
    'example-pelican-cas-explosive': lambda: proof('PelicanCasExplosive'),
    'example-pelican-ems': lambda: proof('PelicanEmsExample'),
    'example-pelican-gas': lambda: proof('PelicanGasExample'),
    'example-pelican-cannon': lambda: proof('PelicanCannonExample'),
    'example-orbital-ems-barrage': lambda: proof('OrbitalEmsBarrageExample'),
    'example-eat23': lambda: proof('EAT23Example'),
    'example-shredder-silo': lambda: proof('ShredderSiloExample'),
    'example-hmg-sentry': lambda: proof('HmgSentryExample'),
    'example-eagle-stun-rocket-pods': lambda: proof('EagleStunRocketPodsExample'),
    'custom-stratagem-multiplayer': lambda: proof('HmgSentryExample'),
    'proof-peer-hello': lambda: proof('RuntimePeerHelloProof'),
    'client-write-proof': lambda: proof('GasEatExample'),
    'proof-text-write-refused': lambda: proof('CustomStratagemP0Proof'),
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
    """Map resource-name hash to Lua source for the runtime archive inside a ZIP (a Lua-only archive, or one with
    other resources too: the Runtime's fonts)."""
    from hd2_archive import LUA_TYPE, read_archive
    with zipfile.ZipFile(path) as package:
        name = next(n for n in package.namelist() if n.endswith('.patch_0'))
        data = package.read(name)
        gpu = package.read(name + '.gpu_resources') if name + '.gpu_resources' in package.namelist() else b''
    found = {}
    for (kind, name_hash), (main, _gpu) in read_archive(data, gpu).items():
        if kind != LUA_TYPE:
            continue
        length, version = struct.unpack_from('<II', main, 0)
        assert version == 2, 'unexpected Lua resource version'
        found[name_hash] = main[8:8 + length]
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
-- An index of the overlay: every entry's address in ascending order and the longest entry. A read applies only the
-- entries it touches (a binary search, then forward); when two of those overlap each other it scans every entry in
-- table order instead, so a read returns exactly the bytes a scan of every entry would.
local overlay_sorted,overlay_longest={},0
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
-- Runtime-owned blocks (custom projectile rows): a Lua overlay at addresses the snapshot does not map. They are the
-- Runtime's own memory, never game memory, so never an overlay write; SpawnProjectile itself is not provided.
local owned,next_owned={},0x7FFE00000000
counts.owned_blocks=0
function runtime.owned_block(size)
 assert(type(size)=='number' and size>0 and size<=4096 and size%8==0,'owned block size')
 local address=next_owned;next_owned=next_owned+0x1000
 owned[address]=string.rep('\0',size);counts.owned_blocks=counts.owned_blocks+1
 return address
end
function runtime.owned_write(address,bytes)
 assert(owned[address] and #owned[address]==#bytes,'not a whole Runtime-owned block')
 owned[address]=bytes;return true
end
-- Runtime-owned permanent blocks (a Runtime text table): the same Lua overlay memory, filled once; never game memory,
-- so never an overlay write.
counts.permanent_blocks=0
function runtime.permanent_block(bytes)
 assert(type(bytes)=='string' and #bytes>0 and #bytes<=65536,'permanent block size')
 local address=next_owned;next_owned=next_owned+0x10000
 owned[address]=bytes;counts.permanent_blocks=counts.permanent_blocks+1
 return address
end
function runtime.read(at,n)
 for address,bytes in pairs(owned)do
  if at>=address and at+n<=address+#bytes then return bytes:sub(at-address+1,at-address+n)end
 end
 local bytes,why=source.read(at,n)
 if not bytes then return nil,why end
 for address,value in pairs(SEED or{})do
  if address<at+n and address+#value>at then
   local first=math.max(address,at);local last=math.min(address+#value,at+n)
   bytes=bytes:sub(1,first-at)..value:sub(first-address+1,last-address)..bytes:sub(last-at+1)
  end
 end
 local sorted,count=overlay_sorted,#overlay_sorted
 if count==0 then return bytes end
 local lo,hi,low=1,count+1,at-overlay_longest
 while lo<hi do
  local mid=math.floor((lo+hi)/2)
  if sorted[mid]<=low then lo=mid+1 else hi=mid end
 end
 -- The touched entries in address order: the read is cut into pieces and joined once (rebuilding a long read per
 -- entry makes many near-identical long strings, which this LuaJIT's sampled string hash chains together).
 local parts,pos,reach,overlapping=nil,1,nil,false
 for i=lo,count do
  local address=sorted[i]
  if address>=at+n then break end
  local value=overlay[address]
  if address+#value>at then
   if reach and address<reach then overlapping=true;break end
   local first=math.max(address,at);local last=math.min(address+#value,at+n)
   parts=parts or{}
   parts[#parts+1]=bytes:sub(pos,first-at)
   parts[#parts+1]=value:sub(first-address+1,last-address)
   pos=last-at+1
   reach=math.max(reach or 0,address+#value)
  end
 end
 if not overlapping then
  if not parts then return bytes end
  parts[#parts+1]=bytes:sub(pos)
  return table.concat(parts)
 end
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
 counts.writes=counts.writes+1
 if overlay[at]==nil then
  local lo,hi=1,#overlay_sorted+1
  while lo<hi do
   local mid=math.floor((lo+hi)/2)
   if overlay_sorted[mid]<at then lo=mid+1 else hi=mid end
  end
  table.insert(overlay_sorted,lo,at)
 end
 overlay[at]=bytes
 if #bytes>overlay_longest then overlay_longest=#bytes end
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
-- Every registered operation, including ones the addon kept no handle for (hd2.diagnostics.operations()).
local function registered()
 local ok,list=pcall(function()return require(ENTRY).diagnostics.operations()end)
 if not ok or type(list)~='table'then return nil end
 local out={}
 for index,op in ipairs(list)do
  local legacy={}
  for _,use in ipairs(op.legacy or{})do legacy[#legacy+1]=use.field end
  out[index]={kind=op.kind,id=op.id,mod=op.mod,sdk=op.sdk,status=op.status,result=op.result,code=op.code,
   error=op.error,runs=op.runs,legacy=legacy}
 end
 return out
end
local operations_settled=registered()
if AFTER then AFTER_RESULTS=assert(loadstring(AFTER))()(frame,watches,counts,lines)end
local report={scenario=SCENARIO,settled=settled(),startup_seconds=simulated,watches=describe(),
 operations=operations_settled,
 counts={writes=counts.writes,protection_changes=counts.protection_changes,module_hashes=counts.module_hashes,
  package_requests=counts.package_requests},packages=package_log}

-- Simulated game reset: ensures must detect drift and re-apply with lookups still closed.
local ensures={}
for index,w in ipairs(watches)do
 if w.runs~=nil and w.status~='rejected' and w.status~='unavailable' then ensures[index]=w.runs end
end
if next(ensures)then
 overlay={};overlay_sorted={};overlay_longest=0;protection={}
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
report.operations_final=registered()
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


def scenario_program(scenario, addon, seed=None):
    """The scenario-specific tail that follows the prelude. seed: {address: bytes} under the write overlay."""
    return ('\nlocal SEED=' + ('{' + ','.join('[%d]=%s' % (k, lua_bytes(v)) for k, v in sorted(seed.items())) + '}'
        if seed else 'nil')
        + '\nlocal SCENARIO=' + lua(scenario) + '\nlocal ADDON=' + lua(addon)
        + '\nlocal MENU=' + (lua(EXTRAS.get(scenario, {}).get('menu')) if EXTRAS.get(scenario, {}).get('menu') else 'nil')
        + '\nlocal AFTER=' + (lua(EXTRAS.get(scenario, {}).get('after')) if EXTRAS.get(scenario, {}).get('after') else 'nil')
        # Guarded operations resolve one at a time; a large project needs a larger simulated window.
        + '\nlocal MAX_FRAMES=' + str(EXTRAS.get(scenario, {}).get('frames', 36000))
        + '\nlocal RESET_SECONDS=' + str(EXTRAS.get(scenario, {}).get('resetSeconds', 3600))
        + '\nlocal FRAME_SECONDS=' + repr(EXTRAS.get(scenario, {}).get('frameSeconds', 0.1))
        + '\nlocal AFTER_RESULTS\n' + PROGRAM)


def scenario_seed(scenario, snapshot):
    """The scenario's validation-only seed layer ({address: bytes} under the write overlay), or None."""
    spec = EXTRAS.get(scenario, {})
    seed = {}
    for item in ([spec['seed']] if spec.get('seed') else []) + list(spec.get('seeds', [])):
        seed.update(seed_family(snapshot, *item, prior=seed) if spec.get('seedFamily')
            else seed_image(snapshot, *item, prior=seed))
    if spec.get('seedRegistryFull'):
        seed.update(seed_registry_full(snapshot))
    if spec.get('seedPayload'):
        seed.update(seed_payload_mission(snapshot))
    if spec.get('seedClient'):
        seed.update(seed_client(snapshot))
    return seed or None


def run_scenario(resources, names, scenario, addon, snapshot, head=None):
    sys.path.insert(0, str(ROOT / 'sdk'))
    from tools.lua_runner import execute
    program = (head or prelude(resources, names, snapshot)) + scenario_program(scenario, addon,
        scenario_seed(scenario, snapshot))
    return json.loads(execute(program.encode()))


APPLIED = ('APPLIED', 'ALREADY_DESIRED', 'RESIDENT')


def outcome(op):
    """How one registered operation ended: applied, not_applicable, rejected or skipped."""
    status, result = op.get('status'), op.get('result')
    if status == 'rejected' or result == 'REJECTED':
        return 'rejected'
    if status in ('unavailable', 'disabled'):
        return 'not_applicable'
    if result in APPLIED and (op.get('kind') != 'ensure' or (op.get('runs') or 0) >= 1):
        return 'applied'
    return 'skipped'


def registered_operations(report):
    """Every registered operation with its outcome: as it stood once the startup settled (the expected mutation). An
    operation its own option kept inactive at startup (a default-off toggle) that applied once the scenario turned
    the option on counts as applied; one registered later (an option or event step) counts as it stood at the end."""
    settled, final = report.get('operations'), report.get('operations_final')
    if settled is None or final is None:
        return None
    # The harness JSON encoder writes an empty Lua list as {}.
    settled, final = (list(value) if isinstance(value, list) else [] for value in (settled, final))
    result = []
    for index, op in enumerate(settled):
        later = final[index] if index < len(final) else op
        state = outcome(op)
        if state == 'not_applicable' and outcome(later) == 'applied':
            op, state = later, 'applied'
        # An ensure still waiting for its Mod Options when the startup settled (only the handles an addon returns are
        # waited for) counts by what it did by the end: it applied if it ran with an applied result, even when a later
        # option step of the scenario switched it off again.
        elif (op.get('status') == 'waiting_for_options' and later.get('result') in APPLIED
                and (later.get('runs') or 0) >= 1):
            op, state = later, 'applied'
        result.append((op, state))
    return result + [(op, outcome(op)) for op in final[len(settled):]]


def check_operations(report, extras):
    """Failures for the registered operations of one scenario, and how many ended each way."""
    operations = registered_operations(report)
    if operations is None:
        return ['the packaged runtime does not list its registered operations (hd2.diagnostics.operations)'], {}
    expected_rejections = extras.get('rejected', {})
    unavailable = set(extras.get('unavailable', ()))
    legacy = {key: sorted(value) for key, value in extras.get('legacy', {}).items()}
    failures, counts = [], {'applied': 0, 'legacy': 0, 'not_applicable': 0, 'rejected_expected': 0,
        'rejected': 0, 'skipped': 0}
    seen = set()
    log = report.get('log') or []
    for op, result in operations:
        name = op.get('id') or '(no id)'
        seen.add(name)
        fields = sorted(op.get('legacy') or [])
        detail = 'status=%s result=%s error=%s' % (op.get('status'), op.get('result'), op.get('error'))
        if name in expected_rejections:
            reason = expected_rejections[name]
            if result != 'rejected':
                failures.append(f'{name}: expected a refusal ({reason}), got {result} ({detail})')
            elif reason not in str(op.get('error')) and not any(name in line and reason in line for line in log):
                failures.append(f'{name}: refused for another reason than {reason!r} ({detail})')
            else:
                counts['rejected_expected'] += 1
            continue
        if name in unavailable:
            if result != 'not_applicable':
                failures.append(f'{name}: expected an inactive (not applicable) operation, got {result} ({detail})')
            else:
                counts['not_applicable'] += 1
            continue
        if result == 'rejected':
            failures.append(f'{name}: rejected unexpectedly ({detail})')
        elif result == 'skipped':
            failures.append(f'{name}: skipped, never applied ({detail})')
        elif result == 'not_applicable':
            failures.append(f'{name}: not applied ({op.get("status")}) and the scenario does not declare it '
                'unavailable')
        counts[result] += 1
        if fields and name not in legacy:
            failures.append(f'{name}: applied only through the legacy SDK path ({", ".join(fields)}); declare it')
        if name in legacy:
            if fields != legacy[name]:
                failures.append(f'{name}: expected legacy fields {legacy[name]}, got {fields} ({detail})')
            elif result == 'applied':
                counts['legacy'] += 1
                if not any(': legacy SDK ' in line and name in line for line in log):
                    failures.append(f'{name}: applied as a legacy operation without its log line')
    for name in list(expected_rejections) + sorted(unavailable) + sorted(legacy):
        if name not in seen:
            failures.append(f'{name}: expected operation was never registered')
    return failures, counts


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
    if not str(report.get('scenario', '')).startswith('options-') and not EXTRAS.get(report.get('scenario'), {}).get(
            'options'):
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
    extras = EXTRAS.get(report.get('scenario'), {})
    failures += check_operations(report, extras)[0]
    # A mutation scenario must have written; an observing one must not have. A missionOnly scenario writes only on a
    # mission snapshot (aboard the ship nothing applies, by design); tests/test_packaged_runtime.py asserts both sides.
    writes = (report.get('counts') or {}).get('writes')
    if extras.get('readOnly') and writes:
        failures.append(f'read-only scenario wrote {writes} times')
    if not extras.get('readOnly') and not extras.get('missionOnly') and not writes:
        failures.append('no write reached the overlay')
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
    named = re.search(r'HD2Runtime-(\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?)-runtime', Path(zip_path).name)
    if named and named.group(1) != version:
        failures.append(f'artifact name says {named.group(1)} but the packaged runtime reports {version}')
    if not scan['packageModuleList']:
        failures.append('package module list is missing: ' + PACKAGE_MODULES)
    names = list(scenarios or SCENARIOS)
    head = prelude(resources, scan['names'], snapshot).encode()
    reports = [json.loads(raw) for raw in parallel.lua_programs(
        [['head', scenario_program(name, SCENARIOS[name](), scenario_seed(name, snapshot)).encode()] for name in names],
        {'head': head}, jobs)]
    for name, report in zip(names, reports):
        problems = check(report)
        # Every session names the packaged runtime version exactly once, as its first log line.
        log = [entry.rstrip(chr(13) + chr(10)) for entry in report.get('log') or []]
        if log.count(line) != 1 or not log or log[0] != line:
            problems.append(f'startup version line {line!r} expected once as the first log line '
                f'(found {log.count(line)}, first {log[0] if log else None!r})')
        result['scenarios'][name] = {'passed': not problems, 'problems': problems,
            'outcomes': check_operations(report, EXTRAS.get(name, {}))[1],
            'watches': report.get('watches'), 'reset': report.get('reset', {}).get('reapplied'),
            'overlayWrites': report.get('counts', {}).get('writes'),
            'moduleHashes': report.get('counts', {}).get('module_hashes'),
            'lateLookupsMissing': sorted(set(report.get('lookups', {}).get('late_missing', []))),
            'packageRequests': report.get('counts', {}).get('package_requests', 0),
            'steps': [{'name': step.get('name'), 'passed': step.get('passed')} for step in report.get('after') or []]}
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
            'reset_reapplied=%s' % item['reset'], ' '.join('%s=%s' % pair for pair in item['outcomes'].items()
                if pair[1]))


if __name__ == '__main__':
    main()
