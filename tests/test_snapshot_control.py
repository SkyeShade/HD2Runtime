"""Armed in-mission snapshot capture: the SDK command (`hd2.py snapshot arm`), the in-game controller
(api/snapshot_control.lua) and the capture engine's label, context and capture-time revalidation."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

from support import ROOT, lua, run

sys.path.insert(0, str(ROOT / 'sdk'))
from tools import snapshot_control as sc  # noqa: E402

EXE, DLL = 'A' * 64, 'B' * 64


class FakeProcesses:
    def __init__(self):
        self.alive_pids = {4242}

    def alive(self, pid):
        return pid in self.alive_pids


class FakeGame:
    """The in-game controller's side of the protocol: status heartbeats, and one capture per request."""

    def __init__(self, directory, clock, session='4242-100', respond=True, reject=None):
        self.directory, self.clock, self.session = Path(directory), clock, session
        self.respond, self.reject = respond, reject
        self.requests, self.state = [], {'state': 'idle'}
        self.beat()

    def identity(self):
        return {'session': self.session, 'process_id': '4242', 'exe_sha': EXE, 'dll_sha': DLL,
            'exe_base': '140000000', 'dll_base': '140700000'}

    def beat(self):
        fields = dict(self.state, heartbeat=f'{self.clock():.0f}', **self.identity())
        (self.directory / 'status.txt').write_text(sc.serialize(fields), encoding='utf-8')

    def tick(self):
        request = sc.parse_fields((self.directory / 'request.txt').read_text(encoding='utf-8')) \
            if (self.directory / 'request.txt').exists() else None
        if request and self.respond:
            (self.directory / 'request.txt').unlink()
            self.requests.append(request)
            if self.reject:
                self.state = {'state': 'rejected', 'request': request['id'], 'reason': self.reject}
            else:
                name = f"{EXE[:12]}-20260929T120000Z-{request['label']}.hd2snap"
                self.state = {'state': 'complete', 'request': request['id'], 'label': request['label'],
                    'path': 'C:\\snaps\\' + name, 'context_path': 'C:\\snaps\\' + name + '.capture.json'}
        self.beat()


class FakeClock:
    def __init__(self):
        self.now = 1000.0
        self.game = None
        self.sleeps = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds
        if self.game:
            self.game.tick()


def environment(clock, answers=(), processes=None):
    out, answers = [], list(answers)

    def prompt(text):
        out.append(text)
        return answers.pop(0)
    ids = iter(f'req{n}' for n in range(1, 100))
    return sc.Environment(clock=clock.time, sleep=clock.sleep, prompt=prompt, out=out.append,
        processes=processes or FakeProcesses(), new_id=lambda: next(ids)), out


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(dir=ROOT / 'build')
        self.dir = Path(self.folder.name)
        self.clock = FakeClock()

    def tearDown(self):
        self.folder.cleanup()

    def game(self, **kwargs):
        self.clock.game = FakeGame(self.dir, self.clock.time, **kwargs)
        return self.clock.game

    def test_delay_and_label_parsing(self):
        self.assertEqual(sc.parse_delay('300'), 300.0)
        self.assertEqual(sc.parse_delay('0'), 0.0)
        self.assertEqual(sc.parse_delay('12.5'), 12.5)
        for bad in ('-1', 'nan', 'inf', '-inf', 'abc', '', '100000', None):
            with self.assertRaises(ValueError, msg=repr(bad)):
                sc.parse_delay(bad)
        self.assertEqual(sc.sanitize_label('mission-host-alive'), 'mission-host-alive')
        self.assertEqual(sc.sanitize_label('Mission Host: alive!'), 'Mission-Host-alive')
        self.assertEqual(sc.sanitize_label('../../evil\\name'), 'evil-name')
        self.assertEqual(sc.sanitize_label('a' * 80), 'a' * 48)
        self.assertIsNone(sc.sanitize_label(None))
        for bad in ('', '!!!', '..', '---'):
            with self.assertRaises(ValueError):
                sc.sanitize_label(bad)

    def test_the_command_and_the_engine_sanitize_labels_identically(self):
        cases = ['mission-host-alive', 'Mission Host: alive!', '../../evil\\name', 'a' * 80, 'x.y_z', ' -a- ',
            'ünïcode label', 'a' * 47 + '.b']
        expected = [sc.sanitize_label(case) for case in cases]
        got = run(r'''
local capture=require('hd2runtime/api/snapshot_capture')
local out={}
for _,case in ipairs(''' + lua([case.encode('utf-8') for case in cases]) + r''')do out[#out+1]=capture.sanitize_label(case)end
local ok=pcall(capture.sanitize_label,'!!!')
assert(not ok,'an unusable label is refused')
return table.concat(out,'\n')
''').decode('utf-8').split('\n')
        self.assertEqual(got, expected)

    def test_immediate_mode_captures_once_without_waiting(self):
        game = self.game()
        env, out = environment(self.clock)
        results = sc.arm(sc.Options(mode='immediate', label='quick', directory=self.dir), env)
        self.assertEqual(len(game.requests), 1)
        self.assertEqual(game.requests[0]['mode'], 'immediate')
        self.assertEqual(results[0]['state'], 'complete')
        self.assertFalse(any('remaining' in line for line in out))
        self.assertFalse((self.dir / 'request.txt').exists())

    def test_delayed_mode_counts_down_then_captures_once(self):
        game = self.game()
        env, out = environment(self.clock)
        armed_at = self.clock.now
        sc.arm(sc.Options(mode='delay', delay=300, label='mission-host-alive', directory=self.dir), env)
        self.assertEqual(len(game.requests), 1, 'the capture path runs once, after the wait')
        request = game.requests[0]
        self.assertGreaterEqual(float(request['triggered_at']), armed_at + 300)
        self.assertEqual((request['mode'], request['delay'], request['label']), ('delay', '300', 'mission-host-alive'))
        self.assertEqual(request['session'], '4242-100')
        milestones = [line for line in out if line.endswith('s remaining')]
        self.assertEqual(milestones, [f'{n} s remaining' for n in (240, 180, 120, 60, 30, 10)])
        self.assertTrue(out[1].startswith('Snapshot armed: capture in 300 s (label mission-host-alive)'))
        self.assertLess(out.index('10 s remaining'), out.index('Capturing...'))
        self.assertLessEqual(max(self.clock.sleeps), 1.0, 'no long blind sleeps: the process stays checked')

    def test_the_process_is_rechecked_while_armed_and_at_capture_time(self):
        game = self.game()
        processes = FakeProcesses()
        env, out = environment(self.clock, processes=processes)

        def die_after(seconds):
            limit = self.clock.now + seconds
            original = self.clock.sleep

            def sleep(value):
                original(value)
                if self.clock.now >= limit:
                    processes.alive_pids.clear()
            env.sleep = sleep
        die_after(100)
        with self.assertRaisesRegex(sc.CaptureError, 'no longer running; nothing captured'):
            sc.arm(sc.Options(mode='delay', delay=300, directory=self.dir), env)
        self.assertEqual(game.requests, [])
        self.assertFalse((self.dir / 'request.txt').exists())

    def test_a_restarted_game_is_not_captured(self):
        game = self.game()
        env, out = environment(self.clock, answers=[''])

        def prompt(text):
            game.session = '4242-999'      # the game restarted while armed: a new controller session
            game.beat()
            return ''
        env.prompt = prompt
        with self.assertRaisesRegex(sc.CaptureError, 'restarted or changed since arming \\(session\\)'):
            sc.arm(sc.Options(mode='manual', directory=self.dir), env)
        self.assertEqual(game.requests, [])

    def test_manual_mode_and_repeat(self):
        game = self.game()
        env, out = environment(self.clock, answers=['', '', 'q'])
        results = sc.arm(sc.Options(mode='manual', label='mission-extraction', repeat=True, directory=self.dir), env)
        self.assertEqual(len(results), 2)
        self.assertEqual([r['mode'] for r in game.requests], ['manual', 'manual'])
        self.assertEqual(len({r['id'] for r in game.requests}), 2)
        self.assertTrue(out[1].startswith('Snapshot armed. Press ENTER to capture (q then ENTER to quit).'))
        game2 = self.game()
        env, out = environment(self.clock, answers=['q'])
        self.assertEqual(sc.arm(sc.Options(mode='manual', directory=self.dir), env), [])
        self.assertEqual(game2.requests, [])
        with self.assertRaises(ValueError):
            sc.arm(sc.Options(mode='delay', delay=5, repeat=True, directory=self.dir), env)

    def test_an_unanswered_request_is_withdrawn(self):
        self.game(respond=False)
        env, out = environment(self.clock)
        with self.assertRaisesRegex(sc.CaptureError, 'did not take the request within 60 s'):
            sc.arm(sc.Options(mode='immediate', directory=self.dir), env)
        self.assertFalse((self.dir / 'request.txt').exists(), 'no stale request can fire later')

    def test_cancelling_leaves_no_request(self):
        game = self.game()
        env, out = environment(self.clock)
        calls = []

        def interrupted(value):
            calls.append(value)
            if len(calls) == 5:
                raise KeyboardInterrupt
            self.clock.sleep(value)
        env.sleep = interrupted
        with self.assertRaises(KeyboardInterrupt):
            sc.arm(sc.Options(mode='delay', delay=300, directory=self.dir), env)
        self.assertEqual(game.requests, [])
        self.assertFalse((self.dir / 'request.txt').exists())
        # Interrupted after the request was written but before the game took it: withdrawn.
        game = self.game(respond=False)
        env, out = environment(self.clock)
        env.sleep = lambda value: (_ for _ in ()).throw(KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt):
            sc.arm(sc.Options(mode='immediate', directory=self.dir), env)
        self.assertFalse((self.dir / 'request.txt').exists())

    def test_a_refusal_and_a_missing_package_fail_cleanly(self):
        self.game(reject='TARGET_CHANGED: game.dll fingerprint is X, armed with Y')
        env, out = environment(self.clock)
        with self.assertRaisesRegex(sc.CaptureError, 'refused the capture: TARGET_CHANGED'):
            sc.arm(sc.Options(mode='immediate', directory=self.dir), env)
        (self.dir / 'status.txt').unlink()
        with self.assertRaisesRegex(sc.CaptureError, 'No armed capture package is running'):
            sc.arm(sc.Options(mode='immediate', directory=self.dir), env)
        game = self.game()
        self.clock.now += 120                     # the last heartbeat is two minutes old
        with self.assertRaisesRegex(sc.CaptureError, 'No armed capture package is running'):
            sc.arm(sc.Options(mode='immediate', directory=self.dir), env)
        self.assertEqual(game.requests, [])


FAKE_RUNTIME = r'''
local p=require('hd2runtime/schemas/current')
local function runtime(opts)
 opts=opts or{}
 local rows={{base=0x10000,size=0x10000,allocation_base=0x10000,state=0x1000,type=0x1000000,protect=2},
  {base=0x20000,size=0x10000,allocation_base=0x20000,state=0x1000,type=0x1000000,protect=2},
  {base=0x30000,size=0x10000,allocation_base=0x30000,state=0x1000,type=0x20000,protect=4}}
 local rt={mode='live',pid=opts.pid or 4242,dll=opts.dll or 0x20000,reads=0}
 function rt.module(name)return name and rt.dll or 0x10000 end
 function rt.address(value)return value end
 function rt.module_hash(value)return value==0x10000 and p.exe_sha or(rt.dll_sha or p.dll_sha)end
 function rt.process_id()return rt.pid end
 function rt.system_info()return 4096,0x40000 end
 function rt.query(at)for _,r in ipairs(rows)do if at>=r.base and at<r.base+r.size then return r end end end
 function rt.read(at,n)rt.reads=rt.reads+1;if rt.fail_reads and rt.reads>=rt.fail_reads then error('simulated read fault')end
  return string.rep('x',n)end
 function rt.monotonic_time()return 0 end
 function rt.ensure_directory(value)return value end
 return rt
end
local function exists(path)local f=io.open(path,'rb');if f then f:close();return true end;return false end
'''


class EngineTests(unittest.TestCase):
    def lua(self, body, folder):
        self.assertEqual(run(FAKE_RUNTIME + 'local DIR=' + lua(str(folder)) + '\n' + body), b'ok')

    def test_immediate_capture_is_unchanged_without_label_or_context(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'build') as folder:
            self.lua(r'''
local w=require('hd2runtime/api/snapshot_capture').start(runtime(),function()end,
 {output_directory=DIR,capture_delay_seconds=0,bytes_per_tick=65536,chunk_bytes=65536})
while w.status=='running'do w.tick()end
assert(w.status=='complete',w.error)
local name=w.result.path:match('[^\\/]+$')
assert(name:match('^'..p.exe_sha:sub(1,12)..'%-%d+T%d+Z%.hd2snap$'),name)
assert(w.result.context_path==nil and not exists(w.result.path..'.capture.json'),'no sidecar without context')
return 'ok'
''', folder)

    def test_label_names_the_file_and_context_is_a_sidecar(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'build') as folder:
            self.lua(r'''
local w=require('hd2runtime/api/snapshot_capture').start(runtime(),function()end,
 {output_directory=DIR,capture_delay_seconds=0,bytes_per_tick=65536,chunk_bytes=65536,label='Mission Host: alive!',
  context={mode='delay',configured_delay_seconds=300,request_id='abc'}})
while w.status=='running'do w.tick()end
assert(w.status=='complete',w.error)
assert(w.result.path:match('%-Mission%-Host%-alive%.hd2snap$'),w.result.path)
local s=require('hd2runtime/runtime/snapshot_memory_reader').open(w.result.path,{expected_exe_sha=p.exe_sha,expected_dll_sha=p.dll_sha})
s.close()                                  -- the snapshot format is unchanged
local f=assert(io.open(w.result.path..'.capture.json','rb'));local text=f:read('*a');f:close()
for _,needle in ipairs({'"label": "Mission-Host-alive"','"mode": "delay"','"configured_delay_seconds": 300',
  '"request_id": "abc"','"process_id": 4242','"executable_sha256": "'..p.exe_sha..'"','"captured_at": "'})do
 assert(text:find(needle,1,true),needle..' missing from '..text)
end
assert(not exists(w.result.path..'.capture.json.partial'))
return 'ok'
''', folder)

    def test_capture_time_revalidation_refuses_a_changed_process_or_build(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'build') as folder:
            self.lua(r'''
local capture=require('hd2runtime/api/snapshot_capture')
local good={process_id=4242,exe_sha=p.exe_sha,dll_sha=p.dll_sha,exe_base=0x10000,dll_base=0x20000}
local cases={
 {runtime({pid=999}),'process id'},
 {runtime({dll=0x28000}),'game.dll base'},
}
local changed=runtime();changed.dll_sha=string.rep('C',64);cases[#cases+1]={changed,'game.dll fingerprint'}
for _,case in ipairs(cases)do
 local w=capture.start(case[1],function()end,{output_directory=DIR,capture_delay_seconds=0,label='x',expected=good})
 w.tick()
 assert(w.status=='rejected'and w.error:find('TARGET_CHANGED: '..case[2],1,true),tostring(w.error))
end
local listing=io.popen('dir /b "'..DIR..'"'):read('*a')
assert(listing:gsub('%s','')=='','nothing was written: '..listing)
local w=capture.start(runtime(),function()end,{output_directory=DIR,capture_delay_seconds=0,bytes_per_tick=65536,
 chunk_bytes=65536,expected=good})
while w.status=='running'do w.tick()end
assert(w.status=='complete',w.error)
return 'ok'
''', folder)

    def test_a_failed_or_cancelled_capture_leaves_no_partial_file(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'build') as folder:
            self.lua(r'''
local capture=require('hd2runtime/api/snapshot_capture')
local rt=runtime();rt.fail_reads=2
local errors={}
local w=capture.start(rt,function()end,{output_directory=DIR,capture_delay_seconds=0,bytes_per_tick=65536,
 chunk_bytes=65536,label='fails',on_error=function(reason,detail)errors[#errors+1]=detail end})
while w.status=='running'do w.tick()end
assert(w.status=='rejected'and w.error:find('simulated read fault',1,true),tostring(w.error))
assert(errors[1].partial_removed)
local c=capture.start(runtime(),function()end,{output_directory=DIR,capture_delay_seconds=0,bytes_per_tick=65536,
 chunk_bytes=65536,label='cancelled'})
c.tick();c.cancel()
assert(c.status=='cancelled')
local listing=io.popen('dir /b "'..DIR..'"'):read('*a')
assert(listing:gsub('%s','')=='','no partial or final file remains: '..listing)
return 'ok'
''', folder)


class ControllerTests(unittest.TestCase):
    def test_requests_are_validated_and_captured_once(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'build') as folder:
            control = Path(folder) / 'control'
            output = Path(folder) / 'out'
            output.mkdir()
            control.mkdir()
            self.assertEqual(run(FAKE_RUNTIME + 'local CONTROL=' + lua(str(control)) + '\nlocal OUT=' + lua(str(output))
                + r'''
local control=require('hd2runtime/api/snapshot_control')
local clock=5000
local rt=runtime()
local logs={}
local w=control.start(rt,function(x)logs[#logs+1]=x end,{control_directory=CONTROL,output_directory=OUT,
 bytes_per_tick=65536,chunk_bytes=65536,clock=function()return clock end})
local function status()local f=assert(io.open(CONTROL..'\\status.txt','rb'));local s=control.parse(f:read('*a'));f:close();return s end
local s=status()
assert(s.state=='idle'and s.process_id=='4242'and s.exe_sha==p.exe_sha and s.dll_base==tostring(0x20000),s.state)
local session=s.session
local function request(fields)
 local base={id='r1',label='mission-host-alive',mode='delay',delay='300',armed_at='4700',triggered_at='5000',
  expires='5060',session=session,process_id='4242',exe_sha=p.exe_sha,dll_sha=p.dll_sha,exe_base=tostring(0x10000),
  dll_base=tostring(0x20000)}
 for k,v in pairs(fields or{})do base[k]=v end
 local lines={}
 for k,v in pairs(base)do lines[#lines+1]=k..'='..v end
 local f=assert(io.open(CONTROL..'\\request.txt','wb'));f:write(table.concat(lines,'\n')..'\nend=1\n');f:close()
end
local function run_until(state,id)
 for _=1,2000 do w.tick(0.5);local s=status();if s.request==id and s.state==state then return s end end
 error('never reached '..state..' for '..id..': '..tostring(status().state)..' '..tostring(status().reason))
end
-- Refusals: expired, another process, another session, another build; each id is handled once.
request({id='old',expires='4000'});assert(run_until('rejected','old').reason=='request expired')
request({id='pid',process_id='1'});assert(run_until('rejected','pid').reason=='request targets another process')
request({id='ses',session='other'});assert(run_until('rejected','ses').reason:find('another game session',1,true))
request({id='sha',dll_sha=string.rep('9',64)});assert(run_until('rejected','sha').reason:find('dll_sha',1,true))
local listing=io.popen('dir /b "'..OUT..'"'):read('*a');assert(listing:gsub('%s','')=='','no refused request captured')
-- A valid request: one capture with its label and context.
request({id='r1'})
local done=run_until('complete','r1')
assert(done.path:match('%-mission%-host%-alive%.hd2snap$'),done.path)
local f=assert(io.open(done.context_path,'rb'));local text=f:read('*a');f:close()
assert(text:find('"request_id": "r1"',1,true)and text:find('"mode": "delay"',1,true)
 and text:find('"configured_delay_seconds": 300',1,true)and text:find('"game_session": "'..session..'"',1,true),text)
-- The same id again does nothing; the request file was consumed.
request({id='r1'})
for _=1,10 do w.tick(0.5)end
local count=0;for _ in io.popen('dir /b "'..OUT..'\\*.hd2snap"'):lines()do count=count+1 end
assert(count==1,'captured once: '..count)
assert(status().captures=='1')
return 'ok'
'''), b'ok')


class EndToEndTests(unittest.TestCase):
    def test_the_command_drives_the_real_controller(self):
        """The real Lua controller (on the game's LuaJIT, fake memory, real files) in a background thread, and the
        real command in this thread: arm, a 2-second countdown, one capture with its label and context."""
        import threading
        with tempfile.TemporaryDirectory(dir=ROOT / 'build') as folder:
            control, output = Path(folder) / 'control', Path(folder) / 'out'
            control.mkdir()
            output.mkdir()
            stop = Path(folder) / 'stop'
            result = {}

            def game():
                try:
                    result['lua'] = run(FAKE_RUNTIME + 'local CONTROL=' + lua(str(control)) + '\nlocal OUT='
                        + lua(str(output)) + '\nlocal STOP=' + lua(str(stop)) + r'''
local ffi=require('ffi')
ffi.cdef('void Sleep(uint32_t ms);')
local control=require('hd2runtime/api/snapshot_control')
local w=control.start(runtime(),function()end,{control_directory=CONTROL,output_directory=OUT,
 bytes_per_tick=65536,chunk_bytes=65536})
local started=os.clock()
while not exists(STOP)and os.clock()-started<60 do w.tick(0.05);ffi.C.Sleep(50)end
return 'ok'
''')
                except Exception as error:   # reported by the main thread
                    result['error'] = error
            thread = threading.Thread(target=game, daemon=True)
            thread.start()
            try:
                import time
                for _ in range(100):
                    if (control / 'status.txt').exists():
                        break
                    time.sleep(0.05)
                out = []
                env = sc.Environment(out=out.append, processes=FakeProcesses())
                results = sc.arm(sc.Options(mode='delay', delay=2, label='mission-host-alive', directory=control,
                    ack_timeout=20), env)
            finally:
                stop.write_text('stop')
                thread.join(30)
            self.assertNotIn('error', result, result.get('error'))
            self.assertEqual(result.get('lua'), b'ok')
            self.assertEqual(len(results), 1)
            snapshots = sorted(output.glob('*.hd2snap'))
            self.assertEqual(len(snapshots), 1)
            self.assertTrue(snapshots[0].name.endswith('-mission-host-alive.hd2snap'), snapshots[0].name)
            context = json.loads(Path(str(snapshots[0]) + '.capture.json').read_text(encoding='utf-8'))
            self.assertEqual((context['label'], context['mode'], context['configured_delay_seconds'], context['process_id']),
                ('mission-host-alive', 'delay', 2, 4242))
            self.assertEqual(sorted(p.name for p in output.iterdir()),
                sorted([snapshots[0].name, snapshots[0].name + '.capture.json']), 'no partial files')
            self.assertFalse((control / 'request.txt').exists())
            self.assertIn('Snapshot armed: capture in 2 s (label mission-host-alive). Keep this window open; '
                'Ctrl+C cancels.', out)


class IdentityTests(unittest.TestCase):
    def test_the_controller_identifies_the_game_once_its_modules_load(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'build') as folder:
            self.assertEqual(run(FAKE_RUNTIME + 'local CONTROL=' + lua(str(folder)) + r'''
local control=require('hd2runtime/api/snapshot_control')
local rt=runtime()
local real=rt.module
rt.module=function(name)if name=='game.dll'then return nil end;return real(name)end
local hashes=0
local hash=rt.module_hash
rt.module_hash=function(v)hashes=hashes+1;return hash(v)end
local w=control.start(rt,function()end,{control_directory=CONTROL})
local function status()local f=assert(io.open(CONTROL..'\\status.txt','rb'));local s=control.parse(f:read('*a'));f:close();return s end
assert(status().exe_sha==nil,'not identified before game.dll is loaded')
rt.module=real
for _=1,5 do w.tick(0.5)end
assert(status().dll_sha==p.dll_sha and status().dll_base==tostring(0x20000),'identified at a later heartbeat')
local after=hashes
for _=1,20 do w.tick(0.5)end
assert(hashes==after,'the module files are hashed once, not every heartbeat')
return 'ok'
'''), b'ok')


class PackageTests(unittest.TestCase):
    def test_the_armed_package_is_separate_and_declarative(self):
        sys.path.insert(0, str(ROOT / 'scripts'))
        import build_snapshot_capture as build
        timed, armed = build.resources(), build.resources(armed=True)
        self.assertEqual(set(timed), {build.ENTRY})
        self.assertEqual(set(armed), {build.ARMED['entry']})
        body = next(iter(armed.values()))
        self.assertIn(b'hd2.snapshot_control', body)
        self.assertNotIn(b'capture_snapshot', body, 'the armed package never captures on its own')
        for token in (b'VirtualProtect', b'WriteProcessMemory', b'ReadProcessMemory', b'ffi.', b'update='):
            self.assertNotIn(token, body)
        self.assertNotEqual(build.ARMED['guid'], json.loads((ROOT / 'snapshot_capture/hd2runtime.json').read_text())['guid'])


if __name__ == '__main__':
    unittest.main()
