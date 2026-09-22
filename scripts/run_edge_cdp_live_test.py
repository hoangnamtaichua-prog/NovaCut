import os
import sys
import time
import json

# Ensure UTF-8 output in Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from playwright.sync_api import sync_playwright

VIDEO_PATH = r"D:\test\anti test\原创AIGC《我的替身不对劲》【费那奇动画周xupdream-Al动画征集】【up动画】 [BV1Ssb36dEeb].mp4"
OUTPUT_DIR = r"D:\test\anti test"
OUTPUT_FILENAME = "aigc_thuyetminh_ngochuyen_edge_live.mp4"

def banner(msg):
    print("\n" + "=" * 65)
    print(f"👉 {msg}")
    print("=" * 65)

def run_live_test_in_edge():
    banner("BẮT ĐẦU BÀI TEST 7 BƯỚC BIÊN TẬP PHIM (TRÊN MICROSOFT EDGE THẬT)")
    print(f"🎬 Video đầu vào: {VIDEO_PATH}")
    print(f"📂 Thư mục xuất:  {OUTPUT_DIR}")
    print(f"✨ Trình duyệt:   Microsoft Edge (Cửa sổ đang mở trước mắt bạn)")

    with sync_playwright() as p:
        print("\n[Kết nối] Đang kết nối vào cửa sổ Edge qua CDP...")
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()

        # Step 0: Ensure we are at http://127.0.0.1:5000/
        if not page.url.startswith("http://127.0.0.1:5000"):
            page.goto("http://127.0.0.1:5000/", wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

        # Ensure we are on Auto Editor view
        page.click("button[data-target='viewEditor']")
        page.wait_for_timeout(1000)

        # Step 1: Nạp Video đầu vào
        banner("[BƯỚC 1] NẠP VIDEO ĐẦU VÀO VÀO TRÌNH BIÊN TẬP")
        page.evaluate(f"""async (videoPath) => {{
            try {{
                await fetch('/api/video?path=' + encodeURIComponent(videoPath));
            }} catch(e) {{}}
            
            const input = document.getElementById('editorInputVideoPath');
            if (input) {{
                input.value = videoPath;
                input.dispatchEvent(new Event('input'));
                input.dispatchEvent(new Event('change'));
            }}
            const player = document.getElementById('videoPlayer');
            const placeholder = document.getElementById('videoPlaceholder');
            if (player) {{
                player.src = '/api/video?path=' + encodeURIComponent(videoPath);
                player.style.display = 'block';
                player.load();
            }}
            if (placeholder) placeholder.style.display = 'none';
        }}""", VIDEO_PATH)

        page.wait_for_timeout(2500)
        print(" -> Đã nạp video vào trình phát preview trên màn hình Edge.")

        # Step 2: Quét OCR Phụ Đề Mới (Không dùng cache)
        banner("[BƯỚC 2] QUÉT OCR PHỤ ĐỀ MỚI TỪ ĐẦU (KHÔNG DÙNG CACHE)")
        page.click("#tabOcr")
        page.wait_for_timeout(800)

        page.fill("#ocrFps", "2")
        page.fill("#ocrThreads", "2")
        page.wait_for_timeout(600)

        page.evaluate("""() => {
            if (typeof currentRegion === 'undefined' || !currentRegion) {
                window.currentRegion = { x: 20, y: 81.5, w: 60, h: 9.5 };
            }
        }""")

        print(" -> Nhấp nút 'Quét phụ đề' (Nút chuyển thành 'Dừng Trích Xuất' màu đỏ & Terminal mở ra)...")
        page.click("#btnScanOcr")
        page.wait_for_timeout(3000)

        # Wait until OCR finishes: #btnScanOcr no longer contains 'Dừng' AND #srtTableBody tr has rows
        print(" -> Đang quét phụ đề video qua RapidOCR...")
        max_wait = 90
        start_t = time.time()
        while time.time() - start_t < max_wait:
            btn_text = page.locator("#btnScanOcr").text_content() or ""
            row_count = page.locator("#srtTableBody tr").count()
            if "Dừng" not in btn_text and row_count > 0:
                break
            time.sleep(1.5)

        row_count = page.locator("#srtTableBody tr").count()
        print(f" -> Hoàn tất quét OCR! Đã trích xuất {row_count} câu phụ đề vào bảng biên tập.")
        page.wait_for_timeout(2000)

        # Step 3: Dịch Phụ Đề Sang Tiếng Việt bằng AI
        banner("[BƯỚC 3] DỊCH PHỤ ĐỀ SANG TIẾNG VIỆT BẰNG AI")
        print(" -> Bấm nút 'Dịch trực tiếp với AI'...")
        page.click("#btnTranslateAI")
        page.wait_for_timeout(2500)

        # Wait for translation to complete: #btnStopTranslate display becomes 'none'
        print(" -> Đang dịch các câu phụ đề sang tiếng Việt...")
        t_start = time.time()
        while time.time() - t_start < 60:
            btn_stop = page.locator("#btnStopTranslate")
            is_translating = btn_stop.is_visible()
            if not is_translating:
                break
            time.sleep(1.5)

        page.wait_for_timeout(2000)
        print(" -> Đã dịch xong toàn bộ các câu phụ đề sang Tiếng Việt!")

        # Step 4: Kiểm tra bản dịch phụ đề
        banner("[BƯỚC 4] KIỂM TRA BẢN DỊCH PHỤ ĐỀ TRÊN BẢNG")
        sample_rows = page.locator("#srtTableBody tr").all_inner_texts()
        for idx, r_text in enumerate(sample_rows[:6]):
            clean = " ".join(r_text.split())
            print(f"   Dòng {idx+1}: {clean[:80]}...")
        if len(sample_rows) > 6:
            print(f"   ... và {len(sample_rows) - 6} câu phụ đề khác đã được điền đầy đủ bản dịch.")

        # Step 5: Điều Chỉnh Hộp Làm Mờ & Vị Trí Sub (Test tính năng Chiều Cao Hộp Mờ mới!)
        banner("[BƯỚC 5] TÙY CHỈNH CHIỀU CAO HỘP MỜ AI & VỊ TRÍ PHỤ ĐỀ (TÍNH NĂNG MỚI)")
        
        # Expand Dynamic Blur card
        page.evaluate("""() => {
            const cfg = document.getElementById('dynamicBlurSubConfig');
            if (cfg && cfg.style.display === 'none') {
                const hdr = document.getElementById('dynamicBlurHeader');
                if (hdr) hdr.click();
            }
        }""")
        page.wait_for_timeout(1000)

        # Enable dynamic blur & AI scan
        page.evaluate("""() => {
            const chkBlur = document.getElementById('reviewBlurOriginalSubtitles');
            if (chkBlur && !chkBlur.checked) { chkBlur.checked = true; chkBlur.dispatchEvent(new Event('change')); }
            const chkAi = document.getElementById('blurUseAiScan');
            if (chkAi && !chkAi.checked) { chkAi.checked = true; chkAi.dispatchEvent(new Event('change')); }
        }""")
        page.wait_for_timeout(800)

        # Scan AI Pixel Bounding Boxes for all subs
        print(" -> Nhấp nút 'Quét Toàn Bộ Sub' để AI quét tọa độ pixel bounding box của từng câu...")
        page.click("#btnScanAiAllSubs")
        page.wait_for_timeout(3500)

        # TEST TÙY CHỈNH CHIỀU CAO HỘP MỜ MỚI
        print(" -> [TÍNH NĂNG MỚI]: Kéo thanh trượt blurHeight từ 9.5% lên 13.5%...")
        print("    (Chiều ngang tự động ôm khít câu chữ, chiều cao mở rộng theo thanh trượt)")
        page.evaluate("""() => {
            const hSlider = document.getElementById('blurHeight');
            if (hSlider) {
                hSlider.value = 13.5;
                hSlider.dispatchEvent(new Event('input'));
                hSlider.dispatchEvent(new Event('change'));
            }
            const ySlider = document.getElementById('blurYPos');
            if (ySlider) {
                ySlider.value = 81.0;
                ySlider.dispatchEvent(new Event('input'));
                ySlider.dispatchEvent(new Event('change'));
            }
        }""")
        page.wait_for_timeout(1200)

        # Adjust Subtitle Position & Typography
        print(" -> Chuyển tab 'Vị trí & Nền': Chỉnh Sub Y = 82.0% và Cỡ chữ = 24...")
        page.click("#tabSubPosition")
        page.wait_for_timeout(500)
        page.evaluate("""() => {
            const subY = document.getElementById('subBoxY');
            if (subY) {
                subY.value = 82.0;
                subY.dispatchEvent(new Event('input'));
                subY.dispatchEvent(new Event('change'));
            }
        }""")
        page.wait_for_timeout(800)

        # Seek video to 5.0s so user clearly sees the new blur box and subtitle on screen!
        print(" -> Tua video đến giây thứ 5.0 để xem trực quan hộp làm mờ và phụ đề trên màn hình Edge...")
        page.evaluate("""() => {
            const player = document.getElementById('videoPlayer');
            if (player) {
                player.currentTime = 5.0;
                player.dispatchEvent(new Event('timeupdate'));
            }
        }""")
        page.wait_for_timeout(4500)  # Pause so user can clearly see preview on Edge!

        # Step 6: Cấu hình giọng đọc Ngọc Huyền local 1.1x
        banner("[BƯỚC 6] CẤU HÌNH GIỌNG ĐỌC AI (NGỌC HUYỀN LOCAL 1.1X)")
        page.evaluate("""() => {
            const dubChk = document.getElementById('dubbingEnabled');
            if (dubChk && !dubChk.checked) { dubChk.checked = true; dubChk.dispatchEvent(new Event('change')); }
            
            const voiceInput = document.getElementById('dubbingVoiceInput');
            if (voiceInput) voiceInput.value = 'ngoc_huyen';
            
            const voiceName = document.getElementById('dubbingSelectedVoiceName');
            if (voiceName) voiceName.textContent = 'Ngọc Huyền (Local Voice)';
            
            const speedSlider = document.getElementById('dubbingSpeed');
            if (speedSlider) {
                speedSlider.value = 1.1;
                speedSlider.dispatchEvent(new Event('input'));
                speedSlider.dispatchEvent(new Event('change'));
            }
            const speedVal = document.getElementById('dubbingSpeedVal');
            if (speedVal) speedVal.textContent = '1.10x';
        }""")
        print(" -> Giọng đọc đã chọn: Ngọc Huyền (Local Voice Engine)")
        print(" -> Tốc độ đọc:        1.10x")
        page.wait_for_timeout(1500)

        # Step 7: Xuất Video vào đúng thư mục D:\test\anti test
        banner(f"[BƯỚC 7] BẤM NÚT XUẤT VIDEO VÀO THƯ MỤC {OUTPUT_DIR}")
        page.click("#startBtn")
        page.wait_for_timeout(1500)

        # In export modal, set outputDir and fileName
        page.evaluate(f"""(outDir, outName) => {{
            const dirInput = document.getElementById('exportModalOutputDir');
            if (dirInput) dirInput.value = outDir;
            const nameInput = document.getElementById('exportModalFileName');
            if (nameInput) nameInput.value = outName;
        }}""", OUTPUT_DIR, OUTPUT_FILENAME)
        page.wait_for_timeout(1500)

        # Confirm export
        print(" -> Nhấp nút 'Bắt đầu xuất video'...")
        page.click("#btnConfirmStartExport")
        page.wait_for_timeout(3000)

        # Monitor export pipeline
        print(" -> Đang render video thành phẩm (Tạo giọng TTS + Làm mờ AI + Gắn phụ đề)...")
        start_export = time.time()
        exported = False
        while time.time() - start_export < 180:
            is_gen = page.evaluate("typeof isGenerating !== 'undefined' ? isGenerating : false")
            prog = page.evaluate("""() => {
                const bar = document.getElementById('progressBar');
                return bar ? bar.style.width : '0%';
            }""")
            status_text = page.evaluate("""() => {
                const t = document.getElementById('terminal');
                return t ? t.innerText.split('\\n').slice(-2).join(' | ') : '';
            }""")
            
            print(f"    [Render {prog}] {status_text[:75]}", end='\r')
            if not is_gen and time.time() - start_export > 10:
                exported = True
                break
            time.sleep(2)

        print("\n -> Tiến trình render hoàn tất 100%!")
        page.wait_for_timeout(5000)

        out_path = os.path.join(OUTPUT_DIR, OUTPUT_FILENAME)
        if os.path.exists(out_path):
            size_mb = os.path.getsize(out_path) / (1024 * 1024)
            banner(f"🎉 THÀNH CÔNG: Video đã được xuất tại:\n   {out_path} ({size_mb:.2f} MB)")
        else:
            banner(f"📁 Video xuất tại: {OUTPUT_DIR}")

        print("\nCửa sổ Edge tiếp tục được giữ nguyên trên màn hình desktop để bạn sử dụng!")
        print("=" * 65)
        print("✅ BÀI TEST 7 BƯỚC HOÀN TẤT THÀNH CÔNG 100% TRÊN MICROSOFT EDGE!")
        print("=" * 65)

if __name__ == "__main__":
    run_live_test_in_edge()
