local hd2=require('mods/skyeshade/hd2runtime')

return hd2.ensure({
    patch={
        id='stratagem-9fb77b22d9f4ba8687ce146c',
        target=hd2.stratagem('Orbital Precision Strike'),
        field=hd2.fields.stratagem.definition_cooldown,
        expect=80,
        value=60,
    }
})
