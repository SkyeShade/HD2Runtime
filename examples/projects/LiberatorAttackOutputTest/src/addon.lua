local hd2=require('mods/skyeshade/hd2runtime')
-- One Mod Options choice switches what the AR-23 Liberator's attack emits. The Liberator keeps its own magazine,
-- ammunition use, reload, rate of fire and handling: only its projectile reference (ProjectileWeapon +0) changes.
-- Each choice is one complete composition, so switching is a single atomic write through the same ensure.
-- The donor's package is loaded automatically before the write; nobody needs to carry the donor weapon.
-- Cross-class outputs are structurally one reference but not gameplay-proven, hence both acknowledgements.
-- LAS beam, Trident and ARC-3 arc outputs are not offered: beams and arcs are fired by their own weapon components,
-- which a projectile weapon cannot reference (docs/attack-outputs.md).
local host=hd2.weapon('AR-23 Liberator'):attack('primary')
local options=hd2.options({id='liberator_attack_output',title='Liberator Attack Output'})
local output=options:choice({id='output',label='Liberator output',
    choices={'Vanilla','EAT-700 Napalm','GL-52 Arc (impact)'},
    values={host:projectile(),hd2.attack_output('EAT-700 Expendable Napalm'),hd2.attack_output('GL-52 De-Escalator')},
    default=1,description='What each Liberator round becomes. Vanilla restores the normal bullet. EAT-700: the '
        ..'napalm rocket. GL-52: the De-Escalator arc grenade (arc on impact). The magazine, reload and rate of '
        ..'fire stay the Liberator ones.'})
return hd2.ensure({patch={id='liberator-attack-output',target=host,allow_unverified_reference=true,
    allow_unverified_effect=true,field=hd2.fields.attack.projectile,expect=host:projectile(),value=output}})
