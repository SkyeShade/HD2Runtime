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

    def test_a_following_choice_changes_with_its_leader_and_is_proved_with_it(self):
        self.lua(r'''
local mod=hd2.mod('mods/t/editor')
-- the Liberator's empty rate slots: filling them needs the rate-of-fire selector bound in the same transaction
local liberator=hd2.weapon('AR-23 Liberator')
local info=liberator:fire_rate_modes()
assert(info.state=='addable'and info.binding,'the Liberator can take a selector')
local three={450,700,950}
local rates=mod:choice({id='rates',values={info.expect,three}})
local binding=mod:choice({id='binding',values={info.binding.expect,info.binding.value},follow=rates})
assert(binding:get()==info.binding.expect,'starts with its leader')
-- the follower cannot be set itself; the leader moves it, before any listener runs
assert(not pcall(binding.set,binding,info.binding.value))
assert(not pcall(binding.select,binding,2))
local seen
binding:subscribe(function()seen=rates:index()end)
assert(rates:set(three)==true and binding:get()==info.binding.value and seen==2,'moved with its leader')
assert(rates:select(1)==true and binding:get()==info.binding.expect)
-- values may repeat in a follower (selected by index); counts must match; only a script choice of the same mod
local again=mod:choice({id='again',values={'none','none'},follow=rates})
assert(again:get()=='none')
assert(not pcall(mod.choice,mod,{id='short',values={'none'},follow=rates}),'count')
assert(not pcall(hd2.mod('mods/t/other').choice,hd2.mod('mods/t/other'),{id='x',values={1,2},follow=rates}),'other mod')
-- proved together: rates with three slots and the binding pass as a pair
local acks={}
for _,a in ipairs(info.acknowledgements or{})do acks[a]=true end
local function request(id,b)
    local t={id=id,target=liberator,changes={
        {field=hd2.fields.fire_rate.modes,expect=info.expect,value=rates},
        {field=info.binding.field,expect=info.binding.expect,value=b}}}
    for a in pairs(acks)do t[a]=true end
    return {transaction=t,startup_delay=0}
end
local watch=bind(request('paired',binding))
assert(watch.status=='waiting_for_options'or watch.status=='waiting','bound: '..tostring(watch.status))
-- an independent binding choice is proved value by value and refused (three rates with no binding)
local loose=mod:choice({id='loose',values={info.binding.expect,info.binding.value}})
local ok,why=pcall(bind,request('loose',loose))
assert(not ok and tostring(why):find('SELECTOR_REQUIRED'),'independent choices fail: '..tostring(why))
return 'ok'
''')

    def test_every_mods_options_are_listed_with_values_and_operations(self):
        self.lua(r'''
local page=events.run_as('mods/t/menu',function()return hd2.options({id='menu_mod',title='Menu Mod'})end)
local speed=page:slider({id='speed',label='Speed',min=1,max=10,step=1,default=4})
page:toggle({id='on',label='On',default=true})
local mod=hd2.mod('mods/t/editor')
local c=mod:choice({id='c1',values={1,2}})
mod:choice({id='f1',values={'a','b'},follow=c})
local list=hd2.diagnostics.options()
local menu,script
for _,p in ipairs(list)do
    if p.id=='menu_mod'then menu=p end
    if p.kind=='script'and p.owner=='mods/t/editor'then script=p end
end
assert(menu and menu.kind=='menu'and menu.owner=='mods/t/menu'and menu.title=='Menu Mod','menu page: '..tostring(menu and menu.owner))
assert(#menu.options==2 and menu.options[1].option=='speed'and menu.options[1].value==4 and menu.options[1].max==10)
assert(script and#script.options==2 and script.options[2].follows=='c1','script values and followers')
-- an ensure bound to the page is listed with it
local bound=events.run_as('mods/t/menu',function()return bind({patch={id='speedy',target=hd2.weapon('AR-23 Liberator'),
    field='weapon.fire_rate',expect=640,value=speed},startup_delay=0})end)
local again
for _,p in ipairs(hd2.diagnostics.options())do if p.id=='menu_mod'then again=p end end
assert(again.operations[1]=='speedy','operations: '..tostring(again.operations[1]))
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


class WheelTests(unittest.TestCase):
    def test_the_wheel_combines_the_message_hook_and_the_engine_axis(self):
        self.assertEqual(run(HARNESS + r'''
local wheel=require('hd2runtime/runtime/mouse_wheel')
wheel.reset_for_tests()
local axis=0
rawset(_G,'stingray',{Mouse={axis=function()return {y=axis}end,axis_index=function(name)assert(name=='wheel')return 1 end}})
-- the native hook's counters, as the procedure accumulates them: legacy delta, raw delta, messages
local legacy,raw,count,installs,removed=0,0,0,0,false
wheel.hooks.install=function()
    installs=installs+1
    return {remove=function()removed=true end,thread=7,read=function()return legacy,raw,count end}
end
local function tick(dt)events.tick(dt or 1/60)end
assert(hd2.input.wheel()==0,'still')
assert(installs==1,'the hook is installed on the first query')
legacy=120
tick()
assert(hd2.input.wheel()==1,'a notch from WM_MOUSEWHEEL')
tick()
assert(hd2.input.wheel()==0,'one tick only')
axis=-1
tick()
assert(hd2.input.wheel()==-1,'the engine axis when the hook saw nothing')
axis=0
-- the same turn seen as raw input and as legacy messages counts once (raw wins)
legacy,raw=legacy-240,-240;tick()
assert(hd2.input.wheel()==-2,'raw input wheel, not doubled')
assert(hd2.input.wheel_status().source=='WM_MOUSEWHEEL','the first source is kept')
for _=1,90 do tick()end
assert(removed,'removed after a second without queries')
-- a failing install is retried at most every two seconds (never every frame), and an error disables it
wheel.reset_for_tests()
local attempts=0
wheel.hooks.install=function()attempts=attempts+1;return nil,'the game window does not have the focus'end
for _=1,60 do hd2.input.wheel();tick()end
assert(attempts==1,'one attempt in a second, got '..attempts)
for _=1,90 do hd2.input.wheel();tick()end
assert(attempts==2,'retried after two seconds, got '..attempts)
-- blocking: a lease renewed by every call, cleared by false and when nobody renews it for a second
wheel.reset_for_tests()
local flags,until_ms
wheel.hooks.install=function()
    return {remove=function()end,thread=7,read=function()return 0,0,0 end,blocked=function()return 3 end,
        block=function(f,u)flags,until_ms=f,u end,now=function()return 5000 end}
end
assert(hd2.input.block({keyboard=true,mouse=true})==true and flags==3 and until_ms==5500,'lease: '..tostring(until_ms))
assert(hd2.input.wheel_status().blocking==3 and hd2.input.wheel_status().blocked==3)
assert(hd2.input.block(false)==true and flags==0,'stopped')
hd2.input.block({keyboard=true})
assert(flags==1)
for _=1,90 do tick()end
assert(flags==0,'released when not renewed')
wheel.reset_for_tests()
wheel.hooks.install=function()error('boom')end
hd2.input.wheel()
assert(wheel.status().disabled:find('boom'),'disabled')
return 'ok'
'''), b'ok')

    def test_the_native_hook_procedure_counts_wheel_messages_and_always_passes_on(self):
        # The real x64 procedure, executed: GetRawInputData and CallNextHookEx are Lua callbacks on this thread.
        self.assertEqual(run(HARNESS + r'''
local ffi=require('ffi')
local wheel=require('hd2runtime/runtime/mouse_wheel')
local kernel=ffi.load('kernel32')
local alloc=ffi.cast('void *(*)(void *, size_t, uint32_t, uint32_t)',
    require('hd2runtime/runtime/windows_ffi').kernel.GetProcAddress(
    require('hd2runtime/runtime/windows_ffi').kernel.GetModuleHandleA('kernel32.dll'),'VirtualAlloc'))
local counters=ffi.cast('int32_t *',alloc(nil,4096,0x3000,0x04))
local raw_record=nil
local raw_calls,next_calls=0,{}
local raw_cb=ffi.cast('uint32_t (*)(void *, uint32_t, void *, uint32_t *, uint32_t)',function(h,command,data,size,header)
    raw_calls=raw_calls+1
    assert(command==0x10000003 and header==24 and size[0]==64,'GetRawInputData arguments')
    assert(tonumber(ffi.cast('uintptr_t',h))==0xABCD,'the message handle')
    if not raw_record then return 0xFFFFFFFF end
    ffi.copy(data,raw_record,#raw_record)
    return #raw_record
end)
local next_cb=ffi.cast('intptr_t (*)(void *, int, uintptr_t, intptr_t)',function(hook,code,wparam,lparam)
    next_calls[#next_calls+1]={hook==nil,code,tonumber(wparam)}
    return 77
end)
local clock=1000
local tick_cb=ffi.cast('uint64_t (*)(void)',function()return clock end)
local code=wheel.hook_code(tonumber(ffi.cast('uintptr_t',counters)),tonumber(ffi.cast('uintptr_t',raw_cb)),
    tonumber(ffi.cast('uintptr_t',next_cb)),tonumber(ffi.cast('uintptr_t',tick_cb)))
local lease=ffi.cast('uint64_t *',counters+4)
local page=alloc(nil,4096,0x3000,0x40)                       -- PAGE_EXECUTE_READWRITE (test only)
ffi.copy(page,code,#code)
local proc=ffi.cast('intptr_t (*)(int, uintptr_t, intptr_t)',page)
local msg=ffi.new('uint8_t[48]')
local function send(code_,remove,message,wparam,lparam)
    ffi.cast('uint32_t *',msg+8)[0]=message
    ffi.cast('uint64_t *',msg+16)[0]=wparam
    ffi.cast('uint64_t *',msg+24)[0]=lparam or 0
    return tonumber(proc(code_,remove,tonumber(ffi.cast('intptr_t',msg))))
end
-- WM_MOUSEWHEEL: HIWORD(wParam) is the signed delta
assert(send(0,1,0x020A,0x00780000)==77,'CallNextHookEx result returned')
assert(send(0,1,0x020A,0xFF880000)==77)
assert(counters[0]==0 and counters[2]==2,'+120 then -120: '..counters[0]..' '..counters[2])
assert(send(0,1,0x020A,0xFE200000)==77)
assert(counters[0]==-480,'delta -480: '..counters[0])
-- not removed (PM_NOREMOVE) or code < 0: not counted, still passed on
send(0,0,0x020A,0x00780000);send(-1,1,0x020A,0x00780000)
assert(counters[0]==-480 and #next_calls==5,'only removed messages count')
assert(next_calls[5][1]==true and next_calls[5][2]==-1 and next_calls[5][3]==1,'arguments passed on')
-- WM_INPUT: a raw mouse record with RI_MOUSE_WHEEL and delta -240
local record=ffi.new('uint8_t[48]')
ffi.cast('uint32_t *',record)[0]=0                           -- RIM_TYPEMOUSE
ffi.cast('uint16_t *',record+28)[0]=0x0400
ffi.cast('int16_t *',record+30)[0]=-240
raw_record=ffi.string(record,48)
send(0,1,0x00FF,0,0xABCD)
assert(counters[1]==-240 and counters[2]==4,'raw delta: '..counters[1])
-- a keyboard record, a mouse record without the wheel flag, and an error are ignored
ffi.cast('uint32_t *',record)[0]=1;raw_record=ffi.string(record,48);send(0,1,0x00FF,0,0xABCD)
ffi.cast('uint32_t *',record)[0]=0;ffi.cast('uint16_t *',record+28)[0]=0x0001;raw_record=ffi.string(record,48)
send(0,1,0x00FF,0,0xABCD)
raw_record=nil;send(0,1,0x00FF,0,0xABCD)
assert(counters[1]==-240 and counters[2]==4 and raw_calls==4,'ignored records')
-- other messages never call GetRawInputData
send(0,1,0x0200,0,0xABCD)
assert(raw_calls==4 and #next_calls==10,'other messages pass straight on')
-- blocking: nothing is blocked without flags
local function message()return ffi.cast('uint32_t *',msg+8)[0]end
send(0,1,0x0100,0x2E,0);assert(message()==0x0100 and counters[6]==0,'no flags: a key press passes')
-- keyboard flag with a live lease: presses and characters become WM_NULL, releases pass
counters[3]=1;lease[0]=1500
send(0,1,0x0100,0x2E,0);assert(message()==0,'WM_KEYDOWN blocked')
send(0,1,0x0102,0x41,0);assert(message()==0,'WM_CHAR blocked')
send(0,1,0x0101,0x2E,0);assert(message()==0x0101,'WM_KEYUP passes')
send(0,1,0x0201,0,0);assert(message()==0x0201,'mouse not asked: a click passes')
-- raw keyboard: a make is blocked, a break passes
ffi.cast('uint32_t *',record)[0]=1;ffi.cast('uint16_t *',record+26)[0]=0;raw_record=ffi.string(record,48)
send(0,1,0x00FF,0,0xABCD);assert(message()==0,'raw key make blocked')
ffi.cast('uint16_t *',record+26)[0]=1;raw_record=ffi.string(record,48)
send(0,1,0x00FF,0,0xABCD);assert(message()==0x00FF,'raw key break passes')
-- the lease runs out: nothing is blocked
clock=2000
send(0,1,0x0100,0x2E,0);assert(message()==0x0100,'an expired lease blocks nothing')
-- mouse flag: button presses and the wheel (still counted) are blocked; movement passes
counters[3]=2;lease[0]=2500
send(0,1,0x0201,0,0);assert(message()==0,'WM_LBUTTONDOWN blocked')
send(0,1,0x0202,0,0);assert(message()==0x0202,'WM_LBUTTONUP passes')
local w0=counters[0]
send(0,1,0x020A,0x00780000);assert(message()==0 and counters[0]==w0+120,'the wheel counted, then blocked')
ffi.cast('uint32_t *',record)[0]=0;ffi.cast('uint16_t *',record+28)[0]=0x0004;raw_record=ffi.string(record,48)
send(0,1,0x00FF,0,0xABCD);assert(message()==0,'a raw right-button press blocked')
ffi.cast('uint16_t *',record+28)[0]=0;raw_record=ffi.string(record,48)
send(0,1,0x00FF,0,0xABCD);assert(message()==0x00FF,'raw movement passes')
send(0,1,0x0200,0,0);assert(message()==0x0200,'WM_MOUSEMOVE passes')
assert(counters[6]==6,'blocked count: '..counters[6])
counters[3]=0
-- the shipped pages: real GetRawInputData and CallNextHookEx, an execute-read code page, called directly
local pages=wheel.pages()
assert(wheel.pages()==pages,'allocated once')
local real=ffi.cast('intptr_t (*)(int, uintptr_t, intptr_t)',pages.code)
ffi.cast('uint32_t *',msg+8)[0]=0x020A
ffi.cast('uint64_t *',msg+16)[0]=0x00F00000
local before=pages.counters[0]
real(0,1,tonumber(ffi.cast('intptr_t',msg)))
assert(pages.counters[0]-before==240,'the shipped procedure counts')
ffi.cast('uint32_t *',msg+8)[0]=0x00FF
ffi.cast('uint64_t *',msg+24)[0]=0                           -- invalid HRAWINPUT: GetRawInputData fails, ignored
real(0,1,tonumber(ffi.cast('intptr_t',msg)))
assert(pages.counters[1]==0,'a failed raw read is ignored')
return 'ok'
'''), b'ok')


if __name__ == '__main__':
    unittest.main()
