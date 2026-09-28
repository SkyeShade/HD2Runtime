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
        function methods.no_explosion()
            return {resource='player_weapon',path='no_explosion',weapon=name,
                attack=attack.role,phase=phase}
        end
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
    local support_catalog=require('hd2runtime/domains/support_weapon_catalog')
    local support_authoring=require('hd2runtime/domains/support_weapon_authoring')
    local function support_attack(name,index)
        local weapon=assert(support_catalog.weapons[name],'unknown reviewed support weapon')
        local attack=assert(weapon.attackGraph[index],'unknown support weapon attack index')
        local role=attack.runtimeMatch and attack.runtimeMatch.runtimeAttackRole
        local authoring=support_authoring.weapons[name]
        local writable=role and authoring and authoring.attacks[role]
        local methods={}
        function methods.describe()return copy(attack)end
        function methods.projectile()
            assert(writable and writable.kind=='Projectile','attack has no writable reviewed projectile object')
            local projectile_methods={}
            function projectile_methods.describe()return copy(writable)end
            function projectile_methods.damage(self)return self end
            return setmetatable({resource='support_weapon',path='projectile_reference',weapon=name,
                attack=role},{__index=projectile_methods})
        end
        function methods.explosion()
            assert(writable and writable.kind=='Explosion','attack has no writable reviewed explosion object')
            local explosion_methods={}
            function explosion_methods.describe()return copy(writable)end
            function explosion_methods.damage(self)return self end
            return setmetatable({resource='support_weapon',path='explosion',weapon=name,
                attack=role},{__index=explosion_methods})
        end
        function methods.damage(self)
            assert(writable and writable.kind~='Status','attack has no directly owned DamageInfo')
            return self
        end
        local identity={resource='support_weapon',path=writable and'attack'or'attack_read_only',weapon=name}
        if writable then identity.attack=role else identity.attack_index=index end
        return setmetatable(identity,{__index=methods})
    end
    function builders.support_weapon(name)
        local weapon=assert(support_catalog.weapons[name],
            'unknown reviewed support weapon: '..tostring(name))
        local methods={}
        function methods.describe()
            local result=copy(weapon);local authoring=support_authoring.weapons[name]
            result.authoring={writable=authoring and not authoring.ordinaryWritesBlocked or false,
                blockReason=authoring and authoring.blockReason or nil,
                writableFieldCount=authoring and#authoring.fields or 0}
            return result
        end
        function methods.attacks()
            local result={};for index=1,#weapon.attackGraph do result[index]=support_attack(name,index)end
            return result
        end
        function methods.attack(_,identity)
            if type(identity)=='number'then return support_attack(name,identity)end
            for index,item in ipairs(weapon.attackGraph)do
                if item.name==identity or item.runtimeMatch
                    and item.runtimeMatch.runtimeAttackRole==identity then return support_attack(name,index)end
            end
            error('unknown reviewed support attack: '..tostring(identity))
        end
        function methods.projectile(_,identity)return methods.attack(nil,identity):projectile()end
        function methods.explosion(_,identity)return methods.attack(nil,identity):explosion()end
        return setmetatable({resource='support_weapon',path='weapon',weapon=name},{__index=methods})
    end
    local legacy_stratagem=builders.stratagem
    local stratagem_authoring=require('hd2runtime/domains/stratagem_authoring')
    local function public_field(field)
        return {instanceKey=field.instanceKey,semanticFieldId=field.semanticFieldId,
            displayName=field.displayName,type=field.type,unit=field.unit,
            currentDefault=copy(field.currentDefault),editable=field.editable,
            reason=field.reason,backingObjectId=field.backingObjectId,
            operationGroup=field.operationGroup,planGroup=field.planGroup,
            requires=field.requires,allowSharedRequired=field.allowSharedRequired,
            shared=field.shared,sharedConsumers=copy(field.sharedConsumers),
            provenance=field.provenance}
    end
    local function stratagem_attack(name,role)
        local entry=assert(stratagem_authoring.stratagems[name])
        local attack=assert(entry.attacks[role],'unknown reviewed stratagem attack: '..tostring(role))
        local deployed=false
        for _,field in ipairs(entry.fields)do
            if field.target.attack==role and field.target.entity then deployed=true;break end
        end
        local methods={}
        function methods.describe()
            local result=copy(attack);result.fieldInstances={}
            for _,field in ipairs(entry.fields)do if field.target.attack==role then
                result.fieldInstances[#result.fieldInstances+1]=public_field(field)end end
            return result
        end
        function methods.projectile(self)
            assert(attack.kind=='ProjectileSettings','attack is not a projectile settings object');return self
        end
        function methods.explosion(self)
            assert(attack.kind=='ExplosionSettings','attack is not an explosion settings object');return self
        end
        function methods.damage(self)
            assert(attack.kind=='DamageInfo','attack is not a DamageInfo object');return self
        end
        function methods.status(self)
            assert(attack.kind=='StatusEffectSettings','attack is not a status settings object');return self
        end
        function methods.arc(self)
            assert(attack.kind=='ArcSettings','attack is not an arc settings object');return self
        end
        function methods.beam(self)
            assert(attack.kind=='BeamSettings','attack is not a beam settings object');return self
        end
        local identity={resource='stratagem',stratagem=name,path='attack',attack=role}
        if deployed then identity.entity='main';identity.weapon='primary'end
        return setmetatable(identity,{__index=methods})
    end
    local function stratagem_entity(name)
        local entry=assert(stratagem_authoring.stratagems[name])
        assert(entry.deployedEntity,'stratagem has no deployed entity definition')
        local methods={}
        function methods.describe()
            local result=copy(entry.deployedEntity);result.name=entry.name;result.fields={};result.weapons={}
            result.damageZones=copy(entry.damageZones or{});result.shield=copy(entry.shield)
            for _,field in ipairs(entry.fields)do
                local path=field.target.path
                if path=='deployed_entity' or path=='weapon' or path=='attack' or path=='shield'
                    or path=='damage_zone' then result.fields[#result.fields+1]=public_field(field)end
            end
            for role,attack in pairs(entry.attacks)do
                local weapon=attack.weapon or 'primary'
                result.weapons[weapon]=result.weapons[weapon] or {identity=weapon,attacks={}}
                result.weapons[weapon].attacks[#result.weapons[weapon].attacks+1]=role
            end
            return result
        end
        function methods.health(self)return self end
        function methods.weapon(_,identity)
            identity=identity or 'primary'
            local target={resource='stratagem',stratagem=name,path='weapon',entity='main',weapon=identity}
            local weapon_methods={}
            function weapon_methods.describe()
                local result={name=name,identity=identity,fields={},attacks={}}
                for _,field in ipairs(entry.fields)do
                    if field.target.path=='weapon' and field.target.weapon==identity
                        or field.target.path=='attack' and field.target.weapon==identity then
                        result.fields[#result.fields+1]=public_field(field)
                    end
                end
                for role,attack in pairs(entry.attacks)do
                    if (attack.weapon or 'primary')==identity then result.attacks[#result.attacks+1]=role end
                end
                table.sort(result.attacks);return result
            end
            function weapon_methods.attack(_,role)return stratagem_attack(name,role)end
            function weapon_methods.attacks()
                local result={}
                for role,attack in pairs(entry.attacks)do
                    if (attack.weapon or 'primary')==identity then result[#result+1]=stratagem_attack(name,role)end
                end
                table.sort(result,function(a,b)return a.attack<b.attack end);return result
            end
            return setmetatable(target,{__index=weapon_methods})
        end
        function methods.weapons()
            local result={};local seen={}
            for _,field in ipairs(entry.fields)do
                local identity=field.target.weapon
                if identity and not seen[identity]then seen[identity]=true;result[#result+1]=methods.weapon(nil,identity)end
            end
            for _,attack in pairs(entry.attacks)do
                local identity=attack.weapon or 'primary'
                if not seen[identity]then seen[identity]=true;result[#result+1]=methods.weapon(nil,identity)end
            end
            table.sort(result,function(a,b)return a.weapon<b.weapon end);return result
        end
        function methods.attack(_,role)return stratagem_attack(name,role)end
        local function sub_target(path,zone)
            local target={resource='stratagem',stratagem=name,path=path,entity='main',zone=zone}
            local sub={}
            function sub.describe()
                local result={name=name,path=path,zone=zone,fields={}}
                for _,field in ipairs(entry.fields)do
                    if field.target.path==path and field.target.zone==zone then
                        result.fields[#result.fields+1]=public_field(field)end
                end
                if path=='shield'then result.shield=copy(entry.shield)end
                return result
            end
            return setmetatable(target,{__index=sub})
        end
        function methods.shield()
            assert(entry.shield,'deployed entity has no reviewed shield configuration')
            return sub_target('shield')
        end
        local function zone_identity(identity)
            for _,zone in ipairs(entry.damageZones or{})do
                if identity==zone.zoneId or identity==zone.name
                    or type(identity)=='number'and zone.zoneId=='zone_'..identity then return zone.zoneId end
            end
            error('unknown reviewed damage zone for '..name..': '..tostring(identity),0)
        end
        function methods.damage_zones()
            local result={}
            for _,zone in ipairs(entry.damageZones or{})do result[#result+1]=sub_target('damage_zone',zone.zoneId)end
            return result
        end
        function methods.damage_zone(_,identity)return sub_target('damage_zone',zone_identity(identity))end
        return setmetatable({resource='stratagem',stratagem=name,path='deployed_entity',entity='main'},
            {__index=methods})
    end
    local entity_authoring=require('hd2runtime/domains/entity_authoring')
    local function entity_public(field)
        local result=public_field(field)
        result.target=copy(field.target);result.allowedValues=copy(field.allowedValues)
        result.acknowledgement=field.acknowledgement
        return result
    end
    local function fields_for(entry,path,key,value)
        local result={}
        for _,field in ipairs(entry.fields)do
            if field.target.path==path and(key==nil or field.target[key]==value)then
                result[#result+1]=entity_public(field)end
        end
        return result
    end
    local function weapon_view(identity)
        local weapon=assert(entity_authoring.mountedWeapons[identity],'unknown discovered mounted weapon')
        return {semanticId=weapon.semanticId,displayName=weapon.displayName,attackFamily=weapon.attackFamily}
    end
    local legacy_vehicle=builders.vehicle
    function builders.vehicle(name)
        local entry=entity_authoring.vehicles[name]
        if not entry then return legacy_vehicle(name)end
        local methods={}
        local function zone_target(zone)
            local zone_methods={}
            function zone_methods.describe()
                local info=entry.zones[zone]
                return {vehicle=name,zone=zone,index=info.index,name=info.name,
                    fields=fields_for(entry,'damage_zone','zone',zone)}
            end
            return setmetatable({resource='vehicle',vehicle=name,path='damage_zone',zone=zone},
                {__index=zone_methods})
        end
        local function zone_identity(identity)
            for zone,info in pairs(entry.zones)do
                if identity==zone or identity==info.name or identity==info.index then return zone end
            end
            error('unknown reviewed damage zone for '..name..': '..tostring(identity),0)
        end
        local function mount_target(mount)
            local info=entry.mounts[mount]
            local field
            for _,item in ipairs(entry.fields)do
                if item.target.path=='mount'and item.target.mount==mount then field=item end
            end
            local mount_methods={}
            function mount_methods.describe()
                return {vehicle=name,mount=mount,slot=info.slot,role=info.role,
                    current=weapon_view(info.current),fields=fields_for(entry,'mount','mount',mount)}
            end
            function mount_methods.current()return weapon_view(info.current)end
            function mount_methods.candidates()
                local result={}
                for _,identity in ipairs(field and field.allowedValues or{})do result[#result+1]=weapon_view(identity)end
                return result
            end
            function mount_methods.candidate(_,identity)
                local found
                for _,candidate in ipairs(mount_methods.candidates())do
                    if candidate.semanticId==identity or candidate.displayName==identity then
                        assert(not found,'mounted weapon display name is ambiguous; use its semanticId')
                        found=candidate
                    end
                end
                return assert(found,'not a compatible discovered mounted weapon: '..tostring(identity))
            end
            return setmetatable({resource='vehicle',vehicle=name,path='mount',mount=mount},
                {__index=mount_methods})
        end
        local function mount_identity(identity)
            for mount,info in pairs(entry.mounts)do
                if identity==mount or identity==info.role or identity==info.slot then return mount end
            end
            error('unknown swappable mount for '..name..': '..tostring(identity),0)
        end
        function methods.describe()
            local zones,mounts={},{}
            for zone,info in pairs(entry.zones)do zones[#zones+1]={zone=zone,index=info.index,name=info.name}end
            table.sort(zones,function(a,b)return a.index<b.index end)
            for mount,info in pairs(entry.mounts)do
                mounts[#mounts+1]={mount=mount,slot=info.slot,role=info.role,current=weapon_view(info.current)}
            end
            table.sort(mounts,function(a,b)return a.slot<b.slot end)
            return {name=name,semanticId=entry.semanticId,fields=fields_for(entry,'entity'),
                damageZones=zones,mounts=mounts}
        end
        function methods.entity(self)return self end
        function methods.health(self)return self end
        function methods.damage_zones()
            local ids={};for zone,info in pairs(entry.zones)do ids[#ids+1]={zone,info.index}end
            table.sort(ids,function(a,b)return a[2]<b[2]end)
            local result={};for index,item in ipairs(ids)do result[index]=zone_target(item[1])end
            return result
        end
        function methods.damage_zone(_,identity)return zone_target(zone_identity(identity))end
        function methods.mounts()
            local ids={};for mount,info in pairs(entry.mounts)do ids[#ids+1]={mount,info.slot}end
            table.sort(ids,function(a,b)return a[2]<b[2]end)
            local result={};for index,item in ipairs(ids)do result[index]=mount_target(item[1])end
            return result
        end
        function methods.mount(_,identity)return mount_target(mount_identity(identity))end
        return setmetatable({resource='vehicle',vehicle=name,path='entity'},{__index=methods})
    end
    function builders.backpack(name)
        local entry=assert(entity_authoring.backpacks[name],'unknown reviewed backpack: '..tostring(name))
        local methods={}
        function methods.describe()
            return {name=name,semanticId=entry.semanticId,fields=fields_for(entry,'backpack')}
        end
        return setmetatable({resource='backpack',backpack=name,path='backpack'},{__index=methods})
    end
    function builders.stratagem(name)
        local entry=stratagem_authoring.stratagems[name]
        if not entry then return legacy_stratagem(name)end
        local methods={}
        local legacy_ok,legacy=pcall(legacy_stratagem,name)
        if legacy_ok then for method in pairs(metadata.types.stratagem.methods)do
            if legacy[method]then methods[method]=function()return legacy[method](legacy)end end
        end
            if legacy.read_target then methods.read_target=function()return legacy:read_target()end end
        end
        function methods.describe()
            local result={name=entry.name,family=entry.family,rootResolution=entry.rootResolution,
                fields={},attackRoles={},deployedEntity=entry.deployedEntity,
                mineScopeDeferred=entry.family=='mine'}
            for _,field in ipairs(entry.fields)do if field.target.path=='stratagem'then
                result.fields[#result.fields+1]=public_field(field)end end
            for role in pairs(entry.attacks)do result.attackRoles[#result.attackRoles+1]=role end
            table.sort(result.attackRoles);return result
        end
        function methods.attacks()
            local roles={};for role in pairs(entry.attacks)do roles[#roles+1]=role end;table.sort(roles)
            local result={};for index,role in ipairs(roles)do result[index]=stratagem_attack(name,role)end
            return result
        end
        function methods.attack(_,role)return stratagem_attack(name,role)end
        function methods.deployed_entity()return stratagem_entity(name)end
        function methods.eagle_rearm()
            assert(entry.family=='eagle','stratagem has no Eagle rearm definition')
            local rearm_methods={}
            function rearm_methods.describe()
                local result={name=name,path='eagle_rearm',fields={}}
                for _,field in ipairs(entry.fields)do if field.target.path=='eagle_rearm'then
                    result.fields[#result.fields+1]=public_field(field)end end
                return result
            end
            return setmetatable({resource='stratagem',stratagem=name,path='eagle_rearm'},
                {__index=rearm_methods})
        end
        return setmetatable({resource='stratagem',stratagem=name,path='stratagem'},
            {__index=methods})
    end
    return builders
end
return M
