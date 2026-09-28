-- Build fingerprint check shared by every resolver and writer.
--
-- Hashing the executable and game.dll reads ~30 MB from disk and is synchronous,
-- so it must not repeat per operation or per ensure cycle. Windows keeps a mapped
-- module's image file locked for the life of the mapping, so a successful match for
-- the same loaded module identities stays valid for the whole process. Only
-- successes are cached; a mismatch is re-hashed and still fails closed.
local profile=require('hd2runtime/schemas/current')
local metrics=require('hd2runtime/runtime/metrics')
local M={}
local verified={}
-- Loaded-module identity: base address plus handle. A different module at
-- application time is a new identity and is always hashed again.
local function identity(runtime,handle)
    local address=runtime.address and runtime.address(handle)
    return tostring(address)..'@'..tostring(handle)
end
-- Returns true when the loaded modules match the pinned build, false on mismatch,
-- and nil when the modules are not loaded yet.
function M.matches(runtime)
    local exe,dll=runtime.module(nil),runtime.module('game.dll')
    if not exe or not dll then return nil end
    local key=tostring(runtime.mode)..'|'..identity(runtime,exe)..'|'..identity(runtime,dll)
    if verified[key]then metrics.count('fingerprint.cache_hits');return true end
    metrics.count('fingerprint.module_hashes',2)
    local started=metrics.now()
    local ok=runtime.module_hash(exe)==profile.exe_sha and runtime.module_hash(dll)==profile.dll_sha
    metrics.elapsed('fingerprint.module_hash',started)
    if ok then verified[key]=true end
    return ok
end
-- Test/audit hook: forget cached verifications.
function M.reset()verified={}end
-- Resolver entry check with the historical error messages.
function M.require(runtime)
    local ok=M.matches(runtime)
    if ok==nil then error('TARGET_UNAVAILABLE: game modules not ready',0)end
    assert(ok,'unsupported build fingerprint')
end
return M
