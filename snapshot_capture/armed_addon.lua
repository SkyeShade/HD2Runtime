-- HD2-Addon: mods/skyeshade/hd2runtime_snapshot_armed
-- Armed snapshot capture (docs/snapshots.md#armed-in-mission-capture). Never captures on its own: it waits for
-- `py hd2.py snapshot arm` (a countdown or ENTER in a console window) and then runs the normal read-only capture.
local key='HD2RuntimeSnapshotArmedV1'
local existing=rawget(_G,key);if existing then return existing end
local hd2=require('mods/skyeshade/hd2runtime')
assert(hd2.api_version==1,'HD2Runtime API 1 required')
assert(hd2.snapshot_control,'the armed snapshot capture needs an HD2Runtime build with hd2.snapshot_control')
local state={status='armed',mode='read_only',writes=0,protection_changes=0}
rawset(_G,key,state)
state.watch=hd2.snapshot_control{}
return state
