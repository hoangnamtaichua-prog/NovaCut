import requests
import re
import json

r = requests.get('https://ai33.pro/assets/index-CIXNlLt-.js')
text = r.text

# Find all occurrences of words like 'credit', 'pricing', 'token', 'plan', 'tier'
matches = re.findall(r'(\{[^{}]{0,300}(?:credit|plan|pricing)[^{}]{0,300}\})', text, re.IGNORECASE)

with open('ai33_pricing_dump.txt', 'w', encoding='utf-8') as f:
    f.write(f"Total length of JS: {len(text)}\n")
    for m in matches:
        f.write("MATCH: " + m + "\n---\n")

print(f"Dumped {len(matches)} matches to ai33_pricing_dump.txt")
