local hd2=require('mods/skyeshade/hd2runtime')
-- Live test B: the SMG-32 Reprimand fires the LAS-58 Talon's projectile, in a mission where nobody brought
-- the Talon. The projectile's unit and effects live in the Talon's package, so they are loaded first.
local target=hd2.weapon('SMG-32 Reprimand'):attack('primary')
return hd2.ensure({patch={id='asset-test-reprimand-talon',target=target,field=hd2.fields.attack.projectile,
    expect=target:projectile(),value=hd2.weapon('LAS-58 Talon'):attack('primary'):projectile()}})
