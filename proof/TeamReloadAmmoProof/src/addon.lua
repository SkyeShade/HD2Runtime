local hd2=require('mods/skyeshade/hd2runtime')
-- TeamReloadAmmoProof 0.1.0 (HD2Runtime 0.30.4, development only): team-reload weapons carrying spares of their own,
-- and bigger team-reload backpacks (docs/support-weapon-api.md "Team-reload weapons", docs/backpack-ammo.md). One
-- options toggle per test; call a new weapon in after changing one (the counts are set when it spawns).
local mod=hd2.mod()
local BUILD='0.1.0 TEAM RELOAD'
mod:log('TeamReloadAmmoProof '..BUILD..' BUILD: GR-8 3 own spares, GR-8 backpack 12 and AC-8 backpack 20 are on by '
    ..'default; GR-8 backpack starts with 2, W.A.S.P. 2 own magazines and Spear backpack 8 are off (MODS tab). '
    ..'Call a new weapon in after a change.')
local page=hd2.options({id='team_reload_ammo_proof',title='Team Reload Ammo Proof'})
local function report(label)
    return function(status,info)
        mod:log(label..': '..tostring(info and info.previous)..' -> '..tostring(status)
            ..(info and info.error and(': '..tostring(info.error))or''))
    end
end
local F=hd2.fields
local gr8=hd2.support_weapon('GR-8 Recoilless Rifle')
local wasp=hd2.support_weapon('StA-X3 W.A.S.P. Launcher')
local tests={
    {id='gr8_own_spares',label='GR-8 carries 3 spare rockets of its own',default=true,target=gr8,changes={
        {field=F.magazine.spare_magazines,expect=0,value=3},{field=F.magazine.starting_magazines,expect=0,value=3},
        {field=F.magazine.magazines_from_supply,expect=6,value=3}}},
    {id='gr8_backpack_12',label='Recoilless backpack holds 12',default=true,target=gr8:backpack(),changes={
        {field=F.deposit.capacity,expect=5,value=12}}},
    {id='ac8_backpack_20',label='AC-8 backpack holds 20 magazines',default=true,
        target=hd2.support_weapon('AC-8 Autocannon'):backpack(),changes={
        {field=F.deposit.capacity,expect=10,value=20},{field=F.deposit.refill_amount,expect=5,value=10}}},
    {id='gr8_backpack_starts_2',label='Recoilless backpack starts with 2',default=false,target=gr8:backpack(),changes={
        {field=F.deposit.start_amount,expect=-1,value=2}}},
    {id='wasp_own_spares',label='W.A.S.P. carries 2 magazines of its own',default=false,target=wasp,changes={
        {field=F.magazine.spare_magazines,expect=0,value=2},{field=F.magazine.starting_magazines,expect=0,value=2}}},
    {id='spear_backpack_8',label='Spear backpack holds 8',default=false,
        target=hd2.support_weapon('FAF-14 Spear'):backpack(),changes={
        {field=F.deposit.capacity,expect=4,value=8}}},
}
for _,t in ipairs(tests)do
    local toggle=page:toggle({id=t.id,label=t.label,default=t.default})
    hd2.ensure({enabled=toggle,transaction={id='team-reload-'..t.id,target=t.target,allow_unverified_effect=true,
        changes=t.changes},on_status=report(t.label)})
end
