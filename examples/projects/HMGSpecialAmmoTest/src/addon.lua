local hd2=require('mods/skyeshade/hd2runtime')
-- Live test: an MG-206 Heavy Machine Gun with a second, special-ammunition mode built by the projectile builder
-- (weapon:programmable_ammo()). The HMG's right weapon-function input selects its rate of fire; its left input is free,
-- so the ProgrammableAmmo function is bound there and the mode fires a donor bullet with a status on hit.
-- The HMG's own bullet row is named by 15 typed references across 6 entities (the frv_mg and heavy_mg packages
-- among them), and no native row is an unreferenced twin of it, so giving the HMG's own bullet a status would change
-- all of them. The mode instead fires another weapon's ballistic bullet (same class, no cross-class acknowledgement)
-- that already applies the status: Incendiary = R-4 Hyena (fire), Stun = AR-32 Pacifier (Stun Medium), Gas = P-35
-- Re-Educator (gas and gas confusion). The bullet's flight and damage are the donor's. No native acid-on-hit bullet
-- is catalogued.
-- Labels are the game's own strings; each donor's label is written on that donor's own row (fired only by it, and
-- the donors have no weapon-function menu). The normal mode is labelled STANDARD: the HMG row is shared, so that
-- label write needs allow_shared (it changes nothing but a label and icon the other entities never show).
-- The binding and the function projectile are copied into an HMG when the game builds it: call in a fresh one.
local hmg=hd2.support_weapon('MG-206 Heavy Machine Gun')
local builder=hmg:programmable_ammo()
assert(builder:describe().writable,'the HMG can no longer take a programmable projectile')
local options=hd2.options({id='hmg_special_ammo',title='HMG Special Ammo'})
local enabled=options:toggle({id='enabled',label='Special ammunition mode',default=true,
    description='Add a second mode that fires status bullets. Off: the normal HMG only.'})
local ammo=options:choice({id='ammo',label='Special ammunition',choices={'Incendiary','Stun','Gas'},
    values={hd2.attack_output('R-4 Hyena'),hd2.attack_output('AR-32 Pacifier'),hd2.attack_output('P-35 Re-Educator')},
    description='Incendiary: R-4 Hyena bullet (fire). Stun: AR-32 Pacifier bullet. Gas: P-35 Re-Educator bullet.'})
local labels=options:toggle({id='labels',label='Mode labels',default=true,
    description='Name the modes STANDARD and INCENDIARY / STUN / GAS in the weapon-function menu.'})
local operations={}
for _,request in ipairs(builder:operations({id='hmg-special',enabled=enabled,base=ammo,
        allow_unverified_effect=true,allow_unverified_reference=true}))do
    operations[#operations+1]=hd2.ensure(request)
end
for _,request in ipairs(builder:presentation({id='hmg-labels',enabled=labels,base=ammo,
        label={['R-4 Hyena']='incendiary',['AR-32 Pacifier']='stun',['P-35 Re-Educator']='gas'},
        primary_label='standard',allow_shared=true,allow_unverified_effect=true}))do
    operations[#operations+1]=hd2.ensure(request)
end
return operations
