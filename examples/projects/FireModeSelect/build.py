"""Build this mod using a shared, separately installed developer SDK."""
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parent
if __name__=='__main__':
    sdk=(ROOT/json.loads((ROOT/'hd2runtime.json').read_text())['sdk']).resolve()
    subprocess.run([sys.executable,'-B',str(sdk/'hd2.py'),'build',str(ROOT)],check=True)
