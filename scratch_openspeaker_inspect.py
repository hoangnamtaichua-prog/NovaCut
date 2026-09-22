import requests
import json

api_key = 'sk_30y1l9o2ub5o0af0wkbrmaj5qf1biqprd22q3gl5hu3gkv7l'
headers = {'xi-api-key': api_key}

try:
    r = requests.get('https://api.ai33.pro/v1/models', headers=headers, timeout=10)
    models = r.json()
    print("=== MODELS & MULTIPLIERS ===")
    for m in models:
        mid = m.get('model_id')
        name = m.get('name')
        rates = m.get('model_rates', {})
        char_mult = rates.get('character_cost_multiplier', 1)
        factor = m.get('token_cost_factor', 1)
        langs = [l.get('language_id') for l in m.get('languages', [])]
        has_vi = 'vi' in langs
        print(f"ID: {mid:<26} | Name: {name:<26} | Char Mult: {char_mult:<4} | Cost Factor: {factor:<3} | Has 'vi': {has_vi}")
except Exception as e:
    print("Error models:", e)

try:
    r2 = requests.get('https://api.ai33.pro/v1/user/subscription', headers=headers, timeout=10)
    print("=== SUBSCRIPTION ===")
    print(r2.text)
except Exception as e:
    print("Error sub:", e)

try:
    r3 = requests.get('https://api.ai33.pro/v1/credits', headers=headers, timeout=10)
    print("=== CREDITS ===")
    print(r3.text)
except Exception as e:
    print("Error credits:", e)
