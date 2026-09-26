-- Public read-only structural weapon enumeration job.
local b=require('hd2runtime/core/bytes')
local Reader=require('hd2runtime/runtime/reader')
local discover=require('hd2runtime/runtime/discover')
local entities=require('hd2runtime/core/entity_catalog')
local profile=require('hd2runtime/schemas/current')
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
local unmapped={'fire_rate','capacity','projectile_velocity','projectile_mass','drag','gravity','pellet_count'}

local function copy(value)
    if type(value)~='table'then return value end
    local out={};for key,item in pairs(value)do out[key]=copy(item)end;return out
end
local function field(output,name,value,evidence)
    local p=copy(evidence);p.current_live_ownership_proven=output.mode=='live'
    output.resolvedFields[name]={value=value,provenance=p}
    output.matchFields[name]=value
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
        local roots=discover.locate(runtime,reader,profile,{entity=true,projectile=true,damage=true})
        local catalog=entities.capture(reader,roots.entity,profile,
            {'ProjectileWeaponComponentData','WeaponDataComponentData'})
        assert(#catalog.candidates==profile.weapon_mapper.expected_candidates,
            'weapon candidate count changed')
        local damage_consumers={}
        for projectile_type,record in pairs(roots.projectile.records)do
            local damage_type=b.u32(record.bytes,60)
            local consumers=damage_consumers[damage_type] or {}
            consumers[#consumers+1]=projectile_type;damage_consumers[damage_type]=consumers
        end
        local results,failed={},0
        for index,candidate in ipairs(catalog.candidates)do
            reader.stage='api/weapon_mapper:candidate_checkpoint';reader.checkpoint()
            local output={resourceHash=candidate.resourceHash,entityRow=candidate.entityRow,
                ownership=copy(candidate.ownership),resolvedFields={},matchFields={},attacks={},
                diagnostics=copy(candidate.diagnostics),mode=runtime.mode or 'fixture'}
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
                    field(output,'crosshair_type',b.u32(record.bytes,400),provenance.crosshair_type)
                end)
            end
            local projectile_owner=candidate.ownership.ProjectileWeaponComponentData
            if projectile_owner then
                attempt('ProjectileWeaponComponentData',function()
                    local weapon=catalog.record(candidate,'ProjectileWeaponComponentData')
                    local projectile_type=b.u32(weapon.bytes,0)
                    field(output,'projectile_type',projectile_type,provenance.projectile_type)
                    local projectile=assert(roots.projectile.records[projectile_type],
                        'linked ProjectileSettings record absent')
                    local damage_type=b.u32(projectile.bytes,60)
                    local damage=assert(roots.damage.records[damage_type],
                        'linked DamageInfo record absent')
                    local attack={role='primary',projectileType=projectile_type,
                        projectileSettings={group=projectile.group,row=projectile.row,
                            recordType=projectile_type,settingsType=projectile.settings_type},
                        damageInfo={group=damage.group,row=damage.row,recordType=damage_type,
                            settingsType=damage.settings_type,
                            projectileConsumerCount=#(damage_consumers[damage_type] or {})},
                        resolvedFields={}}
                    output.attacks[1]=attack
                    field(output,'damage_type',damage_type,provenance.damage)
                    for _,spec in ipairs(damage_fields)do
                        local name,value=spec[1],b.value(damage.bytes,spec[2],spec[3])
                        field(output,name,value,provenance.damage)
                        attack.resolvedFields[name]=value
                    end
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
                index,#catalog.candidates,candidate.resourceHash,output.resolutionStatus))
        end
        reader.stage='runtime/reader:stable_reread';reader.verify()
        return {runtimeCandidates=results,fingerprint={exe=exe_sha,dll=dll_sha},
            requestedProfileFingerprint={exe=profile.exe_sha,dll=profile.dll_sha},
            historicalAnalysis=request.historical_analysis==true,
            mode=runtime.mode or 'fixture',stableSnapshot=true,writes=0,protectionChanges=0,
            fixtureFallback='disabled',fieldsCurrentlyUsable={'projectile_type','damage_type',
                'standard_damage','durable_damage','ap_direct','ap_slight','ap_large','ap_extreme',
                'demolition','stagger','push_force','crosshair_type'},
            fieldsNotRuntimeMapped=unmapped,metrics={candidateCount=#results,candidateFailures=failed,
                candidatesProcessed=#results,expectedCandidateCount=profile.weapon_mapper.expected_candidates,
                sharedDiscoveryPasses=1,queries=reader.queries,
                bytesRead=reader.bytes,queryLimit=100000,byteLimit=16*1024*1024,
                candidatesPerTick=1,candidateComponentReadLimit=2}}
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
