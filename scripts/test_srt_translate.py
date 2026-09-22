# -*- coding: utf-8 -*-
import sys, re, json
sys.stdout.reconfigure(encoding='utf-8')

path = r'D:\test\九皇子成天装咸鱼挖地道，只想攒钱跑路远走高飞，殊不知他爹魏皇帝能听见心声，全程看他演戏没戳破 [BV1iZb36PE3o]_ocr.srt'

with open(path, 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

blocks = re.split(r'\n\s*\n', text.strip())
subtitles = []
for b in blocks[:5]:
    lines = [l.strip() for l in b.strip().split('\n') if l.strip()]
    if len(lines) >= 3:
        sid = lines[0]
        t = lines[1]
        txt = ' '.join(lines[2:])
        subtitles.append({'id': sid, 'time': t, 'text': txt})

print(f"Test with {len(subtitles)} subs:")
for s in subtitles:
    print(f"  {s['id']}: {s['text']}")

import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from web_app import app
client = app.test_client()
print("Calling Flask test_client /api/translate_subtitles...")
res = client.post('/api/translate_subtitles', json={
    'mode': 'ai',
    'subtitles': subtitles,
    'source_lang': 'zh',
    'target_lang': 'vi'
})
print(f"Status code: {res.status_code}")
data = res.get_json()
if data and 'subtitles' in data:
    for s in data['subtitles']:
        print(f"  Result {s['id']}: {s.get('translation')}")
    print(f"Usage: {data.get('usage')}")
    print(f"Stats: {data.get('stats')}")
else:
    print(f"Data error: {data}")
