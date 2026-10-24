"""Small standalone Lua states; no research submodule or game process needed."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from lua_offline import execute

def modules(names):
    chunks=[]
    for name in names:
        source=(ROOT/(name+'.lua')).read_text(encoding='utf-8')
        chunks.append('package.preload["hd2runtime/'+name+'"]=function(...)\n'+source+'\nend\n')
    return ''.join(chunks)

def run(body,names=()):
    return execute((modules(names)+body+"\nreturn 'ok'").encode('utf-8'))
