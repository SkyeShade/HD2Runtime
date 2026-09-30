local hd2=require('mods/skyeshade/hd2runtime')
-- Live test: the AR/GL-21 One-Two underbarrel grenade launcher (research/underbarrel-weapons-F5FEE03DCFDB.json). The
-- launcher is its own weapon entity, named by the rifle's default underbarrel item; the game creates it as a separate
-- weapon when the One-Two is set up. Its grenade spread and grenade reserve are that entity's own records (the same
-- members as weapon.horizontal_spread / rounds.spare_rounds on every weapon), written on
-- hd2.weapon('AR/GL-21 One-Two'):underbarrel(). The rifle is untouched. The values are copied when the weapon is
-- built: re-equip the One-Two (or call in a new loadout) after APPLY.
local launcher=hd2.weapon('AR/GL-21 One-Two'):underbarrel()
assert(launcher:describe().subweaponOf=='AR/GL-21 One-Two','the One-Two underbarrel is no longer catalogued')
local options=hd2.options({id='one_two_underbarrel_test',title='One-Two Underbarrel Test'})
local tight=options:toggle({id='tight_grenades',label='Tight grenades',default=true,
    description='Grenade spread 30 -> 3 (horizontal and vertical): grenades land where you aim.'})
local pouch=options:toggle({id='grenade_pouch',label='Grenade pouch',default=true,
    description='Spare grenades 5 -> 15, resupply 5 -> 15, starting reserve 3 -> 9.'})
-- The underbarrel fields are mapped offline, not yet shown in game.
return {
    hd2.ensure({enabled=tight,transaction={id='one-two-spread',target=launcher,allow_unverified_effect=true,changes={
        {field=hd2.fields.weapon.horizontal_spread,expect=30,value=3},
        {field=hd2.fields.weapon.vertical_spread,expect=30,value=3}}}}),
    hd2.ensure({enabled=pouch,transaction={id='one-two-grenades',target=launcher,allow_unverified_effect=true,changes={
        {field=hd2.fields.rounds.spare_rounds,expect=5,value=15},
        {field=hd2.fields.rounds.rounds_from_supply,expect=5,value=15},
        {field=hd2.fields.rounds.starting_rounds,expect=3,value=9}}}}),
}
