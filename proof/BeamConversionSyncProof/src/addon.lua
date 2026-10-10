local hd2=require('mods/skyeshade/hd2runtime')
-- BeamConversionSyncProof 0.1.0 (HD2Runtime beam conversion sync, development only; docs/beam-conversion.md
-- "Multiplayer"; README.md has the two-machine test plan). Public API only: hd2.weapon(name):beam_conversion() and
-- hd2.ensure. The Runtime itself publishes this machine's conversions under the lobby key `hd2bc`, reads every other
-- member's and logs `BEAM CONVERSION SYNC:` lines; this proof only makes the conversions to publish.
-- Options (MODS tab, page "Beam Conversion Sync Proof"), all off by default:
--   * Sickle: Trident pulses;
--   * Liberator: Trident pulses, at the rate of
--   * Liberator rate: 600 rpm (the same on both machines) or 450 rpm (deliberately different: another digest).
-- A conversion is applied ONLY SOLO and only while no instance of that weapon exists on this machine: set the options
-- with the weapons unequipped and the armory closed, wait for APPLIED, then equip. Choose the Liberator rate BEFORE
-- turning the Liberator on (a converted weapon's rate set by another value of this option is a CONFLICT).
-- NEVER carry a weapon type another player has converted: their game crashes when it spawns (even if you converted it
-- too: research/docs/beam-conversion-mp-sync-F5FEE03DCFDB.md). Restart the game after the session.
local mod=hd2.mod()
local BUILD='0.1.0 BEAM CONVERSION SYNC'
mod:log('BeamConversionSyncProof '..BUILD..' BUILD: every option is off; conversions apply SOLO ONLY; never carry a '
    ..'weapon type another player converted; restart the game after the session.')
local page=hd2.options({id='beam_conversion_sync_proof',title='Beam Conversion Sync Proof'})
local F=hd2.fields
local function report(label)
    return function(status,info)
        mod:log(label..': '..tostring(info and info.previous)..' -> '..tostring(status)
            ..(info and info.error and(': '..tostring(info.error))or''))
    end
end
local ON={field=F.beam_conversion.enabled,expect=false,value=true}
local sickle=page:toggle({id='sickle',label='Sickle: Trident pulses',default=false})
local liberator=page:toggle({id='liberator',label='Liberator: Trident pulses',default=false})
local rate=page:choice({id='liberator_rate',label='Liberator rate',default=1,values={600,450},
    choices={'600 rpm (same on both machines)','450 rpm (deliberately different)'},
    description='beam.fire_rate of the converted Liberator; choose it before turning the Liberator on'})
local tests={
    {id='sickle',label='Sickle: Trident pulses',toggle=sickle,target=hd2.weapon('LAS-16 Sickle'):beam_conversion(),
        changes={ON}},
    {id='liberator',label='Liberator: Trident pulses',toggle=liberator,
        target=hd2.weapon('AR-23 Liberator'):beam_conversion(),changes={ON,
        {field=F.beam.fire_rate,expect=300,value=rate}}},
}
for _,t in ipairs(tests)do
    -- recover: a busy gate (a live weapon, another player, the Trident package loading) is retried until it clears;
    -- with another player present the apply waits (NOT_SOLO, with the sync's decision in the reason).
    hd2.ensure({enabled=t.toggle,recover={delay=5,max_delay=20},on_status=report(t.label),transaction={
        id='beamsync-'..t.id,target=t.target,changes=t.changes,allow_component_swap=true,
        allow_unverified_effect=true}})
end
-- A one-line status of both conversions every 30 s while either option is on (read-only).
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
                ..(st.settings and(' '..st.settings.fire_rate..' rpm')or'')..(st.live and(' live '..st.live)or'')
                ..(st.lobby and(' lobby '..tostring(st.lobby))or'')
        end
    end
    if#parts>0 then mod:log('STATUS: '..table.concat(parts,'; '))end
end)
