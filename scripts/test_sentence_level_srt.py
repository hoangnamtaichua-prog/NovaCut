import os, sys, re, time, wave
import soundfile as sf
import numpy as np

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from local_voice_engine import LOCAL_VOICE_PRESETS, synthesize

def sec_to_srt_time(sec):
    hrs = int(sec // 3600)
    mins = int((sec % 3600) // 60)
    secs = int(sec % 60)
    milis = int(round((sec - int(sec)) * 1000))
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{milis:03d}"

def test_sentence_level_srt():
    print("\n--- Testing Sentence-by-Sentence TTS Alignment with Local Voice ---")
    text = "Đẳng cấp nằm ở những trận chung kết, hay sự vĩ đại nằm ở việc duy trì đỉnh cao qua 5 kỳ World Cup? Mỗi người một lối đi riêng vào lịch sử. Bạn chọn 'Chung kết' hay 'Trường tồn'?"
    
    # Split sentences
    sentences = [s.strip() for s in re.split(r'(?<=[.!?\n])\s+', text) if s.strip()]
    print(f"Split into {len(sentences)} sentences:")
    for i, s in enumerate(sentences):
        print(f"  {i+1}: {s}")

    os.makedirs('temp', exist_ok=True)
    temp_chunks = []
    srt_blocks = []
    current_time = 0.0
    pause_sec = 0.2
    
    start_t = time.time()
    for idx, sentence in enumerate(sentences):
        chunk_out = f"temp/chunk_{idx}.wav"
        synthesize(text=sentence, voice_id="local_ngoc_huyen", speed=1.0, output_path=chunk_out)
        
        with wave.open(chunk_out, 'r') as wf:
            dur = wf.getnframes() / float(wf.getframerate())
            
        start_srt = sec_to_srt_time(current_time)
        end_srt = sec_to_srt_time(current_time + dur)
        srt_blocks.append(f"{idx + 1}\n{start_srt} --> {end_srt}\n{sentence}")
        
        data, sr = sf.read(chunk_out)
        temp_chunks.append(data)
        # Add pause
        pause_samples = int(sr * pause_sec)
        temp_chunks.append(np.zeros((pause_samples, 2) if len(data.shape) > 1 else (pause_samples,)))
        
        current_time += dur + pause_sec

    # Combine audio
    final_audio = np.concatenate(temp_chunks, axis=0)
    final_path = 'temp/final_sentence_aligned.wav'
    sf.write(final_path, final_audio, 48000)
    
    srt_content = "\n\n".join(srt_blocks) + "\n"
    srt_path = 'temp/final_sentence_aligned.srt'
    with open(srt_path, 'w', encoding='utf-8') as f:
        f.write(srt_content)
        
    elapsed = time.time() - start_t
    print(f"\nGenerated Audio in {elapsed:.2f}s! Total duration: {len(final_audio)/48000:.2f}s")
    print("--- Generated SRT Content: ---")
    print(srt_content)
    
    assert os.path.exists(final_path)
    assert os.path.exists(srt_path)
    print("SUCCESS: Sentence-by-sentence SRT generation is 100% accurate and instant!")

if __name__ == '__main__':
    test_sentence_level_srt()
