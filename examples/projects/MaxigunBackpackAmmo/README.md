# MaxigunBackpackAmmo

Doubles the M-1000 Maxigun's ammunition: the backpack holds 2000 rounds (was 1000), starts full at 2000
(was 1000), and a supply pickup refills 1000 (was 500).

The Maxigun owns no `WeaponMagazineComponent`. Its `WeaponLinkedAmmoComponent` draws from whatever sits in
the Backpack inventory slot and carries a matching tag. Only the minigun backpack carries that tag, and the
Maxigun call-in's hellpod rack delivers the gun and that backpack together. The ammunition is the backpack's
`DepositComponent`: capacity (+0), start amount (+4) and refill amount (+8). The runtime reaches it with
`hd2.support_weapon('M-1000 Maxigun'):backpack()` and re-proves every link of that chain before each write.

The deposit record belongs to this backpack alone, so no `allow_shared` is needed. `allow_unverified_effect`
is required because the edit has not been confirmed in game yet. The ammo-box refill (250) is half of the
supply refill and follows it; game code applies it and it is not a stored value. This was built only, not
deployed or launched.
