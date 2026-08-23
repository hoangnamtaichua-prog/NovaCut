import os, sys
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from web_app import app

def test_clone_voice_edit_flow():
    client = app.test_client()

    print("\n--- 1. Testing POST /api/clone_voice/save with Full Metadata ---")
    sample_path = os.path.join(ROOT_DIR, 'output', 'tts_open_vbee_hn_male_manhdung_full_24k-st_1787246130.mp3')
    
    save_res = client.post('/api/clone_voice/save', json={
        'name': 'Giọng Nam Idol Test',
        'audio_path': sample_path,
        'lang': 'Vietnamese',
        'region': 'Sài Gòn',
        'gender': 'Male',
        'age': 'young',
        'style': 'story',
        'tag': 'Giọng kể chuyện ma đêm khuya ấm áp'
    })
    assert save_res.status_code == 200, f"Save failed: {save_res.data}"
    voice = save_res.json['voice']
    voice_id = voice['id']
    print(f"Created Voice ID: {voice_id}")
    print(f"Initial Name: {voice['name']}, Region: {voice['region']}, Style: {voice['style']}")
    assert voice['region'] == 'Sài Gòn'
    assert voice['gender'] == 'Male'
    assert voice['style'] == 'story'

    print("\n--- 2. Testing POST /api/clone_voice/update (Editing voice metadata) ---")
    update_res = client.post('/api/clone_voice/update', json={
        'voice_id': voice_id,
        'name': 'Idol Mạnh Dũng Vip',
        'lang': 'Vietnamese',
        'region': 'Hà Nội',
        'gender': 'Male',
        'age': 'middle_aged',
        'style': 'review',
        'tag': 'Giọng review phim hành động đỉnh cao'
    })
    assert update_res.status_code == 200, f"Update failed: {update_res.data}"
    up_voice = update_res.json['voice']
    print(f"Updated Name: {up_voice['name']}")
    print(f"Updated Region: {up_voice['region']}, Age: {up_voice['age']}, Style: {up_voice['style']}")
    assert up_voice['region'] == 'Hà Nội'
    assert up_voice['age'] == 'middle_aged'
    assert up_voice['style'] == 'review'
    assert 'Idol Mạnh Dũng Vip' in up_voice['name']

    print("\n--- 3. Verifying updated voice in GET /api/voices ---")
    get_res = client.get('/api/voices')
    all_voices = get_res.json
    found = next((v for v in all_voices if v['id'] == voice_id), None)
    assert found is not None, "Voice not found in /api/voices"
    print("Found in library:", found['name'], "-", found['region'], "-", found['style'], "-", found['tag'])
    assert found['region'] == 'Hà Nội'
    assert found['style'] == 'review'

    print("\n--- 4. Cleaning up (Delete voice) ---")
    del_res = client.post('/api/clone_voice/delete', json={'voice_id': voice_id})
    assert del_res.status_code == 200
    print("Deleted successfully!")

    print("\n=======================================================")
    print("FULL METADATA FIELDS & EDIT FLOW VERIFIED 100% SUCCESS")
    print("=======================================================")

if __name__ == '__main__':
    test_clone_voice_edit_flow()
