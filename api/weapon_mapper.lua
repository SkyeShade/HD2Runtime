-- Public read-only structural weapon enumeration job.
local b=require('hd2runtime/core/bytes')
local Reader=require('hd2runtime/runtime/reader')
local discover=require('hd2runtime/runtime/discover')
local entities=require('hd2runtime/core/entity_catalog')
local weapon_metadata=require('hd2runtime/core/weapon_metadata')
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
    'BeamWeaponComponentData','SprayWeaponComponentData'}

local function copy(value)
    if type(value)~='table'then return value end
    local out={};for key,item in pairs(value)do out[key]=copy(item)end;return out
end
local function field(output,name,value,evidence)
    local p=copy(evidence);p.current_live_ownership_proven=output.mode=='live'
    output.resolvedFields[name]={value=value,provenance=p}
    output.matchFields[name]=value
end
local function damage_attack(output,roots,damage_consumers,kind,settings_name,settings_record,damage_type,attack)
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
    field(output,'damage_type',damage_type,provenance.damage)
    for _,spec in ipairs(damage_fields)do
        local name,value=spec[1],b.value(damage.bytes,spec[2],spec[3])
        field(output,name,value,provenance.damage);attack.resolvedFields[name]=value
    end
    return attack
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
        local roots=discover.locate(runtime,reader,profile,
            {entity=true,projectile=true,damage=true,arc='optional',beam='optional'})
        local catalog=entities.capture(reader,roots.entity,profile,component_names)
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
                    output.capacity=weapon_metadata.capacity(capacity_records,mapper_schema)
                    if output.capacity.baseValue~=nil then
                        field(output,'base_capacity',output.capacity.baseValue,
                            mapper_schema.fields.capacity.evidence)
                    end
                    if output.capacity.value~=nil then
                        field(output,'capacity',output.capacity.value,mapper_schema.fields.capacity.evidence)
                    end
                end)
            else output.capacity={status='UNMAPPED',reason='no reviewed magazine/feed component'}end
            local projectile_owner=candidate.ownership.ProjectileWeaponComponentData
            if projectile_owner then
                attempt('ProjectileWeaponComponentData',function()
                    local weapon=catalog.record(candidate,'ProjectileWeaponComponentData')
                    local projectile_type=b.u32(weapon.bytes,0)
                    field(output,'projectile_type',projectile_type,provenance.projectile_type)
                    local fire=mapper_schema.fields.fire_rate
                    field(output,'fire_rate',b.value(weapon.bytes,fire.offset,fire.storage),fire.evidence)
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
        return {runtimeCandidates=results,fingerprint={exe=exe_sha,dll=dll_sha},
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
