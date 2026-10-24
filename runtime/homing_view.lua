-- Pre-fire homing support, extracted from the user-tested AR-23 Homing Lab 0.4.1.
-- The generic Runtime integration is not yet live-tested.
-- Read-only stingray camera adapter. API calls follow Guided Rounds' reticle code.
-- No guessed FOV, center correction, offset reads, FFI, GUI creation or native writes.
local M={}
local camera_cache
local DISCOVERY_CAPTURES=30 -- a capture-call limit, not a claimed wall-clock duration
local function finite(v) return type(v)=='number' and v==v and math.abs(v)<math.huge end
local function callable(v)
    if type(v)=='function' then return true end
    if type(v)~='table' and type(v)~='userdata' then return false end
    local mt=getmetatable(v)
    return type(mt)=='table' and type(mt.__call)=='function'
end
local function has(ns,key)
    local ok,v=pcall(function() return ns[key] end)
    return ok and callable(v)
end
-- HD2Runtime engine_gui.temp_scope documents the one-integer temporary-ring API.
-- Only ordinary tables/numbers and persistent camera/world handles leave this scope.
local function guarded(fn,...)
    local S=rawget(_G,'stingray'); local script=type(S)=='table' and S.Script
    if not has(script,'temp_count') or not has(script,'set_temp_count') then
        return false,nil,'temporary_api_missing'
    end
    local read,mark=pcall(script.temp_count)
    if not read or not finite(mark) or mark<0 or mark>=1048576 or mark%1~=0 then
        return false,nil,'temporary_mark_invalid'
    end
    local ok,value,reason=pcall(fn,...)
    local restored=pcall(script.set_temp_count,mark)
    if not restored then return false,nil,'temporary_restore_failed' end
    return ok,value,reason
end
local function xyz(v)
    return type(v)=='table' and finite(v.x) and finite(v.y) and finite(v.z)
        and math.abs(v.x)<=100000 and math.abs(v.y)<=100000 and math.abs(v.z)<=100000
end
local function unpack_vector(S,v)
    local out={x=S.Vector3.x(v),y=S.Vector3.y(v),z=S.Vector3.z(v)}
    return xyz(out) and out or nil
end
local function listed(S,world)
    for _,w in pairs(S.Application.worlds() or {}) do if w==world then return true end end
    return false
end
local function camera_live(f)
    local S=f.sr
    if rawget(_G,'stingray')~=S or not listed(S,f.world) or S.Unit.alive(f.camera_unit)~=true then return false end
    local n=S.Unit.num_cameras(f.camera_unit)
    return finite(n) and n>=f.camera_index and S.Unit.camera(f.camera_unit,f.camera_index)==f.camera
end
local function raw_project(f,p)
    local S=f.sr
    local v=S.Camera.world_to_screen(f.camera,S.Vector3(p.x,p.y,p.z),nil,S.Vector2(f.width,f.height))
    if v==nil then return nil end
    local x,y=S.Vector3.x(v),S.Vector3.y(v)
    if not finite(x) or not finite(y) then return nil end
    return {x=x,y=y}
end
local function project(f,p)
    if type(f)~='table' or not xyz(p) or not xyz(f.origin) or not xyz(f.forward) or not camera_live(f) then return nil end
    local depth=(p.x-f.origin.x)*f.forward.x+(p.y-f.origin.y)*f.forward.y+(p.z-f.origin.z)*f.forward.z
    if not finite(depth) or depth<=0 then return nil end
    local out=raw_project(f,p)
    -- The engine's raw x/y are used as bottom-origin GUI pixels, as in Guided Rounds.
    if not out or out.x<0 or out.y<0 or out.x>f.width or out.y>f.height then return nil end
    out.depth=depth -- signed distance along the captured forward axis; not engine depth-buffer z.
    return out
end
function M.project(frame,position)
    local ok,out=guarded(project,frame,position)
    return ok and out or nil
end
function M.radius(frame,half_angle_deg)
    if type(frame)~='table' or not finite(frame.height) or frame.height<=0
        or not finite(frame.vertical_fov) or frame.vertical_fov<=.05 or frame.vertical_fov>=3
        or not finite(half_angle_deg) or half_angle_deg<0 or half_angle_deg>=90 then return nil end
    local r=(frame.height/2)*math.tan(math.rad(half_angle_deg))/math.tan(frame.vertical_fov/2)
    return finite(r) and r or nil
end

local NEED={Application={'main_world','worlds'},World={'units','debug_camera_pose'},
    Unit={'alive','num_cameras','camera'},Camera={'world_position','vertical_fov','world_to_screen'},
    Matrix4x4={'translation','forward'},Gui={'resolution'},Vector3={'x','y','z'}}
local function engine()
    local S=rawget(_G,'stingray')
    if type(S)~='table' then return nil end
    for ns,names in pairs(NEED) do
        for _,name in ipairs(names) do if not has(S[ns],name) then return nil end end
    end
    if not callable(S.Vector2) or not callable(S.Vector3) then return nil end
    return S
end
local function candidate(S,world,unit,index,origin,forward,width,height)
    local camera=S.Unit.camera(unit,index)
    if camera==nil then return nil end
    local p=unpack_vector(S,S.Camera.world_position(camera))
    if not p or (p.x-origin.x)^2+(p.y-origin.y)^2+(p.z-origin.z)^2>.25 then return nil end
    local fov=S.Camera.vertical_fov(camera)
    if not finite(fov) or fov<=.05 or fov>=3 then return nil end
    local f={sr=S,world=world,camera=camera,camera_unit=unit,camera_index=index,
        origin=p,forward=forward,width=width,height=height,vertical_fov=fov,aim_basis='render_camera'}
    -- A similarly positioned camera is not enough: its axis must project to center.
    local axis=raw_project(f,{x=p.x+forward.x*50,y=p.y+forward.y*50,z=p.z+forward.z*50})
    if not axis or math.abs(axis.x-width/2)>2 or math.abs(axis.y-height/2)>2 then return nil end
    -- Confirm that this camera's projection scale agrees with its own FOV. A
    -- perpendicular direction suffices; this check does not assume camera roll.
    local rx,ry,rz=-forward.y,forward.x,0
    if rx*rx+ry*ry<.01 then rx,ry,rz=0,-forward.z,forward.y end
    local rl=math.sqrt(rx*rx+ry*ry+rz*rz); local spread=50*math.tan(math.rad(10))
    local edge=raw_project(f,{x=p.x+forward.x*50+rx/rl*spread,
        y=p.y+forward.y*50+ry/rl*spread,z=p.z+forward.z*50+rz/rl*spread})
    if not edge then return nil end
    local expected=M.radius(f,10)
    local actual=math.sqrt((edge.x-axis.x)^2+(edge.y-axis.y)^2)
    if math.abs(actual-expected)>math.max(2,expected*.02) then return nil end
    return f
end
local function discover_cameras(S,world)
    local units=S.World.units(world)
    if type(units)~='table' then return nil,'camera_units_unavailable' end
    local groups,count={},0
    for _,unit in pairs(units) do
        count=count+1
        if count>65536 then return nil,'camera_scan_limit' end
        if S.Unit.alive(unit)==true then
            local n=S.Unit.num_cameras(unit)
            if not finite(n) or n<0 or n>32 or n%1~=0 then return nil,'camera_count_invalid' end
            if n>0 then
                local group={unit=unit,count=n,cameras={}}
                for i=1,n do group.cameras[i]=S.Unit.camera(unit,i) or false end
                groups[#groups+1]=group
            end
        end
    end
    return groups
end
local function evaluate_cameras(S,world,groups,origin,forward,width,height)
    local found,seen=nil,{}
    for _,group in ipairs(groups) do
        if S.Unit.alive(group.unit)~=true or S.Unit.num_cameras(group.unit)~=group.count then
            return nil,'camera_cache_changed'
        end
        for index=1,group.count do
            if (S.Unit.camera(group.unit,index) or false)~=group.cameras[index] then
                return nil,'camera_cache_changed'
            end
            local ok,f=pcall(candidate,S,world,group.unit,index,origin,forward,width,height)
            if ok and f and not seen[f.camera] then
                if found then return nil,'camera_ambiguous' end
                seen[f.camera]=true; found=f
            end
        end
    end
    if not found then return nil,'camera_not_found' end
    return found
end
local function select_camera(S,world,origin,forward,width,height)
    -- Newly-created, coincident camera units with otherwise unchanged observations
    -- are discovered at the next bounded scan. Pose/FOV/projection are never cached.
    local c=camera_cache
    if c and c.sr==S and c.world==world and c.width==width and c.height==height and c.age<DISCOVERY_CAPTURES then
        -- Failed discovery still means no camera/HUD; reuse only the reason to
        -- avoid enumerating a large mission world every update while unavailable.
        if c.failure then c.age=c.age+1; return nil,c.failure end
        local f=evaluate_cameras(S,world,c.groups,origin,forward,width,height)
        -- A changed selection/FOV may be a scope switch with a newly-created camera.
        -- Discover immediately instead of accepting an older matching camera alone.
        if f and f.camera==c.camera and f.vertical_fov==c.fov then
            c.age=c.age+1; f.camera_discovery_cached=true; return f
        end
    end
    camera_cache=nil
    local function failed(why)
        camera_cache={sr=S,world=world,width=width,height=height,age=1,failure=why}
        return nil,why
    end
    local groups,why=discover_cameras(S,world)
    if not groups then return failed(why) end
    local f,reason=evaluate_cameras(S,world,groups,origin,forward,width,height)
    if not f then return failed(reason) end
    camera_cache={sr=S,world=world,width=width,height=height,age=1,groups=groups,camera=f.camera,fov=f.vertical_fov}
    f.camera_discovery_cached=false
    return f
end
local function ui_world(S,main,runtime_world)
    -- Reuse the Runtime's own read-only UI-world resolver when its already-proven
    -- event world is provided. No new offsets or native calls live in this module.
    if runtime_world~=nil then
        local ok,module=pcall(require,'hd2runtime/runtime/stratagem_slot_overlay')
        if ok and has(module,'ui_world') then
            local read,value=pcall(module.ui_world,runtime_world)
            if read and value~=nil and listed(S,value) then return value,nil,'runtime_ui_world' end
        end
    end
    -- Guided Rounds picks a non-main world. Require uniqueness for this fallback.
    local others={}
    for _,w in pairs(S.Application.worlds() or {}) do if w~=main then others[#others+1]=w end end
    if #others==1 then return others[1],nil,'sole_nonmain_reference' end
    return nil,#others==0 and 'ui_world_unavailable' or 'ui_world_ambiguous'
end
local function capture(runtime_world)
    local S=engine()
    if not S then return nil,'camera_api_missing' end
    local world=S.Application.main_world()
    if world==nil or not listed(S,world) then return nil,'world_unavailable' end
    local width,height=S.Gui.resolution()
    if not finite(width) or not finite(height) or width<320 or height<200
        or width>16384 or height>16384 then return nil,'resolution_unavailable' end
    local pose=S.World.debug_camera_pose(world)
    if pose==nil then return nil,'camera_pose_unavailable' end
    local origin=unpack_vector(S,S.Matrix4x4.translation(pose))
    local forward=unpack_vector(S,S.Matrix4x4.forward(pose))
    if not origin or not forward then return nil,'camera_pose_unavailable' end
    local length=math.sqrt(forward.x^2+forward.y^2+forward.z^2)
    if length<.99 or length>1.01 then return nil,'camera_forward_invalid' end
    forward={x=forward.x/length,y=forward.y/length,z=forward.z/length}
    local found,why=select_camera(S,world,origin,forward,width,height)
    if not found then return nil,why end
    if not camera_live(found) then return nil,'camera_changed' end
    found.ui_world,found.ui_reason,found.ui_source=ui_world(S,world,runtime_world)
    return found
end
function M.capture(runtime_world)
    local ok,out,reason=guarded(capture,runtime_world)
    if not ok then return nil,reason or 'camera_read_failed' end
    return out,reason
end
return M
