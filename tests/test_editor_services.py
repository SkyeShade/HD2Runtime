"""Services for in-game editors (HD2Runtime Editor, r50): script choices (mod:choice) bound to any field value through
hd2.ensure's bind-time proof, the registering mod named for mods built without the SDK wrapper's run_as scope, and the
overlay's cursor capture against a recording fake of the engine Window API."""
import unittest

from support import run

HARNESS = r'''
local logged={}
require('hd2runtime/runtime/log').emit=function(line)logged[#logged+1]=line end
local events=require('hd2runtime/runtime/events')
events.reset_for_tests()
local options=require('hd2runtime/api/options')
options.reset()
local hd2=require('hd2runtime/api/hd2')
local ensure=require('hd2runtime/api/ensure')
local function bind(request)return ensure.start({},function()end,request)end
'''


class ScriptChoiceTests(unittest.TestCase):
    def lua(self, body):
        self.assertEqual(run(HARNESS + body), b'ok')

    def test_a_choice_binds_whole_values_and_selects_by_value(self):
        self.lua(r'''
local mod=hd2.mod('mods/t/editor')
-- calldown codes are plain lists: copied at declaration and on every get
local native={'right','right','up'}
local code=mod:choice({id='code',values={native,{'up','down','up'}},default=1})
assert(code.kind=='choice'and code.script and code.state=='ready')
native[1]='left'
assert(code:get()[1]=='right','declared values are copies')
local got=code:get();got[2]='left'
assert(code:get()[2]=='right','get returns a copy')
-- the bind-time proof validates every value through the stratagem writer
local watch=bind({patch={id='code',target=hd2.stratagem('Orbital Precision Strike'),
    field=hd2.fields.stratagem.calldown_code,expect={'right','right','up'},value=code},startup_delay=0})
assert(watch.status=='waiting_for_options'or watch.status=='waiting','bound: '..tostring(watch.status))
-- select by value (deep equal), by index, and refuse a value outside the domain
assert(code:set({'up','down','up'})==true and code:get()[2]=='down')
assert(code:set({'up','down','up'})==false,'no change')
assert(code:select(1)==true and code:get()[1]=='right')
assert(code:set({'left'})==false,'not one of its values')
-- mission uses: a number and the string 'unlimited' in one choice
local uses=mod:choice({id='uses',values={'unlimited',3},labels={'Unlimited','3'}})
assert(uses.choices[1]=='Unlimited'and uses:set(3)and uses:get()==3)
-- references: typed handles compare by identity, not by table address
local w=hd2.weapon('AR-23 Liberator')
local own=w:attack('primary'):projectile()
local projectile=mod:choice({id='proj',values={own}})
assert(projectile:set(hd2.weapon('AR-23 Liberator'):attack('primary'):projectile())==false,'already selected')
assert(options.same(own,hd2.weapon('AR-23 Liberator'):attack('primary'):projectile()))
assert(not options.same(own,hd2.weapon('AR-23A Liberator Carbine'):attack('primary'):projectile()))
-- the same id returns the same choice; a slider id cannot be reused as a choice
assert(mod:choice({id='code',values={{'up'}}})==code)
mod:value({id='slider',min=0,max=10})
assert(not pcall(mod.choice,mod,{id='slider',values={1}}))
-- duplicates and bad values are refused at declaration
assert(not pcall(mod.choice,mod,{id='dup',values={{'up'},{'up'}}}),'duplicate values')
assert(not pcall(mod.choice,mod,{id='fn',values={function()end}}),'functions are not values')
return 'ok'
''')

    def test_a_value_the_field_refuses_fails_the_bind_with_a_readable_value(self):
        self.lua(r'''
local mod=hd2.mod('mods/t/editor')
-- a code equal to another stratagem's native code needs allow_unverified_effect: refused at bind time
local calldown=require('hd2runtime/domains/stratagem_calldown')
local other
for _,code in pairs(calldown.nativeCodes or{})do
    if type(code)=='table'and table.concat(code,',')~='right,right,up'then other=code;break end
end
assert(other,'a native code to clash with')
local code=mod:choice({id='clash',values={{'right','right','up'},other}})
local ok,why=pcall(bind,{patch={id='clash',target=hd2.stratagem('Orbital Precision Strike'),
    field=hd2.fields.stratagem.calldown_code,expect={'right','right','up'},value=code}})
assert(not ok,'refused without the acknowledgement')
assert(tostring(why):find('{',1,true)and not tostring(why):find('table: ',1,true),'the value is shown, not an address: '..tostring(why))
return 'ok'
''')

    def test_the_registering_mod_is_named_without_a_run_as_scope(self):
        self.lua(r'''
local shared=require('hd2runtime/core/shared_records')
local compat=require('hd2runtime/core/sdk_compatibility')
assert(shared.current_mod()=='unknown','no scope, no origin')
local mod=compat.with_origin({mod='mods/t/legacy',sdk='0.27.0',pending={},logged={}},function()return shared.current_mod()end)
assert(mod=='mods/t/legacy','the registration origin names the mod: '..tostring(mod))
-- a run_as scope still wins
local scoped=events.run_as('mods/t/scoped',function()
    return compat.with_origin({mod='mods/t/legacy',pending={},logged={}},function()return shared.current_mod()end)
end)
assert(scoped=='mods/t/scoped')
-- a mods/... chunk on the stack (a template-built mod's main chunk)
-- (not a tail call: a mod's main chunk stays on the stack while it registers)
local chunk=assert(loadstring('local m=require("hd2runtime/core/shared_records").current_mod() return m','@mods/t/chunk'))
assert(chunk()=='mods/t/chunk')
local runtime=assert(loadstring('local m=require("hd2runtime/core/shared_records").current_mod() return m','@mods/skyeshade/hd2runtime'))
assert(runtime()=='unknown','the Runtime library is never a mod')
return 'ok'
''')


class CursorTests(unittest.TestCase):
    def test_a_shown_overlay_frees_the_cursor_and_gives_it_back(self):
        self.assertEqual(run(HARNESS + r'''
local state={show_cursor=false,clip_cursor=true,mouse_focus=true}
local writes={}
local W={}
for name in pairs(state)do
    W[name]=function(...)assert(select('#',...)==0,'getters take no argument');return state[name]end
    W['set_'..name]=function(v,...)
        assert(type(v)=='boolean'and select('#',...)==0,'setters take one boolean')
        writes[#writes+1]=name..'='..tostring(v);state[name]=v
    end
end
rawset(_G,'stingray',{Window=W})
local cursor=require('hd2runtime/runtime/mod_cursor')
cursor.reset_for_tests()
assert(cursor.hold('a'))
assert(state.show_cursor==true and state.clip_cursor==false and state.mouse_focus==false,'freed')
local n=#writes
assert(cursor.hold('a')and#writes==n,'a frame with nothing to change writes nothing')
state.show_cursor=false
cursor.hold('a')
assert(state.show_cursor==true and#writes==n+1,'re-asserted when the game takes it back')
assert(cursor.hold('b',{camera=false}))
cursor.release('a')
assert(state.show_cursor==true,'still held by b')
cursor.release('b')
assert(state.show_cursor==false and state.clip_cursor==true and state.mouse_focus==true,'the saved values restored')
-- an engine error disables the feature for the session and restores what was changed
W.set_show_cursor=function()error('boom')end
local ok,why=cursor.hold('c')
assert(not ok and tostring(why):find('boom'),'disabled: '..tostring(why))
assert(not cursor.hold('c'),'stays disabled')
assert(cursor.status().disabled)
return 'ok'
'''), b'ok')


if __name__ == '__main__':
    unittest.main()
