"""Bounded historical review counts through an EXISTING shared approved Client.

No transport, Client, DB, lease or scheduler is created. The normal shared worker
owns its exact40-call cap, native lease and15-minute requestful-pass gate.
"""
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
import hashlib,json,math,re

VERSION='listing-review-count-population-1'
BASIS='API_reported_filtered_exact_listing_review_count_not_purchases_or_universal_lifetime'
class InconsistentCount(ValueError):pass
def now():return datetime.now(timezone.utc).isoformat()
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(x):return hashlib.sha256(canonical(x).encode()).hexdigest()
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,x):
 tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(x,indent=2,allow_nan=False),encoding='utf-8');tmp.replace(p)
def utc(s):
 d=datetime.fromisoformat(s.replace('Z','+00:00'))
 if d.tzinfo is None:raise ValueError('timezone_aware_cutoff_required')
 return d.astimezone(timezone.utc)
def request_key(q):return digest(dict(path=q['path'],scope=q['scope'],params=q['params']))
def _has_forbidden_key(x):
 if isinstance(x,dict):return any(k in {'target','prediction','prediction_error','estimated_sales','rank','provider_price','provider_revenue','exported_views'} or _has_forbidden_key(v) for k,v in x.items())
 if isinstance(x,list):return any(_has_forbidden_key(v) for v in x)
 return False
def plan_value(plan):
 if isinstance(plan,(str,Path)):plan=json.loads(Path(plan).read_text(encoding='utf-8'))
 if _has_forbidden_key(plan):raise ValueError('teacher_targets_errors_or_provider_estimates_forbidden')
 if plan['version']!='listing-review-count-population-plan-1' or any(plan[k] is not False for k in ('source_eligibility','activation','model_fitting_or_selection')):raise ValueError('frozen_inactive_population_plan_required')
 if plan['max_client_calls_per_pass']!=40 or plan['normal_requestful_spacing_seconds']!=900:raise ValueError('normal_shared40_call_15minute_limits_required')
 refs=plan['references'];requests=plan['requests']
 if not 1<=len(refs)<=250 or len(refs)!=plan['reference_count'] or not 1<=len(requests)<=250 or len(requests)!=plan['grouped_request_count']:raise ValueError('bounded_exact_population_sizes_required')
 byref={r['reference_id']:r for r in refs};bykey={q['request_key']:q for q in requests}
 if len(byref)!=len(refs) or len(bykey)!=len(requests):raise ValueError('duplicate_reference_or_request_key')
 if dict(Counter(r['cohort'] for r in refs))!=plan['cohort_reference_counts']:raise ValueError('cohort_population_changed')
 assigned=set()
 for q in requests:
  if set(q)!={'request_key','listing_id','shop_id','path','scope','params','reference_ids','known_dated30d_count_max','reuse'}:raise ValueError('identity_date_and_review_fields_only_request_required')
  lid,sid=q['listing_id'],q['shop_id']
  if not isinstance(lid,str) or not re.fullmatch('[1-9][0-9]{0,29}',lid) or not isinstance(sid,str) or not re.fullmatch('[1-9][0-9]{0,29}',sid) or q['path']!='/listings/'+lid+'/reviews' or q['scope']!='listing_reviews' or request_key(q)!=q['request_key']:raise ValueError('exact_listing_shop_request_identity_required')
  ids=q['reference_ids']
  if set(q['params'])!={'limit','offset','min_created','max_created'} or any(type(v) is not int for v in q['params'].values()):raise ValueError('integer_bounded_review_request_params_required')
  if not ids or len(ids)!=len(set(ids)) or set(ids)&assigned or not set(ids)<=set(byref):raise ValueError('exact_unique_reference_request_association_required')
  assigned.update(ids);known=[]
  for key in ids:
   r=byref[key]
   if set(r)!={'reference_id','cohort','listing_id','shop_id','cutoff_utc','window_start_utc','known_dated30d_count','provider_exact_cutoff_known','cutoff_basis','request_key'}:raise ValueError('target_free_reference_projection_required')
   n=r['known_dated30d_count'];cutoff=utc(r['cutoff_utc']);start=utc(r['window_start_utc'])
   if type(n) is not int or n<0 or (cutoff-start).total_seconds()!=30*86400 or r['provider_exact_cutoff_known'] is not False:raise ValueError('known_nonnegative_complete_review_window_required')
   if r['listing_id']!=lid or r['shop_id']!=sid or r['request_key']!=q['request_key'] or q['params']!=dict(limit=1,offset=0,min_created=946684800,max_created=math.ceil(cutoff.timestamp())-1):raise ValueError('frozen_exact_historical_request_params_required')
   known.append(n)
  if type(q['known_dated30d_count_max']) is not int or q['known_dated30d_count_max']!=max(known):raise ValueError('known_subset_bound_changed')
  reused=q['reuse']
  if reused is not None:
   if type(reused['count']) is not int or reused['count']<max(known) or reused['count']<=0 or reused['shop_id']!=sid or not all(reused.get(k) is True for k in ('sample_identity_matches','sample_timestamp_in_bounds','sample_rating_valid')):raise ValueError('invalid_exact_probe_reuse')
 if assigned!=set(byref):raise ValueError('all_references_must_be_acquired_including_zeros')
 if sum(q['reuse'] is not None for q in requests)!=plan['reused_request_count'] or sum(q['reuse'] is None for q in requests)!=plan['new_request_count']:raise ValueError('reused_or_new_request_counts_changed')
 return plan

def response(payload,q):
 if not isinstance(payload,dict):raise InconsistentCount('response_not_object')
 count,rows=payload.get('count'),payload.get('results');known=q['known_dated30d_count_max']
 if type(count) is not int or count<0 or not isinstance(rows,list) or len(rows)>1:raise InconsistentCount('invalid_count_or_one_row_page_shape')
 if count<known:raise InconsistentCount('count_below_known_dated30d_subset')
 if count==0:
  if rows:raise InconsistentCount('zero_count_requires_empty_results')
  return dict(count=0,returned_sample_count=0,empty_zero_count_validated=True,sample_identity_matches=None,sample_timestamp_in_bounds=None,sample_rating_valid=None,count_basis=BASIS,capture_at_utc=now())
 if len(rows)!=1 or not isinstance(rows[0],dict):raise InconsistentCount('positive_count_requires_one_sample')
 raw=rows[0]
 if str(raw.get('listing_id'))!=q['listing_id'] or str(raw.get('shop_id'))!=q['shop_id']:raise InconsistentCount('sample_listing_or_shop_mismatch')
 stamp=raw.get('created_timestamp',raw.get('create_timestamp'));rating=raw.get('rating')
 if isinstance(stamp,bool) or not isinstance(stamp,(int,float)) or not math.isfinite(stamp) or not q['params']['min_created']<=stamp<=q['params']['max_created']:raise InconsistentCount('sample_timestamp_outside_requested_bounds')
 if type(rating) is not int or not 1<=rating<=5:raise InconsistentCount('invalid_sample_rating')
 return dict(count=count,returned_sample_count=1,empty_zero_count_validated=False,sample_identity_matches=True,sample_timestamp_in_bounds=True,sample_rating_valid=True,count_basis=BASIS,capture_at_utc=now())

def materialize(plan,state,output):
 bykey={r['request_key']:r for r in state['requests']};rows=[]
 for r in plan['references']:
  saved=bykey[r['request_key']];accepted=saved['status'] in ('complete','reused')
  rows.append(dict(reference_id=r['reference_id'],cohort=r['cohort'],listing_id=r['listing_id'],shop_id=r['shop_id'],cutoff_utc=r['cutoff_utc'],known_dated30d_count=r['known_dated30d_count'],listing_historical_review_count_reported=saved['count'] if accepted else None,status=saved['status'],request_key=r['request_key'],
   provenance=dict(count_basis=BASIS,request_params=next(q['params'] for q in plan['requests'] if q['request_key']==r['request_key']),captured_at_utc=saved.get('capture_at_utc'),reused=saved['status']=='reused',reason=saved.get('reason'),provider_exact_cutoff_known=False,cutoff_basis=r['cutoff_basis'],zero_reviews_are_not_zero_sales=True),source_eligibility=False,activation=False))
 (output/'reference-inputs.jsonl').write_text(''.join(json.dumps(r,allow_nan=False)+'\n' for r in rows),encoding='utf-8')
 _terminal_export(plan,state,output)
 return rows
def _terminal_export(plan,state,output):
 if any(r['status'] not in ('complete','reused','unknown') for r in state['requests']):return
 bykey={r['request_key']:r for r in state['requests']};rows=[]
 for r in plan['references']:
  saved=bykey[r['request_key']];known=saved['status'] in ('complete','reused')
  rows.append(dict(reference_id=r['reference_id'],listing_id=r['listing_id'],shop_id=r['shop_id'],cutoff_utc=r['cutoff_utc'],request_key=r['request_key'],status='complete' if known else 'unknown',count=saved['count'] if known else None,captured_at_utc=saved.get('capture_at_utc')))
 data=''.join(json.dumps(r,allow_nan=False)+'\n' for r in rows);counts=output/'counts-by-reference.jsonl';snapshot=output/'terminal-state.json';complete=output/'counts-completion.json'
 if complete.exists():
  receipt=json.loads(complete.read_text(encoding='utf-8'))
  if receipt['counts_sha256']!=sha(counts) or receipt['counts_sha256']!=hashlib.sha256(data.encode()).hexdigest() or receipt['raw_state_sha256']!=sha(snapshot) or receipt['plan_file_sha256']!=state['plan_file_sha256']:raise ValueError('immutable_terminal_count_export_changed')
  return
 if counts.exists() or snapshot.exists():raise ValueError('partial_terminal_export_preserved_requires_inspection')
 with snapshot.open('x',encoding='utf-8') as stream:json.dump(state,stream,indent=2,allow_nan=False)
 with counts.open('x',encoding='utf-8',newline='') as stream:stream.write(data)
 receipt=dict(status='terminal_counts_export',completed_at_utc=now(),plan_file_sha256=state['plan_file_sha256'],plan_canonical_sha256=state['plan_sha256'],counts_sha256=sha(counts),counts_file=counts.name,raw_state_sha256=sha(snapshot),raw_state_file=snapshot.name,reference_count=len(rows),all_requests_terminal=True,source_eligibility=False,activation=False,model_fitting_or_selection=False)
 with complete.open('x',encoding='utf-8') as stream:json.dump(receipt,stream,indent=2,allow_nan=False)
def summary(plan,state):
 accepted={r['request_key'] for r in state['requests'] if r['status'] in ('complete','reused')}
 return dict(accepted_requests=len(accepted),reused_requests=sum(r['status']=='reused' for r in state['requests']),new_complete_requests=sum(r['status']=='complete' for r in state['requests']),unknown_requests=sum(r['status']=='unknown' for r in state['requests']),pending_requests=sum(r['status']=='pending' for r in state['requests']),accepted_reference_rows=sum(r['request_key'] in accepted for r in plan['references']),halted=state['halted'])

def collect(client,plan,output):
 plan_file_sha256=sha(plan) if isinstance(plan,(str,Path)) else None
 plan=plan_value(plan);output=Path(output);output.mkdir(parents=True,exist_ok=True);path=output/'state.json';fingerprint=digest(plan)
 if type(client.requests) is not int or type(client.batch_limit) is not int or not 1<=client.batch_limit<=40 or 'listing_reviews' not in set(client.scopes):raise ValueError('existing_shared_approved_counted_client_required')
 if path.exists():
  state=json.loads(path.read_text(encoding='utf-8'))
  if state['version']!=VERSION or state['plan_sha256']!=fingerprint or state['plan_file_sha256']!=plan_file_sha256 or [r['request_key'] for r in state['requests']]!=[q['request_key'] for q in plan['requests']]:raise ValueError('frozen_plan_changed_use_original_output')
 else:
  cases=[]
  for q in plan['requests']:
   item=dict(request_key=q['request_key'],listing_id=q['listing_id'],status='pending',count=None,attempts=0)
   if q['reuse'] is not None:item.update(status='reused',count=q['reuse']['count'],capture_at_utc=q['reuse']['captured_at_utc'],reuse_provenance=q['reuse'],count_basis=BASIS)
   cases.append(item)
  state=dict(version=VERSION,plan_sha256=fingerprint,plan_file_sha256=plan_file_sha256,requests=cases,passes=[],halted=False,no_review_text_or_buyer_data_retained=True,source_eligibility=False,activation=False);write(path,state)
 if state['halted']:
  materialize(plan,state,output);return dict(status='halted_unknown_no_more_requests',requests=0,**summary(plan,state))
 if any(r['status']=='in_flight' for r in state['requests']):
  for r in state['requests']:
   if r['status']=='in_flight':r.update(status='unknown',reason='prior_dispatch_uncertain',count=None)
  state['halted']=True;write(path,state);materialize(plan,state,output);return dict(status='halted_prior_uncertain_dispatch',requests=0,**summary(plan,state))
 before=client.requests;receipt=dict(started_at_utc=now(),requests=0,status='running')
 try:
  for q,result in zip(plan['requests'],state['requests']):
   if result['status']!='pending':continue
   if client.requests>=min(client.batch_limit,40):receipt['status']='shared_batch_cap_reached';break
   result.update(status='in_flight',attempts=result['attempts']+1,started_at_utc=now());write(path,state);called_before=client.requests
   try:payload=client.get(q['path'],q['scope'],q['params'])
   except BaseException:
    if client.requests==called_before:result.update(status='pending',reason='source_or_budget_stopped_before_counted_dispatch')
    else:result.update(status='unknown',count=None,reason='source_or_transport_failed_after_counted_dispatch');state['halted']=True
    write(path,state);raise
   try:
    if client.requests!=called_before+1:raise InconsistentCount('review_call_not_counted_exactly_once')
    accepted=response(payload,q)
   except InconsistentCount as exc:
    result.update(status='unknown',count=None,reason=str(exc));state['halted']=True;receipt['status']='invalid_or_inconsistent_response';write(path,state);raise
   result.update(status='complete',**accepted);write(path,state)
  if receipt['status']=='running':receipt['status']='complete' if all(r['status'] in ('complete','reused') for r in state['requests']) else 'pending'
 except BaseException as exc:
  if receipt['status']=='running':receipt.update(status='source_or_budget_exception',exception_type=type(exc).__name__)
  raise
 finally:
  receipt.update(finished_at_utc=now(),requests=client.requests-before,absolute_client_requests=client.requests,**summary(plan,state));state['passes'].append(receipt);write(path,state);materialize(plan,state,output);write(output/'last-pass.json',receipt)
 return receipt
