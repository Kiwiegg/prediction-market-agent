import unittest
from scripts.visualize_market import usable_points, join_candles


class PreviewTests(unittest.TestCase):
    def test_quarantined_incomplete_and_future_buckets_excluded(self):
        valid = {'timestamp': 0, 'bucket_end': 300, 'resolution_seconds': 300,
                 'price': '0.4', 'forecasting_candidate': True}
        history = {'granular': [
            {'complete': False, 'points': [valid]},
            {'complete': True, 'points': [valid, dict(valid, forecasting_candidate=False),
                dict(valid, timestamp=300, bucket_end=600), dict(valid, resolution_seconds=0)]}]}
        self.assertEqual(usable_points(history, 0, 300), [valid])

    def test_join_never_uses_future_or_stale_candle(self):
        points = [{'bucket_end': 300, 'price': '0.4'}, {'bucket_end': 600, 'price': '0.5'}]
        candles = [{'close_time_ms': 299999, 'close': '82000'},
                   {'close_time_ms': 300000, 'close': '83000'}]
        rows = join_candles(points, candles)
        self.assertEqual(rows[0]['btc'], '82000')
        self.assertIsNone(rows[1]['btc'])
