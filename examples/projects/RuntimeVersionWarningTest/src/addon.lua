local hd2=require('mods/skyeshade/hd2runtime')
-- Live test: this mod declares requires.hd2runtime.min_version = 0.29.0, newer than the installed HD2Runtime, so it
-- never reaches this line. Its SDK wrapper reports the requirement to HD2Runtime (hd2.compatibility) and then fails
-- closed, as every too-new mod does. HD2Runtime logs the mod and, once the player has been on the ship for a few
-- seconds, shows one "HD2Runtime update required" message box for every such mod together.
assert(hd2.version,'unreachable: the wrapper refuses this mod before it runs')
return true
