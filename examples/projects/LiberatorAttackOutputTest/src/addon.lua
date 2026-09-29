local hd2=require('mods/skyeshade/hd2runtime')
-- One Mod Options choice switches what the AR-23 Liberator fires. The Liberator fires the projectile of its default
-- ammunition (RIFLE 5,5x50mm. FULL METAL JACKET): that ammunition's delta overwrites ProjectileWeapon +0 when the
-- weapon is built, so writing attack.projectile does nothing in play (live-tested). Every choice therefore writes the
-- active source, weapon:ammunition():projectile(), as one atomic owned transition through the same ensure.
-- The Liberator keeps its own magazine, ammunition use, reload, rate of fire and handling.
-- The donor's package is loaded automatically before the write; nobody needs to carry the donor weapon.
-- Acknowledgements: allow_shared (an ammunition definition applies to every weapon that equips it),
-- allow_unverified_effect (an edited ammunition delta reaching the weapon is not live-proven yet) and
-- allow_unverified_reference (EAT-700 and GL-52 are cross-class outputs).
-- LAS-58 Talon is the control: the same donor is live-proven on the SMG-32 Reprimand.
local liberator=hd2.weapon('AR-23 Liberator')
local source=liberator:attack('primary'):projectile_source()
assert(source.writable and source.mechanism=='ammunition','the Liberator active projectile source changed')
local options=hd2.options({id='liberator_attack_output',title='Liberator Attack Output'})
local output=options:choice({id='output',label='Liberator output',
    choices={'Vanilla','LAS-58 Talon (control)','EAT-700 Napalm','GL-52 Arc (impact)'},
    values={source.expect,hd2.weapon('LAS-58 Talon'):attack('primary'):projectile(),
        hd2.attack_output('EAT-700 Expendable Napalm'),hd2.attack_output('GL-52 De-Escalator')},
    default=1,description='What each Liberator round becomes. Vanilla restores the normal bullet. Talon: the '
        ..'LAS-58 laser bolt (control). EAT-700: the napalm rocket. GL-52: the De-Escalator arc grenade (arc on '
        ..'impact). Takes effect on the next Liberator the game builds (see README).'})
return hd2.ensure({patch={id='liberator-attack-output',target=source.target,field=hd2.fields.ammunition.projectile,
    expect=source.expect,value=output,allow_shared=true,allow_unverified_effect=true,allow_unverified_reference=true}})
