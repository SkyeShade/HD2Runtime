-- Event engine: one scheduler watch drives the game clock, timers, input polling, native event sources and
-- dispatch. See docs/events.md.
--
-- * Dispatch is deterministic: subscribers run by priority (higher first), then in subscription order.
-- * Every callback runs isolated (xpcall). A failure is logged with the owning mod, the event and the error; other
--   subscribers still run. A subscription that fails max_failures times in a row is disabled (logged).
-- * Subscriber lists are copy-on-write: subscribing or unsubscribing while an event dispatches never changes the
--   list being dispatched, and dispatch allocates nothing per subscriber.
-- * Events observed in one update tick are queued and dispatched after every source has been polled, in source
--   order, so a callback that acts (heals, spawns) cannot change what the same tick observes.
-- * Mission scope: mission_ended runs first, then mission-scoped subscriptions, timers and state are cleared and
--   every handle from that mission becomes invalid (the mission epoch advances).
-- * Causes: every event carries `cause`. Native gameplay is {source='native'}. An action a mod performs through
--   Runtime records the mod and the event it reacted to; events Runtime can prove that action produced carry
--   {source='mod', mod=..., action=..., depth=n}. Actions refuse to run past MAX_CAUSE_DEPTH (recursion guard).
--
-- The engine is a process-wide singleton (anchored in _G) so a repeated require never duplicates it.
local KEY='HD2RuntimeEventsV1'
local existing=rawget(_G,KEY)
if existing then return existing end
local scheduler=require('hd2runtime/runtime/scheduler')
local metrics=require('hd2runtime/runtime/metrics')
local log=require('hd2runtime/runtime/log')
local perf=require('hd2runtime/runtime/perf_watch')
local catalog=require('hd2runtime/domains/events_catalog')

local M={}
rawset(_G,KEY,M)
local DEFAULT_MAX_FAILURES=25     -- consecutive callback failures before a subscription is disabled
local LOGGED_FAILURES=3           -- failures logged in full per subscription; then every 100th
local MAX_DISPATCH_DEPTH=8        -- nested dispatch (an internal event emitted from a callback)
M.MAX_CAUSE_DEPTH=4               -- actions caused by mod-caused events, at most this deep
M.MIN_REPEAT=0.05                 -- smallest hd2.every interval (seconds)
M.NATIVE={source='native'}        -- the shared cause of native gameplay events (read-only by convention)

local state={now=0,frame=0,epoch=0,in_mission=false,sequence=0,depth=0,current=nil,
    lists={},by_key={},timers={},timer_keys={},queue={},queue_count=0,sources={},source_order={},
    contexts={},mission_tables={},watch=nil,pollers={},scopes={},frames={}}
M.state=state

local function emit(message)pcall(log.emit,'[HD2Runtime] '..message)end
M.emit_log=emit
-- The error text, plus the first frame outside Runtime when the error carries no position of its own.
local function traceback(message)
    local text=tostring(message)
    if text:find(':%d+:')then return text end
    local trace=debug and debug.traceback and debug.traceback('',2)or''
    for line in trace:gmatch('[^\n]+')do
        line=line:gsub('^%s+','')
        if line~='stack traceback:'and not(line:find('hd2runtime',1,true)and line:find('/runtime/',1,true))and not line:find('[C]',1,true)then
            return text..' ['..line..']'
        end
    end
    return text
end

-- Owner identity, most specific first:
--   1. an explicit owner (opts.owner, a mod context's id);
--   2. the mod scope entered with run_as (the SDK addon wrapper runs a mod's startup inside its own resource id);
--   3. the mod whose callback, timer or keybind is running now (registrations made from inside a callback);
--   4. the calling chunk when it is a mod resource ('mods/author/name');
--   5. 'unknown'.
local function valid_owner(owner)
    return type(owner)=='string'and#owner>0 and#owner<=128 and not owner:find('[%c]')
end
function M.owner(explicit,level)
    if explicit~=nil then
        assert(valid_owner(explicit),'owner must be a mod id string')
        return explicit
    end
    local scope=state.scopes[#state.scopes]
    if scope then return scope end
    local current=state.current and state.current.owner
    if current and current~='unknown'then return current end
    local info=debug and debug.getinfo and debug.getinfo((level or 2)+1,'S')
    local source=info and info.source or''
    source=source:gsub('^[@=]',''):gsub('%.lua$','')
    if source:match('^mods/[%w_/]+$')then return source end
    return 'unknown'
end
-- Run fn(...) with `owner` as the mod every registration inside it belongs to (nested scopes stack). Errors
-- propagate after the scope is left.
-- Timed per mod (runtime/perf_watch.lua): a mod's main file, custom stratagem and Pelican callbacks run here.
local function describe_function(fn)
    local info=debug and debug.getinfo and debug.getinfo(fn,'S')
    if not info then return 'a function'end
    if info.what=='main'then return 'its main file ('..tostring(info.short_src)..')'end
    return 'the function at '..tostring(info.short_src)..':'..tostring(info.linedefined)
end
function M.run_as(owner,fn,...)
    assert(valid_owner(owner),'run_as needs a mod id string')
    assert(type(fn)=='function','run_as needs a function')
    local scopes=state.scopes
    scopes[#scopes+1]=owner
    local depth=#scopes
    local timed=perf.begin()
    local results={pcall(fn,...)}
    perf.finish(timed,owner,fn,describe_function)
    for index=#scopes,depth,-1 do scopes[index]=nil end
    if not results[1]then error(results[2],0)end
    return unpack(results,2,table.maxn(results))
end

---------------------------------------------------------------------------------------------------- the watch --
local function needed()
    if next(state.by_key)or#state.timers>0 or#state.frames>0 or next(state.pollers)then return true end
    for _,source in ipairs(state.source_order)do
        if source.active or(source.status=='retry'and source_wanted and source_wanted(source))then return true end
    end
    return false
end
local tick,source_wanted
local function ensure_watch()
    if state.watch and state.watch.status=='waiting'then return end
    local watch={status='waiting'}
    function watch.cancel()watch.status='cancelled'end
    function watch.tick(dt)
        tick(dt)
        if not needed()then watch.status='complete';if state.watch==watch then state.watch=nil end end
    end
    state.watch=watch
    scheduler.attach(watch)
end
M.ensure_watch=ensure_watch

------------------------------------------------------------------------------------------------ subscriptions --
local Subscription={};Subscription.__index=Subscription
local function rebuild(name)
    local fresh={}
    for _,sub in pairs(state.by_key)do if sub.event==name then fresh[#fresh+1]=sub end end
    table.sort(fresh,function(a,b)
        if a.priority~=b.priority then return a.priority>b.priority end
        return a.seq<b.seq
    end)
    state.lists[name]=#fresh>0 and fresh or nil
    local source=catalog.events[name]and state.sources[catalog.events[name].source]
    if source then M.refresh_source(source)end
end
local function remove(sub,status)
    if state.by_key[sub.key]~=sub then return end
    state.by_key[sub.key]=nil
    sub.state=status or'removed'
    rebuild(sub.event)
end
function Subscription:unsubscribe()remove(self,'removed');return self end
function Subscription:disable()if self.state=='active'then self.state='disabled'end;return self end
function Subscription:enable()
    if self.state=='disabled'or self.state=='failed'then self.state='active';self.consecutive=0 end
    return self
end
function Subscription:active()return self.state=='active'end
function Subscription:describe()
    return {id=self.id,event=self.event,owner=self.owner,priority=self.priority,scope=self.scope,state=self.state,
        calls=self.calls,failures=self.failures,reason=self.reason,once=self.once}
end

-- A refused registration: logged, returned as an inert handle, never raised (one bad call cannot abort a mod).
local function refused(event,owner,why)
    local message=tostring(why):gsub('^[^%s:]+:%d+: ','')
    emit('event subscription '..tostring(event)..' ('..tostring(owner)..') rejected: '..message)
    metrics.count('events.rejected_subscriptions')
    return setmetatable({id=nil,event=event,owner=owner,state='rejected',reason=message,calls=0,failures=0,
        priority=0,seq=0},Subscription)
end
M.refused=refused

function M.subscribe(name,callback,opts,level)
    opts=opts or{}
    local ok,owner=pcall(M.owner,opts.owner,(level or 1)+1)
    if not ok then return refused(name,opts.owner,owner)end
    local valid,why=pcall(function()
        assert(type(name)=='string','event name must be a string')
        local spec=catalog.events[name]
        assert(spec,'unknown event '..name..' (known: '..table.concat(catalog.names,', ')..')')
        assert(spec.status~='blocked','EVENT_BLOCKED: '..name..' is not available: '..tostring(spec.reason))
        assert(type(callback)=='function','event callback must be a function')
        assert(opts.priority==nil or(type(opts.priority)=='number'and opts.priority%1==0
            and math.abs(opts.priority)<=1000),'priority must be an integer from -1000 to 1000')
        assert(opts.scope==nil or opts.scope=='session'or opts.scope=='mission',"scope must be 'session' or 'mission'")
        assert(opts.id==nil or(type(opts.id)=='string'and opts.id:match('^[%w_%.%-]+$')and#opts.id<=64),
            'subscription id must be 1 to 64 letters, digits, _ . -')
        assert(opts.max_failures==nil or(type(opts.max_failures)=='number'and opts.max_failures>=0
            and opts.max_failures%1==0),'max_failures must be a non-negative integer')
    end)
    if not valid then return refused(name,owner,why)end
    state.sequence=state.sequence+1
    -- An id makes registration idempotent per owner and event: running a mod's startup again replaces the callback
    -- of the same subscription instead of adding a second one.
    local key=opts.id and(owner..'|'..name..'|'..opts.id)or('#'..state.sequence)
    local sub=state.by_key[key]
    if sub then
        sub.callback=callback;sub.priority=opts.priority or 0;sub.state='active';sub.consecutive=0
        sub.max_failures=opts.max_failures or DEFAULT_MAX_FAILURES
        rebuild(name)
        return sub
    end
    sub=setmetatable({id=state.sequence,seq=state.sequence,key=key,event=name,owner=owner,callback=callback,
        priority=opts.priority or 0,scope=opts.scope or'session',epoch=state.epoch,once=opts.once==true,
        max_failures=opts.max_failures or DEFAULT_MAX_FAILURES,state='active',calls=0,failures=0,consecutive=0},
        Subscription)
    state.by_key[key]=sub
    rebuild(name)
    ensure_watch()
    metrics.count('events.subscriptions')
    return sub
end

-- Every subscription, for diagnostics.
function M.subscriptions(filter)
    local result={}
    for _,sub in pairs(state.by_key)do
        if(not filter or not filter.owner or filter.owner==sub.owner)and(not filter or not filter.event
            or filter.event==sub.event)then result[#result+1]=sub:describe()end
    end
    table.sort(result,function(a,b)return a.id<b.id end)
    return result
end

--------------------------------------------------------------------------------------------------- dispatch --
-- Runs `fn(a)` isolated as `record` (a subscription, timer or binding) handling `event` (the event being dispatched,
-- or the event a timer's creator was handling). Returns true when it completed.
local function describe_record(record)return tostring(record.perf_what)..' ('..tostring(record.label)..')'end
local function invoke(record,what,fn,a,event)
    local previous,previous_event=state.current,state.current_event
    state.current,state.current_event=record,event
    record.perf_what=what
    local timed=perf.begin()
    local ok,why=xpcall(fn,traceback,a)
    perf.finish(timed,record.owner,record,describe_record)
    state.current,state.current_event=previous,previous_event
    record.calls=record.calls+1
    if ok then record.consecutive=0;return true end
    record.failures=record.failures+1;record.consecutive=record.consecutive+1
    metrics.count('events.callback_failures')
    if record.failures<=LOGGED_FAILURES or record.failures%100==0 then
        emit(what..' callback failed (mod '..record.owner..', '..record.label..'): '..tostring(why)
            ..(record.failures>LOGGED_FAILURES and(' ['..record.failures..' failures]')or''))
    end
    if record.max_failures>0 and record.consecutive>=record.max_failures and record.state=='active'then
        record.state='failed'
        record.reason='disabled after '..record.consecutive..' consecutive failures'
        emit(what..' callback disabled (mod '..record.owner..', '..record.label..'): '..record.reason)
    end
    return false
end
M.invoke=invoke

function M.dispatch(name,event)
    local list=state.lists[name]
    if not list then return 0 end
    if state.depth>=MAX_DISPATCH_DEPTH then
        metrics.count('events.depth_dropped')
        emit('event '..name..' dropped: dispatch nested deeper than '..MAX_DISPATCH_DEPTH)
        return 0
    end
    state.depth=state.depth+1
    local delivered=0
    for index=1,#list do
        local sub=list[index]
        if sub.state=='active'and(sub.scope~='mission'or sub.epoch==state.epoch)then
            sub.label=sub.label or('subscription '..sub.id)
            invoke(sub,'event '..name,sub.callback,event,event)
            delivered=delivered+1
            if sub.once then remove(sub,'complete')end
        end
    end
    state.depth=state.depth-1
    metrics.count('events.dispatched')
    return delivered
end

-- True when anyone listens: sources skip building payloads nobody receives.
function M.wanted(name)return state.lists[name]~=nil end

-- Queue an observed event for this tick's dispatch. The payload gains event (its name), time, frame, mission and
-- cause; `name` stays free for the payload's own use (an entity's catalogued name).
function M.queue(name,event)
    if not state.lists[name]then return end
    event.event=name;event.time=state.now;event.frame=state.frame;event.mission=event.mission or state.epoch
    event.cause=event.cause or M.NATIVE
    local n=state.queue_count+1
    state.queue[n]=event;state.queue_count=n
end
local after_flush={}
-- Run fn once this tick's queued events have been dispatched (mission cleanup after mission_ended).
function M.after_flush(fn)after_flush[#after_flush+1]=fn end
local function flush()
    local i=1
    while i<=state.queue_count do
        local event=state.queue[i];state.queue[i]=false
        M.dispatch(event.event,event)
        i=i+1
    end
    state.queue_count=0
    if#after_flush>0 then
        local pending={unpack(after_flush)}
        for k=#after_flush,1,-1 do after_flush[k]=nil end
        for _,fn in ipairs(pending)do
            local ok,why=pcall(fn)
            if not ok then emit('event cleanup failed: '..tostring(why))end
        end
    end
end

-- The cause of an action a mod performs: the mod, and the event it was reacting to (directly, or through a timer it
-- started). depth counts mod-caused links: reacting to native gameplay gives 1, reacting to an event a mod caused
-- gives that event's depth + 1. parent is the triggering event's name and cause.
function M.action_cause(owner,kind)
    local current,event=state.current,state.current_event
    local parent_cause=event and event.cause
    local depth=((parent_cause and parent_cause.depth)or 0)+1
    state.sequence=state.sequence+1
    return {source='mod',mod=owner or(current and current.owner)or'unknown',action=kind..'#'..state.sequence,
        kind=kind,depth=depth,parent=event and{event=event.event,cause=parent_cause}or nil}
end
-- The mod whose callback is running now (nil outside callbacks).
function M.current_owner()return state.current and state.current.owner end

------------------------------------------------------------------------------------------------------- timers --
local Timer={};Timer.__index=Timer
local heap=state.timers
local function less(a,b)if a.due~=b.due then return a.due<b.due end;return a.seq<b.seq end
local function push(timer)
    local i=#heap+1;heap[i]=timer;timer.index=i
    while i>1 do
        local parent=math.floor(i/2)
        if not less(heap[i],heap[parent])then break end
        heap[i],heap[parent]=heap[parent],heap[i];heap[i].index=i;heap[parent].index=parent;i=parent
    end
end
local function pop()
    local top=heap[1];local last=heap[#heap];heap[#heap]=nil
    if#heap>0 then
        heap[1]=last;last.index=1
        local i=1
        while true do
            local l,r,s=2*i,2*i+1,i
            if heap[l]and less(heap[l],heap[s])then s=l end
            if heap[r]and less(heap[r],heap[s])then s=r end
            if s==i then break end
            heap[i],heap[s]=heap[s],heap[i];heap[i].index=i;heap[s].index=s;i=s
        end
    end
    top.index=nil
    return top
end
local function unheap(timer)
    local i=timer.index
    if not i then return end
    local last=heap[#heap];heap[#heap]=nil;timer.index=nil
    if last~=timer then
        heap[i]=last;last.index=i
        -- Restore order in both directions.
        while i>1 and less(heap[i],heap[math.floor(i/2)])do
            local p=math.floor(i/2);heap[i],heap[p]=heap[p],heap[i];heap[i].index=i;heap[p].index=p;i=p
        end
        while true do
            local l,r,s=2*i,2*i+1,i
            if heap[l]and less(heap[l],heap[s])then s=l end
            if heap[r]and less(heap[r],heap[s])then s=r end
            if s==i then break end
            heap[i],heap[s]=heap[s],heap[i];heap[i].index=i;heap[s].index=s;i=s
        end
    end
end
function Timer:cancel()
    if self.state=='active'then self.state='cancelled';unheap(self);state.timer_keys[self.key]=nil end
    return self
end
-- A frame callback can be paused and resumed (a timer cannot: its schedule would have to be rebuilt).
function Timer:disable()if self.kind=='frame'and self.state=='active'then self.state='disabled'end;return self end
function Timer:enable()
    if self.kind=='frame'and self.state=='disabled'then self.state='active';self.consecutive=0 end
    return self
end
function Timer:active()return self.state=='active'end
function Timer:remaining()return self.state=='active'and self.due and math.max(0,self.due-state.now)or nil end
function Timer:describe()
    return {id=self.id,owner=self.owner,kind=self.kind,interval=self.interval,scope=self.scope,state=self.state,
        remaining=self:remaining(),calls=self.calls,failures=self.failures,reason=self.reason}
end
local function refused_timer(owner,why)
    local message=tostring(why):gsub('^[^%s:]+:%d+: ','')
    emit('timer ('..tostring(owner)..') rejected: '..message)
    return setmetatable({state='rejected',reason=message,owner=owner,calls=0,failures=0},Timer)
end
M.refused_timer=refused_timer
function M.timer(kind,seconds,callback,opts,level)
    opts=opts or{}
    local ok,owner=pcall(M.owner,opts.owner,(level or 1)+1)
    if not ok then return refused_timer(opts.owner,owner)end
    local valid,why=pcall(function()
        assert(type(seconds)=='number'and seconds==seconds and seconds>=0 and seconds<=86400,
            'seconds must be a number from 0 to 86400')
        assert(kind~='every'or seconds>=M.MIN_REPEAT,'hd2.every needs an interval of at least '..M.MIN_REPEAT..' s'
            ..' (hd2.on_frame runs a callback every frame)')
        assert(type(callback)=='function','timer callback must be a function')
        assert(opts.scope==nil or opts.scope=='session'or opts.scope=='mission',"scope must be 'session' or 'mission'")
        assert(opts.scope~='mission'or state.in_mission,'a mission-scoped timer needs a mission in progress')
        assert(opts.id==nil or(type(opts.id)=='string'and opts.id:match('^[%w_%.%-]+$')and#opts.id<=64),
            'timer id must be 1 to 64 letters, digits, _ . -')
    end)
    if not valid then return refused_timer(owner,why)end
    state.sequence=state.sequence+1
    local key=opts.id and(owner..'|timer|'..opts.id)or('#'..state.sequence)
    local previous=state.timer_keys[key]
    if previous then previous:cancel()end
    local timer=setmetatable({id=state.sequence,seq=state.sequence,key=key,kind=kind,owner=owner,callback=callback,
        interval=seconds,due=state.now+seconds,scope=opts.scope or'session',epoch=state.epoch,state='active',
        calls=0,failures=0,consecutive=0,max_failures=DEFAULT_MAX_FAILURES,
        label=(kind=='every'and'repeating timer 'or kind=='frame'and'frame callback 'or'timer ')..state.sequence},Timer)
    -- A timer started from a callback keeps the event that callback handled, so its actions stay attributable.
    timer.origin_event=state.current_event
    state.timer_keys[key]=timer
    if kind=='frame'then
        timer.due,timer.interval=nil,0
        -- callback(dt, handle): invoke passes one argument, so the handle is bound once here, not per frame.
        timer.call=function(dt)return callback(dt,timer)end
        state.frames[#state.frames+1]=timer
    else
        push(timer)
    end
    ensure_watch()
    return timer
end
-- A callback run every update tick with the tick's dt (seconds), after events and timers. Same owner, id, scope and
-- failure rules as a timer; Timer:cancel() removes it, :disable() / :enable() pause it.
function M.frame(callback,opts,level)return M.timer('frame',0,callback,opts,(level or 1)+1)end
local function run_timers()
    while heap[1]and heap[1].due<=state.now do
        local timer=pop()
        if timer.state=='active'then
            if timer.scope=='mission'and timer.epoch~=state.epoch then
                timer.state='cancelled';state.timer_keys[timer.key]=nil
            else
                if timer.kind=='every'then
                    -- Missed intervals are skipped, never replayed in a burst.
                    timer.due=timer.due+timer.interval
                    if timer.due<=state.now then timer.due=state.now+timer.interval end
                    push(timer)
                else
                    timer.state='complete';state.timer_keys[timer.key]=nil
                end
                invoke(timer,timer.kind=='every'and'repeating timer'or'timer',timer.callback,timer,timer.origin_event)
                if timer.state=='failed'then unheap(timer);state.timer_keys[timer.key]=nil end
            end
        end
    end
end
-- Frame callbacks in registration order. One registered during this pass first runs next frame; finished ones
-- (cancelled, failed, or of an ended mission) are dropped in place.
local function run_frames(dt)
    local frames=state.frames
    local count,kept=#frames,0
    for i=1,count do
        local frame=frames[i]
        if frame.scope=='mission'and frame.epoch~=state.epoch and(frame.state=='active'or frame.state=='disabled')then
            frame.state='cancelled';state.timer_keys[frame.key]=nil
        end
        if frame.state=='active'then
            invoke(frame,'frame',frame.call,dt,frame.origin_event)
            if frame.state=='failed'then state.timer_keys[frame.key]=nil end
        end
        if frame.state=='active'or frame.state=='disabled'then kept=kept+1;frames[kept]=frame end
    end
    -- Callbacks added while the pass ran sit after `count`; move them down behind the kept ones.
    for i=count+1,#frames do kept=kept+1;frames[kept]=frames[i]end
    for i=#frames,kept+1,-1 do frames[i]=nil end
end

----------------------------------------------------------------------------------------------- mod contexts --
-- Per-mod mission state is cleared in place when a mission starts and when it ends, so a mod may keep a reference.
local function clear(t)for k in pairs(t)do t[k]=nil end end
function M.mission_table(owner)
    local t=state.mission_tables[owner]
    if not t then t={};state.mission_tables[owner]=t end
    return t
end

-------------------------------------------------------------------------------------------------- sources --
-- A native source produces events. It is started while any of its events has a subscriber and stopped otherwise.
-- source: {name, events={...}, start(ctx)->ok|nil,why, poll(ctx), stop(ctx), always=bool}
function M.register_source(source)
    assert(type(source.name)=='string'and not state.sources[source.name],'duplicate event source '..tostring(source.name))
    source.status='idle';source.active=false
    state.sources[source.name]=source
    state.source_order[#state.source_order+1]=source
    return source
end
function source_wanted(source)
    if source.required_by and source.required_by>0 then return true end
    for _,name in ipairs(source.events or{})do if state.lists[name]then return true end end
    return false
end
function M.require_source(name,delta)
    local source=state.sources[name]
    if not source then return end
    source.required_by=math.max(0,(source.required_by or 0)+delta)
    M.refresh_source(source)
end
local RETRY=5   -- seconds between start attempts while the game modules are not ready yet
function M.refresh_source(source)
    local wanted=source_wanted(source)
    if wanted and not source.active and source.status~='unavailable'then
        if source.status=='retry'and state.now<(source.retry_at or 0)then return end
        local ok,started,why=pcall(source.start,source)
        if ok and started then
            source.active=true;source.status='active';source.reason=nil
            emit('event source '..source.name..' started')
            for _,dependency in ipairs(source.depends or{})do M.require_source(dependency,1)end
            ensure_watch()
        else
            local reason=tostring(ok and why or started)
            if reason:find('TARGET_UNAVAILABLE',1,true)then
                -- Not ready yet (game modules still loading): try again later, log once.
                if source.status~='retry'then emit('event source '..source.name..' waiting: '..reason)end
                source.status='retry';source.reason=reason;source.retry_at=state.now+RETRY
                ensure_watch()
            else
                -- A proof failure is definitive for this session.
                source.status='unavailable';source.reason=reason
                emit('event source '..source.name..' unavailable: '..reason)
            end
        end
    elseif not wanted and source.active then
        source.active=false;source.status='idle'
        pcall(source.stop,source)
        for _,dependency in ipairs(source.depends or{})do M.require_source(dependency,-1)end
    end
end
-- Per-frame work outside sources (input polling). poller: function(now) end
function M.set_poller(name,fn)state.pollers[name]=fn;if fn then ensure_watch()end end

-------------------------------------------------------------------------------------------------- mission --
function M.begin_mission(info)
    state.epoch=state.epoch+1
    state.in_mission=true
    for _,t in pairs(state.mission_tables)do clear(t)end
    return state.epoch
end
function M.end_mission()
    -- mission_ended subscribers have already run; drop everything scoped to the mission that just ended.
    local ended=state.epoch
    state.in_mission=false
    for _,sub in pairs(state.by_key)do
        if sub.scope=='mission'and sub.epoch<=ended then remove(sub,'expired')end
    end
    for _,timer in ipairs({unpack(heap)})do
        if timer.scope=='mission'and timer.epoch<=ended then timer:cancel();timer.state='expired'end
    end
    for _,frame in ipairs(state.frames)do
        if frame.scope=='mission'and frame.epoch<=ended and(frame.state=='active'or frame.state=='disabled')then
            frame.state='expired';state.timer_keys[frame.key]=nil
        end
    end
    for _,t in pairs(state.mission_tables)do clear(t)end
    state.epoch=state.epoch+1   -- every handle from the ended mission is now invalid
end
function M.mission()return state.in_mission,state.epoch end
function M.now()return state.now end

------------------------------------------------------------------------------------------------------ tick --
tick=function(dt)
    local started=metrics.now()
    state.now=state.now+dt
    state.frame=state.frame+1
    for _,poller in pairs(state.pollers)do
        local ok,why=pcall(poller,state.now)
        if not ok then emit('input poll failed: '..tostring(why))end
    end
    for _,source in ipairs(state.source_order)do
        if source.status=='retry'and state.now>=(source.retry_at or 0)then M.refresh_source(source)end
        if source.active then
            local ok,why=pcall(source.poll,source)
            if not ok then
                source.failures=(source.failures or 0)+1
                if source.failures<=3 then emit('event source '..source.name..' poll failed: '..tostring(why))end
                if source.failures>=30 then
                    source.active=false;source.status='unavailable';source.reason='poll failed: '..tostring(why)
                    emit('event source '..source.name..' stopped after repeated failures')
                    pcall(source.stop,source)
                end
            else
                source.failures=0
            end
        end
    end
    flush()
    run_timers()
    if#state.frames>0 then run_frames(dt)end
    metrics.elapsed('events.tick',started)
end
-- Tests drive the engine without the scheduler.
M.tick=function(dt)tick(dt)end

-- Status of every catalogued event: available (a source proved it this session), idle, unavailable, blocked.
function M.status()
    local result={}
    for _,name in ipairs(catalog.names)do
        local spec=catalog.events[name]
        local source=spec.source and state.sources[spec.source]
        result[name]={status=spec.status=='blocked'and'blocked'or(source and source.status)or'idle',
            reason=spec.status=='blocked'and spec.reason or(source and source.reason)or nil,
            subscribers=state.lists[name]and#state.lists[name]or 0,hot=spec.hot or false,phase=spec.phase}
    end
    return result
end

-- Test support: forget everything (never called in game).
function M.reset_for_tests()
    for _,source in ipairs(state.source_order)do if source.active then pcall(source.stop,source)end end
    for k in pairs(state.by_key)do state.by_key[k]=nil end
    for k in pairs(state.lists)do state.lists[k]=nil end
    for i=#heap,1,-1 do heap[i]=nil end
    for k in pairs(state.timer_keys)do state.timer_keys[k]=nil end
    for i=#state.frames,1,-1 do state.frames[i]=nil end
    for k in pairs(state.pollers)do state.pollers[k]=nil end
    for k in pairs(state.mission_tables)do state.mission_tables[k]=nil end
    for k in pairs(state.scopes)do state.scopes[k]=nil end
    state.now,state.frame,state.epoch,state.in_mission,state.depth,state.current=0,0,0,false,0,nil
    state.queue_count=0
    for _,source in ipairs(state.source_order)do
        source.active=false;source.status='idle';source.reason=nil;source.required_by=0;source.failures=0
    end
end
return M
