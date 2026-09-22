# -*- coding: utf-8 -*-
import sys, re, json
sys.stdout.reconfigure(encoding='utf-8')
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routes.core import API_KEYS_FILE
with open(API_KEYS_FILE, 'r', encoding='utf-8') as f:
    for line in f:
        if line.startswith('openaiKey='):
            api_key = line.strip().split('=', 1)[1]

path = r'D:\test\九皇子成天装咸鱼挖地道，只想攒钱跑路远走高飞，殊不知他爹魏皇帝能听见心声，全程看他演戏没戳破 [BV1iZb36PE3o]_ocr.srt'
with open(path, 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

blocks = re.split(r'\n\s*\n', text.strip())
lines = []
for b in blocks[:100]:
    parts = [p.strip() for p in b.strip().split('\n') if p.strip()]
    if len(parts) >= 3:
        lines.append(f"{parts[0]}|{' '.join(parts[2:])}")

input_txt = "\n".join(lines)

import openai
client = openai.OpenAI(
    api_key=api_key,
    base_url='https://openrouter.ai/api/v1',
    default_headers={"HTTP-Referer": "https://novacut.app", "X-Title": "NovaCut AI"}
)

resp = client.chat.completions.create(
    model='qwen/qwen3.7-flash',
    messages=[
        {"role": "system", "content": "Bạn là công cụ dịch phụ đề chuyên nghiệp sang tiếng Việt.\nInput dạng: ID|text\nOutput bắt buộc: ID|text dịch\nKhông bỏ sót dòng nào. Mỗi dòng input có đúng 1 dòng output."},
        {"role": "user", "content": f"[TRANSLATE]\n{input_txt}"}
    ],
    temperature=0.0,
    extra_body={"reasoning": {"effort": "none"}}
)

out = resp.choices[0].message.content
print("Total response lines:", len(out.split('\n')))
print("Finish reason:", resp.choices[0].finish_reason)
print("Tokens:", resp.usage.completion_tokens)
print("First 10 lines of output:")
for l in out.split('\n')[:10]:
    print(" ", l)
print("Last 10 lines of output:")
for l in out.split('\n')[-10:]:
    print(" ", l)
