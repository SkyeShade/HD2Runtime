-- Mod screen overlays (hd2.ui.overlay; docs/ui-overlay.md): rectangles and text a mod draws over the game, through the
-- Runtime's own GUI path, so no mod has to learn its traps again:
--
-- * The world: a screen GUI in the game's Ui World (runtime/stratagem_slot_overlay.lua open_gui), where the Runtime's
--   slot overlays, panel and labels are seen live. Application.main_world is the Game World, under the whole UI.
--   The Ui World is found again every frame; a new one (ship <-> mission) or a new resolution reopens the GUI.
-- * Layers: one band per overlay inside 1..1023. The engine orders a world's GUIs together by layer, the depth key is
--   0.1 * (1023 - layer) / 1023 (exe 0x2693E3), so nothing above 1023 is valid; the default base 1011 sits over the
--   native HUD's own top layers. The game's Noesis UI (menus, the map) always draws above every screen GUI.
-- * Retained primitives: a mod describes the whole frame in its draw function, immediate style; the overlay keeps one
--   engine primitive per drawn item and only updates what changed (Gui.update_rect / update_text), creates what is new
--   and destroys what is gone. An unchanged frame makes no engine call.
-- * Temporaries: every pass that calls the engine runs inside engine_gui.temp_scope (Script.temp_count /
--   set_temp_count), so the Vector3 / Vector2 / Color values it builds never move the temporaries ring on.
-- * Every value is validated before it reaches the engine (the bindings check nothing): finite pixel boxes inside the
--   screen, integer layers inside the band, colours 0..255, printable text of at most 512 bytes, MAX_ITEMS a frame.
-- * Other scripts (research/docs/game-font-text.md): a character the role's font lacks is drawn in the game's own
--   language font that has it, when that font is loaded (the game loads the selected language's): the text is split
--   into runs (runtime/ui_fonts.lua runs), one engine text each; a game font is named by its hash and drawn through
--   its Runtime-owned material, whose instance in this GUI is pointed at the font's atlas (Material.set_texture) once
--   the font, its atlas and the material are proven loaded this frame. Text the role font fully covers is one item,
--   drawn exactly as before. When a game font in use unloads (a language switch), the GUI is closed first and opened
--   again without it.
-- * Coordinates are GUI pixels with the origin at the TOP-LEFT (y down), like hd2.input.mouse(); overlay.scale is the
--   screen against 1920 x 1080 (the smaller ratio), to size a layout made at 1080p.
-- * A draw function that raises is a frame callback failure of the mod (logged, disabled after 25 in a row); the
--   overlay hides its primitives on that frame. An engine call that fails closes the GUI (logged once per reason); it
--   is opened again on a later frame.
-- * The game's own HUD icons (hd2.resources.game_icon; docs/game-icons.md) draw through d:image like a mod's own image:
--   a material instance in this GUI points at the sprite's atlas page (Material.set_texture) and Gui.bitmap_uv draws
--   the sprite's rectangle. Each frame every icon is given a material: a stratagem its own icon material (a second
--   colour set of it a carrier: another stratagem's icon material unused this frame); a booster a UI image material
--   (its own colours with its alpha; runtime/game_icons.lua).
--   set_texture only ever names a page proven loaded this frame; when a page or a material in use unloads, the GUI is
--   closed (its instances go with it) and opened again without that icon.
-- Visual only: nothing here writes game memory.
local engine_gui=require('hd2runtime/runtime/engine_gui')
local events=require('hd2runtime/runtime/events')
local log=require('hd2runtime/runtime/log')
local world_module=require('hd2runtime/runtime/event_world')
local selector=require('hd2runtime/runtime/stratagem_selector')
local slot_overlay=require('hd2runtime/runtime/stratagem_slot_overlay')
local ui_fonts=require('hd2runtime/runtime/ui_fonts')
local font_data=require('hd2runtime/domains/ui_fonts')
local images=require('hd2runtime/runtime/image_resources')
local game_icons=require('hd2runtime/runtime/game_icons')
local input=require('hd2runtime/runtime/input')
local cursor=require('hd2runtime/runtime/mod_cursor')
local KEY='HD2RuntimeModOverlaysV1'
local existing=rawget(_G,KEY)
if existing then return existing end
local M={}
rawset(_G,KEY,M)
M.MAX_LAYER=1023
M.DEFAULT_LAYER=1011
M.MAX_ITEMS=1024
M.FONT_ROLES={body=true,title=true,mono=true}
-- The Runtime's FS Sinclair fonts draw their glyphs this fraction of the size BELOW the baseline Gui.text is given
-- (live 2026-10-07, HD2Runtime Editor at 3838 x 2158: sizes 12-22 all landed 0.37-0.45 x size low, mean 0.41). The
-- font build measures glyph records from the typographic baseline but writes the header offset -descent*0.75
-- (scripts/hd2_font.py), the monaco convention for records measured from the line bottom; the rest is likely the
-- distance-field padding. The overlay lifts its text by this much, so (x, y) is the line's top-left as documented.
M.TEXT_DROP=0.41
local overlays={}

local function emit(message)pcall(log.emit,'[HD2Runtime] '..message)end

-- The hooks the overlay reads the game through (tests replace them).
M.hooks={}
-- The proven event world and its Ui World value, or nil and why. Read once per update tick for every overlay.
local world_tick,world_cache=-1,nil
local function find_world()
    local world,why=world_module.open()
    if not world then return nil,why end
    local proven,pwhy=selector.prove(world)
    if not proven then return nil,pwhy end
    local value,vwhy=slot_overlay.ui_world(world)
    if not value then return nil,'the Ui World: '..tostring(vwhy)end
    return world,value
end
function M.hooks.world()
    local frame=events.state.frame
    if world_tick~=frame then world_tick,world_cache=frame,{find_world()}end
    return world_cache[1],world_cache[2]
end
function M.hooks.open_screen(world,ui_world,max_layer)return engine_gui.open({world=ui_world,max_layer=max_layer})end
-- A font role's font ({name, em, ascent, advances, ...}), or nil and why when neither it nor monaco is loaded.
function M.hooks.font(world,role)
    if role~='mono'then
        local font=ui_fonts.font(world.runtime,role)
        if not font.fallback then return font end
    end
    local m=font_data.fonts.monaco
    for _,kind in ipairs({font_data.types.font,font_data.types.material})do
        local ok,loaded=pcall(images.loaded,world.runtime,kind,m.name)
        if not(ok and loaded)then return nil,'no font is loaded'end
    end
    return m
end
function M.hooks.mouse()return input.mouse()end
-- Whether an image's texture, material and sprite are loaded (runtime/image_resources.lua family), or false and why.
function M.hooks.image_ready(world,handle)
    local family=images.family(world.runtime,handle)
    if family and family.complete then return true end
    return false,family and family.reason or'not loaded'
end
-- A game icon's drawing needs read from the running game (runtime/game_icons.lua resolve), or nil and why.
function M.hooks.game_icon(world,handle)return game_icons.resolve(world.runtime,handle)end
-- Whether an atlas page texture / a stratagem icon material ('%016X') is loaded now.
function M.hooks.page_loaded(world,page)return game_icons.page_loaded(world.runtime,page)end
function M.hooks.material_loaded(world,material)return game_icons.material_loaded(world.runtime,material)end
-- The loaded UI image materials booster icons are drawn through ('%016X' list), or nil and why.
function M.hooks.image_materials(world)return game_icons.image_materials(world.runtime)end
-- The game's language fonts loaded now (runtime/ui_fonts.lua resident_game_fonts; proven at most a second ago), as
-- drawing fonts, in the domain's order.
function M.hooks.game_fonts(world)return ui_fonts.resident_game_fonts(world.runtime)end
-- Whether one game font (its font, atlas and Runtime material) is loaded THIS frame: true, or false and why.
function M.hooks.game_font_ready(world,font)return ui_fonts.game_font_ready(world.runtime,font.game)end
-- Text with characters no loaded font has: ask for the game font package that has them (runtime/ui_fonts.lua want).
function M.hooks.want_fonts(world,font,text,extra)return ui_fonts.want(world.runtime,font,text,extra)end
-- The Runtime reader for queries outside a frame (hd2.ui.can_draw, hd2.ui.fonts): the proven event world's runtime,
-- or nil and why.
function M.hooks.runtime()
    local ok,world,why=pcall(world_module.open)
    if not ok then return nil,tostring(world)end
    if not world then return nil,why end
    return world.runtime
end
-- Offline fallback metrics (only for text_width before the first frame): monaco's.
local function metrics_font()return font_data.fonts.monaco end

---------------------------------------------------------------------------------------------------- values --
local function finite(n)return type(n)=='number'and n==n and n>-math.huge and n<math.huge end
local function byte(n)return math.floor(math.max(0,math.min(255,n))+0.5)end
-- {r, g, b[, a]} (0-255; a defaults to 255) or '#RRGGBB' / '#RRGGBBAA' -> the engine's {a, r, g, b}; nil when invalid.
local function colour(c)
    if c==nil then return {255,255,255,255}end
    if type(c)=='string'then
        local hex=c:match('^#(%x+)$')
        if not hex or(#hex~=6 and#hex~=8)then return nil end
        local r,g,b=tonumber(hex:sub(1,2),16),tonumber(hex:sub(3,4),16),tonumber(hex:sub(5,6),16)
        local a=#hex==8 and tonumber(hex:sub(7,8),16)or 255
        return {a,r,g,b}
    end
    if type(c)~='table'then return nil end
    local r,g,b,a=c[1]or c.r,c[2]or c.g,c[3]or c.b,c[4]or c.a or 255
    if not(finite(r)and finite(g)and finite(b)and finite(a))then return nil end
    return {byte(a),byte(r),byte(g),byte(b)}
end
M.colour=colour

---------------------------------------------------------------------------------------------- the frame builder --
-- d:rect(x, y, w, h, colour, z), d:text(text, x, y, opts), d:text_width(text, size, font): what one frame shows. Items
-- are collected here; the overlay turns them into engine calls after the draw function returns.
local Builder={};Builder.__index=Builder
local function refuse(self,why)
    self.refused=self.refused+1
    if not self.first_refusal then self.first_refusal=why end
end
function Builder:rect(x,y,w,h,c,z)
    if#self.items>=M.MAX_ITEMS then return refuse(self,'more than '..M.MAX_ITEMS..' items in one frame')end
    z=z or 0
    if not(finite(x)and finite(y)and finite(w)and finite(h)and w>=0 and h>=0 and type(z)=='number'and z%1==0
        and z>=0 and self.layer+z<=M.MAX_LAYER)then
        return refuse(self,'invalid rectangle')
    end
    local col=colour(c)
    if not col then return refuse(self,'invalid colour')end
    -- Clipped to the screen (the engine draws nothing outside it; the bindings must never see a box past it).
    local x0,y0=math.max(0,x),math.max(0,y)
    local x1,y1=math.min(self.width,x+w),math.min(self.height,y+h)
    if x1<=x0 or y1<=y0 then return end
    self.items[#self.items+1]={kind='rect',x=x0,y=self.height-y1,w=x1-x0,h=y1-y0,layer=self.layer+z,c=col}
end
-- Where a font's baseline lands below the y Gui.text is given, a fraction of the size: the Runtime's FS Sinclair fonts
-- by the live calibration (M.TEXT_DROP), monaco and the game's fonts as measured on their atlases (domains/ui_fonts.lua
-- drop; research game-font-text: the game fonts' is 0).
local function drop_of(font)
    if type(font.name)=='string'and font.name:find('^hd2runtime_fonts/')then return M.TEXT_DROP end
    return font.drop or 0
end
-- The role's font of this frame, or nil and why.
local function role_font(self,role)
    local font=self.fonts[role]
    if font==nil then
        local f,why=self.font_for(role)
        font=f or false
        self.fonts[role]=font
        if not f then self.font_why=why end
    end
    return font or nil,self.font_why
end
-- The runs text is drawn in (runtime/ui_fonts.lua runs): one run in the role font when it has every character.
local function text_runs(self,font,text)
    if ui_fonts.has(font,text)then return {{font=font,text=text}}end
    local extra=self.extra_fonts and self.extra_fonts()
    if self.want_fonts then self.want_fonts(font,text,extra)end
    return ui_fonts.runs(font,text,extra)
end
-- opts: {size = pixels (default 18), colour, font = 'body' | 'title' | 'mono', align = 'left' | 'center' | 'right',
-- z}. (x, y) is the top-left corner of the line (the text's ascent below y), or its top-centre / top-right.
function Builder:text(text,x,y,opts)
    if#self.items>=M.MAX_ITEMS then return refuse(self,'more than '..M.MAX_ITEMS..' items in one frame')end
    opts=opts or{}
    if type(text)=='number'then text=tostring(text)end
    if type(text)~='string'then return refuse(self,'text must be a string')end
    if text==''then return end
    if#text>ui_fonts.MAX_TEXT_BYTES or text:find('[%z\1-\31\127]')then
        return refuse(self,'text must be 1-'..ui_fonts.MAX_TEXT_BYTES..' printable bytes')
    end
    local size=opts.size or 18
    local z=opts.z or 0
    local role=opts.font or'body'
    if not(finite(x)and finite(y)and finite(size)and size>=4 and size<=256 and type(z)=='number'and z%1==0
        and z>=0 and self.layer+z<=M.MAX_LAYER and M.FONT_ROLES[role])then
        return refuse(self,'invalid text')
    end
    local col=colour(opts.colour or opts.color)
    if not col then return refuse(self,'invalid colour')end
    local font,why=role_font(self,role)
    if not font then return refuse(self,'text not drawn: '..tostring(why))end
    local runs=text_runs(self,font,text)
    if opts.align=='center'or opts.align=='right'then
        local w=0
        for _,run in ipairs(runs)do w=w+ui_fonts.width(run.font,run.text,size)end
        x=x-(opts.align=='center'and w/2 or w)
    end
    local baseline=self.height-(y+font.ascent*size/font.em)
    if type(font.name)=='string'and font.name:find('^hd2runtime_fonts/')then baseline=baseline+M.TEXT_DROP*size end
    if x<0 or x>self.width or baseline<0 or baseline>self.height then return end
    if#runs==1 and runs[1].font==font then
        -- every character in the role's font: one item, exactly as before
        self.items[#self.items+1]={kind='text',s=text,font=font.name,material=font.name,size=size,x=x,y=baseline,
            layer=self.layer+z,c=col}
        return
    end
    if#self.items+#runs>M.MAX_ITEMS then return refuse(self,'more than '..M.MAX_ITEMS..' items in one frame')end
    -- Each run on the role font's visual baseline: a font whose glyphs land `drop` x size below the y it is given is
    -- given that much higher.
    local visual=baseline-drop_of(font)*size
    local pen=x
    for _,run in ipairs(runs)do
        if pen>self.width then break end
        local y_run=run.font==font and baseline or visual+drop_of(run.font)*size
        if y_run>=0 and y_run<=self.height then
            self.items[#self.items+1]={kind='text',s=run.text,font=run.font.name,material=run.font.material or run.font.name,
                size=size,x=pen,y=y_run,layer=self.layer+z,c=col,game=run.font.game and run.font or nil}
        end
        pen=pen+ui_fonts.width(run.font,run.text,size)
    end
end
-- The width in pixels of text at size in a font role (the same metrics and runs the drawing uses).
function Builder:text_width(text,size,role)
    local font=role_font(self,role or'body')or metrics_font()
    text=tostring(text)
    local w=0
    for _,run in ipairs(text_runs(self,font,text))do w=w+ui_fonts.width(run.font,run.text,size or 18)end
    return w
end
-- Whether every character of text can be drawn now in a font role (its own font or a loaded game font): true, or
-- false, the number of distinct characters that would show as '?' and up to three of them.
function Builder:can_draw(text,role)
    local font=role_font(self,role or'body')or metrics_font()
    return ui_fonts.drawable(font,tostring(text),self.extra_fonts and self.extra_fonts())
end
-- Lines of text no wider than `width` pixels (runtime/ui_fonts.lua wrap: at spaces and between CJK characters, never
-- inside a character), measured as d:text draws them. opts: {size = 18, font = 'body', lines = the most lines (the
-- last ends with '...')}.
function Builder:wrap(text,width,opts)
    opts=opts or{}
    local font=role_font(self,opts.font or'body')or metrics_font()
    return ui_fonts.wrap(font,tostring(text),opts.size or 18,width,opts.lines,self.extra_fonts and self.extra_fonts()or{})
end

-- Mask colours of an image (the icon material's c0-c2 for the R, G and B masks; c3 is always zero, because the BC1
-- texture's alpha is about 1 everywhere and a non-zero c3 would flood the quad). opts.colours = {r =, g =, b =} with
-- overlay colours; the alpha is the layer's strength. Default: white R and G, the native 0.2 black shadow on B.
local DEFAULT_MASKS={r={255,255,255,255},g={255,255,255,255},b={0,0,0,51}}
local function mask_vars(spec)
    spec=spec or{}
    local vars,key={},{}
    for index,channel in ipairs({'r','g','b'})do
        local c=colour(spec[channel]or DEFAULT_MASKS[channel])
        if not c then return nil end
        local v={'c'..(index-1),c[1]/255,c[2]/255,c[3]/255,c[4]/255}
        vars[index]=v
        key[index]=table.concat({c[1],c[2],c[3],c[4]},',')
    end
    vars[4]={'c3',0,0,0,0}
    return vars,table.concat(key,';')
end
-- d:image(handle, x, y, w, h, {colours = {r, g, b}, colour = vertex colour (tint / alpha), z}): one of the mod's own
-- images (hd2.resources.image), drawn through the game's icon material (docs/custom-images.md: 256 x 256 masks, or a
-- raw picture shown as a silhouette). Drawn only once the image's resources are proven loaded; an image partly off
-- screen is dropped (a bitmap is never squashed). One colour set per image per overlay (one material instance).
-- A game icon: a stratagem through icon materials with mask colours (default R and G white and the B shadow, as a
-- mod image); a booster through a UI image material in its own colours (opts.colours does not apply; opts.colour, the
-- vertex colour, still tints it).
function Builder:game_icon(handle,x,y,w,h,opts)
    local z=opts.z or 0
    if not(finite(x)and finite(y)and finite(w)and finite(h)and w>0 and h>0 and type(z)=='number'and z%1==0
        and z>=0 and self.layer+z<=M.MAX_LAYER)then
        return refuse(self,'invalid image box')
    end
    local col=colour(opts.colour or opts.color)
    if not col then return refuse(self,'invalid colour')end
    local kind=game_icons.identity(handle).kind
    local vars,key
    if kind=='stratagem'then
        vars,key=mask_vars(opts.colours)
        if not vars then return refuse(self,'invalid mask colours')end
    end
    if x<0 or y<0 or x+w>self.width or y+h>self.height then return end
    local spec,why=self.icon_ready(handle)
    if not spec then self.waiting_images=(self.waiting_images or 0)+1;self.image_why=why;return end
    -- the sprite's UVs for this box (inset by one texel of the mip level it samples; runtime/game_icons.lua uv)
    local uv=spec.rect and game_icons.uv(spec,w,h)or spec.uv
    self.items[#self.items+1]={kind='uvbitmap',icon=handle,page=spec.page,own=spec.own,pool=spec.pool or'icon',uv=uv,
        x=x,y=self.height-(y+h),w=w,h=h,layer=self.layer+z,c=col,vars=vars,
        vkey=spec.page..'|'..(key or'image')}
end
function Builder:image(handle,x,y,w,h,opts)
    if#self.items>=M.MAX_ITEMS then return refuse(self,'more than '..M.MAX_ITEMS..' items in one frame')end
    opts=opts or{}
    if game_icons.issued(handle)then return self:game_icon(handle,x,y,w,h,opts)end
    if not images.issued(handle)then return refuse(self,'not an image from hd2.resources.image')end
    local z=opts.z or 0
    if not(finite(x)and finite(y)and finite(w)and finite(h)and w>0 and h>0 and type(z)=='number'and z%1==0
        and z>=0 and self.layer+z<=M.MAX_LAYER)then
        return refuse(self,'invalid image box')
    end
    local col=colour(opts.colour or opts.color)
    if not col then return refuse(self,'invalid colour')end
    local vars,key=mask_vars(opts.colours)
    if not vars then return refuse(self,'invalid mask colours')end
    if x<0 or y<0 or x+w>self.width or y+h>self.height then return end
    local material=images.material_name(handle)
    local seen=self.materials[material]
    if seen and seen~=key then return refuse(self,'one colour set per image per overlay: '..material)end
    local ready,why=self.image_ready(handle)
    if not ready then self.waiting_images=(self.waiting_images or 0)+1;self.image_why=why;return end
    self.materials[material]=key
    self.items[#self.items+1]={kind='bitmap',material=material,x=x,y=self.height-(y+h),w=w,h=h,layer=self.layer+z,
        c=col,vars=vars,vkey=key}
end

------------------------------------------------------------------------------------------------- reconciling --
local function same_colour(a,b)return a[1]==b[1]and a[2]==b[2]and a[3]==b[3]and a[4]==b[4]end
local function same(a,b)
    if a.kind~=b.kind or a.x~=b.x or a.y~=b.y or a.layer~=b.layer or not same_colour(a.c,b.c)then return false end
    if a.kind=='rect'then return a.w==b.w and a.h==b.h end
    if a.kind=='bitmap'then return a.material==b.material and a.w==b.w and a.h==b.h end
    if a.kind=='uvbitmap'then
        return a.material==b.material and a.w==b.w and a.h==b.h and a.uv[1]==b.uv[1]and a.uv[2]==b.uv[2]
            and a.uv[3]==b.uv[3]and a.uv[4]==b.uv[4]
    end
    return a.s==b.s and a.font==b.font and a.size==b.size and a.material==b.material
end
local function create(screen,item)
    if item.kind=='rect'then return screen.rect(item.x,item.y,item.layer,item.w,item.h,item.c)end
    if item.kind=='bitmap'then return screen.bitmap(item.material,item.x,item.y,item.layer,item.w,item.h,item.c)end
    if item.kind=='uvbitmap'then
        return screen.bitmap_uv(item.material,item.uv,item.x,item.y,item.layer,item.w,item.h,item.c)
    end
    return screen.text(item.s,item.font,item.size,item.material or item.font,item.x,item.y,item.layer,item.c)
end
local function update(screen,old,item)
    if item.kind=='rect'then return screen.update_rect(old.id,item.x,item.y,item.layer,item.w,item.h,item.c)end
    if item.kind=='bitmap'then
        return screen.update_bitmap(old.id,item.material,item.x,item.y,item.layer,item.w,item.h,item.c)
    end
    if item.kind=='uvbitmap'then
        local ok,why=screen.update_bitmap_uv(old.id,item.material,item.uv,item.x,item.y,item.layer,item.w,item.h,item.c)
        if ok==nil and tostring(why):find('not callable',1,true)then
            -- No update_bitmap_uv binding: replace the primitive.
            if not screen.destroy('uvbitmap',old.id)then return nil,'destroy_bitmap failed'end
            local id,cwhy=create(screen,item)
            if id==nil then return nil,cwhy end
            old.id=id
            return true
        end
        return ok,why
    end
    local ok,why=screen.update_text(old.id,item.s,item.font,item.size,item.material or item.font,item.x,item.y,item.layer,
        item.c)
    if ok==nil and tostring(why):find('not callable',1,true)then
        -- No update_text binding: replace the primitive.
        if not screen.destroy('text',old.id)then return nil,'destroy_text failed'end
        local id,cwhy=create(screen,item)
        if id==nil then return nil,cwhy end
        old.id=id
        return true
    end
    return ok,why
end
-- Brings the screen from `drawn` to `items` (both lists of items; drawn ones carry their engine id). Returns the new
-- drawn list and the number of engine calls, or nil and why (the screen is then closed by the caller).
local function reconcile(screen,drawn,items)
    local calls=0
    local out={}
    for i,item in ipairs(items)do
        local old=drawn[i]
        if old and old.kind==item.kind then
            if same(old,item)then item.id=old.id
            else
                local ok,why=update(screen,old,item)
                if not ok then return nil,why end
                item.id=old.id
                calls=calls+1
            end
        else
            if old then
                local ok,why=screen.destroy(old.kind,old.id)
                if not ok then return nil,why end
                calls=calls+1
            end
            local id,why=create(screen,item)
            if id==nil then return nil,why end
            item.id=id
            calls=calls+1
        end
        out[i]=item
    end
    for i=#items+1,#drawn do
        local ok,why=screen.destroy(drawn[i].kind,drawn[i].id)
        if not ok then return nil,why end
        calls=calls+1
    end
    return out,calls
end
M.reconcile=reconcile
-- Reconcile, then give each image material drawn this frame its mask colours (once per GUI, again when they change).
-- A failed material lookup leaves the image transparent and is reported, never failing the screen.
local function reconcile_and_colour(screen,drawn,items,coloured)
    local out,calls=reconcile(screen,drawn,items)
    if not out then return nil,calls end
    for _,item in ipairs(out)do
        if item.kind=='bitmap'and coloured[item.material]~=item.vkey then
            coloured[item.material]=item.vkey
            local instance=screen.material(item.material)
            if instance then
                local ok=screen.set_vectors(instance,item.vars)
                calls=calls+1
                if not ok then coloured[item.material]=false end
            else coloured[item.material]=false end
        elseif item.kind=='uvbitmap'and coloured[item.material]~=item.vkey then
            -- a game icon: this GUI's instance of its material gets the colours and the atlas page (proven loaded
            -- this frame, item.page_ok; a page not proven is never named to the engine)
            coloured[item.material]=item.vkey
            local instance=item.page_ok and screen.material(item.material,true)
            if instance then
                local ok=(item.vars==nil or screen.set_vectors(instance,item.vars))
                    and screen.set_texture(instance,'diffuse_map',item.page)
                calls=calls+2
                if not ok then coloured[item.material]=false end
            else coloured[item.material]=false end
        elseif item.kind=='text'and item.game and item.font_ok and coloured[item.material]~=item.game.atlas then
            -- a game font run: this GUI's instance of the font's Runtime material (created by the text just made)
            -- samples the font's atlas, proven loaded this frame (item.font_ok); until then it shows nothing (its
            -- own texture is an empty placeholder)
            coloured[item.material]=item.game.atlas
            local instance,why=screen.material(item.material)
            local ok
            if instance then ok,why=screen.set_texture(instance,'msdf_texture',item.game.atlas);calls=calls+1 end
            if not ok then
                coloured[item.material]=false
                coloured.text_reason=item.game.key..': '..tostring(why)
            end
        end
    end
    return out,calls
end

-- Gives every game icon of a frame a material (in place; icons left without one are dropped and refused): a
-- stratagem first its own icon material, else (its own material already holds another page or colour set this frame)
-- a carrier from the stratagem icon materials; a booster a material from the UI image materials (image_pool). A carrier
-- is the material that served the same (page, colours) last frame if still free, else the first free loaded one of its
-- pool (sorted, so choices are stable). One instance holds one texture and one colour set, so no two (page, colours)
-- ever share a material in one frame.
local function assign_materials(self,items,carrier_ok,image_pool)
    local used={}
    for _,item in ipairs(items)do
        if item.kind=='uvbitmap'and item.own and(used[item.own]==nil or used[item.own]==item.vkey)then
            used[item.own]=item.vkey
            item.material=item.own
        end
    end
    local keep,dropped={},0
    local carriers=self.carriers or{}
    local next_carriers={}
    for _,item in ipairs(items)do
        if item.kind=='uvbitmap'and not item.material then
            local m=next_carriers[item.vkey]
            if not m then
                local last=carriers[item.vkey]
                if last and used[last]==nil and carrier_ok(last)then m=last end
            end
            if not m then
                local pool=item.pool=='image'and(image_pool or{})or game_icons.carriers()
                for _,candidate in ipairs(pool)do
                    if used[candidate]==nil and carrier_ok(candidate)then m=candidate;break end
                end
            end
            if m then
                used[m]=item.vkey
                next_carriers[item.vkey]=m
                item.material=m
            end
        end
        if item.kind~='uvbitmap'or item.material then keep[#keep+1]=item else dropped=dropped+1 end
    end
    self.carriers=next_carriers
    return keep,dropped
end
M.assign_materials=assign_materials
M.reconcile_and_colour=reconcile_and_colour

---------------------------------------------------------------------------------------------------- overlays --
local Overlay={};Overlay.__index=Overlay
local function close_screen(self)
    self.coloured,self.ready,self.icons,self.icon_pages,self.icon_materials,self.carriers={},{},{},nil,nil,nil
    self.text_fonts=nil
    if self.screen then pcall(self.screen.close)end
    self.screen,self.ui_world,self.drawn=nil,nil,{}
end
local function note(self,state,reason)
    self.state,self.reason=state,reason
    if reason and self.logged_reason~=reason and(state=='failed')then
        self.logged_reason=reason
        emit('overlay '..self.owner..'/'..self.id..': '..reason)
    end
end
local function frame(self,dt)
    if not self.visible or not self.draw_fn then
        if self.cursor then cursor.release(self.key)end
        if self.screen then close_screen(self)end
        note(self,'hidden')
        return
    end
    if self.cursor then
        local held,why=cursor.hold(self.key,self.cursor)
        self.cursor_reason=not held and why or nil
    end
    local world,ui_world=M.hooks.world()
    if not world then if self.screen then close_screen(self)end;note(self,'waiting',tostring(ui_world));return end
    if self.screen and(self.ui_world~=ui_world or self.screen.state~='open')then close_screen(self)end
    if not self.screen then
        local ok,screen,why=pcall(M.hooks.open_screen,world,ui_world,M.MAX_LAYER)
        if not(ok and screen)then note(self,'failed',ok and tostring(why)or tostring(screen));return end
        self.screen,self.ui_world,self.drawn=screen,ui_world,{}
        self.opened=self.opened+1
    end
    -- A game icon page or material in use that unloaded: close the GUI first (its material instances name them), so
    -- nothing on screen keeps pointing at a resource that is gone; the frame below draws without it.
    if self.icon_pages then
        local lost
        for page in pairs(self.icon_pages)do
            local ok,loaded=pcall(M.hooks.page_loaded,world,page)
            if not(ok and loaded)then lost='atlas page '..page;break end
        end
        if not lost and self.icon_materials and self.frames%15==0 then
            for material in pairs(self.icon_materials)do
                local ok,loaded=pcall(M.hooks.material_loaded,world,material)
                if not(ok and loaded)then lost='icon material '..material;break end
            end
        end
        if lost then
            close_screen(self)
            note(self,'waiting','game icon resource unloaded: '..lost)
            local ok2,screen2,why2=pcall(M.hooks.open_screen,world,ui_world,M.MAX_LAYER)
            if not(ok2 and screen2)then note(self,'failed',ok2 and tostring(why2)or tostring(screen2));return end
            self.screen,self.ui_world,self.drawn=screen2,ui_world,{}
            self.opened=self.opened+1
        end
    end
    -- A game font in use that unloaded (a language switch): close the GUI first (its material instances name the
    -- font's atlas), so nothing keeps sampling a texture that is gone; the frame below draws without it.
    local font_ready={}
    local function game_font_ready(font)
        local r=font_ready[font.key]
        if r==nil then
            local ok,ready,why=pcall(M.hooks.game_font_ready,world,font)
            r={ok=ok and ready==true,why=ok and why or tostring(ready)}
            font_ready[font.key]=r
        end
        return r.ok,r.why
    end
    if self.text_fonts then
        local lost
        for _,font in pairs(self.text_fonts)do
            if not game_font_ready(font)then lost=font.key;break end
        end
        if lost then
            close_screen(self)
            note(self,'waiting','game font unloaded: '..lost)
            local ok2,screen2,why2=pcall(M.hooks.open_screen,world,ui_world,M.MAX_LAYER)
            if not(ok2 and screen2)then note(self,'failed',ok2 and tostring(why2)or tostring(screen2));return end
            self.screen,self.ui_world,self.drawn=screen2,ui_world,{}
            self.opened=self.opened+1
        end
    end
    local screen=self.screen
    self.width,self.height=screen.width,screen.height
    self.scale=math.min(screen.width/1920,screen.height/1080)
    self.coloured=self.coloured or{}
    self.ready=self.ready or{}
    local function image_ready(handle)
        local r=self.ready[handle]
        if r and(r.ok or self.frames-r.frame<60)then return r.ok,r.why end
        local ok,result,why=pcall(M.hooks.image_ready,world,handle)
        r={ok=ok and result==true,why=ok and why or tostring(result),frame=self.frames}
        self.ready[handle]=r
        return r.ok,r.why
    end
    self.icons=self.icons or{}
    -- A game icon's needs (runtime/game_icons.lua resolve): kept 30 frames once resolved, retried every 60 frames when
    -- not (the page itself is checked every frame below).
    local function icon_ready(handle)
        local r=self.icons[handle]
        if r and self.frames-r.frame<(r.spec and 30 or 60)then return r.spec,r.why end
        local ok,spec,why=pcall(M.hooks.game_icon,world,handle)
        r={spec=ok and spec or nil,why=ok and why or tostring(spec),frame=self.frames}
        self.icons[handle]=r
        return r.spec,r.why
    end
    local carrier_cache={}
    local function carrier_ok(material)
        local c=carrier_cache[material]
        if c==nil then
            local ok,loaded=pcall(M.hooks.material_loaded,world,material)
            c=ok and loaded==true
            carrier_cache[material]=c
        end
        return c
    end
    -- The game fonts loaded now (asked once a frame, and only when a text has a character its role font lacks).
    local extra
    local function extra_fonts()
        if extra==nil then
            local ok,list=pcall(M.hooks.game_fonts,world)
            extra=ok and type(list)=='table'and list or false
        end
        return extra or nil
    end
    self.world_ref=world
    local d=setmetatable({items={},layer=self.layer,width=screen.width,height=screen.height,scale=self.scale,
        materials={},image_ready=image_ready,icon_ready=icon_ready,extra_fonts=extra_fonts,
        want_fonts=function(font,text,list)pcall(M.hooks.want_fonts,world,font,text,list)end,
        fonts={},refused=0,font_for=function(role)return M.hooks.font(world,role)end},Builder)
    local ok,err=xpcall(self.draw_fn,function(e)return debug.traceback(tostring(e),2)end,d,dt)
    if not ok then
        -- The mod's failure: nothing stale stays on screen; the frame callback records and logs it.
        close_screen(self)
        note(self,'error','the draw function raised')
        error(err,0)
    end
    -- Game icons: a material each, and every page proven loaded this frame (set_texture names only those).
    local image_pool
    for _,item in ipairs(d.items)do
        if item.kind=='uvbitmap'and item.pool=='image'then
            local ok,pool=pcall(M.hooks.image_materials,world)
            image_pool=ok and pool or nil
            break
        end
    end
    local items,dropped=assign_materials(self,d.items,carrier_ok,image_pool)
    if dropped>0 then refuse(d,'no free icon material for '..dropped..' game icon(s)')end
    local pages,materials,page_ok,shown,text_fonts={},{},{},{},{}
    for _,item in ipairs(items)do
        if item.kind=='uvbitmap'then
            if page_ok[item.page]==nil then
                local ok,loaded=pcall(M.hooks.page_loaded,world,item.page)
                page_ok[item.page]=ok and loaded==true
            end
            item.page_ok=page_ok[item.page]
            if item.page_ok then
                pages[item.page]=true
                materials[item.material]=true
                shown[#shown+1]=item
            else
                -- never drawn without its page (the material alone shows the game's placeholder)
                d.waiting_images=(d.waiting_images or 0)+1
                d.image_why='its atlas page is not loaded'
                self.icons[item.icon]=nil
            end
        elseif item.kind=='text'and item.game then
            -- a game font run: drawn only when its font, atlas and material are proven loaded this frame (a font that
            -- is not loaded must never reach Gui.text: the engine does not check, research game-font-text)
            local ready,why=game_font_ready(item.game)
            if ready then
                item.font_ok=true
                text_fonts[item.game.key]=item.game
                shown[#shown+1]=item
            else
                d.waiting_text=(d.waiting_text or 0)+1
                d.text_why=why
            end
        else shown[#shown+1]=item end
    end
    d.items=shown
    self.icon_pages=next(pages)and pages or nil
    self.icon_materials=next(materials)and materials or nil
    self.text_fonts=next(text_fonts)and text_fonts or nil
    self.waiting_text,self.text_why=d.waiting_text or 0,d.text_why
    self.refused,self.first_refusal=d.refused,d.first_refusal
    self.waiting_images,self.image_why=d.waiting_images or 0,d.image_why
    local passed,drawn,calls=engine_gui.temp_scope(reconcile_and_colour,screen,self.drawn,d.items,self.coloured)
    if not(passed and drawn)then
        close_screen(self)
        note(self,'failed','engine GUI call failed: '..tostring(passed and calls or drawn))
        return
    end
    self.drawn=drawn
    self.frames=self.frames+1
    self.calls=self.calls+calls
    note(self,'drawing',d.first_refusal and('refused: '..d.first_refusal)or nil)
end

-- Sets the draw function: fn(d, dt) is called every frame while the overlay is shown and describes the whole frame.
function Overlay:draw(fn)
    assert(type(fn)=='function','overlay:draw needs a function(d, dt)')
    if self.state=='closed'then return nil,'the overlay is closed'end
    self.draw_fn=fn
    return self
end
function Overlay:show(on)
    if self.state=='closed'then return self end
    self.visible=on~=false
    if self.ticker and self.ticker.state=='disabled'and self.visible then self.ticker:enable()end
    return self
end
function Overlay:hide()
    if self.cursor then cursor.release(self.key)end
    return self:show(false)
end
-- While the overlay is shown, free the mouse cursor from the camera (EXPERIMENTAL; runtime/mod_cursor.lua): the engine
-- shows it, stops clipping it and drops the mouse focus. opts = {camera = false} keeps the mouse focus (the cursor is
-- shown but the camera may still turn). free_cursor(false) gives it back.
function Overlay:free_cursor(on,opts)
    if on==false then
        if self.cursor then cursor.release(self.key)end
        self.cursor=nil
    else
        self.cursor={camera=not(type(opts)=='table'and opts.camera==false)}
    end
    return self
end
function Overlay:visible_now()return self.visible==true and self.state=='drawing'end
-- The cursor in overlay coordinates {x, y (top-left origin), left (left button held)}, or nil and why.
function Overlay:mouse()
    local m,why=M.hooks.mouse()
    if not m then return nil,why end
    if not(self.width and self.height)then return nil,'the overlay has not drawn yet'end
    return {x=m.x*self.width/m.w,y=m.y*self.height/m.h,left=m.left}
end
function Overlay:text_width(text,size,role)
    local font=metrics_font()
    if role~='mono'then
        local own=font_data.fonts[role or'body']
        if own then font=own end
    end
    -- the game fonts loaded at the last frame's world (none before the first frame)
    local extra
    if self.world_ref then
        local ok,list=pcall(M.hooks.game_fonts,self.world_ref)
        extra=ok and type(list)=='table'and list or nil
    end
    return ui_fonts.measure(font,tostring(text),size or 18,extra)
end
-- Removes the overlay: its primitives, its GUI and its frame callback.
function Overlay:close()
    if self.state=='closed'then return self end
    if self.ticker then self.ticker:cancel()end
    if self.cursor then cursor.release(self.key)end
    close_screen(self)
    self.state,self.reason='closed',nil
    overlays[self.key]=nil
    return self
end
function Overlay:status()
    return {owner=self.owner,id=self.id,state=self.state,reason=self.reason,layer=self.layer,visible=self.visible,
        width=self.width,height=self.height,scale=self.scale,items=#self.drawn,frames=self.frames,
        engine_calls=self.calls,opened=self.opened,refused=self.refused,first_refusal=self.first_refusal,
        waiting_images=self.waiting_images or 0,image_reason=self.image_why,callback=self.ticker and self.ticker.state,
        cursor=self.cursor and(self.cursor_reason or'free')or nil,game_fonts=self:game_fonts_in_use(),
        waiting_text=self.waiting_text or 0,text_reason=self.text_why or(self.coloured and self.coloured.text_reason)}
end
-- The keys of the game fonts this overlay drew text in last frame (sorted).
function Overlay:game_fonts_in_use()
    local out={}
    for key in pairs(self.text_fonts or{})do out[#out+1]=key end
    table.sort(out)
    return out
end

-- The overlay `opts.id` (default 'main') of `owner`, created on first use; the same object afterwards (its layer
-- follows the latest opts). opts: {id, layer = the band's base (1..1023, default 1011), visible = true}.
function M.open(owner,opts)
    opts=opts or{}
    assert(type(owner)=='string'and owner~='unknown','hd2.ui.overlay() cannot tell which mod is calling: call it '
        ..'from your mod, or pass {owner = "mods/author/name"}')
    local id=opts.id or'main'
    assert(type(id)=='string'and id:match('^[%w_%.%-]+$')and#id<=48,'overlay id must be 1 to 48 letters, digits, _ . -')
    local layer=opts.layer or M.DEFAULT_LAYER
    assert(type(layer)=='number'and layer%1==0 and layer>=1 and layer<=M.MAX_LAYER,
        'overlay layer must be an integer from 1 to '..M.MAX_LAYER)
    local key=owner..'|'..id
    local self=overlays[key]
    if self then
        self.layer=layer
        if opts.visible~=nil then self.visible=opts.visible~=false end
        return self
    end
    self=setmetatable({owner=owner,id=id,key=key,layer=layer,visible=opts.visible~=false,state='waiting',drawn={},
        frames=0,calls=0,opened=0,refused=0},Overlay)
    self.ticker=events.frame(function(dt)return frame(self,dt)end,{owner=owner,id='hd2runtime.overlay.'..id})
    if self.ticker.state=='rejected'then error('overlay rejected: '..tostring(self.ticker.reason),2)end
    overlays[key]=self
    return self
end
function M.list()
    local out={}
    for _,o in pairs(overlays)do out[#out+1]=o:status()end
    table.sort(out,function(a,b)return a.owner..a.id<b.owner..b.id end)
    return out
end
-- Whether every character of text can be drawn now in a font role (default 'body'): the role's font, or a game
-- language font loaded now. Returns true, or false, the number of distinct characters that would show as '?' and up
-- to three of them. Without a proven game process only the role's own font counts.
function M.can_draw(text,role)
    role=role or'body'
    local runtime=M.hooks.runtime()
    local world=runtime and{runtime=runtime}
    local font
    if world then
        local ok,f=pcall(M.hooks.font,world,role)
        font=ok and f or nil
    end
    font=font or(role~='mono'and font_data.fonts[role])or font_data.fonts.monaco
    local extra={}
    if world then
        local ok,list=pcall(M.hooks.game_fonts,world)
        if ok and type(list)=='table'then extra=list end
        -- asking is enough to start loading the font it needs (it draws, and can_draw says so, once loaded)
        pcall(M.hooks.want_fonts,world,font,tostring(text),extra)
    end
    return ui_fonts.drawable(font,tostring(text),extra)
end
-- The game's language fonts the overlay can draw with and whether each is loaded now: {key, label, languages (the
-- game language codes that load it), glyphs, resident, reason}.
function M.game_fonts()
    local runtime,why=M.hooks.runtime()
    local world=runtime and{runtime=runtime}
    local out={}
    for _,entry in ipairs(ui_fonts.GAME)do
        local ready,reason=false,why
        if world then
            local ok,r,w=pcall(M.hooks.game_font_ready,world,{key=entry.key,game=entry})
            ready,reason=ok and r==true,ok and w or r
        end
        out[#out+1]={key=entry.key,label=entry.label,languages=entry.languages,glyphs=entry.glyphs,resident=ready,
            reason=not ready and tostring(reason)or nil}
    end
    return out
end
function M.reset_for_tests()
    for _,o in pairs(overlays)do pcall(o.close,o)end
    overlays={}
end
return M
