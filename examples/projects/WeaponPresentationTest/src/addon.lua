local hd2=require('mods/skyeshade/hd2runtime')
-- Live test: the AR-23C Liberator Concussive's gameplay armor penetration and its displayed label, independently.
-- Gameplay penetration is the AP of its bullets' DamageInfo (2 = light armor). The armory label is presentation: the
-- trait tags of its loadout entry, one of them the localization string LIGHT ARMOR PENETRATING. The game never
-- derives one from the other, so each has its own option:
--   Gameplay penetration: Vanilla (AP 2) or Medium (AP 3), at all four impact angles.
--   Displayed label:      Vanilla (Light), Light, Medium or Heavy.
-- The defaults are deliberately mismatched (gameplay Medium, label Heavy) so each can be seen on its own.
-- Menus build their labels when they open: close and reopen the armory or loadout screen after APPLY.
local concussive=hd2.weapon('AR-23C Liberator Concussive')
local shown=concussive:presentation()
assert(shown.armorPenetration=='light'and shown.writable.armorPenetration,'the Concussive label changed')
local options=hd2.options({id='weapon_presentation_test',title='Concussive Penetration'})
local gameplay=options:choice({id='gameplay_ap',label='Gameplay penetration',choices={'Vanilla (AP 2, light)',
    'Medium (AP 3)'},values={2,3},default=2,description='What the Concussive bullets actually penetrate.'})
local label=options:choice({id='displayed_label',label='Displayed label',choices={'Vanilla (Light)','Light','Medium',
    'Heavy'},values={'light','light','medium','heavy'},default=4,
    description='What the armory and loadout menus say. Reopen the menu after APPLY.'})
local bullets=concussive:attack('primary'):projectile()
local operations={}
operations[1]=hd2.ensure({transaction={id='concussive-gameplay-ap',target=bullets,allow_shared=true,changes={
    {field=hd2.fields.damage.ap_direct,expect=2,value=gameplay},
    {field=hd2.fields.damage.ap_slight,expect=2,value=gameplay},
    {field=hd2.fields.damage.ap_large,expect=2,value=gameplay},
    {field=hd2.fields.damage.ap_extreme,expect=2,value=gameplay}}}})
operations[2]=hd2.ensure({patch={id='concussive-displayed-ap',target=concussive,
    field=hd2.fields.presentation.armor_penetration,expect=shown.armorPenetration,value=label,
    allow_unverified_effect=true}})
return operations
