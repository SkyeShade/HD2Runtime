local hd2=require('mods/skyeshade/hd2runtime')
-- GameIconProbe 0.2.0: WHICH GAME UI MATERIAL DRAWS A BOOSTER ICON AS THE GAME SHOWS IT? Development only, visual
-- only: nothing is written to game memory or game files, and no game resource is loaded, created or replaced. Needs
-- HD2Runtime with hd2.resources.game_icon (0.30.0-dev game-icons r59 or later).
--
-- 0.1.0 proved the technique (a material instance of this GUI pointed at the atlas page with Material.set_texture,
-- Gui.bitmap_uv drawing the sprite's rectangle). Through the stratagem icon material, a BOOSTER shows as a square: a
-- booster sprite is a full-colour picture whose hexagon is its ALPHA, and the icon shader stacks the texture's R, G, B
-- and A as four colour masks (research iconShader), so the colour left outside the hexagon is drawn too (live r59).
-- The game's UI image shader family (templates 0xBA25DE35, 0x09057911, 0x50C4CF1C, 0x40600CA5, 0xAAA07776, 0xDB4D723D:
-- the same diffuse_map slot, the UI variables desaturate / edge fade / distortion, and no c1-c3 mask layers) should draw
-- a texture's own colours with its alpha. This probe draws the Vitality Enhancement booster through one material of
-- each that every retained snapshot has loaded (ship, lobby, mission):
--   columns 1..6: BA25DE35, 09057911, 50C4CF1C, 40600CA5, AAA07776, DB4D723D (F6978E86E4F4B0D5: the material the native
--                 loadout icon element uses, research slotIconAtlas)
--   row 1: the material as it is (only its texture set)
--   row 2: the same, with c0 = (1, 1, 1, 1) (every one of these shaders declares c0; this row is a second GUI, so its
--          instances are its own)
-- A material not loaded is refused by Gui.bitmap (logged) and never reaches Material.*. Ctrl+F7 builds the panel (again:
-- rebuilds it); Ctrl+Shift+F7 closes it.
local mod=hd2.mod()
local BUILD='0.2.0 BOOSTER MATERIAL PROBE'
local overlay=require('hd2runtime/runtime/mod_overlay')
local game_icons=require('hd2runtime/runtime/game_icons')
mod:log('GameIconProbe '..BUILD..': aboard the ship press Ctrl+F7 (Ctrl+Shift+F7 closes). Two rows of six: the '
    ..'Vitality Enhancement booster through six game UI materials, row 1 as they are, row 2 with c0 white. Report '
    ..'which cells show the yellow HEXAGON with its dark glyph and nothing around it.')

local CANDIDATES={
    {shader='BA25DE35',material='00D6B572BE70B16E'},
    {shader='09057911',material='0125AADF01A93BEB'},
    {shader='50C4CF1C',material='004FAA2D735748E5'},
    {shader='40600CA5',material='9448536C2D6AE780'},
    {shader='AAA07776',material='326893A66351097E'},
    {shader='DB4D723D',material='F6978E86E4F4B0D5'},
}
local S=rawget(_G,'stingray')
local guis={}
local function id(hex)return S.IdString64.from_hex(hex)end
local function try(label,fn)
    local ok,result=pcall(fn)
    mod:log(('  %s: %s %s'):format(label,ok and'ok'or'FAILED',tostring(result)))
    return ok and result or nil
end
local function null(m)
    local text=tostring(m)
    return m==nil or text:match('NULL$')~=nil or text:match(':%s*0x0+$')~=nil
end
local function close()
    for _,g in ipairs(guis)do
        pcall(function()
            for _,w in ipairs(S.Application.worlds()or{})do if w==g.world then S.World.destroy_gui(g.world,g.gui)end end
        end)
    end
    if#guis>0 then mod:log('GameIconProbe: panel closed')end
    guis={}
end

local function open()
    close()
    if type(S)~='table'then return mod:log('GameIconProbe: no stingray API')end
    local world,ui_world=overlay.hooks.world()
    if not world then return mod:log('GameIconProbe: no UI world yet: '..tostring(ui_world))end
    local icon=assert(hd2.resources.game_icon('booster','Vitality Enhancement'))
    local spec,why=game_icons.resolve(world.runtime,icon)
    if not spec then return mod:log('GameIconProbe: the booster is not resolvable now: '..tostring(why))end
    local loaded=game_icons.page_loaded(world.runtime,spec.page)
    mod:log(('GameIconProbe %s: booster page %s loaded %s, sprite %dx%d'):format(BUILD,spec.page,tostring(loaded),spec.w,
        spec.h))
    if not loaded then return end
    local cell,gap=150,24
    local uv=game_icons.uv(spec,cell,cell)
    local sw,sh=S.Gui.resolution()
    local x0,top=80,sh-120
    for row=1,2 do
        local gui=try('row '..row..' create_screen_gui',function()return S.World.create_screen_gui(ui_world,'scale',1,1)end)
        if not gui then return end
        guis[#guis+1]={world=ui_world,gui=gui}
        local y=top-row*(cell+gap)
        if row==1 then
            try('backdrop',function()
                return S.Gui.rect(gui,S.Vector3(x0-gap,top-2*(cell+gap)-gap,1),
                    S.Vector2(#CANDIDATES*(cell+gap)+gap,2*(cell+gap)+2*gap),S.Color(235,24,26,30))
            end)
        end
        for col,c in ipairs(CANDIDATES)do
            local label=('row %d col %d (shader %s, material %s)'):format(row,col,c.shader,c.material)
            local drawn=try(label..' bitmap_uv',function()
                return S.Gui.bitmap_uv(gui,id(c.material),S.Vector2(uv[1],uv[2]),S.Vector2(uv[3],uv[4]),
                    S.Vector3(x0+(col-1)*(cell+gap),y,2),S.Vector2(cell,cell),S.Color(255,255,255,255))
            end)
            if drawn then
                local instance=try(label..' Gui.material',function()
                    local m=S.Gui.material(gui,id(c.material))
                    if null(m)then error('no instance (material not found)',0)end
                    return m
                end)
                if instance then
                    try(label..' set_texture',function()
                        S.Material.set_texture(instance,'diffuse_map',id(spec.page));return'set'
                    end)
                    if row==2 then
                        try(label..' set_vector4 c0',function()
                            S.Material.set_vector4(instance,'c0',S.Quaternion.from_elements(1,1,1,1));return'set'
                        end)
                    end
                end
            end
        end
    end
    mod:log('GameIconProbe: panel built at '..sw..' x '..sh..'. Report which cells show the hexagon cleanly.')
end

hd2.input.bind('game_icon_probe.open',{key='Ctrl+F7',on_press=function()
    local ok,err=pcall(open)
    if not ok then mod:log('GameIconProbe: open failed: '..tostring(err));close()end
end})
hd2.input.bind('game_icon_probe.close',{key='Ctrl+Shift+F7',on_press=function()pcall(close)end})
