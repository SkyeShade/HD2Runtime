-- hd2.ui: mod screen overlays (runtime/mod_overlay.lua; docs/ui-overlay.md). Exported without wrappers: the calling
-- mod owns each overlay (stack level 2 is its frame).
local events=require('hd2runtime/runtime/events')
local overlays=require('hd2runtime/runtime/mod_overlay')
local M={}
-- hd2.ui.overlay(opts): the calling mod's overlay opts.id (default 'main'), created on first use and the same object
-- afterwards. opts: {id, layer = the band's base layer (1..1023, default 1011), visible = true, owner}. Then
-- overlay:draw(function(d, dt) d:rect(...); d:text(...) end) describes every frame.
function M.overlay(opts)
    if opts~=nil and type(opts)~='table'then error('hd2.ui.overlay takes an options table or nothing',2)end
    local explicit=opts and opts.owner
    if explicit~=nil and(type(explicit)~='string'or#explicit==0 or#explicit>128 or explicit:find('[%c]'))then
        error('owner must be a mod id string',2)
    end
    local owner=events.owner(explicit,2)
    return overlays.open(owner,opts)
end
-- Every overlay's status (owner, id, state, reason, items, frames, ...).
function M.overlays()return overlays.list()end
-- The cursor capture's state (runtime/mod_cursor.lua): holders, the game's saved values, what the engine reports now.
function M.cursor()return require('hd2runtime/runtime/mod_cursor').status()end
-- A colour as the overlay takes it ({r, g, b[, a]} or '#RRGGBB[AA]') -> {r, g, b, a}, or nil when invalid.
function M.colour(c)
    local engine=overlays.colour(c)
    return engine and{engine[2],engine[3],engine[4],engine[1]}or nil
end
M.color=M.colour
-- Whether every character of text can be drawn now in a font role ('body' default, 'title', 'mono'): the role's font
-- or one of the game's language fonts loaded now (docs/ui-overlay.md "Other scripts"). true, or false, the number of
-- distinct characters that would show as '?' and up to three of them.
function M.can_draw(text,font)
    if type(text)~='string'and type(text)~='number'then error('hd2.ui.can_draw takes a string',2)end
    if font~=nil and not overlays.FONT_ROLES[font]then error("font must be 'body', 'title' or 'mono'",2)end
    return overlays.can_draw(tostring(text),font)
end
-- The game's language fonts overlays draw with: {key, label, languages, glyphs, resident, reason}.
function M.game_fonts()return overlays.game_fonts()end
-- The layer range an overlay may use and the default base.
M.MAX_LAYER=overlays.MAX_LAYER
M.DEFAULT_LAYER=overlays.DEFAULT_LAYER
return M
