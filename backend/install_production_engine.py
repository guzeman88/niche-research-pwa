"""Verify and install the Git-built engine from this backend's bundled wheel."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parent
pin=json.loads((root/'production-engine.json').read_text())
wheel=root/'vendor'/pin['wheel']
if wheel.name!=pin['wheel'] or not wheel.resolve().is_relative_to((root/'vendor').resolve()):raise ValueError('Unsafe production artifact')
if hashlib.sha256(wheel.read_bytes()).hexdigest()!=pin['sha256']:raise ValueError('Production engine artifact changed')
subprocess.run([sys.executable,'-m','pip','install','--force-reinstall','--no-deps',str(wheel)],check=True)
