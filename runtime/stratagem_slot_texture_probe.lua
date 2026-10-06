-- The native-slot texture probe (development only, READ ONLY; docs/custom-stratagems.md, "A custom texture in a native
-- slot"). Not exported by api/hd2.lua and no public field reaches it. Nothing here writes.
--
-- The texture a loadout slot icon shows is not a main-thread field (research slotTexture): binding it stores the texture
-- in the material's CPU list and queues render command 7, which the render thread applies to the material's
-- render-side object R by storing the texture's render handle u32 [resource+0] into R+0x48[k]; every GUI draw reads it
-- there. A custom image in ONE slot would need a write into that render-thread memory, which is read concurrently. Before
-- any such write is considered, this probe resolves and checks the whole chain in the live game and logs it:
--   E = the slot widget's icon element; M = [E+0x148] (the element's own clone: owns bit set, external bit clear);
--   h = M+4; WRI = [M+8] - 0x10; RI = [WRI+0x10]; RW = [RI+0x80] - 0x10 (its vtable, RW+0x150 == WRI);
--   R = [[RW+0x170] + 8 * u32 [[RW+0x1C0] + 4 * (h & [WRI+0x40])]] (its vtable, kind 7, R's shader and template equal
--   M's); k = the index of the image property 0x3AA8B87E in R's properties; the handle R+0x48[k];
--   and, for comparison, the render handles of the atlas page the token's sprite is on and of the custom texture.
local world_module=require('hd2runtime/runtime/event_world')
local selector=require('hd2runtime/runtime/stratagem_selector')
local images=require('hd2runtime/runtime/image_resources')
local log_module=require('hd2runtime/runtime/log')
local b=require('hd2runtime/core/bytes')
local D=require('hd2runtime/domains/stratagem_selector')
local L,I,T=D.loadout,D.slotIcon,D.slotTexture
local M={}

local function log(text)log_module.emit('[HD2Runtime] slot texture probe '..text)end
local function hex(n)return n and string.format('0x%X',n)or'?'end
local function qword(world,at)
    local s=at and world.view.read(at,8)
    return s and b.u32(s,0)+b.u32(s,4)*4294967296
end
local function u32(world,at)return at and world.view.u32(at)end
local function base_of(runtime,name)
    for _,module in ipairs(runtime.modules and runtime.modules()or{})do
        if module.name and module.name:lower()==name then return module.base end
    end
end

-- One slot's chain, read: {slot, element, flags, owns, external, material, handle, rw, r, valid, why, property, k, texture
-- (the handle R+0x48[k])}. Never writes.
function M.slot(world,view,slot)
    local out={slot=slot}
    local E=view.ui+L.panel0Widgets+slot*L.widgetStride+I.element
    out.element=E
    out.flags=u32(world,E+I.flags)
    if not out.flags then out.why='the slot icon element is unreadable';return out end
    out.owns=math.floor(out.flags/T.elementOwns)%2==1
    out.external=math.floor(out.flags/T.elementExternal)%2==1
    local Mt=qword(world,E+I.material)
    out.material=Mt
    if not Mt or Mt==0 then out.why='the element has no material';return out end
    out.handle=u32(world,Mt+T.materialHandle)
    local world_ptr=qword(world,Mt+T.materialWorld)
    if not(out.handle and world_ptr and world_ptr~=0)then out.why='the material is unreadable';return out end
    local wri=world_ptr-T.worldOffset
    local ri=qword(world,wri+T.wriRenderInterface)
    local rw_ptr=ri and qword(world,ri+T.riRenderWorld)
    if not(rw_ptr and rw_ptr~=0)then out.why='the render interface is unreadable';return out end
    local rw=rw_ptr-T.worldOffset
    out.rw=rw
    local exe=world.exe or base_of(world.runtime,'helldivers2.exe')
    if exe and qword(world,rw)~=exe+T.rwVtable then out.why='the render world vtable differs';return out end
    if qword(world,rw+T.rwWri)~=wri then out.why='the render world does not point back to the world interface';return out end
    local mask=u32(world,wri+T.wriMask)
    local index_array,objects=qword(world,rw+T.rwIndex),qword(world,rw+T.rwObjects)
    if not(mask and index_array and objects)then out.why='the render tables are unreadable';return out end
    local idx=u32(world,index_array+4*(out.handle%(mask+1)))
    local R=idx and qword(world,objects+8*idx)
    out.r=R
    if not(R and R~=0)then out.why='no render object for the handle';return out end
    if exe and qword(world,R)~=exe+T.rmVtable then out.why='the render object vtable differs';return out end
    if u32(world,R+T.rmKind)~=T.rmKindMaterial then out.why='the render object is not a material';return out end
    if u32(world,R+T.rmShader)~=u32(world,Mt+T.materialShader)then out.why='the render material shader differs';return out end
    if qword(world,R+T.rmTemplate)~=qword(world,Mt+T.materialTemplate)then
        out.why='the render material template differs';return out
    end
    local count,props=u32(world,R+T.rmPropCount),qword(world,R+T.rmProps)
    local hcount,handles=u32(world,R+T.rmHandleCount),qword(world,R+T.rmHandles)
    if not(count and props and hcount and handles)or count>T.maxProps or hcount>T.maxProps then
        out.why='the render material properties are unreadable';return out
    end
    for k=0,count-1 do
        if u32(world,props+4*k)==T.imageProperty then out.k=k end
    end
    if out.k==nil or out.k>=hcount then out.why='no image property in the render material';return out end
    out.texture=u32(world,handles+4*out.k)
    out.valid=out.texture~=nil
    return out
end

-- A texture's render handle by name hash halves (u32 [resource + 0]), or nil and why.
function M.texture_handle(world,high,low)
    local done,resource,why=pcall(images.texture_resource,world.runtime,high,low)
    if not done then return nil,tostring(resource)end
    if not resource then return nil,why end
    return u32(world,resource)
end

-- The whole probe (read-only): every slot's chain, the atlas page handle of each slot's sprite page, the custom
-- texture's handle. Returns the lines it logs.
function M.run(custom_image)
    local world=world_module.open()
    if not world then return {'no game world'}end
    local proven,why=selector.prove(world)
    if not proven then return {'the code is not the pinned code: '..tostring(why)}end
    local view=selector.screen(world)
    if not(view and view.open)then return {'the loadout screen is not open'}end
    local lines={}
    local custom,custom_why
    if custom_image then
        custom,custom_why=M.texture_resource_handle(world,custom_image)
    end
    for slot=0,L.maxLoadoutEntries-1 do
        local s=M.slot(world,view,slot)
        local page
        if s.valid then
            local name=world.view.read(s.element+I.name,8)
            local done,record,page_name=pcall(images.sprite_record,world.runtime,b.u32(name,4),b.u32(name,0))
            if done and record then
                local page_bytes=world.view.read(record+I.spritePage,8)
                page={name=page_name,handle=page_bytes and M.texture_handle(world,b.u32(page_bytes,4),b.u32(page_bytes,0))}
            end
        end
        lines[#lines+1]=('slot %d (type %s): element %s flags %s (owns %s, external %s), material %s handle %s, render world '
            ..'%s, render material %s: %s%s'):format(slot,tostring(view.widgets[slot+1]),hex(s.element),hex(s.flags),
            tostring(s.owns),tostring(s.external),hex(s.material),hex(s.handle),hex(s.rw),hex(s.r),
            s.valid and('valid; image property at %d, texture handle %s'):format(s.k,hex(s.texture))
                or('NOT resolved: '..tostring(s.why)),
            page and(('; its sprite page %s has handle %s (%s)'):format(tostring(page.name),hex(page.handle),
                page.handle==s.texture and'the slot samples it'or'DIFFERENT'))or'')
    end
    lines[#lines+1]=custom_image and(custom and('custom texture render handle %s'):format(hex(custom))
        or('custom texture not resolved: '..tostring(custom_why or'not loaded')))or'no custom image given'
    lines[#lines+1]='read only: nothing was written'
    for _,line in ipairs(lines)do log(line)end
    return lines
end
function M.texture_resource_handle(world,image)
    local done,resource,why=pcall(images.texture_resource_of,world.runtime,image)
    if not done then return nil,tostring(resource)end
    if not resource then return nil,why end
    return u32(world,resource)
end
return M
