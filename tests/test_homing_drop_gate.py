"""Actual player-drop records gate HUD admission despite a healthy avatar.

Layout/phase/type evidence: same-build HellpodDropHold/src/drop_hold.lua,
read_manager, own_drop_pod, phase_of and candidate; no lifecycle enum, camera
FOV or elapsed-time assumption. Memory is synthetic and native calls never run.
"""
import unittest
from homing_test_support import ROOT, run
from test_homing_visibility_gate import MODULES, PRELUDE
from test_homing_reticle import PRELUDE as HUD_PRELUDE

PODS=r'''
local DROP=0x3326D58
local pod_manager,pod_records,pod_locals,pod_nets,pod_map=0x900000,0x910000,0x920000,0x930000,0x940000
local initial,reinforce='E58163E71928D3E2','EF9EB729A9D6D849'
local phase_addresses={};local pod_descriptors={};local pod_ids={}
local old_exists=W.entity_exists
W.entity_exists=function(w,entity)return old_exists(w,entity)or pod_ids[entity]==true end
local function type_bytes(hex)return u32(tonumber(hex:sub(9),16))..u32(tonumber(hex:sub(1,8),16))end
local function pods(rows)
 phase_addresses={};pod_descriptors={};pod_ids={}
 put(visibility_world.game+DROP,pointer(pod_manager))
 put(pod_manager+36,string.rep('\0',84))
 put(pod_manager+36,u32(8));put(pod_manager+44,u32(#rows));put(pod_manager+48,u32(#rows))
 put(pod_manager+64,pointer(pod_map)..u32(8)..u32(0xffffffff)..u32(1))
 put(pod_manager+88,pointer(pod_records));put(pod_manager+104,pointer(pod_locals))
 put(pod_manager+112,pointer(pod_nets))
 put(pod_map,string.rep('\255',64))
 for index,row in ipairs(rows)do
  local slot=index-1;local desc=0x950000+slot*0x100;local id=row.entity or(500+slot)
  pod_ids[id]=true;pod_descriptors[index]=desc
  put(pod_records+slot*8,pointer(desc))
  put(desc,type_bytes(row.type or initial)..u32(id)..u32(700+slot)..u32(800+slot)..u32(row.owned==false and 0 or 1))
  put(pod_locals+slot*160,string.rep('\0',160))
  local phase=pod_nets+slot*20;put(phase,u32(row.phase or 0)..string.rep('\0',16))
  phase_addresses[index]=phase
  local bucket=id%8
  while b.u32(read(pod_map+bucket*8,4),0)~=0xffffffff do bucket=(bucket+1)%8 end
  put(pod_map+bucket*8,u32(id)..u32(slot))
 end
end
pods({})
local function drop_state()return require('hd2runtime/runtime/homing_drop_state').active(visibility_world)end
'''


class DropGateTests(unittest.TestCase):
    def check(self,body,hud=False):
        names=MODULES
        if (ROOT/'runtime/homing_drop_state.lua').exists():
            names=names+('runtime/homing_drop_state',)
        prefix=HUD_PRELUDE+PRELUDE+PODS if hud else PRELUDE+PODS
        self.assertEqual(run(prefix+body,names),b'ok')

    def test_healthy_spawned_avatar_is_hidden_during_owned_player_drop(self):
        self.check('''
assert(Visibility.blocked(visibility_world,false)==false)
for _,kind in ipairs({initial,reinforce})do for _,phase in ipairs({0,1})do
 pods({{type=kind,phase=phase}})
 local active=drop_state();assert(active==true,'known owned falling/braking player pod not observed')
 assert(Visibility.blocked(visibility_world,false)==true,'healthy lifecycle3 avatar leaked drop HUD')
 put(phase_addresses[1],u32(2))
 assert(drop_state()==false and Visibility.blocked(visibility_world,false)==false,'landing did not release HUD gate')
end end
''')

    def test_other_owners_nonplayer_pods_and_landed_records_are_not_our_descent(self):
        self.check('''
pods({{type=initial,phase=0,owned=false},{type='0123456789ABCDEF',phase=1},{type=reinforce,phase=2}})
assert(drop_state()==false,'foreign or non-player pod blocked local on-foot HUD')
assert(Visibility.blocked(visibility_world,false)==false)
pods({{type=initial,phase=2},{type=reinforce,phase=1}})
assert(drop_state()==true and Visibility.blocked(visibility_world,false)==true)
''')

    def test_unknown_manager_invalid_phase_and_over_budget_fail_closed(self):
        self.check('''
put(visibility_world.game+DROP,pointer(0))
assert(drop_state()==nil and Visibility.blocked(visibility_world,false)==true,'absent manager was treated as landed')
pods({{phase=3}});assert(drop_state()==nil and Visibility.blocked(visibility_world,false)==true)
pods({{phase=0}});mem[phase_addresses[1]]=nil
assert(drop_state()==nil and Visibility.blocked(visibility_world,false)==true,'unreadable phase was treated as landed')
pods({});put(pod_manager+36,u32(4096));put(pod_manager+44,u32(4096));put(pod_manager+48,u32(4096))
assert(drop_state()==nil and Visibility.blocked(visibility_world,false)==true,'unbounded or unobserved scan admitted HUD')
pods({});assert(drop_state()==false and Visibility.blocked(visibility_world,false)==false)
''')

    def test_map_and_record_identity_mismatch_never_claims_a_stable_drop(self):
        self.check('''
pods({{phase=0}})
put(pod_map+(500%8)*8,u32(500)..u32(7))
assert(drop_state()==nil,'manager map disagreed with the selected record index')
assert(Visibility.blocked(visibility_world,false)==true)
pods({{phase=0}})
local original_read=v.read;local descriptor_reads=0
v.read=function(at,n)
 if at==pod_descriptors[1]and n>=24 then
  descriptor_reads=descriptor_reads+1
  if descriptor_reads>1 then put(at+8,u32(999))end
 end
 return original_read(at,n)
end
assert(drop_state()==nil,'a changing descriptor was reported as a stable local drop')
''')

    def test_retained_ring_and_stock_markers_clear_on_actual_pod_state(self):
        self.check('''
enable_stock_assets();S.Window={show_cursor=function()return false end};stingray=S
local h=Hud.new({view=View,style={marker_shape='vanilla'},
 blocked=function()return Visibility.blocked(visibility_world,false)end})
local s=snapshot();h:update(s)
assert(h:status().ring and live_gui_count()==3)
pods({{phase=0}});local created=calls.create;h:tick()
assert(h:status().state=='suppressed'and live_gui_count()==0,'actual falling pod left retained HUD visible')
assert(h:status().drop_state=='falling'and h:status().drop_phase==0 and h:status().drop_entity==500,
 'HUD status must retain observed game pod identity and phase for diagnosis')
h:update(s);assert(calls.create==created)
put(phase_addresses[1],u32(1));h:update(s);assert(calls.create==created)
put(phase_addresses[1],u32(2));h:update(s)
assert(h:status().state=='drawing'and h:status().ring and live_gui_count()==3)
h:shutdown();assert(live_gui_count()==0)
''',hud=True)
