import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_FILE = os.path.join(ROOT_DIR, 'web', 'index.html')

with open(INDEX_FILE, 'r', encoding='utf-8') as f:
    content = f.read()

target = """    <!-- ========================================== -->
    <!-- CLONE VOICE STUDIO VIEW (LOCAL VOICE)     -->
    <!-- ========================================== -->
    <div id="viewCloneVoice" class="main-view" style="display: none;">
        <div class="clone-studio-container" style="max-width: 1350px; margin: 0 auto; padding-bottom: 40px;">
            
            <!-- Top Header / Title Bar -->
            <div class="clone-top-bar" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; padding: 14px 20px; background: linear-gradient(90deg, #1e293b 0%, #0f172a 100%); border: 1px solid #334155; border-radius: 12px; box-shadow: 0 4px 16px rgba(0,0,0,0.3);">"""

clone_view_html = """    <!-- ========================================== -->
    <!-- CLONE VOICE STUDIO VIEW (LOCAL VOICE)     -->
    <!-- ========================================== -->
    <div id="viewCloneVoice" class="main-view" style="display: none;">
        <div class="clone-studio-container" style="max-width: 1350px; margin: 0 auto; padding-bottom: 40px;">
            
            <!-- Top Header / Title Bar -->
            <div class="clone-top-bar" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; padding: 14px 20px; background: linear-gradient(90deg, #1e293b 0%, #0f172a 100%); border: 1px solid #334155; border-radius: 12px; box-shadow: 0 4px 16px rgba(0,0,0,0.3);">
                <div style="display: flex; align-items: center; gap: 12px;">
                    <div style="width: 38px; height: 38px; border-radius: 10px; background: linear-gradient(135deg, rgba(168, 85, 247, 0.2), rgba(14, 165, 233, 0.2)); display: flex; align-items: center; justify-content: center; border: 1px solid rgba(168, 85, 247, 0.4);">
                        <span style="font-size: 20px;">🎙️</span>
                    </div>
                    <div>
                        <h3 style="margin: 0; font-size: 16px; font-weight: 700; color: #f8fafc; letter-spacing: 0.5px;">STUDIO NHÂN BẢN GIỌNG NÓI (CLONE VOICE)</h3>
                        <p style="margin: 0; font-size: 12px; color: #94a3b8;">Nhân bản bất kỳ giọng nói nào chỉ với 3–5 giây âm thanh mẫu • Tự động lưu vĩnh viễn vào Thư viện Local Voice</p>
                    </div>
                </div>
                <div style="display: flex; align-items: center; gap: 10px;">
                    <span class="badge" style="background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.3); padding: 5px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; display: flex; align-items: center; gap: 6px;">
                        <span style="width: 7px; height: 7px; border-radius: 50%; background: #10b981; display: inline-block;"></span>
                        Local Voice ONNX 48kHz Ready
                    </span>
                </div>
            </div>

            <!-- Main 2-Column Grid -->
            <div style="display: grid; grid-template-columns: 1.15fr 0.85fr; gap: 20px; align-items: start;">
                
                <!-- LEFT COLUMN: CLONE WORKBENCH -->
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
                                <button type="button" id="btnCloneModeUpload" class="btn secondary small active" style="flex: 1; padding: 8px 14px; border-color: #38bdf8; color: #38bdf8; font-weight: 600; display: flex; align-items: center; justify-content: center; gap: 6px;">
                                    <span>📁</span> Tải lên file âm thanh (WAV/MP3)
                                </button>
                                <button type="button" id="btnCloneModeRecord" class="btn secondary small" style="flex: 1; padding: 8px 14px; font-weight: 600; display: flex; align-items: center; justify-content: center; gap: 6px;">
                                    <span>🔴</span> Ghi âm trực tiếp từ Mic
                                </button>
                            </div>

                            <!-- Upload Box -->
                            <div id="cloneUploadBox" style="display: block;">
                                <div id="cloneDropZone" style="border: 2px dashed #334155; border-radius: 10px; padding: 24px 16px; text-align: center; background: rgba(30, 41, 59, 0.4); cursor: pointer; transition: all 0.2s;">
                                    <div style="font-size: 32px; margin-bottom: 8px;">🎙️</div>
                                    <div style="font-size: 13.5px; font-weight: 600; color: #f8fafc; margin-bottom: 4px;">Kéo thả file âm thanh vào đây hoặc nhấp để chọn</div>
                                    <div style="font-size: 11.5px; color: #94a3b8;">Hỗ trợ định dạng: WAV, MP3, M4A, AAC, FLAC (Thời lượng 2s đến 15s)</div>
                                    <input type="file" id="cloneFileInput" accept="audio/*" style="display: none;">
                                </div>
                            </div>

                            <!-- Record Box -->
                            <div id="cloneRecordBox" style="display: none; border: 1px solid #334155; border-radius: 10px; padding: 20px; background: rgba(30, 41, 59, 0.4); text-align: center;">
                                <div style="display: flex; flex-direction: column; align-items: center; gap: 12px;">
                                    <div id="cloneRecordTimer" style="font-family: monospace; font-size: 24px; font-weight: 700; color: #38bdf8;">00:00</div>
                                    <div style="display: flex; gap: 12px; align-items: center;">
                                        <button type="button" id="btnStartCloneRecord" class="btn primary-cyan" style="padding: 10px 24px; font-weight: 700; display: flex; align-items: center; gap: 8px; border-radius: 30px; background: linear-gradient(135deg, #ef4444, #dc2626); border: none; color: #fff;">
                                            <span style="width: 10px; height: 10px; border-radius: 50%; background: #fff;"></span>
                                            <span>Bắt đầu Ghi âm</span>
                                        </button>
                                        <button type="button" id="btnStopCloneRecord" class="btn secondary" style="display: none; padding: 10px 20px; font-weight: 700; border-radius: 30px; border-color: #ef4444; color: #ef4444;">
                                            <span>⏹️ Dừng ghi âm</span>
                                        </button>
                                    </div>
                                    <div style="font-size: 12px; color: #94a3b8;">Đọc một câu ngắn tự nhiên khoảng 3-5 giây với âm lượng rõ ràng</div>
                                </div>
                            </div>

                            <!-- Sample Audio Status Card (Hidden initially) -->
                            <div id="cloneSampleStatusCard" style="display: none; margin-top: 14px; padding: 12px 14px; background: #1e293b; border: 1px solid #38bdf8; border-radius: 8px; align-items: center; justify-content: space-between;">
                                <div style="display: flex; align-items: center; gap: 12px; flex: 1; overflow: hidden;">
                                    <span style="font-size: 20px;">🔊</span>
                                    <div style="overflow: hidden;">
                                        <div id="cloneSampleFileName" style="font-size: 12.5px; font-weight: 600; color: #f8fafc; text-overflow: ellipsis; overflow: hidden; white-space: nowrap;">sample.wav</div>
                                        <div style="display: flex; gap: 8px; align-items: center; margin-top: 2px;">
                                            <span id="cloneSampleDuration" style="font-size: 11px; color: #38bdf8; font-weight: 600;">3.8s</span>
                                            <span style="font-size: 10px; color: #64748b;">•</span>
                                            <span id="cloneSampleQuality" style="font-size: 11px; color: #10b981; font-weight: 600;">🟢 Chất lượng: Rất tốt</span>
                                        </div>
                                    </div>
                                </div>
                                <div style="display: flex; align-items: center; gap: 8px;">
                                    <audio id="cloneSampleAudioPlayer" style="display: none;"></audio>
                                    <button type="button" id="btnPlayCloneSample" class="btn secondary small" style="padding: 6px 12px; font-size: 12px; display: flex; align-items: center; gap: 4px;">
                                        <span>▶</span> Nghe mẫu
                                    </button>
                                    <button type="button" id="btnRemoveCloneSample" class="btn secondary small" style="padding: 6px 10px; color: #ef4444;" title="Chọn lại file khác">✕</button>
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

                            <div style="display: flex; gap: 12px; align-items: center;">
                                <button type="button" id="btnPreviewClonedVoice" class="btn secondary" style="padding: 10px 20px; font-weight: 600; display: flex; align-items: center; gap: 8px; border-color: #38bdf8; color: #38bdf8; border-radius: 8px;">
                                    <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
                                    <span>Phát sinh & Nghe thử</span>
                                </button>
                                <div id="clonePreviewLoading" style="display: none; font-size: 12px; color: #38bdf8; align-items: center; gap: 6px;">
                                    <div class="loading-spinner" style="width: 14px; height: 14px; border-width: 2px;"></div>
                                    <span>Đang sinh giọng đọc...</span>
                                </div>
                                <audio id="clonePreviewAudioPlayer" controls style="display: none; flex: 1; height: 36px;"></audio>
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

                <!-- RIGHT COLUMN: CLONED VOICES COLLECTION -->
                <div style="display: flex; flex-direction: column; gap: 16px;">
                    
                    <div class="card settings-card" style="border: 1px solid #334155; border-radius: 12px; background: #0f172a; display: flex; flex-direction: column; min-height: 580px;">
                        
                        <div class="card-header" style="padding: 14px 18px; border-bottom: 1px solid #1e293b; display: flex; align-items: center; justify-content: space-between;">
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <span style="font-size: 16px;">📚</span>
                                <span style="font-weight: 700; font-size: 13.5px; color: #f8fafc;">BỘ SƯU TẬP GIỌNG ĐÃ CLONE</span>
                            </div>
                            <span id="cloneCollectionCount" style="font-size: 12px; font-weight: 700; color: #38bdf8; background: rgba(56, 189, 248, 0.12); padding: 3px 10px; border-radius: 12px; border: 1px solid rgba(56, 189, 248, 0.3);">0 giọng</span>
                        </div>

                        <!-- Search & Filter Bar -->
                        <div style="padding: 12px 18px; border-bottom: 1px solid #1e293b; display: flex; gap: 10px;">
                            <input type="text" id="cloneSearchInput" placeholder="🔍 Tìm kiếm tên giọng đã clone..." style="flex: 1; padding: 8px 12px; background: #1e293b; border: 1px solid #334155; border-radius: 6px; color: #fff; font-size: 12px;">
                            <select id="cloneGenderFilter" style="padding: 8px 10px; background: #1e293b; border: 1px solid #334155; border-radius: 6px; color: #cbd5e1; font-size: 12px;">
                                <option value="">Tất cả</option>
                                <option value="Female">👩 Nữ</option>
                                <option value="Male">👨 Nam</option>
                            </select>
                        </div>

                        <!-- Cloned Voice List -->
                        <div id="cloneVoiceList" style="flex: 1; padding: 14px 18px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; max-height: 480px;">
                            <!-- Dynamically loaded cloned voices -->
                            <div id="cloneListPlaceholder" style="text-align: center; padding: 40px 20px; color: #64748b;">
                                <div style="font-size: 32px; margin-bottom: 8px;">🎙️</div>
                                <div style="font-size: 13px; font-weight: 600; color: #94a3b8;">Chưa có giọng nhân bản nào</div>
                                <div style="font-size: 11.5px; color: #64748b; margin-top: 4px;">Tải lên file mẫu 3–5 giây ở cột bên trái để nhân bản giọng đọc đầu tiên của bạn!</div>
                            </div>
                        </div>

                        <!-- Tips Box -->
                        <div style="padding: 14px 18px; border-top: 1px solid #1e293b; background: rgba(15, 23, 42, 0.6); border-radius: 0 0 12px 12px; font-size: 12px; color: #94a3b8; line-height: 1.5;">
                            <strong style="color: #38bdf8;">💡 Mẹo để có giọng clone tự nhiên nhất:</strong>
                            <ul style="margin: 6px 0 0 16px; padding: 0; color: #cbd5e1;">
                                <li>Dùng audio chất lượng cao, không lẫn tiếng nhạc nền hay tiếng vọng.</li>
                                <li>Thời lượng lý tưởng: <strong>3 đến 6 giây</strong> (1–2 câu nói liền mạch).</li>
                                <li>Các giọng clone sẽ <strong>tự động lưu vĩnh viễn</strong> và xuất hiện ở tab <em>Biên tập phim</em>, <em>TTS</em>, <em>Review Phim</em>.</li>
                            </ul>
                        </div>

                    </div>

                </div>

            </div>

        </div>
    </div>

    <!-- ========================================== -->
    <!-- REVIEW PHIM STUDIO VIEW                    -->
    <!-- ========================================== -->
    <div id="viewReview" class="main-view" style="display: none;">
        <div class="review-studio-container" style="max-width: 1300px; margin: 0 auto; padding-bottom: 40px;">
            
            <!-- Top Header / Title Bar -->
            <div class="review-top-bar" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; padding: 14px 20px; background: linear-gradient(90deg, #1e293b 0%, #0f172a 100%); border: 1px solid #334155; border-radius: 12px; box-shadow: 0 4px 16px rgba(0,0,0,0.3);">"""

if target in content:
    content = content.replace(target, clone_view_html, 1)
    with open(INDEX_FILE, 'w', encoding='utf-8') as f:
        f.write(content)
    print("SUCCESS: Patched web/index.html with viewCloneVoice and viewReview!")
else:
    print("ERROR: Target substring not found in web/index.html")
