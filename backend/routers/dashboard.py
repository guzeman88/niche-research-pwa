"""Bounded, authenticated access to the canonical active research library."""
from contextlib import closing
from fastapi import APIRouter,Query
from services.dashboard_integration import connection,native_database,now

router=APIRouter(prefix='/api/dashboard',tags=['dashboard'])


@router.get('/keywords')
def keywords(q:str=Query('',max_length=200),domain:str=Query('',max_length=200),
             evidence:str=Query('',pattern='^(|verified|partial|failed|unverified)$'),
             sort:str=Query('status',pattern='^(keyword|domain|status|opportunity|gap|trajectory|listing_count|avg_price_usd)$'),
             direction:str=Query('asc',pattern='^(asc|desc)$'),offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=500)):
    filters=[];args=[]
    if q:
        filters.append("s.keyword LIKE ? ESCAPE '\\'")
        args.append('%'+q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%')
    if domain:filters.append('s.domain=?');args.append(domain)
    if evidence:
        filters.append("COALESCE(NULLIF(c.evidence_status,''),'unverified')=?")
        args.append(evidence)
    where=' WHERE '+' AND '.join(filters) if filters else ''
    order={'keyword':'s.keyword','domain':'s.domain','status':"CASE c.evidence_status WHEN 'verified' THEN 0 WHEN 'partial' THEN 1 WHEN 'failed' THEN 3 ELSE 2 END",
           'opportunity':'sc.opportunity_score','gap':'sc.gap_score','trajectory':'sc.trajectory',
           'listing_count':'c.listing_count','avg_price_usd':'c.avg_price_usd'}[sort]
    with closing(connection(native_database())) as con:
        con.execute('BEGIN')
        count_join=' LEFT JOIN keyword_collection_state c ON c.keyword=s.keyword' if evidence else ''
        total=con.execute('SELECT count(*) FROM seeds s'+count_join+where,args).fetchone()[0]
        sql="""WITH latest AS (SELECT keyword,max(id) id FROM scans WHERE score_version IS NOT NULL AND evidence_status='verified' GROUP BY keyword)
            SELECT s.keyword,s.domain,s.source,s.added_at,c.last_collected_at last_scanned_at,
              c.evidence_status,c.listing_count,c.sampled_listing_count,c.avg_price_usd,
              sc.opportunity_score,sc.gap_score,sc.trajectory,sc.score_version,sc.observed_search_volume
            FROM seeds s LEFT JOIN keyword_collection_state c ON c.keyword=s.keyword
            LEFT JOIN latest l ON l.keyword=s.keyword LEFT JOIN scans sc ON sc.id=l.id"""
        null_order=order+' IS NULL ASC,' if sort in ('listing_count','avg_price_usd') else ''
        rows=[dict(r) for r in con.execute(sql+where+' ORDER BY '+null_order+order+' '+direction+',s.keyword ASC LIMIT ? OFFSET ?',(*args,limit,offset))]
    for row in rows:
        row.update(scanned=bool(row['last_scanned_at']),evidence_status=row['evidence_status'] or 'unverified',breakout=False)
    return {'items':rows,'total':total,'offset':offset,'limit':limit,'scope':'native_collection_library','generated_at':now()}
