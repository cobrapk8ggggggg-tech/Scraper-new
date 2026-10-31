# -*- coding: utf-8 -*-
"""
==========================================
📚 سجل المواقع (Site Registry)
==========================================
هنا تُسجَّل جميع المواقع المدعومة من ملفات اللغات:
sites/arabic.py - sites/english.py - sites/chinese.py - sites/korean.py

كل موقع يحتوي على:
- domains: أنماط النطاقات للتعرف على الرابط
- language: اللغة (arabic/english/chinese/korean)
- fetch_metadata: جلب بيانات الرواية
- fetch_chapters: جلب قائمة الفصول
- fetch_content: سحب محتوى فصل
- worker: العامل الكامل (اختياري - يستخدم generic_worker إن لم يحدد)
- status: active / blocked / dead (للتوثيق فقط)
"""

SITE_REGISTRY = []


def register_site(domain_patterns, name, language, fetch_metadata, fetch_chapters=None,
                  fetch_content=None, worker=None, status='active', notes=''):
    """تسجيل موقع جديد في السجل العام"""
    site = {
        'domains': [d.lower() for d in domain_patterns],
        'name': name,
        'language': language,
        'fetch_metadata': fetch_metadata,
        'fetch_chapters': fetch_chapters,
        'fetch_content': fetch_content,
        'worker': worker,
        'status': status,
        'notes': notes,
    }
    SITE_REGISTRY.append(site)
    return site


def resolve_site(url):
    """إيجاد الموقع المناسب لأي رابط (أول تطابق بالأولوية للتسجيل)"""
    url = (url or '').lower()
    for site in SITE_REGISTRY:
        for domain in site['domains']:
            if domain in url:
                return site
    return None


def get_registry():
    """إرجاع نسخة مبسطة من السجل للعرض (للواجهة والتقارير)"""
    return [
        {
            'name': s['name'],
            'domains': s['domains'],
            'language': s['language'],
            'status': s['status'],
            'notes': s['notes'],
        }
        for s in SITE_REGISTRY
    ]
