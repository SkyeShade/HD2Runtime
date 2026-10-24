-- Pre-fire acquisition and assignment. No process writes: the shared homing engine
-- retains projectile ownership, transactions, slot generation and write budgets.
local P=require('hd2runtime/runtime/homing_lock_policy')
local M={MAX_VALIDATIONS=8}
local function copy(t)local r={}for k,v in pairs(t)do r[k]=v end return r end
local function finite(v)return type(v)=='number'and v==v and math.abs(v)<1000000 end
function M.new(deps)
    local world,aim=deps.world,deps.aim
    local sources={};for _,source in ipairs(deps.weapon.sources)do sources[source]=true end
    local aim_height=deps.aim_height or 1
    local position_age=deps.position_age or .5
    local require_aim=deps.require_aim==true
    local c={};local config=assert(P.validate_config(deps.config))
    local policy=P.new();local stopped=false
    local context,session,frame;local basis,view_reason='weapon_root','not_observed'
    local state,reason='waiting',nil;local assigned=0
    local status={locked={},acquiring={}};local los_cache={};local visual_error
    local validation_cursor=0
    local aim_active,aim_reason=nil,'not_observed'
    local function log(event,fields)
        fields=fields or{};fields.event=event
        if deps.log then deps.log(fields)end
    end
    function c:visual_snapshot()
        local s={visible=config.enabled and config.show_hud and context~=nil and frame~=nil,
            frame=frame,half_angle=config.half_angle,max_targets=config.max_targets,mode=config.mode,
            locked={},acquiring={},session=session,reason=view_reason}
        for _,name in ipairs({'locked','acquiring'})do for _,t in ipairs(status[name])do
            local p=copy(t);p.z=p.z+aim_height;s[name][#s[name]+1]=p
        end end
        return s
    end
    local function publish()
        if not c.on_visual then return end
        local ok,why=pcall(c.on_visual,c:visual_snapshot())
        if not ok and visual_error~=tostring(why)then
            visual_error=tostring(why);log('hud_callback_error',{reason=visual_error})
        elseif ok then visual_error=nil end
    end
    local function clear_acquisition(why)
        los_cache={};validation_cursor=0;P.reset(policy,why)
        status={locked={},acquiring={}};state,reason='waiting',why
    end
    local function reset(why)
        context=nil;frame=nil;view_reason=why;aim_active=nil;aim_reason=why
        clear_acquisition(why);publish()
    end
    local function target_live(w,t)
        if not context or not config.enabled or not t or world.entity_exists(w,t.entity)~=true then return false end
        local s=world.entity_state(w,t.entity)
        return s~=nil and s.life==0 and s.descriptor.pointer==t.descriptor
            and s.descriptor.unit==t.unit
    end
    local function before(w,now,items)
        if not config.enabled or stopped then reset('disabled');return false end
        if deps.conflict and deps.conflict()then
            reset('another_homing_writer');state,reason='unavailable','another_homing_writer';return false
        end
        local current,why=aim.capture(w,sources)
        if not current then reset(why);state,reason='waiting',why;return false end
        local observed,view_why
        if deps.view then
            local ok,value,detail=pcall(deps.view.capture,w)
            if ok then observed,view_why=value,detail else view_why='camera_error:'..tostring(value)end
        end
        local next_basis=observed and'camera'or'weapon_root'
        local next_session=current.session_key..':'..next_basis..(observed and':'..tostring(observed.world)or'')
        if session~=next_session then
            reset('session_or_basis_changed');session=next_session
            log('session',{session=session,aim_basis=next_basis,view_reason=view_why})
        end
        context=current;frame=observed;basis=next_basis;view_reason=view_why
        local identity=current.session_key..':weapon:'..tostring(current.weapon_id)..':'..tostring(current.weapon_unit)
        if require_aim then
            aim_active=nil
            local reader=deps.aim_state and deps.aim_state.active
            if type(reader)=='function'then
                local ok,value,detail=pcall(reader,w)
                if ok and type(value)=='boolean'then aim_active=value end
                aim_reason=ok and type(detail)=='string'and detail or'aim_state_read_failed'
            else aim_reason='aim_state_unavailable'end
            if aim_active~=true then
                clear_acquisition(aim_active==false and'not_aiming'or aim_reason)
                publish()
                -- Aim release prevents new allocations. The same verified
                -- owner/weapon identity preserves already launched rounds.
                return true,identity
            end
        else aim_active=nil;aim_reason='not_required'end
        local origin=frame and frame.origin or current.origin
        local forward=frame and frame.forward or current.forward
        local function geometry(p)
            if not p or not finite(p.x)or not finite(p.y)or not finite(p.z)then return end
            local dx,dy,dz=p.x-origin.x,p.y-origin.y,p.z+aim_height-origin.z
            local distance=math.sqrt(dx*dx+dy*dy+dz*dz)
            if not finite(distance)or distance<=0 or distance>config.range then return end
            local cosine=math.max(-1,math.min(1,(dx*forward.x+dy*forward.y+dz*forward.z)/distance))
            local angle=math.deg(math.acos(cosine))
            if angle<=config.half_angle then return angle,distance end
        end
        -- Reuse the shared engine's bounded, aged position scan. Do not turn a
        -- 256-enemy list into 256 health/position/native reads every frame.
        local shortlist={}
        for _,item in ipairs(items or{})do
            if finite(item.at)and now>=item.at and now-item.at<=position_age then
                local angle,distance=geometry(item)
                if angle then shortlist[#shortlist+1]={item=item,angle=angle,distance=distance}end
            end
        end
        table.sort(shortlist,function(a,b)
            if a.angle~=b.angle then return a.angle<b.angle end
            if a.distance~=b.distance then return a.distance<b.distance end
            return a.item.entity<b.item.entity
        end)
        -- Keep in-progress acquisition continuous, while the remaining budget
        -- advances through other candidates (blocked front rows cannot starve
        -- every later visible enemy). Both groups still get fresh validation.
        local prior={}
        for _,name in ipairs({'locked','acquiring'})do for _,t in ipairs(status[name])do
            prior[t.entity]=t.unit
        end end
        local selected,chosen={},{}
        local function choose(item)
            if not selected[item.entity]and #chosen<M.MAX_VALIDATIONS then
                selected[item.entity]=true;chosen[#chosen+1]=item
            end
        end
        for _,entry in ipairs(shortlist)do
            if prior[entry.item.entity]==entry.item.unit then
                choose(entry.item)
            end
        end
        for _=1,#shortlist do
            if #chosen>=M.MAX_VALIDATIONS then break end
            validation_cursor=validation_cursor%#shortlist+1
            choose(shortlist[validation_cursor].item)
        end
        local candidates={};local los_missing=false
        for _,item in ipairs(chosen)do
            local live=world.entity_state(w,item.entity)
            local p=live and live.life==0 and live.descriptor.unit==item.unit
                and world.entity_exists(w,item.entity)==true
                and world.unit_position(w,live.descriptor.unit)
            local angle,distance=geometry(p)
            if angle then
                local point={x=p.x,y=p.y,z=p.z+aim_height}
                local projectable=true
                if frame then
                    local ok,result=pcall(deps.view.project,frame,point)
                    projectable=ok and result~=nil
                end
                if projectable then
                    local net=world.entity_network(w,item.entity)
                    if type(net)=='number'then
                        candidates[#candidates+1]={key=session..':'..item.entity..':'..live.descriptor.pointer,
                            entity=item.entity,descriptor=live.descriptor.pointer,unit=live.descriptor.unit,
                            net=net,node=16,name=item.name or tostring(item.entity),
                            x=p.x,y=p.y,z=p.z,angle_deg=angle,distance=distance,alive=true}
                    end
                end
            end
        end
        table.sort(candidates,function(a,b)
            if a.angle_deg~=b.angle_deg then return a.angle_deg<b.angle_deg end
            if a.distance~=b.distance then return a.distance<b.distance end
            return a.key<b.key
        end)
        -- At most 8 actual queries per observation; reuse unchanged rays for
        -- 0.1 seconds. Acquisition uses the camera, LOS uses the weapon root.
        local next_cache={};local rays=0
        for _,t in ipairs(candidates)do
            local point={x=t.x,y=t.y,z=t.z+aim_height};local cached=los_cache[t.key]
            local function close(a,b)return math.abs(a.x-b.x)+math.abs(a.y-b.y)+math.abs(a.z-b.z)<.1 end
            if cached and now>=cached.at and now-cached.at<=.1
                and close(cached.origin,current.origin)and close(cached.point,point)then
                t.visible,t.los_reason,t.los_observed_at=cached.value,cached.why,cached.at
                next_cache[t.key]=cached
            elseif rays<8 then
                rays=rays+1
                local ok,value,why,detail=pcall(aim.visible,w,current.origin,point,current,t.unit)
                if not ok then value,why=nil,'los_read_failed'end
                if not cached or cached.value~=value or cached.why~=why then
                    detail=type(detail)=='table'and detail or{}
                    log('los_observation',{target_entity=t.entity,target_unit=t.unit,
                        result=value==true and'clear'or(value==false and'blocked'or'unknown'),reason=why,
                        ray_hit_count=detail.hit_count,ray_hit_unit=detail.hit_unit,ray_hit_distance_m=detail.hit_distance,
                        origin_basis='weapon_root',game_time=now,projectile_hit_observed=false})
                end
                t.visible,t.los_reason,t.los_observed_at=value,why,now
                next_cache[t.key]={value=value,why=why,at=now,origin=copy(current.origin),point=point}
            else t.los_reason='los_query_budget'end
            t.los=t.visible==true and'clear'or(t.visible==false and'blocked'or'unknown')
            if t.visible==nil then los_missing=true end
        end
        los_cache=next_cache
        status=P.step(policy,now,candidates,config)
        state,reason=status.reason,config.require_los and los_missing and'los_unavailable'or nil
        -- Publish inside the engine observation, not the previous update callback:
        -- this keeps the visual cone and acquisition on the same camera frame.
        publish()
        -- A view/basis change restarts acquisition and HUD, but is not a new
        -- owner/weapon session. Keep already allocated flying rounds steering.
        return true,identity
    end
    local function spawn(w,slot,shot,now,key)
        if not context or shot.source~=context.weapon_id then return nil,'not_current_weapon'end
        if require_aim and aim_active~=true then return nil,reason or'aim_state_unavailable'end
        local target,why=P.assign(policy,key,now)
        if target and shot.observed_after and target.acquired_at>shot.observed_after then
            target,why=nil,'lock_after_observation_boundary'
        end
        if target and not target_live(w,target)then target,why=nil,'target_changed'end
        log('shot_assignment',{session=session,shot_key=key,game_pool_slot=slot,game_source_entity=shot.source,
            game_projectile_type=shot.type,target_entity=target and target.entity,
            target_key=target and target.key,result=why,lock_time=config.lock_time,mode=config.mode,
            target_los=target and target.los,los_sample_game_time=target and target.los_observed_at})
        if target then assigned=assigned+1 end
        return target,why
    end
    c.hooks={before=before,spawn=spawn,target_valid=target_live,
        reset=function(why)reset(why);session=nil end,
        unavailable=function(why)reset(why);state,reason='unavailable',why end}
    function c:stop()stopped=true;reset('stopped');state='stopped'end
    function c:status()return{state=state,reason=reason,locked=#status.locked,acquiring=#status.acquiring,
        assigned=assigned,aim_basis=basis,view_reason=view_reason,observed_at=policy.snapshot_time,
        aim_active=aim_active,aim_reason=aim_reason}end
    return c
end
return M
