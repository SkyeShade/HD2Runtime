local hd2=require('mods/skyeshade/hd2runtime')
-- Live test: the SH-32 Shield Generator Pack recharge (research/equipment-coverage-F5FEE03DCFDB.json). The three
-- members hold exact published values on three independent shields (SH-32 60 s / 12 s / 150 per s, SH-51 barrier
-- 3 / 6 / 300, FX-12 relay 0.01 / 45 / 400). Copied into a pack when it spawns: call in a fresh one after APPLY.
local pack=hd2.backpack('SH-32 Shield Generator Pack')
local options=hd2.options({id='shield_generator_pack_test',title='Shield Pack Test'})
local quick=options:toggle({id='fast_recharge',label='Fast recharge',default=true,
    description='A damaged (unbroken) shield starts recharging after 2 s instead of 60 s.'})
local restart=options:toggle({id='fast_restart',label='Fast restart',default=true,
    description='A broken shield restarts after 2 s instead of 12 s.'})
local slow=options:toggle({id='slow_refill',label='Slow refill',default=false,
    description='The shield refills 10 health per second instead of 150 (15 s from empty).'})
return {
    hd2.ensure({enabled=quick,patch={id='shield-pack-recharge-delay',target=pack,allow_unverified_effect=true,
        field=hd2.fields.shield.recharge_delay,expect=60,value=2}}),
    hd2.ensure({enabled=restart,patch={id='shield-pack-restart',target=pack,allow_unverified_effect=true,
        field=hd2.fields.shield.broken_recharge_delay,expect=12,value=2}}),
    hd2.ensure({enabled=slow,patch={id='shield-pack-rate',target=pack,allow_unverified_effect=true,
        field=hd2.fields.shield.recharge_rate,expect=150,value=10}}),
}
