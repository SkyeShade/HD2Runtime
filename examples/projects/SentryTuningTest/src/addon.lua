local hd2=require('mods/skyeshade/hd2runtime')
-- Live test for the sentry component fields (docs/stratagem-authoring.md "Sentry turret motion, targeting and weapon
-- handling", research/docs/sentry-components-F5FEE03DCFDB.md). Each field is a member of the sentry's OWN deployed
-- entity (its records have one owner each, so no allow_shared). It is a type-record write: every deployment of that
-- sentry on this machine uses it. Spread, recoil and the targeting ranges are copied into a sentry when it SPAWNS: set
-- them, then call the sentry in. The coupling, the yaw limits and the wind-up are read live.
-- Not yet shown in game: every new field needs allow_unverified_effect (targeting.range is live-proven and needs none).
--
-- What to check, in a mission (host; the log shows APPLIED for each enabled option):
--   * MG-43: bullets fan out about +-8.6 degrees (spread 10/10 -> 300/300 mrad);
--   * AC-8: holds its aim while firing (vertical recoil drift and climb 10 -> 0);
--   * AC-8: the barrel stays level until the sentry faces its target, then elevates (pitch/yaw coupling 1 -> 10);
--   * M-12: elevates while it is still turning (coupling 4 -> 0);
--   * G-16: the barrels take about 6 s to spin up (wind-up 0.5 -> 6 s); note whether the first shot waits;
--   * off by default, one at a time with a fresh MG-43: blind spots (side 10 m, rear 3 m), yaw limits +-30 degrees,
--     and the range control (75 -> 300 m: it should still not engage beyond about 100 m).
local BANNER='SENTRY TUNING 0.1.0 BUILD'
local mod=hd2.mod()
local options=hd2.options({id='sentry_tuning_test',title='Sentry Tuning Test'})
local spread=options:toggle({id='mg43_spread',label='MG-43: very wide spread',default=true,
    description='MG-43 horizontal and vertical spread 10 -> 300 mrad (bullets fan about +-8.6 degrees).'})
local recoil=options:toggle({id='ac8_recoil',label='AC-8: no vertical recoil',default=true,
    description='AC-8 vertical recoil drift and climb 10 -> 0: the aim no longer kicks up per shot.'})
local ac8_coupling=options:toggle({id='ac8_coupling',label='AC-8: turn first, then elevate',default=true,
    description='AC-8 pitch/yaw coupling 1 -> 10: the barrel barely elevates until the sentry faces its target.'})
local m12_coupling=options:toggle({id='m12_coupling',label='M-12: elevate while turning',default=true,
    description='M-12 Mortar pitch/yaw coupling 4 -> 0: pitch and yaw move together.'})
local windup=options:toggle({id='g16_windup',label='G-16: slow spin-up',default=true,
    description='G-16 Gatling wind-up 0.5 -> 6 s.'})
local blind=options:toggle({id='mg43_blind_spots',label='MG-43: blind flanks and rear',default=false,
    description='MG-43 side range -1 -> 10 m and rear range -1 -> 3 m (front stays 75 m). Turn the spread option off.'})
local limits=options:toggle({id='mg43_yaw_limits',label='MG-43: +-30 degree traverse',default=false,
    description='MG-43 yaw limits -180/180 -> -30/30 degrees (read live: also a standing MG-43).'})
local control=options:toggle({id='mg43_range_control',label='MG-43: range 300 m (control)',default=false,
    description='MG-43 targeting range 75 -> 300 m. Expected: still no engagement beyond about 100 m (the AI cut-off).'})
mod:log(BANNER..': MG-43 spread 10 -> 300 mrad, AC-8 vertical recoil 10 -> 0, AC-8 coupling 1 -> 10, M-12 coupling '
    ..'4 -> 0, G-16 wind-up 0.5 -> 6 s; off by default: MG-43 blind spots, yaw limits +-30, range 300 (MODS page '
    ..'"Sentry Tuning Test"; APPLIED lines follow; call each sentry in AFTER its options are set)')
local function sentry(name)return hd2.stratagem(name):deployed_entity()end
return {
    hd2.ensure({enabled=spread,transaction={id='sentry-mg43-spread',target=sentry('A/MG-43 Machine Gun Sentry'):weapon('primary'),
        allow_unverified_effect=true,changes={
        {field=hd2.fields.weapon.horizontal_spread,expect=10,value=300},
        {field=hd2.fields.weapon.vertical_spread,expect=10,value=300}}}}),
    hd2.ensure({enabled=recoil,transaction={id='sentry-ac8-recoil',target=sentry('A/AC-8 Autocannon Sentry'):weapon('primary'),
        allow_unverified_effect=true,changes={
        {field=hd2.fields.weapon.recoil_drift_vertical,expect=10,value=0},
        {field=hd2.fields.weapon.recoil_climb_vertical,expect=10,value=0}}}}),
    hd2.ensure({enabled=ac8_coupling,patch={id='sentry-ac8-coupling',target=sentry('A/AC-8 Autocannon Sentry'):turret(),
        allow_unverified_effect=true,field=hd2.fields.turret.pitch_yaw_coupling,expect=1,value=10}}),
    hd2.ensure({enabled=m12_coupling,patch={id='sentry-m12-coupling',target=sentry('A/M-12 Mortar Sentry'):turret(),
        allow_unverified_effect=true,field=hd2.fields.turret.pitch_yaw_coupling,expect=4,value=0}}),
    hd2.ensure({enabled=windup,patch={id='sentry-g16-windup',target=sentry('A/G-16 Gatling Sentry'):weapon('primary'),
        allow_unverified_effect=true,field=hd2.fields.windup.wind_up_seconds,expect=0.5,value=6}}),
    hd2.ensure({enabled=blind,transaction={id='sentry-mg43-blind-spots',
        target=sentry('A/MG-43 Machine Gun Sentry'):targeting(),allow_unverified_effect=true,changes={
        {field=hd2.fields.targeting.side_range,expect=-1,value=10},
        {field=hd2.fields.targeting.rear_range,expect=-1,value=3}}}}),
    hd2.ensure({enabled=limits,transaction={id='sentry-mg43-yaw-limits',target=sentry('A/MG-43 Machine Gun Sentry'):turret(),
        allow_unverified_effect=true,changes={
        {field=hd2.fields.turret.yaw_min,expect=-180,value=-30},
        {field=hd2.fields.turret.yaw_max,expect=180,value=30}}}}),
    hd2.ensure({enabled=control,patch={id='sentry-mg43-range-control',
        target=sentry('A/MG-43 Machine Gun Sentry'):targeting(),field=hd2.fields.targeting.range,expect=75,value=300}}),
}
