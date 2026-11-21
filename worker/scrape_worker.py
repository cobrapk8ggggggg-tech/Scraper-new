"""Opt-in long scraper process. Claims and checkpoints use C-flow's shared MongoDB protocol."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import signal
import threading
import time
from urllib.parse import urlsplit
import requests

STOP = threading.Event()

def request_stop(*_):
    STOP.set()


def run_step(base, secret, claim, scrape, session=None):
    session = session or requests.Session()
    headers = {'x-automation-secret': secret}
    heartbeat_stop = threading.Event()
    lost = threading.Event()
    def heartbeat():
        while not heartbeat_stop.wait(20):
            try:
                response = session.post(base + '/api/automation/worker/scrape/heartbeat',
                                        json=claim, headers=headers, timeout=15)
                if response.status_code != 200 or response.json().get('status') != 'running':
                    lost.set()
            except requests.RequestException:
                lost.set()
    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        result = scrape(claim['sourceUrl'], claim['chapterNumber'], job_id=claim['jobId'])
        if not lost.is_set():
            response = session.post(base + '/api/automation/worker/scrape/complete',
                                    json={**claim, 'receiptId': result['receiptId']}, headers=headers, timeout=30)
            response.raise_for_status()
    except Exception:
        if not lost.is_set():
            try:
                session.post(base + '/api/automation/worker/scrape/fail', json=claim, headers=headers, timeout=15)
            except requests.RequestException:
                pass
        # Never log upstream exceptions, credentials or response bodies.
        return False
    finally:
        heartbeat_stop.set()
        thread.join(timeout=16)
    return True


def main():
    if os.environ.get('ZEUS_DAEMON_ENABLED') != 'true':
        raise RuntimeError('Worker activation is required')
    base = os.environ.get('NODE_BACKEND_URL', '').rstrip('/')
    secret = os.environ.get('AUTOMATION_SECRET', '')
    if urlsplit(base).scheme != 'https' or not secret:
        raise RuntimeError('Private HTTPS coordinator configuration is required')
    # Import site registrations only after the activation/configuration guard.
    import sites.arabic, sites.english, sites.chinese, sites.korean
    import sites.newcn, sites.cnextra, sites.tomatomtl, sites.wtrlab, sites.faloo_xsw
    from core.automation import scrape_one
    session = requests.Session()
    deadline = time.monotonic() + 45 * 60
    while not STOP.is_set() and time.monotonic() < deadline - 300:
        response = session.post(base + '/api/automation/worker/scrape/claim',
                                json={}, headers={'x-automation-secret': secret}, timeout=15)
        response.raise_for_status()
        claim = response.json()
        if claim.get('disabled') or claim.get('idle'):
            break
        run_step(base, secret, claim, scrape_one, session)


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    try:
        main()
    except Exception:
        print('Scraper worker stopped; inspect persisted job error codes.')
        raise SystemExit(1)
