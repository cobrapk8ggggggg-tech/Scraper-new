# -*- coding: utf-8 -*-
"""
==========================================
📡 الاتصال بالخادم الرئيسي (Backend Bridge)
==========================================
دوال إرسال البيانات إلى خادم Node.js الخاص بتطبيق C:
- send_data_to_backend: إرسال بيانات رواية + فصول
- check_existing_chapters: منع تكرار الفصول الموجودة
"""

import os
from urllib.parse import urlsplit
import requests

from .config import API_SECRET, NODE_BACKEND_URL, AUTOMATION_INGEST_SECRET


def _headers():
    return {
        'Content-Type': 'application/json',
        'Authorization': API_SECRET,
        'x-api-secret': API_SECRET,
        'x-automation-ingest-secret': AUTOMATION_INGEST_SECRET,
    }


def send_data_to_backend(payload):
    """إرسال البيانات إلى الخادم الرئيسي"""
    try:
        endpoint = f"{NODE_BACKEND_URL}/api/scraper/receive"
        response = requests.post(endpoint, json=payload, headers=_headers(), timeout=60)
        if response.status_code != 200:
            return False
        try:
            return response.json().get('success') is True
        except (TypeError, ValueError, AttributeError):
            return False
    except Exception as e:
        print(f"❌ Failed to send data: {e}")
        return False


def check_existing_chapters(title):
    """التحقق من الفصول الموجودة في الباك إند لمنع التكرار"""
    try:
        endpoint = f"{NODE_BACKEND_URL}/api/scraper/check-chapters"
        response = requests.post(endpoint, json={'title': title}, headers=_headers(), timeout=30)

        if response.status_code == 200:
            data = response.json()
            if data.get('exists'):
                return data['chapters']
            return []
        return []
    except Exception as e:
        print(f"❌ Error checking existence: {e}")
        return []


def push_log(message, log_type='info'):
    """🔔 إرسال سجل مرئي إلى كونسول السكرابر في واجهة التطبيق
    (يظهر فوراً للمشرف في شاشة المراقبة) — لا يرفع استثناءات أبداً"""
    try:
        endpoint = f"{NODE_BACKEND_URL}/api/scraper/log"
        requests.post(endpoint, json={'message': message, 'type': log_type},
                      headers=_headers(), timeout=15)
    except Exception as e:
        print(f"   (log push failed: {str(e)[:60]})")


def automation_request(path, payload):
    """Strict durable API: unavailable verification must never mean 'missing'."""
    endpoint = f'{NODE_BACKEND_URL}/api/automation/{path}' if '/' in path else f'{NODE_BACKEND_URL}/api/automation/chapters/{path}'
    if not os.environ.get('NODE_BACKEND_URL') or urlsplit(NODE_BACKEND_URL).scheme != 'https':
        raise RuntimeError('Explicit isolated HTTPS backend is required')
    response = requests.post(endpoint,
                             json=payload, headers=_headers(), timeout=60)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict) or data.get('ok') is not True:
        raise RuntimeError('Backend did not verify durable persistence')
    return data
