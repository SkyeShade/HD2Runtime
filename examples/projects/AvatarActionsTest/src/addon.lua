local hd2=require('mods/skyeshade/hd2runtime')
-- Live test for hd2.actions.heal_limb / heal_limbs / add_velocity (docs/event-scripting.md, limb heals and velocity;
-- docs/research/player-avatar-actions-F5FEE03DCFDB.md). Everything acts on YOUR OWN avatar only (no host needed).
--   * Limb heals use the game's own zone restore: the limb returns to full and an injured limb is healed; main
--     health is unchanged.
--   * Velocity kicks use the game's own movement velocity setter: your current velocity plus the kick.
-- Keys (Ctrl+Alt):
--   F1 head, F2 chest, F3 left arm, F4 right arm, F5 left leg, F6 right leg: heal that limb
--   F7 heal every limb
--   F8 upward kick (+8 m/s up)
--   F9 forward kick (+6 m/s along the way you were last moving, +4 m/s up)
-- Injure limbs first with LimbInjuryTest (Alt+F7 / Alt+F8) or by taking damage. Every line carries the banner.
local BANNER='AVATAR ACTIONS 0.1.0 BUILD'
assert(hd2.actions and hd2.actions.heal_limb and hd2.actions.add_velocity,
    'AvatarActionsTest needs an HD2Runtime build with hd2.actions.heal_limb and add_velocity')
local mod=hd2.mod()

local function report(what,action)
    if action:requested()then
        local detail=action.limb and(' ('..action.limb..' / '..action.zone..', zone health before '
            ..tostring(action.zone_health)..(action.injured_before and', was injured'or'')..')')
            or action.healed and(' ('..table.concat(action.healed,', ')..')')
            or action.after and(' (velocity now '..tostring(action.after)..')')or''
        mod:log(BANNER..': '..what..' requested'..detail)
    else
        mod:log(BANNER..': '..what..' refused: '..tostring(action.code)..': '..tostring(action.reason))
    end
end
local function me()
    local player=hd2.local_player()
    if not player then mod:log(BANNER..': no local player')end
    return player
end

for index,limb in ipairs({'head','chest','l_hand','r_hand','l_knee','r_knee'})do
    hd2.input.bind('avatar_actions_test.heal_'..limb,{key='Ctrl+Alt+F'..index,on_press=function()
        local player=me()
        if player then report('heal '..limb,hd2.actions.heal_limb(player,limb,'full'))end
    end})
end
hd2.input.bind('avatar_actions_test.heal_all',{key='Ctrl+Alt+F7',on_press=function()
    local player=me()
    if player then report('heal all limbs',hd2.actions.heal_limbs(player))end
end})
hd2.input.bind('avatar_actions_test.up',{key='Ctrl+Alt+F8',on_press=function()
    local player=me()
    if player then report('upward kick',hd2.actions.add_velocity(player,{x=0,y=0,z=8}))end
end})

-- "Forward": the way the avatar moved over the last half second (public positions only); +Y when standing still.
local last,heading=nil,{x=0,y=1}
hd2.every(0.5,function()
    local player=hd2.local_player()
    local p=player and player:position()
    if p and last then
        local dx,dy=p.x-last.x,p.y-last.y
        local length=math.sqrt(dx*dx+dy*dy)
        if length>0.2 then heading={x=dx/length,y=dy/length}end
    end
    last=p
end,{scope='session'})
hd2.input.bind('avatar_actions_test.forward',{key='Ctrl+Alt+F9',on_press=function()
    local player=me()
    if player then
        report('forward kick',hd2.actions.add_velocity(player,{x=6*heading.x,y=6*heading.y,z=4}))
    end
end})

mod:log(BANNER..': loaded; in a mission press Ctrl+Alt+F1..F6 to heal a limb, F7 all limbs, F8 upward kick, '
    ..'F9 forward kick')
