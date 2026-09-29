local hd2=require('mods/skyeshade/hd2runtime')

return hd2.ensure({
    patch={
        id='gui-object-7656c9accd9794fd7a19c5e1',
        target=hd2.weapon('MA5C Assault Rifle'),
        field=hd2.fields.magazine.capacity,
        expect=32,
        value=60,
    }
})
