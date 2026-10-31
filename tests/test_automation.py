"""Isolated unit tests: no external requests, accounts or DB writes."""
import importlib.util
import sys
import types
import unittest
from pathlib import Path


def load():
    originals = sys.modules.copy()
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
    backend.automation_request=lambda *args:{'ok':True,'persisted':False}
    for m in (config,registry,backend):
        sys.modules[m.__name__]=m
    filename=Path(__file__).resolve().parents[1]/'core/automation.py'
    spec=importlib.util.spec_from_file_location('automation_test_target',filename)
    module=importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        for name in ('flask', 'core', 'core.config', 'core.registry', 'core.backend'):
            if name in originals: sys.modules[name] = originals[name]
            else: sys.modules.pop(name, None)
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
        def backend(path, payload):
            if path == 'import':
                saved.append(payload)
            return {'ok':True, 'persisted':bool(saved), 'receiptId':'receipt', 'chapterNumber':4}
        mod.automation_request=backend
        response=mod.scrape_one('https://novelfire.net/n',4)
        self.assertEqual(response['status'],'saved')
        self.assertEqual(saved[0]['chapter']['number'],4)
        self.assertEqual(mod.scrape_one('https://novelfire.net/n',4)['status'],'already_exists')
        self.assertEqual(len(saved),1)

    def test_failed_readback_never_acknowledges_success(self):
        mod=load()
        mod.resolve_site=lambda _:{'domains':['novelfire.net'],'status':'active',
            'fetch_metadata':lambda _:{'title':'Sample'},
            'fetch_chapters':lambda _:[{'number':1,'url':'https://novelfire.net/1'}],
            'fetch_content':lambda _:'Text'}
        mod.automation_request=lambda path,_:({'ok':True,'persisted':True,'receiptId':'r','chapterNumber':1}
            if path=='import' else {'ok':True,'persisted':False})
        with self.assertRaises(RuntimeError):
            mod.scrape_one('https://novelfire.net/n',1)

    def test_unavailable_verification_does_not_fetch_or_save(self):
        mod=load()
        def forbidden(_):
            self.fail('Source must not be fetched when verification is unavailable')
        mod.resolve_site=lambda _:{'domains':['novelfire.net'],'status':'active',
            'fetch_metadata':forbidden,'fetch_chapters':forbidden,'fetch_content':forbidden}
        def outage(*args):
            raise RuntimeError('database offline')
        mod.automation_request=outage
        with self.assertRaises(RuntimeError): mod.scrape_one('https://novelfire.net/n',1)

    def test_catalog_cannot_send_content_fetch_to_another_domain(self):
        mod=load()
        mod.resolve_site=lambda _:{'domains':['novelfire.net'],'status':'active',
            'fetch_metadata':lambda _:{'title':'Sample'},
            'fetch_chapters':lambda _:[{'number':1,'url':'http://127.0.0.1/secret'}],
            'fetch_content':lambda _:self.fail('unsafe chapter URL fetched')}
        with self.assertRaises(ValueError): mod.scrape_one('https://novelfire.net/n',1)

    def test_rejects_unsafe_source(self):
        mod=load()
        mod.resolve_site=lambda _:{'domains':['novelfire.net'],'status':'active'}
        with self.assertRaises(ValueError):
            mod.scrape_one('https://novelfire.net.attacker.test/n',1)


if __name__=='__main__':
    unittest.main()
