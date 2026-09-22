# -*- coding: utf-8 -*-
import sys, re, json, time
sys.stdout.reconfigure(encoding='utf-8')
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import routes.subtitles
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

print("--- Test 1: Mặc định (không max_tokens, không reasoning disable) ---")
t0 = time.time()
resp1 = client.chat.completions.create(
    model='qwen/qwen3.7-flash',
    messages=[{"role": "system", "content": sys_msg}, {"role": "user", "content": prompt}],
    temperature=0.0
)
dt1 = time.time() - t0
print(f"Time: {dt1:.2f}s | Output tokens: {resp1.usage.completion_tokens}")

print("\n--- Test 2: extra_body reasoning max_tokens=0 ---")
t0 = time.time()
resp2 = client.chat.completions.create(
    model='qwen/qwen3.7-flash',
    messages=[{"role": "system", "content": sys_msg}, {"role": "user", "content": prompt}],
    temperature=0.0,
    extra_body={"reasoning": {"max_tokens": 0}}
)
dt2 = time.time() - t0
print(f"Time: {dt2:.2f}s | Output tokens: {resp2.usage.completion_tokens}")
print("Output text:")
print(resp2.choices[0].message.content)
