# Báo cáo kiểm tra Biên tập hàng loạt

Ngày kiểm tra: 2026-09-24

## 1. Chọn giọng nam nhưng lồng tiếng ra giọng nữ

### Sai ở đâu
- ai_dubbing.py:64-70 và 91-100: fallback cố định về local_ngoc_huyen hoặc edge_vi-VN-HoaiMyNeural.
- ai_dubbing.py:136-152: fallback Kokoro/local suy đoán giới tính theo tên ID.
- local_voice_engine.py:619-665: voice không resolve được sẽ mặc định dùng Ngọc Huyền.
- routes/video_edit.py:871-876: có thể reuse track TTS cũ.
- web/js/features/batch_editor.js:1746-1795: chỉ gửi voice_id, không gửi metadata voice.

### Cách sửa
Resolve profile theo ID trước khi chạy; truyền gender, lang, provider, base_voice, reference_audio. Fallback phải cùng giới tính và ngôn ngữ. Nếu không có fallback phù hợp thì báo lỗi và dừng item. Fingerprint phải gồm voice ID, profile version, gender, lang, provider và text hash. Ghi log voice thực tế.

### Tuyệt đối không làm
Không fallback cứng về Ngọc Huyền. Không đổi voice nam thành nữ hoặc ngược lại. Không dùng track cũ trong fresh run.

## 2. Tắt subtitle nhưng file xuất vẫn có subtitle

### Sai ở đâu
- routes/video_edit.py:651-675 vẫn tạo temp SRT dù subtitle tắt.
- routes/video_edit.py:1195-1214 chỉ gate một nhánh burn-in.
- routes/video_edit.py:668-670 fallback từ translation về text gốc.
- web/app.js:1018-1165 có fallback về field editor thường.
- web/js/features/batch_editor.js:1810 cần xác minh boolean false trong payload cuối.

### Cách sửa
Log payload ngay trước /api/start. Khi subtitles_enabled=false, backend không được tạo filter subtitles/ass và không dùng manual/temp SRT cho burn-in. Tách subtitle mới, subtitle gốc cần blur và transcript TTS. Nếu video đã hardcode subtitle thì phải báo rõ.

### Tuyệt đối không làm
Không tự bật lại subtitle vì danh sách subtitles còn dữ liệu. Không dùng temp SRT cho burn-in khi đã tắt. Không tuyên bố xóa được subtitle hardcode nếu chưa chạy mask/inpaint.

## 3. Câu chưa dịch, song ngữ và câu trùng dưới 0,7 giây

### Sai ở đâu
- web/js/features/batch_editor.js:2439-2446 giữ im lặng các ID thiếu translation.
- web/js/features/batch_editor.js:2217-2265 chỉ kiểm tra rỗng/lỗi/chữ Hán.
- routes/subtitles.py:720-880 chưa validator đầy đủ cho target English và các ngôn ngữ khác.
- routes/subtitles.py:927-1093 không có hậu kiểm deterministic.
- Không có xử lý duplicate/overlap theo ngưỡng 0,7 giây.

### Cách sửa
Sau OCR, clean, translate và trước export phải: chuẩn hóa timestamp; sort; xóa dòng lỗi; gộp/xóa nội dung trùng khi khoảng cách dưới 0,7 giây; xử lý overlap; bắt buộc mỗi ID có bản dịch; kiểm tra target language; retry ID lỗi; đánh lại ID; đọc lại file SRT sau khi ghi.

### Tuyệt đối không làm
Không giữ nguyên text nguồn khi dịch thất bại. Không coi translation có giá trị là đã dịch đúng. Không export khi còn ID thiếu hoặc timestamp lỗi.

## 4. Batch vẫn dùng tài nguyên cũ

### Sai ở đâu
- web/js/features/batch_editor.js:2853-2855 có SRT/subtitles thì bỏ qua OCR.
- web/js/features/batch_editor.js:2964-2970 bản dịch hoàn chỉnh thì bỏ qua dịch.
- routes/video_edit.py:871-876 có thể reuse manifest TTS ngay cả khi use_cache=false.
- routes/video_edit.py:513-514 dùng lại temp directory.
- routes/video_edit.py:742-799 có nhánh đọc AI boxes cache.

### Cách sửa
Thêm fresh_run=true và run_id riêng. Fresh run luôn chạy OCR → normalize/dedup → clean → translate → validate → TTS → export. Không đọc SRT cũ, subtitle trong localStorage, TTS manifest, dubbed track, AI boxes, stem audio hoặc temp artifact. Chỉ ghi cache sau khi item hoàn tất.

### Tuyệt đối không làm
Không dùng item.srtPath cũ để skip OCR. Không dùng is_manifest_match trong fresh run. Không dùng cache video trước cho video hiện tại. Không coi status completed trong localStorage là lý do bỏ qua.

## 5. Preview voice English lại đọc tiếng Việt

### Sai ở đâu
- web/app.js:10795-10890 ưu tiên sample tĩnh sai ngôn ngữ.
- web/app.js:10855-10865 chỉ gửi voice ID.
- routes/tts.py:354-355 dùng câu mặc định tiếng Việt.
- routes/tts.py:360-368 cache chỉ theo voice_id.wav.
- local_voice_engine.py:658-665 fallback về Ngọc Huyền.

### Cách sửa
Gửi voice_id, text, lang/locale, gender, speed. Chọn câu mẫu đúng locale. Cache key gồm voice, text, locale, speed và engine version. Sample tĩnh sai locale không được dùng.

### Tuyệt đối không làm
Không dùng câu tiếng Việt cho mọi voice. Không trả cache cũ chỉ vì voice ID giống nhau. Không dùng sample tiếng Việt cho voice English.

## 6. Lỗi bổ sung

- All-in-one ghi Dịch & Làm sạch nhưng chỉ gọi translate, chưa gọi clean.
- Sau translate không có validator bắt buộc trước export.
- Có nhiều nhánh replace_original=true, có nguy cơ ghi đè SRT nguồn.
- Batch và editor dùng DOM field khác nhau, dễ sai voice, speed hoặc giá trị false.
- Thiếu test end-to-end cho fresh run, voice fallback, subtitle off, target English và duplicate dưới 0,7 giây.

## Tiêu chí nghiệm thu

- Voice thực tế đúng ID, giới tính và ngôn ngữ.
- Preview đúng locale.
- Subtitle tắt thì ffmpeg không có filter subtitles/ass.
- Không còn bản dịch rỗng, song ngữ ngoài chủ ý hoặc câu nguồn.
- Không còn duplicate/overlap dưới 0,7 giây.
- Fresh run không đọc cache cũ.
- Không ghi đè SRT nguồn mặc định.
- Có test hồi quy và test end-to-end cho từng lỗi.

## Prompt giao cho AI khác

Hãy đọc toàn bộ các file: web/js/features/batch_editor.js, web/app.js, routes/video_edit.py, routes/subtitles.py, routes/tts.py, ai_dubbing.py, local_voice_engine.py và custom_voices.py.

Sửa toàn bộ lỗi trong báo cáo này:

1. Bảo toàn giới tính/ngôn ngữ voice qua mọi fallback; không fallback cứng về Ngọc Huyền.
2. Preview phải đọc đúng locale; cache phụ thuộc voice + text + locale + speed.
3. subtitles_enabled=false phải tuyệt đối không burn-in subtitle.
4. Thêm hậu kiểm SRT chống thiếu dịch, song ngữ, duplicate và overlap dưới 0,7 giây.
5. Sửa pipeline thành OCR → normalize/dedup → clean → translate → validate → TTS → export.
6. Thêm fresh_run=true và không reuse bất kỳ tài nguyên cũ nào.
7. Không ghi đè SRT nguồn mặc định.
8. Viết test hồi quy và end-to-end, báo cáo file đã sửa và kết quả test.

Tuyệt đối không: đổi voice nam thành nữ; dùng sample tiếng Việt cho voice English; dùng cache cũ trong fresh run; giữ nguyên text nguồn khi dịch thất bại; export khi validator còn lỗi; ghi đè file nguồn; kết thúc khi chưa có test chứng minh từng lỗi đã được xử lý.

