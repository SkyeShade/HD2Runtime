local hd2=require('mods/skyeshade/hd2runtime')

local target=hd2.weapon('CB-9 Exploding Crossbow'):attack('primary'):projectile()
    :terminal_action('impact')
local source=hd2.weapon('PLAS-101 Purifier'):attack('primary'):projectile()
    :terminal_action('impact'):explosion()

return hd2.ensure({
    patch={
        id='crossbow-purifier-impact',
        target=target,
        field=hd2.fields.terminal.explosion,
        expect=target:explosion(),
        value=source,
    },
})
