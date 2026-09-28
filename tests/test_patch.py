import json
import re
import unittest
from support import ROOT, run, lua, modules, execute
import build


def check(body):
    return run((ROOT/'tests/write_memory.lua').read_text()+'\n'+body+"\nreturn 'ok'")


class PatchTests(unittest.TestCase):
    def test_success_exact_width_non_target_and_restore(self):
        check(r'''
local before=runtime.read(damage_base,p.settings.damage.size)
local w=patch();assert(w.status=='complete',w.error)
assert(w.result.status=='APPLIED' and w.result.writes==1 and w.result.bytes_written==12)
assert(#writes==1 and writes[1].bytes==desired)
assert(#protections==2 and protections[1].value==4 and protections[2].value==2)
assert(page_protection==2 and w.result.protection_restored and w.result.non_target_bytes_unchanged)
assert(runtime.read(damage_base,#before)==before:sub(1,damage_offset)..desired..before:sub(damage_offset+13))
assert(table.concat(logs,'\n'):find('patch jar5-ap4 APPLIED',1,true))
''')

    def test_already_desired_no_write_or_protection(self):
        check('''
replace(target_address,desired)
local w=patch();assert(w.status=='complete',w.error)
assert(w.result.status=='ALREADY_DESIRED' and #writes==0 and #protections==0)
''')

    def test_third_party_or_mixed_lanes_conflict(self):
        for value in ('u32(5)..old:sub(5)', 'desired:sub(1,4)..old:sub(5)'):
            check(f'''
replace(target_address,{value})
local w=patch();assert(w.status=='rejected' and w.result.code=='CONFLICT',w.error)
assert(#writes==0 and #protections==0)
''')

    def test_stale_read_result_and_declaration_not_used(self):
        check('''
local prior=read({{resource='jar5',fields={'armor_penetration'}}});assert(prior.status=='complete')
local w=hd2.patch(request())
local next_base=0x5100000
for _,s in ipairs(spans)do if s.at==damage_base then s.at=next_base end end
regions[3].base=next_base
runtime.write=function(at,bytes)
    assert(at==next_base+damage_offset,'stale address reused')
    writes[#writes+1]={address=at,bytes=bytes};replace(at,bytes);return true,nil,#bytes
end
target_page=next_base+damage_offset-(next_base+damage_offset)%4096
damage_base=next_base;target_address=next_base+damage_offset
for _=1,1000 do w.tick(0.1);if w.status=='complete' or w.status=='rejected' then break end end
assert(w.status=='complete',w.error);assert(#writes==1)
''')

    def test_ownership_change_after_resolution_before_write(self):
        check('''
local protect=runtime.protect
runtime.protect=function(at,n,value)
    local result=protect(at,n,value)
    if value==4 then replace(0x100000+28+p.resources.jar5.membership_offset,u32(0))end
    return result
end
local w=patch();assert(w.status=='rejected',w.error)
assert(#writes==0 and page_protection==2 and w.result.protection_restored)
''')

    def test_expected_changes_at_final_guard(self):
        check('''
local protect=runtime.protect
runtime.protect=function(at,n,value)
    local result=protect(at,n,value)
    if value==4 then replace(target_address,string.rep(u32(5),3))end
    return result
end
local w=patch();assert(w.status=='rejected')
assert(#writes==0 and page_protection==2)
assert(runtime.read(target_address,12)==string.rep(u32(5),3))
''')

    def test_partial_write_failure_rolls_back_known_prefix(self):
        for n in (0,1,4,7,11):
            check(f'''
local write=runtime.write
local calls=0
runtime.write=function(at,bytes)
    calls=calls+1
    if calls==1 then replace(at,bytes:sub(1,{n}));return false,'injected short write',{n} end
    return write(at,bytes)
end
local w=patch();assert(w.status=='rejected',w.error)
assert(w.result.rollback=='verified',w.result.rollback_error)
assert(runtime.read(target_address,12)==old and page_protection==2 and w.result.protection_restored)
''')

    def test_post_write_reread_mismatch_unknown_value_never_overwritten(self):
        check('''
local write=runtime.write
runtime.write=function(at,bytes)
    write(at,bytes);replace(at,u32(9));return true,nil,12
end
local w=patch();assert(w.status=='rejected' and w.result.rollback=='refused_or_failed')
assert(#writes==1 and runtime.read(target_address,4)==u32(9) and page_protection==2)
''')

    def test_non_target_mutation_detected(self):
        check('''
local write=runtime.write
runtime.write=function(at,bytes)
    write(at,bytes);replace(at+12,u32(1));return true,nil,12
end
local w=patch();assert(w.status=='rejected' and not w.result.non_target_bytes_unchanged)
assert(w.result.rollback=='refused_or_failed' and #writes==1 and page_protection==2)
assert(runtime.read(target_address+12,4)==u32(1))
''')

    def test_restore_failure_is_terminal_and_reported(self):
        check('''
local protect=runtime.protect
runtime.protect=function(at,n,value)
    if value==2 then return nil,'injected restore failure' end
    return protect(at,n,value)
end
local w=patch();assert(w.status=='rejected' and not w.result.protection_restored)
assert(w.result.rollback=='verified' and runtime.read(target_address,12)==old)
local n=#writes;w.tick(60);assert(#writes==n)
''')

    def test_restore_retry_succeeds(self):
        check('''
local protect=runtime.protect
local failed=false
runtime.protect=function(at,n,value)
    if value==2 and not failed then failed=true;return nil,'transient' end
    return protect(at,n,value)
end
local w=patch();assert(w.status=='complete',w.error)
assert(failed and w.result.protection_restored and page_protection==2)
''')

    def test_already_writable_page_no_protection_changes(self):
        check('''
all_writable=true;page_protection=4
local w=patch();assert(w.status=='complete',w.error)
assert(#protections==0 and page_protection==4 and w.result.protection_restored)
''')

    def test_wrong_build_and_unsupported_fields_never_write(self):
        check('''
runtime.module_hash=function()return 'wrong'end
local w=patch();assert(w.status=='rejected' and #writes==0 and #protections==0 and runtime.reads==0)
local r=request();r.field='standard_damage';assert(not pcall(hd2.patch,r))
r=request();r.target.address=123;assert(not pcall(hd2.patch,r))
''')

    def test_application_fingerprint_rechecked(self):
        check('''
local hash=runtime.module_hash;local calls=0
runtime.module_hash=function(name)calls=calls+1;return hash(name)end
-- A verified build is hashed once per loaded-module identity, not per operation.
local w=patch();assert(w.status=='complete',w.error);assert(calls==2,'hashed '..calls)
replace(target_address,old);w=patch();assert(w.status=='complete');assert(calls==2,'rehashed '..calls)
-- A different loaded module at application time is re-hashed and still rejected.
replace(target_address,old)
local module=runtime.module;local swapped=false
runtime.module=function(name)
    if swapped and name=='game.dll'then return 'reloaded.dll'end
    return module(name)
end
runtime.module_hash=function(name)calls=calls+1
    if name=='reloaded.dll'then return 'changed'end;return hash(name)end
local n=#writes
local fingerprint=require('hd2runtime/core/fingerprint')
local matches=fingerprint.matches
fingerprint.matches=function(r)
    local result=matches(r);swapped=true;return result
end
w=patch();assert(w.status=='rejected' and #writes==n,'status='..w.status)
assert(w.error:find('application fingerprint mismatch',1,true),w.error)
''')

    def test_cancellation_and_request_copy(self):
        check('''
local r=request();local w=hd2.patch(r);r.value=9;r.target.resource='amr'
for _=1,1000 do w.tick(0.1);if w.status=='complete' or w.status=='rejected' then break end end
assert(w.status=='complete',w.error);assert(runtime.read(target_address,12)==desired)
local other=hd2.patch(request());other.cancel();local n=runtime.reads
other.tick(60);assert(runtime.reads==n and other.status=='cancelled')
''')

    def test_proof_uses_only_declarative_public_api(self):
        body=(ROOT/'proof/jar5.lua').read_text()
        for forbidden in ('Virtual','ffi','runtime.read','scan','offset','lanes'):
            self.assertNotIn(forbidden,body)

    def test_write_modules_excluded_from_read_only_artifacts(self):
        import build_live_validation
        for sources in (build.resources(),build_live_validation.resources()):
            for name in ('runtime/windows_write','core/guarded_write','core/guarded_transaction',
                         'domains/patches','domains/transactions','domains/composition_plans',
                         'api/patch','api/transaction','api/plan','api/ensure'):
                self.assertNotIn('hd2runtime/'+name,sources)

    def test_proof_runs_from_packaged_sources_and_detaches(self):
        import build_gameplay_proof
        sources=build_gameplay_proof.resources()
        check('local bodies='+lua(sources)+'''
for name,body in pairs(bodies)do
    assert(loadstring(body,name))
    package.preload[name]=function()return assert(loadstring(body,name))()end
    package.loaded[name]=nil
end
package.preload['hd2runtime/runtime/windows_write']=function()return {create=function()return runtime end}end
package.preload['hd2runtime/runtime/log']=function()return {emit=function(line)logs[#logs+1]=line end}end
local job=require('mods/skyeshade/hd2runtime_jar5_ap4')
assert(job.status=='waiting' and #writes==0)
for _=1,1000 do if not update then break end;update(0.1)end
assert(job.status=='complete',job.error)
assert(update==nil and #writes==1 and page_protection==2)
local again=assert(loadstring(bodies['mods/skyeshade/hd2runtime_jar5_ap4']))()
assert(again==job and update==nil and #writes==1)
''')

    def test_native_writer_on_test_owned_allocation(self):
        execute((modules()+'''
local ffi=require('ffi')
ffi.cdef [[void *VirtualAlloc(void *,size_t,uint32_t,uint32_t); int VirtualFree(void *,size_t,uint32_t);]]
local kernel=ffi.load('kernel32')
local memory=kernel.VirtualAlloc(nil,4096,0x3000,4)
assert(memory~=nil,'test allocation failed')
local ok,why=pcall(function()
    local r=require('hd2runtime/runtime/windows_write').create()
    local address=r.address(memory)
    local data=string.rep(string.char(3,0,0,0),3)
    local wrote,reason,n=r.write(address,data)
    assert(wrote and n==12,reason)
    assert(r.read(address,12)==data)
    assert(r.protect(address,4096,2)==4 and r.query(address).protect==2)
    assert(r.protect(address,4096,4)==2 and r.query(address).protect==4)
    local four=string.char(0,0,0,65)
    assert(r.write(address,four) and r.read(address,4)==four)
    -- 8-byte typed references (vehicle mount slots) are 4-byte aligned in native records.
    local reference=string.char(0xFD,0x88,0x5F,0x1A,0xB3,0xEE,0x72,0x98)
    assert(r.write(address+4,reference) and r.read(address+4,8)==reference)
    assert(not pcall(r.write,address+2,reference))
    assert(not pcall(r.write,address,string.rep('x',16)))
    assert(not pcall(r.protect,address,8192,4))
end)
assert(kernel.VirtualFree(memory,0,0x8000)~=0)
assert(ok,why)
return 'ok'
''').encode())

    def test_page_open_failure_no_write_and_restore_verified(self):
        check('''
runtime.protect=function()return nil,'injected open failure'end
local w=patch();assert(w.status=='rejected' and #writes==0)
assert(page_protection==2 and w.result.protection_restored)
''')

    def test_allocation_owner_changes_fail_closed(self):
        check('''
local protect=runtime.protect
local query=runtime.query
local changed=false
runtime.protect=function(at,n,value)
    local result=protect(at,n,value);changed=value==4;return result
end
runtime.query=function(at)
    local r=query(at)
    if changed and r.allocation_base==0x100000 then r.allocation_base=0 end
    return r
end
local w=patch();assert(w.status=='rejected' and #writes==0 and page_protection==2)
''')

    def test_baseline_record_change_fails_before_protection(self):
        check('''
replace(target_address-8,u32(999))
local w=patch();assert(w.status=='rejected' and #writes==0 and #protections==0)
assert(w.error:find('non-target damage record',1,true))
''')

    def test_thrown_write_still_restores_protection(self):
        check('''
runtime.write=function()error('injected adapter failure')end
local w=patch();assert(w.status=='rejected' and page_protection==2)
assert(w.result.protection_restored and w.result.rollback=='refused_or_failed')
''')

    def test_pinned_write_records_match_existing_reference(self):
        source=(ROOT/'domains/patches.lua').read_text()
        reference=json.loads((ROOT/'tests/fixtures/reference.json').read_text())
        for key,offset,size in (('projectile',28+16+262*272,272),('damage',84+16+158*76,76)):
            embedded=re.search(r"local "+key+r"=b.unhex\('([0-9a-f]+)'\)",source).group(1)
            raw=bytes.fromhex(reference['buffers'][key])
            self.assertEqual(bytes.fromhex(embedded),raw[offset:offset+size])

    def test_diagnostic_logging_and_no_public_addresses(self):
        check('''
local r=request();r.diagnostic=true
local w=hd2.patch(r)
for _=1,1000 do w.tick(0.1);if w.status=='complete' or w.status=='rejected' then break end end
assert(w.status=='complete',w.error)
local text=table.concat(logs,' ')
assert(text:find('component=DamageSettings',1,true) and text:find('fixture_fallback=disabled',1,true))
local function inspect(t)
    for k,v in pairs(t)do
        assert(k~='address' and k~='base' and k~='pointer')
        if type(v)=='table' then inspect(v)end
    end
end
inspect(w.result)
''')

    def test_false_success_protection_restore_is_detected(self):
        check('''
local protect=runtime.protect
runtime.protect=function(at,n,value)
    if value==2 then return 4 end -- Claims success but leaves the page writable.
    return protect(at,n,value)
end
local w=patch();assert(w.status=='rejected' and not w.result.protection_restored)
assert(page_protection==4 and w.result.rollback=='verified')
''')

    def test_failed_rollback_still_restores_protection(self):
        check('''
local calls=0
runtime.write=function(at,bytes)
    calls=calls+1
    if calls==1 then replace(at,bytes:sub(1,4));return false,'partial',4 end
    return false,'rollback failed',0
end
local w=patch();assert(w.status=='rejected' and w.result.rollback=='refused_or_failed')
assert(page_protection==2 and w.result.protection_restored)
''')

    def test_target_reallocation_refuses_write_and_protection_of_new_owner(self):
        check('''
local protect=runtime.protect
local query=runtime.query
local changed=false
runtime.protect=function(at,n,value)
    local result=protect(at,n,value);changed=true;return result
end
runtime.query=function(at)
    local r=query(at)
    if changed and r.allocation_base==damage_base then r.allocation_base=damage_base-4096 end
    return r
end
local w=patch();assert(w.status=='rejected' and #writes==0 and #protections==1)
assert(not w.result.protection_restored)
''')

    def test_protection_changed_during_immediate_reread_rejects_write(self):
        check('''
local read=runtime.read
runtime.read=function(at,n)
    local bytes=read(at,n)
    if at==target_address and n==12 and page_protection==4 then page_protection=2 end
    return bytes
end
local w=patch();assert(w.status=='rejected' and #writes==0)
assert(page_protection==2 and w.result.protection_restored)
''')

    def test_page_open_race_preserves_actual_prior_protection(self):
        check('''
local protect=runtime.protect
runtime.protect=function(at,n,value)
    page_protection=4 -- Another actor changed it since the guard query.
    return protect(at,n,value)
end
local w=patch();assert(w.status=='rejected' and #writes==0)
assert(page_protection==4 and #protections==1 and w.result.protection_restored)
''')

    def test_ensure_wraps_patch_and_fails_closed_on_conflict(self):
        check('''
local e=hd2.ensure{patch=request(),interval=1,startup_delay=0}
for _=1,3000 do e.tick(0);if e.runs==1 then break end end
assert(e.runs==1 and runtime.read(target_address,12)==desired)
replace(target_address,old);e.tick(1)
for _=1,3000 do e.tick(0);if e.runs==2 then break end end
assert(e.runs==2 and runtime.read(target_address,12)==desired)
replace(target_address,string.rep(u32(5),3));e.tick(1)
for _=1,3000 do e.tick(0);if e.status=='rejected' then break end end
assert(e.status=='rejected' and e.result.code=='CONFLICT')
assert(runtime.read(target_address,12)==string.rep(u32(5),3))
''')


if __name__=='__main__':
    unittest.main()
