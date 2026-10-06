"""GitHub issue #3: guarded writes on Proton/Wine (core/page_protection.lua, core/guarded_transaction.lua).

Proton maps game.dll's data pages PAGE_WRITECOPY (0x8) where Windows reports PAGE_READWRITE. A DELIVERY_RESOLVED
support weapon (MG-43, MG-206) proves its call-in delivery chain through a read-only context in game.dll, and the
guarded transaction refused that context with failed=protection although its bytes matched. Context and proof reads
now accept every readable protection, exactly what the readers already accepted. A page that is opened and written
must still be READONLY or READWRITE: a copy-on-write (or executable) write target is refused before any page is
opened, protection changed or byte written.
"""
import json
import unittest

from support import ROOT, run
import sys

sys.path.insert(0, str(ROOT / 'scripts'))
import build_profile  # noqa: E402

# Two allocations: game.dll's image (a read-only proof context lives in it; Proton reports its data pages 0x8) and a
# private heap allocation holding the write target (READONLY until the guarded write opens its page).
MEMORY = r'''
local guarded=require('hd2runtime/core/guarded_transaction')
local protection=require('hd2runtime/core/page_protection')
local PAGE=4096
local IMAGE,IMAGE_SIZE=0x7FF000000000,64*PAGE
local HEAP,HEAP_SIZE=0x20000000,16*PAGE
local memory={}
local function mem(base,size)memory[base]={size=size,bytes=string.rep(string.char(0),size)}end
mem(IMAGE,IMAGE_SIZE);mem(HEAP,HEAP_SIZE)
local function find(at)
 for base,m in pairs(memory)do if at>=base and at<base+m.size then return base,m end end
end
local function poke(address,bytes)
 local base,m=find(address);local at=address-base
 m.bytes=m.bytes:sub(1,at)..bytes..m.bytes:sub(at+#bytes+1)
end
local protect={}          -- per page; defaults below
local calls={query=0,protect=0,write=0}
local runtime={}
function runtime.system_info()return PAGE end
local function page_protect(page)
 if protect[page]then return protect[page]end
 local base=find(page)
 return base==IMAGE and protection.WRITECOPY or protection.READONLY
end
function runtime.query(at)
 calls.query=calls.query+1
 local base,m=find(at)
 if not base then return nil end
 local page=at-at%PAGE
 return {base=page,size=PAGE,allocation_base=base,state=0x1000,type=base==IMAGE and 0x1000000 or 0x20000,
  protect=page_protect(page)}
end
function runtime.read(at,n)local base,m=find(at);return m.bytes:sub(at-base+1,at-base+n)end
function runtime.protect(page,size,value)
 calls.protect=calls.protect+1
 local old=page_protect(page);protect[page]=value;return old
end
function runtime.write(at,bytes)
 calls.write=calls.write+1
 assert(page_protect(at-at%PAGE)==protection.READWRITE,'write without a writable page')
 poke(at,bytes);return true,nil,#bytes
end
local image={base=IMAGE,size=IMAGE_SIZE,type=0x1000000}            -- like game.dll: no expected protection
local heap={base=HEAP,size=HEAP_SIZE,type=0x20000,protect=protection.READONLY}
local function u32(v)return string.char(v%256,math.floor(v/256)%256,math.floor(v/65536)%256,math.floor(v/16777216)%256)end
-- The proof: 8 bytes in game.dll (a global pointer, as at game.dll+0x348E8F8), plus the target record's context.
poke(IMAGE+0x8F8,u32(0x12345678)..u32(0x7FF0))
poke(HEAP+0x100,u32(760))
local function plan(target_owner,target_offset)
 local current=runtime.read(target_owner.base+target_offset,4)
 return {changes={{label='weapon.fire_rate',owner=target_owner,offset=target_offset,expected=current,
   desired=u32(900),before=current}},
  snapshots={{owner=image,offset=0x8F8,bytes=runtime.read(IMAGE+0x8F8,8)},
   {owner=target_owner,offset=target_offset-16,bytes=runtime.read(target_owner.base+target_offset-16,48)}}}
end
'''


def check(body):
    return run(MEMORY + body + "\nreturn 'ok'")


class ProtonContextTests(unittest.TestCase):
    def test_a_copy_on_write_proof_context_passes_the_region_checks(self):
        # 1: the read-only proof context in game.dll is PAGE_WRITECOPY (Proton); the target is a READONLY heap page.
        self.assertEqual(check(r'''
assert(runtime.query(IMAGE+0x8F8).protect==0x8)
local report=guarded.apply(runtime,plan(heap,0x100))
assert(report.status=='APPLIED',tostring(report.reason)..' '..tostring(report.guard_failure))
assert(report.writes==1 and report.guard_failure==nil and report.non_target_bytes_unchanged)
assert(report.protection_restored and runtime.query(HEAP+0x100).protect==protection.READONLY)
assert(runtime.read(HEAP+0x100,4)==u32(900))
-- The context itself was only read: no protection change or write in the image.
assert(protect[IMAGE+0x8F8-0x8F8%PAGE]==nil)
'''), b'ok')

    def test_every_readable_protection_is_accepted_for_a_context_and_nothing_else(self):
        self.assertEqual(check(r'''
for _,value in ipairs({0x2,0x4,0x8,0x20,0x40,0x80})do
 poke(HEAP+0x100,u32(760));protect={}
 protect[IMAGE]=value
 local report=guarded.apply(runtime,plan(heap,0x100))
 assert(report.status=='APPLIED',('context protect 0x%X: %s'):format(value,tostring(report.reason)))
end
-- No access, a guard page or a modifier is not readable: refused, nothing written.
for _,value in ipairs({0x1,0x104,0x208,0x10})do
 poke(HEAP+0x100,u32(760));protect={}
 protect[IMAGE]=value
 local writes=calls.write
 local report=guarded.apply(runtime,plan(heap,0x100))
 assert(report.status=='REJECTED'and calls.write==writes,('context protect 0x%X applied'):format(value))
 assert(report.guard_failure:find('failed=protection',1,true),report.guard_failure)
end
'''), b'ok')


class ProtonWriteTargetTests(unittest.TestCase):
    def test_a_copy_on_write_target_is_refused_before_any_page_is_opened(self):
        # 2: the write target itself on a PAGE_WRITECOPY page (in the image, as Proton maps game.dll's data). Refused
        # with failed=protection; no protection change and no write, whatever protection the owner claims.
        self.assertEqual(check(r'''
poke(IMAGE+0x2100,u32(760))
for _,claimed in ipairs({false,0x8,0x2})do
 local owner={base=IMAGE,size=IMAGE_SIZE,type=0x1000000,protect=claimed or nil}
 local before=runtime.read(IMAGE+0x2100,4)
 local protects,writes=calls.protect,calls.write
 local report=guarded.apply(runtime,plan(owner,0x2100))
 assert(report.status=='REJECTED',tostring(claimed))
 assert(calls.protect==protects and calls.write==writes and report.writes==0 and report.protection_changes==0)
 assert(runtime.read(IMAGE+0x2100,4)==before and runtime.query(IMAGE+0x2100).protect==0x8)
 assert(report.guard_failure:find('failed=protection',1,true)and report.guard_failure:find('protect=0x8',1,true),
  report.guard_failure)
end
'''), b'ok')

    def test_an_executable_or_copy_on_write_heap_target_is_refused_too(self):
        self.assertEqual(check(r'''
for _,value in ipairs({0x8,0x20,0x40,0x80})do
 poke(HEAP+0x100,u32(760));protect={}
 protect[HEAP]=value
 local owner={base=HEAP,size=HEAP_SIZE,type=0x20000,protect=value}
 local protects,writes=calls.protect,calls.write
 local report=guarded.apply(runtime,plan(owner,0x100))
 assert(report.status=='REJECTED'and calls.protect==protects and calls.write==writes,('target 0x%X'):format(value))
 assert(runtime.read(HEAP+0x100,4)==u32(760))
end
-- READWRITE and READONLY targets still write (READONLY opened, then restored).
for _,value in ipairs({0x4,0x2})do
 poke(HEAP+0x100,u32(760));protect={}
 protect[HEAP]=value
 local report=guarded.apply(runtime,plan({base=HEAP,size=HEAP_SIZE,type=0x20000,protect=value},0x100))
 assert(report.status=='APPLIED'and runtime.query(HEAP).protect==value,tostring(report.reason))
end
'''), b'ok')


class SharedDefinitionTests(unittest.TestCase):
    def test_readers_and_the_guard_share_one_readable_set(self):
        self.assertEqual(run(r'''
local protection=require('hd2runtime/core/page_protection')
local n=0;for value in pairs(protection.READABLE)do n=n+1;assert(protection.readable(value))end
assert(n==6 and protection.readable(0x8)and not protection.readable(0x1)and not protection.readable(0x108))
assert(protection.writable_target(0x2)and protection.writable_target(0x4))
for _,value in ipairs({0x8,0x20,0x40,0x80,0x1})do assert(not protection.writable_target(value))end
return 'ok'
'''), b'ok')
        for path in ('runtime/reader.lua', 'api/snapshot_capture.lua', 'core/guarded_transaction.lua'):
            body = (ROOT / path).read_text(encoding='utf-8')
            self.assertIn("require('hd2runtime/core/page_protection')", body, path)
            self.assertNotIn('r.protect==8', body, path)


class ProtonSnapshotTests(unittest.TestCase):
    """The issue's own operations on the retained snapshot: MG-43 (a plan) and MG-206 (a patch), through the
    production API, with game.dll's read-write image pages reported PAGE_WRITECOPY as Proton does."""

    def test_mg43_and_mg206_apply_with_proton_protections_exactly_as_on_windows(self):
        import snapshot_regions
        results = {}
        for mode in ('windows', 'proton'):
            body = r'''
local MODE="''' + mode + r'''"
local json=require('hd2runtime/primary_mapper/json')
local adapter,overlay,writes,lines,protections={}, {}, {}, {}, {}
for k,v in pairs(source)do adapter[k]=v end
function adapter.read(address,size)
 local bytes=source.read(address,size)
 if not bytes then return nil end
 for at,value in pairs(overlay)do
  if at<address+size and at+#value>address then
   local first=math.max(at,address);local last=math.min(at+#value,address+size)
   bytes=bytes:sub(1,first-address)..value:sub(first-at+1,last-at)..bytes:sub(last-address+1)
  end
 end
 return bytes
end
function adapter.query(at)
 local r=source.query(at)
 if not r then return r end
 local copy={};for k,v in pairs(r)do copy[k]=v end
 local page=at-at%4096
 if protections[page]then copy.protect=protections[page]
 elseif MODE=='proton'and copy.type==0x1000000 and copy.protect==4 then copy.protect=8 end
 return copy
end
function adapter.write(address,bytes)writes[#writes+1]={address=address,bytes=bytes};overlay[address]=bytes;return true,nil,#bytes end
function adapter.protect(page,size,value)local old=adapter.query(page).protect;protections[page]=value;return old end
local session=require('hd2runtime/api/session').new(adapter,function(line)lines[#lines+1]=line end)
local mg43,mg206=session.support_weapon('MG-43 Machine Gun'),session.support_weapon('MG-206 Heavy Machine Gun')
local ops={
 session.plan{id='mg43',operations={
  {id='rate',target=mg43,field=session.fields.weapon.fire_rate,expect=760,value=900},
  {id='reload',target=mg43,allow_unverified_effect=true,field=session.fields.reload.duration,expect=4.5,value=3}}},
 session.patch{id='mg206',target=mg206,field=session.fields.weapon.fire_rate,expect=600,value=700}}
for _,op in ipairs(ops)do
 for _=1,4000 do op.tick(0.1);if op.status=='complete'or op.status=='rejected'or op.status=='failed'then break end end
end
local out={writes={},results={},guard=0,proton_image_pages=0}
for _,w in ipairs(writes)do
 local r=source.query(w.address);out.writes[#out.writes+1]=r and r.type or 0
end
for _,op in ipairs(ops)do out.results[#out.results+1]=op.result and op.result.status or op.status end
for _,line in ipairs(lines)do if line:find('guard_failure',1,true)then out.guard=out.guard+1 end end
out.write_count=#writes
return json.encode(out)
'''
            results[mode] = json.loads(snapshot_regions.run_lua(body, build_profile.snapshot_directory()
                / 'F5FEE03DCFDB-20260926T222226Z.hd2snap'))
        for mode, result in results.items():
            self.assertEqual(result['results'], ['APPLIED', 'APPLIED'], (mode, result))
            self.assertEqual(result['guard'], 0, mode)
            # Every write lands in a private heap page, never in the (copy-on-write) image.
            self.assertEqual(set(result['writes']), {0x20000}, mode)
        self.assertEqual(results['proton']['write_count'], results['windows']['write_count'])


if __name__ == '__main__':
    unittest.main()
