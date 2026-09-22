import requests

r = requests.get('https://ai33.pro/assets/index-CIXNlLt-.js')
text = r.text

idx = 1363615
start = max(0, idx - 4000)
end = min(len(text), idx + 2000)

with open('tts_ui_component.txt', 'w', encoding='utf-8') as out:
    out.write(text[start:end])

print("Written tts_ui_component.txt")
