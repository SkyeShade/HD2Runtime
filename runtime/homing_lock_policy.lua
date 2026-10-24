-- Pre-fire homing support, extracted from the user-tested AR-23 Homing Lab 0.4.1.
-- The generic Runtime integration is not yet live-tested.
-- Pure acquisition/assignment policy. No game memory, I/O, spawning or binding.
local M = {}
M.MAX_TRACKED=4096
M.PROJECTILE_TTL=120
M.MAX_OBSERVATION_GAP=.5
local DEFAULTS={enabled=false,mode='single',lock_time=.3,max_targets=1,half_angle=12,range=100,require_los=false,show_hud=true}
local function finite(n) return type(n)=='number' and n==n and math.abs(n)<math.huge end
local function integer(n) return finite(n) and n>=0 and n==math.floor(n) end
local function copy(t) local r={} for k,v in pairs(t) do r[k]=v end return r end

function M.validate_config(config)
    if config==nil then config={} end
    if type(config)~='table' then return nil,'config must be a table' end
    local c={}
    for k,v in pairs(DEFAULTS) do if config[k]~=nil then c[k]=config[k] else c[k]=v end end
    if type(c.enabled)~='boolean' or type(c.require_los)~='boolean' or type(c.show_hud)~='boolean' then return nil,'boolean required' end
    if c.mode~='single' and c.mode~='multi' then return nil,'unknown mode' end
    if not finite(c.lock_time) or c.lock_time<0 then return nil,'invalid lock_time' end
    if not integer(c.max_targets) or c.max_targets<1 or c.max_targets>6 then return nil,'invalid max_targets' end
    if not finite(c.half_angle) or c.half_angle<0 or c.half_angle>180 then return nil,'invalid half_angle' end
    if not finite(c.range) or c.range<=0 then return nil,'invalid range' end
    return c
end

function M.reset(state, reason)
    state.pending={}; state.locked={}; state.acquiring={}; state.assigned={}
    state.last_time=nil; state.snapshot_time=nil; state.config=nil
    state.cursor=nil; state.reset_reason=reason or 'reset'
    return state
end
function M.new() return M.reset({},'new') end
local function same_config(a,b)
    if not a then return false end
    for k in pairs(DEFAULTS) do if k~='show_hud' and a[k]~=b[k] then return false end end
    return true
end
local function valid_target(t,c)
    return type(t)=='table' and type(t.key)=='string' and #t.key>0
        and integer(t.net) and integer(t.node) and t.alive==true
        and finite(t.angle_deg) and t.angle_deg>=0 and t.angle_deg<=c.half_angle
        and finite(t.distance) and t.distance>=0 and t.distance<=c.range
        and (not c.require_los or t.visible==true)
end
local function priority(a,b)
    if a.angle_deg~=b.angle_deg then return a.angle_deg<b.angle_deg end
    if a.distance~=b.distance then return a.distance<b.distance end
    return a.key<b.key
end
local function result(s,reason)
    local r={locked={},acquiring={},reason=reason}
    for _,t in ipairs(s.locked) do r.locked[#r.locked+1]=copy(t) end
    for _,t in ipairs(s.acquiring) do r.acquiring[#r.acquiring+1]=copy(t) end
    return r
end

function M.step(state,now,candidates,config)
    local c,err=M.validate_config(config)
    if not c then M.reset(state,'invalid_config'); local r=result(state,'invalid_config'); r.error=err; return r end
    if not finite(now) then M.reset(state,'invalid_time'); return result(state,'invalid_time') end
    if state.last_time and now<state.last_time then M.reset(state,'time_reversal') end
    if not same_config(state.config,c) then M.reset(state,'config_changed') end
    if state.snapshot_time and now-state.snapshot_time>M.MAX_OBSERVATION_GAP then
        state.pending={}; state.locked={}; state.acquiring={}; state.cursor=nil
    end
    state.config=c; state.last_time=now; state.snapshot_time=now
    if not c.enabled then state.pending={}; state.locked={}; state.acquiring={}; return result(state,'disabled') end
    local unique,ambiguous={},{}
    for _,t in ipairs(type(candidates)=='table' and candidates or {}) do
        if valid_target(t,c) then
            local old=unique[t.key]
            if old and (old.net~=t.net or old.node~=t.node) then ambiguous[t.key]=true end
            if not old or priority(t,old) then unique[t.key]=copy(t) end
        end
    end
    local chosen={}
    for key,t in pairs(unique) do if not ambiguous[key] then chosen[#chosen+1]=t end end
    table.sort(chosen,priority)
    local next_pending,locked,acquiring={},{},{}
    local limit=c.mode=='single' and 1 or c.max_targets
    for i=1,math.min(#chosen,limit) do
        local t=chosen[i]; local p=state.pending[t.key]
        if not p or p.net~=t.net or p.node~=t.node then p={since=now,net=t.net,node=t.node} end
        t.acquiring_since=p.since
        t.progress=c.lock_time==0 and 1 or math.min(1,(now-p.since)/c.lock_time)
        if t.progress>=1 then
            p.acquired_at=p.acquired_at or now; t.acquired_at=p.acquired_at
            locked[#locked+1]=t
        else acquiring[#acquiring+1]=t end
        next_pending[t.key]=p
    end
    -- Canonical identity order prevents angular jitter from reordering a locked group.
    table.sort(locked,function(a,b) return a.key<b.key end)
    state.pending=next_pending; state.locked=locked; state.acquiring=acquiring
    return result(state,#locked>0 and 'locked' or (#acquiring>0 and 'acquiring' or 'no_candidates'))
end

-- This returns a policy decision, NOT proof that a native projectile was bound.
-- projectile_key must include the adapter-observed generation, never only a slot.
-- The adapter must reject already-bound/foreign rounds even after a policy reset.
function M.assign(state,projectile_key,now)
    if type(projectile_key)~='string' or #projectile_key==0 then return nil,'invalid_projectile_key' end
    if not finite(now) then M.reset(state,'invalid_time'); return nil,'invalid_time' end
    if state.last_time and now<state.last_time then M.reset(state,'time_reversal'); return nil,'time_reversal' end
    state.last_time=now
    if not state.config or not state.config.enabled then return nil,'disabled' end
    if not state.snapshot_time or now-state.snapshot_time>M.MAX_OBSERVATION_GAP then return nil,'stale_snapshot' end
    local count=0
    for key,when in pairs(state.assigned) do
        if now-when>=M.PROJECTILE_TTL then state.assigned[key]=nil else count=count+1 end
    end
    if state.assigned[projectile_key]~=nil then return nil,'duplicate_projectile' end
    if #state.locked==0 then return nil,'no_locked_target' end
    if count>=M.MAX_TRACKED then return nil,'tracking_capacity' end
    local selected=state.locked[1]
    if state.cursor then
        for _,t in ipairs(state.locked) do if t.key>state.cursor then selected=t; break end end
    end
    state.cursor=selected.key; state.assigned[projectile_key]=now
    local decision=copy(selected); decision.projectile_key=projectile_key; decision.assigned_at=now
    return decision,'assigned'
end

return M
