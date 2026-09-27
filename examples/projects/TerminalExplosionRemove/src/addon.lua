local hd2=require('mods/skyeshade/hd2runtime')

local terminal=hd2.weapon('CB-9 Exploding Crossbow'):attack('primary'):projectile()
    :terminal_action('impact')
return hd2.ensure({
    patch={
        id='crossbow-remove-impact-explosion',
        target=terminal,
        field=hd2.fields.terminal.explosion,
        expect=terminal:explosion(),
        value=terminal:no_explosion(),
    },
})
