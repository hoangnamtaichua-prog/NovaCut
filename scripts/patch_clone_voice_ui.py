import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_FILE = os.path.join(ROOT_DIR, 'web', 'index.html')

with open(INDEX_FILE, 'r', encoding='utf-8') as f:
    content = f.read()

old_card1_start = '<!-- Step 1 Card: Sample Audio -->'
old_card3_end = '<!-- Step 3 Card: Preview Test & Save -->'

# Find the left column content inside viewCloneVoice
start_marker = '<!-- LEFT COLUMN: CLONE WORKBENCH -->'
end_marker = '<!-- RIGHT COLUMN: CLONED VOICES COLLECTION -->'

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx == -1 or end_idx == -1:
    print("Markers not found!")
    exit(1)

new_left_col = '''<!-- LEFT COLUMN: CLONE WORKBENCH -->
                <div style="display: flex; flex-direction: column; gap: 16px;">
                    
                    <!-- Step 1 Card: Sample Audio -->
                    <div class="card settings-card" style="border: 1px solid #334155; border-radius: 12px; background: #0f172a;">
                        <div class="card-header" style="padding: 12px 18px; border-bottom: 1px solid #1e293b; display: flex; align-items: center; justify-content: space-between;">
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <span style="font-size: 16px;">🎵</span>
                                <span style="font-weight: 700; font-size: 13.5px; color: #f8fafc;">1. ÂM THANH MẪU (3 - 5 GIÂY)</span>
                            </div>
                            <span style="font-size: 11px; color: #94a3b8;">Tối ưu: 3–6s • Không nhạc nền</span>
                        </div>
                        <div class="card-body" style="padding: 18px;">
                            
                            <!-- Mode Switcher: Upload vs Record -->
                            <div style="display: flex; gap: 10px; margin-bottom: 14px;">
                                <button type="button" id="btnCloneModeUpload" class="btn secondary small active" style="flex: 1; padding: 9px 14px; border-color: #38bdf8; color: #38bdf8; font-weight: 600; display: flex; align-items: center; justify-content: center; gap: 6px;">
                                    <span>📁</span> Tải lên file âm thanh (WAV/MP3)
                                </button>
                                <button type="button" id="btnCloneModeRecord" class="btn secondary small" style="flex: 1; padding: 9px 14px; font-weight: 600; display: flex; align-items: center; justify-content: center; gap: 6px;">
                                    <span>🔴</span> Ghi âm trực tiếp từ Mic
                                </button>
                            </div>

                            <!-- Hidden file input placed outside dropzone to prevent double trigger -->
                            <input type="file" id="cloneFileInput" accept="audio/*,.wav,.mp3,.m4a,.aac,.flac,.ogg,.webm" style="display: none;">

                            <!-- Upload Box -->
                            <div id="cloneUploadBox" style="display: block;">
                                <div id="cloneDropZone" style="border: 2px dashed #334155; border-radius: 10px; padding: 26px 16px; text-align: center; background: rgba(30, 41, 59, 0.4); cursor: pointer; transition: all 0.2s;">
                                    <div style="font-size: 32px; margin-bottom: 8px;">🎙️</div>
                                    <div style="font-size: 14px; font-weight: 600; color: #f8fafc; margin-bottom: 4px;">Kéo thả file âm thanh vào đây hoặc nhấp để chọn</div>
                                    <div style="font-size: 12px; color: #94a3b8;">Hỗ trợ định dạng: WAV, MP3, M4A, AAC, FLAC, OGG, WEBM (Thời lượng 2s đến 15s)</div>
                                    <button type="button" id="btnBrowseCloneFile" class="btn secondary small" style="margin-top: 12px; padding: 6px 16px; border-color: #38bdf8; color: #38bdf8;">📂 Chọn file từ máy tính</button>
                                </div>
                            </div>

                            <!-- Record Box -->
                            <div id="cloneRecordBox" style="display: none; border: 1px solid #334155; border-radius: 10px; padding: 22px; background: rgba(30, 41, 59, 0.4); text-align: center;">
                                <div style="display: flex; flex-direction: column; align-items: center; gap: 12px;">
                                    <div id="cloneRecordPulseCircle" style="width: 50px; height: 50px; border-radius: 50%; background: rgba(239, 68, 68, 0.15); border: 2px solid #ef4444; display: flex; align-items: center; justify-content: center; font-size: 22px;">
                                        🎙️
                                    </div>
                                    <div id="cloneRecordTimer" style="font-family: monospace; font-size: 26px; font-weight: 700; color: #38bdf8;">00:00</div>
                                    <div style="display: flex; gap: 12px; align-items: center;">
                                        <button type="button" id="btnStartCloneRecord" class="btn primary-cyan" style="padding: 10px 24px; font-weight: 700; display: flex; align-items: center; gap: 8px; border-radius: 30px; background: linear-gradient(135deg, #ef4444, #dc2626); border: none; color: #fff; box-shadow: 0 4px 14px rgba(239, 68, 68, 0.4);">
                                            <span style="width: 10px; height: 10px; border-radius: 50%; background: #fff;"></span>
                                            <span>Bắt đầu Ghi âm</span>
                                        </button>
                                        <button type="button" id="btnStopCloneRecord" class="btn secondary" style="display: none; padding: 10px 22px; font-weight: 700; border-radius: 30px; border-color: #ef4444; color: #ef4444; background: rgba(239, 68, 68, 0.1);">
                                            <span>⏹️ Dừng & Sử dụng mẫu này</span>
                                        </button>
                                    </div>
                                    <div id="cloneRecordHelpText" style="font-size: 12px; color: #94a3b8;">Đọc một câu ngắn tự nhiên khoảng 3-5 giây với âm lượng rõ ràng</div>
                                </div>
                            </div>

                            <!-- Sample Audio Status Card with Immediate Native Audio Player -->
                            <div id="cloneSampleStatusCard" style="display: none; margin-top: 16px; padding: 14px 16px; background: #131d31; border: 1px solid #38bdf8; border-radius: 10px; flex-direction: column; gap: 10px;">
                                <div style="display: flex; align-items: center; justify-content: space-between;">
                                    <div style="display: flex; align-items: center; gap: 10px; overflow: hidden;">
                                        <span style="font-size: 20px;">🎧</span>
                                        <div>
                                            <div id="cloneSampleFileName" style="font-size: 13px; font-weight: 700; color: #f8fafc; text-overflow: ellipsis; overflow: hidden; white-space: nowrap;">sample.wav</div>
                                            <div style="display: flex; gap: 8px; align-items: center; margin-top: 2px;">
                                                <span id="cloneSampleDuration" style="font-size: 11.5px; color: #38bdf8; font-weight: 600;">3.8s</span>
                                                <span style="font-size: 10px; color: #64748b;">•</span>
                                                <span id="cloneSampleQuality" style="font-size: 11.5px; color: #10b981; font-weight: 600;">🟢 Chất lượng: Rất tốt</span>
                                            </div>
                                        </div>
                                    </div>
                                    <button type="button" id="btnRemoveCloneSample" class="btn secondary small" style="padding: 5px 12px; color: #ef4444; border-color: #ef4444;" title="Chọn lại file khác">🔄 Chọn / Thu lại</button>
                                </div>
                                <div style="margin-top: 4px;">
                                    <audio id="cloneSampleAudioPlayer" controls style="width: 100%; height: 38px; border-radius: 6px;"></audio>
                                </div>
                            </div>

                        </div>
                    </div>

                    <!-- Step 2 Card: Voice Metadata -->
                    <div class="card settings-card" style="border: 1px solid #334155; border-radius: 12px; background: #0f172a;">
                        <div class="card-header" style="padding: 12px 18px; border-bottom: 1px solid #1e293b; display: flex; align-items: center; gap: 8px;">
                            <span style="font-size: 16px;">🏷️</span>
                            <span style="font-weight: 700; font-size: 13.5px; color: #f8fafc;">2. THÔNG TIN ĐỊNH DANH GIỌNG NÓI</span>
                        </div>
                        <div class="card-body" style="padding: 18px; display: flex; flex-direction: column; gap: 14px;">
                            
                            <div class="form-group">
                                <label style="font-size: 12px; font-weight: 600; color: #cbd5e1; margin-bottom: 5px; display: block;">Tên hiển thị của giọng <span style="color: #ef4444;">*</span></label>
                                <input type="text" id="cloneVoiceName" class="text-input" placeholder="Ví dụ: Giọng Review Phim Đêm Khuya, Idol Nam Thần, Giọng Kể Chuyện..." style="width: 100%; padding: 10px 14px; background: #1e293b; border: 1px solid #334155; border-radius: 8px; color: #fff; font-size: 13px;">
                            </div>

                            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px;">
                                <div class="form-group">
                                    <label style="font-size: 12px; font-weight: 600; color: #cbd5e1; margin-bottom: 5px; display: block;">Giới tính</label>
                                    <select id="cloneVoiceGender" class="text-input" style="width: 100%; padding: 9px 12px; background: #1e293b; border: 1px solid #334155; border-radius: 8px; color: #fff; font-size: 12.5px;">
                                        <option value="Female" selected>👩 Nữ</option>
                                        <option value="Male">👨 Nam</option>
                                    </select>
                                </div>
                                <div class="form-group">
                                    <label style="font-size: 12px; font-weight: 600; color: #cbd5e1; margin-bottom: 5px; display: block;">Vùng miền</label>
                                    <select id="cloneVoiceRegion" class="text-input" style="width: 100%; padding: 9px 12px; background: #1e293b; border: 1px solid #334155; border-radius: 8px; color: #fff; font-size: 12.5px;">
                                        <option value="Miền Bắc" selected>Miền Bắc</option>
                                        <option value="Miền Nam">Miền Nam</option>
                                        <option value="Miền Trung">Miền Trung</option>
                                        <option value="US English">US English</option>
                                    </select>
                                </div>
                                <div class="form-group">
                                    <label style="font-size: 12px; font-weight: 600; color: #cbd5e1; margin-bottom: 5px; display: block;">Phong cách</label>
                                    <select id="cloneVoiceStyle" class="text-input" style="width: 100%; padding: 9px 12px; background: #1e293b; border: 1px solid #334155; border-radius: 8px; color: #fff; font-size: 12.5px;">
                                        <option value="review" selected>🎬 Review phim</option>
                                        <option value="story">🎙️ Kể chuyện</option>
                                        <option value="news">📰 Thời sự</option>
                                        <option value="emotional">💖 Tình cảm</option>
                                    </select>
                                </div>
                            </div>

                        </div>
                    </div>

                    <!-- Step 3 Card: Preview Test & Save -->
                    <div class="card settings-card" style="border: 1px solid #334155; border-radius: 12px; background: #0f172a;">
                        <div class="card-header" style="padding: 12px 18px; border-bottom: 1px solid #1e293b; display: flex; align-items: center; justify-content: space-between;">
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <span style="font-size: 16px;">🔊</span>
                                <span style="font-weight: 700; font-size: 13.5px; color: #f8fafc;">3. NGHE THỬ PHÁT ÂM & LƯU THƯ VIỆN</span>
                            </div>
                            <span style="font-size: 11px; color: #38bdf8; font-weight: 600;">⚡ Test tức thì (~0.8s)</span>
                        </div>
                        <div class="card-body" style="padding: 18px; display: flex; flex-direction: column; gap: 14px;">
                            
                            <div class="form-group">
                                <label style="font-size: 12px; font-weight: 600; color: #cbd5e1; margin-bottom: 5px; display: block;">Câu văn bản đọc thử nghiệm</label>
                                <textarea id="cloneTestText" class="text-input" rows="2" style="width: 100%; padding: 10px 14px; background: #1e293b; border: 1px solid #334155; border-radius: 8px; color: #fff; font-size: 13px; resize: vertical;">Xin chào! Đây là bản nghe thử chất lượng nhân bản giọng nói chuẩn phòng thu bằng Local Voice.</textarea>
                            </div>

                            <div>
                                <button type="button" id="btnPreviewClonedVoice" class="btn secondary" style="width: 100%; padding: 12px 20px; font-weight: 700; display: flex; align-items: center; justify-content: center; gap: 8px; border-color: #38bdf8; color: #38bdf8; border-radius: 8px; background: rgba(56, 189, 248, 0.08);">
                                    <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
                                    <span>PHÁT SINH & NGHE THỬ GIỌNG ĐỌC</span>
                                </button>
                            </div>

                            <!-- Real-time Process & Log Console for Preview -->
                            <div id="cloneProcessLogBox" style="display: none; background: #0b1120; border: 1px solid #1e293b; border-radius: 8px; padding: 12px 14px; font-family: monospace; font-size: 12px; color: #94a3b8; line-height: 1.6;">
                                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; border-bottom: 1px solid #1e293b; padding-bottom: 4px;">
                                    <span style="font-weight: 700; color: #38bdf8; display: flex; align-items: center; gap: 6px;">
                                        <span class="loading-spinner" id="cloneLogSpinner" style="width: 12px; height: 12px; border-width: 2px;"></span>
                                        <span id="cloneProcessTitle">TIẾN TRÌNH XỬ LÝ</span>
                                    </span>
                                    <span id="cloneProcessPct" style="font-size: 11px; color: #10b981; font-weight: 700;">0%</span>
                                </div>
                                <div id="cloneProcessLogLines" style="max-height: 120px; overflow-y: auto; display: flex; flex-direction: column; gap: 3px;">
                                </div>
                            </div>

                            <!-- Preview Result Audio Player -->
                            <div id="clonePreviewResultContainer" style="display: none; background: #131d31; border: 1px solid #10b981; border-radius: 8px; padding: 12px 14px;">
                                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                                    <span style="font-size: 12.5px; font-weight: 700; color: #10b981;">✅ Bản nghe thử đã tạo thành công (48kHz)</span>
                                </div>
                                <audio id="clonePreviewAudioPlayer" controls style="width: 100%; height: 38px; border-radius: 6px;"></audio>
                            </div>

                            <div style="border-top: 1px solid #1e293b; padding-top: 16px; margin-top: 6px;">
                                <button type="button" id="btnSaveClonedVoice" class="btn primary-cyan" style="width: 100%; padding: 14px; font-size: 15px; font-weight: 700; display: flex; align-items: center; justify-content: center; gap: 10px; border-radius: 8px; background: linear-gradient(135deg, #a855f7, #0ea5e9); border: none; color: #fff; box-shadow: 0 4px 15px rgba(168, 85, 247, 0.35);">
                                    <svg viewBox="0 0 24 24" width="18" height="18" stroke="currentColor" stroke-width="2" fill="none"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"></path><polyline points="17 21 17 13 7 13 7 21"></polyline><polyline points="7 3 7 8 15 8"></polyline></svg>
                                    <span>LƯU VĨNH VIỄN VÀO THƯ VIỆN GIỌNG NÓI</span>
                                </button>
                            </div>

                        </div>
                    </div>

                </div>

                '''

new_content = content[:start_idx] + new_left_col + content[end_idx:]

with open(INDEX_FILE, 'w', encoding='utf-8') as f:
    f.write(new_content)

print("SUCCESS: Updated left column of viewCloneVoice in index.html!")
