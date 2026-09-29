-- In-game mod options through CowboyBingus Mod Options Menu (global `ModOptionsMenu`, api 1).
--
-- Mod Options Menu is a separate addon (it requires Bingus Shared Loader v18+). It adds a
-- MODS tab to the escape menu with toggle, choice and slider rows, applies edits when the
-- player presses APPLY, calls on_change(value, id) once per applied change, and persists
-- applied values itself. HD2Runtime adds no persistence of its own.
--
-- Options are declared at startup. Registration is deferred to the first update ticks
-- because Mod Options Menu may load before or after the declaring mod. Mod Options Menu is an
-- enhancement: without it (not installed, incompatible, or rejecting an option) each page logs
-- one warning and, with the page's default fallback='default', its operations run with the
-- declared defaults. A page declared with fallback='disable' keeps them inactive instead.
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
-- Settled by Mod Options Menu: 'pending', 'ready' or 'unavailable' (see :describe().reason).
function Handle:available()return self.state=='ready'end
-- Internal: availability listeners for bound operations.
function Handle:on_state(listener)self.state_listeners[#self.state_listeners+1]=listener end
function Handle:index()return self.kind=='choice'and self.selected or nil end
-- True when this option is unavailable and its page keeps bound operations inactive.
function Handle:disables()return self.state=='unavailable'and self.page.fallback=='disable'end
function Handle:describe()
    return {id=self.id,option=self.option,kind=self.kind,label=self.label,description=self.description,
        fallback=self.page.fallback,
        default=self.kind=='choice'and self.values[self.default]or self.default,
        value=self:get(),min=self.min,max=self.max,step=self.step,integer=self.integer,
        choices=self.choices,values=self.values,registered=self.registered,source=self.source,
        state=self.state,reason=self.reason}
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
-- Mod Options Menu is an optional dependency, resolved once per session. The result is
-- definitive: nil while unknown, true when a compatible menu is present, otherwise the reason
-- it is unusable. A missing or incompatible menu is never probed again.
local menu_result
local function compatible(menu)
    if type(menu)~='table'then return nil,'Mod Options Menu is not installed'end
    if menu.api~=1 then
        return nil,'Mod Options Menu api '..tostring(menu.api)..' is incompatible (HD2Runtime needs api 1)'
    end
    for _,name in ipairs({'register_option','get','on_change'})do
        if type(menu[name])~='function'then
            return nil,'Mod Options Menu is incompatible (missing '..name..')'
        end
    end
    return menu
end
-- Settle a handle's availability exactly once and tell the operations bound to it.
local function resolve(handle,state,reason)
    if handle.state~='pending'then return end
    handle.state,handle.reason=state,reason
    if state=='unavailable'then
        metrics.count('options.unavailable')
        handle.page.unavailable[#handle.page.unavailable+1]=handle
        -- Without the menu the declared default is the value, even if a saved value was read
        -- before registration failed. Listeners are not called: bound operations are still
        -- waiting for this availability result.
        if handle.kind=='choice'then handle.selected=handle.default else handle.current=handle.default end
        handle.source='default'
    end
    for _,listener in ipairs(handle.state_listeners)do
        local ok,why=pcall(listener,handle)
        if not ok then emit('option '..handle.id..' state listener failed: '..tostring(why))end
    end
end
-- One warning per options page. With fallback='disable' it names the operations kept inactive.
local function warn_pages()
    for _,page in pairs(pages)do
        if #page.unavailable>page.warned then
            page.warned=#page.unavailable
            local reasons,seen={},{}
            for _,handle in ipairs(page.unavailable)do
                if not seen[handle.reason]then seen[handle.reason]=true;reasons[#reasons+1]=handle.reason end
            end
            if page.fallback=='default'then
                metrics.count('options.default_fallbacks')
                emit('options '..page.id..' unavailable: '..table.concat(reasons,'; ')..'; using configured defaults')
            else
                local operations={}
                for id in pairs(page.operations)do operations[#operations+1]=id end
                table.sort(operations)
                emit('options '..page.id..' unavailable: '..table.concat(reasons,'; ')
                    ..'; configurable operation will not be applied'
                    ..(#operations>0 and' ('..table.concat(operations,', ')..')'or''))
            end
        end
    end
end
local function register(menu)
    local batch=unregistered;unregistered={}
    for _,handle in ipairs(batch)do
        metrics.count('options.registration_attempts')
        local ok,registered,why=pcall(menu.register_option,handle.id,menu_spec(handle))
        if not ok then
            resolve(handle,'unavailable','Mod Options Menu failed during registration ('..tostring(registered)..')')
        elseif not registered then
            resolve(handle,'unavailable','Mod Options Menu rejected option '..handle.option
                ..' ('..tostring(why)..')')
        else
            handle.registered=true;metrics.count('options.registered')
            -- The applied value: the saved one if valid, else the default (validated by the menu).
            local got,value=pcall(menu.get,handle.id)
            if got and value~=nil then handle:assign(value,'saved')end
            local hooked,accepted=pcall(menu.on_change,handle.id,function(new)handle:assign(new,'menu')end)
            if hooked and accepted~=false then resolve(handle,'ready')
            else resolve(handle,'unavailable','Mod Options Menu did not accept a change callback for '..handle.option)end
        end
    end
end
local function settle_pending()
    if menu_result==true then
        -- A compatible menu found earlier: register late declarations right away.
        local menu,why=compatible(rawget(_G,'ModOptionsMenu'))
        if menu then register(menu)
        else
            -- The menu went away after it was found: definitive for the rest of the session.
            menu_result=why;for _,handle in ipairs(unregistered)do resolve(handle,'unavailable',why)end
            unregistered={}
        end
    elseif menu_result then
        for _,handle in ipairs(unregistered)do resolve(handle,'unavailable',menu_result)end
        unregistered={}
    end
    warn_pages()
end
local function ensure_watch()
    if watch then return end
    local waited=0
    watch={status='waiting'}
    function watch.cancel()watch.status='cancelled'end
    function watch.tick(dt)
        if menu_result==nil then
            local present=rawget(_G,'ModOptionsMenu')
            local menu,why=compatible(present)
            waited=waited+dt
            -- A present menu is judged at once; an absent one gets the startup grace period,
            -- because it may load after the declaring mod.
            if menu then menu_result=true
            elseif present~=nil or waited>=REGISTRATION_GRACE then menu_result=why
            else return end
        end
        settle_pending()
        watch.status='complete';watch=nil
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
    local duplicate=handles[id]~=nil
    plain(spec.label,LIMITS.label,'label')
    if spec.description~=nil then plain(spec.description,LIMITS.description,'description')end
    assert(spec.gap==nil or type(spec.gap)=='boolean','option gap must be a boolean')
    assert(page.count<LIMITS.options,'Mod Options Menu shows at most '..LIMITS.options..' options per mod')
    local handle=setmetatable({id=id,option=spec.id,page=page,kind=kind,label=spec.label,
        description=spec.description,gap=spec.gap==true,listeners={},state_listeners={},state='pending',
        registered=false,source='default'},Handle)
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
        -- A choice value is a finite number, a semantic name (for example the penetration label 'medium') or a
        -- typed semantic reference handle (weapon:attack(role):projectile(), hd2.attack_output(...)); any of them,
        -- the bound ensure validates every value through the operation's normal guards when it is declared.
        for _,value in ipairs(values)do
            local reference=type(value)=='table'and getmetatable(value)~=nil and type(value.resource)=='string'
            local name=type(value)=='string'and#value>=1 and#value<=LIMITS.choice and value:match('^[%w_%-%.]+$')~=nil
            assert(reference or name or type(value)=='number'and value==value and value>-math.huge
                and value<math.huge,'choice values must be finite numbers, semantic names or semantic reference handles')
        end
        local default=spec.default==nil and 1 or spec.default
        assert(type(default)=='number'and default%1==0 and default>=1 and default<=#choices,
            'choice default must be a 1-based choice index')
        handle.choices,handle.values,handle.default,handle.selected={},{},default,default
        for index=1,#choices do handle.choices[index]=choices[index];handle.values[index]=values[index]end
    end
    if duplicate then
        -- Declared twice (in this mod or by another mod using the same ids): the menu can hold
        -- only one row per id, so the later declaration is unavailable rather than fatal.
        resolve(handle,'unavailable','option '..spec.id..' is declared twice')
        warn_pages()
        return handle
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
    local result={id=self.id,title=self.title,fallback=self.fallback,options={}}
    for _,handle in ipairs(self.order)do result.options[#result.options+1]=handle:describe()end
    return result
end

-- hd2.options({id='my-mod', title='My Mod', fallback='default'}): one options page (a MODS
-- category button). fallback says what bound operations do when Mod Options Menu is unavailable:
-- 'default' (the default) runs them with the declared defaults; 'disable' keeps them inactive.
function M.page(spec)
    assert(type(spec)=='table','options requires a descriptor')
    for key in pairs(spec)do
        assert(key=='id'or key=='title'or key=='fallback','unsupported options key: '..tostring(key))
    end
    local fallback=spec.fallback==nil and'default'or spec.fallback
    assert(fallback=='default'or fallback=='disable',"options fallback must be 'default' or 'disable'")
    assert(type(spec.id)=='string'and spec.id:match('^[%w_%-]+$')and#spec.id<=40,
        'options id must be 1 to 40 letters, digits, _ or -')
    plain(spec.title,LIMITS.title,'title')
    local existing=pages[spec.id]
    if existing then
        assert(existing.title==spec.title,'options page already declared with another title: '..spec.id)
        assert(existing.fallback==fallback,'options page already declared with another fallback: '..spec.id)
        return existing
    end
    local page=setmetatable({id=spec.id,title=spec.title,fallback=fallback,count=0,order={},unavailable={},
        warned=0,operations={}},Page)
    pages[spec.id]=page
    return page
end

-- Script values (hd2.value / mod:value): a number a mod sets from its own code (for example from an event
-- callback) and binds to one hd2.ensure field value, exactly like a slider: the ensure validates min, max, the default
-- and one step through the operation's normal guards when it is declared, and re-applies (debounced) when the value
-- changes. Never shown in Mod Options Menu; always ready.
local script_pages={}
function M.value(spec,owner)
    assert(type(spec)=='table','value requires a descriptor')
    for key in pairs(spec)do
        assert(key=='id'or key=='min'or key=='max'or key=='step'or key=='default'or key=='owner',
            'unsupported value option: '..tostring(key))
    end
    assert(type(spec.id)=='string'and spec.id:match('^[%w_%-]+$')and#spec.id<=40,
        'value id must be 1 to 40 letters, digits, _ or -')
    owner=owner or'unknown'
    local page=script_pages[owner]
    if not page then
        page={id='script:'..owner,title=owner,fallback='default',count=0,order={},unavailable={},warned=0,operations={}}
        script_pages[owner]=page
    end
    local id=owner..'.'..spec.id
    if handles[id]then return handles[id]end
    local min,max,step=spec.min,spec.max,spec.step or 1
    for _,value in ipairs({min,max,step})do
        assert(type(value)=='number'and value==value and value>-math.huge and value<math.huge,
            'value min, max and step must be finite numbers')
    end
    assert(min<max and step>0 and step<=max-min,'value needs min < max and 0 < step <= max - min')
    local handle=setmetatable({id=id,option=spec.id,page=page,kind='slider',script=true,label=spec.id,listeners={},
        state_listeners={},state='ready',registered=false,source='default',min=min,max=max,step=step},Handle)
    handle.decimals=decimals(step)
    if min%1~=0 then handle.decimals=math.max(handle.decimals,1)end
    handle.integer=handle.decimals==0
    local default=spec.default==nil and min or spec.default
    assert(type(default)=='number'and default>=min and default<=max,'value default outside min..max')
    handle.default=snap(handle,default)
    assert(handle.default==default,'value default must sit on a step')
    handle.current=handle.default
    handles[id]=handle
    return handle
end
-- Set a script value (snapped to its step, clamped to min..max). True when it changed.
function Handle:set(value)
    assert(self.script,'only script values can be set from code; menu options follow the menu')
    if type(value)~='number'or value~=value then return false end
    return self:assign(math.min(self.max,math.max(self.min,value)),'script')
end

-- Test/audit hook: forget every declaration.
function M.reset()
    if watch then watch.cancel()end
    pages,handles,unregistered,watch,menu_result={}, {},{},nil,nil
    script_pages={}
end
return M
