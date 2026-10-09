local hd2=require('mods/skyeshade/hd2runtime')
-- StatusForeignProof 0.1.0 (HD2Runtime 0.30.4, development only).
-- 1. Status effect stats: fire 3 s -> 10 s and 100 -> 300 per tick; gas (and gas_2, gloom: one row) 25 -> 100 per tick.
-- 2. Ctrl+F9: hd2.inspect over common values, logged with their state and owner, and the values owned by unknown
--    mods (hd2.diagnostics.foreign_values()).
local mod=hd2.mod()
local BUILD='0.1.0 STATUS+FOREIGN'
mod:log('StatusForeignProof '..BUILD..' BUILD: fire lasts 10 s and deals 300 per tick, gas deals 100 per tick. '
    ..'Ctrl+F9 logs who owns common values (vanilla / runtime / foreign owner=unknown).')

local function report(label)
    return function(status,info)
        mod:log(label..' '..tostring(info and info.previous)..' -> '..tostring(status)
            ..(info and info.error and(': '..tostring(info.error))or''))
    end
end
local fire=hd2.status_effect('fire')
hd2.ensure({patch={id='proof-fire-duration',target=fire,allow_shared=true,field=hd2.fields.status.duration,
    expect=3,value=10},on_status=report('fire duration 3 -> 10:')})
hd2.ensure({transaction={id='proof-fire-damage',target=fire:damage(),allow_shared=true,allow_unverified_effect=true,
    changes={{field='damage.standard_damage',expect=100,value=300},{field='damage.durable_damage',expect=100,value=300}}},
    on_status=report('fire tick damage 100 -> 300:')})
hd2.ensure({transaction={id='proof-gas-damage',target=hd2.status_effect('gas'):damage(),allow_shared=true,
    allow_unverified_effect=true,changes={{field='damage.standard_damage',expect=25,value=100},
        {field='damage.durable_damage',expect=25,value=100}}},
    on_status=report('gas tick damage 25 -> 100:')})

-- Common values a data-file mod is likely to change.
local CHECKS={
    {label='status fire',target=fire,fields={hd2.fields.status.duration}},
    {label='status fire damage',target=fire:damage(),fields={'damage.standard_damage','damage.durable_damage'}},
    {label='status gas damage',target=hd2.status_effect('gas'):damage(),fields={'damage.standard_damage'}},
    {label='status stun_medium',target=hd2.status_effect('stun_medium'),fields={hd2.fields.status.duration}},
    {label='Orbital Gas Strike',target=hd2.stratagem('Orbital Gas Strike'),
        fields={'stratagem.cooldown','stratagem.call_in_time'}},
    {label='Eagle 500kg Bomb',target=hd2.stratagem('Eagle 500kg Bomb'),fields={'stratagem.cooldown'}},
    {label='Gatling Sentry turret',target=hd2.stratagem('A/G-16 Gatling Sentry'):deployed_entity():turret(),
        fields={hd2.fields.turret.yaw_speed,hd2.fields.turret.pitch_speed}},
}
local function inspect_all()
    for _,check in ipairs(CHECKS)do
        local ok,why=pcall(hd2.inspect,{target=check.target,fields=check.fields,on_result=function(result)
            for _,f in ipairs(result.fields)do
                mod:log(('inspect %s %s: state=%s owner=%s value=%s vanilla=%s%s'):format(check.label,f.field,
                    tostring(f.state),tostring(f.owner),tostring(f.value),tostring(f.vanilla),
                    f.reason and(' reason='..tostring(f.reason))or''))
            end
        end})
        if not ok then mod:log('inspect '..check.label..' refused: '..tostring(why))end
    end
    local list=hd2.diagnostics.foreign_values()
    mod:log('values owned by unknown mods so far: '..#list)
    for _,v in ipairs(list)do
        mod:log(('  %s %s = %s (reviewed %s), seen %d'):format(v.target,v.field,tostring(v.observed),
            tostring(v.expected),v.seen))
    end
end
hd2.input.bind('status_foreign_proof.inspect',{key='Ctrl+F9',on_press=inspect_all})
