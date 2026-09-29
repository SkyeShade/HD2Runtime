"""Worker-count policy and a deterministic subprocess pool for the validation and release pipeline.

Independent checks (snapshot validators, test classes, packaged-runtime scenarios) run concurrently, but every
result is returned in the order it was requested, so reports, exit codes and error text do not depend on which
worker finished first. Offline tooling only; nothing here ships in the runtime.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
# Measured on a Ryzen 9 7950X (16 cores / 32 threads): wall time stops improving beyond 16 workers, because the
# validators are single-threaded LuaJIT and SMT siblings share one core's execution units.
MAX_DEFAULT_JOBS = 16


def default_jobs() -> int:
    """HD2_JOBS if set, else one worker per physical core (capped); never more than the machine has."""
    configured = os.environ.get('HD2_JOBS')
    if configured:
        return max(1, int(configured))
    logical = os.cpu_count() or 1
    return max(1, min(MAX_DEFAULT_JOBS, logical // 2 if logical >= 4 else logical))


def resolve(jobs: int | None) -> int:
    return default_jobs() if not jobs else max(1, jobs)


def add_argument(parser):
    parser.add_argument('--jobs', '-j', type=int, default=0, metavar='N',
        help=f'parallel workers (default: HD2_JOBS or one per physical core, at most {MAX_DEFAULT_JOBS}; 1 = serial)')


def configure(jobs: int | None) -> int:
    """Resolve --jobs and export it as HD2_JOBS, so every subprocess (validators, test workers) uses the same
    limit; --jobs 1 then runs the whole tree serially."""
    jobs = resolve(jobs)
    os.environ['HD2_JOBS'] = str(jobs)
    return jobs


def run(command, name=None, cwd=ROOT, env=None) -> dict:
    started = time.perf_counter()
    result = subprocess.run([sys.executable, '-B', *command], cwd=cwd, capture_output=True, text=True,
        encoding='utf-8', errors='replace', env=env)
    return {'name': name or ' '.join(command), 'command': list(command), 'returncode': result.returncode,
        'stdout': result.stdout, 'stderr': result.stderr, 'seconds': time.perf_counter() - started}


def map_ordered(function, items, jobs: int | None):
    """function(item) for every item on up to `jobs` threads; results in input order. Worker exceptions are
    re-raised (never swallowed). Threads suffice: each item is a subprocess, or releases the GIL in ctypes."""
    items = list(items)
    jobs = resolve(jobs)
    if jobs == 1 or len(items) <= 1:
        return [function(item) for item in items]
    with ThreadPoolExecutor(max_workers=min(jobs, len(items))) as pool:
        futures = [pool.submit(function, item) for item in items]
        return [future.result() for future in futures]


_SHARED = {}


def _lua_init(shared):
    _SHARED.update(shared)
    sys.path.insert(0, str(ROOT / 'sdk'))


def _lua_run(pieces) -> bytes:
    from tools.lua_runner import execute
    return execute(b''.join(_SHARED[piece] if isinstance(piece, str) else piece for piece in pieces))


def lua_programs(tasks, shared: dict[str, bytes], jobs: int | None) -> list[bytes]:
    """Run Lua programs on HD2's lua51.dll, one worker process each, results in task order.

    A task is a list of pieces: bytes, or the name of a `shared` blob (sent to each worker once, not per task).
    Processes, not threads: every Lua state in one process shares LuaJIT's low-address memory arena (about
    2 GB), which a few concurrent validators exhaust. A Lua error in any task is re-raised here."""
    tasks = list(tasks)
    jobs = resolve(jobs)
    if jobs == 1 or len(tasks) <= 1:
        _lua_init(shared)
        return [_lua_run(task) for task in tasks]
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=min(jobs, len(tasks), 60), initializer=_lua_init,
            initargs=(shared,)) as pool:
        futures = [pool.submit(_lua_run, task) for task in tasks]
        return [future.result() for future in futures]


def run_commands(commands, jobs: int | None, order=None) -> list[dict]:
    """Run (name, argv) pairs as Python subprocesses. `order` optionally lists names to start first (longest
    jobs first shortens the critical path); results always come back in the given order."""
    commands = list(commands)
    priority = {name: index for index, name in enumerate(order or ())}
    started = sorted(range(len(commands)), key=lambda i: (priority.get(commands[i][0], len(priority)), i))
    results = map_ordered(lambda i: run(commands[i][1], commands[i][0]), started, jobs)
    by_index = dict(zip(started, results))
    return [by_index[i] for i in range(len(commands))]
