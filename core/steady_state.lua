-- Cheap steady-state verification for ensured operations.
--
-- After a fully guarded operation reaches its desired state, re-running discovery,
-- catalog rebuilds, ownership walks, and the transaction guard every interval is
-- pure overhead. This module retains only the exact target byte ranges, their
-- owner allocation identity, and a small owner header fingerprint. A check costs a
-- few VirtualQuery calls and small reads. Any doubt (region gone or changed,
-- header differs, target not desired) reports drift, and the caller falls back to
-- the unchanged full guarded resolution and write path. This path never writes.
local metrics=require('hd2runtime/runtime/metrics')
local M={}
local HEADER=32

local function region_ok(runtime,owner,at)
    local r=runtime.query(at)
    return r and r.state==0x1000 and r.allocation_base==owner.base
        and r.type==(owner.type or 0x20000) and (r.protect==2 or r.protect==4)
        and r.base<=at and at<r.base+r.size
end
local function owner_key(owner)return tostring(owner.base)..':'..tostring(owner.size)end

-- Build a verification handle from prepared changes. Returns nil if the plan
-- shape is not understood, so the caller keeps the full-resolution behavior.
function M.capture(runtime,changes)
    if type(changes)~='table'or#changes==0 then return nil end
    local handle={targets={},owners={}}
    for _,change in ipairs(changes)do
        local owner=change.owner
        if type(owner)~='table'or type(owner.base)~='number'or type(change.offset)~='number'
            or type(change.desired)~='string'then return nil end
        local key=owner_key(owner)
        if not handle.owners[key]then
            if not region_ok(runtime,owner,owner.base)then return nil end
            local header=runtime.read(owner.base,math.min(HEADER,owner.size or HEADER))
            if not header then return nil end
            handle.owners[key]={owner=owner,header=header}
        end
        handle.targets[#handle.targets+1]={owner=owner,key=key,offset=change.offset,desired=change.desired}
    end
    return handle
end

-- Returns true when every target is still present, owned, and desired.
function M.verify(runtime,handle)
    local started=metrics.now()
    metrics.count('steady.verifications')
    local ok,stable,reason=pcall(function()
        for _,item in pairs(handle.owners)do
            local owner=item.owner
            if not region_ok(runtime,owner,owner.base)then return false,'owner allocation changed'end
            if runtime.read(owner.base,#item.header)~=item.header then return false,'owner header changed'end
        end
        for _,target in ipairs(handle.targets)do
            local at=target.owner.base+target.offset
            if not region_ok(runtime,target.owner,at)then return false,'target region changed'end
            metrics.count('steady.target_reads')
            if runtime.read(at,#target.desired)~=target.desired then return false,'target value drifted'end
        end
        return true
    end)
    metrics.elapsed('steady.verify',started)
    if not ok then return false,'verification error: '..tostring(stable)end
    if not stable then metrics.count('steady.drift')end
    return stable,reason
end
return M
