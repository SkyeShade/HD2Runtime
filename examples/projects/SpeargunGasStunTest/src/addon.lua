local hd2=require('mods/skyeshade/hd2runtime')
-- Live test: an S-11 Speargun with two player-selectable modes, Gas (its own spear) and Stun (an EMS field).
-- The game's two-projectile mechanism is the ProgrammableAmmo weapon function: while it is on, every shot fires the
-- weapon's function projectile instead of its normal one (AC-8 FLAK, GR-8 HE, RL-77). The Speargun has the member
-- (empty) and a free left weapon-function input, so one transaction binds the function to that input and sets the
-- function projectile.
-- The stun field: the Speargun's gas cloud is a Gas status volume its spear's explosion leaves where it lands. The
-- EMS field is the same mechanism with the StaticField template (Stun Medium, no damage). The A/M-23 EMS Mortar
-- Sentry's shell leaves one for 7 s, radius 10, and Runtime loads the turret's package before writing it.
-- Mode labels: the weapon-function menu shows each mode's projectile label and icon. The spear and the EMS shell
-- have none (a blank label, the default icon), so a second option names them GAS and STUN (with the stun icon),
-- using the game's own strings and icon; the menu reads them from the projectile rows. The binding and the function
-- projectile are copied into a Speargun when the game builds it: call in a fresh one after APPLY.
local spear=hd2.support_weapon('S-11 Speargun')
local source=spear:feed('programmable'):source()
assert(source.writable and source.binding,'the Speargun can no longer take a programmable projectile')
local gas=hd2.attack_output('S-11 Speargun')
local ems=hd2.attack_output('A/M-23 EMS Mortar Sentry')
assert(ems:describe().fieldEffect.volume=='StaticField','the EMS Mortar shell no longer leaves a StaticField')
local options=hd2.options({id='speargun_gas_stun',title='Speargun Gas Stun'})
local enabled=options:toggle({id='enabled',label='Enabled',default=true,
    description='Off removes the stun mode: the Speargun fires only gas spears again.'})
local labels=options:toggle({id='labels',label='Mode labels',default=true,
    description='Name the modes GAS and STUN (stun icon) in the weapon-function menu. Off: the game defaults.'})
local operations={}
operations[1]=hd2.ensure({enabled=enabled,transaction={id='speargun-gas-stun',target=source.target,
    allow_unverified_effect=true,allow_unverified_reference=true,changes={
        {field=source.binding.field,expect=source.binding.expect,value=source.binding.value},
        {field=hd2.fields.function_ammo.projectile,expect=source.expect,value=ems}}}})
operations[2]=hd2.ensure({enabled=labels,patch={id='speargun-gas-label',target=gas,
    field=hd2.fields.presentation.mode_label,expect=gas:describe().presentation.label,value='gas',
    allow_unverified_effect=true}})
operations[3]=hd2.ensure({enabled=labels,transaction={id='speargun-stun-label',target=ems,
    allow_unverified_effect=true,changes={
        {field=hd2.fields.presentation.mode_label,expect=ems:describe().presentation.label,value='stun'},
        {field=hd2.fields.presentation.mode_icon,expect=ems:describe().presentation.icon,value='ammo_stun'}}}})
return operations
