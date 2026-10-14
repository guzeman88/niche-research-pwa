"""Install the Git-built private engine artifact after verifying its exact digest."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
pin=json.loads((root/'backend/production-engine.json').read_text())
wheel=root/'backend/vendor'/pin['wheel']
if wheel.name!=pin['wheel'] or not wheel.resolve().is_relative_to((root/'backend/vendor').resolve()):raise ValueError('Unsafe production artifact')
if hashlib.sha256(wheel.read_bytes()).hexdigest()!=pin['sha256']:raise ValueError('Production engine artifact changed')
subprocess.run([sys.executable,'-m','pip','install','--force-reinstall','--no-deps',str(wheel)],check=True)
