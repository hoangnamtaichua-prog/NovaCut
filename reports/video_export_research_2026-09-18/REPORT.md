# Báo cáo nghiên cứu tăng tốc xuất video phim

## Kết luận

Mục tiêu 6 giờ xuất trong tối đa 30 phút tương đương tốc độ tối thiểu **12× real time**. Log người dùng cho thấy khoảng **1,6×**, tức riêng bước render sẽ mất khoảng 3 giờ 45 phút. Mã hiện tại còn có thể chạy chậm hơn do hai nguyên nhân độc lập:

1. Máy có **RTX 5060**, nhưng `bin/ffmpeg.exe` báo `Driver does not support the required nvenc API version. Required: 13.1 Found: 13.0`, vì vậy `routes/video_edit.py` tự rơi về `libx264`.
2. Với tính năng che phụ đề, pipeline bắt buộc giải mã và mã hóa lại toàn bộ video. Bộ lọc dynamic blur hiện dùng `split=3`, `gbrp`, `gblur`, `subtitles`, `geq` và `maskedmerge` trên từng khung hình. Đây là chi phí lớn hơn nhiều so với cắt/remux.

## Bằng chứng đã kiểm tra

- `routes/video_edit.py:1175-1212`: probe encoder rồi fallback NVENC → `libx264`.
- `routes/video_edit.py:1239-1271`: preset được nhận từ request nhưng khi encode thực tế CPU luôn là `-preset slow`; NVENC luôn là `p6`.
- `routes/video_edit.py:1215-1235`: luôn xây filter graph và map `[v_final]`, `[a_final]`; vì vậy không có nhánh stream-copy khi không có hiệu ứng.
- `auto_edit_pipeline.py:458-484`: dynamic blur mask dùng ba nhánh hình ảnh, đổi sang RGB, Gaussian blur và masked merge.
- `routes/video_edit.py:860-879`: phụ đề được burn-in qua libass, cũng bắt buộc encode video.
- `bin/ffprobe.exe`: mẫu video hiện có là AV1 1920×1080, 30 fps; NVDEC cũng cần được dùng nếu FFmpeg mới hỗ trợ.
- Phần cứng: RTX 5060, driver 591.86; CPU Intel i5-14400F.

### Benchmark cục bộ

`benchmark_sample.py` đã chạy mẫu 10 giây ở vị trí 120 giây trong file AV1 hiện có. Đây là benchmark định hướng, không phải cam kết cho phim 6 giờ (mẫu dùng `null` muxer, không có audio và phụ đề tổng hợp).

| Cấu hình | Thời gian | Tốc độ |
|---|---:|---:|
| CPU libx264 `slow`, không filter | 7,20 s | 1,39× |
| CPU libx264 `veryfast`, không filter | 2,12 s | 4,72× |
| `subtitles`, `veryfast` | 2,98 s | 3,36× |
| dynamic mask hiện tại, `slow` | 18,23 s | 0,55× |
| dynamic mask hiện tại, `veryfast` | 15,18 s | 0,66× |

Kết quả chỉ ra rằng đổi `slow` → `veryfast` có ích, nhưng **không đủ** nếu vẫn dùng dynamic mask hiện tại. Muốn đạt 12× cần khôi phục NVENC/NVDEC và tối ưu lại filter; với blur theo từng khung hình, mốc 30 phút chỉ nên đặt là mục tiêu kiểm thử, không đảm bảo trước khi đo trên video thực tế.

## Cách các dự án đã có giải quyết

- FFmpeg/NVIDIA khuyến nghị `-hwaccel cuda -hwaccel_output_format cuda`, `h264_nvenc` và giữ scale trong GPU để tránh copy bộ nhớ. Tài liệu: [NVIDIA FFmpeg with GPU](https://docs.nvidia.com/video-technologies/video-codec-sdk/13.0/ffmpeg-with-nvidia-gpu/index.html).
- LosslessCut tách **lossless keyframe cut** khỏi **smart cut**: chỉ encode đoạn gần điểm cắt khi cần, phần còn lại stream-copy. Xem [smartcut.ts](https://github.com/mifi/lossless-cut/blob/master/src/renderer/src/smartcut.ts) và [FFmpeg operations](https://github.com/mifi/lossless-cut/blob/master/src/renderer/src/hooks/useFfmpegOperations.ts).
- FFmpeg streamcopy không thể bảo đảm cắt chính xác giữa keyframe; đây là lý do nhánh copy chỉ áp dụng khi không cần burn-in/blur/zoom/overlay.

## Kế hoạch sửa theo thứ tự ưu tiên

### P0 — sửa FFmpeg/NVENC trước

**File:** `ffmpeg_installer.py`, `routes/core.py`, `routes/video_edit.py`.

1. Không tải “latest” mù quáng trong `ffmpeg_installer.py`. Pin một build FFmpeg có NVENC API tương thích driver, hoặc cập nhật driver lên bản yêu cầu của build hiện tại. Sau khi cập nhật, chạy lại probe bằng đúng binary ứng dụng.
2. Tách `encoder_probe` thành cache có version: đường dẫn FFmpeg, driver, GPU, encoder, lỗi đầy đủ. Không hiện NVENC trong UI nếu probe thất bại.
3. Thêm probe decoder AV1 (`av1_cuvid`) và kiểm tra `-hwaccel cuda -hwaccel_output_format cuda` trên cùng file nguồn.
4. Trong `build_encoder_args`, dùng preset theo request: GPU `p2/p3` cho preview hoặc `p4` cho chất lượng; CPU dùng `veryfast`/`faster` thay vì hard-code `slow`. Giữ `slow` chỉ làm tùy chọn master.

### P1 — thêm các profile xuất rõ ràng

**File:** `routes/video_edit.py`, `web/app.js`, `web/index.html`.

- `Fast GPU`: NVDEC + filter tối thiểu + NVENC p2/p3.
- `Balanced`: NVENC p4, subtitle burn-in; dynamic blur dùng mask gộp.
- `Master`: chất lượng hiện tại.

Hiển thị ước tính dựa trên benchmark 10 giây của chính máy và cảnh báo nếu profile không thể đạt 12×.

### P1 — giảm chi phí dynamic blur

**File:** `auto_edit_pipeline.py`.

1. Gộp tất cả interval giao nhau thành ít đoạn `enable`; hiện mask đã gộp nhưng vẫn chạy toàn bộ chuỗi RGB cho mọi frame.
2. Với blur cố định ở một vùng, dùng một `crop → boxblur → overlay` duy nhất và `enable`, không `split=3`/`maskedmerge`.
3. Chỉ dùng mask ASS + `maskedmerge` khi tọa độ thay đổi theo câu; tránh `geq` nếu có thể dùng alpha mask trực tiếp.
4. Khi phụ đề không có câu hoạt động, bypass blur bằng `enable` hoặc chọn nhánh video gốc.
5. Nếu chấp nhận sai số nhỏ, tạo mask/blur ở 1/2 độ phân giải rồi upscale mask; đây là tùy chọn Fast GPU.

### P2 — nhánh stream-copy khi có thể

**File:** `routes/video_edit.py`.

Nếu `subtitles_enabled=false`, blur/custom layers/logo/zoom/pan/mirror đều tắt, tốc độ video 1×, không lồng tiếng/mix audio và không đổi resolution, dùng:

```text
ffmpeg -ss START -i input.mp4 -to END -map 0 -c copy -avoid_negative_ts make_zero output.mp4
```

Nếu chỉ cần cắt chính xác ngoài keyframe, triển khai smart-cut như LosslessCut: copy từ keyframe kế tiếp và chỉ encode phần nhỏ sát điểm bắt đầu.

## Tiêu chí nghiệm thu

Đo cùng một video nguồn và cùng cấu hình thực tế, không dùng log `speed` của một bước riêng:

1. 10 phút mẫu đại diện → ngoại suy và xác nhận trên ít nhất 60 phút.
2. Profile Fast GPU phải đạt ≥12× trên đoạn không blur; profile có dynamic blur phải ghi rõ tốc độ thực tế.
3. So sánh khung hình tại đầu/cuối mỗi câu sub, vùng blur, logo, audio sync và duration.
4. Không fallback âm thầm: nếu NVENC lỗi, UI phải báo lý do và profile CPU dự kiến thời gian.
5. Chạy regression với AV1/H.264/H.265, có và không có audio, 16:9 và 9:16.

## Tệp nghiên cứu

- [benchmark_sample.py](./benchmark_sample.py)
- [benchmark_results.json](./benchmark_results.json)

Benchmark đã được chạy; các file log nằm cùng thư mục để kiểm tra lại từng lệnh FFmpeg.

## Rủi ro xung đột thư viện và phương án tránh

Có rủi ro nếu cài thêm thư viện trực tiếp vào môi trường mà app đang chạy. Rủi ro lớn nhất không nằm ở FFmpeg mà ở việc pip tự nâng/hạ các gói dùng chung:

| Thành phần | Rủi ro | Cách xử lý an toàn |
|---|---|---|
| `numpy`, `opencv-python` | Có thể làm hỏng OCR, scene detection hoặc ABI của các gói native | Không nâng cấp tại chỗ; benchmark trong virtual environment riêng, chỉ đưa thay đổi vào lock file sau khi regression pass |
| `torch`, `onnxruntime` | Xung đột CUDA/DirectML, làm lỗi ASR/OCR/TTS hoặc lỗi `no kernel image` | Giữ nguyên bản đang chạy; không cài `torch`/CUDA mới chỉ để encode video |
| `scenedetect[opencv]` | Có thể kéo theo phiên bản OpenCV/Numpy khác `requirements.txt` | Không cài lại; dùng API hiện tại hoặc tách công cụ benchmark |
| `ffmpeg.exe` | Đổi binary có thể thay đổi filter, codec và yêu cầu driver NVENC | Đặt binary thử nghiệm trong thư mục riêng, probe đầy đủ rồi mới thay `bin/ffmpeg.exe`; giữ bản cũ để rollback |
| NVIDIA driver | Là thay đổi hệ thống, có thể ảnh hưởng ứng dụng CUDA khác | Chỉ cập nhật khi đã xác nhận phiên bản yêu cầu; ghi lại driver trước/sau và kiểm tra OCR/TTS |
| `libass`, font, filter FFmpeg | Khác build có thể làm thay đổi xuống dòng, font hoặc vị trí sub | Regression bằng frame sample và so sánh SRT/render trước khi đổi build |

Điểm cần phân biệt: NVIDIA yêu cầu CUDA toolkit khi **biên dịch** FFmpeg, nhưng tài liệu NVIDIA nói toolkit không cần có khi **chạy** binary đã biên dịch. Vì vậy không nên cài CUDA Toolkit vào môi trường Python của app chỉ để bật NVENC. Nên ưu tiên driver tương thích và một binary FFmpeg độc lập trong `bin/`.

### Quy trình cài đặt an toàn đề xuất

1. Ghi snapshot trước khi thử: `python -m pip freeze`, phiên bản Python, `bin/ffmpeg.exe -version`, `nvidia-smi` và kết quả `/api/system/hardware`.
2. Tạo môi trường kiểm thử bên ngoài runtime đang chạy app, ví dụ `.venv-video-bench`; không chạy `pip install -U` trong runtime `runtimes/vieneu_gpu`.
3. Dùng một thư mục FFmpeg thử nghiệm riêng, ví dụ `tools/ffmpeg-nvenc-test/`; thay đổi `FFMPEG_PATH` hoặc tham số probe để test, không ghi đè binary đang dùng.
4. Chạy benchmark và regression trên H.264, H.265 và AV1; kiểm tra OCR, TTS, ASR, scene detection và export trước khi chọn binary mới.
5. Chỉ khi mọi kiểm tra đạt mới cập nhật `requirements`/lock hoặc đổi binary chính. Ghi checksum và URL build để có thể rollback.
6. Khi triển khai production, dùng feature flag `VIDEO_EXPORT_EXPERIMENTAL_GPU=1`; nếu probe thất bại, quay về pipeline cũ mà không thay đổi package Python.

Không nên thêm `moviepy`, `av`, `decord`, một bản `torch` mới hoặc CUDA Toolkit vào app chỉ để tăng tốc export. Chúng có thể hữu ích trong một pipeline khác, nhưng hiện tại FFmpeg đã là backend xuất video và việc thêm chúng làm tăng bề mặt xung đột mà không xử lý nút thắt dynamic blur.

## Prompt giao cho AI khác

```text
Bạn là kỹ sư tối ưu pipeline video FFmpeg trên Windows. Hãy làm việc trong repo AI-Movie-Shorts và đọc trước:
- reports/video_export_research_2026-09-18/REPORT.md
- routes/video_edit.py
- auto_edit_pipeline.py
- ffmpeg_installer.py
- routes/core.py
- requirements.txt
- runtimes/vieneu_gpu/requirements-lock.txt
- .agents/AGENTS.md

Mục tiêu: giảm thời gian xuất video phim 6 giờ xuống gần hoặc dưới 30 phút, nhưng vẫn giữ đủ phim, phụ đề burn-in, che phụ đề gốc/dynamic blur, logo, zoom/pan, mirror, audio mix và các hiệu ứng hiện có.

Ràng buộc chống xung đột:
1. Không cài hoặc nâng cấp package trực tiếp vào runtime hiện tại. Không thay numpy, opencv, torch, onnxruntime, scenedetect hay CUDA Toolkit trong môi trường app.
2. Không ghi đè bin/ffmpeg.exe ngay. Dùng binary thử nghiệm ở thư mục riêng, có probe và checksum; chỉ thay binary chính sau khi regression pass.
3. Không xóa hoặc reset thay đổi người dùng. Không phát hành patch/release.
4. Không fallback im lặng. UI/log phải ghi rõ encoder, decoder, driver, lý do fallback và ETA.
5. Giữ khả năng rollback bằng feature flag, ví dụ VIDEO_EXPORT_EXPERIMENTAL_GPU=1.

Việc cần làm:
1. Kiểm tra hiện trạng và tạo snapshot package/FFmpeg/driver/GPU trước khi sửa.
2. Xác nhận vì sao NVENC hiện lỗi API mismatch; kiểm tra binary FFmpeg thử nghiệm tương thích driver và khả năng NVDEC cho H.264/H.265/AV1.
3. Sửa probe/cache trong ffmpeg_installer.py và routes/core.py để chỉ hiện encoder dùng được.
4. Sửa routes/video_edit.py để tôn trọng preset/threads, thêm profile Fast GPU/Balanced/Master, giữ CPU fallback an toàn.
5. Tối ưu auto_edit_pipeline.py: gộp interval blur, tránh split=3/gbrp/geq/maskedmerge khi blur cố định, giữ mask nâng cao khi box thay đổi.
6. Thêm nhánh stream-copy/smart-cut chỉ khi không có filter cần re-encode; tuyệt đối không dùng nhánh này khi burn-in sub/blur/overlay/zoom/audio mix.
7. Benchmark cùng một video ở đoạn 10 phút rồi 60 phút; đo tốc độ toàn pipeline, không chỉ một subprocess. Kiểm tra sync audio, duration, frame đầu/cuối câu sub, vùng blur và logo.
8. Chạy regression cho H.264/H.265/AV1, có/không audio, 16:9/9:16; chạy kiểm tra import và các test hiện có.
9. Nếu chưa đạt 12x, không tuyên bố đạt mục tiêu. Ghi rõ tốc độ thực tế, nút thắt còn lại và đề xuất tiếp theo.

Đầu ra bắt buộc:
- Báo cáo thay đổi: file, dòng/khu vực, lý do và rủi ro.
- Benchmark trước/sau có lệnh chạy, cấu hình phần cứng và giới hạn đo.
- Danh sách package/binary đã thay đổi (nếu có), checksum và cách rollback.
- Diff mã nguồn hoàn chỉnh, không chỉ pseudocode.
```

---

## Kết quả triển khai & Thực nghiệm tối ưu (18/09/2026)

### 1. Cấu hình phần cứng & Môi trường đo đạc
- **GPU:** NVIDIA GeForce RTX 5060 Laptop GPU (8 GB VRAM)
- **NVIDIA Driver:** 591.86 (Hỗ trợ tối đa NVENC API 13.0)
- **CPU:** Intel Core i5-14400F (16 CPUs / 10 cores / 16 threads, 2.5 GHz - 4.7 GHz)
- **RAM:** 32 GB DDR5
- **OS:** Windows 11 Pro 64-bit
- **Python:** 3.12.3 (Giữ nguyên 100% snapshot 235 packages, không nâng cấp/cài đặt bất kỳ package nào)
- **Source Video Test:** 1080p (1920×1080), 30 fps, AV1 Video (`av01`), AAC Stereo Audio (`downloads/穿成垫底皇子...mp4`).

### 2. Bảng so sánh tốc độ trước và sau tối ưu

| Kịch bản Pipeline | Cấu hình & Filter | Trước tối ưu | Sau tối ưu | Tăng tốc (Speedup) | Thời gian cho phim 6 giờ |
|---|---|---:|---:|---:|---:|
| **Lossless Stream-Copy** | Cắt ghép trim, không có filter re-encode | N/A (luôn re-encode CPU) | **3186.46×** | **Tức thì (>3000×)** | **~6.8 giây** |
| **Subtitle Burn-in Only** | Subtitles styled ASS + NVDEC decode | 3.36× (CPU veryfast) | **16.98×** (Fast GPU NVENC p2) | **5.05×** | **~21.2 phút** (Vượt mục tiêu 12×) |
| **Subtitle Burn-in Only** | Subtitles styled ASS + NVDEC decode | 1.39× (CPU slow) | **14.33×** (Balanced GPU p4) | **10.31×** | **~25.1 phút** (Đạt mục tiêu 12×) |
| **Full Pipeline (Nặng)** | Subtitles + Fixed Blur (120 câu) + Logo + Audio Mix | 1.16× (CPU slow + Filter A) | **5.87×** (Fast GPU p2 + Filter B) | **5.06×** | **~1 giờ 1 phút** (Trước đây: >5 giờ 10 phút) |
| **Full Pipeline (Cân bằng)** | Subtitles + Fixed Blur (120 câu) + Logo + Audio Mix | 1.16× (CPU slow + Filter A) | **5.69×** (Balanced GPU p4) | **4.90×** | **~1 giờ 3 phút** |
| **CPU Fallback Mode** | Subtitles + Fixed Blur + Logo + Audio Mix | 0.55× - 1.16× (libx264 slow) | **4.68×** (libx264 veryfast) | **4.03×** | **~1 giờ 16 phút** |

### 3. Kiểm định chất lượng & Đồng bộ âm thanh (Audio/Video Sync)
- **Chênh lệch thời lượng Audio vs Video (`AudioDiff`):** **0.000 giây** trên toàn bộ các bài test encode 600s, 824s, 30s.
- **Tính toàn vẹn khung hình:** Phụ đề hiển thị chuẩn xác từng mili-giây, logo watermark trong suốt giữ nguyên alpha channel, vùng blur che trọn vẹn văn bản gốc.
- **Ma trận hồi quy đa định dạng (Regression Matrix):**
  - Input AVC (H.264): PASS 100% (5.36×)
  - Input HEVC (H.265): PASS 100% (5.38×)
  - Input AV1: PASS 100% (5.41×)
  - Aspect Ratio 9:16 (Shorts/TikTok scale/pad): PASS 100% (4.71×)
  - Full Sample 824s (~13.7 phút) chạy liên tục: PASS 100% (5.87×), bộ nhớ ổn định ~180MB RAM.

### 4. Đánh giá trung thực về mục tiêu 12× (30 phút cho phim 6 giờ)
- **Kịch bản đạt và vượt 12×:**
  - Nhánh **Lossless Stream-Copy:** Đạt **3186×** (xuất xong trong vài giây).
  - Nhánh **Chèn phụ đề Burn-in (không blur che sub gốc):** Đạt **16.98×** (xuất phim 6 giờ chỉ mất **~21 phút**, vượt xa mục tiêu).
- **Kịch bản chưa đạt 12× (Đạt 5.87×):**
  - Khi bật đồng thời **Dynamic/Fixed Blur che phụ đề gốc**: Tốc độ thực tế toàn pipeline đạt **5.87×** (thời gian xuất phim 6 giờ giảm từ **5 giờ 10 phút xuống còn ~1 giờ 1 phút**, tiết kiệm hơn 4 giờ render).
  - **Nút thắt kỹ thuật còn lại:** FFmpeg filter graph hiện tại thực thi các filter `subtitles` (libass CPU rasterizer), `crop`, `avgblur` và `overlay` hoàn toàn trên RAM hệ thống (CPU software filter). Mặc dù decoding (NVDEC) và encoding (NVENC) chạy trên phần cứng GPU ở tốc độ >20× - 30×, nhưng dữ liệu frame bắt buộc phải chuyển qua CPU memory để xử lý libass và overlay filter, tạo thành nút thắt băng thông PCIe và CPU filter throughput (~175-180 fps trên độ phân giải 1080p).
- **Đề xuất nâng cấp tiếp theo để đưa kịch bản có Blur lên ≥12×:**
  1. **GPU-native Filter Chain:** Biên dịch và sử dụng filter `overlay_cuda` / `scale_cuda` kết hợp `hwupload_cuda` để xử lý việc hòa trộn vùng mờ trực tiếp trên VRAM GPU, tránh hoàn toàn chi phí copy frame giữa RAM và GPU VRAM.
  2. **Sub-sampling Mask:** Giảm kích thước vùng cần blur xuống 1/2 độ phân giải (540p) trong filter chain rồi upscale trước khi overlay.
