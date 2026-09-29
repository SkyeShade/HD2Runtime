-- Semantic asset requirements: hd2.require_assets(target) / hd2.asset_dependency(target).
-- Targets are the typed handles Runtime already hands out (hd2.pickup, hd2.weapon, hd2.support_weapon,
-- hd2.throwable, hd2.vehicle, hd2.backpack, mounted-weapon candidates, projectile handles). Package IDs never
-- appear in requests or results.
local assets=require('hd2runtime/core/assets')
local database=require('hd2runtime/domains/package_residency')
local M={}

-- Semantic catalog key for a typed handle, or nil with a reason.
function M.key_for(target)
    if type(target)~='table'then return nil,'asset requirements take a typed Runtime handle'end
    local resource=rawget(target,'resource')
    if resource=='pickup'then return'pickup/'..tostring(target.semanticId)end
    if resource=='throwable'then return'throwable/'..tostring(target.throwable)end
    if resource=='backpack'then return'backpack/'..tostring(target.backpack)end
    if resource=='vehicle'then return'vehicle/'..tostring(target.vehicle)end
    if resource=='support_weapon'then return'support_weapon/'..tostring(target.weapon)end
    if resource=='player_weapon'or resource=='weapon'then
        if target.attack and(target.path=='projectile_reference'or target.path=='attack')then
            return'projectile_source/'..tostring(target.weapon)..':'..tostring(target.attack)
        end
        return'player_weapon/'..tostring(target.weapon)
    end
    local semantic=rawget(target,'semanticId')
    if type(semantic)=='string'and semantic:match('^mounted%-weapon/')then return'mounted_weapon/'..semantic end
    return nil,'no asset catalog entry for this handle ('..tostring(resource)..')'
end

-- Offline metadata for tools: known / auto-loadable / derivation. No IDs.
function M.describe(target)
    local key,why=M.key_for(target)
    if not key then return {known=false,autoLoadSupported=false,blocker=why}end
    local item=database.dependencies[key]
    if not item then
        return {key=key,known=false,autoLoadSupported=false,liveTested=false,
            blocker='no loadout package owns this object and no vanilla holder with a package references it'}
    end
    local name=database.packages[item.package].name
    return {key=key,known=true,autoLoadSupported=true,derivation=item.via,liveTested=false,
        package=name:match('[^/]+$'),retain=database.policy.retain}
end

local function dependencies_for(request)
    local targets=request.targets or{request.target}
    assert(type(targets)=='table'and#targets>=1 and#targets<=16,'require_assets takes one to 16 targets')
    local found={}
    for _,target in ipairs(targets)do
        local key,why=M.key_for(target)
        assert(key,why)
        local dependency=assets.dependency(key)
        assert(dependency,'ASSET_UNAVAILABLE: no known package for '..key)
        found[#found+1]=dependency
    end
    return found
end

-- A scheduler watch: 'waiting_for_assets' -> 'complete' (every package resident) | 'rejected'.
function M.start(runtime,emit,request)
    assert(type(request)=='table'and type(request.id)=='string'and#request.id>0 and#request.id<=64
        and not request.id:find('[^%w_%-]'),'require_assets needs a valid id')
    for key in pairs(request)do assert(key=='id'or key=='target'or key=='targets',
        'unsupported require_assets option: '..tostring(key))end
    local spec={id=request.id,asset_dependencies=dependencies_for(request)}
    local gate=assets.gate(runtime,spec,emit)
    local watch={status='waiting_for_assets',asset_dependencies=spec.asset_dependencies}
    function watch.cancel()
        if watch.status~='complete'and watch.status~='rejected'then
            watch.status='cancelled';assets.release(spec.id)
        end
    end
    function watch.tick(dt)
        if watch.status~='waiting_for_assets'then return end
        local state,why=gate.tick(dt)
        if state=='ready'then watch.status='complete';watch.result={status='RESIDENT',
            packages=#spec.asset_dependencies}
        elseif state=='failed'then watch.status='rejected';watch.error=why
            watch.result={status='REJECTED',code='ASSET_UNAVAILABLE',reason=why}
            pcall(emit,'[HD2Runtime] require_assets '..spec.id..' REJECTED code=ASSET_UNAVAILABLE reason='..why)
        end
    end
    return watch
end
return M
