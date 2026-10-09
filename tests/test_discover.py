import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import discover
import ingest

FIXTURES = Path(__file__).parent / 'fixtures'
MARKETS = json.loads((FIXTURES / 'bitcoin-markets.json').read_text())
RESPONSE = json.loads((FIXTURES / 'bitcoin-response.json').read_text())
SCHEMA = json.loads(discover.SCHEMA_PATH.read_text())


def final_response(value):
    response = copy.deepcopy(RESPONSE)
    response['output'][0]['content'][0]['text'] = json.dumps(value)
    return response


def tool_response(name, arguments, call_id):
    return {'status': 'completed', 'output': [{'type': 'function_call', 'name': name,
            'arguments': json.dumps(arguments), 'call_id': call_id, 'id': call_id}]}


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.markets_path = self.root / 'markets.json'
        self.markets_path.write_bytes(ingest.encode(MARKETS))

    def run_saved(self, response=RESPONSE, **kwargs):
        path = self.root / 'response.json'
        path.write_bytes(ingest.encode(response))
        return discover.run(self.root, query='Bitcoin closing prices',
                            markets_path=self.markets_path, response_file=path, **kwargs)

    def output(self):
        return discover.extract_response(copy.deepcopy(RESPONSE))

    def test_saved_response_trace_and_unreviewed_output(self):
        path, session = self.run_saved()
        self.assertEqual(session['status'], 'completed')
        result = json.loads((path / 'contracts.json').read_text())
        self.assertEqual(len(result['contracts']), 2)
        record = result['contracts'][0]
        self.assertEqual(record['threshold'], '85000')
        self.assertFalse(record['pricing_eligible'])
        self.assertEqual(record['source']['sha256'], discover.digest(self.markets_path.read_bytes()))
        for span in record['evidence']:
            self.assertEqual(MARKETS[0]['rules'][span['start']:span['end']], span['quote'])
        self.assertEqual(session['model_calls'][0]['response'], RESPONSE)
        self.assertIn('prompt_sha256', session)
        self.assertIn('output_schema', session)

    def test_fabricated_quote_wrong_id_missing_market_and_extra_field_rejected(self):
        for mutation in ('quote', 'id', 'missing', 'extra'):
            with self.subTest(mutation=mutation):
                value = self.output()
                if mutation == 'quote':
                    value['contracts'][0]['evidence'][0]['quote'] = 'Not present in actual rules'
                elif mutation == 'id':
                    value['contracts'][0]['market_id'] = 'invented'
                elif mutation == 'missing':
                    value['contracts'].pop()
                else:
                    value['contracts'][0]['probability'] = '0.8'
                path, session = self.run_saved(final_response(value))
                self.assertEqual(session['status'], 'failed')
                self.assertFalse((path / 'contracts.json').exists())
                self.assertTrue((path / 'session.json').exists())

    def test_null_fields_require_abstention_and_missing_fields(self):
        value = self.output()
        record = value['contracts'][0]
        record['observation_time'] = None
        record['missing_fields'] = ['observation_time']
        record['evidence'] = [span for span in record['evidence'] if span['field'] != 'observation_time']
        _, session = self.run_saved(final_response(value))
        self.assertEqual(session['status'], 'failed')
        record['status'] = 'abstained'
        record['reason'] = 'Observation time unavailable'
        path, session = self.run_saved(final_response(value))
        self.assertEqual(session['status'], 'completed')
        result = json.loads((path / 'contracts.json').read_text())
        self.assertIsNone(result['contracts'][0]['observation_time'])
        record['missing_fields'] = []
        _, session = self.run_saved(final_response(value))
        self.assertEqual(session['status'], 'failed')

    def test_intraday_and_nonbinary_cannot_be_extracted(self):
        for field, invalid in [('observation_kind', 'intraday_touch'), ('payout_model', 'nonbinary')]:
            value = self.output()
            value['contracts'][0][field] = invalid
            _, session = self.run_saved(final_response(value))
            self.assertEqual(session['status'], 'failed')
            value['contracts'][0]['status'] = 'unsupported'
            _, session = self.run_saved(final_response(value))
            self.assertEqual(session['status'], 'completed')

    def test_decimal_and_time_validation(self):
        for field, invalid in [('threshold', 'NaN'), ('threshold', '85,000'),
                               ('threshold', '-1'), ('observation_time', '2026-10-10'),
                               ('observation_time', '2026-10-10T00:00:00')]:
            value = self.output()
            value['contracts'][0][field] = invalid
            _, session = self.run_saved(final_response(value))
            self.assertEqual(session['status'], 'failed')

    def test_missing_field_evidence_and_duplicate_quotes_rejected(self):
        value = self.output()
        value['contracts'][0]['evidence'] = value['contracts'][0]['evidence'][1:]
        _, session = self.run_saved(final_response(value))
        self.assertEqual(session['status'], 'failed')
        rows = copy.deepcopy(MARKETS)
        rows[0]['rules'] += ' Bitcoin (BTC)'
        rows[0]['rules_sha256'] = discover.digest(rows[0]['rules'].encode())
        self.markets_path.write_bytes(ingest.encode(rows))
        _, session = self.run_saved()
        self.assertEqual(session['status'], 'failed')

    def test_changed_rule_hash_fails_and_retains_session(self):
        rows = copy.deepcopy(MARKETS)
        rows[0]['rules'] += ' changed'
        self.markets_path.write_bytes(ingest.encode(rows))
        _, session = self.run_saved()
        self.assertEqual(session['status'], 'failed')
        self.assertIn('hash mismatch', session['errors'][0])

    def test_refusal_and_incomplete_response_fail(self):
        for response in [dict(RESPONSE, status='incomplete'),
                         {'status': 'completed', 'output': [{'type': 'message',
                          'content': [{'type': 'refusal', 'refusal': 'No'}]}]},
                         {'status': 'completed', 'output': None},
                         {'status': 'completed', 'output': [{'type': 'message', 'content': ['bad']}]},
                         []]:
            path, session = self.run_saved(response)
            self.assertEqual(session['status'], 'failed')
            self.assertFalse((path / 'contracts.json').exists())

    def test_partial_source_cannot_be_reported_as_complete(self):
        rows = copy.deepcopy(MARKETS)
        rows[0]['issues'] = ['YES:missing_fee_data']
        rows[0]['ingestion_status'] = 'partial'
        self.markets_path.write_bytes(ingest.encode(rows))
        _, session = self.run_saved()
        self.assertEqual(session['status'], 'partial')

    def test_full_search_read_extract_tool_loop(self):
        fixture = json.loads((FIXTURES / 'responses.json').read_text())
        fetched = []

        def getter(url, timeout):
            fetched.append(url)
            parsed = urlparse(url)
            if parsed.path == '/public-search':
                value = {'events': [{'id': 'event-1', 'slug': 'bitcoin-close', 'title': 'Bitcoin close'}],
                         'pagination': {'hasMore': False}}
            elif parsed.path == '/events/slug/bitcoin-close':
                value = {'id': 'event-1', 'markets': [dict(fixture['markets'][0],
                         id=row['market_id'], description=row['rules'], conditionId=row['condition_id'],
                         clobTokenIds=json.dumps([row['outcomes'][label]['token_id'] for label in ['NO', 'YES']]))
                         for row in MARKETS]}
            elif parsed.path.startswith('/clob-markets/'):
                row = next(row for row in MARKETS if row['condition_id'] == parsed.path.split('/')[-1])
                value = dict(fixture['clob_info'], t=[{'o': label, 't': outcome['token_id']}
                             for label, outcome in row['outcomes'].items()])
            else:
                token = parse_qs(parsed.query)['token_id'][0]
                outcome = next(outcome for row in MARKETS for outcome in row['outcomes'].values()
                               if outcome['token_id'] == token)
                value = outcome['book' if parsed.path == '/book' else 'fee']
            return 200, json.dumps(value).encode()

        responses = iter([tool_response('search_events', {'query': 'Bitcoin close', 'page': 1}, 'c1'),
                          tool_response('read_event', {'slug': 'bitcoin-close'}, 'c2'), RESPONSE])
        payloads = []

        def responder(payload):
            payloads.append(copy.deepcopy(payload))
            return next(responses)

        path, session = discover.run(self.root, query='Bitcoin close', model='fixture-model',
                                     responder=responder, getter=getter, limit=2)
        self.assertEqual(session['status'], 'completed')
        self.assertEqual(len(session['tools']), 2)
        self.assertEqual(len(session['model_calls']), 3)
        self.assertTrue(any('/public-search?' in url for url in fetched))
        self.assertEqual(len(json.loads((path / 'contracts.json').read_text())['contracts']), 2)
        messages = [item for item in payloads[-1]['input'] if item.get('type') == 'function_call_output']
        self.assertEqual([item['call_id'] for item in messages], ['c1', 'c2'])
        read_result = json.loads(messages[-1]['output'])
        self.assertNotIn('outcomes', read_result['markets'][0])
        self.assertEqual(payloads[0]['output_schema'], SCHEMA)

    def test_unknown_tool_and_undiscovered_slug_do_not_fetch(self):
        for name, arguments in [('shell', {'cmd': 'whoami'}),
                                ('read_event', {'slug': 'https://untrusted.example'})]:
            responses = iter([tool_response(name, arguments, 'c1'),
                              final_response({'contracts': [], 'summary': 'No usable inputs'})])
            def no_getter(*args):
                self.fail('Unauthorized network fetch')
            _, session = discover.run(self.root, query='Bitcoin', model='fixture-model',
                                       responder=lambda payload: next(responses), getter=no_getter)
            self.assertEqual(session['status'], 'partial')
            self.assertTrue(session['errors'])

    def test_tool_and_model_limits_stop_calls(self):
        count = 0
        def responder(payload):
            nonlocal count
            count += 1
            return tool_response('search_events', {'query': 'Bitcoin', 'page': 1}, 'c1')
        def getter(*args):
            return 200, b'{"events": []}'
        _, session = discover.run(self.root, query='Bitcoin', responder=responder,
                                   getter=getter, max_calls=2, max_tools=1)
        self.assertEqual(count, 2)
        self.assertEqual(len(session['tools']), 1)
        self.assertEqual(session['status'], 'failed')

    def test_saved_input_mode_never_offers_search_tools(self):
        def responder(payload):
            self.assertNotIn('tools', payload)
            return RESPONSE
        _, session = discover.run(self.root, query='Bitcoin', markets_path=self.markets_path,
                                   responder=responder)
        self.assertEqual(session['status'], 'completed')

    def test_missing_cli_fails_before_creating_run(self):
        with patch.object(discover.shutil, 'which', return_value=None), self.assertRaisesRegex(ValueError, 'Codex CLI'):
            discover.run(self.root, query='Bitcoin', model='selected-model')
        self.assertFalse((self.root / 'research').exists())

    def test_search_bounds_and_shape(self):
        with self.assertRaises(ValueError):
            discover.search_events('Bitcoin', page=4)
        with self.assertRaises(ValueError):
            discover.search_events('', page=1)
        with self.assertRaises(ValueError):
            discover.search_events('Bitcoin', getter=lambda *args: (200, b'[]'))

    def test_threshold_not_in_evidence_rejected(self):
        value = self.output()
        value['contracts'][0]['threshold'] = '90000'
        _, session = self.run_saved(final_response(value))
        self.assertEqual(session['status'], 'failed')

    def test_empty_model_output_without_search_is_not_discovery(self):
        _, session = discover.run(self.root, query='Bitcoin', responder=lambda payload:
                                   final_response({'contracts': [], 'summary': 'Nothing found'}))
        self.assertEqual(session['status'], 'failed')

    def test_saved_session_replays_final_response(self):
        original_path, _ = self.run_saved()
        replay_path, session = discover.run(self.root, query='Bitcoin', markets_path=self.markets_path,
                                            response_file=original_path / 'session.json')
        self.assertEqual(session['status'], 'completed')
        original = json.loads((original_path / 'contracts.json').read_text())
        replay = json.loads((replay_path / 'contracts.json').read_text())
        self.assertEqual(original['contracts'], replay['contracts'])

    def test_codex_adapter_uses_chatgpt_and_disables_builtin_tools(self):
        step = {'action': 'finish', 'query': None, 'page': None, 'slug': None, 'result': self.output()}
        payload = {'model': 'fixture-model', 'instructions': 'Extract only', 'input': [], 'output_schema': SCHEMA}

        def runner(command, **kwargs):
            self.assertNotIn('shell', kwargs)
            self.assertIn('--ignore-user-config', command)
            self.assertIn('--ephemeral', command)
            self.assertIn('read-only', command)
            self.assertIn('forced_login_method="chatgpt"', command)
            self.assertIn('agents.enabled=false', command)
            self.assertIn('shell_tool', command)
            self.assertNotIn('OPENAI_API_KEY', kwargs['env'])
            output_path = Path(command[command.index('--output-last-message') + 1])
            output_path.write_text(json.dumps(step))
            return discover.subprocess.CompletedProcess(command, 0, stdout=json.dumps(
                {'type': 'turn.completed', 'usage': {'input_tokens': 10, 'output_tokens': 5}}), stderr='')

        with patch.object(discover.subprocess, 'run', side_effect=runner):
            response = discover.call_codex(payload, timeout=30)
        self.assertEqual(discover.extract_response(response), self.output())
        self.assertEqual(response['provider'], 'codex_cli')
        self.assertEqual(response['usage']['input_tokens'], 10)

    def test_codex_adapter_routes_search_action(self):
        step = {'action': 'search_events', 'query': 'Bitcoin', 'page': 1, 'slug': None, 'result': None}
        payload = {'model': 'fixture-model', 'instructions': 'Search', 'input': [],
                   'output_schema': SCHEMA, 'tools': discover.TOOLS}

        def runner(command, **kwargs):
            Path(command[command.index('--output-last-message') + 1]).write_text(json.dumps(step))
            return discover.subprocess.CompletedProcess(command, 0, stdout='', stderr='')

        with patch.object(discover.subprocess, 'run', side_effect=runner):
            response = discover.call_codex(payload, timeout=30)
        call = response['output'][0]
        self.assertEqual(call['name'], 'search_events')
        self.assertEqual(json.loads(call['arguments']), {'query': 'Bitcoin', 'page': 1})
        del payload['tools']
        with patch.object(discover.subprocess, 'run', side_effect=runner), self.assertRaises(ValueError):
            discover.call_codex(payload, timeout=30)

    def test_codex_builtin_tool_event_or_failure_is_rejected(self):
        step = {'action': 'finish', 'query': None, 'page': None, 'slug': None, 'result': self.output()}
        payload = {'model': 'fixture-model', 'instructions': 'Extract', 'input': [], 'output_schema': SCHEMA}
        for event in [{'type': 'item.completed', 'item': {'type': 'command_execution'}}, {'type': 'turn.failed'}]:
            def runner(command, **kwargs):
                Path(command[command.index('--output-last-message') + 1]).write_text(json.dumps(step))
                return discover.subprocess.CompletedProcess(command, 0, stdout=json.dumps(event), stderr='')
            with patch.object(discover.subprocess, 'run', side_effect=runner), self.assertRaises(ValueError):
                discover.call_codex(payload, timeout=30)

    def test_access_denial_stops_discovery_without_retrying_model(self):
        calls = 0
        def responder(payload):
            nonlocal calls
            calls += 1
            return tool_response('search_events', {'query': 'Bitcoin', 'page': 1}, 'c1')
        path, session = discover.run(self.root, query='Bitcoin', responder=responder,
                                     getter=lambda *args: (451, b'{}'))
        self.assertEqual(calls, 1)
        self.assertEqual(session['status'], 'failed')
        self.assertIn('HTTP 451', session['tools'][0]['result']['error'])
        self.assertFalse((path / 'contracts.json').exists())

    def test_api_key_login_is_rejected(self):
        login = discover.subprocess.CompletedProcess([], 0, stdout='Logged in using an API key', stderr='')
        with patch.object(discover.shutil, 'which', return_value='/local/codex'), \
                patch.object(discover.subprocess, 'run', return_value=login), \
                self.assertRaisesRegex(ValueError, 'ChatGPT'):
            discover.codex_preflight()


if __name__ == '__main__':
    unittest.main()
