import requests
import re

r = requests.get('https://ai33.pro/pricing')
scripts = re.findall(r'src=["\'](/assets/[^"\']+)["\']', r.text)
print("Scripts found:", scripts)

for s in scripts:
    js_url = 'https://ai33.pro' + s
    res = requests.get(js_url)
    text = res.text
    # look for pricing tables, plans, cost per character, etc.
    hits = re.findall(r'(\d+[\s]*(?:credits?|characters?|chars?|token)[^\n\r]{0,60})', text, re.IGNORECASE)
    if hits:
        print(f"\n--- Hits in {s} ({len(hits)}) ---")
        for h in hits[:15]:
            print("  *", h.strip())
            
    # Search for model or provider credit rules
    hits2 = re.findall(r'([^.?!;\n\r]{0,50}(?:1\s*credit|credit[s]?\s*per|credits?\s*=\s*\d+|character[s]?\s*=\s*\d+|cost_multiplier)[^.?!;\n\r]{0,50})', text, re.IGNORECASE)
    if hits2:
        print(f"\n--- Credit rules in {s} ---")
        for h in set(hits2[:15]):
            print("  >", h.strip())
