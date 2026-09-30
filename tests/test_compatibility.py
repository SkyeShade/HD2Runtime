"""Mods that need a newer HD2Runtime: SemVer precedence, per-mod logging, one aggregated warning per session on a
stable ship, and a GUI failure that never escapes."""
import json
import sys
import unittest

from support import ROOT, run

sys.path.insert(0, str(ROOT / 'sdk'))
import hd2 as sdk  # noqa: E402


class CompatibilityTests(unittest.TestCase):
    def test_semver_and_session_warning(self):
        self.assertEqual(run(r'''
local c=require('hd2runtime/api/compatibility')
c._reset()
assert(c.compare('0.28.0','0.28.0')==0 and c.compare('0.28.0','0.29.0')==-1 and c.compare('1.0.0','0.99.99')==1)
assert(c.compare('0.29.0-rc.1','0.29.0')==-1 and c.compare('0.29.0','0.29.0-rc.1')==1)
assert(c.compare('1.0.0-alpha','1.0.0-alpha.1')==-1 and c.compare('1.0.0-alpha.beta','1.0.0-beta')==-1)
assert(c.compare('1.0.0-beta.2','1.0.0-beta.11')==-1 and c.compare('1.0.0-rc.1','1.0.0-beta.11')==1)
assert(c.compare('1.0.0+a','1.0.0+b')==0 and c.compare('1.0','1.0.0')==nil and c.compare('1.0.0-','1.0.0')==nil)
local installed=c.installed()
-- Equal and older requirements never warn.
assert(c.require_runtime('mods/a',installed)==true and c.require_runtime('mods/b','0.1.0')==true)
assert(#c.incompatible()==0 and c.highest()==nil)
local shown,state,fail={},'Mission',false
c.game_state=function()return {name=state}end
c.presenter=function(title,message)if fail then error('no GUI')end;shown[#shown+1]={title,message};return true end
local ok,why=c.require_runtime('mods/new','9.0.0','New Mod')
assert(ok==false and why:find('9.0.0',1,true))
c.require_runtime('mods/newer','9.1.0-rc.1')
c.require_runtime('mods/new','9.0.0')          -- repeated: recorded once
assert(#c.incompatible()==2 and c.highest()=='9.1.0-rc.1')
local watch=c.status()and rawget(_G,'HD2RuntimeCompatibilityV1').watch
for _=1,30 do watch.tick(0.5)end
assert(#shown==0,'shown during a mission')
state='Ship'
for _=1,4 do watch.tick(1)end
state='PrepareMission'                         -- the ship was not stable: the count starts again
watch.tick(1)
state='Ship'
for _=1,4 do watch.tick(1)end
assert(#shown==0,'shown before five consecutive ship polls')
watch.tick(1)
assert(#shown==1 and shown[1][1]=='HD2Runtime update required')
assert(shown[1][2]=='One or more installed mods require a newer HD2Runtime version.\n\nRequired version: 9.1.0-rc.1'
 ..'\nInstalled version: '..installed..'\n\nPlease update HD2Runtime.')
assert(watch.status=='complete'and c.status().shown and c.status().dialog=='shown')
c.require_runtime('mods/late','9.2.0')          -- once per session: no second dialog
for _=1,20 do watch.tick(1)end
assert(#shown==1)
-- A GUI failure only logs.
c._reset();fail=true
c.require_runtime('mods/new','9.0.0')
watch=rawget(_G,'HD2RuntimeCompatibilityV1').watch
state='Ship'
for _=1,6 do watch.tick(1)end
assert(c.status().shown and c.status().dialog=='unavailable')
c._reset()
return 'ok'
'''), b'ok')

    def test_wrapper_reports_before_failing_closed(self):
        wrapped = sdk.wrap_addon('mods/test/too_new', '9.0.0-rc.2', 'return "started"', 'TooNew')
        older = sdk.wrap_addon('mods/test/fine', '0.1.0', 'return "started"', 'Fine')
        result = run(r'''
rawset(_G,'CowboyBingusModLoader',rawget(_G,'CowboyBingusModLoader')or{api=1,version=18})
local c=require('hd2runtime/api/compatibility')
c._reset()
package.preload['mods/skyeshade/hd2runtime']=function()return require('hd2runtime/api/hd2')end
local ok,why=pcall(assert(loadstring(''' + json.dumps(wrapped) + ''')))
assert(not ok and tostring(why):find('HD2Runtime dependency version mismatch',1,true),tostring(why))
local items=c.incompatible()
assert(#items==1 and items[1].mod=='mods/test/too_new'and items[1].required=='9.0.0-rc.2'and items[1].display=='TooNew')
local started=assert(loadstring(''' + json.dumps(older) + '''))()
assert(started=='started'and#c.incompatible()==1)
c._reset()
return 'ok'
''')
        self.assertEqual(result, b'ok')

    def test_sdk_accepts_semver_minimums(self):
        import re
        for good in ('0.28.0', '0.29.0-rc.1', '1.0.0-alpha.1+build.5'):
            self.assertTrue(re.fullmatch(sdk.SEMVER, good), good)
        for bad in ('0.28', '0.28.0-', '01.2.3', 'v0.28.0'):
            self.assertFalse(re.fullmatch(sdk.SEMVER, bad), bad)


if __name__ == '__main__':
    unittest.main()
