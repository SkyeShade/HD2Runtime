local hd2=require('mods/skyeshade/hd2runtime')
-- Live test D: the MG-43 Machine Gun pod opens with a world Grenade Box instead of the machine gun. The Grenade
-- Box's package is otherwise loaded only when level generation happens to place grenade boxes.
-- The MG-43 rack is shared with other call-ins (allow_shared).
local rack=hd2.pod_rack('MG-43 Machine Gun pod')
return hd2.ensure({patch={id='asset-test-mg43-pod-grenade-box',target=rack:slot(1),field=hd2.fields.payload.entity,
    expect=rack:slot(1):current(),value=hd2.pickup('Grenade Box'),allow_unverified_reference=true,
    allow_shared=true}})
