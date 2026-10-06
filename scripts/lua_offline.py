"""Execute a fixture in an isolated state of HD2's standalone Lua VM.

This loads only lua51.dll into the test process. It never loads the game
executable or game.dll, and fixtures provide all resource lookup themselves.
"""
import ctypes
import os
from pathlib import Path


def execute(script: bytes) -> bytes:
    game=Path(os.environ.get('HD2_GAME_ROOT',
        r'C:\Program Files (x86)\Steam\steamapps\common\Helldivers 2'))
    library=ctypes.CDLL(str(game/'bin/lua51.dll'))
    library.luaL_newstate.restype=ctypes.c_void_p
    library.luaL_openlibs.argtypes=[ctypes.c_void_p]
    library.luaL_loadbuffer.argtypes=[ctypes.c_void_p,ctypes.c_char_p,
                                      ctypes.c_size_t,ctypes.c_char_p]
    library.lua_pcall.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int]
    library.lua_tolstring.argtypes=[ctypes.c_void_p,ctypes.c_int,
                                    ctypes.POINTER(ctypes.c_size_t)]
    library.lua_tolstring.restype=ctypes.c_void_p
    library.lua_close.argtypes=[ctypes.c_void_p]
    state=library.luaL_newstate()
    if not state: raise RuntimeError('Offline luaL_newstate failed')
    try:
        library.luaL_openlibs(state)
        status=library.luaL_loadbuffer(state,script,len(script),b'@offline-resource-fixture')
        if status==0: status=library.lua_pcall(state,0,1,0)
        length=ctypes.c_size_t()
        pointer=library.lua_tolstring(state,-1,ctypes.byref(length))
        result=ctypes.string_at(pointer,length.value) if pointer else b''
        if status: raise RuntimeError(result.decode('utf-8','replace'))
        return result
    finally:
        library.lua_close(state)


# -- precompiled prefixes (tests/support.py run) ---------------------------------------------------------------------
# A prefix that only defines package.preload entries (no locals the script sees) can run as its own chunk before the
# script, in the same state. Compiled once to LuaJIT bytecode by this same lua51.dll (string.dump keeps line info),
# it loads several times faster than its source parses. Same chunk name, so its line numbers read as in execute().
CHUNK=b'@offline-resource-fixture'
LUA_GLOBALSINDEX=-10002
_library=None


def library():
    global _library
    if _library is None:
        game=Path(os.environ.get('HD2_GAME_ROOT',
            r'C:\Program Files (x86)\Steam\steamapps\common\Helldivers 2'))
        lib=ctypes.CDLL(str(game/'bin/lua51.dll'))
        lib.luaL_newstate.restype=ctypes.c_void_p
        lib.luaL_openlibs.argtypes=[ctypes.c_void_p]
        lib.luaL_loadbuffer.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_size_t,ctypes.c_char_p]
        lib.lua_pcall.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int]
        lib.lua_tolstring.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.POINTER(ctypes.c_size_t)]
        lib.lua_tolstring.restype=ctypes.c_void_p
        lib.lua_close.argtypes=[ctypes.c_void_p]
        lib.lua_settop.argtypes=[ctypes.c_void_p,ctypes.c_int]
        lib.lua_getfield.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_char_p]
        lib.lua_pushvalue.argtypes=[ctypes.c_void_p,ctypes.c_int]
        _library=lib
    return _library


def _top_string(lib,state):
    length=ctypes.c_size_t()
    pointer=lib.lua_tolstring(state,-1,ctypes.byref(length))
    return ctypes.string_at(pointer,length.value) if pointer else b''


def compile_chunk(source: bytes, name: bytes=CHUNK) -> bytes:
    """The LuaJIT bytecode of `source` (string.dump of its loaded chunk)."""
    lib=library()
    state=lib.luaL_newstate()
    if not state: raise RuntimeError('Offline luaL_newstate failed')
    try:
        lib.luaL_openlibs(state)
        if lib.luaL_loadbuffer(state,source,len(source),name):
            raise RuntimeError(_top_string(lib,state).decode('utf-8','replace'))
        lib.lua_getfield(state,LUA_GLOBALSINDEX,b'string')
        lib.lua_getfield(state,-1,b'dump')
        lib.lua_pushvalue(state,-3)
        if lib.lua_pcall(state,1,1,0):
            raise RuntimeError(_top_string(lib,state).decode('utf-8','replace'))
        return _top_string(lib,state)
    finally:
        lib.lua_close(state)


def execute_after(prefix: bytes, script: bytes) -> bytes:
    """Run `prefix` (source or bytecode; its result is discarded), then `script` in the same state, both named as in
    execute(); returns the script's result. A failure of either raises as execute() does."""
    lib=library()
    state=lib.luaL_newstate()
    if not state: raise RuntimeError('Offline luaL_newstate failed')
    try:
        lib.luaL_openlibs(state)
        for chunk in (prefix,script):
            status=lib.luaL_loadbuffer(state,chunk,len(chunk),CHUNK)
            if status==0: status=lib.lua_pcall(state,0,1,0)
            result=_top_string(lib,state)
            if status: raise RuntimeError(result.decode('utf-8','replace'))
            if chunk is prefix: lib.lua_settop(state,0)
        return result
    finally:
        lib.lua_close(state)
