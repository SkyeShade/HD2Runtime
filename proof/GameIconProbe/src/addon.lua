local hd2=require('mods/skyeshade/hd2runtime')
-- GameIconProbe 0.1.0: CAN A SCREEN GUI DRAW THE GAME'S OWN HUD ICONS? Development only, visual only: nothing is
-- written to game memory or game files, and no game resource is loaded, created or replaced.
--
-- The question (docs/game-icons.md): every stratagem and booster HUD icon is a 256 x 256 sprite of one of three
-- texture_atlas pages the game keeps loaded. A Gui.bitmap draws a MATERIAL, never a texture or a sprite (research
-- bitmapContract), but a GUI's own material instance can be given another texture: Material.set_texture(instance,
-- 'diffuse_map', IdString64 page) (exe 0x4A0460: the slot name hashed to its upper 32 bits, the texture an IdString64;
-- the icon material's one slot is 0x3AA8B87E = murmur64('diffuse_map') >> 32, research image-resources). With the page
-- set, Gui.bitmap_uv(gui, material, uv00, uv11, position, size, color) (exe 0x3E31D0: uv00 index 3, uv11 index 4) draws
-- only the sprite's rectangle of it. The material is the stratagem's own vanilla icon material (named by the icon hash,
-- exactly the sprite's name), so the instance is this GUI's own: the game's UI keeps its own instance untouched.
--
-- F7 opens the probe panel (again: rebuilds it; Shift+F7 closes it). Three rows, four columns:
--   rows:    1 EXO-45 Patriot Exosuit (atlas page 1)   2 B/MD C4 Pack (page 2)   3 Vitality Enhancement (booster page,
--            drawn through the Eagle 500kg Bomb's icon material as the carrier)
--   columns: A  the sprite, uv00 = (u0, v0)      uv11 = (u0 + du, v0 + dv)
--            B  the sprite, uv00 = (u0, v0 + dv) uv11 = (u0 + du, v0)        (A or B is upside down)
--            C  the whole page (Gui.bitmap with the texture set): proves set_texture changed what the material shows
--            D  control: the Resupply icon material with no texture set (what a vanilla icon material shows by itself)
-- Every step is logged; set_texture is called only when the page texture is proven loaded (an unloaded name is never
-- passed to the engine).
local mod=hd2.mod()
local BUILD='0.1.0 GAME ICON PROBE'
local overlay=require('hd2runtime/runtime/mod_overlay')
local images=require('hd2runtime/runtime/image_resources')
mod:log('GameIconProbe '..BUILD..': open the loadout screen aboard the ship, then press F7 (Shift+F7 closes). Rows: '
    ..'Patriot (page 1), C4 Pack (page 2), Vitality Enhancement (booster); columns A and B the sprite in two UV '
    ..'orientations, C the whole page, D an untouched vanilla icon material.')

-- The sprites (sdk/tools/hd2_hud_icons.py records of build F5FEE03DCFDB): sprite = icon material name, page texture.
local STRATAGEM={c0={0.8,1.0,0.43,0.36},c1={1,1,1,0.93},c2={0.2,0,0,0},c3={0,0,0,0}}
local BOOSTER={c0={1,1,0.78,0.17},c1={0,0,0,0},c2={0,0,0,0},c3={0,0,0,0}}
local ROWS={
    {label='EXO-45 Patriot Exosuit',material='396ECA60A6E80E17',page='5207684C3952B0CC',
        uv={0.8046875,0.23828125,0.0625,0.0625},colours=STRATAGEM},
    {label='B/MD C4 Pack',material='286AD42DBC7314D0',page='6E09D5A15DEC6F79',
        uv={0.5703125,0.4296875,0.125,0.125},colours=STRATAGEM},
    {label='Vitality Enhancement (booster, carrier: Eagle 500kg Bomb material)',material='F96A659EBFFDFBE4',
        page='18EDBED388A3D706',uv={0.89501953125,0.1484375,0.0625,0.125},colours=BOOSTER},
}
local CONTROL='89FB769B9CF03E58'     -- the Resupply icon material, drawn as it is

local S=rawget(_G,'stingray')
local panel        -- {world, gui}
local function halves(hex)return tonumber(hex:sub(1,8),16),tonumber(hex:sub(9,16),16)end
local function id(hex)return S.IdString64.from_hex(hex)end
local function try(label,fn)
    local ok,result=pcall(fn)
    mod:log(('  %s: %s %s'):format(label,ok and'ok'or'FAILED',ok and tostring(result)or tostring(result)))
    return ok and result or nil
end

local function close()
    if panel then
        pcall(function()
            for _,w in ipairs(S.Application.worlds()or{})do
                if w==panel.world then S.World.destroy_gui(panel.world,panel.gui)end
            end
        end)
        panel=nil
        mod:log('GameIconProbe: panel closed')
    end
end

local function open()
    close()
    if type(S)~='table'then return mod:log('GameIconProbe: no stingray API')end
    local world,ui_world=overlay.hooks.world()
    if not world then return mod:log('GameIconProbe: no UI world yet: '..tostring(ui_world))end
    local runtime=world.runtime
    mod:log('GameIconProbe '..BUILD..': building the panel')
    -- residency first: each material (exactly a vanilla icon material: material + atlas sprite) and each page texture
    local ready={}
    for i,row in ipairs(ROWS)do
        local fam=images.family_of(runtime,halves(row.material))
        local page,why=images.texture_resource(runtime,halves(row.page))
        ready[i]=page~=nil
        mod:log(('  row %d %s: material %s (sprite %s); page %s %s'):format(i,row.label,tostring(fam.material),
            tostring(fam.sprite),row.page,page and'LOADED'or('not loaded: '..tostring(why))))
    end
    local cfam=images.family_of(runtime,halves(CONTROL))
    mod:log('  control material '..CONTROL..': '..tostring(cfam.material))
    local gui=try('create_screen_gui',function()return S.World.create_screen_gui(ui_world,'scale',1,1)end)
    if not gui then return end
    panel={world=ui_world,gui=gui}
    local sw,sh=S.Gui.resolution()
    local cell,gap=150,24
    local x0=80
    local top=sh-120
    -- a dark backdrop so masks with a white layer show
    try('backdrop',function()
        return S.Gui.rect(gui,S.Vector3(x0-gap,top-3*(cell+gap)-gap,1),S.Vector2(4*(cell+gap)+gap,3*(cell+gap)+2*gap),
            S.Color(235,24,26,30))
    end)
    for i,row in ipairs(ROWS)do
        local y=top-i*(cell+gap)
        local u0,v0,du,dv=row.uv[1],row.uv[2],row.uv[3],row.uv[4]
        mod:log(('row %d %s'):format(i,row.label))
        -- A and B: the sprite (the material must have a bitmap in this GUI before Gui.material)
        try('A bitmap_uv (u0,v0)-(u1,v1)',function()
            return S.Gui.bitmap_uv(gui,id(row.material),S.Vector2(u0,v0),S.Vector2(u0+du,v0+dv),S.Vector3(x0,y,2),
                S.Vector2(cell,cell),S.Color(255,255,255,255))
        end)
        try('B bitmap_uv (u0,v1)-(u1,v0)',function()
            return S.Gui.bitmap_uv(gui,id(row.material),S.Vector2(u0,v0+dv),S.Vector2(u0+du,v0),
                S.Vector3(x0+(cell+gap),y,2),S.Vector2(cell,cell),S.Color(255,255,255,255))
        end)
        try('C bitmap (whole page)',function()
            return S.Gui.bitmap(gui,id(row.material),S.Vector3(x0+2*(cell+gap),y,2),S.Vector2(cell,cell),
                S.Color(255,255,255,255))
        end)
        local instance=try('Gui.material',function()
            local m=S.Gui.material(gui,id(row.material))
            local text=tostring(m)
            if m==nil or text:match('NULL$')or text:match(':%s*0x0+$')then error('no instance (material not found)',0)end
            return m
        end)
        if instance then
            for _,name in ipairs({'c0','c1','c2','c3'})do
                local c=row.colours[name]
                try('set_vector4 '..name,function()
                    S.Material.set_vector4(instance,name,S.Quaternion.from_elements(c[1],c[2],c[3],c[4]))
                    return'set'
                end)
            end
            if ready[i]then
                try('set_texture diffuse_map = page '..row.page,function()
                    S.Material.set_texture(instance,'diffuse_map',id(row.page))
                    return'set'
                end)
            else
                mod:log('  set_texture skipped: the page texture is not loaded')
            end
        end
        -- D: the control, a vanilla icon material with nothing but its colours
        try('D control bitmap',function()
            return S.Gui.bitmap(gui,id(CONTROL),S.Vector3(x0+3*(cell+gap),y,2),S.Vector2(cell,cell),
                S.Color(255,255,255,255))
        end)
        if i==1 then
            local c=try('control Gui.material',function()return S.Gui.material(gui,id(CONTROL))end)
            if c then
                for _,name in ipairs({'c0','c1','c2'})do
                    local v=STRATAGEM[name]
                    try('control set_vector4 '..name,function()
                        S.Material.set_vector4(c,name,S.Quaternion.from_elements(v[1],v[2],v[3],v[4]));return'set'
                    end)
                end
            end
        end
    end
    mod:log('GameIconProbe: panel built at '..sw..' x '..sh..'. Report, per row, what columns A, B, C and D show.')
end

hd2.input.bind('game_icon_probe.open',{key='F7',on_press=function()
    local ok,err=pcall(open)
    if not ok then mod:log('GameIconProbe: open failed: '..tostring(err));close()end
end})
hd2.input.bind('game_icon_probe.close',{key='Shift+F7',on_press=function()pcall(close)end})
