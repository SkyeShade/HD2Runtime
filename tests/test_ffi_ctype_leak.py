"""The C type leak (2026-10-08): LuaJIT never interns a function type, so ffi.cast('ret (*)(args)', p) in a function
called again and again adds new C types each call until LuaJIT's C type table overflows ('table overflow'; every later
FFI call fails, the custom multiplayer lobby reads and posts included). r51's mouse wheel retried such casts every frame
and failed live; the lobby read's own cast (windows_write) filled the table after about 11,000 calls on the game's
LuaJIT, a long multiplayer session's worth of polls. Every native call made more than once now casts through
windows_ffi.fn (one parsed type per declaration).

Checked here: on the game's own LuaJIT, 200,000 casts of each lobby signature through fn never overflow; and no Runtime
module casts a function-pointer declaration string inline outside the few reviewed sites that run once per session."""
import re
import unittest

from support import ROOT, run

# Inline function-pointer casts that run once per session (a cached upvalue or a backend built once), reviewed.
ONCE = {
    'runtime/input.lua': 'proc(): the Win32 backend is built once (backend cached; reset only in tests)',
    'runtime/mouse_wheel.lua': 'typed(): inside bindings(), built once and cached in win32',
    'runtime/windows_readonly.lua': 'process_id() and module_at() cache their function in an upvalue',
    'runtime/windows_ffi.lua': 'GetSystemInfo at module load (the module is kept in _G)',
}
INLINE = re.compile(r"ffi\.cast\(\s*(signature\b|'[^'\n]*(\(\*\)|__stdcall \*\)))")


class CTypeLeakTests(unittest.TestCase):
    def test_cached_function_types_never_overflow_on_the_games_luajit(self):
        self.assertEqual(run(r'''
local ffi=require('ffi')
local win=require('hd2runtime/runtime/windows_ffi')
local p=ffi.cast('void *',0)
for i=1,200000 do
    local a=ffi.cast(win.fn('int32_t (*)(void *, uint32_t, const char **, const char **)'),p)
    local b=ffi.cast(win.fn('const char *(*)(void *, uint64_t, const char *)'),p)
end
assert(win.fn('void (*)(void *)')==win.fn('void (*)(void *)'),'one type per declaration')
return 'ok'
'''), b'ok')

    def test_no_module_casts_a_function_declaration_inline_outside_the_reviewed_once_sites(self):
        found = []
        for folder in ('runtime', 'core', 'api'):
            for path in sorted((ROOT / folder).glob('*.lua')):
                rel = path.relative_to(ROOT).as_posix()
                for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                    code = line.split('--', 1)[0]
                    if INLINE.search(code) and rel not in ONCE:
                        found.append('%s:%d: %s' % (rel, number, line.strip()))
        self.assertEqual(found, [], 'cast through windows_ffi.fn (a C type parsed once):\n' + '\n'.join(found))


if __name__ == '__main__':
    unittest.main()
