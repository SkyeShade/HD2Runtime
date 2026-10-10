"""Original bullet references survive a donor's own swap without relaxing live handles or guards."""
import unittest
from support import run

FIXTURE = r'''
local hd2=require('hd2runtime/api/session').new({},function()end)
local writes=require('hd2runtime/domains/player_weapon_writes')
local plans=require('hd2runtime/domains/composition_plans')
local db=require('hd2runtime/domains/player_weapon_authoring')
local b=require('hd2runtime/core/bytes')
local guard=require('hd2runtime/core/guarded_transaction')
local function splice(s,o,v)return s:sub(1,o)..v..s:sub(o+#v+1)end
local owner={base=0x100000,size=16384,type=0x20000,protect=2}
local memory=string.rep('\0',owner.size)
local roots={projectile={owner=owner,records={}},damage={owner=owner,records={}}}
local candidates,components,fields={},{},{}
local one='AR/GL-21 One-Two';local sta='StA-52 Assault Rifle';local tender='AR-61 Tenderizer'
local cursor=256
local function allocate(bytes)local at=cursor;cursor=cursor+#bytes+16;memory=splice(memory,at,bytes);return at end
local function settings(backing,bytes)
 return {group=backing.group,row=backing.row,kind=backing.recordType,settings_type=backing.settingsType,
  offset=allocate(bytes),bytes=bytes}
end
for _,name in ipairs({one,sta,tender})do
 local f={};fields[name]=f
 for _,field in ipairs(db.weapons[name].fields)do f[field.semanticFieldId]=field end
 local selector=f['attack.primary.projectile'];local backing=selector.backing
 local candidate={name=name,resourceHash=db.weapons[name].resources[1],ownership={ProjectileWeaponComponentData={}}}
 candidates[name]=candidate
 components[name]={owner=owner,offset=allocate(b.encode(selector.currentDefault.projectileType,'u32')..string.rep('\0',596)),
  identity={recordIndex=backing.recordIndex,indexRow=backing.indexRow,ownerCount=backing.ownerCount,
   componentType='ProjectileWeaponComponentData',uniqueOwner=true}}
 local damage=f['damage.standard_damage'].backing
 local damage_bytes=string.rep('\0',128)
 damage_bytes=splice(damage_bytes,4,b.encode(f['damage.standard_damage'].currentDefault,'i32'))
 damage_bytes=splice(damage_bytes,8,b.encode(f['damage.durable_damage'].currentDefault,'i32'))
 roots.damage.records[damage.recordType]=settings(damage,damage_bytes)
 roots.projectile.records[selector.currentDefault.projectileType]=settings(selector.referenceSettings,
  splice(string.rep('\0',200),60,b.encode(damage.recordType,'u32')))
end
local catalog={record=function(candidate)
 local r=components[candidate.name];r.bytes=memory:sub(r.offset+1,r.offset+600);return r
end}
local function refresh()
 for _,kind in ipairs({'projectile','damage'})do for _,r in pairs(roots[kind].records)do
  r.bytes=memory:sub(r.offset+1,r.offset+#r.bytes)
 end end
end
local reader={snapshots={}}
local function prepare(spec)
 refresh();reader.snapshots={{owner=owner,offset=0,bytes=memory}}
 local resolved={roots=roots,catalog=catalog,candidate=candidates[spec.weapon],reference_sources={}}
 for _,c in ipairs(spec.changes)do if c.desired_selector and c.desired_selector.weapon then
  resolved.reference_sources[c.canonical_field]=candidates[c.desired_selector.weapon]
 end end
 return writes.prepare(resolved,reader,spec)
end
local protection=2;local write_count=0;local fail_at
local runtime={system_info=function()return 4096,0x1000000 end,
 query=function()return {base=owner.base,size=owner.size,allocation_base=owner.base,state=0x1000,type=owner.type,protect=protection}end,
 read=function(at,n)return memory:sub(at-owner.base+1,at-owner.base+n)end,
 protect=function(_,_,value)local old=protection;protection=value;return old end,
 write=function(at,value)write_count=write_count+1
  if fail_at==write_count then return false,'injected',0 end
  memory=splice(memory,at-owner.base,value);return true,nil,#value end}
local a=hd2.weapon(one):attack('primary');local s=hd2.weapon(sta):attack('primary')
local t=hd2.weapon(tender):attack('primary')
local function damage(target)
 return writes.validate_transaction{id='damage',target=target,allow_shared=true,changes={
  {field=hd2.fields.damage.player_standard_damage,expect=95,value=80},
  {field=hd2.fields.damage.player_durable_damage,expect=24,value=85}}}
end
local function swap(target,value)
 return writes.validate_patch{id='swap',target=target,field=hd2.fields.attack.projectile,
  expect=target:projectile(),value=value}
end
local damage_spec=damage(a:original_projectile())
local sta_spec=swap(s,a:original_projectile())
local one_spec=swap(a,t:projectile())
local function apply(spec)return guard.apply(runtime,prepare(spec))end
'''


class OriginalProjectileTests(unittest.TestCase):
    def check(self, body):
        self.assertEqual(run(FIXTURE + body), b'ok')

    def test_damage_transfer_swap_and_fresh_resolution_are_idempotent(self):
        self.check(r'''
assert(apply(damage_spec).status=='APPLIED')
assert(apply(sta_spec).status=='APPLIED')
assert(apply(one_spec).status=='APPLIED')
local before=write_count
assert(apply(damage_spec).status=='ALREADY_DESIRED')
assert(apply(sta_spec).status=='ALREADY_DESIRED')
assert(apply(one_spec).status=='ALREADY_DESIRED')
assert(write_count==before)
local original=fields[one]['attack.primary.projectile'].currentDefault.projectileType
assert(b.u32(memory,components[sta].offset)==original)
assert(b.u32(memory,components[one].offset)==fields[tender]['attack.primary.projectile'].currentDefault.projectileType)
local d=roots.damage.records[fields[one]['damage.standard_damage'].backing.recordType]
assert(b.u32(memory,d.offset+4)==80 and b.u32(memory,d.offset+8)==85)
local td=roots.damage.records[fields[tender]['damage.standard_damage'].backing.recordType]
assert(b.u32(memory,td.offset+4)==105 and b.u32(memory,td.offset+8)==30)
-- Existing live handles continue to reject a changed donor; the new behavior is explicit.
assert(not pcall(prepare,swap(s,a:projectile())))
assert(not pcall(prepare,damage(a:projectile())))
return'ok'
''')

    def test_target_conflicts_and_identity_changes_still_reject_without_writes(self):
        self.check(r'''
local at=components[sta].offset
memory=splice(memory,at,b.encode(999,'u32'))
local before=write_count
assert(not pcall(apply,sta_spec)and write_count==before)
components[one].identity.recordIndex=-1
assert(not pcall(prepare,sta_spec)and write_count==before)
assert(not pcall(prepare,damage_spec)and write_count==before)
return'ok'
''')

    def test_original_settings_and_damage_link_are_reproven(self):
        self.check(r'''
local projectile=roots.projectile.records[fields[one]['attack.primary.projectile'].currentDefault.projectileType]
local row=projectile.row;projectile.row=-1
assert(not pcall(prepare,sta_spec));assert(not pcall(prepare,damage_spec));projectile.row=row
memory=splice(memory,projectile.offset+60,b.encode(999,'u32'))
assert(not pcall(prepare,damage_spec));assert(write_count==0)
return'ok'
''')

    def test_damage_write_failure_rolls_back_and_restores_protection(self):
        self.check(r'''
local before=memory;fail_at=2
local result=apply(damage_spec)
assert(result.status=='REJECTED'and result.rollback=='verified')
assert(memory==before and protection==2)
return'ok'
''')

    def test_handles_remain_narrow_and_shared_acknowledgement_is_required(self):
        self.check(r'''
assert(not pcall(writes.validate_patch,{id='bad',target=a:original_projectile(),
 field=hd2.fields.damage.player_standard_damage,expect=95,value=80}))
assert(not pcall(writes.validate_patch,{id='bad',target=a:original_projectile(),allow_shared=true,
 field=hd2.fields.attack.projectile,expect=a:projectile(),value=t:projectile()}))
assert(not pcall(writes.validate_patch,{id='bad',target=s,field=hd2.fields.attack.projectile,
 expect=s:original_projectile(),value=a:original_projectile()}))
assert(not pcall(swap,s,hd2.weapon('R-36 Eruptor'):attack('primary'):original_projectile()))
assert(not pcall(damage,hd2.weapon('AR-23 Liberator'):attack('primary'):original_projectile()))
return'ok'
''')

    def test_atomic_plan_repeats_after_partial_reload_and_rolls_back_on_failure(self):
        self.check(r'''
local function combined()
 local complete={changes={},snapshots={{owner=owner,offset=0,bytes=memory}}}
 for _,spec in ipairs({damage_spec,sta_spec,one_spec})do
  for _,c in ipairs(prepare(spec).changes)do complete.changes[#complete.changes+1]=c end
 end
 return complete
end
local baseline=memory;fail_at=4
local failed=guard.apply(runtime,combined())
assert(failed.status=='REJECTED'and failed.rollback=='verified'and memory==baseline and protection==2)
fail_at=nil
assert(guard.apply(runtime,combined()).status=='APPLIED')
assert(guard.apply(runtime,combined()).status=='ALREADY_DESIRED')
-- Only one selector reloads; the original donor handle is still resolvable.
memory=splice(memory,components[sta].offset,b.encode(fields[sta]['attack.primary.projectile'].currentDefault.projectileType,'u32'))
local repair=guard.apply(runtime,combined())
assert(repair.status=='APPLIED'and repair.writes==1)
return'ok'
''')
