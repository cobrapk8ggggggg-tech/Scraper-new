"""One bounded runner subprocess; output never includes credentials or upstream logs."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sites.arabic, sites.english, sites.chinese, sites.korean
import sites.newcn, sites.cnextra, sites.tomatomtl, sites.wtrlab, sites.faloo_xsw
from core.automation import scrape_one

if __name__ == '__main__':
    try:
        body = json.load(sys.stdin)
        result = scrape_one(body['sourceUrl'], body['chapterNumber'], job_id=body['jobId'])
        print('ZEUS_RESULT:' + json.dumps(result))
    except Exception:
        raise SystemExit(1)
