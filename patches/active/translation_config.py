# -*- coding: utf-8 -*-
"""
Cấu hình trung tâm cho dịch thuật AI NovaCut
Central Configuration for Subtitle Translation Pipeline
"""

DEFAULT_TRANSLATION_MODEL = "qwen/qwen3.8-flash"

DEFAULT_TRANSLATION_CONFIG = {
    "model": "qwen/qwen3.8-flash",
    "chunkSize": 80,
    "concurrency": 3,
    "maxRetries": 3,
    "requestTimeout": 60,  # 60 giây (tránh treo ngâm)
    "contextLines": 6,
    "temperature": 0.0,
    "providerRouting": "throughput"
}

def get_default_translation_model():
    return DEFAULT_TRANSLATION_MODEL

def get_translation_config():
    return DEFAULT_TRANSLATION_CONFIG.copy()
