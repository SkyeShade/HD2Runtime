local hd2=require('mods/skyeshade/hd2runtime')
-- BreakthroughProof 0.1.0 (HD2Runtime 0.30.4, development only): mounted-weapon spread (WeaponData +84/+88, the member
-- the projectile shot reads for every shot and pellet) and the EXO-55 Breakthrough shield arm (its left mount: arm pool
-- and plate zone of its own HealthComponent). docs/vehicle-weapons.md "Spread" and "EXO-55 Breakthrough shield arm",
-- research/docs/mounted-spread-shield-F5FEE03DCFDB.md. One options toggle per test. Every value is copied when the
-- Exosuit is created: call in a NEW Exosuit after changing a toggle. Toggles that edit the same field (flak x5 / flak
-- zero) must not be on together: the second is refused (CONFLICT) and logged.
local mod=hd2.mod()
local BUILD='0.1.0 BREAKTHROUGH'
mod:log('BreakthroughProof '..BUILD..' BUILD: flak cannon spread x5 and shield plate 5x health are on by default; flak '
    ..'zero spread, shield plate armor 5, shield arm 5x health and Patriot minigun zero spread are off (MODS tab). '
    ..'Call in a new Exosuit after each change.')
local page=hd2.options({id='breakthrough_proof',title='Breakthrough Proof'})
local function report(label)
    return function(status,info)
        mod:log(label..': '..tostring(info and info.previous)..' -> '..tostring(status)
            ..(info and info.error and(': '..tostring(info.error))or''))
    end
end
local F=hd2.fields
local breakthrough=hd2.vehicle('EXO-55 Breakthrough Exosuit')
local flak=breakthrough:weapon('right_gun')
local shield=breakthrough:shield()
local tests={
    {id='flak_spread_x5',label='Flak cannon spread x5',default=true,target=flak,changes={
        {field=F.weapon.horizontal_spread,expect=200,value=1000},{field=F.weapon.vertical_spread,expect=200,value=1000}}},
    {id='flak_spread_zero',label='Flak cannon zero spread (x5 off)',default=false,target=flak,changes={
        {field=F.weapon.horizontal_spread,expect=200,value=0},{field=F.weapon.vertical_spread,expect=200,value=0}}},
    {id='shield_plate_health_x5',label='Shield plate 5x health',default=true,target=shield,changes={
        {field=F.zone.health,expect=5000,value=25000}}},
    {id='shield_plate_armor_5',label='Shield plate armor 5',default=false,target=shield,changes={
        {field=F.zone.armor,expect=4,value=5}}},
    {id='shield_arm_health_x5',label='Shield arm 5x health',default=false,target=shield,changes={
        {field=F.entity.health,expect=800,value=4000}}},
    {id='patriot_minigun_zero_spread',label='Patriot minigun zero spread',default=false,
        target=hd2.vehicle('EXO-45 Patriot Exosuit'):weapon('right_gun'),changes={
        {field=F.weapon.horizontal_spread,expect=50,value=0},{field=F.weapon.vertical_spread,expect=50,value=0}}},
}
for _,t in ipairs(tests)do
    local toggle=page:toggle({id=t.id,label=t.label,default=t.default})
    hd2.ensure({enabled=toggle,transaction={id='breakthrough-'..t.id,target=t.target,allow_unverified_effect=true,
        changes=t.changes},on_status=report(t.label)})
end
