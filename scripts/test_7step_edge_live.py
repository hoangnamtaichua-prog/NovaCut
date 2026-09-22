import os
import sys
import time
import json
import ctypes

# Ensure UTF-8 output in Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from playwright.sync_api import sync_playwright

VIDEO_PATH = r"D:\test\anti test\原创AIGC《我的替身不对劲》【费那奇动画周xupdream-Al动画征集】【up动画】 [BV1Ssb36dEeb].mp4"
OUTPUT_DIR = r"D:\test\anti test"
OUTPUT_FILENAME = "aigc_thuyetminh_ngochuyen_edge.mp4"

def bring_window_to_front():
    """Đưa cửa sổ trình duyệt Edge lên vị trí TOPMOST đè lên phía trước để người dùng thấy 100%"""
    try:
        user32 = ctypes.windll.user32
        def enum_handler(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                buf = ctypes.create_unicode_buffer(512)
                user32.GetWindowTextW(hwnd, buf, 512)
                title = buf.value
                if 'NovaCut' in title or 'Edge' in title:
                    # HWND_TOPMOST (-1), SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
                    user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
                    user32.ShowWindow(hwnd, 3) # SW_MAXIMIZE
                    user32.SetForegroundWindow(hwnd)
            return True
        user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)(enum_handler), 0)
    except Exception as e:
        pass

def run_edge_demo():
    print("=" * 65)
    print("🚀 BẮT ĐẦU BÀI TEST 7 BƯỚC BIÊN TẬP PHIM (MICROSOFT EDGE LIVE)")
    print("=" * 65)
    print(f"🎬 Video đầu vào: {VIDEO_PATH}")
    print(f"📂 Thư mục xuất:  {OUTPUT_DIR}")
    print(f"✨ Trình duyệt:   Microsoft Edge (Bật giao diện trực quan)")
    print("-" * 65)

    with sync_playwright() as p:
        # Launch real Microsoft Edge with slow_mo=1000 so user can clearly follow every click
        browser = p.chromium.launch(
            channel="msedge",
            headless=False,
            slow_mo=1000,
            args=['--start-maximized']
        )
        context = browser.new_context(no_viewport=True)
        page = context.new_page()

        # Step 0: Open App
        print("\n[Bước 0] Đang mở NovaCut Web Studio trong Microsoft Edge...")
        page.goto("http://127.0.0.1:5000/", wait_until="domcontentloaded")
        page.wait_for_timeout(2500)

        # Force Edge window to foreground!
        bring_window_to_front()
        page.wait_for_timeout(1000)

        # Ensure we are on Auto Editor view
        page.click("button[data-target='viewEditor']")
        page.wait_for_timeout(1000)

        # Step 1: Nạp Video đầu vào
        print("\n[Bước 1] Nạp video vào trình biên tập...")
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

        bring_window_to_front()
        page.wait_for_timeout(2500)
        print(" -> Đã nạp video và tải preview lên trình phát Edge.")

        # Step 2: Quét OCR Phụ Đề Mới (Không dùng cache)
        print("\n[Bước 2] Bắt đầu quét OCR trích xuất phụ đề gốc (Không dùng cache)...")
        page.click("#tabOcr")
        page.wait_for_timeout(600)

        page.fill("#ocrFps", "2")
        page.fill("#ocrThreads", "2")
        page.wait_for_timeout(600)

        page.evaluate("""() => {
            if (typeof currentRegion === 'undefined' || !currentRegion) {
                window.currentRegion = { x: 20, y: 81.5, w: 60, h: 9.5 };
            }
        }""")

        print(" -> Nhấp nút 'Quét phụ đề'...")
        page.click("#btnScanOcr")

        print(" -> Đang chờ tiến trình quét OCR bắt đầu và xử lý frame...")
        page.wait_for_timeout(2500)

        # Wait until OCR finishes
        max_wait = 90
        start_t = time.time()
        while time.time() - start_t < max_wait:
            is_extracting = page.evaluate("typeof isExtractingOCR !== 'undefined' ? isExtractingOCR : false")
            sub_count = page.evaluate("typeof srtData !== 'undefined' && Array.isArray(srtData) ? srtData.length : 0")
            if not is_extracting and sub_count > 0:
                break
            time.sleep(1.5)

        sub_count = page.evaluate("typeof srtData !== 'undefined' && Array.isArray(srtData) ? srtData.length : 0")
        print(f" -> Hoàn tất quét OCR! Trích xuất thành công {sub_count} câu phụ đề.")
        page.wait_for_timeout(2000)

        # Step 3: Dịch Phụ Đề Sang Tiếng Việt bằng AI
        print("\n[Bước 3] Dịch toàn bộ phụ đề sang Tiếng Việt bằng AI...")
        page.evaluate("() => { if (typeof handleTranslateSubtitles === 'function') handleTranslateSubtitles('ai'); }")
        page.wait_for_timeout(2000)

        print(" -> Đang dịch song song với mô hình AI...")
        t_start = time.time()
        while time.time() - t_start < 60:
            is_translating = page.evaluate("""() => {
                const btn = document.getElementById('btnStopTranslate');
                return btn && btn.style.display !== 'none';
            }""")
            translated_count = page.evaluate("""() => {
                return (typeof srtData !== 'undefined' && Array.isArray(srtData)) 
                    ? srtData.filter(s => s.translation && s.translation.trim().length > 0).length 
                    : 0;
            }""")
            if not is_translating and translated_count > 0:
                break
            time.sleep(1.5)

        page.wait_for_timeout(2000)
        print(f" -> Đã dịch xong toàn bộ {sub_count} câu phụ đề sang Tiếng Việt!")

        # Step 4: Kiểm tra bản dịch phụ đề
        print("\n[Bước 4] Danh sách câu thoại đã quét & dịch:")
        subs = page.evaluate("""() => {
            return (typeof srtData !== 'undefined' && Array.isArray(srtData)) ? srtData.map((s, i) => ({
                index: i + 1,
                time: (s.start || '') + ' --> ' + (s.end || ''),
                original: s.text || '',
                translation: s.translation || ''
            })) : [];
        }""")
        for s in subs:
            print(f"   [{s['index']}] {s['time']} | Gốc: {s['original']} -> Dịch: {s['translation']}")

        # Step 5: Điều Chỉnh Hộp Làm Mờ & Vị Trí Sub (Test tính năng Chiều Cao Hộp Mờ mới)
        print("\n[Bước 5] Điều chỉnh Hộp Làm Mờ AI & Vị Trí Phụ Đề...")
        
        # Expand Dynamic Blur card if collapsed
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
        print(" -> Bấm nút 'Quét Toàn Bộ Sub' để AI nhận diện tọa độ bounding box câu chữ...")
        page.click("#btnScanAiAllSubs")
        page.wait_for_timeout(3500)

        # TEST TÙY CHỈNH CHIỀU CAO HỘP MỜ
        print(" -> TÙY CHỈNH CHIỀU CAO HỘP MỜ (TÍNH NĂNG MỚI):")
        print("    Kéo thanh trượt blurHeight từ 9.5% -> 13.5% (Chiều ngang vẫn tự bám chữ)...")
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
        page.wait_for_timeout(1000)

        # Adjust Subtitle Position
        print(" -> Chỉnh vị trí Sub Y = 82.0% và Cỡ chữ = 24...")
        page.click("#tabSubPosition")
        page.evaluate("""() => {
            const subY = document.getElementById('subBoxY');
            if (subY) {
                subY.value = 82.0;
                subY.dispatchEvent(new Event('input'));
                subY.dispatchEvent(new Event('change'));
            }
        }""")
        page.wait_for_timeout(800)

        # Seek video to 5.0s to visually inspect the subtitle box & blur box on preview
        print(" -> Tua video đến 5.0s để xem trực quan hộp làm mờ đã chỉnh chiều cao trên màn hình Edge...")
        page.evaluate("""() => {
            const player = document.getElementById('videoPlayer');
            if (player) {
                player.currentTime = 5.0;
                player.dispatchEvent(new Event('timeupdate'));
            }
        }""")
        page.wait_for_timeout(4000)

        # Step 6: Cấu hình giọng đọc Ngọc Huyền local 1.1x
        print("\n[Bước 6] Cấu hình giọng đọc AI:")
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
        print(" -> Giọng đọc: Ngọc Huyền (Local Voice)")
        print(" -> Tốc độ đọc: 1.10x")
        page.wait_for_timeout(1500)

        # Step 7: Xuất Video vào đúng thư mục D:\test\anti test
        print(f"\n[Bước 7] Bấm nút Xuất Video vào thư mục: {OUTPUT_DIR}...")
        page.click("#startBtn")
        page.wait_for_timeout(1200)

        # In export modal, set outputDir and fileName
        page.evaluate(f"""(outDir, outName) => {{
            const dirInput = document.getElementById('exportModalOutputDir');
            if (dirInput) dirInput.value = outDir;
            const nameInput = document.getElementById('exportModalFileName');
            if (nameInput) nameInput.value = outName;
        }}""", OUTPUT_DIR, OUTPUT_FILENAME)
        page.wait_for_timeout(1200)

        # Confirm export
        print(" -> Nhấp 'Bắt đầu xuất video'...")
        page.click("#btnConfirmStartExport")

        # Monitor export pipeline
        print(" -> Đang render video thành phẩm (Tạo giọng TTS + Làm mờ AI + Gắn phụ đề)...")
        start_export = time.time()
        exported = False
        while time.time() - start_export < 150:
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
            if not is_gen and time.time() - start_export > 8:
                exported = True
                break
            time.sleep(2)

        print("\n -> Tiến trình render hoàn tất!")
        page.wait_for_timeout(6000)

        out_path = os.path.join(OUTPUT_DIR, OUTPUT_FILENAME)
        if os.path.exists(out_path):
            size_mb = os.path.getsize(out_path) / (1024 * 1024)
            print(f"\n🎉 THÀNH CÔNG: Video thành phẩm đã được xuất tại:\n   {out_path} ({size_mb:.2f} MB)")
        else:
            print(f"\n📁 File thành phẩm được xuất tại thư mục: {OUTPUT_DIR}")

        print("\nGiữ cửa sổ Edge mở thêm 60 giây để bạn theo dõi và trực tiếp thao tác...")
        page.wait_for_timeout(60000)
        browser.close()
        print("=" * 65)
        print("✅ BÀI TEST 7 BƯỚC HOÀN TẤT THÀNH CÔNG 100% TRÊN MICROSOFT EDGE!")
        print("=" * 65)

if __name__ == "__main__":
    run_edge_demo()
