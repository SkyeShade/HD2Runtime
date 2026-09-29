local hd2=require('mods/skyeshade/hd2runtime')
-- Live test: the SG-20 Halt's two feeds, modified independently. The Halt has two WeaponRounds magazines, both built
-- into every Halt, and its Magazine weapon function switches between them:
--   feed 'primary'   = the FLECHETTES magazine (8 rounds, flechette pellets)
--   feed 'alternate' = the Stun ALTERNATE magazine (8 rounds, stun pellets)
-- This test changes each feed on its own:
--   primary:   4 rounds, and its flechettes set enemies on fire (Fire, strength 2, the AR-2 Coyote value);
--   alternate: 12 rounds, stun pellets unchanged.
-- Capacities are weapon data copied into a Halt when the game builds it; the projectile status is read when it hits.
local halt=hd2.weapon('SG-20 Halt')
local primary,alternate=halt:feed('primary'),halt:feed('alternate')
assert(primary:describe().mechanism=='rounds_magazine'and alternate:describe().capacityField=='rounds.feed_capacity_2',
    'the Halt feeds changed')
local operations={}
operations[1]=hd2.ensure({transaction={id='halt-feed-capacities',target=halt,changes={
    {field=primary:describe().capacityField,expect=8,value=4},
    {field=alternate:describe().capacityField,expect=8,value=12}}}})
-- The flechette pellets' own DamageInfo row: the first status slot is empty; status references are live-proven.
operations[2]=hd2.ensure({transaction={id='halt-flechettes-burn',target=primary:projectile(),allow_shared=true,changes={
    {field=hd2.fields.damage.status_1_type,expect='none',value='fire'},
    {field=hd2.fields.damage.status_1_strength,expect=0,value=2}}}})
return operations
