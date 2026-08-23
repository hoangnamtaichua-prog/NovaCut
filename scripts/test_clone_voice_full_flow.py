import os
import sys
import json
import numpy as np
import soundfile as sf

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from web_app import app

def test_clone_flow():
    client = app.test_client()

    print("\n--- 1. Testing GET /api/voices ---")
    res = client.get('/api/voices')
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    voices = res.json
    print(f"Total voices returned: {len(voices)}")
    local_presets = [v for v in voices if v.get('provider') == 'local_voice' and not v.get('is_custom')]
    print(f"Local Voice Presets count: {len(local_presets)}")
    assert len(local_presets) >= 8, "Expected at least 8 Local Voice presets"
    print("Sample preset:", local_presets[0]['name'], f"({local_presets[0]['id']})")

    print("\n--- 2. Creating a test sample WAV (3.5s 48kHz audio) ---")
    os.makedirs('temp', exist_ok=True)
    sample_wav = 'temp/unit_test_sample.wav'
    sr = 48000
    t = np.linspace(0, 3.5, int(sr * 3.5), endpoint=False)
    # Simple sine wave test audio
    audio = 0.2 * np.sin(2 * np.pi * 440 * t)
    sf.write(sample_wav, audio, sr)
    print(f"Created sample wav: {sample_wav}")

    print("\n--- 3. Testing POST /api/clone_voice/upload ---")
    with open(sample_wav, 'rb') as f:
        res = client.post('/api/clone_voice/upload', data={
            'audio_file': (f, 'test_sample.wav')
        }, content_type='multipart/form-data')
    assert res.status_code == 200, f"Upload failed: {res.data}"
    up_data = res.json
    print("Upload result:", up_data)
    assert up_data['success'] == True
    uploaded_path = up_data['audio_path']

    print("\n--- 4. Testing POST /api/clone_voice/preview ---")
    res = client.post('/api/clone_voice/preview', json={
        'text': 'Chào bạn, đây là thử nghiệm nhân bản giọng nói hoàn hảo.',
        'audio_path': uploaded_path,
        'speed': 1.0
    })
    assert res.status_code == 200, f"Preview failed: {res.data}"
    prev_data = res.json
    print("Preview result:", prev_data)
    assert prev_data['success'] == True
    assert os.path.exists(prev_data['output_path'])
    print(f"Generated preview audio at {prev_data['output_path']} (size: {os.path.getsize(prev_data['output_path'])} bytes)")

    print("\n--- 5. Testing POST /api/clone_voice/save ---")
    test_voice_name = "Giọng Test Tự Động Clone"
    res = client.post('/api/clone_voice/save', json={
        'name': test_voice_name,
        'audio_path': uploaded_path,
        'gender': 'Female',
        'region': 'Miền Bắc',
        'style': 'review'
    })
    assert res.status_code == 200, f"Save failed: {res.data}"
    save_data = res.json
    print("Save result:", save_data)
    assert save_data['success'] == True
    saved_voice = save_data['voice']
    voice_id = saved_voice['id']
    print(f"Saved voice ID: {voice_id}")

    print("\n--- 6. Verifying saved voice appears in GET /api/voices ---")
    res = client.get('/api/voices')
    voices = res.json
    found = next((v for v in voices if v['id'] == voice_id), None)
    assert found is not None, f"Saved voice {voice_id} not found in /api/voices"
    print(f"Found saved voice: {found['name']} - Provider: {found['provider']} - Tag: {found['tag']}")

    print("\n--- 7. Testing Dubbing Engine synthesis with new voice ID ---")
    import ai_dubbing
    dub_out = 'temp/test_dub_output.wav'
    res_path = ai_dubbing.synthesize_sentence(
        text="Đây là câu thoại được lồng tiếng từ giọng nhân bản vừa lưu.",
        voice_id=voice_id,
        output_path=dub_out,
        speed=1.0
    )
    assert os.path.exists(dub_out)
    print(f"Synthesized dubbing audio with cloned voice: {dub_out} (size: {os.path.getsize(dub_out)} bytes)")

    print("\n--- 8. Testing POST /api/clone_voice/delete ---")
    res = client.post('/api/clone_voice/delete', json={'voice_id': voice_id})
    assert res.status_code == 200, f"Delete failed: {res.data}"
    del_data = res.json
    print("Delete result:", del_data)
    assert del_data['success'] == True

    print("\n--- 9. Verifying voice deleted from /api/voices ---")
    res = client.get('/api/voices')
    voices = res.json
    found_after = next((v for v in voices if v['id'] == voice_id), None)
    assert found_after is None, f"Voice {voice_id} should have been deleted from /api/voices"
    print("Verification complete: Voice was deleted successfully!")

    print("\n=======================================================")
    print("ALL TESTS PASSED! FULL CLONE VOICE PIPELINE VERIFIED 100%")
    print("=======================================================")

if __name__ == '__main__':
    test_clone_flow()
