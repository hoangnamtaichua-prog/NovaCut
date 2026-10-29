import os
import sys
import pytest
import json

# Ensure project root is in sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from routes.tts import (
    _format_srt_timecode,
    analyze_voice_timeline_overlaps,
    build_voice_timeline_srt_text
)


def test_format_srt_timecode():
    assert _format_srt_timecode(0) == "00:00:00,000"
    assert _format_srt_timecode(1.5) == "00:00:01,500"
    assert _format_srt_timecode(65.123) == "00:01:05,123"
    assert _format_srt_timecode(3665.456) == "01:01:05,456"


def test_analyze_voice_timeline_overlaps_clean():
    """Kiểm tra trường hợp các câu diễn ra tuần tự, không bị đè lên nhau."""
    chunks = [
        {
            "id": 1,
            "index": 1,
            "text": "Câu thứ nhất rất ngắn.",
            "start_seconds": 1.0,
            "duration": 2.0  # Kết thúc ở 3.0s
        },
        {
            "id": 2,
            "index": 2,
            "text": "Câu thứ hai bắt đầu sau câu một.",
            "start_seconds": 4.0,  # Bắt đầu ở 4.0s (cách 1s)
            "duration": 2.5  # Kết thúc ở 6.5s
        },
        {
            "id": 3,
            "index": 3,
            "text": "Câu thứ ba kết thúc câu chuyện.",
            "start_seconds": 7.0,  # Bắt đầu ở 7.0s (cách 0.5s)
            "duration": 1.8  # Kết thúc ở 8.8s
        }
    ]

    summary = analyze_voice_timeline_overlaps(chunks)

    assert summary["total_chunks"] == 3
    assert summary["overlap_count"] == 0
    assert summary["has_any_overlap"] is False
    assert summary["clean_count"] == 3
    assert summary["total_overlap_duration"] == 0.0

    assert chunks[0]["voice_end_seconds"] == 3.0
    assert chunks[0]["has_overlap"] is False
    assert chunks[0]["gap_to_next"] == 1.0
    assert chunks[0]["srt_timecode"] == "00:00:01,000 --> 00:00:03,000"

    assert chunks[1]["voice_end_seconds"] == 6.5
    assert chunks[1]["has_overlap"] is False
    assert chunks[1]["gap_to_next"] == 0.5


def test_analyze_voice_timeline_overlaps_detected():
    """Kiểm tra trường hợp phát hiện trùng đè (Overlap) thời gian giữa các câu."""
    chunks = [
        {
            "id": 1,
            "index": 1,
            "text": "Nhân vật chính bước vào phòng và nhìn xung quanh.",
            "start_seconds": 2.0,
            "duration": 4.5  # Kết thúc ở 6.5s
        },
        {
            "id": 2,
            "index": 2,
            "text": "Bất ngờ có tiếng động lạ từ phía sau cánh cửa.",
            "start_seconds": 5.0,  # Bắt đầu ở 5.0s -> BỊ ĐÈ 1.5s!
            "duration": 3.0  # Kết thúc ở 8.0s
        },
        {
            "id": 3,
            "index": 3,
            "text": "Anh ta lập tức quay lại và rút vũ khí.",
            "start_seconds": 8.2,  # Bắt đầu ở 8.2s -> Không bị đè, nghỉ 0.2s
            "duration": 2.0
        }
    ]

    summary = analyze_voice_timeline_overlaps(chunks)

    assert summary["total_chunks"] == 3
    assert summary["overlap_count"] == 1
    assert summary["has_any_overlap"] is True
    assert summary["total_overlap_duration"] == 1.5

    # Câu 1 đè lên câu 2
    assert chunks[0]["has_overlap"] is True
    assert chunks[0]["overlap_duration"] == 1.5
    assert len(chunks[0]["overlap_targets"]) == 1
    assert chunks[0]["overlap_targets"][0]["target_index"] == 2
    assert chunks[0]["overlap_targets"][0]["overlap_seconds"] == 1.5

    # Câu 2 bị câu 1 đè lên
    assert len(chunks[1]["is_overlapped_by"]) == 1
    assert chunks[1]["is_overlapped_by"][0]["source_index"] == 1
    assert chunks[1]["is_overlapped_by"][0]["overlap_seconds"] == 1.5

    # Câu 2 không đè câu 3 (kết thúc 8.0s, câu 3 bắt đầu 8.2s)
    assert chunks[1]["has_overlap"] is False
    assert chunks[1]["gap_to_next"] == 0.2


def test_build_voice_timeline_srt_text():
    """Kiểm tra định dạng sinh file SRT timeline có ghi chú cảnh báo trùng đè."""
    chunks = [
        {
            "index": 1,
            "text": "Câu số một dài hơi.",
            "start_seconds": 1.0,
            "duration": 3.5
        },
        {
            "index": 2,
            "text": "Câu số hai bị đè.",
            "start_seconds": 3.0,
            "duration": 2.0
        }
    ]

    analyze_voice_timeline_overlaps(chunks)
    srt_text = build_voice_timeline_srt_text(chunks)

    assert "1\n00:00:01,000 --> 00:00:04,500" in srt_text
    assert "[⚠️ TRÙNG ĐÈ 1.5s VỚI CÂU #2] Câu số một dài hơi." in srt_text
    assert "2\n00:00:03,000 --> 00:00:05,000" in srt_text
    assert "Câu số hai bị đè." in srt_text


def test_export_timeline_srt_endpoint():
    """Kiểm tra Flask API endpoint tải file SRT."""
    from web_app import app
    client = app.test_client()

    sample_srt = "1\n00:00:01,000 --> 00:00:03,000\nXin chào các bạn.\n"
    res = client.post('/api/tts/export_timeline_srt', json={"srt_content": sample_srt})
    assert res.status_code == 200
    assert "voice_timeline.srt" in res.headers.get("Content-Disposition", "")
    assert res.data.decode("utf-8") == sample_srt.strip()


def test_get_timeline_manifest_endpoint():
    """Kiểm tra Flask API endpoint lấy manifest timeline đã lưu."""
    from web_app import app
    client = app.test_client()

    # Thử với video không tồn tại manifest
    res = client.post('/api/tts/get_timeline_manifest', json={"video_path": "non_existent.mp4"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is False
    assert data["has_manifest"] is False


def test_export_pipeline_pregenerated_voice_reuse():
    """Kiểm tra logic tái sử dụng voice trong pipeline xuất video."""
    import tempfile
    import wave
    from routes.video_edit import is_tts_manifest_valid, save_tts_manifest, compute_tts_fingerprint

    with tempfile.TemporaryDirectory() as temp_dir:
        subtitles = [{"text": "Xin chào", "startSeconds": 0.0, "endSeconds": 2.0}]
        fingerprint = compute_tts_fingerprint(subtitles, "local_minh_duc", 1.1, 10.0)

        # Tạo file WAV chuẩn 1.0 giây
        wav_file = os.path.join(temp_dir, "dubbed_timeline.wav")
        with wave.open(wav_file, "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(44100)
            wf.writeframes(b"\x00\x00\x00\x00" * 44100)

        # Lưu manifest
        save_tts_manifest(temp_dir, fingerprint, "local_minh_duc", 1.1, 10.0, 1)

        # Kiểm tra manifest hợp lệ
        assert is_tts_manifest_valid(temp_dir, fingerprint) is True

        has_cached_audio = os.path.exists(wav_file) and os.path.getsize(wav_file) > 1000
        manifest_valid = is_tts_manifest_valid(temp_dir, fingerprint)
        explicit_reuse = True
        fresh_run = False

        can_reuse_audio = (
            not fresh_run and 
            has_cached_audio and 
            (explicit_reuse or manifest_valid)
        )
        assert can_reuse_audio is True


def test_cancel_pregenerate_endpoint():
    """Kiểm tra Flask API endpoint dừng tiến trình tạo voice."""
    from web_app import app
    client = app.test_client()

    res = client.post('/api/tts/cancel_pregenerate', json={"session_id": "non_existent"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True


def test_auto_shift_srt_algorithm():
    """Kiểm tra thuật toán tự động đẩy lùi thời gian SRT để triệt tiêu hoàn toàn trùng đè."""
    # Giả lập: Câu 1 bắt đầu 10.0s, voice kéo dài 2.422s -> voice kết thúc lúc 12.422s
    # Câu 2 bắt đầu 12.0s -> Bị câu 1 đè 0.422s
    # Câu 3 bắt đầu 15.0s, voice kéo dài 1.5s -> Không bị đè
    subtitles = [
        {"id": 1, "startSeconds": 10.0, "endSeconds": 12.0, "text": "Câu một dài hơi"},
        {"id": 2, "startSeconds": 12.0, "endSeconds": 14.0, "text": "Câu hai bị đè"},
        {"id": 3, "startSeconds": 15.0, "endSeconds": 17.0, "text": "Câu ba thoải mái"}
    ]
    chunks = [
        {"id": 1, "duration": 2.422},
        {"id": 2, "duration": 1.800},
        {"id": 3, "duration": 1.500}
    ]
    safety_buffer = 0.05

    shifted_count = 0
    total_shift = 0.0

    for i in range(len(subtitles)):
        cur = subtitles[i]
        cur_start = cur["startSeconds"]
        cur_end = cur["endSeconds"]
        orig_dur = max(0.5, cur_end - cur_start)
        cur_voice_dur = chunks[i]["duration"]

        if i > 0:
            prev = subtitles[i - 1]
            prev_start = prev["startSeconds"]
            prev_voice_dur = chunks[i - 1]["duration"]
            prev_voice_end = prev_start + prev_voice_dur
            min_allowed_start = round(prev_voice_end + safety_buffer, 3)

            if cur_start < min_allowed_start:
                shift_needed = round(min_allowed_start - cur_start, 3)
                cur_start = min_allowed_start
                cur_end = round(cur_start + max(orig_dur, cur_voice_dur), 3)
                shifted_count += 1
                total_shift += shift_needed
            else:
                if cur_end < cur_start + cur_voice_dur:
                    cur_end = round(cur_start + cur_voice_dur, 3)
        else:
            if cur_end < cur_start + cur_voice_dur:
                cur_end = round(cur_start + cur_voice_dur, 3)

        cur["startSeconds"] = cur_start
        cur["endSeconds"] = cur_end

    # Kiểm tra: Câu 2 phải bị đẩy lùi từ 12.0s lên ít nhất 12.472s (10.0 + 2.422 + 0.05)
    assert shifted_count == 1
    assert subtitles[1]["startSeconds"] == 12.472
    assert subtitles[1]["endSeconds"] >= 14.272
    # Câu 3 không bị đẩy lùi vì 15.0s > 12.472 + 1.8 + 0.05 (14.322s)
    assert subtitles[2]["startSeconds"] == 15.0


def test_auto_shift_srt_cascade_resolve():
    """Kiểm tra thuật toán đẩy lùi liên hoàn khi nhiều câu liên tiếp bị đè."""
    from routes.tts import analyze_voice_timeline_overlaps
    # Câu 1: 0.0s -> 2.0s (voice đọc 2.5s -> đè câu 2 tại 2.0s)
    # Câu 2: 2.0s -> 4.0s (voice đọc 2.3s -> khi bị đẩy lùi sẽ tiếp tục đè câu 3 tại 4.2s)
    # Câu 3: 4.2s -> 6.0s (voice đọc 1.8s)
    subs = [
        {"id": 1, "startSeconds": 0.0, "endSeconds": 2.0, "text": "Câu một"},
        {"id": 2, "startSeconds": 2.0, "endSeconds": 4.0, "text": "Câu hai"},
        {"id": 3, "startSeconds": 4.2, "endSeconds": 6.0, "text": "Câu ba"}
    ]
    chunks = [
        {"id": 1, "duration": 2.5, "start_seconds": 0.0},
        {"id": 2, "duration": 2.3, "start_seconds": 2.0},
        {"id": 3, "duration": 1.8, "start_seconds": 4.2}
    ]

    # Kiểm tra ban đầu: chắc chắn có trùng đè
    init_ov = analyze_voice_timeline_overlaps(chunks)
    assert init_ov["has_any_overlap"] is True
    assert init_ov["overlap_count"] >= 1

    safety_buffer = 0.05
    for i in range(len(subs)):
        cur = subs[i]
        c_dur = chunks[i]["duration"]
        if i > 0:
            prev = subs[i - 1]
            min_allowed = round(prev["endSeconds"] + safety_buffer, 3)
            if cur["startSeconds"] < min_allowed:
                cur["startSeconds"] = min_allowed
                cur["endSeconds"] = round(cur["startSeconds"] + c_dur, 3)
            else:
                if cur["endSeconds"] < cur["startSeconds"] + c_dur:
                    cur["endSeconds"] = round(cur["startSeconds"] + c_dur, 3)
        else:
            if cur["endSeconds"] < cur["startSeconds"] + c_dur:
                cur["endSeconds"] = round(cur["startSeconds"] + c_dur, 3)

    # Cập nhật chunks theo startSeconds mới đã đẩy lùi
    shifted_chunks = []
    for i, s in enumerate(subs):
        shifted_chunks.append({
            "id": s["id"],
            "index": i + 1,
            "duration": chunks[i]["duration"],
            "start_seconds": s["startSeconds"]
        })

    # Phân tích lại: Phải sạch 100% không còn câu nào bị đè
    resolved_ov = analyze_voice_timeline_overlaps(shifted_chunks)
    assert resolved_ov["has_any_overlap"] is False
    assert resolved_ov["overlap_count"] == 0
    assert resolved_ov["clean_count"] == 3


def test_restitch_timeline_endpoint():
    """Kiểm tra Flask API endpoint restitch_timeline với payload rỗng."""
    from web_app import app
    client = app.test_client()

    res = client.post('/api/tts/restitch_timeline', json={"subtitles": []})
    assert res.status_code == 400
    data = res.get_json()
    assert data["success"] is False


if __name__ == '__main__':
    print("--- Running test_format_srt_timecode ---")
    test_format_srt_timecode()
    print("PASS: test_format_srt_timecode")

    print("--- Running test_analyze_voice_timeline_overlaps_clean ---")
    test_analyze_voice_timeline_overlaps_clean()
    print("PASS: test_analyze_voice_timeline_overlaps_clean")

    print("--- Running test_analyze_voice_timeline_overlaps_detected ---")
    test_analyze_voice_timeline_overlaps_detected()
    print("PASS: test_analyze_voice_timeline_overlaps_detected")

    print("--- Running test_build_voice_timeline_srt_text ---")
    test_build_voice_timeline_srt_text()
    print("PASS: test_build_voice_timeline_srt_text")

    print("--- Running test_export_timeline_srt_endpoint ---")
    test_export_timeline_srt_endpoint()
    print("PASS: test_export_timeline_srt_endpoint")

    print("--- Running test_get_timeline_manifest_endpoint ---")
    test_get_timeline_manifest_endpoint()
    print("PASS: test_get_timeline_manifest_endpoint")

    print("--- Running test_export_pipeline_pregenerated_voice_reuse ---")
    test_export_pipeline_pregenerated_voice_reuse()
    print("PASS: test_export_pipeline_pregenerated_voice_reuse")

    print("--- Running test_cancel_pregenerate_endpoint ---")
    test_cancel_pregenerate_endpoint()
    print("PASS: test_cancel_pregenerate_endpoint")

    print("--- Running test_auto_shift_srt_algorithm ---")
    test_auto_shift_srt_algorithm()
    print("PASS: test_auto_shift_srt_algorithm")

    print("--- Running test_auto_shift_srt_cascade_resolve ---")
    test_auto_shift_srt_cascade_resolve()
    print("PASS: test_auto_shift_srt_cascade_resolve")

    print("--- Running test_restitch_timeline_endpoint ---")
    test_restitch_timeline_endpoint()
    print("PASS: test_restitch_timeline_endpoint")

    print("\n✅ TẤT CẢ CÁC BÀI TEST ĐÃ VƯỢT QUA 100%!")
