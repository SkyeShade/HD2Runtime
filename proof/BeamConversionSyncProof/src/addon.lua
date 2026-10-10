local hd2=require('mods/skyeshade/hd2runtime')
-- BeamConversionSyncProof 0.2.0 (HD2Runtime beam conversion sync, development only; docs/beam-conversion.md
-- "Multiplayer"; README.md has the two-machine test plan). Public API only: hd2.weapon(name):beam_conversion() and
-- hd2.ensure. The Runtime itself publishes this machine's conversions under the lobby key `hd2bc` (hd2bc/2), reads
-- every other member's and logs `BEAM CONVERSION SYNC:` lines; this proof only makes the conversions to publish.
-- Options (MODS tab, page "Beam Conversion Sync Proof"), all off by default:
--   * Sickle: Trident pulses (ADD layout: allowed with other players when every member holds the identical conversion),
--     at the rate of
--   * Sickle rate: 600 rpm (the same on both machines) or 450 rpm (deliberately different: another digest);
--   * Talon: Trident pulses (ADD layout; converts in the lobby once the other player holds it);
--   * Liberator: Trident pulses (SWAP layout: solo only; restored at once when someone joins).
-- A conversion is written only while no instance of that weapon exists on this machine: set the options with the
-- weapons unequipped and the armory closed, wait for APPLIED, then equip. Choose the Sickle rate BEFORE turning the
-- Sickle on (a converted weapon's rate set by another value of this option is a CONFLICT).
-- NEVER carry a weapon type another player has SWAP-converted (the Liberator here): their game crashes when it spawns.
local mod=hd2.mod()
local BUILD='0.2.0 BEAM CONVERSION SYNC'
mod:log('BeamConversionSyncProof '..BUILD..' BUILD: every option is off; the Sickle and Talon (add layout) need the '
    ..'identical conversion on every machine; the Liberator (swap layout) is solo only; never carry a weapon type '
    ..'another player swap-converted.')
local page=hd2.options({id='beam_conversion_sync_proof',title='Beam Conversion Sync Proof'})
local F=hd2.fields
local function report(label)
    return function(status,info)
        mod:log(label..': '..tostring(info and info.previous)..' -> '..tostring(status)
            ..(info and info.error and(': '..tostring(info.error))or''))
    end
end
local ON={field=F.beam_conversion.enabled,expect=false,value=true}
local sickle=page:toggle({id='sickle',label='Sickle: Trident pulses (add layout)',default=false})
local rate=page:choice({id='sickle_rate',label='Sickle rate',default=1,values={600,450},
    choices={'600 rpm (same on both machines)','450 rpm (deliberately different)'},
    description='beam.fire_rate of the converted Sickle; choose it before turning the Sickle on'})
local talon=page:toggle({id='talon',label='Talon: Trident pulses (add layout)',default=false})
local liberator=page:toggle({id='liberator',label='Liberator: Trident pulses (swap layout, solo only)',default=false})
local tests={
    {id='sickle',label='Sickle: Trident pulses (add layout)',toggle=sickle,
        target=hd2.weapon('LAS-16 Sickle'):beam_conversion(),changes={ON,
        {field=F.beam.fire_rate,expect=300,value=rate}}},
    {id='talon',label='Talon: Trident pulses (add layout)',toggle=talon,
        target=hd2.weapon('LAS-58 Talon'):beam_conversion(),changes={ON}},
    {id='liberator',label='Liberator: Trident pulses (swap layout)',toggle=liberator,
        target=hd2.weapon('AR-23 Liberator'):beam_conversion(),changes={ON}},
}
for _,t in ipairs(tests)do
    -- recover: a busy gate (a live weapon, a lobby that does not agree, the Trident package loading) is retried until
    -- it clears: an add-layout apply waits NOT_AGREED, a swap-layout apply NOT_SOLO, with the sync's decision.
    hd2.ensure({enabled=t.toggle,recover={delay=5,max_delay=20},on_status=report(t.label),transaction={
        id='beamsync-'..t.id,target=t.target,changes=t.changes,allow_component_swap=true,
        allow_unverified_effect=true}})
end
-- A one-line status of the conversions every 30 s while any option is on (read-only).
local elapsed=0
hd2.on_frame(function(dt)
    elapsed=elapsed+(dt or 0)
    if elapsed<30 then return end
    elapsed=0
    local parts={}
    for _,t in ipairs(tests)do
        if t.toggle:get()==true then
            local st=t.target:status()
            parts[#parts+1]=t.target.weapon..' '..tostring(st.ok and st.state or('unreadable: '..tostring(st.reason)))
                ..' ['..tostring(st.layout)..']'..(st.settings and(' '..st.settings.fire_rate..' rpm')or'')
                ..(st.live and(' live '..st.live)or'')..(st.lobby and(' lobby '..tostring(st.lobby))or'')
        end
    end
    if#parts>0 then mod:log('STATUS: '..table.concat(parts,'; '))end
end)
