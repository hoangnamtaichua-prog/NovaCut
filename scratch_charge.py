with open('ai33_pricing_dump.txt', 'r', encoding='utf-8') as f:
    pass

import requests
import re

r = requests.get('https://ai33.pro/assets/index-CIXNlLt-.js')
text = r.text

idx = text.find('CHARGE_MULTIPLIER')
if idx != -1:
    print("Found CHARGE_MULTIPLIER at", idx)
    start = max(0, idx - 1500)
    end = min(len(text), idx + 1500)
    with open('charge_multiplier_context.txt', 'w', encoding='utf-8') as out:
        out.write(text[start:end])
    print("Saved context to charge_multiplier_context.txt")
else:
    print("Not found")
