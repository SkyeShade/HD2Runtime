"""Guarded read budget (core/guarded_transaction.lua) after the HMG user report (tests/fixtures/user-reports/hmg-read-budget).

The budget is derived from the plan's shape under a hard ceiling. Contexts captured more than once are checked once,
and every write is still preceded and followed by a full check with nothing written in between. A plan too large to
verify is refused before any page is opened, and a concurrent change is still detected and rolled back.
"""
import unittest

from support import run

MEMORY = r'''
local guarded=require('hd2runtime/core/guarded_transaction')
local BASE,SIZE,PAGE=0x10000000,4*1024*1024,4096
local memory=string.rep(string.char(0),SIZE)
local opened,calls={}, {query=0,read=0,protect=0,write=0}
local runtime={}
local function poke(address,bytes)
 local at=address-BASE;memory=memory:sub(1,at)..bytes..memory:sub(at+#bytes+1)
end
function runtime.system_info()return PAGE end
function runtime.query(at)
 calls.query=calls.query+1
 local page=at-at%PAGE
 if opened[page]then return {base=page,size=PAGE,allocation_base=BASE,state=0x1000,type=0x20000,protect=opened[page]}end
 return {base=BASE,size=SIZE,allocation_base=BASE,state=0x1000,type=0x20000,protect=2}
end
function runtime.read(at,n)calls.read=calls.read+1;return memory:sub(at-BASE+1,at-BASE+n)end
function runtime.protect(page,size,value)
 calls.protect=calls.protect+1
 local old=opened[page]or 2
 if value==2 then opened[page]=nil else opened[page]=value end
 return old
end
function runtime.write(at,bytes)
 calls.write=calls.write+1
 assert(opened[at-at%PAGE]==4,'write without a writable page')
 poke(at,bytes);return true,nil,#bytes
end
local owner={base=BASE,size=SIZE,type=0x20000,protect=2}
local function u32(v)return string.char(v%256,math.floor(v/256)%256,math.floor(v/65536)%256,math.floor(v/16777216)%256)end
-- A plan of `count` changes (4 bytes each, one per page), plus `extra` non-target context bytes, listed `copies` times.
local function plan(count,extra,copies)
 local changes,snapshots={}, {}
 for i=1,count do
  local offset=i*PAGE
  poke(BASE+offset,u32(i))
  changes[i]={label='field'..i,owner=owner,offset=offset,expected=u32(i),desired=u32(1000+i),before=u32(i)}
  snapshots[#snapshots+1]={owner=owner,offset=offset-64,bytes=memory:sub(offset-64+1,offset+64)}
 end
 local context={owner=owner,offset=2*1024*1024,bytes=memory:sub(2*1024*1024+1,2*1024*1024+extra)}
 for _=1,copies do snapshots[#snapshots+1]=context end
 return {changes=changes,snapshots=snapshots}
end
'''


def check(body):
    return run(MEMORY + body + "\nreturn 'ok'")


class GuardedReadBudgetTests(unittest.TestCase):
    def test_hmg_shaped_plan_applies_within_the_derived_allowance(self):
        # 19 changes and one ~428 KB context captured six times: the old fixed 16 MiB cap was exceeded
        # ((4 + 2*19) checks x all copies), the derived allowance is not, and each copy is read once per check.
        self.assertEqual(check(r'''
local p=plan(19,428*1024,6)
local unique=19*128+428*1024
local report=guarded.apply(runtime,p)
assert(report.status=='APPLIED' and report.writes==19,tostring(report.reason))
assert(report.non_target_bytes_unchanged and report.protection_restored)
-- changed+3 full checks of the unique context bytes, plus two target reads per change.
assert(report.guard_bytes==(19+3)*unique+2*19*4,report.guard_bytes)
assert(report.guard_bytes<=guarded.read_allowance(19,unique,19*4))
assert((4+2*19)*(19*128+6*428*1024)>16*1024*1024,'the fixture no longer exceeds the old cap')
for i=1,19 do assert(memory:sub(i*PAGE+1,i*PAGE+4)==u32(1000+i))end
'''), b'ok')

    def test_a_failure_at_the_last_write_still_has_budget_to_roll_everything_back(self):
        # The old fixed cap ran out mid-commit on the HMG plan: 8 writes landed and the rollback had no reads left, so
        # they stayed in memory. The allowance now reserves the rollback's worst case.
        self.assertEqual(check(r'''
local p=plan(19,428*1024,6)
local write=runtime.write;local n=0
runtime.write=function(at,bytes)n=n+1;if n==19 then return false,'injected failure',0 end;return write(at,bytes)end
local report=guarded.apply(runtime,p)
assert(report.status=='REJECTED' and tostring(report.reason):find('exact-width write failed',1,true),tostring(report.reason))
assert(report.rollback=='verified' and report.protection_restored,tostring(report.rollback_error))
assert(report.guard_bytes<=guarded.read_allowance(19,19*128+428*1024,19*4),report.guard_bytes)
for i=1,19 do assert(memory:sub(i*PAGE+1,i*PAGE+4)==u32(i),'field '..i..' was left written')end
'''), b'ok')

    def test_duplicate_context_that_differs_fails_closed_before_any_page_opens(self):
        self.assertEqual(check(r'''
local p=plan(2,4096,1)
local copy={owner=owner,offset=p.snapshots[#p.snapshots].offset,bytes=string.rep('x',4096)}
p.snapshots[#p.snapshots+1]=copy
local ok,why=pcall(guarded.apply,runtime,p)
assert(not ok and tostring(why):find('duplicate transaction context differs',1,true),tostring(why))
assert(calls.protect==0 and calls.write==0)
'''), b'ok')

    def test_plan_beyond_the_ceiling_is_refused_before_any_page_opens(self):
        self.assertEqual(check(r'''
-- 40 changes over ~1.5 MB of context: (2*40+6) x 1.5 MB is far above the 64 MiB ceiling.
local p=plan(40,1536*1024,1)
local ok,why=pcall(guarded.apply,runtime,p)
assert(not ok and tostring(why):find('transaction read budget exceeded',1,true)
 and tostring(why):find('split the operation',1,true),tostring(why))
assert(calls.query==0 and calls.read==0 and calls.protect==0 and calls.write==0)
assert(guarded.READ_CEILING==64*1024*1024)
'''), b'ok')

    def test_a_change_right_before_a_later_write_is_caught_before_that_write(self):
        # A foreign non-target change during the second write's own target reread is caught by the full check right
        # before that write: only the first write landed, and the rollback refuses to write over memory it no longer
        # recognises (fail closed, exactly as before the budget change).
        self.assertEqual(check(r'''
local p=plan(3,4096,1)
local query=runtime.query;local armed=false
local write=runtime.write
runtime.write=function(at,bytes)local ok,why,n=write(at,bytes);armed=true;return ok,why,n end
runtime.query=function(at)
 if armed and at==BASE+2*PAGE then armed=false;poke(BASE+2*1024*1024+8,'!!!!')end
 return query(at)
end
local report=guarded.apply(runtime,p)
assert(report.status=='REJECTED' and report.non_target_check=='mismatch',tostring(report.reason))
assert(report.writes==1 and calls.write==1,report.writes)
assert(report.rollback=='refused_or_failed' and report.protection_restored,report.rollback)
for i=2,3 do assert(memory:sub(i*PAGE+1,i*PAGE+4)==u32(i),'field '..i..' was written after the change')end
for page in pairs(opened)do error('page left open')end
'''), b'ok')

    def test_a_write_that_disturbs_its_context_is_caught_before_the_next_write(self):
        # A write that also changes bytes next to its target (a misbehaving write) is caught by the check right before
        # the next write, and that write never happens.
        self.assertEqual(check(r'''
local p=plan(3,4096,1)
local write=runtime.write;local n=0
runtime.write=function(at,bytes)
 local ok,why,count=write(at,bytes);n=n+1
 if n==1 then poke(at+4,'­')end
 return ok,why,count
end
local report=guarded.apply(runtime,p)
assert(report.status=='REJECTED' and report.non_target_check=='mismatch',tostring(report.reason))
assert(report.writes==1,report.writes)
for i=2,3 do assert(memory:sub(i*PAGE+1,i*PAGE+4)==u32(i))end
'''), b'ok')

    def test_budget_is_enforced_while_reading(self):
        # A runtime whose reads balloon (every check sees a different region split) still cannot read past the
        # allowance: the derived bound is a hard stop, not advice.
        self.assertEqual(check(r'''
local p=plan(2,4096,1)
local allowance=guarded.read_allowance
guarded.read_allowance=function(changed,context,target)return context end
local ok,why=pcall(guarded.apply,runtime,p)
guarded.read_allowance=allowance
local report=ok and why or nil
assert(report and report.status=='REJECTED' and tostring(report.reason):find('transaction read budget exceeded',1,true),
 tostring(report and report.reason or why))
assert(report.rollback~='refused_or_failed' and report.protection_restored)
'''), b'ok')


if __name__ == '__main__':
    unittest.main()
