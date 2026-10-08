local hd2=require('mods/skyeshade/hd2runtime')
-- Sentry and emplacement projectile swaps (0.30.2): each host's own ProjectileWeapon +0, through
-- hd2.stratagem(name):attack('primary'):projectile_source(). Same-class donors only. Not live-tested: every write
-- needs allow_unverified_effect, and an uncatalogued donor allow_unverified_reference.
local function swap(id,stratagem,donor)
    local source=hd2.stratagem(stratagem):attack('primary'):projectile_source()
    assert(source.writable,stratagem..': '..tostring(source.reason))
    return {id=id,target=source.target,allow_unverified_effect=true,allow_unverified_reference=true,changes={
        {field=hd2.fields.attack.projectile,expect=source.expect,value=hd2.attack_output(donor)}}}
end
return hd2.ensure({plan={id='sentry-projectile-swap',operations={
    -- Player-aimed: the HMG Emplacement fires APW-1 anti-materiel rounds, the AT Emplacement recoilless rockets.
    swap('hmg','E/MG-101 HMG Emplacement','APW-1 Anti-Materiel Rifle'),
    swap('at','E/AT-12 Anti-Tank Emplacement','GR-8 Recoilless Rifle'),
    -- AI-aimed: the Autocannon Sentry fires Scorcher plasma (slower than its shell: watch whether it leads correctly).
    swap('autocannon','A/AC-8 Autocannon Sentry','PLAS-1 Scorcher'),
}}})
