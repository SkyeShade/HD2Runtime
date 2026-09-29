import json
from pathlib import Path
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
local logged={}
local log_module=require('hd2runtime/runtime/log')
log_module.emit=function(line)logged[#logged+1]=line end
local function count(text)local n=0;for _,line in ipairs(logged)do if line:find(text,1,true)then n=n+1 end end;return n end
local function vitality(id,value,enabled)
 return scheduler.attach(ensure.start({},function(line)logged[#logged+1]=line end,{enabled=enabled,patch={id=id,
  allow_unverified_effect=true,target=vitality_target(),field=hd2.fields.booster.damage_taken_scale,
  expect=0.9,value=value}}))
end
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
fails(hd2.options,"fallback must be 'default' or 'disable'",{id='fb',title='Fb',fallback='maybe'})
assert(page.fallback=='default')                                      -- the default mode
assert(hd2.options({id='strict',title='Strict',fallback='disable'}).fallback=='disable')
fails(hd2.options,'another fallback',{id='limits',title='Limits',fallback='disable'})
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
assert(page:toggle({id='dup',label='Dup'}).state=='unavailable')   -- duplicate: unavailable, not fatal
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
assert(rate.state=='ready'and bad.state=='unavailable'and bad.reason:find('rejected option bad',1,true))
assert(count('options reg unavailable: Mod Options Menu rejected option bad (refused)')==1)
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
fails(start,'field is read-only',{patch={id='e',target=hd2.stratagem('Eagle Airstrike'),
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
 -- Refused at registration as a logged, rejected handle (never a raised error that aborts the mod).
 local refused=hd2[call](request)
 assert(refused.status=='rejected'and tostring(refused.error):find('require hd2.ensure',1,true),tostring(refused.error))
 assert(count(call..' i rejected: option-bound values require hd2.ensure')>=1)
end
local w=start({enabled=on,patch={id='ok',allow_unverified_effect=true,target=vitality_target(),
 field=hd2.fields.booster.damage_taken_scale,expect=0.9,value=vit}})
assert(w.bound and w.status=='waiting_for_options'and w.kind=='patch')
on:assign(false,'menu')
local off=start({enabled=on,patch={id='off',allow_unverified_effect=true,target=vitality_target(),
 field=hd2.fields.booster.damage_taken_scale,expect=0.9,value=vit}})
assert(off.status=='waiting_for_options')
-- Requests without options take the unchanged ensure path.
local plain=start({patch={id='plain',allow_unverified_effect=true,target=vitality_target(),
 field=hd2.fields.booster.damage_taken_scale,expect=0.9,value=0.8}})
assert(plain.bound==nil and plain.enabled==nil)
return 'ok'
''')

    def test_mods_without_options_never_touch_the_dependency(self):
        self.lua(r"""
local plain=ensure.start({},function(line)logged[#logged+1]=line end,{patch={id='plain',allow_unverified_effect=true,
 target=vitality_target(),field=hd2.fields.booster.damage_taken_scale,expect=0.9,value=0.8}})
assert(plain.bound==nil and scheduler.active()==0)
tick(10)
assert(count('Mod Options Menu')==0 and count('options ')==0)
return 'ok'
""")

    def test_dependency_present_runs_with_the_applied_values(self):
        self.lua(r"""
local page=hd2.options({id='present',title='Present'})
local value=page:slider({id='v',label='V',min=0.5,max=1,step=0.05,default=0.9})
local on=page:toggle({id='on',label='On',default=true})
local w=vitality('present',value,on)
assert(w.status=='waiting_for_options')
rawset(_G,'ModOptionsMenu',{api=1,register_option=function()return true end,
 get=function(id)return id=='present.v'and 0.7 or nil end,on_change=function()return true end})
tick(0.1)
assert(value.state=='ready'and on.state=='ready'and value:get()==0.7)
assert(w.status=='waiting'and count('unavailable')==0)
tick(0.1)
assert(w.status=='running')                       -- resolving with the saved value, not a default
return 'ok'
""")

    def test_missing_dependency_applies_declared_defaults(self):
        self.lua(r"""
local page=hd2.options({id='liberator_damage',title='Liberator Damage'})
local damage=page:slider({id='damage',label='Damage',min=0.5,max=1,step=0.05,default=0.8})
local on=page:toggle({id='enabled',label='Enabled',default=true})
local bound=vitality('liberator-damage',damage,on)
local plain=ensure.start({},function()end,{patch={id='plain',allow_unverified_effect=true,
 target=hd2.booster('Stamina Enhancement'):tuning(),field=hd2.fields.booster.stamina_scale,expect=1.3,value=1.5}})
scheduler.attach(plain)
tick(4)
assert(bound.status=='waiting_for_options')        -- inside the startup grace: nothing applied yet
tick(2)
-- The grace period ended without the menu: the operation runs its normal guarded path with the
-- declared defaults (the synthetic fixture cannot apply booster writes; the packaged
-- options-missing scenario proves the write against real memory).
assert(bound.status~='unavailable'and bound.status~='waiting_for_options'and bound.option_defaults==true)
assert(damage.state=='unavailable'and damage:get()==0.8 and damage.source=='default'and on:get()==true)
assert(damage:describe().fallback=='default')
assert(count('[HD2Runtime] options liberator_damage unavailable: Mod Options Menu is not installed; '
 ..'using configured defaults')==1)
assert(count('will not be applied')==0)
assert(plain.bound==nil and plain.status~='unavailable'and plain.status~='waiting_for_options')
-- Definitive: no re-probing and no repeated warning, even if a menu appears later.
local metrics=require('hd2runtime/runtime/metrics')
local attempts=metrics.snapshot().counters['options.registration_attempts']
rawset(_G,'ModOptionsMenu',{api=1,register_option=function()error('must not be called')end,
 get=function()end,on_change=function()end})
tick(30)
assert(count('Mod Options Menu')==1 and bound.status~='unavailable')
assert(metrics.snapshot().counters['options.registration_attempts']==attempts)
assert(metrics.snapshot().counters['options.default_operations']>=1)
-- A later declaration inherits the result immediately and also uses its default.
local late=page:slider({id='late',label='Late',min=0.5,max=1,step=0.05,default=0.9})
local late_op=vitality('late-op',late)
tick(0.1)
assert(late.state=='unavailable'and late_op.status~='unavailable'and late_op.option_defaults==true)
assert(count('options liberator_damage unavailable')==2)   -- one new warning for the new option only
return 'ok'
""")

    def test_missing_dependency_in_strict_mode_leaves_bound_operations_inactive(self):
        self.lua(r"""
local page=hd2.options({id='liberator_damage',title='Liberator Damage',fallback='disable'})
local damage=page:slider({id='damage',label='Damage',min=0.5,max=1,step=0.05,default=0.8})
local on=page:toggle({id='enabled',label='Enabled',default=true})
local bound=vitality('liberator-damage',damage,on)
local plain=ensure.start({},function()end,{patch={id='plain',allow_unverified_effect=true,
 target=hd2.booster('Stamina Enhancement'):tuning(),field=hd2.fields.booster.stamina_scale,expect=1.3,value=1.5}})
scheduler.attach(plain)
tick(4)
assert(bound.status=='waiting_for_options')        -- inside the startup grace: nothing applied
tick(2)
assert(bound.status=='unavailable'and bound.runs==0 and bound.result==nil and bound.option_defaults==nil)
assert(damage.state=='unavailable'and damage:get()==0.8 and damage:describe().fallback=='disable')
assert(count('[HD2Runtime] options liberator_damage unavailable: Mod Options Menu is not installed; '
 ..'configurable operation will not be applied (liberator-damage)')==1)
-- Untouched by option state (it applies against real memory in the packaged options-missing scenario).
assert(plain.bound==nil and plain.status~='unavailable'and plain.status~='waiting_for_options')
-- Definitive: no re-probing, no repeated warning, and the bound operation left the scheduler.
local attempts=require('hd2runtime/runtime/metrics').snapshot().counters['options.registration_attempts']
rawset(_G,'ModOptionsMenu',{api=1,register_option=function()error('must not be called')end,
 get=function()end,on_change=function()end})
tick(30)
assert(count('Mod Options Menu')==1 and bound.status=='unavailable')
assert(require('hd2runtime/runtime/metrics').snapshot().counters['options.registration_attempts']==attempts)
-- A later declaration inherits the result immediately (no second grace period).
local late=page:slider({id='late',label='Late',min=0.5,max=1,step=0.05,default=0.9})
local late_op=vitality('late-op',late)
tick(0.1)
assert(late.state=='unavailable'and late_op.status=='unavailable')
assert(count('options liberator_damage unavailable')==2)   -- one new warning for the new option only
return 'ok'
""")

    def test_incompatible_rejecting_and_failing_menus(self):
        self.lua(r"""
local page=hd2.options({id='old',title='Old'})
local v=page:slider({id='v',label='V',min=0.5,max=1,step=0.05,default=0.9})
local w=vitality('old-op',v)
rawset(_G,'ModOptionsMenu',{api=2,register_option=function()error('must not be called')end})
tick(0.1)
assert(w.status~='unavailable'and w.option_defaults==true and v.reason:find('api 2 is incompatible',1,true))
assert(count('options old unavailable: Mod Options Menu api 2 is incompatible (HD2Runtime needs api 1); '
 ..'using configured defaults')==1)
return 'ok'
""")
        self.lua(r"""
local page=hd2.options({id='fail',title='Fail',fallback='disable'})
local ok_option=page:slider({id='ok',label='Ok',min=0.5,max=1,step=0.05,default=0.9})
local refused=page:slider({id='refused',label='Refused',min=0.5,max=1,step=0.05,default=0.9})
local broken=page:slider({id='broken',label='Broken',min=0.5,max=1,step=0.05,default=0.9})
local good_op=vitality('good-op',ok_option)
local refused_op=ensure.start({},function()end,{patch={id='refused-op',allow_unverified_effect=true,
 target=hd2.booster('Stamina Enhancement'):tuning(),field=hd2.fields.booster.stamina_scale,expect=1.3,
 value=page:slider({id='stamina',label='Stamina',min=1,max=2,step=0.1,default=1.3})}})
rawset(_G,'ModOptionsMenu',{api=1,
 register_option=function(id)
  if id=='fail.refused'or id=='fail.stamina'then return false,'option already registered differently'end
  if id=='fail.broken'then error('menu went away')end
  return true end,
 get=function()return nil end,on_change=function()return true end})
tick(0.1)
assert(ok_option.state=='ready'and good_op.status=='waiting')      -- unaffected option still works
assert(refused.state=='unavailable'and refused_op.status=='unavailable')
assert(broken.state=='unavailable'and broken.reason:find('failed during registration',1,true))
assert(count('options fail unavailable')==1)                       -- one warning for the page
assert(count('option already registered differently')==1 and count('menu went away')==1)
-- The menu disappearing after it was found is definitive for later declarations.
rawset(_G,'ModOptionsMenu',nil)
local later=page:toggle({id='later',label='Later'})
tick(0.1)
assert(later.state=='unavailable'and later.reason=='Mod Options Menu is not installed')
return 'ok'
""")
        # Default mode: a rejected option uses its default, even if a saved value was read before
        # the menu refused the change callback, and the other options stay live.
        self.lua(r"""
local page=hd2.options({id='mixed',title='Mixed'})
local live=page:slider({id='live',label='Live',min=0.5,max=1,step=0.05,default=0.9})
local half=page:slider({id='half',label='Half',min=0.5,max=1,step=0.05,default=0.8})
local live_op=vitality('live-op',live)
local half_op=vitality('half-op',half)
rawset(_G,'ModOptionsMenu',{api=1,register_option=function()return true end,
 get=function(id)return id=='mixed.live'and 0.6 or 0.55 end,
 on_change=function(id)return id~='mixed.half'end})
tick(0.1)
assert(live.state=='ready'and live:get()==0.6 and live_op.option_defaults==nil)
assert(half.state=='unavailable'and half:get()==0.8 and half.source=='default'and half_op.option_defaults==true)
assert(count('options mixed unavailable: Mod Options Menu did not accept a change callback for half; '
 ..'using configured defaults')==1)
return 'ok'
""")

    def test_duplicate_declaration_is_unavailable_not_fatal(self):
        self.lua(r"""
local page=hd2.options({id='dup',title='Dup'})
local first=page:slider({id='v',label='V',min=0.5,max=1,step=0.05,default=0.9})
local second=page:slider({id='v',label='V',min=0.5,max=1,step=0.05,default=0.9})
assert(first~=second and second.state=='unavailable'and second.reason=='option v is declared twice')
assert(count('options dup unavailable: option v is declared twice; using configured defaults')==1)
local op=vitality('dup-op',second)
assert(op.status~='unavailable'and op.option_defaults==true)      -- default mode: runs with 0.9
local strict=hd2.options({id='dup_strict',title='Dup Strict',fallback='disable'})
strict:slider({id='v',label='V',min=0.5,max=1,step=0.05,default=0.9})
local strict_op=vitality('dup-strict-op',strict:slider({id='v',label='V',min=0.5,max=1,step=0.05,default=0.9}))
assert(strict_op.status=='unavailable')
rawset(_G,'ModOptionsMenu',{api=1,register_option=function()return true end,get=function()end,
 on_change=function()return true end})
tick(0.1)
assert(first.state=='ready')
return 'ok'
""")

    def test_invalid_defaults_fail_at_declaration(self):
        self.lua(r"""
local page=hd2.options({id='bad_defaults',title='Bad Defaults'})
fails(page.slider,'outside',page,{id='out',label='Out',min=0.5,max=1,step=0.05,default=2})
fails(page.slider,'on a step',page,{id='off',label='Off',min=0.5,max=1,step=0.1,default=0.55})
fails(page.toggle,'toggle default',page,{id='t',label='T',default='yes'})
fails(page.choice,'1-based',page,{id='c',label='C',choices={'A','B'},values={0.8,0.9},default=0})
-- A declared default the operation itself would reject fails when the ensure is declared, so
-- the fallback can never apply an unvalidated value. Here it is -1, outside the reviewed 0..4
-- range of the booster scale (negative values would heal).
local choice=page:choice({id='scale',label='Scale',choices={'Heal','Normal'},values={-1,0.9},default=1})
fails(vitality,'outside the reviewed range [0, 4]','bad-default-op',choice)
-- Every other value in the option's domain is proven at the same point.
local later=page:choice({id='later',label='Later',choices={'Normal','Heal'},values={0.9,-1},default=1})
fails(vitality,'value -1 is not accepted by bad-domain-op','bad-domain-op',later)
-- The acknowledgement stays mandatory for defaults too.
local ok_default=page:slider({id='fine',label='Fine',min=0.5,max=1,step=0.05,default=0.8})
fails(function()return ensure.start({},function()end,{patch={id='no-ack',target=vitality_target(),
 field=hd2.fields.booster.damage_taken_scale,expect=0.9,value=ok_default}})end,'allow_unverified_effect')
return 'ok'
""")

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
                'assert(w.bound and w.status=="waiting_for_options")\nreturn "ok"')

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

    def test_optional_dependency_metadata(self):
        import shutil
        import tempfile
        sys.path.insert(0, str(ROOT / 'sdk'))
        import hd2
        source = ROOT / 'examples/projects/LiberatorDamageOptions'
        spec = json.loads((source / 'hd2runtime.json').read_text())
        # The required contract is unchanged; the menu is declared as optional only.
        self.assertEqual(spec['requires']['bingus'], {'min_release': 15, 'api': 1})
        self.assertEqual(spec['optional'], {'mod_options_menu': {'min_version': '1.0.0', 'api': 1,
            'bingus_min_release': 18}})
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder) / 'Project'
            shutil.copytree(source, project, ignore=shutil.ignore_patterns('build'))
            import zipfile
            with zipfile.ZipFile(hd2.build_project(project)) as package:
                manifest = json.loads(package.read('manifest.json'))
                metadata = json.loads(package.read('hd2runtime.json'))
                report = json.loads(package.read('build-report.json'))
            self.assertIn('Optional: CowboyBingus Mod Options Menu v1+', manifest['Description'])
            self.assertEqual(metadata['optional'], spec['optional'])
            self.assertEqual(report['optional'], spec['optional'])
            for bad in ({'mod_options_menu': {'min_version': '1.0.0', 'api': 1, 'bingus_min_release': 16}},
                    {'other': {}}, {'mod_options_menu': {'api': 1}}):
                (project / 'hd2runtime.json').write_text(json.dumps(dict(spec, optional=bad)))
                with self.assertRaises(ValueError):
                    hd2.build_project(project)
            (project / 'hd2runtime.json').write_text(json.dumps({k: v for k, v in spec.items() if k != 'optional'}))
            with zipfile.ZipFile(hd2.build_project(project)) as package:
                self.assertNotIn('Optional', json.loads(package.read('manifest.json'))['Description'])

    def test_packaged_runtime_ships_and_exercises_options(self):
        resources = build_release.runtime_resources()
        for name in ('hd2runtime/api/options', 'hd2runtime/core/ownership'):
            self.assertIn(name, resources)
            self.assertIn(json.dumps(name), resources[build_release.PACKAGE_MODULES].decode())
        self.assertIn('options-live', validate_packaged_runtime.SCENARIOS)
        self.assertIn('options-live', validate_packaged_runtime.EXTRAS)
        self.assertIn('options-missing', validate_packaged_runtime.SCENARIOS)
        # Default fallback applies (nothing is expected inactive); strict mode keeps it inactive.
        self.assertNotIn('unavailable', validate_packaged_runtime.EXTRAS['options-missing'])
        self.assertEqual(validate_packaged_runtime.EXTRAS['options-missing-strict']['unavailable'],
            ('liberator-damage',))
        self.assertIn("fallback='disable'", validate_packaged_runtime.SCENARIOS['options-missing-strict']())
        # No dynamic module names: every internal require is a literal the static scan can resolve.
        for name in ('api/ensure.lua', 'api/options.lua', 'api/hd2.lua'):
            self.assertNotIn("require('hd2runtime/api/'..", (ROOT / name).read_text())


if __name__ == '__main__':
    unittest.main()
