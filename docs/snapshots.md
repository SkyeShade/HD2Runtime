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

The command uses the owned HD2 `bin/lua51.dll` through `HD2_GAME_ROOT`, or an
explicit `--lua-dll`. It executes the bundled copy of the production Lua scanner
modules and writes `<build>.weapon-map.json` plus
`<build>.weapon-map.identity-candidates.json`.

Fingerprint mismatches fail by default. `--historical-analysis` explicitly
allows an old snapshot to be inspected with the bundled schema, which may still
reject changed layouts. Old captures are never promoted to current-build proof.
