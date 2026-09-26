-- Lazy adapter loading: describing/importing the API never opens process memory.
local factory=require('hd2runtime/api/session')
local instance
local M={}
local function session()
    if not instance then
        local runtime=require('hd2runtime/runtime/windows_readonly')()
        instance=factory.new(runtime,require('hd2runtime/runtime/log').emit)
    end
    return instance
end
for _,name in ipairs({'read'})do
    local method=name
    M[method]=function(...)return session()[method](...)end
end
local metadata=factory.new({},require('hd2runtime/runtime/log').emit)
M.describe=metadata.describe
M.format=metadata.format
function M.observe(request)
    return require('hd2runtime/runtime/scheduler').attach(session().observe(request))
end
local function disabled()
    require('hd2runtime/runtime/log').emit('[HD2Runtime] write request rejected: read-only milestone')
    return nil,{code='READ_ONLY_MILESTONE',message='No gameplay writer is included in milestone 1'}
end
M.weapon=require('hd2runtime/api/target').weapon
M.stratagem=require('hd2runtime/api/target').stratagem
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
function M.ensure(request)
    local ok,adapter=pcall(require,'hd2runtime/runtime/windows_write')
    if not ok then return disabled()end
    return require('hd2runtime/runtime/scheduler').attach(
        require('hd2runtime/api/ensure').start(adapter.create(),
            require('hd2runtime/runtime/log').emit,request))
end
return M
