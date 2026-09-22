import requests
import re
import json

r = requests.get('https://ai33.pro/assets/index-CIXNlLt-.js')
text = r.text

# Find translation objects or strings containing 'credit' or 'tín dụng' or 'ký tự'
matches = re.findall(r'("(?:[^"\\]|\\.)*credits?(?:[^"\\]|\\.)*")', text, re.I)
print(f"Found {len(matches)} string matches")

unique_matches = set()
for m in matches:
    if len(m) < 150:
        unique_matches.add(m)

with open('credit_strings.txt', 'w', encoding='utf-8') as f:
    for u in sorted(unique_matches):
        f.write(u + '\n')

print("Wrote to credit_strings.txt")
