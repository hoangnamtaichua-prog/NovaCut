import os, sys
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from web_app import app

def test_user_mp3_upload():
    client = app.test_client()
    mp3_path = os.path.join(ROOT_DIR, 'output', 'tts_open_vbee_hn_male_manhdung_full_24k-st_1787246130.mp3')
    assert os.path.exists(mp3_path), f"File not found: {mp3_path}"

    print(f"\n--- Testing upload of exact user MP3: {mp3_path} ---")
    with open(mp3_path, 'rb') as f:
        res = client.post('/api/clone_voice/upload', data={
            'audio_file': (f, 'tts_open_vbee_hn_male_manhdung_full_24k-st_1787246130.mp3')
        }, content_type='multipart/form-data')

    assert res.status_code == 200, f"Upload failed: {res.data}"
    data = res.json
    print("Response JSON:", data)
    assert data['success'] == True
    print(f"Detected Duration: {data['duration']}s (Expected ~9.57s)")
    print(f"Quality Score: {data.get('quality_score')} - Desc: {data.get('quality_desc')}")
    assert data['duration'] > 5.0, f"Duration is too short: {data['duration']}s"
    print("\nSUCCESS: Exact user MP3 file duration verified correctly!")

if __name__ == '__main__':
    test_user_mp3_upload()
