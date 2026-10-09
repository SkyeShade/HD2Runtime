-- Public read-only structural weapon enumeration job.
local b=require('hd2runtime/core/bytes')
local Reader=require('hd2runtime/runtime/reader')
local discover=require('hd2runtime/runtime/discover')
local entities=require('hd2runtime/core/entity_catalog')
local weapon_metadata=require('hd2runtime/core/weapon_metadata')
local stratagem=require('hd2runtime/core/stratagem')
local profile=require('hd2runtime/schemas/current')
local mapper_schema=require('hd2runtime/schemas/weapon_mapper')
local M={}

local provenance={
    projectile_type={source='Jar-5_buff/research/jar5-evidence.json',structural_candidate=true,
        schema_labelled=true,gameplay_proven=true,native_consumer_proven=false},
    damage={source='Jar-5_buff/research/jar5-evidence.json',structural_candidate=true,
        schema_labelled=true,gameplay_proven=true,native_consumer_proven=false},
    crosshair_type={source='ReticleAmr/research/gameplay-confirmation-0.1.0.json',structural_candidate=true,
        schema_labelled=true,gameplay_proven=true,native_consumer_proven=false},
}
local damage_fields={
    {'standard_damage',4,'i32'},{'durable_damage',8,'i32'},
    {'ap_direct',12,'u32'},{'ap_slight',16,'u32'},{'ap_large',20,'u32'},{'ap_extreme',24,'u32'},
    {'demolition',28,'u32'},{'stagger',32,'u32'},{'push_force',36,'u32'},
}
local function status_effects(damage_bytes)
    local result={}
    for index=0,3 do
        local offset=44+index*8
        local effect_type=b.u32(damage_bytes,offset)
        if effect_type==0 then break end
        result[#result+1]={type=effect_type,strength=b.value(damage_bytes,offset+4,'f32')}
    end
    return result
end
local unmapped=mapper_schema.unmapped
local component_names={'ProjectileWeaponComponentData','WeaponDataComponentData',
    'LoadoutPackageComponentData','WeaponMagazineComponentData','WeaponRoundsComponentData',
    'WeaponCustomizationComponentData','ArcWeaponComponentData','MeleeWeaponComponentData',
    'BeamWeaponComponentData','SprayWeaponComponentData','WeaponHeatComponentData',
    'WeaponChargeComponentData',
    'ExplosiveComponentData','HellpodRackComponentData','WeaponLinkedAmmoComponentData',
    'BackpackComponentData','WeaponLinkerComponentData'}

local function copy(value)
    if type(value)~='table'then return value end
    local out={};for key,item in pairs(value)do out[key]=copy(item)end;return out
end
local function field(output,name,value,evidence)
    local p=copy(evidence);p.current_live_ownership_proven=output.mode=='live'
    output.resolvedFields[name]={value=value,provenance=p}
    output.matchFields[name]=value
end
local function attach_status_attacks(output,roots,parent)
    if not roots.status then return end
    for _,effect in ipairs(parent.statusEffects or{})do
        local settings_record=roots.status.records[effect.type]
        if settings_record then
            output.attacks[#output.attacks+1]={role=parent.role..'_status_'..effect.type,kind='Status',
                parentRole=parent.role,statusType=effect.type,
                statusSettings={group=settings_record.group,row=settings_record.row,
                    recordType=effect.type,settingsType=settings_record.settings_type},
                resolvedFields={status_strength=effect.strength,
                    status_duration=b.value(settings_record.bytes,40,'f32')}}
        end
    end
end
local function damage_attack(output,roots,damage_consumers,kind,settings_name,settings_record,damage_type,attack,promote)
    local damage=assert(roots.damage.records[damage_type],'linked DamageInfo record absent')
    attack=attack or{role='primary',kind=kind,resolvedFields={}}
    attack.damageInfo={group=damage.group,row=damage.row,
        recordType=damage_type,settingsType=damage.settings_type,
        projectileConsumerCount=#(damage_consumers[damage_type]or{})}
    attack.statusEffects=status_effects(damage.bytes)
    if settings_name and settings_record then
        attack[settings_name]={group=settings_record.group,row=settings_record.row,
            recordType=b.u32(settings_record.bytes,0),settingsType=settings_record.settings_type}
    end
    if not output.attacks[1]or output.attacks[#output.attacks]~=attack then
        output.attacks[#output.attacks+1]=attack
    end
    if promote~=false then field(output,'damage_type',damage_type,provenance.damage)end
    for _,spec in ipairs(damage_fields)do
        local name,value=spec[1],b.value(damage.bytes,spec[2],spec[3])
        if promote~=false then field(output,name,value,provenance.damage)end
        attack.resolvedFields[name]=value
    end
    attach_status_attacks(output,roots,attack)
    return attack
end
local function explosion_attack(output,roots,damage_consumers,explosion_type,role,parent_role)
    if explosion_type==0 or not roots.explosion then return nil end
    local explosion=assert(roots.explosion.records[explosion_type],
        'linked ExplosionSettings record absent')
    local attack={role=role,kind='Explosion',explosionType=explosion_type,parentRole=parent_role,
        explosionSettings={group=explosion.group,row=explosion.row,recordType=explosion_type,
            settingsType=explosion.settings_type},resolvedFields={}}
    output.attacks[#output.attacks+1]=attack
    local radius_fields={{'explosion_inner_radius',16},{'explosion_outer_radius',20},
        {'explosion_shockwave_radius',24}}
    for _,spec in ipairs(radius_fields)do
        attack.resolvedFields[spec[1]]=b.value(explosion.bytes,spec[2],'f32')
    end
    return damage_attack(output,roots,damage_consumers,'Explosion','explosionSettings',
        explosion,b.u32(explosion.bytes,4),attack,false)
end
local function projectile_attack(output,roots,damage_consumers,projectile_type,role,promote)
    if projectile_type==0 then return nil end
    for _,existing in ipairs(output.attacks)do
        if existing.kind=='Projectile'and existing.projectileType==projectile_type then
            existing.sources=existing.sources or{}
            existing.sources[#existing.sources+1]=role
            return existing
        end
    end
    local projectile=assert(roots.projectile.records[projectile_type],
        'linked ProjectileSettings record absent')
    local attack={role=role,kind='Projectile',projectileType=projectile_type,
        projectileSettings={group=projectile.group,row=projectile.row,
            recordType=projectile_type,settingsType=projectile.settings_type},
        resolvedFields={},sources={role}}
    output.attacks[#output.attacks+1]=attack
    for _,name in ipairs({'pellet_count','projectile_velocity','projectile_mass','drag','gravity'})do
        local spec=mapper_schema.fields[name]
        local value=b.value(projectile.bytes,spec.offset,spec.storage)
        attack.resolvedFields[name]=value
        if promote then field(output,name,value,spec.evidence)end
    end
    local damage_type=b.u32(projectile.bytes,60)
    local damage=assert(roots.damage.records[damage_type],'linked DamageInfo record absent')
    attack.damageInfo={group=damage.group,row=damage.row,recordType=damage_type,
        settingsType=damage.settings_type,projectileConsumerCount=#(damage_consumers[damage_type]or{})}
    attack.statusEffects=status_effects(damage.bytes)
    attack.resolvedFields.damage_type=damage_type
    for _,spec in ipairs(damage_fields)do
        local name,value=spec[1],b.value(damage.bytes,spec[2],spec[3])
        attack.resolvedFields[name]=value
        if promote then field(output,name,value,provenance.damage)end
    end
    if promote then field(output,'damage_type',damage_type,provenance.damage)end
    attach_status_attacks(output,roots,attack)
    if roots.explosion then
        explosion_attack(output,roots,damage_consumers,b.u32(projectile.bytes,144),
            role..'_impact',role)
        local expiry=b.u32(projectile.bytes,156)
        if expiry~=b.u32(projectile.bytes,144) then
            explosion_attack(output,roots,damage_consumers,expiry,role..'_expiry',role)
        end
    end
    return attack
end

function M.start(runtime,emit,request)
    request=request or {};emit=emit or print
    local job={status='pending'}
    local reader
    local worker=coroutine.create(function()
        reader=Reader.new(runtime);reader.stage='runtime/windows_readonly:fingerprint'
        local exe,dll=runtime.module(nil),runtime.module('game.dll')
        if not exe or not dll then error('TARGET_UNAVAILABLE: game modules not ready',0)end
        local exe_sha,dll_sha=runtime.module_hash(exe),runtime.module_hash(dll)
        if not request.historical_analysis then
            assert(exe_sha==profile.exe_sha and dll_sha==profile.dll_sha,'unsupported build fingerprint')
        end
        local needed={entity=true,projectile=true,damage=true,arc='optional',beam='optional'}
        if request.support_graph then needed.explosion=true;needed.status=true end
        local roots=discover.locate(runtime,reader,profile,needed)
        -- An identity scan (no write, historical snapshots included): the records' own bytes, wherever the game reads
        -- them from now (core/component_tables.lua guards the writes).
        local catalog=entities.capture(reader,roots.entity,profile,component_names,{identity_scan=true})
        local weapon_candidates={}
        for _,candidate in ipairs(catalog.candidates)do
            if candidate.ownership.ProjectileWeaponComponentData
                or candidate.ownership.WeaponDataComponentData then
                weapon_candidates[#weapon_candidates+1]=candidate
            end
        end
        assert(#weapon_candidates==profile.weapon_mapper.expected_candidates,
            'weapon candidate count changed')
        local damage_consumers={}
        for projectile_type,record in pairs(roots.projectile.records)do
            local damage_type=b.u32(record.bytes,60)
            local consumers=damage_consumers[damage_type] or {}
            consumers[#consumers+1]=projectile_type;damage_consumers[damage_type]=consumers
        end
        local results,failed={},0
        for index,candidate in ipairs(weapon_candidates)do
            reader.stage='api/weapon_mapper:candidate_checkpoint';reader.checkpoint()
            local output={resourceHash=candidate.resourceHash,entityRow=candidate.entityRow,
                ownership=copy(candidate.ownership),resolvedFields={},matchFields={},attacks={},
                diagnostics=copy(candidate.diagnostics),mode=runtime.mode or 'fixture'}
            output.implementationFamilies=weapon_metadata.implementation_families(candidate.ownership)
            if candidate.ownership.ProjectileWeaponComponentData then
                output.matchFields.attack_kind='Projectile'
            end
            local resolved=0
            local function attempt(label,action)
                local ok,why=pcall(action)
                if ok then resolved=resolved+1
                else output.diagnostics[#output.diagnostics+1]=label..': '..tostring(why)end
            end
            local weapon_data=candidate.ownership.WeaponDataComponentData
            if weapon_data then
                attempt('WeaponDataComponentData',function()
                    local record=catalog.record(candidate,'WeaponDataComponentData')
                    output.weaponData={recordIndex=weapon_data.recordIndex,
                        ownerCount=weapon_data.ownerCount,uniqueOwner=weapon_data.uniqueOwner,
                        componentType=weapon_data.componentType}
                    field(output,'crosshair_type',b.u32(record.bytes,400),provenance.crosshair_type)
                    for _,name in ipairs({'spread_horizontal','spread_vertical','sway','ergonomics',
                        'primary_fire_mode'})do
                        local spec=mapper_schema.fields[name]
                        field(output,name,b.value(record.bytes,spec.offset,spec.storage),spec.evidence)
                    end
                    local hs=mapper_schema.fields.horizontal_recoil
                    local horizontal=(b.value(record.bytes,hs.offsets[1],'f32')
                        +b.value(record.bytes,hs.offsets[2],'f32'))/2
                    local vs=mapper_schema.fields.vertical_recoil
                    local vertical=(b.value(record.bytes,vs.offsets[1],'f32')
                        +b.value(record.bytes,vs.offsets[2],'f32'))/2
                    field(output,'horizontal_recoil',horizontal,hs.evidence)
                    field(output,'vertical_recoil',vertical,vs.evidence)
                    field(output,'recoil',(horizontal+vertical)/2,mapper_schema.fields.recoil.evidence)
                    for _,name in ipairs({'recoil_drift_horizontal','recoil_drift_vertical',
                        'recoil_climb_horizontal','recoil_climb_vertical'})do
                        local spec=mapper_schema.fields[name]
                        field(output,name,b.value(record.bytes,spec.offset,spec.storage),spec.evidence)
                    end
                    local suppressed=mapper_schema.fields.is_suppressed
                    field(output,'is_suppressed',b.value(record.bytes,suppressed.offset,suppressed.storage)~=0,
                        suppressed.evidence)
                end)
            end
            if candidate.ownership.WeaponHeatComponentData then
                attempt('WeaponHeatComponentData',function()
                    local record=catalog.record(candidate,'WeaponHeatComponentData')
                    for _,name in ipairs({'heat_capacity','heat_per_shot','heat_per_second',
                        'heat_cool_per_second','heatsink_starting','heatsink_from_supply',
                        'heatsink_spare'})do
                        local spec=mapper_schema.fields[name]
                        field(output,name,b.value(record.bytes,spec.offset,spec.storage),spec.evidence)
                    end
                end)
            end
            local loadout=candidate.ownership.LoadoutPackageComponentData
            if loadout then
                attempt('LoadoutPackageComponentData',function()
                    local record=catalog.record(candidate,'LoadoutPackageComponentData')
                    local slot,detail=weapon_metadata.weapon_slot(record.bytes,mapper_schema)
                    output.weaponSlot=detail
                    if slot then field(output,'weapon_slot',slot,mapper_schema.fields.weapon_slot.evidence)end
                end)
            else output.weaponSlot={status='UNCLASSIFIED',reason='loadout package ownership absent'}end
            local capacity_records={}
            for _,name in ipairs({'WeaponMagazineComponentData','WeaponRoundsComponentData',
                'WeaponCustomizationComponentData'})do
                if candidate.ownership[name]then
                    attempt(name,function()capacity_records[name]=catalog.record(candidate,name).bytes end)
                end
            end
            if next(capacity_records)then
                attempt('weapon capacity',function()
                    output.ammo=weapon_metadata.ammo(capacity_records,mapper_schema)
                    output.capacity=output.ammo.capacity
                    if output.capacity.baseValue~=nil then
                        field(output,'base_capacity',output.capacity.baseValue,
                            mapper_schema.fields.capacity.evidence)
                    end
                    if output.capacity.value~=nil then
                        field(output,'capacity',output.capacity.value,mapper_schema.fields.capacity.evidence)
                    end
                end)
            else
                output.ammo={kind='none',capacity={status='UNMAPPED',reason='no reviewed magazine/feed component'}}
                output.capacity=output.ammo.capacity
            end
            local charge_owner=candidate.ownership.WeaponChargeComponentData
            if charge_owner then
                attempt('WeaponChargeComponentData',function()
                    local charge=catalog.record(candidate,'WeaponChargeComponentData')
                    output.chargeCadence={recordIndex=charge_owner.recordIndex,
                        ownerCount=charge_owner.ownerCount,uniqueOwner=charge_owner.uniqueOwner,
                        levels={b.value(charge.bytes,0,'f32'),b.value(charge.bytes,24,'f32'),
                            b.value(charge.bytes,48,'f32')},
                        minimumSeconds=b.value(charge.bytes,72,'f32'),
                        maximumSeconds=b.value(charge.bytes,76,'f32'),
                        fireRateRepresentation='charge_controlled'}
                end)
            end
            local projectile_owner=candidate.ownership.ProjectileWeaponComponentData
            if projectile_owner then
                attempt('ProjectileWeaponComponentData',function()
                    local weapon=catalog.record(candidate,'ProjectileWeaponComponentData')
                    local projectile_type=b.u32(weapon.bytes,0)
                    field(output,'projectile_type',projectile_type,provenance.projectile_type)
                    local fire=mapper_schema.fields.fire_rate
                    field(output,'fire_rate',b.value(weapon.bytes,fire.offset,fire.storage),fire.evidence)
                    output.fireRateOptions={low=b.value(weapon.bytes,4,'f32'),
                        default=b.value(weapon.bytes,8,'f32'),high=b.value(weapon.bytes,12,'f32'),
                        representation='schema_vec3_selector'}
                    projectile_attack(output,roots,damage_consumers,projectile_type,'primary',true)
                end)
            end
            local rounds_owner=candidate.ownership.WeaponRoundsComponentData
            if rounds_owner then
                local rounds
                attempt('WeaponRoundsComponentData feed',function()
                    rounds=catalog.record(candidate,'WeaponRoundsComponentData')
                    local primary=b.u32(rounds.bytes,mapper_schema.fields.rounds_primary_projectile_type.offset)
                    local alternate=b.u32(rounds.bytes,mapper_schema.fields.rounds_alternate_projectile_type.offset)
                    field(output,'rounds_primary_projectile_type',primary,
                        mapper_schema.fields.rounds_primary_projectile_type.evidence)
                    field(output,'rounds_alternate_projectile_type',alternate,
                        mapper_schema.fields.rounds_alternate_projectile_type.evidence)
                end)
                if rounds then
                    local primary=b.u32(rounds.bytes,mapper_schema.fields.rounds_primary_projectile_type.offset)
                    local alternate=b.u32(rounds.bytes,mapper_schema.fields.rounds_alternate_projectile_type.offset)
                    if primary~=0 then attempt('WeaponRounds primary projectile',function()
                        projectile_attack(output,roots,damage_consumers,primary,'feed_primary',false)
                    end)end
                    if alternate~=0 and alternate~=primary then
                        attempt('WeaponRounds alternate projectile',function()
                            projectile_attack(output,roots,damage_consumers,alternate,'feed_alternate',false)
                        end)
                    end
                end
            end
            local arc_owner=candidate.ownership.ArcWeaponComponentData
            if arc_owner then
                attempt('ArcWeaponComponentData',function()
                    local component=catalog.record(candidate,'ArcWeaponComponentData')
                    local arc_type=b.u32(component.bytes,0)
                    output.matchFields.attack_kind='Arc'
                    field(output,'arc_type',arc_type,mapper_schema.fields.arc_type.evidence)
                    field(output,'fire_rate',b.value(component.bytes,4,'f32'),mapper_schema.fields.arc_fire_rate.evidence)
                    local arc=assert(roots.arc and roots.arc.records[arc_type],
                        'linked ArcSettings record absent')
                    local attack=damage_attack(output,roots,damage_consumers,'Arc','arcSettings',arc,b.u32(arc.bytes,36))
                    attack.arcType=arc_type
                    field(output,'arc_velocity',b.value(arc.bytes,4,'f32'),mapper_schema.fields.arc_velocity.evidence)
                    field(output,'arc_range',b.value(arc.bytes,8,'f32'),mapper_schema.fields.arc_range.evidence)
                    for _,name in ipairs({'arc_distance_at_max_spread',
                        'arc_distance_at_max_spread_first_shot','arc_max_angle_spread',
                        'arc_max_angle_spread_first_shot','arc_chain_count','arc_max_split'})do
                        local spec=mapper_schema.fields[name]
                        field(output,name,b.value(arc.bytes,spec.offset,spec.storage),spec.evidence)
                    end
                    attack.resolvedFields.arc_velocity=b.value(arc.bytes,4,'f32')
                    attack.resolvedFields.arc_range=b.value(arc.bytes,8,'f32')
                    attack.resolvedFields.arc_spread=b.value(arc.bytes,12,'f32')
                    attack.resolvedFields.arc_chain_spread=b.value(arc.bytes,20,'f32')
                    attack.resolvedFields.arc_chain_count=b.u32(arc.bytes,28)
                    attack.resolvedFields.arc_max_split=b.u32(arc.bytes,32)
                end)
            end
            local beam_owner=candidate.ownership.BeamWeaponComponentData
            if beam_owner then
                attempt('BeamWeaponComponentData',function()
                    local component=catalog.record(candidate,'BeamWeaponComponentData')
                    local beam_type=b.u32(component.bytes,0)
                    output.matchFields.attack_kind='Beam'
                    field(output,'beam_type',beam_type,mapper_schema.fields.beam_type.evidence)
                    local beam=assert(roots.beam and roots.beam.records[beam_type],
                        'linked BeamSettings record absent')
                    local attack=damage_attack(output,roots,damage_consumers,'Beam','beamSettings',beam,b.u32(beam.bytes,12))
                    attack.beamType=beam_type
                    field(output,'beam_radius',b.value(beam.bytes,4,'f32'),mapper_schema.fields.beam_radius.evidence)
                    field(output,'beam_range',b.value(beam.bytes,8,'f32'),mapper_schema.fields.beam_range.evidence)
                end)
            end
            local spray_owner=candidate.ownership.SprayWeaponComponentData
            if spray_owner then
                attempt('SprayWeaponComponentData',function()
                    local component=catalog.record(candidate,'SprayWeaponComponentData')
                    local damage_type=b.u32(component.bytes,mapper_schema.fields.spray_damage_type.offset)
                    output.matchFields.attack_kind='Spray'
                    field(output,'spray_damage_type',damage_type,
                        mapper_schema.fields.spray_damage_type.evidence)
                    damage_attack(output,roots,damage_consumers,'Spray',nil,nil,damage_type)
                end)
            end
            local melee_owner=candidate.ownership.MeleeWeaponComponentData
            if melee_owner then
                attempt('MeleeWeaponComponentData',function()
                    local component=catalog.record(candidate,'MeleeWeaponComponentData')
                    local damage_type=b.u32(component.bytes,mapper_schema.fields.melee_damage_type.offset)
                    output.matchFields.attack_kind='Melee'
                    field(output,'melee_damage_type',damage_type,
                        mapper_schema.fields.melee_damage_type.evidence)
                    damage_attack(output,roots,damage_consumers,'Melee',nil,nil,damage_type)
                end)
            end
            output.mode=nil
            if resolved==0 then
                failed=failed+1
                output.resolutionStatus='FAILED'
            elseif #output.diagnostics>0 then output.resolutionStatus='PARTIAL'
            else output.resolutionStatus='RESOLVED' end
            results[#results+1]=output
            pcall(emit,string.format('[HD2Runtime] PRIMARY_WEAPON_SCAN candidate=%d/%d resource=%s status=%s',
                index,#weapon_candidates,candidate.resourceHash,output.resolutionStatus))
        end
        local support_graph=nil
        if request.support_graph then
            support_graph={explosiveEntities={},hellpodRacks={},linkedAmmoOwners={},
                backpackEntities={},weaponLinkers={},stratagems={},diagnostics={},
                settingsCounts={explosion=0,status=0}}
            for _ in pairs(roots.explosion.records)do
                support_graph.settingsCounts.explosion=support_graph.settingsCounts.explosion+1
            end
            for _ in pairs(roots.status.records)do
                support_graph.settingsCounts.status=support_graph.settingsCounts.status+1
            end
            for _,candidate in ipairs(catalog.candidates)do
                local function graph_attempt(label,action)
                    local ok,value=pcall(action)
                    if not ok then support_graph.diagnostics[#support_graph.diagnostics+1]=
                        candidate.resourceHash..' '..label..': '..tostring(value)end
                end
                if candidate.ownership.ExplosiveComponentData then graph_attempt('ExplosiveComponentData',function()
                    local record=catalog.record(candidate,'ExplosiveComponentData')
                    local node={resourceHash=candidate.resourceHash,entityRow=candidate.entityRow,
                        ownership={ExplosiveComponentData=copy(candidate.ownership.ExplosiveComponentData)},
                        attacks={},resolvedFields={},matchFields={},mode=runtime.mode or'fixture'}
                    local detonation=b.u32(record.bytes,36);local impact=b.u32(record.bytes,40)
                    explosion_attack(node,roots,damage_consumers,detonation,'detonation',nil)
                    if impact~=detonation then explosion_attack(node,roots,damage_consumers,impact,'impact',nil)end
                    node.mode=nil;support_graph.explosiveEntities[#support_graph.explosiveEntities+1]=node
                end)end
                if candidate.ownership.HellpodRackComponentData then graph_attempt('HellpodRackComponentData',function()
                    local record=catalog.record(candidate,'HellpodRackComponentData');local attached={}
                    for index=0,7 do
                        local resource=b.resource(record.bytes,index*64)
                        if resource~='0x0000000000000000'then attached[#attached+1]=resource end
                    end
                    support_graph.hellpodRacks[#support_graph.hellpodRacks+1]={resourceHash=candidate.resourceHash,
                        entityRow=candidate.entityRow,recordIndex=candidate.ownership.HellpodRackComponentData.recordIndex,
                        attachedResources=attached}
                end)end
                if candidate.ownership.WeaponLinkedAmmoComponentData then graph_attempt('WeaponLinkedAmmoComponentData',function()
                    local record=catalog.record(candidate,'WeaponLinkedAmmoComponentData')
                    support_graph.linkedAmmoOwners[#support_graph.linkedAmmoOwners+1]={
                        resourceHash=candidate.resourceHash,entityRow=candidate.entityRow,
                        recordIndex=candidate.ownership.WeaponLinkedAmmoComponentData.recordIndex,
                        linkedAmmoType=b.pointer(record.bytes,0),ammoClass=b.u32(record.bytes,8),
                        ammoVariant=b.u32(record.bytes,12),nativeValues={b.u32(record.bytes,16),
                            b.u32(record.bytes,20),b.u32(record.bytes,24),b.u32(record.bytes,28)}}
                end)end
                if candidate.ownership.BackpackComponentData then
                    support_graph.backpackEntities[#support_graph.backpackEntities+1]={
                        resourceHash=candidate.resourceHash,entityRow=candidate.entityRow,
                        recordIndex=candidate.ownership.BackpackComponentData.recordIndex}
                end
                if candidate.ownership.WeaponLinkerComponentData then graph_attempt('WeaponLinkerComponentData',function()
                    local record=catalog.record(candidate,'WeaponLinkerComponentData')
                    support_graph.weaponLinkers[#support_graph.weaponLinkers+1]={
                        resourceHash=candidate.resourceHash,entityRow=candidate.entityRow,
                        recordIndex=candidate.ownership.WeaponLinkerComponentData.recordIndex,
                        linkerType=b.u32(record.bytes,0),linkerId=b.u32(record.bytes,4),
                        flags=b.u32(record.bytes,8)}
                end)end
            end
            local ok,records=pcall(stratagem.capture_all,runtime,reader,profile)
            if ok then support_graph.stratagems=records
            else support_graph.diagnostics[#support_graph.diagnostics+1]='stratagems: '..tostring(records)end
            table.sort(support_graph.explosiveEntities,function(a,c)return a.resourceHash<c.resourceHash end)
            table.sort(support_graph.hellpodRacks,function(a,c)return a.resourceHash<c.resourceHash end)
            table.sort(support_graph.linkedAmmoOwners,function(a,c)return a.resourceHash<c.resourceHash end)
            table.sort(support_graph.backpackEntities,function(a,c)return a.resourceHash<c.resourceHash end)
            table.sort(support_graph.weaponLinkers,function(a,c)return a.resourceHash<c.resourceHash end)
        end
        local shared_projectiles={}
        for _,output in ipairs(results)do
            if output.matchFields.weapon_slot then
                for _,attack in ipairs(output.attacks)do
                    local settings_record=attack.projectileSettings
                    if settings_record then
                        local key=table.concat({settings_record.settingsType,settings_record.group,
                            settings_record.row,settings_record.recordType},':')
                        local group=shared_projectiles[key]or{key=key,consumers={}}
                        group.consumers[#group.consumers+1]=output
                        shared_projectiles[key]=group
                    end
                end
            end
        end
        for _,group in pairs(shared_projectiles)do
            if #group.consumers>1 then
                for _,output in ipairs(group.consumers)do
                    output.matchFields.use_weapon_data=true
                    output.sharedProjectileSettings=output.sharedProjectileSettings or{}
                    output.sharedProjectileSettings[#output.sharedProjectileSettings+1]=
                        {identity=group.key,classifiedPlayerResourceCount=#group.consumers}
                end
            end
        end
        reader.stage='runtime/reader:stable_reread';reader.verify()
        return {runtimeCandidates=results,supportGraph=support_graph,fingerprint={exe=exe_sha,dll=dll_sha},
            requestedProfileFingerprint={exe=profile.exe_sha,dll=profile.dll_sha},
            historicalAnalysis=request.historical_analysis==true,
            mode=runtime.mode or 'fixture',stableSnapshot=true,writes=0,protectionChanges=0,
            fixtureFallback='disabled',fieldsCurrentlyUsable={'weapon_slot','capacity','base_capacity',
                'recoil','horizontal_recoil','vertical_recoil','is_suppressed',
                'recoil_drift_horizontal','recoil_drift_vertical',
                'recoil_climb_horizontal','recoil_climb_vertical',
                'projectile_type','damage_type',
                'fire_rate','pellet_count','projectile_velocity','projectile_mass','drag','gravity',
                'arc_type','arc_velocity','arc_range','arc_distance_at_max_spread',
                'arc_distance_at_max_spread_first_shot','arc_max_angle_spread',
                'arc_max_angle_spread_first_shot','arc_chain_count','arc_max_split',
                'beam_type','beam_radius','beam_range',
                'spray_damage_type','melee_damage_type','rounds_primary_projectile_type',
                'rounds_alternate_projectile_type',
                'projectile_impact_explosion_type','projectile_expiry_explosion_type',
                'explosion_damage_type','explosion_inner_radius','explosion_outer_radius',
                'explosion_shockwave_radius','status_duration','status_strength',
                'charge_level_1','charge_level_2','charge_level_3','charge_min_seconds','charge_max_seconds',
                'spread_horizontal','spread_vertical','sway','ergonomics',
                'primary_fire_mode',
                'standard_damage','durable_damage','ap_direct','ap_slight','ap_large','ap_extreme',
                'demolition','stagger','push_force','crosshair_type'},
            fieldsNotRuntimeMapped=unmapped,metrics={candidateCount=#results,candidateFailures=failed,
                candidatesProcessed=#results,expectedCandidateCount=profile.weapon_mapper.expected_candidates,
                sharedDiscoveryPasses=1,queries=reader.queries,
                bytesRead=reader.bytes,queryLimit=100000,byteLimit=16*1024*1024,
                candidatesPerTick=1,candidateComponentReadLimit=#component_names}}
    end)
    function job.step()
        if job.status=='complete'or job.status=='rejected'then return true end
        job.status='running'
        local ok,result=coroutine.resume(worker)
        job.adapter=reader and reader.stage or 'runtime/windows_readonly:fingerprint'
        if not ok then
            job.status='rejected';job.error=tostring(result)
            job.code=job.error:sub(1,19)=='TARGET_UNAVAILABLE:'and'TARGET_UNAVAILABLE'or'VALIDATION_FAILED'
            pcall(emit,'[HD2Runtime] primary weapon mapper rejected: '..job.error)
            return true
        end
        if coroutine.status(worker)=='dead'then job.status='complete';job.result=result;return true end
        return false
    end
    return job
end
return M
