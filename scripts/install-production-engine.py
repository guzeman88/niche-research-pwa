"""Install the Git-built private engine artifact after verifying its exact digest."""
from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).resolve().parents[1]/'backend/install_production_engine.py'),run_name='__main__')
