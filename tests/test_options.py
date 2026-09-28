import json
import re
import sys
import unittest

from support import ROOT, run
sys.path.insert(0, str(ROOT / 'scripts'))
import build_release
import validate_packaged_runtime

PRELUDE = r'''
local hd2=require('hd2runtime/api/hd2')
local options=require('hd2runtime/api/options')
local ensure=require('hd2runtime/api/ensure')
local scheduler=require('hd2runtime/runtime/scheduler')
options.reset()
local function fails(fn,needle,...)
 local ok,why=pcall(fn,...)
 assert(not ok,'expected failure: '..needle)
 assert(tostring(why):find(needle,1,true),'wrong failure: '..tostring(why)..' (wanted '..needle..')')
end
-- The scheduler restores the host's update (nil in this harness) once its last watch finishes.
local function tick(seconds)for _=1,math.floor(seconds/0.1+0.5)do if update then update(0.1)end end end
local vitality_target=function()return hd2.booster('Vitality Enhancement'):tuning()end
'''


class OptionsTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(PRELUDE + body), b'ok')

    def test_declarations_follow_the_menu_limits(self):
        self.lua(r'''
local page=hd2.options({id='limits',title='Limits'})
assert(page==hd2.options({id='limits',title='Limits'}))
fails(hd2.options,'another title',{id='limits',title='Other'})
fails(hd2.options,'options id',{id='bad id',title='X'})
fails(hd2.options,'title',{id='long',title=string.rep('x',41)})
fails(page.slider,'decimal',page,{id='fine',label='Fine',min=0,max=1,step=0.0001})
fails(page.slider,'min < max',page,{id='flat',label='Flat',min=1,max=1})
fails(page.slider,'on a step',page,{id='off',label='Off',min=0,max=10,step=2,default=3})
fails(page.slider,'outside',page,{id='out',label='Out',min=0,max=10,default=11})
fails(page.choice,'2 to 16',page,{id='one',label='One',choices={'A'}})
fails(page.choice,'one value per choice',page,{id='vals',label='Vals',choices={'A','B'},values={1}})
fails(page.choice,'1-based',page,{id='idx',label='Idx',choices={'A','B'},default=3})
fails(page.toggle,'label',page,{id='nolabel'})
fails(page.toggle,'description',page,{id='desc',label='Desc',description=string.rep('d',401)})
fails(page.toggle,'unsupported toggle option',page,{id='extra',label='Extra',min=1})
page:toggle({id='dup',label='Dup'})
fails(page.toggle,'already declared',page,{id='dup',label='Dup'})
local many=hd2.options({id='many',title='Many'})
for index=1,32 do many:toggle({id='t'..index,label='T'..index})end
fails(many.toggle,'at most 32',many,{id='t33',label='T33'})
return 'ok'
''')

    def test_values_normalize_like_the_menu(self):
        self.lua(r'''
local page=hd2.options({id='norm',title='Norm'})
local slider=page:slider({id='s',label='S',min=0.5,max=2,step=0.25,default=1})
local toggle=page:toggle({id='t',label='T',default=true})
local choice=page:choice({id='c',label='C',choices={'Low','High'},values={10,20},default=2})
assert(slider:get()==1 and toggle:get()==true and choice:get()==20 and choice:index()==2)
assert(slider:assign(1.3,'menu')and slider:get()==1.25)          -- snapped to the step
assert(slider:assign(9,'menu')and slider:get()==2)               -- clamped to max
assert(not slider:assign('x','saved')and slider:get()==2)        -- unusable: ignored
assert(not slider:assign(0/0,'saved')and slider:get()==2)
assert(toggle:assign(false,'menu')and toggle:get()==false)       -- false is a real value
assert(not toggle:assign(1,'menu')and toggle:get()==false)
assert(not choice:assign(3,'menu')and choice:get()==20)
assert(choice:assign(1,'menu')and choice:get()==10)
assert(not slider:assign(2,'menu'))                              -- unchanged: no notification
local d=slider:describe()
assert(d.kind=='slider'and d.min==0.5 and d.max==2 and d.value==2 and d.source=='menu'and d.default==1)
return 'ok'
''')

    def test_registration_with_the_menu_and_without_it(self):
        self.lua(r'''
local page=hd2.options({id='reg',title='Reg'})
local rate=page:slider({id='rate',label='Rate',min=0,max=100,step=10,default=50})
local bad=page:toggle({id='bad',label='Bad'})
local registered,callbacks={},{}
rawset(_G,'ModOptionsMenu',{api=1,
 register_option=function(id,spec)
  if id=='reg.bad'then return false,'refused'end
  assert(spec.mod=='Reg'and spec.type and spec.label);registered[id]=spec;return true end,
 get=function(id)return id=='reg.rate'and 80 or nil end,
 on_change=function(id,fn)callbacks[id]=fn;return true end,ready=function()return true end})
assert(scheduler.active()>=1)
tick(0.1)
assert(registered['reg.rate'].min==0 and registered['reg.rate'].step==10)
assert(rate.registered and rate:get()==80 and rate.source=='saved')
assert(not bad.registered and bad:get()==false)
callbacks['reg.rate'](30,'reg.rate')
assert(rate:get()==30 and rate.source=='menu')
assert(scheduler.active()==0)                                 -- registration watch removed
rawset(_G,'ModOptionsMenu',nil)
local other=hd2.options({id='nomenu',title='No Menu'})
local keep=other:slider({id='keep',label='Keep',min=1,max=3,default=2})
tick(6)
assert(not keep.registered and keep:get()==2 and scheduler.active()==0)
return 'ok'
''')

    def test_binding_keeps_every_write_guard(self):
        self.lua(r'''
local page=hd2.options({id='guards',title='Guards'})
local vit=page:slider({id='vit',label='Vit',min=0.5,max=1,step=0.05,default=0.9})
local wide=page:slider({id='wide',label='Wide',min=0,max=10,step=1,default=1})
local half=page:slider({id='half',label='Half',min=0,max=20,step=0.5,default=1})
local on=page:toggle({id='on',label='On',default=true})
local shared=page:slider({id='shared',label='Shared',min=2,max=6,step=1,default=2})
local uses=page:slider({id='uses',label='Uses',min=1,max=10,default=2})
local function start(request)return ensure.start({},function()end,request)end
fails(start,'allow_unverified_effect',{patch={id='a',target=vitality_target(),
 field=hd2.fields.booster.damage_taken_scale,expect=0.9,value=vit}})
fails(start,'reviewed range',{patch={id='b',allow_unverified_effect=true,
 target=hd2.booster('Integrated Extinguishers'):tuning(),field=hd2.fields.booster.burn_decay_bonus,
 expect=0.5,value=wide}})
fails(start,'integer',{patch={id='c',allow_unverified_effect=true,
 target=hd2.booster('Increased Reinforcement Budget'):tuning(),
 field=hd2.fields.booster.reinforcements_per_player,expect=1,value=half}})
fails(start,'allow_shared',{transaction={id='d',allow_unverified_effect=true,
 target=hd2.booster('Firebomb Hellpods'):explosion(),
 changes={{field=hd2.fields.explosion.inner_radius,expect=2,value=shared}}}})
fails(start,'field is read-only',{patch={id='e',target=hd2.stratagem('GR-8 Recoilless Rifle'),
 field=hd2.fields.stratagem.max_uses,expect=0,value=uses}})
fails(start,'only bind a field value',{patch={id='f',allow_unverified_effect=true,target=vitality_target(),
 field=hd2.fields.booster.damage_taken_scale,expect=vit,value=0.8}})
fails(start,'toggle option can only control',{patch={id='g',allow_unverified_effect=true,target=vitality_target(),
 field=hd2.fields.booster.damage_taken_scale,expect=0.9,value=on}})
fails(start,'enabled must be a toggle',{enabled=vit,patch={id='h',allow_unverified_effect=true,
 target=vitality_target(),field=hd2.fields.booster.damage_taken_scale,expect=0.9,value=0.8}})
for _,call in ipairs({'patch','transaction','plan'})do
 local request=call=='patch'and{id='i',allow_unverified_effect=true,target=vitality_target(),
  field=hd2.fields.booster.damage_taken_scale,expect=0.9,value=vit}
  or call=='transaction'and{id='i',allow_unverified_effect=true,target=vitality_target(),
  changes={{field=hd2.fields.booster.damage_taken_scale,expect=0.9,value=vit}}}
  or{id='i',operations={{id='o',allow_unverified_effect=true,target=vitality_target(),
  field=hd2.fields.booster.damage_taken_scale,expect=0.9,value=vit}}}
 fails(hd2[call],'require hd2.ensure',request)
end
local w=start({enabled=on,patch={id='ok',allow_unverified_effect=true,target=vitality_target(),
 field=hd2.fields.booster.damage_taken_scale,expect=0.9,value=vit}})
assert(w.bound and w.enabled and w.status=='waiting'and w.kind=='patch')
on:assign(false,'menu')
local off=start({enabled=on,patch={id='off',allow_unverified_effect=true,target=vitality_target(),
 field=hd2.fields.booster.damage_taken_scale,expect=0.9,value=vit}})
assert(off.status=='disabled'and not off.enabled)
-- Requests without options take the unchanged ensure path.
local plain=start({patch={id='plain',allow_unverified_effect=true,target=vitality_target(),
 field=hd2.fields.booster.damage_taken_scale,expect=0.9,value=0.8}})
assert(plain.bound==nil and plain.enabled==nil)
return 'ok'
''')

    def test_ownership_rule(self):
        self.lua(r'''
local ownership=require('hd2runtime/core/ownership')
local change={field='f',expected='AAAA',desired='BBBB'}
assert(ownership.expected(change,'AAAA')=='AAAA')
assert(ownership.expected(change,'BBBB')=='AAAA')
fails(ownership.expected,'CONFLICT: f',change,'CCCC')
change.owned='CCCC'
assert(ownership.expected(change,'CCCC')=='CCCC')          -- this operation's own bytes
fails(ownership.expected,'CONFLICT: f',change,'DDDD')        -- anything else still conflicts
return 'ok'
''')

    def test_documented_examples_validate(self):
        addon = (ROOT / 'examples/projects/LiberatorDamageOptions/src/addon.lua').read_text()
        guide = (ROOT / 'docs/getting-started.md').read_text(encoding='utf-8')
        snippet = re.search(r'### In-game options.*?```lua\n(.*?)```', guide, re.S).group(1)
        for source in (addon, 'local hd2=require(\'mods/skyeshade/hd2runtime\')\n' + snippet):
            self.lua('package.preload["mods/skyeshade/hd2runtime"]=function()return hd2 end\n'
                'package.preload["hd2runtime/runtime/windows_write"]=function()return{create=function()return{}end}end\n'
                'local w=assert(loadstring(' + json.dumps(source) + '))()\n'
                'assert(w.bound and w.status=="waiting")\nreturn "ok"')

    def test_snapshot_lifecycle_validation(self):
        result = json.loads((ROOT / 'validation/options-binding-snapshot.json').read_text())
        self.assertEqual(result['status'], 'VALIDATED')
        self.assertTrue(result['checks'] and all(check['passed'] for check in result['checks']))
        names = {check['name'] for check in result['checks']}
        for required in ('options registered with saved values', 'malformed saved choice falls back to the default',
                'out-of-range saved slider is clamped by the menu', 'missing saved value uses the default',
                'live change writes the new value', 'change from an applied value is an owned transition',
                'no-op change does no work', 'rapid changes coalesce', 'steady state is a byte check, not a resolution',
                'drift after a change re-applies the new desired value', 'disable restores the reviewed baseline',
                'a reset while disabled writes nothing', 're-enable applies the current value',
                'change while the target is unavailable waits', 'pending retry picks up the newest value',
                'disable during a pending retry restores the baseline', 'a third-party value is a conflict',
                'plan applies every bound value atomically', 'transaction applies both bound fields in one write set',
                'allow_shared stays mandatory', 'allow_unverified_effect stays mandatory',
                'slider range must fit the reviewed field range', 'read-only capabilities stay read-only',
                'one-shot operations refuse option handles'):
            self.assertIn(required, names)
        self.assertEqual(result['modOptionsMenu']['api'], 1)
        self.assertFalse(result['modOptionsMenu']['nativeReady'])
        self.assertFalse(result['persistence']['writeBackExercised'])
        self.assertGreaterEqual(result['metrics']['options.owned_transitions'], 1)

    def test_packaged_runtime_ships_and_exercises_options(self):
        resources = build_release.runtime_resources()
        for name in ('hd2runtime/api/options', 'hd2runtime/core/ownership'):
            self.assertIn(name, resources)
            self.assertIn(json.dumps(name), resources[build_release.PACKAGE_MODULES].decode())
        self.assertIn('options-live', validate_packaged_runtime.SCENARIOS)
        self.assertIn('options-live', validate_packaged_runtime.EXTRAS)
        # No dynamic module names: every internal require is a literal the static scan can resolve.
        for name in ('api/ensure.lua', 'api/options.lua', 'api/hd2.lua'):
            self.assertNotIn("require('hd2runtime/api/'..", (ROOT / name).read_text())


if __name__ == '__main__':
    unittest.main()
