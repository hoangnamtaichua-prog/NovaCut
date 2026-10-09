# -*- coding: utf-8 -*-
import os
import wave
import json
import pytest
import numpy as np

from subtitle_postprocessor import deterministic_normalize_subtitles
from routes.video_edit import is_tts_manifest_valid


def test_subtitle_postprocessor_no_cascade_drift():
    """Kiểm tra giải thuật xử lý overlap không làm trôi dạt timestamp về tương lai."""
    # Giả lập chuỗi phụ đề có nhiều đoạn chồng lấn / xuất hiện gần như đồng thời
    raw_subtitles = [
        {"id": 1, "startSeconds": 10.0, "endSeconds": 13.0, "text": "Câu 1", "translation": "Câu 1"},
        {"id": 2, "startSeconds": 10.1, "endSeconds": 12.0, "text": "Câu 2", "translation": "Câu 2"},
        {"id": 3, "startSeconds": 12.5, "endSeconds": 15.0, "text": "Câu 3", "translation": "Câu 3"},
        {"id": 4, "startSeconds": 13.0, "endSeconds": 16.0, "text": "Câu 4", "translation": "Câu 4"},
        {"id": 5, "startSeconds": 15.2, "endSeconds": 18.0, "text": "Câu 5", "translation": "Câu 5"},
        {"id": 6, "startSeconds": 18.5, "endSeconds": 21.0, "text": "Câu 6", "translation": "Câu 6"},
    ]

    normalized = deterministic_normalize_subtitles(raw_subtitles, dedup_window=0.7)

    # 1. Đảm bảo startSeconds của các câu không bị đẩy lùi về tương lai hàng giây
    for norm_item in normalized:
        orig = next(s for s in raw_subtitles if s["id"] == norm_item["id"])
        drift = norm_item["startSeconds"] - orig["startSeconds"]
        assert abs(drift) <= 0.1, f"Câu {norm_item['id']} bị trôi lệch {drift:.2f}s (start={norm_item['startSeconds']})"

    # 2. Đảm bảo câu 6 vẫn bắt đầu đúng mốc ~18.5s chứ không bị dồn lên 25s+
    last_item = normalized[-1]
    assert abs(last_item["startSeconds"] - 18.5) <= 0.1


def test_is_tts_manifest_valid_rejects_empty_wav(tmp_path):
    """Kiểm tra is_tts_manifest_valid từ chối file WAV rỗng hoặc hỏng."""
    temp_dir = str(tmp_path)
    fp = "test_fp_123"

    # Trường hợp 1: Chưa có manifest hoặc wav
    assert is_tts_manifest_valid(temp_dir, fp) is False

    # Trường hợp 2: Có manifest nhưng wav rỗng (0 frames)
    manifest_file = os.path.join(temp_dir, 'tts_manifest.json')
    wav_file = os.path.join(temp_dir, 'dubbed_timeline.wav')
    with open(manifest_file, 'w', encoding='utf-8') as f:
        json.dump({"fingerprint": fp}, f)

    # Tạo WAV không có frame
    with wave.open(wav_file, 'wb') as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(44100)
        # 0 frames

    assert is_tts_manifest_valid(temp_dir, fp) is False

    # Trường hợp 3: WAV hợp lệ có audio
    with wave.open(wav_file, 'wb') as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(44100)
        silence = np.zeros((44100 * 2, 2), dtype=np.int16)
        wf.writeframes(silence.tobytes())

    assert is_tts_manifest_valid(temp_dir, fp) is True
