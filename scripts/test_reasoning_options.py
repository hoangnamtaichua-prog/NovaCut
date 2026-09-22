# -*- coding: utf-8 -*-
import sys, re, json, time
sys.stdout.reconfigure(encoding='utf-8')
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routes.core import API_KEYS_FILE

api_key = None
with open(API_KEYS_FILE, 'r', encoding='utf-8') as f:
    for line in f:
        if line.startswith('openaiKey='):
            api_key = line.strip().split('=', 1)[1]

import openai
client = openai.OpenAI(
    api_key=api_key,
    base_url='https://openrouter.ai/api/v1',
    default_headers={"HTTP-Referer": "https://novacut.app", "X-Title": "NovaCut AI"}
)

prompt = "1|陛下驾崩\n2|封棺\n3|朕还没死\n4|谁敢封棺\n5|陛下诈尸了"
sys_msg = "Bạn là công cụ dịch phụ đề chuyên nghiệp sang tiếng Việt.\nInput dạng ID|text\nOutput dạng ID|text dịch"

print("--- Test 3: reasoning: effort='none' or 'low' ---")
for effort in ['none', 'low']:
    try:
        t0 = time.time()
        resp = client.chat.completions.create(
            model='qwen/qwen3.7-flash',
            messages=[{"role": "system", "content": sys_msg}, {"role": "user", "content": prompt}],
            temperature=0.0,
            extra_body={"reasoning": {"effort": effort}}
        )
        dt = time.time() - t0
        print(f"Effort '{effort}': Time={dt:.2f}s | Tokens={resp.usage.completion_tokens}")
    except Exception as e:
        print(f"Effort '{effort}' failed: {e}")

print("--- Test 4: Provider Alibaba direct vs other models ---")
for m in ['google/gemini-2.5-flash', 'deepseek/deepseek-chat', 'meta-llama/llama-3.3-70b-instruct']:
    try:
        t0 = time.time()
        resp = client.chat.completions.create(
            model=m,
            messages=[{"role": "system", "content": sys_msg}, {"role": "user", "content": prompt}],
            temperature=0.0
        )
        dt = time.time() - t0
        print(f"Model {m}: Time={dt:.2f}s | Tokens={resp.usage.completion_tokens}")
    except Exception as e:
        print(f"Model {m} failed: {e}")
