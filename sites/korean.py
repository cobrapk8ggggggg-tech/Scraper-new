# -*- coding: utf-8 -*-
"""
==========================================
🟨 المواقع الكورية (Korean Novel Sites)
==========================================
المواقع المسجلة في هذا الملف:
1. Agitoon - agit664.xyz (+ دوال بديلة) ✅ جديد (الموقع يدور بين الدومينات)

ملاحظة مهمة: موقع Agitoon يغيّر نطاقه باستمرار (agit501/601/664...)
تم تنفيذ آلية اكتشاف الدومين التلقائية نفسها المستخدمة في إضافة
LNReader الرسمية: نطلب الدومين الأساسي ونتبع التحويل.
"""

import re
import time
import requests
from urllib.parse import urljoin

from core.registry import register_site
from core.utils import (
    http_get, parse_html, get_headers, get_base_url, fix_image_url,
    extract_chapter_number, clean_text,
    UA_MOBILE,
    generic_worker,
)

# الدومينات المعروفة لـ Agitoon بالترتيب (تدور باستمرار)
AGITOON_DOMAINS = [
    'agit664.xyz', 'agit501.xyz', 'agit601.xyz',
    'agit430.xyz', 'agitoon.xyz', 'agitoon.com',
]

KR_HEADERS_LANG = 'ko-KR,ko;q=0.9,en;q=0.7'

# تخزين الدومين الفعال بعد الاكتشاف
_agitoon_active_base = None


def _is_parked(url):
    """فحص إن كان الدومين موقفاً (ww38. / ww25. / صفحة فارغة)"""
    try:
        parsed = urlsplit_base(url)
        host = parsed.netloc.lower()
        return re.match(r'^ww\d+\.', host) is not None
    except Exception:
        return False


def urlsplit_base(url):
    from urllib.parse import urlparse
    return urlparse(url)


def resolve_agitoon_base(prefer_domain=None):
    """
    اكتشاف الدومين الفعال لـ Agitoon:
    يجرّب الدومينات بالترتيب ويتابع التحويلات (نفس منطق checkUrl في LNReader)
    """
    global _agitoon_active_base
    if _agitoon_active_base and not prefer_domain:
        return _agitoon_active_base

    candidates = ([prefer_domain] if prefer_domain else []) + AGITOON_DOMAINS

    for domain in candidates:
        if not domain:
            continue
        base = f"https://{domain}"
        try:
            r = requests.get(
                base,
                headers=get_headers(ua=UA_MOBILE, lang=KR_HEADERS_LANG),
                timeout=15,
                allow_redirects=True,
            )
            final_url = r.url
            # تجاهل الدومينات الموقوفة (تحويل إلى wwNN.)
            if re.match(r'^ww\d+\.', urlsplit_base(final_url).netloc.lower()):
                print(f"Agitoon: {domain} is parked -> trying next")
                continue
            if r.status_code == 200:
                _agitoon_active_base = final_url.rstrip('/')
                print(f"✅ Agitoon active domain: {_agitoon_active_base}")
                return _agitoon_active_base
        except Exception as e:
            print(f"Agitoon: {domain} failed: {type(e).__name__}")
            continue

    # لم نجد دوماً فعالاً - نعيد الافتراضي
    _agitoon_active_base = 'https://agit664.xyz'
    return _agitoon_active_base


def _agitoon_base_from_url(url):
    """إذا كان الرابط نفسه على دومين Agitoon نستخدمه مباشرة (مع حل التحويل)"""
    parsed = urlsplit_base(url)
    host = parsed.netloc.lower()
    if host and not re.match(r'^ww\d+\.', host):
        return f"{parsed.scheme}://{parsed.netloc}"
    return resolve_agitoon_base()


def fetch_metadata_agitoon(url):
    try:
        base = _agitoon_base_from_url(url)

        # معرف الرواية من الرابط: /novel/list/{id} أو مباشرة {id}
        m = re.search(r'/novel/(?:list/)?(\d+)', url)
        if not m:
            print("Agitoon: cannot extract novel id from url")
            return None
        novel_id = m.group(1)

        novel_url = f"{base}/novel/list/{novel_id}"
        r = http_get(novel_url, ua=UA_MOBILE, lang=KR_HEADERS_LANG, timeout=20)
        if r is None or r.status_code != 200:
            return None
        soup = parse_html(r)

        title_tag = soup.select_one('h5.pt-2') or soup.find('h5') or soup.find('h1')
        title = title_tag.get_text(strip=True) if title_tag else "Unknown Title"

        cover = ""
        img_tag = soup.select_one('div.col-5.pr-0.pl-0 img')
        if img_tag:
            cover = img_tag.get('src') or ""
        cover = fix_image_url(cover, base_url=base)

        summary_div = soup.select_one('.pt-1.mt-1.pb-1.mb-1')
        description = summary_div.get_text('\n', strip=True) if summary_div else ""

        author = ""
        author_el = soup.select_one('.post-item-list-cate-v')
        if author_el:
            author = author_el.get_text(strip=True).split(' : ')[-1].strip()

        tags = []
        for span in soup.select('.col-7 > .post-item-list-cate > span'):
            txt = span.get_text(strip=True)
            if txt:
                tags.append(txt)
        category = tags[0] if tags else "عام"

        status = "مستمرة"
        page_text = soup.get_text()[:6000]
        if '완결' in page_text or '完結' in page_text:
            status = "مكتملة"

        return {
            'title': title, 'description': description, 'cover': cover,
            'author': author, 'status': status, 'category': category, 'tags': tags,
            'novel_id': novel_id,
            'sourceUrl': novel_url,
            'lastUpdate': None
        }
    except Exception as e:
        print(f"Error Agitoon metadata: {e}")
        return None


def fetch_chapter_list_agitoon(url):
    """قائمة الفصول عبر POST /novel/list.update.php (JSON)"""
    chapters = []
    try:
        base = _agitoon_base_from_url(url)

        m = re.search(r'/novel/(?:list/)?(\d+)', url)
        if not m:
            return []
        novel_id = m.group(1)

        resp = requests.post(
            f"{base}/novel/list.update.php",
            headers={
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'User-Agent': UA_MOBILE,
                'Referer': f"{base}/novel/list/{novel_id}",
                'X-Requested-With': 'XMLHttpRequest',
            },
            data={
                'mode': 'get_data_novel_list_c',
                'wr_id_p': novel_id,
                'page_no': '1',
                'cnt_list': '10000',
                'order_type': 'Asc',
            },
            timeout=25,
        )
        if resp.status_code != 200:
            print(f"Agitoon list.update failed: HTTP {resp.status_code}")
            return []

        try:
            data = resp.json()
        except Exception:
            print("Agitoon: invalid JSON response")
            return []

        index = 0
        for ch in (data.get('list') or []):
            wr_id = str(ch.get('wr_id', '')).strip()
            subject = ch.get('wr_subject', '') or f"Chapter {index + 1}"
            if not wr_id:
                continue
            index += 1
            # رقم الفصل من الموضوع إن وجد وإلا الترتيب
            number = extract_chapter_number(subject, wr_id) or index
            chapters.append({
                'number': number,
                'url': f"{base}/novel/view/{wr_id}/2",
                'title': subject,
            })

        chapters.sort(key=lambda x: x['number'])
        print(f"✅ Agitoon chapters found: {len(chapters)}")
        return chapters
    except Exception as e:
        print(f"Error Agitoon chapter list: {e}")
        return chapters


def scrape_chapter_agitoon(url):
    try:
        r = http_get(url, ua=UA_MOBILE, lang=KR_HEADERS_LANG, timeout=20)
        if r is None or r.status_code != 200:
            return None
        soup = parse_html(r)

        content_div = soup.select_one('#id_wr_content')
        if not content_div:
            return None

        # إزالة نافذة البوب أب
        text = content_div.get_text(separator='\n\n', strip=True)
        text = text.replace('팝업메뉴는 빈공간을 더치하거나 스크룰시 사라집니다', '')
        text = clean_text(text)

        if len(text.strip()) < 30:
            return None
        return text
    except Exception:
        return None


def worker_agitoon(url, admin_email, metadata):
    generic_worker(url, admin_email, metadata, fetch_chapter_list_agitoon, scrape_chapter_agitoon, delay=1.5)


# ==========================================
# 📋 تسجيل المواقع الكورية
# ==========================================

register_site(
    domain_patterns=AGITOON_DOMAINS,
    name='Agitoon (아기툰)',
    language='korean',
    fetch_metadata=fetch_metadata_agitoon,
    fetch_chapters=fetch_chapter_list_agitoon,
    fetch_content=scrape_chapter_agitoon,
    worker=worker_agitoon,
    status='active',
    notes='جديد (من LNReader)! موقع روايات كورية مترجمة آلياً. الدومين يدور باستمرار '
          '(agit501/601/664...) - تم تنفيذ اكتشاف الدومين التلقائي.'
)
