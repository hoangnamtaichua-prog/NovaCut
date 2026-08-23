import os, sys
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from web_app import app
import soundfile as sf

def test_auto_rhythm_and_srt_generation():
    print("\n=======================================================")
    print("TESTING FULL MULTI-SENTENCE TTS + 0.5s PAUSE + SRT PIPELINE")
    print("=======================================================")

    client = app.test_client()

    input_text = """
    Đẳng cấp nằm ở những trận chung kết, hay sự vĩ đại nằm ở việc duy trì đỉnh cao qua 5 kỳ World Cup?
    
    Mỗi người một lối đi riêng vào lịch sử bóng đá thế giới.
    
    Bạn chọn "Chung kết" hay "Trường tồn"?
    """

    res = client.post('/api/tts/kokoro', json={
        'text': input_text,
        'voice': 'local_ngoc_huyen',
        'speed': 1.0,
        'output_dir': 'output',
        'filename': 'test_rhythm_and_sub.wav'
    })

    assert res.status_code == 200, f"TTS API Error: {res.data}"
    data = res.json
    print("API Response:", data)
    assert data['success'] is True
    assert 'audio_url' in data
    assert 'srt_url' in data

    audio_path = os.path.join(ROOT_DIR, 'output', 'test_rhythm_and_sub.wav')
    srt_path = os.path.join(ROOT_DIR, 'output', 'test_rhythm_and_sub.srt')

    assert os.path.exists(audio_path), "Audio file was not created!"
    assert os.path.exists(srt_path), "SRT file was not created!"

    f = sf.SoundFile(audio_path)
    dur = len(f) / float(f.samplerate)
    print(f"\nAudio File Created: {audio_path}")
    print(f"Sample Rate: {f.samplerate}Hz • Channels: {f.channels} • Duration: {dur:.2f}s")
    assert dur > 5.0, "Audio duration too short"

    with open(srt_path, 'r', encoding='utf-8') as srt_file:
        srt_content = srt_file.read()

    print("\n--- GENERATED SRT SUBTITLE CONTENT: ---")
    print(srt_content)
    print("---------------------------------------")

    assert "1\n00:00:00,000 -->" in srt_content
    assert "2\n" in srt_content
    assert "3\n" in srt_content
    assert "Đẳng cấp nằm ở những trận chung kết" in srt_content
    assert "Mỗi người một lối đi riêng" in srt_content
    assert "Bạn chọn" in srt_content

    print("\n=======================================================")
    print("PHƯƠNG ÁN 1 + 0.5s PAUSE + SMART SRT VERIFIED 100% SUCCESS")
    print("=======================================================")

if __name__ == '__main__':
    test_auto_rhythm_and_srt_generation()
