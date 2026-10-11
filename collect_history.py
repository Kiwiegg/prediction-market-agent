#!/usr/bin/env python3
"""Collect read-only Bitcoin history; Python 3.11+, standard library only."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import quote, urlencode
from uuid import uuid4
from zoneinfo import ZoneInfo

from ingest import fetch, now, token_mapping

GAMMA = 'https://gamma-api.polymarket.com'
DATA = 'https://data-api.polymarket.com/v2'
BINANCE = 'https://api.binance.com/api/v3/klines'
TEMPLATES = json.loads(Path(__file__).with_name('bitcoin_history_templates.json').read_text())
RULE = '''This market will resolve to "Yes" if the Binance 1 minute candle for BTC/USDT 12:00 in the ET timezone (noon) on the date specified in the title has a final "Close" price higher than the price specified in the title. Otherwise, this market will resolve to "No".

The resolution source for this market is Binance, specifically the BTC/USDT "Close" prices currently available at https://www.binance.com/en/trade/BTC_USDT with "1m" and "Candles" selected on the top bar.

Please note that this market is about the price according to Binance BTC/USDT, not according to other exchanges or trading pairs.

Price precision is determined by the number of decimal places in the source.'''


def progress(message):
    # Losing the terminal during a restart must not mark saved data as failed.
    try:
        print(message, flush=True)
    except BrokenPipeError:
        pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def utc(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timestamp requires a timezone')
    return result.astimezone(timezone.utc)


def pages(url, params, get, cap=100):
    """Retain partial pages on failure; never call a truncated result complete."""
    rows, receipts, seen = [], [], set()
    try:
        for _ in range(cap):
            body, received = get(url + '?' + urlencode(params))
            if not isinstance(body, dict) or not isinstance(body.get('data'), list):
                raise ValueError('Expected Data v2 envelope')
            rows.extend(body['data'])
            receipts.append(received)
            pagination = body.get('pagination')
            if not isinstance(pagination, dict):
                raise ValueError('Missing pagination')
            cursor = pagination.get('next_cursor')
            if not cursor:
                if pagination.get('has_more') is True:
                    raise ValueError('has_more without cursor')
                return rows, receipts, None
            if cursor in seen:
                raise ValueError('Repeated pagination cursor')
            seen.add(cursor)
            params = dict(params, cursor=cursor)
        raise ValueError('Page cap reached')
    except (ValueError, TypeError) as error:
        return rows, receipts, str(error)


def normalize(event, market, received, source):
    rules = market.get('description') or ''
    record = {
        'schema_version': 1, 'event_id': str(event['id']), 'market_id': str(market['id']),
        'condition_id': market.get('conditionId'), 'title': market.get('question'),
        'rules': rules, 'rule_hash': hashlib.sha256(rules.encode()).hexdigest(),
        'source_url': source, 'source_hash': digest(market), 'received_at': received,
        'source_metadata': {k: market.get(k) for k in (
            'slug', 'startDate', 'endDate', 'createdAt', 'updatedAt', 'closed',
            'outcomes', 'clobTokenIds', 'outcomePrices', 'umaResolutionStatus',
            'umaResolutionStatuses', 'resolutionSource', 'negRisk')},
        'semantics_status': 'unsupported', 'semantics': None, 'issues': [],
        'pricing_eligible': False,
    }
    try:
        record['tokens'] = token_mapping(market)
    except (ValueError, TypeError) as error:
        record['tokens'] = None
        record['issues'].append(str(error))
    if rules != RULE:
        record['semantics'] = hit_semantics(market)
        if record['semantics']:
            record['semantics_status'] = 'supported_template'
        else:
            record['issues'].append('Unverified rule template; preserve for later interpretation')
        return record
    title = re.fullmatch(r'Will the price of Bitcoin be above \$([\d,]+(?:\.\d+)?) on ([A-Za-z]+ \d{1,2})\?', market.get('question', ''))
    try:
        if not title:
            raise ValueError('Title does not match verified template')
        # The year must be explicit in the slug, never inferred from receipt/end time.
        year = re.search(r'-(\d{4})$', market.get('slug', ''))
        if not year:
            raise ValueError('Missing explicit year in market slug')
        day = datetime.strptime(title[2] + ' ' + year[1], '%B %d %Y')
        candle = day.replace(hour=12, tzinfo=ZoneInfo('America/New_York')).astimezone(timezone.utc)
        threshold = Decimal(title[1].replace(',', ''))
        if threshold <= 0:
            raise ValueError('Invalid threshold')
        record['semantics'] = {
            'template_version': 'binance-noon-close-v1', 'asset': 'BTC', 'quote': 'USDT',
            'source': 'Binance', 'symbol': 'BTCUSDT', 'kind': 'terminal_close',
            'comparator': 'gt', 'threshold': str(threshold),
            'timezone': 'America/New_York', 'candle_start': candle.isoformat(),
            'measurement_available_at': (candle + timedelta(minutes=1)).isoformat(),
            'historical_rule_version': 'unverified',
            'window_start': None, 'window_end': None,
        }
        record['semantics_status'] = 'supported_template'
    except (ValueError, TypeError) as error:
        record['issues'].append(str(error))
    return record


def hit_semantics(market):
    template = next((t for t in TEMPLATES if market.get('description') == t['rules']), None)
    if not template:
        return None
    year = re.search(r'-(\d{4})$', market.get('slug', ''))
    if not year:
        return None
    if template['family'] == 'weekly':
        title = re.fullmatch(r'Will Bitcoin (reach|dip to) \$([\d,]+(?:\.\d+)?) ([A-Za-z]+ \d{1,2})-(?:([A-Za-z]+) )?(\d{1,2})\?', market.get('question', ''))
    else:
        title = re.fullmatch(r'Will Bitcoin (reach|dip to) \$([\d,]+(?:\.\d+)?) (on|in) ([A-Za-z]+(?: \d{1,2})?)\?', market.get('question', ''))
    if not title:
        return None
    direction = 'up' if title[1] == 'reach' else 'down'
    if direction != template['direction']:
        return None
    try:
        if template['family'] == 'weekly':
            first = datetime.strptime(title[3] + ' ' + year[1], '%B %d %Y')
            last = datetime.strptime((title[4] or title[3].split()[0]) + ' ' + title[5] + ' ' + year[1], '%B %d %Y')
            # Cross-year weekly titles need a separate reviewed convention.
            if last < first:
                return None
            start = first.replace(tzinfo=ZoneInfo('America/New_York'))
            end = last.replace(tzinfo=ZoneInfo('America/New_York')) + timedelta(days=1)
        else:
            if (title[3] == 'on') != (template['family'] == 'daily'):
                return None
            day = datetime.strptime(title[4] + ' ' + year[1], '%B %d %Y' if title[3] == 'on' else '%B %Y')
            start = day.replace(tzinfo=ZoneInfo('America/New_York'))
            if template['family'] == 'daily':
                end = start + timedelta(days=1)
            else:
                end = start.replace(year=start.year + (start.month == 12), month=start.month % 12 + 1, day=1)
        start, end = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
        if template['window'] == 'creation':
            start = utc(market['createdAt'])
        if start >= end:
            return None
        threshold = Decimal(title[2].replace(',', ''))
        if not threshold.is_finite() or threshold <= 0:
            return None
        return {'template_version': template['version'], 'asset': 'BTC', 'quote': 'USDT',
                'source': 'Binance', 'symbol': 'BTCUSDT', 'kind': 'window_high' if direction == 'up' else 'window_low',
                'comparator': 'gte' if direction == 'up' else 'lte', 'threshold': str(threshold),
                'timezone': 'America/New_York', 'timeframe': template['family'],
                'window_start': start.isoformat(), 'window_end': end.isoformat(),
                'window_basis': template['window'], 'candle_start': None,
                'measurement_available_at': end.isoformat(),
                'creation_boundary_review_required': template['window'] == 'creation',
                'historical_rule_version': 'unverified'}
    except (KeyError, ValueError, TypeError, ArithmeticError):
        return None


def price_rows(rows, resolved):
    result = []
    for row in rows:
        try:
            t, width = row['timestamp'], row['resolution_seconds']
            if isinstance(t, bool) or not isinstance(t, int) or t <= 0:
                raise ValueError('Invalid price timestamp')
            if isinstance(width, bool) or not isinstance(width, int) or width < 0:
                raise ValueError('Invalid resolution')
            p = Decimal(str(row['price']))
            if not p.is_finite() or not 0 <= p <= 1:
                raise ValueError('Invalid price')
            # Conservatively quarantine every zero-width point on resolved tokens.
            # This can exclude real ticks, but does not silently admit synthetic labels.
            suspect = resolved and width == 0
            result.append(dict(row, price=str(p), bucket_end=t + width,
                               forecasting_candidate=not suspect,
                               exclusion='resolved_zero_width_unclassified' if suspect else None))
        except (KeyError, ValueError, TypeError, ArithmeticError) as error:
            result.append({'source_point': row, 'forecasting_candidate': False,
                           'exclusion': 'invalid_point: ' + str(error)})
    return result


def observation_at(points, cutoff):
    candidates = [p for p in points if p.get('forecasting_candidate')
                  and p['bucket_end'] <= cutoff]
    latest = max(candidates, key=lambda p: p['bucket_end']) if candidates else None
    return {'cutoff': cutoff, 'point': latest,
            'age_seconds': cutoff - latest['bucket_end'] if latest else None,
            'status': 'candidate_price_semantics_unverified' if latest else 'missing'}


def candles(start, end, get, cap=1000):
    rows, receipts = [], []
    cursor = start
    for _ in range(cap):
        body, received = get(BINANCE + '?' + urlencode({
            'symbol': 'BTCUSDT', 'interval': '1m', 'startTime': cursor * 1000,
            'endTime': end * 1000 - 1, 'limit': 1000}))
        receipts.append(received)
        if not isinstance(body, list) or not body:
            raise ValueError('Missing Binance candles')
        for row in body:
            if len(row) < 7 or row[0] != cursor * 1000 or row[6] != row[0] + 59999:
                raise ValueError('Gap or invalid boundary in Binance candles')
            for value in row[1:5]:
                number = Decimal(str(value))
                if not number.is_finite() or number <= 0:
                    raise ValueError('Invalid candle price')
            opened, high, low, closed = [Decimal(str(value)) for value in row[1:5]]
            if not low <= opened <= high or not low <= closed <= high:
                raise ValueError('Inconsistent candle OHLC values')
            rows.append({'open_time_ms': row[0], 'open': str(row[1]), 'high': str(row[2]),
                         'low': str(row[3]), 'close': str(row[4]), 'close_time_ms': row[6]})
            cursor += 60
        if cursor >= end:
            return rows, receipts
    raise ValueError('Binance page cap reached')


def collect_event(event, received, source, folder, get, lookback, page_cap):
    folder.mkdir()
    markets = [normalize(event, m, received, source) for m in event.get('markets', [])]
    save(folder / 'markets.json', markets)
    inputs = {'markets.json': digest(markets)}
    issues, prices, labels = [], [], []
    # Store the response data, not oracle encodings interpreted as BTC prices.
    resolution_rows, resolution_receipts, resolution_error = [], [], None
    try:
        response, receipt = get(DATA + '/resolutions?' + urlencode({'event_id': event['id']}))
        if not isinstance(response, dict) or not isinstance(response.get('data'), list):
            raise ValueError('Expected resolutions data envelope')
        resolution_rows, resolution_receipts = response['data'], [receipt]
    except (ValueError, TypeError) as error:
        resolution_error = str(error)
    if resolution_error:
        issues.append('resolutions: ' + resolution_error)
    resolutions = {r.get('condition_id'): r for r in resolution_rows}
    supported = [m for m in markets if m['semantics']]
    btc, btc_receipts = [], []
    btc_complete = False
    if supported:
        starts = [int(utc(m['semantics']['window_start'] or m['semantics']['candle_start']).timestamp()) for m in supported]
        ends = [int(utc(m['semantics']['measurement_available_at']).timestamp()) for m in supported]
        start = min(starts) - lookback * 86400
        end = min(max(ends), int(datetime.now(timezone.utc).timestamp()) // 60 * 60)
        try:
            # Align creation timestamps down for collection; boundary semantics remain quarantined.
            btc, btc_receipts = candles(start // 60 * 60, end, get)
            btc_complete = end >= max(ends)
        except (ValueError, TypeError, ArithmeticError) as error:
            issues.append('btc: ' + str(error))
    for m in markets:
        resolution = resolutions.get(m['condition_id'])
        resolved = resolution is not None and resolution.get('status') == 'resolved'
        if not m['tokens']:
            issues.append(m['market_id'] + ': missing token mapping')
            continue
        raw, receipts, error = pages(DATA + '/prices-history', {
            'token_id': m['tokens']['YES'], 'interval': 'max', 'limit': 10000}, get, page_cap)
        points = price_rows(raw, resolved or m['source_metadata']['umaResolutionStatus'] == 'resolved')
        cutoffs, granular = [], []
        if m['semantics']:
            semantics = m['semantics']
            anchor = int(utc(semantics['window_start'] or semantics['candle_start']).timestamp())
            until = min(int(utc(semantics['measurement_available_at']).timestamp()),
                        int(datetime.now(timezone.utc).timestamp()))
            created = m['source_metadata'].get('createdAt')
            begin = max(anchor - lookback * 86400, int(utc(created).timestamp())) if created else anchor - lookback * 86400
            # Fixed widths expose retention gaps; coarse lifetime data remain separate.
            width = 300 if until > int(datetime.now(timezone.utc).timestamp()) - 60 * 86400 else 10800
            for start in range(begin, until, 15 * 86400):
                stop = min(start + 15 * 86400, until)
                fine, fine_receipts, fine_error = pages(DATA + '/prices-history', {
                    'token_id': m['tokens']['YES'], 'start': start, 'end': stop,
                    'bucket_seconds': width, 'limit': 10000}, get, page_cap)
                granular.append({'start': start, 'end': stop, 'requested_resolution_seconds': width,
                                 'source_hash': digest(fine), 'received_at': fine_receipts,
                                 'complete': fine_error is None, 'error': fine_error,
                                 'points': price_rows(fine, resolved or m['source_metadata']['umaResolutionStatus'] == 'resolved')})
                if fine_error:
                    issues.append(m['market_id'] + ': granular history: ' + fine_error)
            for h in (24, 6, 1):
                cutoff = anchor - h * 3600
                candidates = [(index, observation_at(segment['points'], cutoff)) for index, segment in enumerate(granular) if segment['complete']]
                available = [(index, obs) for index, obs in candidates if obs['point']]
                if available:
                    index, obs = max(available, key=lambda item: item[1]['point']['bucket_end'])
                    obs['series'] = 'granular'
                    obs['segment_index'] = index
                else:
                    obs = observation_at(points if not error else [], cutoff)
                    obs['series'] = 'coarse_lifetime'
                cutoffs.append(obs)
        prices.append({'market_id': m['market_id'], 'token_id': m['tokens']['YES'],
                       'source': DATA + '/prices-history', 'source_hash': digest(raw),
                       'received_at': receipts, 'complete': error is None, 'error': error,
                       'price_definition': 'unverified', 'price_units': 'unknown', 'points': points,
                       'granular': granular, 'cutoffs': cutoffs})
        if error or not raw:
            issues.append(m['market_id'] + ': ' + (error or 'empty price history'))
        label = {'market_id': m['market_id'], 'resolution': resolution,
                 'reported_yes': None, 'source_yes': None, 'status': 'unverified'}
        oracle = str(resolution.get('price')) if resolved else None
        if oracle in ('0', '1000000000000000000') and not resolution.get('new_version_q') and not resolution.get('was_disputed'):
            label['reported_yes'] = oracle == '1000000000000000000'
        if m['semantics'] and btc:
            semantics = m['semantics']
            threshold = Decimal(semantics['threshold'])
            if semantics['kind'] == 'terminal_close':
                expected = int(utc(semantics['candle_start']).timestamp()) * 1000
                row = next((r for r in btc if r['open_time_ms'] == expected), None)
                if row:
                    label['source_yes'] = Decimal(row['close']) > threshold
            elif not semantics['creation_boundary_review_required']:
                start_ms = int(utc(semantics['window_start']).timestamp()) * 1000
                end_ms = int(utc(semantics['window_end']).timestamp()) * 1000
                window = [r for r in btc if start_ms <= r['open_time_ms'] < end_ms]
                if window:
                    hit = any(Decimal(r['high']) >= threshold for r in window) if semantics['kind'] == 'window_high' else any(Decimal(r['low']) <= threshold for r in window)
                    # A hit is established early; NO requires complete window coverage.
                    label['source_yes'] = True if hit else False if btc_complete else None
            if label['source_yes'] is not None and label['reported_yes'] is not None:
                label['status'] = 'matched' if label['reported_yes'] == label['source_yes'] else 'discrepancy'
        if resolution and resolution.get('new_version_q'):
            label['status'] = 'rule_version_review_required'
        labels.append(label)
    save(folder / 'prices.json', {'schema_version': 1, 'inputs': inputs, 'markets': prices})
    btc_record = {'schema_version': 1, 'source': BINANCE, 'received_at': btc_receipts,
                  'symbol': 'BTCUSDT', 'price_units': 'USDT per BTC', 'interval': '1m', 'measurement_windows_complete': btc_complete, 'candles': btc}
    save(folder / 'btc.json', btc_record)
    save(folder / 'labels.json', {'schema_version': 1, 'inputs': dict(inputs, **{'btc.json': digest(btc_record)}),
                                'resolution_received_at': resolution_receipts,
                                'resolution_complete': resolution_error is None, 'markets': labels})
    coverage = {'event_id': str(event['id']), 'markets': len(markets),
                'supported_markets': len(supported), 'prices_with_data': sum(bool(p['points']) for p in prices),
                'matched_labels': sum(l['status'] == 'matched' for l in labels),
                'collection_complete': not issues, 'analysis_ready': False,
                'issues': issues, 'limitations': ['Price aggregation semantics unverified',
                    'Historical rule version unverified', 'Unknown hit/window templates unsupported',
                    'Zero-width points on resolved tokens quarantined; real ticks may be excluded',
                    'Cutoff candidates have no freshness eligibility gate; inspect age_seconds']}
    save(folder / 'coverage.json', coverage)
    derive_observations(folder)
    return coverage


def discover(start, end, get, cap, tag_id=102134):
    events, receipts, seen = [], [], set()
    try:
        for page in range(cap):
            body, received = get(GAMMA + '/events?' + urlencode({
                'tag_id': tag_id, 'closed': 'true', 'end_date_min': start,
                'end_date_max': end, 'order': 'id', 'ascending': 'true',
                'limit': 100, 'offset': page * 100}))
            receipts.append(received)
            progress(f'Catalog page {page + 1}: {len(body) if isinstance(body, list) else 0} events')
            if not isinstance(body, list):
                raise ValueError('Expected Gamma event array')
            for event in body:
                if event['id'] in seen:
                    raise ValueError('Duplicate event across discovery pages')
                seen.add(event['id'])
                if re.match(r'(?:what-price-will-bitcoin-hit|bitcoin-above-on-)', event.get('slug', '')):
                    events.append((event, received, GAMMA + '/events'))
            if len(body) < 100:
                return events, receipts, None
        raise ValueError('Gamma discovery page cap reached')
    except (ValueError, TypeError, KeyError) as error:
        return events, receipts, str(error)



def derive_observations(folder):
    """Create cutoff records from saved sources; never change source files."""
    markets = json.loads((folder / 'markets.json').read_text())
    price_data = json.loads((folder / 'prices.json').read_text())
    btc_data = json.loads((folder / 'btc.json').read_text())
    prices = {p['market_id']: p for p in price_data['markets']}
    btc = btc_data['candles']
    records = []
    receipts = [utc(value).timestamp() for value in btc_data.get('received_at', [])]
    observed_until = max(receipts) if receipts else None
    for market in markets:
        semantics = market['semantics']
        price = prices.get(market['market_id'])
        if not semantics or not price:
            continue
        anchor = int(utc(semantics['window_start'] or semantics['candle_start']).timestamp())
        bases = [('before_measurement' if semantics['kind'] == 'terminal_close' else 'before_window', anchor)]
        if semantics['window_end']:
            bases.append(('before_window_end', int(utc(semantics['window_end']).timestamp())))
        series = [('coarse_lifetime', None, price['points'])] if price['complete'] else []
        series += [('granular', i, segment['points']) for i, segment in enumerate(price.get('granular', [])) if segment['complete']]
        for basis, end in bases:
            for hours in (24, 6, 1):
                cutoff = end - hours * 3600
                if basis == 'before_window_end' and cutoff < anchor:
                    continue
                available = [(name, i, observation_at(points, cutoff)) for name, i, points in series]
                available = [row for row in available if row[2]['point']]
                if available:
                    name, index, observation = max(available, key=lambda row: (row[2]['point']['bucket_end'], -row[2]['point']['resolution_seconds']))
                    observation = dict(observation, series=name, segment_index=index)
                else:
                    observation = observation_at([], cutoff)
                if observed_until is not None and cutoff > observed_until:
                    observation = dict(observation_at([], cutoff), status='cutoff_not_yet_observed')
                known = [row for row in btc if row['close_time_ms'] < cutoff * 1000]
                spot = max(known, key=lambda row: row['close_time_ms']) if known else None
                hit = None
                if semantics['window_start'] and not semantics['creation_boundary_review_required'] and cutoff > anchor:
                    window = [row for row in known if row['open_time_ms'] >= anchor * 1000]
                    if window:
                        threshold = Decimal(semantics['threshold'])
                        reached = any(Decimal(row['high']) >= threshold for row in window) if semantics['kind'] == 'window_high' else any(Decimal(row['low']) <= threshold for row in window)
                        fully_observed = window[0]['open_time_ms'] == anchor * 1000 and window[-1]['close_time_ms'] == cutoff * 1000 - 1
                        hit = True if reached else False if fully_observed else None
                records.append({'market_id': market['market_id'], 'basis': basis, 'hours_before': hours,
                                'cutoff_observed': cutoff <= observed_until if observed_until is not None else None,
                                'price': observation, 'btc_last_completed_candle': spot,
                                'barrier_reached_so_far': hit, 'analysis_ready': False})
    inputs = {name: digest(json.loads((folder / name).read_text())) for name in ('markets.json', 'prices.json', 'btc.json')}
    result = {'schema_version': 1, 'inputs': inputs, 'derivation_hash': digest(Path(__file__).read_text()),
              'records': records, 'limitations': ['Price aggregation and historical rule versions unverified',
                    'Candidates have no freshness gate', 'Do not forecast a new hit once barrier_reached_so_far is true']}
    save(folder / 'observations.json', result)
    return result


def write_report(root, catalog, coverage):
    reports = coverage['events']
    total = sum(r.get('markets', 0) for r in reports)
    supported = sum(r.get('supported_markets', 0) for r in reports)
    histories = sum(r.get('prices_with_data', 0) for r in reports)
    text = ['# Collection coverage', '',
            f"Selected {len(reports)} events from {catalog['discovered']} discovered events.",
            f"Markets: {total}; supported templates: {supported}; nonempty lifetime histories: {histories}.",
            f"Collection complete: {coverage['collection_complete']}; analysis ready: False.", '',
            '| Event | Markets | Supported | Histories | Request issues |',
            '| --- | --- | --- | --- | --- |']
    names = {str(e['id']): e['slug'] for e in catalog['events']}
    for r in reports:
        text.append(f"| {names.get(r['event_id'], r['event_id'])} | {r.get('markets', 0)} | {r.get('supported_markets', 0)} | {r.get('prices_with_data', 0)} | {len(r.get('issues', []))} |")
    text += ['', 'See coverage.json and each event’s coverage.json for failures. Selection caps are disclosed in catalog.json.',
             'Price definitions and historical rule versions remain unverified. Creation-window boundaries require review.',
             'Prices are observations for research, not executable quotes. No forecasting performance has been evaluated.', '']
    (root / 'report.md').write_text('\n'.join(text))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--derive-run', type=Path, help='Derive cutoff observations from a saved run without network')
    parser.add_argument('--start', default='2026-09-01T00:00:00Z')
    parser.add_argument('--end', default='2026-10-10T00:00:00Z')
    parser.add_argument('--slug', action='append', default=[])
    parser.add_argument('--events-file', type=Path, help='Saved Gamma event or array; original receipt time unknown')
    parser.add_argument('--tag-id', type=int, default=102134, help='Hit Price tag; use 102516 for Multi Strikes')
    parser.add_argument('--limit', type=int, default=40)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--lookback-days', type=int, default=7)
    parser.add_argument('--timeout', type=int, default=30)
    parser.add_argument('--retries', type=int, default=2)
    parser.add_argument('--page-cap', type=int, default=100)
    parser.add_argument('--output', type=Path, default=Path('data/collections'))
    args = parser.parse_args()
    if args.derive_run:
        count = 0
        for folder in sorted(args.derive_run.iterdir()):
            if folder.is_dir() and all((folder / name).exists() for name in ('markets.json', 'prices.json', 'btc.json')):
                result = derive_observations(folder)
                count += len(result['records'])
        catalog = json.loads((args.derive_run / 'catalog.json').read_text())
        reports = [json.loads((args.derive_run / str(e['id']) / 'coverage.json').read_text())
                   if (args.derive_run / str(e['id']) / 'coverage.json').exists() else
                   {'event_id': str(e['id']), 'collection_complete': False, 'issues': ['Missing event coverage']}
                   for e in catalog['events']]
        coverage = {'schema_version': 1, 'catalog_hash': digest(catalog),
                    'collection_complete': bool(reports) and not catalog['errors'] and not catalog['truncated'] and all(r['collection_complete'] for r in reports),
                    'analysis_ready': False, 'events': reports, 'errors': catalog['errors'],
                    'rebuilt_from_saved_event_coverage': True}
        save(args.derive_run / 'coverage.json', coverage)
        write_report(args.derive_run, catalog, coverage)
        progress(f'Derived {count} cutoff records without network')
        return 0 if count else 1
    if not 1 <= args.limit <= 200 or not 1 <= args.workers <= 16 or not 1 <= args.lookback_days <= 30 or args.page_cap < 1 or not 1 <= args.timeout <= 120 or not 0 <= args.retries <= 5:
        parser.error('Invalid collection bounds')
    try:
        if utc(args.start) >= utc(args.end):
            parser.error('start must precede end')
    except ValueError as error:
        parser.error(str(error))
    root = args.output / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:8])
    root.mkdir(parents=True)
    progress('Writing ' + str(root))
    get = lambda url: fetch(url, timeout=args.timeout, retries=args.retries)
    events, errors, receipts = [], [], []
    if args.events_file:
        body = json.loads(args.events_file.read_text(), parse_float=str)
        for event in body if isinstance(body, list) else [body]:
            events.append((event, None, str(args.events_file.resolve())))
    elif not args.slug:
        try:
            events, receipts, error = discover(args.start, args.end, get, args.page_cap, args.tag_id)
            if error:
                errors.append('discovery: ' + error)
        except (ValueError, TypeError, KeyError) as error:
            errors.append('discovery: ' + str(error))
    def read_seed(slug):
        source = GAMMA + '/events/slug/' + quote(slug, safe='')
        try:
            event, received = get(source)
            return (event, received, source), None
        except (ValueError, KeyError) as error:
            return None, slug + ': ' + str(error)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for item, error in pool.map(read_seed, args.slug):
            if error:
                errors.append(error)
            elif all(str(e[0]['id']) != str(item[0]['id']) for e in events):
                events.append(item)
    # Spread a bounded pilot across observed series rather than taking only one family.
    groups = {}
    for item in events:
        groups.setdefault(item[0].get('seriesSlug') or 'unknown', []).append(item)
    for group in groups.values():
        group.sort(key=lambda item: int(item[0]['id']), reverse=True)
    selected = []
    while len(selected) < args.limit and any(groups.values()):
        for group in groups.values():
            if group and len(selected) < args.limit:
                selected.append(group.pop(0))
    catalog = {'schema_version': 1, 'created_at': now(), 'collector_hash': digest(Path(__file__).read_text()),
               'templates_hash': digest(TEMPLATES), 'start': args.start, 'end': args.end,
               'scope': 'saved_events' if args.events_file else 'seed_slugs' if args.slug else 'closed_bitcoin_tag_end_date_range',
               'tag_id': args.tag_id, 'selection': 'round_robin_series_latest_ids',
               'discovery_received_at': receipts, 'discovered': len(events),
               'selected': len(selected), 'truncated': len(events) > args.limit, 'errors': errors,
               'events': [{k: e.get(k) for k in ('id', 'slug', 'title', 'startDate', 'endDate', 'closed', 'seriesSlug')}
                          for e, _, _ in selected]}
    save(root / 'catalog.json', catalog)
    def work(item):
        event, received, source = item
        try:
            report = collect_event(event, received, source, root / str(int(event['id'])), get,
                                   args.lookback_days, args.page_cap)
            progress(f"Event {event['id']}: {report['markets']} markets, {report['prices_with_data']} histories")
            return report
        except Exception as error:
            return {'event_id': str(event.get('id')), 'collection_complete': False, 'issues': [str(error)]}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        reports = list(pool.map(work, selected))
    complete = bool(reports) and not errors and not catalog['truncated'] and all(r['collection_complete'] for r in reports)
    coverage = {'schema_version': 1, 'catalog_hash': digest(catalog), 'collection_complete': complete,
                'analysis_ready': False, 'events': reports, 'errors': errors}
    save(root / 'coverage.json', coverage)
    summary = f"Collected {len(reports)} events; complete={complete}; analysis_ready=False\n"
    write_report(root, catalog, coverage)
    progress(str(root))
    progress(summary.strip())
    return 0 if complete else 1


if __name__ == '__main__':
    sys.exit(main())
