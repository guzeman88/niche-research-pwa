"""Read-only capacity checks; never clean, move or rewrite user data."""
from pathlib import Path
import shutil

MINIMUM_FREE=20*1024*1024*1024
WARNING_FREE=25*1024*1024*1024

def storage_state(*paths):
    free=[]
    try:
        for value in paths:
            path=Path(value).resolve()
            if not path.is_dir():path=path.parent
            while not path.exists() and path!=path.parent:path=path.parent
            free.append(shutil.disk_usage(path).free)
    except OSError:
        return {'status':'unknown','free_bytes':None,'minimum_free_bytes':MINIMUM_FREE}
    remaining=min(free) if free else None
    return {'status':'unknown' if remaining is None else 'critical' if remaining<MINIMUM_FREE else 'low' if remaining<WARNING_FREE else 'ok',
            'free_bytes':remaining,'minimum_free_bytes':MINIMUM_FREE}
