# -*- coding: utf-8 -*-
"""One chapter per request: bounded scraper step for ephemeral Vercel Functions.

Preserves legacy API_SECRET and C-flow import endpoint. No daemon threads.
"""
from urllib.parse import urlsplit
from flask import request, jsonify

from core.config import API_SECRET
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


def scrape_one(source_url, chapter_number, admin_email='system@auto'):
    site = resolve_site(source_url)
    if not site or not allowed_source_url(source_url, site):
        raise ValueError('Unsupported or unsafe source domain')
    if site.get('status') != 'active':
        raise ValueError('Source is not active')
    fetch_meta, fetch_list, fetch_content = (
        site.get('fetch_metadata'), site.get('fetch_chapters'), site.get('fetch_content'))
    if not all(callable(fn) for fn in (fetch_meta, fetch_list, fetch_content)):
        raise ValueError('Source does not support per-chapter scraping')

    # Check the durable receipt and actual storage before any source fetch.
    identity = {'sourceUrl': source_url, 'chapterNumber': chapter_number}
    existing = automation_request('check', identity)
    if existing.get('persisted') is True:
        return {'ok': True, 'status': 'already_exists', 'chapterNumber': chapter_number,
                'receiptId': existing['receiptId']}
    metadata = fetch_meta(source_url)
    if not isinstance(metadata, dict) or not metadata.get('title'):
        raise ValueError('Source metadata unavailable')
    catalog = fetch_list(source_url)
    if not isinstance(catalog, (tuple, list)):
        raise ValueError('Source chapter catalog unavailable')
    chapter = next((c for c in catalog if isinstance(c, dict) and c.get('number') == chapter_number), None)
    if chapter is None:
        raise ValueError('Chapter number not found in source catalog')
    chapter_url = chapter.get('url')
    if not allowed_source_url(chapter_url, site):
        raise ValueError('Unsafe chapter domain')

    content = fetch_content(chapter_url)
    if not isinstance(content, str) or not content.strip():
        raise ValueError('No chapter content available')

    result = automation_request('import', {'sourceUrl': source_url, 'novelData': metadata,
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
    @app.route('/automation/scrape-chapter', methods=['POST'])
    def scrape_chapter_step():
        # Keep the exact existing API_SECRET; the feature never rotates it.
        if request.headers.get('Authorization') != API_SECRET:
            return jsonify({'error': 'Unauthorized'}), 401
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({'error': 'JSON body required'}), 400
        chapter_number = body.get('chapterNumber')
        if type(chapter_number) is not int or not 1 <= chapter_number <= 1_000_000:
            return jsonify({'error': 'Invalid chapterNumber'}), 400
        try:
            result = scrape_one(body.get('sourceUrl'), chapter_number,
                                str(body.get('adminEmail') or 'system@auto')[:254])
            return jsonify(result), 200
        except ValueError as e:
            return jsonify({'error': str(e)}), 422
        except Exception as e:
            app.logger.exception('One chapter scrape failed')
            return jsonify({'error': type(e).__name__}), 502
