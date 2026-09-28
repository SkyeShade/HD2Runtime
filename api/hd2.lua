-- Lazy adapter loading: describing/importing the API never opens process memory.
local factory=require('hd2runtime/api/session')
local instance
local M={}
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
function M.patch(request)
    local ok,adapter=pcall(require,'hd2runtime/runtime/windows_write')
    if not ok then return disabled()end
    local watch=require('hd2runtime/api/patch').start(adapter.create(),
        require('hd2runtime/runtime/log').emit,request)
    return require('hd2runtime/runtime/scheduler').attach(watch)
end
function M.transaction(request)
    local ok,adapter=pcall(require,'hd2runtime/runtime/windows_write')
    if not ok then return disabled()end
    return require('hd2runtime/runtime/scheduler').attach(
        require('hd2runtime/api/transaction').start(adapter.create(),
            require('hd2runtime/runtime/log').emit,request))
end
function M.plan(request)
    local ok,adapter=pcall(require,'hd2runtime/runtime/windows_write')
    if not ok then return disabled()end
    return require('hd2runtime/runtime/scheduler').attach(
        require('hd2runtime/api/plan').start(adapter.create(),
            require('hd2runtime/runtime/log').emit,request))
end
function M.ensure(request)
    local ok,adapter=pcall(require,'hd2runtime/runtime/windows_write')
    if not ok then return disabled()end
    return require('hd2runtime/runtime/scheduler').attach(
        require('hd2runtime/api/ensure').start(adapter.create(),
            require('hd2runtime/runtime/log').emit,request))
end
return M
