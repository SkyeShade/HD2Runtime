-- Identity-only builders. No address or memory capability can enter a target.
local M={}
local function target(stage)
    local t={resource='jar5',path=stage}
    if stage=='weapon' then
        function t.projectile()return target('projectile')end
    elseif stage=='projectile' then
        function t.damage()return target('damage')end
    end
    return t
end
function M.weapon(name)
    assert(name=='JAR-5 Dominator' or name=='jar5','weapon alias is not reviewed')
    return target('weapon')
end
function M.stratagem(name)
    assert(name=='Shield Relay' or name=='shield_relay','stratagem alias is not reviewed')
    return {resource='shield_relay',path='stratagem'}
end
return M
