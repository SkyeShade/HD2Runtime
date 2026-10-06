-- hd2.sounds: the weapon firing-sound catalogue, read-only (docs/weapon-sounds.md; runtime/weapon_sounds.lua).
--
-- Every firing sound of this build that a weapon type posts and a Wwise bank defines, by its semantic name
-- (`<family>/<weapon>[/<part>]`). What a mod sees: {name, label, kind ('shot' | 'loop'), family, stratagem (the
-- stratagem whose call-in package provides its bank, or nil), resident_only (true: no stratagem provides it; usable only
-- while the game has its package resident), designed_rpm, range_m (how far its farthest layer carries, a heuristic
-- reading of its bank), midi, pelican_default (the Pelican chin gun's own sound)}. No event, bank or package id is
-- returned or accepted. A name is what hd2.pelican.spawn{gun = {sound = name}} and a custom stratagem's pelican.gun.sound
-- take.
local sounds=require('hd2runtime/runtime/weapon_sounds')
local M={}

-- hd2.sounds.list(filter): the entries (sorted by name). filter: nil (all), a family ('sentry', 'vehicle', 'support',
-- 'primary', 'secondary', 'emplacement', 'eagle', 'backpack', 'pelican', 'automaton', 'illuminate', ...) or a table
-- {family, kind = 'shot' | 'loop', stratagem = true (any) | a stratagem name, resident_only = boolean, text = a part
-- of the name or label}. An invalid filter raises an error naming it.
function M.list(filter)
    local out,why=sounds.list(filter)
    if not out then error('hd2.sounds.list: '..tostring(why),2)end
    return out
end
-- hd2.sounds.describe(name): one entry (by name, or an older alias such as 'maelstrom_main_gun'), or nil.
function M.describe(name)return sounds.describe(name)end
return M
