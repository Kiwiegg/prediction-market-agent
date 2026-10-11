import unittest
from scripts.visualize_market import usable_points, join_candles, distance_rows, first_hit, venue_badge


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

    def test_barrier_status_has_no_future_hit_and_stays_hit(self):
        sem={'threshold':'100','kind':'window_high','window_start':'1970-01-01T00:00:00+00:00','window_end':'1970-01-01T01:00:00+00:00'}
        candles=[{'open_time_ms':0,'close_time_ms':59999,'high':'99'},
                 {'open_time_ms':60000,'close_time_ms':119999,'high':'100'}]
        rows=[{'time':60,'price':'0.3','btc':'80'},{'time':120,'price':'0.9','btc':'90'}]
        result=distance_rows(rows,candles,sem)
        self.assertEqual([r['barrier_status'] for r in result],['before_hit','after_hit'])
        self.assertEqual(result[0]['distance_pct'],'25.00')
        self.assertEqual(result[0]['hours_remaining'],59/60)

    def test_missing_path_is_unknown_unless_hit_observed(self):
        sem={'threshold':'80','kind':'window_low','window_start':'1970-01-01T00:00:00+00:00','window_end':'1970-01-01T01:00:00+00:00'}
        rows=[{'time':120,'price':'0.4','btc':'100'}]
        candles=[{'open_time_ms':60000,'close_time_ms':119999,'low':'90'}]
        self.assertEqual(distance_rows(rows,candles,sem)[0]['barrier_status'],'unknown')
        candles[0]['low']='80'
        result=distance_rows(rows,candles,sem)[0]
        self.assertEqual(result['barrier_status'],'after_hit')
        self.assertEqual(result['distance_pct'],'20.0')

    def test_hit_marker_uses_candle_completion_and_exact_equality(self):
        candles=[{'close_time_ms':59999,'high':'99','low':'90'},
                 {'close_time_ms':119999,'high':'100','low':'80'}]
        self.assertEqual(first_hit(candles,{'threshold':'100','kind':'window_high'}),120)
        self.assertEqual(first_hit(candles,{'threshold':'80','kind':'window_low'}),120)
        self.assertIsNone(first_hit(candles,{'threshold':'101','kind':'window_high'}))

    def test_venue_badge_requires_resolved_yes_record(self):
        self.assertEqual(venue_badge({'resolution':{'status':'proposed','price':'1000000000000000000'}}),'')
        self.assertEqual(venue_badge({'resolution':{'status':'resolved','price':'0'}}),'')
        self.assertIn('Venue recorded YES',venue_badge({'resolution':{'status':'resolved','price':'1000000000000000000','new_version_q':True}}))
