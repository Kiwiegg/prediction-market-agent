"""Build a retrospective analysis selection without changing collected sources."""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path


def classify(history, threshold):
    points = []
    if history.get('complete'):
        points.extend(history.get('points', []))
    for segment in history.get('granular', []):
        if segment.get('complete'):
            points.extend(segment['points'])
    values = [Decimal(p['price']) for p in points if p.get('forecasting_candidate')
              and p.get('resolution_seconds', 0) > 0]
    peak = max(values) if values else None
    complete = history.get('complete') and all(s.get('complete') for s in history.get('granular', []))
    if peak is not None and peak > threshold:
        status = 'keep'
    elif peak is None or not complete:
        status = 'unknown'
    else:
        status = 'drop'
    return {'status': status, 'max_usable_yes': str(peak) if peak is not None else None,
            'usable_points': len(values), 'request_complete': bool(complete)}


def build(root, threshold):
    catalog = json.loads((root/'catalog.json').read_text())
    records, inputs = [], {}
    for event in catalog['events']:
        path = root / str(event['id']) / 'prices.json'
        inputs[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
        for history in json.loads(path.read_text())['markets']:
            records.append(dict(event_id=str(event['id']), market_id=history['market_id'],
                                **classify(history, threshold)))
    counts = {status: sum(r['status'] == status for r in records) for status in ('keep','drop','unknown')}
    result = {'schema_version': 1, 'minimum_peak_yes': str(threshold),
              'rule': 'Keep if any usable saved YES price is strictly above the cutoff; retain unknowns for review.',
              'scope': 'All saved coarse lifetime and granular points in completed requests; positive-width forecasting_candidate points only.',
              'retrospective_only': True, 'inputs': inputs,
              'script_hash': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'counts': counts, 'markets': records}
    (root/'analysis-selection.json').write_text(json.dumps(result,indent=2)+'\n')
    (root/'analysis-selection.md').write_text(f'''# Analysis market selection

Cutoff: maximum usable saved YES price must be **above {threshold}**.

- Keep: {counts['keep']}
- Drop from analysis view: {counts['drop']}
- Unknown, retained for review: {counts['unknown']}

Uses all saved lifetime and granular positive-width candidate points in completed requests.
Zero-width settlement points and failed request segments are excluded. A low peak with incomplete requests is unknown, not dropped.
This describes available history, not proof that an unobserved price never exceeded the cutoff.

Source files are unchanged. Market IDs and reasons are in `analysis-selection.json`.
Selectors and comparison charts use this selection; `--include-all` restores all daily markets.
This full-history filter uses future information and must not select a forecasting backtest universe.
''')
    print(counts)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,default=Path('data/bitcoin'))
    parser.add_argument('--minimum-peak',type=Decimal,default=Decimal('0.05'))
    args = parser.parse_args()
    if not args.minimum_peak.is_finite() or not 0 <= args.minimum_peak <= 1:
        parser.error('minimum-peak must be between 0 and 1')
    build(args.data,args.minimum_peak)


if __name__ == '__main__':
    main()
