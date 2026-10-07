"""The EXPENDABLE custom stratagem family (docs/custom-stratagem-api.md "expendable"; runtime/custom_stratagems.lua,
runtime/weapon_carriers.lua, runtime/weapon_clone.lua, runtime/custom_stratagem_panel.lua). Offline:
  * the carrier weapon pool: the donor's expendable class in order (EAT-700, then EAT-411), a lobby member's native
    pick or another expendable definition's claim takes a candidate, two definitions never share one, deterministic
    whatever the input order; an unselected definition is available only while a candidate remains;
  * registration: the spec rules, the assets (every pool candidate, the payload donors), the exclusions (no pool
    candidate or donor ever becomes a carrier stratagem), the weapon presentation (the definition's name and icon, or the
    donor's), a Mod Options level;
  * the registry hash of every other definition is computed exactly as before; an expendable definition's level is part
    of its own line;
  * the mission glue: the weapon pass of the allocation, the carrier map (only an expendable entry names its weapon), one
    clone per expendable id (assets, conversion, pod row presentation), the beacon redirect to the carrier weapon's pod,
    the delivery (its rack's launchers, the donor's round at the full level), the remote launcher handler;
  * availability aboard the ship: unavailable when every candidate is taken, logged once, and a picked definition UNPICKS
    itself (its slot is plainly the token);
  * the panel: an unavailable tile is dimmed and marked, its tooltip says why, and picking it is refused (nothing
    written); available again, it is drawn and picked normally."""
import unittest

from support import run
from test_stratagem_calldown_code import WORLD
from test_stratagem_selector import SELECT
from test_custom_stratagem_panel import PANEL


HARNESS = r"""
local json=require('hd2runtime/primary_mapper/json')
local images=require('hd2runtime/runtime/image_resources');images.reset_for_tests()
local texts=require('hd2runtime/runtime/text_resources');texts.reset_for_tests()
require('hd2runtime/runtime/virtual_stratagems').reset_for_tests()
local custom=require('hd2runtime/runtime/custom_stratagems');custom.reset_for_tests()
local WC=require('hd2runtime/runtime/weapon_carriers')
local clone=require('hd2runtime/runtime/weapon_clone');clone.reset_for_tests()
local protocol=require('hd2runtime/runtime/peer_protocol')
local catalog=require('hd2runtime/domains/stratagem_authoring')
local log_module=require('hd2runtime/runtime/log')
local lines={}
log_module.emit=function(text)lines[#lines+1]=tostring(text)end
local function count(text)local n=0;for _,l in ipairs(lines)do if l:find(text,1,true)then n=n+1 end end;return n end
local function said(text)local o={};for _,l in ipairs(lines)do if l:find(text,1,true)then o[#o+1]=l end end
    return table.concat(o,' | ')end
local EAT17,EAT700,EAT411='EAT-17 Expendable Anti-Tank','EAT-700 Expendable Napalm','EAT-411 Leveller'
local ID700,ID411=catalog.stratagems[EAT700].root.id,catalog.stratagems[EAT411].root.id
local BLUE={beacon='support',prefer_families={'support','backpack'}}
local function spec(id,over)
    local s={id=id,name='EAT-17G GAS EXPENDABLE ANTI-TANK',name_cased='EAT-17G Gas Expendable Anti-Tank',
        description='Two launchers.',icon=id,code={'down','down','up','up','left','right'},cooldown=70,carrier=BLUE,
        delivery={family='expendable',weapon={weapon=EAT17},modify={impact_explosion='Orbital Gas Strike'}}}
    for k,v in pairs(over or{})do if v==false then s[k]=nil else s[k]=v end end
    return s
end
local function refused(over,text)
    local ok,why=pcall(custom.register,spec('eat17g',over),'mods/test/one')
    assert(not ok,'accepted: '..tostring(text))
    assert(tostring(why):find(text,1,true),tostring(why))
end
"""


class ExpendableTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(HARNESS + body), b'ok')

    def test_the_pool_lobby_picks_and_never_sharing(self):
        self.lua(r'''
local pool=WC.pool(EAT17)
assert(#pool==2 and pool[1].name==EAT700 and pool[2].name==EAT411 and pool[1].stable_id==ID700
    and pool[2].stable_id==ID411 and pool[1].entity=='0xB2B5E0D185605F9E',json.encode(pool))
assert(WC.pool('MG-43 Machine Gun')==nil,'only a reviewed clone donor has a pool')
local a=WC.allocate({{id='a',donor=EAT17}},{})
assert(a.assignments.a.weapon==EAT700)
-- A native pick takes a candidate (whoever picked it): the next one.
a=WC.allocate({{id='a',donor=EAT17}},{[ID700]=true},{who={[ID700]={'your loadout'}}})
assert(a.assignments.a.weapon==EAT411)
-- Both picked natively: unavailable, naming who took each.
a=WC.allocate({{id='a',donor=EAT17}},{[ID700]=true,[ID411]=true},{who={[ID700]={'your loadout'},
    [ID411]={'peer 0000000000000002'}}})
assert(a.assignments.a==nil and a.refused.a==('UNAVAILABLE: every carrier weapon of the EAT-17 Expendable Anti-Tank\'s '
    ..'expendable class is taken: EAT-700 Expendable Napalm (picked natively: your loadout); EAT-411 Leveller (picked '
    ..'natively: peer 0000000000000002)'),a.refused.a)
-- Two definitions never share one; a third is unavailable; the input order never matters.
local x=WC.allocate({{id='c',donor=EAT17},{id='a',donor=EAT17},{id='b',donor=EAT17}},{})
local y=WC.allocate({{id='b',donor=EAT17},{id='c',donor=EAT17},{id='a',donor=EAT17}},{})
for _,r in ipairs({x,y})do
    assert(r.assignments.a.weapon==EAT700 and r.assignments.b.weapon==EAT411 and r.assignments.c==nil)
    assert(r.refused.c:find('EAT-700 Expendable Napalm (the carrier weapon of the custom stratagem a)',1,true)
        and r.refused.c:find('EAT-411 Leveller (the carrier weapon of the custom stratagem b)',1,true),r.refused.c)
end
-- An unselected definition is available while one candidate remains beside the others' claims.
local why,w=WC.unavailable('z',EAT17,{},{{id='a',donor=EAT17}})
assert(why==nil and w.weapon==EAT411)
why=WC.unavailable('z',EAT17,{[ID411]=true},{{id='a',donor=EAT17}},{who={[ID411]={'your loadout'}}})
assert(why and why:find('UNAVAILABLE',1,true)and why:find('EAT-411 Leveller (picked natively: your loadout)',1,true),why)
-- Selected definitions of one donor share one pool: if one remains for the newcomer, the id order gives everyone one.
why=WC.unavailable('0first',EAT17,{},{{id='a',donor=EAT17}})
local both=WC.allocate({{id='a',donor=EAT17},{id='0first',donor=EAT17}},{})
assert(why==nil and both.assignments.a and both.assignments['0first'])
return 'ok'
''')

    def test_registration_rules_assets_exclusions_and_presentation(self):
        self.lua(r'''
refused({delivery={family='expendable',weapon='MG-43 Machine Gun'}},'must name a support weapon with a reviewed '
    ..'expendable clone class (hd2.support_weapon(name)): EAT-17 Expendable Anti-Tank')
refused({carrier={beacon='offensive'}},'an expendable delivery needs a support (blue beacon) carrier')
refused({delivery={family='expendable',weapon=EAT17,level='half'}},"delivery.level must be 'presentation', 'model' or 'full'")
refused({delivery={family='expendable',weapon=EAT17,modify={projectile='MG-43 Machine Gun'}}},
    'delivery.modify.projectile is not supported')
refused({delivery={family='expendable',weapon=EAT17,presentation={colour='red'}}},
    'unsupported delivery.presentation field: colour')
refused({delivery={family='expendable',weapon=EAT17,carrier=EAT700}},'unsupported expendable delivery field: carrier')
refused({delivery={family='expendable',weapon=EAT17,presentation={icon=7}}},'delivery.presentation.icon must be')
local d=custom.register(spec('eat17g'),'mods/test/one')
assert(d.kind=='expendable'and d.delivery.donor==EAT17 and d.delivery.level=='full'and d.delivery.impact=='Orbital Gas Strike')
assert(table.concat(d.assets,',')=='EAT-700 Expendable Napalm,EAT-411 Leveller,Orbital Gas Strike',table.concat(d.assets,','))
local ex={}
for _,n in ipairs(d.exclude)do ex[n]=true end
assert(ex[EAT17]and ex[EAT700]and ex[EAT411]and ex['Orbital Gas Strike'],'no pool candidate or donor is ever a carrier')
assert(d.weapon_text and texts.text(d.weapon_text,'us')=='EAT-17G GAS EXPENDABLE ANTI-TANK'and d.weapon_icon==d.icon)
assert(d.colours==EAT17 and custom.mirrored(d)and custom.remote_handler(d).kind=='launcher'and custom.level_of(d)=='full')
assert(count('REGISTERED eat17g (EAT-17G Gas Expendable Anti-Tank)')==1 and count('a mission-scoped EAT-17 Expendable '
    ..'Anti-Tank clone on an unused carrier weapon of its expendable class (EAT-700 Expendable Napalm, EAT-411 Leveller, '
    ..'first free)')==1,said('REGISTERED'))
-- The donor's presentation instead: no weapon text, no weapon icon.
local d2=custom.register(spec('eat17g_plain',{code={'up','left','up','left','down'},delivery={family='expendable',
    weapon=EAT17,presentation={name='donor',icon='donor'},level='model'}}),'mods/test/one')
assert(d2.weapon_text==nil and d2.weapon_icon==nil and custom.level_of(d2)=='model'and not custom.mirrored(d2))
-- A Mod Options level: a choice of level names, read when used (an unusable value is the presentation level).
local options=require('hd2runtime/api/options')
local page=options.page({id='eat17g_test',title='EAT-17G test'})
local bad=page:choice({id='bad',label='Bad',choices={'A','B'},values={'presentation','huge'},default=1})
refused({id='eat17g_bad',code={'left','left','up','up'},delivery={family='expendable',weapon=EAT17,level=bad}},
    'delivery.level: a choice value must be presentation, model or full (huge)')
local level=page:choice({id='level',label='Level',choices={'P','M','F'},values={'presentation','model','full'},default=2})
local d3=custom.register(spec('eat17g_staged',{code={'right','right','down'},delivery={family='expendable',weapon=EAT17,
    level=level}}),'mods/test/one')
assert(custom.level_of(d3)=='model')
level.selected=3
assert(custom.level_of(d3)=='full')
return 'ok'
''')

    def test_the_registry_hash_of_every_other_definition_is_unchanged(self):
        self.lua(r'''
-- Three definitions of the other families: the hash is the protocol's over exactly the lines it always had, each naming
-- its selection (r44: the carrier itself by default).
custom.register({id='eat17_gas',name='G',description='d',icon='eat17_gas',code={'down','down','right','up','right'},
    carrier=BLUE,delivery={family='support',items={{donor=EAT17,modify={impact_explosion='Orbital Gas Strike'}}}}},'mods/t/a')
custom.register({id='pelican_close_air_support',name='P',description='d',icon='p',code={'left','down','left','up','left','up'},
    carrier={beacon='offensive',prefer_families={'orbital'}},pelican={hover=60}},'mods/t/b')
custom.register({id='orbital_gas_barrage',name='O',description='d',icon='o',code={'up','up','down','down'},
    carrier={beacon='offensive',prefer_families={'orbital'}},orbital={pattern='Orbital 120mm HE Barrage',
    impact_explosion='Orbital Gas Strike',native=true}},'mods/t/c')
local before=custom.registry_hash()
local function line(id,policy,family)return {id=id,policy=policy,family=family}end
local expected=protocol.registry_hash({
    line('eat17_gas','support|support/backpack|||','support|EAT-17 Expendable Anti-Tank|EAT-17 Expendable Anti-Tank/Orbital Gas Strike|impact=Orbital Gas Strike,rounds=nil|selection=carrier'),
    line('pelican_close_air_support','offensive|orbital|||','pelican|||hover=60,kind=pelican|selection=carrier'),
    line('orbital_gas_barrage','offensive|orbital|||','orbital|Orbital 120mm HE Barrage|Orbital 120mm HE Barrage/Orbital Gas Strike|native=Orbital 120mm HE Barrage,impact=Orbital Gas Strike|selection=carrier')})
assert(before==expected,'the hash of the other families changed: '..before..' ~= '..expected)
-- An expendable definition adds its own line; a Mod Options level change changes only that line.
local options=require('hd2runtime/api/options')
local level=options.page({id='h',title='H'}):choice({id='l',label='L',choices={'P','M','F'},
    values={'presentation','model','full'},default=1})
custom.register(spec('eat17g',{delivery={family='expendable',weapon=EAT17,level=level,
    modify={impact_explosion='Orbital Gas Strike'}}}),'mods/t/d')
local with=custom.registry_hash()
assert(with~=before)
level.selected=3
local changed=custom.registry_hash()
assert(changed~=with)
level.selected=1
assert(custom.registry_hash()==with,'the hash follows the level, deterministically')
return 'ok'
''')

    def test_the_mission_glue(self):
        self.lua(r'''
local d=custom.register(spec('eat17g'),'mods/test/one')
local other=custom.register({id='eat17_gas',name='G',description='d',icon='eat17_gas',code={'up','up','up','left'},
    carrier=BLUE,delivery={family='support',items={{donor=EAT17,modify={impact_explosion='Orbital Gas Strike'}}}}},
    'mods/test/two')
local I=custom.internals_for_tests()
-- The allocation's weapon pass on a stubbed carrier allocation (the stratagem carrier is not the subject here).
local allocator=require('hd2runtime/runtime/carrier_allocator')
local world_module=require('hd2runtime/runtime/event_world')
world_module.players=function()return {}end
allocator.allocate_lobby=function(world,defs)
    local a={ready=true,assignments={},refused={},verdicts={},candidates={},order={},line='CUSTOM CARRIERS: stub'}
    for k,x in ipairs(defs)do a.order[k]=x.id;a.assignments[x.id]={carrier='MG-43 Machine Gun',stable_id=1000+k,type=200+k}end
    return a
end
local a=I.allocate({},{[ID700]=true},{d,other},'test',nil,{[ID700]={'your loadout'}})
assert(a.assignments.eat17g.weapon.weapon==EAT411 and a.assignments.eat17_gas.weapon==nil,'the weapon pass')
assert(count('CUSTOM CARRIER WEAPONS: eat17g = EAT-411 Leveller (test)')==1,said('CARRIER WEAPONS'))
-- The carrier map: only the expendable entry names its weapon (a value, never new grammar).
local map,hash,text=I.carrier_map(a,{'eat17_gas','eat17g'})
assert(map.eat17_gas==a.assignments.eat17_gas.stable_id and map.eat17g==a.assignments.eat17g.stable_id..'+'..ID411)
assert(text:find('carrier weapon EAT-411 Leveller',1,true)and hash==protocol.carrier_hash(map))
local plain=I.carrier_map(a,{'eat17_gas'})
assert(protocol.carrier_hash(plain)==protocol.carrier_hash({eat17_gas=a.assignments.eat17_gas.stable_id}))
-- Both clone candidates taken: the regular EAT-17 (the donor itself, the pool's last member), its beacon a separate
-- support carrier.
local b=I.allocate({},{[ID700]=true,[ID411]=true},{d},'test',nil,{})
assert(b.assignments.eat17g and b.assignments.eat17g.weapon.donor_self and b.assignments.eat17g.weapon.weapon==EAT17
    and b.assignments.eat17g.carrier=='MG-43 Machine Gun'and b.refused.eat17g==nil)
assert(count('THE DONOR ITSELF: every clone carrier weapon of its class is taken')==1,said('EXPENDABLE CARRIERS'))
-- The regular EAT-17 picked natively too: no carrier weapon is left: unavailable (no fallback beside a native pick).
local EAT17ID=catalog.stratagems[EAT17].root.id
local none=I.allocate({},{[ID700]=true,[ID411]=true,[EAT17ID]=true},{d},'test',nil,{})
assert(none.assignments.eat17g==nil and tostring(none.refused.eat17g):find('the regular EAT-17 Expendable Anti-Tank (picked natively',1,true),
    tostring(none.refused.eat17g))
-- The clone of one mission: its assets, its conversion, its pod row's presentation; then the redirect and delivery.
local core_assets=require('hd2runtime/core/assets')
core_assets.gate=function()return {tick=function()return'ready'end}end
local cp=require('hd2runtime/runtime/carrier_presentation')
local applied,presented={},{}
clone.apply=function(s,cb)applied[#applied+1]=s;cb({status='applied'});return {status='applied'}end
cp.apply=function(s,cb)presented[#presented+1]=s;cb({status='applied'});return {status='applied'}end
I.add_clone(d,a.assignments.eat17g)
local M=I.mission()
assert(M.clones.eat17g.state=='assets'and M.clones.eat17g.level=='full')
for _=1,3 do I.clone_step({runtime={}})end
assert(M.clones.eat17g.state=='ready'and#applied==1 and#presented==1,M.clones.eat17g.state)
local s=applied[1]
assert(s.carrier==EAT411 and s.donor==EAT17 and s.level=='full'and s.name==d.weapon_text and s.icon==d.weapon_icon
    and s.multiplayer==true)
assert(presented[1].carrier==EAT411 and presented[1].text==d.texts and presented[1].icon==d.icon and presented[1].code==nil)
assert(count('MISSION (eat17g): carrier weapon EAT-411 Leveller READY as the EAT-17 Expendable Anti-Tank (level full); '
    ..'its pod and its marker present as EAT-17G Gas Expendable Anti-Tank')==1,said('READY as'))
-- A beacon of its carrier: redirected to the carrier weapon's own pod.
M.by_type[201]={definition=d,assignment=a.assignments.eat17g}
local change=I.decide({type=201})
assert(change.delivery==EAT411,tostring(change.delivery))
-- Its delivery: the EAT-411's rack, the launchers firing the donor's round (132) at the full level.
local dl=custom.delivery_of(d)
assert(dl.stratagem==EAT411 and dl.item_types['7617642765AC38C7']and dl.items['7617642765AC38C7'].projectile==132
    and dl.impact=='Orbital Gas Strike',json.encode(dl.items))
local model=custom.expendable_delivery(d,{weapon=EAT700},'model')
assert(model.items['B2B5E0D185605F9E'].projectile==259,'below full the carrier weapon keeps its own round')
-- Another machine's launcher of this call: the remote handler checks it against this mission's carrier weapon.
local item=custom.remote_handler(d).check(nil,d,4242,'7617642765AC38C7')
assert(item and item.projectile==132)
assert(custom.remote_handler(d).check(nil,d,4242,'80932FA0ED6901D3')==nil,'a real EAT-17 is never this call\'s launcher')
return 'ok'
''')

    def test_a_round_override(self):
        # delivery.round: another support weapon's reviewed round the clone fires at every level (the RL-77 Airburst's
        # 312 on an EAT-17 clone; runtime/weapon_clone.lua M.round), its weapon's package an asset, part of the hash.
        self.lua(r'''
local RL77='RL-77 Airburst Rocket Launcher'
local function round_spec(over)
    local delivery={family='expendable',weapon={weapon=EAT17},round={weapon=RL77}}
    for k,v in pairs(over or{})do delivery[k]=v end
    return {delivery=delivery}
end
refused(round_spec({round={weapon='GR-8 Recoilless Rifle'}}),'delivery.round must name a support weapon whose round '
    ..'is reviewed for the EAT-17 Expendable Anti-Tank\'s clone (hd2.support_weapon(name)): RL-77 Airburst Rocket Launcher')
refused(round_spec({round=312}),'delivery.round must name a support weapon')
refused(round_spec({modify={impact_explosion='Orbital Gas Strike'}}),'delivery.round with '
    ..'delivery.modify.impact_explosion')
-- Without a pod: the round at every level, the RL-77's package an asset.
local d=custom.register(spec('eat_cluster',round_spec()),'mods/test/one')
assert(d.delivery.round.name==RL77 and d.delivery.round.type==312)
assert(table.concat(d.assets,','):find(RL77,1,true),table.concat(d.assets,','))
for _,level in ipairs({'presentation','model','full'})do
    local dl=custom.expendable_delivery(d,{weapon=EAT700},level)
    assert(dl.projectile==312,level..' '..tostring(dl.projectile))
end
assert(count('it fires the RL-77 Airburst Rocket Launcher\'s round 312')==1,said('REGISTERED'))
local hash=custom.registry_hash()
-- The same definition without its round: another registry hash.
custom.reset_for_tests();images.reset_for_tests();texts.reset_for_tests()
require('hd2runtime/runtime/virtual_stratagems').reset_for_tests()
custom.register(spec('eat_cluster',{delivery={family='expendable',weapon={weapon=EAT17}}}),'mods/test/one')
assert(custom.registry_hash()~=hash,'the round is part of the registry hash')
-- With its own pod: the clone items fire the round too.
custom.reset_for_tests();images.reset_for_tests();texts.reset_for_tests()
require('hd2runtime/runtime/virtual_stratagems').reset_for_tests()
local pd=custom.register(spec('eat_cluster',round_spec({pod={{item='clone',count=2}}})),'mods/test/one')
for _,level in ipairs({'presentation','full'})do
    local dl=custom.expendable_delivery(pd,{weapon=EAT411},level)
    assert(dl and dl.projectile==312,level)
    for _,item in pairs(dl.items)do if item.kind=='weapon'then assert(item.projectile==312,level)end end
end
-- The clone step hands the round to the conversion.
local I=custom.internals_for_tests()
local core_assets=require('hd2runtime/core/assets')
core_assets.gate=function()return {tick=function()return'ready'end}end
local applied={}
clone.apply=function(x,cb)applied[#applied+1]=x;cb({status='refused',code='TEST',reason='stopped'});return {}end
I.add_clone(pd,{weapon={weapon=EAT411}})
for _=1,2 do I.clone_step({runtime={}})end
assert(#applied==1 and applied[1].round==RL77 and applied[1].carrier==EAT411,tostring(applied[1]and applied[1].round))
return 'ok'
''')

    def test_a_direct_damage_override(self):
        # delivery.modify.direct_damage (2026-10-07, the custom Gas and EMS EATs: 500 instead of 2000): a reviewed
        # override of the donor's own round, carried with the impact explosion by every delivery of it (the clone's, its
        # pod items', the donor fallback's), part of the hash; refused without an impact, with a round, unreviewed.
        self.lua(r'''
local function dd(modify,over)
    local delivery={family='expendable',weapon={weapon=EAT17},modify=modify}
    for k,v in pairs(over or{})do delivery[k]=v end
    return {delivery=delivery}
end
refused(dd({impact_explosion='Orbital Gas Strike',direct_damage=400}),'delivery.modify.direct_damage: projectile 132 '
    ..'has no reviewed direct damage override 400 (reviewed: 500)')
refused(dd({direct_damage=500}),'delivery.modify.direct_damage needs delivery.modify.impact_explosion')
refused(dd({impact_explosion='Orbital Gas Strike',direct_damage=500},{round={weapon='RL-77 Airburst Rocket Launcher'}}),
    'delivery.round with delivery.modify.impact_explosion')
local d=custom.register(spec('eat17g',dd({impact_explosion='Orbital Gas Strike',direct_damage=500},
    {pod={{item='clone',count=2}}})),'mods/test/one')
assert(d.delivery.damage==500 and d.delivery.impact=='Orbital Gas Strike')
local dl=custom.expendable_delivery(d,{weapon=EAT700},'full')
assert(dl.damage==500,'the delivery carries it')
for _,item in pairs(dl.items)do if item.kind=='weapon'then assert(item.damage==500,'its clone item carries it')end end
assert(d.delivery.fallback and d.delivery.fallback.damage==500,'the donor fallback carries it')
local self_dl=custom.expendable_delivery(d,{weapon={donor_self=true},donor_self=true},'full')
assert(self_dl==nil or self_dl.damage==500)
local hash=custom.registry_hash()
custom.reset_for_tests();images.reset_for_tests();texts.reset_for_tests()
require('hd2runtime/runtime/virtual_stratagems').reset_for_tests()
custom.register(spec('eat17g',dd({impact_explosion='Orbital Gas Strike'},{pod={{item='clone',count=2}}})),'mods/test/one')
assert(custom.registry_hash()~=hash,'the direct damage is part of the registry hash')
return 'ok'
''')

    def test_the_donor_fallback_mission(self):
        # Every carrier weapon taken (the user's rule of 2026-10-06): the regular EAT-17 from its own pod. No clone, no
        # rack or presentation write; only the call's own launchers change, per projectile (the EAT-17G's gas; the
        # EAT-17C's round falls back to the RL-77's cluster on impact), mirrored on every machine.
        self.lua(r'''
local EAT17_TYPE='80932FA0ED6901D3'
local RL77='RL-77 Airburst Rocket Launcher'
local donors=require('hd2runtime/runtime/explosion_donors')
-- The cluster donor: explosion 325, a launcher's (never a gun's), its mission package required.
local c=donors.DONORS[RL77]
assert(c and c.explosion==325 and not c.automatic and not c.slow and c.internal and c.requires[1]=='0x7ED1F941859987B4')
-- Internal: the fallback's own; never a mod's impact_explosion, never listed.
assert(donors.resolve(RL77,{internal=true})==RL77 and donors.resolve(RL77)==nil and donors.resolve(RL77,{gun=true,rpm=30})==nil)
assert(table.concat(donors.names(),', ')=='Orbital EMS Strike, Orbital Gas Strike')
local ok,why=pcall(custom.register,spec('eat_bad',{code={'down','down','up','up','right','right'},
    delivery={family='expendable',weapon={weapon=EAT17},modify={impact_explosion=RL77}}}),'mods/test/one')
assert(not ok and tostring(why):find('must be a reviewed explosion donor',1,true),tostring(why))
local gas=custom.register(spec('eat17g'),'mods/test/one')
local cluster=custom.register(spec('eat_cluster',{code={'down','down','up','up','right','left'},
    delivery={family='expendable',weapon={weapon=EAT17},round={weapon=RL77},pod={{item='clone',count=2}}}}),
    'mods/test/one')
assert(gas.delivery.fallback and gas.delivery.fallback.impact=='Orbital Gas Strike'and gas.delivery.fallback.stratagem==EAT17)
assert(cluster.delivery.fallback and cluster.delivery.fallback.impact==RL77)
-- Both definitions' payloads are mirrored per projectile (a round definition only in a donor-fallback mission).
assert(custom.remote_handler(gas)and custom.remote_handler(cluster))
local I=custom.internals_for_tests()
local core_assets=require('hd2runtime/core/assets')
core_assets.gate=function()return {tick=function()return'ready'end}end
local applied,racked,presented=0,0,0
clone.apply=function(x,cb)applied=applied+1;cb({status='applied'});return {}end
require('hd2runtime/runtime/carrier_pod').apply=function(x,cb)racked=racked+1;cb({status='applied'});return {}end
require('hd2runtime/runtime/carrier_presentation').apply=function(x,cb)presented=presented+1;cb({status='applied'})
    return {}end
local WCR=require('hd2runtime/runtime/weapon_carriers')
for _,d in ipairs({gas,cluster})do
    I.add_clone(d,{weapon=WCR.donor_self(EAT17,'both picked natively'),carrier='MG-43 Machine Gun'})
end
assert(count('MISSION (eat17g): THE DONOR ITSELF: every clone carrier weapon of EAT-700 Expendable Napalm, EAT-411 Leveller is '
    ..'taken (both picked natively): the regular EAT-17 Expendable Anti-Tank from its own pod, no clone')==1,said('DONOR'))
assert(count('each launcher\'s rocket explodes as RL-77 Airburst Rocket Launcher\'s on impact')==1,said('DONOR'))
for _=1,4 do I.clone_step({runtime={}})end
local M=I.mission()
assert(M.clones.eat17g.state=='ready'and M.clones.eat_cluster.state=='ready')
assert(applied==0 and racked==0 and presented==0,'no clone, rack or presentation write')
-- Its delivery: the EAT-17's own pod, its launchers the vanilla EAT-17 with the call's payload.
local dg,dc=custom.delivery_of(gas),custom.delivery_of(cluster)
assert(dg.stratagem==EAT17 and dg.item_types[EAT17_TYPE]and dg.items[EAT17_TYPE].projectile==132 and dg.count==2
    and dg.impact=='Orbital Gas Strike'and dg.donor_self)
assert(dc.stratagem==EAT17 and dc.items[EAT17_TYPE].projectile==132 and dc.impact==RL77)
-- Its beacon (a separate support carrier's) goes to the EAT-17's own pod.
M.by_type[201]={definition=cluster,assignment={weapon=WCR.donor_self(EAT17,'x'),carrier='MG-43 Machine Gun'}}
assert(I.decide({type=201}).delivery==EAT17)
-- Another machine's launcher of this call (published by its network id): its rockets explode as the mission's payload.
local item=custom.remote_handler(cluster).check(nil,cluster,4242,EAT17_TYPE)
assert(item and item.projectile==132 and item.impact==RL77,tostring(item and item.impact))
local g=custom.remote_handler(gas).check(nil,gas,4242,EAT17_TYPE)
assert(g and g.impact=='Orbital Gas Strike')
-- In a clone mission the round is the clone's own: nothing per projectile.
M.clones.eat_cluster.delivery=custom.expendable_delivery(cluster,{weapon=EAT411},'full')
local none,why=custom.remote_handler(cluster).check(nil,cluster,4242,'7617642765AC38C7')
assert(none==nil and tostring(why):find('the clone\'s own',1,true),tostring(why))
return 'ok'
''')

    def test_unavailable_aboard_the_ship_unpicks_itself(self):
        self.lua(r'''
local d=custom.register(spec('eat17g'),'mods/test/one')
local I=custom.internals_for_tests()
local loadout=require('hd2runtime/runtime/stratagem_loadout')
local selector=require('hd2runtime/runtime/stratagem_selector')
local slots=require('hd2runtime/runtime/stratagem_slot_conversion')
local PRECISION=catalog.stratagems['Orbital Precision Strike'].root.id
local saved={PRECISION,ID700,ID411}
loadout.saved=function()local p={};for k,id in ipairs(saved)do p[k]={id=id}end;return {pairs=p}end
slots.records=function()return {{peer='0000000000000002',entries={}}}end
selector.set_virtual_slots_for_tests({slots={[0]={definition='eat17g',token=PRECISION,type=118}},pairs={PRECISION,ID700,ID411}})
assert(selector.reconstruct(saved)[0]=='eat17g')
-- The donor itself is its last carrier weapon: available, the regular EAT-17.
I.availability_step({},nil)
assert(custom.unavailable('eat17g')==nil)
assert(count('AVAILABILITY (eat17g): AVAILABLE: its carrier weapon is EAT-17 Expendable Anti-Tank (the donor itself: '
    ..'every clone carrier weapon of its class is taken (EAT-700 Expendable Napalm (picked natively: your loadout); EAT-411 '
    ..'Leveller (picked natively: your loadout)): the regular EAT-17 Expendable Anti-Tank from its own pod')==1,
    said('AVAILABILITY'))
assert(selector.virtual_slots()~=nil,'still picked')
-- A definition that cannot fall back: unavailable, and it unpicks itself.
d.delivery.fallback=nil
custom.AVAILABILITY_EVERY=0                 -- re-evaluated at once (its throttle)
I.availability_step({},nil)
local why=custom.unavailable('eat17g')
assert(why and why:find('EAT-700 Expendable Napalm (picked natively: your loadout); EAT-411 Leveller (picked natively: '
    ..'your loadout)',1,true),tostring(why))
assert(count('AVAILABILITY (eat17g): UNAVAILABLE: every carrier weapon')==1,said('AVAILABILITY'))
assert(selector.virtual_slots()==nil,'the picked definition unpicked itself')
assert(count('SHIP (eat17g): UNPICKED loadout slot 0: UNAVAILABLE')==1 and count('plainly the Orbital Precision Strike '
    ..'token again: no conversion, no presentation, no payload')==1,said('UNPICKED'))
-- Logged once: the same state again says nothing.
local n=#lines
I.availability_step({},nil)
assert(#lines==n)
return 'ok'
''')


PANEL_TEST = r"""
screen_1080({entries={{type=136},{type=22},{type=41}},slot=1,rows={4,4,2},sections={0}})
local REASON='UNAVAILABLE: every carrier weapon of the EAT-17 Expendable Anti-Tank\'s expendable class is taken: '
    ..'EAT-700 Expendable Napalm (picked natively: your loadout); EAT-411 Leveller (picked natively: your loadout)'
local blocked=true
local refusals={}
local P=panel.panel({placeholders=0,focus=true,selection=true,availability=function(id)
    return blocked and id=='orbital_gas_barrage'and REASON or nil end,on_selected=function(h)refusals[#refusals+1]=h end})
tick(4)
assert(P.shown,table.concat(logged,' | '))
local g=guis()[1]
local shade,mark=false,false
for _,c in ipairs(gui_calls(g,'rect'))do
    if c.args[2][3]==panel.LAYER_BASE+17 and c.args[4][1]==170 then shade=true end
end
for _,c in ipairs(gui_calls(g,'text'))do if c.args[2]=='!'then mark=true end end
assert(shade and mark,'the unavailable tile is dimmed and marked')
assert(P.press()=='focused orbital_gas_barrage')
local tooltip=false
for _,c in ipairs(of('text'))do if tostring(c.args[2]):find('UNAVAILABLE',1,true)then tooltip=true end end
assert(tooltip,'its tooltip says why')
local result=P.press()
assert(result:find('^unavailable: UNAVAILABLE'),result)
assert(SCREEN.entry(1)==22 and selector.virtual_slots()==nil,'nothing written, nothing selected')
assert(#refusals==1 and refusals[1].status=='refused'and refusals[1].code=='UNAVAILABLE')
local refused_logged=false
for _,l in ipairs(logged)do if l:find('F7 on orbital_gas_barrage REFUSED (nothing written): UNAVAILABLE',1,true)then
    refused_logged=true end end
assert(refused_logged,table.concat(logged,' | '))
-- Available again: redrawn without the mark, and picked normally.
blocked=false
tick(10)
local redrawn=false
for _,l in ipairs(logged)do if l:find('the availability of an entry changed',1,true)then redrawn=true end end
assert(redrawn,table.concat(logged,' | '))
assert(P.focus==1,'the focus stays on the redrawn tile')
assert(P.press():find('selecting orbital_gas_barrage into slot 1',1,true))
local job=settle_job(P.handle)
assert(job.status=='selected'and selector.virtual_slots().slots[1].definition=='orbital_gas_barrage')
P.stop()
return 'ok'
"""


class ExpendablePanelTests(unittest.TestCase):
    def test_an_unavailable_tile_warns_and_cannot_be_picked(self):
        self.assertEqual(run(WORLD + SELECT + PANEL + PANEL_TEST), b'ok')


if __name__ == '__main__':
    unittest.main()
