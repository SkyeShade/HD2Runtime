# HD2Runtime process snapshots

HD2Runtime 0.7.1 provides two implementations of the scanner address-space
contract: `LiveProcessReader` and `SnapshotMemoryReader`. Both expose exact
reads, region queries, allocation bases, module bases, and module fingerprints.
The entity, component, projectile settings, damage settings, and weapon matcher
code is shared unchanged between modes.

## Capture package

Install HD2Runtime 0.7.1 once, then load
`HD2Runtime-SnapshotCapture-0.7.1.zip` for the session to capture. The package
contains only an entrypoint calling `hd2.capture_snapshot`; the native reader
remains in the external runtime. Capture never writes process memory and never
changes page protection.

Capture is scheduled 60 seconds after the package loads by default. During this
delay it performs no region enumeration and creates no output file. The log
records the configured delay and the UTC capture start time. Developers can set
`capture_delay_seconds=0` in a direct `hd2.capture_snapshot` request when an
immediate test capture is required.

Capture enumerates the current process address space once with `VirtualQuery`.
It records every returned region and captures each region once when it is:

- `MEM_COMMIT`;
- readable;
- neither `PAGE_NOACCESS` nor `PAGE_GUARD`.

`MEM_PRIVATE`, `MEM_IMAGE`, and `MEM_MAPPED` are included. Memory reads use
1 MiB chunks with an 8 MiB default per-update budget. A region that fails after
a partial read is marked `READ_FAILED`, including the error and partial byte
count; `SnapshotMemoryReader` refuses every read from that region.

Snapshots are written to:

```text
%LOCALAPPDATA%\HD2Runtime\local_research\snapshots\
```

The temporary `.partial` file is renamed to `<exe-sha-prefix>-<timestamp>.hd2snap`
only after its header and index are complete. `local_research/`, `*.hd2snap`,
and `*.partial` are ignored by Git.

## Armed in-mission capture

The timed package above captures a fixed time after the game loads, which is usually still on the ship. To capture
while a mission is running, use the **armed** package and trigger it from a console window when the game is in the
state you want.

**Install** (with Arsenal or HD2MM, like any mod): an HD2Runtime build that has `hd2.snapshot_control`, and
`HD2Runtime-SnapshotCaptureArmed-<version>.zip` (built with `py scripts/build_snapshot_capture.py --armed`). Do not
also enable the timed package unless you also want its capture 60 s after load. The armed package never captures on
its own: it only writes a status file and waits.

**Trigger** from the SDK folder, while the game runs:

```powershell
py hd2.py snapshot status                                              # is the armed package running?
py hd2.py snapshot arm --delay 300 --label mission-host-alive          # capture in 5 minutes
py hd2.py snapshot arm --wait-for-key --label mission-host-alive       # capture when ENTER is pressed here
py hd2.py snapshot arm --wait-for-key --repeat --label mission-host    # capture on every ENTER; q quits
py hd2.py snapshot arm --label mission-host-alive                      # capture now
```

(`hd2.cmd` runs the same command.) Options:

| Option | Meaning |
| --- | --- |
| `--delay SECONDS` | Wait, then capture. 0 to 86400; negative, NaN, infinite or non-numeric values are refused. Progress: an "armed" line, then 240, 180, 120, 60, 30 and 10 s remaining (plus every 5 minutes for longer delays). |
| `--wait-for-key` | Print "Snapshot armed. Press ENTER to capture." and capture on ENTER (`q` + ENTER quits). |
| `--repeat` | With `--wait-for-key`: stay armed after each capture. |
| `--label TEXT` | Added to the file name. Letters, digits, `.`, `_` and `-`; any other run of characters becomes one `-`; at most 48 characters. |
| `--ack-timeout SECONDS` | How long the game may take to accept a request (default 60). |
| `--control-dir DIR` | The control folder (default `%LOCALAPPDATA%\HD2Runtime\local_research\snapshots\control`). |

Neither mode (nor a plain `arm`) changes the capture itself: it is the same read-only engine
(`api/snapshot_capture.lua`) as the timed package, started with no delay once the trigger arrives.

### How it is kept safe

- **Attach**: the command reads the package's status (heartbeat, process id, game session, `helldivers2.exe` and
  `game.dll` fingerprints and module bases). It refuses when there is no fresh heartbeat (the package is not
  running, or the game is not updating) or when that process id is not a running `helldivers2.exe`.
- **While armed**: nothing in the game does any work; the command checks every 15 s that the process still exists.
  Ctrl+C cancels and leaves no request behind.
- **At capture time**: the command checks the process again and that the package still reports the same game
  session, process, fingerprints and bases (a restarted game is refused: "run the command again to arm the new
  session"). It then writes one request (id, label, mode, delay, times, the armed identity) that expires after the
  acknowledgement timeout. The game takes each request id once, refuses an expired request or one armed for another
  process or session, and starts the capture with the armed identity as its expectation. The engine re-reads the
  process id, both module fingerprints (it hashes the module files again) and both bases before it creates any file,
  and refuses a mismatch (`TARGET_CHANGED`). An unanswered request is withdrawn, so it can never fire later.
- **Failure**: a capture that fails or is cancelled deletes its `.partial` container; only a complete snapshot is
  ever renamed into place.

### Output

- `<exe-sha-12>-<UTC time>-<label>.hd2snap`, the unchanged HD2SNAP v1 container (the label is only in the file
  name, never in the header or any proof), in the usual snapshot folder.
- `<same name>.hd2snap.capture.json`, the capture context: `captured_at`, `capture_unix_time`, `capture_started_at`,
  both fingerprints and module bases, `process_id`, `label`, `mode` (`delay`, `manual` or `immediate`),
  `configured_delay_seconds`, `armed_at_unix`, `triggered_at_unix`, `request_id`, `game_session` and the HD2Runtime
  version. It records the test setup only. Host or client, mission phase and player state are **not** recorded: they
  are what the research reads out of the snapshot.
- The command prints the snapshot and context paths; the game keeps running during the 1-4 minute capture, and the
  command prints the captured size every 15 s.

### Snapshots wanted for the event research

Each is the full process memory; nothing extra is added for these questions.

| Label | When | Questions it answers |
| --- | --- | --- |
| `mission-host-alive` | Host (or solo), deployed, alive, weapon out, enemies nearby | mission state, host flag, player and avatar records, live entities, the equipped-weapon chain |
| `mission-host-after-reinforce` | Host, shortly after dying and being reinforced | avatar lifetime, death and reinforce transitions, stat tables |
| `mission-host-dead` | Host, dead and waiting to be reinforced | the dead state, lifecycle values |
| `mission-client-alive` | Joined someone else's mission | the client side of host / client, which records a client owns |
| `mission-extraction` | Host, extraction called or the pelican landing | mission phase and extraction |
| `mission-host-after-hellbomb` | Just after a Hellbomb or any stratagem explosion | the explosion request path |

## HD2SNAP v1

The single uncompressed container has a fixed 16 MiB header/index reserve and
directly seekable region payloads. Its versioned header stores capture time,
HD2Runtime version, optional known game version, architecture, system bounds,
EXE/game.dll bases and SHA-256 fingerprints, aggregate sizes, module metadata,
and category counters. Each 64-byte region index row stores original base,
allocation base, size, state, type, protection, capture status, captured length,
payload offset, and read error code.

`total_virtual_bytes` covers every enumerated address-space region, including
uncommitted gaps. Progress `bytes_skipped` counts committed pages excluded by
protection/readability plus failed reads; the header records uncommitted bytes
separately so large free virtual gaps do not distort capture progress.

Absolute relocated pointers retain their original virtual values and remain
followable through the region index. Serialized relative pointers are unchanged.
Uncaptured addresses and cross-region reads fail explicitly.

The format is uncompressed. Expected file size is the process's readable
committed memory plus 16 MiB. HD2 commonly occupies several GiB, so plan for
roughly 6–12 GiB of free disk space. At 50–150 MiB/s sustained capture throughput,
that is approximately 1–4 minutes. The live progress log reports actual rate
and estimated remaining time rather than assuming these figures.

## Offline weapon scan

Extract the SDK and run:

```powershell
py -B hd2.py snapshot scan-weapons <build>.hd2snap wiki_primary_weapons.json
```

The generalized player-weapon catalog command is:

```powershell
py -B hd2.py snapshot scan-player-weapons <build>.hd2snap wiki_player_weapons.json
```

It preserves weapon slot/category metadata and matches each runtime chain
against every structurally compatible attack branch. Projectile and DamageInfo
branches are reported separately when the runtime chain combines them, as with
the PLAS-101 Purifier.

The command uses the owned HD2 `bin/lua51.dll` through `HD2_GAME_ROOT`, or an
explicit `--lua-dll`. It executes the bundled copy of the production Lua scanner
modules and writes `<build>.weapon-map.json` plus
`<build>.weapon-map.identity-candidates.json`.

Fingerprint mismatches fail by default. `--historical-analysis` explicitly
allows an old snapshot to be inspected with the bundled schema, which may still
reject changed layouts. Old captures are never promoted to current-build proof.
