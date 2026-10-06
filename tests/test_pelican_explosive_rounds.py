"""Explosive rounds for the Pelican gunship (gun.impact_explosion; runtime/pelican_gunship.lua, runtime/custom_mp_pelican.lua,
runtime/projectile_impact.lua continuous bindings, runtime/explosion_donors.lua automatic donors; research/custom-payloads
pelicanDonor and impactCarriers):
  * the research: the chin turret's own round 120 explodes as 234 (its chain reviewed), and the Pelican CAS rounds 148 and
    275 have no explosion of their own and the impact-time flags of the live-verified Talon base 144;
  * a continuous binding writes EVERY round of its exact source from 0 to the donor's explosion (each round's own copy,
    one guarded write), never a row, never another source's round, and ends when its source is gone;
  * an automatic donor belongs to a continuous binding only, and only reviewed carriers may start from no explosion;
    a changed carrier row, donor chain or package leaves the rounds plain;
  * the credit binding (the host's, for a client's call) and the impact binding share the turret: both writes land;
  * the donor never reaches the launcher, Eagle or orbital families (explosion_donors.resolve without automatic);
  * the gunship binds its own turret's configured round; every other machine binds its own copy (the mirror)."""
import json
import unittest

from support import ROOT, run
from test_stratagem_calldown_code import WORLD
from test_stratagem_slot_conversion import SLOT
from test_bombardment_payload import PAYLOAD
from test_gas_eat import IMPACT
from test_pelicans import PELICANS
from test_pelican_gatling import GATLING
from test_pelican_weapon import WEAPON
from test_pelican_ai import AI
from test_pelican_heading import HEADING
from test_pelican_readonly_probes import HARNESS
from test_pelican_gatling_proof import PROOF
from test_pelican_gunship import GUNSHIP
from test_custom_mp_pelican import MIRROR
from support import lua as lua_literal
from test_custom_stratagem_api import REGISTRATION
from test_pelican_ai import AI as AI_FIXTURE, RELEASE

RESEARCH = json.loads((ROOT / 'research/custom-payloads-F5FEE03DCFDB.json').read_text(encoding='utf-8'))


def names_of(donor):
    return {p['name'] for p in donor['packages']}
PELICAN_RESEARCH = json.loads((ROOT / 'research/pelican-F5FEE03DCFDB.json').read_text(encoding='utf-8'))

EXPLOSIVE = r"""
local CP=require('hd2runtime/domains/custom_payloads')
local donors=require('hd2runtime/runtime/explosion_donors')
local PD=CP.explosionDonors['Pelican chin autocannon']
local CARRIERS=CP.impactCarriers
local DONOR='Pelican chin autocannon'
local P2='5555666677778888'
-- The donor's chain exactly as reviewed: explosion 234 and its damage row 373.
local chain_rows={}
for _,item in ipairs(PD.rows)do
    local at=W.alloc(item.stride);W.write(at,b.unhex(item.reviewed))
    W.write(W.GAME+tonumber(item.table:sub(3),16)+item.id*8,W.u64(at))
    chain_rows[#chain_rows+1]={at=at,stride=item.stride}
end
local function chain234()
    local out={}
    for _,r in ipairs(chain_rows)do out[#out+1]=W.read(r.at,r.stride)end
    return table.concat(out)
end
-- A carrier row: no impact or expiry explosion, its flags +0xF0 (the reviewed ones: the Talon base's).
local function carrier_row(kind,flags)
    return W.projectile_row(kind,W.u32(kind)..string.rep('\0',CARRIERS.flagsOffset-4)
        ..string.char(flags%256,math.floor(flags/256))..string.rep('\0',0x110-CARRIERS.flagsOffset-2))
end
local row275=carrier_row(275,CARRIERS.baseFlags)
local ROW275=W.read(row275,0x110)
-- The packages resident here: loadout_shared (one of those that ship the donor's effect) unless a test says otherwise;
-- every other package the game would hold stays as the fixture says.
local LOADOUT_SHARED='0xAF782724C0F7658B'
local resident={[LOADOUT_SHARED]=true}
local pelican_resident=true
local effect_packages={}
for _,e in pairs(CP.explosionDonors)do
    for _,p in ipairs(e.automatic and e.packages or{})do effect_packages[p.id]=true end
end
local previous_state=W.runtime.package_state
W.runtime.package_state=function(hex)
    if effect_packages[hex]then
        return(resident[hex]and pelican_resident)and'resident'or'absent'
    end
    if previous_state then return previous_state(hex)end
    return'resident'
end
require('hd2runtime/runtime/explosion_donors').reset_for_tests()
local function creditor(hit)
    local raw=W.read(hit+H.creditor,8)
    return require('hd2runtime/runtime/event_world').peer_hex(b.u32(raw,0),b.u32(raw,4))
end
"""


class ResearchTests(unittest.TestCase):
    def test_the_pelican_donor_and_its_carriers(self):
        donor = RESEARCH['explosionDonors']['Pelican chin autocannon']
        self.assertEqual((donor['round'], donor['explosion'], donor['automatic'], donor['radii']), (120, 234, True,
            [2.0, 6.0, 8.0]))
        self.assertEqual(donor['links'], {'damage': 373, 'template': 0, 'seconds': 0.0, 'statuses': []})
        self.assertEqual(donor['damage'], {'standard': 150, 'durable': 150, 'armorPenetration': [3, 0, 0, 0]})
        self.assertEqual([(r['kind'], r['id'], r['masked']) for r in donor['rows']], [('explosion', 234, [40, 44]),
            ('damage', 373, [])])
        # The round is the chin turret's own (research/pelican), the donor's explosion its row's impact explosion.
        self.assertEqual(PELICAN_RESEARCH['turretWeapon']['observed']['chinTurret']['projectileType'], donor['round'])
        carriers = RESEARCH['impactCarriers']
        self.assertEqual((carriers['base'], carriers['baseFlags'], carriers['flagsOffset']), (144, 0x7D, 0xF0))
        self.assertEqual(carriers['types'], {'148': {'impact': 0, 'expiry': 0, 'flags': 0x7D},
            '275': {'impact': 0, 'expiry': 0, 'flags': 0x7D}})
        self.assertIn('A Pelican CAS round (148 / 275)', ' '.join(RESEARCH['unproven']))
        # The rounds the gunship fires are exactly the carriers.
        self.assertEqual(PELICAN_RESEARCH['apDonor']['projectile'], 275)
        self.assertEqual(PELICAN_RESEARCH['apDonor']['standard']['projectile'], 148)

    def test_the_other_automatic_donors_and_where_their_effects_ship(self):
        donors = {name: d for name, d in RESEARCH['explosionDonors'].items() if d.get('automatic')}
        facts = {name: (d['round'], d['explosion'], d['damage']['standard'], d['damage']['armorPenetration'][0],
            d['radii'], d['asset']) for name, d in donors.items()}
        self.assertEqual(facts, {
            'Pelican chin autocannon': (120, 234, 150, 3, [2.0, 6.0, 8.0], None),
            '66mm Missile Mk2': (272, 170, 150, 5, [1.0, 2.0, 4.0], 'MLS-4X Commando'),
            'Automaton explosion 27': (302, 27, 70, 4, [1.0, 2.0, 3.5], None),
            'Illuminate explosion 392': (166, 392, 150, 4, [1.2, 2.7, 4.0], None),
            'Strafing run cannon': (16, 50, 350, 3, [2.5, 5.0, 6.5], 'Eagle Strafing Run'),
            'Exploding crossbow': (249, 59, 350, 3, [3.0, 6.0, 7.0], None),
            'Assault walker cannon': (301, 397, 65, 3, [1.0, 3.0, 5.0], None)})
        self.assertEqual(names_of(donors['Assault walker cannon']), {'packages/content/cyborgs'})
        self.assertEqual(donors['Exploding crossbow']['assetKey'], 'player_weapon/CB-9 Exploding Crossbow')
        for name, d in donors.items():
            self.assertEqual(d['links']['template'], 0, name)
            self.assertEqual(d['links']['statuses'], [], name)
            self.assertEqual([r['kind'] for r in d['rows']], ['explosion', 'damage'], name)
        names = {name: {p['name'] for p in d['packages']} for name, d in donors.items()}
        # 27 and 392 are faction content: their effect ships in the Automaton / Illuminate package only.
        self.assertEqual(names['Automaton explosion 27'], {'packages/content/cyborgs'})
        self.assertEqual(names['Illuminate explosion 392'], {'packages/content/illuminate'})
        self.assertIn('packages/content/loadout_shared', names['Pelican chin autocannon'])
        self.assertIn('packages/generated/loadout/laser_guided_missile_launcher', names['66mm Missile Mk2'])
        self.assertIn('packages/generated/loadout/eagle_base', names['Strafing run cannon'])
        self.assertIn('packages/generated/loadout/crossbow_greyfax', names['Exploding crossbow'])
        # The game's own label for round 272.
        presentation = json.loads((ROOT / 'research/weapon-presentation-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
        self.assertEqual(presentation['modes']['projectiles']['272']['name'], '66mm Missile Mk2')


class ContinuousBindingTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + IMPACT + EXPLOSIVE + body + "\nreturn 'ok'"), b'ok')

    def test_every_round_of_the_exact_source_takes_the_donor_explosion(self):
        self.check(r"""
iworld()
local before=chain234()
local events={}
local binding,code,why=impacts.bind({sources={5001},projectiles={275},donor=DONOR,continuous=true,provenance=true,
    label='Pelican explosive rounds'},function(e)events[#events+1]=e end)
assert(binding,tostring(code)..' '..tostring(why))
assert(binding.from==0 and binding.to==234 and binding.continuous)
tick()
local writes=#W.runtime.writes
-- 70 rounds of the turret (more than any per-source round limit): every one converted, 0 -> 234, one write each.
local hits={}
for k=1,70 do
    local _,h=fire(5001,{type=275,impact=0})
    hits[k]=h
    if k%20==0 then tick()end
end
tick()
for k,h in ipairs(hits)do assert(impact_of(h)==234,'round '..k..' stayed '..impact_of(h))end
assert(#W.runtime.writes==writes+70,'writes '..(#W.runtime.writes-writes))
local converted=0
for _,e in ipairs(events)do if e.kind=='converted'then converted=converted+1 end end
assert(converted==70 and binding.status=='active')
assert(count('projectile impact CONVERTED (Pelican explosive rounds): projectile 275 in pool slot')==1
    and count('impact explosion 0 -> 234 (1 write; read back true; non-target bytes unchanged true; protection '
    ..'restored true)')==1,table.concat(logged,' | '))
-- Another source's round and another type from the turret: never touched.
local _,other=fire(5003,{type=275,impact=0})
local _,gatling=fire(5001,{type=148,impact=0})
tick()
assert(impact_of(other)==0 and impact_of(gatling)==0 and#W.runtime.writes==writes+70)
-- No row was written: the round's row, the donor's chain.
assert(W.read(row275,0x110)==ROW275 and chain234()==before,'a shared row was written')
-- The rounds hit (the game requests each copy's explosion); then the turret is gone: the binding ends.
for _,h in ipairs(hits)do W.write(h+H.impactRequested,string.char(1))end
tick()
local impacts_seen=0
for _,e in ipairs(events)do if e.kind=='impact'then impacts_seen=impacts_seen+1;assert(e.explosion==234)end end
assert(impacts_seen==70,impacts_seen)
W.remove(5001)
tick()
assert(binding.status=='complete'and events[#events].kind=='ended',events[#events].kind)
""")

    def test_the_rules_of_a_continuous_binding(self):
        self.check(r"""
iworld()
donors.READY_CALLS=0                 -- every check reads the residency (no remembered result between steps)
local function refused(spec,code,text)
    local b_,c,why=impacts.bind(spec)
    assert(not b_ and c==code and(not text or tostring(why):find(text,1,true)),tostring(c)..' '..tostring(why))
end
-- A gun's donor (automatic or slow) only in a continuous binding, and a continuous binding only with one.
refused({sources={5001},projectiles={275},donor='Orbital Gas Strike',continuous=true},'UNSUITABLE_DONOR',
    'gun donors: 66mm Missile Mk2, Assault walker cannon, Automaton explosion 27, EMS mortar field, Exploding crossbow, '
    ..'Gas grenade cloud, Gas mortar cloud, Illuminate explosion 392, Pelican chin autocannon, Strafing run cannon')
refused({sources={5001},projectile=132,donor=DONOR},'UNSUITABLE_DONOR','a continuous binding')
refused({sources={5001},projectiles={275},donor=DONOR,continuous=true,rounds=4},'INVALID')
-- A row without an impact explosion: still refused outside a continuous binding ...
refused({sources={5001},projectile=275,donor='Orbital Gas Strike'},'NO_IMPACT_EXPLOSION')
-- ... and inside one unless it is a reviewed carrier with its reviewed flags.
carrier_row(160,CARRIERS.baseFlags)
refused({sources={5001},projectiles={160},donor=DONOR,continuous=true},'NO_IMPACT_EXPLOSION',
    'not a reviewed explosion-less carrier')
carrier_row(148,CARRIERS.baseFlags+0x1000)
refused({sources={5001},projectiles={148},donor=DONOR,continuous=true},'NO_IMPACT_EXPLOSION',
    'not the reviewed explosion-less carrier')
-- The donor's package not resident, its chain changed: refused.
pelican_resident=false
refused({sources={5001},projectiles={275},donor=DONOR,continuous=true},'DONOR_NOT_RESIDENT')
pelican_resident=true
local saved=W.read(chain_rows[1].at+4,4)
W.write(chain_rows[1].at+4,W.u32(999))
refused({sources={5001},projectiles={275},donor=DONOR,continuous=true},'DONOR_CHANGED')
W.write(chain_rows[1].at+4,saved)
-- Bound: a round whose copy is not the row's stays as it is; the carrier row changed later: every round stays plain.
local events={}
local binding=assert(impacts.bind({sources={5001},projectiles={275},donor=DONOR,continuous=true,label='rules'},
    function(e)events[#events+1]=e end))
tick()
local _,h1=fire(5001,{type=275,impact=376});tick()
assert(events[#events].code=='UNEXPECTED_EXPLOSION'and impact_of(h1)==376)
carrier_row(275,CARRIERS.baseFlags+0x1000)
local _,h2=fire(5001,{type=275,impact=0});tick()
assert(events[#events].code=='CARRIER_CHANGED'and impact_of(h2)==0,tostring(events[#events].code))
carrier_row(275,CARRIERS.baseFlags)
-- The donor's package unloaded mid-flight: that round stays plain.
pelican_resident=false
local _,h3=fire(5001,{type=275,impact=0});tick()
assert(events[#events].code=='DONOR_NOT_RESIDENT'and impact_of(h3)==0)
pelican_resident=true
local _,h4=fire(5001,{type=275,impact=0});tick()
assert(events[#events].kind=='converted'and impact_of(h4)==234)
binding.cancel()
""")

    def test_the_credit_and_the_explosion_of_one_round_both_land(self):
        # A client's call on the host: its credit binding (each round to the requester) and its explosive rounds follow
        # the same turret; the credit is written first, the explosion follows the exact turret (provenance).
        self.check(r"""
iworld()
W.players({{peer=LOCAL_PEER,avatar=100},{peer=P2}},LOCAL_PEER)
local credit=assert(impacts.bind_credit({sources={5001},projectiles={275},credit_to=P2,label='credit',multiplayer=true}))
local explosive,code,why=impacts.bind({sources={5001},projectiles={275},donor=DONOR,continuous=true,provenance=true,
    multiplayer=true,label='explosive'})
assert(explosive,tostring(code)..' '..tostring(why))
-- One of each per source.
assert(select(2,impacts.bind({sources={5001},projectiles={275},donor=DONOR,continuous=true,provenance=true,
    multiplayer=true}))=='ALREADY_BOUND')
assert(select(2,impacts.bind_credit({sources={5001},projectiles={275},credit_to=P2,multiplayer=true}))=='ALREADY_BOUND')
assert(impacts.binding_of(5001)==explosive)
tick()
local writes=#W.runtime.writes
local _,h=fire(5001,{type=275,impact=0,creditor=LOCAL_PEER})
tick()
assert(creditor(h)==P2 and impact_of(h)==234 and#W.runtime.writes==writes+2,creditor(h)..' '..impact_of(h))
-- Without provenance, the explosion would stop at the requester's credit (another player's round).
explosive.cancel()
local plain=assert(impacts.bind({sources={5001},projectiles={275},donor=DONOR,continuous=true,multiplayer=true,
    label='plain'}))
local _,h2=fire(5001,{type=275,impact=0,creditor=LOCAL_PEER})
tick()
assert(creditor(h2)==P2 and impact_of(h2)==0,'NOT_LOCAL without provenance')
plain.cancel();credit.cancel()
""")

    def test_the_donor_never_reaches_the_other_families(self):
        self.check(r"""
assert(donors.resolve(DONOR)==nil and donors.resolve(DONOR,{automatic=true})==DONOR)
assert(donors.resolve({name=DONOR},{automatic=true})==DONOR)
assert(donors.resolve('Orbital Gas Strike')=='Orbital Gas Strike'and donors.resolve('Orbital Gas Strike',{automatic=true})==nil)
assert(table.concat(donors.names(),',')=='Orbital EMS Strike,Orbital Gas Strike',table.concat(donors.names(),','))
assert(table.concat(donors.names({automatic=true}),',')=='66mm Missile Mk2,Assault walker cannon,Automaton explosion 27,Exploding '
    ..'crossbow,Illuminate explosion 392,Pelican chin autocannon,Strafing run cannon',table.concat(donors.names({automatic=true}),','))
assert(donors.resolve('strafing_run_cannon',{automatic=true})=='Strafing run cannon')
assert(donors.dependency('Strafing run cannon').package=='0x2C26BC4C6592FA14')
-- By key too (a Mod Options choice value has no spaces).
assert(donors.resolve('pelican_chin_autocannon',{automatic=true})==DONOR)
assert(donors.resolve('66mm_missile_mk2',{automatic=true})=='66mm Missile Mk2')
assert(donors.resolve('automaton_explosion_27',{automatic=true})=='Automaton explosion 27')
assert(donors.resolve('illuminate_explosion_392',{automatic=true})=='Illuminate explosion 392')
assert(donors.resolve('automaton_explosion_27')==nil)
-- What a definition loads: the 66mm's effect through the MLS-4X Commando's call-in package; a faction's blast nothing.
assert(donors.dependency('66mm Missile Mk2').package=='0xC0052E5B38E18C33')
assert(donors.dependency(DONOR)==nil and donors.dependency('Automaton explosion 27')==nil)
""")

    def test_a_blast_is_usable_only_while_a_package_that_ships_its_effect_is_resident(self):
        self.check(r"""
iworld()
local world=require('hd2runtime/runtime/event_world').open()
-- The reviewed chains of the other three, as for the Pelican's.
for _,name in ipairs({'66mm Missile Mk2','Automaton explosion 27','Illuminate explosion 392'})do
    for _,item in ipairs(CP.explosionDonors[name].rows)do
        local at=W.alloc(item.stride);W.write(at,b.unhex(item.reviewed))
        W.write(W.GAME+tonumber(item.table:sub(3),16)+item.id*8,W.u64(at))
    end
end
donors.READY_CALLS=0
-- loadout_shared resident: the Pelican's blast is ready; the 66mm's effect is not in it; a faction's is not resident.
assert(donors.ready(world,DONOR))
assert(donors.resident_package(DONOR).name=='packages/content/loadout_shared')
local ok,code,why=donors.ready(world,'Automaton explosion 27')
assert(not ok and code=='DONOR_NOT_RESIDENT'and why=='Automaton explosion 27\'s effect ships only in '
    ..'packages/content/cyborgs; none is resident',tostring(why))
assert(select(3,donors.ready(world,'Illuminate explosion 392')):find('packages/content/illuminate',1,true))
assert(select(2,donors.ready(world,'66mm Missile Mk2'))=='DONOR_NOT_RESIDENT')
-- An Automaton mission (its faction content resident): explosion 27 is ready; the Commando's package: the 66mm's.
resident['0xFDF011DAECF24312']=true
assert(donors.ready(world,'Automaton explosion 27'))
resident['0xC0052E5B38E18C33']=true
assert(donors.ready(world,'66mm Missile Mk2'))
-- The residency is remembered for READY_CALLS checks, a refusal too (each read walks the engine's package list).
donors.READY_CALLS=2
donors.reset_for_tests()
resident['0xFDF011DAECF24312']=nil
assert(not donors.ready(world,'Automaton explosion 27'))
resident['0xFDF011DAECF24312']=true
assert(not donors.ready(world,'Automaton explosion 27')and not donors.ready(world,'Automaton explosion 27'))
assert(donors.ready(world,'Automaton explosion 27'),'re-read after READY_CALLS checks')
""")
        # A custom stratagem's launcher, Eagle or orbital never takes it: their validation resolves without automatic.
        import re
        source = (ROOT / 'runtime/custom_stratagems.lua').read_text(encoding='utf-8')
        calls = re.findall(r'donors\.resolve\(([^()]*(?:\([^()]*\)[^()]*)*)\)', source)
        self.assertGreaterEqual(len(calls), 4)
        for args in calls:
            self.assertNotIn('automatic', args)


class GunshipTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + PELICANS + "\nlocal PROOF_ADDON=''\nlocal PROOF_RESOURCE="
            + lua_literal('mods/test/gunship') + '\n' + 'return (function()\n' + HARNESS + GATLING + WEAPON + AI
            + HEADING + PROOF + GUNSHIP + body + '\nend)()\n'), b'ok')

    def test_the_gun_option(self):
        self.lua(r"""
local ok=assert(gunship.check_gun({impact_explosion='Pelican chin autocannon'}))
assert(ok.impact=='Pelican chin autocannon')
assert(gunship.check_gun({impact_explosion={name='Pelican chin autocannon'}}).impact=='Pelican chin autocannon')
local bad,why=gunship.check_gun({impact_explosion='Orbital Gas Strike'})
assert(not bad and why=='gun.impact_explosion must be an explosion donor reviewed for its rate (a slow donor needs '
    ..'gun.rpm): 66mm Missile Mk2, Assault walker cannon, Automaton explosion 27, Exploding crossbow, Illuminate explosion '
    ..'392, Pelican chin autocannon, Strafing run cannon',tostring(why))
assert(gunship.check_gun(FROZEN).impact==nil)
assert(gunship.check_gun({impact_explosion='automaton_explosion_27'}).impact=='Automaton explosion 27')
-- A Mod Options choice of keys and 'none': its value now.
local options=require('hd2runtime/api/options')
local page=options.page({id='pelican_test',title='Pelican test'})
local choice=page:choice({id='blast',label='Blast',choices={'Off','Pelican','66mm','Automaton','Illuminate'},
    values={'none','pelican_chin_autocannon','66mm_missile_mk2','automaton_explosion_27','illuminate_explosion_392'},
    default=2})
local g=assert(gunship.check_gun({impact_explosion=choice}))
assert(g.impact=='Pelican chin autocannon'and g.impact_set)
choice.selected=1
g=assert(gunship.check_gun({impact_explosion=choice}))
assert(g.impact==nil and g.impact_set and gunship.impact_now(choice)=='none')
choice.selected=4
assert(gunship.check_gun({impact_explosion=choice}).impact=='Automaton explosion 27')
local wrong=page:choice({id='wrong',label='Wrong',choices={'Gas','Off'},values={'orbital_gas_strike','none'},default=2})
local bad2,why2=gunship.check_gun({impact_explosion=wrong})
assert(not bad2 and why2:find('choice value orbital_gas_strike is neither',1,true),tostring(why2))
local slider=page:slider({id='s',label='S',min=1,max=2,step=1,default=1})
assert(select(2,gunship.check_gun({impact_explosion=slider}))=='gun.impact_explosion must be a donor or a Mod Options '
    ..'choice')
assert(table.concat(gunship.impact_assets(choice),',')=='MLS-4X Commando')
assert(#gunship.impact_assets('Pelican chin autocannon')==0)
return 'ok'
""")

    def test_its_own_turrets_configured_round_is_bound_after_the_credit(self):
        self.lua(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
tick(4)
scene()
controller()
stage(0,2,0)
ai(4)
local impacts=require('hd2runtime/runtime/projectile_impact')
local order={}
local credited,bound
impacts.bind_credit=function(spec)order[#order+1]='credit';credited=spec;return {status='active',cancel=function()end}end
impacts.bind=function(spec,cb)order[#order+1]='impact';bound=spec;return {status='active',cancel=function()end}end
local gun={}
for k,v in pairs(FROZEN)do gun[k]=v end
gun.impact_explosion='Pelican chin autocannon'
local events={}
assert(gunship.arm(9501,{gun=gun,credit_peer='5555666677778888',label='cas'},function(e)events[#events+1]=e end))
tick(16)
assert(bound and bound.sources[1]==8102 and bound.projectiles[1]==275 and bound.donor=='Pelican chin autocannon'
    and bound.continuous==true and bound.provenance==true,'the turret\'s own round 275, every round')
assert(table.concat(order,',')=='credit,impact',table.concat(order,','))
local armed
for _,e in ipairs(events)do if e.kind=='armed'then armed=e end end
assert(armed and armed.impact_explosion=='Pelican chin autocannon')
local n=0
for _,line in ipairs(logged)do if line:find('cas: EXPLOSIVE ROUNDS: chin turret 8102\'s projectile 275 rounds request '
    ..'Pelican chin autocannon\'s explosion 234 on impact',1,true)then n=n+1 end end
assert(n==1,table.concat(logged,' | '))
return 'ok'
""")

    def test_a_refused_binding_leaves_the_rounds_plain_and_says_so(self):
        self.lua(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
tick(4)
scene()
controller()
stage(0,2,0)
ai(4)
local impacts=require('hd2runtime/runtime/projectile_impact')
impacts.bind=function()return nil,'DONOR_NOT_RESIDENT','Pelican chin autocannon\'s package is not resident'end
local gun={}
for k,v in pairs(FROZEN)do gun[k]=v end
gun.impact_explosion='Pelican chin autocannon'
local events={}
assert(gunship.arm(9501,{gun=gun,label='cas'},function(e)events[#events+1]=e end))
tick(16)
local refused,armed
for _,e in ipairs(events)do
    if e.kind=='refused'and e.stage=='impact'then refused=e end
    if e.kind=='armed'then armed=e end
end
assert(refused and refused.code=='DONOR_NOT_RESIDENT'and armed and armed.impact_explosion==nil)
local n=0
for _,line in ipairs(logged)do if line:find('cas: EXPLOSIVE ROUNDS REFUSED (its rounds stay plain): DONOR_NOT_RESIDENT',
    1,true)then n=n+1 end end
assert(n==1,table.concat(logged,' | '))
return 'ok'
""")


class CrossbowTests(unittest.TestCase):
    """The CB-9 Exploding Crossbow's blast: a primary weapon's package, loaded through the asset loader by its catalogue
    key (explosion_donors.assets) before the chin gun's rounds are bound."""
    def lua(self, body):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + PELICANS + "\nlocal PROOF_ADDON=''\nlocal PROOF_RESOURCE="
            + lua_literal('mods/test/gunship') + '\n' + 'return (function()\n' + HARNESS + GATLING + WEAPON + AI
            + HEADING + PROOF + GUNSHIP + body + "\nreturn 'ok'\nend)()\n"), b'ok')

    SETUP = r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
tick(4)
scene()
controller()
stage(0,2,0)
ai(4)
local donors=require('hd2runtime/runtime/explosion_donors');donors.reset_for_tests()
local CROSS=donors.dependency('Exploding crossbow').package
assert(CROSS=='0xBA40A2814D01BDA0')
local loaded=false
local prev=W.runtime.package_state
W.runtime.package_state=function(hex)if hex==CROSS then return loaded and'resident'or'queued'end return prev(hex)end
local impacts=require('hd2runtime/runtime/projectile_impact')
local bound
local gun={}
for k,v in pairs(FROZEN)do gun[k]=v end
gun.impact_explosion='exploding_crossbow'
"""

    def test_the_gun_waits_for_the_crossbows_package_then_binds(self):
        self.lua(self.SETUP + r"""
impacts.bind=function(spec)bound=spec;return {status='active',cancel=function()end}end
local requests=GX.requests
local g=assert(gunship.arm(9501,{gun=gun,label='cas'},function()end))
tick(16)
-- Its package requested through the asset loader; the gun waits for it (well inside the wait).
assert(GX.requests>requests,'the crossbow package was not requested')
assert(bound==nil and not g.config and(g.waited or 0)<gunship.SOUND_WAIT,tostring(g.waited))
loaded=true
tick(8)
assert(bound and bound.donor=='Exploding crossbow'and bound.continuous and bound.projectiles[1]==275,
    tostring(bound and bound.donor))
""")

    def test_a_package_that_never_loads_leaves_the_rounds_plain(self):
        self.lua(self.SETUP + r"""
local tried
impacts.bind=function(spec)tried=spec;return nil,'DONOR_NOT_RESIDENT','Exploding crossbow\'s effect ships only in ...'end
local g=assert(gunship.arm(9501,{gun=gun,label='cas'},function()end))
for _=1,200 do tick(1)if g.config then break end end
-- After the wait the gun is armed anyway; its rounds stay plain and the log says why.
assert(g.config and tried and tried.donor=='Exploding crossbow')
local n=0
for _,line in ipairs(logged)do if line:find('cas: EXPLOSIVE ROUNDS REFUSED (its rounds stay plain): DONOR_NOT_RESIDENT',
    1,true)then n=n+1 end end
assert(n==1,table.concat(logged,' | '))
""")


class SpreadAndAimTests(unittest.TestCase):
    """gun.spread as a Mod Options choice of widths, and the gunship's read-only aim diagnostic (research section 20b)."""
    def lua(self, body):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + PELICANS + "\nlocal PROOF_ADDON=''\nlocal PROOF_RESOURCE="
            + lua_literal('mods/test/gunship') + '\n' + 'return (function()\n' + HARNESS + GATLING + WEAPON + AI
            + HEADING + PROOF + GUNSHIP + body + "\nreturn 'ok'\nend)()\n"), b'ok')

    def test_a_spread_choice(self):
        self.lua(r"""
local options=require('hd2runtime/api/options')
local page=options.page({id='spread_test',title='Spread test'})
local spread=page:choice({id='spread',label='Spread',choices={'Tight','Wide'},values={1,100},default=2})
local gun={}
for k,v in pairs(FROZEN)do gun[k]=v end
gun.spread=spread
assert(gunship.check_gun(gun).spread==100 and gunship.gun_now(gun).spread==100 and gunship.has_choice(gun))
spread.selected=1
assert(gunship.check_gun(gun).spread==1 and gunship.gun_now(gun).spread==1)
local bad=page:choice({id='bad',label='Bad',choices={'A','B'},values={1,500},default=1})
gun.spread=bad
assert(select(2,gunship.check_gun(gun))=='gun.spread: choice value 500 is not a width in mrad above 0 and at most 100',
    tostring(select(2,gunship.check_gun(gun))))
assert(not gunship.has_choice(FROZEN))
""")

    def test_the_aim_diagnostic_samples_while_firing(self):
        self.lua(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
tick(4)
scene()
controller()
stage(0,2,0)
ai(4)
assert(gunship.arm(9501,{gun=FROZEN,label='cas'},function()end))
tick(16)
local g=gunship.of(9501)
assert(g and g.config,'armed')
-- The AI fires at target 777 (213 stage 12); the turret points 1 m above the aim point, which is 0.5 m above the root.
weapon.ai_state=function()return {id=213,stage=12,target=777}end
weapon.target_step=function()return {}end   -- the target controller is not under test here
weapon.aim_state=function()
    return {target=777,point={x=0,y=50,z=0.5},aim={x=0,y=100,z=1.5},muzzle={x=0,y=0,z=0.5},velocity={x=0,y=0,z=0},
        recoil={x=0,y=0}}
end
local wm=require('hd2runtime/runtime/event_world')
local es,up=wm.entity_state,wm.unit_position
wm.entity_state=function(w,e)if e==777 then return {descriptor={unit=4242}}end return es(w,e)end
wm.unit_position=function(w,u)if u==4242 then return {x=0,y=50,z=0}end return up(w,u)end
gunship.AIM_EVERY=0          -- a sample every update here (1 s in a mission)
for _=1,12 do tick(1)end
local n=0
for _,line in ipairs(logged)do if line:find('cas: AIM #',1,true)then n=n+1 end end
assert(n==gunship.AIM_LOG,'the first samples are logged: '..n..' | '..table.concat(logged,' | '):sub(-600))
local first
for _,line in ipairs(logged)do if line:find('cas: AIM #1:',1,true)then first=line end end
assert(first and first:find('target 777 at 50.0 m: the shot crosses 0.50 m above its aim point',1,true)
    and first:find('the aim point is 0.50 m above the target\'s root',1,true),tostring(first))
assert(g.aim.n>gunship.AIM_LOG)
""")


class AimPointTests(unittest.TestCase):
    """The chin turret's aim point, lowered through its own targeting record's aim override (research/custom-payloads
    pelicanAim; build/test-artifacts/aim-research/aim-point.md), and recoil block A zeroed with block B."""
    def weapon(self, body):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + PELICANS + 'return (function()\n' + GATLING + WEAPON + body
            + "\nreturn 'ok'\nend)()\n"), b'ok')

    def gunship(self, body):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + PELICANS + "\nlocal PROOF_ADDON=''\nlocal PROOF_RESOURCE="
            + lua_literal('mods/test/gunship') + '\n' + 'return (function()\n' + HARNESS + GATLING + WEAPON + AI
            + HEADING + PROOF + GUNSHIP + body + "\nreturn 'ok'\nend)()\n"), b'ok')

    def test_the_research(self):
        aim = RESEARCH['pelicanAim']
        self.assertEqual((aim['global'], aim['map'], aim['records'], aim['stride'], aim['network'], aim['networkStride'],
            aim['networkBits'], aim['point'], aim['curveA'], aim['curveB'], aim['t'], aim['mode'], aim['advance']),
            (0x3326D30, 0x150, 0x178, 0xD0, 0x180, 0x18, 0x10, 0x8, 0x20, 0x2C, 0x50, 0x60, 0x6C))
        self.assertEqual((aim['linearMode'], aim['on'], aim['off']), (2, 1.0, -1.0))
        self.assertEqual(len(RESEARCH['proofs']['pelicanAim']), 73)
        roles = ' '.join(p['role'] for p in RESEARCH['proofs']['pelicanAim'])
        for text in ('T (+8) = Q', 'curve(t)', 'mode 2', 'targeting init: t = -1'):
            self.assertIn(text, roles)
        # Every live targeting record of every retained snapshot has the override off.
        for name, t in aim['observed'].items():
            if t:
                self.assertEqual(set(t['t']) - {'-1.0'}, set(), name)

    def test_the_override_is_written_released_and_guarded(self):
        self.weapon(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
scene()
local world=world_module.open()
local PA=require('hd2runtime/domains/custom_payloads').pelicanAim
local function lower(p)return in_update(function()return weapon.aim_lower(world,8102,p,'test')end)end
local function code(...)return select(2,...)end
-- The game.dll pins not proven: refused.
assert(code(lower({x=1,y=2,z=3}))=='UNSUPPORTED_BUILD')
for _,pin in ipairs(PA.pins)do W.write(W.GAME+pin.rva,b.unhex(pin.hex))end
local NET=W.alloc(0x400);W.write(TGCOMP+PA.network,W.u64(NET))
W.write(TGRECS+PA.t,f32(-1))
-- Not a turret this Runtime configured: refused.
assert(code(lower({x=1,y=2,z=3}))=='NOT_CONFIGURED')
assert(in_update(function()return weapon.configure(world,9501,{projectile=148,rpm=600},'test')end))
local rec=W.read(TGRECS,PA.stride)
local w0=#W.runtime.writes
local r,c,why=lower({x=10,y=20,z=0.5})
assert(r and r.applied and r.first and r.writes==4,tostring(c)..' '..tostring(why))  -- A, B, mode, t (advance is 0)
local st=weapon.aim_override_state(world,8102)
assert(st.t==1 and st.mode==2 and st.advance==0 and st.a.x==10 and st.b.y==20 and st.b.z==0.5,'the override')
-- Only the override members changed.
local after=W.read(TGRECS,PA.stride)
for k=0,PA.stride-1 do
    local inside=(k>=PA.curveA and k<PA.curveA+12)or(k>=PA.curveB and k<PA.curveB+12)or(k>=PA.t and k<PA.t+4)
        or(k>=PA.mode and k<PA.mode+4)or k==PA.advance
    if not inside then assert(after:byte(k+1)==rec:byte(k+1),'byte +'..k..' changed')end
end
-- The same point: nothing; a new point: A and B only.
assert(lower({x=10,y=20,z=0.5}).writes==0)
r=lower({x=11,y=20,z=0.5})
assert(r.writes==2 and not r.first,tostring(r.writes))
-- Released: t = -1 (the game's own off); releasing again writes nothing.
local rel=in_update(function()return weapon.aim_release(world,8102,'test')end)
assert(rel.applied and weapon.aim_override_state(world,8102).t==-1)
assert(in_update(function()return weapon.aim_release(world,8102,'test')end).writes==0)
-- Another user's override is never touched.
W.write(TGRECS+PA.t,f32(0.5));W.write(TGRECS+PA.mode,W.u32(0))
assert(code(lower({x=1,y=1,z=1}))=='OVERRIDE_IN_USE')
assert(code(in_update(function()return weapon.aim_release(world,8102,'test')end))=='OVERRIDE_IN_USE')
W.write(TGRECS+PA.t,f32(-1))
-- A scripted aim (network bits), a point that is not finite, outside the update, a client: refused.
W.write(NET+PA.networkBits,W.u32(2))
assert(code(lower({x=1,y=1,z=1}))=='NETWORK_BITS')
W.write(NET+PA.networkBits,W.u32(0))
assert(code(lower({x=0/0,y=1,z=1}))=='INVALID')
assert(code(weapon.aim_lower(world,8102,{x=1,y=1,z=1},'test'))=='NOT_GAME_THREAD')
W.state(4,{host=false})
assert(code(lower({x=1,y=1,z=1}))=='NOT_HOST')
W.state(4)
""")

    def test_zero_recoil_zeroes_block_a_too(self):
        self.weapon(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
scene()
local world=world_module.open()
local AW=AIMD.weaponData
local typeA=wdrec(AIMD.observed.chinTurret):sub(1,28)
W.write(WDRECS+AW.recoilA,typeA)
local r=weapon.configure_recoil(world,8102,'test','zero')
assert(r.applied and r.a and r.a.applied and r.a.before.y==10,tostring(r.reason)..' '..tostring(r.a and r.a.reason))
local a=W.read(WDRECS+AW.recoilA,28)
assert(b.value(a,0,'f32')==0 and b.value(a,4,'f32')==0 and a:sub(9)==typeA:sub(9),'block A zeroed, the rest kept')
assert(n('block A 2.5, 10 -> ZERO: 0, 0 (read back true)')==1,table.concat(logged,' | '))
""")

    def test_the_gun_option(self):
        self.gunship(r"""
local gun={}
for k,v in pairs(FROZEN)do gun[k]=v end
gun.aim_height=0.4
assert(gunship.check_gun(gun).aim_height==0.4)
gun.aim_height=0
assert(gunship.check_gun(gun).aim_height==nil,'0 is the game\'s own aim')
gun.aim_height=4
assert(select(2,gunship.check_gun(gun))=="gun.aim_height is metres above the target's feet, 0 (the game's own) to 3")
assert(select(2,gunship.check_gun({aim_height=0.4}))=="gun.aim_height follows the Gatling AI's target: it needs "
    .."behave_as = 'gatling_sentry'")
local options=require('hd2runtime/api/options')
local choice=options.page({id='aim_test',title='Aim test'}):choice({id='aim',label='Aim',choices={'Game','Low'},
    values={0,0.4},default=2})
gun.aim_height=choice
assert(gunship.check_gun(gun).aim_height==0.4 and gunship.gun_now(gun).aim_height==0.4 and gunship.has_choice(gun))
choice.selected=1
assert(gunship.check_gun(gun).aim_height==nil)
""")

    def test_the_gunship_follows_the_target_and_leaves_bile_titans_alone(self):
        self.gunship(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
tick(4)
scene()
controller()
stage(0,2,0)
ai(4)
local gun={}
for k,v in pairs(FROZEN)do gun[k]=v end
gun.aim_height=0.4
assert(gunship.arm(9501,{gun=gun,label='cas'},function()end))
tick(16)
local g=gunship.of(9501)
assert(g and g.config,'armed')
local lowered,released,written={},0,nil
weapon.aim_lower=function(world,turret,p)lowered[#lowered+1]=p;written=p;return {applied=true,writes=5,first=true}end
weapon.aim_release=function()released=released+1;return {applied=true,writes=1}end
weapon.aim_override_state=function()return written and{b=written,point=written}or nil end
weapon.target_step=function()return {}end
local target=777
weapon.ai_state=function()return {id=213,stage=12,target=target}end
local wm=require('hd2runtime/runtime/event_world')
local et,es,up=wm.entity_type,wm.entity_state,wm.unit_position
local pos={[4777]={x=10,y=20,z=1},[4888]={x=50,y=60,z=2}}
wm.entity_type=function(w,e)if e==777 then return'00000000000007A7'elseif e==888 then return'9E2E17F2CCCCAFDD'end return et(w,e)end
wm.entity_state=function(w,e)if e==777 then return {descriptor={unit=4777}}elseif e==888 then return {descriptor={unit=4888}}end
    return es(w,e)end
wm.unit_position=function(w,u)if pos[u]then return pos[u]end return up(w,u)end
tick(2)
assert(#lowered>=1 and lowered[1].x==10 and lowered[1].y==20 and math.abs(lowered[1].z-1.4)<1e-6,'its feet + 0.4 m')
local n0=#lowered
-- A 1 cm move is not written again; a 1 m move is.
pos[4777]={x=10.01,y=20,z=1};tick(2)
assert(#lowered==n0)
pos[4777]={x=11,y=20,z=1};tick(2)
assert(#lowered==n0+1 and lowered[#lowered].x==11)
-- A Bile Titan: the game's own aim node (released).
target=888;tick(2)
assert(released==1 and #lowered==n0+1,'Bile Titans keep the game\'s aim')
-- Back to a bug, then no target: released again.
target=777;tick(2)
assert(#lowered==n0+2)
target=nil;tick(2)
assert(released==2)
local function said(text)for _,line in ipairs(logged)do if line:find(text,1,true)then return true end end return false end
assert(said('cas: AIM POINT LOWERED: chin turret 8102 aims at target 777\'s feet + 0.40 m'),table.concat(logged,' | '))
assert(said('cas: AIM POINT CONSUMED: the game aims at the written point'),table.concat(logged,' | '))
""")


class ActivityTests(unittest.TestCase):
    """The gunship's activity diagnostic (read-only): time per AI stage, idle spells with the enemies it could attack, and
    why its locks were released; and the 3 s give-up."""
    def gunship(self, body):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + PELICANS + "\nlocal PROOF_ADDON=''\nlocal PROOF_RESOURCE="
            + lua_literal('mods/test/gunship') + '\n' + 'return (function()\n' + HARNESS + GATLING + WEAPON + AI
            + HEADING + PROOF + GUNSHIP + body + "\nreturn 'ok'\nend)()\n"), b'ok')

    def test_idle_spells_and_the_summary(self):
        self.gunship(r"""
assert(weapon.RELEASE_SECONDS==3,'3 s of firing without damage before a target is let go')
pworld()
BOMB.set_clock(T0)
tcount(0)
tick(4)
scene()
controller()
stage(0,2,0)
ai(4)
local g=assert(gunship.arm(9501,{gun=FROZEN,label='cas'},function()end))
tick(16)
assert(g.config,'armed')
local stage_now=12
weapon.ai_state=function()return {id=213,stage=stage_now,target=777}end
weapon.target_step=function()return {}end
weapon.aim_state=function()return nil end
weapon.candidates=function()return {{entity=901,distance=64},{entity=902,distance=70}}end
-- Firing, then a long spell in alert and aiming while two enemies could be attacked, then firing again.
for _=1,10 do tick(1)end
stage_now=3
for _=1,40 do tick(1)end
stage_now=5
for _=1,10 do tick(1)end
stage_now=12
for _=1,10 do tick(1)end
weapon.target_step=function()return {{kind='released',reason='not hittable'},{kind='released',reason='dead'}}end
tick(1)
local idle
for _,line in ipairs(logged)do if line:find('cas: IDLE ',1,true)then idle=line end end
assert(idle and idle:find('without firing: alert',1,true)and idle:find('enemies it could attack meanwhile: up to 2 '
    ..'(nearest 64 m)',1,true),tostring(idle))
assert(g.activity.spells==1 and g.activity.with>0 and g.activity.releases['not hittable']==1)
local text
for _,line in ipairs(logged)do if line:find('SUMMARY',1,true)then text=line end end
assert(text==nil,'not ended yet')
""")


class AggressiveTargetingTests(unittest.TestCase):
    """Behaviour 213's own timers made due sooner (research/custom-payloads pelicanIdle; build/test-artifacts/ai-research/
    idle-ai.md): the re-pick while it searches with something to attack, the fire check while it aims at a live, perceived
    target; and an unaimable target replaced by the one the turret turns least to reach."""
    PRELUDE = r"""
local PI=require('hd2runtime/domains/custom_payloads').pelicanIdle
for _,pin in ipairs(PI.pins)do W.write(W.GAME+pin.rva,b.unhex(pin.hex))end
-- The muzzle, 30 m from enemy 5555.
W.write(WDRECS+AIMD.weaponData.muzzle,f32(60)..f32(70)..f32(12))
local function u64at(at)local raw=W.read(at,8);return b.u32(raw,0)+b.u32(raw,4)*4294967296 end
local function has(list,kind)for _,e in ipairs(list)do if e.kind==kind then return true end end return false end
"""

    def check(self, body):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + PELICANS + 'return (function()\n' + GATLING + WEAPON + AI_FIXTURE
            + RELEASE + self.PRELUDE + body + "\nreturn 'ok'\nend)()\n"), b'ok')

    def test_the_re_pick_is_made_due_while_it_searches_with_something_to_attack(self):
        self.check(r"""
assert(weapon.AGGRESSIVE and weapon.AIM_SECONDS==1.5)
local t=T0+5000000
ai(3)
W.write(record(1)+AID.repick,W.u64(t+1000000))
-- Nothing it could attack: its own 1 s re-pick stands.
local ev=step(t)
assert(not has(ev,'repick_forced')and repick()==t+1000000,kinds(ev))
-- An enemy it could attack: the re-pick due now.
perceive(5555,90,70,12)
ev=step(t+300000)
assert(has(ev,'repick_forced')and repick()==t+300000,kinds(ev))
-- Not again within 0.25 s.
W.write(record(1)+AID.repick,W.u64(t+2000000))
ev=step(t+400000)
assert(not has(ev,'repick_forced'),kinds(ev))
-- Four forced re-picks that left it searching: a 2 s pause.
local forced=1
local clock=t+400000
for _=1,6 do
    clock=clock+300000
    W.write(record(1)+AID.repick,W.u64(clock+1000000))
    if has(step(clock),'repick_forced')then forced=forced+1 end
end
assert(forced==4,'forced '..forced)
-- Back to aiming or firing: the streak is forgotten.
""")

    def test_the_fire_check_is_made_due_while_it_aims_at_a_live_perceived_target(self):
        self.check(r"""
local t=T0+5000000
perceive(5555,90,70,12)
ai(5,5555)
local FC=record(1)+AID.fireCheck
W.write(FC,W.u64(t+500000))
local ev=step(t)
assert(has(ev,'fire_check_forced')and u64at(FC)==t,kinds(ev))
-- Its target no longer perceived: the game's own 0.5 s check stands.
perceive(5555,90,70,12,false)
W.write(FC,W.u64(t+600000))
ev=step(t+50000)
assert(not has(ev,'fire_check_forced')and u64at(FC)==t+600000,kinds(ev))
-- Off: nothing is made due.
weapon.AGGRESSIVE=false
perceive(5555,90,70,12)
ev=step(t+100000)
assert(not has(ev,'fire_check_forced'),kinds(ev))
""")

    def test_an_unaimable_target_is_replaced_by_the_one_the_turret_turns_least_to_reach(self):
        self.check(r"""
local t=T0+5000000
-- 5555 30 m away; 6666 80 m from the muzzle and 99 m from 5555 (none near it).
W.add{entity=7777,type='73F8498BFFDCF415',unit=7777,health=500};W.unit(7777,20,140,12)
perceive(5555,90,70,12)
perceive(7777,20,140,12)
W.write(WDRECS+AIMD.weaponData.aim,f32(90)..f32(70)..f32(12))
ai(5,5555)
local ev=step(t)
assert(has(ev,'locked'),kinds(ev))
-- Aiming 1.6 s without firing: let go, and the turret is given the least-turn candidate through the setter.
ev=step(t+1600000)
assert(kinds(ev):find('released:cannot fire',1,true),kinds(ev))
local target=b.u32(W.read(record(1)+AI.target,4),0)
assert(target==7777,'the replacement: '..target..' | '..kinds(ev))
""")


class MirrorTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + PELICANS + 'return (function()\n' + GATLING + WEAPON + MIRROR
            + body + "\nreturn 'ok'\nend)()\n"), b'ok')

    def test_every_other_machine_binds_its_own_copys_rounds(self):
        self.check(r"""
local world=client_copy()
local impacts=require('hd2runtime/runtime/projectile_impact')
local bound,binds={},0
impacts.bind=function(spec,cb)binds=binds+1;bound=spec;return {status='active',cancel=function()end}end
GUN.impact_explosion='Pelican chin autocannon'
local m=mirror()
tick()                                       -- its gun copy configured; the blast's package requested
assert(m.configured and binds==0)
tick()                                       -- the blast's package resident: bound
assert(binds==1,table.concat(logged,' | '))
assert(bound.sources[1]==8102 and bound.projectiles[1]==148 and bound.donor=='Pelican chin autocannon'
    and bound.continuous==true and bound.provenance==true and bound.multiplayer==true and bound.client==true)
assert(n('REMOTE CUSTOM PELICAN: m: EXPLOSIVE ROUNDS on this machine\'s own copy: its projectile 148 rounds request '
    ..'Pelican chin autocannon\'s explosion 234 on impact')==1,table.concat(logged,' | '))
tick();tick()
assert(binds==1,'bound once')
assert(m.describe():find('explosive rounds Pelican chin autocannon',1,true),m.describe())
gone();tick()
assert(n('REMOTE CUSTOM PELICAN: m: explosive rounds 0 converted, 0 impacts seen, 0 stayed plain')==1,
    table.concat(logged,' | '))
""")

    def test_a_mod_options_choice_is_read_on_this_machine(self):
        self.check(r"""
local world=client_copy()
local impacts=require('hd2runtime/runtime/projectile_impact')
local bound,binds=nil,0
impacts.bind=function(spec)binds=binds+1;bound=spec;return {status='active',cancel=function()end}end
local page=require('hd2runtime/api/options').page({id='mirror_test',title='Mirror test'})
local choice=page:choice({id='blast',label='Blast',choices={'Off','66mm'},values={'none','66mm_missile_mk2'},default=1})
GUN.impact_explosion=choice
local m=mirror()
tick();tick()
assert(m.configured and binds==0 and n('REMOTE CUSTOM PELICAN: m: explosive rounds off (the Mod Options choice is none)')
    ==1,table.concat(logged,' | '))
gone();tick()
assert(n('explosive rounds 0 converted')==0,'no count line for none')
""")
        self.check(r"""
local world=client_copy()
local impacts=require('hd2runtime/runtime/projectile_impact')
local bound
impacts.bind=function(spec)bound=spec;return {status='active',cancel=function()end}end
local page=require('hd2runtime/api/options').page({id='mirror_test',title='Mirror test'})
local choice=page:choice({id='blast',label='Blast',choices={'Off','66mm'},values={'none','66mm_missile_mk2'},default=2})
GUN.impact_explosion=choice
local m=mirror()
tick();tick()
assert(bound and bound.donor=='66mm Missile Mk2',tostring(bound and bound.donor))
assert(m.describe():find('explosive rounds 66mm Missile Mk2',1,true),m.describe())
""")

    def test_without_the_option_nothing_is_bound(self):
        self.check(r"""
local world=client_copy()
local impacts=require('hd2runtime/runtime/projectile_impact')
local binds=0
impacts.bind=function()binds=binds+1;return {status='active',cancel=function()end}end
local m=mirror()
tick();tick()
assert(m.configured and binds==0 and n('EXPLOSIVE ROUNDS')==0)
""")


class StrafingRoundTests(unittest.TestCase):
    """The Eagle Strafing Run's own 23mm rounds on the chin gun's own copies (gun.round = 'strafing_run' or
    'strafing_run_pattern'; runtime/pelican_weapon.lua M.STRAFING)."""
    def weapon(self, body):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + PELICANS + 'return (function()\n' + GATLING + WEAPON + body
            + "\nreturn 'ok'\nend)()\n"), b'ok')

    def test_the_research(self):
        r = RESEARCH['pelicanRounds']['strafing_run']
        self.assertEqual((r['projectile'], r['plain'], r['pattern'], r['explosion'], r['damage'], r['velocity'], r['mass'],
            r['asset']), (16, 27, [16, 27, 27, 27], 50, 218, 1050.0, 400.0, 'Eagle Strafing Run'))
        self.assertIn('packages/generated/loadout/eagle_base', {p['name'] for p in r['packages']})

    def test_its_own_copy_fires_the_he_round_in_the_eagles_pattern(self):
        self.weapon(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
scene()
local world=world_module.open()
local ROW16=projectile_row(16,1050,400,218);W.write(ROW16+0x90,W.u32(50))
local ROW27=projectile_row(27,1050,400,218)
local function cfg(spec)return in_update(function()return weapon.configure(world,9501,spec,'test')end)end
local SPACK=weapon.strafing_dependency().package
assert(SPACK=='0x2C26BC4C6592FA14')
local prev=W.runtime.package_state
local absent=true
W.runtime.package_state=function(hex)if hex==SPACK then return absent and'absent'or'resident'end return prev(hex)end
-- Its package not resident, its plain twin not the reviewed row, the pattern with another round: refused, nothing written.
local w0=#W.runtime.writes
assert(select(2,cfg({projectile=16,rpm=1600,pattern='strafing_run'}))=='ASSET_UNAVAILABLE'and#W.runtime.writes==w0)
absent=false
W.write(ROW27+0x3C,W.u32(219))
assert(select(2,cfg({projectile=16,rpm=1600,pattern='strafing_run'}))=='DONOR_UNEXPECTED'and#W.runtime.writes==w0)
W.write(ROW27+0x3C,W.u32(218))
assert(select(2,cfg({projectile=275,rpm=1600,pattern='strafing_run'}))=='INVALID')
assert(select(2,cfg({projectile=16,rpm=1600,pattern='other'}))=='INVALID')
local r16,r27=W.read(ROW16,272),W.read(ROW27,272)
local r,code,reason=cfg({projectile=16,rpm=1600,pattern='strafing_run'})
assert(r and r.verified,tostring(code)..' '..tostring(reason))
assert(r.writes==9,'writes '..tostring(r.writes))                       -- 2 weapon + mode + 4 entries + 2 record
-- Its own magazine copy holds the Eagle's pattern (HE, plain, plain, plain); its own ProjectileWeapon copy the HE round.
local copy=W.read(MGCOPIES,0x14)
assert(b.u32(copy,0)==1 and b.u32(copy,4)==16 and b.u32(copy,8)==27 and b.u32(copy,12)==27 and b.u32(copy,16)==27)
local w=pelicans.weapon_config(world,8102)
assert(w.copy.projectileType==16 and w.magazine.pattern and w.magazine.length==4)
assert(r.donor.projectile==16 and r.donor.pattern[1]==16 and r.verify.rows)
-- Neither row was written: only its own copies name them.
assert(W.read(ROW16,272)==r16 and W.read(ROW27,272)==r27)
assert(n('holds the pattern 16,27,27,27')==1,table.concat(logged,' | '))
""")

    def test_every_round_without_the_pattern(self):
        self.weapon(r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
scene()
local world=world_module.open()
local ROW16=projectile_row(16,1050,400,218);W.write(ROW16+0x90,W.u32(50))
local r,code,reason=in_update(function()return weapon.configure(world,9501,{projectile=16,rpm=1600},'test')end)
assert(r and r.verified and r.writes==2,tostring(code)..' '..tostring(reason))
local w=pelicans.weapon_config(world,8102)
assert(w.copy.projectileType==16 and not w.magazine.pattern)
""")

    def test_the_gunship_passes_its_round_and_pattern(self):
        body = r"""
pworld()
BOMB.set_clock(T0)
tcount(0)
tick(4)
scene()
controller()
stage(0,2,0)
ai(4)
local captured
weapon.strafing_assets=function()return'ready'end
weapon.configure=function(world,pelican,spec)captured=spec;return nil,'TEST','stopped here'end
local options=require('hd2runtime/api/options')
local round=options.page({id='round_test',title='Round test'}):choice({id='round',label='Round',
    choices={'AP4','23mm','23mm pattern'},values={'ap4','strafing_run','strafing_run_pattern'},default=3})
local gun={}
for k,v in pairs(FROZEN)do gun[k]=v end
gun.round=round
assert(gunship.check_gun(gun).round=='strafing_run_pattern')
assert(gunship.gun_now(gun).round=='strafing_run_pattern')
assert(table.concat(gunship.round_assets(round),',')=='MG-206 Heavy Machine Gun,Eagle Strafing Run')
assert(gunship.arm(9501,{gun=gun,label='cas'},function()end))
tick(16)
assert(captured and captured.projectile==16 and captured.pattern=='strafing_run','the HE round in the Eagle pattern')
local bad=options.page({id='round_test',title='Round test'}):choice({id='bad',label='Bad',choices={'A','B'},
    values={'ap4','ap5'},default=1})
gun.round=bad
assert(select(2,gunship.check_gun(gun))=="gun.round: choice value ap5 is not 'standard', 'native', 'ap4', "
    .."'strafing_run' or 'strafing_run_pattern'")
return 'ok'
"""
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + PELICANS + "\nlocal PROOF_ADDON=''\nlocal PROOF_RESOURCE="
            + lua_literal('mods/test/gunship') + '\n' + 'return (function()\n' + HARNESS + GATLING + WEAPON + AI
            + HEADING + PROOF + GUNSHIP + body + '\nend)()\n'), b'ok')

    def test_another_machine_fires_the_he_round_without_the_pattern(self):
        self.assertEqual(run(WORLD + SLOT + PAYLOAD + PELICANS + 'return (function()\n' + GATLING + WEAPON + MIRROR
            + r"""
local world=client_copy()
local ROW16=projectile_row(16,1050,400,218);W.write(ROW16+0x90,W.u32(50))
local spec={}
for k,v in pairs(SPEC)do spec[k]=v end
spec.round='strafing_run_pattern'
local r,code,reason=in_update(function()return weapon.mirror_configure(world,8102,spec,'mirror')end)
assert(r and r.projectile==16,tostring(code)..' '..tostring(reason))
assert(n('MIRROR (mirror): the Strafing Run pattern is the host\'s own magazine: every round of this machine\'s copy is '
    ..'the HE round')==1,table.concat(logged,' | '))
return 'ok'
end)()
"""), b'ok')


class RegistrationTests(unittest.TestCase):
    def test_a_definition_with_a_mod_options_choice(self):
        out = run(REGISTRATION + r"""
local options=require('hd2runtime/api/options')
local page=options.page({id='pelican_cas_test',title='Pelican CAS test'})
local choice=page:choice({id='blast',label='Blast',choices={'Off','Pelican','66mm','Automaton','Illuminate'},
    values={'none','pelican_chin_autocannon','66mm_missile_mk2','automaton_explosion_27','illuminate_explosion_392'},
    default=1})
local d=custom.register(spec({pelican={hover=90,gun={behave_as='gatling_sentry',rate_multiplier=1,round='ap4',
    impact_explosion=choice}}}),'mods/test/one')
-- The choice stays the handle (read at each arm); the 66mm's loading package is an asset on every machine.
assert(d.pelican.gun.impact_explosion==choice)
local assets=table.concat(d.assets or{},',')
assert(assets:find('MLS-4X Commando',1,true),assets)
-- The registry hash follows the choice, deterministically (so two machines on different choices are incompatible).
local off=custom.registry_hash()
choice.selected=3
local missile=custom.registry_hash()
assert(missile~=off)
choice.selected=1
assert(custom.registry_hash()==off)
-- A fixed donor by key is stored by its name.
custom.reset_for_tests();images.reset_for_tests();texts.reset_for_tests()
require('hd2runtime/runtime/virtual_stratagems').reset_for_tests()
local fixed=custom.register(spec({pelican={hover=90,gun={impact_explosion='automaton_explosion_27'}}}),'mods/test/one')
assert(fixed.pelican.gun.impact_explosion=='Automaton explosion 27')
-- A round choice: each value's package is an asset; the hash follows it too.
custom.reset_for_tests();images.reset_for_tests();texts.reset_for_tests()
require('hd2runtime/runtime/virtual_stratagems').reset_for_tests()
local round=page:choice({id='round',label='Round',choices={'AP4','23mm','23mm pattern'},
    values={'ap4','strafing_run','strafing_run_pattern'},default=1})
local r=custom.register(spec({pelican={hover=90,gun={behave_as='gatling_sentry',round=round,impact_explosion=choice}}}),
    'mods/test/one')
local ra=table.concat(r.assets,',')
assert(ra:find('MG-206 Heavy Machine Gun',1,true)and ra:find('Eagle Strafing Run',1,true),ra)
local h1=custom.registry_hash()
round.selected=2
assert(custom.registry_hash()~=h1)
round.selected=1
assert(custom.registry_hash()==h1)
-- A spread choice: the hash follows it too.
custom.reset_for_tests();images.reset_for_tests();texts.reset_for_tests()
require('hd2runtime/runtime/virtual_stratagems').reset_for_tests()
local spread=page:choice({id='spread',label='Spread',choices={'Tight','Wide'},values={1,100},default=2})
custom.register(spec({pelican={hover=90,gun={spread=spread}}}),'mods/test/one')
local wide=custom.registry_hash()
spread.selected=1
assert(custom.registry_hash()~=wide)
spread.selected=2
assert(custom.registry_hash()==wide)
-- An aim height choice: the hash follows it too.
custom.reset_for_tests();images.reset_for_tests();texts.reset_for_tests()
require('hd2runtime/runtime/virtual_stratagems').reset_for_tests()
local aim=page:choice({id='aim',label='Aim',choices={'Game','Low'},values={0,0.4},default=2})
custom.register(spec({pelican={hover=90,gun={behave_as='gatling_sentry',aim_height=aim}}}),'mods/test/one')
local low=custom.registry_hash()
aim.selected=1
assert(custom.registry_hash()~=low)
-- Any other choice value is refused at registration.
local wrong=page:choice({id='wrong',label='Wrong',choices={'Gas','Off'},values={'orbital_gas_strike','none'},default=2})
custom.reset_for_tests()
refused({pelican={hover=90,gun={impact_explosion=wrong}}},'choice value orbital_gas_strike is neither')
return 'ok'
""")
        self.assertEqual(out, b'ok')


if __name__ == '__main__':
    unittest.main()
