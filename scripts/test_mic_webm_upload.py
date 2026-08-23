import os, sys, subprocess, wave
import numpy as np
import soundfile as sf

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from web_app import app
from local_voice_engine import _get_ffmpeg_exe

def test_mic_recording_flow():
    client = app.test_client()

    print("\n--- 1. Generating a synthetic WebM/Opus audio (simulating browser mic) ---")
    ffmpeg_exe = _get_ffmpeg_exe()
    os.makedirs('temp', exist_ok=True)
    temp_wav = 'temp/mic_sim_src.wav'
    temp_webm = 'temp/mic_recording_sim.webm'
    
    sr = 48000
    t = np.linspace(0, 4.0, int(sr * 4.0), endpoint=False)
    audio = 0.25 * np.sin(2 * np.pi * 350 * t)
    sf.write(temp_wav, audio, sr)

    cmd = [ffmpeg_exe, "-y", "-i", temp_wav, "-c:a", "libopus", "-b:a", "64k", temp_webm]
    subprocess.run(cmd, capture_output=True, check=True)
    print(f"Created simulated browser microphone recording: {temp_webm} (size: {os.path.getsize(temp_webm)} bytes)")

    print("\n--- 2. Uploading simulated microphone WebM to /api/clone_voice/upload ---")
    with open(temp_webm, 'rb') as f:
        res = client.post('/api/clone_voice/upload', data={
            'audio_file': (f, 'mic_recording_1787245.webm')
        }, content_type='multipart/form-data')
        
    assert res.status_code == 200, f"Upload failed: {res.data}"
    up_data = res.json
    print("Upload result:", up_data)
    assert up_data['success'] == True
    print(f"Cleaned normalized audio path: {up_data['audio_path']} (duration: {up_data['duration']}s)")

    print("\n--- 3. Testing Preview generation with the converted Mic recording ---")
    res = client.post('/api/clone_voice/preview', json={
        'text': 'Đây là câu nghe thử từ mẫu ghi âm microphone trực tiếp.',
        'audio_path': up_data['audio_path'],
        'speed': 1.0
    })
    assert res.status_code == 200, f"Preview failed: {res.data}"
    prev_data = res.json
    print("Preview result:", prev_data)
    assert prev_data['success'] == True
    assert os.path.exists(prev_data['output_path'])
    print(f"Preview generated successfully at: {prev_data['output_path']}")

    print("\n=======================================================")
    print("MICROPHONE WEBM AUDIO CONVERSION & PREVIEW VERIFIED 100%")
    print("=======================================================")

if __name__ == '__main__':
    test_mic_recording_flow()
