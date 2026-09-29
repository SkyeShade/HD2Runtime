"""`py hd2.py snapshot arm`: take a process snapshot while a mission is running.

The capture itself runs inside the game (the armed capture package, HD2Runtime-SnapshotCaptureArmed, using the one
read-only capture engine). This command is the trigger: it attaches to the running package through its control
folder, waits (a countdown, or ENTER), re-checks that the same game process and build are still there, and then asks
the package to capture. See docs/snapshots.md#armed-in-mission-capture.

  py hd2.py snapshot arm --delay 300 --label mission-host-alive
  py hd2.py snapshot arm --wait-for-key --label mission-host-alive [--repeat]
  py hd2.py snapshot arm --label quick                     # capture now
  py hd2.py snapshot status

Control folder: %LOCALAPPDATA%\\HD2Runtime\\local_research\\snapshots\\control (status.txt from the game,
request.txt from this command). Nothing here reads or writes game memory.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import os
from pathlib import Path
import re
import time
from typing import Callable
import uuid

LABEL_MAX = 48
MAX_DELAY = 86400.0
HEARTBEAT_MAX_AGE = 15.0      # seconds: an older status means the package is not running (or the game froze)
PROCESS_CHECK_INTERVAL = 15.0  # seconds between process checks while armed
PROGRESS_INTERVAL = 15.0       # seconds between capture progress lines
MILESTONES = (240, 180, 120, 60, 30, 10)


class CaptureError(RuntimeError):
    """The capture did not happen (and nothing partial was left behind by this command)."""


def default_directory() -> Path:
    local = os.environ.get('LOCALAPPDATA')
    if not local:
        raise CaptureError('LOCALAPPDATA is not set; pass --control-dir')
    return Path(local) / 'HD2Runtime' / 'local_research' / 'snapshots' / 'control'


def sanitize_label(text: str | None) -> str | None:
    """The same rule as the in-game capture engine (api/snapshot_capture.lua sanitize_label)."""
    if text is None:
        return None
    clean = re.sub(r'[^A-Za-z0-9._-]+', '-', text)
    clean = re.sub(r'-{2,}', '-', clean)
    clean = re.sub(r'^[-.]+', '', clean)
    clean = re.sub(r'[-.]+$', '', clean)
    clean = re.sub(r'[-.]+$', '', clean[:LABEL_MAX])
    if not clean:
        raise ValueError('snapshot label has no usable characters: ' + repr(text))
    return clean


def parse_delay(text) -> float:
    try:
        value = float(text)
    except (TypeError, ValueError):
        raise ValueError(f'--delay must be a number of seconds, not {text!r}') from None
    if math.isnan(value) or math.isinf(value) or value < 0:
        raise ValueError(f'--delay must be a finite number of seconds >= 0, not {text!r}')
    if value > MAX_DELAY:
        raise ValueError(f'--delay must be at most {int(MAX_DELAY)} seconds')
    return value


def parse_fields(text: str | None) -> dict | None:
    """key=value lines; None unless complete (terminated by end=1)."""
    if not text:
        return None
    fields = {}
    for line in text.splitlines():
        key, sep, value = line.partition('=')
        if sep and re.fullmatch(r'[A-Za-z0-9_]+', key):
            fields[key] = value
    return fields if fields.get('end') == '1' else None


def serialize(fields: dict) -> str:
    return ''.join(f'{key}={str(value).replace(chr(10), " ").replace(chr(13), " ")}\n'
        for key, value in fields.items() if value is not None) + 'end=1\n'


class WindowsProcesses:
    """Is this process id still a running helldivers2.exe? (OpenProcess / GetExitCodeProcess.)"""

    def alive(self, pid: int) -> bool:
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        handle = kernel.OpenProcess(0x1000, False, int(pid))   # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != 259:  # STILL_ACTIVE
                return False
            size = wintypes.DWORD(32768)
            name = ctypes.create_unicode_buffer(size.value)
            if not kernel.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(size)):
                return False
            return name.value.lower().endswith('helldivers2.exe')
        finally:
            kernel.CloseHandle(handle)


@dataclass
class Environment:
    clock: Callable[[], float] = time.time
    sleep: Callable[[float], None] = time.sleep
    prompt: Callable[[str], str] = input
    out: Callable[[str], None] = print
    processes: object = field(default_factory=WindowsProcesses)
    new_id: Callable[[], str] = lambda: uuid.uuid4().hex[:16]


@dataclass
class Options:
    mode: str = 'immediate'            # 'immediate' | 'delay' | 'manual'
    delay: float = 0.0
    label: str | None = None
    repeat: bool = False
    directory: Path | None = None
    ack_timeout: float = 60.0
    capture_timeout: float = 3600.0
    heartbeat_max_age: float = HEARTBEAT_MAX_AGE


IDENTITY = ('session', 'process_id', 'exe_sha', 'dll_sha', 'exe_base', 'dll_base')


def read_status(directory: Path) -> dict | None:
    try:
        return parse_fields((directory / 'status.txt').read_text(encoding='utf-8', errors='replace'))
    except OSError:
        return None


def _fresh(status: dict | None, now: float, max_age: float) -> bool:
    try:
        return status is not None and now - float(status['heartbeat']) <= max_age
    except (KeyError, ValueError):
        return False


def _gib(value) -> str:
    try:
        return f'{int(value) / 1073741824:.2f} GiB'
    except (TypeError, ValueError):
        return '?'


class Session:
    def __init__(self, options: Options, env: Environment):
        self.options, self.env = options, env
        self.directory = Path(options.directory) if options.directory else default_directory()
        self.identity: dict | None = None
        self.pending: str | None = None     # request id written but not yet acknowledged

    # -------------------------------------------------------------------------------------------------- attach --
    def attach(self) -> dict:
        status = read_status(self.directory)
        if not _fresh(status, self.env.clock(), self.options.heartbeat_max_age):
            raise CaptureError(f'No armed capture package is running: no fresh status in {self.directory}. Install '
                'HD2Runtime-SnapshotCaptureArmed with the matching HD2Runtime build, start Helldivers 2, and run this '
                'again once the game has loaded.')
        missing = [key for key in IDENTITY if not status.get(key)]
        if missing:
            raise CaptureError('The capture package has not identified the game modules yet (' + ', '.join(missing)
                + '); wait a moment and run this again.')
        if not self.env.processes.alive(int(status['process_id'])):
            raise CaptureError(f"Helldivers 2 process {status['process_id']} is not running.")
        self.identity = {key: status[key] for key in IDENTITY}
        self.env.out(f"Attached: Helldivers 2 process {status['process_id']} (helldivers2.exe "
            f"{status['exe_sha'][:12]}, game.dll {status['dll_sha'][:12]}), capture session {status['session']}.")
        return self.identity

    def check_process(self):
        if not self.env.processes.alive(int(self.identity['process_id'])):
            raise CaptureError(f"Helldivers 2 (process {self.identity['process_id']}) is no longer running; "
                'nothing captured.')

    # ---------------------------------------------------------------------------------------------------- wait --
    def countdown(self, seconds: float):
        env = self.env
        deadline = env.clock() + seconds
        marks = sorted({m for m in range(300, int(seconds), 300)} | {m for m in MILESTONES if m < seconds},
            reverse=True)
        env.out(f'Snapshot armed: capture in {seconds:g} s' + (f' (label {self.options.label})'
            if self.options.label else '') + '. Keep this window open; Ctrl+C cancels.')
        next_check = env.clock() + PROCESS_CHECK_INTERVAL
        while True:
            remaining = deadline - env.clock()
            if remaining <= 0:
                return
            while marks and remaining <= marks[0]:
                env.out(f'{marks.pop(0)} s remaining')
            if env.clock() >= next_check:
                self.check_process()
                next_check = env.clock() + PROCESS_CHECK_INTERVAL
            wait = min(1.0, remaining)
            if marks:
                wait = min(wait, max(remaining - marks[0], 0.001))
            env.sleep(wait)

    def ask(self, first: bool) -> bool:
        text = ('Snapshot armed. Press ENTER to capture' if first else 'Press ENTER to capture another')
        text += (' (q then ENTER to quit)' if self.options.repeat else '') + '.'
        answer = self.env.prompt(text + ' ')
        return answer.strip().lower() not in ('q', 'quit')

    # ------------------------------------------------------------------------------------------------- trigger --
    def trigger(self) -> dict:
        env, options = self.env, self.options
        self.check_process()
        # The game may be between frames (loading); wait for a fresh heartbeat of the same session.
        deadline = env.clock() + options.ack_timeout
        while True:
            status = read_status(self.directory)
            if _fresh(status, env.clock(), options.heartbeat_max_age):
                break
            if env.clock() >= deadline:
                raise CaptureError('The capture package stopped reporting (no fresh status); nothing captured.')
            env.sleep(1.0)
        changed = [key for key in IDENTITY if status.get(key) != self.identity[key]]
        if changed:
            raise CaptureError('Helldivers 2 restarted or changed since arming (' + ', '.join(changed)
                + '); nothing captured. Run the command again to arm the new session.')
        request_id = env.new_id()
        now = env.clock()
        request = {'id': request_id, 'label': options.label or '', 'mode': options.mode,
            'delay': f'{options.delay:g}', 'armed_at': f'{self.armed_at:.0f}', 'triggered_at': f'{now:.0f}',
            'expires': f'{now + options.ack_timeout:.0f}', **self.identity}
        target = self.directory / 'request.txt'
        temporary = self.directory / 'request.txt.tmp'
        temporary.write_text(serialize(request), encoding='utf-8')
        os.replace(temporary, target)
        self.pending = request_id
        env.out('Capturing...')
        return self.wait_for_result(request_id)

    def withdraw(self):
        """Remove our request if the game has not taken it (so it can never fire later)."""
        if not self.pending:
            return
        target = self.directory / 'request.txt'
        request = parse_fields(target.read_text(encoding='utf-8')) if target.exists() else None
        if request and request.get('id') == self.pending:
            target.unlink(missing_ok=True)
        self.pending = None

    def wait_for_result(self, request_id: str) -> dict:
        env, options = self.env, self.options
        ack_deadline = env.clock() + options.ack_timeout
        capture_deadline = None
        next_progress = env.clock() + PROGRESS_INTERVAL
        next_check = env.clock() + PROCESS_CHECK_INTERVAL
        while True:
            status = read_status(self.directory) or {}
            if status.get('request') == request_id:
                state = status.get('state')
                if state == 'complete':
                    self.pending = None
                    env.out(f"Snapshot complete: {status.get('path')}")
                    if status.get('context_path'):
                        env.out(f"Capture context: {status['context_path']}")
                    return status
                if state == 'rejected':
                    self.pending = None
                    raise CaptureError(f"The game refused the capture: {status.get('reason')}")
                if state == 'capturing' and capture_deadline is None:
                    self.pending = None       # taken by the game: it will finish or fail on its own
                    capture_deadline = env.clock() + options.capture_timeout
                    env.out('The game accepted the request; capturing (the game keeps running).')
                if capture_deadline is not None and env.clock() >= next_progress:
                    env.out(f"  {_gib(status.get('bytes_captured'))} of {_gib(status.get('eligible_bytes'))} captured")
                    next_progress = env.clock() + PROGRESS_INTERVAL
            if capture_deadline is None and env.clock() >= ack_deadline:
                self.withdraw()
                raise CaptureError(f'The capture package did not take the request within {options.ack_timeout:g} s '
                    '(is the game running and not stuck on a loading screen?); nothing captured.')
            if capture_deadline is not None and env.clock() >= capture_deadline:
                raise CaptureError('The capture did not finish within the time limit; check HD2Runtime.log.')
            if env.clock() >= next_check:
                self.check_process()
                next_check = env.clock() + PROCESS_CHECK_INTERVAL
            env.sleep(0.5)

    # ------------------------------------------------------------------------------------------------------ run --
    def run(self) -> list[dict]:
        env, options = self.env, self.options
        self.attach()
        self.armed_at = env.clock()
        results = []
        first = True
        try:
            while True:
                if options.mode == 'delay' and first:
                    self.countdown(options.delay)
                elif options.mode == 'manual':
                    if not self.ask(first):
                        break
                results.append(self.trigger())
                first = False
                if not (options.mode == 'manual' and options.repeat):
                    break
        except KeyboardInterrupt:
            self.withdraw()
            env.out('Cancelled; nothing more will be captured by this command.')
            raise
        except BaseException:
            self.withdraw()
            raise
        return results


def arm(options: Options, env: Environment | None = None) -> list[dict]:
    if options.mode not in ('immediate', 'delay', 'manual'):
        raise ValueError('unknown snapshot arm mode: ' + str(options.mode))
    if options.repeat and options.mode != 'manual':
        raise ValueError('--repeat needs --wait-for-key')
    options.label = sanitize_label(options.label)
    return Session(options, env or Environment()).run()


def status(directory: Path | None = None, env: Environment | None = None) -> str:
    env = env or Environment()
    directory = Path(directory) if directory else default_directory()
    current = read_status(directory)
    if not current:
        return f'No status in {directory}: the armed capture package has not run.'
    age = env.clock() - float(current.get('heartbeat', 0) or 0)
    lines = [f"state={current.get('state')} heartbeat {age:.0f} s ago"
        + ('' if age <= HEARTBEAT_MAX_AGE else ' (stale: the game is not running or not updating)')]
    for key in ('process_id', 'session', 'exe_sha', 'dll_sha', 'request', 'label', 'path', 'reason', 'captures'):
        if current.get(key):
            lines.append(f'{key}={current[key]}')
    return '\n'.join(lines)
