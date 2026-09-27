import unittest
from support import run, ROOT


class RuntimeTests(unittest.TestCase):
    def test_known_values(self):
        result = run("""
local job=read();assert(job.status=='complete',job.error)
assert(job.result.writes==0 and job.result.protection_changes==0)
for _,target in ipairs(job.result.targets)do for _,f in pairs(target.fields)do
 assert(f.expected_match,'baseline differs')
 assert(not f.evidence.current_live_ownership_proven,'fixture promoted to live evidence')
 assert(not f.evidence.native_consumer_proven)
end end
return hd2.format(job.result)
""").decode()
        self.assertIn('standard_damage = 275', result)
        self.assertIn('cooldown = 90', result)
        self.assertIn('interval = 0.1', result)
        self.assertIn('main_health = 8000', result)
        (ROOT/'build').mkdir(exist_ok=True)
        (ROOT/'build/known-values.txt').write_text(result+'\n')

    def rejected(self, setup, contains, targets='targets'):
        run(setup+"\nlocal job=read("+targets+");assert(job.status=='rejected','accepted invalid fixture');assert(job.error:find("+repr(contains)+",1,true),job.error);return 'ok'")

    def test_wrong_build_before_memory(self):
        run("runtime.module_hash=function()return 'WRONG'end;local j=read();assert(j.status=='rejected');assert(runtime.reads==0);return 'ok'")

    def test_missing_entity(self):
        self.rejected("regions[1].size=regions[1].size+4096", 'entity allocation absent')

    def test_duplicate_entity(self):
        self.rejected("""
table.insert(regions,2,{base=0x3000000,size=p.entity_region_size})
spans[#spans+1]={at=0x3000000,bytes=b.unhex(p.map_header)}
""", 'unique entity')

    def test_changed_membership(self):
        self.rejected("replace(0x100000+28+p.resources.amr.membership_offset,u32(0))", 'membership changed')

    def test_unsafe_membership_pointer(self):
        self.rejected("replace(0x100000+28+p.resources.amr.owner_row*32+8,u64(0x70000000))", 'bounded pointer')

    def test_relocated_membership(self):
        run("""
for _,r in pairs(p.resources)do
 replace(0x100000+28+r.owner_row*32+8,u64(0x100000+28+r.membership_offset))
end
local j=read();assert(j.status=='complete',j.error);return 'ok'
""")

    def test_relocated_settings(self):
        run("""
for key,base in pairs({projectile=0x4000000,damage=0x5000000})do
 for _,g in ipairs(p.settings[key].groups)do if g.root then replace(base+g.root,u64(base+g.root+g.row_offset))end end
end
local j=read();assert(j.status=='complete',j.error);return 'ok'
""")

    def test_shared_record(self):
        self.rejected("""
local c=p.components.WeaponDataComponentData
local row=p.resources.amr.components.WeaponDataComponentData.row
local alias=row==0 and 1 or 0
replace(0x100000+c.offset+28+alias*16,u64(123)..u32(354)..u32(0))
""", 'absent/shared')

    def test_schema_framing(self):
        self.rejected("replace(0x100000+p.components.ShieldComponentData.offset+16,u32(123))", 'framing changed')

    def test_settings_link(self):
        self.rejected("local c=p.components.ProjectileWeaponComponentData;local r=p.resources.jar5.components.ProjectileWeaponComponentData.record;replace(0x100000+c.offset+28+c.record_offset+r*c.stride,u32(178))", 'projectile link changed')

    def test_settings_pointer(self):
        self.rejected("local g=p.settings.damage.groups[2];replace(0x5000000+g.root,u64(999))", 'settings pointer')

    def test_stratagem_runtime_table(self):
        self.rejected("replace(0x10000000+p.stratagem.table_rva+22*8,u64(0))", 'runtime table mismatch')

    def test_stratagem_payload(self):
        self.rejected("replace(0x6000000+cooldown_offset+152,u64(0x6000000))", 'payload list pointer outside/ambiguous')

    def test_unstable_snapshot(self):
        self.rejected("""
local original=runtime.read
local reads=0
runtime.read=function(at,n)
 local s=original(at,n)
 if at==0x100000 and n==65536 then reads=reads+1;if reads==2 then s='X'..s:sub(2)end end
 return s
end
""", 'unstable')

    def test_guard_page(self):
        self.rejected("local q=runtime.query;runtime.query=function(at)local r=q(at);if at>0x100000 and at<0x100000+p.entity_region_size then r.protect=0x102 end;return r end", 'ownership/protection')

    def test_short_read(self):
        self.rejected("local r=runtime.read;runtime.read=function(at,n)return r(at,n):sub(2)end", 'short memory')

    def test_modded_value_reported_without_write(self):
        run("""
local c=p.components.WeaponDataComponentData
replace(0x100000+c.offset+28+c.record_offset+354*c.stride+400,u32(4))
local j=read({{resource='amr',fields={'crosshair_type'}}})
assert(j.status=='complete',j.error)
local f=j.result.targets[1].fields.crosshair_type
assert(f.value==4 and not f.expected_match)
return 'ok'
""")

    def test_write_apis_inert(self):
        run("for _,name in ipairs({'patch','ensure','transaction','plan'})do local value,err=hd2[name]{};assert(not value and err.code=='READ_ONLY_MILESTONE')end;assert(runtime.reads==0);return 'ok'")

    def test_observe_interval_and_cancel(self):
        run("""
local count=0
local watch=hd2.observe{targets={{resource='amr',fields={'crosshair_type'}}},on_result=function()count=count+1 end}
watch.tick(1);assert(runtime.reads==0)
watch.tick(1)
for i=1,1000 do watch.tick(0);if count==1 then break end end
assert(count==1)
local n=runtime.reads;watch.tick(59);assert(runtime.reads==n)
watch.tick(1)
for i=1,1000 do watch.tick(0);if count==2 then break end end
assert(count==2)
watch.cancel();n=runtime.reads;watch.tick(60);assert(runtime.reads==n)
return 'ok'
""")

    def test_failure_latches_observer(self):
        run("""
runtime.module_hash=function()return 'wrong'end
local count=0
local w=hd2.observe{targets=targets,on_error=function()count=count+1 end}
w.tick(2);w.tick(60);assert(w.status=='rejected' and count==1);return 'ok'
""")

    def test_missing_target_retries_then_resolves(self):
        run("""
local original=runtime.module
runtime.module=function()return nil end
local results=0
local w=hd2.observe{targets={{resource='amr',fields={'crosshair_type'}}},on_result=function()results=results+1 end}
w.tick(2);assert(w.status=='waiting' and runtime.reads==0)
runtime.module=original
w.tick(4);assert(runtime.reads==0)
w.tick(1)
for _=1,1000 do w.tick(0);if results==1 then break end end
assert(results==1);return 'ok'
""")

    def test_missing_target_retry_limit(self):
        run("""
runtime.module=function()return nil end
local errors=0
local w=hd2.observe{targets=targets,on_error=function()errors=errors+1 end}
w.tick(2)
for _=1,5 do w.tick(5)end
assert(w.status=='rejected' and errors==1 and runtime.reads==0)
w.tick(60);assert(errors==1);return 'ok'
""")

    def test_public_identity_no_addresses(self):
        run("""
local j=read();assert(j.status=='complete',j.error)
local function inspect(t)for k,v in pairs(t)do assert(k~='address' and k~='base' and k~='pointer');if type(v)=='table'then inspect(v)end end end
inspect(j.result);return 'ok'
""")


if __name__ == '__main__':
    unittest.main()
