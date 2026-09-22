# -*- coding: utf-8 -*-
import sys, re, json
sys.stdout.reconfigure(encoding='utf-8')
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web_app import app
from routes.subtitles import clean_sub_translation

path = r'D:\test\九皇子成天装咸鱼挖地道，只想攒钱跑路远走高飞，殊不知他爹魏皇帝能听见心声，全程看他演戏没戳破 [BV1iZb36PE3o]_ocr.srt'
with open(path, 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

blocks = re.split(r'\n\s*\n', text.strip())
subtitles = []
for b in blocks[:100]:
    lines = [l.strip() for l in b.strip().split('\n') if l.strip()]
    if len(lines) >= 3:
        subtitles.append({'id': lines[0], 'time': lines[1], 'text': ' '.join(lines[2:])})

client = app.test_client()
res = client.post('/api/translate_subtitles', json={
    'mode': 'ai',
    'subtitles': subtitles,
    'source_lang': 'zh',
    'target_lang': 'vi'
})
data = res.get_json()
missing = []
for s in data['subtitles']:
    if not s.get('translation'):
        missing.append(s)

print(f"Total missing: {len(missing)}")
for m in missing[:10]:
    print(f"  Missing ID: {m['id']} - text: {m['text']}")
