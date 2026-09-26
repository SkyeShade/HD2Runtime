-- HD2-Addon: mods/skyeshade/hd2runtime_snapshot_capture
local key='HD2RuntimeSnapshotCaptureV1'
local existing=rawget(_G,key);if existing then return existing end
local hd2=require('mods/skyeshade/hd2runtime')
assert(hd2.api_version==1,'HD2Runtime API 1 required')
local state={status='starting',mode='read_only',writes=0,protection_changes=0}
rawset(_G,key,state)
state.watch=hd2.capture_snapshot{
    on_result=function(result)
        state.status='complete';state.result=result;state.path=result.path
        print('[HD2Runtime] snapshot available at '..result.path)
    end,
    on_error=function(reason,detail)
        state.status='rejected';state.error=tostring(reason);state.detail=detail
    end,
}
state.status='capturing'
return state
