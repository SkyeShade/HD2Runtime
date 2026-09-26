# ReadKnownValues

Requires Bingus Shared Loader v15+ / API 1 and HD2Runtime 0.5.0+ / API 1 installed once.

This project contains only gameplay declarations. Do not copy the runtime or SDK stubs into src.

Build: `python build.py`. Test: `python -m unittest discover -s tests -v`.

The shared SDK path is in hd2runtime.json; `.luarc.json` references its stubs.
After moving the SDK run `python <SDK>/hd2.py configure . --sdk <SDK>`.

In Rider, configure Lua language tooling to index the shared stubs directory. LuaLS reads `.luarc.json`; other EmmyLua tooling may require adding that directory as a library manually.

Players install Bingus, the standalone HD2Runtime package, and this mod. The mod explicitly requires HD2Runtime; no gameplay-mod priority ordering is needed. Dependency metadata is descriptive, not manager auto-installation.
