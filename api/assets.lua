-- Semantic asset requirements: hd2.require_assets(target) / hd2.asset_dependency(target).
-- Targets are the typed handles Runtime already hands out (hd2.pickup, hd2.weapon, hd2.support_weapon,
-- hd2.throwable, hd2.vehicle, hd2.backpack, mounted-weapon candidates, projectile handles, and a sound's bank through
-- hd2.sounds.asset(name): a firing sound or a sound event of the full catalogue). Package IDs never appear in requests or results.
local assets=require('hd2runtime/core/assets')
local database=require('hd2runtime/domains/package_residency')
local weapon_sounds=require('hd2runtime/runtime/weapon_sounds')
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
    if resource=='sound'then return'sound/'..tostring(target.sound)end
    local semantic=rawget(target,'semanticId')
    if type(semantic)=='string'and semantic:match('^mounted%-weapon/')then return'mounted_weapon/'..semantic end
    return nil,'no asset catalog entry for this handle ('..tostring(resource)..')'
end

-- Offline metadata for tools: known / auto-loadable / derivation. No IDs.
function M.describe(target)
    local key,why=M.key_for(target)
    if not key then return {known=false,autoLoadSupported=false,blocker=why}end
    if key:match('^sound/')then
        local list,swhy=M.sound_dependencies(target.sound)
        if not list then return {key=key,known=false,autoLoadSupported=false,liveTested=false,blocker=swhy}end
        return {key=key,known=true,autoLoadSupported=true,derivation=list[1]and list[1].via or'sound_bank_stratagem_call_in',
            liveTested=false,packages=#list,retain=database.policy.retain}
    end
    local item=database.dependencies[key]
    if not item then
        return {key=key,known=false,autoLoadSupported=false,liveTested=false,
            blocker='no loadout package owns this object and no vanilla holder with a package references it'}
    end
    local package=database.packages[item.package]
    return {key=key,known=true,autoLoadSupported=true,derivation=item.via,liveTested=item.live==true,
        package=package.named and package.name:match('[^/]+$')or nil,retain=database.policy.retain}
end

-- A sound event's bank (runtime/sound_catalogue.lua): its stratagem's call-in packages that list the bank, or the
-- loadout item's own package that lists it; nil and why for a resident-only bank.
local function event_dependencies(name)
    local catalogue=require('hd2runtime/runtime/sound_catalogue')
    local canonical,e=catalogue.resolve(name)
    if not e then return nil,'no sound '..tostring(name)end
    local p=catalogue.provider(e)
    if not p then
        return nil,'the '..canonical..' sound is resident-only: no stratagem or loadout package Runtime can load lists its bank'
    end
    local out={}
    if p.stratagem then
        for _,dep in ipairs(assets.dependencies_for_stratagem(p.stratagemId,p.stratagem)or{})do
            for _,package in ipairs(p.packages or{})do
                if dep.package==package then
                    out[#out+1]={key='sound/'..canonical..(#out>0 and('/'..(#out+1))or''),package=dep.package,
                        label=canonical..' sound',name=dep.name,via='sound_bank_stratagem_call_in'}
                end
            end
        end
    elseif p.item then
        local dep=assets.dependency(p.item)
        if dep then
            out[1]={key='sound/'..canonical,package=dep.package,label=canonical..' sound',name=dep.name,
                via='sound_bank_loadout_item'}
        end
    end
    if#out==0 then return nil,'no package is known for the '..canonical..' sound'end
    return out
end

-- A catalogue sound's bank: its stratagem's call-in packages that list the bank (the packages a Pelican gun or a
-- sentry taking that sound requests; runtime/weapon_sounds.lua), or nil and why. A sound event of the full catalogue
-- (runtime/sound_catalogue.lua): the package of the stratagem or loadout item that provides its bank.
function M.sound_dependencies(name)
    local canonical,s=weapon_sounds.resolve(name)
    if not s then return event_dependencies(name)end
    if s.own then return {}end
    if not(s.stratagemId and s.stratagem)then
        return nil,'the '..canonical..' sound is resident-only: no stratagem package provides its bank'
    end
    local out={}
    for _,dep in ipairs(assets.dependencies_for_stratagem(s.stratagemId,s.stratagem)or{})do
        for _,p in ipairs(s.requests or{})do
            if dep.package==p then
                out[#out+1]={key='sound/'..canonical..(#out>0 and('/'..(#out+1))or''),package=dep.package,
                    label=s.label..' sound',name=dep.name,via='sound_bank_stratagem_call_in'}
            end
        end
    end
    if#out==0 then return nil,'no package is known for the '..canonical..' sound'end
    return out
end

local function dependencies_for(request)
    local targets=request.targets or{request.target}
    assert(type(targets)=='table'and#targets>=1 and#targets<=16,'require_assets takes one to 16 targets')
    local found={}
    for _,target in ipairs(targets)do
        local key,why=M.key_for(target)
        assert(key,why)
        if key:match('^sound/')then
            local list,swhy=M.sound_dependencies(target.sound)
            assert(list,'ASSET_UNAVAILABLE: '..tostring(swhy))
            for _,dependency in ipairs(list)do found[#found+1]=dependency end
        else
            local dependency=assets.dependency(key)
            assert(dependency,'ASSET_UNAVAILABLE: no known package for '..key)
            found[#found+1]=dependency
        end
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
