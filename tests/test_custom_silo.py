"""The silo payload family and the MS-N223 Shredder Silo (2026-10-06; runtime/custom_silos.lua, api/actions.lua named
explosions, research/silo-payload-F5FEE03DCFDB.json, research/event-actions "Cyborg Production Unit"):
  * the research: the MS-11 Solo Silo's rack delivers the missile (its own explosive, detonation 135, one owner, not a
    projectile) and the laser remote; the Cyborg Production Unit's self-destruct is ExplosionType 293, an ability's code
    literal through the ability explosion wrapper, its effect and sound in two objective packages (by identity);
  * the generated tables: the silo by role, the named explosion with its sound package, the queue entry layout pinned;
  * hd2.explosions: the Cyborg Production Unit resolves with both packages and is resident only when both are;
  * the definition: registered as a silo (a blue support carrier, the Solo Silo's colours), its blasts' packages its
    assets, mirrored for several players (a client family, the silo remote handler), the registry hash covering the
    blast; the refusals (another donor, an unknown blast, the same fallback, a red carrier, an unknown field);
  * the detonation watch: the missile's own queued detonation (type and source) at once, else its removal after it left
    the silo, never a blast for a missile that never left it; another source or type is not this missile's;
  * the blast: every machine that watches the missile requests it from its own copy (the game's pattern for an
    explosive's own blast), with the detonation's own attribution; the fallback when the blast's packages are not
    resident; the mirrored request itself (api/actions.lua, internal);
  * the example: a valid custom_stratagems.json, its addon the compiled project, its fixture the project, its code free
    of every native code and of the other examples', the user's name, description and traits."""
import hashlib
import json
import sys
import unittest

from support import ROOT, run
from test_stratagem_calldown_code import WORLD

sys.path.insert(0, str(ROOT / 'sdk'))
from tools import custom_stratagem_project as P  # noqa: E402

FOLDER = ROOT / 'proof/ShredderSiloExample'
DESCRIPTION = ('A silo that fits one single, tactical nuclear missile. Possible side effects include shell shock, '
    'mutation, and/or death. A laser targetting remote is provided.')


class ResearchTests(unittest.TestCase):
    def test_the_solo_silo_pod_delivers_a_missile_and_a_remote(self):
        r = json.loads((ROOT / 'research/silo-payload-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
        self.assertEqual(r['writes'], 0)
        silo, = r['silos']
        self.assertEqual((silo['stratagem'], silo['rack']), ('MS-11 Solo Silo', '0xDE18775FA447A9BF'))
        roles = {i['role']: i for i in silo['items']}
        self.assertEqual((roles['missile']['slot'], roles['missile']['resource']), (0, '0xDDDB2910FF2B24E9'))
        self.assertEqual((roles['remote']['slot'], roles['remote']['resource']), (1, '0xFC13460592CA79AA'))
        e = roles['missile']['explosive']
        self.assertEqual((e['mode'], e['detonation'], e['impact'], e['owners']), (2, 135, 420, 1))
        self.assertEqual((roles['missile']['seekingMissile']['projectileHandled'],
            roles['missile']['seekingMissile']['projectileType']), (0, 0))

    def test_the_cyborg_production_unit_explosion_is_proven(self):
        r = json.loads((ROOT / 'research/event-actions-F5FEE03DCFDB.json').read_text(encoding='utf-8'))
        named = {n['name']: n for n in r['namedExplosions']}
        c = named['Cyborg Production Unit']
        self.assertEqual((c['type'], c['requestedBy'], c['behaviorId'], c['abilityId'], c['tick']),
            (293, 'ability', 327, 906, 1800))
        self.assertEqual(c['settings'], {'damageType': 497, 'inner': 50.0, 'outer': 100.0, 'shockwave': 100.0})
        a = c['assets']
        # The effect package: the smaller of the two that hold its particle effect; the sound: its bank's package.
        self.assertEqual(sorted(p['id'] for p in a['effectPackages']), ['0x9BFA7EB1324C29A5', '0x9C3D59D7095B4C6A'])
        self.assertEqual(a['effectPackage'], min(a['effectPackages'], key=lambda p: p['bytes'])['id'])
        self.assertEqual((a['soundBank'], a['soundPackage']), ('content/audio/obj_cy_city_blow_up_assembly_site',
            '0xCF1B36D0765B57A5'))
        asm = [p['asm'] for p in r['proofs']['cyborgProductionUnit']]
        for text in ('mov edx, 0x38a', 'cmp edx, 0x708', 'mov edx, 0x125', 'call 0x11ad240', 'mov r8d, r14d',
                'call 0x13c0a80'):
            self.assertIn(text, asm)
        det = [p['asm'] for p in r['proofs']['explosiveDetonation']]
        self.assertIn('mov r9d, dword ptr [r14 + 8]', det)        # source = the explosive's own entity
        self.assertIn('mov r8d, dword ptr [r15 + 0x24]', det)     # type = its record's detonation
        # Its settings row matches in every mission snapshot.
        for o in r['observations']:
            self.assertTrue(all(t['match'] for t in o['settingsTable']), o['snapshot'])

    def test_the_generated_tables(self):
        natives = (ROOT / 'domains/event_natives.lua').read_text(encoding='utf-8')
        for label in ('Cyborg Production Unit: requests ExplosionType 293', 'ability wrapper calls RequestExplosion',
                'explosion queue entry +0x0C: type', 'explosion queue entry +0x10: source',
                'an explosive detonation: source = the explosive entity'):
            self.assertIn(label, natives)
        self.assertIn('["soundPackage"]="0xCF1B36D0765B57A5"', natives)
        pods = (ROOT / 'domains/pod_payload_authoring.lua').read_text(encoding='utf-8')
        self.assertIn('["silos"]={["MS-11 Solo Silo"]={["id"]=1337271929,["missile"]={["detonation"]=135,["impact"]=420,'
            '["resource"]="0xDDDB2910FF2B24E9",["slot"]=0},["rack"]="0xDE18775FA447A9BF",["remote"]={["resource"]='
            '"0xFC13460592CA79AA",["slot"]=1}}}', pods)
        residency = (ROOT / 'domains/package_residency.lua').read_text(encoding='utf-8')
        self.assertIn('["explosion/Cyborg Production Unit"]={["label"]="Cyborg Production Unit",["package"]='
            '"0x9BFA7EB1324C29A5",["via"]="explosion_effect_package"}', residency)
        self.assertIn('["explosion/Cyborg Production Unit/sound"]={["label"]="Cyborg Production Unit (sound)",'
            '["package"]="0xCF1B36D0765B57A5",["via"]="explosion_sound_package"}', residency)


SILO = r'''
local function silo_spec(over)
    local s={id='shredder',name='MS-N223 SHREDDER SILO',name_cased='MS-N223 Shredder Silo',description='A silo.',
        icon='x',code={'down','up','right','up','down','down','right'},carrier={group='support'},
        silo={donor='MS-11 Solo Silo',blast='Cyborg Production Unit',fallback='Hellbomb'}}
    for k,v in pairs(over or{})do if v==false then s[k]=nil else s[k]=v end end
    return s
end
'''


class ExplosionTests(unittest.TestCase):
    def test_the_named_explosion_needs_both_its_packages(self):
        self.assertEqual(run(r'''
local actions=require('hd2runtime/api/actions')
local t=assert(actions.explosion_target('Cyborg Production Unit'))
assert(t.type==293 and#t.dependencies==2)
assert(t.dependencies[1].package=='0x9BFA7EB1324C29A5'and t.dependencies[2].package=='0xCF1B36D0765B57A5')
assert(t.dependencies[1].via=='explosion_effect_package'and t.dependencies[2].via=='explosion_sound_package')
local hb=assert(actions.explosion_target('Hellbomb'))
assert(hb.name=='NUX-223 Hellbomb'and#hb.dependencies==1)
-- Resident only when every package is (read through the asset state).
local state={}
local runtime={package_state=function(hex)return state[hex]or'absent'end}
assert(actions.explosion_resident(runtime,t)==false)
state['0x9BFA7EB1324C29A5']='resident'
assert(actions.explosion_resident(runtime,t)==false,'the sound package is missing')
state['0xCF1B36D0765B57A5']='resident'
assert(actions.explosion_resident(runtime,t)==true)
-- The list names it, an objective explosion.
local found
for _,e in ipairs(actions.explosions.reviewed())do if e.name=='Cyborg Production Unit'then found=e end end
assert(found and found.type==nil and found.source=='behavior'and found.assets_known==true and found.objective==true)
assert(found.catalogue=='entity/cyborg_production_unit/ability')
assert(#actions.explosions.reviewed()==16)
return 'ok'
'''), b'ok')


class RegistrationTests(unittest.TestCase):
    def test_the_silo_registers_with_its_assets_and_multiplayer(self):
        self.assertEqual(run(WORLD + SILO + r'''
local custom=require('hd2runtime/runtime/custom_stratagems');custom.reset_for_tests()
local mp=require('hd2runtime/runtime/multiplayer')
local log_module=require('hd2runtime/runtime/log')
local lines={}
log_module.emit=function(text)lines[#lines+1]=tostring(text)end
local d=custom.register(silo_spec({traits={'Support Weapon','Explosive','Anti-Tank','Expendable'},cooldown=180}),
    'mods/test/silo')
assert(d.kind=='silo'and d.group=='support')
-- An objective blast's packages (about 300 MB) may take the core loader's own 90 s at mission start.
assert(d.asset_timeout==custom.OBJECTIVE_ASSET_TIMEOUT and custom.OBJECTIVE_ASSET_TIMEOUT==90 and d.delivery.objective)
local s=d.delivery
assert(s.stratagem=='MS-11 Solo Silo'and s.missile=='DDDB2910FF2B24E9'and s.remote=='FC13460592CA79AA'
    and s.detonation==135 and s.blast=='Cyborg Production Unit'and s.fallback=='NUX-223 Hellbomb')
assert(s.item_types['DDDB2910FF2B24E9']and s.item_types['FC13460592CA79AA'])
-- Its blasts' packages are its assets (loaded at mission start): the effect, the sound, the Hellbomb's.
local keys={}
for _,dep in ipairs(d.pod_deps)do keys[#keys+1]=dep.key end
assert(table.concat(keys,'|')=='explosion/Cyborg Production Unit|explosion/Cyborg Production Unit/sound|'
    ..'explosion/NUX-223 Hellbomb',table.concat(keys,'|'))
-- The Solo Silo is never its carrier (its delivery), and it shows the Solo Silo's blue colours.
local excluded=false
for _,n in ipairs(d.exclude)do excluded=excluded or n=='MS-11 Solo Silo'end
assert(excluded and d.colours=='MS-11 Solo Silo')
-- Several players: a client runs its own call; every compatible Runtime watches the missile (the host blasts).
assert(mp.client_family(d)=='silo'and custom.mirrored(d)and custom.remote_handler(d).kind=='silo')
local reg
for _,l in ipairs(lines)do if l:find('REGISTERED shredder',1,true)then reg=l end end
assert(reg and reg:find('the vanilla MS-11 Solo Silo pod: its silo and laser remote',1,true)
    and reg:find('the session host requests the Cyborg Production Unit explosion',1,true),tostring(reg))
-- The panel: the user's traits, the stats.
local p=custom.panel_details('shredder')
assert(table.concat(p.traits,'|')=='CUSTOM STRATAGEM|SUPPORT WEAPON|EXPLOSIVE|ANTI-TANK|EXPENDABLE')
assert(p.stats[3][2]=='180 SEC'and p.stats[2][2]=='UNLIMITED')
assert(custom.KIND_TRAITS.silo=='MISSILE SILO'and custom.POD_KINDS.silo)
-- describe: the Solo Silo's own vanilla rack.
local de=custom.describe('shredder')
assert(de.kind=='silo'and de.pod.rack=='0xDE18775FA447A9BF'and de.pod.vanilla and de.pod.count==2)
return 'ok'
'''), b'ok')

    def test_the_registry_hash_covers_the_blast(self):
        self.assertEqual(run(WORLD + SILO + r'''
local custom=require('hd2runtime/runtime/custom_stratagems')
local function hash(over)
    custom.reset_for_tests()
    require('hd2runtime/runtime/virtual_stratagems').reset_for_tests()
    require('hd2runtime/runtime/text_resources').reset_for_tests()
    custom.register(silo_spec(over),'mods/test/silo')
    return custom.registry_hash()
end
local a=hash()
assert(a==hash(),'the same definition is the same hash')
assert(a~=hash({silo={donor='MS-11 Solo Silo',blast='Hellbomb'}}),'the blast')
assert(a~=hash({silo={donor='MS-11 Solo Silo',blast='Cyborg Production Unit'}}),'the fallback')
return 'ok'
'''), b'ok')

    def test_refusals(self):
        self.assertEqual(run(WORLD + SILO + r'''
local custom=require('hd2runtime/runtime/custom_stratagems');custom.reset_for_tests()
local function refused(over,text)
    local ok,why=pcall(custom.register,silo_spec(over),'mods/test/silo')
    assert(not ok and tostring(why):find(text,1,true),tostring(why))
end
refused({silo={donor='EAT-17 Expendable Anti-Tank',blast='Hellbomb'}},'silo.donor must be a reviewed missile silo: '
    ..'MS-11 Solo Silo')
refused({silo={donor='MS-11 Solo Silo'}},'silo.blast is required')
refused({silo={donor='MS-11 Solo Silo',blast='Nuke 9000'}},'silo.blast must be a catalogued explosion')
refused({silo={donor='MS-11 Solo Silo',blast=293}},'silo.blast must be a catalogued explosion')
refused({silo={donor='MS-11 Solo Silo',blast='Hellbomb',fallback='NUX-223 Hellbomb'}},'silo.fallback must be another')
refused({silo={donor='MS-11 Solo Silo',blast='Hellbomb',countdown=10}},'unsupported silo field: countdown')
refused({carrier={beacon='offensive',prefer_families={'orbital'}}},'a silo needs a support (blue beacon) carrier')
refused({carrier={group='orbital'}},'a silo needs a support (blue beacon) carrier')
refused({carrier={group='support_pod'}},'carrier.group support_pod cannot carry a silo payload')
refused({sentry={donor='A/MG-43 Machine Gun Sentry'}},'one payload family per custom stratagem')
return 'ok'
'''), b'ok')


# A simulated world for the watch and the blast: one missile entity, its positions, the explosion queue.
FAKE = r'''
local wm=require('hd2runtime/runtime/event_world')
local silos=require('hd2runtime/runtime/custom_silos')
local F={exists=true,pos={x=0,y=0,z=0},queue={},mission=true,host=true}
wm.open=function()return {runtime={package_state=function(hex)return F.resident and F.resident[hex]or'absent'end}}end
wm.game_state=function()return {mission=F.mission,host=F.host}end
wm.entity_exists=function(_,e)return e==7001 and F.exists end
wm.entity_unit=function(_,e)return e==7001 and F.exists and 99 or nil end
wm.unit_position=function(_,u)return u==99 and F.pos or nil end
wm.explosion_queue=function(_,n)return F.queue end
local function watch()
    local events={}
    local w=silos.watch({missile=7001,detonation=135,label='t'},function(e)events[#events+1]=e end)
    return w,events
end
local function kinds(events)local o={};for _,e in ipairs(events)do o[#o+1]=e.kind end;return table.concat(o,' ')end
'''


class WatchTests(unittest.TestCase):
    def test_its_own_queued_detonation(self):
        self.assertEqual(run(FAKE + r'''
local w,events=watch()
w.tick(0.1)
-- A queued 135 before it left the silo is not its detonation (it has not launched); nor another source's or type's.
F.queue={{x=1,y=1,z=1,type=135,source=7001}}
w.tick(0.1)
assert(kinds(events)=='',kinds(events))
F.pos={x=0,y=0,z=40}
F.queue={{x=5,y=5,z=5,type=135,source=6000},{x=6,y=6,z=6,type=158,source=7001}}
w.tick(0.1)
assert(kinds(events)=='launched',kinds(events))
F.pos={x=300,y=10,z=2}
F.queue={{x=1,y=2,z=3,type=50,source=1},{x=301.5,y=10.5,z=1.5,type=135,source=7001,owner=900,peer_lo=5,peer_hi=6}}
w.tick(0.1)
assert(kinds(events)=='launched detonated ended',kinds(events))
local e=events[2]
assert(e.via=='queue'and e.position.x==301.5 and e.position.y==10.5 and e.position.z==1.5)
assert(e.origin.source==7001 and e.origin.owner==900 and e.origin.peer_lo==5 and e.origin.peer_hi==6)
assert(w.status=='complete')
return 'ok'
'''), b'ok')

    def test_its_removal_after_the_launch(self):
        self.assertEqual(run(FAKE + r'''
local w,events=watch()
w.tick(0.1)
F.pos={x=0,y=0,z=60};w.tick(0.1)
F.pos={x=120,y=0,z=5};w.tick(0.1)
F.exists=false;w.tick(0.1)
assert(kinds(events)=='launched detonated ended',kinds(events))
assert(events[2].via=='removal'and events[2].position.x==120)
return 'ok'
'''), b'ok')

    def test_never_a_blast_for_a_missile_that_never_left_the_silo(self):
        self.assertEqual(run(FAKE + r'''
local w,events=watch()
w.tick(0.1)
F.pos={x=0,y=0,z=3};w.tick(0.1)     -- the silo deploying: a few metres
F.exists=false;w.tick(0.1)
assert(kinds(events)=='gone ended',kinds(events))
-- The mission's end ends a watch.
F.exists,F.pos=true,{x=0,y=0,z=0}
local w2,events2=watch()
w2.tick(0.1)
F.mission=false;w2.tick(0.1)
assert(kinds(events2)=='ended'and events2[1].reason=='the mission ended')
return 'ok'
'''), b'ok')


class BlastTests(unittest.TestCase):
    def test_every_watching_machine_requests_it_and_the_fallback(self):
        self.assertEqual(run(WORLD + SILO + FAKE + r'''
local custom=require('hd2runtime/runtime/custom_stratagems');custom.reset_for_tests()
local d=custom.register(silo_spec(),'mods/test/silo')
local actions=require('hd2runtime/api/actions')
local requested={}
actions.mirror_explosion=function(name,position,origin)
    requested[#requested+1]={name=name,x=position.x,origin=origin}
    return name
end
local origin={source=7001,owner=900,peer_lo=5,peer_hi=6}
-- Neither package set resident: none.
local a,why=silos.blast(d,{x=1,y=2,z=3},'t',origin)
assert(a==nil and why:find('ASSET_UNAVAILABLE',1,true)and why:find('nor the fallback NUX-223 Hellbomb',1,true),why)
-- Only the Hellbomb's: the fallback, with the detonation's own attribution.
F.resident={['0x681275AF9E93CB2C']='resident'}
local name
a,name=silos.blast(d,{x=1,y=2,z=3},'t',origin)
assert(a and a.status=='requested'and name=='NUX-223 Hellbomb'and requested[1].origin==origin and requested[1].x==1)
-- Both of the Cyborg Production Unit's: the blast itself; a client requests it too (each machine its own copy).
F.resident['0x9BFA7EB1324C29A5']='resident';F.resident['0xCF1B36D0765B57A5']='resident'
F.host=false
a,name=silos.blast(d,{x=4,y=5,z=6},'t',origin)
assert(a and name=='Cyborg Production Unit'and requested[2].name=='Cyborg Production Unit'and requested[2].x==4)
-- A refusal of the request is reported.
actions.mirror_explosion=function()return nil,'RATE_LIMITED','too many'end
a,why=silos.blast(d,{x=4,y=5,z=6},'t',origin)
assert(a==nil and why=='RATE_LIMITED: too many')
return 'ok'
'''), b'ok')

    def test_the_mirrored_request_on_this_machine(self):
        self.assertEqual(run(WORLD + r'''
local wm=require('hd2runtime/runtime/event_world')
local handles=require('hd2runtime/runtime/handles')
local actions=require('hd2runtime/api/actions')
local F={mission=true,host=false,exists={[7001]=true,[900]=true},resident={}}
wm.open=function()return {runtime={package_state=function(hex)return F.resident[hex]or'absent'end}}end
wm.game_state=function()return {mission=F.mission,host=F.host}end
wm.entity_exists=function(_,e)return F.exists[e]==true end
wm.local_peer=function()return 11,12 end
handles.local_avatar=function()return {id=555}end
local calls={}
wm.explode=function(_,spec)calls[#calls+1]=spec;if F.refuse then local r=F.refuse;F.refuse=nil;return nil,r end
    return true end
local origin={source=7001,owner=900,peer_lo=5,peer_hi=6}
-- Its packages not resident: refused, nothing requested.
local name,code=actions.mirror_explosion('Cyborg Production Unit',{x=1,y=2,z=3},origin)
assert(name==nil and code=='ASSET_UNAVAILABLE'and#calls==0)
F.resident['0x9BFA7EB1324C29A5']='resident';F.resident['0xCF1B36D0765B57A5']='resident'
-- On a client too, with the detonation's own source, owner and creditor.
name=actions.mirror_explosion('Cyborg Production Unit',{x=1,y=2,z=3},origin)
local c=calls[1]
assert(name=='Cyborg Production Unit'and c.type==293 and c.source==7001 and c.owner==900 and c.peer_lo==5
    and c.peer_hi==6 and c.x==1 and c.z==3)
-- The detonation's entities gone: the local avatar and peer.
F.exists[7001]=nil
name=actions.mirror_explosion('Cyborg Production Unit',{x=1,y=2,z=3},origin)
c=calls[2]
assert(name and c.source==555 and c.owner==555 and c.peer_lo==11 and c.peer_hi==12)
-- The game refusing the detonation's attribution: once more with the local avatar.
F.exists[7001]=true
F.refuse='the source entity no longer exists'
name=actions.mirror_explosion('Cyborg Production Unit',{x=1,y=2,z=3},origin)
assert(name and calls[3].source==7001 and calls[4].source==555)
-- Not in a mission: refused. A raw type: refused. Not exported to mods.
F.mission=false
name,code=actions.mirror_explosion('Cyborg Production Unit',{x=1,y=2,z=3},origin)
assert(name==nil and code=='NOT_IN_MISSION')
F.mission=true
name,code=actions.mirror_explosion(293,{x=1,y=2,z=3},origin)
assert(name==nil and code=='UNKNOWN_EXPLOSION')
local hd2=require('hd2runtime/api/hd2')
assert(hd2.explosions.mirror_explosion==nil and hd2.actions.mirror_explosion==nil)
return 'ok'
'''), b'ok')


CALL = r'''
local custom=require('hd2runtime/runtime/custom_stratagems');custom.reset_for_tests()
require('hd2runtime/runtime/spawned_instances').reset_for_tests()
local log_module=require('hd2runtime/runtime/log')
local logged={}
log_module.emit=function(t)logged[#logged+1]=tostring(t)end
local function count(text)local n=0;for _,l in ipairs(logged)do if l:find(text,1,true)then n=n+1 end end;return n end
local I=custom.internals_for_tests()
local silos=require('hd2runtime/runtime/custom_silos')
local d=custom.register(silo_spec(),'mods/test/silo')
local watched,wcb
silos.watch=function(spec,cb)watched=spec;wcb=cb;return {status='active',cancel=function()watched.cancelled=true end}end
local blasted
silos.blast=function(def,pos,label,origin)blasted={def=def,pos=pos,label=label,origin=origin}
    return {status='requested'},'Cyborg Production Unit'end
'''


class CaptureTests(unittest.TestCase):
    def test_the_call_captures_its_missile_and_blasts_at_its_detonation(self):
        self.assertEqual(run(WORLD + SILO + CALL + r'''
local pods=require('hd2runtime/runtime/support_pods')
local mp_items=require('hd2runtime/runtime/custom_mp_items')
local G=require('hd2runtime/domains/stratagem_authoring').stratagems['MS-11 Solo Silo'].root
settings=W.stratagem_settings({{type=89,id=G.id,package=G.package,payloads=G.payloads,sequence={3,1,2,3,3},
    group=G.group,row=G.row,cooldown=180}})
local pod_spec
pods.capture=function(spec,cb)
    pod_spec=spec
    cb({kind='pod',pod=510})
    cb({kind='captured',pod=510,rack=6100,items={6101,6102},types={'DDDB2910FF2B24E9','FC13460592CA79AA'},
        slots={0,1},networks={301,302}})
    return {status='complete'}
end
local published
mp_items.own=function(spec)published=spec;return true end
I.mission().mp={state='running'}
local ctx=I.new_call(d,{carrier='M-105 Stalwart',stable_id=3,type=60},0)
ctx.beacon={entity=7010,network=810}
I.start_capture(ctx,d)
-- The Solo Silo's own pod (its type), its rack's two items by type; read-only.
assert(pod_spec and pod_spec.type==89 and pod_spec.item_types['DDDB2910FF2B24E9']
    and pod_spec.item_types['FC13460592CA79AA']and not pod_spec.content_type,table.concat(logged,' | '))
assert(ctx.missile==6101 and ctx.state=='delivered')
assert(custom.instance_of(6101).role=='missile'and custom.instance_of(6102).role=='remote'
    and custom.instance_of(6100).role=='silo')
assert(count('shredder#1: DELIVERED: pod 510, silo 6100: missile 6101, remote 6102 (exactly this pod\'s; every other '
    ..'MS-11 Solo Silo stays vanilla)')==1,table.concat(logged,' | '))
-- Several players: the missile's network id published (the host watches its own copy).
assert(published and published.id=='shredder'and published.items[1]==301 and published.entities[1]==6101
    and published.roles[1]=='payload'and published.beacon==810)
assert(count('CUSTOM MP ITEMS: missile network id 301 (call beacon network id 810) published to every compatible '
    ..'Runtime: every machine requests its blast from its own copy')==1)
-- The watch of exactly that missile; the blast where it detonates.
assert(watched.missile==6101 and watched.detonation==135)
wcb({kind='launched',position={x=0,y=0,z=40}})
assert(blasted==nil)
local origin={source=6101,owner=900,peer_lo=5,peer_hi=6}
wcb({kind='detonated',position={x=300,y=10,z=2},via='queue',seconds=12,origin=origin})
assert(blasted and blasted.def==d and blasted.pos.x==300 and blasted.label=='shredder#1'and blasted.origin==origin)
assert(count('missile 6101 DETONATED at (300.0, 10.0, 2.0) (its own detonation in the explosion queue, 12.0 s after its '
    ..'capture): Cyborg Production Unit explosion requested there on this machine (requested)')==1,
    table.concat(logged,' | '))
return 'ok'
'''), b'ok')

    def test_the_remote_handler_watches_another_players_missile(self):
        self.assertEqual(run(WORLD + SILO + CALL + r'''
local h=custom.remote_handler(d)
assert(h.kind=='silo'and h.title=='REMOTE CUSTOM SILO'and h.noun(1)=='missile')
local world=require('hd2runtime/runtime/event_world').open()
local info,why=h.check(world,d,4242,'37CDE43876BA26BB')
assert(info==nil and why:find('not the MS-11 Solo Silo\'s missile',1,true),tostring(why))
local b=h.bind({entity=6201,network=401,caller='peer-b',id='shredder',definition=d})
assert(b.status=='active'and b.kind=='silo'and watched.missile==6201 and watched.detonation==135)
wcb({kind='detonated',position={x=1,y=2,z=3},via='removal',seconds=4})
assert(blasted and blasted.def==d and blasted.label=='remote peer-b shredder missile 401')
assert(count('REMOTE CUSTOM SILO: peer peer-b\'s custom shredder missile network id 401 (entity 6201 here): DETONATED '
    ..'at (1.0, 2.0, 3.0) (inferred: the missile is gone): Cyborg Production Unit explosion requested there on this '
    ..'machine')==1,
    table.concat(logged,' | '))
b.cancel()
assert(watched.cancelled)
return 'ok'
'''), b'ok')


class ProjectTests(unittest.TestCase):
    def test_the_example_is_its_compiled_project(self):
        schema = P.load_schema()
        raw = (FOLDER / 'custom_stratagems.json').read_bytes()
        proj = json.loads(raw)
        self.assertEqual(P.validate(proj, schema), [])
        self.assertEqual((FOLDER / 'src/addon.lua').read_text(encoding='utf-8'),
            P.compile_lua(proj, hashlib.sha256(raw).hexdigest()), 'rebuild it (hd2.py build)')
        self.assertEqual(json.loads((ROOT / 'sdk/fixtures/custom_stratagems/ShredderSiloExample.json').read_text(
            encoding='utf-8')), proj)
        s, = proj['stratagems']
        self.assertEqual((s['name_cased'], s['description'], s['code'], s['cooldown']), ('MS-N223 Shredder Silo',
            DESCRIPTION, ['down', 'up', 'right', 'up', 'down', 'down', 'right'], 180))
        self.assertEqual(s['traits'], ['Support Weapon', 'Explosive', 'Anti-Tank', 'Expendable'])
        self.assertEqual(s['payload'], {'family': 'silo', 'donor': 'MS-11 Solo Silo', 'blast': 'Cyborg Production Unit',
            'fallback': 'NUX-223 Hellbomb'})
        self.assertIn("silo={donor='MS-11 Solo Silo',blast='Cyborg Production Unit',fallback='NUX-223 Hellbomb'},",
            (FOLDER / 'src/addon.lua').read_text(encoding='utf-8'))

    def test_its_code_is_free(self):
        from test_new_stratagem_examples import ARROWS, SPEC
        schema = P.load_schema()
        code = ['down', 'up', 'right', 'up', 'down', 'down', 'right']
        for native in schema['catalogs']['nativeCodes']:
            self.assertIsNone(P._relation(code, native['code']), native.get('name') or native['stableId'])
        for name, spec in SPEC.items():
            self.assertIsNone(P._relation(code, [ARROWS[c] for c in spec[2]]), name)
        # The code the user first asked for starts with the A/G-16 Gatling Sentry's whole code: refused in a mission.
        bad = json.loads((FOLDER / 'custom_stratagems.json').read_text(encoding='utf-8'))
        bad['stratagems'][0]['code'] = ['down', 'up', 'right', 'left', 'down', 'down', 'right']
        self.assertTrue(any('A/G-16 Gatling Sentry' in p and 'starts with' in p for p in P.validate(bad, schema)),
            P.validate(bad, schema))

    def test_builder_refusals(self):
        schema = P.load_schema()
        base = json.loads((FOLDER / 'custom_stratagems.json').read_text(encoding='utf-8'))

        def problems(payload):
            p = json.loads(json.dumps(base))
            p['stratagems'][0]['payload'] = payload
            return P.validate(p, schema)
        self.assertTrue(any('must be a reviewed missile silo' in p for p in problems(
            {'family': 'silo', 'donor': 'MS-11 Solo Silo X', 'blast': 'Cyborg Production Unit'})))
        self.assertTrue(any('.blast' in p and 'catalogued explosion' in p for p in problems(
            {'family': 'silo', 'donor': 'MS-11 Solo Silo', 'blast': 'Hellbomb'})), 'aliases are the Runtime\'s only')
        self.assertTrue(any('.blast' in p and 'required' in p for p in problems(
            {'family': 'silo', 'donor': 'MS-11 Solo Silo'})))
        self.assertTrue(any('another explosion' in p for p in problems({'family': 'silo', 'donor': 'MS-11 Solo Silo',
            'blast': 'NUX-223 Hellbomb', 'fallback': 'NUX-223 Hellbomb'})))
        self.assertTrue(any('countdown' in p for p in problems({'family': 'silo', 'donor': 'MS-11 Solo Silo',
            'blast': 'NUX-223 Hellbomb', 'countdown': 10})))
        red = json.loads(json.dumps(base))
        red['stratagems'][0]['carrier'] = {'beacon': 'offensive'}
        self.assertTrue(any('needs a support beacon' in p for p in P.validate(red, schema)), P.validate(red, schema))


if __name__ == '__main__':
    unittest.main()
