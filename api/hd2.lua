-- Lazy adapter loading: describing/importing the API never opens process memory.
local factory=require('hd2runtime/api/session')
local log=require('hd2runtime/runtime/log')
local instance
local M={}
-- Support/debugging: the first line a session writes names the Runtime version actually loaded. The version is the
-- packaged copy of VERSION (domains/metadata.lua, generated from schemas/sdk.json and checked against VERSION); the
-- global flag keeps it to one line per Lua state even if this module is required again after package.loaded changes.
do
    local metadata=require('hd2runtime/domains/metadata')
    if not rawget(_G,'HD2RuntimeStartupLogged')then
        rawset(_G,'HD2RuntimeStartupLogged',metadata.version)
        log.emit('[HD2Runtime] HD2Runtime '..tostring(metadata.version)..' initialized (API '
            ..tostring(metadata.api_version)..')')
    end
end
local function session()
    if not instance then
        local runtime=require('hd2runtime/runtime/live_process_reader')()
        instance=factory.new(runtime,require('hd2runtime/runtime/log').emit)
    end
    return instance
end
for _,name in ipairs({'read','enumerate_primary_weapons'})do
    local method=name
    M[method]=function(...)return session()[method](...)end
end
local metadata=factory.new({},require('hd2runtime/runtime/log').emit)
M.describe=metadata.describe
M.format=metadata.format
function M.observe(request)
    return require('hd2runtime/runtime/scheduler').attach(session().observe(request))
end
function M.map_primary_weapons(request)
    return require('hd2runtime/runtime/scheduler').attach(session().map_primary_weapons(request))
end
function M.capture_snapshot(request)
    return require('hd2runtime/runtime/scheduler').attach(session().capture_snapshot(request))
end
-- Armed capture: waits for `py hd2.py snapshot arm` requests (research tooling; never captures on its own).
function M.snapshot_control(request)
    return require('hd2runtime/runtime/scheduler').attach(session().snapshot_control(request))
end
local function disabled()
    require('hd2runtime/runtime/log').emit('[HD2Runtime] write request rejected: read-only milestone')
    return nil,{code='READ_ONLY_MILESTONE',message='No gameplay writer is included in milestone 1'}
end
-- Export every typed builder (legacy resources plus support_weapon, backpack, and other
-- catalog-backed builders), not only the legacy metadata builder list.
for name in pairs(require('hd2runtime/api/target').new(metadata.describe))do M[name]=metadata[name]end
M.fields=metadata.fields;M.enums=metadata.enums;M.resources=metadata.resources
M.version=metadata.version;M.api_version=metadata.api_version
-- Process-wide work counters and worst durations for performance audits.
function M.metrics()return require('hd2runtime/runtime/metrics').snapshot()end
-- In-game options (Mod Options Menu). Required at startup with the rest of the API.
local options=require('hd2runtime/api/options')
function M.options(spec)return options.page(spec)end
-- One-shot operations resolve once and cannot follow an option; ensure owns bound values.
local function one_shot(request)
    assert(not options.contains(request),'option-bound values require hd2.ensure')
end
-- Registration isolation. A request that fails validation never writes; it is logged with its id and reason and
-- returned as a rejected handle instead of raising, so one invalid operation cannot abort an addon that registers
-- many independent operations (a ModBuilder export registers one per backing object, in a generated order).
local function operation_id(kind,request)
    if type(request)~='table'then return nil end
    local body=request
    if kind=='ensure'then body=request.patch or request.transaction or request.plan end
    return type(body)=='table'and type(body.id)=='string'and body.id or nil
end
local function rejected(kind,request,why)
    -- Drop the raising chunk's position prefix ('[string "x"]:12: ' or 'name:12: '); the reason follows it.
    local message=tostring(why):gsub('^%[string "[^"]*"%]:%d+: ',''):gsub('^[^%s:]+:%d+: ','')
    -- Runtime reason codes (DORMANT_PROJECTILE_REFERENCE, CONFLICT, ...) may follow a field prefix.
    local code=message:match('%f[%w]([A-Z][A-Z0-9_]*[A-Z0-9]):')or'INVALID_REQUEST'
    local id=operation_id(kind,request)
    log.emit('[HD2Runtime] '..kind..' '..(id or'(no id)')..' rejected: '..message)
    require('hd2runtime/runtime/metrics').count('api.rejected_registrations')
    local handle={kind=kind,id=id,status='rejected',error=message,runs=kind=='ensure'and 0 or nil,
        result={status='REJECTED',code=code,message=message}}
    function handle.tick()end
    function handle.cancel()end
    return handle
end
-- Apply latency is visible: component values are copied into a weapon when the game builds it, so a weapon built
-- before its operation applied keeps the old value until it is rebuilt. Once every operation registered in one
-- burst has settled (applied, rejected, unavailable or failed), one line reports the counts and the elapsed time.
local burst
local function settled(handle)
    if handle.status=='rejected'or handle.status=='unavailable'or handle.status=='cancelled'
        or handle.status=='complete'or handle.status=='disabled'then return true end
    return handle.runs~=nil and handle.runs>=1
end
local function track(handle)
    if not burst then
        burst={handles={},elapsed=0}
        local current=burst
        local watcher={status='waiting'}
        function watcher.cancel()watcher.status='cancelled'end
        function watcher.tick(dt)
            current.elapsed=current.elapsed+dt
            for _,h in ipairs(current.handles)do if not settled(h)then return end end
            local counts={applied=0,rejected=0,other=0}
            for _,h in ipairs(current.handles)do
                local result=h.result and h.result.status
                if h.status=='rejected'then counts.rejected=counts.rejected+1
                elseif result=='APPLIED'or result=='ALREADY_DESIRED'then counts.applied=counts.applied+1
                else counts.other=counts.other+1 end
            end
            log.emit(string.format('[HD2Runtime] %d registered operations settled in %.0f s: %d applied, '
                ..'%d rejected, %d other (see earlier lines)',#current.handles,current.elapsed,counts.applied,
                counts.rejected,counts.other))
            if burst==current then burst=nil end
            watcher.status='complete'
        end
        require('hd2runtime/runtime/scheduler').attach(watcher)
    end
    burst.handles[#burst.handles+1]=handle
    return handle
end
local function register(kind,module,request,check)
    if check then
        local valid,why=pcall(check,request)
        if not valid then return track(rejected(kind,request,why))end
    end
    local ok,adapter=pcall(require,'hd2runtime/runtime/windows_write')
    if not ok then return disabled()end
    local started,watch=pcall(function()
        return require(module).start(adapter.create(),log.emit,request)
    end)
    if not started then return track(rejected(kind,request,watch))end
    return track(require('hd2runtime/runtime/scheduler').attach(watch))
end
function M.patch(request)return register('patch','hd2runtime/api/patch',request,one_shot)end
function M.transaction(request)return register('transaction','hd2runtime/api/transaction',request,one_shot)end
function M.plan(request)return register('plan','hd2runtime/api/plan',request,one_shot)end
-- Load (through the game's own package system) the assets a semantic target needs; see docs/asset-loading.md.
function M.require_assets(request)
    local ok,adapter=pcall(require,'hd2runtime/runtime/windows_write')
    if not ok then return disabled()end
    return require('hd2runtime/runtime/scheduler').attach(
        require('hd2runtime/api/assets').start(adapter.create(),require('hd2runtime/runtime/log').emit,request))
end
-- Offline: is this target's package dependency known and auto-loadable? (no IDs)
function M.asset_dependency(target)return require('hd2runtime/api/assets').describe(target)end
function M.ensure(request)return register('ensure','hd2runtime/api/ensure',request)end
-- Gameplay scripting (docs/events.md): events, timers, keybinds and per-mod contexts. Required at startup with the
-- rest of the API; nothing polls until a mod subscribes, starts a timer or binds a key.
local scripting=require('hd2runtime/api/events')
M.events=scripting.events
M.after=scripting.after
M.every=scripting.every
M.input=scripting.input
M.mod=scripting.mod
M.players=scripting.players
M.game_state=scripting.game_state
M.local_player=scripting.local_player
M.entities=scripting.entities
-- Gameplay actions an event script can perform (api/actions.lua): exported without wrappers so the calling mod is
-- their owner.
local actions=require('hd2runtime/api/actions')
M.actions={heal=actions.heal,status=actions.status}
M.explosions=actions.explosions
M.projectiles=actions.projectiles
M.status=actions.status_effects
return M
