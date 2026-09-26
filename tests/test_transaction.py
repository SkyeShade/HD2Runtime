import unittest

from support import ROOT, run, lua


def check(body):
    return run((ROOT/'tests/transaction_memory.lua').read_text()+'\n'+body+"\nreturn 'ok'")


class TransactionTests(unittest.TestCase):
    def test_four_field_transaction_is_all_or_nothing(self):
        check(r'''
local w=transaction();assert(w.status=='complete',w.error)
assert(w.result.status=='APPLIED' and w.result.writes==4 and w.result.bytes_written==16)
assert(w.result.non_target_bytes_unchanged and w.result.protection_restored)
assert_values('new');protection_is(2)
assert(targets.radius.page==targets.durability.page)
local unique={};for _,t in pairs(targets)do unique[t.page]=true end
local count=0;for _ in pairs(unique)do count=count+1 end
assert(count==3 and #protections==6)
local text=table.concat(logs,'\n')
assert(text:find('transaction shield-relay-proof targets resolved',1,true))
assert(text:find('radius 15 -> 8',1,true))
assert(text:find('transaction shield-relay-proof APPLIED',1,true))
''')

    def test_partial_descriptor_validation_fails_before_memory(self):
        check('''
local r=transaction_request();r.changes[3].value=91
assert(not pcall(hd2.transaction,r))
assert(runtime.reads==0 and #writes==0 and #protections==0)
''')

    def test_runtime_validation_conflict_blocks_every_write(self):
        for field in ('radius','durability','lifetime','cooldown'):
            check(f'''
replace(targets.{field}.address,string.char(1,2,3,4))
local w=transaction();assert(w.status=='rejected' and w.result.code=='CONFLICT',w.error)
assert(#writes==0 and #protections==0)
''')

    def test_partial_write_failure_rolls_back_prior_fields(self):
        for failed_at,prefix in ((2,0),(3,2),(4,3)):
            check(f'''
local native=runtime.write;local calls=0
runtime.write=function(address,bytes)
    calls=calls+1
    if calls=={failed_at} then
        replace(address,bytes:sub(1,{prefix}));return false,'injected partial write',{prefix}
    end
    return native(address,bytes)
end
local w=transaction();assert(w.status=='rejected',w.error)
assert(w.result.rollback=='verified',w.result.rollback_error)
assert(w.result.protection_restored);assert_values('old');protection_is(2)
''')

    def test_rollback_failure_is_reported_and_all_pages_restored(self):
        check('''
local native=runtime.write;local calls=0
runtime.write=function(address,bytes)
    calls=calls+1
    if calls==3 then replace(address,bytes:sub(1,2));return false,'partial',2 end
    if calls>3 then return false,'rollback failed',0 end
    return native(address,bytes)
end
local w=transaction();assert(w.status=='rejected')
assert(w.result.rollback=='refused_or_failed' and w.result.protection_restored)
protection_is(2)
''')

    def test_same_page_fields_open_and_restore_once(self):
        check('''
local r=transaction_request();r.changes={r.changes[1],r.changes[2]}
local w=transaction(r);assert(w.status=='complete',w.error)
assert(#writes==2 and #protections==2)
assert(protections[1].page==targets.radius.page and protections[2].page==targets.radius.page)
assert(runtime.read(targets.radius.address,4)==targets.radius.new)
assert(runtime.read(targets.durability.address,4)==targets.durability.new)
''')

    def test_separate_pages_each_restore(self):
        check('''
local r=transaction_request();r.changes={r.changes[1],r.changes[3],r.changes[4]}
local w=transaction(r);assert(w.status=='complete',w.error)
assert(#writes==3 and #protections==6);protection_is(2)
local opened={};for _,p in ipairs(protections)do opened[p.page]=(opened[p.page]or 0)+1 end
assert(opened[targets.radius.page]==2 and opened[targets.lifetime.page]==2
    and opened[targets.cooldown.page]==2)
''')

    def test_later_page_open_failure_restores_every_opened_page_before_any_write(self):
        check('''
local native=runtime.protect
runtime.protect=function(page,size,value)
    if page==targets.lifetime.page and value==4 then return nil end
    return native(page,size,value)
end
local w=transaction();assert(w.status=='rejected')
assert(#writes==0 and w.result.rollback=='not_needed' and w.result.protection_restored)
protection_is(2)
assert(protections[1].page==targets.radius.page and protections[1].value==4)
assert(protections[#protections].page==targets.radius.page and protections[#protections].value==2)
''')

    def test_transient_restore_failure_is_retried_and_all_pages_are_verified(self):
        check('''
local native=runtime.protect;local failed=false
runtime.protect=function(page,size,value)
    if page==targets.lifetime.page and value==2 and not failed then
        failed=true;return nil
    end
    return native(page,size,value)
end
local w=transaction();assert(w.status=='complete',w.error)
assert(failed and w.result.protection_restored and w.result.status=='APPLIED')
assert_values('new');protection_is(2)
''')

    def test_all_already_desired_is_zero_write_noop(self):
        check('''
for _,target in pairs(targets)do replace(target.address,target.new)end
local w=transaction();assert(w.status=='complete',w.error)
assert(w.result.status=='ALREADY_DESIRED' and #writes==0 and #protections==0)
assert(w.result.non_target_bytes_unchanged and w.result.protection_restored)
''')

    def test_mixed_desired_expected_is_deterministic(self):
        check('''
replace(targets.radius.address,targets.radius.new)
replace(targets.cooldown.address,targets.cooldown.new)
local w=transaction();assert(w.status=='complete',w.error)
assert(#writes==2 and writes[1].field=='durability' and writes[2].field=='lifetime')
assert(w.result.fields[1].state=='ALREADY_DESIRED' and w.result.fields[2].state=='APPLIED')
assert(w.result.fields[3].state=='APPLIED' and w.result.fields[4].state=='ALREADY_DESIRED')
assert_values('new');protection_is(2)
''')

    def test_non_target_change_during_commit_fails_closed(self):
        check('''
local protect=runtime.protect;local changed=false
runtime.protect=function(page,size,value)
    local prior=protect(page,size,value)
    if value==4 and not changed then changed=true;replace(targets.cooldown.address+4,string.char(1,0,0,0))end
    return prior
end
local w=transaction();assert(w.status=='rejected')
assert(#writes==0 and w.result.rollback=='not_needed' and w.result.protection_restored)
protection_is(2)
''')

    def test_no_public_address_in_result(self):
        check('''
local w=transaction();assert(w.status=='complete',w.error)
local function inspect(t)
    for k,v in pairs(t)do
        assert(k~='address' and k~='base' and k~='pointer')
        if type(v)=='table'then inspect(v)end
    end
end
inspect(w.result)
''')

    def test_ensure_transaction_default_interval_and_reapply(self):
        check('''
local e=hd2.ensure{transaction=transaction_request(),startup_delay=0}
assert(e.interval==60 and e.kind=='transaction','metadata')
for _=1,3000 do e.tick(0);if e.runs==1 then break end end
assert(e.runs==1 and e.status=='waiting','first '..tostring(e.error));assert_values('new')
local n=#writes;replace(targets.lifetime.address,targets.lifetime.old)
e.tick(59);assert(#writes==n and e.runs==1,'early')
e.tick(1)
for _=1,3000 do e.tick(0);if e.runs==2 then break end end
assert(e.runs==2 and #writes==n+1 and writes[#writes].field=='lifetime',
    'second runs='..e.runs..' writes='..#writes..' status='..e.status..' error='..tostring(e.error))
assert_values('new');protection_is(2)
e.cancel();local reads=runtime.reads;e.tick(60);assert(runtime.reads==reads,'cancel')
''')

    def test_ensure_transaction_noop_then_conflict_is_terminal(self):
        check('''
for _,target in pairs(targets)do replace(target.address,target.new)end
local e=hd2.ensure{transaction=transaction_request(),interval=1,startup_delay=0}
for _=1,3000 do e.tick(0);if e.runs==1 then break end end
assert(e.runs==1 and #writes==0 and #protections==0)
replace(targets.radius.address,string.char(1,2,3,4));e.tick(1)
for _=1,3000 do e.tick(0);if e.status=='rejected' then break end end
assert(e.status=='rejected' and e.result.code=='CONFLICT')
assert(#writes==0 and runtime.read(targets.radius.address,4)==string.char(1,2,3,4))
local reads=runtime.reads;e.tick(60);assert(runtime.reads==reads)
''')

    def test_ensure_requires_exactly_one_operation(self):
        check('''
assert(not pcall(hd2.ensure,{}))
assert(not pcall(hd2.ensure,{patch={},transaction={}}))
assert(runtime.reads==0 and #writes==0 and #protections==0)
''')

    def test_proof_entrypoint_is_declarative(self):
        body=(ROOT/'proof/addon.lua').read_text()
        for forbidden in ('update','Virtual','ffi','runtime.','memory','protect','timer','offset'):
            self.assertNotIn(forbidden,body)
        self.assertIn('hd2.ensure',body)
        self.assertIn("hd2.stratagem('Shield Relay')",body)

    def test_packaged_proof_runs_and_scheduler_detaches_on_cancel(self):
        import build_transaction_proof
        sources=build_transaction_proof.resources()
        check('local bodies='+lua(sources)+r'''
for name,body in pairs(bodies)do
    assert(loadstring(body,name))
    package.preload[name]=function()return assert(loadstring(body,name))()end
    package.loaded[name]=nil
end
package.preload['hd2runtime/runtime/windows_write']=function()return {create=function()return runtime end}end
package.preload['hd2runtime/runtime/log']=function()return {emit=function(line)logs[#logs+1]=line end}end
local state=require('mods/skyeshade/hd2runtime_shield_relay')
for _=1,3000 do update(0.1);if state.runs==1 then break end end
assert(state.runs==1 and state.status=='waiting');assert_values('new')
assert(update~=nil);state.cancel();update(0);assert(update==nil)
local again=assert(loadstring(bodies['mods/skyeshade/hd2runtime_shield_relay']))()
assert(again==state and update==nil and #writes==4)
''')


if __name__=='__main__':
    unittest.main()
