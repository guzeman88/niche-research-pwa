import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone
import pytest
from services import public_exports, public_collection


def generator(tmp_path,monkeypatch):
    repo=tmp_path/'code'
    (repo/'backend/services').mkdir(parents=True)
    (repo/'dist/data').mkdir(parents=True)
    (repo/'dist/data/release.json').write_text(json.dumps({'commit':'a'*40}))
    (repo/'scripts').mkdir()
    package=Path(public_exports.__file__).resolve().parents[2]/'scripts/public-research-package.cjs'
    (repo/'scripts/build-data.cjs').write_text('''
if(process.env.TEST_FAIL==='1')process.exit(2);
const {writePackage}=require(PACKAGE);
const n=Number(process.env.TEST_ROWS||2),data=Object.fromEntries(require(PACKAGE).names.map(name=>[name,name==='stats.json'?{total_seeds:n}:name==='keywords.json'?Array.from({length:n},(_,i)=>({keyword:'fixture '+i})):[]]));
writePackage(process.env.SNAPSHOT_OUTPUT_DIR,data,{commit:process.env.SNAPSHOT_COMMIT,sourceDataAsOf:'2026-11-25T12:00:00Z'});
'''.replace('PACKAGE',json.dumps(str(package))),encoding='utf-8')
    monkeypatch.setattr(public_exports,'__file__',str(repo/'backend/services/public_exports.py'))
    monkeypatch.setenv('APP_PUBLIC_EXPORT_ROOT',str(tmp_path/'cache'))
    monkeypatch.setenv('APP_PUBLIC_EXPORT_NODE',shutil.which('node') or '')
    monkeypatch.setenv('SUPABASE_URL','http://127.0.0.1:54321')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY','fixture-not-a-secret')
    return public_exports.Worker()


def test_atomic_export_preserves_complete_version_after_failure_and_rejects_corruption(tmp_path,monkeypatch):
    worker=generator(tmp_path,monkeypatch);worker.refresh()
    directory,first=public_exports.current_package()
    assert first['resources']['keywords.json']['items']==2
    assert public_exports.package_file(first['id'],'stats.json').is_file()
    monkeypatch.setenv('TEST_FAIL','1')
    with pytest.raises(ValueError):worker.refresh()
    assert public_exports.current_package()[1]['id']==first['id']
    assert not list((tmp_path/'cache').glob('stage-*'))
    with pytest.raises(ValueError):public_exports.package_file(first['id'],'../../private.env')
    (directory/'stats.json').write_text('{}')
    with pytest.raises(ValueError):public_exports.package_file(first['id'],'stats.json')


def test_cache_retention_preserves_unknown_user_files(tmp_path,monkeypatch):
    worker=generator(tmp_path,monkeypatch);worker.refresh()
    first,_=public_exports.current_package();(first/'operator-note.txt').write_text('preserve')
    for count in (3,4,5):monkeypatch.setenv('TEST_ROWS',str(count));worker.refresh()
    assert (first/'operator-note.txt').read_text()=='preserve'
    assert len(list((tmp_path/'cache/versions').iterdir()))==3
    assert public_exports.current_package()[1]['resources']['keywords.json']['items']==5


def test_native_collection_counts_measure_one_window_without_fabricating_missing_tables(tmp_path):
    path=tmp_path/'library.sqlite'
    with sqlite3.connect(path) as con:
        con.execute('CREATE TABLE keyword_observations(source TEXT,observed_at TEXT)')
        con.executemany('INSERT INTO keyword_observations VALUES(?,?)',[
            ('etsy_open_api','2026-11-25T01:00:00Z'),('etsy_open_api','2026-11-20T00:00:00Z'),
            ('google_ads_keyword_planner','2026-11-25T01:00:00Z'),('google_keyword_planner','2026-11-25T02:00:00Z')])
    result=public_collection.measure(path,datetime(2026,11,25,12,tzinfo=timezone.utc))
    assert result['counts']['etsy_observations_total']==2
    assert result['counts']['etsy_observations_24h']==1
    assert result['counts']['google_planner_observations_24h']==2
    assert result['counts']['erank_observations_total']==0
    assert 'etsy_listings_total' not in result['counts']
    assert result['data_status']=='partial'
