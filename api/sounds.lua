-- hd2.sounds: the weapon firing-sound catalogue, read-only (docs/weapon-sounds.md; runtime/weapon_sounds.lua).
--
-- Every firing sound of this build that a weapon type posts and a Wwise bank defines, by its semantic name
-- (`<family>/<weapon>[/<part>]`). What a mod sees: {name, label, kind ('shot' | 'loop'), family, stratagem (the
-- stratagem whose call-in package provides its bank, or nil), resident_only (true: no stratagem provides it; usable only
-- while the game has its package resident), designed_rpm, range_m (how far its farthest layer carries, a heuristic
-- reading of its bank), midi, pelican_default (the Pelican chin gun's own sound)}. No event, bank or package id is
-- returned by the catalogue. A name is what hd2.pelican.spawn{gun = {sound = name}}, a custom stratagem's
-- pelican.gun.sound and hd2.sounds.play take.
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

-- Playing sounds (runtime/sound_events.lua; docs/sounds.md). The calling mod owns each post (rate-limited per mod).
local events=require('hd2runtime/runtime/events')
local sound_events=require('hd2runtime/runtime/sound_events')
-- hd2.sounds.play(event, opts): posts a game sound event now. event: a catalogue name ('sentry/gatling' starts its
-- loop, a shot entry plays one shot), 'ui/<key>' (the loadout screen's own sounds: ui/stratagem_pick, ui/picker_close,
-- ui/slot_select, ui/generic_select, ui/item_hover_select), any Wwise event name, or {id = <32-bit event id>}.
-- opts: {position = {x, y, z} (a 3D sound at that world position; else the game world's own 2D source)}. The sound
-- plays on the game's mixer, so the game's volume settings apply. Its bank must be loaded: a catalogue sound's with
-- hd2.require_assets{targets = {hd2.sounds.asset(name)}}. Returns a handle (handle:stop()) or nil, code, reason.
function M.play(event,opts)
    local owner=events.owner(type(opts)=='table'and opts.owner or nil,2)
    return sound_events.play(owner,event,opts)
end
-- hd2.sounds.available(event): whether the sound engine knows the event now (its bank is loaded); nil and why when
-- that cannot be asked.
function M.available(event)return sound_events.available(event)end
-- hd2.sounds.asset(name): a catalogue sound as an asset target, for hd2.require_assets / hd2.asset_dependency (its
-- bank's package: the call-in package of the stratagem the catalogue names for it). Raises on an unknown name.
function M.asset(name)
    local canonical=sounds.resolve(name)
    if not canonical then error('hd2.sounds.asset: no firing sound '..tostring(name)..'; '..sounds.hint(),2)end
    return {resource='sound',sound=canonical}
end
-- hd2.sounds.name_for(id): a name the sound engine maps to a 32-bit event id (what play({id = id}) posts), or nil.
-- The first call for an id searches for about 40 ms; the result is cached for the session.
function M.name_for(id)return sound_events.name_for(id)end
return M
