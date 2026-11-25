"""Match frozen estimates to complete own-shop receipt windows, without promotion.

Gross units/purchases by receipt creation are a declared target. They are not net
sales, profitability or a population accuracy claim. Missing data stays unknown.
"""
from contextlib import closing
import json
import math
from . import store

TARGETS={'units':'gross_paid_units_by_receipt_creation','purchases':'gross_paid_purchases_by_receipt_creation'}


def compare(prediction,coverage,receipts,shop_id):
    def pending(reason):return {'status':reason,'actual':None,'absolute_percentage_error':None,'within_10_percent':None}
    try:
        start=store.stamp(prediction['period_start']).timestamp();end=store.stamp(prediction['period_end']).timestamp()
        recorded=store.stamp(prediction['recorded_at']).timestamp()
        predicted=prediction['value'];unit=prediction['unit'];target=TARGETS.get(unit)
        if (not target or prediction.get('target_definition')!=target):return pending('target_definition_not_comparable')
        if prediction.get('shop_id')!=shop_id:return pending('listing_ownership_not_verified')
        if store.stamp(prediction['trained_at']).timestamp()>start:return pending('window_not_held_out_from_training')
        if (isinstance(predicted,bool) or not isinstance(predicted,(int,float)) or not math.isfinite(predicted)
                or predicted<0 or end<=start or abs((end-start)-prediction['days']*86400)>1):return pending('invalid_prediction')
        if not coverage or coverage['since']>start or coverage['cutoff']<end:return pending('incomplete_order_window')
        if recorded>end+300 or recorded<end or recorded>=coverage['checked']:return pending('prediction_not_frozen_before_order_check')
        identity=set();actual=0
        for receipt in receipts:
            key=receipt['receipt_id']
            if key in identity:return pending('duplicate_receipt')
            identity.add(key)
            created=receipt['created_at'];modified=receipt['modified_at']
            if created is None or modified is None or modified<created:return pending('receipt_dates_unknown')
            if not start<=created<end:continue
            if receipt['is_paid'] is None:return pending('payment_status_unknown')
            if receipt['is_paid'] is not True:continue
            if not receipt['transactions_complete']:return pending('receipt_items_incomplete')
            matching=[item for item in receipt['transactions'] if item['listing_id']==prediction['listing_id']]
            actual+=sum(item['quantity'] for item in matching) if unit=='units' else int(bool(matching))
        error=abs(predicted-actual)/actual if actual else None
        return {'status':'matched_own_shop_window','actual':actual,'prediction':predicted,
                'absolute_percentage_error':error*100 if error is not None else None,
                'absolute_error':abs(predicted-actual),'within_10_percent':error<=.10 if error is not None else predicted==0,
                'target_definition':target,'qualification_credit':False}
    except (KeyError,ValueError,TypeError,OverflowError):return pending('recording_or_window_proof_missing')


def report(account):
    from services.seller_connection import configured_store,ConnectionFailure
    try:
        seller=configured_store()
        with closing(seller.connect()) as con:
            shop=con.execute("SELECT shop_id FROM seller_connections WHERE account=? AND status='connected'",(account,)).fetchone()
            if not shop:return {'status':'seller_not_connected','matched':0,'cases':[],'general_accuracy':None}
            if not con.execute("SELECT 1 FROM sqlite_master WHERE name='seller_order_coverage'").fetchone():
                return {'status':'awaiting_complete_order_capture','matched':0,'cases':[],'general_accuracy':None}
            coverage=con.execute('SELECT * FROM seller_order_coverage WHERE account=?',(account,)).fetchone()
            sync=con.execute('SELECT status FROM seller_order_sync WHERE account=?',(account,)).fetchone()
            if not sync or sync['status']!='completed':coverage=None
            count=con.execute('SELECT count(*) FROM seller_orders WHERE account=?',(account,)).fetchone()[0]
            if count>10000:return {'status':'order_volume_requires_review','matched':0,'cases':[],'general_accuracy':None}
            receipts=[json.loads(row[0]) for row in con.execute('SELECT v.payload FROM seller_orders o JOIN seller_order_versions v ON v.account=o.account AND v.identity=o.identity AND v.digest=o.digest WHERE o.account=?',(account,))]
        with store.database() as con:
            predictions=[json.loads(row[0]) for row in con.execute('SELECT payload FROM predictions ORDER BY as_of DESC LIMIT 500')]
        cases=[]
        for prediction in predictions:
            if prediction.get('shop_id')!=shop['shop_id']:continue
            cases.append({'listing_id':prediction['listing_id'],'model_id':prediction['model_id'],
                          'period_start':prediction['period_start'],'period_end':prediction['period_end'],
                          **compare(prediction,dict(coverage) if coverage else None,receipts,shop['shop_id'])})
        matched=[case for case in cases if case['status']=='matched_own_shop_window']
        total=sum(case['actual'] for case in matched)
        return {'status':'comparisons_available' if matched else 'awaiting_comparable_frozen_predictions',
                'matched':len(matched),'cases':cases,'evaluated_prediction_limit':500,
                'wape_percent':100*sum(case['absolute_error'] for case in matched)/total if total else None,
                'within_10_percent':sum(case['within_10_percent'] for case in matched)/len(matched) if matched else None,
                'general_accuracy':None,'automatic_training':False,'automatic_promotion':False,
                'basis':'Own-shop captured receipts; gross paid units or purchases by creation date. No net-sales or competitor accuracy claim.'}
    except ConnectionFailure:return {'status':'seller_not_configured','matched':0,'cases':[],'general_accuracy':None}
