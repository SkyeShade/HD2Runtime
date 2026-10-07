-- Build fingerprint check shared by every resolver and writer.
--
-- Hashing the executable and game.dll reads ~30 MB from disk and is synchronous,
-- so it must not repeat per operation or per ensure cycle. Windows keeps a mapped
-- module's image file locked for the life of the mapping, so the result for the same
-- loaded module identities stays valid for the whole process: a match and a mismatch
-- are both cached. A hash that fails to complete raises and is never cached (a
-- wrong build is only remembered once both files were hashed in full), and a
-- different module at the same name is a new identity that is hashed again.
local profile=require('hd2runtime/schemas/current')
local metrics=require('hd2runtime/runtime/metrics')
local M={}
local verified={}   -- identity key -> true (pinned build) or false (another build)
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
    if verified[key]~=nil then metrics.count('fingerprint.cache_hits');return verified[key]end
    metrics.count('fingerprint.module_hashes',2)
    local started=metrics.now()
    local exe_sha,dll_sha=runtime.module_hash(exe),runtime.module_hash(dll)
    metrics.elapsed('fingerprint.module_hash',started)
    local ok=exe_sha==profile.exe_sha and dll_sha==profile.dll_sha
    if type(exe_sha)=='string'and type(dll_sha)=='string'then verified[key]=ok end
    return ok
end
-- The build status without raising: 'matched', 'mismatched' or 'not_ready' (modules not loaded, or the hash could
-- not be completed; the reason is the second value). Cheap after the first answer for a loaded build.
function M.status(runtime)
    local ok,result=pcall(M.matches,runtime)
    if not ok then return 'not_ready',(tostring(result):gsub('^[^%s:]+:%d+: ',''))end
    if result==nil then return 'not_ready','game modules not loaded'end
    return result and'matched'or'mismatched'
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
