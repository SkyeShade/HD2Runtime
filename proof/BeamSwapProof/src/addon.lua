local hd2=require('mods/skyeshade/hd2runtime')
-- BeamSwapProof 0.1.0 (HD2Runtime 0.30.4, development only): beam swaps (docs/attack-outputs.md "Beam swaps"). A beam
-- weapon's BeamType reference, on its active beam source, takes another weapon's beam (its BeamSettings row: length,
-- damage, hit effects, visuals); the host keeps its own fire mode, rate, heat and sounds. One options toggle per test;
-- re-equip the weapon, resupply or call a new one in after a change (the beam is copied when the weapon is built).
local mod=hd2.mod()
local BUILD='0.1.0 BEAM SWAPS'
mod:log('BeamSwapProof '..BUILD..' BUILD: Scythe <- Trident beam, LAS-98 <- Meltagun beam, Laser Sentry <- Trident beam '
    ..'and the Liberator Talon-bolt control are on by default; Dagger <- LAS-98 and Trident <- Scythe are off (MODS tab).')
local page=hd2.options({id='beam_swap_proof',title='Beam Swap Proof'})
local function report(label)
    return function(status,info)
        mod:log(label..': '..tostring(info and info.previous)..' -> '..tostring(status)
            ..(info and info.error and(': '..tostring(info.error))or''))
    end
end
-- A beam swap through the host's own beam source (its weapon record, or the Scythe's default muzzle).
local function beam(label,source,donor,shared)
    assert(source.writable,label..': '..tostring(source.reason))
    return {target=source.target,field=hd2.fields.attack.beam,expect=source.expect,value=hd2.attack_output(donor),
        allow_shared=shared or nil}
end
local scythe=hd2.weapon('LAS-5 Scythe'):beam_source()
local las98=hd2.support_weapon('LAS-98 Laser Cannon'):beam_source()
local sentry=hd2.stratagem('A/LAS-98 Laser Sentry'):attack('primary'):beam_source()
local dagger=hd2.weapon('LAS-7 Dagger'):beam_source()
local trident=hd2.weapon('LAS-13 Trident'):beam_source()
-- The control: a projectile weapon fires laser BOLTS (a projectile swap), never a beam.
local liberator=hd2.weapon('AR-23 Liberator'):projectile_source()
local tests={
    {id='scythe_trident',label='Scythe fires the Trident beam',default=true,
        request=beam('scythe',scythe,'LAS-13 Trident',true)},
    {id='las98_meltagun',label='LAS-98 fires the Meltagun beam',default=true,
        request=beam('las98',las98,'40-K Meltagun')},
    {id='sentry_trident',label='Laser Sentry fires the Trident beam',default=true,
        request=beam('sentry',sentry,'LAS-13 Trident')},
    {id='liberator_talon',label='Liberator fires Talon laser bolts (control)',default=true,
        request={target=liberator.target,field=hd2.fields.ammunition.projectile,expect=liberator.expect,
            value=hd2.attack_output('LAS-58 Talon'),allow_shared=true}},
    {id='dagger_las98',label='Dagger fires the LAS-98 beam',default=false,
        request=beam('dagger',dagger,'LAS-98 Laser Cannon')},
    {id='trident_scythe',label='Trident fires the Scythe beam',default=false,
        request=beam('trident',trident,'LAS-5 Scythe')},
}
for _,t in ipairs(tests)do
    local toggle=page:toggle({id=t.id,label=t.label,default=t.default})
    local patch=t.request
    patch.id='beam-swap-'..t.id;patch.allow_unverified_reference=true;patch.allow_unverified_effect=true
    hd2.ensure({enabled=toggle,patch=patch,on_status=report(t.label)})
end
