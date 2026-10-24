-- Pre-fire homing support, extracted from the user-tested AR-23 Homing Lab 0.4.1.
-- The generic Runtime integration is not yet live-tested.
-- LOS result interpretation only. No FFI, native address, world lookup or physics
-- query is bundled here. An independently verified reader must be injected.
-- true = an observed clear segment; false = an observed obstruction; nil = unknown.
-- The caller supplies the weapon-root origin (not the acquisition camera) and the
-- exact target point used for acquisition. Weapon root is not a verified muzzle.
local M={MAX_HITS=64,MIN_DISTANCE=1,MAX_DISTANCE=400,MAX_COORDINATE=100000}
local function finite(n)return type(n)=='number'and n==n and math.abs(n)<math.huge end
local function uint(n)return finite(n)and n>=0 and n<4294967296 and n%1==0 end
local function identity(n)return uint(n)and n>0 and n<4294967295 end
local function vector(v)
    if type(v)~='table'then return nil end
    for _,k in ipairs({'x','y','z'})do
        if not finite(v[k])or math.abs(v[k])>M.MAX_COORDINATE then return nil end
    end
    return{x=v.x,y=v.y,z=v.z}
end
local function request(world,origin,target,ids)
    if type(world)~='table'or type(world.key)~='string'or#world.key==0 then return nil,'world_unavailable'end
    local start,finish=vector(origin),vector(target)
    if not start or not finish then return nil,'invalid_position'end
    if type(ids)~='table'or not identity(ids.target_unit)or not identity(ids.avatar_unit)
        or not identity(ids.weapon_unit)then return nil,'unit_identity_unavailable'end
    if ids.target_unit==ids.avatar_unit or ids.target_unit==ids.weapon_unit then return nil,'target_is_owner'end
    local x,y,z=finish.x-start.x,finish.y-start.y,finish.z-start.z
    local distance=math.sqrt(x*x+y*y+z*z)
    -- These are adapter admission bounds, not claims about the game's limits.
    -- The conservative 1..400 m segment range follows the reference LOS guard.
    if not finite(distance)or distance<M.MIN_DISTANCE or distance>M.MAX_DISTANCE then
        return nil,'distance_out_of_range'
    end
    return{world_key=world.key,origin=start,target=finish,direction={x=x/distance,y=y/distance,z=z/distance},
        distance=distance,target_unit=ids.target_unit,avatar_unit=ids.avatar_unit,weapon_unit=ids.weapon_unit}
end
local function interpret(result,q)
    if type(result)~='table'then return nil,'invalid_query_result'end
    if result.abi_verified~=true then return nil,'abi_unverified'end
    if result.world_verified~=true then return nil,'world_unverified'end
    if result.world_key~=q.world_key then return nil,'world_changed'end
    if result.overflow~=false or result.complete~=true then return nil,'incomplete_query'end
    if type(result.hits)~='table'then return nil,'invalid_hits'end
    local count,maximum=0,0
    for k in pairs(result.hits)do
        if not uint(k)or k<1 then return nil,'invalid_hits'end
        count=count+1;maximum=math.max(maximum,k)
        if count>M.MAX_HITS or maximum>M.MAX_HITS then return nil,'hit_capacity_exceeded'end
    end
    if count~=maximum then return nil,'sparse_hits'end
    local sorted,ignored={},0
    for i=1,count do
        local hit=result.hits[i]
        if type(hit)~='table'or not finite(hit.distance)or hit.distance<0 or hit.distance>q.distance
            or not uint(hit.unit)then return nil,'invalid_hit'end
        -- Unit 0 / UINT_MAX are allowed as non-entity geometry. They never equal
        -- our positively identified owner/target units and therefore block LOS.
        if hit.unit==q.avatar_unit or hit.unit==q.weapon_unit then ignored=ignored+1
        else sorted[#sorted+1]={distance=hit.distance,unit=hit.unit}end
    end
    -- Validate the entire result before deciding. A malformed later record must
    -- not disappear behind an earlier target hit and produce a false clear.
    table.sort(sorted,function(a,b)return a.distance<b.distance end)
    local detail={query_distance=q.distance,hit_count=count,ignored_owner_hits=ignored,
        origin_basis='weapon_root',native_query_observed=true,native_hit_observation=count>0}
    local first=sorted[1]
    if not first then return true,count==0 and'clear_no_hit'or'clear_owner_only',detail end
    local target_first=first.unit==q.target_unit
    for i=2,#sorted do
        local hit=sorted[i]
        if hit.distance~=first.distance then break end
        if (hit.unit==q.target_unit)~=target_first then return nil,'ambiguous_first_hit',detail end
    end
    detail.hit_distance,detail.hit_unit=first.distance,first.unit
    if target_first then return true,'target_hit',detail end
    return false,'occluded',detail
end

function M.new(deps)
    deps=deps or{}
    local reader=type(deps)=='table'and deps.read
    local instance={}
    -- reader(world, request) -> a complete normalized query result, or nil,reason.
    -- Required result fields: abi_verified=true, world_verified=true,
    -- world_key=request.world_key, complete=true, overflow=false, hits={...}.
    -- Each hit is {distance=<metres along segment>, unit=<game unit id>}.
    -- The reader must establish physics-world validity and query completeness;
    -- these booleans are evidence gates, not facts this pure module can discover.
    function instance:visible(world,origin,target,ids)
        if type(reader)~='function'then return nil,'reader_unavailable'end
        local q,why=request(world,origin,target,ids)
        if not q then return nil,why end
        -- Keep the proof inputs separate from the table handed to the reader.
        local proof={world_key=q.world_key,distance=q.distance,target_unit=q.target_unit,
            avatar_unit=q.avatar_unit,weapon_unit=q.weapon_unit}
        local ok,value,reason=pcall(reader,world,q)
        if world.key~=proof.world_key then return nil,'world_changed'end
        if not ok then return nil,'reader_error'end
        if value==nil then return nil,type(reason)=='string'and reason or'query_unavailable'end
        local parsed,clear,decision,detail=pcall(interpret,value,proof)
        if not parsed then return nil,'invalid_query_result'end
        return clear,decision,detail
    end
    return instance
end
return M
