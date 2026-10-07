# CustomStratagemPack 0.2.0

All of our custom stratagems in one mod: the four Pelican support stratagems, the heavy MG sentry, the orbital gas and
EMS barrages, the three expendable EATs and the
MS-N223 Shredder Silo. Requires Bingus Shared Loader v15+ and HD2Runtime 0.30.0-dev (install
separately). Its mod manager logo is the Shredder Silo's in-game icon.

**Uninstall the single mods it replaces** (the projects below) before installing it: the same stratagem in two mods
is refused at registration.

| stratagem | code (U D L R) | from |
| --- | --- | --- |
| Pelican Gatling Support | `L D L L U U` | PelicanCasExplosive |
| Pelican Cannon Support | `L D L U L U` | PelicanCannonExample |
| Pelican EMS Support | `L D L R L D` | PelicanEmsExample |
| Pelican Gas Support | `L D L R D R` | PelicanGasExample |
| A/MG-101 Heavy MG Sentry | `D U R R R L` | HmgSentryExample |
| Orbital Gas Barrage | `R R D L D L` | GasBarrageExample |
| Orbital EMS Barrage | `R D U R L D` | OrbitalEmsBarrageExample |
| EAT-77 Expendable Cluster | `D D L D L` | EAT17CExample |
| EAT-40 Expendable Gas | `D D L D R` | EAT17GExample |
| EAT-23 Expendable EMS | `D D L R R` | EAT23Example |
| MS-N223 Shredder Silo | `D U R U D D R` | ShredderSiloExample |

Each stratagem is copied unchanged from its project (`custom_stratagems.json`, its icon); the pack only combines them.
Source versions: PelicanCasExplosive 0.8.0, PelicanCannonExample 0.1.0, PelicanEmsExample 0.3.0, PelicanGasExample 0.3.0, HmgSentryExample 0.3.2, GasBarrageExample 0.2.0, OrbitalEmsBarrageExample 0.1.0, EAT17CExample 0.3.0, EAT17GExample 0.3.0, EAT23Example 0.1.0, ShredderSiloExample 0.2.0.

Build: `py ../../sdk/hd2.py build .`. A source project that changes is copied in again by hand (its stratagem
entry and its icon). Not live-tested as one mod.
