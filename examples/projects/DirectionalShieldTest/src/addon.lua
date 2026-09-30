local hd2=require('mods/skyeshade/hd2runtime')
-- Live test: the SH-51 Directional Shield (research/equipment-coverage-F5FEE03DCFDB.json). The backpack body (health
-- 400, armor Heavy: exact published) and the energy barrier are separate entities. The barrier is spawned through the
-- backpack's ShieldController (re-proven before every write) and owns the shield energy: capacity 1000, recharge
-- after 3 s, restart 6 s after breaking, 300 per s (exact published). Values are copied when the entity spawns: call
-- in a fresh SH-51 after APPLY.
local backpack=hd2.backpack('SH-51 Directional Shield')
local barrier=backpack:energy_shield()
local options=hd2.options({id='directional_shield_test',title='Directional Shield Test'})
local big=options:toggle({id='big_barrier',label='5000 shield',default=true,
    description='Barrier capacity 1000 -> 5000.'})
local outage=options:toggle({id='long_outage',label='Long outage',default=true,
    description='A broken barrier restarts after 20 s instead of 6 s.'})
local sturdy=options:toggle({id='sturdy_emitter',label='Sturdy emitter',default=false,
    description='Backpack body health 400 -> 4000 (the emitter on your back, not the barrier).'})
return {
    hd2.ensure({enabled=big,patch={id='sh51-capacity',target=barrier,allow_unverified_effect=true,
        field=hd2.fields.shield.entity_durability,expect=1000,value=5000}}),
    hd2.ensure({enabled=outage,patch={id='sh51-outage',target=barrier,allow_unverified_effect=true,
        field=hd2.fields.shield.broken_recharge_delay,expect=6,value=20}}),
    hd2.ensure({enabled=sturdy,patch={id='sh51-body',target=backpack,allow_unverified_effect=true,
        field=hd2.fields.entity.health,expect=400,value=4000}}),
}
