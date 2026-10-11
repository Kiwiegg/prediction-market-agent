"""Build a standalone event explorer from saved JSON, without network or dependencies."""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path

if __package__:
    from .visualize_market import epoch, distance_rows, first_hit
else:
    from visualize_market import epoch, distance_rows, first_hit


def window_points(history, start, end):
    points = {}
    for segment in history.get('granular', []):
        if not segment.get('complete'):
            continue
        for p in segment['points']:
            if (p.get('forecasting_candidate') and p['resolution_seconds'] > 0
                    and start <= p['timestamp'] < p['bucket_end'] <= end):
                points[(p['timestamp'], p['bucket_end'])] = p
    return sorted(points.values(), key=lambda p: p['bucket_end'])


def prepare_event(event, markets, histories, btc, labels, selection):
    histories = {m['market_id']: m for m in histories['markets']}
    labels = {m['market_id']: m for m in labels['markets']}
    candles = sorted(btc['candles'], key=lambda c: c['close_time_ms'])
    result = []
    omitted = []
    for market in markets:
        sem = market['semantics']
        if not sem or sem['kind'] not in ('window_high','window_low'):
            omitted.append(market['market_id'])
            continue
        start, end = epoch(sem['window_start']), epoch(sem['window_end'])
        source = [c for c in candles if start*1000 <= c['open_time_ms'] and c['close_time_ms'] < end*1000]
        points = window_points(histories[market['market_id']], start, end)
        # Join exact completed candles; no carrying spot through missing minutes.
        by_end = {(c['close_time_ms']+1)//1000:c for c in source}
        rows = [{'time':p['bucket_end'], 'price':p['price'],
                 'btc':by_end[p['bucket_end']]['close'] if p['bucket_end'] in by_end else None} for p in points]
        rows = distance_rows(rows,source,sem)
        if sem['creation_boundary_review_required']:
            for row in rows:
                row['barrier_status'] = 'unknown'
        label = labels.get(market['market_id'], {})
        resolution = label.get('resolution') or {}
        hit = None if sem['creation_boundary_review_required'] else first_hit(source,sem)
        # Exact quantities stay in the source files; floating point is display only.
        packed = [[r['time'],float(Decimal(r['price'])),float(Decimal(r['btc'])) if r['btc'] else None,
                   float(Decimal(r['distance_pct'])) if r['distance_pct'] is not None else None,
                   {'before_hit':0,'after_hit':1,'unknown':2}[r['barrier_status']],p['resolution_seconds']]
                  for r,p in zip(rows,points)]
        result.append({'id':market['market_id'],'title':market['title'],
                       'threshold':float(Decimal(sem['threshold'])),
                       'direction':'up' if sem['kind']=='window_high' else 'down',
                       'frame':sem['timeframe'],'start':start,'end':end,'window_basis':sem['window_basis'],
                       'review_boundary':sem['creation_boundary_review_required'],
                       'hit':hit,'venue_yes':resolution.get('status')=='resolved' and str(resolution.get('price'))=='1000000000000000000',
                       'selection':selection.get(market['market_id'],'unknown'), 'points':packed})
    return {'id':str(event['id']),'title':event['title'],'markets':result,'omitted':omitted}


def build(root, output):
    catalog = json.loads((root/'catalog.json').read_text())
    selection_path = root/'analysis-selection.json'
    selection, inputs = {}, {}
    if selection_path.exists():
        selection_data = json.loads(selection_path.read_text())
        for relative, expected in selection_data['inputs'].items():
            if hashlib.sha256((root/relative).read_bytes()).hexdigest()!=expected:
                raise ValueError('Selection is stale; rerun scripts/select_markets.py')
        selection = {m['market_id']:m['status'] for m in selection_data['markets']}
        inputs['analysis-selection.json']=hashlib.sha256(selection_path.read_bytes()).hexdigest()
    events = []
    for event in catalog['events']:
        folder=root/str(event['id'])
        data=[]
        for name in ('markets.json','prices.json','btc.json','labels.json'):
            path=folder/name
            inputs[str(path.relative_to(root))]=hashlib.sha256(path.read_bytes()).hexdigest()
            data.append(json.loads(path.read_text()))
        events.append(prepare_event(event,*data,selection))
    events.sort(key=lambda e:min((m['start'] for m in e['markets']),default=0))
    payload={'schema_version':1,'events':events,'inputs':inputs,
             'script_hash':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             'template_hash':hashlib.sha256(Path(__file__).with_name('event_explorer.html').read_bytes()).hexdigest(),
             'retrospective_only':True}
    template=Path(__file__).with_name('event_explorer.html').read_text()
    serialized=json.dumps(payload,separators=(',',':'),ensure_ascii=False).replace('<','\\u003c')
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(template.replace('__DATA__',serialized))
    print(f'{output}: {len(events)} events; {sum(len(e["markets"]) for e in events)} supported markets; '+
          f'{sum(len(m["points"]) for e in events for m in e["markets"])} granular points')
    return payload


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,default=Path('data/bitcoin'))
    parser.add_argument('--output',type=Path,default=Path('data/analysis/event-explorer.html'))
    args=parser.parse_args()
    build(args.data,args.output)


if __name__=='__main__':
    main()
