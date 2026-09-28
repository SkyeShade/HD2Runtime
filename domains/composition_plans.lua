-- Declarative multi-target player-weapon composition plans. This layer validates
-- semantic identities and dependencies; core/guarded_transaction still owns every
-- byte, protection, verification, and rollback decision.
local domains=require('hd2runtime/domains/write_domains')
local M={}

local function valid_id(value,label)
    assert(type(value)=='string'and#value>0 and#value<=64
        and not value:find('[^%w_%-]'),label..' must be a short identifier')
end
local function keys(value,allowed,label)
    assert(type(value)=='table',label..' must be a descriptor')
    for key in pairs(value)do assert(allowed[key],
        'unsupported '..label..' option: '..tostring(key))end
end
local function target_from(dependency,path)
    local change=assert(dependency.spec.changes[1],'dependency has no change')
    assert(#dependency.spec.changes==1 and change.descriptor.type=='projectile_reference',
        'target_from operation must reference a projectile replacement operation')
    local selector=assert(change.desired_selector,'projectile replacement destination missing')
    if path=='projectile'then
        return {resource='player_weapon',path='projectile_reference',
            weapon=selector.weapon,attack=selector.attack}
    end
    local phase=path:match('^terminal%.(impact)$')or path:match('^terminal%.(expiry)$')
    assert(phase,'unsupported target_from path: '..tostring(path))
    return {resource='player_weapon',path='terminal_action',
        weapon=selector.weapon,attack=selector.attack,phase=phase}
end
local function backing_scope(change)
    local backing=assert(change.descriptor.backing,'composition field backing missing')
    if change.descriptor.operationGroup then return change.descriptor.operationGroup end
    if backing.kind=='settings'then
        return 'settings:'..assert(backing.settings,'composition settings owner missing')
    end
    if backing.kind=='component'then
        return 'component:'..assert(backing.component,'composition component owner missing')
    end
    error('unsupported composition backing kind: '..tostring(backing.kind),0)
end
local function validate_operation(plan,phase_index,index,item,known)
    keys(item,{id=true,target=true,target_from=true,field=true,expect=true,value=true,
        changes=true,allow_shared=true,allow_unverified_reference=true,allow_unverified_effect=true},
        'plan operation')
    valid_id(item.id,'plan operation id')
    assert(not known[item.id],'duplicate plan operation id: '..item.id)
    assert((item.target~=nil)~=(item.target_from~=nil),
        'plan operation requires exactly one target or target_from')
    assert((item.field~=nil)~=(item.changes~=nil),
        'plan operation requires exactly one field or changes list')
    local target=item.target;local dependency
    if item.target_from then
        keys(item.target_from,{operation=true,path=true},'target_from')
        dependency=assert(known[item.target_from.operation],
            'target_from operation must precede its dependent operation')
        assert(dependency.phase<phase_index,
            'target_from requires a prior phase for fresh resolution')
        target=target_from(dependency,item.target_from.path)
    end
    local request={id=item.id,target=target,diagnostic=plan.diagnostic,
        allow_shared=item.allow_shared==true}
    if item.allow_unverified_reference~=nil then
        request.allow_unverified_reference=item.allow_unverified_reference
    end
    if item.allow_unverified_effect~=nil then request.allow_unverified_effect=item.allow_unverified_effect end
    local spec
    if item.field~=nil then
        request.field=item.field;request.expect=item.expect;request.value=item.value
        spec=domains.for_resource(target.resource).validate_patch(request)
    else
        request.changes=item.changes
        spec=domains.for_resource(target.resource).validate_transaction(request)
    end
    local scope=backing_scope(spec.changes[1])
    for change_index=2,#spec.changes do
        assert(backing_scope(spec.changes[change_index])==scope,
            'plan operation '..item.id..' spans multiple backing objects; '
                ..'split it into operations so shared scope is explicit')
    end
    local operation={id=item.id,phase=phase_index,index=index,spec=spec,
        target=target,target_from=item.target_from,dependency=dependency and dependency.id or nil,
        allow_shared=item.allow_shared==true,backing_scope=scope}
    known[item.id]=operation
    return operation
end

function M.validate(request)
    keys(request,{id=true,operations=true,phases=true,diagnostic=true},'plan')
    valid_id(request.id,'plan id')
    assert((request.operations~=nil)~=(request.phases~=nil),
        'plan requires exactly one operations list or phases list')
    assert(request.diagnostic==nil or type(request.diagnostic)=='boolean','invalid diagnostic flag')
    local input=request.phases or{{operations=request.operations}}
    assert(type(input)=='table'and#input>=1 and#input<=8,'plan requires one to eight phases')
    local plan={kind='composition_plan',id=request.id,diagnostic=request.diagnostic==true,
        phases={},operations={},operation_by_id={}}
    local count=0
    for phase_index,source in ipairs(input)do
        keys(source,{id=true,operations=true},'plan phase')
        if source.id~=nil then valid_id(source.id,'plan phase id')end
        assert(type(source.operations)=='table'and#source.operations>=1,
            'plan phase requires operations')
        local phase={id=source.id or('phase-'..phase_index),index=phase_index,
            operations={},dependency_specs={},capture_specs={},capture_operation_ids={}}
        local dependency_seen={}
        for index,item in ipairs(source.operations)do
            count=count+1;assert(count<=64,'plan supports at most 64 operations')
            local operation=validate_operation(plan,phase_index,index,item,plan.operation_by_id)
            if operation.dependency then
                local dependency=plan.operation_by_id[operation.dependency]
                if not dependency_seen[dependency.id]then
                    phase.dependency_specs[#phase.dependency_specs+1]=dependency.spec
                    phase.capture_specs[#phase.capture_specs+1]=dependency.spec
                    phase.capture_operation_ids[#phase.capture_operation_ids+1]='dependency:'..dependency.id
                    dependency_seen[dependency.id]=true
                end
            end
            phase.operations[#phase.operations+1]=operation
            phase.capture_specs[#phase.capture_specs+1]=operation.spec
            phase.capture_operation_ids[#phase.capture_operation_ids+1]=operation.id
            plan.operations[#plan.operations+1]=operation
        end
        plan.phases[#plan.phases+1]=phase
    end
    return plan
end

local function same_bytes(a,c)return a==c end
function M.prepare_phase(resolved,reader,phase)
    assert(#resolved==#phase.capture_specs,'composition resolution count changed')
    local plan={changes={},snapshots=reader.snapshots,phase=phase.index,
        phase_id=phase.id,operation_fields={}}
    local physical={}
    for spec_index,spec in ipairs(phase.capture_specs)do
        local prepared=domains.for_kind(spec.kind).prepare(resolved[spec_index],reader,spec)
        local operation_id=assert(phase.capture_operation_ids[spec_index])
        plan.operation_fields[operation_id]={}
        for _,change in ipairs(prepared.changes)do
            local key=tostring(change.owner.base)..':'..tostring(change.offset)..':'..#change.desired
            local prior=physical[key]
            if prior then
                assert(prior.canonical_field==change.canonical_field
                    and same_bytes(prior.expected,change.expected),
                    'overlapping plan fields are not identical semantic aliases: '
                        ..prior.label..' and '..change.label)
                if not same_bytes(prior.desired,change.desired)then
                    error('SEMANTIC_CONFLICT: '..prior.label..' and '..change.label
                        ..' resolve to the same backing bytes with different desired values',0)
                end
                prior.plan_operations=prior.plan_operations or{}
                prior.plan_operations[#prior.plan_operations+1]=operation_id
                plan.operation_fields[operation_id][#plan.operation_fields[operation_id]+1]=prior
            else
                change.plan_operations={operation_id};physical[key]=change
                plan.changes[#plan.changes+1]=change
                plan.operation_fields[operation_id][#plan.operation_fields[operation_id]+1]=change
            end
        end
    end
    assert(#plan.changes>=1 and#plan.changes<=128,'plan phase write-set size unsupported')
    return plan
end
return M
