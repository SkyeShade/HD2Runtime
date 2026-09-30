local hd2=require('mods/skyeshade/hd2runtime')
-- Live test: mounted weapons in the one projectile system (docs/attack-outputs.md, mounted hosts). The EXO-45 Patriot
-- Exosuit's minigun is a projectile host by the same rule as player and support weapons: magazine-fed, and every shot
-- is its own ProjectileWeapon +0 (research/active-projectile-sources). Its record belongs to the Patriot alone.
-- - Minigun projectile: the minigun fires another catalogued projectile (any loadout slot): EAT-17, Talon, Scorcher,
--   or a bullet that applies a status on hit (R-4 Hyena fire, AR-32 Pacifier stun, P-35 Re-Educator gas). One field:
--   only one choice at a time. Runtime loads the donor's package first.
-- - Impact effect: an explosion released where the minigun's own bullet hits (GL-21 grenade blast, Speargun gas cloud,
--   EMS Mortar field, EAT-700 napalm). The minigun bullet row is SHARED: 10 entities fire it (the Gatling and
--   machine-gun sentries among them), so this needs allow_shared and changes them too. It applies while the minigun
--   fires its own bullet (projectile Vanilla). Default None.
-- The projectile reference is copied into the Patriot when it is built: call in a fresh Exosuit after APPLY.
local patriot=hd2.vehicle('EXO-45 Patriot Exosuit'):weapon('right_gun')
local source=patriot:projectile_source()
assert(source.writable,'the Patriot minigun is no longer a projectile host: '..tostring(source.reason))
local options=hd2.options({id='vehicle_projectile_builder',title='Vehicle Projectile Builder'})
local projectile=options:choice({id='projectile',label='Patriot minigun projectile',
    choices={'Vanilla','EAT-17','Talon','Scorcher','Incendiary','Stun','Gas'},
    values={source.expect,hd2.attack_output('EAT-17 Expendable Anti-Tank'),hd2.attack_output('LAS-58 Talon'),
        hd2.attack_output('PLAS-1 Scorcher'),hd2.attack_output('R-4 Hyena'),hd2.attack_output('AR-32 Pacifier'),
        hd2.attack_output('P-35 Re-Educator')},
    description='What every minigun shot fires. Incendiary / Stun / Gas are bullets that apply that status on hit.'})
local bullet=hd2.attack_output('EXO-45 Patriot Exosuit / right_gun')
local impact=options:choice({id='impact',label='Minigun impact effect',
    choices={'None','Grenade blast','Gas cloud','EMS field','Napalm'},
    values={'none',hd2.attack_output('GL-21 Grenade Launcher'):impact_explosion(),
        hd2.attack_output('S-11 Speargun'):expiry_explosion(),
        hd2.attack_output('A/M-23 EMS Mortar Sentry'):expiry_explosion(),
        hd2.attack_output('EAT-700 Expendable Napalm'):impact_explosion()},
    description='Released where the minigun bullet hits. Shared: also the Gatling and machine-gun sentries.'})
-- Mounted projectile swaps and slot writes are mapped offline, not yet shown in game.
return {
    hd2.ensure({transaction={id='patriot-minigun-projectile',target=source.target,allow_unverified_effect=true,
        allow_unverified_reference=true,changes={{field=source.field,expect=source.expect,value=projectile}}}}),
    hd2.ensure({transaction={id='patriot-minigun-impact',target=bullet,allow_shared=true,allow_unverified_effect=true,
        changes={{field=hd2.fields.projectile.impact_explosion,expect='none',value=impact}}}}),
}
