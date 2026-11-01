import unittest
from worker import scrape_worker as worker

class WorkerTests(unittest.TestCase):
    def test_result_is_reported_with_same_claim_and_receipt(self):
        class Response:
            def raise_for_status(self): pass
        class Session:
            def __init__(self): self.calls=[]
            def post(self,url,**kw): self.calls.append((url,kw));return Response()
        session=Session()
        claim={'jobId':'j','taskId':'t','token':'lease','fence':3,'sourceUrl':'https://example.invalid/n','chapterNumber':2}
        self.assertTrue(worker.run_step('https://backend.invalid','test-only',claim,
            lambda *args,**kwargs:{'receiptId':'verified'},session))
        self.assertTrue(session.calls[0][0].endswith('/complete'))
        self.assertEqual(session.calls[0][1]['json']['receiptId'],'verified')
        self.assertEqual(session.calls[0][1]['json']['fence'],3)
    def test_failed_scrape_reports_failure_without_false_completion(self):
        class Session:
            def __init__(self):self.calls=[]
            def post(self,url,**kw):self.calls.append(url)
        def fail(*args,**kwargs):raise RuntimeError('test outage')
        session=Session()
        self.assertFalse(worker.run_step('https://backend.invalid','test-only',{},fail,session))
        self.assertTrue(session.calls[0].endswith('/fail'))
