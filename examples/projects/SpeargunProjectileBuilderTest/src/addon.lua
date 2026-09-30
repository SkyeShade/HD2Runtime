local hd2=require('mods/skyeshade/hd2runtime')
-- Live test: an S-11 Speargun with two modes built by the projectile builder (weapon:programmable_ammo()).
-- Mode A (GAS) is the Speargun's own spear: its direct hit applies gas and gas confusion, and when the spear expires
-- (stuck in the ground or a target) its expiry explosion leaves a gas cloud (a Gas status volume, 10 s).
-- Mode B (STUN) keeps the spear: the base is the Speargun's spare twin, a native projectile row no other weapon
-- references that is byte-identical to the spear (same flight, model, trail and sound). Its expiry explosion is
-- pointed at the EMS Mortar shell's explosion, which leaves a StaticField (Stun Medium) instead of gas. Nothing else
-- fires the spare twin, so no other weapon changes. Runtime loads the EMS turret's package before the write.
-- The binding and the function projectile are copied into a Speargun when the game builds it: call in a fresh one
-- after APPLY. Labels and icons are the game's own: GAS shows the plain round, STUN the stun icon.
local spear=hd2.support_weapon('S-11 Speargun')
local builder=spear:programmable_ammo()
assert(builder:describe().writable,'the Speargun can no longer take a programmable projectile')
local twin=hd2.attack_output('S-11 Speargun (spare twin)')
assert(twin:describe().spare and twin:describe().spare.independent,'the Speargun spare twin is no longer independent')
local ems=hd2.attack_output('A/M-23 EMS Mortar Sentry')
assert(ems:describe().fieldEffect.volume=='StaticField','the EMS Mortar shell no longer leaves a StaticField')
local options=hd2.options({id='speargun_projectile_builder',title='Speargun Projectile Builder'})
local stun=options:toggle({id='stun_mode',label='Stun spear mode',default=true,
    description='Add mode B: the same spear, leaving an EMS stun field instead of gas. Off: gas spears only.'})
local labels=options:toggle({id='gas_label',label='GAS label',default=true,
    description='Name the normal mode GAS (plain round icon) in the weapon-function menu. Off: the game default.'})
local operations={}
-- Live-proven exactly as written here (schemas/live_evidence.json); the acknowledgements stay.
for _,request in ipairs(builder:operations({id='spear-stun',enabled=stun,base=twin,
        expiry_explosion=ems:expiry_explosion(),label='stun',
        allow_unverified_effect=true,allow_unverified_reference=true}))do
    operations[#operations+1]=hd2.ensure(request)
end
for _,request in ipairs(builder:presentation({id='spear-gas',enabled=labels,primary_label='gas',
        allow_unverified_effect=true}))do
    operations[#operations+1]=hd2.ensure(request)
end
return operations
