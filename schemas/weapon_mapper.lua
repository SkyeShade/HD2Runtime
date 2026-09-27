-- Read-only mapper fields correlated from complete current-build records.
-- These offsets are structural/correlation evidence pending gameplay confirmation.
local source='research/primary-weapon-field-correlation-F5FEE03DCFDB.json'
local slot_capacity_source='research/weapon-slot-capacity-F5FEE03DCFDB.json'
local function evidence(comparisons)
    return {source=source,structural_candidate=true,schema_labelled=false,
        correlation_proven=true,current_live_ownership_proven=false,
        gameplay_proven=false,native_consumer_proven=false,
        pending_gameplay_confirmation=true,confidence_evidence=comparisons}
end
return {
    fields={
        weapon_slot={structure='LoadoutPackageComponentData',offset=0,storage='u32',
            value_type='enum',tags={[0x82C32E74]='primary',[0x89747DEC]='secondary'},
            evidence={source=slot_capacity_source,structural_candidate=true,schema_labelled=true,
                correlation_proven=true,current_live_ownership_proven=false,gameplay_proven=false,
                native_consumer_proven=false,pending_gameplay_confirmation=true,
                confidence_evidence='54/54 uniquely identified anchors separated: 43 primary tag 0x82C32E74, 11 secondary tag 0x89747DEC'}},
        capacity={value_type='integer',unit='rounds',
            magazine={structure='WeaponMagazineComponentData',offset=136,storage='u32',chambered_offset=156},
            rounds={structure='WeaponRoundsComponentData',offset=72,storage='f32',chambered_offset=104},
            default_customizations={structure='WeaponCustomizationComponentData',offset=0,stride=8,count=10,none=0,magazine=5},
            evidence={source=slot_capacity_source,structural_candidate=true,schema_labelled=true,
                correlation_proven=true,current_live_ownership_proven=false,gameplay_proven=false,
                native_consumer_proven=false,pending_gameplay_confirmation=true,
                confidence_evidence='35/35 unambiguous anchors exact: 30 direct WeaponMagazine Capacity and 5 WeaponRounds MagazineCapacity[0]; default magazine customizations fail closed'}},
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
    unmapped={'capacity when supplied by a default magazine customization AddPath'},
}
