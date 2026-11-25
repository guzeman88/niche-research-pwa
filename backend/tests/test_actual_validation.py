from datetime import datetime,timezone,timedelta
from services.sales_intelligence.actual_validation import compare


def inputs():
    end=datetime(2026,11,25,12,tzinfo=timezone.utc);start=end-timedelta(days=30)
    prediction={'listing_id':'123','shop_id':'456','model_id':'fixture','days':30,'unit':'units',
                'period_start':start.isoformat(),'period_end':end.isoformat(),'recorded_at':end.isoformat(),
                'value':9.5,'trained_at':start.isoformat(),'target_definition':'gross_paid_units_by_receipt_creation'}
    coverage={'since':start.timestamp(),'cutoff':end.timestamp(),'checked':end.timestamp()+3600}
    receipt={'receipt_id':'77','created_at':start.timestamp()+100,'modified_at':start.timestamp()+100,
             'is_paid':True,'transactions_complete':True,'transactions':[{'listing_id':'123','quantity':10}]}
    return prediction,coverage,[receipt]


def test_frozen_comparable_window_and_zero_denominator():
    prediction,coverage,receipts=inputs();result=compare(prediction,coverage,receipts,'456')
    assert result['actual']==10 and result['absolute_percentage_error']==5
    assert result['within_10_percent'] and not result['qualification_credit']
    prediction['value']=0;result=compare(prediction,coverage,[],'456')
    assert result['actual']==0 and result['absolute_percentage_error'] is None and result['within_10_percent']


def test_missing_coverage_ownership_timing_and_target_never_become_accuracy():
    prediction,coverage,receipts=inputs()
    for changes in ({'shop_id':'wrong'},{'target_definition':None},{'trained_at':'2026-11-24T12:00:00Z'},{'recorded_at':None},{'recorded_at':'2026-11-25T14:00:00Z'}):
        result=compare({**prediction,**changes},coverage,receipts,'456')
        assert result['actual'] is None and result['within_10_percent'] is None
    assert compare(prediction,None,receipts,'456')['status']=='incomplete_order_window'
    assert compare(prediction,coverage,receipts*2,'456')['status']=='duplicate_receipt'
    receipts[0]['transactions_complete']=False
    assert compare(prediction,coverage,receipts,'456')['actual'] is None
