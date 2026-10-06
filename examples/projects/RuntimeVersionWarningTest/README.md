# RuntimeVersionWarningTest

Live test: the warning HD2Runtime shows when an installed mod needs a newer HD2Runtime. This mod declares
`requires.hd2runtime.min_version` = **0.31.0**, newer than the HD2Runtime 0.30 line, so it must never start. It has no
gameplay effect and no options.

## How to test

1. Install HD2Runtime 0.28.0 and the mod, start the game and wait on the ship.
2. Check `HD2Runtime.log`: one line `mod mods/hd2runtime_examples/runtime_version_warning_test
   (RuntimeVersionWarningTest) requires HD2Runtime 0.31.0 or newer; installed ...`. The Bingus loader log still
   shows the mod failing its dependency check (it is fail-closed, as before).
3. A few seconds after the ship is loaded, a Windows message box titled **HD2Runtime update required** should appear
   (on top of the game or in the taskbar): the required version (0.31.0), the installed version and "Please update
   HD2Runtime." It is informational: the game keeps running while it is open; click **OK** to close it.
4. It appears once per game session, not again when you return to the ship after a mission.
5. With the mod removed (or with only mods for this or an older HD2Runtime) there is no warning.

Report whether the box appeared, when (loading, ship, mission), whether it stayed behind a fullscreen game, and the
exact log lines. If it did not appear, the log line `HD2Runtime update warning could not be shown (...)` gives the
reason; the mod is still refused either way.
