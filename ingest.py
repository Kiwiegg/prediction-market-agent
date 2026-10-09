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


def fetch(url, getter=http_get, timeout=15, retries=2):
    """Return parsed data and receipt time; raise on a failed retrieval."""
    for attempt in range(retries + 1):
        status = None
        try:
            status, body = getter(url, timeout)
            if status != 200:
                raise ValueError(f'HTTP {status}')
            return json.loads(body, parse_float=str), now()
        except HTTPError as error:
            status = error.code
            message = f'HTTP {status}: {error.reason}'
        except (URLError, TimeoutError, OSError) as error:
            message = str(error)
        except (ValueError, UnicodeError, TypeError) as error:
            message = str(error)
            if status == 200:
                message = f'Invalid JSON: {message}'
        if attempt < retries and (status is None or status == 429 or status >= 500):
            time.sleep(0.5 * (2 ** attempt))
        else:
            break
    raise ValueError(f'{url}: {message}')


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


def normalize(market, fetched_at, event=None):
    rules = market.get('description')
    rules = rules if isinstance(rules, str) else ''
    parents = [event] if event else market.get('events', [])
    parent = parents[0] if isinstance(parents, list) and len(parents) == 1 else None
    event_id = parent.get('id') if isinstance(parent, dict) else None
    record = {
        'schema_version': 5, 'market_id': market.get('id'),
        'event_id': event_id,
        'condition_id': market.get('conditionId'), 'question': market.get('question'),
        'slug': market.get('slug'), 'rules': rules,
        'rules_sha256': hashlib.sha256(rules.encode()).hexdigest() if rules.strip() else None,
        'resolution_source': market.get('resolutionSource'), 'end_date': market.get('endDate'),
        'fetched_at': fetched_at, 'active': market.get('active'), 'closed': market.get('closed'),
        'neg_risk': market.get('negRisk'), 'outcomes': {}, 'issues': [],
        'venue': {
            'position_system': None, 'market_version_metadata': market.get('version'),
            'collateral_asset_metadata': market.get('denominationToken'), 'payout_unit': None,
            'status': 'unsupported' if market.get('negRisk') is True else 'unverified',
        },
        'clob_info': None, 'clob_info_fetched_at': None,
        'semantic_review_status': 'not_reviewed', 'pricing_eligible': False,
    }
    if not rules.strip():
        record['issues'].append('missing_rules')
    if not record['condition_id']:
        record['issues'].append('missing_condition_id')
    if event_id is None:
        record['issues'].append('ambiguous_event_id' if isinstance(parents, list) and len(parents) > 1
                                else 'missing_event_id')
    if market.get('active') is not True or market.get('closed') is not False:
        record['issues'].append('inactive_or_unknown_market_status')
    try:
        record['outcomes'] = {
            label: {'token_id': token, 'book': None, 'book_fetched_at': None,
                    'fee': None, 'fee_fetched_at': None, 'fee_formula_status': 'unverified'}
            for label, token in token_mapping(market).items()
        }
    except (ValueError, TypeError):
        record['issues'].append('invalid_binary_token_mapping')
    return record


def ingest(root, *, limit=10, event_slug=None, market_slug=None, getter=http_get,
           timeout=15, retries=2):
    # Discovery failure raises before writing a misleading empty successful dataset.
    event = None
    if event_slug:
        event, fetched_at = fetch(GAMMA + '/events/slug/' + quote(event_slug, safe=''),
                                 getter, timeout, retries)
        markets = event.get('markets') if isinstance(event, dict) else None
    else:
        params = {'slug': market_slug} if market_slug else {
            'active': 'true', 'closed': 'false', 'limit': limit,
            'order': 'liquidityNum', 'ascending': 'false'}
        markets, fetched_at = fetch(GAMMA + '/markets?' + urlencode(params), getter, timeout, retries)
    if not isinstance(markets, list) or not markets:
        raise ValueError('Discovery returned no markets or an invalid response')
    records = []
    seen = set()
    for market in markets[:limit]:
        if not isinstance(market, dict) or market.get('id') is None:
            raise ValueError('Discovery returned a market without an ID')
        if str(market['id']) in seen:
            raise ValueError('Discovery returned a duplicate market ID')
        seen.add(str(market['id']))
        record = normalize(market, fetched_at, event)
        records.append(record)

        def get(url, field):
            try:
                return fetch(url, getter, timeout, retries)
            except ValueError as error:
                record['issues'].append(f'{field}: {error}')
                return None, None

        condition = record['condition_id']
        if condition:
            info, received_at = get(CLOB + '/clob-markets/' + quote(str(condition), safe=''), 'clob_info')
            record['clob_info'] = info
            record['clob_info_fetched_at'] = received_at
            if not isinstance(info, dict) or 'error' in info:
                record['issues'].append('missing_clob_info')
            elif record['outcomes']:
                reported = info.get('t')
                expected = {(label, outcome['token_id']) for label, outcome in record['outcomes'].items()}
                actual = {(str(item.get('o')).upper(), item.get('t')) for item in reported
                          if isinstance(item, dict)} if isinstance(reported, list) else set()
                if actual != expected:
                    record['issues'].append('clob_token_mapping_mismatch')
        for label, outcome in record['outcomes'].items():
            token = outcome['token_id']
            book, received_at = get(CLOB + '/book?' + urlencode({'token_id': token}), label + ':book')
            outcome['book'], outcome['book_fetched_at'] = book, received_at
            record['issues'].extend(f'{label}:{issue}' for issue in book_issues(book, token, condition))
            if isinstance(book, dict) and book.get('neg_risk') is True:
                record['venue']['status'] = 'unsupported'
            fee, received_at = get(CLOB + '/fee-rate?' + urlencode({'token_id': token}), label + ':fee')
            outcome['fee'], outcome['fee_fetched_at'] = fee, received_at
            if not isinstance(fee, dict) or not decimal_valid(fee.get('base_fee'), 0):
                record['issues'].append(f'{label}:missing_fee_data')
        record['ingestion_status'] = 'partial' if record['issues'] else 'captured'
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid4().hex[:8]
    path = Path(root) / 'runs' / run_id / 'markets.json'
    path.parent.mkdir(parents=True, exist_ok=False)
    with path.open('xb') as stream:
        stream.write(encode(records))
    return path, records


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
    try:
        path, markets = ingest(args.output, limit=args.limit, event_slug=args.event_slug,
                               market_slug=args.market_slug, timeout=args.timeout, retries=args.retries)
    except ValueError as error:
        print(f'Ingestion failed: {error}', file=sys.stderr)
        return 1
    complete = all(not market['issues'] for market in markets)
    print(f"{'complete' if complete else 'partial'}: {len(markets)} markets; data: {path}")
    return 0 if complete else 1


if __name__ == '__main__':
    sys.exit(main())
