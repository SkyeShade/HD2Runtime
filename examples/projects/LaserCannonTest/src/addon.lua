local hd2=require('mods/skyeshade/hd2runtime')
-- Live test: the LAS-98 Laser Cannon beam fire rate (research/equipment-coverage-F5FEE03DCFDB.json): the published
-- "Beam Fire Rate" of seven weapons (LAS-98 60, LAS-13 Trident 300, 40-K Meltagun 50 per minute) sits at one typed
-- BeamWeapon member: how often the beam applies its damage. Everything else on the LAS-98 (beam, damage, heat,
-- heatsinks, handling, status) is already authored. Copied when the weapon is built: call in a fresh LAS-98.
local cannon=hd2.support_weapon('LAS-98 Laser Cannon')
local options=hd2.options({id='laser_cannon_test',title='Laser Cannon Test'})
local fast=options:toggle({id='fast_beam',label='Fast beam',default=true,
    description='The beam applies its damage 240 times a minute instead of 60.'})
return {
    hd2.ensure({enabled=fast,patch={id='laser-cannon-beam-rate',target=cannon,allow_unverified_effect=true,
        field=hd2.fields.beam.fire_rate,expect=60,value=240}}),
}
