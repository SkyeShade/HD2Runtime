local hd2=require('mods/skyeshade/hd2runtime')
-- Live test: an S-11 Speargun with a player-selectable second ammunition, Gas <-> Stun.
-- Natively the Speargun fires one projectile, the gas spear. The game has a native two-projectile mechanism: the
-- ProgrammableAmmo weapon function. While it is switched on, every shot fires the weapon's function projectile instead
-- of its normal one; the AC-8 Autocannon (flak), GR-8 Recoilless Rifle and RL-77 use it. The Speargun has the member
-- (empty) and a free left weapon-function input, so one transaction:
--   binds ProgrammableAmmo to the left input (the selector), and
--   sets the function projectile to a stun donor (its package loads automatically first).
-- Gas stays the normal ammunition: switch the new weapon function on for Stun and off for Gas.
-- Both changes are copied into a Speargun when the game builds it: call in a fresh Speargun after APPLY.
local spear=hd2.support_weapon('S-11 Speargun')
local source=spear:feed('programmable'):source()
assert(source.writable and source.binding,'the Speargun can no longer take a programmable projectile')
local options=hd2.options({id='speargun_gas_stun',title='Speargun Gas Stun'})
local enabled=options:toggle({id='enabled',label='Enabled',default=true,
    description='Off removes the second ammunition: the Speargun fires only gas spears again.'})
local stun=options:choice({id='stun',label='Stun ammunition',choices={'GL-52 Arc grenade','AR-32 Pacifier round',
    'SMG-72 Pummeler round'},values={hd2.attack_output('GL-52 De-Escalator'),hd2.attack_output('AR-32 Pacifier'),
    hd2.attack_output('SMG-72 Pummeler')},default=1,description='What the Speargun fires while its programmable '
    ..'ammunition is on. GL-52: the De-Escalator arc grenade (arc on impact, live-proven donor). Pacifier and '
    ..'Pummeler: their stun bullets.'})
return hd2.ensure({enabled=enabled,transaction={id='speargun-gas-stun',target=source.target,
    allow_unverified_effect=true,allow_unverified_reference=true,changes={
        {field=source.binding.field,expect=source.binding.expect,value=source.binding.value},
        {field=hd2.fields.function_ammo.projectile,expect=source.expect,value=stun}}}})
