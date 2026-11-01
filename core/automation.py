# -*- coding: utf-8 -*-
"""One chapter per request: bounded scraper step for ephemeral Vercel Functions.

Preserves legacy API_SECRET and C-flow import endpoint. No daemon threads.
"""
from urllib.parse import urlsplit
from flask import request, jsonify

from core.config import API_SECRET, AUTOMATION_INGEST_SECRET
from core.registry import resolve_site
from core.backend import automation_request


def allowed_source_url(source_url, site):
    if not isinstance(source_url, str) or not source_url or len(source_url) > 2048:
        return False
    try:
        parsed = urlsplit(source_url)
        hostname = (parsed.hostname or '').lower().rstrip('.')
        if parsed.scheme not in ('https', 'http') or not hostname or parsed.username or parsed.password or parsed.port:
            return False
        for domain in site.get('domains', []):
            registered = str(domain).lower().strip('.').split('/')[0]
            if hostname == registered or hostname.endswith('.' + registered):
                return True
    except (ValueError, AttributeError):
        pass
    return False


def scrape_one(source_url, chapter_number, admin_email='system@auto', job_id=None):
    site = resolve_site(source_url)
    if not site or not allowed_source_url(source_url, site):
        raise ValueError('Unsupported or unsafe source domain')
    # Check the durable receipt and actual storage before any source fetch.
    identity = {'sourceUrl': source_url, 'chapterNumber': chapter_number}
    existing = automation_request('check', identity)
    if existing.get('persisted') is True:
        return {'ok': True, 'status': 'already_exists', 'chapterNumber': chapter_number,
                'receiptId': existing['receiptId']}
    if existing.get('receiptId'):
        recovered = automation_request('recover', identity)
        verified = automation_request('check', identity)
        if recovered.get('persisted') is not True or verified.get('persisted') is not True:
            raise RuntimeError('Stored original reconciliation incomplete')
        return {'ok': True, 'status': 'saved', 'chapterNumber': chapter_number,
                'receiptId': recovered['receiptId']}
    if site.get('status') != 'active':
        raise ValueError('Source is not active')
    fetch_meta, fetch_list, fetch_content = (
        site.get('fetch_metadata'), site.get('fetch_chapters'), site.get('fetch_content'))
    if not all(callable(fn) for fn in (fetch_meta, fetch_list, fetch_content)):
        raise ValueError('Source does not support per-chapter scraping')

    catalog_identity = {**identity, 'jobId': job_id or 'legacy'}
    cached = automation_request('catalog/check', catalog_identity)
    if cached.get('ready') is True:
        metadata, chapter = cached.get('metadata'), cached.get('chapter')
    else:
        metadata = fetch_meta(source_url)
        if not isinstance(metadata, dict) or not metadata.get('title'):
            raise ValueError('Source metadata unavailable')
        catalog = fetch_list(source_url)
        if not isinstance(catalog, (tuple, list)) or not catalog:
            raise ValueError('Source chapter catalog unavailable')
        valid = [c for c in catalog if isinstance(c, dict) and type(c.get('number')) is int
                 and c['number'] > 0 and allowed_source_url(c.get('url'), site)]
        if len(valid) != len(catalog) or len({c['number'] for c in valid}) != len(valid):
            raise ValueError('Unsafe or ambiguous source catalog')
        for offset in range(0, len(valid), 100):
            saved_catalog = automation_request('catalog/save', {**catalog_identity,
                'metadata': metadata, 'chapters': valid[offset:offset + 100], 'total': len(valid)})
        if saved_catalog.get('ready') is not True:
            raise RuntimeError('Source catalog persistence incomplete')
        chapter = next((c for c in valid if c['number'] == chapter_number), None)
    if not isinstance(chapter, dict):
        raise ValueError('Chapter number not found in source catalog')
    if not isinstance(metadata, dict) or not metadata.get('title'):
        raise RuntimeError('Invalid stored catalog')
    chapter_url = chapter.get('url')
    if not allowed_source_url(chapter_url, site):
        raise ValueError('Unsafe chapter domain')

    content = fetch_content(chapter_url)
    if not isinstance(content, str) or not content.strip():
        raise ValueError('No chapter content available')

    result = automation_request('import', {'sourceUrl': source_url, 'jobId': job_id, 'novelData': metadata,
        'chapter': {'number': chapter_number,
                    'title': str(chapter.get('title') or f'Chapter {chapter_number}'),
                    'content': content}})
    if result.get('persisted') is not True or result.get('chapterNumber') != chapter_number:
        raise RuntimeError('C-flow did not confirm chapter persistence')
    # A separate read request proves retry/idempotency visibility.
    verified = automation_request('check', identity)
    if verified.get('persisted') is not True or verified.get('receiptId') != result.get('receiptId'):
        raise RuntimeError('C-flow chapter readback failed')
    return {'ok': True, 'status': 'saved', 'chapterNumber': chapter_number,
            'receiptId': result['receiptId']}



def register_automation_routes(app):
    @app.route('/automation/health', methods=['GET'])
    def durable_health():
        import os
        return jsonify({'protocol': 2, 'revision': os.environ.get('VERCEL_GIT_COMMIT_SHA', 'local'),
                        'ingestConfigured': bool(AUTOMATION_INGEST_SECRET)})

    @app.route('/automation/scrape-chapter', methods=['POST'])
    def scrape_chapter_step():
        # Keep the exact existing API_SECRET; the feature never rotates it.
        if request.headers.get('Authorization') != API_SECRET:
            return jsonify({'error': 'Unauthorized'}), 401
        if not AUTOMATION_INGEST_SECRET:
            return jsonify({'error': 'Durable ingest is not configured'}), 503
        import hmac
        if not hmac.compare_digest(request.headers.get('x-automation-ingest-secret', ''), AUTOMATION_INGEST_SECRET):
            return jsonify({'error': 'Unauthorized'}), 403
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({'error': 'JSON body required'}), 400
        chapter_number = body.get('chapterNumber')
        if type(chapter_number) is not int or not 1 <= chapter_number <= 1_000_000:
            return jsonify({'error': 'Invalid chapterNumber'}), 400
        try:
            result = scrape_one(body.get('sourceUrl'), chapter_number,
                                str(body.get('adminEmail') or 'system@auto')[:254], body.get('jobId'))
            return jsonify(result), 200
        except ValueError as e:
            return jsonify({'error': str(e)}), 422
        except Exception as e:
            app.logger.exception('One chapter scrape failed')
            return jsonify({'error': type(e).__name__}), 502
