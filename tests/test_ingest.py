import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse

import ingest

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/responses.json').read_text())


def fixture_getter(fixture):
    def get(url, timeout):
        parsed = urlparse(url)
        if parsed.path == '/markets':
            value = fixture['markets']
        elif parsed.path.startswith('/events/slug/'):
            value = {'id': 'event-2', 'slug': 'selected-event', 'title': 'Selected event',
                     'markets': fixture['markets']}
        elif parsed.path.startswith('/clob-markets/'):
            value = fixture['clob_info']
        else:
            token = parse_qs(parsed.query)['token_id'][0]
            value = fixture['books' if parsed.path == '/book' else 'fees'][token]
        return 200, json.dumps(value).encode()
    return get


class IngestionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def run_fixture(self, fixture=None, **kwargs):
        return ingest.ingest(self.root, getter=fixture_getter(fixture or FIXTURE), retries=0, **kwargs)

    def test_self_contained_market_file_and_independent_runs(self):
        path, markets = self.run_fixture()
        second_path, second = self.run_fixture()
        self.assertNotEqual(path.parent, second_path.parent)
        self.assertEqual(path.name, 'markets.json')
        self.assertEqual(list(path.parent.iterdir()), [path])
        self.assertEqual(json.loads(path.read_text()), markets)
        market = markets[0]
        self.assertEqual(market['event_id'], 'event-1')
        self.assertEqual(market['outcomes']['YES']['token_id'], '111')
        self.assertEqual(market['outcomes']['NO']['token_id'], '222')
        self.assertEqual(market['outcomes']['YES']['book']['asks'][0]['price'], '0.50')
        self.assertEqual(market['outcomes']['YES']['fee'], {'base_fee': 0})
        self.assertTrue(market['outcomes']['YES']['book_fetched_at'])
        self.assertEqual(market['rules'], FIXTURE['markets'][0]['description'])
        self.assertEqual(market['rules_sha256'], ingest.hashlib.sha256(market['rules'].encode()).hexdigest())
        self.assertFalse(market['pricing_eligible'])
        self.assertNotIn('observations', market)
        self.assertNotIn('source_observation', market)
        self.assertEqual(market['outcomes']['YES']['book'], second[0]['outcomes']['YES']['book'])

    def test_missing_rules_and_fees_are_not_defaults(self):
        fixture = copy.deepcopy(FIXTURE)
        fixture['markets'][0]['description'] = ''
        fixture['fees']['111'] = {}
        _, markets = self.run_fixture(fixture)
        self.assertIn('missing_rules', markets[0]['issues'])
        self.assertIn('YES:missing_fee_data', markets[0]['issues'])
        self.assertIsNone(markets[0]['rules_sha256'])

    def test_unsupported_mechanics_are_explicit(self):
        fixture = copy.deepcopy(FIXTURE)
        fixture['markets'][0]['negRisk'] = True
        _, markets = self.run_fixture(fixture)
        self.assertEqual(markets[0]['venue']['status'], 'unsupported')
        self.assertTrue(markets[0]['neg_risk'])

    def test_invalid_mapping_skips_outcome_requests(self):
        fixture = copy.deepcopy(FIXTURE)
        fixture['markets'][0]['clobTokenIds'] = '["111", "111"]'
        _, markets = self.run_fixture(fixture)
        self.assertIn('invalid_binary_token_mapping', markets[0]['issues'])
        self.assertEqual(markets[0]['outcomes'], {})

    def test_book_identity_and_nonfinite_values_rejected(self):
        fixture = copy.deepcopy(FIXTURE)
        fixture['books']['111']['asset_id'] = '222'
        fixture['books']['222']['asks'][0]['price'] = 'NaN'
        _, markets = self.run_fixture(fixture)
        self.assertIn('YES:book_identity_mismatch', markets[0]['issues'])
        self.assertIn('NO:invalid_asks_level', markets[0]['issues'])

    def test_crossed_book_with_unsorted_levels(self):
        book = copy.deepcopy(FIXTURE['books']['111'])
        book['bids'].append({'price': '0.55', 'size': '1'})
        self.assertIn('crossed_or_locked_book', ingest.book_issues(book, '111', '0xexample'))

    def test_discovery_failure_produces_no_dataset(self):
        for getter in [lambda url, timeout: (404, b'{}'),
                       lambda url, timeout: (200, b'not-json')]:
            with self.assertRaises(ValueError):
                ingest.ingest(self.root, getter=getter, retries=0)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_failed_leg_retains_other_data_and_error(self):
        regular = fixture_getter(FIXTURE)
        def get(url, timeout):
            if '/book?' in url and '111' in url:
                raise URLError('DNS unavailable')
            return regular(url, timeout)
        _, markets = ingest.ingest(self.root, getter=get, retries=0)
        self.assertIsNone(markets[0]['outcomes']['YES']['book'])
        self.assertIsNotNone(markets[0]['outcomes']['NO']['book'])
        self.assertTrue(any('DNS unavailable' in issue for issue in markets[0]['issues']))
        self.assertEqual(markets[0]['ingestion_status'], 'partial')

    def test_event_selection_preserves_parent_membership_and_limit(self):
        fixture = copy.deepcopy(FIXTURE)
        fixture['markets'].append(dict(fixture['markets'][0], id='example-2'))
        _, markets = self.run_fixture(fixture, event_slug='selected-event', limit=1)
        self.assertEqual(len(markets), 1)
        self.assertEqual(markets[0]['event_id'], 'event-2')
        self.assertNotIn('event_slug', markets[0])
        self.assertNotIn('events', markets[0])

    def test_missing_or_ambiguous_parent_is_not_guessed(self):
        for parents, issue in [([], 'missing_event_id'),
                               ([{'id': 'a'}, {'id': 'b'}], 'ambiguous_event_id')]:
            fixture = copy.deepcopy(FIXTURE)
            fixture['markets'][0]['events'] = parents
            _, markets = self.run_fixture(fixture)
            self.assertIsNone(markets[0]['event_id'])
            self.assertIn(issue, markets[0]['issues'])

    def test_changed_rules_have_distinct_hashes(self):
        _, before = self.run_fixture()
        fixture = copy.deepcopy(FIXTURE)
        fixture['markets'][0]['description'] += ' Changed rule.'
        _, after = self.run_fixture(fixture)
        self.assertNotEqual(before[0]['rules_sha256'], after[0]['rules_sha256'])

    def test_clob_mapping_mismatch_is_rejected(self):
        fixture = copy.deepcopy(FIXTURE)
        fixture['clob_info']['t'][0]['t'] = '999'
        _, markets = self.run_fixture(fixture)
        self.assertIn('clob_token_mapping_mismatch', markets[0]['issues'])

    def test_rate_limit_retries_without_request_log(self):
        attempts = []
        def get(url, timeout):
            attempts.append(url)
            return (429, b'{}') if len(attempts) == 1 else (200, b'[]')
        with patch('ingest.time.sleep'):
            value, received_at = ingest.fetch('https://example.invalid', get)
        self.assertEqual(value, [])
        self.assertTrue(received_at)
        self.assertEqual(len(attempts), 2)


if __name__ == '__main__':
    unittest.main()
