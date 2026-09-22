with open('ai33_pricing_dump.txt', 'r', encoding='utf-8') as f:
    content = f.read()

import re
# Find anything mentioning credit cost or deduction for TTS
for block in content.split('---'):
    if any(k in block.lower() for k in ['tts', 'speech', 'character', 'cost', 'pricing', 'multiplier', 'plans']):
        print(block.strip()[:400])
        print("="*50)
