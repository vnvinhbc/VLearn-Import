import json
import logging
import os
import unittest
from threading import Event
from unittest.mock import Mock, patch

from vlearn_importer.api_worker import ApiClient, ApiFailure, process_job
from vlearn_importer.config import Settings
from vlearn_importer.structured import CONTRACT

TOKEN = 'sensitive-' + 'z' * 32
LEASE = 'lease-' + 'x' * 32
BASE = '/api/v1/importer/jobs'
SOURCE_URL = f'{BASE}/job-1/source'
CLAIM = {
    'data': {
        'id': 'job-1',
        'kind': 'VOCABULARY',
        'filename': 'course.csv',
        'leaseToken': LEASE,
        'sourceUrl': SOURCE_URL,
        'leaseExpiresAt': '2099-01-01T00:00:00.000Z',
    },
}
COLUMNS = CONTRACT['kinds']['VOCABULARY']['columns']
SOURCE = (','.join(COLUMNS) + '\noffice,văn phòng,,,,,,\n').encode()
API_SETTINGS = Settings(mode='api', api_url='https://vlearn.example', service_token=TOKEN)


class ApiWorkerTests(unittest.TestCase):
    def test_environment_requires_secure_origin_and_token(self):
        for url in (
            'http://example.org', 'https://user@example.org', 'https://example.org/path',
            'https://example.org?x=1', '//example.org', 'https://example.org\\@untrusted.org',
            'https://example.org#', 'https://example.org?',
        ):
            with self.subTest(url=url), patch.dict(
                os.environ, WORKER_MODE='api', VLEARN_API_URL=url, VLEARN_SERVICE_TOKEN=TOKEN,
                clear=True,
            ), self.assertRaises(ValueError):
                Settings.from_environment()

        origin = 'http://127.0.0.1:8787'
        with patch.dict(
            os.environ, WORKER_MODE='api', VLEARN_API_URL=origin + '/',
            VLEARN_SERVICE_TOKEN=TOKEN, clear=True,
        ):
            self.assertEqual(Settings.from_environment().api_url, origin)

        with patch.dict(
            os.environ, WORKER_MODE='api', VLEARN_API_URL=origin,
            VLEARN_SERVICE_TOKEN='short', clear=True,
        ), self.assertRaises(ValueError):
            Settings.from_environment()

    def test_empty_claim_only_polls_once(self):
        client = Mock(spec=ApiClient)
        client.claim.return_value = None
        self.assertFalse(process_job(client, Event()))
        client.fetch_source.assert_not_called()
        client.submit_result.assert_not_called()

    def test_lost_ack_resubmits_identical_fenced_result(self):
        client = ApiClient(API_SETTINGS)
        stop = Mock(spec=Event)
        stop.wait.return_value = False
        stop.is_set.return_value = False
        with patch.object(
            client, 'request', side_effect=[
                json.dumps(CLAIM).encode(), SOURCE, ApiFailure(retryable=True), b'{"data":{}}',
            ],
        ) as request:
            self.assertTrue(process_job(client, stop))
        claim, source, attempt, retry = request.call_args_list
        self.assertEqual(claim.args[:2], ('POST', f'{BASE}/claim'))
        self.assertEqual(source.args[:2], ('GET', SOURCE_URL))
        self.assertEqual(source.kwargs['lease_token'], LEASE)
        self.assertEqual(attempt, retry)
        result = json.loads(attempt.kwargs['body'])
        self.assertEqual(result['leaseToken'], LEASE)
        self.assertEqual(result['rows'][0]['values']['term'], 'office')
        self.assertNotIn('error', result)
        stop.wait.assert_called_once_with(1)

    def test_shutdown_interrupts_result_retry(self):
        client = ApiClient(API_SETTINGS)
        stop = Mock(spec=Event)
        stop.is_set.return_value = False
        stop.wait.return_value = True
        with patch.object(
            client, 'request', side_effect=[
                json.dumps(CLAIM).encode(), SOURCE, ApiFailure(retryable=True),
            ],
        ) as request, self.assertLogs('vlearn_importer.api_worker', logging.WARNING):
            self.assertFalse(process_job(client, stop))
        self.assertEqual(request.call_count, 3)
        stop.wait.assert_called_once_with(1)

    def test_parser_failure_submits_safe_error(self):
        client = ApiClient(API_SETTINGS)
        with patch.object(
            client, 'request',
            side_effect=[json.dumps(CLAIM).encode(), b'malformed private source', b'{"data":{}}'],
        ) as request:
            self.assertTrue(process_job(client, Event()))
        result = json.loads(request.call_args.kwargs['body'])
        self.assertEqual(result['leaseToken'], LEASE)
        self.assertEqual(result['rows'], [])
        self.assertNotIn('malformed private source', result['error'])

    def test_invalid_claim_cannot_fetch_off_origin_or_log_secrets(self):
        for url in (
            'https://untrusted.org/source', '//untrusted.org/source',
            f'{BASE}/other/source', SOURCE_URL + '?query',
        ):
            client = ApiClient(API_SETTINGS)
            job = dict(CLAIM['data'], sourceUrl=url)
            with patch.object(
                client, 'request', return_value=json.dumps({'data': job}).encode(),
            ) as request, self.assertLogs('vlearn_importer.api_worker', logging.WARNING) as logs:
                self.assertFalse(process_job(client, Event()))
            self.assertEqual(request.call_count, 1)
            self.assertNotIn(TOKEN, '\n'.join(logs.output))
            self.assertNotIn(LEASE, '\n'.join(logs.output))
            self.assertNotIn(url, '\n'.join(logs.output))

    def test_transport_sets_authentication_and_rejects_redirects(self):
        client = ApiClient(API_SETTINGS)
        response = Mock(status=302)
        response.getheader.return_value = 'https://untrusted.org/source'
        with patch('vlearn_importer.api_worker.HTTPSConnection') as connection:
            transport = connection.return_value
            transport.getresponse.return_value = response
            with self.assertRaises(ApiFailure):
                client.request('GET', SOURCE_URL, lease_token=LEASE)
        connection.assert_called_once()
        transport.request.assert_called_once()
        sent = transport.request.call_args
        self.assertEqual(sent.args[:2], ('GET', SOURCE_URL))
        self.assertEqual(sent.kwargs['headers']['Authorization'], f'Bearer {TOKEN}')
        self.assertEqual(sent.kwargs['headers']['X-Import-Lease'], LEASE)
        transport.close.assert_called_once()
