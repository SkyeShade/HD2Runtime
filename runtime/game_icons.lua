-- The game's own HUD icons for mod overlays (hd2.resources.game_icon; docs/game-icons.md). Read-only: nothing is
-- written to game memory or game files, and no game resource is loaded, created or replaced.
--
-- Every stratagem and booster HUD icon is a sprite of a texture_atlas page the game keeps loaded (domains/hud_icons.lua
-- names each one; the names only). A screen GUI draws a MATERIAL, never a texture or a sprite (research bitmapContract),
-- so an icon is drawn as GameIconProbe 0.1.0 proved live:
--   * a vanilla stratagem icon material (each named by its stratagem's icon, exactly the sprite name; loaded with the
--     sprite) gets this GUI's own instance by a bitmap of it; the game's UI keeps its own instance untouched;
--   * Material.set_texture(instance, 'diffuse_map', page) points that instance at the sprite's atlas page (exe 0x4A0460;
--     the icon material's one slot is murmur64('diffuse_map') >> 32);
--   * Gui.bitmap_uv draws the sprite's rectangle of the page (exe 0x3E2F10: uv00 = (u, v) is the top-left).
-- A stratagem's icon uses its own material; a booster (no icon material of its own) and a second colour set of one
-- stratagem in one overlay borrow a CARRIER: another stratagem's icon material this overlay does not use this frame.
-- The sprite record (page and rectangle) is read from the running game's atlas sprite map every time it is resolved
-- (runtime/image_resources.lua atlas_sprite), never assumed: an icon whose sprite or page is not loaded (booster icons
-- during a mission) is not drawn.
local D=require('hd2runtime/domains/hud_icons')
local images=require('hd2runtime/runtime/image_resources')
local M={}
M.KINDS={stratagem='stratagems',booster='boosters'}

local Icon={}
local IconMeta={__index=Icon,__tostring=function(self)return'game icon '..self.kind..': '..self.name end}
local identities=setmetatable({},{__mode='k'})
local issued={}
-- The handle of one game icon by kind ('stratagem' | 'booster') and its name (as the Runtime's catalogues name it:
-- 'EXO-45 Patriot Exosuit', 'Vitality Enhancement'); the same handle every time. nil, code and reason otherwise.
function M.handle(kind,name)
    local list=M.KINDS[kind]
    if not list then return nil,'UNKNOWN_KIND','game icons are of kind "stratagem" or "booster", not '..tostring(kind)end
    if type(name)~='string'then return nil,'UNKNOWN_ICON','a game icon is named by a string'end
    local key=kind..'|'..name
    if issued[key]then return issued[key]end
    local sprite=D[list][name]
    if not sprite then
        local why=D.missing[name]
        return nil,'UNKNOWN_ICON',why and(name..': the game has no HUD icon for it ('..why..')')
            or(name..' is not a '..kind..' with a HUD icon (hd2.resources.game_icons("'..kind..'") lists them)')
    end
    local handle=setmetatable({kind=kind,name=name},IconMeta)
    identities[handle]={kind=kind,name=name,sprite=sprite,high=tonumber(sprite:sub(1,8),16),
        low=tonumber(sprite:sub(9,16),16)}
    issued[key]=handle
    return handle
end
function M.issued(value)return type(value)=='table'and identities[value]~=nil end
-- {kind, name, sprite ('%016X'), high, low} of a handle.
function M.identity(handle)return assert(identities[handle],'not a game icon from hd2.resources.game_icon')end
-- The names of every icon of a kind, sorted.
function M.names(kind)
    local list=assert(M.KINDS[kind],'game icons are of kind "stratagem" or "booster"')
    local out={}
    for name in pairs(D[list])do out[#out+1]=name end
    table.sort(out)
    return out
end
-- The stratagem icon materials a booster or a second colour set may borrow, sorted (stable carrier choices).
local carriers
function M.carriers()
    if not carriers then
        carriers={}
        for _,sprite in pairs(D.stratagems)do carriers[#carriers+1]=sprite end
        table.sort(carriers)
    end
    return carriers
end

-- What drawing a handle needs now, read from the running game: {sprite, page, uv = {u0, v0, u1, v1} (inset by half a
-- page pixel, so filtering never reaches a neighbouring sprite), own = the icon's own material ('%016X') or nil (a
-- booster)}, or nil and why. Read-only: the atlas sprite record, the page texture and (a stratagem) its icon material.
function M.resolve(runtime,handle)
    local id=M.identity(handle)
    local ok,s,why=pcall(images.atlas_sprite,runtime,id.high,id.low)
    if not ok then return nil,tostring(s)end
    if not s then return nil,why end
    local loaded,lwhy=M.page_loaded(runtime,s.page)
    if not loaded then return nil,'its atlas page is not loaded ('..tostring(lwhy)..')'end
    local own
    if id.kind=='stratagem'then
        local mok,material,mwhy=pcall(images.icon_material,runtime,id.high,id.low)
        if not(mok and material==true)then
            return nil,'its icon material is not loaded ('..tostring(mok and mwhy or material)..')'
        end
        own=id.sprite
    end
    local iu,iv=0.5/s.page_w,0.5/s.page_h
    return {sprite=id.sprite,page=s.page,own=own,w=s.w,h=s.h,uv={s.u+iu,s.v+iv,s.u+s.du-iu,s.v+s.dv-iv}}
end
-- Whether an atlas page texture ('%016X') is loaded: true, or false and why. Read-only.
function M.page_loaded(runtime,page)
    local ok,loaded,why=pcall(images.texture_loaded,runtime,tonumber(page:sub(1,8),16),tonumber(page:sub(9,16),16))
    if not ok then return false,tostring(loaded)end
    return loaded==true,why
end
-- Whether a stratagem icon material ('%016X') is loaded and exactly an icon material (a carrier must be): true, or
-- false and why. Read-only.
function M.material_loaded(runtime,material)
    local ok,loaded,why=pcall(images.icon_material,runtime,tonumber(material:sub(1,8),16),
        tonumber(material:sub(9,16),16))
    if not ok then return false,tostring(loaded)end
    return loaded==true,why
end
return M
