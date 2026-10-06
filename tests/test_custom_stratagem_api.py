"""hd2.custom_stratagem (runtime/custom_stratagems.lua, api/custom_stratagem.lua; docs/custom-stratagem-api.md): the
custom stratagem API. Offline:
  * registration: the spec rules (ids, texts, icons, codes that never collide, cooldowns, carrier policies, assets,
    support deliveries, callbacks), refused at load time;
  * carrier policies (runtime/carrier_allocator.lua allocate_policies) on a stubbed discovery: offensive and support
    beacons, family preference, allowed families, never shared, every custom stratagem's donors and deliveries excluded,
    deterministic whatever the registration order;
  * the multi-instance modules: two carriers' presentations, two definitions' conversions and cooldowns at once."""
import unittest

from support import ROOT, run, lua as lua_literal


REGISTRATION = r"""
local images=require('hd2runtime/runtime/image_resources');images.reset_for_tests()
local texts=require('hd2runtime/runtime/text_resources');texts.reset_for_tests()
require('hd2runtime/runtime/virtual_stratagems').reset_for_tests()
local custom=require('hd2runtime/runtime/custom_stratagems');custom.reset_for_tests()
local function spec(over)
    local s={id='pelican_close_air_support',name='PELICAN CLOSE AIR SUPPORT',name_cased='Pelican Close Air Support',
        description='Calls in a Pelican.',icon='pelican_close_air_support',code={'left','down','left','up','left','up'},
        cooldown=60,carrier={beacon='offensive',prefer_families={'orbital'}}}
    for k,v in pairs(over or{})do if v==false then s[k]=nil else s[k]=v end end
    return s
end
local function refused(over,text)
    local ok,why=pcall(custom.register,spec(over),'mods/test/one')
    assert(not ok,'accepted: '..tostring(text))
    assert(tostring(why):find(text,1,true),tostring(why))
end
"""


ALLOCATION = r"""
local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
local A=require('hd2runtime/runtime/carrier_allocator')
local CANDIDATES
local function cand(name,id,family,beacon,class,ping,ok)
    return {name=name,id=id,type=id,family=family,class=class,beaconCategory=beacon,
        beamColour=beacon=='offensive'and'red'or beacon=='support'and'blue'or'yellow',pingColour=ping or'red',
        eligible=ok~=false,reasons=ok==false and{'an eagle (limited uses, rearm)'}or{},codes={}}
end
local seen_excludes={}
slots.discover_carriers=function(world,token,opts)
    local out={ready=true,candidates={}}
    local exclude={}
    for _,n in ipairs(opts.exclude or{})do exclude[n]=true end
    seen_excludes[#seen_excludes+1]=table.concat(opts.exclude or{},',')
    for _,c in ipairs(CANDIDATES)do
        local copy={}
        for k,v in pairs(c)do copy[k]=v end
        copy.reasons={}
        for _,r in ipairs(c.reasons)do copy.reasons[#copy.reasons+1]=r end
        if exclude[c.name]then copy.eligible=false;copy.reasons[#copy.reasons+1]='excluded'end
        if opts.present[c.id]then copy.eligible=false;copy.reasons[#copy.reasons+1]='in the loadout'end
        out.candidates[#out.candidates+1]=copy
    end
    return out
end
local PELICAN={id='pelican_close_air_support',label='Pelican CAS',token='Orbital Precision Strike',
    policy={beacon='offensive',prefer_families={'orbital'}}}
local GAS={id='orbital_gas_barrage',label='Gas Barrage',token='Orbital Precision Strike',
    policy={beacon='offensive',prefer_families={'orbital'}}}
local EAT={id='eat17_gas',label='Gas EAT',token='Orbital Precision Strike',
    policy={beacon='support',prefer_families={'support','backpack'}}}
local function full()
    return {cand('Orbital Gatling Barrage',2084654169,'orbital','offensive',1),
        cand('Orbital 380mm HE Barrage',3108516875,'orbital','offensive',1),
        cand('Orbital EMS Strike',1280711447,'orbital','support',1),
        cand('Eagle Airstrike',111,'eagle','offensive',nil,'red',false),
        cand('A/MG-43 Machine Gun Sentry',222,'sentry','support',3,'blue'),
        cand('MG-43 Machine Gun',333,'support','support',4,'blue'),
        cand('LIFT-850 Jump Pack',444,'backpack','support',4,'blue'),
        cand('Orbital Gas Strike',3193297673,'orbital','offensive',2)}
end
local function names(a)
    local out={}
    for _,id in ipairs({'eat17_gas','orbital_gas_barrage','pelican_close_air_support'})do
        out[#out+1]=id..'='..tostring(a.assignments[id]and a.assignments[id].carrier)
    end
    return table.concat(out,'; ')
end
"""


class RegistrationTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(REGISTRATION + body), b'ok')

    def test_the_spec_rules_refuse_at_load_time(self):
        self.lua(r'''
refused({id='Bad Id'},'id must be')
refused({name=('x'):rep(65)},'name must be a string of 1 to 64')
refused({description=''},'description must be')
refused({icon=7},'icon must be')
refused({code={'up','sideways'}},'code must be 1 to 8 directions')
refused({code={'up','up','up','up','up','up','up','up','up'}},'code must be 1 to 8 directions')
refused({cooldown=0},'cooldown must be seconds above 0')
refused({cooldown=601},'cooldown must be seconds above 0')
refused({carrier={beacon='purple'}},"carrier.beacon must be 'offensive', 'support' or 'any'")
refused({carrier={beacon='offensive',require_unlimited=false}},'require_unlimited can only be true')
refused({carrier={beacon='offensive',sideways=true}},'unsupported carrier option: sideways')
refused({assets={'No Such Stratagem'}},'assets[1] must name a catalogued stratagem')
-- Support deliveries: any catalogued support weapon or backpack with a reviewed pod rack, from a blue carrier.
refused({delivery={stratagem='Orbital Gas Strike'}},'is not a support weapon or backpack')
refused({delivery={stratagem='EAT-17 Expendable Anti-Tank'}},'a support delivery needs a support (blue beacon) carrier')
local BLUE={beacon='support',prefer_families={'support','backpack'}}
refused({carrier=BLUE,delivery={family='support',items={{donor='MG-43 Machine Gun'},{donor='B-1 Supply Pack'}}}},
    'one native pod delivers ONE stratagem\'s rack; MG-43 Machine Gun and B-1 Supply Pack cannot be delivered by one call')
refused({carrier=BLUE,delivery={family='support',items={{donor='MG-43 Machine Gun',count=2}}}},
    'the MG-43 Machine Gun pod holds 1 (its rack\'s own count)')
refused({carrier=BLUE,delivery={family='support',items={{donor='B-1 Supply Pack',modify={rpm=600}}}}},
    'B-1 Supply Pack delivers no weapon; no instance-local backpack field is reviewed')
refused({carrier=BLUE,delivery={family='support',items={{donor='APW-1 Anti-Materiel Rifle',modify={rpm=5000}}}}},
    'rpm must be 30..3000')
refused({carrier=BLUE,delivery={family='support',items={{donor='MG-43 Machine Gun',modify={rpm=600}}}}},
    'the MG-43 Machine Gun binds the rate-of-fire selector')
refused({carrier=BLUE,delivery={family='support',items={{donor='MG-43 Machine Gun',modify={projectile=275}}}}},
    'a raw projectile type is not accepted')
refused({carrier=BLUE,delivery={family='support',items={{donor='MG-43 Machine Gun',modify={explosion_scale=2}}}}},
    'unsupported weapon modification explosion_scale')
refused({carrier=BLUE,delivery={family='support',items={{donor='MG-43 Machine Gun',modify={impact_explosion='Big Boom'}}}}},
    'must be a reviewed explosion donor')
refused({on_delivered=function()end},'on_delivered needs a delivery (support, sentry or eagle)')
-- Sentries: a sentry donor, from sentry-family carriers only (blue).
refused({carrier=BLUE,sentry={donor='MG-43 Machine Gun'}},'sentry.donor must be a catalogued sentry')
refused({carrier={beacon='offensive',allow_families={'sentry'}},sentry={donor='A/G-16 Gatling Sentry'}},
    'a sentry needs a support (blue beacon) carrier')
refused({carrier=BLUE,sentry={donor='A/G-16 Gatling Sentry'}},'a sentry allows the sentry family only')
refused({carrier={beacon='support'},sentry={donor='A/G-16 Gatling Sentry'}},'its carrier must be sentry only')
refused({carrier={beacon='support',allow_families={'sentry'}},sentry={donor='A/G-16 Gatling Sentry',
    weapon={impact_explosion='Orbital EMS Strike'}}},'impact_explosion is not supported here')
-- Eagles: an Eagle donor, Eagle-family carriers only (red), no custom cooldown.
refused({eagle={donor='Orbital Gas Strike'}},'eagle.donor must be a catalogued Eagle')
refused({carrier={beacon='offensive',prefer_families={'orbital'}},eagle={donor='Eagle 110mm Rocket Pods'}},
    'an Eagle allows the eagle family only')
refused({carrier={beacon='support',allow_families={'eagle'}},eagle={donor='Eagle 110mm Rocket Pods'}},
    'an Eagle needs an offensive (red beacon) carrier')
refused({cooldown=30,carrier={beacon='offensive',allow_families={'eagle'}},eagle={donor='Eagle 110mm Rocket Pods'}},
    'an Eagle keeps its native cooldown and rearm')
refused({carrier={beacon='offensive',allow_families={'eagle'}},eagle={donor='Eagle 110mm Rocket Pods',uses=0}},
    'eagle.uses must be 1..20')
refused({carrier={beacon='offensive',allow_families={'eagle'}},eagle={donor='Eagle Cluster Bomb',
    payload={impact_explosion='Orbital EMS Strike'}}},'has no impact explosion only')
refused({carrier={beacon='offensive',allow_families={'eagle'}},eagle={donor='Eagle 110mm Rocket Pods',
    pattern={rockets=8}}},'eagle.pattern is not supported')
refused({carrier={beacon='offensive',allow_families={'eagle'}},eagle={donor='Eagle 110mm Rocket Pods',
    payload={projectile='MG-206 Heavy Machine Gun'}}},'eagle.payload.projectile is not supported')
-- Orbitals: reviewed shells and patterns, bounded counts, no shared explosion scaling.
refused({orbital={shell='Eagle Airstrike'}},'orbital.shell must be a reviewed orbital')
refused({orbital={shell='Orbital Gas Strike',salvos=0}},'orbital.salvos must be a whole number 1..16')
refused({orbital={shell='Orbital Gas Strike',salvos=16,shells_per_salvo=16}},'256 shells in all; at most 64')
refused({orbital={shell='Orbital Gas Strike',explosion_scale=2}},'explosion_scale is not supported')
refused({orbital={shell='Orbital Gas Strike'},eagle={donor='Eagle 110mm Rocket Pods'}},'one payload family per custom '
    ..'stratagem')
refused({on_activate=7},'on_activate must be a function')
refused({colour='red'},'unsupported custom stratagem field: colour')
-- A valid one, then the rules between custom stratagems: ids and codes never collide.
local d=custom.register(spec(),'mods/test/one')
assert(d.id=='pelican_close_air_support'and d.code_text=='left down left up left up')
refused({},'custom stratagem pelican_close_air_support is already registered')
refused({id='other',code={'left','down','left','up','left','up'}},'collides with the custom stratagem '
    ..'pelican_close_air_support')
refused({id='other',code={'left','down','left'}},'collides with the custom stratagem pelican_close_air_support')
refused({id='other',code={'left','down','left','up','left','up','down'}},'collides with the custom stratagem')
-- A support delivery: a blue carrier, the delivered stratagem and every asset excluded as carriers of any of them.
local eat=custom.register(spec({id='eat17_gas',code={'down','down','right','up','right'},icon='eat17_gas',
    carrier={beacon='support',prefer_families={'support','backpack'}},delivery={stratagem='EAT-17 Expendable Anti-Tank'},
    assets={'Orbital Gas Strike'},on_delivered=function()end}),'mods/test/two')
assert(eat.delivery.stratagem=='EAT-17 Expendable Anti-Tank'and eat.delivery.item=='80932FA0ED6901D3'
    and eat.delivery.projectile==132 and eat.delivery.count==2 and eat.delivery.item_types['80932FA0ED6901D3']
    and eat.kind=='support')
assert(table.concat(eat.exclude,',')=='Orbital Gas Strike,EAT-17 Expendable Anti-Tank')
-- The virtual definitions behind them: the token, discovered carriers.
local V=require('hd2runtime/runtime/virtual_stratagems')
assert(V.get('eat17_gas').selection.token=='Orbital Precision Strike'and V.get('eat17_gas').mission.discover)
assert(#custom.list()==2)
return 'ok'
''')

    def test_the_public_api_names_the_calling_mod(self):
        self.lua(r'''
local hd2=require('hd2runtime/api/hd2')
local events=require('hd2runtime/runtime/events')
local d=events.run_as('mods/test/caller',hd2.custom_stratagem.register,spec())
assert(d.id=='pelican_close_air_support'and d.owner=='mods/test/caller')
assert(custom.get('pelican_close_air_support').owner=='mods/test/caller')
local s=hd2.custom_stratagem.status()
assert(#s==1 and s[1].id=='pelican_close_air_support'and s[1].state=='ship')
assert(type(hd2.custom_stratagem.focus_next())=='string')
return 'ok'
''')


class CarrierPolicyTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(ALLOCATION + body), b'ok')

    def test_offensive_and_support_policies_take_distinct_carriers_of_their_families(self):
        self.lua(r'''
CANDIDATES=full()
local a=A.allocate_policies(nil,{PELICAN,GAS,EAT},{},{'Orbital Gas Strike','EAT-17 Expendable Anti-Tank'})
assert(a.ready and a.distinct,a.line)
-- The support stratagem takes the support weapon (never the sentry, never an orbital); the two offensive ones the two
-- unused RED orbitals (never the blue EMS Strike, never the excluded Gas Strike, never an Eagle).
assert(names(a)=='eat17_gas=MG-43 Machine Gun; orbital_gas_barrage=Orbital Gatling Barrage; '
    ..'pelican_close_air_support=Orbital 380mm HE Barrage',names(a))
assert(a.verdicts.pelican_close_air_support[1280711447]:find('not offensive: a support beacon',1,true))
assert(a.verdicts.pelican_close_air_support[2084654169]=='taken by Gas Barrage (never shared)')
assert(a.verdicts.eat17_gas[222]=='not an allowed family (sentry)')
assert(a.verdicts.eat17_gas[3193297673]=='rejected: excluded')
assert(a.verdicts.eat17_gas[2084654169]=='not support: an offensive beacon (red beam, red ping)')
-- The line names them by id (the allocation's own order), whatever the input order.
assert(a.line=='CUSTOM CARRIERS: Gas EAT = MG-43 Machine Gun (support, blue beacon), Gas Barrage = Orbital Gatling '
    ..'Barrage (orbital, red beacon), Pelican CAS = Orbital 380mm HE Barrage (orbital, red beacon); distinct = true',a.line)
-- Every custom stratagem's donors and deliveries are excluded for all of them.
for _,e in ipairs(seen_excludes)do assert(e=='Orbital Gas Strike,EAT-17 Expendable Anti-Tank',e)end
-- Deterministic whatever the registration order.
local b=A.allocate_policies(nil,{EAT,GAS,PELICAN},{},{'Orbital Gas Strike','EAT-17 Expendable Anti-Tank'})
local c=A.allocate_policies(nil,{GAS,EAT,PELICAN},{},{'Orbital Gas Strike','EAT-17 Expendable Anti-Tank'})
assert(names(b)==names(a)and names(c)==names(a),names(b)..' / '..names(c))
return 'ok'
''')

    def test_a_pinned_carrier_is_kept_until_anyone_else_holds_it(self):
        # The carrier-in-slot probe 0.2.1: a definition whose loadout slot holds its carrier keeps it (pinned first),
        # whatever ranks higher; once it is a native pick the pin no longer holds and the next carrier is given.
        self.lua(r'''
CANDIDATES=full()
local EXCL={'Orbital Gas Strike','EAT-17 Expendable Anti-Tank'}
local function pinned(d,pin)local c={};for k,v in pairs(d)do c[k]=v end;c.pin=pin;return c end
-- The Pelican's slot holds the Gatling (the Gas Barrage's carrier without pins): the Pelican keeps it.
local a=A.allocate_policies(nil,{pinned(PELICAN,2084654169),GAS},{},EXCL)
assert(names(a)=='eat17_gas=nil; orbital_gas_barrage=Orbital 380mm HE Barrage; pelican_close_air_support=Orbital '
    ..'Gatling Barrage',names(a))
assert(a.assignments.pelican_close_air_support.pinned and not a.assignments.orbital_gas_barrage.pinned)
assert(a.verdicts.pelican_close_air_support[2084654169]=='SELECTED (its loadout slot already holds it)')
-- A higher-ranked carrier being free never moves a pinned slot.
local b=A.allocate_policies(nil,{pinned(GAS,3108516875)},{},EXCL)
assert(b.assignments.orbital_gas_barrage.carrier=='Orbital 380mm HE Barrage'and b.assignments.orbital_gas_barrage.pinned)
assert(b.verdicts.orbital_gas_barrage[2084654169]=='eligible; its slot holds another carrier (kept)')
-- Picked natively by anyone: the pin no longer holds; the next carrier.
local c=A.allocate_policies(nil,{pinned(GAS,3108516875)},{[3108516875]=true},EXCL)
assert(c.assignments.orbital_gas_barrage.carrier=='Orbital Gatling Barrage'and not c.assignments.orbital_gas_barrage.pinned)
-- A pin outside its pool (an excluded carrier) counts for nothing.
local d=A.allocate_policies(nil,{pinned(GAS,3193297673)},{},EXCL)
assert(d.assignments.orbital_gas_barrage.carrier=='Orbital Gatling Barrage'and not d.assignments.orbital_gas_barrage.pinned)
return 'ok'
''')

    def test_a_support_policy_falls_back_to_a_backpack_then_refuses(self):
        self.lua(r'''
CANDIDATES=full()
-- The MG-43 in the loadout: the backpack.
local a=A.allocate_policies(nil,{EAT},{[333]=true},{})
assert(a.assignments.eat17_gas.carrier=='LIFT-850 Jump Pack',a.line)
-- Neither: refused (never the sentry, the EMS Strike or anything else).
local b=A.allocate_policies(nil,{EAT},{[333]=true,[444]=true},{})
assert(not b.assignments.eat17_gas and b.refused.eat17_gas:find('no unused support (blue beacon) carrier of the '
    ..'families support/backpack: 0 eligible',1,true),b.line)
return 'ok'
''')

    def test_more_offensive_stratagems_than_red_carriers_never_share(self):
        self.lua(r'''
CANDIDATES=full()
local THIRD={id='zz_third',label='Third',token='Orbital Precision Strike',policy={beacon='offensive'}}
local a=A.allocate_policies(nil,{PELICAN,GAS,THIRD},{},{'Orbital Gas Strike'})
assert(a.distinct)
local taken=0
for _,id in ipairs({'pelican_close_air_support','orbital_gas_barrage','zz_third'})do
    if a.assignments[id]then taken=taken+1 end
end
assert(taken==2 and a.refused.zz_third and a.refused.zz_third:find('taken by another custom stratagem',1,true),a.line)
return 'ok'
''')


if __name__ == '__main__':
    unittest.main()
