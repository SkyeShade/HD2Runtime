-- Visual-only homing lock HUD. No selection, input, allocation or game-memory writes.
-- Ring/marker GUI separation follows Guided Rounds commit 71303dd, reticle_step.
-- Native argument contracts: HD2Runtime v0.40 runtime/engine_gui.lua / docs/ui-overlay.md.
-- Gui.triangle uses Vector3(x,0,y); rect/text use bottom-origin Vector3(x,y,layer).
local M={}
local Style=require('hd2runtime/runtime/homing_reticle_style')
M.validate_style=Style.validate
local FONT='core/performance_hud/monaco' -- verified font AND material name in domains/ui_fonts.lua
local DIM={180,20,24,28}
local DIGITS={'bc','abged','abgcd','fgbc','afgcd','afgecd'}
-- Guided Rounds reticle_step: the P-92 Warrant marker in its stock atlas.
-- Only use already-resident resources; never force a weapon package to load.
local STOCK={material='5af18dfb697cfef2',texture='f9a3f22a93eedcbd',slot='3aa8b87e00000000',
    uv={.5712890625,.0078125,.03125,.0625}}
local function finite(n,lo,hi)return type(n)=='number' and n==n and n>=lo and n<=hi end
local function callable(v)
    if type(v)=='function'then return true end
    local meta=(type(v)=='table'or type(v)=='userdata')and getmetatable(v)
    return type(meta)=='table'and type(meta.__call)=='function'
end
local function listed(s,world)
    if not s or not world then return false end
    local ok,worlds=pcall(s.Application.worlds)
    if not ok or type(worlds)~='table'then return false end
    for _,w in pairs(worlds)do if w==world then return true end end
    return false
end
local function same(a,b)
    if not a then return false end
    for k,v in pairs(b)do if a[k]~=v then return false end end
    return true
end
local function material_handle(value)
    -- Same boundary as engine_gui.screen.material: a failed lookup is a NULL
    -- lightuserdata, not Lua nil. It must never reach a Material.* setter.
    if type(value)~='userdata'and type(value)~='table'then return false end
    local text=tostring(value)
    return not(text:match('NULL$')or text:match(':%s*0x0+$')or text:match(':%s*0+$'))
end

function M.new(deps)
    assert(type(deps)=='table' and type(deps.view)=='table','HUD requires view')
    assert(type(deps.view.project)=='function' and type(deps.view.radius)=='function','HUD requires projection')
    local style=Style.validate(deps.style)
    local AMBER,GREEN,CLEAR,RED,UNKNOWN=style.acquiring_color,style.locked_color,
        style.clear_color,style.blocked_color,style.unknown_color
    local SEGMENTS=style.ring_segments
    local hud={};local stopped=false
    local s,world,width,height,session,ring,markers,ring_key
    local stock_gui,stock_key,stock_family;local stock_quads={}
    local primitives,numbers={},{}
    local state={state='hidden',markers=0,locked=0,acquiring=0,ring=false,text_supported=false,live_verified=false}
    local function set_status(value,reason)
        if state.state~=value or state.reason~=reason then
            if deps.log then pcall(deps.log,'[HD2Runtime homing HUD] '..value..(reason and(': '..reason)or''))end
        end
        state.state,state.reason=value,reason
    end
    local function observe_drop(drop)
        state.drop_state=type(drop)=='table'and drop.state or nil
        state.drop_phase=type(drop)=='table'and drop.phase or nil
        state.drop_entity=type(drop)=='table'and drop.entity or nil
        state.drop_type=type(drop)=='table'and drop.type or nil
        state.drop_records=type(drop)=='table'and drop.count or nil
    end
    local function blocked()
        if not deps.blocked then observe_drop(nil);return false end
        local ok,value,why,drop=pcall(deps.blocked)
        observe_drop(drop)
        return not ok or value~=false,ok and why or'menu_gate_failed'
    end
    local function destroy(gui)
        -- A removed world already released its native containers. Never call it.
        if gui and listed(s,world)then pcall(s.World.destroy_gui,world,gui)end
    end
    local function drop_stock()
        destroy(stock_gui);stock_gui,stock_key,stock_family=nil,nil,nil;stock_quads={}
    end
    local function clear()
        destroy(ring);destroy(markers);drop_stock()
        ring,markers,ring_key=nil,nil,nil;primitives,numbers={},{}
        world,width,height,session=nil,nil,nil,nil
        state.markers,state.locked,state.acquiring,state.ring,state.text_supported=0,0,0,false,false
        state.marker_renderer,state.renderer_reason=nil,nil
    end
    local function require_api(api)
        assert(type(api)=='table','engine_api_missing')
        for module,methods in pairs({Application={'worlds'},World={'create_screen_gui','destroy_gui'},
            Gui={'triangle','rect','update_rect','destroy_rect'},Script={'temp_count','set_temp_count'}})do
            assert(type(api[module])=='table','engine_api_missing:'..module)
            for _,name in ipairs(methods)do assert(callable(api[module][name]),'engine_api_missing:'..module..'.'..name)end
        end
        for _,name in ipairs({'Vector2','Vector3','Color'})do assert(callable(api[name]),'engine_api_missing:'..name)end
    end
    local function new_gui()
        local gui=s.World.create_screen_gui(world,'scale',1,1)
        assert(gui~=nil and gui~=false,'create_screen_gui_failed')
        return gui
    end
    local function color(c)return s.Color(c[1],c[2],c[3],c[4])end
    local function stock_assets()
        for module,methods in pairs({Application={'can_get'},IdString64={'from_hex'},Material={'set_texture'},
            Gui={'material','bitmap_3d_uv','update_bitmap_3d_uv'},Quaternion={'axis_angle'},
            Matrix4x4={'from_quaternion_position'}})do
            if type(s[module])~='table'then return nil,'marker_api_missing'end
            for _,name in ipairs(methods)do if not callable(s[module][name])then return nil,'marker_api_missing'end end
        end
        local material,texture,slot=s.IdString64.from_hex(STOCK.material),s.IdString64.from_hex(STOCK.texture),
            s.IdString64.from_hex(STOCK.slot)
        if not material or not texture or not slot then return nil,'marker_resource_id_missing'end
        if s.Application.can_get('material',material)~=true then return nil,'material_not_loaded'end
        if s.Application.can_get('texture',texture)~=true then return nil,'texture_not_loaded'end
        return{material=material,texture=texture,slot=slot}
    end
    local stock_marker
    local function prepare_stock(items,scale)
        local ok,family,why=pcall(stock_assets)
        if not ok then family,why=nil,'marker_asset_query_failed'end
        if not family then drop_stock();return false,why end
        local keys={};for _,item in ipairs(items)do keys[#keys+1]=item.target.key end
        table.sort(keys);local key=table.concat(keys,'\0')
        if stock_key~=key then drop_stock()end
        if #items>0 and not stock_gui then
            local setup=pcall(function()
                stock_gui=new_gui()
                stock_family=family
                -- A GUI has no material instance until a bitmap using it exists
                -- (engine_gui.screen.material). Seed the first real target's
                -- three quads, then bind the atlas before this update returns.
                local first=items[1];local p=first.point;local t=first.target
                local progress=first.locked and 1 or(finite(t.progress,0,1)and t.progress or 0)
                stock_marker(t.key,math.floor(p.x*2+.5)/2,math.floor(p.y*2+.5)/2,
                    progress,scale,first.locked and GREEN or AMBER)
                local material=s.Gui.material(stock_gui,family.material)
                assert(material_handle(material),'marker_material_unavailable')
                s.Material.set_texture(material,family.slot,family.texture)
            end)
            if not setup then drop_stock();return false,'marker_setup_failed'end
        end
        stock_key,stock_family=key,family
        return true
    end
    stock_marker=function(key,x,y,progress,scale,c)
        local unit=scale*style.marker_size/12;local radius=(24-14*progress)*unit;local size=48*unit
        for i=0,2 do
            local angle=progress*2*math.pi+i*2*math.pi/3
            local px,py=x+math.sin(angle)*radius,y+math.cos(angle)*radius
            local spec={x=px,y=py,size=size,angle=angle,a=c[1],r=c[2],g=c[3],b=c[4]}
            local id=key..'/'..i;local old=stock_quads[id]
            if not old or not same(old.spec,spec)then
                local sine,cosine=math.sin(angle),math.cos(angle)
                local rotation=s.Quaternion.axis_angle(s.Vector3(0,1,0),angle)
                local pose=s.Matrix4x4.from_quaternion_position(rotation,
                    s.Vector3(px-size/2*(cosine+sine),0,py-size/2*(cosine-sine)))
                local uv=STOCK.uv;local uv0,uv1=s.Vector2(uv[1],uv[2]),s.Vector2(uv[1]+uv[3],uv[2]+uv[4])
                local pos,tint=s.Vector3(0,0,0),color(c)
                if old then
                    s.Gui.update_bitmap_3d_uv(stock_gui,old.id,stock_family.material,uv0,uv1,pose,pos,1011,s.Vector2(size,size),tint)
                    old.spec=spec
                else
                    local bitmap=s.Gui.bitmap_3d_uv(stock_gui,stock_family.material,uv0,uv1,pose,pos,1011,s.Vector2(size,size),tint)
                    assert(type(bitmap)=='number','bitmap_id_missing');stock_quads[id]={id=bitmap,spec=spec}
                end
            end
        end
    end
    local function draw_ring(radius)
        local key=tostring(radius)
        if ring_key==key and ring then return end
        destroy(ring);ring=nil;ring_key=nil
        ring=new_gui()
        local c=color(style.ring_color);local cx,cy=width/2,height/2
        local ax,ay=cx+radius,cy
        for i=1,SEGMENTS do
            local angle=i*2*math.pi/SEGMENTS
            local bx,by=cx+radius*math.cos(angle),cy+radius*math.sin(angle)
            local dx,dy=bx-ax,by-ay;local length=math.sqrt(dx*dx+dy*dy)
            local nx,ny=-dy/length*style.ring_width/2,dx/length*style.ring_width/2
            s.Gui.triangle(ring,s.Vector3(ax+nx,0,ay+ny),s.Vector3(bx+nx,0,by+ny),
                s.Vector3(bx-nx,0,by-ny),1010,c)
            s.Gui.triangle(ring,s.Vector3(ax+nx,0,ay+ny),s.Vector3(bx-nx,0,by-ny),
                s.Vector3(ax-nx,0,ay-ny),1010,c)
            ax,ay=bx,by
        end
        ring_key=key
    end
    local function font_loaded()
        if not(callable(s.Application.can_get)and callable(s.Gui.text)
            and callable(s.Gui.update_text)and callable(s.Gui.destroy_text))then return false end
        local a,font=pcall(s.Application.can_get,'font',FONT)
        local b,material=pcall(s.Application.can_get,'material',FONT)
        return a and b and font==true and material==true
    end
    local wanted
    local function rect(key,x,y,w,h,c)
        local right,top=math.min(width,x+w),math.min(height,y+h)
        x,y=math.max(0,x),math.max(0,y);w,h=right-x,top-y
        if w<=0 or h<=0 then return end
        local spec={kind='rect',x=x,y=y,w=w,h=h,a=c[1],r=c[2],g=c[3],b=c[4]}
        wanted[key]=true;local old=primitives[key]
        if old and same(old.spec,spec)then return end
        local pos,size,tint=s.Vector3(x,y,1011),s.Vector2(w,h),color(c)
        if old then s.Gui.update_rect(markers,old.id,pos,size,tint);old.spec=spec
        else
            local id=s.Gui.rect(markers,pos,size,tint);assert(type(id)=='number','rect_id_missing')
            primitives[key]={id=id,spec=spec}
        end
    end
    local function text(key,value,x,y,c,scale)
        x=math.max(0,math.min(width-180*scale,x));y=math.max(0,math.min(height-18*scale,y))
        local spec={kind='text',text=value,x=x,y=y,size=14*scale,a=c[1],r=c[2],g=c[3],b=c[4]}
        wanted[key]=true;local old=primitives[key]
        if old and same(old.spec,spec)then return end
        local pos,tint=s.Vector3(x,y,1012),color(c)
        if old then s.Gui.update_text(markers,old.id,value,FONT,spec.size,FONT,pos,tint);old.spec=spec
        else
            local id=s.Gui.text(markers,value,FONT,spec.size,FONT,pos,tint);assert(type(id)=='number','text_id_missing')
            primitives[key]={id=id,spec=spec}
        end
    end
    local function digit(key,number,x,y,scale,c)
        -- Asset-free 1..6 labels survive missing font/material resources.
        local lines={a={0,10,5,1},b={4,5,1,5},c={4,0,1,5},d={0,0,5,1},
            e={0,0,1,5},f={0,5,1,5},g={0,5,5,1}}
        for name in DIGITS[number]:gmatch('.')do
            local q=lines[name];rect(key..'/digit/'..name,x+q[1]*scale,y+q[2]*scale,q[3]*scale,q[4]*scale,c)
        end
    end
    local function stroke(key,ax,ay,bx,by,thick,c)
        -- Eight retained, clipped rectangles approximate a rotated stroke. The
        -- existing rectangle API supplies updates; no sprite/native API is added.
        for i=0,7 do
            local x0,y0=ax+(bx-ax)*i/8,ay+(by-ay)*i/8
            local x1,y1=ax+(bx-ax)*(i+1)/8,ay+(by-ay)*(i+1)/8
            rect(key..'/'..i,math.min(x0,x1)-thick/2,math.min(y0,y1)-thick/2,
                math.abs(x1-x0)+thick,math.abs(y1-y0)+thick,c)
        end
    end
    local function vanilla_marker(key,x,y,progress,scale,thick,c)
        -- Asset-free Warrant-style replica, not the native target-lock HUD or
        -- stock atlas sprite. Guided Rounds reticle_step/markers_draw places
        -- three marks 120 degrees apart, rotates once over acquisition and
        -- contracts their orbit 24 -> 10 pixels. Use this target's real progress.
        local unit=scale*style.marker_size/12
        local radius=(24-14*progress)*unit
        for i=0,2 do
            local angle=progress*2*math.pi+i*2*math.pi/3
            local dx,dy=math.sin(angle),math.cos(angle)
            local tx,ty=x+dx*(radius-4*unit),y+dy*(radius-4*unit)
            local bx,by=x+dx*(radius+3*unit),y+dy*(radius+3*unit)
            local marker=key..'/vanilla/'..i
            stroke(marker..'/left',bx-dy*4*unit,by+dx*4*unit,tx,ty,thick,c)
            stroke(marker..'/right',tx,ty,bx+dy*4*unit,by-dx*4*unit,thick,c)
        end
    end
    local function target_marker(t,p,locked,scale,fonts)
        local progress=locked and 1 or(finite(t.progress,0,1)and t.progress or 0)
        local half=(style.marker_size+(locked and 0 or 4-4*progress))*scale
        local x,y=math.floor(p.x*2+.5)/2,math.floor(p.y*2+.5)/2
        local thick,arm=style.line_width*scale,style.marker_size/2*scale;local c=locked and GREEN or AMBER
        if style.marker_shape=='vanilla'then
            local extent=state.marker_renderer=='vanilla_asset'and 48 or 28
            half=(extent-14*progress)*style.marker_size/12*scale+thick/2
        end
        if style.marker_shape=='vanilla'then
            if state.marker_renderer=='vanilla_asset'then stock_marker(t.key,x,y,progress,scale,c)
            else vanilla_marker(t.key,x,y,progress,scale,thick,c)end
        elseif style.marker_shape=='box'then
            rect(t.key..'/box/t',x-half,y+half,2*half,thick,c)
            rect(t.key..'/box/b',x-half,y-half,2*half,thick,c)
            rect(t.key..'/box/l',x-half,y-half,thick,2*half,c)
            rect(t.key..'/box/r',x+half,y-half,thick,2*half,c)
        elseif style.marker_shape=='cross'then
            for i=-1,1,2 do
                rect(t.key..'/cross/h/'..i,x+i*(half-arm/2)-arm/2,y-thick/2,arm,thick,c)
                rect(t.key..'/cross/v/'..i,x-thick/2,y+i*(half-arm/2)-arm/2,thick,arm,c)
            end
        else for ix=-1,1,2 do for iy=-1,1,2 do
            local edge_x,edge_y=x+ix*half,y+iy*half
            local key=t.key..'/corner/'..ix..'/'..iy
            rect(key..'/h',ix<0 and edge_x or edge_x-arm,edge_y,arm,thick,c)
            rect(key..'/v',edge_x,iy<0 and edge_y or edge_y-arm,thick,arm,c)
        end end end
        -- Every acquiring target has a progress bar; completion adds a solid
        -- top bar as well as LOCK, so shape/text also distinguish the state.
        if style.show_progress then rect(t.key..'/progress_bg',x-half,y-half-6*scale,2*half,3*scale,DIM)
        rect(t.key..'/progress',x-half,y-half-6*scale,2*half*progress,3*scale,c)
        if locked then rect(t.key..'/complete',x-4*scale,y+half+4*scale,8*scale,2*scale,c)end
        end
        if style.show_numbers then digit(t.key,numbers[t.key],x-half-8*scale,y+half-9*scale,scale,c)end
        local los=t.los or'unknown'
        local tint=los=='clear'and CLEAR or(los=='blocked'and RED or UNKNOWN)
        local bars=los=='clear'and 1 or(los=='blocked'and 2 or 3)
        for i=1,style.show_los and bars or 0 do
            rect(t.key..'/los/'..i,x+half+4*scale,y-half+(i-1)*3*scale,
                (los=='unknown'and 2 or 6)*scale,1.5*scale,tint)
        end
        if fonts and style.show_labels then
            local label=locked and'LOCK'or('ACQ '..math.floor(progress*100+.5)..'%')
            text(t.key..'/label',label,x-half,y+half+9*scale,c,scale)
            if style.show_los then text(t.key..'/los_label',los=='clear'and'LOS CLEAR'or(los=='blocked'and'LOS BLOCKED'or'LOS ?'),
                x-half,y-half-24*scale,tint,scale)end
        end
    end
    local function targets(snapshot)
        local by={}
        local function add(list,locked)
            for _,t in ipairs(type(list)=='table'and list or{})do
                if type(t)=='table'and type(t.key)=='string'and#t.key>0 and#t.key<=256
                    and not by[t.key]and finite(t.x,-1e9,1e9)and finite(t.y,-1e9,1e9)and finite(t.z,-1e9,1e9)then
                    by[t.key]={target=t,locked=locked}
                end
            end
        end
        add(snapshot.locked,true);add(snapshot.acquiring,false)
        local items={};for _,item in pairs(by)do items[#items+1]=item end
        table.sort(items,function(a,b)
            local an,bn=numbers[a.target.key],numbers[b.target.key]
            if an and bn then return an<bn elseif an then return true elseif bn then return false end
            return a.target.key<b.target.key
        end)
        local limit=finite(snapshot.max_targets,1,6)and math.floor(snapshot.max_targets)or 6
        if snapshot.mode=='single'then limit=1 end
        while #items>limit do table.remove(items)end
        local present,used={},{}
        for _,item in ipairs(items)do present[item.target.key]=true end
        for key,n in pairs(numbers)do if not present[key]then numbers[key]=nil else used[n]=true end end
        for _,item in ipairs(items)do
            local key=item.target.key
            if not numbers[key]then for n=1,6 do if not used[n]then numbers[key]=n;used[n]=true;break end end end
        end
        return items
    end
    local function render(snapshot,mark)
        if type(snapshot)~='table'or snapshot.visible~=true then observe_drop(nil);clear();set_status('hidden');return end
        local hidden,why=blocked()
        if hidden then clear();set_status('suppressed',why);return end
        local frame=snapshot.frame
        assert(type(frame)=='table','camera_frame_missing')
        local api=frame.sr or rawget(_G,'stingray');require_api(api)
        assert(mark~=nil,'temporary_scope_unavailable')
        assert(finite(frame.width,320,16384)and finite(frame.height,200,16384),'resolution_invalid')
        if not listed(api,frame.ui_world)then clear();set_status('unavailable',frame.ui_reason or'ui_world_unavailable');return end
        if not listed(api,frame.world)then clear();set_status('unavailable','game_world_unavailable');return end
        if frame.ui_world==frame.world then clear();set_status('unavailable','ui_world_is_game_world');return end
        if s~=api or world~=frame.ui_world or width~=frame.width or height~=frame.height or session~=snapshot.session then
            clear();s,world,width,height,session=api,frame.ui_world,frame.width,frame.height,snapshot.session
        end
        local radius=style.ring_radius or deps.view.radius(frame,snapshot.half_angle)
        if style.ring and finite(radius,1,math.sqrt(width*width+height*height)/2)then
            radius=math.max(2,math.floor(radius/4+.5)*4);draw_ring(radius)
        else destroy(ring);ring,ring_key=nil,nil end
        if not markers then markers=new_gui()end
        local fonts=font_loaded();wanted={}
        local scale=style.scale*math.max(.7,math.min(2,math.min(width/1920,height/1080)))
        local count,locked,acquiring=0,0,0
        local drawable={}
        for _,item in ipairs(targets(snapshot))do
            local p=deps.view.project(frame,item.target)
            if type(p)=='table'and finite(p.x,0,width)and finite(p.y,0,height)and finite(p.depth,.000001,1e9)then
                drawable[#drawable+1]={target=item.target,point=p,locked=item.locked}
            end
        end
        if style.marker_shape=='vanilla'then
            local ready,why=prepare_stock(drawable,scale)
            state.marker_renderer,state.renderer_reason=ready and'vanilla_asset'or'vanilla_geometry',why
        else state.marker_renderer,state.renderer_reason='geometry',nil end
        for _,item in ipairs(drawable)do
            target_marker(item.target,item.point,item.locked,scale,fonts);count=count+1
            if item.locked then locked=locked+1 else acquiring=acquiring+1 end
        end
        for key,item in pairs(primitives)do if not wanted[key]then
            if item.spec.kind=='rect'then s.Gui.destroy_rect(markers,item.id)else s.Gui.destroy_text(markers,item.id)end
            primitives[key]=nil
        end end
        state.markers,state.locked,state.acquiring,state.ring,state.text_supported=count,locked,acquiring,ring~=nil,fonts
        set_status('drawing',not fonts and'font_unavailable'or nil)
    end
    function hud:update(snapshot,dt)
        if stopped then return end
        local frame=type(snapshot)=='table'and snapshot.frame
        local api=type(frame)=='table'and(frame.sr or rawget(_G,'stingray'))or s
        local script=type(api)=='table'and api.Script
        local mark
        if type(script)=='table'and callable(script.temp_count)and callable(script.set_temp_count)then
            local ok,value=pcall(script.temp_count)
            if ok and finite(value,0,1048575)and value%1==0 then mark=value end
        end
        local ok,why=pcall(render,snapshot,mark)
        if mark~=nil then pcall(script.set_temp_count,mark)end
        if not ok then
            clear()
            local reason=tostring(why)
            if reason:find('resolution_invalid',1,true)then set_status('unavailable','resolution_invalid')
            else set_status('error',reason)end
        end
    end
    function hud:status()
        local out={};for k,v in pairs(state)do out[k]=v end
        out.numbers={};for k,v in pairs(numbers)do out.numbers[k]=v end
        return out
    end
    -- The engine may skip observation while a menu is up; clear retained GUI
    -- from the entry's every-frame update as well. Closing waits for fresh data.
    function hud:tick()
        -- Nothing retained needs clearing. Inactive snapshots otherwise alternate
        -- hidden/suppressed on every frame, flooding the synchronous log.
        if stopped or not(ring or markers)then return end
        local hidden,why=blocked()
        if hidden then clear();set_status('suppressed',why)end
    end
    function hud:shutdown()
        if stopped then return end
        stopped=true;clear();set_status('stopped')
    end
    return hud
end
return M
