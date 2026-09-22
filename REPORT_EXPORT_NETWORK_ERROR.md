# Báo cáo chẩn đoán và yêu cầu sửa lỗi xuất video bị “network error”

Ngày: 21/09/2026. Nguồn: ảnh log người dùng gửi và kiểm tra tĩnh mã nguồn hiện tại. Chưa tái hiện phiên xuất lỗi, chưa có log backend của phiên đó; tài liệu không khẳng định nguyên nhân gốc đã được xác định. Yêu cầu hiện tại chỉ lập báo cáo, chưa sửa code.

## 1. Kết luận để giao việc

Thông báo trực tiếp là **giao diện gặp exception khi chạy/đọc luồng kết quả xuất video**, được hiển thị thành “Lỗi kết nối tới Server: network error”. Không đủ bằng chứng kết luận Internet yếu, FFmpeg lỗi, GPU lỗi hoặc vùng blur bị treo.

Có những vấn đề xác nhận được trong source cần sửa: các công đoạn dài thiếu log/heartbeat; việc render nằm trong generator HTTP; giao diện bắt lỗi quá chung và không đối soát trạng thái job; parser streaming không giữ chunk chưa hoàn chỉnh. Riêng việc tách giọng chạy im lặng ngay sau log cuối cùng là **giả thuyết ưu tiên kiểm tra nếu người dùng bật xóa giọng gốc**, chưa phải kết luận cho phiên này.

Mục tiêu sửa: xác định chính xác đang chạy công đoạn nào, lưu bằng chứng trước khi mất kết nối, không hủy render chỉ vì UI mất kết nối, không tạo lại 1.213 câu TTS vô ích, báo thành công/thất bại/hủy dựa trên trạng thái backend.

## 2. Diễn biến nhìn thấy trong ảnh

| Thời điểm | Nội dung | Diễn giải có căn cứ |
|---|---|---|
| 21:52:52 | Tạo xong 1213/1213 câu; ghép timeline bằng NumPy | TTS đã báo hoàn thành toàn bộ câu; 100% này không phải 100% xuất video |
| 21:52:55 | Đã tạo và đồng bộ xong track âm thanh lồng tiếng AI | Đã qua bước ghép track theo log; chưa xác nhận chất lượng file bằng kiểm tra thực |
| 21:52:56 | Đang khởi chạy FFmpeg, encoder auto, 16 luồng, preset faster, FAST GPU | Đây là log chuẩn bị; trong source nó xuất hiện trước Popen encode thực |
| 21:52:56 | Tùy chọn chèn phụ đề đang tắt | Không burn-in phụ đề là cấu hình hiện tại, không phải lỗi được ảnh chứng minh |
| 21:52:56 | Đang xử lý 1 vùng làm mờ và chữ động | Đã đến xây filter custom layer; dòng tổng quát không cho biết layer là blur hay text |
| 23:11:27 | Lỗi kết nối tới Server: network error | Cách log trước 1 giờ 18 phút 31 giây; không thấy SUCCESS/FAILED/exit code |

Ảnh không có kích thước/thời lượng nguồn, setting stem, RAM/VRAM, GPU thực được chọn, log console backend, PID hoặc file đầu ra. Không suy ra timeout cố định 78 phút hay dùng số “2333.1s” cạnh câu TTS làm thời gian chờ mạng.

## 3. Điểm mã nguồn liên quan

Số dòng tham khảo có thể thay đổi. AI sửa phải tìm lại theo tên hàm và chuỗi log, kiểm tra cả chế độ source/patch overlay đang chạy.

### A. Catch giao diện quá rộng và SSE parser thiếu buffer

`web/app.js` khoảng 1120–1214: gọi POST `/api/start`, lấy `response.body.getReader()`. Mỗi chunk đang được `decoder.decode(value)` rồi `chunk.split('\n')`, không giữ phần còn lại và không dùng streaming decoder.

Hệ quả có thể xảy ra: một sự kiện JSON/nhãn SUCCESS bị chia giữa hai chunk sẽ không được parse đúng; UTF-8 tiếng Việt có thể hỏng khi byte bị cắt. Đây là lỗi độc lập xác nhận qua source, **không đủ giải thích trực tiếp network error trong ảnh**.

Khối catch dùng chung cho request, đọc stream và logic trong try; mọi exception không phải AbortError đều ghi “Lỗi kết nối tới Server”. `exportFailedEvent` được thu thập nhưng UI cuối vẫn báo thất bại chung; CANCELLED bị bỏ qua. EOF không có SUCCESS bị coi là lỗi mà không hỏi trạng thái backend.

Trong cùng file còn có thông báo tương tự cho OCR quanh dòng 5472; không sửa nhầm chỉ nhánh OCR vì ảnh là luồng xuất.

### B. Log “khởi chạy FFmpeg” xuất hiện sớm

`routes/video_edit.py` khoảng 792 phát log trước khi xây filter, custom layers, stem separation, cấu hình audio, phát hiện encoder và gọi Popen khoảng 1471. Không thể dùng log đó làm bằng chứng FFmpeg render đã chạy suốt 78 phút.

### C. Điểm nghi vấn công đoạn dài sau log cuối

`routes/video_edit.py` khoảng 1072 phát log custom layers. Sau vòng xây filter là mục `3.6 AI Stem & Vocal Separation` khoảng 1210 trở đi:

```python
sep_res = audio_separator.separate_audio_stems(
    input_video, output_dir=temp_stem_dir,
    mode=stem_mode, device=stem_device
)
```

Chỉ chạy nếu `stem_enabled and has_orig_audio`, và không có cleaned SFX hợp lệ để tái sử dụng. Lời gọi đồng bộ không truyền `progress_cb`, `logger_cb`, `cancel_check_cb`, dù `audio_separator.py::separate_audio_stems` hỗ trợ cả ba và chuyển xuống `mdx_separator`.

Nếu nhánh này được bật, UI có thể đứng ở log “Lớp phủ tùy chọn” trong lúc thực tế đang trích audio/tách giọng. Nếu setting tắt, phải loại giả thuyết này. Các bước phát hiện phần cứng hoặc xử lý khác sau đó cũng cần stage log để phân biệt.

### D. Vòng đời công việc phụ thuộc stream

Route `/api/start` trả `Response(generate(), mimetype='text/event-stream')`. Generator chứa cả công việc nặng. Ở cuối có `except GeneratorExit: _terminate_process_tree(process)` và finally đặt `_export_active = False`.

Khi server đóng generator do client ngắt, tiến trình encode được tham chiếu có thể bị kết thúc. Việc phát hiện disconnect không nhất thiết xảy ra ngay khi đường truyền ngắt, nhất là khi generator đang mắc trong lời gọi đồng bộ. Không có cơ chế job độc lập để UI kết nối lại và biết kết quả chắc chắn.

Kiểm tra thêm nhánh stream-copy dùng `proc_sc`, còn cleanup GeneratorExit dùng `process`; cần thống nhất quản lý child process, tránh sót tiến trình hoặc giữ tham chiếu cũ. Đây là rủi ro ở nhánh khác, không phải nguyên nhân ảnh vì ảnh có custom layer nên không đủ điều kiện stream-copy.

### E. Trạng thái và chẩn đoán còn thiếu

- `/api/export_status` hiện chỉ trả `{active: bool}`; không có job ID, stage, kết quả, path, lỗi hoặc thời điểm cập nhật.
- Vòng đọc FFmpeg dùng blocking `stdout.readline()`; nếu không có output thì không có heartbeat từ vòng đó.
- Hồ sơ `export_failure_diagnostic_*.log` chủ yếu được ghi sau nhánh FFmpeg thất bại có kiểm soát. Nếu kẹt ở stem, crash Python hoặc stream bị ngắt trước đó, có thể không có hồ sơ này.
- `web_app.py` chạy app ở `127.0.0.1:5000`; thông báo server có thể là kết nối local, không đồng nghĩa mất Internet. Cần xác nhận bản người dùng thực sự chạy cùng cấu hình.
- TTS có cache `dubbed_timeline.wav` trong `editor_temp_dir`, nhưng `use_cache=False` có thể dọn thư mục trước chạy. Chưa được chạy lại/xóa cache khi chưa sao lưu bằng chứng.

## 4. Các giả thuyết và cách kiểm chứng

| Giả thuyết | Ưu tiên | Bằng chứng phải lấy |
|---|---|---|
| Stem separation chạy lâu, không có tiến độ ra UI | Cao nếu bật xóa giọng gốc | Payload đã che bí mật, stage start/end, log MDX, CPU/GPU, cleaned_path |
| Stream bị đóng trong khoảng im lặng | Cao để kiểm tra | DevTools Network/console, log server disconnect, heartbeat, PID còn sống tại thời điểm lỗi |
| Backend crash/OOM/lỗi thư viện native | Có thể | Python stderr, Windows Application Error, peak RAM/VRAM, PID biến mất, exit code |
| FFmpeg bị treo hoặc lỗi filter/encoder | Có thể, chưa thấy log launch thật trong ảnh | Popen start/PID, command đã lọc bí mật, filter script, stderr, exit code |
| Người dùng reload/đóng UI, máy sleep hoặc WebView lỗi | Có thể | Mốc reload/sleep, lifecycle UI/server, tái hiện disconnect có kiểm soát |
| Parser SSE làm sai kết quả cuối | Lỗi source đã thấy | Test split byte/chunk; không đánh đồng với nguyên nhân transport bị ngắt |

Không chữa bằng cách tắt blur, tắt stem, chuyển CPU, tăng timeout tùy tiện hoặc giảm số câu TTS. Chỉ đổi cấu hình khi có bằng chứng và không âm thầm thay yêu cầu đầu ra.

## 5. Thu thập bằng chứng trước khi sửa sâu

1. Xác định phiên bản đang chạy, executable Python/app, source gốc hay `patches/active`; ghi hash/mtime module liên quan. Repo đang có nhiều thay đổi chưa commit, không reset hoặc copy đè hàng loạt.
2. Giữ nguyên `dubbed_timeline.wav`, `dubbing_temp`, filter graph, file output dở và log hiện có. Tìm đúng temp bằng `get_editor_temp_dir(output_dir, input_video)`; không quét/xóa tất cả output của người dùng.
3. Lấy cấu hình tối thiểu: nguồn và output, duration/resolution/fps/codec, TTS mode, use_cache, custom layer đã sanitize, stem enabled/model/device/precomputed path, encoder/profile/threads.
4. Xem backend có sống không, status endpoint có phản hồi không; ghi trạng thái Python/FFmpeg/MDX. Một ảnh chụp hiện tại không chứng minh trạng thái tại 23:11:27, phải ghi rõ thời điểm lấy.
5. Bổ sung log ra file từ lúc nhận job, gồm UTC timestamp, monotonic elapsed, job ID, stage, start/end, child PID, progress, exit code và traceback Python. Giữ log có giới hạn/rotation, không lưu token hoặc toàn bộ lời thoại.
6. Tái hiện với clip ngắn, trước tiên cùng loại layer, sau đó bật/tắt stem có kiểm soát để cô lập. Không bắt người dùng tạo lại 1.213 câu chỉ để kiểm tra lớp phủ.

## 6. Phương án sửa

### Giai đoạn 1 — Quan sát đúng và sửa lỗi riêng lẻ

- Đổi log sớm thành “Đang chuẩn bị cấu hình xuất video”. Chỉ ghi “FFmpeg đã khởi chạy” sau Popen thành công, kèm PID và encoder thực.
- Stage rõ ràng: preparing → dubbing → mixing → separating → building_filters → encoding → finalizing. Trình tự thực có thể khác, phải log theo công việc thực tế.
- Truyền callbacks progress/logger/cancel của stem. Callback đẩy event vào queue; không cố `yield` từ callback đồng bộ rồi cho rằng client nhận được heartbeat.
- Sửa parser SSE chung: `TextDecoder.decode(value, {stream:true})`, buffer qua chunk, nhận LF/CRLF, tách event theo dòng trống, xử lý `data:` nhiều dòng và comment heartbeat. Flush decoder và xử lý EOF theo quy tắc, không coi event dở là SUCCESS.
- Tách lỗi HTTP/start, đọc stream, parse event và cập nhật UI. Catch transport hiển thị “Mất kết nối cập nhật tiến độ — đang kiểm tra trạng thái xuất”, không tự khẳng định render thất bại.
- Bổ sung structured terminal state; không coi HTTP 200/EOF là thành công; CANCELLED phải có trạng thái riêng.

Chỉ thêm một `yield heartbeat` trước lời gọi stem hoặc sau `readline` không giải quyết khoảng im lặng bên trong lời gọi blocking. Cần worker/queue để kênh stream phát heartbeat độc lập.

### Giai đoạn 2 — Tách job xuất khỏi kết nối UI (khuyến nghị)

Job manager sở hữu công việc, stop event, child process, stage, kết quả và log. Worker tiếp tục chạy khi người dùng đổi tab/reload hoặc subscription ngắt; chỉ yêu cầu hủy rõ ràng mới dừng job. Duy trì giới hạn số job hiện tại, không tự mở render đồng thời gây tràn tài nguyên.

API đề xuất:

| API | Vai trò |
|---|---|
| `POST /api/export/jobs` | Validate quyền/input, tạo job, trả 202 `{job_id}`; start request có idempotency key để retry không tạo job trùng |
| `GET /api/export/jobs/<id>` | Trả state, stage, progress, updated_at, last_progress_at, output/error |
| `GET /api/export/jobs/<id>/events?after=<seq>` | SSE chỉ subscribe, event ID tăng dần, replay giới hạn, heartbeat 10–15 giây |
| `POST /api/export/jobs/<id>/cancel` | Yêu cầu hủy idempotent, đưa về cancelling rồi cancelled khi worker/child đã dừng |

Tách state backend `queued/running/cancelling/succeeded/failed/cancelled/interrupted` khỏi connection state frontend `connected/reconnecting/disconnected`. Mỗi job chỉ một terminal state. Chốt state trước khi gửi event; không được đổi success thành failed chỉ vì client biến mất sau khi hoàn tất.

Frontend mất stream thì GET job status và reconnect có backoff hữu hạn; không POST xuất mới. Nếu server không truy cập được, giữ “Chưa xác định được trạng thái”, cung cấp Thử kết nối lại. Khi server sống trở lại, phục hồi trạng thái từ job ID. Sau backend restart, job running cũ phải thành interrupted trừ khi có cơ chế reconcile tiến trình thực; không tự tuyên bố resume FFmpeg hoặc success.

Lưu metadata/snapshot job bền vững trong user data bằng ghi atomic/SQLite, không ghi đè cấu hình chung. Worker registry quản lý mọi child thuộc job, không chỉ FFmpeg cuối. Stream subscriber chậm không được chặn render hoặc gây queue không giới hạn: lưu trạng thái cuối riêng, giới hạn buffer log và báo gap/reload snapshot khi cần.

Hủy: truyền stop event tới TTS/MDX, kiểm tra giữa các stage; với lời gọi native không hủy hợp tác được, đánh giá worker process riêng để có thể dừng an toàn, không giả vờ thread đã dừng. Đóng pipe/wait/terminate tree theo timeout hữu hạn, không kill mọi python.exe/ffmpeg.exe trên máy. Lock chỉ nhả khi tài nguyên job đã giải phóng.

Watchdog phân biệt heartbeat còn sống và progress thật. Không kill job chỉ vì không có frame trong 60 giây: stem, tải model, finalize MP4 có thể dài. Báo stage im lặng và cung cấp hủy, ghi bằng chứng trước khi áp dụng deadline theo stage được cấu hình.

Giữ tương thích `/api/start`, `/api/stop_export`, `/api/export_status` hoặc cập nhật toàn bộ caller, gồm `web/js/features/batch_editor.js`. Nếu dùng adapter cũ, adapter cũng phải subscribe vào job, không quay lại sở hữu render trong generator. Giữ kiểm tra license frontend/backend và security path, không mở endpoint điều khiển job không bảo vệ.

### Giai đoạn 3 — Bảo toàn TTS và đầu ra

Không tái dùng cache chỉ dựa trên file tồn tại/size >1000. Thêm manifest/fingerprint gồm source identity, phụ đề/nội dung, giọng/model, tốc độ và tham số ảnh hưởng timeline; kiểm tra WAV đọc được, sample rate/channels/duration phù hợp. Cache không khớp phải báo và tạo lại đúng phần cần thiết.

Khi mạng đứt, không xóa TTS/cache của job còn chạy. Khi render lỗi, giữ cache hợp lệ để retry encode. Khi sửa blur/encoder nhưng không sửa TTS/timeline, có thể tái sử dụng track hợp lệ. Hết hạn cache phải có chính sách riêng, không dọn tùy tiện lúc người dùng thử kết nối lại.

Encode vào file tạm riêng của job trên cùng volume output, validate thành công rồi finalize theo chính sách ghi đè hiện có. Bảo toàn video cũ nếu lần mới thất bại; không coi file cũ cùng tên là output thành công của job mới. Nếu tính năng lịch sử xuất được triển khai, chỉ ghi một lần sau finalize thành công, không ghi khi chỉ reconnect UI.

## 7. Giao diện sau sửa

Giữ dark mode của app: nền `#070a13`, panel `#111827`, viền `#1f2937`, chữ chính `#f8fafc`, chữ phụ `#94a3b8`, cyan `#0ea5e9`. Warning vàng `#fbbf24`, failed đỏ `#f87171`, success xanh `#4ade80`. Có nhãn và icon, không chỉ đổi màu.

```text
Đang xuất video                         [Dừng xuất]
Bước hiện tại: Tách giọng gốc
Tiến độ bước này: 42% | Đã chạy: 00:12:34
TTS: Đã tạo xong 1.213/1.213 câu
Kết nối tiến độ: Đang kết nối lại…
Chưa xác nhận tác vụ đã dừng. Đang kiểm tra trạng thái máy chủ.
[Thử kết nối lại] [Xem nhật ký]
```

Không hiển thị 100% tổng khi TTS vừa xong; nếu chưa có cách tính tổng đáng tin, chỉ hiển thị tiến độ stage. Không bịa ETA cho stem nếu callback không cung cấp số liệu. Trạng thái kết nối mất không mở khóa nút tạo job mới trong khi job cũ chưa rõ kết quả; vẫn cho người dùng tra trạng thái và thao tác hủy có xác nhận từ backend. Khi terminal: hiển thị đúng path hoặc lý do lỗi/cancel/interrupted và nút mở log. Dùng toast/modal app, không alert/confirm native.

## 8. Kiểm thử bắt buộc

| Ca kiểm thử | Kết quả phải đạt |
|---|---|
| Clip ngắn TTS + một blur, không stem | Encode hoàn tất, đúng âm thanh/hình ảnh |
| Cùng clip bật stem | Thấy separating progress; có log bắt đầu/kết thúc; không im lặng vô hạn |
| Stage giả lập blocking vài phút | Heartbeat tiếp tục, status API phản hồi, subscriber không chặn worker |
| Ngắt stream/reload giữa TTS, stem, encode, finalize | Job không bị hủy vì disconnect, kết nối lại đúng job, không chạy lại TTS |
| Mất kết nối ngay sau success | GET status vẫn trả success/path; không báo render failed |
| SSE chia từng byte, UTF-8, JSON/event chia nhiều chunk, LF/CRLF | Parser khôi phục đúng; SUCCESS/FAILED/CANCELLED chỉ xử lý một lần |
| SSE EOF không có terminal event | Đối soát status, không tự success hoặc render lại |
| Cancel ở mỗi stage, bấm cancel lặp | Có phản hồi, child process đúng job được dừng, không còn orphan |
| Stream-copy disconnect/cancel | Không sót proc_sc hoặc kẹt export lock |
| FFmpeg filter lỗi, encoder lỗi, disk full/quyền ghi lỗi | Error có stage/exit code/log; không gọi chung network error |
| Python worker/server crash mô phỏng | Trạng thái interrupted/unknown phù hợp; giữ log/cache; không tự success |
| Cache đúng/sai giọng, phụ đề, tốc độ, source | Chỉ tái dùng đúng fingerprint; WAV hỏng không được tái dùng |
| Cùng path có video cũ, lần xuất mới lỗi | Không mất video cũ; không báo success dựa vào file cũ |
| Subscriber rất chậm và nhiều reconnect | Bộ nhớ bị giới hạn, không duplicate job, không duplicate terminal/history |
| Batch editor và các endpoint cũ | Không phá caller hiện có; đủ quyền frontend/backend |

Unit test dùng fake worker/clock/stream và thư mục tạm, mock launch/kill. Integration dùng video tổng hợp ngắn và ffmpeg thật sẵn có. Chạy thử lâu có kiểm soát với cấu hình gần ca người dùng sau khi clip ngắn pass; dùng lại TTS hợp lệ nếu có, tránh chi phí tạo lại 1.213 câu. Đo peak RAM/VRAM, thời gian stage, khoảng heartbeat, cancel latency và số child còn sống.

Khi demo/test trực tiếp UI, tuân thủ repo dùng trình duyệt có giao diện nhìn thấy. Ghi lệnh test, kết quả thật và ca chưa chạy. Compile pass không đồng nghĩa đã xác minh hết ca mất kết nối hoặc MDX dài.

## 9. Tiêu chí nghiệm thu và bàn giao

- Có bằng chứng xác định hoặc loại trừ stem/FFmpeg/backend crash cho ca tái hiện; nếu chưa tái hiện thì ghi nguyên nhân còn chưa xác định.
- Không còn chỉ thấy “Lớp phủ tùy chọn” trong lúc thực tế đang chạy stage khác mà không có status/log.
- Mất stream không làm mất công việc hoặc khiến tạo lại giọng; hủy chỉ theo thao tác hủy/job policy rõ ràng.
- Kết quả cuối lấy từ backend, parser chịu được chunk tùy ý, terminal state nhất quán.
- Có log bền vững, giới hạn dung lượng, không chứa bí mật; cache/output cũ được bảo toàn.
- AI bàn giao diff, giải thích nguyên nhân có bằng chứng, ảnh UI thực và test report. Cập nhật TODO mục chờ phát hành khi đã sửa xong, không tự publish/đóng patch.zip.

Phạm vi tài liệu này là lỗi xuất/streaming. Không bắt buộc triển khai toàn bộ tính năng lịch sử ở báo cáo trước trong cùng lần sửa; chỉ bảo đảm hai phần có thể tích hợp sau.
