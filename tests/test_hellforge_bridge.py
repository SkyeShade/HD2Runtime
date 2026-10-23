import unittest
from support import run

# A fake HellForge Lua bridge (runtime/hellforge.lua's backend functions, in Lua): records every call.
FAKE = r'''
local hf=require('hd2runtime/runtime/hellforge')
calls,logs={},{}
local fake={queue={}}
local mods={}
function fake.info()return {bridge=1,sdk=9,ready=15,build='25480438',logs=''}end
function fake.mod(name)mods[name]=mods[name]or{name='lua.'..name};return mods[name]end
function fake.set(m,c,t,o,k,n,u,f)
 calls[#calls+1]={op='set',mod=m.name,component=c,target=t,offset=o,kind=k,number=n,u64=u,flags=f}
 if fake.refuse and fake.refuse(c,o)then return 0 end
 return 2
end
function fake.clear(m,c,t,o,k)calls[#calls+1]={op='clear',mod=m.name,component=c,target=t,offset=o,kind=k};return 2 end
function fake.set_stat(m,s,c,r,rec,o,k,n)
 calls[#calls+1]={op='set_stat',mod=m.name,stat=s,component=c,resource=r,record=rec,offset=o,kind=k,number=n};return 3
end
function fake.clear_stat(m,s,c,r,rec,o,k)
 calls[#calls+1]={op='clear_stat',mod=m.name,stat=s,component=c,resource=r,record=rec,offset=o,kind=k};return 3
end
function fake.copy_row(m,t,row,from,o,size)
 calls[#calls+1]={op='copy_row',mod=m.name,table=t,row=row,from=from,offset=o,size=size};return 1
end
function fake.owner(c,r)if fake.unloaded then return nil,0 end;return 0x77,fake.owners or 1 end
function fake.last()return 'refused for the test'end
function fake.listen()return true end
function fake.poll()local l=fake.queue;fake.queue={};return l,0 end
function fake.rewrites(rva,size)return rva==0x13A9715 end
function fake.stratagem_type(stable)if fake.stratagems_unloaded then return 0 end;return stable==1685231450 and 82 or stable==3753216434 and 15 or 50 end
function fake.load_package()return 2 end
function fake.set_passives(m,a,s)calls[#calls+1]={op='passives',armor=a,second=s};return true end
hf.set_backend(fake)
FAKE=fake
local function emit(line)logs[#logs+1]=line end
function finish(w)for _=1,200 do w.tick(0.1);if w.status=='complete'or w.status=='rejected'then break end end;return w end
function start(kind,spec)return finish(require('hd2runtime/api/'..kind).start_spec(nil,emit,spec,0))end
'''


def check(body):
    return run(FAKE + body + "\nreturn 'ok'")


class HellForgeBridgeTests(unittest.TestCase):
    def test_inactive_outside_hellforge(self):
        run('''
local hf=require('hd2runtime/runtime/hellforge')
assert(hf.active()==false and hf.reason,'no HellForge DLL in the test process')
local hd2=require('hd2runtime/api/hd2')
assert(hd2.hellforge.active==false)
return 'ok'
''')

    def test_weapon_field_becomes_a_hellforge_live_edit(self):
        check(r'''
local hd2=require('hd2runtime/api/hd2')
assert(hd2.hellforge.active and hd2.hellforge.bridge==1)
local spec=require('hd2runtime/domains/patches').validate({id='erg',target=hd2.weapon('P-19 Redeemer'),
 field=hd2.fields.weapon.ergonomics,expect=95,value=50})
spec.mod='mods/test/fast'
local w=start('patch',spec)
assert(w.status=='complete'and w.result.status=='APPLIED'and w.result.backend=='hellforge',w.error)
local c=calls[1]
assert(#calls==1 and c.op=='set'and c.mod=='lua.mods/test/fast'and c.component=='WeaponDataComponentData'
 and c.offset==356 and c.kind==5 and c.number==50 and c.target==0x77 and c.flags==0,c.component)
assert(table.concat(logs,'\n'):find('through HellForge',1,true))
-- back to the reviewed value: the mod's edit is removed (HellForge puts back what is under it)
calls={}
spec=require('hd2runtime/domains/patches').validate({id='erg',target=hd2.weapon('P-19 Redeemer'),
 field=hd2.fields.weapon.ergonomics,expect=95,value=95})
spec.mod='mods/test/fast'
w=start('patch',spec)
assert(w.status=='complete'and w.result.status=='ALREADY_DESIRED'and calls[1].op=='clear',w.error)
''')

    def test_an_ensure_applies_once_and_is_held_by_hellforge(self):
        # HellForge keeps a Lua mod's live edits for the session: an ensure is not applied again every interval (a full
        # pass of ~500 ensures at once froze the game for half a second every few minutes, HellForge bug-report-0043).
        check(r'''
local hd2=require('hd2runtime/api/hd2')
local w=require('hd2runtime/api/ensure').start(nil,function(line)logs[#logs+1]=line end,{interval=1,startup_delay=0,
 patch={id='erg',target=hd2.weapon('P-19 Redeemer'),field=hd2.fields.weapon.ergonomics,expect=95,value=50}})
for _=1,600 do w.tick(0.1)end
local sets=0
for _,c in ipairs(calls)do if c.op=='set'then sets=sets+1 end end
local text=table.concat(logs,' | ')
assert(sets==1,'set '..sets..' times: '..text)
assert(text:find('steady=held by HellForge',1,true),text)
assert(w.verifications>0 and w.current_interval>1,'it backs off: '..tostring(w.current_interval))
-- held while the bridge is there to hold it
assert(require('hd2runtime/core/steady_state').verify(nil,{backend='hellforge'})==true)
''')

    def test_a_published_mod_plan_with_a_slot_list(self):
        # Railgun - RePenetrated 0.3.0 (a ModBuilder export): the projectile's damage row and the armory's penetration
        # label, a five-slot trait list the bridge sends slot by slot.
        check(r'''
local hd2=require('hd2runtime/api/hd2')
local w=finish(require('hd2runtime/api/plan').start(nil,function(line)logs[#logs+1]=line end,{
 id='support-plan',operations={
  {id='a',target=hd2.support_weapon('RS-422 Railgun'):attack('primary'):projectile(),allow_shared=true,changes={
   {field=hd2.fields.damage.ap_direct,expect=5,value=9},{field=hd2.fields.damage.ap_extreme,expect=5,value=9},
   {field=hd2.fields.damage.ap_large,expect=5,value=9},{field=hd2.fields.damage.ap_slight,expect=5,value=9}}},
  {id='b',target=hd2.support_weapon('RS-422 Railgun'),allow_unverified_effect=true,
   field=hd2.fields.presentation.armor_penetration,expect='light_anti_tank',value='anti_tank'}}}))
assert(w.status=='complete',w.error)
local damage,slots=0,0
for _,c in ipairs(calls)do
 -- the railgun's damage by its id (64), not its position in the table (69: another attack's damage)
 if c.op=='set'and c.component=='DamageInfo'and c.number==9 then assert(c.target==64,'DamageInfo '..tostring(c.target));damage=damage+1 end
 if c.op=='set'and c.kind==3 and c.component~='DamageInfo'then slots=slots+1 end
end
assert(damage==4 and slots>=1,'damage '..damage..', slots '..slots..': '..table.concat(logs,' | '))
''')

    def test_set_stat_and_row_copy_routes(self):
        # Entity deltas (an attachment's stats, a mission's timer), a status multiplier and the Urchin's pulse row copy:
        # HellForge's set_stat and copy_row, named as its stats schema and references.json name them.
        check(r'''
local b=require('hd2runtime/core/bytes')
local hd2=require('hd2runtime/api/hd2')
local W=require('hd2runtime/runtime/hellforge_writes')
local function patch(r)return finish(require('hd2runtime/api/patch').start(nil,function(line)logs[#logs+1]=line end,r))end
-- a magazine attachment's capacity: EntityDelta "<component>:<member>", the delta's resource and settings index
local id='weapon-attachment/v1/magazine/whisper-rifle-5-5x50mm-standard/16af29c8d0590809'
local field=require('hd2runtime/domains/attachment_authoring').attachments[id].fields['attachment.magazine_capacity']
calls={}
local w=start('patch',{id='a',mod='m',kind='attachment',attachment=id,target_path='magazine',changes={{field='attachment.magazine_capacity',
 descriptor=field,desired=b.encode(40,'u32'),expected=b.encode(30,'u32'),value=40,expect=30}}})
assert(w.status=='complete',w.error)
local c=calls[1]
assert(c.op=='set_stat'and c.stat=='EntityDelta'and c.component=='5:136'and c.record==156 and c.offset==171124 and c.number==40
 and c.resource==W.resource('0xFD5B6104526745D2'),tostring(c.component)..' '..tostring(c.record)..' '..tostring(c.offset))
-- back to its reviewed value: the mod's value taken away
calls={}
w=start('patch',{id='a2',mod='m',kind='attachment',attachment=id,target_path='magazine',changes={{field='attachment.magazine_capacity',
 descriptor=field,desired=b.encode(30,'u32'),expected=b.encode(30,'u32'),value=30,expect=30}}})
assert(w.status=='complete'and calls[1].op=='clear_stat'and calls[1].component=='5:136',w.error)
-- a mission's timer: a director's HiveMindComponentData record, or an entity delta
calls={}
w=patch({id='blitz',target=hd2.mission('automatons/a41d64ac'),field=hd2.fields.mission.duration_seconds,expect=720,value=1200,
 allow_shared=true,allow_unverified_effect=true})
assert(w.status=='complete'and calls[1].op=='set'and calls[1].component=='HiveMindComponentData'and calls[1].offset==116
 and calls[1].target==W.resource('0x33296F9C47993942')and calls[1].number==1200,tostring(w.error)..' | '..table.concat(logs,' | '))
local D=require('hd2runtime/domains/missions')
local delta_mission=D.sources['delta/7407a1dc9fa3fb41'].missions[1]
calls={}
w=patch({id='tcs',target=hd2.mission(delta_mission),field=hd2.fields.mission.duration_seconds,expect=720,value=900,
 allow_shared=true,allow_unverified_effect=true})
assert(w.status=='complete'and calls[1].op=='set_stat'and calls[1].stat=='EntityDelta'and calls[1].component=='212:116'
 and calls[1].record==3 and calls[1].offset==110176,tostring(w.error)..' | '..table.concat(logs,' | '))
-- a booster status's multiplier: StatusMultiplier, the stat it names, the status row's id, the element's value
calls={}
w=patch({id='infusion',target=hd2.booster('Experimental Infusion'):status_effect(),allow_shared=true,allow_unverified_effect=true,
 field=hd2.fields.status.incoming_damage_scale,expect=0.9,value=0.8})
assert(w.status=='complete'and calls[1].op=='set_stat'and calls[1].stat=='StatusMultiplier'and calls[1].component=='2'
 and calls[1].record==29 and calls[1].offset==4,tostring(w.error)..' | '..table.concat(logs,' | '))
-- the Urchin's pulse: copy_row from the donor's row (HellForge copies the final discharge's with it), and back
local urchin=hd2.throwable('G-109 Urchin'):pulse()
calls={}
w=patch({id='sticky',target=urchin,field=hd2.fields.throwable.pulse_explosion,expect=hd2.explosion('throwable/g109_urchin/detonation'),
 value=hd2.explosion('support_weapon/plas45_epoch/impact'),allow_shared=true,allow_unverified_effect=true,allow_unverified_reference=true})
assert(w.status=='complete',tostring(w.error)..' | '..table.concat(logs,' | '))
local copies={}
for _,x in ipairs(calls)do if x.op=='copy_row'then copies[#copies+1]=x end end
assert(#copies==1 and copies[1].table=='ExplosionSettings'and copies[1].row==369 and copies[1].from==227 and copies[1].offset==4
 and copies[1].size==148,table.concat(logs,' | '))
calls={}
w=patch({id='sticky2',target=urchin,field=hd2.fields.throwable.pulse_explosion,expect=hd2.explosion('throwable/g109_urchin/detonation'),
 value=hd2.explosion('throwable/g109_urchin/detonation'),allow_shared=true,allow_unverified_effect=true,allow_unverified_reference=true})
assert(w.status=='complete'and calls[#calls].op=='copy_row'and calls[#calls].from==0,tostring(w.error))
''')

    def test_a_hellforge_session_without_a_usable_bridge_refuses(self):
        # An older HellForge (no bridge, or an older one): the Runtime must not write the game itself there.
        check(r'''
local hd2=require('hd2runtime/api/hd2')
local real=os.getenv
os.getenv=function(name)if name=='HELLFORGE_MODLOADER'then return 'C:\\HellForge\\hellforge_modloader.dll'end;return real(name)end
hf.set_backend(nil)
assert(not hf.active()and hf.session()and hf.reason~=nil)
local w=finish(require('hd2runtime/api/patch').start(nil,function(line)logs[#logs+1]=line end,{id='old',
 target=hd2.support_weapon('RS-422 Railgun'):attack('primary'):projectile(),allow_shared=true,
 field=hd2.fields.damage.ap_direct,expect=5,value=9}))
assert(w.status=='rejected'and w.error:find('HELLFORGE_UNAVAILABLE',1,true)and w.error:find('bridge cannot be used',1,true),
 tostring(w.status)..' '..tostring(w.error))
os.getenv=real
hf.set_backend(FAKE)
''')

    def test_armor_perks(self):
        # Every catalogued perk value: HellForge's PassiveModifier / PassiveStat rows, id passive * 16 + index, the
        # offset within the entry.
        check(r'''
local hd2=require('hd2runtime/api/hd2')
local D=require('hd2runtime/domains/armor_perks')
local n=0
for _,e in ipairs(D.entries)do
 for _,f in ipairs(e.fields)do
  local value=f.max~=f.currentDefault and f.max or f.min
  calls={}
  local w=finish(require('hd2runtime/api/patch').start(nil,function(line)logs[#logs+1]=line end,{id='perk',
   target=hd2.passives.perk(e.id),field=f.semanticFieldId,expect=f.currentDefault,value=value,allow_shared=true,
   allow_unverified_effect=true}))
  local c,k=calls[1],f.backing
  local stride=k.part=='modifier'and 16 or 12
  assert(w.status=='complete'and c.op=='set'and c.component==(stride==16 and'PassiveModifier'or'PassiveStat')
   and c.target==k.passive*16+k.index and c.offset==k.offset-k.index*stride
   and(stride==16 and c.offset==8 or stride==12 and(c.offset==4 or c.offset==8)),
   tostring(e.id)..' '..f.semanticFieldId..': '..tostring(w.error))
  n=n+1
 end
end
assert(n>=70,'perk fields '..n)
''')

    def test_calldown_codes(self):
        # docs/stratagem-calldown-code.md: a code (with the cooldown in one transaction) through HellForge's set_code, by
        # the stratagem's stable id; its own code back takes the change away.
        check(r'''
local hd2=require('hd2runtime/api/hd2')
local function run(kind,r)return finish(require('hd2runtime/api/'..kind).start(nil,function(line)logs[#logs+1]=line end,r))end
function FAKE.set_code(m,stable,values)calls[#calls+1]={op='set_code',mod=m.name,stable=stable,values=values};return 1 end
calls={}
local w=run('transaction',{id='precision',target=hd2.stratagem('Orbital Precision Strike'),changes={
 {field=hd2.fields.stratagem.definition_cooldown,expect=80,value=60},
 {field=hd2.fields.stratagem.calldown_code,expect={'right','right','up'},value={'right','up','right','up'}}}})
assert(w.status=='complete',tostring(w.error)..' | '..table.concat(logs,' | '))
local code
for _,c in ipairs(calls)do if c.op=='set_code'then code=c end end
assert(code and code.values and table.concat(code.values,',')=='2,1,2,1'and code.stable==
 require('hd2runtime/domains/stratagem_authoring').stratagems['Orbital Precision Strike'].root.id,table.concat(logs,' | '))
calls={}
w=run('patch',{id='back',target=hd2.stratagem('Orbital Precision Strike'),field=hd2.fields.stratagem.calldown_code,
 expect={'right','right','up'},value={'right','right','up'}})
assert(w.status=='complete'and calls[1].op=='set_code'and calls[1].values==nil,tostring(w.error))
''')

    def test_booster_plans_through_the_public_api(self):
        # examples/projects/IncendiaryHellpods and BoosterTuning: the booster's explosion and its DamageInfo by their
        # ids, the booster's own row, the stratagem it grants.
        check(r'''
local hd2=require('hd2runtime/api/hd2')
local firebomb=hd2.booster('Firebomb Hellpods'):explosion()
local w=finish(require('hd2runtime/api/plan').start(nil,function(line)logs[#logs+1]=line end,{id='incendiary',operations={
 {id='radius',target=firebomb,allow_shared=true,allow_unverified_effect=true,changes={
  {field=hd2.fields.explosion.inner_radius,expect=2,value=3},{field=hd2.fields.explosion.outer_radius,expect=4,value=6}}},
 {id='damage',target=firebomb,allow_shared=true,allow_unverified_effect=true,changes={
  {field=hd2.fields.explosion.damage_standard_damage,expect=200,value=300},{field=hd2.fields.status.strength,expect=20,value=40}}},
 {id='eat-uses',target=hd2.booster('Surplus EAT Allocation'):granted_stratagem(),allow_unverified_effect=true,
  field=hd2.fields.stratagem.max_uses,expect=2,value=4},
 {id='vitality',target=hd2.booster('Vitality Enhancement'):tuning(),allow_unverified_effect=true,
  field=hd2.fields.booster.damage_taken_scale,expect=0.9,value=0.75}}}))
assert(w.status=='complete',tostring(w.status)..' '..tostring(w.error)..' '..tostring(w.waiting)..' | '..table.concat(logs,' | '))
local seen={}
for _,c in ipairs(calls)do if c.op=='set'then seen[c.component..' '..tostring(c.target)]=(seen[c.component..' '..tostring(c.target)]or 0)+1 end end
assert(seen['ExplosionSettings 83']==2 and seen['DamageInfo 427']==2 and seen['StratagemDefinition 15']==1
 and seen['BoosterSettings '..tostring(require('hd2runtime/domains/booster_authoring').boosters['Vitality Enhancement'].targets.tuning.value)]==1,
 table.concat(logs,' | '))
''')

    def test_shared_records_waits_refusals_and_unsupported(self):
        check(r'''
local b=require('hd2runtime/core/bytes')
local function change(backing,value,expect)
 local encode=function(v)return backing.storage=='bytes'and string.rep('x',12)or b.encode(v,backing.storage)end
 return {field='f',descriptor={backing=backing},desired=encode(value),expected=encode(expect or 1),value=value,
  expect=expect or 1}
end
local comp={kind='component',component='WeaponMagazineComponentData',recordIndex=4,offset=136,width=4,storage='u32',
 ownerCount=1,uniqueOwner=true}
-- a record other entities share goes with HF_LIVE_SHARED
FAKE.owners=2
local w=start('patch',{id='a',mod='m',changes={change(comp,60)}})
assert(w.status=='complete'and calls[1].flags==1 and calls[1].kind==3 and calls[1].number==60,w.error)
FAKE.owners=1
-- before the entity data loads it waits, then applies
FAKE.unloaded=true;calls={}
w=require('hd2runtime/api/patch').start_spec(nil,function()end,{id='b',mod='m',changes={change(comp,61)}},0)
for _=1,5 do w.tick(0.1)end
assert(w.status=='waiting'and #calls==0)
FAKE.unloaded=false
finish(w)
assert(w.status=='complete'and #calls==1,w.error)
-- a settings row by its id
calls={}
local row={kind='settings',settings='projectile',recordType=148,offset=32,width=4,storage='f32'}
w=start('patch',{id='c',mod='m',changes={change(row,1200,385)}})
assert(w.status=='complete'and calls[1].component=='ProjectileSettings'and calls[1].target==148 and calls[1].number==1200,w.error)
-- a transaction is undone when one of its changes is refused
calls={}
FAKE.refuse=function(c,o)return o==140 end
local second={kind='component',component='WeaponMagazineComponentData',recordIndex=4,offset=140,width=4,storage='u32'}
w=start('transaction',{id='d',mod='m',changes={change(comp,62),change(second,9)}})
assert(w.status=='rejected'and w.result.code=='HELLFORGE_REFUSED'and w.error:find('refused for the test',1,true),w.error)
assert(#calls==3 and calls[3].op=='clear'and calls[3].offset==136)
FAKE.refuse=nil
-- fields HellForge cannot take yet
for _,backing in ipairs({{kind='entity_delta',offset=4,width=4,storage='f32'},
  {kind='settings',settings='booster',recordType=3,offset=8,width=4,storage='f32'},
  {kind='component',component='X',recordIndex=1,offset=0,width=12,storage='bytes'}})do
 calls={}
 w=start('patch',{id='e',mod='m',changes={change(backing,1)}})
 assert(w.status=='rejected'and w.result.code=='HELLFORGE_UNSUPPORTED'and #calls==0,tostring(w.error))
end
-- enemies wait until HellForge maps them
w=start('patch',{id='f',mod='m',kind='enemy',changes={change(comp,1)}})
assert(w.status=='rejected'and w.result.code=='HELLFORGE_UNAVAILABLE',w.error)
-- a settings row by its id (nativeIdentity), never its position in the table (row)
calls={}
w=start('patch',{id='n',mod='m',changes={change({kind='ProjectileSettings',nativeIdentity=130,row=9,offset=32,width=4,storage='f32'},900,385)}})
assert(w.status=='complete'and calls[1].component=='ProjectileSettings'and calls[1].target==130,w.error)
-- a stratagem's definition by its stable id (as its type), waiting until the stratagems load; a booster's row
calls={}
FAKE.stratagems_unloaded=true
w=require('hd2runtime/api/patch').start_spec(nil,function()end,{id='s',mod='m',changes={change({kind='StratagemDefinition',
 nativeIdentity=1685231450,offset=104,width=4,storage='f32'},60,90)}},0)
for _=1,3 do w.tick(0.1)end
assert(w.status=='waiting'and #calls==0)
FAKE.stratagems_unloaded=nil
finish(w)
assert(w.status=='complete'and calls[1].component=='StratagemDefinition'and calls[1].target==82 and calls[1].offset==104,w.error)
calls={}
w=start('patch',{id='b',mod='m',changes={change({kind='booster_table',row=14,offset=8,width=4,storage='f32'},0.5,1)}})
assert(w.status=='complete'and calls[1].component=='BoosterSettings'and calls[1].target==14,w.error)
-- a stratagem's icon (an 8-byte image hash) as one u64; a mod's own icon image is refused until HellForge loads it
local icon={field='i',descriptor={backing={kind='StratagemDefinition',nativeIdentity=1685231450,offset=176,width=8,storage='presentation'}},
 desired='12345678',expected='abcdefgh',value='Orbital Laser',expect='Eagle Smoke Strike'}
calls={}
w=start('patch',{id='p2',mod='m',changes={icon}})
assert(w.status=='complete'and calls[1].kind==6 and calls[1].offset==176,w.error)
icon.image={id='x'}
w=start('patch',{id='p3',mod='m',changes={icon}})
assert(w.status=='rejected'and w.error:find('icon image',1,true),w.error)
-- a component named by its kind
calls={}
w=start('patch',{id='o',mod='m',changes={change({kind='OrbitalAbilityComponentData',recordIndex=1,offset=472,width=4,storage='f32'},5,3)}})
assert(w.status=='complete'and calls[1].component=='OrbitalAbilityComponentData',w.error)
-- rows a field leaves to its target, by the target's ids: a booster's explosion and its DamageInfo (never the rows'
-- positions), the stratagem it grants; a stratagem's payload entity
calls={}
w=start('patch',{id='be',mod='m',booster='Stun Pods',target_path='explosion',changes={
 change({kind='explosion',offset=24,width=4,storage='f32'},9,6),change({kind='explosion_damage',offset=12,width=4,storage='u32'},5,3)}})
assert(w.status=='complete'and calls[1].component=='ExplosionSettings'and calls[1].target==335
 and calls[2].component=='DamageInfo'and calls[2].target==428,w.error)
calls={}
w=start('patch',{id='bs',mod='m',booster='Experimental Infusion',target_path='status_effect',changes={
 change({kind='status_row',offset=40,width=4,storage='f32'},20,10)}})
assert(w.status=='complete'and calls[1].component=='StatusEffectSettings'and calls[1].target==29,w.error)
w=start('patch',{id='bc',mod='m',booster='Concealed Insertion',target_path='explosion',changes={
 change({kind='explosion_damage',offset=4,width=4,storage='i32'},5,3)}})
assert(w.status=='rejected'and w.error:find('no DamageInfo row',1,true),w.error)
calls={}
w=start('patch',{id='bg',mod='m',booster='Surplus EAT Allocation',target_path='granted_stratagem',changes={
 change({kind='stratagem_row',offset=80,width=4,storage='u32'},6,4)}})
assert(w.status=='complete'and calls[1].component=='StratagemDefinition'and calls[1].target==15,w.error)
calls={}
w=start('patch',{id='ol',mod='m',stratagem='Orbital Laser',target_path='stratagem',changes={
 change({kind='OrbitalAbilityComponentData',nativeIdentity=970450596,offset=460,phase=1,width=4,storage='f32'},9,6)}})
assert(w.status=='complete'and calls[1].component=='OrbitalAbilityComponentData'
 and calls[1].target==require('hd2runtime/runtime/hellforge_writes').resource('0xEC3575E7A93793BB'),w.error)
w=start('patch',{id='ox',mod='m',changes={change({kind='OrbitalAbilityComponentData',nativeIdentity=970450596,offset=460,
 width=4,storage='f32'},9,6)}})
assert(w.status=='rejected',w.error)
-- a plan: every phase's changes
calls={}
w=start('plan',{id='g',mod='m',phases={{capture_specs={{changes={change(comp,70)}},{changes={change(row,900,385)}}}}}})
assert(w.status=='complete'and #calls==2,w.error)
''')

    def test_unavailable_areas_and_passives(self):
        check(r'''
local hd2=require('hd2runtime/api/hd2')
local h=hd2.custom_stratagem.register({id='x'})
assert(h.status=='rejected'and h.result.code=='HELLFORGE_UNAVAILABLE')
assert(select(2,hd2.enemies.spawn_weight())=='HELLFORGE_UNAVAILABLE')
assert(type(hd2.explosions.list())=='table'and type(hd2.projectiles.list())=='table') -- catalogue reads stay
local areas=table.concat(hd2.hellforge.unavailable,',')
assert(areas=='custom_stratagem,enemies'and #hd2.hellforge.events_unavailable==0,areas)
local s=hd2.player_passives.set({armor='SCOUT'})
assert(s.status=='active'and calls[#calls].op=='passives'and calls[#calls].second==0xFFFFFFFF,s.reason)
s:stop()
assert(calls[#calls].armor==0xFFFFFFFF and s.status=='stopped')
assert(hd2.player_passives.set({armor='NOT A PASSIVE'}).status=='refused')
''')

    def test_actions_through_hellforge(self):
        # Each action's last step is HellForge's engine action; the Runtime's own checks and answers stay.
        check(r'''
local hd2=require('hd2runtime/api/hd2')
local act=function(op)return function(...)calls[#calls+1]={op=op,args={...}};return FAKE.answer or 2 end end
for _,op in ipairs({'heal','heal_limb','injure','apply_status','add_velocity','resupply_from_pack','spawn_explosion',
 'spawn_projectile','credit_to_player','freeze_mission_timer'})do FAKE[op]=act(op)end
function FAKE.limb_state()return {health=20,max=35,injured=false}end
function FAKE.homing(m,kind,sources,turn,cone,range,arm,aim,flags)calls[#calls+1]={op='homing',kind=kind,sources=sources,turn=turn,cone=cone,flags=flags};return 7 end
local next_rule=10
function FAKE.modify_shots(m,kind,sources,damage)next_rule=next_rule+1;calls[#calls+1]={op='modify',kind=kind,damage=damage,id=next_rule};return next_rule end
function FAKE.stop_shots(m,id)calls[#calls+1]={op='stop',id=id};return true end
local world=require('hd2runtime/runtime/event_world')
-- the status request, explosions and projectiles: HellForge's
calls={}
assert(world.status({},{type=5,target=77,buildup=100})==true and calls[1].op=='apply_status'and calls[1].args[2]==77 and calls[1].args[3]==5)
assert(world.explode({},{type=158,x=1,y=2,z=3})==true and calls[2].op=='spawn_explosion'and calls[2].args[2]==158)
FAKE.answer=3
local ok,why=world.explode({},{type=158,x=1,y=2,z=3})
assert(ok==nil and why:find('ASSET_UNAVAILABLE',1,true))
FAKE.answer=0
ok,why=world.projectile({},{type=40,x=0,y=0,z=0,dx=1,dy=0,dz=0})
assert(ok==nil and why:find('HELLFORGE_REFUSED',1,true),why)
FAKE.answer=nil
-- the mission timer freeze, kill credit
calls={}
local r=hd2.freeze_mission_timer({frozen=true,allow_unverified_effect=true})
assert(r and r.status=='APPLIED'and calls[1].op=='freeze_mission_timer'and calls[1].args[2]==true)
assert(hd2.freeze_mission_timer({frozen=true})==nil)
local credit=require('hd2runtime/runtime/ownership').credit_to_host({},99,'x')
assert(credit.applied and calls[2].op=='credit_to_player'and calls[2].args[2]==99)
-- homing: degrees and HellForge's flags; per-shot changes: one rule per type, renewed by set, ended by stop
calls={}
local homing=require('hd2runtime/runtime/projectile_homing')
local config=homing.configure({owner='m',output='w#40',weapon='w',type=40,sources={'B6AFF2195568767F'},target='friendly',
 turn_rate=math.rad(90),cone=math.rad(30),range=100,arm_distance=2,aim_height=1,retarget=false,multiplayer=false})
assert(config and config.id==7 and math.abs(calls[1].turn-90)<1e-6 and math.abs(calls[1].cone-30)<1e-6 and calls[1].flags==6
 and #calls[1].sources==1)
assert(homing.stop(config)and calls[2].op=='stop'and calls[2].id==7)
local shots=require('hd2runtime/runtime/projectile_shots')
calls={}
local c=shots.configure({owner='m',weapon='w',types={40,41},sources={},changes={damage=2}})
assert(c and #c.rules==2 and calls[1].damage==2 and calls[2].kind==41)
assert(shots.set(c,{damage=3})and calls[3].op=='stop'and calls[5].damage==3)
assert(shots.stop(c)and c.status=='stopped')
''')

    def test_event_sources_from_hellforge(self):
        check(r'''
local b=require('hd2runtime/core/bytes')
local events=require('hd2runtime/runtime/events')
local world=require('hd2runtime/runtime/event_world')
local sources=require('hd2runtime/runtime/event_sources')
-- a world the sources read: one local player, its Helldiver 55
world.open=function()return {}end
world.players=function()return {{peer='0000000000000007',['local']=true,avatar=55,entity=44,slot=0}}end
world.entity_state=function()return {descriptor={type='4D1C334D294DFA97',pointer=1,unit=9,goid=3},life=0,health=100,max_health=125}end
world.source_name=function(hex)return hex=='B6AFF2195568767F'and'R-36 Eruptor'or nil end
world.entity_type=function(w,id)return id==55 and'4D1C334D294DFA97'or nil end
world.unit_position=function()return nil end
local got={}
events.queue=function(name,event)got[#got+1]={name=name,event=event}end
events.wanted=function()return true end
local function data(kind,fields)
 local s=string.rep('\0',128)
 local function put(at,str)s=s:sub(1,at)..str..s:sub(at+#str+1)end
 put(0,b.encode(128,'u32'));put(4,b.encode(kind,'u32'))
 for _,f in ipairs(fields)do put(f[1],b.encode(f[2],f[3]or'u32'))end
 return s
end
local function poll(name,raw)
 local s=sources[name]
 if not s.started then assert(s.start(s));s.started=true end
 got={}
 FAKE.queue={raw}
 events.state.frame=(events.state.frame or 0)+1
 s.poll(s)
 return got
end
-- a heal of the local Helldiver
local q=poll('health',data(10,{{16,55},{20,25},{24,100},{28,125},{32,7},{40,1}}))
assert(#q==1 and q[1].name=='player_healed'and q[1].event.amount==25 and q[1].event.local_player and q[1].event.max_health==125)
-- shots fired, by source
q=poll('stats',data(11,{{16,0x565790DA},{20,3},{24,10},{28,0},{32,44},{36,1},{40,0x5568767F},{44,0xB6AFF219},{48,3}}))
assert(#q==1 and q[1].name=='player_fired'and q[1].event.shots==3 and q[1].event.total==10 and q[1].event.sources[1].name=='R-36 Eruptor'
 and q[1].event.sources[1].shots==3)
-- a switch: unequipped, equipped, changed
q=poll('weapons',data(12,{{16,55},{20,55},{24,605},{28,600},{32,0x5568767F},{36,0xB6AFF219},{40,1},{44,2},{48,2},{52,1}}))
assert(#q==3 and q[1].name=='weapon_unequipped'and q[1].event.reason=='switched'and q[2].event.weapon.name=='R-36 Eruptor'
 and q[2].event.weapon.slot=='secondary'and q[3].name=='weapon_changed')
-- an explosion credited to the local player
q=poll('explosions',data(13,{{16,158},{20,55},{24,55},{32,7},{40,1.5,'f32'}}))
assert(#q==1 and q[1].event.source_type=='4D1C334D294DFA97'and q[1].event.local_player and q[1].event.creditor_peer=='0000000000000007')
-- a bug hole closed
q=poll('bug_holes',data(14,{{16,900},{20,901},{24,0x759CBD61},{28,0x8C31B749},{32,2},{36,1}}))
assert(#q==1 and q[1].event.hole=='warrior'and q[1].event.level==2 and q[1].event.owned and q[1].event.position==nil)
-- the world proof skips only the code HellForge rewrites
local hf=require('hd2runtime/runtime/hellforge')
assert(hf.backend().rewrites(0x13A9715,7))
assert(hf.rewritten('game',0x13A9715,7) and not hf.rewritten('game',0x10,4) and not hf.rewritten('exe',0x13A9715,7))
''')


if __name__ == '__main__':
    unittest.main()
