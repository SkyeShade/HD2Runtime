"""Conflict diagnostics (core/ownership.lua). A user log showed `CONFLICT: magazine.spare_magazines is neither expected
nor desired` with nothing else. The message now names the target and the expected, desired and observed values, plus
the field's sharing scope. The rule itself is unchanged: only the reviewed baseline, bytes already desired, or bytes
the same option-bound ensure owns may be replaced."""
import unittest

from support import run


class ConflictDiagnosticTests(unittest.TestCase):
    def test_conflict_names_target_values_and_scope_and_still_fails_closed(self):
        self.assertEqual(run(r'''
local ownership=require('hd2runtime/core/ownership')
local b=require('hd2runtime/core/bytes')
local change={field='magazine.spare_magazines',expect=2,value=10,expected=b.encode(2,'u32'),desired=b.encode(10,'u32'),
 descriptor={backing={storage='u32'},writeScope='weapon_local',affectsMultipleWeapons=false}}
-- Unchanged rule: the baseline and the desired bytes are accepted, and so are bytes the ensure owns.
assert(ownership.expected(change,change.expected)==change.expected)
assert(ownership.expected(change,change.desired)==change.expected)
change.owned=b.encode(6,'u32')
assert(ownership.expected(change,change.owned)==change.owned)
-- Anything else is refused, and the message says what collided.
local ok,why=pcall(ownership.expected,change,b.encode(7,'u32'),nil,{target='support_weapon MG-206 Heavy Machine Gun'})
assert(not ok,'a third-party value was accepted')
why=tostring(why)
assert(why:find('CONFLICT: magazine.spare_magazines is neither expected nor desired (',1,true),why)
for _,needle in ipairs({'target support_weapon MG-206 Heavy Machine Gun','expected 2 (2)','desired 10 (10)',
  'observed 7','owned 6','scope weapon_local'})do
 assert(why:find(needle,1,true),needle..' missing: '..why)
end
-- Shared fields say how many other weapons share them; floats decode, unknown widths fall back to hex.
local shared={field='projectile.velocity',expect=980,value=1960,expected=b.encode(980,'f32'),
 desired=b.encode(1960,'f32'),descriptor={backing={storage='f32'},writeScope='shared_projectile',
 affectsMultipleWeapons=true,sharedWithWeapons={'a','b'}}}
ok,why=pcall(ownership.expected,shared,b.encode(1200,'f32'))
assert(not ok and tostring(why):find('observed 1200',1,true)
 and tostring(why):find('scope shared_projectile, shared with 2 other weapons',1,true),tostring(why))
local raw={field='x',expect='a',value='b',expected='\1\2\3\4\5\6\7\8',desired='\8\7\6\5\4\3\2\1'}
ok,why=pcall(ownership.expected,raw,'\0\0\0\0\0\0\0\0')
assert(not ok and tostring(why):find('observed 0x0000000000000000',1,true),tostring(why))
return 'ok'
'''), b'ok')


if __name__ == '__main__':
    unittest.main()
