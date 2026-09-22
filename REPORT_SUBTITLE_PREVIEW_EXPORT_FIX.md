# Báo cáo phương án sửa lỗi Preview và video xuất

## 1. Kết luận và phương án được chọn

Chọn một hợp đồng tọa độ duy nhất cho toàn bộ lớp hiển thị:

```text
phần trăm trên vùng video thật
        -> tọa độ pixel trên khung xuất cuối
        -> render blur và subtitle trên cùng khung đó
```

Phương án gồm bốn phần:

1. Preview và FFmpeg dùng cùng công thức tọa độ, có tính vùng letterbox/padding.
2. Phụ đề ASS dùng `\\an5\\pos(x,y)` (hoặc `\\an4/\\an6` cho trái/phải), không neo bằng `Alignment=2` và `MarginV`.
3. Mặt nạ blur được tạo nhị phân trong không gian RGB full-range rồi mới `maskedmerge`; không đưa mặt nạ 0/255 trở lại YUV limited trước khi merge.
4. Preview và FFmpeg dùng cùng file font được đóng gói trong ứng dụng.

Không nên áp dụng nguyên văn chuỗi `format=gray,...,format=yuv420p` trong báo cáo cũ, vì bước chuyển lại sang YUV limited làm mất ý nghĩa 0/255 của mặt nạ.

## 2. Phạm vi file cần sửa

Sửa mã chạy thật:

- `routes/video_edit.py`
- `auto_edit_pipeline.py`
- `web/app.js`
- `web/index.html` hoặc stylesheet được index nạp

Sau khi hoàn tất, đồng bộ cùng thay đổi sang:

- `patches/active/routes/video_edit.py`
- `patches/active/auto_edit_pipeline.py`
- `patches/active/web/app.js`
- `patches/active/web/index.html`

Thêm thư mục font:

- `resources/fonts/`

Không sửa các file kiểm thử scratch để làm thay đổi hành vi chính.

## 3. Sửa vị trí và kích thước phụ đề

### 3.1. `routes/video_edit.py`

#### Hàm cần sửa

`generate_styled_ass()` hiện đặt `Alignment=2` và tính `MarginV` từ đáy. Thay bằng các bước sau:

1. Nhận thêm `output_geometry` gồm:

   - `out_w`, `out_h`: kích thước khung xuất;
   - `content_x`, `content_y`, `content_w`, `content_h`: vùng video thật sau scale/pad;
   - vùng subtitle theo phần trăm tương đối với vùng video thật.

2. Đổi vùng phần trăm sang pixel của khung xuất:

```python
box_x = geometry.content_x + geometry.content_w * region_x / 100.0
box_y = geometry.content_y + geometry.content_h * region_y / 100.0
box_w = geometry.content_w * region_w / 100.0
box_h = geometry.content_h * region_h / 100.0
center_x = box_x + box_w / 2.0
center_y = box_y + box_h / 2.0
```

3. Chọn anchor theo căn chữ:

```text
left   -> \\an4, x = box_x
center -> \\an5, x = center_x
right  -> \\an6, x = box_x + box_w
y luôn là box_y + box_h/2 cho căn giữa dọc
```

4. Sinh mỗi dòng với override tag:

```text
{\\an5\\pos(center_x,center_y)}Nội dung phụ đề
```

5. Giữ giới hạn xuống dòng bằng bề rộng hộp đã quy đổi. Không dùng `\\fscx/\\fscy` để ép kích thước chữ theo bề rộng hộp; kích thước chữ phải giữ theo style của người dùng.

6. Tính `Fontsize` theo chiều cao vùng video thật, không theo chiều cao phần padding:

```python
font_size = round(base_font_size * geometry.content_h / 720.0)
```

7. Đặt `Alignment=5` trong style mặc định để fallback vẫn có cùng anchor với override tag.

### 3.2. Tính `output_geometry`

Tạo một helper dùng chung trong `routes/video_edit.py`, ví dụ `compute_output_geometry(src_w, src_h, out_w, out_h)`. Helper phải dùng cùng công thức scale/pad đang dùng ở filter `scale=...:force_original_aspect_ratio=decrease,pad=...`.

Điểm bắt buộc: với output 9:16, 1:1 hoặc 21:9, `content_y`/`content_x` phải được cộng vào tọa độ ASS. Nếu không, `\\pos()` vẫn lệch khi video có letterbox.

### 3.3. `web/app.js`

Trong `applySubStylesToElement()`:

1. Với `subPreviewBox`, lấy `getVideoContentRect()`.
2. Đặt kích thước chữ preview theo:

```javascript
const contentScale = (vRect?.videoH || 720) / 720;
el.style.fontSize = `${Math.round(size * contentScale)}px`;
```

3. Không áp dụng phép scale này cho các hộp UI không nằm trên video.
4. Giữ `display:flex`, `alignItems:center` và `justifyContent` theo lựa chọn trái/giữa/phải.

Preview lúc này dùng chiều cao video thật, còn FFmpeg dùng `geometry.content_h`; hai bên có cùng tỷ lệ tương đối.

## 4. Sửa font để loại bỏ fallback

### 4.1. Thêm font đóng gói

Thêm các file TTF/OTF tương ứng với những font cho phép chọn trong UI vào `resources/fonts/`, tối thiểu các weight đang dùng của Montserrat. Nếu không muốn đóng gói toàn bộ font, phải giới hạn danh sách UI còn các font đã đóng gói.

### 4.2. Preview

Trong `web/index.html` hoặc stylesheet, dùng `@font-face` trỏ tới cùng font local mà FFmpeg sẽ dùng. Không phụ thuộc vào Google Fonts để kết quả không thay đổi khi máy mất mạng.

### 4.3. FFmpeg

Trong filter `subtitles` ở `routes/video_edit.py`, truyền `fontsdir` tới `resources/fonts` và escape đường dẫn đúng cho Windows. Ghi log tên font được chọn và kiểm tra log libass không có dòng fallback sang Arial.

## 5. Sửa pipeline blur

### 5.1. `auto_edit_pipeline.py`

Sửa `generate_dynamic_blur_ass_mask()` và `build_dynamic_blur_filter_chain()`.

Mặt nạ ASS nên dùng `PlayResX/PlayResY` bằng kích thước frame tại stage filter. Nếu giữ filter ở stage trước scale thì dùng kích thước frame đầu vào; nếu chuyển filter sang frame cuối thì dùng `out_w/out_h`. Không dùng giá trị 10000 cố định nếu không có lý do tương thích cụ thể.

### 5.2. Graph FFmpeg được dùng

Mặt nạ phải được chuyển sang RGB full-range và được nhân bản đồng nhất trên các kênh màu. Graph mục tiêu:

```text
[base]split=3[orig][blur_src][mask_src];
[orig]format=gbrp[orig_rgb];
[blur_src]format=gbrp,
    gblur=sigma=SIGMA:sigmaV=SIGMA:steps=2,
    lutrgb=r='val*(1-TINT)':g='val*(1-TINT)':b='val*(1-TINT)'[blur_rgb];
[mask_src]drawbox=c=black:t=fill,
    subtitles=filename='MASK_ASS',
    format=gray,
    geq=lum='if(gt(lum(X,Y),100),255,0)',
    format=gbrp[mask_rgb];
[orig_rgb][blur_rgb][mask_rgb]maskedmerge,
    format=yuv420p[out]
```

Trong đó:

- `TINT = 0.06` để khớp `background: rgba(0,0,0,0.06)` của Preview;
- không dùng opacity 15–25% nếu chưa thay đổi Preview tương ứng;
- `maskedmerge` nhận ba luồng cùng kích thước và cùng pixel format `gbrp`;
- `format=yuv420p` chỉ thực hiện sau khi merge xong.

Nếu bản FFmpeg cụ thể không chấp nhận `gbrp` với `maskedmerge`, dùng phương án tương đương: tạo alpha mask full-range rồi `overlay` video đã blur lên video gốc. Không quay lại YUV limited mask với U/V=128.

### 5.3. Thuật toán blur và bán kính

Dùng `gblur` làm mặc định vì Preview dùng blur dạng kính. `sigma` phải được hiệu chỉnh bằng frame thực tế; không coi `sigma=15` là tương đương tuyệt đối với CSS `blur(15px)`. Có thể dùng `boxblur` nhiều lượt nếu cần hiệu năng, nhưng phải giữ cùng một giá trị cảm nhận qua kiểm thử.

Bán kính phải được tính theo frame tại đúng stage filter. Phương án ưu tiên là tạo blur sau khi đã có khung output cuối và trước khi burn subtitle; khi đó:

```python
blur_px = round(blur_intensity * content_h / 720.0)
```

Nếu vì lý do timeline phải giữ blur trước scale, dùng chiều cao frame đầu vào của stage đó, không dùng mù quáng `cur_out_h`.

### 5.4. Vị trí filter trong `routes/video_edit.py`

Hiện dynamic blur được dựng trước các bước scale/pad. Chuyển việc gọi `build_dynamic_blur_filter_chain()` xuống sau khi tính xong output geometry và tạo frame output. Các `aiBox` phải được quy đổi từ phần trăm vùng video thật sang phần trăm khung output trước khi tạo ASS mask.

Nếu filter được đặt sau `setpts` (tăng/giảm tốc), phải chia thời gian bắt đầu/kết thúc của interval cho `video_speed`. Đây là điều kiện bắt buộc để mask vẫn xuất hiện đúng lúc.

Thứ tự mục tiêu:

```text
input
 -> crop/zoom/mirror
 -> scale + pad thành output frame
 -> dynamic blur trên output frame
 -> burn subtitle ASS
 -> encode
```

## 6. Không gộp nhầm hai loại nền

Giữ riêng:

- `dynamicBlurOverlay`: làm mờ chữ gốc trong video;
- `subBgStyle=blur`: nền phía sau phụ đề tiếng Việt.

Muốn hai bên giống nhau, mỗi cơ chế phải có thông số riêng nhưng dùng cùng giá trị đã định nghĩa rõ. Không dùng nền subtitle `rgba(0,0,0,0.3)` để suy ra tint của dynamic blur.

## 7. Kiểm thử bắt buộc

### 7.1. Kiểm thử hình học ASS

Sinh ASS cho các trường hợp:

- 1920x1080, không padding;
- 1080x1920, nguồn 16:9;
- 1080x1080, nguồn 16:9;
- căn trái, giữa, phải;
- một dòng và hai dòng.

Đọc lại ASS để kiểm tra `\\an`, `\\pos`, `PlayResX/Y`, font size và tọa độ tâm.

### 7.2. Kiểm thử zero-leak mask

Dùng video tổng hợp có nền đơn màu và chữ trắng. Render một frame với mask RGB mới, sau đó đo:

- pixel ngoài vùng mask phải giữ nguyên video gốc trong sai số mã hóa;
- pixel trong vùng mask phải lấy từ nhánh blur;
- không có thay đổi màu toàn khung do U/V=128.

Kiểm thử này phải chạy qua `bin/ffmpeg.exe` của dự án.

### 7.3. Kiểm thử Preview/export

Với cùng một timestamp, chụp frame Preview và frame xuất ở 720p, 1080p, 4K, 9:16 và 1:1. So sánh:

- tâm bounding box chữ;
- kích thước chữ theo chiều cao video thật;
- biên vùng blur;
- độ sáng nền blur;
- không còn chữ gốc sắc nét trong vùng cần che.

Chấp nhận sai số hình học khoảng 1–2 pixel sau rasterization, không chấp nhận lệch có hệ thống hàng chục pixel.

## 8. Tiêu chí hoàn thành

Chỉ coi là hoàn tất khi:

1. Không còn `Alignment=2`/`MarginV` được dùng để định vị subtitle có region tùy chỉnh.
2. ASS và Preview dùng cùng content rectangle, kể cả khi có padding.
3. Font được chọn không fallback trong log libass.
4. Mask không còn đường rò do YUV limited range.
5. Blur được hiệu chỉnh theo stage filter và độ phân giải hiển thị.
6. Bản root và `patches/active` có cùng hành vi.

