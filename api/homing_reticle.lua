-- One visual owner per homing handle. Styling never reconfigures targeting or
-- touches projectile records. The shared engine publishes fresh snapshots;
-- the frame callback only clears retained GUI when input/menu state changes.
local R=require('hd2runtime/runtime/homing_reticle')
local View=require('hd2runtime/runtime/homing_view')
local Gate=require('hd2runtime/runtime/homing_visibility')
local events=require('hd2runtime/runtime/events')
local M={}
local function copy(opts)
    local out={}
    for k,v in pairs(opts or{})do
        if type(v)=='table'then out[k]={v[1]or v.r,v[2]or v.g,v[3]or v.b,v[4]or v.a or 255}
        else out[k]=v end
    end
    return out
end
function M.open(handle,opts)
    assert(handle.status=='active'and handle._lock,'a reticle needs active pre_fire acquisition')
    R.validate_style(opts) -- Reject before stopping or replacing an existing GUI.
    local c={};local spec=copy(opts);local visible,stopped=true,false
    local renderer,timer,publish
    local function make()
        return R.new({view=View,style=spec,blocked=function()return Gate.blocked(nil,spec.aim_only~=false)end,
            log=events.emit_log})
    end
    renderer=make()
    publish=function(snapshot)
        if stopped then return end
        renderer:update(visible and snapshot or{visible=false})
    end
    handle._lock.on_visual=publish
    timer=events.frame(function()
        if handle.status~='active'then c:stop()else renderer:tick()end
    end,{owner=handle.owner,scope='session'})
    function c:style(patch)
        assert(not stopped,'reticle is stopped')
        assert(type(patch)=='table','reticle style patch must be a table')
        local next_spec=copy(spec)
        for k,v in pairs(patch)do next_spec[k]=v end
        R.validate_style(next_spec)
        spec=copy(next_spec)
        renderer:shutdown();renderer=make()
        publish(handle._lock:visual_snapshot())
        return self
    end
    function c:show()assert(not stopped,'reticle is stopped');visible=true;return self end
    function c:hide()visible=false;renderer:update({visible=false});return self end
    function c:status()local s=renderer:status();s.visible=visible and not stopped;return s end
    function c:stop()
        if stopped then return self end
        stopped=true;renderer:shutdown()
        if timer then timer:cancel()end
        if handle._lock.on_visual==publish then handle._lock.on_visual=nil end
        return self
    end
    return c
end
return M
