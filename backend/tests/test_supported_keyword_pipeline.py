from datetime import datetime, timedelta, timezone
import json
import pytest

from pipeline import keyword_database as db
from services import supported_keywords as support, research_listing as listing, product_validation as validation


@pytest.fixture
def research(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'DB_PATH', tmp_path/'research.sqlite')
    monkeypatch.setenv('VALIDATION_DB_PATH', str(tmp_path/'ledger.sqlite'))
    db.init_db()
    return db


def evidence(con, keyword, at, volume=1000, count=500, sample=50, variants=(), title=None):
    timestamp = at.isoformat()
    run = keyword + ':' + timestamp
    con.execute('INSERT OR IGNORE INTO seeds VALUES(?,?,?,?)', (keyword, 'product', 'manual', timestamp))
    for source, metric, value, geo, metadata in [('etsy_open_api','listing_count',count,None,{}),
        ('google_ads_keyword_planner','monthly_searches',volume,'US',{'close_variants':list(variants)})]:
        con.execute('''INSERT INTO provider_keyword_state(provider,keyword,last_attempt_at,status,row_count)
            VALUES(?,?,?,?,?) ON CONFLICT(provider,keyword) DO UPDATE SET last_attempt_at=excluded.last_attempt_at,
            status=excluded.status,row_count=excluded.row_count''', (source,keyword,timestamp,'no_data' if value is None else 'completed',int(value is not None)))
        if value is None:
            continue
        con.execute('''INSERT INTO keyword_observations(keyword,source,observed_at,metric,value,unit,metadata_json,geography,period_start,period_end,collection_run_id)
            VALUES(?,?,?,?,?,'count',?,?,?,?,?)''', (keyword,source,timestamp,metric,value,json.dumps(metadata),geo,
            (at-timedelta(days=365)).date().isoformat(),(at-timedelta(days=30)).date().isoformat(),run))
    for i in range(sample):
        con.execute('''INSERT INTO keyword_listing_snapshots(keyword,source,observed_at,listing_id,title,shop_name,collection_run_id,price,currency_code)
            VALUES(?,'etsy_open_api',?,?,?,?,?,18.5,'USD')''',(keyword,timestamp,str(i),title or keyword,str(i%10),run))


def test_baseline_refreshes_and_aliases_do_not_inflate_month(research):
    at = datetime(2026,10,14,tzinfo=timezone.utc)
    with research._conn() as con:
        evidence(con,'teacher mug',at)
        report = support.refresh(con,at)
        assert report['baseline_groups'] == 1
        assert report['qualified_this_month'] == 0
        later=at+timedelta(days=1)
        evidence(con,'nurse mug',later,variants=['nurse mugs'])
        evidence(con,'nurse mugs',later,variants=['nurse mug'])
        report=support.refresh(con,later)
        assert report['qualified_this_month'] == 1
        assert report['available_supported_groups'] == 2
        for _ in range(2):
            assert support.refresh(con,later)['qualified_this_month'] == 1
        saved=con.execute("SELECT first_evidence_json FROM feed_supported_keywords WHERE keyword='nurse mug'").fetchone()[0]
        evidence(con,'nurse mug',later+timedelta(days=1),volume=None)
        support.refresh(con,later+timedelta(days=1))
        assert con.execute("SELECT status FROM feed_supported_keywords WHERE keyword='nurse mug'").fetchone()[0] == 'needs_evidence'
        assert con.execute("SELECT first_evidence_json FROM feed_supported_keywords WHERE keyword='nurse mug'").fetchone()[0] == saved


@pytest.mark.parametrize('volume,count,sample,title', [(0,500,50,None),(None,500,50,None),
    (1000,4000,50,None),(1000,500,10,None),(1000,500,50,'unrelated downloadable poster')])
def test_unknown_low_demand_supply_and_irrelevance_do_not_qualify(research, volume,count,sample,title):
    at=datetime.now(timezone.utc)
    with research._conn() as con:
        evidence(con,'teacher mug',at,volume,count,sample,title=title)
        assert support.refresh(con,at)['available_supported_groups'] == 0


def test_stale_future_and_mismatched_collection_samples_stay_unknown(research):
    at=datetime.now(timezone.utc)
    with research._conn() as con:
        evidence(con,'teacher mug',at-timedelta(days=8))
        evidence(con,'nurse mug',at+timedelta(days=1))
        evidence(con,'coder mug',at)
        con.execute("UPDATE keyword_listing_snapshots SET collection_run_id='other' WHERE keyword='coder mug'")
        assert support.refresh(con,at)['available_supported_groups'] == 0


def test_small_complete_sample_can_qualify_and_month_credit_never_repeats(research):
    at=datetime(2026,10,14,tzinfo=timezone.utc)
    with research._conn() as con:
        support.refresh(con,at)
        evidence(con,'teacher mug',at,count=12,sample=12)
        assert support.refresh(con,at)['qualified_this_month'] == 1
        next_month=at.replace(month=11)
        evidence(con,'teacher mug',next_month,count=12,sample=12)
        report=support.refresh(con,next_month)
        assert report['qualified_this_month'] == 0
        assert report['available_supported_groups'] == 1


def test_direct_etsy_counts_require_identical_window_and_scope(research):
    at=datetime.now(timezone.utc)
    with research._conn() as con:
        evidence(con,'teacher mug',at,volume=None)
        for metric, geo, value in [('searches','US',1000),('listing_count','GB',500)]:
            con.execute('''INSERT INTO keyword_observations(keyword,source,observed_at,metric,value,unit,geography,period_start,period_end)
                VALUES('teacher mug','etsy_marketplace_insights',?,?,?,'count',?,?,?)''',
                (at.isoformat(),metric,value,geo,(at-timedelta(days=30)).date().isoformat(),(at-timedelta(days=1)).date().isoformat()))
        assert support.refresh(con,at)['available_supported_groups'] == 0
        con.execute("UPDATE keyword_observations SET geography='US' WHERE source='etsy_marketplace_insights'")
        report=support.refresh(con,at)
        assert report['etsy_demand_backed_groups'] == 1
        assert report['candidates'][0]['etsy_marketplace']['ratio'] == 2


def test_alias_merge_reconciles_previous_credit(research):
    at=datetime(2026,10,14,tzinfo=timezone.utc)
    with research._conn() as con:
        support.refresh(con,at)
        evidence(con,'teacher mug',at)
        evidence(con,'teacher mugs',at)
        assert support.refresh(con,at)['qualified_this_month'] == 2
        evidence(con,'teacher mug',at+timedelta(hours=1),variants=['teacher mugs'])
        assert support.refresh(con,at+timedelta(hours=1))['qualified_this_month'] == 1


def test_draft_unknown_costs_no_publication_and_revisions_preserve_work(research):
    at=datetime.now(timezone.utc)-timedelta(minutes=1)
    with research._conn() as con:
        evidence(con,'teacher mug',at)
        support.refresh(con,at)
    facts={'keyword':'teacher mug','product_name':'Personalized Ceramic Teacher Mug',
           'product_type':'mug','details':'A ceramic mug with your chosen teacher name.',
           'material':'ceramic','product_matches_keyword':True}
    result=listing.create_draft(facts)
    assert result['draft']['facts']['price'] is None
    assert result['draft']['audit']['can_publish'] is False
    assert 'Complete conservative product economics' in result['draft']['audit']['blockers']
    assert result['draft']['support_fingerprint']
    project = validation.summary(result['project_id'])
    assert project['queue'][0]['sample_count'] == 50
    assert validation.records(result['project_id'], 'competitors')[0]['payload']['relevance_reviewed'] is False
    assert listing.create_draft(facts)['duplicate'] is True
    assert len(validation.records(kind='project')) == 1
    assert len(validation.records(kind='listing_draft')) == 1
    updated=listing.create_draft({**facts,'price':'24.99'})
    assert not updated['duplicate']
    assert updated['project_id'] == result['project_id']
    assert listing.export_draft(result['id'])['publication_performed'] is False
    with validation.connect() as con:
        assert con.execute("SELECT count(*) FROM revisions WHERE record_id=?",(result['id'],)).fetchone()[0] == 2
    with research._conn() as con:
        con.execute("UPDATE feed_supported_keywords SET status='needs_evidence'")
    exported=listing.export_draft(result['id'])
    assert not exported['draft']['audit']['keyword_supported']
    with pytest.raises(ValueError,match='Refresh'):
        listing.create_draft(facts)


def test_draft_requires_real_facts_and_confirmation(research):
    at=datetime.now(timezone.utc)-timedelta(minutes=1)
    with research._conn() as con:
        evidence(con,'teacher mug',at)
        support.refresh(con,at)
    facts={'keyword':'teacher mug','product_name':'Teacher Mug','product_type':'mug','details':'Teacher mug.'}
    with pytest.raises(ValueError,match='Confirm'):
        listing.create_draft(facts)
    with pytest.raises(ValueError,match='Price'):
        listing.create_draft({**facts,'product_matches_keyword':True,'price':float('nan')})
    assert validation.records() == []
