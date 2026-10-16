"""Run the fixed, exploratory one-hour forecast pilot on saved data only."""
import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
from statistics import mean, median

BASE = ['btc_return_1h_bps','btc_return_6h_bps','btc_volatility_6h_hour_bps','hours_remaining']
MARKET = ['up_yes','up_distance_pct','up_yes_change_1h','down_yes','down_distance_pct','down_yes_change_1h']
LAMBDAS = [0.01,0.1,1.0,10.0]
PROTOCOL = Path(__file__).resolve().parent.parent/'docs/forecast-pilot.md'


def read(path):
    return json.loads(path.read_text(),parse_float=str)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')


def epoch(value):
    return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()


def number(value):
    d=Decimal(str(value))
    if not d.is_finite():
        raise ValueError('nonfinite_number')
    return d


def candles_by_end(rows):
    result={}
    for raw in rows:
        start, end=raw['open_time_ms'],raw['close_time_ms']
        if start%60000 or end!=start+59999:
            raise ValueError('invalid_candle_time')
        row={k:number(raw[k]) for k in ('open','high','low','close')}
        if row['low']<=0 or row['high']<max(row['open'],row['close']) or row['low']>min(row['open'],row['close']):
            raise ValueError('invalid_candle_prices')
        t=(end+1)//1000
        if t in result and result[t]!=row:
            raise ValueError('conflicting_candles')
        result[t]=row
    return result


def continuous(candles, start, end):
    rows=[]
    for t in range(start+60,end+1,60):
        if t not in candles:
            raise ValueError('missing_btc_candle')
        rows.append(candles[t])
    return rows


def price_index(history, cutoff=None):
    if not history.get('complete') or any(not s.get('complete') for s in history.get('granular',[])):
        raise ValueError('incomplete_market_history')
    values={}
    for segment in history.get('granular',[]):
        for p in segment['points']:
            if not p.get('forecasting_candidate') or p.get('resolution_seconds')!=300:
                continue
            t=p.get('timestamp');end=p.get('bucket_end')
            if not isinstance(t,int) or isinstance(t,bool) or end!=t+300:
                continue
            if cutoff is not None and end>cutoff:
                continue
            value=number(p['price'])
            if not 0<=value<=1:
                continue
            if end in values and values[end][1]!=value:
                raise ValueError('conflicting_market_points')
            values[end]=(t,value)
    return {'times':sorted(values),'values':values}


def price_at(index,t):
    i=bisect_right(index['times'],t)-1
    if i<0:
        raise ValueError('missing_market_price')
    end=index['times'][i];start,value=index['values'][end]
    if t-end>=300:
        raise ValueError('stale_market_price')
    return value, {'timestamp':start,'bucket_end':end,'age_seconds':t-end,'price':str(value)}


def candidate_row(event_id,start,end,t,markets,histories,candles):
    # Coverage may examine the target interval; features below read only times <= t.
    continuous(candles,t-21600,t+3600)
    if t-21600 not in candles:
        raise ValueError('missing_btc_start_close')
    path=continuous(candles,start,t)
    if not path:
        raise ValueError('missing_measurement_path')
    spot=candles[t]['close'];past=candles[t-3600]['close'];old=candles[t-21600]['close']
    high=max(c['high'] for c in path);low=min(c['low'] for c in path)
    returns=[(candles[u]['close']/candles[u-60]['close']-1)*10000 for u in range(t-21600+60,t+1,60)]
    average=sum(returns)/len(returns)
    vol=(sum((r-average)**2 for r in returns)/len(returns)).sqrt()*Decimal(60).sqrt()
    features={'btc_return_1h_bps':(spot/past-1)*10000,'btc_return_6h_bps':(spot/old-1)*10000,
              'btc_volatility_6h_hour_bps':vol,'hours_remaining':Decimal(end-t)/3600}
    selected={}
    for direction,kind in [('up','window_high'),('down','window_low')]:
        options=[]
        for m in markets:
            sem=m['semantics']
            if sem['kind']!=kind:
                continue
            threshold=number(sem['threshold'])
            unhit=high<threshold if direction=='up' else low>threshold
            distance=((threshold/spot-1) if direction=='up' else (1-threshold/spot))*100
            if unhit and 0<distance<=5:
                created=m['source_metadata'].get('createdAt')
                if created and epoch(created)>t:
                    continue  # A future market cannot enter the historical universe.
                options.append((distance,m['market_id'],m))
        if not options:
            raise ValueError('no_nearby_unhit_'+direction)
        distance,_,market=min(options,key=lambda item:(item[0],item[1]))
        created=market['source_metadata'].get('createdAt')
        if not created or epoch(created)>t-3600:
            raise ValueError('market_not_created_at_lag_'+direction)
        token=(market.get('tokens') or {}).get('YES')
        no=(market.get('tokens') or {}).get('NO')
        history=histories.get(market['market_id'])
        if not token or not no or token==no or not history or history['token_id']!=token:
            raise ValueError('token_mapping_'+direction)
        index=price_index(history,t)
        current,current_ref=price_at(index,t)
        lag,lag_ref=price_at(index,t-3600)
        features.update({direction+'_yes':current,direction+'_distance_pct':distance,
                         direction+'_yes_change_1h':current-lag})
        selected[direction]={'market_id':market['market_id'],'yes_token_id':token,
                             'threshold':str(market['semantics']['threshold']),
                             'current':current_ref,'lag_1h':lag_ref}
    return {'event_id':event_id,'cutoff':t,'target_end':t+3600,'spot_btc_usdt':str(spot),
            'features':{k:str(v) for k,v in features.items()},'selected':selected,
            'target_return_bps':str((candles[t+3600]['close']/spot-1)*10000)}


def split_events(events):
    events=sorted(events,key=lambda e:e['start'])
    if len(events)!=32:
        raise ValueError('The fixed protocol requires exactly 32 daily events')
    if any(a['end']>b['start'] for a,b in zip(events,events[1:])):
        raise ValueError('overlapping_event_windows')
    return [dict(e,split='train' if i<19 else 'validation' if i<25 else 'test') for i,e in enumerate(events)]


def make_rows(root):
    catalog=read(root/'catalog.json');inputs={'catalog.json':digest(root/'catalog.json')};events=[]
    for event in catalog['events']:
        path=root/str(event['id'])/'markets.json';markets=read(path)
        supported=[m for m in markets if m.get('semantics') and m['semantics']['timeframe']=='daily'
                   and m['semantics']['window_basis']=='calendar' and not m['semantics']['creation_boundary_review_required']
                   and m['semantics']['kind'] in ('window_high','window_low')]
        if not supported:
            continue
        windows={(int(epoch(m['semantics']['window_start'])),int(epoch(m['semantics']['window_end']))) for m in supported}
        if len(windows)!=1:
            raise ValueError('incompatible_daily_windows')
        start,end=windows.pop()
        events.append({'event_id':str(event['id']),'title':event['title'],'start':start,'end':end,'markets':supported})
    events=split_events(events);accepted=[];rejected=[];assignments=[]
    for event in events:
        folder=root/event['event_id']
        assignments.append({k:v for k,v in event.items() if k!='markets'})
        for name in ('markets.json','prices.json','btc.json','coverage.json'):
            inputs[str((folder/name).relative_to(root))]=digest(folder/name)
        candles=None;histories={};event_error=None
        try:
            if not read(folder/'coverage.json')['collection_complete']:
                raise ValueError('event_collection_incomplete')
            candles=candles_by_end(read(folder/'btc.json')['candles'])
            histories={h['market_id']:h for h in read(folder/'prices.json')['markets']}
        except (ValueError,KeyError,TypeError,ArithmeticError) as error:
            event_error='event_input: '+str(error)
        for t in range(event['start']+3600,event['end'],3600):
            try:
                if event_error:
                    raise ValueError(event_error)
                row=candidate_row(event['event_id'],event['start'],event['end'],t,event['markets'],histories,candles)
                row['split']=event['split'];accepted.append(row)
            except (ValueError,KeyError,TypeError,ArithmeticError) as error:
                rejected.append({'event_id':event['event_id'],'cutoff':t,'split':event['split'],'reason':str(error)})
    # Enforce the split boundary on labels as well as feature timestamps.
    boundaries={s:min(e['start'] for e in assignments if e['split']==s) for s in ('validation','test')}
    for row in accepted:
        boundary=boundaries['validation'] if row['split']=='train' else boundaries['test'] if row['split']=='validation' else None
        if boundary is not None and row['target_end']>boundary:
            raise ValueError('target_crosses_split_boundary')
    return accepted,rejected,assignments,inputs


def solve(a,b):
    augmented=[list(row)+[v] for row,v in zip(a,b)];n=len(b)
    for i in range(n):
        pivot=max(range(i,n),key=lambda j:abs(augmented[j][i]))
        augmented[i],augmented[pivot]=augmented[pivot],augmented[i]
        divisor=augmented[i][i]
        if abs(divisor)<1e-14:
            raise ValueError('singular_fit')
        augmented[i]=[v/divisor for v in augmented[i]]
        for j in range(n):
            if j!=i:
                factor=augmented[j][i]
                augmented[j]=[x-factor*y for x,y in zip(augmented[j],augmented[i])]
    return [row[-1] for row in augmented]


def fit(rows,names,penalty):
    if not rows:
        raise ValueError('empty_fitting_rows')
    x=[[float(r['features'][k]) for k in names] for r in rows];y=[float(r['target_return_bps']) for r in rows]
    centers=[mean(col) for col in zip(*x)]
    scales=[math.sqrt(mean((row[i]-centers[i])**2 for row in x)) or 1 for i in range(len(names))]
    z=[[(v-centers[i])/scales[i] for i,v in enumerate(row)] for row in x];intercept=mean(y);n=len(rows)
    gram=[[sum(row[i]*row[j] for row in z)/n+(penalty if i==j else 0) for j in range(len(names))] for i in range(len(names))]
    rhs=[sum(row[i]*(v-intercept) for row,v in zip(z,y))/n for i in range(len(names))]
    return {'features':names,'lambda':penalty,'centers':centers,'scales':scales,'intercept':intercept,
            'coefficients':solve(gram,rhs),'fit_rows':n}


def predict(model,row):
    return model['intercept']+sum(coef*(float(row['features'][name])-center)/scale for name,coef,center,scale in
                                  zip(model['features'],model['coefficients'],model['centers'],model['scales']))


def score(rows,predictions):
    if not rows:
        raise ValueError('empty_scoring_rows')
    if len(rows)!=len(predictions):
        raise ValueError('prediction_count_mismatch')
    by_event=defaultdict(list);errors=[]
    for row,prediction in zip(rows,predictions):
        error=prediction-float(row['target_return_bps']);errors.append(error);by_event[row['event_id']].append(error)
    daily={event:{'rows':len(es),'mae_bps':mean(abs(e) for e in es),'rmse_bps':math.sqrt(mean(e*e for e in es))} for event,es in by_event.items()}
    return {'event_mean_mae_bps':mean(d['mae_bps'] for d in daily.values()),
            'pooled_mae_bps':mean(abs(e) for e in errors),'pooled_rmse_bps':math.sqrt(mean(e*e for e in errors)),
            'rows':len(rows),'events':len(daily),'by_event':daily}


def experiment(rows):
    groups={split:[r for r in rows if r['split']==split] for split in ('train','validation','test')}
    if any(not r for r in groups.values()):
        raise ValueError('An event split has no accepted rows; no model result is available')
    models={};choices={};scores={};predictions=[]
    # No test labels enter this loop.
    for label,names in [('btc',BASE),('augmented',BASE+MARKET)]:
        candidates=[]
        for penalty in LAMBDAS:
            model=fit(groups['train'],names,penalty)
            metric=score(groups['validation'],[predict(model,r) for r in groups['validation']])
            candidates.append({'lambda':penalty,'validation_event_mae_bps':metric['event_mean_mae_bps']})
        chosen=min(candidates,key=lambda c:(c['validation_event_mae_bps'],-c['lambda']))
        choices[label]={'candidates':candidates,'chosen_lambda':chosen['lambda']}
        models[label]=fit(groups['train']+groups['validation'],names,chosen['lambda'])
    for label,model in models.items():
        scores[label]=score(groups['test'],[predict(model,r) for r in groups['test']])
    scores['zero']=score(groups['test'],[0.0]*len(groups['test']))
    for row in groups['test']:
        predictions.append({'event_id':row['event_id'],'cutoff':row['cutoff'],'target_end':row['target_end'],
                            'actual_return_bps':row['target_return_bps'],
                            **{label+'_forecast_bps':predict(model,row) for label,model in models.items()}})
    improvement={e:scores['btc']['by_event'][e]['mae_bps']-scores['augmented']['by_event'][e]['mae_bps'] for e in scores['btc']['by_event']}
    leave_one={e:mean(v for k,v in improvement.items() if k!=e) for e in improvement} if len(improvement)>1 else {}
    return {'choices':choices,'models':models,'test_scores':scores,'predictions':predictions,
            'daily_improvement_bps':improvement,'median_daily_improvement_bps':median(improvement.values()),
            'day_wins':sum(v>0 for v in improvement.values()),'leave_one_event_out_improvement_bps':leave_one}


def run(root,output):
    output.mkdir(parents=True,exist_ok=True)
    rows,rejected,events,inputs=make_rows(root)
    provenance={'schema_version':1,'inputs':inputs,'protocol_hash':digest(PROTOCOL),'code_hash':digest(Path(__file__)),
                'qualified_forecast':False,'pricing_eligible':False,
                'limitations':['Price aggregation and historical publication/revisions unverified','Historical rule versions unverified',
                               'Small selected daily-event pilot; no general forecasting or trading claim']}
    save(output/'rows.json',dict(provenance,rows=rows))
    save(output/'rejections.json',dict(provenance,events=events,rejected=rejected))
    result=dict(provenance,events=events,accepted_rows=len(rows),rejected_rows=len(rejected))
    try:
        result.update(experiment(rows));result['status']='exploratory_complete'
    except ValueError as error:
        result.update(status='incomplete',error=str(error))
    save(output/'results.json',result)
    report=['# One-hour BTC forecast pilot','','This is an initial calculation. Forecast qualification remains false.','',
            f'Accepted rows: {len(rows)}. Rejected candidates: {len(rejected)}.','',
            '| Split | Events | Events with rows | Accepted | Rejected |','| --- | --- | --- | --- | --- |']
    for split in ('train','validation','test'):
        accepted=[r for r in rows if r['split']==split]
        report.append(f"| {split} | {sum(e['split']==split for e in events)} | {len({r['event_id'] for r in accepted})} | {len(accepted)} | {sum(r['split']==split for r in rejected)} |")
    report+=['','## Rejected candidates','']+[f'- {reason}: {count}' for reason,count in Counter(r['reason'] for r in rejected).most_common()]
    if result['status']=='exploratory_complete':
        report+=['','## Test errors (basis points)','','| Model | Mean daily MAE | Pooled MAE | Pooled RMSE |','| --- | --- | --- | --- |']
        for name,s in result['test_scores'].items():
            report.append(f"| {name} | {s['event_mean_mae_bps']:.4f} | {s['pooled_mae_bps']:.4f} | {s['pooled_rmse_bps']:.4f} |")
        report+=['','## Test events','','Positive improvement means the augmented model has lower error.','',
                 '| Date (UTC window start) | Event | Rows | BTC MAE | Augmented MAE | Improvement |','| --- | --- | --- | --- | --- | --- |']
        for e in events:
            if e['split']!='test':continue
            event=e['event_id'];date=datetime.fromtimestamp(e['start'],timezone.utc).date()
            if event not in result['daily_improvement_bps']:
                report.append(f'| {date} | {event} | 0 | unavailable | unavailable | coverage failure |');continue
            a=result['test_scores']['btc']['by_event'][event];b=result['test_scores']['augmented']['by_event'][event]
            report.append(f"| {date} | {event} | {a['rows']} | {a['mae_bps']:.4f} | {b['mae_bps']:.4f} | {a['mae_bps']-b['mae_bps']:.4f} |")
        report+=['',f"Day wins: {result['day_wins']}/{len(result['daily_improvement_bps'])}. Median daily improvement: {result['median_daily_improvement_bps']:.4f} bps.",'',
                 'Improvement with each event omitted (no refit):','']+[f'- Omit {e}: {v:.4f} bps' for e,v in result['leave_one_event_out_improvement_bps'].items()]
        report+=['','Validation-selected lambda: '+', '.join(f"{name}={v['chosen_lambda']}" for name,v in result['choices'].items())+'.']
    else:
        report+=['','Incomplete: '+result['error']]
    report+=['','The same accepted rows were used for both models. The full-history 0.05 filter was not used.',
             'Unknown aggregation, historical publication timing and rule versions limit this result. The test period has now been inspected.',
             'Do not tune this protocol against these test results. A changed experiment needs new untouched data.',
             'See results.json for coefficients, validation choices, predictions and input/code/protocol hashes.','']
    (output/'report.md').write_text('\n'.join(report))
    print(f'{output}/report.md: {result["status"]}; {len(rows)} accepted; {len(rejected)} rejected')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,default=Path('data/bitcoin'))
    parser.add_argument('--output',type=Path,default=Path('data/forecast/pilot-v1'))
    args=parser.parse_args()
    result=run(args.data,args.output)
    return 0 if result['status']=='exploratory_complete' else 1


if __name__=='__main__':
    raise SystemExit(main())
