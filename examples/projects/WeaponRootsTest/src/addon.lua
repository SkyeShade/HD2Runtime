local hd2=require('mods/skyeshade/hd2runtime')
-- Live test (0.30.2): the seven weapons that were blocked as DUPLICATE identities now resolve to their proven roots
-- (research/weapon-roots-F5FEE03DCFDB.json). One clearly visible, weapon-local change per weapon, each on its own
-- toggle (MODS tab, page "Weapon Roots Test"). Every change is copied into the weapon when the game builds it:
-- equip the weapon in the loadout and start a mission (or re-equip / redeploy) after the mod applied.
local mod=hd2.mod()
mod:log('WeaponRootsTest 0.1.0 (0.30.2-dev5): equip the weapons, start a mission, and check each one against the '
    ..'MODS page "Weapon Roots Test". Expected: Dagger fires about 4x longer before overheating; Scythe about 4x '
    ..'longer; GP-31 starts with 12 grenades and 20 spare; P-72 holds 150 fuel; Defender fires at 1100 rpm; '
    ..'Machete and E-Tool one-hit most small enemies.')
local options=hd2.options({id='weapon_roots_test',title='Weapon Roots Test'})
local function weapon(name,id,label,description,changes)
    local enabled=options:toggle({id=id,label=label,default=true,description=description})
    local spec={id='weapon-roots-'..id,target=hd2.weapon(name),changes=changes}
    return hd2.ensure({enabled=enabled,transaction=spec})
end
return {
    weapon('LAS-7 Dagger','dagger','LAS-7 Dagger: 4x heat capacity',
        'Heat capacity 100 -> 400: about four times longer firing before it overheats.',
        {{field=hd2.fields.heat.capacity,expect=100,value=400}}),
    weapon('LAS-5 Scythe','scythe','LAS-5 Scythe: a quarter of the heat',
        'Heat per second 12.5 -> 3: about four times longer firing before it overheats.',
        {{field=hd2.fields.heat.heat_per_second,expect=12.5,value=3}}),
    weapon('GP-31 Grenade Pistol','gp31','GP-31: 12 grenades, 20 spare',
        'Starting rounds 4 -> 12 and spare rounds 6 -> 20.',
        {{field=hd2.fields.rounds.starting_rounds,expect=4,value=12},
         {field=hd2.fields.rounds.spare_rounds,expect=6,value=20}}),
    weapon('P-72 Crisper','crisper','P-72 Crisper: 150 fuel',
        'Magazine capacity 50 -> 150.',
        {{field=hd2.fields.magazine.capacity,expect=50,value=150}}),
    weapon('SMG-37 Defender','defender','SMG-37 Defender: 1100 rpm',
        'Fire rate 520 -> 1100 rounds per minute.',
        {{field=hd2.fields.weapon.fire_rate,expect=520,value=1100}}),
    weapon('CQC-42 Machete','machete','CQC-42 Machete: 1500 damage',
        'Damage 300 -> 1500: one hit kills most small enemies.',
        {{field=hd2.fields.damage.player_standard_damage,expect=300,value=1500}}),
    weapon('CQC-73 Entrenchment Tool','etool','CQC-73 E-Tool: 1500 damage',
        'Damage 165 -> 1500: one hit kills most small enemies.',
        {{field=hd2.fields.damage.player_standard_damage,expect=165,value=1500}}),
}
