local hd2=require('mods/skyeshade/hd2runtime')
-- Live test: the more projectile donors (docs/attack-outputs.md, "More donors"): a stratagem's Eagle bomb, an orbital
-- shell, an emplacement round and weapons' second projectiles, fired by ordinary weapons. Each donor is re-proven from
-- its own component right before the write, and its package is loaded first. None is live-tested yet, so each swap
-- carries allow_unverified_reference and allow_unverified_effect. Each swap is copied into the weapon when the game
-- builds it: call in or re-equip a fresh one after APPLY.
local mod=hd2.mod()
mod:log('ProjectileDonorTest 0.1.0 MORE DONORS BUILD: Mod Options > Projectile Donor Test; then a mission. Defaults: '
    ..'the Reprimand fires Eagle 500kg bombs, the Stalwart fires Orbital Precision Strike shells, the Arbitrator fires '
    ..'the HMG Emplacement round.')
local options=hd2.options({id='projectile_donor_test',title='Projectile Donor Test'})
local function toggle(id,label,default,description)
    return options:toggle({id=id,label=label,default=default,description=description})
end
local SWAPS={
    {toggle('reprimand_500kg','Reprimand fires 500kg bombs',true,
        'The SMG-32 Reprimand fires the Eagle 500kg Bomb (projectile 239).'),
        'reprimand-500kg',hd2.weapon('SMG-32 Reprimand'),'Eagle 500kg Bomb (projectile 239)'},
    {toggle('stalwart_precision','Stalwart fires precision shells',true,
        'The M-105 Stalwart fires the Orbital Precision Strike shell (projectile 100).'),
        'stalwart-precision',hd2.support_weapon('M-105 Stalwart'),'Orbital Precision Strike (projectile 100)'},
    {toggle('arbitrator_hmg','Arbitrator fires HMG rounds',true,
        'The AR-11 Arbitrator fires the E/MG-101 HMG Emplacement round (projectile 83; the same class).'),
        'arbitrator-hmg',hd2.weapon('AR-11 Arbitrator'),'E/MG-101 HMG Emplacement (projectile 83)'},
    {toggle('apw_flak','APW-1 fires AC-8 flak',false,
        'The APW-1 Anti-Materiel Rifle fires the AC-8 Autocannon\'s second projectile (projectile 284).'),
        'apw-flak',hd2.support_weapon('APW-1 Anti-Materiel Rifle'),'AC-8 Autocannon (projectile 284)'},
    {toggle('hmg_gatling','HMG fires orbital gatling rounds',false,
        'The MG-206 Heavy Machine Gun fires the Orbital Gatling Barrage round (projectile 77).'),
        'hmg-gatling',hd2.support_weapon('MG-206 Heavy Machine Gun'),'Orbital Gatling Barrage (projectile 77)'},
    {toggle('amendment_railcannon','Amendment fires the railcannon round',false,
        'The R-2 Amendment fires the Orbital Railcannon Strike round (projectile 277, 14,000 m/s).'),
        'amendment-railcannon',hd2.weapon('R-2 Amendment'),'Orbital Railcannon Strike (projectile 277)'},
}
local out={}
for _,s in ipairs(SWAPS)do
    local enabled,id,weapon,donor=s[1],s[2],s[3],s[4]
    local source=weapon:projectile_source()
    assert(source.writable,id..': the host is no longer a projectile host')
    out[#out+1]=hd2.ensure({enabled=enabled,transaction={id=id,target=source.target,changes={{field=source.field,
        expect=source.expect,value=hd2.attack_output(donor)}},allow_unverified_reference=true,
        allow_unverified_effect=true}})
end
return out
