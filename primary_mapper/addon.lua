-- HD2-Addon: mods/skyeshade/hd2runtime_primary_weapon_mapper
local key='HD2RuntimePrimaryWeaponMapperV1'
local existing=rawget(_G,key);if existing then return existing end
local hd2=require('mods/skyeshade/hd2runtime')
assert(hd2.api_version==1,'HD2Runtime API 1 required')
local state={status='initializing',mode='read_only',writes=0,protection_changes=0}
rawset(_G,key,state)
local dataset=require('hd2runtime/primary_mapper/wiki_data')
local report=require('hd2runtime/primary_mapper/report')
local build=require('hd2runtime/primary_mapper/build_metadata')
state.watch=hd2.map_primary_weapons{
    startup_delay=3,
    on_result=function(raw)
        local full,compact=report.compose(raw,dataset,{version=hd2.version,commit=build.commit})
        local lines=report.log_lines(full)
        state.files=require('hd2runtime/primary_mapper/output').write(full,compact,lines)
        state.status='complete';state.report=full;state.mapping=compact
    end,
    on_error=function(reason,detail)
        state.status='rejected';state.error=tostring(reason);state.detail=detail
        print('[HD2Runtime] PRIMARY_WEAPON_MAP rejected adapter='..tostring(detail and detail.adapter)
            ..' reason='..tostring(reason)..' writes=0 protection_changes=0 fixture_fallback=disabled')
    end,
}
state.status='running'
return state
