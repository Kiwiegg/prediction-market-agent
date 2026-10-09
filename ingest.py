#!/usr/bin/env python3
"""Read-only Polymarket ingestion. Python standard library; JSON file storage."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

GAMMA = 'https://gamma-api.polymarket.com'
CLOB = 'https://clob.polymarket.com'


def now():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + '\n').encode()


def http_get(url, timeout):
    request = Request(url, headers={'User-Agent': 'prediction-market-research/0.1',
                                    'Accept': 'application/json'})
    with urlopen(request, timeout=timeout) as response:
        return response.status, response.read()


def fetch(root, url, observations, getter=http_get, timeout=15, retries=2):
    """Keep every attempt, including HTTP error bodies and malformed JSON."""
    for attempt in range(retries + 1):
        record = {'url': url, 'requested_at': now(), 'attempt': attempt + 1}
        status, body = None, None
        try:
            status, body = getter(url, timeout)
        except HTTPError as error:
            status, body = error.code, error.read()
            record['error'] = str(error)
        except (URLError, TimeoutError, OSError) as error:
            record['error'] = str(error)
        record.update(received_at=now(), http_status=status)
        if body is not None:
            response_path = Path('responses') / f'{len(observations):03d}.json'
            (root / response_path).parent.mkdir(parents=True, exist_ok=True)
            with (root / response_path).open('xb') as stream:
                stream.write(body)
            record['body_path'] = response_path.as_posix()
            record['body_sha256'] = hashlib.sha256(body).hexdigest()
        value = None
        if status == 200:
            try:
                value = json.loads(body, parse_float=str)
                record['status'] = 'ok'
            except (ValueError, UnicodeError, TypeError) as error:
                record.update(status='error', error=f'Invalid JSON: {error}')
        else:
            record['status'] = 'error'
        observations.append(record)
        if record['status'] == 'ok':
            return value, len(observations) - 1
        if attempt < retries and (status is None or status == 429 or status >= 500):
            time.sleep(0.5 * (2 ** attempt))
        else:
            break
    return None, len(observations) - 1


def array(value):
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, list):
        raise ValueError('Expected an array or JSON-encoded array')
    return value


def token_mapping(market):
    outcomes = array(market.get('outcomes'))
    tokens = array(market.get('clobTokenIds'))
    if len(tokens) != 2 or len(outcomes) != 2:
        raise ValueError('Expected exactly two outcome tokens')
    labels = [str(label).strip().upper() for label in outcomes]
    if set(labels) != {'YES', 'NO'}:
        raise ValueError('Expected explicit YES and NO outcomes')
    if any(not isinstance(token, str) or not re.fullmatch(r'[0-9]+', token) for token in tokens):
        raise ValueError('Invalid outcome token ID')
    if tokens[0] == tokens[1]:
        raise ValueError('Duplicate outcome token ID')
    return dict(zip(labels, tokens))


def decimal_valid(value, minimum, maximum=None, strict=False):
    if isinstance(value, bool) or value is None:
        return False
    try:
        number = Decimal(str(value))
        return (number.is_finite() and (number > minimum if strict else number >= minimum)
                and (maximum is None or number <= maximum))
    except InvalidOperation:
        return False


def book_issues(book, token, condition):
    if not isinstance(book, dict):
        return ['missing_book']
    issues = []
    if book.get('asset_id') != token or book.get('market') != condition:
        issues.append('book_identity_mismatch')
    if not book.get('timestamp') or not book.get('hash'):
        issues.append('missing_book_timestamp_or_hash')
    if not decimal_valid(book.get('tick_size'), 0, 1, strict=True):
        issues.append('invalid_tick_size')
    if not decimal_valid(book.get('min_order_size'), 0, strict=True):
        issues.append('invalid_min_order_size')
    for side in ('bids', 'asks'):
        levels = book.get(side)
        if not isinstance(levels, list):
            issues.append(f'invalid_{side}')
            continue
        if any(not isinstance(level, dict)
               or not decimal_valid(level.get('price'), 0, 1)
               or not decimal_valid(level.get('size'), 0, strict=True) for level in levels):
            issues.append(f'invalid_{side}_level')
    # Preserve source ordering; never infer the best quote from list position.
    if not issues and book['bids'] and book['asks']:
        bid = max(Decimal(str(x['price'])) for x in book['bids'])
        ask = min(Decimal(str(x['price'])) for x in book['asks'])
        if bid >= ask:
            issues.append('crossed_or_locked_book')
    return issues


def normalize(market, source_index):
    rules = market.get('description')
    # Canonicalization only changes newline convention. Offsets can target this text.
    rules = rules.replace('\r\n', '\n').replace('\r', '\n') if isinstance(rules, str) else ''
    record = {
        'schema_version': 2, 'market_id': market.get('id'), 'condition_id': market.get('conditionId'),
        'question': market.get('question'), 'slug': market.get('slug'),
        'source_observation': source_index, 'rule_text': rules,
        'rule_sha256': hashlib.sha256(rules.encode()).hexdigest() if rules.strip() else None,
        'resolution_source': market.get('resolutionSource'),
        'trading_end_metadata': market.get('endDate'),
        'observation_time': None, 'expected_resolution_time': None,
        'tokens': {}, 'books': {}, 'fees': {}, 'issues': [],
        'venue': {
            'adapter_version': 'polymarket-read-only-v1',
            'position_system': None, 'market_version_metadata': market.get('version'),
            'collateral_asset_metadata': market.get('denominationToken'),
            'payout_unit': None, 'negative_risk': market.get('negRisk'),
            'status': 'unverified', 'operations_enabled': [],
            'reason': 'Position system, collateral and binary payouts require adapter verification',
        },
        'semantic_review_status': 'not_reviewed', 'pricing_eligible': False,
    }
    if not rules.strip():
        record['issues'].append('missing_rules')
    if not record['condition_id']:
        record['issues'].append('missing_condition_id')
    if market.get('negRisk') is True:
        record['venue'].update(status='unsupported', reason='Negative-risk mechanics excluded from V1')
    if market.get('active') is not True or market.get('closed') is not False:
        record['issues'].append('inactive_or_unknown_market_status')
    try:
        record['tokens'] = token_mapping(market)
    except (ValueError, TypeError):
        record['issues'].append('invalid_binary_token_mapping')
    return record


def ingest(root, *, limit=10, event_slug=None, market_slug=None, getter=http_get,
           timeout=15, retries=2):
    root = Path(root)
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid4().hex[:8]
    run_dir = root / 'runs' / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    run = {'schema_version': 2, 'run_id': run_id, 'started_at': now(), 'status': 'running',
           'config': {'limit': limit, 'event_slug': event_slug, 'market_slug': market_slug,
                      'timeout': timeout, 'retries': retries},
           'observations': [], 'markets': [], 'issues': []}
    observations = run['observations']

    def get(url):
        return fetch(run_dir, url, observations, getter, timeout, retries)

    try:
        if event_slug:
            value, source = get(GAMMA + '/events/slug/' + quote(event_slug, safe=''))
            markets = value.get('markets') if isinstance(value, dict) else None
        else:
            params = {'slug': market_slug} if market_slug else {
                'active': 'true', 'closed': 'false', 'limit': limit,
                'order': 'liquidityNum', 'ascending': 'false'}
            markets, source = get(GAMMA + '/markets?' + urlencode(params))
        if not isinstance(markets, list):
            run['issues'].append('discovery_failed_or_invalid_response')
            markets = []
        seen = set()
        for market in markets[:limit]:
            if not isinstance(market, dict):
                run['issues'].append('invalid_market_record')
                continue
            identity = market.get('id')
            if identity is None or str(identity) in seen:
                run['issues'].append('missing_or_duplicate_market_id')
                continue
            seen.add(str(identity))
            record = normalize(market, source)
            run['markets'].append(record)
            condition = record['condition_id']
            if condition:
                info, index = get(CLOB + '/clob-markets/' + quote(str(condition), safe=''))
                record['clob_info_observation'] = index
                if not isinstance(info, dict) or 'error' in info:
                    record['issues'].append('missing_clob_info')
                elif record['tokens']:
                    reported = info.get('t')
                    expected = {(label, token) for label, token in record['tokens'].items()}
                    actual = {(str(item.get('o')).upper(), item.get('t'))
                              for item in reported if isinstance(item, dict)} if isinstance(reported, list) else set()
                    if actual != expected:
                        record['issues'].append('clob_token_mapping_mismatch')
            for label, token in record['tokens'].items():
                book, index = get(CLOB + '/book?' + urlencode({'token_id': token}))
                issues = book_issues(book, token, condition)
                record['books'][label] = {'observation': index, 'issues': issues}
                record['issues'].extend(f'{label}:{issue}' for issue in issues)
                if isinstance(book, dict) and book.get('neg_risk') is True:
                    record['venue'].update(status='unsupported', reason='Book reports negative-risk mechanics')
                fee, index = get(CLOB + '/fee-rate?' + urlencode({'token_id': token}))
                valid = isinstance(fee, dict) and decimal_valid(fee.get('base_fee'), 0)
                record['fees'][label] = {'observation': index,
                                         'status': 'captured' if valid else 'missing_or_invalid',
                                         'formula_status': 'unverified'}
                if not valid:
                    record['issues'].append(f'{label}:missing_fee_data')
            record['ingestion_status'] = 'partial' if record['issues'] else 'captured'
        if not run['markets']:
            run['issues'].append('no_markets_collected')
        run['status'] = ('partial' if run['issues'] or any(m['issues'] for m in run['markets'])
                         or any(o['status'] != 'ok' for o in observations) else 'complete')
    except (ValueError, TypeError, KeyError) as error:
        run['issues'].append(f'invalid_response: {error}')
        run['status'] = 'partial'
    run['finished_at'] = now()
    path = run_dir / 'manifest.json'
    with path.open('xb') as stream:
        stream.write(encode(run))
    return path, run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('data'))
    parser.add_argument('--limit', type=int, default=10, help='Maximum markets (1–50)')
    selectors = parser.add_mutually_exclusive_group()
    selectors.add_argument('--event-slug', help='Manually seed one event family')
    selectors.add_argument('--market-slug', help='Collect one exact market')
    parser.add_argument('--timeout', type=float, default=15)
    parser.add_argument('--retries', type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.limit <= 50 or args.timeout <= 0 or not 0 <= args.retries <= 5:
        parser.error('Require limit 1–50, positive timeout, and retries 0–5')
    path, run = ingest(args.output, limit=args.limit, event_slug=args.event_slug,
                       market_slug=args.market_slug, timeout=args.timeout, retries=args.retries)
    print(f"{run['status']}: {len(run['markets'])} markets; manifest: {path}")
    return 0 if run['status'] == 'complete' else 1


if __name__ == '__main__':
    sys.exit(main())
