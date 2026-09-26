import re
import struct
import unittest

from support import ROOT, run, lua, execute
import build_live_validation as live_build
from hd2_archive import make_archive, lua_resource, resource_hash


def packaged(setup='', checks="return 'ok'"):
    return run('local bodies='+lua(live_build.resources('fixture-test-commit'))+'\n'+"""
local logs={}
CowboyBingusModLoader={open_log=function()
 return {write=function(_,line)logs[#logs+1]=line end,flush=function()end}
end}
print=function()end
for name,body in pairs(bodies)do
 package.preload[name]=function()return assert(loadstring(body,name))()end
 package.loaded[name]=nil
end
package.preload['hd2runtime/runtime/windows_readonly']=function()return function()return runtime end end
"""+setup+"""
local state=require('mods/skyeshade/hd2runtime_live_validation')
assert(runtime.reads==0,'read before startup delay')
for _=1,10000 do
 if state.status~='running' then break end
 assert(update,'validation detached before completion')
 update(0.1)
end
local output=table.concat(logs)
"""+checks)


class LiveValidationTests(unittest.TestCase):
    def test_all_regression_expectations_against_actual_fixture_bytes(self):
        output=run("""
local expectations=require('hd2runtime/validation/expectations')
local report=require('hd2runtime/validation/report')
local lines={}
local field_count=0
for _,spec in ipairs(expectations)do
 local fields={};for _,field in ipairs(spec.fields)do fields[#fields+1]=field.name;field_count=field_count+1 end
 local job=read({{resource=spec.resource,fields=fields}})
 assert(job.status=='complete',job.error)
 local status,text,live=report.evaluate(spec,job.result)
 assert(status=='NOT_LIVE' and not live,text)
 assert(not text:find('status=MISMATCH',1,true),text)
 assert(not text:find('ownership=MISMATCH',1,true),text)
 lines[#lines+1]=text
end
assert(field_count==62,field_count)
return table.concat(lines,'\\n')
""").decode()
        (ROOT/'build').mkdir(exist_ok=True)
        (ROOT/'build/live-validation-fixture-output.txt').write_text(output+'\n')
        self.assertIn('record_kind=513',output)
        self.assertIn('record_index=504',output)
        self.assertIn('field=movement_scalar_04 observed=20',output)
        self.assertIn('field=movement_scalar_24 observed=60',output)
        self.assertIn('field=zones.37.armor observed=0',output)
        self.assertIn('component=WeaponDataComponentData type=0x88E4DBB1',output)

    def test_package_runs_all_six_and_rejects_fixture_promotion(self):
        packaged(checks="""
assert(state.status=='complete' and state.completed==6)
assert(state.live_resolved==0 and state.passed==0 and update==nil)
for _,r in pairs(state.reports)do assert(r.status=='NOT_LIVE')end
assert(output:find('LIVE_VALIDATION_SUMMARY completed=6/6 live_resolved=0 passed=0',1,true))
assert(not output:find('status=LIVE_PASS',1,true))
local again=assert(loadstring(bodies['mods/skyeshade/hd2runtime_live_validation']))()
assert(again==state and update==nil)
return 'ok'
""")

    def test_package_continues_after_one_resolver_fails(self):
        packaged("replace(0x100000+p.components.WeaponDataComponentData.offset+16,u32(1))", """
assert(state.status=='complete' and state.completed==6 and update==nil)
assert(state.errors.amr and state.errors.amr.adapter=='core/entity:WeaponDataComponentData')
assert(state.reports.jar5 and state.reports.bastion and state.reports.orbital_laser
 and state.reports.shield_relay and state.reports.jump_pack)
assert(output:find('adapter=core/entity:WeaponDataComponentData',1,true))
assert(not state.reports.amr)
return 'ok'
""")

    def test_package_names_stratagem_adapter_failure(self):
        packaged("replace(0x10000000+p.stratagem.table_rva+22*8,u64(0))", """
assert(state.status=='complete' and state.completed==6)
assert(state.errors.shield_relay.adapter=='core/stratagem:grouped_records')
assert(state.reports.jump_pack)
assert(output:find('observed=unavailable',1,true))
return 'ok'
""")

    def test_changed_value_logged_without_replacing_it(self):
        packaged("""
local c=p.components.WeaponDataComponentData
replace(0x100000+c.offset+28+c.record_offset+354*c.stride+400,u32(4))
""", """
assert(state.status=='complete')
assert(state.reports.amr.result.targets[1].fields.crosshair_type.value==4)
assert(output:find('field=crosshair_type observed=4 expected=3 status=MISMATCH',1,true))
return 'ok'
""")

    def test_synthetic_live_metadata_branch_and_ownership_mismatch(self):
        run("""
local spec=require('hd2runtime/validation/expectations')[2]
local report=require('hd2runtime/validation/report')
local job=read({{resource='amr',fields={'crosshair_type'}}})
assert(job.status=='complete',job.error)
-- Synthetic metadata to exercise the renderer. This is not a live capture.
job.result.mode='live'
local f=job.result.targets[1].fields.crosshair_type
f.evidence.current_live_ownership_proven=true
local status,_,live=report.evaluate(spec,job.result)
assert(status=='LIVE_PASS' and live)
f.value=4
status,_,live=report.evaluate(spec,job.result)
assert(status=='VALUE_MISMATCH' and live)
f.identity.record_index=355
status,_,live=report.evaluate(spec,job.result)
assert(status=='OWNERSHIP_MISMATCH' and not live)
return 'ok'
""")

    def test_missing_field_never_falls_back_to_expectation(self):
        run("""
local spec=require('hd2runtime/validation/expectations')[2]
local job=read({{resource='amr',fields={'crosshair_type'}}})
job.result.targets[1].fields.crosshair_type=nil
local status,text=require('hd2runtime/validation/report').evaluate(spec,job.result)
assert(status=='OWNERSHIP_MISMATCH')
assert(text:find('observed=unavailable expected=3',1,true))
assert(not text:find('observed=3',1,true))
return 'ok'
""")

    def test_public_client_has_no_private_api_dependency(self):
        for name in ('validation/addon.lua','validation/report.lua'):
            source=(ROOT/name).read_text()
            imports=re.findall(r"require\('([^']+)'\)",source)
            self.assertTrue(all(i=='mods/skyeshade/hd2runtime' or i.startswith('hd2runtime/validation/') for i in imports))
            calls=set(re.findall(r'hd2\.(\w+)\(',source))
            self.assertTrue(calls.issubset({'describe','read','observe'}))
            for token in ('VirtualQuery','VirtualProtect','ffi.','runtime.read','schemas/current','tests/fixtures'):
                self.assertNotIn(token,source)

    def test_archive_contains_native_adapter_but_no_fixture_or_old_entry(self):
        sources=live_build.resources('abc123')
        self.assertIn('hd2runtime/runtime/windows_readonly',sources)
        self.assertNotIn('mods/skyeshade/hd2runtime_report',sources)
        self.assertTrue(all('fixtures' not in n and 'examples' not in n for n in sources))
        archive=make_archive({resource_hash(n):lua_resource(b) for n,b in sources.items()})
        count=struct.unpack_from('<I',archive,8)[0]
        bodies={}
        for i in range(count):
            row=struct.unpack_from('<7Q6I',archive,104+80*i)
            size,version=struct.unpack_from('<II',archive,row[2])
            self.assertEqual(version,2)
            bodies[row[0]]=archive[row[2]+8:row[2]+8+size]
        self.assertEqual(bodies,{resource_hash(n):b for n,b in sources.items()})
        execute(('local sources='+lua(sources)+"\nfor n,b in pairs(sources)do assert(loadstring(b,n))end;return 'ok'").encode())
        entries=[n for n,b in sources.items() if b.startswith(b'-- HD2-Addon:')]
        self.assertEqual(set(entries),{'mods/skyeshade/hd2runtime',live_build.ENTRY})

    def test_memory_discovery_step_and_total_budgets(self):
        run("""
local original=runtime.query
local per_tick=0
runtime.query=function(at)per_tick=per_tick+1;return original(at)end
local job=hd2.read{targets=targets}
for _=1,10000 do
 per_tick=0
 local done=job.step()
 assert(per_tick<=64,'nonincremental discovery: '..per_tick)
 if done then break end
end
assert(job.status=='complete',job.error)
assert(job.result.diagnostics.queries<=100000 and job.result.diagnostics.bytes<=16*1024*1024)
return 'ok'
""")

    def test_observation_time_budget(self):
        run("""
local errors=0
local w=hd2.observe{targets=targets,timeout=0.5,on_error=function(reason,detail)
 assert(detail.code=='TIMEOUT');errors=errors+1 end}
w.tick(3);assert(w.status=='rejected' and errors==1 and runtime.reads==0)
return 'ok'
""")


if __name__=='__main__':
    unittest.main()
