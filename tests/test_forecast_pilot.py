import copy
import json
from pathlib import Path
import unittest
from scripts import forecast_pilot as f

FIXTURE=json.loads((Path(__file__).parent/'fixtures/forecast-pilot.json').read_text())


class ForecastTests(unittest.TestCase):
    def row(self,data=None):
        d=data or FIXTURE
        return f.candidate_row('event',d['start'],d['end'],d['cutoff'],d['markets'],d['histories'],f.candles_by_end(d['candles']))

    def test_returns_and_bucket_references(self):
        row=self.row();t=FIXTURE['cutoff'];candles=f.candles_by_end(FIXTURE['candles'])
        self.assertEqual(f.number(row['target_return_bps']),(candles[t+3600]['close']/candles[t]['close']-1)*10000)
        self.assertEqual(row['features']['up_yes'],'0.3')
        self.assertEqual(f.number(row['features']['up_yes_change_1h']),f.Decimal('0.1'))
        for selected in row['selected'].values():
            self.assertLessEqual(selected['current']['bucket_end'],t)
            self.assertLessEqual(selected['lag_1h']['bucket_end'],t-3600)

    def test_future_prices_and_candles_do_not_change_features(self):
        changed=copy.deepcopy(FIXTURE);t=changed['cutoff']
        for h in changed['histories'].values():
            h['granular'][0]['points'][-1]['price']='0.01'
        for candle in changed['candles']:
            if candle['open_time_ms']>=t*1000:
                candle.update(open='102',close='102',high='103',low='98')
        before=self.row();after=self.row(changed)
        self.assertEqual(before['features'],after['features']);self.assertEqual(before['selected'],after['selected'])
        self.assertNotEqual(before['target_return_bps'],after['target_return_bps'])

    def test_exact_barrier_hit_excludes_market_without_using_final_label(self):
        d=copy.deepcopy(FIXTURE);t=d['cutoff']
        next(c for c in d['candles'] if c['close_time_ms']==t*1000-1)['high']='101'
        with self.assertRaisesRegex(ValueError,'no_nearby_unhit_up'):self.row(d)

    def test_missing_candles_prices_and_wrong_tokens_fail(self):
        d=copy.deepcopy(FIXTURE);d['candles']=[c for c in d['candles'] if c['close_time_ms']!=(d['cutoff']-60)*1000-1]
        with self.assertRaisesRegex(ValueError,'missing_btc_candle'):self.row(d)
        d=copy.deepcopy(FIXTURE);d['histories']['up']['token_id']='wrong'
        with self.assertRaisesRegex(ValueError,'token_mapping'):self.row(d)
        d=copy.deepcopy(FIXTURE);d['histories']['up']['granular'][0]['points'].pop(1)
        with self.assertRaisesRegex(ValueError,'stale_market_price'):self.row(d)

    def test_no_alternative_selected_when_nearest_price_is_missing(self):
        d=copy.deepcopy(FIXTURE);other=copy.deepcopy(d['markets'][0]);other['market_id']='further';other['semantics']['threshold']='102';d['markets'].append(other)
        d['histories']['further']=copy.deepcopy(d['histories']['up']);d['histories']['up']['granular'][0]['points']=[]
        with self.assertRaisesRegex(ValueError,'missing_market_price'):self.row(d)

    def test_future_market_does_not_change_historical_selection(self):
        d=copy.deepcopy(FIXTURE);future=copy.deepcopy(d['markets'][0]);future['market_id']='future'
        future['semantics']['threshold']='100.5'
        future['source_metadata']['createdAt']=f.datetime.fromtimestamp(d['cutoff']+60,f.timezone.utc).isoformat()
        d['markets'].append(future)
        self.assertEqual(self.row()['selected'],self.row(d)['selected'])

    def test_zero_width_future_and_conflicting_points(self):
        h=copy.deepcopy(FIXTURE['histories']['up']);t=FIXTURE['cutoff']
        h['granular'][0]['points'].append({'timestamp':t,'bucket_end':t,'resolution_seconds':0,'price':'1','forecasting_candidate':False})
        index=f.price_index(h,t);self.assertEqual(f.price_at(index,t)[0],f.Decimal('.3'))
        duplicate=copy.deepcopy(h['granular'][0]['points'][1]);duplicate['price']='.4';h['granular'][0]['points'].append(duplicate)
        with self.assertRaisesRegex(ValueError,'conflicting_market_points'):f.price_index(h,t)
        h=copy.deepcopy(FIXTURE['histories']['up']);h['granular'][0]['complete']=False
        with self.assertRaisesRegex(ValueError,'incomplete_market_history'):f.price_index(h,t)

    def test_fixed_chronological_event_splits_and_overlap_rejection(self):
        events=[{'event_id':str(i),'start':i*86400,'end':(i+1)*86400} for i in range(32)]
        result=f.split_events(list(reversed(events)))
        self.assertEqual([sum(e['split']==s for e in result) for s in ('train','validation','test')],[19,6,7])
        events[18]['end']+=1
        with self.assertRaisesRegex(ValueError,'overlapping_event_windows'):f.split_events(events)

    def model_rows(self):
        return [{'event_id':str(i//4),'features':{'x':str(i)},'target_return_bps':str(2*i+3)} for i in range(12)]

    def test_ridge_solution_and_train_only_scaling(self):
        rows=self.model_rows();model=f.fit(rows,['x'],.1)
        self.assertEqual(model['centers'],[5.5]);self.assertEqual(model['intercept'],14)
        x=float(rows[-1]['features']['x']);expected=14+2*(x-5.5)/1.1
        self.assertAlmostEqual(f.predict(model,rows[-1]),expected)
        unseen={'features':{'x':'10000'}};f.predict(model,unseen)
        self.assertEqual(model['centers'],[5.5])
        constant=f.fit([dict(r,features={'x':'1'}) for r in rows],['x'],1)
        self.assertEqual(constant['coefficients'],[0])

    def test_daily_weighting_and_empty_split_failure(self):
        rows=[{'event_id':'many','target_return_bps':'0'}]*9+[{'event_id':'one','target_return_bps':'0'}]
        score=f.score(rows,[0]*9+[10]);self.assertEqual(score['event_mean_mae_bps'],5);self.assertEqual(score['pooled_mae_bps'],1)
        with self.assertRaisesRegex(ValueError,'no accepted rows'):f.experiment([])

    def test_test_labels_cannot_change_fits_or_validation_selection(self):
        rows=[]
        for i in range(30):
            features={name:str((i+1)*(j+1)%11) for j,name in enumerate(f.BASE+f.MARKET)}
            rows.append({'event_id':str(i//3),'cutoff':i,'target_end':i+1,'features':features,
                         'target_return_bps':str(i%7),'split':'train' if i<18 else 'validation' if i<24 else 'test'})
        first=f.experiment(rows);changed=copy.deepcopy(rows)
        for row in changed:
            if row['split']=='test':row['target_return_bps']='1000000'
        second=f.experiment(changed)
        self.assertEqual(first['choices'],second['choices']);self.assertEqual(first['models'],second['models'])
