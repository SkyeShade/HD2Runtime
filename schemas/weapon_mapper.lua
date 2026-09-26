-- Read-only mapper fields correlated from complete current-build records.
-- These offsets are structural/correlation evidence pending gameplay confirmation.
local source='research/primary-weapon-field-correlation-F5FEE03DCFDB.json'
local function evidence(comparisons)
    return {source=source,structural_candidate=true,schema_labelled=false,
        correlation_proven=true,current_live_ownership_proven=false,
        gameplay_proven=false,native_consumer_proven=false,
        pending_gameplay_confirmation=true,confidence_evidence=comparisons}
end
return {
    fields={
        fire_rate={structure='ProjectileWeaponComponentData',offset=8,storage='f32',
            value_type='number',unit='rounds_per_minute',tolerance=1,
            evidence=evidence('33/37 identities all-variant exact; 42/49 candidates exact; every identity has a matching variant')},
        pellet_count={structure='ProjectileSettings',offset=28,storage='u32',
            value_type='integer',unit='projectiles_per_shot',tolerance=0,
            evidence=evidence('5/5 wiki-labelled shotgun identities exact; no mismatches')},
        projectile_velocity={structure='ProjectileSettings',offset=32,storage='f32',
            value_type='number',unit='meters_per_second',tolerance=2,
            evidence=evidence('36/37 identities exact; 48/49 candidates exact')},
        projectile_mass={structure='ProjectileSettings',offset=36,storage='f32',
            value_type='number',unit='grams',tolerance=0.1,
            evidence=evidence('36/37 identities exact; 48/49 candidates exact')},
        drag={structure='ProjectileSettings',offset=40,storage='f32',
            value_type='number',unit='factor',tolerance=0.01,
            evidence=evidence('36/37 identities exact; 48/49 candidates exact')},
        gravity={structure='ProjectileSettings',offset=44,storage='f32',
            value_type='number',unit='factor',tolerance=0.01,
            evidence=evidence('37/37 identities and 49/49 candidates exact')},
    },
    unmapped={'capacity'},
}
