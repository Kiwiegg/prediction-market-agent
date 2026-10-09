import copy
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

import ingest

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/responses.json').read_text())


def fixture_getter(fixture):
    def get(url, timeout):
        parsed = urlparse(url)
        if parsed.path == '/markets':
            value = fixture['markets']
        elif parsed.path.startswith('/events/slug/'):
            value = {'markets': fixture['markets']}
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

    def test_repeat_collection_stores_independent_responses(self):
        path, first = self.run_fixture()
        second_path, second = self.run_fixture()
        self.assertNotEqual(path.parent, second_path.parent)
        self.assertEqual(first['observations'][0]['response'], second['observations'][0]['response'])
        self.assertEqual(list(path.parent.iterdir()), [path])
        self.assertEqual(list(second_path.parent.iterdir()), [second_path])
        self.assertEqual(len(second['observations']), 6)
        self.assertEqual(first['status'], 'complete')
        self.assertEqual(first['schema_version'], 3)
        market = first['markets'][0]
        self.assertEqual(market['tokens'], {'NO': '222', 'YES': '111'})
        self.assertIn('\n', market['rule_text'])
        self.assertNotIn('\r', market['rule_text'])
        source = first['observations'][market['source_observation']]
        raw = source['response']
        self.assertIn('\r\n', raw[0]['description'])
        self.assertEqual(ingest.hashlib.sha256(market['rule_text'].encode()).hexdigest(), market['rule_sha256'])
        self.assertFalse(market['pricing_eligible'])
        self.assertEqual(market['venue']['status'], 'unverified')
        self.assertIsNone(market['observation_time'])

    def test_missing_rules_and_fees_are_not_defaults(self):
        fixture = copy.deepcopy(FIXTURE)
        fixture['markets'][0]['description'] = ''
        fixture['fees']['111'] = {}
        _, run = self.run_fixture(fixture)
        self.assertEqual(run['status'], 'partial')
        self.assertIn('missing_rules', run['markets'][0]['issues'])
        self.assertIn('YES:missing_fee_data', run['markets'][0]['issues'])
        self.assertIsNone(run['markets'][0]['rule_sha256'])

    def test_unsupported_mechanics_are_explicit(self):
        fixture = copy.deepcopy(FIXTURE)
        fixture['markets'][0]['negRisk'] = True
        _, run = self.run_fixture(fixture)
        self.assertEqual(run['markets'][0]['venue']['status'], 'unsupported')
        self.assertEqual(run['markets'][0]['venue']['operations_enabled'], [])

    def test_invalid_token_mapping_does_not_request_wrong_books(self):
        fixture = copy.deepcopy(FIXTURE)
        fixture['markets'][0]['clobTokenIds'] = '["111", "111"]'
        _, run = self.run_fixture(fixture)
        self.assertIn('invalid_binary_token_mapping', run['markets'][0]['issues'])
        self.assertEqual(run['markets'][0]['books'], {})

    def test_book_identity_and_nonfinite_values_rejected(self):
        fixture = copy.deepcopy(FIXTURE)
        fixture['books']['111']['asset_id'] = '222'
        fixture['books']['222']['asks'][0]['price'] = 'NaN'
        _, run = self.run_fixture(fixture)
        self.assertEqual(run['status'], 'partial')
        self.assertIn('YES:book_identity_mismatch', run['markets'][0]['issues'])
        self.assertIn('NO:invalid_asks_level', run['markets'][0]['issues'])

    def test_crossed_book_rejected_even_with_unsorted_levels(self):
        book = copy.deepcopy(FIXTURE['books']['111'])
        book['bids'].append({'price': '0.55', 'size': '1'})
        self.assertIn('crossed_or_locked_book', ingest.book_issues(book, '111', '0xexample'))

    def test_http_error_preserves_response_and_run_is_partial(self):
        def fail(url, timeout):
            raise HTTPError(url, 404, 'Not found', {}, BytesIO(b'{"error":"not found"}'))
        path, run = ingest.ingest(self.root, getter=fail, retries=0)
        self.assertTrue(path.exists())
        self.assertEqual(run['status'], 'partial')
        record = run['observations'][0]
        self.assertEqual(record['http_status'], 404)
        self.assertEqual(record['response'], {'error': 'not found'})

    def test_dns_failure_and_invalid_json_are_auditable(self):
        def fail(url, timeout):
            raise URLError('DNS unavailable')
        _, run = ingest.ingest(self.root, getter=fail, retries=0)
        self.assertEqual(run['status'], 'partial')
        self.assertIn('DNS unavailable', run['observations'][0]['error'])
        _, run = ingest.ingest(self.root, getter=lambda url, timeout: (200, b'not-json'), retries=0)
        self.assertIn('Invalid JSON', run['observations'][0]['error'])
        self.assertNotIn('response', run['observations'][0])

    def test_event_selection_and_limit(self):
        fixture = copy.deepcopy(FIXTURE)
        fixture['markets'].append(dict(fixture['markets'][0], id='example-2'))
        _, run = self.run_fixture(fixture, event_slug='synthetic-event', limit=1)
        self.assertEqual(len(run['markets']), 1)
        self.assertIn('/events/slug/synthetic-event', run['observations'][0]['url'])

    def test_changed_rules_have_distinct_hashes(self):
        _, before = self.run_fixture()
        fixture = copy.deepcopy(FIXTURE)
        fixture['markets'][0]['description'] += ' Changed rule.'
        _, after = self.run_fixture(fixture)
        self.assertNotEqual(before['markets'][0]['rule_sha256'], after['markets'][0]['rule_sha256'])

    def test_clob_mapping_mismatch_is_rejected(self):
        fixture = copy.deepcopy(FIXTURE)
        fixture['clob_info']['t'][0]['t'] = '999'
        _, run = self.run_fixture(fixture)
        self.assertIn('clob_token_mapping_mismatch', run['markets'][0]['issues'])

    def test_rate_limit_retry_retains_each_attempt(self):
        attempts = []
        def get(url, timeout):
            attempts.append(url)
            if len(attempts) == 1:
                return 429, b'{"error":"rate limited"}'
            return 200, b'[]'
        from unittest.mock import patch
        observations = []
        with patch('ingest.time.sleep'):
            value, index = ingest.fetch(self.root, 'https://example.invalid', observations, get)
        self.assertEqual(value, [])
        self.assertEqual(index, 1)
        self.assertEqual([o['http_status'] for o in observations], [429, 200])
        self.assertEqual(observations[0]['response'], {'error': 'rate limited'})
        self.assertEqual(observations[1]['response'], [])


if __name__ == '__main__':
    unittest.main()
