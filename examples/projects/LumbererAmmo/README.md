# LumbererAmmo

Recreates the Lumberer Ammo v1.1 reference mod. The left arm is the flamethrower (a spray weapon), and its
capacity goes from 500 to 1000. The right arm is the anti-tank cannon, and its capacity goes from 25 to 35.
The reference mod only inferred which record was the flamethrower. The mount trace confirms it, because
that arm's weapon entity owns the `SprayWeaponComponentData`. This was built only, not deployed or launched.
