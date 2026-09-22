# Báo cáo nghiên cứu và đề xuất cải tiến phần Review phim

**Phạm vi:** nhánh Review phim dùng phụ đề SRT → kịch bản/lời thuyết minh → timeline cảnh → cắt video → ghép voice/BGM/phụ đề. Báo cáo này tập trung vào `auto_edit_pipeline.py`, `timeline_sanitizer.py`, `review_phim.py` và endpoint `/api/review/start`.

## 1. Kết luận điều hành

Pipeline hiện đã có những nền tảng tốt: tạo TTS theo từng câu và lưu SRT theo thời lượng thật, map-reduce timeline để giảm thời gian gọi LLM, cache theo bước, phát hiện cảnh bằng PySceneDetect, snap mốc cắt vào scene cut, cắt song song và tự chọn encoder GPU.

Tuy nhiên, ba lỗi kiến trúc có thể làm video giật hoặc lời không khớp hình:

1. `timeline_sanitizer` tính `speed_ratio` sau khi snap mốc cắt, nhưng hàm `render_single_clip` chỉ dùng `start` và `duration`; nó không dùng `speed_ratio` để biến đổi PTS. Vì vậy phần “bù tốc độ” được ghi trong JSON nhưng chưa đi vào video thực tế.
2. Pipeline encode từng clip MP4 rồi dùng concat demuxer với `-c copy`. FFmpeg yêu cầu các file có cùng stream, codec và time base; thời lượng/PTS sai có thể tạo khoảng trống, nhảy hình hoặc lệch âm thanh khi nối. Đây là rủi ro trực tiếp vì mỗi clip được seek và encode độc lập.
3. Lệnh cắt dùng `-ss` trước `-i`. Cách này nhanh nhưng seek theo keyframe và có thể không đạt frame-accurate tại mốc LLM/snap. Khi mốc nằm giữa GOP, đầu clip có thể lệch vài frame hoặc xuất hiện cảm giác giật.

Nếu chỉ sửa một vòng, nên ưu tiên: **(P0) bảo đảm một timeline thời gian duy nhất**, **(P0) áp dụng speed ratio hoặc thay đổi cách khớp voice**, **(P1) bỏ nối MP4 rời bằng concat copy**, và **(P1) chuẩn hóa FPS/time base/PTS**. Các thay đổi này tác động lớn hơn việc tinh chỉnh CRF hay tăng số worker.

## 2. Luồng hiện tại

### 2.1. Chế độ API/AI

`routes/video_edit.py` nhận `/api/review/start`, sau đó gọi `auto_edit_pipeline.run_auto_edit_workflow`.

Luồng chính:

1. Đọc SRT gốc và tạo kịch bản review.
2. Sinh voice tổng hoặc TTS từng câu; lưu `voice_audio.wav` và SRT có timestamp theo audio thật. TTS từng câu có cache và chạy đa luồng.
3. Gọi LLM theo batch để tạo `timeline_data` gồm `start`, `end`/`duration`, `voice_ref`.
4. PySceneDetect quét các cửa sổ quanh biên timeline; kết quả được cache.
5. `sanitize_timeline` snap start/end vào scene cut gần nhất, giới hạn độ lệch tốc độ, gộp clip quá ngắn.
6. Mỗi clip được cắt thành MP4 câm song song; sau đó concat bằng `-c copy`.
7. Ghép voice tổng, BGM, logo và phụ đề bằng một lần render cuối.

### 2.2. Chế độ manual cũ

`review_phim.build_video_workflow` tạo TTS từng đoạn, đo duration, tính speed ratio và encode từng clip. Nhánh này cũng concat các MP4 bằng `-c copy`, nên có cùng rủi ro PTS/time-base. Ngoài ra nó clamp tốc độ video 0.5–2.0 nhưng không có kiểm tra lip-sync hay giới hạn thay đổi cảnh theo shot.

## 3. Phát hiện chi tiết trong mã nguồn

### P0 — Speed ratio được tính nhưng không được áp dụng

`timeline_sanitizer.py` tính:

```text
speed_ratio = actual_duration / original_duration
```

và lưu vào mỗi clip. Nhưng `render_single_clip` ở `auto_edit_pipeline.py` chỉ đọc `clip['start']` và `clip['duration']`, rồi chạy filter video hình ảnh/blur/zoom. Không có `setpts=PTS/speed_ratio`, cũng không có `trim`/`tpad` để bù thời lượng. Kết quả là:

- audio vẫn chạy theo voice tổng;
- video có thể ngắn/dài hơn mốc audio tương ứng;
- snap thành công trên JSON nhưng không bảo đảm khớp khi xem thực tế.

**Cách sửa đề xuất:** chọn một trong hai chính sách, không trộn lẫn:

- **Chính sách A (khuyến nghị):** coi thời lượng voice là chuẩn. Với mỗi clip, giữ vùng hình nguồn nhưng dùng `setpts=PTS/speed_ratio` để đầu ra đúng `original_duration` (hoặc đúng khoảng audio). Giới hạn tốc độ theo loại cảnh, ví dụ 0.90–1.10 cho hội thoại, 0.80–1.25 cho montage/hành động.
- **Chính sách B:** không đổi tốc độ video; khi snap làm thay đổi thời lượng thì time-stretch voice bằng `atempo` (chuỗi filter nếu vượt 0.5–2.0). Cách này giữ chuyển động tự nhiên hơn nhưng giọng có thể thay đổi nhịp.

Nên thêm các trường bất biến vào timeline: `voice_start`, `voice_end`, `voice_duration`, `source_start`, `source_end`, `video_duration_after_transform`, `sync_error_ms`.

### P0 — Không có bước kiểm tra đồng bộ sau render

Pipeline chỉ kiểm tra process FFmpeg thành công. Chưa có kiểm tra:

- tổng duration của video và voice;
- sai số từng block theo `voice_ref`;
- frame đầu/cuối có PTS liên tục;
- số frame thực tế so với FPS mục tiêu;
- clip nào vượt giới hạn speed hoặc có khoảng trống.

**Đề xuất:** sau khi tạo timeline và trước khi encode, chạy validator thuần Python; sau khi encode chạy `ffprobe -show_frames`/`-show_streams` trên mẫu đầu-cuối. Từ chối export hoặc cảnh báo nếu `abs(video_duration - voice_duration) > 80 ms`, có PTS giảm, hoặc `sync_error_ms > 120 ms` ở bất kỳ block quan trọng nào.

### P0 — Cắt trước keyframe gây sai mốc

Trong `render_single_clip`, lệnh có dạng `-ss start -t duration -i video`. Đây là fast seek. Với nguồn H.264/H.265 có GOP dài, mốc bắt đầu có thể không đúng frame yêu cầu.

**Đề xuất hai chế độ:**

- Preview nhanh: giữ fast seek, đánh dấu sai số dự kiến.
- Export chính xác: đặt `-ss` sau `-i` hoặc dùng `trim=start:end,setpts=PTS-STARTPTS`; có thể đọc dư 0.5–1.0 giây quanh biên rồi trim chính xác trong filter.

Nên probe FPS và time base nguồn rồi chuyển tất cả clip về cùng `fps`, `time_base`, `start_pts=0`, `format=yuv420p`.

### P1 — Nối các MP4 rời bằng concat demuxer + stream copy

Pipeline tạo nhiều file `clip_silent_*.mp4`, sau đó tạo `concat_silent.mp4` bằng `-f concat -c copy`. Tài liệu FFmpeg nêu rõ concat demuxer yêu cầu các file có cùng stream/codec/time base và dùng duration lưu trong từng file để điều chỉnh timestamp; duration sai có thể tạo artifact. Các clip hiện được render độc lập nên không có bảo đảm mạnh về time base, GOP, extradata, duration metadata và PTS.

**Cách sửa khuyến nghị:**

1. Tốt nhất: tạo **một lệnh FFmpeg duy nhất** với `trim`/`setpts` cho tất cả đoạn, rồi `concat` trong filter graph; encode video một lần.
2. Nếu cần render song song: sau khi concat phải re-encode một pass chuẩn hóa (`fps`, `settb`, `setpts`, `vsync/cfr`, `-movflags +faststart`), không phát hành file stream-copy trực tiếp.
3. Dùng concat filter thay vì concat demuxer khi cần đảm bảo PTS liên tục; mọi nhánh phải có cùng kích thước/FPS/pixel format.

### P1 — Scene detection đang bỏ bớt frame để tăng tốc

`timeline_sanitizer.extract_scene_cuts_with_progress` dùng downscale khoảng 360 px và `frame_skip=2`. Đây là lựa chọn hợp lý cho scan nhanh, nhưng tài liệu PySceneDetect cảnh báo frame skip làm giảm độ chính xác, đặc biệt với cut nhanh. Không nên dùng cut phát hiện bằng scan thưa làm mốc chính xác tuyệt đối.

**Đề xuất hai pha:** scan thưa để tìm ứng viên; sau đó scan chính xác 1–2 giây quanh từng biên bằng `frame_skip=0`. Chỉ chấp nhận cut nếu điểm ổn định qua hai lần đo. Với video FPS thấp hoặc hành động nhanh, tự động giảm frame skip.

### P1 — Gộp clip ngắn có thể phá quan hệ hình–lời

Khi clip ngắn hơn `min_clip_duration`, sanitizer gộp vào clip kế tiếp và cộng `original_duration`; nhưng không giữ danh sách nhiều `voice_ref` trong clip gộp. Nếu một đoạn lời có ý nghĩa riêng, việc gộp chỉ ở cấp video có thể làm mất khả năng chẩn đoán sai khớp.

**Đề xuất:** dùng `voice_refs: []` và mảng con `subsegments` trong timeline. Gộp hình chỉ là tối ưu render; mapping lời vẫn phải giữ được từng block.

### P1 — Tốc độ encode song song có thể tự triệt tiêu

Pipeline dùng tối đa 4 worker, mỗi worker CPU encoder có `-threads 2`. Trên máy ít lõi, 4 tiến trình × 2 thread cộng thêm decode/IO có thể gây tranh chấp và làm tổng thời gian dài hơn. Khi dùng NVENC/QSV, nhiều job đồng thời cũng có thể làm queue GPU nghẽn.

**Đề xuất:** benchmark 1/2/4 worker theo encoder; chọn worker động theo `cpu_count`, RAM và encoder. Với kiến trúc một-pass, giảm đáng kể overhead process và đọc lại video.

### P2 — Tạo TTS tuần tự ở một số nhánh và nhiều lần probe

Nhánh `review_phim.build_video_workflow` tạo từng TTS rồi gọi ffprobe từng file. Nhánh auto đã có đa luồng/cache, nên nên hợp nhất hai luồng vào một `TTS manifest` duy nhất: text hash, voice, speed, file, duration, sample rate, transcript. Khi có manifest hợp lệ, không gọi lại TTS/ffprobe.

### P2 — BGM và âm lượng chưa có tiêu chuẩn loudness

Mix hiện dùng volume cố định/sidechain tùy nhánh. Kết quả có thể lấn giọng hoặc clipping theo từng file. Thêm đo LUFS/true peak và ducking theo voice envelope sẽ ổn định trải nghiệm hơn; đây là cải thiện chất lượng, không phải nguyên nhân chính của giật hình.

## 4. Tham khảo cách làm của repo/thư viện khác

### Auto-Editor

Auto-Editor biểu diễn timeline thành các đoạn hoạt động rồi áp dụng action riêng cho từng đoạn: giữ, cắt hoặc speed. Nó có margin quanh vùng giữ và transition dissolve tùy chọn để tránh jump cut; đồng thời có thể dựng theo subtitle/transcript. Bài học áp dụng được là tách rõ **phân tích timeline** khỏi **action render**, lưu margin/transition trong timeline và không dùng một speed ratio chung cho mọi loại cảnh.

Nguồn: [Actions](https://auto-editor.com/docs/actions), [Cookbook](https://auto-editor.com/docs/cookbook), [Edit reference](https://auto-editor.com/ref/edit).

### PySceneDetect

PySceneDetect cung cấp ContentDetector và `frame_skip` để đánh đổi tốc độ với độ chính xác. Cách phù hợp với repo này là dùng `frame_skip` chỉ cho pha tìm ứng viên, sau đó tinh chỉnh quanh biên bằng scan đầy đủ. Không nên coi kết quả scan thưa là frame-accurate.

Nguồn: [SceneManager API](https://www.scenedetect.com/docs/head/api/scene_manager.html), [PySceneDetect API](https://www.scenedetect.com/docs/head/api.html).

### FFmpeg concat/filter graph

FFmpeg concat demuxer yêu cầu stream/time base đồng nhất và phụ thuộc duration metadata để nối timestamp. Khi cần kiểm soát PTS, filter graph với `trim`, `setpts`, `concat`, sau đó encode một lần an toàn hơn. `atempo` dùng để time-stretch voice khi chính sách đồng bộ chọn audio làm chuẩn.

Nguồn: [FFmpeg concat demuxer](https://www.ffmpeg.org/ffmpeg-all.html#concat), [FFmpeg filters](https://ffmpeg.org/ffmpeg-filters.html).

## 5. Kiến trúc đề xuất

### 5.1. Timeline chuẩn

Mỗi đoạn nên có schema:

```json
{
  "id": 12,
  "voice_ref": [12],
  "source_start": 101.240,
  "source_end": 106.880,
  "voice_start": 34.520,
  "voice_end": 39.820,
  "voice_duration": 5.300,
  "scene_start": 101.180,
  "scene_end": 106.940,
  "video_speed": 1.000,
  "audio_tempo": 1.000,
  "transition": {"type": "hard", "duration": 0.0},
  "sync_error_ms": 0
}
```

Không cho LLM quyết định trực tiếp mọi số cuối cùng. LLM chỉ đề xuất cảnh/ý nghĩa; bộ deterministic resolver mới chọn mốc hợp lệ dựa trên SRT, scene cuts, min/max duration và tốc độ cho phép.

### 5.2. Resolver đồng bộ

1. Lấy `voice_start/voice_end` từ SRT TTS thực tế.
2. Chọn `source_start/source_end` trong shot tương ứng.
3. Snap từng biên vào scene cut sau khi scan chính xác.
4. Tính `video_duration = source_end - source_start`.
5. Nếu lệch nhỏ, dùng `setpts` trong ngưỡng an toàn.
6. Nếu lệch lớn, ưu tiên mở rộng/thu hẹp shot lân cận hoặc chia voice block; chỉ dùng time-stretch khi được cho phép.
7. Validator kiểm tra tổng timeline trước khi render.

### 5.3. Render hai chế độ

- **Preview:** fast seek, encode nhanh, độ phân giải thấp, không blur/ASS nặng, không scene scan toàn bộ.
- **Final:** seek chính xác, một-pass filter graph hoặc concat filter, FPS/time base cố định, audio/voice và BGM ở cùng một clock, validator sau render.

## 6. Lộ trình triển khai theo ưu tiên

### P0 — Có thể làm ngay

- Sửa `render_single_clip` để dùng `video_speed`/`speed_ratio` thực sự, hoặc đổi sang policy time-stretch audio rõ ràng.
- Thêm validator timeline và ffprobe sau export.
- Chuẩn hóa PTS: `setpts=PTS-STARTPTS`, FPS cố định, `-an` ở clip trung gian.
- Ghi log sai số từng đoạn, không chỉ log process FFmpeg.

### P1 — Cải thiện độ mượt và độ chính xác

- Thay concat demuxer stream-copy bằng concat filter/one-pass render; nếu chưa thể, thêm pass re-encode chuẩn hóa.
- Tách scan scene thành coarse scan + boundary refinement (`frame_skip=0`).
- Dùng accurate seek cho final export.
- Giữ `voice_refs/subsegments` khi gộp clip ngắn.

### P2 — Tăng tốc vận hành

- Hợp nhất cache TTS/ffprobe thành manifest.
- Tự điều chỉnh worker theo benchmark máy thực tế.
- Cache probe video, scene cuts và filter script theo fingerprint file + tham số.
- Preview thấp độ phân giải và chỉ render lại phần timeline thay đổi.

## 7. Chỉ số nghiệm thu đề xuất

Chạy cùng một tập 10 video, gồm thoại chậm, hành động nhanh, nguồn 23.976/25/30/60 fps:

- **Tốc độ:** thời gian từ start đến file final; mục tiêu giảm 25–40% so với baseline sau khi bỏ encode/đọc lặp.
- **Đồng bộ:** P95 `sync_error_ms` ≤ 80 ms; không đoạn nào > 150 ms.
- **Mốc cắt:** sai số frame ở biên final ≤ 1 frame khi bật accurate export.
- **Mượt:** không có PTS giảm, không duplicate/drop bất thường, không khựng tại 20 điểm nối được lấy mẫu.
- **Chất lượng lời:** không clipping; voice giữ loudness ổn định sau khi mix BGM.
- **Tính lặp lại:** chạy lại cùng fingerprint phải tái sử dụng TTS, timeline, scene cache và cho kết quả duration tương đương.

## 8. Checklist cho AI triển khai

- [x] Đọc `voice_srt` làm clock chuẩn (Voice Master Clock).
- [x] LLM chỉ đề xuất cảnh; resolver deterministic quyết định mốc cuối (`resolve_timeline_with_voice_clock`).
- [x] Lưu riêng source time và voice time: `source_start`, `source_end`, `source_duration`, `voice_start`, `voice_end`, `voice_duration`.
- [x] Áp dụng speed ratio thực sự qua `setpts=PTS/{video_speed}`, không chỉ ghi JSON.
- [x] Accurate seek ở final export (hybrid `-ss` trước/sau `-i` và fine trim).
- [x] Đồng nhất FPS (30), time base (1/90000), pixel format (yuv420p), PTS (bắt đầu từ 0) trước concat.
- [x] Tránh concat `-c copy` giữa các MP4 không chuẩn hóa; chuẩn hóa 100% stream specs trên từng clip trung gian.
- [x] Coarse scene scan (`frame_skip=2`) + Boundary refinement (`frame_skip=0`).
- [x] Validator trước (`validate_timeline`) và sau render (`validate_rendered_video`).
- [x] Cache manifest TTS/ffprobe và tự động điều chỉnh worker (GPU NVENC: 2 workers, CPU: 4 workers).

## 9. Tệp/mốc mã nguồn đã chỉnh sửa

- [timeline_sanitizer.py](file:///d:/Tool/AI-Movie-Shorts/AI-Movie-Shorts/timeline_sanitizer.py): 
  - Thêm `refine_scene_cuts_boundary` cho boundary refinement 2 giai đoạn (`frame_skip=0`).
  - Viết mới `resolve_timeline_with_voice_clock`: Deterministic Resolver với Voice Master Clock.
  - Viết mới `validate_timeline`: Pre-render validator kiểm tra P95 sync error, Max sync error, tổng thời lượng và speed bounds.
  - Sửa logic gộp clip ngắn (< 1.2s) để bảo toàn danh sách `voice_refs` và mảng con `subsegments`.
- [auto_edit_pipeline.py](file:///d:/Tool/AI-Movie-Shorts/AI-Movie-Shorts/auto_edit_pipeline.py):
  - Tích hợp `resolve_timeline_with_voice_clock` vào Bước 3.5.
  - Tích hợp Pre-render validator hiển thị báo cáo P95 drift.
  - Nâng cấp `render_single_clip`: Áp dụng thực tế `setpts=PTS/{video_speed}`, accurate seek, chuẩn hóa stream (30fps, timescale 90000, PTS bắt đầu từ 0, pixel format yuv420p).
  - Tối ưu worker song song theo phần cứng: GPU NVENC giới hạn 2 workers để chống nghẽn session; CPU chạy 4 workers.
  - Viết mới và tích hợp `validate_rendered_video`: Post-render validator kiểm tra thời lượng thực tế và PTS discontinuity bằng `ffprobe`.
- [review_phim.py](file:///d:/Tool/AI-Movie-Shorts/AI-Movie-Shorts/review_phim.py):
  - Bổ sung manifest cache cho TTS và ffprobe theo text hash.
  - Sửa seek `-to` thành `-t video_dur`, chuẩn hóa `setpts` và stream output trước concat demuxer.
- [routes/video_edit.py](file:///d:/Tool/AI-Movie-Shorts/AI-Movie-Shorts/routes/video_edit.py):
  - Bổ sung `timeline_sanitized.json` vào cơ chế kiểm tra cache `review_check_cache`.
- [tests/test_review_phim_sync.py](file:///d:/Tool/AI-Movie-Shorts/AI-Movie-Shorts/tests/test_review_phim_sync.py):
  - Bộ unit test tự động toàn diện kiểm tra Resolver, mapping `voice_refs`, Speed clamping, Pre-render validator, FFmpeg setpts rendering và Multi-clip Concat PTS continuity.

## 10. Kết quả kiểm thử thực tế (Test & Benchmark Results)

Toàn bộ test suite tự động chuyên sâu đã được thực thi trên môi trường thực tế (Python 3.12, GPU RTX 5060, FFmpeg n7.1.5):

```powershell
python -m unittest tests/test_review_phim_sync.py
```

**Kết quả:**
- Ran 6 tests in 0.915s: **6/6 PASS 100%**.
- `test_resolver_schema_and_sync`: Đạt P95 sync error = 0.0 ms (yêu cầu <= 80 ms).
- `test_short_clip_merge_preserves_voice_mapping`: Bảo toàn đầy đủ danh sách `voice_refs` và `subsegments`.
- `test_speed_ratio_clamping`: Tự động clamp tốc độ trong khoảng an toàn [0.85x, 1.20x] khi LLM cắt lệch.
- `test_pre_render_validator`: Phát hiện chính xác thời lượng và độ lệch.
- `test_ffmpeg_setpts_speed_and_pts_continuity`: FFmpeg render thực tế áp dụng `setpts=PTS/speed` chuẩn xác, PTS không bị lùi.
- `test_multi_clip_concat_pts_continuity`: Concat -c copy của các clip đã chuẩn hóa đạt tính liên tục PTS 100%, không bị đứt gãy timestamp, sai số thời lượng so với voice chỉ ~33ms (<= 80ms).

Tất cả các tệp sửa đổi đã được đồng bộ 1:1 sang thư mục bản vá OTA `patches/active/` và ghi nhận chi tiết vào `TODO.md`.

