local hd2=require('mods/skyeshade/hd2runtime')
-- Live test for the Eagle component fields (hd2.fields.eagle.*, docs/stratagem-authoring.md "Eagle attack fields",
-- docs/research/eagle-components-F5FEE03DCFDB.md). Each field is a member of the EagleComponentData record of the
-- stratagem's OWN jet (its payload[0]), re-proven before every write. It is a type-record write: every call of that
-- Eagle on this machine uses it (not per call), and no other Eagle reads it. The Napalm and Strafing Run jets are also
-- read by the Democracy Space Station's Eagle Storm (and an unused DSS strafing row), so they need allow_shared.
-- Not yet shown in game: every write needs allow_unverified_effect.
--
-- What to check, in a mission (host; each option is on by default; the log shows APPLIED for each):
--   * Eagle Airstrike: 8 bombs in a tight 21 m zigzag instead of 6 over 35 m (pattern 0 -> 2);
--   * Eagle Napalm Airstrike: the 4 bombs are released 0.6 s apart instead of 0.2 s (same landing points);
--   * Eagle Strafing Run: the burst lasts 3 s instead of 1.5 s (200 rounds instead of 100, the 60 m sweep slower);
--   * Eagle 110mm Rocket Pods: rockets engage enemies 30-50 m from the beacon (target search 20 m -> 60 m).
local BANNER='EAGLE FIELDS 0.1.0 BUILD'
local mod=hd2.mod()
local options=hd2.options({id='eagle_fields_test',title='Eagle Fields Test'})
local pattern=options:toggle({id='airstrike_pattern',label='Airstrike: 8-bomb zigzag',default=true,
    description='Eagle Airstrike landing pattern 0 (6 bombs over 35 m) -> 2 (8 bombs in a tight 21 m zigzag).'})
local interval=options:toggle({id='napalm_interval',label='Napalm: slow release',default=true,
    description='Eagle Napalm Airstrike: 0.2 s -> 0.6 s between its 4 bomb releases.'})
local strafe=options:toggle({id='strafe_duration',label='Strafing Run: double burst',default=true,
    description='Eagle Strafing Run attack 1.5 s -> 3.0 s: 200 rounds instead of 100.'})
local radius=options:toggle({id='rocket_radius',label='110mm: wide target search',default=true,
    description='Eagle 110mm Rocket Pods target search radius 20 m -> 60 m around the beacon.'})
mod:log(BANNER..': Airstrike pattern 0 -> 2, Napalm drop interval 0.2 -> 0.6 s, Strafing Run attack 1.5 -> 3.0 s, '
    ..'110mm target radius 20 -> 60 m (MODS page "Eagle Fields Test"; APPLIED lines follow)')
return {
    hd2.ensure({enabled=pattern,patch={id='eagle-airstrike-pattern',target=hd2.stratagem('Eagle Airstrike'),
        allow_unverified_effect=true,field=hd2.fields.eagle.airstrike_pattern,expect=0,value=2}}),
    hd2.ensure({enabled=interval,patch={id='eagle-napalm-interval',target=hd2.stratagem('Eagle Napalm Airstrike'),
        allow_shared=true,allow_unverified_effect=true,field=hd2.fields.eagle.drop_interval,expect=0.2,value=0.6}}),
    hd2.ensure({enabled=strafe,patch={id='eagle-strafe-duration',target=hd2.stratagem('Eagle Strafing Run'),
        allow_shared=true,allow_unverified_effect=true,field=hd2.fields.eagle.fire_duration,expect=1.5,value=3.0}}),
    hd2.ensure({enabled=radius,patch={id='eagle-rocket-radius',target=hd2.stratagem('Eagle 110mm Rocket Pods'),
        allow_unverified_effect=true,field=hd2.fields.eagle.target_radius,expect=20,value=60}}),
}
