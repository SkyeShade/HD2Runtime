local hd2=require('mods/skyeshade/hd2runtime')

-- An explosive_impact selector replacement: the PLAS-1 Scorcher fires the CB-9 Exploding Crossbow bolt. Both attacks
-- fire their own ProjectileWeapon member (projectile_source() is ACTIVE_DIRECT), so the write changes what fires.
local target=hd2.weapon('PLAS-1 Scorcher'):attack('primary')
local source=hd2.weapon('CB-9 Exploding Crossbow'):attack('primary'):projectile()

return hd2.ensure({
    patch={
        id='scorcher-crossbow-projectile',
        target=target,
        field=hd2.fields.attack.projectile,
        expect=target:projectile(),
        value=source,
    },
})
