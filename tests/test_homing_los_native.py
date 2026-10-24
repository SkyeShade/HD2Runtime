"""Real guarded LOS helper with an adapter capability, never a game native call."""
import unittest
from homing_test_support import run


PRELUDE=r'''
local bytes=require('hd2runtime/core/bytes')
local Native=require('hd2runtime/runtime/homing_los_native')
local function u64(value)return bytes.encode(value%4294967296,'u32')..bytes.encode(math.floor(value/4294967296),'u32')end
local physics,vtable,method=0x400000,0x500000,0x600000
local calls,reads,proofs=0,0,0
local in_update,code_ok,descriptor_ok,mission,host=true,true,true,true,true
local player_count,other_world=1,false
local output,count,call_reason=string.rep('\0',8*44),0,nil
local runtime={native_raycast=function(entry,origin,direction,distance)
 calls=calls+1
 assert(entry==0x100000+0x77DEC0 and origin.x==0 and origin.y==0 and origin.z==1)
 assert(direction.x==0 and direction.y==1 and direction.z==0 and distance==10)
 return output,count,call_reason
end}
local world={key='proven-world',exe=0x100000,runtime=runtime}
world.view={
 proves=function(at,hex)
  proofs=proofs+1
  if at==world.exe+Native.DESCRIPTORS then return descriptor_ok end
  return code_ok
 end,
 read=function(at,size)
  reads=reads+1;assert(size==8)
  for i=0,3 do if at==world.exe+Native.WORLDS+i*0xB0+0x20 then
   return u64((i==2 or(other_world and i==1))and physics or 0)
  end end
  error('unexpected read')
 end,
 pointer=function(at)
  if at==physics+0x20 then return vtable end
  if at==vtable+0x148 then return method end
 end}
package.preload['hd2runtime/runtime/event_world']=function()return{
 game_state=function()return{mission=mission,host=host}end,
 players=function()local out={}for i=1,player_count do out[i]={}end return out end}end
package.preload['hd2runtime/runtime/scheduler']=function()return{in_update=function()return in_update end}end
package.preload.ffi=function()error('helper must not load FFI')end
local q={world_key=world.key,origin={x=0,y=0,z=1},direction={x=0,y=1,z=0},distance=10}
local function query()return Native.read(world,q)end
'''


class NativeLosTests(unittest.TestCase):
    def check(self,body):
        self.assertEqual(run(PRELUDE+body,('core/bytes','runtime/homing_los_pins',
                                         'runtime/homing_los_native')),b'ok')

    def test_missing_adapter_capability_never_loads_ffi_or_queries_memory(self):
        self.check('''
runtime.native_raycast=nil
local value,why=query();assert(value==nil and why=='raycast_adapter_unavailable')
assert(calls==0 and reads==0 and proofs==0 and package.loaded.ffi==nil)
''')

    def test_outside_game_update_never_calls_adapter(self):
        self.check('''
in_update=false
local value,why=query();assert(value==nil and why=='game_update_required')
assert(calls==0 and reads==0 and proofs==0 and package.loaded.ffi==nil)
''')

    def test_proven_query_routes_through_adapter_and_decodes_hits(self):
        self.check('''
output=string.rep('\0',24)..bytes.encode(5,'f32')..bytes.encode(300,'u32')..string.rep('\0',12)
count=1
local value=assert(query())
assert(calls==1 and value.abi_verified and value.world_verified and value.complete and not value.overflow)
assert(value.world_key==world.key and value.hits[1].distance==5 and value.hits[1].unit==300)
assert(package.loaded.ffi==nil)
''')

    def test_code_descriptor_world_and_authority_fail_closed(self):
        for setup,reason in (('code_ok=false','raycast_code_changed'),
                             ('descriptor_ok=false','raycast_descriptor_changed'),
                             ('other_world=true','physics_world_ambiguous'),
                             ('method=nil','physics_query_method_unavailable'),
                             ('host=false','solo_mission_required'),
                             ('mission=false','solo_mission_required'),
                             ('player_count=2','solo_mission_required')):
            with self.subTest(reason=reason):
                self.check(setup+";local value,why=query();assert(value==nil and why=='"+
                           reason+"',tostring(why));assert(calls==0)")

    def test_descriptor_is_rechecked_after_initial_proof(self):
        self.check('''
assert(query());assert(calls==1)
descriptor_ok=false
local value,why=query();assert(value==nil and why=='raycast_descriptor_changed'and calls==1)
''')

    def test_adapter_guard_and_saturation_remain_unknown(self):
        self.check('''
output=nil;call_reason='raycast_buffer_guard'
local value,why=query();assert(value==nil and why=='raycast_buffer_guard')
output=string.rep('\0',8*44);count=8;call_reason=nil
value,why=query();assert(value==nil and why=='raycast_saturated')
count=0;assert(#assert(query()).hits==0)
''')

    def test_invalid_request_never_calls_adapter(self):
        self.check('''
q.direction.y=2
local value,why=query();assert(value==nil and why=='invalid_native_query'and calls==0)
''')


class RaycastAdapterTests(unittest.TestCase):
    """Exercise the real FFI adapter against a local callback, never game code."""
    def check(self,body):
        prelude=r'''
package.preload['hd2runtime/runtime/windows_readonly']=function()return function()return{}end end
local runtime=require('hd2runtime/runtime/windows_write').create()
local win=require('hd2runtime/runtime/windows_ffi');local ffi=win.ffi
local calls,damage_guard=0,false
local callback=ffi.cast(win.fn('uint32_t (*)(uint32_t, const float *, const float *, float, uint32_t, void *, uint32_t)'),
 function(descriptor,origin,direction,distance,filter,out,capacity)
  calls=calls+1
  assert(descriptor==0 and origin[0]==1 and origin[1]==2 and origin[2]==3)
  assert(direction[0]==0 and direction[1]==1 and direction[2]==0)
  assert(distance==10 and filter==4294967295 and capacity==8)
  local bytes=ffi.cast('uint8_t *',out)
  ffi.cast('float *',bytes+24)[0]=5
  ffi.cast('uint32_t *',bytes+28)[0]=300
  if damage_guard then bytes[16384]=0 end
  return 1
 end)
local entry=tonumber(ffi.cast('uintptr_t',callback))
local function query()return runtime.native_raycast(entry,{x=1,y=2,z=3},{x=0,y=1,z=0},10)end
'''
        self.assertEqual(run(prelude+body,('runtime/memory_watch','runtime/windows_ffi',
                                          'runtime/windows_write','core/bytes')),b'ok')

    def test_adapter_preserves_abi_output_and_reuses_accounted_scratch(self):
        self.check('''
local memory=require('hd2runtime/runtime/memory_watch')
local bytes,count=assert(query());assert(count==1 and #bytes==8*44 and calls==1)
local b=require('hd2runtime/core/bytes')
assert(b.value(bytes,24,'f32')==5 and b.u32(bytes,28)==300)
local allocated=memory.snapshot().total;assert(allocated==16472)
query();assert(calls==2 and memory.snapshot().total==allocated)
callback:free()
''')

    def test_buffer_guard_failure_latches_before_later_calls(self):
        self.check('''
damage_guard=true
local value,count,why=query();assert(value==nil and count==nil and why=='raycast_buffer_guard'and calls==1)
damage_guard=false
value,count,why=query();assert(value==nil and why=='raycast_buffer_guard'and calls==1)
callback:free()
''')

    def test_adapter_rejects_invalid_extent_before_native_call(self):
        self.check('''
assert(not pcall(runtime.native_raycast,entry,{x=1,y=2,z=3},{x=0,y=2,z=0},10))
assert(not pcall(runtime.native_raycast,entry,{x=1,y=2,z=3},{x=0,y=1,z=0},401))
assert(calls==0)
callback:free()
''')
