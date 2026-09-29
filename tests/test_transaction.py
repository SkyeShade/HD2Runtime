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



# Region guard diagnostics (Proton/Wine support). The guard is unchanged: every refused case below writes nothing and
# changes no protection. The diagnostic names the failed conditions, the observed region and whether the targets
# still hold their expected bytes, as one log line and as the same text in the result (no raw address values).
REGION = r"""
local query=runtime.query
-- Faults start once targets are resolved, so read-only discovery succeeds and only the write guard sees them (the
-- reported Proton case: resolution passed, the guard refused).
local function armed()
    for _,entry in ipairs(logs)do if entry:find('targets resolved',1,true)then return true end end
end
local function refuse_at(page,edit)
    runtime.query=function(at)
        local r=query(at)
        if armed()and at>=page and at<page+4096 and r then
            local copy={};for k,v in pairs(r)do copy[k]=v end
            edit(copy);return copy
        end
        return r
    end
end
local function line(prefix)
    for _,entry in ipairs(logs)do if entry:find(prefix,1,true)then return entry end end
end
"""


class GuardDiagnosticsTests(unittest.TestCase):
    def test_unchanged_region_applies_and_reports_verified(self):
        check(REGION + '''
local w=transaction();assert(w.status=='complete',w.error)
assert(w.result.non_target_check=='verified' and w.result.guard_failure==nil)
assert(line('non_target_bytes_unchanged=true')=='[HD2Runtime] non_target_bytes_unchanged=true')
assert(not line('guard_failure'))
''')

    def test_benign_subdivision_is_accepted(self):
        # A region split into one-page regions of the same allocation (as Wine may report) is not a change.
        check(REGION + '''
runtime.query=function(at)
    local r=query(at)
    if armed()and r and r.state==0x1000 then
        local page=at-at%4096
        return {base=page,size=4096,allocation_base=r.allocation_base,state=r.state,type=r.type,protect=r.protect,
            allocation_protect=4}
    end
    return r
end
local w=transaction();assert(w.status=='complete',w.error)
assert(w.result.status=='APPLIED' and #writes==4);assert_values('new');protection_is(2)
''')

    def test_changed_protection_is_refused_with_diagnostics(self):
        # PAGE_EXECUTE_READWRITE (0x40) where 2/4 was captured: refused, never normalised.
        check(REGION + '''
refuse_at(targets.cooldown.page,function(r)r.protect=0x40;r.allocation_protect=0x40 end)
local w=transaction();assert(w.status=='rejected')
assert(#writes==0 and #protections==0 and w.result.writes==0 and w.result.rollback=='not_needed')
assert(w.result.non_target_bytes_unchanged==false and w.result.non_target_check=='not_reached')
local text=assert(line('guard_failure'),'no guard_failure line')
assert(text=='[HD2Runtime] '..w.result.guard_failure,text)
assert(text:find('failed=protection ',1,true)and text:find('protect=0x40 ',1,true),text)
assert(text:find('allocation_protect=0x40 ',1,true)and text:find('expected_protect=0x2 ',1,true),text)
assert(text:find('expected_bytes=match (4 match, 0 differ, 0 unreadable)',1,true),text)
assert(text:find('module=none',1,true),text)
assert(line('non_target_bytes_unchanged=false non_target_check=not_reached'))
protection_is(2);assert_values('old')
''')

    def test_changed_allocation_base_is_refused(self):
        check(REGION + '''
refuse_at(targets.lifetime.page,function(r)r.allocation_base=r.allocation_base+0x10000 end)
local w=transaction();assert(w.status=='rejected' and #writes==0 and #protections==0)
local text=assert(line('guard_failure'))
assert(text:find('failed=allocation_base ',1,true)and text:find('expected_bytes=match',1,true),text)
''')

    def test_true_allocation_replacement_is_refused_and_bytes_differ(self):
        # A different allocation (base and type) now holds other bytes at the target.
        check(REGION + '''
local swapped=false
refuse_at(targets.cooldown.page,function(r)
    r.allocation_base=r.allocation_base+0x20000;r.type=0x40000
    if not swapped then swapped=true;replace(targets.cooldown.address,string.char(9,9,9,9))end
end)
local w=transaction();assert(w.status=='rejected' and #writes==0 and #protections==0)
local text=assert(line('guard_failure'))
assert(text:find('failed=allocation_base,type ',1,true),text)
assert(text:find('expected_bytes=differ (3 match, 1 differ, 0 unreadable)',1,true),text)
''')

    def test_failed_query_is_refused(self):
        check(REGION + '''
runtime.query=function(at)
    if armed()and at>=targets.radius.page and at<targets.radius.page+4096 then return nil end
    return query(at)
end
local w=transaction();assert(w.status=='rejected' and #writes==0 and #protections==0)
assert(assert(line('guard_failure')):find('failed=query_failed ',1,true))
''')

    def test_protection_restore_failure_is_named(self):
        check(REGION + '''
local native=runtime.protect
runtime.protect=function(page,size,value)
    if page==targets.lifetime.page and value==2 then return nil end
    return native(page,size,value)
end
local w=transaction();assert(w.status=='rejected')
assert(w.result.protection_restored==false)
local text=assert(line('protection_restore_failure page=0x'),table.concat(logs,' | '))
assert(text:find('original=0x2 ',1,true)and text:find('restore failed',1,true),text)
''')

    def test_rejected_result_has_no_raw_address_values(self):
        check(REGION + '''
refuse_at(targets.cooldown.page,function(r)r.protect=0x40 end)
local w=transaction();assert(w.status=='rejected')
local function inspect(t)
    for k,v in pairs(t)do
        assert(k~='address' and k~='base' and k~='pointer',k)
        if type(v)=='table'then inspect(v)end
    end
end
inspect(w.result)
assert(type(w.result.guard_failure)=='string')
''')

if __name__=='__main__':
    unittest.main()
