# LiberatorDamageOptions

Adds a **Liberator Damage** page to the in-game MODS tab: an **Enabled** toggle and an **AR-23 Liberator Damage** slider from 90 to 500 in steps of 10 (default 150).

One `hd2.ensure` owns the write. When the player presses APPLY, it follows the new value through the normal guarded path; no new operation is created. The expected baseline stays 90, and a value written by another mod is still a conflict. Turning the toggle off restores 90 through the same guards; turning it on applies the slider value again. The damage row is a shared projectile definition (AR-23A Liberator Carbine, StA-52), so the ensure acknowledges `allow_shared`.

Requires HD2Runtime 0.25.0+. The MODS tab needs CowboyBingus **Mod Options Menu** v1+ and **Bingus Shared Loader v18+**. Without them, the mod still applies the default 150. Built only; never deployed or launched.
