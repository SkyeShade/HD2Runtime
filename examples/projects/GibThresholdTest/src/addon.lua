local hd2=require('mods/skyeshade/hd2runtime')
-- Live test for the whole-body gib ("splootch") threshold, hd2.fields.gore.whole_body_gib_damage
-- (docs/enemy-authoring.md, docs/research/enemy-gib-threshold-F5FEE03DCFDB.md). A Terminid bursts when the hit that
-- kills it deals at least this much final damage (after armor and zone multipliers; Electricity counts double).
-- The value is read at hit time, so bugs already alive follow a change at once.
--
-- 0.2.0 EXTREME: two rows on the MODS tab (Mod Options Menu) set EVERY Terminid class that has a whole-body gore
-- group (23 classes: Scavengers 400, Hunters 500, Warriors and Brood/Alpha Commanders 750, Hive Guard -1):
--   1 (default)  any killing hit bursts the bug: a non-overcharged Railgun, a pistol, anything;
--   -1 (never)   no bug of these classes bursts (limbs may still sever);
--   the 'Extreme burst test' toggle off restores each class to its own vanilla value.
-- Classes without a whole-body group (Chargers, Bile Titans, Spewers, Stalkers, Shriekers) are not affected.
-- Every line this mod logs starts with the banner.
local BANNER='GIB THRESHOLD 0.2.0 EXTREME BUILD'
local mod=hd2.mod()
local CLASSES={
    {'scavenger_base',400},{'scavenger_gloom',400},{'scavenger_predator',400},{'scavenger_spitter',400},
    {'scavenger_tier_1',400},{'scavenger_tier_1_captive',400},{'scavenger_tier_2',400},
    {'hunter_base',500},{'Spore Burst Hunter',500},{'hunter_tier_1',500},{'hunter_tier_2',500},
    {'Predator Hunter',500},
    {'warrior_base',750},{'warrior_acid',750},{'warrior_big',750},{'warrior_big_tier2',750},
    {'warrior_burrower',750},{'Spore Burst Warrior',750},{'warrior_tier_1',750},{'warrior_tier_1_captive',750},
    {'warrior_tier_2',750},{'warrior_tier_2_guard',750},
    {'Hive Guard',-1},
}
local options=hd2.options({id='gib_threshold_test',title='Gib Threshold Test'})
-- Off restores every class to its own vanilla value (400 / 500 / 750 / -1) through the ensures' guarded restore.
local active=options:toggle({id='extreme_active',label='Extreme burst test',default=true,
    description='On: every listed Terminid class uses the value below. Off: each class back to vanilla.'})
local burst=options:choice({id='terminid_burst_damage',label='Terminid burst damage',
    choices={'1 (everything bursts)','-1 (never)'},values={1,-1},default=1,
    description='1: any killing hit bursts the bug (try a Safe-mode Railgun or a pistol). -1: none of them bursts.'})

local operations={}
for index,item in ipairs(CLASSES)do
    local name,vanilla=item[1],item[2]
    operations[index]=hd2.ensure({enabled=active,patch={id='gib-threshold-'..name:lower():gsub('[^%w]+','-'),
        target=hd2.enemy(name),allow_unverified_effect=true,field=hd2.fields.gore.whole_body_gib_damage,
        expect=vanilla,value=burst}})
end

local function current()
    local on=type(active)=='table'and active:get()or active
    if on==false then return 'vanilla (test off)'end
    return tostring(type(burst)=='table'and burst:get()or burst)
end

hd2.events.on('mission_started',function()
    mod:log(BANNER..': mission started; Terminid burst damage '..tostring(current())..' on '..#CLASSES..' classes')
end,{id='gib_threshold_mission'})

mod:log(BANNER..': loaded; Terminid burst damage '..tostring(current())..' on '..#CLASSES
    ..' classes (Scavengers, Hunters, Warriors, Brood/Alpha Commanders, Hive Guard)')
return operations
