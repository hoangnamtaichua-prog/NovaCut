import requests
import re

r = requests.get('https://ai33.pro/assets/index-CIXNlLt-.js')
text = r.text

# Find functions or occurrences of "text-to-speech" or "characters" with credits
matches = [m.start() for m in re.finditer(r'text-to-speech', text, re.I)]
print(f"Found {len(matches)} occurrences of text-to-speech")

for idx in matches[:10]:
    start = max(0, idx - 400)
    end = min(len(text), idx + 600)
    snippet = text[start:end]
    if any(w in snippet.lower() for w in ['credit', 'cost', 'calc', 'length', 'mult']):
        print(f"--- Around {idx} ---")
        print(snippet[:500])
