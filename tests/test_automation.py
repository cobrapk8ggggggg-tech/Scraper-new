"""Isolated unit tests: no external requests, accounts or DB writes."""
import importlib.util
import sys
import types
import unittest
from pathlib import Path


def load():
    flask=types.ModuleType('flask')
    flask.request=None
    flask.jsonify=lambda x: x
    sys.modules['flask']=flask
    core=types.ModuleType('core')
    core.__path__=[]
    sys.modules['core']=core
    config=types.ModuleType('core.config')
    config.API_SECRET='dummy'
    registry=types.ModuleType('core.registry')
    registry.resolve_site=lambda _:None
    backend=types.ModuleType('core.backend')
    backend.send_data_to_backend=lambda _:True
    backend.check_existing_chapters=lambda _:[]
    for m in (config,registry,backend):
        sys.modules[m.__name__]=m
    filename=Path(__file__).resolve().parents[1]/'core/automation.py'
    spec=importlib.util.spec_from_file_location('automation_test_target',filename)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AutomationFoundationTests(unittest.TestCase):
    def test_exact_domain_matching(self):
        mod=load()
        site={'domains':['novelfire.net']}
        self.assertTrue(mod.allowed_source_url('https://www.novelfire.net/book/1',site))
        for url in ['https://novelfire.net.evil.test/book','https://bad.test/?url=novelfire.net',
                    'file:///etc/passwd','https://user:pass@novelfire.net/',
                    'http://novelfire.net:8080/x']:
            self.assertFalse(mod.allowed_source_url(url,site))

    def test_chapter_save_and_idempotency(self):
        mod=load()
        mod.resolve_site=lambda _:{
            'domains':['novelfire.net'],'status':'active',
            'fetch_metadata':lambda _:{'title':'Sample Novel','sourceUrl':'https://novelfire.net/n'},
            'fetch_chapters':lambda _:[{'number':4,'title':'Fourth Chapter','url':'https://novelfire.net/4'}],
            'fetch_content':lambda _:'Original chapter text'
        }
        saved=[]
        mod.send_data_to_backend=lambda payload:saved.append(payload) or True
        response=mod.scrape_one('https://novelfire.net/n',4)
        self.assertEqual(response['status'],'saved')
        self.assertEqual(saved[0]['chapters'][0]['number'],4)
        mod.check_existing_chapters=lambda _:[4]
        self.assertEqual(mod.scrape_one('https://novelfire.net/n',4)['status'],'already_exists')
        self.assertEqual(len(saved),1)

    def test_rejects_unsafe_source(self):
        mod=load()
        mod.resolve_site=lambda _:{'domains':['novelfire.net'],'status':'active'}
        with self.assertRaises(ValueError):
            mod.scrape_one('https://novelfire.net.attacker.test/n',1)


if __name__=='__main__':
    unittest.main()
