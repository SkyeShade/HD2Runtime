-- Text in the Runtime's own panels in the game's language fonts (0.31.0, issue #8): the custom stratagem panel and its
-- details, and the alert card, draw their text straight on an engine GUI (runtime/engine_gui.lua). This gives them the
-- technique the mod overlay uses (runtime/mod_overlay.lua, live-proven 2026-10-09): text the role font fully covers is
-- one engine text, exactly as before; otherwise it is split into runs (runtime/ui_fonts.lua runs) and a character the
-- role font lacks is drawn in a loaded game font that has it (named by its hash, through its Runtime material, whose
-- instance in this GUI is pointed at the font's atlas), on the role font's baseline. A text with characters no loaded
-- font has asks for the game font package that has them (ui_fonts.want); until it is loaded they show '?'.
--
-- Safety, as the overlay's: a game font run is drawn only after its font, atlas and material are proven loaded in the
-- same frame (ui_fonts.game_font_ready); the engine is never handed a font that is not. A GUI that drew game font
-- text must call M.still_ready every frame it stays on screen and close (and redraw) itself when that fails: a
-- language switch unloads the font under it.
local fonts=require('hd2runtime/runtime/ui_fonts')
local M={}

-- Where the role font's glyphs land below the y the engine is given (a fraction of the size): the Runtime's FS
-- Sinclair fonts the live-calibrated overlay drop, monaco and the game fonts their measured one.
local function drop_of(font)
    if type(font.name)=='string'and font.name:find('^hd2runtime_fonts/')then
        local ok,overlay=pcall(require,'hd2runtime/runtime/mod_overlay')
        return ok and overlay.TEXT_DROP or 0
    end
    return font.drop or 0
end

-- One per GUI: the runtime the fonts are read from, the game fonts its text uses, and the atlas each of its material
-- instances was pointed at.
function M.context(runtime)return {runtime=runtime,used={},textured={}}end

-- The loaded game fonts (the overlay's list, proven at most a second ago).
local function extra(ctx)
    local ok,list=pcall(fonts.resident_game_fonts,ctx.runtime)
    return ok and type(list)=='table'and list or{}
end
-- The width of s at size in `font` as M.text draws it.
function M.width(ctx,font,s,size)
    if fonts.has(font,s)then return fonts.width(font,s,size)end
    return fonts.measure(font,s,size,extra(ctx))
end
-- Lines no wider than width (ui_fonts.wrap: at spaces and between CJK characters), measured as M.text draws them.
function M.wrap(ctx,font,s,size,width,lines)
    if fonts.has(font,s)then return fonts.wrap(font,s,size,width,lines)end
    return fonts.wrap(font,s,size,width,lines,extra(ctx))
end

-- Draws s like screen.text(s, font.name, size, font.name, x, y, layer, colour) (y the engine's baseline for `font`).
-- Returns the first engine text's id, or nil (the screen's refusal) like screen.text.
function M.text(ctx,screen,s,font,size,x,y,layer,colour)
    if fonts.has(font,s)then return screen.text(s,font.name,size,font.name,x,y,layer,colour)end
    local list=extra(ctx)
    pcall(fonts.want,ctx.runtime,font,s,list)
    local runs=fonts.runs(font,s,list)
    local visual=y-drop_of(font)*size
    local pen,first=x,nil
    for _,run in ipairs(runs)do
        local f=run.font
        local id
        if f.game and fonts.game_font_ready(ctx.runtime,f.game)then
            id=screen.text(run.text,f.name,size,f.material,pen,visual+drop_of(f)*size,layer,colour)
            if id~=nil then
                ctx.used[f.key]=f.game
                if ctx.textured[f.material]~=f.atlas then
                    -- this GUI's instance of the font's material (made by the text just drawn) samples its atlas
                    local instance=screen.material and screen.material(f.material)
                    local ok=instance and screen.set_texture(instance,'msdf_texture',f.atlas)
                    ctx.textured[f.material]=ok and f.atlas or false
                end
            end
        else
            -- the role font: its own characters, or '?' for a game font not loaded now
            id=screen.text(run.text,font.name,size,font.name,pen,y,layer,colour)
            f=font
        end
        if id==nil then return nil end
        first=first or id
        pen=pen+fonts.width(f,run.text,size)
    end
    return first
end

-- Whether every game font this GUI's text uses is still loaded: true, or false and the font's key.
function M.still_ready(ctx)
    for key,entry in pairs(ctx and ctx.used or{})do
        local ok,ready=pcall(fonts.game_font_ready,ctx.runtime,entry)
        if not(ok and ready)then return false,key end
    end
    return true
end
return M
