-- HD2-Addon: mods/skyeshade/hd2runtime_report
local existing=rawget(_G,'HD2RuntimeReportV1')
if existing then return existing end
local hd2=require('mods/skyeshade/hd2runtime')
local log=require('hd2runtime/runtime/log').emit
local state={mode='read_only',writes=0,protection_changes=0}
rawset(_G,'HD2RuntimeReportV1',state)
state.watch=hd2.observe{
    targets=require('hd2runtime/examples/known_values'),
    on_result=function(result)
        log(hd2.format(result))
        state.result=result
        state.watch.cancel()
    end,
    on_error=function(reason)state.error=reason end,
}
return state
