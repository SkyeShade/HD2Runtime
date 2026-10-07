local hd2=require('mods/skyeshade/hd2runtime')
-- Live test for hd2.actions.injure (docs/event-scripting.md#limb-injuries,
-- research/docs/player-injury-path-F5FEE03DCFDB.md). Runtime queues damage at one limb of YOUR OWN avatar through the
-- game's own damage request, with the template of the game's own VG-70 Variable self-damage (its third fire mode
-- hurts the shooter's right shoulder the same way). The game applies it later in the frame like any hit on that
-- limb: the limb's zone loses the damage (arms 35, legs 45, chest 60, head 85) and main health loses its share.
-- No host needed: each machine injures only the avatar it owns.
--
-- What to check, in a mission:
--   * every shot you fire costs your right arm 2 per shot (at most 35 at once): after about 18 shots the right arm
--     is injured: the HUD shows it, your aim sways; a stim heals it;
--   * Alt+F7: injures the right arm at once (r_hand 35);
--   * Alt+F8: injures the left leg at once (l_knee 45): you limp;
--   * Alt+F9: 10 damage to the head (no HUD indicator; main health drops by 15).
-- Every request and refusal is logged with this banner.
local BANNER='LIMB INJURY 0.1.0 BUILD'
assert(hd2.actions and hd2.actions.injure,'LimbInjuryTest needs an HD2Runtime build with hd2.actions.injure')
local mod=hd2.mod()
local PER_SHOT,ARM=2,35

local function report(what,action)
    if action:requested()then
        mod:log(BANNER..': '..what..' requested ('..action.limb..' / '..action.zone..' -'..action.damage
            ..', zone health before '..tostring(action.zone_health)
            ..(action.injured_before and', already injured'or'')..')')
    else
        mod:log(BANNER..': '..what..' refused: '..tostring(action.code)..': '..tostring(action.reason))
    end
end
local function injure(what,limb,damage)
    local player=hd2.local_player()
    if not player then mod:log(BANNER..': '..what..': no local player');return end
    report(what,hd2.actions.injure(player,limb,damage))
end

hd2.events.on('player_fired',function(event)
    injure(event.shots..' shot(s)','r_hand',math.min(ARM,PER_SHOT*event.shots))
end,{id='arm_per_shot'})
hd2.input.bind('limb_injury_test.arm',{key='Alt+F7',on_press=function()injure('Alt+F7 right arm','r_hand',35)end})
hd2.input.bind('limb_injury_test.leg',{key='Alt+F8',on_press=function()injure('Alt+F8 left leg','l_knee',45)end})
hd2.input.bind('limb_injury_test.head',{key='Alt+F9',on_press=function()injure('Alt+F9 head','head',10)end})

local limbs={}
for _,limb in ipairs(hd2.actions.limbs())do limbs[#limbs+1]=limb.name..'='..limb.zone..':'..limb.max_damage end
mod:log(BANNER..': loaded (limbs '..table.concat(limbs,', ')..'); fire a weapon in a mission, or press Alt+F7 / '
    ..'Alt+F8 / Alt+F9')
