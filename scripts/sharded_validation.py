"""Split one snapshot validator's independent objects across parallel Lua states and merge their reports.

A validator opts in by filtering its sorted object list with `shard(list)` (every object whose 1-based position
p satisfies (p-1) % count == index) and by guarding one-off work with `if EXTRAS then`. Each shard is a fresh Lua
state over the same read-only snapshot with its own copy-on-write overlay, so nothing one shard proves can leak
into another. Reports merge by summing counts and taking the union of keyed tables; any other value must be
identical in every shard that reports it, or the merge fails. With one job the validator runs as a single,
unsharded program. Offline tooling only.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'sdk'))
import parallel  # noqa: E402

PRELUDE = r'''
local function shard(list)
 if not SHARD then return list end
 local out={}
 if SHARD.none then return out end
 for index,value in ipairs(list)do if(index-1)%SHARD.count==SHARD.index then out[#out+1]=value end end
 return out
end
'''


def header(shard_index=None, count=None, extras=True) -> str:
    """shard_index None: every object; -1: none (the EXTRAS-only shard); else that slice of `count`."""
    shard = 'nil' if shard_index is None else '{none=true}' if shard_index < 0 else '{index=%d,count=%d}' % (
        shard_index, count)
    return 'local SHARD=' + shard + '\nlocal EXTRAS=' + ('true' if extras else 'false') + '\n' + PRELUDE


def merge(reports: list):
    """Sum numbers, union keyed tables, require every other value to agree. Lua's JSON encoder writes an empty
    table as [], so an empty list merges as an empty keyed table."""
    present = [report for report in reports if report is not None]
    if all(isinstance(value, dict) or value == [] for value in present):
        keys = sorted({key for value in present if isinstance(value, dict) for key in value})
        if not keys and present:
            return present[0]
        return {key: merge([value.get(key) for value in present if isinstance(value, dict)]) for key in keys}
    if all(isinstance(value, int) and not isinstance(value, bool) for value in present):
        return sum(present)
    first = present[0]
    if any(value != first for value in present[1:]):
        raise ValueError('shards disagree on a non-count value: %r' % (present,))
    return first


def run(before: str, after: str, jobs=None, extras=True, shards=None) -> dict:
    """Run the validator program `before + <shard header> + after` once per shard (plus once for the one-off
    EXTRAS block when `extras`), each in its own worker process, and merge the reports."""
    jobs = parallel.resolve(jobs)
    shared = {'before': before.encode(), 'after': after.encode()}
    if jobs == 1:
        heads = [header()]
    else:
        count = max(1, min(jobs, shards or jobs) - (1 if extras else 0))
        heads = [header(index, count, extras=False) for index in range(count)]
        if extras:
            heads.append(header(-1, extras=True))
    reports = [json.loads(raw) for raw in parallel.lua_programs([['before', head.encode(), 'after'] for head in heads],
        shared, jobs)]
    return reports[0] if len(reports) == 1 else merge(reports)
