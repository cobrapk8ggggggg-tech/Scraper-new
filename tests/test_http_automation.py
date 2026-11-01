"""Flask HTTP contract, using a synthetic chapter only."""
import os
import unittest
from unittest.mock import patch

os.environ['AUTOMATION_INGEST_SECRET'] = 'local-test-ingest'
os.environ['API_SECRET'] = 'local-ci-secret-not-for-production'
os.environ['NODE_BACKEND_URL'] = 'https://example.invalid'
from flask import Flask
from core.automation import register_automation_routes


class HttpAutomationTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        register_automation_routes(self.app)
        self.client = self.app.test_client()

    def test_requires_original_api_secret(self):
        response = self.client.post('/automation/scrape-chapter',
            json={'sourceUrl':'https://novelfire.net/story','chapterNumber':1})
        self.assertEqual(response.status_code,401)
        self.assertEqual(response.json.get('error'),'Unauthorized')

    def test_public_legacy_key_alone_cannot_run_durable_ingest(self):
        response=self.client.post('/automation/scrape-chapter',
            headers={'Authorization':os.environ['API_SECRET']},
            json={'sourceUrl':'https://novelfire.net/story','chapterNumber':1})
        self.assertEqual(response.status_code,403)

    def test_rejects_malformed_and_noninteger_input(self):
        h={'Authorization':os.environ['API_SECRET'],'x-automation-ingest-secret':os.environ['AUTOMATION_INGEST_SECRET']}
        self.assertEqual(self.client.post('/automation/scrape-chapter',headers=h).status_code,400)
        self.assertEqual(self.client.post('/automation/scrape-chapter',
            json={'sourceUrl':'https://novelfire.net/story','chapterNumber':True},headers=h).status_code,400)

    def test_synchronous_step_acknowledgement(self):
        h={'Authorization':os.environ['API_SECRET'],'x-automation-ingest-secret':os.environ['AUTOMATION_INGEST_SECRET']}
        with patch('core.automation.scrape_one',
            return_value={'ok':True,'status':'saved','chapterNumber':7}) as execute:
            response = self.client.post('/automation/scrape-chapter',
                headers=h,json={'sourceUrl':'https://novelfire.net/story','chapterNumber':7})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['status'],'saved')
        execute.assert_called_once()

    def test_failed_scrape_does_not_return_success(self):
        h={'Authorization':os.environ['API_SECRET'],'x-automation-ingest-secret':os.environ['AUTOMATION_INGEST_SECRET']}
        with patch('core.automation.scrape_one',side_effect=RuntimeError('synthetic outage')):
            response=self.client.post('/automation/scrape-chapter',headers=h,
                json={'sourceUrl':'https://novelfire.net/story','chapterNumber':8})
        self.assertEqual(response.status_code,502)
        self.assertNotIn('ok',response.json)

if __name__=='__main__':
    unittest.main()
