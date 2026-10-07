-- CarrierSlotProbe 0.3.0: the carrier-in-slot probe (development; docs/custom-stratagem-api.md, "selection =
-- 'carrier' (probe)"). One custom stratagem, an Orbital Gas Barrage, whose loadout slot holds its CARRIER itself
-- instead of the Orbital Precision Strike token. Solo host only. What it answers: the slot holds the carrier from the
-- pick on (no conversion in the mission), the presentation lands before the HUD builds (no Precision Strike flash),
-- the slot is locked until it is ready to call, its 3 uses are the game's own per-slot uses (the HUD counter), its
-- carrier is never locked out of the native picker (0.2.1) and stays pickable in the other slots, the custom slot
-- moving to its next carrier, or swapped at the launch when it could not move in time (0.3.0).
local hd2=require('mods/skyeshade/hd2runtime')
local mod=hd2.mod()
local BUILD='0.3.0 CARRIER SLOT DOUBLES PROBE BUILD'
mod:log('CarrierSlotProbe '..BUILD..': solo, select Carrier Slot Probe in the custom panel, then a mission; call it '
    ..'with UP DOWN UP DOWN LEFT RIGHT LEFT. The log lines CARRIER-IN-SLOT PROBE show the timing.')

hd2.custom_stratagem.register({
    id='carrier_slot_probe',
    name='CARRIER SLOT PROBE',
    name_cased='Carrier Slot Probe',
    description='Development probe: an Orbital Gas Barrage whose loadout slot holds its carrier itself. 3 uses per '
        ..'mission, 45 s cooldown.',
    icon=hd2.resources.image('carrier_slot_probe'),
    code={'up','down','up','down','left','right','left'},
    cooldown=45,
    uses=3,
    traits={'Orbital','Probe'},
    carrier={beacon='offensive',prefer_families={'orbital'}},
    -- The 120mm's own barrage; each of its shells takes the Gas Strike's explosion (the live-proven native barrage).
    orbital={native=true,pattern='Orbital 120mm HE Barrage',impact_explosion='Orbital Gas Strike'},
    -- The probe: the loadout slot holds the carrier itself.
    selection='carrier',
})
