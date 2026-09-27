-- Identity-only typed builders. Metadata and method names never carry an address.
local metadata=require('hd2runtime/domains/metadata')
local catalog=require('hd2runtime/domains/catalog')
local player_weapons=require('hd2runtime/domains/player_weapon_authoring')
local composition=require('hd2runtime/domains/player_weapon_composition')
local M={}
function M.new(describe)
    local builders={}
    local function copy(value)
        if type(value)~='table'then return value end
        local result={};for key,item in pairs(value)do result[key]=copy(item)end;return result
    end
    local function target(key,domain)
        local resource=metadata.resources[key]
        local methods={}
        local function names()
            local result={}
            for name,f in pairs(catalog[key])do
                if domain==resource.kind or f.domain==domain then result[#result+1]=name end
            end
            table.sort(result);return result
        end
        function methods.read_target()return {resource=key,fields=names()}end
        function methods.describe()
            local result=describe(key)
            local fields={}
            for _,name in ipairs(names())do fields[name]=result.fields[name]end
            result.fields=fields;result.domain=domain
            return result
        end
        for method,next_domain in pairs(metadata.types[domain].methods)do
            local next_type=next_domain
            methods[method]=function()
                local found=false
                for _,available in ipairs(resource.domains)do if available==next_type then found=true end end
                assert(found,'domain is not mapped for '..resource.label..': '..next_type)
                return target(key,next_type)
            end
        end
        -- Methods live on the metatable; strict patch/transaction identity validation is unchanged.
        return setmetatable({resource=key,path=domain},{__index=methods})
    end
    local function explosion_target(name,role,phase)
        local attack=assert(composition.weapons[name].attacks[role],'unknown reviewed attack role')
        local action=assert(attack.terminal_actions[phase],'unknown terminal action phase: '..tostring(phase))
        assert(action.reference_type~=0 and action.linked_explosion_record,
            'terminal action has no reviewed ExplosionSettings reference')
        local explosion
        for _,candidate in ipairs(attack.explosions or{})do
            if candidate.explosionType==action.reference_type then explosion=candidate;break end
        end
        assert(explosion,'reviewed ExplosionSettings descriptor missing')
        local methods={}
        function methods.describe()return copy(explosion)end
        function methods.damage(self)return self end
        function methods.shrapnel()return copy(explosion.shrapnel)end
        return setmetatable({resource='player_weapon',path='explosion',weapon=name,
            attack=attack.role,phase=phase},{__index=methods})
    end
    local function terminal_target(name,role,phase)
        local attack=assert(composition.weapons[name].attacks[role],'unknown reviewed attack role')
        local action=assert(attack.terminal_actions[phase],'unknown terminal action phase: '..tostring(phase))
        local methods={}
        function methods.describe()return copy(action)end
        function methods.explosion()return explosion_target(name,attack.role,phase)end
        return setmetatable({resource='player_weapon',path='terminal_action',weapon=name,
            attack=attack.role,phase=phase},{__index=methods})
    end
    local function projectile_reference(name,role)
        local attack=assert(composition.weapons[name].attacks[role],'unknown reviewed attack role')
        local methods={}
        function methods.describe()return copy(attack)end
        function methods.terminal_action(_,phase)return terminal_target(name,attack.role,phase)end
        return setmetatable({resource='player_weapon',path='projectile_reference',weapon=name,
            attack=attack.role},{__index=methods})
    end
    local function attack_target(name,role)
        local attack=assert(composition.weapons[name].attacks[role],
            'unknown reviewed attack role for '..name..': '..tostring(role))
        local methods={}
        function methods.describe()return copy(attack)end
        function methods.projectile()return projectile_reference(name,attack.role)end
        return setmetatable({resource='player_weapon',path='attack',weapon=name,attack=attack.role},
            {__index=methods})
    end
    local function magazine_target(name,option)
        local methods={};function methods.describe()return copy(option)end
        return setmetatable({resource='player_weapon',path='magazine_option',weapon=name,
            option=option.optionId or option.name},{__index=methods})
    end
    local function attachment_target(name,category,option)
        local methods={};function methods.describe()return copy(option)end
        return setmetatable({resource='player_weapon',path='attachment_option',weapon=name,
            category=category,option=option.name},{__index=methods})
    end
    local function attachment_category(graph,category)
        for _,item in ipairs(graph.magazine.attachment_categories or{})do
            if item.category==category then return item end
        end
    end
    local function player_target(name,legacy)
        local weapon=player_weapons.weapons[name]
        local graph=composition.weapons[name]
        local methods={}
        function methods.describe()return weapon end
        function methods.read_target()
            error('generic player-weapon live reads use the mapper/capability API')
        end
        if legacy then
            for method in pairs(metadata.types.weapon.methods)do
                if legacy[method]then methods[method]=function()return legacy[method](legacy)end end
            end
        end
        function methods.attacks()
            local result={};for _,role in ipairs(graph.attack_order)do
                result[#result+1]=attack_target(name,role)
            end
            return result
        end
        function methods.attack(_,role)return attack_target(name,role)end
        function methods.fire_modes()return copy(graph.fire_mode)end
        function methods.magazine_options()
            local result={};local category=attachment_category(graph,'Magazine')
            for _,option in ipairs(category and category.options or graph.magazine.observed_options)do
                result[#result+1]=magazine_target(name,option)
            end
            return result
        end
        function methods.default_magazine()
            local category=attachment_category(graph,'Magazine')
            if category then for _,option in ipairs(category.options)do
                if option.default then return magazine_target(name,option)end
            end end
            local option=graph.magazine.default_option
            return option and magazine_target(name,option)or nil
        end
        function methods.magazine(_,identity)
            local category=attachment_category(graph,'Magazine')
            if category then for _,option in ipairs(category.options)do
                local native=option.nativeOption
                if identity==option.name or native and identity==native.optionId then
                    return magazine_target(name,option)
                end
            end end
            local option=graph.magazine.default_option
            if option and(identity==option.name or identity==option.optionId)then
                return magazine_target(name,option)
            end
            for _,candidate in ipairs(graph.magazine.observed_options)do
                if identity==candidate.name or identity==candidate.optionId then
                    return magazine_target(name,candidate)
                end
            end
            error('unknown reviewed magazine option for '..name..': '..tostring(identity))
        end
        function methods.attachment_options(_,category)
            local item=assert(attachment_category(graph,category),
                'unknown reviewed attachment category for '..name..': '..tostring(category))
            local result={};for _,option in ipairs(item.options)do
                result[#result+1]=attachment_target(name,category,option)
            end
            return result
        end
        function methods.attachment(_,category,identity)
            local item=assert(attachment_category(graph,category),
                'unknown reviewed attachment category for '..name..': '..tostring(category))
            for _,option in ipairs(item.options)do if option.name==identity then
                return attachment_target(name,category,option)end end
            error('unknown reviewed attachment for '..name..': '..tostring(identity))
        end
        return setmetatable({resource='player_weapon',path='weapon',weapon=name},{__index=methods})
    end
    for method,domain in pairs(metadata.builders)do
        local kind=domain
        builders[method]=function(name)
            for key,resource in pairs(metadata.resources)do
                if resource.kind==kind then
                    for _,alias in ipairs(resource.aliases)do
                        if name==alias then
                            local legacy=target(key,kind)
                            if kind=='weapon'and player_weapons.weapons[name]then
                                return player_target(name,legacy)
                            end
                            return legacy
                        end
                    end
                end
            end
            if kind=='weapon'and player_weapons.weapons[name]then
                return player_target(name)
            end
            error('unknown reviewed '..kind..' alias: '..tostring(name))
        end
    end
    return builders
end
return M
