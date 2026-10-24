local hd2=require('mods/skyeshade/hd2runtime')
-- Needs the development Runtime with docs/homing-lock-on.md, not stock 0.40.0.
-- Offline integration example; this exact Runtime package has not been live-tested.
local gun=hd2.projectiles.homing('AR-23 Liberator',{
    acquisition='pre_fire',lock_time=.3,max_targets=3,
    cone=12,range=100,arm_distance=0,require_los=true,require_aim=true,
    lateral_acceleration=600,turn_rate=1440,
})
if gun.status~='active'then
    hd2.mod():log('HomingLockOn requires the pre-fire extension: '..tostring(gun.reason))
    return
end
local hud=gun:reticle({marker_shape='corners',marker_size=12,ring_width=1.5,
    acquiring_color='#FFB420',locked_color='#40FF60',aim_only=true})
-- Appearance only, e.g. from your mod's own settings callback:
-- hud:style({marker_shape='cross',locked_color='#00CCFF',show_labels=false})
-- hud:hide() / hud:show() / hud:stop() do not reset locks or flying rounds.
-- A custom renderer can instead inspect gun:lock_state(), checking ui_visible.
-- gun:stop() also destroys this HUD and cancels its callback.
