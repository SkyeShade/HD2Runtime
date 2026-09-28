-- In-game mod options through CowboyBingus Mod Options Menu (global `ModOptionsMenu`, api 1).
--
-- Mod Options Menu is a separate addon (it requires Bingus Shared Loader v18+). It adds a
-- MODS tab to the escape menu with toggle, choice and slider rows, applies edits when the
-- player presses APPLY, calls on_change(value, id) once per applied change, and persists
-- applied values itself. HD2Runtime adds no persistence of its own.
--
-- Options are declared at startup. Registration is deferred to the first update ticks
-- because Mod Options Menu may load before or after the declaring mod. Without it (not
-- installed, or older), every option keeps its default and nothing else changes.
local metrics=require('hd2runtime/runtime/metrics')
local log=require('hd2runtime/runtime/log')
local scheduler=require('hd2runtime/runtime/scheduler')
local M={}
-- Mod Options Menu v1 limits, checked here so a bad declaration fails at startup.
local LIMITS={id=96,label=64,title=40,description=400,choices=16,choice=48,decimals=3,mods=8,options=32}
local REGISTRATION_GRACE=5 -- update seconds to wait for Mod Options Menu to appear
local Handle={};Handle.__index=Handle
local pages,handles,unregistered={}, {},{}
local watch

local function emit(message)pcall(log.emit,'[HD2Runtime] '..message)end
local function plain(value,limit,name)
    assert(type(value)=='string'and value:find('%S')and#value<=limit and not value:find('[%c]'),
        'option '..name..' must be plain text of 1 to '..limit..' bytes')
end
local function decimals(step)
    for places=0,LIMITS.decimals do
        local scaled=step*10^places
        if math.abs(scaled-math.floor(scaled+0.5))<=1e-6 then return places end
    end
    error('slider step needs at most '..LIMITS.decimals..' decimal places',0)
end
-- Same snapping as Mod Options Menu, so both sides agree on every value.
local function snap(handle,value)
    local steps=math.floor((value-handle.min)/handle.step+0.5)
    local snapped=math.min(handle.max,math.max(handle.min,handle.min+steps*handle.step))
    return tonumber(string.format('%.'..handle.decimals..'f',snapped))
end
-- A value from the menu or its saved file: normalised, or nil when unusable.
local function normalize(handle,value)
    if handle.kind=='toggle'then
        if type(value)=='boolean'then return value end
        return nil
    end
    if type(value)~='number'or value~=value or value==math.huge or value==-math.huge then return nil end
    if handle.kind=='choice'then
        return (value%1==0 and value>=1 and value<=#handle.choices)and value or nil
    end
    return snap(handle,value)
end

function Handle:get()
    if self.kind=='choice'then return self.values[self.selected]end
    return self.current
end
function Handle:index()return self.kind=='choice'and self.selected or nil end
function Handle:describe()
    return {id=self.id,option=self.option,kind=self.kind,label=self.label,description=self.description,
        default=self.kind=='choice'and self.values[self.default]or self.default,
        value=self:get(),min=self.min,max=self.max,step=self.step,integer=self.integer,
        choices=self.choices,values=self.values,registered=self.registered,source=self.source}
end
-- Internal: listeners run only when the value actually changes.
function Handle:subscribe(listener)self.listeners[#self.listeners+1]=listener end
function Handle:assign(value,source)
    local normalized=normalize(self,value)
    if normalized==nil then
        metrics.count('options.rejected_values')
        emit('option '..self.id..' ignored an invalid '..source..' value; keeping '..tostring(self:get()))
        return false
    end
    local key=self.kind=='choice'and'selected'or'current'
    if self[key]==normalized then metrics.count('options.noop_changes');self.source=source;return false end
    self[key]=normalized;self.source=source
    metrics.count('options.changes')
    for _,listener in ipairs(self.listeners)do
        local ok,why=pcall(listener,self)
        if not ok then emit('option '..self.id..' listener failed: '..tostring(why))end
    end
    return true
end
-- Values an operation must accept across the option's whole domain (validated at bind time).
function Handle:samples()
    if self.kind=='choice'then return self.values end
    if self.kind=='toggle'then return {false,true}end
    local result={self.min,self.max,self.default}
    if self.min+self.step<self.max then result[#result+1]=snap(self,self.min+self.step)end
    return result
end
function M.is_handle(value)return getmetatable(value)==Handle end
-- True when a request contains any option handle (target objects are not searched).
function M.contains(value,depth)
    if getmetatable(value)==Handle then return true end
    if type(value)~='table'or getmetatable(value)~=nil or(depth or 0)>16 then return false end
    for _,item in pairs(value)do if M.contains(item,(depth or 0)+1)then return true end end
    return false
end

local function menu_spec(handle)
    local spec={type=handle.kind,label=handle.label,mod=handle.page.title,description=handle.description,
        gap=handle.gap or nil}
    if handle.kind=='toggle'then spec.default=handle.default
    elseif handle.kind=='choice'then spec.choices=handle.choices;spec.default=handle.default
    else spec.min=handle.min;spec.max=handle.max;spec.step=handle.step;spec.default=handle.default end
    return spec
end
local function register(menu)
    for _,handle in ipairs(unregistered)do
        local ok,registered,why=pcall(menu.register_option,handle.id,menu_spec(handle))
        if ok and registered then
            handle.registered=true;metrics.count('options.registered')
            -- The applied value: the saved one if valid, else the default (validated by the menu).
            local got,value=pcall(menu.get,handle.id)
            if got and value~=nil then handle:assign(value,'saved')end
            pcall(menu.on_change,handle.id,function(new)handle:assign(new,'menu')end)
        else
            emit('option '..handle.id..' not registered: '..tostring(ok and why or registered)
                ..'; it keeps value '..tostring(handle:get()))
        end
    end
    unregistered={}
end
local function ensure_watch()
    if watch then return end
    local waited=0
    watch={status='waiting'}
    function watch.cancel()watch.status='cancelled'end
    function watch.tick(dt)
        local menu=rawget(_G,'ModOptionsMenu')
        if type(menu)=='table'and menu.api==1 and type(menu.register_option)=='function'then
            register(menu)
            local ready=type(menu.ready)=='function'and menu.ready()
            emit('Mod Options Menu found; options registered'..(ready and''or
                ' (menu integration inactive on this game build; values stay at saved/defaults)'))
            watch.status='complete';watch=nil;return
        end
        waited=waited+dt
        if waited>=REGISTRATION_GRACE then
            emit('Mod Options Menu not installed (needs Mod Options Menu v1+ and Bingus Shared Loader v18+); '
                ..#unregistered..' option(s) keep their defaults')
            unregistered={};watch.status='complete';watch=nil
        end
    end
    scheduler.attach(watch)
end

local Page={};Page.__index=Page
local function option(page,kind,spec)
    assert(type(spec)=='table','option requires a descriptor')
    local allowed={id=true,label=true,description=true,default=true,gap=true}
    if kind=='slider'then allowed.min=true;allowed.max=true;allowed.step=true end
    if kind=='choice'then allowed.choices=true;allowed.values=true end
    for key in pairs(spec)do assert(allowed[key],'unsupported '..kind..' option: '..tostring(key))end
    assert(type(spec.id)=='string'and spec.id:match('^[%w_%-]+$'),'option id must use letters, digits, _ or -')
    local id=page.id..'.'..spec.id
    assert(#id<=LIMITS.id,'option id too long')
    assert(not handles[id],'option already declared: '..id)
    plain(spec.label,LIMITS.label,'label')
    if spec.description~=nil then plain(spec.description,LIMITS.description,'description')end
    assert(spec.gap==nil or type(spec.gap)=='boolean','option gap must be a boolean')
    assert(page.count<LIMITS.options,'Mod Options Menu shows at most '..LIMITS.options..' options per mod')
    local handle=setmetatable({id=id,option=spec.id,page=page,kind=kind,label=spec.label,
        description=spec.description,gap=spec.gap==true,listeners={},registered=false,source='default'},Handle)
    if kind=='toggle'then
        assert(spec.default==nil or type(spec.default)=='boolean','toggle default must be a boolean')
        handle.default=spec.default==true;handle.current=handle.default
    elseif kind=='slider'then
        local min,max,step=spec.min,spec.max,spec.step or 1
        for _,value in ipairs({min,max,step})do
            assert(type(value)=='number'and value==value and value>-math.huge and value<math.huge,
                'slider min, max and step must be finite numbers')
        end
        assert(min<max and step>0 and step<=max-min,'slider needs min < max and 0 < step <= max - min')
        handle.min,handle.max,handle.step=min,max,step
        handle.decimals=decimals(step)
        if min%1~=0 then handle.decimals=math.max(handle.decimals,1)end
        handle.integer=handle.decimals==0
        local default=spec.default==nil and min or spec.default
        assert(type(default)=='number'and default>=min and default<=max,'slider default outside min..max')
        handle.default=snap(handle,default)
        assert(handle.default==default,'slider default must sit on a step')
        handle.current=handle.default
    else
        local choices=spec.choices
        assert(type(choices)=='table'and#choices>=2 and#choices<=LIMITS.choices,
            'choice needs 2 to '..LIMITS.choices..' choices')
        for _,name in ipairs(choices)do plain(name,LIMITS.choice,'choice')end
        local values=spec.values
        if values==nil then values={};for index=1,#choices do values[index]=index end end
        assert(type(values)=='table'and#values==#choices,'choice values must list one value per choice')
        for _,value in ipairs(values)do
            assert(type(value)=='number'and value==value and value>-math.huge and value<math.huge,
                'choice values must be finite numbers')
        end
        local default=spec.default==nil and 1 or spec.default
        assert(type(default)=='number'and default%1==0 and default>=1 and default<=#choices,
            'choice default must be a 1-based choice index')
        handle.choices,handle.values,handle.default,handle.selected={},{},default,default
        for index=1,#choices do handle.choices[index]=choices[index];handle.values[index]=values[index]end
    end
    page.count=page.count+1;page.order[#page.order+1]=handle
    handles[id]=handle;unregistered[#unregistered+1]=handle
    ensure_watch()
    return handle
end
function Page:toggle(spec)return option(self,'toggle',spec)end
function Page:slider(spec)return option(self,'slider',spec)end
function Page:choice(spec)return option(self,'choice',spec)end
function Page:describe()
    local result={id=self.id,title=self.title,options={}}
    for _,handle in ipairs(self.order)do result.options[#result.options+1]=handle:describe()end
    return result
end

-- hd2.options({id='my-mod', title='My Mod'}): one options page (a MODS category button).
function M.page(spec)
    assert(type(spec)=='table','options requires a descriptor')
    for key in pairs(spec)do assert(key=='id'or key=='title','unsupported options key: '..tostring(key))end
    assert(type(spec.id)=='string'and spec.id:match('^[%w_%-]+$')and#spec.id<=40,
        'options id must be 1 to 40 letters, digits, _ or -')
    plain(spec.title,LIMITS.title,'title')
    local existing=pages[spec.id]
    if existing then
        assert(existing.title==spec.title,'options page already declared with another title: '..spec.id)
        return existing
    end
    local page=setmetatable({id=spec.id,title=spec.title,count=0,order={}},Page)
    pages[spec.id]=page
    return page
end

-- Test/audit hook: forget every declaration.
function M.reset()
    if watch then watch.cancel()end
    pages,handles,unregistered,watch={}, {},{},nil
end
return M
