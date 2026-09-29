local hd2=require('mods/skyeshade/hd2runtime')
-- Live test A: the M-105 Stalwart pod opens with a Stalwart AND an EAT-700, in a mission where nobody
-- brought the EAT-700. Before automatic asset loading the EAT-700 slot spawned as a purple, non-interactable
-- question mark, because the EAT-700's package is only loaded when some player carries it.
local rack=hd2.pod_rack('M-105 Stalwart pod')
return hd2.ensure({plan={id='asset-test-stalwart-pod-eat700',operations={
    {id='slot-2',target=rack:slot(2),field=hd2.fields.payload.entity,expect=rack:slot(2):current(),
        value=hd2.pickup('EAT-700 Expendable Napalm'),allow_unverified_reference=true},
    {id='spawn-both',target=rack,field=hd2.fields.payload.spawn_count,expect=1,value=2,allow_unverified_effect=true},
}}})
