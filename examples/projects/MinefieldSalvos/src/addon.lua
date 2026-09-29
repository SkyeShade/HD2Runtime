local hd2=require('mods/skyeshade/hd2runtime')
-- MD-6 Anti-Personnel Minefield: 6 salvos -> 2 (48 mines -> 16). Counts can only be reduced (one launch socket per
-- mine). Live-proven 2026-09-29 (sdk/LiveEvidenceCatalog.json): no acknowledgement is needed. Fewer salvos cover
-- fewer rotational sectors of the launcher's pattern; they do not thin the mines evenly around the circle.
local mines=hd2.stratagem('MD-6 Anti-Personnel Minefield'):deployed_entity():minefield()
return hd2.ensure({patch={id='minefield-salvos',target=mines,field=hd2.fields.minefield.salvos,expect=6,value=2}})
