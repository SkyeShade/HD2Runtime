"""Carrier GROUPS, CARRIER PODS and the CONDENSED expendable carrier (runtime/carrier_groups.lua,
runtime/carrier_pod.lua, runtime/custom_stratagems.lua; docs/custom-stratagem-api.md "Carrier groups", "pod",
"describe"). Offline:
  * the groups: the catalogue, a requested group checked against its payload (refused with the reason), a group's
    beacon and families, slots only for a pod group; a legacy policy keeps its allocation (its group is a label);
  * pod items: support weapons and backpacks (CONFIRMED), primaries only with allow_unverified_effect, secondaries and
    throwables refused, 'clone' only in an expendable pod, backpack modify refused, each item once, the 8-item limit,
    a donor/item mix refused; an expendable pod must hold the clone and fit a pool weapon's rack;
  * the support_pod group allocation: only a candidate with an exclusive rack of the capacity and slot roles asked for;
  * the condensed carrier: the carrier weapon's own stratagem carries the beacon (one vanilla stratagem), with the
    fallback (a separate support carrier) only when that stratagem is ineligible, and UNAVAILABLE when neither works; in a
    lobby an only-unowned row stays the carrier (refused locally);
  * the mission glue: the clone, then the rack write of the carrier weapon's own pod (two clone launchers), no pod-row
    presentation of its own when condensed (the definition's presentation does it with the code), no beacon change, the
    beacon marked as its own delivery, the planned slot layout and per-item modify at the capture; a carrier pod's rack
    step before its presentation; restore_all restores the pods;
  * describe: the group, the carrier, the carrier weapon, the pod's rack, capacity and slots, availability;
  * the registry hash: every definition without the new options keeps its line; a pod or a requested group adds to its
    own line only;
  * availability of a group definition: UNAVAILABLE naming the lobby picks that took its members, unpicked when picked."""
import json
import unittest

from support import run
from test_stratagem_calldown_code import WORLD


HARNESS = r"""
local json=require('hd2runtime/primary_mapper/json')
local function J(x)local ok,t=pcall(json.encode,x);return ok and t or tostring(x)end
local images=require('hd2runtime/runtime/image_resources');images.reset_for_tests()
local texts=require('hd2runtime/runtime/text_resources');texts.reset_for_tests()
require('hd2runtime/runtime/virtual_stratagems').reset_for_tests()
local custom=require('hd2runtime/runtime/custom_stratagems');custom.reset_for_tests()
local groups=require('hd2runtime/runtime/carrier_groups')
local pod=require('hd2runtime/runtime/carrier_pod');pod.reset_for_tests()
local WC=require('hd2runtime/runtime/weapon_carriers')
local clone=require('hd2runtime/runtime/weapon_clone');clone.reset_for_tests()
local protocol=require('hd2runtime/runtime/peer_protocol')
local catalog=require('hd2runtime/domains/stratagem_authoring')
local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
local allocator=require('hd2runtime/runtime/carrier_allocator')
local log_module=require('hd2runtime/runtime/log')
local lines={}
log_module.emit=function(text)lines[#lines+1]=tostring(text)end
local function count(text)local n=0;for _,l in ipairs(lines)do if l:find(text,1,true)then n=n+1 end end;return n end
local function said(text)local o={};for _,l in ipairs(lines)do if l:find(text,1,true)then o[#o+1]=l end end
    return table.concat(o,' | ')end
local EAT17,EAT700,EAT411='EAT-17 Expendable Anti-Tank','EAT-700 Expendable Napalm','EAT-411 Leveller'
local ID700,ID411=catalog.stratagems[EAT700].root.id,catalog.stratagems[EAT411].root.id
local SW=function(name)return {resource='support_weapon',weapon=name}end
local BP=function(name)return {resource='backpack',backpack=name}end
local PW=function(name)return {resource='player_weapon',weapon=name}end
local function eat17g(id,over)
    local s={id=id,name='EAT-17G GAS EXPENDABLE ANTI-TANK',name_cased='EAT-17G Gas Expendable Anti-Tank',
        description='Two launchers.',icon=id,code={'down','down','up','up','left','right'},cooldown=70,
        carrier={group='expendable'},delivery={family='expendable',weapon=SW(EAT17),pod={{item='clone',count=2}},
        modify={impact_explosion='Orbital Gas Strike'}}}
    for k,v in pairs(over or{})do if v==false then s[k]=nil else s[k]=v end end
    return s
end
local function kit(id,over)
    local s={id=id,name='SUPPORT KIT',name_cased='Support Kit',description='A machine gun and a supply pack.',icon=id,
        code={'right','left','right','left','up'},cooldown=90,carrier={group='support_pod',slots=2},
        delivery={family='support',items={{item=SW('MG-43 Machine Gun'),modify={ammo=300}},{item=BP('B-1 Supply Pack')}}}}
    for k,v in pairs(over or{})do if v==false then s[k]=nil else s[k]=v end end
    return s
end
local function refused(spec,text)
    local ok,why=pcall(custom.register,spec,'mods/test/one')
    assert(not ok,'accepted: '..tostring(text))
    assert(tostring(why):find(text,1,true),tostring(why))
end
-- A discovery candidate (stratagem_slot_conversion's candidate shape).
local function cand(name,over)
    local e=catalog.stratagems[name]
    local c={name=name,id=e.root.id,type=500+(e.root.id%97),family=e.family,eligible=true,reasons={},codes={},
        beaconCategory='support',beamColour='blue',pingColour='blue',class=4}
    for k,v in pairs(over or{})do c[k]=v end
    return c
end
"""


class GroupTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(WORLD + HARNESS + body), b'ok')

    def test_the_groups_and_their_payloads(self):
        self.lua(r'''
local cat=groups.catalogue()
local names={}
for _,g in ipairs(cat)do names[#names+1]=g.name end
assert(table.concat(names,',')=='orbital,any_red,any,support,support_pod,expendable,weapon,sentry,emplacement,eagle',
    table.concat(names,','))
assert(groups.resolve({group='support_pod',slots=2},'pod',2)=='support_pod')
local g,why=groups.resolve({group='orbital'},'eagle')
assert(g==nil and why:find('carrier.group orbital cannot carry a eagle payload (it needs eagle)',1,true),why)
g,why=groups.resolve({group='eagle',beacon='support'},'eagle')
assert(g==nil and why:find('throws a offensive beacon; carrier.beacon support contradicts it',1,true),why)
g,why=groups.resolve({group='support_pod',allow_families={'orbital'}},'pod')
assert(g==nil and why:find('lists orbital, outside the group support_pod',1,true),why)
g,why=groups.resolve({group='orbital',slots=2},'runtime')
assert(g==nil and why:find('carrier.slots is a pod capacity',1,true),why)
g,why=groups.resolve({group='support_pod',slots=1},'pod',2)
assert(g==nil and why:find('carrier.slots 1 is below the pod\'s 2 items',1,true),why)
-- A legacy policy keeps its allocation: its group is a label.
assert(groups.label({beacon='offensive',prefer_families={'orbital'}},'pelican')=='any_red')
assert(groups.label({beacon='offensive',allow_families={'orbital'}},'orbital')=='orbital')
assert(groups.label({beacon='support'},'support')=='support'and groups.label({beacon='support'},'expendable')=='expendable')
-- The allocator's policy check takes a group (its beacon optional) and refuses slots without one.
assert(allocator.check_policy({group='support_pod',slots=2}))
local ok,w=allocator.check_policy({slots=2,beacon='support'})
assert(not ok and w:find('carrier.slots needs carrier.group',1,true))
ok,w=allocator.check_policy({group='nowhere'})
assert(not ok and w:find('carrier.group must be one of',1,true))
return 'ok'
''')

    def test_pod_item_rules(self):
        self.lua(r'''
refused(kit('k1',{delivery={family='support',items={{item=SW('MG-43 Machine Gun')},{donor='AC-8 Autocannon'}}}}),
    'a delivery lists items (the carrier\'s own pod) or donors')
refused(kit('k2',{delivery={family='support',items={{item=PW('JAR-5 Dominator')}}}}),
    'JAR-5 Dominator is a primary in a pod rack: not live-tested')
local p=custom.register(kit('k3',{code={'up','down','up','down','up'},carrier={group='support_pod'},
    delivery={family='support',items={{item=PW('JAR-5 Dominator'),allow_unverified_effect=true}}}}),'mods/test/one')
assert(p.kind=='pod'and p.delivery.pod.entries[1].kind=='primary'and p.slots==1)
refused(kit('k4',{delivery={family='support',items={{item=SW('MG-43 Machine Gun'),allow_unverified_effect=true}}}}),
    'is a reviewed kind (support_weapon): no acknowledgement')
refused(kit('k5',{delivery={family='support',items={{item={resource='player_weapon',weapon='P-2 Peacemaker'},
    allow_unverified_effect=true}}}}),'cannot be a pod item')
refused(kit('k6',{delivery={family='support',items={{item={resource='throwable',throwable='G-6 Frag'}}}}}),
    'not a catalogued pod item')
refused(kit('k7',{delivery={family='support',items={{item=BP('B-1 Supply Pack'),modify={ammo=3}}}}}),
    'is a backpack; no instance-local backpack field is reviewed')
refused(kit('k8',{delivery={family='support',items={{item=SW('MG-43 Machine Gun')},{item=SW('MG-43 Machine Gun')}}}}),
    'is listed twice (give it a count)')
refused(kit('k9',{delivery={family='support',items={{item=SW('MG-43 Machine Gun'),count=9}}}}),'.count must be a whole')
refused(kit('k10',{delivery={family='support',items={{item='clone'}}}}),"'clone' is an expendable definition's")
refused(kit('k11',{carrier={group='support',beacon='support'}}),'carrier.group support cannot carry a pod payload')
refused(kit('k12',{carrier={group='support_pod',beacon='offensive'}}),'a carrier pod needs a support (blue beacon) carrier')
local d=custom.register(kit('support_kit'),'mods/test/one')
assert(d.kind=='pod'and d.group=='support_pod'and d.group_source=='requested'and d.slots==2)
assert(d.delivery.count==2 and d.delivery.pod.total==2 and#d.pod_deps==2,J(d.delivery.count))
assert(d.delivery.items['11C27D3BABB38956'].kind=='weapon'and d.delivery.items['11C27D3BABB38956'].modify.ammo==300
    and d.delivery.items['4EF9A47109239A58'].kind=='backpack')
assert(d.alloc_policy.beacon=='support'and d.alloc_policy.allow_families[1]=='support')
assert(count('REGISTERED support_kit (Support Kit)')==1 and count('carrier group support_pod (requested, capacity 2)')==1
    and count('the carrier\'s OWN pod (no redirect), its exclusive rack holding support_weapon/MG-43 Machine Gun x1 '
    ..'{ammo=300}; backpack/B-1 Supply Pack x1 for the mission (2 items)')==1,said('REGISTERED'))
-- The MG-43 binds the rate-of-fire selector (its rate is rebuilt from its type's three slots): a per-call rpm is refused
-- at registration, as the delivery would refuse it.
refused({id='kit_rpm',name='KIT',description='d',icon='x',code={'right','left','right','left','down','down','down'},
    carrier={group='support_pod',slots=2},delivery={family='support',items={{item=SW('MG-43 Machine Gun'),
    modify={rpm=900}}}}},'the MG-43 Machine Gun binds the rate-of-fire selector')
-- An expendable pod: it must hold the clone, and some pool weapon's rack must hold it.
refused(eat17g('e1',{delivery={family='expendable',weapon=SW(EAT17),pod={{item=BP('B-1 Supply Pack')}}}}),
    "delivery.pod must hold the clone")
refused(eat17g('e2',{delivery={family='expendable',weapon=SW(EAT17),pod={{item='clone',count=3}}}}),
    'no carrier weapon of the EAT-17 Expendable Anti-Tank\'s class can hold it')
refused(eat17g('e3',{delivery={family='expendable',weapon=SW(EAT17),pod={{item='clone'},{item=BP('B-1 Supply Pack')}}}}),
    'has no free backpack slot')
refused(eat17g('e4',{carrier={group='support_pod'}}),'carrier.group support_pod cannot carry a expendable payload')
local e=custom.register(eat17g('eat17g'),'mods/test/one')
assert(e.kind=='expendable'and e.group=='expendable'and e.slots==2 and e.delivery.pod.total==2
    and e.delivery.fits[EAT700]and e.delivery.fits[EAT411])
assert(count('its pod holds clone x2 (2 items; carrier weapons that can hold them: EAT-700 Expendable Napalm, EAT-411 '
    ..'Leveller)')==1,said('REGISTERED eat17g'))
-- The policy the expendable group stands for (its fallback carrier): a blue support/backpack carrier.
assert(e.alloc_policy.beacon=='support'and e.alloc_policy.prefer_families[2]=='backpack')
return 'ok'
''')

    def test_the_support_pod_group_allocation(self):
        self.lua(r'''
local d=custom.register(kit('support_kit'),'mods/test/one')
local two=custom.register(kit('two_guns',{code={'up','up','right','down','down'},carrier={group='support_pod'},
    delivery={family='support',items={{item=SW('MG-43 Machine Gun'),count=2}}}}),'mods/test/one')
slots.discover_carriers=function(world,token,opts)
    local out={}
    local ex={}
    for _,n in ipairs(opts.exclude or{})do ex[n]=true end
    for _,n in ipairs({'M-105 Stalwart','AC-8 Autocannon','MG-43 Machine Gun','MGX-42 Bullet Storm','B-1 Supply Pack'})do
        local c=cand(n)
        if ex[n]then c.eligible=false;c.codes={'donor'};c.reasons={'excluded'}end
        out[#out+1]=c
    end
    return {ready=true,candidates=out}
end
local defs={{id=d.id,label=d.label,token='Orbital Precision Strike',policy=d.alloc_policy,filter=d.filter},
    {id=two.id,label=two.label,token='Orbital Precision Strike',policy=two.alloc_policy,filter=two.filter}}
local a=allocator.allocate_policies({},defs,{},{})
assert(a.assignments.support_kit.carrier=='AC-8 Autocannon',J(a.verdicts.support_kit))
assert(a.assignments.two_guns.carrier=='MGX-42 Bullet Storm',J(a.verdicts.two_guns))
local v=a.verdicts.support_kit
local function id(n)return catalog.stratagems[n].root.id end
assert(v[id('M-105 Stalwart')]:find('its pod holds at most 1 item, 2 needed',1,true),v[id('M-105 Stalwart')])
assert(v[id('MG-43 Machine Gun')]:find('no exclusive pod rack',1,true),v[id('MG-43 Machine Gun')])
assert(v[id('MGX-42 Bullet Storm')]:find('has no free backpack slot',1,true),tostring(v[id('MGX-42 Bullet Storm')]))
-- With the AC-8 picked natively by someone, the kit has no free member: refused (never another group).
a=allocator.allocate_policies({},defs,{},{'AC-8 Autocannon'})
assert(a.assignments.support_kit==nil and a.refused.support_kit:find('no unused support (blue beacon) carrier',1,true))
return 'ok'
''')

    def test_condensed_fallback_and_unavailable(self):
        self.lua(r'''
local e=custom.register(eat17g('eat17g'),'mods/test/one')
local I=custom.internals_for_tests()
local world_module=require('hd2runtime/runtime/event_world')
world_module.players=function()return {}end
local policy_defs
allocator.allocate_lobby=function(world,defs)
    policy_defs=defs
    local a={ready=true,assignments={},refused={},verdicts={},candidates={},order={},line='CUSTOM CARRIERS: stub'}
    for k,x in ipairs(defs)do a.order[k]=x.id;a.assignments[x.id]={carrier='M-105 Stalwart',stable_id=14345846,type=13}end
    return a
end
-- 1. Condensed: the EAT-411's own row is an eligible blue carrier.
local asked
slots.validate_carrier=function(world,token,carrier,opts)
    asked={carrier=carrier,opts=opts}
    return {ready=true,valid=true,candidate=cand(carrier,{type=16})}
end
local a=I.allocate({},{[ID700]=true},{e},'test',nil,{[ID700]={'your loadout'}})
local x=a.assignments.eat17g
assert(x,J(a.refused)..' | '..table.concat(lines,' | '))
assert(x.condensed and x.carrier==EAT411 and x.stable_id==ID411 and x.type==16 and x.weapon.weapon==EAT411,J(x))
assert(#policy_defs==0,'a condensed definition takes no policy carrier')
assert(asked.carrier==EAT411 and asked.opts.present[ID700])
for _,n in ipairs(asked.opts.exclude)do assert(n~=EAT700 and n~=EAT411,'its own pool is not excluded from itself')end
assert(count('EXPENDABLE CARRIERS: eat17g = EAT-411 Leveller (CONDENSED: its own beacon, clone and pod; one vanilla '
    ..'stratagem) (test)')==1,said('EXPENDABLE CARRIERS'))
-- The carrier map names it twice (beacon carrier + carrier weapon): a value, never new grammar.
local map=I.carrier_map(a,{'eat17g'})
assert(map.eat17g==ID411..'+'..ID411)
-- 2. Fallback: its row is not owned (solo): a separate support carrier throws the beacon.
slots.validate_carrier=function(world,token,carrier)
    return {ready=true,valid=false,candidate=cand(carrier,{type=16,eligible=false,codes={'not_owned'},reasons={'not owned'}}),
        reasons={'not owned'},codes={'not_owned'}}
end
a=I.allocate({},{[ID700]=true},{e},'test fallback',nil,{})
x=a.assignments.eat17g
assert(x,J(a.refused)..' | '..table.concat(lines,' | '))
assert(not x.condensed and x.carrier=='M-105 Stalwart'and x.weapon.weapon==EAT411 and x.fallback=='not owned',J(x))
assert(#policy_defs==1 and policy_defs[1].id=='eat17g'and policy_defs[1].policy.beacon=='support')
assert(count('eat17g = EAT-411 Leveller (FALLBACK: a separate support carrier throws the beacon, because EAT-411 '
    ..'Leveller cannot carry it: not owned)')==1,said('FALLBACK'))
-- 3. In a lobby an only-unowned row stays the carrier for every machine; refused here (never remapped).
world_module.players=function()return {{},{}}end
a=I.allocate({},{[ID700]=true},{e},'test lobby',nil,{})
assert(a.assignments.eat17g==nil and a.refused.eat17g:find('the lobby\'s carrier for it is EAT-411 Leveller, which this '
    ..'account does not own',1,true)and a.weapons_kept.eat17g.weapon==EAT411,J(a.refused))
assert(count('eat17g = EAT-411 Leveller (CONDENSED: its own beacon, clone and pod; one vanilla stratagem) (test lobby)')==1)
world_module.players=function()return {}end
-- 4. Neither: no fallback carrier free -> UNAVAILABLE with both reasons.
allocator.allocate_lobby=function(world,defs)
    local a={ready=true,assignments={},refused={},verdicts={},candidates={},order={},line='CUSTOM CARRIERS: stub'}
    for k,x in ipairs(defs)do a.order[k]=x.id;a.refused[x.id]='no unused support (blue beacon) carrier: 0 eligible'end
    return a
end
a=I.allocate({},{[ID700]=true},{e},'test none',nil,{})
assert(a.assignments.eat17g==nil and a.refused.eat17g:find('^UNAVAILABLE: its carrier weapon EAT%-411 Leveller cannot '
    ..'carry its beacon %(not owned%) and no separate support carrier is free'),a.refused.eat17g)
-- 5. A pool weapon whose pod cannot hold the items is never the carrier weapon (capacity): EAT-700 holds 2, EAT-411 2.
local w=WC.allocate({{id='z',donor=EAT17,slots=3}},{})
assert(w.assignments.z==nil and w.refused.z:find('EAT-700 Expendable Napalm (its pod holds at most 2, 3 asked)',1,true),
    w.refused.z)
return 'ok'
''')

    def test_the_condensed_mission_glue(self):
        self.lua(r'''
local e=custom.register(eat17g('eat17g'),'mods/test/one')
local I=custom.internals_for_tests()
local core_assets=require('hd2runtime/core/assets')
core_assets.gate=function()return {tick=function()return'ready'end}end
local cp=require('hd2runtime/runtime/carrier_presentation')
local applied,racked,presented={},{},{}
clone.apply=function(s,cb)applied[#applied+1]=s;cb({status='applied'});return {status='applied'}end
pod.apply=function(s,cb)racked[#racked+1]=s;cb({status='applied',slots=1,layout={}});return {status='applied'}end
cp.apply=function(s,cb)presented[#presented+1]=s;cb({status='applied'});return {status='applied'}end
local assignment={label=e.label,carrier=EAT411,stable_id=ID411,type=16,condensed=true,group='expendable',
    weapon={weapon=EAT411,stable_id=ID411,entity='0x7617642765AC38C7'}}
local M=I.mission()
M.queue[1]={definition=e,assignment=assignment,state='clone',slots={3}}
I.add_clone(e,assignment)
assert(count('CONDENSED: EAT-411 Leveller is also its beacon carrier and its pod (one vanilla stratagem); its pod: clone x2')
    ==1,said('MISSION (eat17g)'))
for _=1,5 do I.clone_step({runtime={}})end
local c=M.clones.eat17g
assert(c.state=='ready'and#applied==1 and#racked==1 and#presented==0,c.state..' '..#racked..' '..#presented)
-- The rack: two clone launchers (the EAT-411's own entity) in its two usable slots.
local r=racked[1]
assert(r.carrier==EAT411 and#r.items==2 and r.items[1].resource=='0x7617642765AC38C7'and r.items[2].role=='weapon'
    and r.multiplayer==true)
local dl=custom.delivery_of(e)
assert(dl.count==2 and dl.layout[0]=='7617642765AC38C7'and dl.layout[1]=='7617642765AC38C7'
    and dl.items['7617642765AC38C7'].projectile==132 and dl.items['7617642765AC38C7'].impact=='Orbital Gas Strike'
    and dl.stratagem==EAT411,J(dl.layout))
-- Its beacon: nothing to change (the weapon's own stratagem); the call is its own delivery.
M.by_type[16]={definition=e,assignment=assignment}
assert(I.decide({type=16})==nil)
-- Fallback (not condensed): the redirect to the weapon's own pod, as before.
M.by_type[13]={definition=e,assignment={carrier='M-105 Stalwart',type=13,weapon=assignment.weapon}}
assert(I.decide({type=13}).delivery==EAT411)
-- The capture: the planned layout checked, each launcher's own payload.
local pods=require('hd2runtime/runtime/support_pods')
local G=catalog.stratagems[EAT411].root
settings=W.stratagem_settings({{type=16,id=G.id,package=G.package,payloads=G.payloads,sequence={3,3,2,1,3},
    group=G.group,row=G.row,cooldown=70}})
local bound={}
local impacts=require('hd2runtime/runtime/projectile_impact')
impacts.bind=function(spec,cb)bound[#bound+1]=spec;return {status='active',from=376,to=82}end
pods.capture=function(spec,cb)
    assert(spec.type==16 and spec.item_types['7617642765AC38C7'])
    cb({kind='pod',pod=501})
    cb({kind='captured',pod=501,rack=6000,items={6001,6002},types={'7617642765AC38C7','7617642765AC38C7'},slots={0,1}})
    return {status='complete'}
end
local ctx=I.new_call(e,assignment,3)
ctx.beacon={entity=7006,network=802}
I.start_capture(ctx,e)
assert(#ctx.weapons==2 and#bound==2 and bound[1].donor=='Orbital Gas Strike'and bound[1].projectile==132)
assert(count('eat17g#1: POD: 2 items, each in its planned slot (2 planned)')==1,said('POD'))
assert(ctx.carrier.condensed==true and ctx.carrier.group=='expendable')
return 'ok'
''')

    def test_a_carrier_pod_mission_and_describe(self):
        self.lua(r'''
local d=custom.register(kit('support_kit'),'mods/test/one')
local e=custom.register(eat17g('eat17g'),'mods/test/one')
local I=custom.internals_for_tests()
local core_assets=require('hd2runtime/core/assets')
core_assets.gate=function()return {tick=function()return'ready'end}end
local AC8=catalog.stratagems['AC-8 Autocannon'].root.id
local racked
pod.apply=function(s,cb)racked=s;cb({status='applied',slots=4,layout={{slot=0,resource='0x11C27D3BABB38956'},
    {slot=1,resource='0x4EF9A47109239A58'}}});return {status='applied'}end
local cp=require('hd2runtime/runtime/carrier_presentation')
local presented
cp.apply=function(s,cb)presented=s;return {status='pending'}end
local a={label=d.label,carrier='AC-8 Autocannon',stable_id=AC8,type=25,family='support',beacon='support',beam='blue'}
local item={definition=d,assignment=a,state='assets',slots={0},gate={tick=function()return'ready'end},waited=0}
local M=I.mission()
M.queue[1]=item
do
    I.advance({runtime={}},item)
    assert(item.state=='pod_rack',item.state)
    I.advance({runtime={}},item)
    assert(racked and racked.carrier=='AC-8 Autocannon'and#racked.items==2 and racked.items[2].role=='backpack')
    assert(item.state=='pod_done',item.state)
    I.advance({runtime={}},item)
    assert(item.state=='presenting'and presented and presented.carrier=='AC-8 Autocannon'and presented.code)
    local dl=custom.delivery_of(d)
    assert(dl.stratagem=='AC-8 Autocannon'and dl.id==AC8 and dl.layout[0]=='11C27D3BABB38956'and dl.layout[1]
        =='4EF9A47109239A58')
    M.by_type[25]=item
    assert(I.decide({type=25})==nil,'a carrier pod delivers its own pod: no beacon change')
end
-- describe (the ship's allocation, stubbed): the group, the carrier, the pod.
local S=I.ship()
S.alloc={assignments={support_kit=a,eat17g={label=e.label,carrier=EAT411,stable_id=ID411,type=16,condensed=true,
    family='support',beacon='support',beam='blue',weapon={weapon=EAT411,stable_id=ID411,entity='0x7617642765AC38C7'}}},
    refused={}}
local x=custom.describe('support_kit')
assert(x.group=='support_pod'and x.group_source=='requested'and x.carrier.name=='AC-8 Autocannon'and x.pod.capacity==2
    and x.pod.exclusive and x.pod.rack=='0x5F41C4DCABE95421'and#x.pod.items==2 and x.pod.slots[2].slot==1
    and x.available==true,J(x))
local y=custom.describe('eat17g')
assert(y.group=='expendable'and y.carrier.condensed and y.carrier.name==EAT411 and y.carrier_weapon.name==EAT411
    and y.carrier_weapon.level=='full'and y.pod.rack=='0x8A9E543022C18092'and y.pod.capacity==2
    and y.pod.slots[1].slot==0 and y.pod.slots[2].slot==1 and y.pod.items[1].item=='clone'and y.pod.items[1].count==2,
    J(y))
assert(custom.describe('nobody')==nil)
local api=require('hd2runtime/api/custom_stratagem')
assert(api.describe('eat17g').carrier.name==EAT411 and#api.groups()==10)
return 'ok'
''')

    def test_registry_hash_stability(self):
        self.lua(r'''
-- An expendable definition without the new options (the 0.1.0 example's shape) keeps its line exactly.
custom.register({id='eat17g_clone',name='E',description='d',icon='e',code={'down','down','up','up','left','right'},
    carrier={beacon='support',prefer_families={'support','backpack'}},delivery={family='expendable',weapon=SW(EAT17),
    modify={impact_explosion='Orbital Gas Strike'},level='presentation'}},'mods/t/a')
local expected=protocol.registry_hash({{id='eat17g_clone',policy='support|support/backpack|||',
    family='expendable|EAT-17 Expendable Anti-Tank|EAT-17 Expendable Anti-Tank/EAT-411 Leveller/EAT-700 Expendable Napalm/'
    ..'Orbital Gas Strike|expendable=EAT-17 Expendable Anti-Tank,level=presentation,impact=Orbital Gas Strike,rounds=nil'}})
assert(custom.registry_hash()==expected,'the line of a definition without the new options changed')
custom.reset_for_tests()
-- A pod and a requested group add to the definition's own line only.
custom.register(eat17g('eat17g',{delivery={family='expendable',weapon=SW(EAT17),pod={{item='clone',count=2}},
    modify={impact_explosion='Orbital Gas Strike'},level='presentation'}}),'mods/t/a')
local with=protocol.registry_hash({{id='eat17g',policy='nil|||||group=expendable',
    family='expendable|EAT-17 Expendable Anti-Tank|EAT-17 Expendable Anti-Tank/EAT-411 Leveller/EAT-700 Expendable Napalm/'
    ..'Orbital Gas Strike|expendable=EAT-17 Expendable Anti-Tank,level=presentation,impact=Orbital Gas Strike,rounds=nil,'
    ..'pod=clone x2'}})
assert(custom.registry_hash()==with,'the pod line')
return 'ok'
''')

    def test_availability_of_a_group_definition(self):
        self.lua(r'''
local d=custom.register(kit('support_kit'),'mods/test/one')
local I=custom.internals_for_tests()
local loadout=require('hd2runtime/runtime/stratagem_loadout')
local selector=require('hd2runtime/runtime/stratagem_selector')
local PRECISION=catalog.stratagems['Orbital Precision Strike'].root.id
local AC8=catalog.stratagems['AC-8 Autocannon'].root.id
local saved={PRECISION,AC8}
loadout.saved=function()local p={};for k,id in ipairs(saved)do p[k]={id=id}end;return {pairs=p}end
slots.records=function()return {}end
selector.set_virtual_slots_for_tests({slots={[0]={definition='support_kit',token=PRECISION,type=118}},
    pairs={PRECISION,AC8}})
allocator.allocate_lobby=function(world,defs,lobby)
    return {ready=true,assignments={},refused={support_kit='no unused support (blue beacon) carrier of the families '
        ..'support/backpack: 0 eligible, 3 checked'},candidates={support_kit={cand('AC-8 Autocannon',{eligible=false,
        codes={'in_loadout'},reasons={'in the loadout'}})}},order={'support_kit'},verdicts={}}
end
I.availability_step({},nil)
local why=custom.unavailable('support_kit')
assert(why and why:find('UNAVAILABLE: no free member of its carrier group support_pod',1,true)
    and why:find('taken by lobby picks: AC-8 Autocannon (picked natively: your loadout)',1,true),tostring(why))
assert(selector.virtual_slots()==nil and count('SHIP (support_kit): UNPICKED loadout slot 0')==1,said('UNPICKED'))
return 'ok'
''')


class CarrierPodPlanTests(unittest.TestCase):
    def test_the_plan(self):
        out = run(WORLD + HARNESS + r'''
local D=require('hd2runtime/domains/carrier_pod_items')
local function units(n,role,res)local o={};for k=1,n do o[k]={role=role,resource=res,label='x'..k}end;return o end
local p=pod.plan('EAT-411 Leveller',units(2,'weapon','0x7617642765AC38C7'))
local q=pod.plan('EAT-700 Expendable Napalm',units(2,'weapon','0xB2B5E0D185605F9E'))
local r=pod.plan('RL-77 Airburst Rocket Launcher',units(1,'weapon','0x11C27D3BABB38956'))
local _,c1=pod.plan('EAT-411 Leveller',units(3,'weapon','0x1'))
local _,c2=pod.plan('M-105 Stalwart',units(1,'backpack','0x4EF9A47109239A58'))
local _,c3=pod.plan('EAT-17 Expendable Anti-Tank',units(1,'weapon','0x1'))
local slot1=D.racks['EAT-411 Leveller'].slots[2]
return json.encode({leveller={writes=p.writes,s0=p.desired[0],s1=p.desired[1],s2=p.desired[2]},eat700=q.writes,
    rl77={writes=r.writes,s1=r.desired[1],s2=r.desired[2],s3=r.desired[3]},codes={c1,c2,c3},
    slot1={node=slot1.node,name=slot1.nodeName,index=slot1.nodeIndex,usable=slot1.usable,role=slot1.role},
    capacity={pod.capacity('EAT-411 Leveller'),pod.capacity('M-105 Stalwart'),pod.capacity('AC-8 Autocannon'),
    pod.capacity('MG-43 Machine Gun')},carriers=#pod.carriers()})
''')
        r = json.loads(out)
        self.assertEqual(r['leveller'], {'writes': 1, 's0': '0x7617642765AC38C7', 's1': '0x7617642765AC38C7',
            's2': '0x0000000000000000'})
        self.assertEqual(r['eat700'], 0)
        self.assertEqual(r['rl77'], {'writes': 4, 's1': '0x0000000000000000', 's2': '0x0000000000000000',
            's3': '0x0000000000000000'})
        self.assertEqual(r['codes'], ['CAPACITY', 'ROLE', 'NO_EXCLUSIVE_RACK'])
        self.assertEqual(r['slot1'], {'node': 3902607911, 'name': 'attach_1', 'index': 17, 'usable': True,
            'role': 'weapon'})
        self.assertEqual(r['capacity'], [2, 1, 2, 0])
        self.assertEqual(r['carriers'], 41)


class CarrierReservationTests(unittest.TestCase):
    """0.30 release hardening: a native card is BLOCKED only when picking it would leave a currently satisfiable selected
    custom stratagem without a carrier (the deterministic allocator re-run as a feasibility test); the native picker's
    blocked state (runtime/stratagem_blocking.lua, live-proven r6) shows exactly that set."""

    HARNESS = r"""
local custom=require('hd2runtime/runtime/custom_stratagems');custom.reset_for_tests()
local selector=require('hd2runtime/runtime/stratagem_selector')
local catalog=require('hd2runtime/domains/stratagem_authoring')
local I=custom.internals_for_tests()
local lines={}
require('hd2runtime/runtime/log').emit=function(t)lines[#lines+1]=t end
local function count(t)local n=0;for _,l in ipairs(lines)do if l:find(t,1,true)then n=n+1 end end;return n end
local world_module=require('hd2runtime/runtime/event_world')
world_module.players=function()return {}end
-- The policy allocator as a deterministic pool per definition (ids in order; a native pick or another id's carrier is
-- never taken), like carrier_allocator.allocate_lobby.
local POOLS={}
require('hd2runtime/runtime/carrier_allocator').allocate_lobby=function(world,defs,opts)
    local a={ready=true,assignments={},refused={},verdicts={},candidates={},order={},line='CUSTOM CARRIERS: stub'}
    local list={}
    for _,d in ipairs(defs)do list[#list+1]=d end
    table.sort(list,function(x,y)return x.id<y.id end)
    local taken={}
    for _,d in ipairs(list)do
        a.order[#a.order+1]=d.id
        for _,c in ipairs(POOLS[d.id]or{{id=9000+#a.order,name='spare '..d.id}})do
            if not(opts.present[c.id]or taken[c.id])and not a.assignments[d.id]then
                taken[c.id]=true
                a.assignments[d.id]={carrier=c.name,stable_id=c.id,type=100+c.id%100}
            end
        end
        if not a.assignments[d.id]then a.refused[d.id]='UNAVAILABLE: every member taken'end
    end
    return a
end
local EAT17,EAT700,EAT411='EAT-17 Expendable Anti-Tank','EAT-700 Expendable Napalm','EAT-411 Leveller'
local ID700,ID411=catalog.stratagems[EAT700].root.id,catalog.stratagems[EAT411].root.id
local BLUE={beacon='support',prefer_families={'support','backpack'}}
local RED={beacon='offensive',prefer_families={'orbital'}}
local function blocks(present,list,ids)
    local a=I.allocate({},present,list,'test',ids,nil,true)
    local scope={}
    for _,d in ipairs(list)do scope[#scope+1]=d.id end
    if ids then scope=ids end
    return custom.carrier_blocks({},{present=present,list=list,ids=ids},a,scope),a
end
local function keys(t)local o={};for k in pairs(t)do o[#o+1]=k end;table.sort(o);return o end
"""

    def lua(self, body):
        from support import run
        self.assertEqual(run(self.HARNESS + body + "\nreturn 'ok'"), b'ok')

    def test_eat17g_blocks_only_its_last_viable_carrier_weapon(self):
        self.lua(r"""
local d=custom.register({id='eat17g',name='EAT-17G',description='d',icon='eat17g',code={'down','down','up','up','left','right'},
    carrier=BLUE,delivery={family='expendable',weapon={weapon=EAT17},modify={impact_explosion='Orbital Gas Strike'}}},
    'mods/test/one')
-- The donor itself is the pool's last member (the user's rules of 2026-10-06), reserved like the others: the EAT-700,
-- the EAT-411, then the regular EAT-17. With two of them free nothing is its last carrier: nothing is blocked.
local eat17=catalog.stratagems[EAT17].root.id
-- (the stub's separate beacon carrier is one spare per id: only the carrier weapons are the subject here)
local function weapons_blocked(t)return t[ID700]or t[ID411]or t[eat17]end
for _,present in ipairs({{},{[ID700]=true},{[ID411]=true}})do
    local b0=blocks(present,{d})
    assert(not weapons_blocked(b0),'no carrier weapon blocked with two of them free: '..table.concat(keys(b0),','))
end
-- Both clone carriers picked natively: the regular EAT-17 is its carrier weapon and its last one: BLOCKED.
local b1,both=blocks({[ID700]=true,[ID411]=true},{d})
local w=both.assignments.eat17g.weapon
assert(w.donor_self and w.weapon==EAT17 and both.refused.eat17g==nil,tostring(w.weapon))
assert(b1[eat17]and b1[eat17].ids[1]=='eat17g'and b1[ID700]==nil and b1[ID411]==nil,table.concat(keys(b1),','))
-- All three picked natively: no carrier at all: unavailable, nothing blocked.
local b2,none=blocks({[ID700]=true,[ID411]=true,[eat17]=true},{d})
assert(none.assignments.eat17g==nil and none.refused.eat17g:find('^UNAVAILABLE')and next(b2)==nil)
assert(none.refused.eat17g:find('the regular EAT-17 Expendable Anti-Tank (picked natively',1,true),none.refused.eat17g)
-- Two EAT definitions (the EAT-17G and the EAT-17C): one native EAT pick leaves the other two each one's last carrier.
local c=custom.register({id='eat17c',name='EAT-17C',description='d',icon='eat17c',code={'down','up','up','down','down','up'},
    carrier=BLUE,delivery={family='expendable',weapon={weapon=EAT17},modify={impact_explosion='Orbital Gas Strike'}}},
    'mods/test/two')
local b3,two=blocks({},{d,c})
assert(not weapons_blocked(b3),'three carrier weapons for two: none blocked: '..table.concat(keys(b3),','))
assert(two.assignments.eat17c.weapon.weapon==EAT700 and two.assignments.eat17g.weapon.weapon==EAT411)
local b4,one=blocks({[ID700]=true},{d,c})
assert(one.assignments.eat17c.weapon.weapon==EAT411 and one.assignments.eat17g.weapon.donor_self)
assert(b4[ID411]and b4[eat17]and b4[ID700]==nil,'the EAT-411 and the EAT-17 blocked: '..table.concat(keys(b4),','))
-- A definition that cannot fall back (as before the fallback): only its last viable carrier weapon is blocked.
d.delivery.fallback=nil
-- Both candidates free: its allocation could move, so neither is blocked.
local b,a=blocks({},{d})
assert(a.assignments.eat17g.weapon.weapon==EAT700)
assert(b[ID700]==nil and b[ID411]==nil,'neither blocked: '..table.concat(keys(b),','))
-- The EAT-700 picked natively: the EAT-411 is its last carrier weapon: blocked.
b,a=blocks({[ID700]=true},{d})
assert(a.assignments.eat17g.weapon.weapon==EAT411 and b[ID411]and b[ID411].ids[1]=='eat17g'and b[ID700]==nil)
-- The EAT-411 picked natively: the EAT-700 is blocked.
b,a=blocks({[ID411]=true},{d})
assert(a.assignments.eat17g.weapon.weapon==EAT700 and b[ID700]and b[ID411]==nil)
-- Both picked natively before the custom: no carrier: unavailable (nothing to block: nothing to keep).
b,a=blocks({[ID700]=true,[ID411]=true},{d})
assert(a.assignments.eat17g==nil and a.refused.eat17g:find('^UNAVAILABLE')and next(b)==nil)
-- One of them removed again: available again, the other one its last carrier.
b,a=blocks({[ID411]=true},{d})
assert(a.assignments.eat17g~=nil and b[ID700]~=nil)
""")

    def test_overlapping_offensive_custom_stratagems_are_solved_globally(self):
        self.lua(r"""
local CODES={gas={'up','left','up','left'},pel={'up','right','up','right'},eagle={'down','left','down','left'}}
local function red(id)return custom.register({id=id,name=id,description='d',icon=id,code=CODES[id],carrier=RED},
    'mods/test/'..id)end
local gas,pel=red('gas'),red('pel')
POOLS.gas={{id=1,name='A'},{id=2,name='B'},{id=3,name='C'}}
POOLS.pel={{id=1,name='A'},{id=2,name='B'},{id=3,name='C'}}
-- Three free carriers for two custom ids: any single native pick still leaves both a carrier: nothing blocked.
local b=blocks({},{gas,pel})
assert(next(b)==nil,'nothing blocked: '..table.concat(keys(b),','))
-- One picked natively: the other two are each one id's last carrier (picking either leaves one id without).
b=blocks({[1]=true},{gas,pel})
assert(b[2]and b[3]and b[1]==nil,table.concat(keys(b),','))
-- An unrelated custom id with its own pool never blocks these.
POOLS.eagle={{id=7,name='E'},{id=8,name='F'}}
local eagle=red('eagle')
b=blocks({[1]=true},{gas,pel,eagle})
assert(b[7]==nil and b[8]==nil and b[2]and b[3])
""")

    def test_lobby_wide_selections_and_native_picks_decide_this_players_blocks(self):
        self.lua(r"""
local CODES={gas={'up','left','up','left'},pel={'up','right','up','right'},eagle={'down','left','down','left'}}
local function red(id)return custom.register({id=id,name=id,description='d',icon=id,code=CODES[id],carrier=RED},
    'mods/test/'..id)end
local gas=red('gas')
POOLS.gas={{id=1,name='A'},{id=2,name='B'}}
-- Custom multiplayer: only a TEAMMATE selects gas (the synced table's ids); a teammate natively picked A: B is gas's
-- last carrier lobby-wide, so this player's B card is blocked although this player selects no custom stratagem.
local b=blocks({[1]=true},{},{'gas'})
assert(b[2]and b[2].ids[1]=='gas',table.concat(keys(b),','))
-- The same id selected by several players shares one carrier: still one block, not one per player.
local v={status='enabled',local_peer='ME',table={ME={[0]='gas',[1]=false,[2]=false,[3]=false},
    OTHER={[0]=false,[1]='gas',[2]=false,[3]=false}}}
I.ship().alloc=select(2,blocks({[1]=true},{},{'gas'}))
I.ship().inputs={present={[1]=true},list={},ids={'gas'}}
I.reservations_step({},v)
assert(count('CARRIER BLOCKS (aboard the ship): B (stable id 2): picking it would leave no carrier for gas (you slot 0, '
    ..'peer OTHER slot 1)')==1,table.concat(lines,' | '))
-- The teammate's native A is removed: two carriers again: released.
I.ship().alloc=select(2,blocks({},{},{'gas'}))
I.ship().inputs={present={},list={},ids={'gas'}}
I.reservations_step({},v)
assert(count('CARRIER BLOCK RELEASED: B (stable id 2)')==1,table.concat(lines,' | '))
""")

    def test_the_blocked_set_goes_to_the_native_module_every_update_and_clears_on_deselection(self):
        self.lua(r"""
local blocking=require('hd2runtime/runtime/stratagem_blocking')
local seen={}
blocking.apply=function(world,blocked,dt)seen[#seen+1]=blocked;return {status='applied'}end
local d=custom.register({id='eat17g',name='EAT-17G',description='d',icon='eat17g',code={'down','down','up','up','left','right'},
    carrier=BLUE,delivery={family='expendable',weapon={weapon=EAT17},modify={impact_explosion='Orbital Gas Strike'}}},
    'mods/test/one')
-- (A definition that cannot fall back to the donor itself: with the fallback nothing is ever its last carrier.)
d.delivery.fallback=nil
selector.set_virtual_slots_for_tests({slots={[2]={definition='eat17g',token=1,type=118}},pairs={7,8,1}})
local _,a=blocks({[ID700]=true},{d})
I.ship().alloc,I.ship().inputs=a,{present={[ID700]=true},list={d}}
I.reservations_step({},nil)
I.blocked_apply({},0.016)
local s=seen[#seen]
assert(s[ID411]and s[ID411].holders[1]=='eat17g (you slot 2)'and s[ID700]==nil,'only the last viable carrier')
selector.set_virtual_slots_for_tests(nil)
I.reservations_step({},nil)
I.blocked_apply({},0.016)
assert(next(seen[#seen])==nil,'unblocked on deselection')
""")

    def test_the_orchestrator_main_chunk_keeps_headroom_under_luajits_200_locals(self):
        # r6 development: the main chunk passed 200 locals and every test that loads it failed to compile.
        import re
        from support import ROOT
        count = 0
        for line in (ROOT / 'runtime/custom_stratagems.lua').read_text(encoding='utf-8').split('\n'):
            if line.startswith('local function '):
                count += 1
            elif line.startswith('local '):
                m = re.match(r'local ([\w_,\s]+)', line)
                if m:
                    count += len([n for n in m.group(1).split(',') if n.strip()])
        self.assertLessEqual(count, 190, 'group new helpers in a do-block (LuaJIT allows 200 locals per function)')


class PublicApiTests(unittest.TestCase):
    def test_a_pelican_gun_sound_loads_the_maelstrom_package_on_every_machine(self):
        from support import run
        self.assertEqual(run(r"""
local custom=require('hd2runtime/runtime/custom_stratagems');custom.reset_for_tests()
local function pel(id,code,gun)return custom.register({id=id,name=id,description='d',icon=id,code=code,
    carrier={beacon='offensive',prefer_families={'orbital'}},pelican={hover=60,gun=gun}},'mods/test/'..id)end
local GUN={behave_as='gatling_sentry',rate_multiplier=2,round='ap4',spread=100,recoil=false,face_target=true,
    unlimited_ammo=true}
local plain=pel('plain',{'left','down','left','up','left','up'},GUN)
local loud={};for k,v in pairs(GUN)do loud[k]=v end;loud.sound='maelstrom_main_gun'
local maelstrom=pel('loud',{'left','down','left','up','right','up'},loud)
local function has(d,name)for _,a in ipairs(d.assets)do if a==name then return true end end;return false end
assert(not has(plain,'TD-110 Maelstrom')and has(maelstrom,'TD-110 Maelstrom'))
assert(maelstrom.pelican.gun.sound=='maelstrom_main_gun')
-- A raw event id is never accepted.
local ok=pcall(pel,'raw',{'down','down','down','up'},{behave_as='gatling_sentry',sound='E5CA1945'})
assert(not ok,'raw Wwise ids are refused')
return 'ok'
"""), b'ok')

    def test_describe_and_groups_are_reachable_through_the_public_hd2_table(self):
        # Live r5: EAT17GExample's on_delivered failed with "attempt to call field 'describe' (a nil value)": the hd2 table
        # handed to mods did not export describe and groups (the stubs and the docs did).
        from support import run
        self.assertEqual(run(r"""
local hd2=require('hd2runtime/api/hd2')
assert(type(hd2.custom_stratagem.describe)=='function'and type(hd2.custom_stratagem.groups)=='function')
local g=hd2.custom_stratagem.groups()
assert(#g==10 and g[6].name=='expendable'and#g[6].members==5)
assert(g[7].name=='weapon'and#g[7].members==1 and g[7].members[1].name=='M-1000 Maxigun')
assert(hd2.custom_stratagem.describe('no such custom stratagem')==nil)
return 'ok'
"""), b'ok')


if __name__ == '__main__':
    unittest.main()
