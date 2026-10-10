local hd2=require('mods/skyeshade/hd2runtime')
-- UserRequestsProof 0.1.0 (HD2Runtime 0.30.4, development only): live tests for three user requests.
--   1. Charges before cooldown: hd2.fields.stratagem.rearm_pool puts a stratagem into the Eagle Rearm pool, so its
--      max_uses become charges refilled together by Eagle Rearm (docs/stratagem-uses.md "Charges before cooldown",
--      research/docs/stratagem-charges-F5FEE03DCFDB.md).
--   2. Orbital Railcannon targeting: orbital.search_radius / movement_speed / duration / fire_delay on the strike, and
--      the Orbital Laser's orbital.retarget_interval (docs/stratagem-authoring.md "Orbital targeting",
--      research/docs/orbital-targeting-F5FEE03DCFDB.md).
--   3. Hot-Shot fire modes: the game's fire-mode selector bound on a free input together with the extra modes
--      (docs/fire-modes.md "Adding the selector", research/docs/fire-mode-selector-F5FEE03DCFDB.md).
-- One options toggle per test (MODS tab, page "User Requests Proof"). Toggles that edit the same field must not be on
-- together (the second is refused, CONFLICT, and logged). When each takes effect: the charges at the next mission
-- (write them on the ship), the Railcannon / Laser values at the next call, the fire modes when the weapon is next
-- built (equip it again on the ship or redeploy).
local mod=hd2.mod()
local BUILD='0.1.0 USER REQUESTS'
mod:log('UserRequestsProof '..BUILD..' BUILD: Orbital Laser 5 charges, Railcannon search radius 200 m, Railcannon '
    ..'tracking x5 and the Hot-Shot single/auto selector are on by default; everything else is off (MODS tab).')
local page=hd2.options({id='user_requests_proof',title='User Requests Proof'})
local function report(label)
    return function(status,info)
        mod:log(label..': '..tostring(info and info.previous)..' -> '..tostring(status)
            ..(info and info.error and(': '..tostring(info.error))or''))
    end
end
local F=hd2.fields
local laser=hd2.stratagem('Orbital Laser')
local rail=hd2.stratagem('Orbital Railcannon Strike')
local hotshot=hd2.weapon('R/40-K Hot-Shot Marksman Rifle')
local tests={
    -- 1. Charges before cooldown (the Eagle Rearm pool)
    {id='laser_charges',label='Orbital Laser 5 charges (15 s apart, Eagle Rearm refills)',default=true,target=laser,
        changes={{field=F.stratagem.max_uses,expect=3,value=5},
        {field=F.stratagem.definition_cooldown,expect=300,value=15},
        {field=F.stratagem.rearm_pool,expect='none',value='eagle_rearm'}}},
    {id='railcannon_charges',label='Railcannon 3 charges (15 s apart, Eagle Rearm refills)',default=false,target=rail,
        changes={{field=F.stratagem.max_uses,expect='unlimited',value=3},
        {field=F.stratagem.definition_cooldown,expect=180,value=15},
        {field=F.stratagem.rearm_pool,expect='none',value='eagle_rearm'}}},
    -- 2. Orbital targeting
    {id='railcannon_radius',label='Railcannon search radius 200 m (30)',default=true,target=rail,changes={
        {field=F.orbital.search_radius,expect=30,value=200}}},
    {id='railcannon_radius_small',label='Railcannon search radius 3 m (control; 200 m off)',default=false,target=rail,
        changes={{field=F.orbital.search_radius,expect=30,value=3}}},
    {id='railcannon_tracking',label='Railcannon tracking x5 (90 -> 450)',default=true,target=rail,changes={
        {field=F.orbital.movement_speed,expect=90,value=450}}},
    {id='railcannon_slow_tracking',label='Railcannon tracking x0.1 (90 -> 9; x5 off)',default=false,target=rail,
        changes={{field=F.orbital.movement_speed,expect=90,value=9}}},
    {id='railcannon_quick_shot',label='Railcannon shot after 0.5 s (1.7)',default=false,target=rail,changes={
        {field=F.orbital.fire_delay,expect=1.7,value=0.5}}},
    {id='railcannon_long_beam',label='Railcannon targeting beam 2 -> 8 s',default=false,target=rail,changes={
        {field=F.orbital.duration,expect=2,value=8}}},
    {id='laser_retarget',label='Orbital Laser re-target every 0.25 s (1)',default=false,
        target=laser:attack('beam'),changes={{field=F.orbital.retarget_interval,expect=1,value=0.25}}},
    {id='laser_no_retarget',label='Orbital Laser re-target every 30 s (control; 0.25 s off)',default=false,
        target=laser:attack('beam'),changes={{field=F.orbital.retarget_interval,expect=1,value=30}}},
    -- 3. Fire-mode selector
    {id='hotshot_single_auto',label='Hot-Shot single/auto selector',default=true,target=hotshot,changes={
        {field=F.fire_mode.modes,expect={'single'},value={'single','automatic'}},
        {field=F.weapon_function.left,expect='none',value='fire_mode'}}},
    {id='hotshot_three',label='Hot-Shot single/auto/burst selector (single/auto off)',default=false,target=hotshot,
        changes={{field=F.fire_mode.modes,expect={'single'},value={'single','automatic','burst'}},
        {field=F.weapon_function.left,expect='none',value='fire_mode'}}},
    {id='mg43_single',label='MG-43: auto/single selector beside its rate selector',default=false,
        target=hd2.support_weapon('MG-43 Machine Gun'),changes={
        {field=F.fire_mode.modes,expect={'automatic'},value={'automatic','single'}},
        {field=F.weapon_function.left,expect='none',value='fire_mode'}}},
}
for _,t in ipairs(tests)do
    local toggle=page:toggle({id=t.id,label=t.label,default=t.default})
    hd2.ensure({enabled=toggle,transaction={id='user-requests-'..t.id,target=t.target,allow_unverified_effect=true,
        changes=t.changes},on_status=report(t.label)})
end
