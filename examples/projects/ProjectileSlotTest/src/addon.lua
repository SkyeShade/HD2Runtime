local hd2=require('mods/skyeshade/hd2runtime')
-- Live test: projectile slots on an ordinary weapon's own bullet (research/projectile-builder-F5FEE03DCFDB.json).
-- The AR-2 Coyote's bullet row is fired by the Coyote alone, so re-pointing its references changes no other weapon.
-- Natively the bullet has a direct hit (damage plus fire) and no impact or expiry explosion.
-- - Impact explosion: give every Coyote bullet another output's explosion, released where the bullet hits: the GL-21
--   grenade blast, the EMS Mortar shell's stun field, the Speargun's gas cloud or the EAT-700's napalm burst (whose
--   fire shrapnel is its own submunition; Runtime follows that chain and refuses any that would respawn the bullet).
-- - Stun rounds: the direct hit becomes the AR-32 Pacifier's (Stun Medium instead of fire).
-- Each donor row is only read; Runtime loads the donor's package before the write. The bullet row is read when a shot
-- is fired, so the change should apply to the next shots without re-equipping (that is part of what this tests).
-- The EMS field and the gas cloud affect Helldivers too: test away from your squad.
local coyote=hd2.attack_output('AR-2 Coyote')
assert(coyote:describe().slots.impactExplosion.present==false,'the Coyote bullet gained a native impact explosion')
local options=hd2.options({id='projectile_slot_test',title='Projectile Slot Test'})
local impact=options:choice({id='impact',label='Coyote impact explosion',
    choices={'Vanilla (none)','Grenade blast','EMS stun field','Gas cloud','Napalm burst'},
    values={'none',hd2.attack_output('GL-21 Grenade Launcher'):impact_explosion(),
        hd2.attack_output('A/M-23 EMS Mortar Sentry'):expiry_explosion(),
        hd2.attack_output('S-11 Speargun'):expiry_explosion(),
        hd2.attack_output('EAT-700 Expendable Napalm'):impact_explosion()},
    description='What every Coyote bullet releases where it hits.'})
local stun=options:toggle({id='stun_rounds',label='Stun rounds',default=false,
    description='The Coyote direct hit becomes the AR-32 Pacifier direct hit (stun instead of fire).'})
-- Live-proven for exactly these tuples (projectile_slot_composition); the acknowledgement stays for the rest.
return {
    hd2.ensure({transaction={id='coyote-impact',target=coyote,allow_unverified_effect=true,changes={
        {field=hd2.fields.projectile.impact_explosion,expect='none',value=impact}}}}),
    hd2.ensure({enabled=stun,transaction={id='coyote-stun',target=coyote,allow_unverified_effect=true,changes={
        {field=hd2.fields.projectile.direct_damage,expect=coyote:direct_damage(),
            value=hd2.attack_output('AR-32 Pacifier'):direct_damage()}}}}),
}
