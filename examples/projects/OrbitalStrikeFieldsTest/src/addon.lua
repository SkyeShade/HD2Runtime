local hd2=require('mods/skyeshade/hd2runtime')
-- Live test for the orbital bombardment pattern fields (hd2.fields.orbital.salvos, shells_per_salvo, shell_interval,
-- salvo_interval, scatter, ...) and the call-in time (hd2.fields.stratagem.call_in_time); docs/stratagem-authoring.md
-- "Orbital bombardment pattern" and "Call-in time". Each orbital field is a member of the orbital's OWN
-- BombardmentComponentData record (its shell list is re-proven before every write); the call-in time is the
-- stratagem's own StratagemInfo +0x54. Both are type-record writes: every call of that stratagem on this machine uses
-- them (not per call). Not yet shown in game: every write needs allow_unverified_effect.
--
-- What to check, in a mission (host; the log shows APPLIED for each option that is on):
--   * Orbital EMS Strike becomes an EMS barrage: 5 salvos of 3 EMS shells, 1.5 s apart, spread wide (scatter 1 -> 20);
--   * Orbital Napalm Barrage becomes a precision napalm strike: one single napalm shell on the beacon;
--   * Orbital 120mm HE Barrage arrives 1 s after the beacon lands instead of 5 s (ship upgrades shorten both);
--   * Orbital 380mm HE Barrage waits 15 s instead of 6 s before it starts;
--   * (off by default) Orbital Gatling Barrage pauses 1 s between its 4 bursts instead of firing them back to back;
--   * (off by default) Eagle 500kg Bomb: the jet is dispatched 5 s after the beacon lands instead of at once.
local BANNER='ORBITAL STRIKE FIELDS 0.1.0 BUILD'
local mod=hd2.mod()
local options=hd2.options({id='orbital_strike_fields_test',title='Orbital Strike Fields Test'})
local ems=options:toggle({id='ems_barrage',label='EMS Strike: barrage',default=true,
    description='Orbital EMS Strike: 1 salvo of 1 shell -> 5 salvos of 3 shells, 1.5 s between salvos, scatter 20.'})
local napalm=options:toggle({id='precise_napalm',label='Napalm Barrage: one shell',default=true,
    description='Orbital Napalm Barrage: 5 salvos of 5 shells (scatter 25) -> 1 salvo of 1 shell (scatter 1).'})
local fast=options:toggle({id='fast_120mm',label='120mm: 1 s call-in',default=true,
    description='Orbital 120mm HE Barrage call-in 5 s -> 1 s (before the game\'s upgrades).'})
local slow=options:toggle({id='slow_380mm',label='380mm: 15 s call-in',default=true,
    description='Orbital 380mm HE Barrage call-in 6 s -> 15 s (before the game\'s upgrades).'})
local gatling=options:toggle({id='gatling_pauses',label='Gatling: pause between bursts',default=false,
    description='Orbital Gatling Barrage: 0 s -> 1 s between its 4 salvos of 60 rounds.'})
local eagle=options:toggle({id='eagle_delay',label='500kg: delayed dispatch',default=false,
    description='Eagle 500kg Bomb call-in 0 s -> 5 s: the jet leaves 5 s after the beacon lands.'})
mod:log(BANNER..': EMS Strike -> barrage, Napalm Barrage -> one shell, 120mm call-in 5 -> 1 s, 380mm call-in 6 -> 15 s '
    ..'(and, off by default, Gatling pauses and a delayed 500kg; MODS page "Orbital Strike Fields Test")')
return {
    hd2.ensure({enabled=ems,transaction={id='ems-barrage',target=hd2.stratagem('Orbital EMS Strike'),
        allow_unverified_effect=true,changes={
            {field=hd2.fields.orbital.salvos,expect=1,value=5},
            {field=hd2.fields.orbital.shells_per_salvo,expect=1,value=3},
            {field=hd2.fields.orbital.shell_interval,expect=0.35,value=0.4},
            {field=hd2.fields.orbital.salvo_interval,expect=2,value=1.5},
            {field=hd2.fields.orbital.scatter,expect=1,value=20}}}}),
    hd2.ensure({enabled=napalm,transaction={id='precise-napalm',target=hd2.stratagem('Orbital Napalm Barrage'),
        allow_unverified_effect=true,changes={
            {field=hd2.fields.orbital.salvos,expect=5,value=1},
            {field=hd2.fields.orbital.shells_per_salvo,expect=5,value=1},
            {field=hd2.fields.orbital.scatter,expect=25,value=1}}}}),
    hd2.ensure({enabled=fast,patch={id='fast-120mm',target=hd2.stratagem('Orbital 120mm HE Barrage'),
        allow_unverified_effect=true,field=hd2.fields.stratagem.call_in_time,expect=5,value=1}}),
    hd2.ensure({enabled=slow,patch={id='slow-380mm',target=hd2.stratagem('Orbital 380mm HE Barrage'),
        allow_unverified_effect=true,field=hd2.fields.stratagem.call_in_time,expect=6,value=15}}),
    hd2.ensure({enabled=gatling,patch={id='gatling-pauses',target=hd2.stratagem('Orbital Gatling Barrage'),
        allow_unverified_effect=true,field=hd2.fields.orbital.salvo_interval,expect=0,value=1}}),
    hd2.ensure({enabled=eagle,patch={id='eagle-delay',target=hd2.stratagem('Eagle 500kg Bomb'),
        allow_unverified_effect=true,field=hd2.fields.stratagem.call_in_time,expect=0,value=5}}),
}
