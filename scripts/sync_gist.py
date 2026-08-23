import os
import sys
import json
import requests

TOKEN = "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"
CONFIG_FILE = os.path.join(os.path.dirname(__file__), '..', 'gist_config.json')
TEMPLATE_FILE = os.path.join(os.path.dirname(__file__), '..', 'google_apps_script_template.js')

def sync_to_gist():
    if not os.path.exists(TEMPLATE_FILE):
        print(f"Error: {TEMPLATE_FILE} not found!")
        return False

    with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
        code_content = f.read()

    headers = {
        'Authorization': f'Bearer {TOKEN}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28'
    }

    # 1. Check existing config
    gist_id = None
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
                gist_id = cfg.get('gist_id')
        except Exception:
            pass

    # 2. Check if gist exists on GitHub if not in config
    if not gist_id:
        res = requests.get('https://api.github.com/gists', headers=headers, timeout=10)
        if res.status_code == 200:
            gists = res.json()
            for g in gists:
                if 'ams_license_engine.js' in g.get('files', {}):
                    gist_id = g['id']
                    break

    # 3. Create or Update Gist
    filename = 'ams_license_engine.js'
    payload = {
        'description': 'AI Movie Shorts - License & Payment Cloud Engine',
        'files': {
            filename: {
                'content': code_content
            }
        }
    }

    if gist_id:
        print(f"Updating existing Gist: {gist_id}...")
        res = requests.patch(f'https://api.github.com/gists/{gist_id}', headers=headers, json=payload, timeout=15)
    else:
        print("Creating new Secret Gist...")
        payload['public'] = False
        res = requests.post('https://api.github.com/gists', headers=headers, json=payload, timeout=15)

    if res.status_code in [200, 201]:
        data = res.json()
        gist_id = data['id']
        raw_url = data['files'][filename]['raw_url']
        
        # Strip commit hash for permanent latest raw URL
        # e.g., https://gist.githubusercontent.com/user/gist_id/raw/hash/file.js -> https://gist.githubusercontent.com/user/gist_id/raw/file.js
        parts = raw_url.split('/raw/')
        if len(parts) == 2:
            subparts = parts[1].split('/', 1)
            if len(subparts) == 2:
                permanent_raw_url = f"{parts[0]}/raw/{subparts[1]}"
            else:
                permanent_raw_url = raw_url
        else:
            permanent_raw_url = raw_url

        config_data = {
            'github_user': data.get('owner', {}).get('login', ''),
            'gist_id': gist_id,
            'filename': filename,
            'html_url': data.get('html_url', ''),
            'permanent_raw_url': permanent_raw_url,
            'token': TOKEN
        }

        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)

        print("SUCCESS")
        print(f"GIST_ID: {gist_id}")
        print(f"HTML_URL: {data.get('html_url')}")
        print(f"PERMANENT_RAW_URL: {permanent_raw_url}")
        return True
    else:
        print(f"Failed to sync Gist: {res.status_code} - {res.text}")
        return False

if __name__ == '__main__':
    sync_to_gist()
