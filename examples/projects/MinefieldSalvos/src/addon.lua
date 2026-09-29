local hd2=require('mods/skyeshade/hd2runtime')
-- MD-6 Anti-Personnel Minefield: 6 salvos -> 2 (48 mines -> 16). ThrowerComponent slot 0 +40 equals the wiki's
-- "six salvos of eight mines" on every minefield, and salvos x mines per salvo equals the launcher's launch sockets.
-- Counts can only be reduced (one socket per mine); the gameplay effect is not yet live-confirmed.
local mines=hd2.stratagem('MD-6 Anti-Personnel Minefield'):deployed_entity():minefield()
return hd2.ensure({patch={id='minefield-salvos',target=mines,allow_unverified_effect=true,
    field=hd2.fields.minefield.salvos,expect=6,value=2}})
