# Báo cáo rà soát chức năng Biên tập hàng loạt

## Phạm vi

Đã rà luồng từ giao diện `viewBatchEditor` đến module `web/js/features/batch_editor.js`, các API phụ trợ SRT/chọn file, và API xuất dùng chung của Biên tập phim tại `routes/video_edit.py`. Phần `batch_queue_manager.py`/`web/js/features/batch_queue.js` không thuộc phạm vi chính của báo cáo này.

## Kết luận

Chức năng hiện có khung giao diện và cơ chế tái sử dụng Editor rất tốt, nhưng chưa thể chạy ổn định vì cấu hình gửi từ Batch Editor không đồng nhất với schema mà `/api/start` đang nhận. Lỗi nghiêm trọng nhất là tên trường giọng đọc/âm lượng, đọc SRT sai HTTP method, tự ghép SRT dù file không tồn tại, và cách đọc SSE không an toàn khi một message bị chia giữa nhiều chunk mạng.

Nên sửa theo hướng chuẩn hóa Batch Editor thành một lớp điều phối gọi lại pipeline `/api/start` của Biên tập phim, không tạo pipeline render mới.

## Lỗi cần sửa theo mức độ ưu tiên

### P0 — Chặn chạy đúng cấu hình

1. **Sai tên trường cấu hình lồng tiếng**
   - Vị trí: `web/js/features/batch_editor.js:898-976`.
   - Batch gửi `dubbing.voice`, `voice_vol`, `orig_vol`, `ducking`.
   - Backend đọc `dubbing.voice_id`, `voice_volume`, `original_volume`, `audio_ducking` tại `routes/video_edit.py:744-810` và `1209-1266`.
   - Hậu quả: giọng người dùng chọn bị bỏ qua và rơi về voice mặc định; âm lượng/ducking không áp dụng.
   - Cách sửa: đổi payload về đúng schema hiện có:
     - `voice_id: voiceInput`
     - `voice_volume: voiceVol / 100`
     - `original_volume: origVol / 100`
     - `audio_ducking: ducking`
     - `mode: 'tts'`
     - nếu cần tách giọng: dùng đúng các khóa mà Editor đơn lẻ đang gửi (`remove_original_vocals`, `stem_separation.enabled`, `stem_separation.mode`, `stem_separation.device`, `stem_separation.keep_sfx`).
   - Không đổi backend chỉ để tương thích tên riêng của Batch Editor; hãy dùng schema của Editor đơn lẻ làm chuẩn.

2. **Batch chỉ nhận `[EVENT:SUCCESS]` nhưng không lấy path thực tế từ event**
   - Vị trí: `web/js/features/batch_editor.js:1087-1141`.
   - Backend gửi JSON chứa `path` tại `routes/video_edit.py:865`, `1529`.
   - Batch tự dựng `outputPath = outDir + '/' + outName`, dễ sai khi backend chuẩn hóa đường dẫn, đổi tên, hoặc dùng separator Windows.
   - Cách sửa: parse JSON sau `[EVENT:SUCCESS]`, lưu `item.outputPath = event.path`; chỉ fallback bằng `path.join` khi event không có path.

3. **Parser SSE làm mất message khi chunk mạng bị cắt giữa dòng**
   - Vị trí: `web/js/features/batch_editor.js:1093-1137`.
   - `decoder.decode(value).split('\\n')` xử lý từng chunk độc lập; message bị chia đôi sẽ không nhận được `EVENT:SUCCESS/FAILED`.
   - Cách sửa: dùng buffer tích lũy; nối chunk vào buffer, tách theo `\n\n` hoặc `\n`, giữ phần chưa hoàn chỉnh cho lần đọc tiếp theo; dùng `new TextDecoder().decode(value, {stream:true})` và flush decoder sau khi reader kết thúc.

4. **Không kiểm tra thành công dựa trên file đầu ra**
   - Vị trí: `web/js/features/batch_editor.js:1139-1155`.
   - Nếu stream kết thúc bất thường nhưng không có event, item bị đánh lỗi không rõ nguyên nhân; nếu backend phát success nhưng file chưa hoàn tất thì UI đánh dấu xong quá sớm.
   - Cách sửa: yêu cầu event success có `path`, kiểm tra backend đã xác nhận file; nếu thiếu event thì báo lỗi “stream kết thúc bất thường”, giữ `errorMsg` và cho Retry.

### P1 — Lỗi chức năng thường gặp

5. **Gọi sai API đọc SRT**
   - Vị trí: `web/js/features/batch_editor.js:310` và `604`.
   - Frontend gọi `GET /api/read_srt?path=...`; backend chỉ đăng ký `POST /api/read_srt` và nhận JSON `{srt_path}` tại `routes/subtitles.py:308-356`.
   - Hậu quả: SRT được chọn nhưng không nạp được subtitle array.
   - Cách sửa: dùng `POST`, body JSON `{srt_path: normPath}`; xử lý `response.ok`, lỗi 404/413 và thông báo cụ thể.
   - Có thể dùng `/api/subtitles/parse_file` nếu muốn dùng parser tolerant mới; chọn một API duy nhất, không duy trì hai cách đọc.

6. **`autoPairVideosAndSrts()` gán đường dẫn SRT ảo mà không kiểm tra tồn tại**
   - Vị trí: `web/js/features/batch_editor.js:407-418`.
   - Hàm đặt `item.srtPath = videoPath thay extension + '.srt'` ngay cả khi file không tồn tại; Batch sau đó lọc item là “đủ điều kiện” và backend từ chối `manualSrt`.
   - Cách sửa: gửi request kiểm tra/đọc SRT trước khi chuyển trạng thái `ready`; chỉ đặt `srtPath` khi file tồn tại và được phép. Nếu không tồn tại, giữ `pending` và hiển thị “Không tìm thấy SRT”.

7. **Đường dẫn SRT `.vtt/.ass` được nhận ở UI nhưng backend `manualSrt` chỉ cho `.srt`**
   - Vị trí: `batch_editor.js:210-247`, `routes/video_edit.py:389-395`.
   - Cách sửa: hoặc giới hạn UI chỉ nhận `.srt`, hoặc chuyển `.vtt/.ass` qua parser/export thành SRT trước khi gửi `/api/start`. Không gửi trực tiếp extension backend không chấp nhận.

8. **Chọn “bỏ qua video thiếu SRT” nhưng vẫn có thể xử lý dữ liệu không hợp lệ**
   - Vị trí: `batch_editor.js:1005-1018`.
   - `queue` chỉ kiểm tra có chuỗi `srtPath`, không kiểm tra file tồn tại; subtitle array có thể rỗng.
   - Cách sửa: preflight từng item: video tồn tại, SRT tồn tại hoặc subtitle array hợp lệ, đường dẫn được backend cho phép; hiển thị danh sách bị loại trước khi chạy.

9. **Dừng hàng loạt dùng cờ global `/api/stop_export`**
   - Vị trí: `batch_editor.js:1174-1191`, backend `routes/video_edit.py:1637-1648`.
   - Cờ dừng là global; request AbortController có thể đóng stream nhưng backend vẫn đang xử lý một khoảng thời gian. Cần chờ event cancelled/failed hoặc xác nhận process đã dừng trước khi cho chạy Batch tiếp.
   - Cách sửa: sau abort gọi stop một lần, đặt trạng thái item hiện tại về `pending/cancelled`, khóa nút Start đến khi request hiện tại kết thúc; không cho khởi động phiên xuất thứ hai khi `_export_active` còn true.

### P2 — Độ bền dữ liệu và trải nghiệm

10. **LocalStorage lưu tối đa 50 item nhưng không lưu đủ cấu hình/trạng thái lỗi**
    - Vị trí: `batch_editor.js:57-77`.
    - Không lưu global preset, selected đầy đủ, progress/error chi tiết; reload làm mất thiết lập người dùng.
    - Cách sửa: lưu schema có `version`, `items`, `globalConfig`, `outputDir`; loại bỏ dữ liệu nhị phân nhưng giữ subtitle metadata cần thiết. Khi khôi phục, migrate version và reset `processing` về `pending`.

11. **ID dùng `Date.now()+Math.random()` và thao tác theo index**
    - Vị trí: `batch_editor.js:268-283`, toàn bộ render/event dùng `data-index`.
    - Trong lúc render async hoặc xóa dòng, index có thể trỏ nhầm item.
    - Cách sửa: dùng `data-id`, tìm item bằng ID; giữ index chỉ để hiển thị thứ tự.

12. **Modal mượn trực tiếp DOM/state của Editor đơn lẻ nhưng không snapshot/khôi phục state**
    - Vị trí: `batch_editor.js:669-711`, `web/app.js:5532-5565`.
    - `loadVideoToEditor()` và `returnTopRowToEditor()` dùng state global (`srtData`, `currentRegion`, player). Mở nhiều item liên tiếp hoặc đóng bằng nhiều đường có thể làm rò trạng thái sang Editor đơn lẻ.
    - Cách sửa: trước khi mở modal lưu snapshot state Editor; khi Save chỉ lấy dữ liệu cần thiết (`subtitles`, `ocrRegion`, SRT path); khi Cancel khôi phục snapshot; khi đóng modal luôn dọn listener/player. Vẫn tái sử dụng UI và hàm Editor hiện có.

13. **Lưu modal chỉ lưu subtitle, chưa lưu chắc chắn vùng OCR/biên tập hình ảnh**
    - Vị trí: `batch_editor.js:727-769`.
    - `item.ocrRegion` được gửi khi export nhưng không thấy cập nhật từ vùng đang vẽ trong Editor.
    - Cách sửa: expose getter dùng chung từ Editor, ví dụ `window.getEditorOcrRegion()`, lấy giá trị khi Save; không tự viết lại canvas/drag logic.

14. **Gọi `renderBatchTable()` trong từng progress event gây render lại toàn bảng**
    - Vị trí: `batch_editor.js:1126-1133`.
    - Với nhiều item/progress dày, UI giật và mất focus.
    - Cách sửa: throttle 100–250 ms hoặc cập nhật riêng progress cell; chỉ render toàn bảng khi thêm/xóa/đổi trạng thái.

15. **Nhiều tác vụ async không có thông báo lỗi đầy đủ**
    - Vị trí: `batch_editor.js:304-331`, `381-403`, `595-613`.
    - Nhiều `catch(e) {}` nuốt lỗi.
    - Cách sửa: ghi log item/file, hiển thị trạng thái “SRT không đọc được”, tiếp tục item khác; không để lỗi im lặng.

## Nên tận dụng từ Biên tập phim hiện có

1. **Giữ `/api/start` là engine xuất duy nhất**: Batch chỉ tạo payload cho từng video rồi đọc SSE. Không viết FFmpeg/TTS/blur/subtitle renderer mới.
2. **Tái sử dụng schema payload trong `web/app.js:854-930`**. Tách phần tạo config thành hàm dùng chung, ví dụ `window.buildEditorExportConfig(overrides)`. Batch truyền `inputVideo`, `manualSrt`, `subtitles`, `outputDir`, `outputName`, và preset chung.
3. **Tái sử dụng `window.loadVideoToEditor`, `window.getEditorSrtData`, `window.returnTopRowToEditor`** nhưng bổ sung snapshot/restore và getter OCR thay vì sao chép giao diện xử lý subtitle.
4. **Tái sử dụng `/api/subtitles/parse_file` hoặc `/api/read_srt`**; chuẩn hóa một parser duy nhất.
5. **Tái sử dụng `/api/editor/check_cache` và cache của Editor** để tránh OCR/ASR/TTS lặp lại. Batch nên chạy preflight cache trước khi xuất, tương tự luồng đơn lẻ.
6. **Tái sử dụng `generate_styled_ass()` và toàn bộ pipeline `routes/video_edit.py`** cho style subtitle, blur, logo, tốc độ, aspect ratio, stem separation.

## Kiến trúc sửa đề xuất

### Bước 1 — Chuẩn hóa contract

Tạo một hàm JS dùng chung để trả về payload đúng schema Editor đơn lẻ. Batch không tự đặt tên khóa mới. Thêm kiểm tra schema ở frontend trước khi gọi API và log payload đã loại bỏ dữ liệu nhạy cảm.

### Bước 2 — Preflight trước khi chạy

Với mỗi item đã chọn: chuẩn hóa đường dẫn, kiểm tra video tồn tại, kiểm tra SRT/subtitles, parse SRT, kiểm tra output directory, kiểm tra cache. Hiển thị bảng item hợp lệ/lỗi; chỉ đưa item hợp lệ vào queue.

### Bước 3 — Runner tuần tự an toàn

Giữ chạy tuần tự vì backend đang khóa `_export_active` toàn cục. Mỗi item có `AbortController`/trạng thái riêng; parser SSE có buffer; success lấy `event.path`; luôn `finally` dọn reader, trạng thái và lưu storage.

### Bước 4 — Modal chỉnh sửa dùng snapshot

Mở item → snapshot Editor hiện tại → nạp item → cho người dùng dùng nguyên công cụ Editor → Save lấy subtitle + OCR region + SRT path → restore layout/state. Cancel chỉ restore, không ghi item.

### Bước 5 — Kiểm thử bắt buộc

- Thêm 2 video, 2 SRT, auto-pair thành công.
- SRT không tồn tại: không được vào queue.
- Đọc SRT qua API POST và file UTF-8/GBK.
- Chọn voice/âm lượng khác mặc định: backend nhận đúng.
- SRT dài khiến SSE chia nhiều chunk: vẫn nhận success.
- Một item lỗi: item sau vẫn chạy, Retry chỉ chạy item lỗi.
- Dừng giữa TTS/FFmpeg: không thể Start phiên thứ hai khi backend chưa nhả lock.
- Mở Editor đơn lẻ → mở modal Batch → Cancel/Save → Editor đơn lẻ vẫn giữ đúng video, SRT, vùng OCR.
- Reload trang: hàng đợi và global config khôi phục đúng, item `processing` về `pending`.

## Thứ tự triển khai cho AI khác

1. Sửa contract payload và đọc SRT (P0/P1).
2. Sửa SSE parser + lấy output path + stop/finally.
3. Thêm preflight đường dẫn/file và bỏ auto-pair ảo.
4. Tách hàm tạo config dùng chung từ Editor đơn lẻ.
5. Snapshot/restore modal và getter OCR.
6. Tối ưu render, localStorage migration, rồi chạy bộ kiểm thử hồi quy.

## Tiêu chí hoàn thành

Một phiên Batch chỉ được coi là thành công khi từng item có event success hợp lệ, file output tồn tại và mở được; lỗi một item không làm dừng item sau; dừng không để lại lock backend; reload không làm mất queue; cấu hình Batch cho kết quả tương đương khi dùng cùng cấu hình trong Biên tập phim đơn lẻ.

## Bổ sung — Rà soát riêng phần giao diện

### P1 — Giao diện đang cho phép chọn nhưng cấu hình thực tế không đầy đủ

1. **Thư mục xuất bị ẩn hoàn toàn**
   - Vị trí: `web/index.html:1810-1818`.
   - `batch_outputDir` là input `type="hidden"`, chỉ có nút “Mở thư mục xuất video”, không có nút chọn/đổi thư mục.
   - Người dùng không biết file sẽ xuất ở đâu và không thể đổi thư mục từ Batch Studio.
   - Cách sửa: hiển thị đường dẫn dạng readonly + nút “Chọn thư mục”, gọi API chọn thư mục đang dùng ở Editor đơn lẻ; lưu lại lựa chọn vào localStorage. Nút mở thư mục chỉ mở, không thay thế nút chọn.

2. **Các công tắc có giao diện nhưng không có đủ control tương ứng**
   - Stem Separator chỉ có công tắc `batch_editorStemSeparationEnabled`; `batch_editorStemMode` được đọc ở `batch_editor.js:908` nhưng không tồn tại trong HTML.
   - Auto Delogo chỉ có công tắc; không có chọn góc, kích thước, phương pháp dù JS đọc `batch_delogoCorner`, `batch_delogoSize`, `batch_delogoMethod`.
   - Watermark có công tắc nhưng không thấy ô chọn file logo; JS đọc `batch_logoInputPath` và opacity nhưng giao diện không cung cấp đầy đủ.
   - Cách sửa: hoặc bổ sung các control còn thiếu và disable chúng khi công tắc tắt, hoặc loại bỏ hẳn khỏi Batch UI cho đến khi hỗ trợ đầy đủ. Không nên hiển thị tính năng mà người dùng không thể cấu hình.

3. **Nhãn “Chống bản quyền” dễ gây hiểu nhầm và chỉ có lật ngang**
   - Vị trí: `web/index.html:1745-1761`.
   - Batch đang gửi tốc độ, aspect ratio và mirror; tên “Chống bản quyền” có thể khiến người dùng hiểu là đã có toàn bộ preset chống bản quyền.
   - Cách sửa: đổi nhãn thành “Lật ngang video” hoặc đưa đầy đủ nhóm preset tương ứng với Editor đơn lẻ; giữ mô tả trung tính trong UI.

### P1 — Điều khiển có nhưng phản hồi trực quan không hoạt động đầy đủ

4. **Thanh âm lượng không cập nhật số phần trăm**
   - HTML có `batch_dubbingVoiceVolVal` và `batch_dubbingOrigVolVal`, nhưng `setupBatchGlobalPresetEvents()` chỉ gắn listener cho tốc độ đọc và tốc độ video (`batch_editor.js:796-824`).
   - Kéo slider nhưng số 100%/45% vẫn giữ nguyên.
   - Cách sửa: gắn `input` listener cho voice volume, original volume, threads, subtitle size/outline; cập nhật text ngay khi kéo.

5. **Ô mã màu chữ không đồng bộ với color picker**
   - Vị trí: `web/index.html:1700-1712`, `batch_editor.js:813-816`.
   - JS chỉ lắng nghe color picker, không đồng bộ ngược với `batch_subColorText`/`batch_subOutlineColorText`; người dùng nhập mã màu bằng tay nhưng preview và payload vẫn lấy giá trị picker cũ.
   - Cách sửa: dùng một hàm `syncColorPair(picker, text)` có validate HEX; cập nhật hai chiều, hiển thị lỗi khi mã màu không hợp lệ.

6. **Preset phụ đề hiển thị nhưng chưa áp dụng đủ style**
   - `applyBatchSubtitlePreset()` chỉ đổi font và màu (`batch_editor.js:830-854`), không đổi size, outline, bold/position; preview không phản ánh đầy đủ kết quả render.
   - Cách sửa: preset phải là object đầy đủ cùng schema `subtitle_style` của Editor đơn lẻ; preview dùng cùng các trường đó.

7. **Nút bắt đầu không phản ánh lý do chưa thể chạy**
   - Nút `BẮT ĐẦU LÀM HÀNG LOẠT` luôn bật trong HTML và chỉ báo lỗi sau khi bấm.
   - Cách sửa: cập nhật trạng thái disabled khi không có item được chọn/không có item hợp lệ/đang chạy; thêm dòng giải thích ngay cạnh nút, không chỉ dùng toast.

### P2 — Bố cục và thao tác với danh sách lớn

8. **Bảng không có thanh cuộn ngang rõ ràng trên màn hình hẹp**
   - Vị trí: `web/index.html:1525`, `web/style.css:5094-5321`.
   - Bảng có 6 cột và tên/path dài; trên laptop nhỏ hoặc zoom lớn có thể ép cột hành động quá hẹp, nút bị tràn.
   - Cách sửa: thêm `overflow-x:auto`, `min-width` cho bảng, giữ cột checkbox/hành động sticky; ở breakpoint nhỏ chuyển mỗi item thành card hoặc cho phép cuộn ngang có chỉ báo.

9. **Chiều cao bảng cố định 48vh/400px gây lãng phí hoặc che khuất nội dung**
   - Vị trí: `web/index.html:1525`, `web/style.css:5297-5304`.
   - Màn hình thấp phải cuộn nhiều; màn hình cao vẫn chỉ thấy ít dòng.
   - Cách sửa: dùng `clamp()`/CSS grid theo viewport, hoặc cho phép người dùng kéo thay đổi chiều cao; bảo đảm khu vực cấu hình và nút chạy vẫn nhìn thấy.

10. **Select All mặc định checked nhưng danh sách rỗng**
    - Vị trí: `web/index.html:1548`.
    - Khi mới mở, checkbox tổng thể hiện đã chọn dù chưa có video; dễ tạo cảm giác ứng dụng đã chọn dữ liệu.
    - Cách sửa: mặc định bỏ checked; chỉ checked khi có item và tất cả item đều được chọn; thêm trạng thái indeterminate khi chọn một phần.

11. **Xóa từng dòng không có xác nhận và không có Undo**
    - Vị trí: `batch_editor.js:581-589`.
    - Nút thùng rác nhỏ, dễ bấm nhầm; xóa ngay khỏi localStorage.
    - Cách sửa: xác nhận khi item đã có subtitle/đã hoàn thành; với xóa đơn giản nên có toast Undo trong vài giây.

12. **Trạng thái lỗi chỉ nằm trong tooltip**
    - Vị trí: `batch_editor.js:505-507`.
    - Lỗi dùng `title`, khó xem trên cảm ứng và không rõ khi bảng dài.
    - Cách sửa: hiển thị dòng lỗi rút gọn trong ô trạng thái, nút “Xem lỗi/Retry”, tooltip chỉ là bổ sung.

13. **Drop zone không có trạng thái hướng dẫn đủ rõ khi kéo file**
    - Hiện chỉ đổi class `drag-over`.
    - Cách sửa: khi `dragenter` hiển thị overlay “Thả video/SRT vào đây”, phân biệt file hợp lệ và file không hỗ trợ; sau drop báo số file video/SRT/không hợp lệ.

### P2 — Modal và khả năng tiếp cận

14. **Modal chi tiết cần khóa focus và hỗ trợ bàn phím**
    - Vị trí: `web/index.html:6326+`, `batch_editor.js:655-711`.
    - Cần `role="dialog"`, `aria-modal="true"`, focus vào nút đóng, đóng bằng Escape, trap focus; hiện chủ yếu dựa vào nút đóng.

15. **Màu trạng thái phụ thuộc nhiều vào màu sắc và emoji**
    - Các badge xanh/vàng/đỏ cần thêm text rõ (`Sẵn sàng`, `Đang chạy`, `Thất bại`) và biểu tượng không phải thông tin duy nhất; kiểm tra tương phản khi theme tối.

16. **Tên file/path dài làm mất thông tin quan trọng**
    - Có ellipsis nhưng chưa có nút copy path.
    - Cách sửa: giữ tooltip đầy đủ, thêm “Copy đường dẫn” trong menu dòng hoặc modal chi tiết.

## Tiêu chí giao diện sau khi sửa

- Người dùng luôn biết thư mục xuất và có thể đổi trước khi chạy.
- Mọi control hiển thị đều có tác dụng thật hoặc bị ẩn/disable có giải thích.
- Slider, màu, preset cập nhật preview và giá trị hiển thị tức thì.
- Trên màn hình hẹp không mất nút Sửa/Xóa/Retry.
- Item lỗi nhìn thấy nguyên nhân và có Retry rõ ràng.
- Modal dùng được bằng chuột, bàn phím và Escape; không làm mất trạng thái Editor đơn lẻ.
