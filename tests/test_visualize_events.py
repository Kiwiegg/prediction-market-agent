import json
from pathlib import Path
import tempfile
import unittest
from scripts.visualize_events import prepare_event, window_points, build

FIXTURE=json.loads((Path(__file__).parent/'fixtures/event-explorer.json').read_text())


class EventExplorerTests(unittest.TestCase):
    def test_hit_status_uses_only_completed_candles(self):
        result=prepare_event(**FIXTURE)
        up=next(m for m in result['markets'] if m['id']=='up')
        down=next(m for m in result['markets'] if m['id']=='down')
        self.assertEqual([p[4] for p in up['points']],[0,1,1])
        self.assertEqual([p[4] for p in down['points']],[0,0,1])
        self.assertEqual(up['hit'],120)
        self.assertEqual(down['hit'],180)
        self.assertTrue(up['venue_yes'])
        self.assertEqual(down['selection'],'drop')

    def test_boundary_review_and_unsupported_rules_remain_explicit(self):
        result=prepare_event(**FIXTURE)
        review=next(m for m in result['markets'] if m['id']=='review')
        self.assertEqual([p[4] for p in review['points']],[2,2,2])
        self.assertIsNone(review['hit'])
        self.assertEqual(result['omitted'],['unsupported'])

    def test_failed_segments_and_zero_width_points_excluded(self):
        history=FIXTURE['histories']['markets'][0]
        self.assertEqual(len(window_points(history,0,180)),3)
        self.assertEqual(window_points({'granular':[{'complete':False,'points':history['granular'][0]['points']}]},0,180),[])

    def test_missing_spot_remains_null(self):
        result=prepare_event(**dict(FIXTURE,btc={'candles':[]}))
        for market in result['markets']:
            for p in market['points']:
                self.assertIsNone(p[2]);self.assertIsNone(p[3]);self.assertEqual(p[4],2)

    def test_standalone_report_escapes_fetched_text_and_records_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);folder=root/'test';folder.mkdir()
            event=dict(FIXTURE['event'],title='Test </script> event')
            (root/'catalog.json').write_text(json.dumps({'events':[event]}))
            for file,key in [('markets.json','markets'),('prices.json','histories'),('btc.json','btc'),('labels.json','labels')]:
                (folder/file).write_text(json.dumps(FIXTURE[key]))
            output=root/'report.html';payload=build(root,output)
            self.assertEqual(len(payload['inputs']),4)
            self.assertNotIn('Test </script> event',output.read_text())
            self.assertIn('Test \\u003c/script>',output.read_text())
