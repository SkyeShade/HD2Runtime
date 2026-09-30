local hd2=require('mods/skyeshade/hd2runtime')
-- Live test: Guard Dog backpacks, drones and drone weapons (research/equipment-coverage-F5FEE03DCFDB.json).
-- Chain: backpack -> the drone it deploys (backpack DepositComponent +24, re-proven before every write) -> the
-- drone's mounted weapon. Drone magazines are the backpack's (exact published 8 / 8 / 8 on the AR-23); the drone has
-- its own health (100) and body damage zone. Values are copied when the backpack or drone spawns: call in a fresh
-- backpack after APPLY.
local dog=hd2.backpack('AX/AR-23 Guard Dog')
local drone=dog:drone()
local gun=drone:weapon()
local rover=hd2.backpack('AX/LAS-5 Rover'):drone():weapon()
local k9=hd2.backpack('AX/ARC-3 K-9'):drone():weapon()
local options=hd2.options({id='guard_dog_test',title='Guard Dog Test'})
local reloads=options:toggle({id='more_reloads',label='AR-23: 20 drone magazines',default=true,
    description='The backpack holds and starts with 20 drone magazines instead of 8.'})
local tough=options:toggle({id='tough_dog',label='AR-23: tough drone',default=true,
    description='Drone health 100 -> 2000 (main health and its body damage zone).'})
local drum=options:toggle({id='drum',label='AR-23: 200-round gun',default=true,
    description='The drone gun fires 200 rounds before it reloads instead of 45.'})
local fast=options:toggle({id='fast_gun',label='AR-23: double fire rate',default=false,
    description='The drone gun fires 1320 rounds per minute instead of 660.'})
local beam=options:toggle({id='rover_beam',label='Rover: fast beam',default=false,
    description='The Rover laser applies its damage 240 times a minute instead of 60.'})
local arc=options:toggle({id='k9_arc',label='K-9: long arc',default=false,
    description='The K-9 arc reaches 110 m instead of 55 m and chains to 6 targets instead of 2.'})
return {
    hd2.ensure({enabled=reloads,transaction={id='guard-dog-reloads',target=dog,allow_unverified_effect=true,changes={
        {field=hd2.fields.deposit.capacity,expect=8,value=20},
        {field=hd2.fields.deposit.start_amount,expect=8,value=20}}}}),
    hd2.ensure({enabled=tough,patch={id='guard-dog-health',target=drone,allow_unverified_effect=true,
        field=hd2.fields.entity.health,expect=100,value=2000}}),
    hd2.ensure({enabled=tough,patch={id='guard-dog-body',target=drone:damage_zone(0),allow_unverified_effect=true,
        field=hd2.fields.zone.health,expect=100,value=2000}}),
    hd2.ensure({enabled=drum,patch={id='guard-dog-drum',target=gun,allow_unverified_effect=true,
        field=hd2.fields.weapon.capacity,expect=45,value=200}}),
    hd2.ensure({enabled=fast,patch={id='guard-dog-rate',target=gun,allow_unverified_effect=true,
        field=hd2.fields.weapon.fire_rate,expect=660,value=1320}}),
    hd2.ensure({enabled=beam,patch={id='rover-beam-rate',target=rover,allow_unverified_effect=true,
        field=hd2.fields.beam.fire_rate,expect=60,value=240}}),
    hd2.ensure({enabled=arc,transaction={id='k9-arc',target=k9:attack('primary'),allow_shared=true,
        allow_unverified_effect=true,changes={
            {field=hd2.fields.arc.range,expect=55,value=110},
            {field=hd2.fields.arc.chain_count,expect=2,value=6}}}}),
}
