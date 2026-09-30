local hd2=require('mods/skyeshade/hd2runtime')
-- Live test: one projectile donor pool across loadout slots. A projectile host is any weapon whose fired projectile
-- Runtime can write (weapon:projectile_source().writable): its own ProjectileWeapon +0 (primary, secondary and, new,
-- magazine-fed support weapons) or its default ammunition (Liberator). A donor is any catalogued projectile output
-- (hd2.attack_output(name)) or another weapon's attack projectile handle, whatever slot it comes from; beam, arc,
-- spray and melee outputs are refused. Each swap is copied into the weapon when the game builds it: call in or
-- re-equip a fresh one after APPLY. Runtime loads each donor's package first.
local eat=hd2.support_weapon('EAT-17 Expendable Anti-Tank')
local reprimand=hd2.weapon('SMG-32 Reprimand')
local liberator=hd2.weapon('AR-23 Liberator')
local stalwart=hd2.support_weapon('M-105 Stalwart')
for _,weapon in ipairs({eat,reprimand,liberator,stalwart})do
    assert(weapon:projectile_source().writable,weapon:projectile_source().weapon..' is no longer a projectile host')
end
local options=hd2.options({id='unified_projectile_swap',title='Unified Projectile Swap'})
local eat_scorcher=options:toggle({id='eat_scorcher',label='EAT-17 fires Scorcher plasma',default=true,
    description='Support host <- primary donor: the EAT-17 fires the PLAS-1 Scorcher plasma bolt.'})
local reprimand_napalm=options:toggle({id='reprimand_napalm',label='Reprimand fires EAT-700 napalm',default=true,
    description='Primary host <- support donor: the SMG-32 Reprimand fires the EAT-700 napalm rocket.'})
local liberator_talon=options:toggle({id='liberator_talon',label='Liberator fires Talon lasers',default=true,
    description='Ammunition host: the AR-23 Liberator fires the LAS-58 Talon laser bolt (live-proven path).'})
local stalwart_amr=options:toggle({id='stalwart_amr',label='Stalwart fires AMR rounds',default=false,
    description='Support host <- support donor: the M-105 Stalwart fires the APW-1 Anti-Materiel Rifle round.'})
local function swap(enabled,id,weapon,value,extra)
    local source=weapon:projectile_source()
    local request={id=id,target=source.target,changes={{field=source.field,expect=source.expect,value=value}}}
    for key,flag in pairs(extra)do request[key]=flag end
    return hd2.ensure({enabled=enabled,transaction=request})
end
return {
    -- Same class (explosive impact): only the not-yet-live-proven support host path is acknowledged.
    swap(eat_scorcher,'eat-scorcher',eat,hd2.weapon('PLAS-1 Scorcher'):attack('primary'):projectile(),
        {allow_unverified_effect=true}),
    -- Cross class (a plain host, a shrapnel rocket): both acknowledgements.
    swap(reprimand_napalm,'reprimand-napalm',reprimand,
        hd2.support_weapon('EAT-700 Expendable Napalm'):attack('primary'):projectile(),
        {allow_unverified_effect=true,allow_unverified_reference=true}),
    -- The Liberator's default ammunition is shared with the weapons that list it (allow_shared).
    swap(liberator_talon,'liberator-talon',liberator,hd2.attack_output('LAS-58 Talon'),{allow_shared=true}),
    swap(stalwart_amr,'stalwart-amr',stalwart,hd2.attack_output('APW-1 Anti-Materiel Rifle'),
        {allow_unverified_effect=true}),
}
