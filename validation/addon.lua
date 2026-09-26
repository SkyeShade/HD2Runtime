-- HD2-Addon: mods/skyeshade/hd2runtime_live_validation
local key='HD2RuntimeLiveValidationV1'
local existing=rawget(_G,key)
if existing then return existing end
local state={status='initializing',mode='read_only',writes=0,protection_changes=0}
rawset(_G,key,state)
local ok,result=pcall(function()
    return require('hd2runtime/validation/report').start(
        require('mods/skyeshade/hd2runtime'),
        require('hd2runtime/validation/expectations'),
        require('hd2runtime/validation/build_metadata'))
end)
if ok then state=result;rawset(_G,key,state)
else
    state.status='error';state.error=tostring(result)
    print('[HD2Runtime] LIVE_VALIDATION status=ERROR adapter=initialization reason='..state.error
        ..' observed=unavailable writes=0 protection_changes=0 fixture_fallback=disabled')
end
return state
