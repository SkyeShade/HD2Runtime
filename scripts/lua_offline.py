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
