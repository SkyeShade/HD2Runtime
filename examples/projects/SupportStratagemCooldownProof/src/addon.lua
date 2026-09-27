local hd2=require('mods/skyeshade/hd2runtime')
return hd2.patch({id='support-stratagem-cooldown-proof',
 target=hd2.stratagem('AC-8 Autocannon'),field=hd2.fields.stratagem.definition_cooldown,
 expect=480,value=60})
