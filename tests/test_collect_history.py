import tempfile
import json
import unittest
from pathlib import Path

from scripts import collect_history as h

FIXTURE = json.loads((Path(__file__).parent / 'fixtures' / 'history-responses.json').read_text())


class HistoryTests(unittest.TestCase):
    def event(self, date='March 8', year='2026'):
        market = {'id': '2', 'conditionId': 'condition', 'question': f'Will the price of Bitcoin be above $60,000 on {date}?',
                  'slug': 'bitcoin-above-60k-on-march-8-' + year, 'description': h.RULE,
                  'outcomes': '["No", "Yes"]', 'clobTokenIds': '["123", "456"]'}
        return {'id': '1', 'markets': [market]}, market

    def test_actual_mapping_and_dst(self):
        event, market = self.event()
        record = h.normalize(event, market, None, 'fixture')
        self.assertEqual(record['tokens'], {'NO': '123', 'YES': '456'})
        self.assertEqual(record['semantics']['candle_start'], '2026-03-08T16:00:00+00:00')
        market['question'] = market['question'].replace('March 8', 'March 7')
        self.assertEqual(h.normalize(event, market, None, 'fixture')['semantics']['candle_start'], '2026-03-07T17:00:00+00:00')

    def test_daily_hit_dst_and_inclusive_threshold(self):
        up = next(t for t in h.TEMPLATES if t['family'] == 'daily' and t['direction'] == 'up')
        market = {'question': 'Will Bitcoin reach $90,000 on March 8?', 'slug': 'will-bitcoin-reach-90k-on-march-8-2026', 'description': up['rules']}
        semantics = h.hit_semantics(market)
        self.assertEqual(semantics['comparator'], 'gte')
        self.assertEqual(semantics['window_start'], '2026-03-08T05:00:00+00:00')
        self.assertEqual(semantics['window_end'], '2026-03-09T04:00:00+00:00')
        market['question'] = market['question'].replace('reach', 'dip to')
        self.assertIsNone(h.hit_semantics(market))

    def test_weekly_range_and_cross_year_abstention(self):
        template = next(t for t in h.TEMPLATES if t['family'] == 'weekly' and t['direction'] == 'up' and t['window'] == 'calendar')
        market = {'question': 'Will Bitcoin reach $98,000 September 28-October 4?', 'slug': 'bitcoin-hit-september-28-october-4-2026', 'description': template['rules']}
        semantics = h.hit_semantics(market)
        self.assertEqual(semantics['window_start'], '2026-09-28T04:00:00+00:00')
        self.assertEqual(semantics['window_end'], '2026-10-05T04:00:00+00:00')
        market['question'] = 'Will Bitcoin reach $98,000 December 28-January 3?'
        self.assertIsNone(h.hit_semantics(market))

    def test_monthly_creation_windows_are_distinct(self):
        template = next(t for t in h.TEMPLATES if t['family'] == 'monthly' and t['direction'] == 'down' and t['window'] == 'creation')
        market = {'question': 'Will Bitcoin dip to $70,000 in September?', 'slug': 'bitcoin-dip-70000-september-2026', 'description': template['rules'], 'createdAt': '2026-09-15T12:34:56Z'}
        semantics = h.hit_semantics(market)
        self.assertEqual(semantics['window_start'], '2026-09-15T12:34:56+00:00')
        self.assertEqual(semantics['window_end'], '2026-10-01T04:00:00+00:00')
        self.assertTrue(semantics['creation_boundary_review_required'])
        del market['createdAt']
        self.assertIsNone(h.hit_semantics(market))

    def test_discovery_keeps_first_page_when_second_fails(self):
        def get(url):
            if 'offset=100' in url:
                raise ValueError('HTTP 403')
            return [{'id': str(i), 'title': 'Bitcoin hit', 'slug': 'what-price-will-bitcoin-hit-test-' + str(i)} for i in range(100)], 'receipt'
        events, receipts, error = h.discover('start', 'end', get, 3)
        self.assertEqual(len(events), 100)
        self.assertIn('403', error)

    def test_unknown_rules_and_missing_year_abstain(self):
        event, market = self.event()
        market['description'] += '\nException: fractional payouts.'
        self.assertIsNone(h.normalize(event, market, None, 'fixture')['semantics'])
        market['description'] = h.RULE
        market['slug'] = 'bitcoin-above'
        self.assertIsNone(h.normalize(event, market, None, 'fixture')['semantics'])

    def test_future_bucket_and_settlement_excluded(self):
        rows = FIXTURE['resolved_prices']
        points = h.price_rows(rows, True)
        self.assertIsNone(h.observation_at(points, 159)['point'])
        self.assertEqual(h.observation_at(points, 180)['point']['price'], '0.4')
        self.assertEqual(h.observation_at(points, 180)['age_seconds'], 20)
        self.assertFalse(points[-1]['forecasting_candidate'])
        self.assertTrue(h.price_rows(rows[-1:], False)[0]['forecasting_candidate'])

    def test_invalid_price_is_not_candidate(self):
        for price in ['NaN', '1.01', '-0.01']:
            self.assertFalse(h.price_rows([{'timestamp': 100, 'resolution_seconds': 60, 'price': price}], False)[0]['forecasting_candidate'])

    def test_saved_cutoffs_exclude_future_prices_and_future_hits(self):
        up = next(t for t in h.TEMPLATES if t['family'] == 'daily' and t['direction'] == 'up')
        event, market = self.event(date='March 8')
        market.update(question='Will Bitcoin reach $90,000 on March 8?', description=up['rules'])
        record = h.normalize(event, market, None, 'fixture')
        semantics = record['semantics']
        end = int(h.utc(semantics['window_end']).timestamp())
        cutoff = end - 3600
        raw = [{'timestamp': cutoff - 300, 'resolution_seconds': 300, 'price': '0.4'},
               {'timestamp': cutoff - 100, 'resolution_seconds': 300, 'price': '0.9'}]
        candles = [{'open_time_ms': cutoff * 1000 - 60000, 'close_time_ms': cutoff * 1000 - 1, 'close': '85000', 'high': '85000', 'low': '84000'},
                   {'open_time_ms': cutoff * 1000, 'close_time_ms': cutoff * 1000 + 59999, 'close': '95000', 'high': '95000', 'low': '85000'}]
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            h.save(folder / 'markets.json', [record])
            h.save(folder / 'prices.json', {'markets': [{'market_id': '2', 'complete': True, 'points': h.price_rows(raw, False)}]})
            h.save(folder / 'btc.json', {'candles': candles})
            before = {name: (folder / name).read_bytes() for name in ('markets.json', 'prices.json', 'btc.json')}
            result = h.derive_observations(folder)
            row = next(r for r in result['records'] if r['basis'] == 'before_window_end' and r['hours_before'] == 1)
            self.assertEqual(row['price']['point']['price'], '0.4')
            self.assertEqual(row['btc_last_completed_candle']['close'], '85000')
            self.assertIsNone(row['barrier_reached_so_far'])  # Earlier window coverage is missing.
            self.assertEqual(before, {name: (folder / name).read_bytes() for name in before})
            candles[0]['high'] = '90000'
            h.save(folder / 'btc.json', {'candles': candles})
            result = h.derive_observations(folder)
            row = next(r for r in result['records'] if r['basis'] == 'before_window_end' and r['hours_before'] == 1)
            self.assertTrue(row['barrier_reached_so_far'])

    def test_cursor_keeps_filters_and_partial_failure(self):
        urls = []
        def get(url):
            urls.append(url)
            if len(urls) == 1:
                return {'data': [1], 'pagination': {'next_cursor': 'abc', 'has_more': True}}, 'receipt'
            raise ValueError('HTTP 403')
        rows, receipts, error = h.pages('https://example.test', {'token_id': '123', 'interval': 'max'}, get)
        self.assertEqual(rows, [1])
        self.assertIn('HTTP 403', error)
        self.assertIn('token_id=123', urls[1])
        self.assertIn('interval=max', urls[1])
        self.assertIn('cursor=abc', urls[1])

    def test_repeated_cursor_fails(self):
        get = lambda url: ({'data': [], 'pagination': {'next_cursor': 'a'}}, 'receipt')
        self.assertIn('Repeated', h.pages('url', {}, get)[2])

    def test_candles_require_contiguous_source(self):
        row = FIXTURE['binance_one_minute']
        get = lambda url: ([row], 'receipt')
        candles, _ = h.candles(60, 120, get)
        self.assertEqual(candles[0]['close'], '101')
        with self.assertRaisesRegex(ValueError, 'Gap'):
            h.candles(0, 120, get)
        invalid = list(row)
        invalid[2] = '90'
        with self.assertRaisesRegex(ValueError, 'OHLC'):
            h.candles(60, 120, lambda url: ([invalid], 'receipt'))

    def test_threshold_equality_is_no_and_version_flag_blocks_label(self):
        event, market = self.event()
        timestamp = int(h.utc('2026-03-08T16:00:00Z').timestamp())
        def get(url):
            if '/resolutions' in url:
                return {'data': [{'condition_id': 'condition', 'status': 'resolved', 'price': '0', 'new_version_q': True}]}, 'receipt'
            if '/prices-history' in url:
                return {'data': [{'timestamp': timestamp - 86400, 'resolution_seconds': 60, 'price': '0.4'}], 'pagination': {'next_cursor': None}}, 'receipt'
            return [[timestamp * 1000, '60000', '60000', '60000', '60000', '1', timestamp * 1000 + 59999]], 'receipt'
        with tempfile.TemporaryDirectory() as temp:
            # Only one minute requested for source equality check.
            from unittest.mock import patch
            with patch.object(h, 'candles', return_value=([{'open_time_ms': timestamp * 1000, 'close_time_ms': timestamp * 1000 + 59999, 'open': '60000', 'high': '60000', 'low': '60000', 'close': '60000'}], ['2026-03-09T00:00:00+00:00'])):
                report = h.collect_event(event, None, 'fixture', Path(temp) / '1', get, 1, 3)
                label = json.loads((Path(temp) / '1' / 'labels.json').read_text())['markets'][0]
            self.assertFalse(label['source_yes'])
            self.assertIsNone(label['reported_yes'])
            self.assertEqual(label['status'], 'rule_version_review_required')
            self.assertFalse(report['analysis_ready'])


if __name__ == '__main__':
    unittest.main()
