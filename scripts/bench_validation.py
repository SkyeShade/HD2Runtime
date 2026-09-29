"""Benchmark validation/release commands: wall time, CPU time (whole process tree), peak memory.

  py scripts/bench_validation.py --label before -- py -B scripts/validate_migration.py validation/migrations/<m>
  py scripts/bench_validation.py --steps       # time every validate_migration step on its own

Each command runs inside a Windows job object, so CPU time and peak committed memory include every
subprocess and worker it starts. Results are appended to build/bench/<label>.jsonl. Offline tooling only.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in ('ReadOperationCount', 'WriteOperationCount',
        'OtherOperationCount', 'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]


class BASIC_LIMIT(ctypes.Structure):
    _fields_ = [('PerProcessUserTimeLimit', ctypes.c_longlong), ('PerJobUserTimeLimit', ctypes.c_longlong),
        ('LimitFlags', wintypes.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
        ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', wintypes.DWORD),
        ('Affinity', ctypes.c_size_t), ('PriorityClass', wintypes.DWORD), ('SchedulingClass', wintypes.DWORD)]


class EXTENDED_LIMIT(ctypes.Structure):
    _fields_ = [('BasicLimitInformation', BASIC_LIMIT), ('IoInfo', IO_COUNTERS),
        ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
        ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]


class BASIC_ACCOUNTING(ctypes.Structure):
    _fields_ = [('TotalUserTime', ctypes.c_longlong), ('TotalKernelTime', ctypes.c_longlong),
        ('ThisPeriodTotalUserTime', ctypes.c_longlong), ('ThisPeriodTotalKernelTime', ctypes.c_longlong),
        ('TotalPageFaultCount', wintypes.DWORD), ('TotalProcesses', wintypes.DWORD),
        ('ActiveProcesses', wintypes.DWORD), ('TotalTerminatedProcesses', wintypes.DWORD)]


kernel32.CreateJobObjectW.restype = wintypes.HANDLE
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
kernel32.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
    ctypes.c_void_p]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
CREATE_SUSPENDED = 0x4


def measure(command, cwd=ROOT, quiet=True) -> dict:
    """Run one command in a fresh job object and return its whole-tree resource use."""
    job = kernel32.CreateJobObjectW(None, None)
    started = time.perf_counter()
    process = subprocess.Popen(command, cwd=cwd, creationflags=CREATE_SUSPENDED,
        stdout=subprocess.PIPE if quiet else None, stderr=subprocess.STDOUT if quiet else None)
    kernel32.AssignProcessToJobObject(job, int(process._handle))
    # Resume the main thread of the suspended child (Popen gives us no thread handle, so use NtResumeProcess).
    ctypes.WinDLL('ntdll').NtResumeProcess(wintypes.HANDLE(int(process._handle)))
    output = process.communicate()[0]
    wall = time.perf_counter() - started
    accounting, limits = BASIC_ACCOUNTING(), EXTENDED_LIMIT()
    kernel32.QueryInformationJobObject(job, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None)
    kernel32.QueryInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits), None)
    kernel32.CloseHandle(job)
    cpu = (accounting.TotalUserTime + accounting.TotalKernelTime) / 1e7
    return {'command': [str(part) for part in command], 'exit': process.returncode, 'wall': round(wall, 2),
        'cpu': round(cpu, 2), 'utilization': round(cpu / wall, 2) if wall else 0,
        'peakJobCommitMB': round(limits.PeakJobMemoryUsed / 2**20), 'peakProcessCommitMB':
        round(limits.PeakProcessMemoryUsed / 2**20), 'processes': accounting.TotalProcesses,
        'tail': (output or b'').decode('utf-8', 'replace').strip().splitlines()[-3:]}


def record(label, result):
    folder = ROOT / 'build/bench'
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / (label + '.jsonl')).open('a', encoding='utf-8') as file:
        file.write(json.dumps(dict(result, label=label, at=time.strftime('%Y-%m-%dT%H:%M:%S'))) + '\n')
    print(f"{result['wall']:8.1f}s wall {result['cpu']:8.1f}s cpu x{result['utilization']:<5} "
        f"{result['peakJobCommitMB']:6d} MB  exit {result['exit']}  {' '.join(result['command'][2:])[:90]}")


def steps():
    """Every command validate_migration.py runs, one at a time."""
    sys.path.insert(0, str(ROOT / 'scripts'))
    from validate_migration import SNAPSHOT_VALIDATORS
    yield ['scripts/regenerate_domains.py', '--check']
    for name in SNAPSHOT_VALIDATORS:
        yield ['scripts/' + name + '.py']
    yield ['scripts/validate_examples.py']
    yield ['-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_sdk.py']
    yield ['-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_migration.py']
    yield ['-m', 'unittest', 'discover', '-s', 'tests']


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--label', default='bench')
    parser.add_argument('--steps', action='store_true')
    parser.add_argument('--show', action='store_true', help='stream the command output instead of capturing it')
    parser.add_argument('--cwd', type=Path, default=ROOT, help='working directory (e.g. a baseline worktree)')
    parser.add_argument('command', nargs='*')
    args = parser.parse_args(argv)
    if args.steps:
        for command in steps():
            record(args.label, measure([sys.executable, '-B', *command]))
    if args.command:
        record(args.label, measure(args.command, cwd=args.cwd, quiet=not args.show))


if __name__ == '__main__':
    main()
