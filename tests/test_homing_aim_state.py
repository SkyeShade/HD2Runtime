import unittest
from homing_test_support import run

PRELUDE=r'''

package.preload['hd2runtime/domains/input_bindings']=function()
 return {ownerGlobal=0x347cf18,state=808,stateStride=32,actionsPerGroup=97,
  pins={{rva=10,bytes='abc'}}}
end
held=0;proven=true;owner=0x200000;changed=false;proofs=0
world={key='build/world',game=0x100000,view={
 proves=function(at,bytes)proofs=proofs+1;return proven end,
 pointer=function(at)assert(at==world.game+0x347cf18);return owner end,
 read=function(at,n)
  assert(at==0x200000+808+32*(2*97+8) and n==1)
  if changed then owner=0x300000 end
  return type(held)=='number'and string.char(held)or held
 end}}

local AimState=require('hd2runtime/runtime/homing_aim_state')
'''

class AimStateTests(unittest.TestCase):
    def check(self,code):
        self.assertEqual(run(PRELUDE+code,('runtime/homing_aim_state',)),b'ok')

    def test_activation_and_release_are_live_and_pins_are_per_world(self):
        self.check('''
assert(AimState.active(world)==false);held=1;assert(AimState.active(world)==true)
held=0;assert(AimState.active(world)==false);assert(proofs==1)
world.key='next world';assert(AimState.active(world)==false);assert(proofs==2)
''')

    def test_unknown_read_failed_pin_or_owner_change_never_shows_hud(self):
        for setup in ('held=2','held=nil','held=""','proven=false','changed=true'):
            self.check(setup+';assert(AimState.active(world)==nil)')
