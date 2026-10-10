local hd2=require('mods/skyeshade/hd2runtime')
-- WaspRocketProof 0.1.0 (HD2Runtime 0.30.4, development only): the missile the StA-X3 W.A.S.P. Launcher (and the Spear
-- and P-33) spawns per shot, authored through its own SeekingMissile record (docs/support-weapon-api.md "Missiles",
-- research/docs/wasp-rocket-F5FEE03DCFDB.md). One options toggle per test. Speed, lifetime and turning apply to rockets
-- already in flight; the starting speed to the next rocket. Toggles that edit the same field (slow / fast) must not be
-- on together: the second is refused (CONFLICT) and logged.
local mod=hd2.mod()
local BUILD='0.1.0 WASP ROCKET'
mod:log('WaspRocketProof '..BUILD..' BUILD: W.A.S.P. slow rockets is on by default; fast rockets, short life, no '
    ..'turning, guidance after 2 s, big blast, slow programmable missile, slow Spear and slow P-33 are off (MODS tab). '
    ..'Turn slow off before fast.')
local page=hd2.options({id='wasp_rocket_proof',title='W.A.S.P. Rocket Proof'})
local function report(label)
    return function(status,info)
        mod:log(label..': '..tostring(info and info.previous)..' -> '..tostring(status)
            ..(info and info.error and(': '..tostring(info.error))or''))
    end
end
local F=hd2.fields
local wasp=hd2.support_weapon('StA-X3 W.A.S.P. Launcher')
local tests={
    {id='wasp_slow',label='W.A.S.P. slow rockets',default=true,target=wasp,changes={
        {field=F.missile.preferred_speed,expect=100,value=20},{field=F.missile.minimum_speed,expect=10,value=5},
        {field=F.missile.starting_speed,expect=10,value=5}}},
    {id='wasp_fast',label='W.A.S.P. fast rockets (slow off)',default=false,target=wasp,changes={
        {field=F.missile.preferred_speed,expect=100,value=300},{field=F.missile.acceleration,expect=200,value=2000}}},
    {id='wasp_short_life',label='W.A.S.P. rockets end after 1.5 s',default=false,target=wasp,changes={
        {field=F.missile.max_lifetime,expect=30,value=1.5}}},
    {id='wasp_no_turning',label='W.A.S.P. rockets do not turn',default=false,target=wasp,changes={
        {field=F.missile.turn_rate_at_max_angle,expect=15,value=0},{field=F.missile.turn_rate_aligned,expect=18,value=0}}},
    {id='wasp_guidance_2s',label='W.A.S.P. guidance after 2 s',default=false,target=wasp,changes={
        {field=F.missile.guidance_delay,expect=0.01,value=2}}},
    {id='wasp_big_blast',label='W.A.S.P. big blast (the carried row)',default=false,shared=true,
        target=wasp:attack('primary_impact'):explosion(),changes={
        {field=F.explosion.inner_radius,expect=2.5,value=6},{field=F.explosion.outer_radius,expect=5,value=12},
        {field=F.explosion.shockwave_radius,expect=7,value=16}}},
    {id='wasp_function_slow',label='W.A.S.P. programmable missile slow',default=false,target=wasp,changes={
        {field=F.function_missile.preferred_speed,expect=80,value=20},
        {field=F.function_missile.minimum_speed,expect=10,value=5}}},
    {id='spear_slow',label='Spear slow missile',default=false,target=hd2.support_weapon('FAF-14 Spear'),changes={
        {field=F.missile.preferred_speed,expect=100,value=25},{field=F.missile.minimum_speed,expect=10,value=5}}},
    {id='p33_slow',label='P-33 slow missiles',default=false,target=hd2.weapon('P-33 Missile Pistol'),changes={
        {field=F.missile.preferred_speed,expect=100,value=20},{field=F.missile.minimum_speed,expect=10,value=5}}},
}
for _,t in ipairs(tests)do
    local toggle=page:toggle({id=t.id,label=t.label,default=t.default})
    hd2.ensure({enabled=toggle,transaction={id='wasp-rocket-'..t.id,target=t.target,allow_unverified_effect=true,
        allow_shared=t.shared or nil,changes=t.changes},on_status=report(t.label)})
end
