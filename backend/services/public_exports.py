"""Bounded public research packages, generated off the request path.

Only the existing public keyword projection is read. Account/customer stores and
artwork are not inputs. The account project receives status, never these files.
"""
from pathlib import Path
from contextlib import contextmanager
import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse
from starlette.middleware.gzip import GZipMiddleware

FILES = frozenset(('stats.json','opportunities.json','store-ideas.json','gaps.json',
                   'breakouts.json','reports.json','test-candidates.json'))
MAX_FILE = 8 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024
INTERVAL = 6 * 3600


class PublicExportCompression:
    """Compress public JSON export streams before the home uplink, not artwork."""
    def __init__(self, app):
        self.app=app
        self.compressed=GZipMiddleware(app,minimum_size=1024,compresslevel=5)

    async def __call__(self,scope,receive,send):
        path=scope.get('path','')
        selected=scope['type']=='http' and (path=='/api/export/public-snapshot' or path.startswith('/api/export/public-snapshot/'))
        await (self.compressed if selected else self.app)(scope,receive,send)


def now():
    return datetime.now(timezone.utc).isoformat()


def root():
    from services.product_validation import db_path
    return Path(os.environ.get('APP_PUBLIC_EXPORT_ROOT') or db_path().parent/'public-research-exports').resolve()


def valid_name(name):
    return name in FILES or bool(re.fullmatch(r'keywords/part-[0-9]{5}\.json', name))


def remove_owned_directory(path, parent, pattern):
    if (path.is_symlink() or getattr(path,'is_junction',lambda:False)()
            or path.resolve().parent != parent.resolve() or not re.fullmatch(pattern,path.name)):
        raise ValueError('Refusing to remove an unexpected cache directory')
    shutil.rmtree(path)


@contextmanager
def staging(directory):
    stage = directory/('stage-'+uuid.uuid4().hex)
    stage.mkdir(mode=0o700)
    try:yield stage
    finally:
        if stage.exists():remove_owned_directory(stage,directory,r'stage-[a-f0-9]{32}')


def status():
    try:return json.loads((root()/'status.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):return {'enabled':os.environ.get('APP_PUBLIC_EXPORT_ENABLED')=='1','status':'not_ready'}


def load_manifest(directory, verify=False):
    if (directory.is_symlink() or getattr(directory,'is_junction',lambda:False)()
            or not directory.resolve().is_relative_to(root())):
        raise ValueError('Public research directory escapes its cache')
    if (directory/'release.json').stat().st_size > 256*1024:
        raise ValueError('Public research manifest exceeds its bound')
    manifest = json.loads((directory/'release.json').read_text(encoding='utf-8'))
    if (not isinstance(manifest,dict) or manifest.get('schema_version') != 1 or manifest.get('source') != 'supabase_local'
            or manifest.get('scope') != 'local_research_projection'
            or not re.fullmatch('[a-f0-9]{64}', manifest.get('id',''))
            or not re.fullmatch('[a-f0-9]{40}', manifest.get('commit',''))):
        raise ValueError('Invalid public research identity')
    files = manifest.get('files', {})
    if not isinstance(files,dict) or not 1 <= len(files) <= 512:
        raise ValueError('Invalid public research file count')
    total = 0
    for name, record in files.items():
        if (not valid_name(name) or not isinstance(record,dict) or type(record.get('bytes')) is not int
                or not 2 <= record['bytes'] <= MAX_FILE
                or not re.fullmatch('[a-f0-9]{64}', record.get('sha256',''))):
            raise ValueError('Invalid public research file')
        total += record['bytes']
        if verify:
            path = directory/name
            if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
                raise ValueError('Public research file escapes its package')
            with path.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            if path.stat().st_size != record['bytes'] or digest != record['sha256']:
                raise ValueError('Public research checksum failed')
    if total > MAX_TOTAL:
        raise ValueError('Public research package exceeds its bound')
    identity = {key:manifest[key] for key in ('commit','source_data_as_of','files','resources')}
    if hashlib.sha256(json.dumps(identity,separators=(',',':'),ensure_ascii=False).encode()).hexdigest() != manifest['id']:
        raise ValueError('Public research identity checksum failed')
    resources = manifest['resources']
    if not isinstance(resources,dict) or set(resources) != FILES | {'keywords.json'}:
        raise ValueError('Incomplete public research resources')
    if any(not isinstance(value,dict) for value in resources.values()):
        raise ValueError('Invalid public research resources')
    keywords=resources['keywords.json']
    parts = keywords.get('parts')
    if (not isinstance(parts,list) or type(keywords.get('items')) is not int
            or keywords['items']<0 or any(resources[name].get('path')!=name for name in FILES)):
        raise ValueError('Invalid public keyword resource')
    expected = [f'keywords/part-{i:05d}.json' for i in range(len(parts))]
    if not parts or parts != expected or set(files) != FILES | set(parts):
        raise ValueError('Incomplete public keyword partitions')
    return manifest


def current_package():
    pointer = json.loads((root()/'current.json').read_text(encoding='utf-8'))
    identity = pointer.get('id','')
    if not re.fullmatch('[a-f0-9]{64}', identity):
        raise ValueError('Invalid public research pointer')
    directory = root()/'versions'/identity
    manifest = load_manifest(directory)
    if manifest['id'] != identity:
        raise ValueError('Public research pointer differs')
    return directory, manifest


def package_file(identity, name):
    if not re.fullmatch('[a-f0-9]{64}', identity) or not valid_name(name):
        raise ValueError('Unsupported public research file')
    directory = root()/'versions'/identity
    manifest = load_manifest(directory)
    if manifest['id'] != identity or name not in manifest['files']:
        raise ValueError('Public research file is absent')
    path = directory/name
    if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
        raise ValueError('Public research file escapes its package')
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream,'sha256').hexdigest()
    if path.stat().st_size != manifest['files'][name]['bytes'] or digest != manifest['files'][name]['sha256']:
        raise ValueError('Public research file changed')
    return path


class Worker:
    def __init__(self):
        self.task = None
        self.process = None
        self.stopping = False
        self.lock = threading.RLock()
        self.event = asyncio.Event()
        self.state = {'enabled':True,'status':'starting','last_attempt':None,'last_success':None}

    def status(self):
        with self.lock:
            return dict(self.state)

    def update(self, **values):
        with self.lock:
            self.state = {**self.state, **values}
            directory=root();directory.mkdir(parents=True,exist_ok=True,mode=0o700)
            temporary=directory/'status.json.tmp'
            temporary.write_text(json.dumps(self.state),encoding='utf-8')
            os.replace(temporary,directory/'status.json')

    def start(self):
        self.task = asyncio.create_task(self.run())

    def request(self):
        self.event.set()
        return self.status()

    def terminate(self):
        with self.lock:
            child = self.process
        if child and child.poll() is None:
            child.terminate()
            try: child.wait(10)
            except subprocess.TimeoutExpired: child.kill();child.wait(5)

    async def stop(self):
        with self.lock:self.stopping = True
        self.event.set()
        await asyncio.to_thread(self.terminate)
        if self.task:
            await self.task

    def refresh(self):
        if self.stopping:return
        from etgen_production.marketplace import lock
        directory = root()
        directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        if shutil.disk_usage(directory).free < 2*1024**3:
            raise ValueError('Public export storage reserve is unavailable')
        repo = Path(__file__).resolve().parents[2]
        release = json.loads((repo/'dist/data/release.json').read_text(encoding='utf-8'))
        commit = release.get('commit','')
        url = os.environ.get('SUPABASE_URL','')
        if not re.fullmatch('[a-f0-9]{40}',commit) or urlparse(url).hostname not in ('localhost','127.0.0.1','::1'):
            raise ValueError('Public export requires the pinned local research service')
        key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY','')
        node = Path(os.environ.get('APP_PUBLIC_EXPORT_NODE') or shutil.which('node') or '')
        if not key or not node.is_file():
            raise ValueError('Public export dependencies are not configured')
        with lock(directory/'generation.lock'), staging(directory) as stage:
            env = dict(os.environ, SNAPSHOT_SOURCE='supabase',SNAPSHOT_LAYOUT='sharded-v1',
                       SNAPSHOT_OUTPUT_DIR=str(stage),SNAPSHOT_COMMIT=commit,
                       MIN_GOOGLE_VOLUME_COUNT='30000',PIPELINE_PYTHON=sys.executable)
            self.update(status='generating',last_attempt=now())
            with (directory/'last-generation.log').open('w',encoding='utf-8') as log:
                with self.lock:
                    if self.stopping:return
                    child = subprocess.Popen([str(node),str(repo/'scripts/build-data.cjs'),'--etgen-public-export'],
                        cwd=repo,env=env,stdout=log,stderr=subprocess.STDOUT,
                        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    self.process = child
                try:
                    if child.wait(600):raise ValueError('Public research generation failed')
                except subprocess.TimeoutExpired:
                    self.terminate();raise ValueError('Public research generation timed out') from None
                finally:
                    with self.lock:self.process = None
            if self.stopping:return
            manifest = load_manifest(stage,verify=True)
            versions = directory/'versions';versions.mkdir(exist_ok=True)
            destination = versions/manifest['id']
            if destination.exists():
                previous = load_manifest(destination,verify=True)
                if previous['files'] != manifest['files']:raise ValueError('Public package identity collision')
                manifest = previous
            else:stage.rename(destination)
            pointer = directory/'current.json.tmp'
            pointer.write_text(json.dumps({'id':manifest['id']}),encoding='utf-8')
            os.replace(pointer,directory/'current.json')
            self.update(status='ready',last_success=now(),snapshot_id=manifest['id'],
                        generated_at=manifest['generated_at'],source_data_as_of=manifest['source_data_as_of'],
                        keyword_count=manifest['resources']['keywords.json']['items'],error=None)
            candidates=[]
            for previous in versions.iterdir():
                if previous.is_dir() and re.fullmatch('[a-f0-9]{64}',previous.name) and previous.name!=manifest['id']:
                    try:
                        old=load_manifest(previous,verify=True)
                        expected={str(previous/name) for name in old['files']}|{str(previous/'release.json')}
                        if {str(p) for p in previous.rglob('*') if p.is_file()}==expected:
                            candidates.append(previous)
                    except (OSError,ValueError,KeyError):pass
            # Keep the current and one preceding complete generated cache. Raw
            # research, source archives and unexpected/user files are untouched.
            for previous in sorted(candidates,key=lambda p:p.stat().st_mtime,reverse=True)[1:]:
                remove_owned_directory(previous,versions,r'[a-f0-9]{64}')

    async def run(self):
        while not self.stopping:
            self.event.clear()
            delay = INTERVAL
            try:await asyncio.to_thread(self.refresh)
            except Exception:
                self.update(status='needs_attention',error='public_export_failed');delay = 300
            if self.stopping:return
            try:await asyncio.wait_for(self.event.wait(),timeout=delay)
            except asyncio.TimeoutError:pass
            if not self.stopping and self.event.is_set():
                await asyncio.sleep(5)  # Coalesce requests; no duplicate generators.


def configured_worker():
    return Worker() if os.environ.get('APP_PUBLIC_EXPORT_ENABLED') == '1' else None
