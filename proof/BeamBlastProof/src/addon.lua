local hd2=require('mods/skyeshade/hd2runtime')
-- BeamBlastProof 0.1.0 (HD2Runtime 0.30.4, development only): the firing charge (wind-up) of heat weapons and the
-- LAS-13 Trident's pulsed beam on another beam weapon. One options toggle per test; re-equip after changing one.
local mod=hd2.mod()
local BUILD='0.1.0 BEAM BLASTS'
mod:log('BeamBlastProof '..BUILD..' BUILD: Trident-like Scythe, instant Sickle and a 2 s Double-Edge wind-up are on '
    ..'by default; Trident long pulse and 6 beams are off (MODS tab). Re-equip the weapon after a change.')
local page=hd2.options({id='beam_blast_proof',title='Beam Blast Proof'})
local function report(label)
    return function(status,info)
        mod:log(label..': '..tostring(info and info.previous)..' -> '..tostring(status)
            ..(info and info.error and(': '..tostring(info.error))or''))
    end
end
local reviewed=require('hd2runtime/api/inspect').reviewed
local scythe,sickle=hd2.weapon('LAS-5 Scythe'),hd2.weapon('LAS-16 Sickle')
local double,trident=hd2.weapon('LAS-17 Double-Edge Sickle'),hd2.weapon('LAS-13 Trident')
local tests={
    {id='trident_scythe',label='Trident-like Scythe',default=true,target=scythe,changes={
        {field='beam.fire_mode',expect=4,value=6},{field='beam.fire_rate',expect=reviewed(scythe,'beam.fire_rate'),value=300},
        {field='beam.pulse_beams',expect=1,value=2},{field='beam.pulse_seconds',expect=0,value=0.15}}},
    {id='instant_sickle',label='Instant Sickle (no wind-up)',default=true,target=sickle,changes={
        {field='heat.firing_charge',expect=100,value=0}}},
    {id='slow_double_edge',label='Double-Edge Sickle: 2 s wind-up',default=true,target=double,changes={
        {field='heat.charge_gain_per_second',expect=200,value=50}}},
    {id='trident_long_pulse',label='Trident: 1 s pulses',default=false,target=trident,changes={
        {field='beam.pulse_seconds',expect=reviewed(trident,'beam.pulse_seconds'),value=1}}},
    {id='trident_six_beams',label='Trident: 6 beams per pulse',default=false,target=trident,changes={
        {field='beam.pulse_beams',expect=2,value=6}}},
}
for _,t in ipairs(tests)do
    local toggle=page:toggle({id=t.id,label=t.label,default=t.default})
    hd2.ensure({enabled=toggle,transaction={id='beam-blast-'..t.id,target=t.target,allow_unverified_effect=true,
        changes=t.changes},on_status=report(t.label)})
end
