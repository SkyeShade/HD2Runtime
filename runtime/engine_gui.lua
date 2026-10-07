-- The engine GUI subset the Runtime draws with (docs/custom-stratagems.md, "Drawing: the engine GUI subset"). Not
-- exported by api/hd2.lua itself: mods draw through hd2.ui.overlay (runtime/mod_overlay.lua), which uses it.
--
-- Only the calls a released Helldivers 2 Lua mod (Know Your Constellation, Vanilla Plus Megapack) is seen to use
-- in game, plus Gui.bitmap for the Runtime's own icon material:
--   stingray.Application.main_world / worlds, stingray.World.create_screen_gui(world, 'scale', 1, 1) / destroy_gui,
--   stingray.Gui.resolution / rect / update_rect / text / bitmap, stingray.Vector2 / Vector3 / Color;
--   and, as the reference mod sets its font atlas, Gui.material + Material.set_vector4 (+ Quaternion.from_elements) for
--   the icon shader's mask colours c0-c3, which are zero unless set (research iconShader).
-- Vector2 and Vector3 are module TABLES with a __call constructor (exe 0x430F3F, 0x43517F); Color is a plain function
-- (0x3E72CB). A constructor is therefore checked as callable, never as type 'function'.
-- The bindings check no arguments (a wrong value most likely crashes instead of raising a Lua error), so every value is
-- validated here first; the first failing required call closes the GUI and marks the screen failed. Return values follow
-- the bindings: create_screen_gui, rect, bitmap and text return one value (the GUI, an id: exe 0x3F09D3, 0x3E1D5C,
-- 0x3E2BA7, 0x3E5491); update_rect, update_bitmap, update_text and destroy_gui return none (0x3E1F90, 0x3E2DF7,
-- 0x3F105D). A creation must return its id; an update succeeds when it raises no error. A call marked optional
-- ({optional = true}) that fails leaves the GUI open. Positions are in pixels from the bottom-left corner, z the layer.
-- Nothing here writes game memory.
--
-- Render order (docs/custom-stratagems.md, "Render order"): a screen GUI's primitives are drawn in its world's
-- "transparent" passes; z only orders them inside that GUI (Gui.rect truncates it to an int32 layer, exe 0x3E1CBD). The
-- game's own UI world is rendered through the viewport hud_world_ui_and_composite_layer, whose layer config draws the
-- transparent passes, THEN the Noesis UI (generator "noesis") into the same ui_target, then composites it over the game
-- image into the back buffer (copy_and_blend_ui). The development render-order probe (runtime/render_probe.lua) also
-- opens screens in a script-created world (M.script_world) and in immediate mode.
local M={}

local function callable(value)
    if type(value)=='function'then return true end
    if type(value)~='table'and type(value)~='userdata'then return false end
    local meta=getmetatable(value)
    return type(meta)=='table'and type(rawget(meta,'__call'))=='function'
end
M.callable=callable

local NEED={Application={'main_world','worlds'},World={'create_screen_gui','destroy_gui'},
    Gui={'resolution','rect','update_rect','text','bitmap'}}
-- The engine API table, or nil and the reason.
function M.api()
    local S=rawget(_G,'stingray')
    if type(S)~='table'then return nil,'the engine scripting API (stingray) is unavailable'end
    for module,functions in pairs(NEED)do
        if type(S[module])~='table'then return nil,'stingray.'..module..' is unavailable'end
        for _,name in ipairs(functions)do
            if not callable(S[module][name])then return nil,'stingray.'..module..'.'..name..' is not callable'end
        end
    end
    for _,name in ipairs({'Vector2','Vector3','Color'})do
        if not callable(S[name])then return nil,'stingray.'..name..' is not callable'end
    end
    return S
end

-- Read-only engine facts for coordinate diagnostics: the GUI resolution, the back buffer size (when the binding exists),
-- the number of worlds and which one main_world is. Nothing is created or written.
function M.diagnostics()
    local S,why=M.api()
    if not S then return nil,why end
    local out={}
    pcall(function()out.resolution={S.Gui.resolution()}end)
    if callable(S.Application.back_buffer_size)then pcall(function()out.backBuffer={S.Application.back_buffer_size()}end)end
    pcall(function()
        local list=S.Application.worlds()or{}
        local main=S.Application.main_world()
        out.worlds=#list
        for i,w in ipairs(list)do if w==main then out.mainIndex=i end end
    end)
    return out
end

-- The world the game rendered last, its 1-based index in Application.worlds and the world count; or nil and the reason.
-- index_of(world) gives a listed world's index and the count. Read-only.
function M.main_world()
    local S,why=M.api()
    if not S then return nil,why end
    local ok,world,index,count=pcall(function()
        local main=S.Application.main_world()
        local list=S.Application.worlds()or{}
        for i,w in ipairs(list)do if w==main then return main,i,#list end end
        return nil,nil,#list
    end)
    if not ok then return nil,tostring(world)end
    if world==nil then return nil,'the main world is not among the worlds'end
    return world,index,count
end
function M.index_of(world)
    local S=M.api()
    if not S or world==nil then return nil end
    local ok,index,count=pcall(function()
        local list=S.Application.worlds()or{}
        for i,w in ipairs(list)do if w==world then return i,#list end end
        return nil,#list
    end)
    if ok then return index,count end
end

local function finite(n,low,high)return type(n)=='number'and n==n and n>=low and n<=high end
local function text_ok(s)return type(s)=='string'and#s>=1 and#s<=160 and not s:find('[%z\1-\31\127]')end
local function name_ok(s)return type(s)=='string'and#s>=1 and#s<=128 and s:match('^[%w_/%.%-]+$')~=nil end
local function color_ok(c)
    if type(c)~='table'then return false end
    for i=1,4 do if not(finite(c[i],0,255)and c[i]%1==0)then return false end end
    return true
end

-- Opens a screen GUI, by default in the world the game rendered last. opts (development, the render-order probe):
-- world = a listed world to open it in; mode = 'immediate' for an immediate GUI (create_screen_gui(world, 0, 0,
-- 'immediate'), as the engine's performance HUD script does; its primitives are drawn again every frame) instead of the
-- retained 'scale' GUI; max_layer = the highest layer accepted (default 999; above 999 the render side's use of the layer
-- is unproven). Returns the screen, or nil and the reason.
function M.open(opts)
    opts=opts or{}
    local S,why=M.api()
    if not S then return nil,why end
    local max_layer=opts.max_layer==nil and 999 or opts.max_layer
    if type(max_layer)~='number'or max_layer%1~=0 or max_layer<0 or max_layer>10000 then
        return nil,'invalid layer range'
    end
    if opts.mode~=nil and opts.mode~='immediate'then return nil,'unknown GUI mode'end
    local screen={state='open',calls=0,mode=opts.mode or'retained',maxLayer=max_layer}
    local world,gui
    local function close()
        if gui and world then
            pcall(function()
                local alive=false
                for _,w in ipairs(S.Application.worlds()or{})do if w==world then alive=true end end
                if alive then S.World.destroy_gui(world,gui)end
            end)
        end
        gui,world=nil,nil
        if screen.state=='open'then screen.state='closed'end
    end
    local ok,err=pcall(function()
        if opts.world~=nil then world=opts.world else world=S.Application.main_world()end
        if world==nil then error('no main world',0)end
        local listed=false
        for _,w in ipairs(S.Application.worlds()or{})do if w==world then listed=true end end
        if not listed then error(opts.world~=nil and'the world is not among the worlds'or'the main world is not among the worlds',0)end
        local width,height=S.Gui.resolution()
        if not(finite(width,320,16384)and finite(height,240,16384))then error('unexpected GUI resolution',0)end
        screen.width,screen.height=width,height
        if opts.mode=='immediate'then gui=S.World.create_screen_gui(world,0,0,'immediate')
        else gui=S.World.create_screen_gui(world,'scale',1,1)end
        if gui==nil then error('create_screen_gui returned nothing',0)end
    end)
    if not ok then close();return nil,tostring(err)end
    -- Runs one validated engine call. kind 'create': it must return its id (returned); kind 'update': true when it
    -- raised no error (the binding returns nothing). A failed required call closes the GUI and fails the screen; a
    -- failed optional call leaves it open and returns nil and the reason.
    local function call(fn,kind,opt)
        if screen.state~='open'then return nil,'the GUI is '..screen.state end
        local done,result=pcall(fn)
        local reason
        if not done then reason=tostring(result)
        elseif kind=='create'and result==nil then reason='the engine returned no id'end
        if reason then
            if opt and opt.optional then return nil,reason end
            close();screen.state,screen.reason='failed',reason
            return nil,reason
        end
        screen.calls=screen.calls+1
        if kind=='update'then return true end
        return result
    end
    local function position(x,y,layer)return S.Vector3(x,y,layer)end
    local function size(w,h)return S.Vector2(w,h)end
    local function color(c)return S.Color(c[1],c[2],c[3],c[4])end
    local function box_ok(x,y,layer,w,h)
        return finite(x,-1,screen.width+1)and finite(y,-1,screen.height+1)and finite(layer,0,max_layer)and layer%1==0
            and finite(w,0,screen.width)and finite(h,0,screen.height)
    end
    -- A rectangle: {x, y, layer, w, h} in pixels, color {a, r, g, b}. Returns its id. opt: {optional = true}.
    function screen.rect(x,y,layer,w,h,c,opt)
        if not(box_ok(x,y,layer,w,h)and color_ok(c))then return nil,'invalid rectangle'end
        return call(function()return S.Gui.rect(gui,position(x,y,layer),size(w,h),color(c))end,'create',opt)
    end
    -- Moves or recolours a rectangle: true when the engine raised no error (update_rect returns nothing).
    function screen.update_rect(id,x,y,layer,w,h,c,opt)
        if id==nil or not(box_ok(x,y,layer,w,h)and color_ok(c))then return nil,'invalid rectangle'end
        return call(function()return S.Gui.update_rect(gui,id,position(x,y,layer),size(w,h),color(c))end,'update',opt)
    end
    -- A bitmap of a loaded GUI material, by resource name (the caller proves it is loaded first). Returns its id.
    function screen.bitmap(material,x,y,layer,w,h,c,opt)
        if not(name_ok(material)and box_ok(x,y,layer,w,h)and color_ok(c))then return nil,'invalid bitmap'end
        return call(function()return S.Gui.bitmap(gui,material,position(x,y,layer),size(w,h),color(c))end,'create',opt)
    end
    -- Moves, resizes or recolours a bitmap: Gui.update_bitmap(gui, id, material, position, size, color) (exe 0x3E2E30,
    -- the bitmap's own parser after the id); true when the engine raised no error (it returns nothing).
    function screen.update_bitmap(id,material,x,y,layer,w,h,c,opt)
        if id==nil or not(name_ok(material)and box_ok(x,y,layer,w,h)and color_ok(c))then return nil,'invalid bitmap'end
        if not callable(S.Gui.update_bitmap)then return nil,'stingray.Gui.update_bitmap is not callable'end
        return call(function()return S.Gui.update_bitmap(gui,id,material,position(x,y,layer),size(w,h),color(c))end,
            'update',opt)
    end
    -- A bitmap of a loaded GUI material named by its 64-bit resource name hash (16 hex digits) instead of its name:
    -- stingray.IdString64.from_hex builds the id (tag 0x6F6F4D64, frame-temporary) and Gui.bitmap takes it as it takes a
    -- name (research bitmapContract). For materials whose name string is unknown (the development icon diagnostics).
    function screen.bitmap_id(hex,x,y,layer,w,h,c,opt)
        if not(type(hex)=='string'and hex:match('^%x+$')and #hex==16 and box_ok(x,y,layer,w,h)and color_ok(c))then
            return nil,'invalid bitmap'
        end
        if not(type(S.IdString64)=='table'and callable(S.IdString64.from_hex))then
            return nil,'stingray.IdString64.from_hex is not callable'
        end
        return call(function()
            return S.Gui.bitmap(gui,S.IdString64.from_hex(hex),position(x,y,layer),size(w,h),color(c))
        end,'create',opt)
    end
    -- The GUI's own instance of a material, by resource name or (hex) by its 64-bit name hash: Gui.material resolves it
    -- through the same per-GUI lookup as Gui.bitmap (exe 0x3E7ED9), so it is the instance this GUI's bitmaps of that
    -- material draw with. Call it only after a bitmap of that material was created in this GUI and the caller proved the
    -- material loaded: a material the engine did not find comes back as a NULL light userdata, refused here, which must
    -- never reach Material.*. Returns the instance, or nil and the reason (never fails the screen).
    local function null_handle(v)
        local text=tostring(v)
        return text:match('NULL$')~=nil or text:match(':%s*0x0+$')~=nil or text:match(':%s*0+$')~=nil
    end
    function screen.material(name,hex)
        if screen.state~='open'then return nil,'the GUI is '..screen.state end
        if not callable(S.Gui.material)then return nil,'stingray.Gui.material is not callable'end
        local key
        if hex then
            if not(type(name)=='string'and name:match('^%x+$')and#name==16)then return nil,'invalid material id'end
            if not(type(S.IdString64)=='table'and callable(S.IdString64.from_hex))then
                return nil,'stingray.IdString64.from_hex is not callable'
            end
        elseif not name_ok(name)then return nil,'invalid material name'end
        local done,instance=pcall(function()
            return S.Gui.material(gui,hex and S.IdString64.from_hex(name)or name)
        end)
        if not done then return nil,tostring(instance)end
        if instance==nil or(type(instance)~='userdata'and type(instance)~='table')or null_handle(instance)then
            return nil,'the GUI has no instance of that material (not found)'
        end
        return instance
    end
    -- Sets float4 shader variables on a material instance from screen.material: vars = {{name, x, y, z, w}, ...}, each
    -- through Material.set_vector4(instance, name, Quaternion.from_elements(x, y, z, w)) (exe 0x49E09F: the engine setter
    -- the game's UI uses; the value is read as any 4-float box). Names are 1-32 characters of [%w_]; values finite in
    -- [-16, 16]. Returns true, or nil and the reason (never fails the screen; an engine error stops at that variable).
    function screen.set_vectors(instance,vars)
        if screen.state~='open'then return nil,'the GUI is '..screen.state end
        if instance==nil or null_handle(instance)then return nil,'no material instance'end
        if not(type(S.Material)=='table'and callable(S.Material.set_vector4))then
            return nil,'stingray.Material.set_vector4 is not callable'
        end
        if not(type(S.Quaternion)=='table'and callable(S.Quaternion.from_elements))then
            return nil,'stingray.Quaternion.from_elements is not callable'
        end
        if type(vars)~='table'or#vars<1 or#vars>8 then return nil,'invalid variables'end
        for _,v in ipairs(vars)do
            if not(type(v)=='table'and type(v[1])=='string'and v[1]:match('^[%w_]+$')and#v[1]<=32)then
                return nil,'invalid variable name'
            end
            for i=2,5 do if not finite(v[i],-16,16)then return nil,'invalid value for '..v[1]end end
        end
        for _,v in ipairs(vars)do
            local done,err=pcall(function()
                S.Material.set_vector4(instance,v[1],S.Quaternion.from_elements(v[2],v[3],v[4],v[5]))
            end)
            if not done then return nil,'Material.set_vector4 '..v[1]..': '..tostring(err)end
            screen.calls=screen.calls+1
        end
        return true
    end
    -- Text in a loaded font and its material, by resource name (the caller proves both are loaded first); (x, y) is the
    -- baseline start. Returns its id.
    function screen.text(s,font,font_size,material,x,y,layer,c,opt)
        if not(text_ok(s)and name_ok(font)and name_ok(material)and finite(font_size,4,256)
                and box_ok(x,y,layer,0,0)and color_ok(c))then
            return nil,'invalid text'
        end
        return call(function()return S.Gui.text(gui,s,font,font_size,material,position(x,y,layer),color(c))end,'create',
            opt)
    end
    -- Changes a text's string, font, size, place or colour: Gui.update_text(gui, id, text, font, size, material,
    -- position, color) (exe 0x3E5860 -> 0x3E54D0: Gui.text's own parser with the id read second, lua_tointeger(2),
    -- then text 3, font 4, size 5, material 6, the position 7 and the colour 8, the indices Gui.text reads one lower;
    -- it returns nothing). true when the engine raised no error. Nil and why when the binding is missing.
    function screen.update_text(id,s,font,font_size,material,x,y,layer,c,opt)
        if id==nil or not(text_ok(s)and name_ok(font)and name_ok(material)and finite(font_size,4,256)
                and box_ok(x,y,layer,0,0)and color_ok(c))then
            return nil,'invalid text'
        end
        if not callable(S.Gui.update_text)then return nil,'stingray.Gui.update_text is not callable'end
        return call(function()return S.Gui.update_text(gui,id,s,font,font_size,material,position(x,y,layer),color(c))end,
            'update',opt)
    end
    -- Removes one primitive this GUI created: kind 'rect', 'text' or 'bitmap' -> Gui.destroy_rect / destroy_text /
    -- destroy_bitmap(gui, id) (exe 0x3E2040, 0x3E58E0, 0x3E2EB0: lua_touserdata(1), lua_tointeger(2), the GUI's one
    -- primitive removal 0x267990(gui, id); they return nothing). Only ids this screen returned may be passed.
    local DESTROY={rect='destroy_rect',text='destroy_text',bitmap='destroy_bitmap'}
    function screen.destroy(kind,id,opt)
        local name=DESTROY[kind]
        if not name or type(id)~='number'or id%1~=0 then return nil,'invalid primitive'end
        if not callable(S.Gui[name])then return nil,'stingray.Gui.'..name..' is not callable'end
        return call(function()return S.Gui[name](gui,id)end,'update',opt)
    end
    screen.close=close
    return screen
end

-- Runs fn(...) and gives the engine's Lua temporaries back afterwards: Script.temp_count() before, set_temp_count(n)
-- after. In this build both take ONE integer, the byte position in the 1 MiB temporaries ring the Vector2 / Vector3 /
-- Color constructors draw from (exe 0x490150: (cur - start) mod 0x100000 pushed as one integer; 0x490270: cur = start +
-- n, wrapped), not the three counts of older engines. So a pass that builds many values never moves the ring on for
-- other scripts' temporaries. Returns what fn returns (pcall-style: ok, ...); without the bindings it just runs fn.
function M.temp_scope(fn,...)
    local S=rawget(_G,'stingray')
    local script=type(S)=='table'and type(S.Script)=='table'and S.Script
    local mark
    if script and callable(script.temp_count)and callable(script.set_temp_count)then
        local ok,n=pcall(script.temp_count)
        if ok and finite(n,0,1048575)and n%1==0 then mark=n end
    end
    local results={pcall(fn,...)}
    if mark then pcall(script.set_temp_count,mark)end
    return unpack(results,1,table.maxn(results))
end

-- A script-created world, as the engine's performance HUD script makes one (development; the render-order probe):
-- Application.new_world(), Application.create_viewport(world, template), World.create_shading_environment(world,
-- shading), World.spawn_unit(world, 'core/units/camera') and Unit.camera(unit, 'camera'). template must be one of the
-- render config's viewports this probe knows: 'overlay' (its layer config draws the transparent pass straight into the
-- back buffer). The caller proves the camera unit and the shading environment resident first. Returns {world, render()
-- (Application.render_world(world, camera, viewport, shading), only from the engine's render callback), release()} or
-- nil and the reason; a failure releases whatever was created.
local TEMPLATES={overlay=true}
M.CAMERA_UNIT,M.SHADING='core/units/camera','core/stingray_renderer/environments/midday/midday'
local WORLD_NEED={Application={'new_world','release_world','create_viewport','destroy_viewport','render_world','worlds'},
    World={'create_shading_environment','destroy_shading_environment','spawn_unit'},Unit={'camera'}}
function M.script_world(template)
    if not TEMPLATES[template]then return nil,'unknown viewport template'end
    local S,why=M.api()
    if not S then return nil,why end
    for module,functions in pairs(WORLD_NEED)do
        if type(S[module])~='table'then return nil,'stingray.'..module..' is unavailable'end
        for _,name in ipairs(functions)do
            if not callable(S[module][name])then return nil,'stingray.'..module..'.'..name..' is not callable'end
        end
    end
    local W={state='open',template=template}
    local world,viewport,shading,camera
    local function release()
        if world==nil then W.state='released';return true end
        pcall(function()
            local alive=false
            for _,w in ipairs(S.Application.worlds()or{})do if w==world then alive=true end end
            if alive then
                if viewport~=nil then S.Application.destroy_viewport(world,viewport)end
                if shading~=nil then S.World.destroy_shading_environment(world,shading)end
                S.Application.release_world(world)
            end
        end)
        world,viewport,shading,camera=nil,nil,nil,nil
        W.world,W.state=nil,'released'
        return true
    end
    local ok,err=pcall(function()
        world=S.Application.new_world()
        if world==nil then error('new_world returned nothing',0)end
        viewport=S.Application.create_viewport(world,template)
        if viewport==nil then error('create_viewport returned nothing',0)end
        shading=S.World.create_shading_environment(world,M.SHADING)
        if shading==nil then error('create_shading_environment returned nothing',0)end
        local unit=S.World.spawn_unit(world,M.CAMERA_UNIT)
        if unit==nil then error('spawn_unit returned nothing',0)end
        camera=S.Unit.camera(unit,'camera')
        if camera==nil then error('the camera unit has no camera',0)end
    end)
    if not ok then release();return nil,tostring(err)end
    W.world=world
    -- Queues the world's render. The engine runs the Lua render callback before the game's own render callback in the
    -- same frame (exe 0x689BC0, then the game plugin's +0x90), so this render is queued before the game's worlds.
    function W.render()
        if W.state~='open'then return nil,'the world is '..W.state end
        local done,result=pcall(S.Application.render_world,world,camera,viewport,shading)
        if not done then release();W.state,W.reason='failed',tostring(result);return nil,W.reason end
        return true
    end
    W.release=release
    return W
end
return M
