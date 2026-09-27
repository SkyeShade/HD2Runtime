import json
import unittest

from support import ROOT, execute, modules


CAPABILITIES = json.loads((ROOT / 'sdk/CompositionPlanCapabilities.json').read_text())


class CompositionPlanTests(unittest.TestCase):
    def run_lua(self, body):
        self.assertEqual(execute((modules() + body).encode()), b'ok')

    def test_concussive_damage_and_terminal_references_validate_as_one_plan(self):
        self.run_lua(r'''
local hd2=require('hd2runtime/api/session').new({},function()end)
local plans=require('hd2runtime/domains/composition_plans')
local reviewed=require('hd2runtime/domains/player_weapon_authoring').weapons['AR-23C Liberator Concussive']
for _,field in ipairs(reviewed.fields)do if field.semanticFieldId=='damage.ap_extreme'then
 assert(field.currentDefault==2,'reviewed extreme='..tostring(field.currentDefault))end end
local projectile=hd2.weapon('AR-23C Liberator Concussive'):attack('primary'):projectile()
local impact=projectile:terminal_action('impact')
local expiry=projectile:terminal_action('expiry')
local source=hd2.weapon('R-36 Eruptor'):attack('primary'):projectile()
 :terminal_action('impact'):explosion()
local spec=plans.validate{id='concussive-composition',operations={
 {id='damage',target=projectile,allow_shared=true,changes={
  {field=hd2.fields.damage.ap_direct,expect=2,value=3},
  {field=hd2.fields.damage.ap_slight,expect=2,value=3},
  {field=hd2.fields.damage.ap_large,expect=2,value=3},
  {field=hd2.fields.damage.ap_extreme,expect=2,value=3},
  {field=hd2.fields.damage.push_force,expect=60,value=30}}},
 {id='impact',target=impact,allow_shared=true,field=hd2.fields.terminal.explosion,
  expect=impact:no_explosion(),value=source},
 {id='expiry',target=expiry,allow_shared=true,field=hd2.fields.terminal.explosion,
  expect=expiry:no_explosion(),value=source}}}
assert(spec.kind=='composition_plan'and#spec.phases==1 and#spec.operations==3)
assert(#spec.phases[1].capture_specs==3)
assert(#spec.operations[1].spec.changes==5)
assert(spec.operations[2].spec.changes[1].descriptor.type=='explosion_reference')
assert(spec.operations[3].spec.changes[1].descriptor.referencePhase=='expiry')
return'ok'
''')

    def test_physics_damage_terminals_and_explosion_objects_are_valid_targets(self):
        self.run_lua(r'''
local hd2=require('hd2runtime/api/session').new({},function()end)
local plans=require('hd2runtime/domains/composition_plans')
local verdict=hd2.weapon('P-113 Verdict'):attack('primary'):projectile()
local spec=plans.validate{id='physics-damage',operations={
 {id='physics',target=verdict,allow_shared=true,changes={
  {field=hd2.fields.projectile.velocity,expect=285,value=300},
  {field=hd2.fields.projectile.drag,expect=1.2,value=0.5}}},
 {id='damage',target=verdict,allow_shared=true,changes={
  {field=hd2.fields.damage.ap_direct,expect=3,value=4},
  {field=hd2.fields.damage.push_force,expect=10,value=20}}}}}
assert(#spec.operations==2 and#spec.operations[1].spec.changes==2)
assert(spec.operations[1].backing_scope=='settings:projectile')
assert(spec.operations[2].backing_scope=='settings:damage')
local eruptor=hd2.weapon('R-36 Eruptor'):attack('primary'):projectile()
 :terminal_action('impact'):explosion()
local explosion=plans.validate{id='explosion-tuning',operations={{id='geometry',
 target=eruptor,allow_shared=true,changes={
  {field=hd2.fields.explosion.inner_radius,expect=4,value=5},
  {field=hd2.fields.explosion.outer_radius,expect=7,value=8}}},
 {id='damage',target=eruptor,allow_shared=true,changes={
  {field=hd2.fields.explosion.damage_standard_damage,expect=225,value=300},
  {field=hd2.fields.explosion.damage_ap_direct,expect=3,value=4},
  {field=hd2.fields.explosion.damage_push_force,expect=40,value=50}}}}}
assert(#explosion.operations==2 and explosion.operations[1].backing_scope=='settings:explosion')
assert(explosion.operations[2].backing_scope=='settings:explosion_damage')
local ok,why=pcall(plans.validate,{id='unsafe-shared-scope',operations={{id='mixed',
 target=verdict,allow_shared=true,changes={
  {field=hd2.fields.projectile.velocity,expect=285,value=300},
  {field=hd2.fields.damage.ap_direct,expect=3,value=4}}}}})
assert(not ok and tostring(why):find('multiple backing objects',1,true))
return'ok'
''')

    def test_terminal_references_form_a_single_deterministic_write_set(self):
        self.run_lua(r'''
local hd2=require('hd2runtime/api/session').new({},function()end)
local plans=require('hd2runtime/domains/composition_plans')
local projectile=hd2.weapon('AR-23C Liberator Concussive'):attack('primary'):projectile()
local impact=projectile:terminal_action('impact');local expiry=projectile:terminal_action('expiry')
local source=hd2.weapon('R-36 Eruptor'):attack('primary'):projectile()
 :terminal_action('impact'):explosion()
local spec=plans.validate{id='terminals',operations={
 {id='impact',target=impact,allow_shared=true,field=hd2.fields.terminal.explosion,
  expect=impact:no_explosion(),value=source},
 {id='expiry',target=expiry,allow_shared=true,field=hd2.fields.terminal.explosion,
  expect=expiry:no_explosion(),value=source}}}
assert(spec.operations[1].id=='impact'and spec.operations[2].id=='expiry')
assert(spec.phases[1].capture_operation_ids[1]=='impact')
assert(spec.phases[1].capture_operation_ids[2]=='expiry')
return'ok'
''')

    def test_shared_acknowledgement_is_per_operation(self):
        self.run_lua(r'''
local hd2=require('hd2runtime/api/session').new({},function()end)
local plans=require('hd2runtime/domains/composition_plans')
local projectile=hd2.weapon('JAR-5 Dominator'):attack('primary'):projectile()
local ok,why=pcall(plans.validate,{id='shared-missing',operations={{id='velocity',
 target=projectile,field=hd2.fields.projectile.velocity,expect=180,value=200}}})
assert(not ok and tostring(why):find('allow_shared=true',1,true))
ok,why=pcall(plans.validate,{id='scope-isolated',operations={
 {id='velocity',target=projectile,allow_shared=true,
  field=hd2.fields.projectile.velocity,expect=180,value=200},
 {id='damage',target=projectile,
  field=hd2.fields.damage.ap_direct,expect=3,value=4}}})
assert(not ok and tostring(why):find('allow_shared=true',1,true))
local valid=plans.validate{id='scope-explicit',operations={
 {id='velocity',target=projectile,allow_shared=true,
  field=hd2.fields.projectile.velocity,expect=180,value=200},
 {id='damage',target=projectile,allow_shared=true,
  field=hd2.fields.damage.ap_direct,expect=3,value=4}}}
assert(valid.operations[1].allow_shared and valid.operations[2].allow_shared)
return'ok'
''')

    def test_projectile_replacement_dependency_resolves_to_source_object(self):
        self.run_lua(r'''
local hd2=require('hd2runtime/api/session').new({},function()end)
local plans=require('hd2runtime/domains/composition_plans')
local target=hd2.weapon('SMG-32 Reprimand'):attack('primary')
local source=hd2.weapon('JAR-5 Dominator'):attack('primary'):projectile()
local spec=plans.validate{id='swap-and-tune',phases={
 {id='selector',operations={{id='swap',target=target,
  field=hd2.fields.attack.projectile,expect=target:projectile(),value=source}}},
 {id='definition',operations={
  {id='physics',target_from={operation='swap',path='projectile'},allow_shared=true,
   changes={{field=hd2.fields.projectile.velocity,expect=180,value=220},
    {field=hd2.fields.projectile.drag,expect=0,value=0.2}}},
  {id='impact',target_from={operation='swap',path='terminal.impact'},allow_shared=true,
   field=hd2.fields.terminal.explosion,
   expect=source:terminal_action('impact'):no_explosion(),
   value=hd2.weapon('R-36 Eruptor'):attack('primary'):projectile()
    :terminal_action('impact'):explosion()}}}}}
assert(#spec.phases==2 and#spec.phases[2].dependency_specs==1)
assert(spec.operations[2].target.weapon=='JAR-5 Dominator')
assert(spec.operations[2].target.path=='projectile_reference')
assert(spec.operations[3].target.path=='terminal_action'and spec.operations[3].target.phase=='impact')
assert(spec.phases[2].capture_operation_ids[1]=='dependency:swap')
assert(spec.phases[2].capture_operation_ids[2]=='physics')
assert(spec.phases[2].capture_operation_ids[3]=='impact')
return'ok'
''')

    def test_dependency_must_be_prior_phase_and_projectile_replacement(self):
        self.run_lua(r'''
local hd2=require('hd2runtime/api/session').new({},function()end)
local plans=require('hd2runtime/domains/composition_plans')
local projectile=hd2.weapon('JAR-5 Dominator'):attack('primary'):projectile()
local ok,why=pcall(plans.validate,{id='same-phase',operations={
 {id='damage',target=projectile,allow_shared=true,
  field=hd2.fields.damage.ap_direct,expect=3,value=4},
 {id='dependent',target_from={operation='damage',path='projectile'},allow_shared=true,
  field=hd2.fields.projectile.velocity,expect=180,value=200}}})
assert(not ok and tostring(why):find('prior phase',1,true))
return'ok'
''')

    def test_multi_object_guard_order_noop_conflict_and_late_rollback(self):
        self.run_lua(r'''
local b=require('hd2runtime/core/bytes')
local guard=require('hd2runtime/core/guarded_transaction')
local function splice(value,offset,bytes)return value:sub(1,offset)..bytes..value:sub(offset+#bytes+1)end
local owners={{base=0x100000,size=4096,type=0x20000,protect=2},
 {base=0x200000,size=4096,type=0x20000,protect=2}}
local memory={[1]=string.rep('\0',4096),[2]=string.rep('\0',4096)}
local before={b.encode(2,'u32'),b.encode(60,'u32'),b.encode(0,'u32'),b.encode(0,'u32')}
local desired={b.encode(3,'u32'),b.encode(30,'u32'),b.encode(59,'u32'),b.encode(59,'u32')}
local offsets={12,36,144,156};local which={1,1,2,2}
for i=1,4 do memory[which[i]]=splice(memory[which[i]],offsets[i],before[i])end
local function make_plan(states)
 local snapshots={{owner=owners[1],offset=0,bytes=memory[1]},
  {owner=owners[2],offset=0,bytes=memory[2]}}
 local changes={}
 for i=1,4 do changes[i]={label='field-'..i,canonical_field='field-'..i,
  owner=owners[which[i]],offset=offsets[i],expected=before[i],desired=desired[i],
  before=states and states[i]or before[i],identity={},chain={},expect=0,value=1}end
 return{changes=changes,snapshots=snapshots}
end
local protection={[1]=2,[2]=2};local writes,order,fail_at=0,{},nil
local runtime={}
function runtime.system_info()return 4096,0x1000000 end
local function locate(address)return address>=owners[2].base and 2 or 1 end
function runtime.query(address)local n=locate(address);local owner=owners[n]
 return{base=owner.base,size=owner.size,allocation_base=owner.base,state=0x1000,
  type=owner.type,protect=protection[n]}end
function runtime.read(address,length)local n=locate(address);local owner=owners[n]
 return memory[n]:sub(address-owner.base+1,address-owner.base+length)end
function runtime.protect(address,_,value)local n=locate(address);local old=protection[n];protection[n]=value;return old end
function runtime.write(address,value)writes=writes+1;order[#order+1]=address
 if fail_at and writes==fail_at then return false,'injected',0 end
 local n=locate(address);memory[n]=splice(memory[n],address-owners[n].base,value)
 return true,nil,#value end
local result=guard.apply(runtime,make_plan())
assert(result.status=='APPLIED'and result.writes==4)
assert(order[1]==owners[1].base+12 and order[4]==owners[2].base+156)
assert(result.non_target_bytes_unchanged and result.protection_restored)
-- Exact desired state is a coherent zero-write plan.
local states={};for i=1,4 do states[i]=desired[i]end
local no_op=guard.apply(runtime,make_plan(states))
assert(no_op.status=='ALREADY_DESIRED'and no_op.writes==0 and no_op.protection_changes==0)
-- Reset, fail late, and prove all earlier objects roll back.
for i=1,4 do memory[which[i]]=splice(memory[which[i]],offsets[i],before[i])end
writes=0;order={};fail_at=4
local failed=guard.apply(runtime,make_plan())
assert(failed.status=='REJECTED'and failed.rollback=='verified'and failed.protection_restored)
for i=1,4 do assert(runtime.read(owners[which[i]].base+offsets[i],4)==before[i])end
return'ok'
''')

    def test_inverse_plan_rolls_back_prior_phase_after_dependent_failure(self):
        self.run_lua(r'''
local b=require('hd2runtime/core/bytes');local guard=require('hd2runtime/core/guarded_transaction')
local owner={base=0x300000,size=4096,type=0x20000,protect=2};local protection=2
local function splice(value,offset,bytes)return value:sub(1,offset)..bytes..value:sub(offset+#bytes+1)end
local memory=string.rep('\0',4096);memory=splice(memory,0,b.encode(10,'u32'))
local runtime={};function runtime.system_info()return 4096,0x1000000 end
function runtime.query(address)return{base=owner.base,size=owner.size,allocation_base=owner.base,
 state=0x1000,type=owner.type,protect=protection}end
function runtime.read(address,length)return memory:sub(address-owner.base+1,address-owner.base+length)end
function runtime.protect(_,_,value)local old=protection;protection=value;return old end
function runtime.write(address,value)memory=splice(memory,address-owner.base,value);return true,nil,#value end
local phase1={snapshots={{owner=owner,offset=0,bytes=memory}},changes={{label='selector',owner=owner,
 offset=0,expected=b.encode(10,'u32'),desired=b.encode(20,'u32'),before=b.encode(10,'u32'),
 identity={},chain={},expect=10,value=20}}}
assert(guard.apply(runtime,phase1).status=='APPLIED'and b.u32(memory,0)==20)
local inverse=guard.inverse(phase1);assert(#inverse.changes==1)
-- A dependent phase sees the post-swap selector, then fails without changing it.
assert(b.u32(memory,0)==20)
assert(guard.apply(runtime,inverse).status=='APPLIED'and b.u32(memory,0)==10)
return'ok'
''')

    def test_unexpected_external_non_target_mutation_rejects(self):
        self.run_lua(r'''
local b=require('hd2runtime/core/bytes');local guard=require('hd2runtime/core/guarded_transaction')
local owner={base=0x500000,size=4096,type=0x20000,protect=2};local protection=2
local function splice(value,offset,bytes)return value:sub(1,offset)..bytes..value:sub(offset+#bytes+1)end
local captured=string.rep('\0',128);captured=splice(captured,12,b.encode(2,'u32'))
local memory=splice(captured,64,'X')
local runtime={};function runtime.system_info()return 4096,0x1000000 end
function runtime.query()return{base=owner.base,size=owner.size,allocation_base=owner.base,
 state=0x1000,type=owner.type,protect=protection}end
function runtime.read(address,length)return memory:sub(address-owner.base+1,address-owner.base+length)end
function runtime.protect(_,_,value)local old=protection;protection=value;return old end
local writes=0;function runtime.write()writes=writes+1;return true,nil,4 end
local result=guard.apply(runtime,{snapshots={{owner=owner,offset=0,bytes=captured}},changes={{
 label='ap',owner=owner,offset=12,expected=b.encode(2,'u32'),desired=b.encode(3,'u32'),
 before=b.encode(2,'u32'),identity={},chain={},expect=2,value=3}}})
assert(result.status=='REJECTED'and writes==0 and result.protection_changes==0)
assert(result.reason:find('non-target bytes changed',1,true))
return'ok'
''')

    def test_ensure_accepts_plan_and_metadata_is_address_free(self):
        self.assertEqual(CAPABILITIES['api'], 'hd2.plan')
        self.assertEqual(CAPABILITIES['sharedScope']['granularity'], 'operation')
        self.assertFalse(CAPABILITIES['sharedScope']['implicitCrossObjectAuthorization'])
        encoded = json.dumps(CAPABILITIES).lower()
        self.assertNotIn('address', encoded)
        self.run_lua(r'''
local runtime={write=function()end,protect=function()end}
local hd2=require('hd2runtime/api/session').new(runtime,function()end)
local projectile=hd2.weapon('JAR-5 Dominator'):attack('primary'):projectile()
local watch=hd2.ensure{startup_delay=0,plan={id='ensured-plan',operations={{id='damage',
 target=projectile,allow_shared=true,field=hd2.fields.damage.ap_direct,expect=3,value=4}}}}
assert(watch.kind=='plan'and watch.status=='waiting');watch.cancel();assert(watch.status=='cancelled')
return'ok'
''')

    def test_plan_coordinator_fresh_phase_and_cross_phase_rollback(self):
        self.run_lua(r'''
local b=require('hd2runtime/core/bytes');local profile=require('hd2runtime/schemas/current')
local guard=require('hd2runtime/core/guarded_transaction')
local owners={{base=0x600000,size=4096,type=0x20000,protect=2},
 {base=0x700000,size=4096,type=0x20000,protect=2}}
local function splice(value,offset,bytes)return value:sub(1,offset)..bytes..value:sub(offset+#bytes+1)end
local memory={[1]=splice(string.rep('\0',4096),0,b.encode(10,'u32')),
 [2]=splice(string.rep('\0',4096),32,b.encode(1,'f32'))}
local protection={2,2};local writes,fail_on=0,2
local runtime={mode='synthetic'}
function runtime.module(name)return name or'exe'end
function runtime.module_hash(module)return module=='exe'and profile.exe_sha or profile.dll_sha end
function runtime.system_info()return 4096,0x1000000 end
local function locate(address)return address>=owners[2].base and 2 or 1 end
function runtime.query(address)local n=locate(address);local owner=owners[n]
 return{base=owner.base,size=owner.size,allocation_base=owner.base,state=0x1000,
  type=owner.type,protect=protection[n]}end
function runtime.read(address,length)local n=locate(address);return memory[n]:sub(
 address-owners[n].base+1,address-owners[n].base+length)end
function runtime.protect(address,_,value)local n=locate(address);local old=protection[n];protection[n]=value;return old end
function runtime.write(address,value)writes=writes+1;if writes==fail_on then return false,'late',0 end
 local n=locate(address);memory[n]=splice(memory[n],address-owners[n].base,value);return true,nil,#value end
local Reader={};function Reader.new()return{snapshots={},verify=function()end}end
local Weapons={};local captures=0
function Weapons.capture_many(_,reader,_)captures=captures+1
 if captures==1 then coroutine.yield()else assert(b.u32(memory[1],0)==20,'phase 2 did not see swapped selector')end
 return{{},{}}end
local Plans={}
function Plans.prepare_phase(_,reader,phase)
 if phase.index==1 then
  reader.snapshots={{owner=owners[1],offset=0,bytes=memory[1]}}
  return{snapshots=reader.snapshots,changes={{label='swap',canonical_field='attack.projectile',
   plan_operations={'swap'},owner=owners[1],offset=0,expected=b.encode(10,'u32'),
   desired=b.encode(20,'u32'),before=b.encode(10,'u32'),identity={},chain={},expect=10,value=20}}}
 end
 reader.snapshots={{owner=owners[1],offset=0,bytes=memory[1]},
  {owner=owners[2],offset=0,bytes=memory[2]}}
 return{snapshots=reader.snapshots,changes={{label='swap',canonical_field='attack.projectile',
  plan_operations={'dependency:swap'},owner=owners[1],offset=0,expected=b.encode(10,'u32'),
  desired=b.encode(20,'u32'),before=b.encode(20,'u32'),identity={},chain={},expect=10,value=20},
  {label='velocity',canonical_field='projectile.velocity',plan_operations={'velocity'},
  owner=owners[2],offset=32,expected=b.encode(1,'f32'),desired=b.encode(2,'f32'),
  before=b.encode(1,'f32'),identity={},chain={},expect=1,value=2}}}
end
package.loaded['hd2runtime/runtime/reader']=Reader
package.loaded['hd2runtime/domains/player_weapon_writes']=Weapons
package.loaded['hd2runtime/domains/composition_plans']=Plans
package.loaded['hd2runtime/core/guarded_transaction']=guard
local api=require('hd2runtime/api/plan')
local spec={id='phased',phases={{id='selector',index=1,capture_specs={{}}},
 {id='definition',index=2,capture_specs={{},{}}}}}
local watch=api.start_spec(runtime,function()end,spec,0)
for _=1,20 do watch.tick(1);if watch.status=='complete'or watch.status=='rejected'then break end end
assert(watch.status=='rejected'and watch.result.rollback=='verified')
assert(b.u32(memory[1],0)==10 and b.value(memory[2],32,'f32')==1)
assert(protection[1]==2 and protection[2]==2 and captures==2)
-- Run the same coordinator without the injected failure. Both phases apply and
-- the dependent phase observes the freshly selected projectile.
fail_on=nil;writes=0;captures=0
watch=api.start_spec(runtime,function()end,spec,0)
for _=1,20 do watch.tick(1);if watch.status=='complete'or watch.status=='rejected'then break end end
assert(watch.status=='complete'and watch.result.status=='APPLIED')
assert(#watch.result.phases==2 and watch.result.phases[1].status=='APPLIED')
assert(watch.result.phases[2].status=='APPLIED'and captures==2)
assert(b.u32(memory[1],0)==20 and b.value(memory[2],32,'f32')==2)
assert(watch.result.non_target_bytes_unchanged and watch.result.protection_restored)
assert(protection[1]==2 and protection[2]==2)
return'ok'
''')


if __name__ == '__main__':
    unittest.main()
