local hd2=require('mods/skyeshade/hd2runtime')
-- Live test for the charge fields (hd2.fields.charge.*, docs/support-weapon-api.md "Charge",
-- research/docs/railgun-charge-F5FEE03DCFDB.md). Every field is a member of the weapon's OWN WeaponChargeComponent
-- record, read live by the native charge code every frame: an APPLIED write takes effect at once, also on a Railgun
-- already in your hands. Not yet shown in game: the new fields need allow_unverified_effect (the overcharge explosion
-- of another weapon also allow_unverified_reference). The charge times are older ids and need no acknowledgement.
--
-- Railgun fire modes: Safe (the charge stops at "full" and waits for release) and Unsafe (it keeps charging and the
-- weapon explodes at the overcharge time). Toggle the mode with the weapon-function key.
local BANNER='RAILGUN CHARGE 0.1.0 BUILD'
local mod=hd2.mod()
local rail=hd2.support_weapon('RS-422 Railgun')
local arc=hd2.support_weapon('ARC-3 Arc Thrower')
local options=hd2.options({id='railgun_charge_test',title='Railgun Charge Test'})
local slow=options:toggle({id='slow_charge',label='Slow charge',default=true,
    description='Charge times 0.45 / 0.5 / 3 s -> 0.05 / 2 / 8 s (minimum / full / overcharge).'})
local no_explode=options:toggle({id='no_explode',label='No overcharge explosion',default=false,
    description='Unsafe: reaching the overcharge time no longer fires and destroys the Railgun.'})
local hold_limit=options:toggle({id='hold_limit',label='5 s hold limit',default=false,
    description='Unsafe: overcharged for 5 s, the Railgun explodes WITHOUT firing (use with No overcharge explosion).'})
local auto_fire=options:toggle({id='auto_fire',label='Auto fire at full charge',default=false,
    description='Safe: the shot leaves by itself as soon as the charge is full, trigger still held.'})
local crawl=options:toggle({id='crawl_shot',label='Crawling minimum shot',default=false,
    description='Projectile speed multiplier at minimum charge 0.7 -> 0.05.'})
local weak_ap=options:toggle({id='weak_ap',label='Weak overcharged armor penetration',default=false,
    description='Armor-penetration multiplier at full overcharge 1.0 -> 0.2 (AP 5 -> 1).'})
local huge=options:toggle({id='huge_damage',label='Huge overcharged damage',default=false,
    description='Damage multiplier at full overcharge 2.5 -> 10.'})
local epoch=options:toggle({id='epoch_blast',label='Epoch overcharge explosion',default=false,
    description='The Railgun overcharge failure spawns the PLAS-45 Epoch explosion (loads the Epoch package).'})
local burst=options:toggle({id='arc_burst',label='Arc Thrower 3-arc burst',default=false,
    description='ARC-3: 3 arcs per charge, 0.25 s apart (vanilla 1).'})
mod:log(BANNER..': RS-422 Railgun charge times, overcharge explosion and limit, auto fire, speed / AP / damage '
    ..'multipliers, Epoch explosion; ARC-3 burst (MODS page "Railgun Charge Test"; APPLIED lines follow)')
return {
    hd2.ensure({enabled=slow,transaction={id='railgun-charge-times',target=rail,changes={
        {field=hd2.fields.charge.level_1,expect=0.45,value=0.05},
        {field=hd2.fields.charge.level_2,expect=0.5,value=2},
        {field=hd2.fields.charge.level_3,expect=3,value=8}}}}),
    hd2.ensure({enabled=no_explode,patch={id='railgun-no-explode',target=rail,allow_unverified_effect=true,
        field=hd2.fields.charge.explode_at_overcharge,expect=true,value=false}}),
    hd2.ensure({enabled=hold_limit,patch={id='railgun-hold-limit',target=rail,allow_unverified_effect=true,
        field=hd2.fields.charge.overcharge_limit_seconds,expect=0,value=5}}),
    hd2.ensure({enabled=auto_fire,patch={id='railgun-auto-fire',target=rail,allow_unverified_effect=true,
        field=hd2.fields.charge.auto_fire_at_full,expect=false,value=true}}),
    hd2.ensure({enabled=crawl,patch={id='railgun-crawl-shot',target=rail,allow_unverified_effect=true,
        field=hd2.fields.charge.speed_multiplier_min,expect=0.7,value=0.05}}),
    hd2.ensure({enabled=weak_ap,patch={id='railgun-weak-ap',target=rail,allow_unverified_effect=true,
        field=hd2.fields.charge.penetration_multiplier_overcharge,expect=1,value=0.2}}),
    hd2.ensure({enabled=huge,patch={id='railgun-huge-damage',target=rail,allow_unverified_effect=true,
        field=hd2.fields.charge.damage_multiplier_overcharge,expect=2.5,value=10}}),
    hd2.ensure({enabled=epoch,patch={id='railgun-epoch-blast',target=rail,allow_unverified_effect=true,
        allow_unverified_reference=true,field=hd2.fields.charge.overcharge_explosion,expect='RS-422 Railgun',
        value='PLAS-45 Epoch'}}),
    hd2.ensure({enabled=burst,transaction={id='arc-burst',target=arc,allow_unverified_effect=true,changes={
        {field=hd2.fields.charge.burst_shots,expect=0,value=3},
        {field=hd2.fields.charge.burst_interval_seconds,expect=0,value=0.25}}}}),
}
