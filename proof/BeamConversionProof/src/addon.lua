local hd2=require('mods/skyeshade/hd2runtime')
-- BeamConversionProof 0.1.0 (HD2Runtime beam conversion, development only; docs/beam-conversion.md). Public API only:
-- hd2.weapon(name):beam_conversion() and hd2.ensure. One toggle per test on the MODS tab (page "Beam Conversion
-- Proof"), all off by default. SOLO ONLY. A conversion is written only while NO instance of that weapon exists on this
-- machine: equip OTHER weapons and keep the armory closed, turn the toggle on, wait for "APPLIED" in the log (or the
-- toggle's status line), then equip the converted weapon and deploy. To turn a test off, unequip the weapon first.
-- Restart the game after the session (a weapon spawned while converted can leave a stale private copy behind).
local mod=hd2.mod()
local BUILD='0.1.0 BEAM CONVERSION'
mod:log('BeamConversionProof '..BUILD..' BUILD: every test is off; SOLO ONLY; unequip a weapon before its toggle, '
    ..'restart the game after the session.')
local page=hd2.options({id='beam_conversion_proof',title='Beam Conversion Proof'})
local F=hd2.fields
local function report(label)
    return function(status,info)
        mod:log(label..': '..tostring(info and info.previous)..' -> '..tostring(status)
            ..(info and info.error and(': '..tostring(info.error))or''))
    end
end
local ON={field=F.beam_conversion.enabled,expect=false,value=true}
local tests={
    {id='sickle',label='Sickle: Trident pulses',target=hd2.weapon('LAS-16 Sickle'):beam_conversion(),
        changes={ON}},
    {id='double_edge',label='Double-Edge Sickle: Trident pulses',
        target=hd2.weapon('LAS-17 Double-Edge Sickle'):beam_conversion(),changes={ON}},
    {id='sai',label='Sai: Trident pulses',target=hd2.weapon('LAS-12 Sai'):beam_conversion(),changes={ON}},
    {id='talon_600',label='Talon: Trident pulses at 600 rpm',
        target=hd2.weapon('LAS-58 Talon'):beam_conversion(),changes={ON,
        {field=F.beam.fire_rate,expect=300,value=600}}},
    {id='liberator_x10',label='Liberator: Trident pulses, damage x10, AP 4',
        target=hd2.weapon('AR-23 Liberator'):beam_conversion(),changes={ON,
        {field=F.damage.player_standard_damage,expect=60,value=600},
        {field=F.damage.player_durable_damage,expect=6,value=60},
        {field=F.damage.ap_direct,expect=2,value=4},{field=F.damage.ap_slight,expect=2,value=4},
        {field=F.damage.ap_large,expect=2,value=4}}},
    {id='reprimand_range',label='Reprimand: Trident pulses, range 100 m',
        target=hd2.weapon('SMG-32 Reprimand'):beam_conversion(),changes={ON,
        {field=F.beam.length,expect=200,value=100}}},
    -- The real LAS-13 Trident's own pulse (not a conversion): the pulse caps the rate.
    {id='trident_fast',label='Trident: 600 rpm with a 0.05 s pulse',
        target=hd2.weapon('LAS-13 Trident'),transaction_ack={allow_unverified_effect=true},changes={
        {field=F.beam.fire_rate,expect=300,value=600},{field=F.beam.pulse_seconds,expect=0.15,value=0.05}}},
    {id='trident_capped',label='Trident control: 600 rpm, 0.15 s pulse (capped)',
        target=hd2.weapon('LAS-13 Trident'),transaction_ack={allow_unverified_effect=true},changes={
        {field=F.beam.fire_rate,expect=300,value=600}}},
}
for _,t in ipairs(tests)do
    local toggle=page:toggle({id=t.id,label=t.label,default=false})
    t.toggle=toggle
    local body={id='beamconv-'..t.id,target=t.target,changes=t.changes,allow_unverified_effect=true}
    if not t.transaction_ack then body.allow_component_swap=true end
    -- recover: a busy gate (a live weapon, another player, the Trident package loading) is retried until it clears.
    hd2.ensure({enabled=toggle,recover={delay=5,max_delay=20},transaction=body,on_status=report(t.label)})
end
-- A one-line status of every conversion every 30 s while any test is on (read-only).
local elapsed=0
hd2.on_frame(function(dt)
    elapsed=elapsed+(dt or 0)
    if elapsed<30 then return end
    elapsed=0
    local parts={}
    for _,t in ipairs(tests)do
        if not t.transaction_ack and t.toggle:get()==true then
            local st=t.target:status()
            if st.ok and st.state~='vanilla'then
                parts[#parts+1]=t.target.weapon..' '..tostring(st.state)..(st.settings and(' '..st.settings.fire_rate
                    ..' rpm, '..string.format('%.3g',st.settings.pulse_seconds)..' s')or'')
                    ..(st.pair and(' own rows '..st.pair.beamType..'/'..st.pair.damageInfo)or'')
                    ..(st.live and(' live '..st.live)or'')
            end
        end
    end
    if#parts>0 then mod:log('STATUS: '..table.concat(parts,'; '))end
end)
