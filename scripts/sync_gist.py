import json
import os

import requests


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(ROOT_DIR, "gist_config.json")
TEMPLATE_FILE = os.path.join(ROOT_DIR, "google_apps_script_template.js")


def get_github_token():
    """Read a GitHub token from a secure local source, never from source code."""
    for name in ("NOVACUT_GITHUB_TOKEN", "GITHUB_TOKEN", "GIST_GITHUB_TOKEN"):
        token = os.environ.get(name, "").strip()
        if token:
            return token

    token_file = os.path.join(ROOT_DIR, ".github_token")
    try:
        with open(token_file, "r", encoding="utf-8") as file:
            return file.read().strip()
    except OSError:
        return ""


def sync_to_gist():
    if not os.path.exists(TEMPLATE_FILE):
        print(f"Error: {TEMPLATE_FILE} not found!")
        return False

    token = get_github_token()
    if not token:
        print("Error: set NOVACUT_GITHUB_TOKEN, GITHUB_TOKEN, or .github_token before syncing the Gist.")
        return False

    with open(TEMPLATE_FILE, "r", encoding="utf-8") as file:
        code_content = file.read()

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    gist_id = None
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as file:
                gist_id = json.load(file).get("gist_id")
        except (OSError, ValueError):
            pass

    if not gist_id:
        response = requests.get("https://api.github.com/gists", headers=headers, timeout=10)
        if response.status_code == 200:
            for gist in response.json():
                if "ams_license_engine.js" in gist.get("files", {}):
                    gist_id = gist["id"]
                    break

    filename = "ams_license_engine.js"
    payload = {
        "description": "AI Movie Shorts - License & Payment Cloud Engine",
        "files": {filename: {"content": code_content}},
    }

    if gist_id:
        print(f"Updating existing Gist: {gist_id}...")
        response = requests.patch(
            f"https://api.github.com/gists/{gist_id}", headers=headers, json=payload, timeout=15
        )
    else:
        print("Creating new Secret Gist...")
        payload["public"] = False
        response = requests.post("https://api.github.com/gists", headers=headers, json=payload, timeout=15)

    if response.status_code not in (200, 201):
        print(f"Failed to sync Gist: {response.status_code} - {response.text}")
        return False

    data = response.json()
    gist_id = data["id"]
    raw_url = data["files"][filename]["raw_url"]
    parts = raw_url.split("/raw/", 1)
    if len(parts) == 2 and "/" in parts[1]:
        permanent_raw_url = f"{parts[0]}/raw/{parts[1].split('/', 1)[1]}"
    else:
        permanent_raw_url = raw_url

    config_data = {
        "github_user": data.get("owner", {}).get("login", ""),
        "gist_id": gist_id,
        "filename": filename,
        "html_url": data.get("html_url", ""),
        "permanent_raw_url": permanent_raw_url,
    }
    with open(CONFIG_FILE, "w", encoding="utf-8") as file:
        json.dump(config_data, file, indent=2, ensure_ascii=False)

    print("SUCCESS")
    print(f"GIST_ID: {gist_id}")
    print(f"HTML_URL: {data.get('html_url')}")
    print(f"PERMANENT_RAW_URL: {permanent_raw_url}")
    return True


if __name__ == "__main__":
    sync_to_gist()
