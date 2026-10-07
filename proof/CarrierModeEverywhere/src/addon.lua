-- CarrierModeEverywhere 0.1.0: a development test switch (2026-10-07). While installed, every custom stratagem of every
-- installed mod that does not name its selection takes the carrier-in-slot mode (its loadout slot holds its CARRIER
-- itself, not the Orbital Precision Strike token): one session shows which kinds work in that mode and which fail.
-- docs/custom-stratagem-api.md, "The carrier-mode switch". Remove it to get the token back.
local hd2=require('mods/skyeshade/hd2runtime')
local mod=hd2.mod()
local BUILD='0.1.0 CARRIER MODE EVERYWHERE TEST BUILD'
mod:log('CarrierModeEverywhere '..BUILD..': every custom stratagem without its own selection now picks its CARRIER '
    ..'into the slot. Re-pick your custom slots. Every player of a lobby needs this mod too (the registry hash).')
hd2.custom_stratagem.carrier_mode_all(true)
