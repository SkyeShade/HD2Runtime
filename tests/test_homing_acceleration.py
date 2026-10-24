import unittest
from homing_test_support import run

PRELUDE="""
package.preload['hd2runtime/runtime/events']=function()return {owner=function(v)return v or 'test'end,emit_log=function()end}end
local configs={};local engine={configure=function(c)configs[#configs+1]=c;return c end,stop=function()return true end,configs=function()return configs end}
package.preload['hd2runtime/runtime/projectile_homing']=function()return engine end
local api=require('hd2runtime/api/homing')
"""
class AccelerationTests(unittest.TestCase):
    def test_optional_setting_validates_and_preserves_old_defaults(self):
        self.assertEqual(run(PRELUDE+"""
local old=api.homing('AR-23 Liberator');assert(old.status=='active')
assert(configs[1].lateral_acceleration==nil and configs[1].turn_rate==math.rad(90))
local auto=api.homing('AR-23 Liberator',{lateral_acceleration=600,turn_rate=1440})
assert(auto.status=='active',auto.reason)
assert(configs[2].lateral_acceleration==600 and auto:describe().options.lateral_acceleration==600)
for _,v in ipairs({0,-1,100001,math.huge,0/0,'600',false})do
 local bad=api.homing('AR-23 Liberator',{lateral_acceleration=v});assert(bad.status=='refused'and bad.code=='INVALID_OPTION')
end
assert(#configs==2)
""",('api/homing','domains/projectile_homing')),b'ok')

    def test_actual_engine_computes_speed_dependent_rate_with_angular_cap(self):
        deps=('core/bytes','core/page_protection','core/guarded_transaction','runtime/metrics','runtime/memory_watch','runtime/spawn_compatibility','domains/projectile_rows','domains/projectile_homing','domains/event_natives','runtime/projectile_homing')
        self.assertEqual(run("""
package.preload['hd2runtime/runtime/event_world']=function()return {}end
package.preload['hd2runtime/runtime/scheduler']=function()return {}end
package.preload['hd2runtime/runtime/log']=function()return {}end
local E=require('hd2runtime/runtime/projectile_homing')
local c={turn_rate=math.rad(1440),lateral_acceleration=600}
assert(E.angular_limit(c,300)==2 and E.angular_limit(c,900)==600/900)
assert(E.angular_limit(c,1)==c.turn_rate)
c.lateral_acceleration=nil;assert(E.angular_limit(c,900)==c.turn_rate)
""",deps),b'ok')
